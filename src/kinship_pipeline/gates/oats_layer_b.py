"""OATS Layer B: validate internal OATS consistency."""

from typing import Any, Dict

from ..backends.base import KinshipBackend
from ..query_generator import QueryGenerator


class OatsLayerB:
    """Run the OATS-only validation sequence (IRR, RED, CON, CIR, PAR)."""

    def __init__(self, backend: KinshipBackend, query_generator: QueryGenerator) -> None:
        self.backend = backend
        self.query_generator = query_generator

    def run(self, oats_graph: str = "urn:kinship:oats") -> Dict[str, Any]:
        """Execute Layer B and return a report."""
        queries = self.query_generator.generate_oats(data_graph=oats_graph)
        report: Dict[str, Any] = {
            "status": "ok",
            "graph": oats_graph,
            "violations": [],
        }
        for name, sparql in queries.items():
            results = self.backend.execute_query(sparql)
            if results:
                report["status"] = "violation"
                report["violations"].append({
                    "query": name,
                    "count": len(results),
                    "triples": results,
                })
        return report
