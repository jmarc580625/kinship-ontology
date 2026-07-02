# Volume 1: Consistency Control — Document 4: Implementation Paths

## 1. Purpose

This document describes implementation paths for the consistency control
pipeline defined in Document 1 (Gates Pipeline Architecture) and Document 2
(Gate Pipelines and Pattern Catalogs), across the two targeted
triplestores: rdflib and GraphDB.

## 2. FATS Gate

| Mechanism | rdflib | GraphDB |
| --- | --- | --- |
| Property-type rejection at ingestion | filter on predicate before `graph.add()` | SHACL shape with `sh:targetSubjectsOf` on the FATS property list, applied to the intake graph |
| Bulk check on existing data | `graph.query()` with a `VALUES` clause over FATS properties, scoped to `<urn:kinship:intake>` | same SPARQL query via the REST endpoint |

## 3. MATS Gate

Both triplestores execute the same SPARQL SELECT/ASK queries from the
pattern catalog (Document 2) without modification, scoped to
`<urn:kinship:asserted>`:

| Mechanism | rdflib | GraphDB |
| --- | --- | --- |
| Pre-inference pattern queries | `graph.query(sparql_string)` | `POST /repositories/{id}` with the query string |
| Pipeline staging (MATS Gate steps) | sequential Python function calls, each wrapping a query | sequential REST calls, or a single SPARQL script orchestrated externally |

## 4. Named-graph quarantine architecture

| Mechanism | rdflib | GraphDB |
| --- | --- | --- |
| Multiple named graphs | `ConjunctiveGraph` with distinct context URIs (`intake`, `asserted`, `mats-closure`, `oats`, `full`, `validation`) | native — named graphs are a core feature, no special setup |
| Promotion from intake to asserted / oats | `graph.query()` SELECT + manual `graph.add()`/`graph.remove()` across contexts | `INSERT ... WHERE` / `DELETE ... WHERE` SPARQL UPDATE across named graphs in a single statement |
| Cross-graph query (Layer A's two-`GRAPH` pattern) | native — `graph.query()` supports multiple `GRAPH` clauses against a `ConjunctiveGraph` | native — standard SPARQL feature against named graphs in the same repository |

## 5. OATS Gate — Layer A

Layer A is implemented as a single generated SPARQL query (see Document 1
for its full specification and Document 3 for the cross-set generalization)
— **not** as a SHACL shape. It reads two graphs via explicit `GRAPH`
clauses: `<urn:kinship:oats>` (the candidate OATS triple under test) and
`<urn:kinship:mats-closure>` (the trusted MATS evidence).

| Mechanism | rdflib | GraphDB |
| --- | --- | --- |
| Query execution | `graph.query(sparql_string)`, with the `ConjunctiveGraph` exposing both the `oats` and `mats-closure` contexts to the same query | `POST /repositories/{id}` with the query string, both named graphs residing in the same repository |
| Result handling | each result row identifies the conflicting OATS triple and the MATS evidence it conflicts with — no separate report graph is produced | same; results are consumed directly, not persisted to a dedicated graph |

No SHACL infrastructure, validation engine, or report graph is involved in
Layer A. The SHACL validation engine described in §7 below belongs
exclusively to the SHACL Gate, a distinct stage that runs later in the
pipeline, after Materialization Step 2.

## 6. OATS Gate — Layer B

Implemented identically to the MATS gate pattern queries — plain SPARQL
with explicit `VALUES` enumerations over the OATS properties, scoped to
`<urn:kinship:oats>`. No additional infrastructure beyond what the MATS
gate queries already require.

## 7. SHACL Gate — positioning only

The SHACL Gate is a distinct, later stage of the pipeline (see Document 1,
§3.7): it runs after Materialization Step 2, reads `<urn:kinship:full>`,
and writes `<urn:kinship:validation>`. Its shapes and detection queries are
a separate, less mature specification (Document 2bis) to be revisited; the
table below positions its implementation mechanism within the corpus
without consolidating its content.

| Mechanism | rdflib | GraphDB |
| --- | --- | --- |
| SHACL validation engine | `pyshacl.validate()` against a shapes graph, with the data graph limited to the `<urn:kinship:full>` context | native SHACL support — shapes loaded into a dedicated named graph, validation triggered via `POST /rest/repositories/{id}/shacl/validate` |
| Validation report storage | in-memory `Graph` object returned by `pyshacl`, or serialized to a file | `sh:ValidationResult` triples persisted into `<urn:kinship:validation>` |
| Targeted querying of results | `graph.query()` over the returned report graph | SPARQL SELECT filtered by `sh:sourceShape` over `<urn:kinship:validation>` |

## 8. Ad-hoc ingestion parser

Purely a Python-side concern in both cases — the parser sits in front of
either triplestore and only needs an HTTP client (`requests`) for GraphDB
or direct `Graph` manipulation for rdflib. No triplestore-specific
constraint.

```python
MATS_PROPS = {KIN.hasBloodChild, KIN.hasBloodParent, KIN.hasGender, ...}
FATS_PROPS = {KIN.hasRelative, KIN.hasDescendant, KIN.MalePerson, ...}

def classify(p):
    if p in FATS_PROPS:
        return "FATS"
    if p in MATS_PROPS:
        return "MATS"
    return "OATS"
```

## 9. Transactional safety

### 9.1 Pre-insertion ASK check

The pre-condition check below corresponds to the Layer A query of §5: an
ASK form of the same two-graph pattern, evaluated before an OATS triple is
admitted to `<urn:kinship:oats>`.

| Mechanism | rdflib | GraphDB |
| --- | --- | --- |
| Pre-condition check before adding an OATS triple | `graph.query("ASK {...}")` scoped to the `mats-closure` context, evaluated synchronously before adding to the `oats` context | `GET /repositories/{id}` with an ASK query scoped to `<urn:kinship:mats-closure>`, evaluated before issuing the `INSERT` into `<urn:kinship:oats>` |
| Atomicity of check + insert | not native — must be simulated (snapshot the graph state, roll back on failure) | native transactions via `POST /transactions`, with `COMMIT`/rollback (implicit on transaction abandonment) |

```python
# GraphDB — atomic check-then-insert via REST transactions
tx = requests.post(f"{BASE}/transactions").headers["Location"]
ask = requests.get(BASE, params={"query": ask_query}).json()["boolean"]
if ask:
    requests.delete(tx)          # abort — OATS would conflict
else:
    requests.post(tx, params={"action": "ADD"}, data=triple_data,
                  headers={"Content-Type": "text/turtle"})
    requests.put(f"{tx}?action=COMMIT")
```

```python
# rdflib — simulated atomicity via snapshot/rollback
snapshot = copy.deepcopy(graph)
if list(graph.query(ask_query))[0][0].toPython():
    graph = snapshot              # rollback
    raise ValueError("OATS rejected: conflicts with existing MATS link")
graph.add(triple)                 # commit
```

### 9.2 Deferred re-validation

Both triplestores re-run the Layer A query after every MATS-affecting
transaction; the mechanism is identical to the initial Layer A execution
(§5), simply re-triggered after Materialization Step 1 has refreshed
`<urn:kinship:mats-closure>`. No additional infrastructure is required
beyond scheduling the re-run, which can be a simple post-commit hook in
either environment.

### 9.3 RDF-star temporal marking

| Mechanism | rdflib | GraphDB |
| --- | --- | --- |
| RDF-star (quoted triples) support | not supported as of mid-2026 (confirmed by rdflib maintainers; RDF 1.2 is still a Working Draft) | native support |
| Querying by assertion timestamp | not available | SPARQL-star SELECT via the standard endpoint |

```turtle
<<:alice :hasSibling :carol>> :assertedAt "2026-03-01"^^xsd:date .
```

## 10. Practical recommendation

For the target scale of this ontology (a few hundred individuals per
family network), rdflib with `pyshacl` is sufficient for prototyping and
small deployments, with the caveat that transactional atomicity must be
simulated rather than relying on native support, and that RDF-star-based
audit trails are unavailable. GraphDB is preferable for any deployment
requiring concurrent writers, native transaction guarantees, or RDF-star
audit trails, and its native SHACL engine removes the need for an external
validation library for the SHACL Gate.
