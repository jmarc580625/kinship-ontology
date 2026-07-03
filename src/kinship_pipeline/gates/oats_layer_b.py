"""OATS Layer B: validate internal OATS consistency.

Same severity model as the MATS Gate:
  violation -- pipeline ends with "violation" status.
  warning   -- pipeline ends with "warning" status.

CIR2 (generational cycles) is detected by the graph-algorithm cycle
detector rather than a SPARQL query.
"""

from typing import Any, Dict, List

from ..backends.base import KinshipBackend
from ..cycle_detector import detect_generational_cycles
from ..query_generator import QueryGenerator, QUERY_SEVERITY


class OatsLayerB:
    """Run the OATS-only validation sequence (IRR, RED, CON, CIR, PAR)."""

    def __init__(self, backend: KinshipBackend, query_generator: QueryGenerator) -> None:
        self.backend = backend
        self.query_generator = query_generator

    def run(self, oats_graph: str = "urn:kinship:oats") -> Dict[str, Any]:
        """Execute Layer B and return a report.

        Returns
        -------
        {
          "status":     "ok" | "warning" | "violation",
          "graph":      <graph URI>,
          "violations": [ {query, count, ...}, ... ],
          "warnings":   [ {query, count, ...}, ... ],
        }
        """
        queries = self.query_generator.generate_oats(data_graph=oats_graph)
        violations: List[Dict[str, Any]] = []
        warnings:   List[Dict[str, Any]] = []

        # SPARQL-based detection families.
        for name, sparql in queries.items():
            results = self.backend.execute_query(sparql)
            if not results:
                continue
            entry = {"query": name, "count": len(results), "triples": results}
            if QUERY_SEVERITY.get(name, "violation") == "warning":
                warnings.append(entry)
            else:
                violations.append(entry)

        # Graph-algorithm cycle detection (Q-CIR2).
        cir2 = detect_generational_cycles(
            self.backend, self.query_generator, oats_graph, "OATS",
        )
        if cir2["count"] > 0:
            violations.append(cir2)

        if violations:
            status = "violation"
        elif warnings:
            status = "warning"
        else:
            status = "ok"

        return {
            "status":     status,
            "graph":      oats_graph,
            "violations": violations,
            "warnings":   warnings,
        }
