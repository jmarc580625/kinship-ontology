"""
Ontology-driven query generator for the kinship consistency pipeline.

Reads the TBox from the backend's ontology graph and produces the SPARQL
detection queries used by the FATS, MATS and OATS gates.  The generated
queries mirror the hand-written catalog in V1D2 but are derived from the
ontology so they stay in sync as the TBox evolves.

Supported query families:
    - IRR  (irreflexive / asymmetric properties)
    - RED1 (subproperty / superproperty redundancy)
    - RED2 (inverse property redundancy)
    - RED3 (symmetric property both directions)
    - CON  (ascending / descending conflict)
    - CIR1 (mutual same-property)
    - CIR2 (generational cycle depth 2)
    - CAR  (cardinality / qualified cardinality)
    - TWI  (twins with missing / single shared parent)
    - PAR  (partnership / lineage conflict)
"""

from typing import Any, Dict, List, Optional

from .backends.base import KinshipBackend


_KIN = "http://example.org/kinship#"
_OWL = "http://www.w3.org/2002/07/owl#"
_RDFS = "http://www.w3.org/2000/01/rdf-schema#"


# Severity of each query family.
# "violation" → pipeline blocks on this gate.
# "warning"   → reported but pipeline continues.
QUERY_SEVERITY: Dict[str, str] = {
    "Q-IRR":  "violation",
    "Q-RED1": "warning",
    "Q-RED2": "warning",
    "Q-RED3": "warning",
    "Q-CON":  "violation",   # OATS generic CON
    "Q-CON1": "violation",
    "Q-CON2": "violation",
    "Q-CON3": "violation",
    "Q-CON4": "violation",
    "Q-CAR1": "violation",
    "Q-CAR2": "violation",
    "Q-TWI1": "violation",
    "Q-TWI2": "violation",
    "Q-CIR1": "violation",
    "Q-CIR2": "violation",
    "Q-PAR1": "violation",
    "Q-PAR2": "violation",
    "Q-PAR3": "violation",
}


class QueryGenerator:
    """Generate validation queries from the kinship TBox."""

    def __init__(
        self,
        backend: KinshipBackend,
        ontology_graph: str = "urn:kinship:ontology",
        namespace: str = "http://example.org/kinship#",
    ) -> None:
        self.backend = backend
        self.ontology_graph = ontology_graph
        self.namespace = namespace
        self._cache: Dict[str, Any] = {}
        self._discover()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_mats(self, data_graph: str = "urn:kinship:asserted") -> Dict[str, str]:
        """Generate all MATS gate queries.

        Note: Q-CIR2 (generational cycles) is handled by the graph-algorithm
        cycle detector and is not included here.
        """
        return {
            "Q-IRR": self._irr_query(self._cache["mats_irr"], data_graph),
            "Q-RED1": self._red1_query(self._cache["mats_red1"], data_graph),
            "Q-RED2": self._red2_query(self._cache["mats_red2"], data_graph),
            "Q-RED3": self._red3_query(self._cache["mats_red3"], data_graph),
            "Q-CON1": self._con1_query(data_graph),
            "Q-CON2": self._con2_query(self._cache["mats_asc"], self._cache["mats_desc"], data_graph),
            "Q-CON3": self._con3_query(data_graph),
            "Q-CON4": self._con4_query(self._cache["mats_asc"], self._cache["mats_desc"], data_graph),
            "Q-CAR1": self._car1_query(data_graph),
            "Q-CAR2": self._car2_query(data_graph),
            "Q-TWI1": self._twi1_query(data_graph),
            "Q-TWI2": self._twi2_query(data_graph),
            "Q-CIR1": self._cir1_query(self._cache["mats_cir1"], data_graph),
            "Q-PAR1": self._par1_query(data_graph),
            "Q-PAR2": self._par2_query(data_graph),
            "Q-PAR3": self._par3_query(data_graph),
        }

    def generate_oats(self, data_graph: str = "urn:kinship:oats") -> Dict[str, str]:
        """Generate all OATS Layer B queries.

        Note: Q-CIR2 (generational cycles) is handled by the graph-algorithm
        cycle detector and is not included here.
        """
        return {
            "Q-IRR": self._irr_query(self._cache["oats_irr"], data_graph),
            "Q-RED1": self._red1_query(self._cache["oats_red1"], data_graph),
            "Q-RED2": self._red2_query(self._cache["oats_red2"], data_graph),
            "Q-RED3": self._red3_query(self._cache["oats_red3"], data_graph),
            "Q-CON": self._con2_query(self._cache["oats_asc"], self._cache["oats_desc"], data_graph),
            "Q-CIR1": self._cir1_query(self._cache["oats_cir1"], data_graph),
            "Q-PAR1": self._par1_query(data_graph),
            "Q-PAR2": self._par2_query(data_graph),
            "Q-PAR3": self._par3_query(data_graph),
        }

    def generate_fats_rejection(self) -> str:
        """Generate the FATS gate rejection query."""
        fats = self._cache["fats"]
        if not fats:
            return "SELECT ?s ?p ?o WHERE { FILTER(false) }"
        values = " ".join(self._qname(p) for p in fats)
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT ?s ?p ?o WHERE {{\n"
            f"  VALUES ?p {{ {values} }}\n"
            f"  ?s ?p ?o .\n"
            f"}}"
        )

    # ------------------------------------------------------------------
    # TBox discovery
    # ------------------------------------------------------------------

    def _discover(self) -> None:
        """Discover properties and restrictions from the ontology graph."""
        self._cache["mats"] = self._members("MATS")
        self._cache["oats"] = self._members("OATS")
        self._cache["fats"] = self._members("FATS")

        self._cache["mats_irr"] = self._irr_properties("MATS")
        self._cache["oats_irr"] = self._irr_properties("OATS")

        self._cache["mats_red1"] = self._red1_pairs("MATS")
        self._cache["oats_red1"] = self._red1_pairs("OATS")

        self._cache["mats_red2"] = self._red2_pairs("MATS")
        self._cache["oats_red2"] = self._red2_pairs("OATS")

        self._cache["mats_red3"] = self._red3_properties("MATS")
        self._cache["oats_red3"] = self._red3_properties("OATS")

        self._cache["mats_asc"], self._cache["mats_desc"] = self._directional("MATS")
        self._cache["oats_asc"], self._cache["oats_desc"] = self._directional("OATS")

        self._cache["mats_cir1"] = self._cir1_properties("MATS")
        self._cache["oats_cir1"] = self._cir1_properties("OATS")

    def _query(self, sparql: str) -> List[Dict[str, Any]]:
        """Run a SPARQL query against the ontology graph."""
        # Use GRAPH clause so the query works on both rdflib and GraphDB.
        wrapped = (
            f"PREFIX kin: <{_KIN}>\n"
            f"PREFIX owl: <{_OWL}>\n"
            f"PREFIX rdfs: <{_RDFS}>\n"
            f"SELECT * FROM <{self.ontology_graph}> WHERE {{\n"
            f"{sparql}\n"
            f"}}"
        )
        return self.backend.execute_query(wrapped)

    def _members(self, assertion_set: str) -> List[str]:
        rows = self._query(f"?p kin:assertionSet kin:{assertion_set} .")
        return [r["p"] for r in rows]

    def _irr_properties(self, assertion_set: str) -> List[str]:
        rows = self._query(
            f"{{ ?p a owl:IrreflexiveProperty . }} UNION "
            f"{{ ?p a owl:AsymmetricProperty . }}\n"
            f"?p kin:assertionSet kin:{assertion_set} ."
        )
        return [r["p"] for r in rows]

    def _red1_pairs(self, assertion_set: str) -> List[tuple]:
        rows = self._query(
            f"?sub rdfs:subPropertyOf+ ?super .\n"
            f"?sub kin:assertionSet kin:{assertion_set} .\n"
            f"?super kin:assertionSet kin:{assertion_set} .\n"
            f"FILTER(?sub != ?super)"
        )
        return [(r["sub"], r["super"]) for r in rows]

    def _red2_pairs(self, assertion_set: str) -> List[tuple]:
        rows = self._query(
            f"?p owl:inverseOf ?q .\n"
            f"?p kin:assertionSet kin:{assertion_set} .\n"
            f"?q kin:assertionSet kin:{assertion_set} .\n"
            f"FILTER(STR(?p) < STR(?q))"
        )
        return [(r["p"], r["q"]) for r in rows]

    def _red3_properties(self, assertion_set: str) -> List[str]:
        rows = self._query(
            f"?p a owl:SymmetricProperty ; kin:assertionSet kin:{assertion_set} ."
        )
        return [r["p"] for r in rows]

    def _directional(self, assertion_set: str) -> tuple:
        asc = self._query(
            f"?p kin:generationalDirection kin:Ascending ;\n"
            f"   kin:assertionSet kin:{assertion_set} ."
        )
        desc = self._query(
            f"?p kin:generationalDirection kin:Descending ;\n"
            f"   kin:assertionSet kin:{assertion_set} ."
        )
        return [r["p"] for r in asc], [r["p"] for r in desc]

    def _cir1_properties(self, assertion_set: str) -> List[str]:
        rows = self._query(
            f"?p a owl:AsymmetricProperty ;\n"
            f"   kin:assertionSet kin:{assertion_set} ;\n"
            f"   kin:generationalDirection ?dir ."
        )
        return [r["p"] for r in rows]

    # ------------------------------------------------------------------
    # Query builders
    # ------------------------------------------------------------------

    def _qname(self, uri: str) -> str:
        if uri.startswith(_KIN):
            return "kin:" + uri[len(_KIN):]
        return f"<{uri}>"

    def _values_list(self, uris: List[str]) -> str:
        return " ".join(self._qname(u) for u in uris)

    def _values_pairs(self, pairs: List[tuple]) -> str:
        return " ".join(f"({self._qname(a)} {self._qname(b)})" for a, b in pairs)

    @staticmethod
    def _graph(name: str) -> str:
        return f"GRAPH <{name}>"

    def _irr_query(self, properties: List[str], data_graph: str) -> str:
        if not properties:
            return self._empty_query()
        values = self._values_list(properties)
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT DISTINCT ?x ?p WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    VALUES ?p {{ {values} }}\n"
            f"    ?x ?p ?x .\n"
            f"  }}\n"
            f"}}"
        )

    def _red1_query(self, pairs: List[tuple], data_graph: str) -> str:
        if not pairs:
            return self._empty_query()
        values = self._values_pairs(pairs)
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT DISTINCT ?x ?y ?sub ?super WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    VALUES (?sub ?super) {{ {values} }}\n"
            f"    ?x ?sub ?y .\n"
            f"    ?x ?super ?y .\n"
            f"  }}\n"
            f"}}"
        )

    def _red2_query(self, pairs: List[tuple], data_graph: str) -> str:
        if not pairs:
            return self._empty_query()
        values = self._values_pairs(pairs)
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT DISTINCT ?x ?y ?p ?q WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    VALUES (?p ?q) {{ {values} }}\n"
            f"    ?x ?p ?y .\n"
            f"    ?y ?q ?x .\n"
            f"  }}\n"
            f"}}"
        )

    def _red3_query(self, properties: List[str], data_graph: str) -> str:
        if not properties:
            return self._empty_query()
        values = self._values_list(properties)
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT DISTINCT ?x ?y ?p WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    VALUES ?p {{ {values} }}\n"
            f"    ?x ?p ?y .\n"
            f"    ?y ?p ?x .\n"
            f"    FILTER(STR(?x) < STR(?y))\n"
            f"  }}\n"
            f"}}"
        )

    def _con1_query(self, data_graph: str) -> str:
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT DISTINCT ?p ?c WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    {{ ?p kin:hasBloodChild ?c . ?p kin:hasAdoptiveChild ?c . }} UNION\n"
            f"    {{ ?c kin:hasBloodParent ?p . ?c kin:hasAdoptiveParent ?p . }} UNION\n"
            f"    {{ ?p kin:hasBloodChild ?c . ?c kin:hasAdoptiveParent ?p . }} UNION\n"
            f"    {{ ?p kin:hasAdoptiveChild ?c . ?c kin:hasBloodParent ?p . }}\n"
            f"  }}\n"
            f"}}"
        )

    def _con2_query(self, ascending: List[str], descending: List[str], data_graph: str) -> str:
        if not ascending or not descending:
            return self._empty_query()
        asc_values = self._values_list(ascending)
        desc_values = self._values_list(descending)
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT DISTINCT ?x ?y ?cp ?pp WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    VALUES ?cp {{ {desc_values} }}\n"
            f"    VALUES ?pp {{ {asc_values} }}\n"
            f"    ?x ?cp ?y .\n"
            f"    ?x ?pp ?y .\n"
            f"  }}\n"
            f"}}"
        )

    def _con3_query(self, data_graph: str) -> str:
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT ?x WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    ?x kin:hasGender kin:Female .\n"
            f"    ?x kin:hasGender kin:Male .\n"
            f"  }}\n"
            f"}}"
        )

    def _con4_query(self, ascending: List[str], descending: List[str], data_graph: str) -> str:
        if not ascending or not descending:
            return self._empty_query()
        asc_values = self._values_list(ascending)
        desc_values = self._values_list(descending)
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT DISTINCT ?t1 ?t2 WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    ?t1 kin:hasTwin ?t2 .\n"
            f"    VALUES ?cp {{ {desc_values} }}\n"
            f"    VALUES ?pp {{ {asc_values} }}\n"
            f"    {{ ?t1 ?pp ?t2 . }} UNION\n"
            f"    {{ ?t2 ?cp ?t1 . }} UNION\n"
            f"    {{ ?t1 ?cp ?t2 . }} UNION\n"
            f"    {{ ?t2 ?pp ?t1 . }}\n"
            f"  }}\n"
            f"}}"
        )

    def _car1_query(self, data_graph: str) -> str:
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT ?c (COUNT(DISTINCT ?p) AS ?nb) WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    {{ ?c kin:hasBloodParent ?p . }} UNION\n"
            f"    {{ ?p kin:hasBloodChild ?c . }}\n"
            f"  }}\n"
            f"}} GROUP BY ?c HAVING (COUNT(DISTINCT ?p) > 2)"
        )

    def _car2_query(self, data_graph: str) -> str:
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT DISTINCT ?c ?gender (COUNT(DISTINCT ?p) AS ?nb) WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    VALUES ?gender {{ kin:Male kin:Female }}\n"
            f"    {{ ?c kin:hasBloodParent ?p . }} UNION\n"
            f"    {{ ?p kin:hasBloodChild ?c . }}\n"
            f"    ?p kin:hasGender ?gender .\n"
            f"  }}\n"
            f"}} GROUP BY ?c ?gender HAVING (COUNT(DISTINCT ?p) > 1)"
        )

    def _twi1_query(self, data_graph: str) -> str:
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT ?t1 ?t2 WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    ?t1 kin:hasTwin ?t2 .\n"
            f"    FILTER(STR(?t1) < STR(?t2))\n"
            f"    FILTER NOT EXISTS {{\n"
            f"      {{ ?p kin:hasBloodChild ?t1 . ?p kin:hasBloodChild ?t2 . }} UNION\n"
            f"      {{ ?t1 kin:hasBloodParent ?p . ?t2 kin:hasBloodParent ?p . }} UNION\n"
            f"      {{ ?p kin:hasBloodChild ?t1 . ?t2 kin:hasBloodParent ?p . }} UNION\n"
            f"      {{ ?t1 kin:hasBloodParent ?p . ?p kin:hasBloodChild ?t2 . }}\n"
            f"    }}\n"
            f"  }}\n"
            f"}}"
        )

    def _twi2_query(self, data_graph: str) -> str:
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT ?t1 ?t2 (COUNT(DISTINCT ?p) AS ?sharedParents) WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    ?t1 kin:hasTwin ?t2 .\n"
            f"    FILTER(STR(?t1) < STR(?t2))\n"
            f"    {{ ?p kin:hasBloodChild ?t1 . ?p kin:hasBloodChild ?t2 . }} UNION\n"
            f"    {{ ?t1 kin:hasBloodParent ?p . ?t2 kin:hasBloodParent ?p . }} UNION\n"
            f"    {{ ?p kin:hasBloodChild ?t1 . ?t2 kin:hasBloodParent ?p . }} UNION\n"
            f"    {{ ?t1 kin:hasBloodParent ?p . ?p kin:hasBloodChild ?t2 . }}\n"
            f"  }}\n"
            f"}} GROUP BY ?t1 ?t2 HAVING (COUNT(DISTINCT ?p) = 1)"
        )

    def _cir1_query(self, properties: List[str], data_graph: str) -> str:
        if not properties:
            return self._empty_query()
        values = self._values_list(properties)
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT DISTINCT ?x ?y WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    VALUES ?p {{ {values} }}\n"
            f"    ?x ?p ?y . ?y ?p ?x .\n"
            f"    FILTER(STR(?x) < STR(?y))\n"
            f"  }}\n"
            f"}}"
        )

    def _cir2_query(self, data_graph: str) -> str:
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT DISTINCT ?x ?y ?z WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    VALUES ?cp {{ kin:hasChild kin:hasBloodChild kin:hasAdoptiveChild }}\n"
            f"    VALUES ?pp {{ kin:hasParent kin:hasBloodParent kin:hasAdoptiveParent }}\n"
            f"    {{ ?x ?cp ?y . ?y ?cp ?z . ?z ?cp ?x . }} UNION\n"
            f"    {{ ?x ?pp ?y . ?y ?pp ?z . ?z ?pp ?x . }} UNION\n"
            f"    {{ ?x ?cp ?y . ?y ?cp ?z . ?x ?pp ?z . }} UNION\n"
            f"    {{ ?x ?cp ?y . ?z ?pp ?y . ?z ?cp ?x . }} UNION\n"
            f"    {{ ?x ?cp ?y . ?z ?pp ?y . ?x ?pp ?z . }} UNION\n"
            f"    {{ ?y ?pp ?x . ?y ?cp ?z . ?x ?pp ?z . }} UNION\n"
            f"    {{ ?y ?pp ?x . ?y ?cp ?z . ?z ?cp ?x . }} UNION\n"
            f"    {{ ?x ?pp ?y . ?z ?cp ?y . ?z ?pp ?x . }}\n"
            f"    FILTER(?x != ?y && ?y != ?z && ?x != ?z)\n"
            f"  }}\n"
            f"}}"
        )

    def _par1_query(self, data_graph: str) -> str:
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT DISTINCT ?x ?y ?partner ?rel WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    VALUES ?partner {{ kin:hasPartner kin:hasSpouse kin:hasCivilPartner kin:hasLifePartner }}\n"
            f"    VALUES ?rel {{\n"
            f"      kin:hasChild kin:hasBloodChild kin:hasAdoptiveChild\n"
            f"      kin:hasParent kin:hasBloodParent kin:hasAdoptiveParent\n"
            f"    }}\n"
            f"    ?x ?partner ?y .\n"
            f"    {{ ?x ?rel ?y . }} UNION\n"
            f"    {{ ?y ?rel ?x . }}\n"
            f"  }}\n"
            f"}}"
        )


    def _par2_query(self, data_graph: str) -> str:
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT DISTINCT ?x ?y ?z WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    VALUES ?partner {{ kin:hasPartner kin:hasSpouse kin:hasCivilPartner kin:hasLifePartner }}\n"
            f"    VALUES ?cp {{ kin:hasChild kin:hasBloodChild kin:hasAdoptiveChild }}\n"
            f"    VALUES ?pp {{ kin:hasParent kin:hasBloodParent kin:hasAdoptiveParent }}\n"
            f"    ?x ?partner ?y .\n"
            f"    {{\n"
            f"      {{ ?x ?pp ?z . ?z ?pp ?y . }} UNION\n"
            f"      {{ ?x ?pp ?z . ?y ?cp ?z . }} UNION\n"
            f"      {{ ?z ?cp ?x . ?z ?pp ?y . }} UNION\n"
            f"      {{ ?z ?cp ?x . ?y ?cp ?z . }}\n"
            f"    }} UNION {{\n"
            f"      {{ ?x ?cp ?z . ?z ?cp ?y . }} UNION\n"
            f"      {{ ?x ?cp ?z . ?y ?pp ?z . }} UNION\n"
            f"      {{ ?z ?pp ?x . ?z ?cp ?y . }} UNION\n"
            f"      {{ ?z ?pp ?x . ?y ?pp ?z . }}\n"
            f"    }}\n"
            f"    FILTER(?z != ?x && ?z != ?y)\n"
            f"  }}\n"
            f"}}"
        )

    def _par3_query(self, data_graph: str) -> str:
        return (
            f"PREFIX kin: <{_KIN}>\n"
            f"SELECT DISTINCT ?t1 ?t2 WHERE {{\n"
            f"  {self._graph(data_graph)} {{\n"
            f"    ?t1 kin:hasTwin ?t2 .\n"
            f"    FILTER(STR(?t1) < STR(?t2))\n"
            f"    VALUES ?partner {{ kin:hasPartner kin:hasSpouse kin:hasCivilPartner kin:hasLifePartner }}\n"
            f"    {{ ?t1 ?partner ?t2 . }} UNION\n"
            f"    {{ ?t2 ?partner ?t1 . }}\n"
            f"  }}\n"
            f"}}"
        )

    def _empty_query(self) -> str:
        return "SELECT ?x WHERE { FILTER(false) }"
