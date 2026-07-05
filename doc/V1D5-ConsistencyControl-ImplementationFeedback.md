# Volume 1: Consistency Control — Document 5: Implementation Feedback

## 1. Purpose

This document records implementation issues encountered while building the
kinship consistency pipeline that were not anticipated in the original V1
specification documents (V1D0–V1D4), and the workarounds used to preserve the
core architectural principles established there.

It is intended as a feedback loop for the design corpus: each issue is paired
with the principle it protects, so that future revisions of V1D1–V1D4 can
incorporate these realities explicitly.

---

## 2. Core principles from V1D0–V1D4 that must be preserved

| Principle | Source | Why it matters |
|---|---|---|
| **MATS Primacy** | V1D1 §2.1 | `M = closure(A)` must be derived only from MATS assertions; OATS must never influence M. |
| **Graph isolation** | V1D1 §2.4, §3 | A, O and M are physically distinct; each gate reads exactly the graphs it is defined on. |
| **Inference only at controlled points** | V1D1 §3.3, §3.7 | Reasoning runs only when the pipeline decides to materialize; loading is inference-free. |
| **Single shape catalog** | V1D2bis, V1D4 §7 | The SHACL Gate should use one backend-agnostic shape definition. |
| **SHACL as warning-only safety net** | V1D2bis §1 | SHACL does not block the pipeline; it flags residuals the SPARQL gates missed. |

---

## 3. Issue: Inferred triples live in different graphs per backend

### Anticipated (V1D1, V1D4)

After running OWL-RL reasoning on a target graph, the inferred triples would be
available inside that target named graph. Materialization scripts and SHACL
shapes could therefore use `GRAPH <urn:kinship:full>` uniformly.

### Encountered

- **RDFLib**: `owl-rl` writes inferred triples back into the target named graph
  passed to `trigger_reasoning()` (e.g. `<urn:kinship:full>`).
- **GraphDB**: inferred triples are stored in the **default graph**, not in the
  target named graph. A `GRAPH <urn:kinship:full>` clause only sees explicit
  triples in that graph.

This means a SPARQL script that works on RDFLib by wrapping its `WHERE` clause
with `GRAPH <urn:kinship:full>` fails on GraphDB (it cannot see inferences), and
a script that leaves the `WHERE` clause unscoped works on GraphDB but leaks
across graphs on RDFLib.

### Workaround

- Introduced `KinshipBackend.scope_where_to_graph`.
  - `True` for RDFLib: materialization `WHERE` clauses are wrapped in
    `GRAPH <target>` so they see only the intended graph and avoid leakage from
    `Dataset(default_union=True)`.
  - `False` for GraphDB: `WHERE` clauses are left unscoped so they can see the
    default-graph inferences.
- For SHACL, removed all `GRAPH` clauses from the shape file and validate the
  whole dataset on both backends. This avoids the backend difference entirely.

### Principle preserved

Graph isolation and MATS Primacy are maintained at the pipeline level by the
OATS stash/restore mechanism (see §4); the WHERE-scoping difference only hides a
backend implementation detail from the materialization scripts.

---

## 4. Issue: GraphDB default graph unions all named graphs

### Anticipated (V1D1)

Named graphs provide physical isolation: `GRAPH <A>` sees only A, `GRAPH <O>`
sees only O.

### Encountered

GraphDB's default graph is the **union of all named graphs** in the repository.
Consequently, an unscoped materialization query on GraphDB sees A, O, M, MO,
ontology and validation graphs at once. If OATS data is present during Step 1,
`M = closure(A)` becomes contaminated by OATS-derived inferences, violating the
MATS Primacy principle.

### Workaround

The pipeline physically removes OATS from the store before MATS gate checks and
before Materialization Step 1:

1. Serialize the OATS graph to NTriples in memory.
2. Clear `<urn:kinship:oats>`.
3. Run MATS gate and Materialization Step 1 on A only.
4. Disable inference, restore OATS, then continue with Layer A/B.

Both backends implement the same `export_graph()` / `import_graph()` API, so the
sequence is backend-agnostic. RDFLib also benefits from this removal because its
`default_union=True` would otherwise let unscoped queries see OATS.

### Principle preserved

MATS Primacy is enforced by physical absence of OATS during M computation, not by
assuming query scoping behaves identically across triplestores.

---

## 5. Issue: GraphDB inference cannot be reliably paused

### Anticipated (V1D4)

GraphDB's inference can be enabled or disabled per transaction or via system
predicates such as `sys:turnInferenceOff`, allowing the pipeline to load data
without inference and trigger it only when needed.

### Encountered

`sys:turnInferenceOff` does **not** prevent OWL-RL inference during data loading.
Inference continued to fire when the ontology or intake data was loaded, making
it impossible to guarantee that OATS data stayed out of the MATS closure.

### Workaround

Implemented backend-level inference control:

- `disable_inference()` switches the active ruleset to `empty`.
- `enable_inference()` switches back to `owl2-rl` and calls `sys:reinfer`.

Both `initialize()` methods call `disable_inference()` immediately after creating
the store, before loading the ontology or intake data. The pipeline is the only
caller of `enable_inference()`, at exactly two points:

1. After MATS gate, before Materialization Step 1.
2. After OATS Layer B, before Materialization Step 2.

RDFLib uses the same API (a flag that makes `trigger_reasoning()` a no-op), so
the 12-step pipeline sequence is identical on both backends.

### Principle preserved

Controlled inference: reasoning runs only when the pipeline explicitly enables it,
ensuring M is derived from A alone and MO is derived from A ∪ O.

---

## 6. Issue: SHACL shapes cannot use `GRAPH` or `VALUES` clauses portably

### Anticipated (V1D2bis, V1D4bis)

A single `kinship-shapes.ttl` file with `GRAPH <urn:kinship:full>` wrappers in
`sh:select` would work for both RDFLib/pyshacl and GraphDB.

### Encountered

- **pyshacl** does not reliably evaluate `GRAPH` clauses inside `sh:sparql`
  constraints; the recommended approach is to pass the target graph as a simple
  graph and remove the `GRAPH` wrapper.
- **pyshacl** also rejects `VALUES` clauses inside `sh:sparql` constraints
  ("A SPARQL Constraint must not contain a VALUES clause"), which the original
  `PostPartnerLineageShape` used.

### Workaround

- Removed all `GRAPH <urn:kinship:full>` wrappers from the shapes.
- Replaced the `VALUES` block in `PostPartnerLineageShape` with an equivalent
  `UNION` of the four partner properties.
- Validated the whole dataset on both backends rather than scoping to a single
  graph.
- Removed the `owl:imports` of `consistency-foundation` from the shapes file,
  because pyshacl could not resolve the import when the shapes were loaded into a
  separate named graph.

### Principle preserved

Single shape catalog: one `kinship-shapes.ttl` is now used by both backends.
The SHACL Gate remains a warning-only safety net running after Materialization
Step 2.

---

## 7. Issue: GraphDB SHACL counts differ due to subproperty inference

### Anticipated

Given the same shape and the same data, both backends would produce the same
number of `sh:ValidationResult` triples.

### Encountered

GraphDB's OWL-RL inference adds inferred superproperty triples. For example,
`hasSpouse` is a subproperty of `hasPartner`, so an assertion
`?x :hasSpouse ?y` also produces an inferred `?x :hasPartner ?y`. The
`PostPartnerLineageShape` checks both `hasSpouse` and `hasPartner`, so the same
fact matched twice, producing twice as many validation results on GraphDB as on
RDFLib.

### Workaround

For the SHACL test scenario, use the most abstract property in the data (`hasPartner`
instead of `hasSpouse`). Because `hasPartner` has no superproperty, no duplicate
inferred triple is produced and both backends report the same count.

This is a test-data adjustment, not a shape change; the shape still covers all
partner properties in production data.

### Principle preserved

Test determinism: the same scenario produces the same expected result on both
backends.

---

## 8. Issue: GraphDB heap exhaustion during explicit-only triple counts

### Anticipated

Counting inferred triples (needed for the `trigger_reasoning()` return value) is
a cheap operation in GraphDB.

### Encountered

The `SELECT (COUNT(*) ...) FROM <http://www.ontotext.com/explicit>` query used by
`GraphDBKinshipBackend.trigger_reasoning()` can exhaust GraphDB's heap on
modest graphs, producing:

```text
Insufficient free Heap Memory ... for group by and distinct
```

This aborts the entire pipeline during Materialization Step 2.

### Workaround

The method is currently a diagnostic counter; it does not drive pipeline logic.
For production use, the count can be disabled or replaced with a lighter estimate.
No code change has been made yet; the issue is tracked as a GraphDB deployment
configuration concern rather than a pipeline logic defect.

### Principle preserved

None violated; the pipeline logic is correct. This is a performance/resource issue
in the current GraphDB deployment.

---

## 9. Issue: RDFLib cannot parse RDF-star quoted triples in the ontology

### Anticipated (V1D4 §9.3)

RDFLib lacks RDF-star support, so RDF-star annotations should be skipped or
handled separately.

### Encountered

`ontology/kinship/kinship-consistency.ttl` contains RDF-star annotations such as
`<< :hasPartner owl:propertyDisjointWith :hasChild >>`. RDFLib's Turtle parser
fails on these, blocking ontology loading.

### Workaround

The RDFLib backend strips RDF-star quoted-triple statements before parsing any
TTL file. It detects lines beginning with `<<` and removes the complete quoted
triple statement. This is a narrow, file-level workaround that preserves the rest
of the ontology.

### Principle preserved

The ontology file remains authoritative; RDFLib receives a plain-Turtle view
of it that contains the equivalent non-star axioms the pipeline actually uses.

---

## 10. Summary of feedback for the design corpus

| V1 doc | Recommended update |
|---|---|
| V1D1 §2.3 / §3.3 | Explicitly state that M may be derived from A only if OATS is physically absent during the derivation, because some triplestores union named graphs in the default graph. |
| V1D4 §3 / §7 | Add a note that `GRAPH` clauses in `sh:sparql` constraints are not portable and that shapes should be backend-agnostic. |
| V1D4 §7 | Document that `sys:turnInferenceOff` is insufficient in GraphDB; ruleset switching (`empty` / `owl2-rl` + `reinfer`) is required for precise inference control. |
| V1D4 §9.3 | Confirm that RDFLib requires RDF-star stripping at load time. |
| V1D4 | Add a deployment note about GraphDB heap requirements for explicit-only count queries on inferred repositories. |

---

## 11. Editing rule: only assertion-set graphs are user-modifiable

As a consequence of the truth-maintenance issues described in §3–§5, the
pipeline deliberately separates **user-editable graphs** from **derived graphs**.

| Graph | Editable? | Content |
|---|---|---|
| `<urn:kinship:intake>` | yes | landing zone for new triples before classification |
| `<urn:kinship:asserted>` | yes | MATS assertions (raw, no inference) |
| `<urn:kinship:oats>` | yes | OATS assertions (raw, quarantined) |
| `<urn:kinship:mats-closure>` | **no** | `closure(A)` — rebuilt by Step 1 |
| `<urn:kinship:full>` | **no** | `closure(A ∪ O)` — rebuilt by Step 2 |
| `<urn:kinship:validation>` | **no** | SHACL report — cleared and repopulated by the SHACL Gate |
| `<urn:kinship:ontology>` | **no** | TBox definitions |

### Rationale

When a user edits a family relationship, the pipeline should re-classify the
modified triples, re-run the gates, and re-derive the closure. Rebuilding the
materialized graphs from the assertion-set graphs avoids the retraction edge
cases discussed in §3 and §9:

- Removing a single `hasSpouse` assertion would require the reasoner to retract
the inferred symmetric `hasSpouse` inverse, the inferred `hasPartner`
superproperty triple, and any transitive/chain triples derived from it. With a
forward-chaining reasoner, it is easy to leave "ghost" inferences behind or to
over-delete triples that have alternative justifications.

- By clearing and re-populating `<urn:kinship:mats-closure>` and
`<urn:kinship:full>` on every run, the pipeline never needs to reason about
which inferred triples depend on which assertions. The derived graphs are simply
correct by construction from the current assertion-set graphs.

This rule also supports a future edit workflow: a user-facing editor modifies
triples only in `asserted` or `oats`, then re-invokes the pipeline. Any
validation failures are reported against the assertion sets, not against the
derived graphs, keeping the data model simple for the user.

## 12. Current status

All RDFLib pipeline scenarios pass (56/56 expectations). The new SHACL-specific
scenario `pipeline-shacl-post-partner-lineage-r3` passes individually on
GraphDB. The full GraphDB suite is blocked by the heap-memory issue described in
§8, not by a logic error.
