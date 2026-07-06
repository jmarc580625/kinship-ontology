# Volume 1: Consistency Control — Document 4bis: SHACL Gate Implementation

## 1. Purpose

This document describes the implementation of the SHACL Gate: how the shapes
file is structured, how validation is executed on each backend, and how the gate
result is interpreted by the pipeline.

---

## 2. Shape file design

A single `kinship-shapes.ttl` file is used on both backends without
modification. It defines four shapes, all targeting `kin:Person`:

| Shape | Residual category | What it detects |
| --- | --- | --- |
| `PostCycleShape` | R1 | Self-ancestry in `hasDescendant` / `hasAncestor` after materialization |
| `PostGenderShape` | R2 | Individual classified as both `MalePerson` and `FemalePerson` |
| `PostPartnerLineageShape` | R3 | Partnership between ancestor and descendant at any depth |
| `PostSiblingParentShape` | R1/R2 | Sibling cascade from an undetected generational cycle |

Design constraints that make the file backend-agnostic:

- **No `GRAPH` clauses** in `sh:sparql` constraints. pyshacl's behaviour with
  `GRAPH` inside `sh:sparql` is unreliable; removing them makes both backends
  validate the whole dataset uniformly.
- **No `VALUES` clauses** in `sh:sparql` constraints. pyshacl rejects them
  with "A SPARQL Constraint must not contain a VALUES clause".
  `PostPartnerLineageShape` uses `UNION` arms instead.
- **No `owl:imports`**. pyshacl cannot resolve imports when shapes are loaded
  into a named graph; the file is self-contained.

---

## 3. Validation execution

### RDFLib / pyshacl

pyshacl is called against the full `Dataset` object with `inference="none"`.
Inference has already been applied by the pipeline before the gate runs; no
additional reasoning is needed here.

```python
conforms, report_graph, report_text = pyshacl.validate(
    data_graph=dataset,        # full Dataset — all named graphs visible
    shacl_graph=shapes_graph,  # Graph extracted from urn:kinship:shapes
    advanced=True,
    inference="none",
    abort_on_first=False,
)
```

The report is a plain rdflib `Graph`. It is copied into `<urn:kinship:validation>`
for persistence and later queried by the gate's violation collector.

### GraphDB

The bulk SHACL validation endpoint is called against the full repository.
No `graphToValidate` parameter is specified; all shapes use no `GRAPH` clauses
so they naturally operate over the whole dataset.

### Violation count

Both backends count `sh:ValidationResult` instances in the report. Both emit
**one result per focus node** regardless of how many SPARQL rows the constraint
SELECT returns for that node. The count is therefore stable across backends even
when OWL-RL inference produces additional inferred triples that match multiple
UNION arms of the same shape.

---

## 4. Gate implementation

The gate is implemented in `src/kinship_pipeline/gates/shacl.py`.

### Run method

```python
def run(self, shapes_graph="urn:kinship:shapes",
              report_graph="urn:kinship:validation") -> dict:
    conforms, total_count = self.backend.run_shacl_validation(
        shapes_graph=shapes_graph,
        report_graph=report_graph,
    )
    if conforms or total_count == 0:
        return {"status": "ok", "conforms": True,
                "violations": [], "total_count": 0, "coverage_gap": 0}

    violations = self._collect_violations(report_graph)
    covered_nodes = {v["node"] for v in violations}
    coverage_gap = max(0, total_count - len(covered_nodes))

    return {"status": "warning", "conforms": False,
            "violations": violations, "total_count": total_count,
            "coverage_gap": coverage_gap}
```

### Violation collector

For each of the four shapes, a targeted SPARQL SELECT queries `<urn:kinship:validation>`
for `sh:ValidationResult` triples associated with that shape's URI. The result
is a flat list of `{shape, node, detail, message}` dicts.

### Coverage gap

`coverage_gap = total_count − len(distinct focus nodes collected)`. A non-zero
gap means the targeted queries did not account for all results in the report —
this indicates either an unknown shape fired or a query error, and should be
investigated.

---

## 5. Gate status and pipeline integration

The SHACL Gate is **warning-only**. It never blocks the pipeline. If violations
are found the pipeline status becomes `"warning"` and the materialized graph
remains usable, but the report indicates that upstream data should be reviewed.

```text
Precondition: Materialization Step 2 complete

ShaclGate.run()
    ↓
    conforms == True or total_count == 0 ?
    ↓ yes                      ↓ no
    status: ok                 status: warning
    Pipeline: warn             MO usable with caveat
    MO usable                  violations logged by shape
```

### Interpreting violations by shape

| Shape fired | Likely root cause | Action |
| --- | --- | --- |
| `POST-CYCLE` or `POST-SIBLING-PARENT` | R1/R2 — undetected cycle or materialization script bug | Review MATS gate and materialization scripts |
| `POST-GENDER` | R2 — conflicting gender assertion or GCI script bug | Review source data and gender scripts |
| `POST-PARTNER-LINEAGE` only | R3 — partnership+lineage at depth > 2, structurally beyond MATS PAR2 | Expected residual; MO is reliable |

A `POST-PARTNER-LINEAGE` violation in isolation is the expected residual for
depth-3+ cases that the MATS `Q-MATS-PAR2` query cannot reach. Any other shape
firing signals a gap in an upstream gate that should be resolved before MO is
considered authoritative.

---

## 6. Named graphs involved

| Graph | Role |
| --- | --- |
| `<urn:kinship:mats>` | Raw MATS assertions |
| `<urn:kinship:oats>` | Raw OATS assertions |
| `<urn:kinship:mats-materialization>` | Script-produced MATS derived triples |
| `<urn:kinship:oats-materialization>` | Script-produced OATS derived triples |
| default graph | All OWL-RL inferences |
| `<urn:kinship:shapes>` | SHACL shapes (loaded once at initialization) |
| `<urn:kinship:validation>` | SHACL report (cleared and repopulated on each run) |

The gate reads from the whole dataset (all graphs above) and writes only to
`<urn:kinship:validation>`.
