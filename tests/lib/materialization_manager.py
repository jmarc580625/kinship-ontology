"""
MaterializationManager: Retrieves SPARQL materialization scripts, declared
entities and inverse-property pairs directly from the triple-store backend,
validates entity references, computes execution order by dependency analysis,
and drives materialization via the same backend.

The backend must be fully initialised (ontology loaded) before passing it to
this class.  No ontology file is read directly — all metadata is queried via
SPARQL SELECT.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SPARQL queries executed against the backend
# ---------------------------------------------------------------------------

# Namespace-independent bootstrap: every well-formed OWL ontology declares
# itself with  ?onto a owl:Ontology .  The namespace is derived from that URI
# (appending '#' when the URI has no trailing separator).  The FILTER excludes
# W3C-vocabulary URIs that OWL-RL reasoning may produce as side-effects.
_Q_DETECT_NS = """\
PREFIX owl: <http://www.w3.org/2002/07/owl#>
SELECT ?onto WHERE {
    ?onto a owl:Ontology .
    FILTER(ISIRI(?onto))
    FILTER(!STRSTARTS(STR(?onto), "http://www.w3.org/"))
}
LIMIT 1"""

# Retrieve every property that carries a materialization script, together with
# its optional reason annotation.
_Q_SCRIPTS = """\
PREFIX : <{ns}>
SELECT ?property ?script ?reason WHERE {{
    ?property :MaterializationScript ?script .
    OPTIONAL {{ ?property :MaterializationReason ?reason . }}
}}"""

# Collect every subject URI declared within the kinship namespace.  Used to
# validate that script predicates / class references actually exist.
_Q_DECLARED = """\
PREFIX : <{ns}>
SELECT DISTINCT ?entity WHERE {{
    ?entity ?p ?o .
    FILTER(STRSTARTS(STR(?entity), "{ns}"))
}}"""

# Retrieve all owl:inverseOf pairs within the kinship namespace so that
# dependency analysis can follow inverse edges between properties.
_Q_INVERSES = """\
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX : <{ns}>
SELECT ?prop ?inverse WHERE {{
    ?prop owl:inverseOf ?inverse .
    FILTER(STRSTARTS(STR(?prop),    "{ns}"))
    FILTER(STRSTARTS(STR(?inverse), "{ns}"))
}}"""

# Retrieve all rdfs:subPropertyOf pairs within the kinship namespace.
# Used to detect indirect materialization dependencies: when a WHERE clause
# references a super-property P, triples for P may come from a sub-property Q
# whose chain axiom (or whose inverse's chain) involves an active mat-target.
_Q_SUBPROPS = """\
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?sub ?super WHERE {{
    ?sub rdfs:subPropertyOf ?super .
    FILTER(STRSTARTS(STR(?sub),   "{ns}"))
    FILTER(STRSTARTS(STR(?super), "{ns}"))
}}"""

# Retrieve all owl:propertyChainAxiom members within the kinship namespace.
# Used to detect indirect materialization dependencies: when a WHERE clause
# references a property that is itself derived from a chain whose links are
# (or whose inverses are) active materialization targets.
_Q_CHAINS = """\
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
SELECT ?prop ?chain_member WHERE {{
    ?prop owl:propertyChainAxiom ?list .
    ?list rdf:rest*/rdf:first ?chain_member .
    FILTER(STRSTARTS(STR(?prop),         "{ns}"))
    FILTER(STRSTARTS(STR(?chain_member), "{ns}"))
}}"""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScriptEntry:
    """One materialization script retrieved from the triple store."""

    property_uri: str
    local_name: str
    script: str
    reason: Optional[str] = None
    dependencies: Set[str] = field(default_factory=set)

    def __repr__(self) -> str:
        return f"ScriptEntry({self.local_name!r}, deps={sorted(self.dependencies)})"


@dataclass
class ValidationIssue:
    """A single issue found during ontology-script consistency check."""

    severity: str        # "error" | "warning"
    property_name: str   # local name of the property whose script has the issue
    entity: str          # the referenced entity that is problematic
    message: str
    ignore_script: bool = False  # if True the script is excluded from execution

    def __str__(self) -> str:
        suffix = " [script ignored]" if self.ignore_script else ""
        return f"[{self.severity.upper()}] {self.property_name}: {self.message}{suffix}"


class CyclicDependencyError(Exception):
    """Raised when a dependency cycle is detected among materialization scripts."""


class ValidationError(Exception):
    """Raised when critical (error-severity) validation issues are found."""


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class MaterializationManager:
    """
    Queries :MaterializationScript annotations from the loaded triple store,
    validates entity references, resolves execution order by dependency
    analysis, and drives materialization via the same backend.

    Backend contract (duck-typed):
        execute_query(sparql: str)  -> list[dict[str, str]]
            Execute a SPARQL SELECT/ASK query and return result bindings.
        execute_update(sparql: str) -> int | None
            Execute a SPARQL UPDATE query; return number of triples added
            (or None / 0 when the backend does not report a count).

    Raises:
        RuntimeError           – if the backend cannot be queried.
        ValidationError        – if error-severity entity references are undefined.
        CyclicDependencyError  – if a dependency cycle is detected.
    """

    # Matches :localName tokens that are either has-properties or capitalised
    # class names (e.g. :FemalePerson, :Male).  The negative look-behind
    # prevents matching other prefixed names (owl:Thing, http://...).
    _ENTITY_RE = re.compile(r"(?<![:\w/]):(has[A-Za-z]+|[A-Z][A-Za-z]+)")

    def __init__(self, backend: Any, *, namespace: Optional[str] = None,
                 script_priority: Optional[Dict[str, int]] = None) -> None:
        """
        Initialise the manager.  The backend must already be initialised
        and have the ontology (and any data) loaded.

        Args:
            backend:   Initialised backend instance (RDFLibBackend, GraphDBBackend,
                       or any object that satisfies the duck-typed contract above).
            namespace: Optional explicit ontology namespace URI (e.g.
                       ``"http://example.org/kinship#"``).  When omitted the
                       namespace is auto-detected from the ``owl:Ontology``
                       declaration in the triple store.  Useful when loading a
                       modular ontology whose module IRI differs from the
                       property namespace.
        """
        self.backend = backend
        self._script_priority: Dict[str, int] = script_priority or {}

        # --- Step 1: resolve namespace ---
        if namespace:
            ns = namespace if (namespace.endswith("#") or namespace.endswith("/")) else namespace + "#"
            self._ns: str = ns
            log.info("Using supplied ontology namespace: %s", self._ns)
        else:
            # Auto-detect from owl:Ontology declaration
            rows = self._query(_Q_DETECT_NS)
            if not rows:
                raise RuntimeError(
                    "Cannot detect ontology namespace: no owl:Ontology declaration "
                    "found in the triple store. "
                    "Ensure the backend is initialised with the ontology loaded."
                )
            uri = rows[0].get("onto", "")
            if not uri:
                raise RuntimeError("owl:Ontology declaration returned an empty IRI.")
            # Append '#' when the ontology URI has no trailing namespace separator.
            self._ns = uri if (uri.endswith("#") or uri.endswith("/")) else uri + "#"
            log.info("Detected ontology namespace: %s", self._ns)
        self._prefix_header: str = f"PREFIX : <{self._ns}>\n"

        # --- Step 2: retrieve scripts from the triple store ---
        self._scripts: Dict[str, ScriptEntry] = self._fetch_scripts()
        log.info("Retrieved %d materialization scripts from backend", len(self._scripts))

        # --- Step 3: retrieve declared entities for validation ---
        self._declared: Set[str] = self._fetch_declared_entities()
        log.debug("Declared ontology entities: %d", len(self._declared))

        # --- Step 4: retrieve inverse map (needed by Principle 2 validation) ---
        self._inverse_map: Dict[str, str] = self._fetch_inverse_map()

        # --- Step 4b: retrieve property chain map (for Rule 3 indirect deps) ---
        self._chain_map: Dict[str, List[str]] = self._fetch_chain_map()

        # --- Step 4c: retrieve sub-property map (for Rule 4 indirect deps) ---
        self._subprop_map: Dict[str, List[str]] = self._fetch_subprop_map()

        # --- Step 5: validate (entity refs, separation of concern, inverse pairs) ---
        self._issues: List[ValidationIssue] = self._validate()
        self._ignored: Set[str] = {i.property_name for i in self._issues if i.ignore_script}
        if self._ignored:
            log.warning("Scripts ignored due to design-principle violations: %s",
                        sorted(self._ignored))
        errors = [i for i in self._issues if i.severity == "error"]
        if errors:
            detail = "\n".join(f"  {i}" for i in errors)
            raise ValidationError(
                f"Ontology consistency check failed ({len(errors)} error(s)):\n{detail}"
            )
        for issue in self._issues:
            log.warning("%s", issue)

        # --- Step 6: build dependency graph (non-ignored scripts only) ---
        self._build_dependency_graph()

        # --- Step 6b: warn on broken dependencies (active WHERE → ignored predicate) ---
        broken_issues = self._check_broken_dependencies()
        if broken_issues:
            self._issues.extend(broken_issues)
            for issue in broken_issues:
                log.warning("%s", issue)

        # --- Step 7: topological sort (non-ignored scripts only) ---
        self._execution_order: List[str] = self._topological_sort()
        log.info(
            "Execution order (%d scripts): %s",
            len(self._execution_order),
            self._execution_order,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def namespace(self) -> str:
        """Ontology namespace URI detected from the triple store (e.g. 'http://example.org/kinship#')."""
        return self._ns

    @property
    def execution_order(self) -> List[str]:
        """Ordered list of property local-names in dependency-resolved sequence."""
        return list(self._execution_order)

    @property
    def scripts(self) -> Dict[str, ScriptEntry]:
        """Read-only copy of retrieved scripts, keyed by local property name."""
        return dict(self._scripts)

    @property
    def validation_issues(self) -> List[ValidationIssue]:
        """All issues found during consistency check (errors + warnings)."""
        return list(self._issues)

    @property
    def ignored_scripts(self) -> Set[str]:
        """
        Local names of scripts excluded from execution due to design-principle
        violations (separation of concern or inverse-pair duplication).
        """
        return set(self._ignored)

    def execute(self, dry_run: bool = False, on_script=None) -> List[Dict[str, Any]]:
        """
        Execute all materialization scripts in dependency order.

        Each script is wrapped with a PREFIX declaration if one is absent.

        After each successful UPDATE ``backend.trigger_reasoning()`` is called
        so that all OWL inferences (inverses, symmetry, transitivity, subproperty
        propagation, property chains) are available before the next script runs.
        Backends that do not expose ``trigger_reasoning`` (e.g. GraphDB, which
        re-reasons automatically after every INSERT) are skipped silently.

        Args:
            dry_run:     If True, scripts are logged but not sent to the backend.
            on_script:   Optional callable(record) invoked after each script
                         completes, enabling real-time progress reporting.

        Returns:
            List of result records (one per script), each containing:
                - property           (str)       local name of the property
                - reason             (str|None)  why materialization is needed
                - script_preview     (str)       first 120 chars of the SPARQL
                - triples_added      (int)       count reported by backend (0 if N/A)
                - reasoning_triggered (bool)     whether OWL reasoning was fired
                - inferred_triples   (int)       triples added by reasoning (0 if N/A)
                - status             (str)       "ok" | "dry-run" | "error: <msg>"
        """
        results: List[Dict[str, Any]] = []
        _reasoner = getattr(self.backend, "trigger_reasoning", None)

        for local_name in self._execution_order:  # type: ignore[assignment]
            entry = self._scripts[local_name]
            sparql = self._ensure_prefix(entry.script)
            preview = " ".join(sparql.split())[:120]

            record: Dict[str, Any] = {
                "property": local_name,
                "reason": entry.reason,
                "script_preview": preview,
                "triples_added": 0,
                "reasoning_triggered": False,
                "inferred_triples": 0,
                "status": "dry-run" if dry_run else "pending",
            }

            if dry_run:
                log.info("[dry-run] %s", local_name)
            else:
                try:
                    added = self.backend.execute_update(sparql)
                    record["triples_added"] = int(added) if isinstance(added, (int, float)) else 0
                    record["status"] = "ok"
                    log.info("✓ %-30s  +%d triples", local_name, record["triples_added"])

                    if callable(_reasoner):
                        inferred = _reasoner()
                        record["reasoning_triggered"] = True
                        record["inferred_triples"] = int(inferred) if isinstance(inferred, (int, float)) else 0
                        log.info(
                            "  ↳ reasoning pass after :%s  +%d inferred",
                            local_name,
                            record["inferred_triples"],
                        )
                except Exception as exc:
                    record["status"] = f"error: {exc}"
                    log.error("✗ %-30s  %s", local_name, exc)

            results.append(record)
            if callable(on_script):
                on_script(record)

        return results

    def summary(self) -> str:
        """Return a human-readable summary of scripts and their execution order."""
        active_count = len(self._scripts) - len(self._ignored)
        lines = [
            f"MaterializationManager — {len(self._scripts)} scripts "
            f"({active_count} active, {len(self._ignored)} ignored)",
            "",
            "Execution order:",
        ]
        for i, name in enumerate(self._execution_order, 1):
            entry = self._scripts[name]
            deps = sorted(entry.dependencies)
            dep_str = f"  ← {deps}" if deps else ""
            lines.append(f"  {i:2d}. {name}{dep_str}")

        if self._ignored:
            lines += ["", f"Ignored scripts ({len(self._ignored)}):"]
            for name in sorted(self._ignored):
                lines.append(f"  - {name}")

        if self._issues:
            lines += ["", f"Validation issues ({len(self._issues)}):"]
            for issue in self._issues:
                lines.append(f"  {issue}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Backend retrieval helpers
    # ------------------------------------------------------------------

    def _local(self, uri: str) -> Optional[str]:
        """Extract the local name from the ontology-namespace URI, or None."""
        return uri[len(self._ns):] if uri.startswith(self._ns) else None

    def _query(self, sparql: str) -> List[Dict[str, Any]]:
        """Delegate a SPARQL SELECT to the backend and return result rows."""
        try:
            return self.backend.execute_query(sparql)
        except Exception as exc:
            raise RuntimeError(f"Backend query failed: {exc}") from exc

    def _tbox_query(self, sparql: str) -> List[Dict[str, Any]]:
        """
        Run SPARQL against the TBox only (pre-OWL-RL) when the backend
        supports it; fall back to the full graph otherwise.
        """
        tbox_q = getattr(self.backend, "execute_tbox_query", None)
        if callable(tbox_q):
            return tbox_q(sparql)
        return self._query(sparql)

    def _fetch_scripts(self) -> Dict[str, ScriptEntry]:
        """
        Query the backend for all :MaterializationScript annotations and
        return a dict keyed by local property name.
        """
        rows = self._query(_Q_SCRIPTS.format(ns=self._ns))
        scripts: Dict[str, ScriptEntry] = {}

        for row in rows:
            prop_uri = row.get("property", "")
            local_name = self._local(prop_uri)
            if not local_name:
                continue

            script_text = row.get("script", "").strip()
            reason_uri = row.get("reason", "")
            reason = self._local(reason_uri) if reason_uri else None

            scripts[local_name] = ScriptEntry(
                property_uri=prop_uri,
                local_name=local_name,
                script=script_text,
                reason=reason,
            )

        return scripts

    def _fetch_declared_entities(self) -> Set[str]:
        """
        Query the backend for all subjects declared within the kinship namespace.
        Used to validate that entity references inside scripts actually exist.
        """
        rows = self._query(_Q_DECLARED.format(ns=self._ns))
        declared: Set[str] = set()
        for row in rows:
            local_name = self._local(row.get("entity", ""))
            if local_name:
                declared.add(local_name)
        return declared

    def _fetch_inverse_map(self) -> Dict[str, str]:
        """
        Query the backend for owl:inverseOf pairs within the kinship namespace
        and return a bidirectional local-name → inverse local-name map.
        """
        rows = self._query(_Q_INVERSES.format(ns=self._ns))
        inv: Dict[str, str] = {}
        for row in rows:
            s_local = self._local(row.get("prop", ""))
            o_local = self._local(row.get("inverse", ""))
            if s_local and o_local:
                inv[s_local] = o_local
                inv[o_local] = s_local
        return inv

    def _fetch_subprop_map(self) -> Dict[str, List[str]]:
        """
        Query the backend for rdfs:subPropertyOf pairs and return a map
        ``{super_local_name: [sub_local_names]}``.
        """
        rows = self._tbox_query(_Q_SUBPROPS.format(ns=self._ns))
        subprop_map: Dict[str, List[str]] = defaultdict(list)
        for row in rows:
            sub   = self._local(row.get("sub", ""))
            super_ = self._local(row.get("super", ""))
            if sub and super_ and sub not in subprop_map[super_]:
                subprop_map[super_].append(sub)
        return dict(subprop_map)

    def _fetch_chain_map(self) -> Dict[str, List[str]]:
        """
        Query the backend for owl:propertyChainAxiom declarations and return a
        map ``{property_local_name: [chain_member_local_names]}``.
        """
        rows = self._tbox_query(_Q_CHAINS.format(ns=self._ns))
        chain_map: Dict[str, List[str]] = defaultdict(list)
        for row in rows:
            prop  = self._local(row.get("prop", ""))
            member = self._local(row.get("chain_member", ""))
            if prop and member and member not in chain_map[prop]:
                chain_map[prop].append(member)
        return dict(chain_map)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _entities_in(self, text: str) -> Set[str]:
        """Extract all :localName entity tokens present in *text*."""
        return set(self._ENTITY_RE.findall(text))

    def _validate(self) -> List[ValidationIssue]:
        """
        Three checks are applied to every materialization script:

        1. Undeclared entity references
           Warns when a :token in the script has no subject triples in the
           store (potential ontology typo).  Script is kept.

        2. Separation of concern (Principle 1)
           A script annotated for :<Relation> MUST only INSERT triples with
           predicate :<Relation>.  Inserting other predicates is a design violation.
           Script is ignored.

        3. Inverse-pair duplication (Principle 2)
           When :<Relation1> owl:inverseOf :<Relation1>, only ONE side should have a script;
           the other is inferred by the reasoner.  If both sides have scripts,
           both are warned and ignored.
        """
        issues: List[ValidationIssue] = []

        for local_name, entry in self._scripts.items():

            # --- Check 1: undeclared entity references ---
            for entity in sorted(self._entities_in(entry.script)):
                if entity not in self._declared:
                    issues.append(ValidationIssue(
                        severity="warning",
                        property_name=local_name,
                        entity=entity,
                        message=(
                            f"references :{entity} which has no declared "
                            f"subject triples in the triple store"
                        ),
                        ignore_script=False,
                    ))

            # --- Check 2: separation of concern ---
            insert_preds = self._extract_insert_predicates(entry.script)
            foreign = insert_preds - {local_name}
            if foreign:
                issues.append(ValidationIssue(
                    severity="warning",
                    property_name=local_name,
                    entity=", ".join(sorted(foreign)),
                    message=(
                        f"violates separation of concern: INSERT block produces "
                        f"{sorted(foreign)} but script is defined for :{local_name} only"
                    ),
                    ignore_script=True,
                ))

            # --- Check 3: inverse-pair duplication ---
            inv_name = self._inverse_map.get(local_name)
            if inv_name and inv_name in self._scripts:
                issues.append(ValidationIssue(
                    severity="warning",
                    property_name=local_name,
                    entity=inv_name,
                    message=(
                        f"both :{local_name} and its owl:inverseOf :{inv_name} "
                        f"have materialization scripts; only one side should be "
                        f"scripted — the other is inferred by the reasoner"
                    ),
                    ignore_script=True,
                ))

        return issues

    # ------------------------------------------------------------------
    # Dependency resolution
    # ------------------------------------------------------------------

    def _extract_insert_predicates(self, script: str) -> Set[str]:
        """Return entity names found inside the INSERT { … } block."""
        m = re.search(r"\bINSERT\b.*?\{(.*?)\}", script, re.DOTALL | re.IGNORECASE)
        return self._entities_in(m.group(1)) if m else set()

    def _extract_where_entities(self, script: str) -> Set[str]:
        """
        Return entity names found inside the WHERE { … } block.
        Falls back to the whole script if no WHERE clause is found.
        """
        m = re.search(r"\bWHERE\b\s*\{(.+)\}", script, re.DOTALL | re.IGNORECASE)
        return self._entities_in(m.group(1)) if m else self._entities_in(script)

    def _build_dependency_graph(self) -> None:
        """
        Populate ``entry.dependencies`` for every active (non-ignored) script.

        A script B depends on script A when A must have executed before B
        so that B's WHERE clause can find the triples it needs.  Two rules
        are applied:

        Rule 1 – Direct mat-target in WHERE:
            B's WHERE clause contains predicate P, and P is itself a
            materialization target (an active script exists for P).

        Rule 2 – OWL inverse of a mat-target:
            B's WHERE clause uses predicate P, and P is the owl:inverseOf of
            predicate Q that has an active script.  After Q's script runs,
            the reasoner must fire to produce P-triples, so B must wait for
            Q's script regardless.

        Note: a "Rule 2 — INSERT producer" existed previously but is now
        redundant.  Principle 1 (separation of concern) guarantees each
        active script inserts only its own predicate, so produced_by[P]
        equals {P's own script}, which Rule 1 already catches.
        """
        active = {k: v for k, v in self._scripts.items() if k not in self._ignored}
        mat_targets = set(active.keys())

        for local_name, entry in active.items():
            where_ents = self._extract_where_entities(entry.script)
            deps: Set[str] = set()

            for entity in where_ents:
                # Rule 1: predicate is itself an active mat-target
                if entity in mat_targets and entity != local_name:
                    deps.add(entity)

                # Rule 2: predicate is the owl:inverseOf an active mat-target
                inv_entity = self._inverse_map.get(entity)
                if inv_entity and inv_entity in mat_targets and inv_entity != local_name:
                    deps.add(inv_entity)

                # Rule 3: predicate is derived from a property chain whose
                # members (or their inverses) are active mat-targets.
                # Rule 3b: also follow one extra level: if a chain member's
                # inverse itself has a chain axiom, check those nested members.
                # This handles hasCousin = (hasBloodUncleAunt ∘ hasChild) where
                # hasBloodUncleAunt = inverse(hasBloodNibling) and
                # hasBloodNibling = (hasSibling ∘ hasChild).
                for chain_member in self._chain_map.get(entity, []):
                    if chain_member in mat_targets and chain_member != local_name:
                        deps.add(chain_member)
                    inv_cm = self._inverse_map.get(chain_member)
                    if inv_cm and inv_cm in mat_targets and inv_cm != local_name:
                        deps.add(inv_cm)
                    # Rule 3b: nested chain via inverse of this chain member
                    if inv_cm:
                        for cm2 in self._chain_map.get(inv_cm, []):
                            if cm2 in mat_targets and cm2 != local_name:
                                deps.add(cm2)
                            inv_cm2 = self._inverse_map.get(cm2)
                            if inv_cm2 and inv_cm2 in mat_targets and inv_cm2 != local_name:
                                deps.add(inv_cm2)

                # Rule 4: predicate is a super-property populated by sub-properties
                # whose chains (or their inverses' chains) involve mat-targets.
                # Rule 4a (sub-property is itself a mat-target) is intentionally
                # omitted: a super-property may have direct ABox triples that are
                # independent of any scripted sub-property, and including 4a creates
                # false cycles between symmetric pairs (e.g. hasWife ↔ hasHusband).
                for sub_prop in self._subprop_map.get(entity, []):
                    # 4b: sub-property has a chain with mat-target members
                    for cm in self._chain_map.get(sub_prop, []):
                        if cm in mat_targets and cm != local_name:
                            deps.add(cm)
                        inv_cm = self._inverse_map.get(cm)
                        if inv_cm and inv_cm in mat_targets and inv_cm != local_name:
                            deps.add(inv_cm)
                    # 4c: inverse of sub-property has a chain with mat-target members
                    inv_sub = self._inverse_map.get(sub_prop)
                    if inv_sub:
                        for cm in self._chain_map.get(inv_sub, []):
                            if cm in mat_targets and cm != local_name:
                                deps.add(cm)
                            inv_cm = self._inverse_map.get(cm)
                            if inv_cm and inv_cm in mat_targets and inv_cm != local_name:
                                deps.add(inv_cm)

            entry.dependencies = deps
            if deps:
                log.debug("  %s → %s", local_name, sorted(deps))

    def _check_broken_dependencies(self) -> List[ValidationIssue]:
        """
        After the dependency graph is built, warn when an active script's
        WHERE clause references a predicate whose materialization script is
        ignored.

        Such a script will find no triples for the ignored predicate at
        runtime and may therefore produce incomplete or empty results.  The
        script is kept active (``ignore_script=False``) so the user can
        decide whether to fix the ignored script or remove the reference.
        """
        active = {k for k in self._scripts if k not in self._ignored}
        issues: List[ValidationIssue] = []

        for local_name in sorted(active):
            entry = self._scripts[local_name]
            where_ents = self._extract_where_entities(entry.script)
            broken = sorted(where_ents & self._ignored)
            if broken:
                issues.append(ValidationIssue(
                    severity="warning",
                    property_name=local_name,
                    entity=", ".join(broken),
                    message=(
                        f"WHERE clause references {broken} whose "
                        f"materialization script is ignored; "
                        f"this script may produce incomplete results"
                    ),
                    ignore_script=False,
                ))

        return issues

    # ------------------------------------------------------------------
    # Topological sort  (Kahn's algorithm)
    # ------------------------------------------------------------------

    def _topological_sort(self) -> List[str]:
        """
        Return active (non-ignored) scripts in topologically sorted order.

        Scripts at the same dependency depth are sorted alphabetically for
        deterministic output.

        Raises:
            CyclicDependencyError: if the dependency graph contains a cycle.
        """
        active = {k for k in self._scripts if k not in self._ignored}
        in_degree: Dict[str, int] = {k: 0 for k in active}
        adjacency: Dict[str, List[str]] = defaultdict(list)

        for local_name in active:
            entry = self._scripts[local_name]
            for dep in entry.dependencies:
                if dep in active:
                    adjacency[dep].append(local_name)
                    in_degree[local_name] += 1

        def _sort_key(k: str):
            return (self._script_priority.get(k, 999999), k)

        # Seed queue with zero-degree nodes, ordered by module load priority
        queue: deque[str] = deque(
            sorted((k for k, v in in_degree.items() if v == 0), key=_sort_key)
        )
        order: List[str] = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbour in sorted(adjacency[node], key=_sort_key):
                in_degree[neighbour] -= 1
                if in_degree[neighbour] == 0:
                    queue.append(neighbour)

        if len(order) != len(active):
            cycle_nodes = sorted(k for k in active if k not in order)
            raise CyclicDependencyError(
                f"Cyclic dependency detected among: {cycle_nodes}"
            )

        return order

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _ensure_prefix(self, script: str) -> str:
        """Prepend the ontology namespace PREFIX declaration if absent."""
        if "prefix :" not in script.lower():
            return self._prefix_header + script
        return script
