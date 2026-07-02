"""OATS Layer A: validate OATS assertions against the MATS closure."""

from typing import Any, Dict

from ..backends.base import KinshipBackend


_KIN = "http://example.org/kinship#"
_RDFS = "http://www.w3.org/2000/01/rdf-schema#"
_OWL = "http://www.w3.org/2002/07/owl#"


class OatsLayerA:
    """Two-graph query: OATS assertions must not redefine MATS-derived facts."""

    def __init__(self, backend: KinshipBackend, namespace: str = "http://example.org/kinship#") -> None:
        self.backend = backend
        self.namespace = namespace

    def run(
        self,
        oats_graph: str = "urn:kinship:oats",
        mats_closure_graph: str = "urn:kinship:mats-closure",
        ontology_graph: str = "urn:kinship:ontology",
    ) -> Dict[str, Any]:
        """Execute Layer A and return a report."""
        sparql = f"""\
PREFIX kin: <{_KIN}>
PREFIX rdfs: <{_RDFS}>
PREFIX owl: <{_OWL}>
SELECT DISTINCT ?p ?x ?y WHERE {{
  GRAPH <{oats_graph}> {{ ?x ?p ?y }}
  GRAPH <{mats_closure_graph}> {{
    {{ ?x ?p ?y }} UNION
    {{ ?x ?q ?y . GRAPH <{ontology_graph}> {{ ?p rdfs:subPropertyOf* ?q }} }} UNION
    {{ ?y ?q ?x . GRAPH <{ontology_graph}> {{ ?p owl:inverseOf ?q }} }} UNION
    {{
      ?x ?q ?y .
      GRAPH <{ontology_graph}> {{
        ?p owl:propertyChainAxiom ?chain .
        ?chain rdf:rest*/rdf:first ?q .
      }}
    }}
  }}
}}"""
        results = self.backend.execute_query(sparql)
        return {
            "status": "ok" if not results else "violation",
            "graph": oats_graph,
            "mats_closure": mats_closure_graph,
            "count": len(results),
            "violations": results[:50],
        }
