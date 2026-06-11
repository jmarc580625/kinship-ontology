"""
Spike: comprehensive test of owlrl post-inference detection on full corrupted dataset.

Run: venv/Scripts/python tests/spike_owlrl_nothing.py
"""
import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TESTS_DIR.parent

sys.path.insert(0, str(_TESTS_DIR))

from rdflib import Graph, Namespace, RDF, OWL
import owlrl

KIN = Namespace("http://example.org/kinship#")

# --- Load ontology chain for core-neutral ---
from lib.ontology_loader import load_chain_for

onto_path = _PROJECT_ROOT / "ontology" / "kinship" / "core-neutral.ttl"
scan_dirs = [onto_path.parent]
ttl_chain = load_chain_for(onto_path, scan_dirs)

# --- Build graph ---
g = Graph()
for ttl in ttl_chain:
    g.parse(str(ttl), format="turtle")

# --- Load full corrupted dataset ---
data_path = _PROJECT_ROOT / "tests" / "data" / "consistency-control-data.ttl"
g.parse(str(data_path), format="turtle")

before = len(g)
print(f"Triples before reasoning: {before}")

# --- Apply OWL-RL reasoning ---
try:
    owlrl.DeductiveClosure(owlrl.RDFS_OWLRL_Semantics).expand(g)
    after = len(g)
    print(f"Triples after reasoning:  {after} (+{after - before} inferred)")
except Exception as exc:
    print(f"\n*** EXCEPTION during reasoning: {type(exc).__name__}: {exc}")
    sys.exit(1)

# --- Run materialization scripts ---
from lib.materialization_manager import MaterializationManager
from backends.rdflib_backend import RDFLibBackend

# We need to use the backend for materialization, but we already have the graph
# Let's just run the sibling materialization manually
sibling_mat = """
PREFIX kin: <http://example.org/kinship#>
INSERT {
    ?person1 kin:hasSibling ?person2 .
}
WHERE {
    ?parent kin:hasChild ?person1 .
    ?parent kin:hasChild ?person2 .
    FILTER(?person1 != ?person2)
}
"""
before_mat = len(g)
g.update(sibling_mat)
after_mat = len(g)
print(f"Sibling materialization: +{after_mat - before_mat} triples")

# Re-run reasoning after materialization
before_r2 = len(g)
owlrl.DeductiveClosure(owlrl.RDFS_OWLRL_Semantics).expand(g)
after_r2 = len(g)
print(f"Re-reasoning after materialization: +{after_r2 - before_r2} triples")

print(f"\nTotal triples: {len(g)}")

# === POST-INFERENCE QUERIES ===
print("\n" + "="*70)
print("POST-INFERENCE TARGETED QUERIES")
print("="*70)

# Q-POST-IRR: reflexive on superproperties
q_irr = """
PREFIX kin: <http://example.org/kinship#>
SELECT DISTINCT ?x ?p WHERE {
    VALUES ?p {
        kin:hasRelative kin:hasLineageRelative
        kin:hasDescendant kin:hasAncestor
        kin:hasChild kin:hasParent
        kin:hasBloodChild kin:hasBloodParent
        kin:hasSibling kin:hasPartner
    }
    ?x ?p ?x .
}
"""
results_irr = list(g.query(q_irr))
print(f"\nQ-POST-IRR: {len(results_irr)} reflexive triple(s)")
individuals_irr = set()
for row in results_irr:
    individuals_irr.add(str(row.x).replace("http://example.org/kinship#", ":"))
print(f"  Distinct individuals: {sorted(individuals_irr)}")

# Q-POST-CIR: self-ancestry
q_cir = """
PREFIX kin: <http://example.org/kinship#>
SELECT DISTINCT ?x WHERE { ?x kin:hasDescendant ?x . }
"""
results_cir = list(g.query(q_cir))
print(f"\nQ-POST-CIR (self-ancestry): {len(results_cir)} individual(s)")
for row in results_cir:
    print(f"  - {str(row.x).replace('http://example.org/kinship#', ':')}")

# Q-POST-CIR-ANC: self-ancestor
q_cir_anc = """
PREFIX kin: <http://example.org/kinship#>
SELECT DISTINCT ?x WHERE { ?x kin:hasAncestor ?x . }
"""
results_cir_anc = list(g.query(q_cir_anc))
print(f"\nQ-POST-CIR-ANC (self-ancestor): {len(results_cir_anc)} individual(s)")
for row in results_cir_anc:
    print(f"  - {str(row.x).replace('http://example.org/kinship#', ':')}")

# Q-POST-DIS: sibling also parent or child
q_dis = """
PREFIX kin: <http://example.org/kinship#>
SELECT DISTINCT ?x ?y WHERE {
    ?x kin:hasSibling ?y .
    { ?x kin:hasParent ?y . } UNION { ?x kin:hasChild ?y . }
}
"""
results_dis = list(g.query(q_dis))
print(f"\nQ-POST-DIS (sibling+parent/child): {len(results_dis)} pair(s)")
for row in results_dis[:10]:
    print(f"  - {str(row.x).replace('http://example.org/kinship#', ':')} - {str(row.y).replace('http://example.org/kinship#', ':')}")
if len(results_dis) > 10:
    print(f"  ... ({len(results_dis) - 10} more)")

# Q-POST-PAR: partner also in lineage
q_par = """
PREFIX kin: <http://example.org/kinship#>
SELECT DISTINCT ?x ?y WHERE {
    ?x kin:hasPartner ?y .
    { ?x kin:hasDescendant ?y . } UNION { ?x kin:hasAncestor ?y . }
}
"""
results_par = list(g.query(q_par))
print(f"\nQ-POST-PAR (partner+lineage): {len(results_par)} pair(s)")
for row in results_par[:10]:
    print(f"  - {str(row.x).replace('http://example.org/kinship#', ':')} - {str(row.y).replace('http://example.org/kinship#', ':')}")
if len(results_par) > 10:
    print(f"  ... ({len(results_par) - 10} more)")

# Q-POST-CAR: dual class membership
q_car = """
PREFIX kin: <http://example.org/kinship#>
SELECT DISTINCT ?x WHERE {
    ?x a kin:MalePerson .
    ?x a kin:FemalePerson .
}
"""
results_car = list(g.query(q_car))
print(f"\nQ-POST-CAR (MalePerson+FemalePerson): {len(results_car)} individual(s)")
for row in results_car:
    print(f"  - {str(row.x).replace('http://example.org/kinship#', ':')}")

print("\n=== SPIKE COMPLETE ===")
