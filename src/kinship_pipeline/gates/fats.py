"""FATS Gate: classify incoming assertions and route them to MATS or OATS."""

from typing import Any, Dict

from ..backends.base import KinshipBackend


_KIN = "http://example.org/kinship#"


class FatsGate:
    """Route intake triples to asserted (MATS) or oats (OATS), reject FATS."""

    def __init__(self, backend: KinshipBackend, namespace: str = "http://example.org/kinship#") -> None:
        self.backend = backend
        self.namespace = namespace

    def run(
        self,
        intake_graph: str = "urn:kinship:intake",
        asserted_graph: str = "urn:kinship:asserted",
        oats_graph: str = "urn:kinship:oats",
        ontology_graph: str = "urn:kinship:ontology",
    ) -> Dict[str, Any]:
        """Execute the FATS gate and return a routing report."""
        self.backend.clear_graph(asserted_graph)
        self.backend.clear_graph(oats_graph)

        # Copy all intake triples into asserted as a starting point.
        self.backend.add_to_graph(intake_graph, asserted_graph)

        # Move OATS-classified triples from asserted to oats.
        self._move_by_set(asserted_graph, oats_graph, ontology_graph, "OATS")

        # Count and delete FATS-classified triples from asserted.
        fats_count = self._delete_by_set(asserted_graph, ontology_graph, "FATS")

        # Count remaining asserted triples (MATS or unclassified).
        mats_count = self.backend.graph_size(asserted_graph)
        oats_count = self.backend.graph_size(oats_graph)

        # Reject unclassified properties as FATS.
        unclassified = self._delete_unclassified(asserted_graph, ontology_graph)
        mats_count -= unclassified

        # Clear intake after successful routing.
        self.backend.clear_graph(intake_graph)

        return {
            "status": "ok" if not fats_count else "warning",
            "mats_count": mats_count,
            "oats_count": oats_count,
            "fats_rejected": fats_count,
            "unclassified_rejected": unclassified,
        }

    def _move_by_set(
        self, source: str, target: str, ontology: str, assertion_set: str
    ) -> int:
        """Move triples whose property is classified in ``assertion_set``."""
        update = f"""\
PREFIX kin: <{_KIN}>
DELETE {{ GRAPH <{source}> {{ ?s ?p ?o }} }}
INSERT {{ GRAPH <{target}> {{ ?s ?p ?o }} }}
WHERE {{
  GRAPH <{source}> {{ ?s ?p ?o }}
  GRAPH <{ontology}> {{ ?p kin:assertionSet kin:{assertion_set} }}
}}"""
        self.backend.execute_update(update)
        return self.backend.graph_size(target)

    def _delete_by_set(self, source: str, ontology: str, assertion_set: str) -> int:
        """Delete triples whose property is classified in ``assertion_set``."""
        before = self.backend.graph_size(source)
        update = f"""\
PREFIX kin: <{_KIN}>
DELETE WHERE {{
  GRAPH <{source}> {{ ?s ?p ?o }}
  GRAPH <{ontology}> {{ ?p kin:assertionSet kin:{assertion_set} }}
}}"""
        self.backend.execute_update(update)
        return before - self.backend.graph_size(source)

    def _delete_unclassified(self, source: str, ontology: str) -> int:
        """Delete triples whose predicate is a kinship property with no assertion set."""
        before = self.backend.graph_size(source)
        update = f"""\
PREFIX kin: <{_KIN}>
DELETE {{ GRAPH <{source}> {{ ?s ?p ?o }} }}
WHERE {{
  GRAPH <{source}> {{ ?s ?p ?o }}
  FILTER(STRSTARTS(STR(?p), "{_KIN}"))
  FILTER NOT EXISTS {{
    GRAPH <{ontology}> {{
      ?p kin:assertionSet ?set .
      FILTER(?set IN (kin:MATS, kin:OATS, kin:FATS))
    }}
  }}
}}"""
        self.backend.execute_update(update)
        return before - self.backend.graph_size(source)
