"""
Materialization engine for the kinship consistency pipeline.

This engine is modelled on the existing ``MaterializationManager`` used by the
test runner, but it is designed for the pipeline graph architecture:

    Step 1:  <urn:kinship:mats>  ->  <urn:kinship:mats-materialization>
    Step 2:  asserted + oats        ->  <urn:kinship:oats-materialization>

The engine reads ``:MaterializationScript`` annotations from the TBox, resolves
their execution order by dependency analysis, and executes them via the
backend.  For performance, reasoning can be deferred until all scripts in a
phase have run.
"""

import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .backends.base import KinshipBackend


class MaterializationEngine:
    """Execute materialization scripts and reasoning for the pipeline."""

    def __init__(self, backend: KinshipBackend, namespace: str = "http://example.org/kinship#") -> None:
        self.backend = backend
        self.namespace = namespace
        self._scripts: Optional[List[Dict[str, Any]]] = None

    def step1(
        self,
        *,
        source_graph: str = "urn:kinship:mats",
        target_graph: str = "urn:kinship:mats-materialization",
        reason_after_each: bool = False,
        on_script: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Materialize the MATS closure from ``<urn:kinship:mats>`` (scripts only)."""
        self.backend.clear_graph(target_graph)
        return self._run_scripts(target_graph, reason_after_each=reason_after_each, on_script=on_script)

    def step2(
        self,
        *,
        mats_graph: str = "urn:kinship:mats",
        oats_graph: str = "urn:kinship:oats",
        target_graph: str = "urn:kinship:oats-materialization",
        reason_after_each: bool = False,
        on_script: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Materialize the OATS closure from asserted + oats (scripts only)."""
        self.backend.clear_graph(target_graph)
        return self._run_scripts(target_graph, reason_after_each=reason_after_each, on_script=on_script)

    def _run_scripts(
        self,
        target_graph: str,
        *,
        reason_after_each: bool,
        on_script: Optional[Callable[[Dict[str, Any]], None]],
    ) -> List[Dict[str, Any]]:
        """Execute materialization scripts against the target graph."""
        scripts = self._ordered_scripts()
        results: List[Dict[str, Any]] = []

        # Pre-reasoning: ensure superproperties, inverses, etc. are materialised
        # before scripts that depend on them run.  Reason over the whole dataset
        # so the default graph contains inferences from the asserted named graph.
        self.backend.trigger_reasoning()

        for entry in scripts:
            sparql = self._wrap_with_target(entry["script"], target_graph)
            record = {
                "property": entry["property"],
                "reason": entry.get("reason"),
                "status": "pending",
                "triples_added": 0,
                "inferred_triples": 0,
                "reasoning_triggered": False,
            }
            try:
                added = self.backend.execute_update(sparql)
                record["status"] = "ok"
                record["triples_added"] = int(added) if isinstance(added, (int, float)) else 0
            except Exception as exc:
                record["status"] = f"error: {exc}"
                results.append(record)
                if callable(on_script):
                    on_script(record)
                continue

            if reason_after_each:
                record["reasoning_triggered"] = True
                record["inferred_triples"] = self.backend.trigger_reasoning()

            results.append(record)
            if callable(on_script):
                on_script(record)

        if not reason_after_each:
            # Single post-materialization reasoning pass.
            self.backend.trigger_reasoning()

        return results

    def _ordered_scripts(self) -> List[Dict[str, Any]]:
        """Discover and order materialization scripts from the ontology."""
        if self._scripts is not None:
            return self._scripts

        # Prefer the battle-tested MaterializationManager from the test suite.
        try:
            self._scripts = self._order_via_manager()
        except Exception as exc:
            print(f"[WARN] MaterializationManager unavailable ({exc}); using fallback ordering.")
            self._scripts = self._order_via_fallback()
        return self._scripts

    def _order_via_manager(self) -> List[Dict[str, Any]]:
        """Use tests.lib.materialization_manager to discover and order scripts."""
        repo_root = Path(__file__).resolve().parents[2]
        tests_lib = str(repo_root / "tests")
        if tests_lib not in sys.path:
            sys.path.insert(0, tests_lib)

        from lib.materialization_manager import MaterializationManager

        manager = MaterializationManager(self.backend, namespace=self.namespace)
        return [
            {
                "property": name,
                "script": manager.scripts[name].script,
                "reason": manager.scripts[name].reason,
            }
            for name in manager.execution_order
        ]

    def _order_via_fallback(self) -> List[Dict[str, Any]]:
        """Simple fallback: retrieve scripts and order by explicit dependency hints."""
        query = f"""\
PREFIX : <{self.namespace}>
SELECT ?property ?script ?reason WHERE {{
    ?property :MaterializationScript ?script .
    OPTIONAL {{ ?property :MaterializationReason ?reason . }}
}}"""
        rows = self.backend.execute_query(query)
        scripts = [
            {
                "property": self._local_name(row["property"]),
                "script": row["script"],
                "reason": row.get("reason"),
            }
            for row in rows
        ]
        # Topological sort by property name dependencies (subproperty/superproperty).
        # A full implementation would parse the SPARQL; this is a placeholder.
        return sorted(scripts, key=lambda s: s["property"])

    def _wrap_with_target(self, script: str, target_graph: str) -> str:
        """Wrap INSERT block with GRAPH <target>.

        The INSERT clause is always scoped to the target graph so new
        materialized triples land in the correct named graph.  The WHERE
        clause is left unscoped on both backends: OWL-RL inferences live in
        the default (global/implicit) graph and must be visible to the
        materialization scripts.  Graph isolation is guaranteed at a higher
        level by the pipeline removing OATS data before MATS materialization.
        """
        import re

        graph_block = f"GRAPH <{target_graph}>"

        # Always wrap INSERT body.
        script = re.sub(
            r"INSERT\s*\{(.*?)\}",
            lambda m: f"INSERT {{ {graph_block} {{ {m.group(1)} }} }}",
            script,
            count=1,
            flags=re.DOTALL | re.IGNORECASE,
        )

        prefix = f"PREFIX : <{self.namespace}>\n"
        if not re.search(r"^\s*PREFIX\s+", script, re.MULTILINE | re.IGNORECASE):
            script = prefix + script
        return script

    def _local_name(self, uri: str) -> str:
        if uri.startswith(self.namespace):
            return uri[len(self.namespace):]
        return uri
