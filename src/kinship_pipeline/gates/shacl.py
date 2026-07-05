"""SHACL Gate: post-inference safety net.

The SHACL Gate runs after Materialization Step 2 and checks the full
materialized closure for residual inconsistencies that escape the SPARQL
gates.  It is a warning-only stage: if it fires, the pipeline status becomes
"warning" but the materialized graph (MO) remains usable.

The gate reads from the whole dataset and writes the validation report into
``<urn:kinship:validation>``.
"""

from typing import Any, Dict, List, Optional

from ..backends.base import KinshipBackend


class ShaclGate:
    """Run post-inference SHACL validation and report residual issues."""

    SHAPES = {
        "POST-CYCLE": "http://example.org/kinship/shapes#PostCycleShape",
        "POST-GENDER": "http://example.org/kinship/shapes#PostGenderShape",
        "POST-PARTNER-LINEAGE": "http://example.org/kinship/shapes#PostPartnerLineageShape",
        "POST-SIBLING-PARENT": "http://example.org/kinship/shapes#PostSiblingParentShape",
    }

    def __init__(self, backend: KinshipBackend) -> None:
        self.backend = backend

    def run(
        self,
        shapes_graph: str = "urn:kinship:shapes",
        report_graph: str = "urn:kinship:validation",
    ) -> Dict[str, Any]:
        """Execute SHACL validation and return a report.

        Returns
        -------
        {
          "status":       "ok" | "warning",
          "conforms":     bool,
          "violations":   [ {shape, node, detail, message}, ... ],
          "total_count":  int,
          "coverage_gap": int,
        }
        """
        conforms, total_count = self.backend.run_shacl_validation(
            shapes_graph=shapes_graph,
            report_graph=report_graph,
        )

        if conforms or total_count == 0:
            return {
                "status": "ok",
                "conforms": True,
                "violations": [],
                "total_count": 0,
                "coverage_gap": 0,
            }

        violations = self._collect_violations(report_graph)
        covered_nodes = {v["node"] for v in violations}
        coverage_gap = max(0, total_count - len(covered_nodes))

        return {
            "status": "warning",
            "conforms": False,
            "violations": violations,
            "total_count": total_count,
            "coverage_gap": coverage_gap,
        }

    def _collect_violations(self, report_graph: str) -> List[Dict[str, Any]]:
        """Run targeted queries per shape and return flat violation list."""
        violations: List[Dict[str, Any]] = []

        for shape_name, shape_uri in self.SHAPES.items():
            query = f"""\
PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX ksh: <http://example.org/kinship/shapes#>
SELECT ?node ?value ?message WHERE {{
    GRAPH <{report_graph}> {{
        ?r a sh:ValidationResult ;
           sh:focusNode ?node ;
           sh:sourceShape <{shape_uri}> ;
           sh:resultMessage ?message .
        OPTIONAL {{ ?r sh:value ?value . }}
    }}
}}"""
            rows = self.backend.execute_query(query)
            for row in rows:
                violations.append({
                    "shape": shape_name,
                    "node": row.get("node", ""),
                    "detail": row.get("value", ""),
                    "message": row.get("message", ""),
                })

        return violations
