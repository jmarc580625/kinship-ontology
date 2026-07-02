"""MATS Gate: validate raw MATS assertions before materialization."""

from typing import Any, Dict

from ..backends.base import KinshipBackend
from ..query_generator import QueryGenerator


class MatsGate:
    """Run the MATS validation sequence (IRR, RED, CON, CIR, CAR, TWI, PAR)."""

    def __init__(self, backend: KinshipBackend, query_generator: QueryGenerator) -> None:
        self.backend = backend
        self.query_generator = query_generator

    def run(self, asserted_graph: str = "urn:kinship:asserted") -> Dict[str, Any]:
        """Execute MATS validation and return a report."""
        queries = self.query_generator.generate_mats(data_graph=asserted_graph)
        report: Dict[str, Any] = {
            "status": "ok",
            "graph": asserted_graph,
            "violations": [],
        }
        for name, sparql in queries.items():
            results = self.backend.execute_query(sparql)
            if results:
                report["status"] = "violation"
                report["violations"].append({
                    "query": name,
                    "count": len(results),
                    "sample": results[:5],
                })
        return report
