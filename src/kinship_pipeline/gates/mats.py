"""MATS Gate: validate raw MATS assertions before materialization.

Each query family carries a severity defined in ``QUERY_SEVERITY``:

  violation -- the gate sets status "violation" and the pipeline blocks.
  warning   -- the gate sets status "warning" (RED families); pipeline continues.

The report separates the two into ``violations`` and ``warnings`` lists.

CIR2 (generational cycles) is detected by the graph-algorithm cycle
detector rather than a SPARQL query.  Its report entry carries ``cycles``
(list of node-path lists) instead of ``triples``.
"""

from typing import Any, Dict, List

from ..backends.base import KinshipBackend
from ..cycle_detector import detect_generational_cycles
from ..query_generator import QueryGenerator, QUERY_SEVERITY


class MatsGate:
    """Run the MATS validation sequence (IRR, RED, CON, CIR, CAR, TWI, PAR)."""

    def __init__(self, backend: KinshipBackend, query_generator: QueryGenerator) -> None:
        self.backend = backend
        self.query_generator = query_generator

    def run(self, mats_graph: str = "urn:kinship:mats") -> Dict[str, Any]:
        """Execute MATS validation and return a report.

        Returns
        -------
        {
          "status":     "ok" | "warning" | "violation",
          "graph":      <graph URI>,
          "violations": [ {query, count, ...}, ... ],   # blocking families
          "warnings":   [ {query, count, ...}, ... ],   # RED families
        }
        """
        queries = self.query_generator.generate_mats(data_graph=mats_graph)
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
            self.backend, self.query_generator, mats_graph, "MATS",
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
            "graph":      mats_graph,
            "violations": violations,
            "warnings":   warnings,
        }
