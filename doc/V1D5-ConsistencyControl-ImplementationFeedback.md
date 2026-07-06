# Volume 1: Consistency Control — Document 5: Implementation Feedback

## 1. Purpose

This document records the gaps between the original V1 specification documents
(V1D0–V1D4) and the current implementation of the kinship consistency pipeline.
Each section states what the specification assumed, what the implementation
actually does, and which design principle is thereby preserved.

It is intended as a feedback loop for the design corpus: future revisions of
V1D1–V1D4 should incorporate these decisions explicitly so that the specification
and the implementation remain consistent.

---

## 2. Core principles from V1D0–V1D4 that must be preserved

| Principle | Source | Why it matters |
|---|---|---|
| **MATS Primacy** | V1D1 §2.1 | `M = closure(A)` must be derived only from MATS assertions; OATS must never influence M. |
| **Graph isolation** | V1D1 §2.4, §3 | A, O and M are physically distinct; each gate reads exactly the graphs it is defined on. |
| **Inference only at controlled points** | V1D1 §3.3, §3.7 | Reasoning runs only when the pipeline decides to materialize; loading is inference-free. |
| **Single shape catalog** | V1D2bis, V1D4 §7 | The SHACL Gate uses one backend-agnostic shape definition. |
| **SHACL as warning-only safety net** | V1D2bis §1 | SHACL does not block the pipeline; it flags residuals the SPARQL gates missed. |
| **OATS Layer B is a blocking gate** | V1D1 §3.5 | Materialization Step 2 has the precondition that Layer B has succeeded; a violation skips Step 2 and the SHACL Gate. |

---

## 3. Inference placement: both backends write inferences to the default graph

### Specification assumption (V1D1, V1D4)

Inferred triples would be available inside the target named graph after
`trigger_reasoning()`, so materialization scripts could scope their `WHERE`
clauses with `GRAPH <target>`.

### Implementation

On **GraphDB**, OWL-RL inferences are stored in the **default graph**, not in
the target named graph. On **RDFLib**, `trigger_reasoning()` clears the default
graph and writes all OWL-RL inferences there, reasoning over the full dataset
(ontology + all named graphs) so that inferences derived from the asserted named
graph are visible.

As a result:

- Materialization scripts use **unscoped `WHERE` clauses** on both backends so
  they can see the default-graph inferences.
- `mats-materialization` and `oats-materialization` contain only
  **script-produced derived triples**; asserted data is never copied into them.
- The default (implicit) graph holds all OWL-RL inferences and is cleared and
  re-derived on every pipeline run.
- SHACL shapes use no `GRAPH` clauses and validate the whole dataset, which
  includes both the named graphs and the default graph.

### Principle preserved

Graph isolation: named graphs hold only what the pipeline explicitly places
there. MATS Primacy: the asserted graph is never mixed into the materialization
targets.

---

## 4. OATS isolation: physical removal required during MATS materialization

### Specification assumption (V1D1)

Named graphs provide physical isolation. A `GRAPH <oats>` clause sees only OATS
data; an unscoped query sees only what is logically in scope.

### Implementation

GraphDB's default graph is the **union of all named graphs**. An unscoped
materialization query therefore sees A, O, ontology, and validation graphs
simultaneously. If OATS data is present during Step 1, OWL-RL inference over
the default graph produces `M = closure(A ∪ O)` instead of `M = closure(A)`,
violating MATS Primacy.

RDFLib with `default_union=True` exhibits the same behaviour.

The pipeline physically removes OATS before the MATS gate and keeps it absent
through Materialization Step 1:

1. Serialize `<urn:kinship:oats>` to NTriples in memory (`export_graph()`).
2. Clear `<urn:kinship:oats>`.
3. Run the MATS gate on A only.
4. Enable inference, run Materialization Step 1 (A → M), disable inference.
5. Restore OATS (`import_graph()`), then continue with OATS Layer A/B and
   Materialization Step 2.

Both backends expose the same `export_graph()` / `import_graph()` API, so the
sequence is backend-agnostic.

### Principle preserved

MATS Primacy is enforced by physical absence of OATS during M computation.

---

## 5. Inference control: ruleset switching rather than per-transaction flags

### Specification assumption (V1D4)

GraphDB inference can be paused per transaction via `sys:turnInferenceOff`.

### Implementation

`sys:turnInferenceOff` does not prevent OWL-RL inference during data loading.
Both backends instead implement `disable_inference()` and `enable_inference()`:

- **GraphDB**: `disable_inference()` switches the active ruleset to `empty`;
  `enable_inference()` switches back to `owl2-rl` and calls `sys:reinfer`.
- **RDFLib**: `disable_inference()` sets an internal flag that makes
  `trigger_reasoning()` a no-op; `enable_inference()` clears the flag and
  immediately runs a full OWL-RL pass over the dataset.

`initialize()` calls `disable_inference()` before loading any ontology or intake
data. The pipeline is the only caller of `enable_inference()`, at exactly two
points:

1. After the MATS gate, before Materialization Step 1.
2. After OATS Layer B, before Materialization Step 2.

### Principle preserved

Inference only at controlled points: reasoning runs only when the pipeline
explicitly enables it, ensuring M is derived from A alone and MO from A ∪ O.

---

## 6. SHACL shapes: no `GRAPH` clauses, no `VALUES` in `sh:sparql`

### Specification assumption (V1D2bis, V1D4bis)

A single `kinship-shapes.ttl` with `GRAPH <urn:kinship:oats-materialization>`
wrappers in `sh:select` would work on both backends.

### Implementation

pyshacl does not reliably evaluate `GRAPH` clauses inside `sh:sparql`
constraints, and explicitly rejects `VALUES` clauses inside them ("A SPARQL
Constraint must not contain a VALUES clause"). Additionally, pyshacl cannot
resolve `owl:imports` when shapes are loaded into a separate named graph.

The shapes file therefore:

- Contains no `GRAPH` clauses; all shapes validate the whole dataset.
- Uses `UNION` arms instead of a `VALUES` block in `PostPartnerLineageShape`.
- Contains no `owl:imports`.

Both backends (pyshacl on RDFLib, the bulk validation endpoint on GraphDB)
validate the full dataset in a single call. Both emit one `sh:ValidationResult`
per focus node regardless of how many SPARQL query rows match for that node.

### Principle preserved

Single shape catalog: one `kinship-shapes.ttl` works on both backends without
modification.

---

## 7. GraphDB heap exhaustion on explicit-triple count queries

### Specification assumption

Counting inferred triples (the return value of `trigger_reasoning()`) is a cheap
operation in GraphDB.

### Implementation

The `SELECT (COUNT(*) ...) FROM <http://www.ontotext.com/explicit>` query in
`GraphDBKinshipBackend.trigger_reasoning()` can exhaust GraphDB's JVM heap on
modest graphs:

```text
Insufficient free Heap Memory ... for group by and distinct
```

This count is a diagnostic metric; it does not drive any pipeline logic. The
pipeline completes correctly regardless of whether the count succeeds. Increasing
the GraphDB JVM heap or disabling the count for production deployments resolves
the issue.

### Principle preserved

No pipeline principle is violated. This is a deployment configuration concern.

---

## 8. RDFLib: RDF-star annotations stripped at load time

### Specification assumption (V1D4 §9.3)

RDF-star annotations in the ontology would be skipped or handled separately by
the RDFLib backend.

### Implementation

`kinship-consistency.ttl` contains RDF-star quoted-triple annotations such as
`<< :hasPartner owl:propertyDisjointWith :hasChild >>`. RDFLib's Turtle parser
rejects these, blocking ontology loading.

The RDFLib backend strips lines beginning with `<<` before parsing any TTL file.
The equivalent plain-Turtle axioms that the pipeline actually uses are retained
unchanged.

### Principle preserved

The ontology file remains authoritative; RDFLib receives a plain-Turtle view
that contains all the axioms the pipeline requires.

---

## 9. Named graph scoping summary

| Graph | Editable? | Content |
|---|---|---|
| `<urn:kinship:intake>` | yes | landing zone before FATS classification |
| `<urn:kinship:mats>` | yes | MATS assertions (raw, no inference) |
| `<urn:kinship:oats>` | yes | OATS assertions (raw, quarantined) |
| `<urn:kinship:mats-materialization>` | **no** | script-produced triples from Step 1 only |
| `<urn:kinship:oats-materialization>` | **no** | script-produced triples from Step 2 only |
| default graph | **no** | all OWL-RL inferences; cleared and re-derived on every run |
| `<urn:kinship:validation>` | **no** | SHACL report; cleared and repopulated by the SHACL Gate |
| `<urn:kinship:ontology>` | **no** | TBox definitions |
| `<urn:kinship:shapes>` | **no** | SHACL shapes |

Derived graphs (`mats-materialization`, `oats-materialization`, default graph,
`validation`) are fully rebuilt on every pipeline run. A user-facing editor
modifies triples only in `mats` or `oats`, then re-invokes the pipeline.
Validation failures are reported against the assertion sets, not the derived
graphs.

---

## 10. Recommended updates to the design corpus

| V1 doc | Recommended update |
|---|---|
| V1D1 §2.3 / §3.3 | State that M requires OATS to be physically absent from the store during derivation; unscoped queries on some triplestores see all named graphs via the default graph. |
| V1D1 §2.3 / §3.3 | Clarify that `mats-materialization` and `oats-materialization` contain only script-produced triples; OWL-RL inferences reside in the default/implicit graph on both backends. |
| V1D1 §3.5 | Confirm that OATS Layer B is a blocking gate: a violation skips Materialization Step 2 and the SHACL Gate. |
| V1D4 §3 / §7 | Note that `GRAPH` clauses and `VALUES` in `sh:sparql` constraints are not supported by pyshacl; shapes must be backend-agnostic. |
| V1D4 §7 | Replace `sys:turnInferenceOff` with ruleset switching (`empty` / `owl2-rl` + `reinfer`) as the mechanism for inference control in GraphDB. |
| V1D4 §7 | Document that both backends write OWL-RL inferences to the default graph; materialization scripts use unscoped `WHERE` clauses accordingly. |
| V1D4 §9.3 | Confirm that RDF-star annotations are stripped by the RDFLib backend at load time. |
| V1D4 | Add a deployment note on GraphDB JVM heap requirements for explicit-triple count queries on inferred repositories. |

---

## 11. Current status

All 8 pipeline scenarios pass on both backends (50/50 expectations on RDFLib,
50/50 on GraphDB). Scenarios cover:

- FATS blocked and FATS property rejection
- MATS violations (all violation families)
- Clean end-to-end run (`pipeline-mats-on-core`)
- OATS clean pass
- OATS Layer A violation (blocks Layer B, Step 2, and SHACL Gate)
- OATS Layer B violation (blocks Step 2 and SHACL Gate)
- SHACL residual R3 case (`PostPartnerLineageShape` at depth > 2)

The GraphDB `--all` suite occasionally raises a heap-memory error during
teardown (`graph_size` in cleanup) as described in §7; this does not affect
scenario results — all expectations pass before teardown.
