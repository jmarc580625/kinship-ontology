"""MATS Gate: validate raw MATS assertions before materialization.

Each query family carries a severity defined in ``QUERY_SEVERITY``:

  violation — the gate sets status "violation" and the pipeline blocks.
  warning   — the gate sets status "warning" (RED families); pipeline continues.

The report separates the two into ``violations`` and ``warnings`` lists.
"""

from typing import Any, Dict, List

from ..backends.base import KinshipBackend
from ..query_generator import QueryGenerator, QUERY_SEVERITY


class MatsGate:
    """Run the MATS validation sequence (IRR, RED, CON, CIR, CAR, TWI, PAR)."""

    def __init__(self, backend: KinshipBackend, query_generator: QueryGenerator) -> None:
        self.backend = backend
        self.query_generator = query_generator

    def run(self, asserted_graph: str = "urn:kinship:asserted") -> Dict[str, Any]:
        """Execute MATS validation and return a report.

        Returns
        -------
        {
          "status":     "ok" | "warning" | "violation",
          "graph":      <graph URI>,
          "violations": [ {query, count, triples}, ... ],   # blocking families
          "warnings":   [ {query, count, triples}, ... ],   # RED families
        }
        """
        queries = self.query_generator.generate_mats(data_graph=asserted_graph)
        violations: List[Dict[str, Any]] = []
        warnings:   List[Dict[str, Any]] = []

        for name, sparql in queries.items():
            results = self.backend.execute_query(sparql)
            if not results:
                continue
            entry = {"query": name, "count": len(results), "triples": results}
            if QUERY_SEVERITY.get(name, "violation") == "warning":
                warnings.append(entry)
            else:
                violations.append(entry)

        if violations:
            status = "violation"
        elif warnings:
            status = "warning"
        else:
            status = "ok"

        return {
            "status":     status,
            "graph":      asserted_graph,
            "violations": violations,
            "warnings":   warnings,
        }
