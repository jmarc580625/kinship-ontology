"""FATS Gate: classify incoming assertions and route them to MATS or OATS.

Routing logic
─────────────
After loading the dataset into <urn:kinship:intake>, the gate applies the
following steps in order:

  1. Detect + delete FATS property triples   (kinship predicates with assertionSet FATS)
  2. Detect + delete FATS class triples       (rdf:type whose object has assertionSet FATS)
  3. Detect + delete unclassified triples     (kinship-namespace predicate, no assertionSet)
  4. Move OATS predicate triples              -> O
  5. Move OATS class (rdf:type) triples       -> O
  6. Move MATS predicate triples              -> A
  7. Move MATS class (rdf:type) triples       -> A
  8. Drop remainder of intake                 (should be empty; clear as a safeguard)

After Steps 1-3 every kinship-namespace predicate has been either rejected or
routed.  Steps 4-7 consume everything that remains.  There is no catch-all
move: anything not explicitly routed is dropped.

The gate report includes full triple lists for every rejection category.
"""

from typing import Any, Dict, List

from ..backends.base import KinshipBackend


_KIN      = "http://example.org/kinship#"
_RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


class FatsGate:
    """Route intake triples to asserted (MATS) or oats (OATS), reject FATS."""

    def __init__(
        self,
        backend: KinshipBackend,
        namespace: str = "http://example.org/kinship#",
    ) -> None:
        self.backend = backend
        self.namespace = namespace

    def run(
        self,
        intake_graph: str = "urn:kinship:intake",
        asserted_graph: str = "urn:kinship:asserted",
        oats_graph: str = "urn:kinship:oats",
        ontology_graph: str = "urn:kinship:ontology",
    ) -> Dict[str, Any]:
        """Execute the FATS gate and return a detailed routing report."""
        self.backend.clear_graph(asserted_graph)
        self.backend.clear_graph(oats_graph)

        # 1-2. Detect FATS rejections, then expunge from intake immediately.
        fats_property_triples = self._detect_fats_properties(intake_graph, ontology_graph)
        fats_class_triples    = self._detect_fats_classes(intake_graph, ontology_graph)
        self._delete_from_intake_by_fats(intake_graph, ontology_graph)

        # 3. Detect unclassified kinship predicates, then expunge.
        unclassified_triples = self._detect_unclassified(intake_graph, ontology_graph)
        self._delete_from_intake_unclassified(intake_graph, ontology_graph)

        # 4-5. Route OATS.
        self._move_by_predicate_set(intake_graph, oats_graph, ontology_graph, "OATS")
        self._move_by_class_set(intake_graph, oats_graph, ontology_graph, "OATS")

        # 6-7. Route MATS.
        self._move_by_predicate_set(intake_graph, asserted_graph, ontology_graph, "MATS")
        self._move_by_class_set(intake_graph, asserted_graph, ontology_graph, "MATS")

        # 8. Drop anything left in intake (safeguard — should already be empty).
        self.backend.clear_graph(intake_graph)

        mats_count    = self.backend.graph_size(asserted_graph)
        oats_count    = self.backend.graph_size(oats_graph)
        fats_count    = len(fats_property_triples) + len(fats_class_triples)
        unclass_count = len(unclassified_triples)

        if mats_count == 0 and oats_count == 0:
            status = "blocked"
        elif fats_count or unclass_count:
            status = "warning"
        else:
            status = "ok"

        return {
            "status":                 status,
            "mats_count":             mats_count,
            "oats_count":             oats_count,
            "fats_rejected":          fats_count,
            "fats_property_triples":  fats_property_triples,
            "fats_class_triples":     fats_class_triples,
            "unclassified_rejected":  unclass_count,
            "unclassified_triples":   unclassified_triples,
        }

    # ------------------------------------------------------------------
    # Detection helpers (SELECT only — never mutate)
    # ------------------------------------------------------------------

    def _detect_fats_properties(self, graph: str, ontology: str) -> List[Dict[str, Any]]:
        """Return all triples in *graph* whose predicate is FATS-classified."""
        return self.backend.execute_query(f"""
PREFIX kin: <{_KIN}>
SELECT ?s ?p ?o WHERE {{
  GRAPH <{graph}>   {{ ?s ?p ?o }}
  GRAPH <{ontology}> {{ ?p kin:assertionSet kin:FATS }}
}}""")

    def _detect_fats_classes(self, graph: str, ontology: str) -> List[Dict[str, Any]]:
        """Return rdf:type triples whose object class is FATS-classified."""
        rows = self.backend.execute_query(f"""
PREFIX kin: <{_KIN}>
SELECT ?s ?o WHERE {{
  GRAPH <{graph}>   {{ ?s a ?o }}
  GRAPH <{ontology}> {{
    ?o a <http://www.w3.org/2002/07/owl#Class> .
    ?o kin:assertionSet kin:FATS .
  }}
}}""")
        return [{"s": r["s"], "p": _RDF_TYPE, "o": r["o"]} for r in rows]

    def _detect_unclassified(self, graph: str, ontology: str) -> List[Dict[str, Any]]:
        """Return triples with a kinship-namespace predicate absent from all assertionSets."""
        return self.backend.execute_query(f"""
PREFIX kin: <{_KIN}>
SELECT ?s ?p ?o WHERE {{
  GRAPH <{graph}> {{ ?s ?p ?o }}
  FILTER(STRSTARTS(STR(?p), "{_KIN}"))
  FILTER NOT EXISTS {{ GRAPH <{ontology}> {{ ?p kin:assertionSet ?set }} }}
}}""")

    # ------------------------------------------------------------------
    # Deletion helpers (DELETE — expunge from intake before routing)
    # ------------------------------------------------------------------

    def _delete_from_intake_by_fats(self, graph: str, ontology: str) -> None:
        """Remove FATS property triples and FATS class (rdf:type) triples."""
        # By predicate
        self.backend.execute_update(f"""
PREFIX kin: <{_KIN}>
DELETE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }}
WHERE  {{
  GRAPH <{graph}>   {{ ?s ?p ?o }}
  GRAPH <{ontology}> {{ ?p kin:assertionSet kin:FATS }}
}}""")
        # By class (rdf:type whose object has assertionSet FATS)
        self.backend.execute_update(f"""
PREFIX kin: <{_KIN}>
DELETE {{ GRAPH <{graph}> {{ ?s a ?o }} }}
WHERE  {{
  GRAPH <{graph}>   {{ ?s a ?o }}
  GRAPH <{ontology}> {{
    ?o a <http://www.w3.org/2002/07/owl#Class> .
    ?o kin:assertionSet kin:FATS .
  }}
}}""")

    def _delete_from_intake_unclassified(self, graph: str, ontology: str) -> None:
        """Remove kinship-namespace triples with no assertionSet annotation."""
        self.backend.execute_update(f"""
PREFIX kin: <{_KIN}>
DELETE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }}
WHERE  {{
  GRAPH <{graph}> {{ ?s ?p ?o }}
  FILTER(STRSTARTS(STR(?p), "{_KIN}"))
  FILTER NOT EXISTS {{ GRAPH <{ontology}> {{ ?p kin:assertionSet ?set }} }}
}}""")

    # ------------------------------------------------------------------
    # Routing helpers (DELETE … INSERT — move from intake to target graph)
    # ------------------------------------------------------------------

    def _move_by_predicate_set(
        self, source: str, target: str, ontology: str, assertion_set: str
    ) -> None:
        """Move triples whose predicate carries *assertion_set*."""
        self.backend.execute_update(f"""
PREFIX kin: <{_KIN}>
DELETE {{ GRAPH <{source}> {{ ?s ?p ?o }} }}
INSERT {{ GRAPH <{target}> {{ ?s ?p ?o }} }}
WHERE  {{
  GRAPH <{source}>  {{ ?s ?p ?o }}
  GRAPH <{ontology}> {{ ?p kin:assertionSet kin:{assertion_set} }}
}}""")

    def _move_by_class_set(
        self, source: str, target: str, ontology: str, assertion_set: str
    ) -> None:
        """Move rdf:type triples whose object class carries *assertion_set*."""
        self.backend.execute_update(f"""
PREFIX kin: <{_KIN}>
DELETE {{ GRAPH <{source}> {{ ?s a ?o }} }}
INSERT {{ GRAPH <{target}> {{ ?s a ?o }} }}
WHERE  {{
  GRAPH <{source}>  {{ ?s a ?o }}
  GRAPH <{ontology}> {{
    ?o a <http://www.w3.org/2002/07/owl#Class> .
    ?o kin:assertionSet kin:{assertion_set} .
  }}
}}""")
