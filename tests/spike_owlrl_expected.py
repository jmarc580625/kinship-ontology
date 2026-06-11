"""
Spike: get exact expected values for OWL post-inference tests.
Outputs JSON-ready expected results.
"""
import sys, json
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TESTS_DIR.parent
sys.path.insert(0, str(_TESTS_DIR))

from rdflib import Graph, Namespace
import owlrl
from lib.ontology_loader import load_chain_for

KIN = Namespace("http://example.org/kinship#")

onto_path = _PROJECT_ROOT / "ontology" / "kinship" / "core-neutral.ttl"
scan_dirs = [onto_path.parent]
ttl_chain = load_chain_for(onto_path, scan_dirs)

g = Graph()
for ttl in ttl_chain:
    g.parse(str(ttl), format="turtle")

data_path = _PROJECT_ROOT / "tests" / "data" / "consistency-control-data.ttl"
g.parse(str(data_path), format="turtle")

owlrl.DeductiveClosure(owlrl.RDFS_OWLRL_Semantics).expand(g)

# Sibling materialization
g.update("""
PREFIX kin: <http://example.org/kinship#>
INSERT { ?p1 kin:hasSibling ?p2 . }
WHERE { ?parent kin:hasChild ?p1 . ?parent kin:hasChild ?p2 . FILTER(?p1 != ?p2) }
""")
owlrl.DeductiveClosure(owlrl.RDFS_OWLRL_Semantics).expand(g)

def shorten(uri):
    return str(uri).replace("http://example.org/kinship#", ":")

def run_query(name, sparql):
    results = list(g.query(sparql))
    rows = []
    for row in results:
        row_dict = {}
        for var in row.labels:
            val = row[var]
            if val is not None:
                row_dict[str(var)] = shorten(val)
        rows.append(row_dict)
    rows.sort(key=lambda r: tuple(sorted(r.items())))
    print(f"\n--- {name}: {len(rows)} row(s) ---")
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return rows

# Q-POST-IRR
run_query("Q-POST-IRR", """
PREFIX kin: <http://example.org/kinship#>
SELECT DISTINCT ?x WHERE {
    VALUES ?p {
        kin:hasRelative kin:hasLineageRelative
        kin:hasDescendant kin:hasAncestor
        kin:hasChild kin:hasParent
        kin:hasBloodChild kin:hasBloodParent
        kin:hasSibling kin:hasPartner
    }
    ?x ?p ?x .
}
""")

# Q-POST-CIR
run_query("Q-POST-CIR", """
PREFIX kin: <http://example.org/kinship#>
SELECT DISTINCT ?x WHERE { ?x kin:hasDescendant ?x . }
""")

# Q-POST-DIS (with filter for ordering)
run_query("Q-POST-DIS", """
PREFIX kin: <http://example.org/kinship#>
SELECT DISTINCT ?x ?y WHERE {
    ?x kin:hasSibling ?y .
    { ?x kin:hasParent ?y . } UNION { ?x kin:hasChild ?y . }
    FILTER(STR(?x) < STR(?y))
}
""")

# Q-POST-PAR (with filter for ordering)
run_query("Q-POST-PAR", """
PREFIX kin: <http://example.org/kinship#>
SELECT DISTINCT ?x ?y WHERE {
    ?x kin:hasPartner ?y .
    { ?x kin:hasDescendant ?y . } UNION { ?x kin:hasAncestor ?y . }
    FILTER(STR(?x) < STR(?y))
}
""")

# Q-POST-CAR
run_query("Q-POST-CAR", """
PREFIX kin: <http://example.org/kinship#>
SELECT DISTINCT ?x WHERE {
    ?x a kin:MalePerson .
    ?x a kin:FemalePerson .
}
""")
