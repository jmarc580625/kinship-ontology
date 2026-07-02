"""
Materialization engine for the kinship consistency pipeline.

This engine is modelled on the existing ``MaterializationManager`` used by the
test runner, but it is designed for the pipeline graph architecture:

    Step 1:  <urn:kinship:asserted>  ->  <urn:kinship:mats-closure>
    Step 2:  asserted + oats        ->  <urn:kinship:full>

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
        source_graph: str = "urn:kinship:asserted",
        target_graph: str = "urn:kinship:mats-closure",
        reason_after_each: bool = False,
        on_script: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Materialize the MATS closure from ``<urn:kinship:asserted>``."""
        self._prepare_target(source_graph, target_graph)
        return self._run_scripts(target_graph, reason_after_each=reason_after_each, on_script=on_script)

    def step2(
        self,
        *,
        asserted_graph: str = "urn:kinship:asserted",
        oats_graph: str = "urn:kinship:oats",
        target_graph: str = "urn:kinship:full",
        reason_after_each: bool = False,
        on_script: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Materialize the full graph from asserted + oats."""
        self.backend.clear_graph(target_graph)
        self.backend.add_to_graph(asserted_graph, target_graph)
        self.backend.add_to_graph(oats_graph, target_graph)
        return self._run_scripts(target_graph, reason_after_each=reason_after_each, on_script=on_script)

    def _prepare_target(self, source: str, target: str) -> None:
        """Copy source into a clean target graph."""
        self.backend.clear_graph(target)
        self.backend.add_to_graph(source, target)

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
        # before scripts that depend on them run.
        self.backend.trigger_reasoning(target_graph)

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
                record["inferred_triples"] = self.backend.trigger_reasoning(target_graph)

            results.append(record)
            if callable(on_script):
                on_script(record)

        if not reason_after_each:
            # Single post-materialization reasoning pass.
            self.backend.trigger_reasoning(target_graph)

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
        """Wrap INSERT block with GRAPH <target> and add a kinship prefix.

        The WHERE clause is left unscoped so it evaluates over the effective
        dataset (the union of all named graphs). This works for RDFLib
        (default_union=True) and for GraphDB (which materialises OWL-RL
        inferences globally and exposes them through the default graph).
        """
        import re

        graph_block = f"GRAPH <{target_graph}>"
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
