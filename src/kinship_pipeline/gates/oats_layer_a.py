"""OATS Layer A: validate OATS assertions against the MATS-derived closure.

This implementation follows the V1D2 specification.  OATS candidates are read
from the quarantine graph and checked against the MATS working set using the
ontology's assertion-set metadata:

- Branch 1: lineage closure (hasLineageRelative)
- Branch 2: partnership (hasPartner)
- Branch 3: declared cross-set disjointness (owl:propertyDisjointWith)
- Branch 4: generational direction conflicts (kin:generationalDirection)

The MATS evidence is read unscoped so it covers raw asserted MATS, OWL-RL
inferences in the default graph, and triples materialized by the Step 1
scripts.  The OATS candidate itself is scoped to the OATS graph so it cannot
match the evidence.
"""

from typing import Any, Dict

from ..backends.base import KinshipBackend


_KIN = "http://example.org/kinship#"
_RDFS = "http://www.w3.org/2000/01/rdf-schema#"
_OWL = "http://www.w3.org/2002/07/owl#"


class OatsLayerA:
    """Validate OATS assertions against the MATS-derived closure."""

    def __init__(self, backend: KinshipBackend, namespace: str = "http://example.org/kinship#") -> None:
        self.backend = backend
        self.namespace = namespace

    def run(
        self,
        oats_graph: str = "urn:kinship:oats",
        ontology_graph: str = "urn:kinship:ontology",
    ) -> Dict[str, Any]:
        """Execute Layer A and return a report.

        The OATS property list is generated from the ontology so it stays in
        sync with the TBox.
        """
        oats_properties = self._oats_properties(ontology_graph)
        if not oats_properties:
            return {
                "status": "ok",
                "graph": oats_graph,
                "count": 0,
                "violations": [],
            }

        filter_in = ", ".join(self._qname(p) for p in oats_properties)

        sparql = f"""\
PREFIX kin: <{_KIN}>
PREFIX rdfs: <{_RDFS}>
PREFIX owl: <{_OWL}>
SELECT DISTINCT ?s ?p ?o ?existingRel WHERE {{
    GRAPH <{oats_graph}> {{
        ?s ?p ?o .
        FILTER(?p IN ({filter_in}))
    }}
    {{
        ?s kin:hasLineageRelative ?o .
        BIND(kin:hasLineageRelative AS ?existingRel)
    }}
    UNION
    {{
        ?s kin:hasPartner ?o .
        BIND(kin:hasPartner AS ?existingRel)
    }}
    UNION
    {{
        ?s ?mats ?o .
        BIND(?mats AS ?existingRel)
        GRAPH <{ontology_graph}> {{
            ?p owl:propertyDisjointWith ?mats .
            ?mats kin:assertionSet kin:MATS .
        }}
    }}
    UNION
    {{
        ?s ?mats ?o .
        BIND(?mats AS ?existingRel)
        GRAPH <{ontology_graph}> {{
            ?p    kin:assertionSet kin:OATS ;
                  kin:generationalDirection ?oatsDir .
            ?mats kin:assertionSet kin:MATS ;
                  kin:generationalDirection ?matsDir .
            FILTER(?oatsDir != ?matsDir)
        }}
    }}
}}"""
        results = self.backend.execute_query(sparql)
        return {
            "status": "ok" if not results else "violation",
            "graph": oats_graph,
            "count": len(results),
            "violations": results[:50],
        }

    def _oats_properties(self, ontology_graph: str) -> list:
        """Return the list of OATS properties from the ontology."""
        sparql = (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT ?p FROM <{ontology_graph}> WHERE {{\n"
            f"    ?p kin:assertionSet kin:OATS .\n"
            f"}}"
        )
        rows = self.backend.execute_query(sparql)
        return sorted({r["p"] for r in rows})

    def _qname(self, uri: str) -> str:
        """Return a SPARQL qname for a known namespace URI."""
        if uri.startswith(self.namespace):
            return f"kin:{uri[len(self.namespace):]}"
        return f"<{uri}>"
        results = self.backend.execute_query(sparql)
        return {
            "status": "ok" if not results else "violation",
            "graph": oats_graph,
            "asserted": asserted_graph,
            "mats_materialization": mats_materialization_graph,
            "count": len(results),
            "violations": results[:50],
        }
