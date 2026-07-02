# Volume 1: Consistency Control — Document 1: Gates Pipeline Architecture

## 1. Overview and Purpose

This document describes the consistency control pipeline strategy. It is part of the broader consistency control framework.

The consistency control pipeline distinguishes between several categories of data at different stages of validation and materialization. Named graphs provide the structural mechanism that enforces these distinctions, ensuring that each gate queries exactly the data it is designed to operate on, and that no contamination between categories can silently corrupt a check.

This document describes the named graph architecture, explains why each graph exists, and maps each graph to the validation pipeline.

---

## 2. Fundamental Concepts

### 2.1 MATS Primacy Principle

The entire architecture rests on one foundational invariant.

```text
When a relation between two persons can be established from MATS
assertions, no OATS assertion may redefine, duplicate, or reinterpret
that relation.

MATS is the single source of truth for the kinship structure.

OATS assertions are only valid when they describe something genuinely
absent from the MATS-derived closure.
```

This principle does not enumerate specific conflicts. It enforces the primacy of MATS as a structural guarantee for all subsequent validation steps.

---

### 2.2 Closure semantics

**Closure definition.** Throughout this document, `closure(X)` means the set of all triples produced by applying the project's own materialization rules to the input set X. This includes `subPropertyOf` and `inverseOf` entailments, `owl:SymmetricProperty`, and the explicit materialization scripts for derived properties (`hasSibling`, `hasDescendant`, `hasAncestor`, etc.).

It does not refer to full OWL 2 DL inference. The triplestore's built-in reasoning rules (OWL RL, RDFS+) may contribute additional triples, but `closure(X)` is defined by the project's rules and scripts, not by the reasoning profile. If the triplestore adds richer reasoning in the future, this definition remains stable.

---

### 2.3 Graph notation

The following notation is used throughout this document.

```text
A   = <urn:kinship:asserted>

      Raw MATS triples only.
      No inference applied.
      OATS-free by invariant.

O   = <urn:kinship:oats>

      Raw OATS triples in quarantine.
      No inference applied.

M   = <urn:kinship:mats-closure>

      closure(A)

      All triples derivable from MATS assertions alone via
      subPropertyOf,
      inverseOf,
      owl:SymmetricProperty,
      and the project's materialization scripts.

MO  = <urn:kinship:full>

      closure(A ∪ O)

      Full working graph produced after both OATS validation layers have
      succeeded.

      Contains all MATS inferences, all validated OATS triples, and all
      inferences from their union.
```

The two materialization steps are sequential and non-interchangeable.

```text
Step 1   A → M

Step 2   A ∪ O → MO
```

---

### 2.4 Core invariants

The architecture relies on the following permanent invariants.

```text
OATS triples never enter A and never influence M.

A is only written by the MATS pipeline.

M is only derived from A.

Therefore M is permanently free of any OATS contribution.
```

This guarantees that every validation stage always operates on the data it is intended to validate.

It also establishes a one-way dependency.

```text
OATS validation depends on A and M,

but A and M never depend on OATS validation.
```

Consequently, any modification of A after OATS validation may invalidate previously validated OATS assertions and therefore requires revalidation.

---

## 3. Named Graph Architecture

### 3.1 Named graph inventory

| Graph                        | Notation | Role                                          |
| ---------------------------- | -------- | --------------------------------------------- |
| `<urn:kinship:ontology>`     | —        | Ontology definitions and consistency metadata |
| `<urn:kinship:intake>`       | —        | Landing zone for incoming triples             |
| `<urn:kinship:asserted>`     | A        | Raw MATS assertions                           |
| `<urn:kinship:mats-closure>` | M        | `closure(A)`                                  |
| `<urn:kinship:oats>`         | O        | Raw OATS assertions awaiting validation       |
| `<urn:kinship:full>`         | MO       | `closure(A ∪ O)`                              |
| `<urn:kinship:validation>`   | —        | SHACL validation results                      |
| `<urn:kinship:temp-closure>` | —        | Temporary graph used during cycle detection   |

---

### 2.2 Why graph isolation is required

Graph isolation is a correctness requirement, not an organizational choice.

The critical constraint in this architecture is that `<urn:kinship:asserted>` must never receive an OATS triple, and that `<urn:kinship:mats-closure>` must be derived exclusively from `<urn:kinship:asserted>`.

These are not conventions—they are what makes the OATS Layer A check logically correct.

Layer A determines whether an OATS assertion connects two persons already linked in the validated MATS closure. The trusted evidence is therefore read exclusively from M, which contains only the closure of validated MATS assertions.

Because `hasLineageRelative` is an inferred relation, it is never asserted directly in A. It becomes available only after materialization step 1 has computed the MATS closure.

If OATS triples were allowed to contribute to M, Layer A would begin using OATS-derived evidence to reject OATS assertions, creating false positives and violating the MATS Primacy Principle.

The permanent separation between A, M and O therefore guarantees that the trusted evidence used during OATS validation is never contaminated by OATS data.

---

## 3. Pipeline Architecture

The consistency control pipeline is composed of a sequence of validation and materialization stages. Each stage operates on a well-defined set of named graphs and has explicit preconditions. A stage executes only when its preconditions are satisfied; otherwise, the pipeline blocks until the inconsistency is resolved.

The overall execution sequence is:

```text
Incoming triples
        │
        ▼
    FATS Gate
        │
        ▼
    MATS Gate
        │
        ▼
Materialization Step 1
        │
        ▼
 OATS Gate – Layer A
        │
        ▼
 OATS Gate – Layer B
        │
        ▼
Materialization Step 2
        │
        ▼
    SHACL Gate
```

---

### 3.1 FATS Gate

**Purpose**:

The FATS gate classifies every incoming assertion according to its assertion set and routes it to the appropriate named graph.

**Preconditions**:

* Incoming triples are present in `<urn:kinship:intake>`.

**Reads**:

* `<urn:kinship:intake>`
* `<urn:kinship:ontology>` (classification metadata)

**Writes**:

* MATS assertions are copied to `<urn:kinship:asserted>`.
* OATS assertions are copied to `<urn:kinship:oats>`.
* FATS assertions are rejected.
* `<urn:kinship:intake>` is cleared after successful routing.

**Outcome**:

The pipeline starts with two isolated datasets:

* raw MATS assertions (A)
* raw OATS assertions (O)

No inference has yet been performed.

---

### 3.2 MATS Gate

**Purpose**:

The MATS gate validates the internal consistency of all MATS assertions before any inference is performed.

Only a fully consistent MATS dataset is allowed to proceed to materialization.

**Preconditions**:

* `<urn:kinship:asserted>` is not empty.

**Reads**:

* `<urn:kinship:asserted>`
* `<urn:kinship:ontology>`

**Writes**:

None.

This is a read-only validation stage.

**Outcome**:

If every MATS validation succeeds, the pipeline proceeds to materialization.

Otherwise the pipeline blocks, and the offending assertions remain in A until corrected or removed.

---

### 3.3 Materialization Step 1

**Purpose**:

Materialization Step 1 computes the closure of the validated MATS assertions.

**Preconditions**:

* The MATS gate has completed successfully.

**Reads**:

* `<urn:kinship:asserted>` (A)

**Writes**:

* `<urn:kinship:mats-closure>` (M)

**Outcome**:

M contains the complete closure of validated MATS assertions.

Because M is derived exclusively from A, it is permanently free of any OATS contribution.

This graph becomes the trusted evidence source for the first OATS validation layer.

---

### 3.4 OATS Gate — Layer A

**Purpose**:

Layer A verifies that every OATS assertion is compatible with the validated MATS closure.

Its role is to prevent OATS assertions from redefining, duplicating or contradicting relationships that are already established by MATS.

**Preconditions**:

* M is available.

**Reads**:

* `<urn:kinship:oats>`
* `<urn:kinship:mats-closure>`
* `<urn:kinship:ontology>`

**Writes**:

None.

This is a read-only validation stage.

**Outcome**:

Assertions that conflict with the trusted MATS closure are rejected.

Assertions that pass remain in O awaiting Layer B validation.

They are **not** promoted to any other graph.

The permanent invariants remain unchanged:

```text
OATS assertions are never promoted to A.

M continues to be derived exclusively from A.
```

---

### 3.5 OATS Gate — Layer B

**Purpose**:

Layer B validates the internal consistency of the remaining OATS assertions.

Unlike Layer A, which compares OATS against MATS, Layer B evaluates consistency entirely within the OATS dataset.

**Preconditions**:

All OATS assertions have successfully passed Layer A.

**Reads**:

* `<urn:kinship:oats>`
* `<urn:kinship:ontology>`

**Writes**:

None.

This is a read-only validation stage.

**Outcome**:

If every OATS validation succeeds, the pipeline proceeds to the second materialization step.

Otherwise the offending assertions remain in O until corrected or removed.

---

### 3.6 Materialization Step 2

**Purpose**:

Materialization Step 2 builds the complete working graph from validated MATS and validated OATS assertions.

**Preconditions**:

* Layer A has succeeded.
* Layer B has succeeded.

**Reads**:

* `<urn:kinship:asserted>` (A)
* `<urn:kinship:oats>` (O)

**Writes**:

* `<urn:kinship:full>` (MO)

**Outcome**:

MO contains

* all validated MATS assertions,
* all validated OATS assertions,
* the complete closure of their union.

This graph is the working graph used by SHACL validation and by downstream applications.

---

### 3.7 SHACL Gate

**Purpose**:

The SHACL gate provides a final post-materialization verification layer.

It is intended as a safety net rather than the primary validation mechanism.

A dataset that successfully passed every previous validation stage is expected to produce no SHACL violations.

**Preconditions**:

* MO is available.

**Reads**:

* `<urn:kinship:full>`
* `<urn:kinship:ontology>`

**Writes**:

* `<urn:kinship:validation>`

**Outcome**:

Any SHACL violation indicates either

* a gap in the pre-materialization validation rules, or
* a regression in the validation pipeline.

SHACL therefore validates the complete inferred dataset rather than participating in the primary consistency checks.

---

## 4. Global Consistency Principles

### 4.1 Lineage takes precedence

The consistency model is founded on the principle that lineage and partnership relationships established from MATS assertions take precedence over all collateral, in-law and step-family relationships.

Whenever the relationship between two individuals can be established from validated MATS assertions, an OATS assertion describing the same pair is considered either redundant or inconsistent.

This is a deliberate ontological design choice rather than a technical consequence of the implementation.

```text
Design principle

Lineage and partnership relations established in the MATS graph take
precedence over all collateral, in-law and step-family OATS assertions.

If the full relational structure between two individuals is already
captured by the MATS-derived closure, adding an OATS relation between
them is either

• redundant (already derivable), or

• inconsistent (contradicts the established structure).

In either case the OATS assertion is rejected.
```

Consequently, once direct lineage and partnership relationships have been described through MATS assertions, the ontology is trusted to derive all compatible relationships automatically.

---

### 4.2 Graph independence

The pipeline relies on the permanent independence of the MATS and OATS validation paths.

The dependency between graphs is intentionally one-way.

```text
A ─────► M

│

└──────────────► MO

O ─────────────► MO
```

This architecture guarantees that:

* MATS validation never depends on OATS.
* OATS validation depends on the validated MATS closure.
* OATS assertions never modify the trusted evidence used during their own validation.

This separation is the fundamental correctness property of the pipeline.

---

### 4.3 Retroactive invalidation

Adding a new MATS assertion after OATS assertions have already been validated may invalidate previously accepted OATS assertions.

The new MATS assertion can introduce relationships in the refreshed MATS closure that were not present when the OATS assertions were originally evaluated.

The recommended strategy is therefore to perform deferred revalidation.

After every modification of A:

1. Materialization Step 1 refreshes M.
2. OATS Layer A is executed again against the unchanged O.
3. Any OATS assertion that no longer satisfies Layer A is reported for user resolution.

This is a correctness-first design choice.

For the expected scale of a family genealogy, revalidating the complete OATS graph is sufficiently inexpensive while guaranteeing that no indirect invalidation is overlooked.

---

## 5. Complete Pipeline Summary

### 5.1 Pipeline overview

```text
                 +--------------------+
                 |      Intake        |
                 +--------------------+
                           │
                           ▼
                 +--------------------+
                 |     FATS Gate      |
                 +--------------------+
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
     +----------------+        +----------------+
     |   Asserted A   |        |    OATS O      |
     +----------------+        +----------------+
              │
              ▼
     +----------------+
     |   MATS Gate    |
     +----------------+
              │
              ▼
     +----------------+
     | Materialization|
     |    Step 1      |
     +----------------+
              │
              ▼
     +----------------+
     | MATS Closure M |
     +----------------+
              │
              ▼
     +----------------+
     | OATS Layer A   |
     +----------------+
              │
              ▼
     +----------------+
     | OATS Layer B   |
     +----------------+
              │
              ▼
     +----------------+
     | Materialization|
     |    Step 2      |
     +----------------+
              │
              ▼
     +----------------+
     |     Full MO    |
     +----------------+
              │
              ▼
     +----------------+
     |   SHACL Gate   |
     +----------------+
              │
              ▼
     +----------------+
     | Validation     |
     +----------------+
```

---

### 5.2 Graph summary

| Graph                        | Purpose                                              |
| ---------------------------- | ---------------------------------------------------- |
| `<urn:kinship:ontology>`     | Ontology definitions and metadata                    |
| `<urn:kinship:intake>`       | Temporary landing zone                               |
| `<urn:kinship:asserted>`     | Validated MATS assertions                            |
| `<urn:kinship:mats-closure>` | Closure derived exclusively from MATS                |
| `<urn:kinship:oats>`         | OATS assertions awaiting or having passed validation |
| `<urn:kinship:full>`         | Complete inferred working graph                      |
| `<urn:kinship:validation>`   | SHACL validation results                             |

---

### 5.3 Pipeline summary

| Stage                  | Reads               | Writes          |
| ---------------------- | ------------------- | --------------- |
| FATS Gate              | Intake              | Asserted / OATS |
| MATS Gate              | Asserted            | —               |
| Materialization Step 1 | Asserted            | MATS Closure    |
| OATS Layer A           | OATS + MATS Closure | —               |
| OATS Layer B           | OATS                | —               |
| Materialization Step 2 | Asserted + OATS     | Full            |
| SHACL Gate             | Full                | Validation      |

---

## 6. Scope of this document

This document specifies the architecture of the consistency control pipeline:

* the role of each named graph;
* the execution sequence of the validation pipeline;
* the responsibilities of each validation stage;
* the architectural invariants that guarantee correctness.

The detailed specification of validation rules, generated queries, implementation algorithms and platform-specific considerations is intentionally outside the scope of this document and is described in the companion document *Consistency Control – Validation Rules Specification*.

---
