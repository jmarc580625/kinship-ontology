"""FATS Gate: classify incoming assertions and route them to MATS or OATS.

Routing logic
─────────────
After loading into <urn:kinship:intake>:

  1. rdf:type triples whose object is a FATS class   → rejected (tracked)
  2. Triples whose predicate is a FATS property       → rejected (tracked)
  3. rdf:type triples whose object is a MATS class    → MATS (asserted)
  4. Triples whose predicate is a MATS property       → MATS (asserted)
  5. rdf:type triples whose object is an OATS class   → OATS
  6. Triples whose predicate is an OATS property      → OATS
  7. Kinship-namespace predicates with no assertionSet → rejected (unclassified)
  8. Non-kinship predicates (rdf:type with MATS class already moved, owl:…)
     are carried along with the MATS graph as metadata.

The FATS gate report includes full triple lists for every rejection category.
"""

from typing import Any, Dict, List

from ..backends.base import KinshipBackend


_KIN = "http://example.org/kinship#"
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

        # --- Step 1: collect FATS rejections before moving anything ---
        fats_property_triples = self._detect_fats_properties(intake_graph, ontology_graph)
        fats_class_triples    = self._detect_fats_classes(intake_graph, ontology_graph)

        # --- Step 2: route OATS (predicate + class) ---
        self._move_by_predicate_set(intake_graph, oats_graph, ontology_graph, "OATS")
        self._move_by_class_set(intake_graph, oats_graph, ontology_graph, "OATS")

        # --- Step 3: route MATS (predicate + class) ---
        self._move_by_predicate_set(intake_graph, asserted_graph, ontology_graph, "MATS")
        self._move_by_class_set(intake_graph, asserted_graph, ontology_graph, "MATS")

        # --- Step 4: carry remaining non-kinship metadata into asserted ---
        #   (e.g. rdf:type kin:Person already moved above; any residual
        #    non-kinship predicates go to asserted so they travel with the data)
        self._move_non_kinship(intake_graph, asserted_graph)

        # --- Step 5: collect and expunge FATS triples from asserted/oats ---
        #   They may have been copied in via the move_non_kinship pass if a
        #   FATS predicate is also used as a class URI — guard against it.
        self._delete_fats_from(asserted_graph, ontology_graph)
        self._delete_fats_from(oats_graph, ontology_graph)

        # --- Step 6: collect unclassified kinship predicates remaining ---
        unclassified_triples = self._detect_unclassified(intake_graph, ontology_graph)
        # Delete what's left in intake (FATS triples + unclassified)
        self.backend.clear_graph(intake_graph)

        mats_count = self.backend.graph_size(asserted_graph)
        oats_count = self.backend.graph_size(oats_graph)

        fats_count    = len(fats_property_triples) + len(fats_class_triples)
        unclass_count = len(unclassified_triples)

        status = "ok"
        if fats_count:
            status = "warning"
        if unclass_count:
            status = "warning"

        return {
            "status": status,
            "mats_count": mats_count,
            "oats_count": oats_count,
            # --- FATS rejections ---
            "fats_rejected": fats_count,
            "fats_property_triples": fats_property_triples,
            "fats_class_triples": fats_class_triples,
            # --- Unclassified ---
            "unclassified_rejected": unclass_count,
            "unclassified_triples": unclassified_triples,
        }

    # ------------------------------------------------------------------
    # Detection helpers (SELECT — return full triple lists)
    # ------------------------------------------------------------------

    def _detect_fats_properties(self, graph: str, ontology: str) -> List[Dict[str, Any]]:
        """Return all triples in *graph* whose predicate is FATS-classified."""
        q = f"""
PREFIX kin: <{_KIN}>
SELECT ?s ?p ?o WHERE {{
  GRAPH <{graph}> {{ ?s ?p ?o }}
  GRAPH <{ontology}> {{ ?p kin:assertionSet kin:FATS }}
}}"""
        return self.backend.execute_query(q)

    def _detect_fats_classes(self, graph: str, ontology: str) -> List[Dict[str, Any]]:
        """Return all rdf:type triples whose object is a FATS-classified class."""
        q = f"""
PREFIX kin: <{_KIN}>
PREFIX rdf: <{_RDF_TYPE.rsplit('#', 1)[0]}#>
SELECT ?s ?o WHERE {{
  GRAPH <{graph}> {{ ?s a ?o }}
  GRAPH <{ontology}> {{
    ?o a <http://www.w3.org/2002/07/owl#Class> .
    ?o kin:assertionSet kin:FATS .
  }}
}}"""
        return [{"s": r["s"], "p": _RDF_TYPE, "o": r["o"]}
                for r in self.backend.execute_query(q)]

    def _detect_unclassified(self, graph: str, ontology: str) -> List[Dict[str, Any]]:
        """Return triples with a kinship-namespace predicate absent from all assertionSets."""
        q = f"""
PREFIX kin: <{_KIN}>
SELECT ?s ?p ?o WHERE {{
  GRAPH <{graph}> {{ ?s ?p ?o }}
  FILTER(STRSTARTS(STR(?p), "{_KIN}"))
  FILTER NOT EXISTS {{
    GRAPH <{ontology}> {{ ?p kin:assertionSet ?set }}
  }}
}}"""
        return self.backend.execute_query(q)

    # ------------------------------------------------------------------
    # Move helpers (DELETE … INSERT — mutate graphs)
    # ------------------------------------------------------------------

    def _move_by_predicate_set(
        self, source: str, target: str, ontology: str, assertion_set: str
    ) -> None:
        """Move triples whose predicate carries *assertion_set*."""
        update = f"""
PREFIX kin: <{_KIN}>
DELETE {{ GRAPH <{source}> {{ ?s ?p ?o }} }}
INSERT {{ GRAPH <{target}> {{ ?s ?p ?o }} }}
WHERE {{
  GRAPH <{source}> {{ ?s ?p ?o }}
  GRAPH <{ontology}> {{ ?p kin:assertionSet kin:{assertion_set} }}
}}"""
        self.backend.execute_update(update)

    def _move_by_class_set(
        self, source: str, target: str, ontology: str, assertion_set: str
    ) -> None:
        """Move rdf:type triples whose object class carries *assertion_set*."""
        update = f"""
PREFIX kin: <{_KIN}>
DELETE {{ GRAPH <{source}> {{ ?s a ?o }} }}
INSERT {{ GRAPH <{target}> {{ ?s a ?o }} }}
WHERE {{
  GRAPH <{source}> {{ ?s a ?o }}
  GRAPH <{ontology}> {{
    ?o a <http://www.w3.org/2002/07/owl#Class> .
    ?o kin:assertionSet kin:{assertion_set} .
  }}
}}"""
        self.backend.execute_update(update)

    def _move_non_kinship(self, source: str, target: str) -> None:
        """Move any remaining triples in *source* to *target* (catch-all metadata)."""
        update = f"""
DELETE {{ GRAPH <{source}> {{ ?s ?p ?o }} }}
INSERT {{ GRAPH <{target}> {{ ?s ?p ?o }} }}
WHERE  {{ GRAPH <{source}> {{ ?s ?p ?o }} }}"""
        self.backend.execute_update(update)

    def _delete_fats_from(self, graph: str, ontology: str) -> None:
        """Remove any FATS-classified triples that ended up in *graph*."""
        # By predicate
        self.backend.execute_update(f"""
PREFIX kin: <{_KIN}>
DELETE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }}
WHERE {{
  GRAPH <{graph}> {{ ?s ?p ?o }}
  GRAPH <{ontology}> {{ ?p kin:assertionSet kin:FATS }}
}}""")
        # By class (rdf:type)
        self.backend.execute_update(f"""
PREFIX kin: <{_KIN}>
DELETE {{ GRAPH <{graph}> {{ ?s a ?o }} }}
WHERE {{
  GRAPH <{graph}> {{ ?s a ?o }}
  GRAPH <{ontology}> {{
    ?o a <http://www.w3.org/2002/07/owl#Class> .
    ?o kin:assertionSet kin:FATS .
  }}
}}""")
