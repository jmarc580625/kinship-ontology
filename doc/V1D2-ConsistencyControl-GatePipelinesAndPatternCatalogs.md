# Volume 1 — Document 2: Validation Gate Pipelines and Pattern Catalogs

## 1. Purpose

This document presents the catalog of identified erroneous data patterns
for each Assertion Type Set (FATS, MATS, OATS) and the SPARQL queries used
to detect them. Its objectives are:

- to identify the exhaustiveness of assertion forms (direct and indirect
  via `owl:inverseOf`);
- to ensure independence from inference and materialization mechanisms, except
  for the OATS Gate Layer A, every detection query in this document runs
  against raw asserted data, before any reasoning step;
- to establish a clear hierarchy by problem family;
- to account for blocking errors as well as data entry anomalies (semantic
  redundancies, etc.).

The catalog is organized by Assertion Type Set defined in Document 0: FATS,
then MATS, then OATS.

Within the MATS and OATS gates, detection queries are grouped into
**steps** — an ordered execution sequence within the gate, not separate
gates. Steps are ordered by two criteria applied in combination: severity
(blocking errors before warnings) and complexity (cheaper, more selective
queries first, for fail-fast behaviour).

A fourth gate, the post-inference SHACL validation layer, follows the OATS
gate in the overall pipeline. Its role and current scope are introduced at
the end of this document; its content remains a separate, less mature
specification to be revisited (see Document 2bis).

## 2. Notation

Patterns use SPARQL property path syntax as a conceptual shorthand, not
valid Turtle. `(:hasChild | :hasBloodChild | :hasAdoptiveChild)` means "any
of these properties".

Each pattern represents a minimal set of assertions that, taken together,
are inconsistent or redundant.

Patterns cover all assertion forms (direct and inverse via `owl:inverseOf`)
to enable SPARQL detection without relying on inference or materialization.

```sparql
PREFIX kin: <http://example.org/kinship#>
```

is assumed in every query header below.

---

## 3. FATS Gate

### 3.1 Scope

The Forbidden Assertion Types Set includes the following class and
property assertions:

- Classes:
  - `MalePerson`
  - `FemalePerson`
- Properties:
  - `hasRelative`
  - `hasLineageRelative`
  - `hasCeremonialBond`
  - `hasCollateralRelative`
  - `hasInLawRelative`
  - `hasStepRelative`
  - `hasDescendant`
  - `hasAncestor`
  - `hasNibling`
  - `hasUncleAunt`
  - all gender-specific properties (e.g., `hasMother`, `hasWife`,
    `hasBrother`...)

### 3.2 Detection mechanism

Unlike MATS and OATS, FATS has no internal pattern catalog — the gate's
criterion is membership itself, not a relationship between assertions. A
single query checks whether any triple in the intake graph uses a FATS
class or property:

```sparql
SELECT ?s ?p ?o WHERE {
    GRAPH <urn:kinship:intake> {
        {
            VALUES ?p {
                kin:hasRelative kin:hasLineageRelative kin:hasCeremonialBond
                kin:hasCollateralRelative kin:hasInLawRelative kin:hasStepRelative
                kin:hasDescendant kin:hasAncestor
                kin:hasNibling kin:hasUncleAunt
                kin:hasMother kin:hasFather kin:hasBrother kin:hasSister
                kin:hasSon kin:hasDaughter kin:hasWife kin:hasHusband
                kin:hasGrandmother kin:hasGrandfather
                ## ... remaining gender-specific properties
            }
            ?s ?p ?o .
        }
        UNION
        {
            VALUES ?c { kin:MalePerson kin:FemalePerson }
            ?s a ?c .
        }
    }
}
```

Severity: blocking. Complexity: O(n) — a single type/predicate check per
triple. Any match is rejected at ingestion (see Document 1 for the
intake-routing mechanism).

---

## 4. MATS Gate

### 4.1 Scope

The Minimal Assertion Types Set includes the following class and property
assertions:

- Class:
  - `Person`
- Properties:
  - *Gender:* `hasGender`
  - *Partnership:* `hasPartner`, `hasSpouse`, `hasCivilPartner`,
    `hasLifePartner`
  - *Filiation:* `hasChild`, `hasBloodChild`, `hasAdoptiveChild`,
    `hasParent`, `hasBloodParent`, `hasAdoptiveParent`
  - *Twinship:* `hasTwin`
  - *Ceremonial:* `hasGodparent`, `hasGodchild`, `hasWitness`,
    `hasWitnessed`

> **Coverage note.** The ceremonial properties were reclassified from OATS
> to MATS during the design of this framework — they cannot be inferred
> from any other assertion, which is the defining criterion for MATS
> membership. The pattern catalog below does not yet enumerate dedicated
> IRR or CON patterns for this group (e.g. a person being simultaneously
> godparent and godchild of the same individual). This is a known gap in
> the hand-written catalog. It does not affect the generated query
> pipeline (Document 3): the ontology-driven generator already covers IRR
> for these properties automatically, since they are declared
> `owl:AsymmetricProperty` with `kin:assertionSet kin:MATS` in
> `kinship-consistency.ttl`. A dedicated CON pattern for ceremonial role
> conflicts remains to be authored by hand if deemed necessary.

### 4.2 Erroneous data patterns

7 categories have been identified:

- 4 ontology violations
  - MATS Irreflexive self (IRR)
  - MATS Contradictory assertion (CON)
  - MATS Circular relationship (CIR)
  - MATS Cardinality violation (CAR)
- 1 redundancy
  - MATS Redundant assertion (RED)
- 2 domain-specific consistencies
  - MATS Twinship-specific inconsistencies (TWI)
  - MATS Partnership-specific inconsistencies (PAR)

#### MATS-IRR — Irreflexive self

Nature: universal impossibility.
Ontology violation: `IrreflexiveProperty`.

**own child**:

```turtle
:c (:hasChild | :hasBloodChild | :hasAdoptiveChild) :c .
```

**own parent**:

```turtle
:p (:hasParent | :hasBloodParent | :hasAdoptiveParent) :p .
```

**own partner**:

```turtle
:s (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :s .
```

**own twin**:

```turtle
:t :hasTwin :t .
```

**own ceremonial**:

```turtle
:x (:hasGodparent | :hasGodchild | :hasWitness | :hasWitnessed) :x .
```

#### MATS-CON — Contradicting assertion

Nature: genuine inconsistency — assertions violating a declared
disjointness axiom.
Ontology violation: disjointness axiom.

##### MATS-CON1 — child & parent type conflict

A person is both biological and adoptive child of the same person.
Violates `hasBloodChild ⊥ hasAdoptiveChild` & `hasBloodParent ⊥
hasAdoptiveParent`.

**from parent perspective**:

```turtle
:p :hasBloodChild    :c .
:p :hasAdoptiveChild :c .
```

**from child perspective**:

```turtle
:c :hasBloodParent    :p .
:c :hasAdoptiveParent :p .
```

**from mixed perspective**:

```turtle
:p :hasBloodChild     :c .
:c :hasAdoptiveParent :p .
```

```turtle
:p :hasAdoptiveChild :c .
:c :hasBloodParent   :p .
```

##### MATS-CON2 — role conflict

A person is simultaneously child and parent of the same individual.
Violates `hasChild ⊥ hasParent`.

```turtle
:x (:hasChild | :hasBloodChild | :hasAdoptiveChild)   :y .
:x (:hasParent | :hasBloodParent | :hasAdoptiveParent) :y .
```

##### MATS-CON3 — gender conflict

A person is assigned both female and male gender.

Design: `hasGender` is the only property that establishes gender; it must
never be inferred from relationship properties.
Violates `hasGender` `maxCardinality` constraint = 1 declared on `Person`.

```turtle
:x :hasGender :Female .
:x :hasGender :Male .
```

##### MATS-CON4 — twin + generational conflict

Twins are parent/child of each other.
Violates `hasSibling ⊥ hasChild` and `hasSibling ⊥ hasParent`.

**twin of his parent (direct)**:

```turtle
:t1 :hasTwin :t2 .
:t1 (:hasParent | :hasBloodParent | :hasAdoptiveParent) :t2 .
```

**twin of his parent (indirect)**:

```turtle
:t1 :hasTwin :t2 .
:t2 (:hasChild | :hasBloodChild | :hasAdoptiveChild) :t1 .
```

**twin of his child (direct)**:

```turtle
:t1 :hasTwin :t2 .
:t1 (:hasChild | :hasBloodChild | :hasAdoptiveChild) :t2 .
```

**twin of his child (indirect)**:

```turtle
:t1 :hasTwin :t2 .
:t2 (:hasParent | :hasBloodParent | :hasAdoptiveParent) :t1 .
```

#### MATS-CIR — Circular relationship

Nature: universal impossibility — applies to all link types (biological,
adoptive, unknown). Patterns cover all 2^n assertion combinations
(`hasChild` vs `hasParent` for each edge) to enable detection without
inference.
Ontology violation: disjointness axiom.

##### MATS-CIR1 — mutual parent/child (depth 1)

Violates `hasChild ⊥ hasParent`.

**mutually child of each other (all hasChild)**:

```turtle
:x (:hasChild | :hasBloodChild | :hasAdoptiveChild) :y .
:y (:hasChild | :hasBloodChild | :hasAdoptiveChild) :x .
```

**mutually parent of each other (all hasParent)**:

```turtle
:x (:hasParent | :hasBloodParent | :hasAdoptiveParent) :y .
:y (:hasParent | :hasBloodParent | :hasAdoptiveParent) :x .
```

##### MATS-CIR2 — generational cycle (depth 2)

Violates `hasDescendant ⊥ hasAncestor` (by transitivity of the
`hasBloodParent`/`hasBloodChild` chain). Own grandparent/grandchild through
8 forms — 3 edges in the cycle × 2 expression options each = 2³ = 8
combinations, named by the position of the `hasParent` expression(s) in
the cycle x→y→z→x.

**form 1 — all hasChild (0 hasParent)**:

```turtle
:x (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :y .
:y (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :z .
:z (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :x .
```

**form 2 — all hasParent (0 hasChild)**:

```turtle
:x (:hasParent | :hasBloodParent | :hasAdoptiveParent) :y .
:y (:hasParent | :hasBloodParent | :hasAdoptiveParent) :z .
:z (:hasParent | :hasBloodParent | :hasAdoptiveParent) :x .
```

**form 3 — hasParent at edge 3**:

```turtle
:x (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :y .
:y (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :z .
:x (:hasParent | :hasBloodParent | :hasAdoptiveParent) :z .
```

**form 4 — hasParent at edge 2**:

```turtle
:x (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :y .
:z (:hasParent | :hasBloodParent | :hasAdoptiveParent) :y .
:z (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :x .
```

**form 5 — hasParent at edges 2 and 3**:

```turtle
:x (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :y .
:z (:hasParent | :hasBloodParent | :hasAdoptiveParent) :y .
:x (:hasParent | :hasBloodParent | :hasAdoptiveParent) :z .
```

**form 6 — hasParent at edge 1**:

```turtle
:y (:hasParent | :hasBloodParent | :hasAdoptiveParent) :x .
:y (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :z .
:z (:hasParent | :hasBloodParent | :hasAdoptiveParent) :x .
```

**form 7 — hasParent at edges 1 and 3**:

```turtle
:y (:hasParent | :hasBloodParent | :hasAdoptiveParent) :x .
:y (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :z .
:z (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :x .
```

**form 8 — hasParent at edges 1 and 2**:

```turtle
:x (:hasParent | :hasBloodParent | :hasAdoptiveParent) :y .
:z (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :y .
:z (:hasParent | :hasBloodParent | :hasAdoptiveParent) :x .
```

#### MATS-CAR — Cardinality violation

Rationale: each person can have at most 2 biological parents.
Ontology violation: cardinality constraint.

##### MATS-CAR1 — more than 2 biological parents

Violates `hasBloodParent` max 2.

**all via hasBloodParent**:

```turtle
:c :hasBloodParent :pa .
:c :hasBloodParent :pb .
:c :hasBloodParent :pc .
```

**all via hasBloodChild**:

```turtle
:pa :hasBloodChild :c .
:pb :hasBloodChild :c .
:pc :hasBloodChild :c .
```

**2 via hasBloodChild + 1 via hasBloodParent**:

```turtle
:pa :hasBloodChild  :c .
:pb :hasBloodChild  :c .
:c  :hasBloodParent :pc .
```

**1 via hasBloodChild + 2 via hasBloodParent**:

```turtle
:pa :hasBloodChild  :c .
:c  :hasBloodParent :pb .
:c  :hasBloodParent :pc .
```

##### MATS-CAR2 — gendered blood parent conflict

Biological impossibility: two parents of the same gender is incompatible
with human reproduction. Condition: only detectable when `hasGender` is
asserted on both parents.
Violates `maxQualifiedCardinality` constraint declared on `hasBloodParent`.

**two male blood parents (direct / indirect / mixed)**:

```turtle
:pa :hasGender :Male . :pb :hasGender :Male .
:c :hasBloodParent :pa . :c :hasBloodParent :pb .
```

```turtle
:pa :hasGender :Male . :pb :hasGender :Male .
:pa :hasBloodChild :c . :pb :hasBloodChild :c .
```

```turtle
:pa :hasGender :Male . :pb :hasGender :Male .
:pa :hasBloodChild  :c . :c  :hasBloodParent :pb .
```

**two female blood parents (direct / indirect / mixed)**:

```turtle
:pa :hasGender :Female . :pb :hasGender :Female .
:c :hasBloodParent :pa . :c :hasBloodParent :pb .
```

```turtle
:pa :hasGender :Female . :pb :hasGender :Female .
:pa :hasBloodChild :c . :pb :hasBloodChild :c .
```

```turtle
:pa :hasGender :Female . :pb :hasGender :Female .
:pa :hasBloodChild  :c . :c  :hasBloodParent :pb .
```

#### MATS-RED — Redundant assertion

Nature: valid but superfluous — not an inconsistency but a data quality
issue. One assertion is inferred from the other. Strictly identical triple
declarations are excluded since RDF graphs are sets — duplicate triples
are silently collapsed and cannot be observed.
Ontology violation: none.

##### MATS-RED1 — duplicate sub/superproperty

```turtle
:p :hasBloodChild :c .
:p :hasChild      :c .
```

```turtle
:p :hasAdoptiveChild :c .
:p :hasChild         :c .
```

```turtle
:c :hasBloodParent :p .
:c :hasParent      :p .
```

```turtle
:c :hasAdoptiveParent :p .
:c :hasParent         :p .
```

```turtle
:s1 :hasSpouse  :s2 .
:s1 :hasPartner :s2 .
```

```turtle
:s1 :hasCivilPartner :s2 .
:s1 :hasPartner      :s2 .
```

```turtle
:s1 :hasLifePartner :s2 .
:s1 :hasPartner     :s2 .
```

##### MATS-RED2 — duplicate inverse sub/super/property

Duplicate assertion of an inverse property and its inverse property,
inverse superproperty, or inverse subproperty.

```turtle
:p :hasChild  :c .
:c :hasParent :p .
```

```turtle
:p :hasBloodChild :c .
:c (:hasBloodParent | :hasParent) :p .
```

```turtle
:p :hasAdoptiveChild :c .
:c (:hasAdoptiveParent | :hasParent) :p .
```

```turtle
:c :hasBloodParent :p .
:p (:hasBloodChild | :hasChild) :c .
```

```turtle
:c :hasAdoptiveParent :p .
:p (:hasAdoptiveChild | :hasChild) :c .
```

##### MATS-RED3 — duplicate symmetric property

```turtle
:s1 :hasSpouse       :s2 . :s2 :hasSpouse      :s1 .
:s1 :hasCivilPartner :s2 . :s2 :hasCivilPartner :s1 .
:s1 :hasLifePartner  :s2 . :s2 :hasLifePartner  :s1 .
:s1 :hasPartner      :s2 . :s2 :hasPartner      :s1 .
:t1 :hasTwin         :t2 . :t2 :hasTwin         :t1 .
```

#### MATS-TWI — Twinship-specific inconsistencies

Rationale: twins must share both biological parents.

##### MATS-TWI1 — twins with no common biological parent (6 forms)

```turtle
:t1 :hasBloodParent :pa . :t1 :hasBloodParent :pb .
:t2 :hasBloodParent :pc . :t2 :hasBloodParent :pd .
:t1 :hasTwin :t2 .
```

```turtle
:pa :hasBloodChild :t1 . :pb :hasBloodChild :t1 .
:pc :hasBloodChild :t2 . :pd :hasBloodChild :t2 .
:t1 :hasTwin :t2 .
```

```turtle
:pa :hasBloodChild :t1 . :pb :hasBloodChild :t1 .
:t2 :hasBloodParent :pc . :t2 :hasBloodParent :pd .
:t1 :hasTwin :t2 .
```

```turtle
:t1 :hasBloodParent :pa . :t1 :hasBloodParent :pb .
:t2 :hasBloodParent :pc . :pd :hasBloodChild :t2 .
:t1 :hasTwin :t2 .
```

```turtle
:pa :hasBloodChild :t1 . :pb :hasBloodChild :t1 .
:pc :hasBloodChild :t2 . :t2 :hasBloodParent :pd .
:t1 :hasTwin :t2 .
```

```turtle
:pa :hasBloodChild :t1 . :t1 :hasBloodParent :pb .
:pc :hasBloodChild :t2 . :t2 :hasBloodParent :pd .
:t1 :hasTwin :t2 .
```

##### MATS-TWI2 — twins with only one common biological parent (6 forms)

```turtle
:pa :hasBloodChild :t1 . :pb :hasBloodChild :t1 .
:pa :hasBloodChild :t2 . :pc :hasBloodChild :t2 .
:t1 :hasTwin :t2 .
```

```turtle
:t1 :hasBloodParent :pa . :t1 :hasBloodParent :pb .
:t2 :hasBloodParent :pa . :t2 :hasBloodParent :pc .
:t1 :hasTwin :t2 .
```

```turtle
:pa :hasBloodChild :t1 . :pb :hasBloodChild :t1 .
:t2 :hasBloodParent :pa . :t2 :hasBloodParent :pc .
:t1 :hasTwin :t2 .
```

```turtle
:t1 :hasBloodParent :pa . :t1 :hasBloodParent :pb .
:t2 :hasBloodParent :pa . :pc :hasBloodChild :t2 .
:t1 :hasTwin :t2 .
```

```turtle
:pa :hasBloodChild :t1 . :pb :hasBloodChild :t1 .
:pa :hasBloodChild :t2 . :t2 :hasBloodParent :pc .
:t1 :hasTwin :t2 .
```

```turtle
:t1 :hasBloodParent :pa . :pb :hasBloodChild :t1 .
:t2 :hasBloodParent :pa . :pc :hasBloodChild :t2 .
:t1 :hasTwin :t2 .
```

#### MATS-PAR — Partnership-specific inconsistencies

Nature: legal/social convention in contemporary legal systems.

##### MATS-PAR1 — partner of his child / parent

**partner of his child (direct / indirect)**:

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:x (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :y .
```

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:y (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :x .
```

**partner of his parent (direct / indirect)**:

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:x (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :y .
```

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:y (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :x .
```

##### MATS-PAR2 — partner of his grandparent / grandchild

Each 2-step lineage chain has 2² = 4 assertion combinations (`hasChild` vs
`hasParent` per edge).

**partner of his grandparent (direct + 3 mixed forms)**:

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:x (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :z .
:z (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :y .
```

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:x (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :z .
:y (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :z .
```

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:z (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :x .
:z (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :y .
```

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:z (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :x .
:y (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :z .
```

**partner of his grandchild (direct + 3 mixed forms)**:

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:x (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :z .
:z (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :y .
```

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:x (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :z .
:y (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :z .
```

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:z (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :x .
:z (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :y .
```

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:z (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :x .
:y (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :z .
```

##### MATS-PAR3 — twin partnership conflict

```turtle
:t1 :hasTwin :t2 .
:t1 (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :t2 .
```

```turtle
:t1 :hasTwin :t2 .
:t2 (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :t1 .
```

### 4.3 SPARQL detection queries

#### Q-MATS-IRR — Irreflexive self

Severity: High. Complexity: O(n) — single node lookup per property.

```sparql
SELECT ?x ?p WHERE {
    GRAPH <urn:kinship:asserted> {
        VALUES ?p {
            kin:hasChild kin:hasBloodChild kin:hasAdoptiveChild
            kin:hasParent kin:hasBloodParent kin:hasAdoptiveParent
            kin:hasPartner kin:hasSpouse kin:hasCivilPartner kin:hasLifePartner
            kin:hasTwin
            kin:hasGodparent kin:hasGodchild kin:hasWitness kin:hasWitnessed
        }
        ?x ?p ?x .
    }
}
```

#### Q-MATS-CON — Contradicting assertion

**Q-MATS-CON1** — Child & parent type conflict. Severity: High.
Complexity: O(n).

```sparql
SELECT DISTINCT ?p ?c WHERE {
    GRAPH <urn:kinship:asserted> {
        {   ?p kin:hasBloodChild    ?c . ?p kin:hasAdoptiveChild  ?c . } UNION
        {   ?c kin:hasBloodParent   ?p . ?c kin:hasAdoptiveParent ?p . } UNION
        {   ?p kin:hasBloodChild    ?c . ?c kin:hasAdoptiveParent ?p . } UNION
        {   ?p kin:hasAdoptiveChild ?c . ?c kin:hasBloodParent    ?p . }
    }
}
```

**Q-MATS-CON2** — Role conflict. Severity: High. Complexity: O(n²).

```sparql
SELECT DISTINCT ?x ?y ?cp ?pp WHERE {
    GRAPH <urn:kinship:asserted> {
        VALUES ?cp { kin:hasChild kin:hasBloodChild kin:hasAdoptiveChild }
        VALUES ?pp { kin:hasParent kin:hasBloodParent kin:hasAdoptiveParent }
        ?x ?cp ?y .
        ?x ?pp ?y .
    }
}
```

**Q-MATS-CON3** — Gender conflict. Severity: High. Complexity: O(n).

```sparql
SELECT ?x WHERE {
    GRAPH <urn:kinship:asserted> {
        ?x kin:hasGender kin:Female .
        ?x kin:hasGender kin:Male .
    }
}
```

**Q-MATS-CON4** — Twin + generational conflict. Severity: High.
Complexity: O(n²).

```sparql
SELECT DISTINCT ?t1 ?t2 WHERE {
    GRAPH <urn:kinship:asserted> {
        ?t1 kin:hasTwin ?t2 .
        VALUES ?cp { kin:hasChild kin:hasBloodChild kin:hasAdoptiveChild }
        VALUES ?pp { kin:hasParent kin:hasBloodParent kin:hasAdoptiveParent }
        {   ?t1 ?pp ?t2 . } UNION  # t2 is parent of t1 (direct)
        {   ?t2 ?cp ?t1 . } UNION  # t2 is parent of t1 (indirect)
        {   ?t1 ?cp ?t2 . } UNION  # t2 is child of t1 (direct)
        {   ?t2 ?pp ?t1 . }        # t2 is child of t1 (indirect)
    }
}
```

#### Q-MATS-CIR — Circular relationship

**Q-MATS-CIR1** — Mutual parent/child (depth 1). Severity: High.
Complexity: O(n²).

```sparql
SELECT DISTINCT ?x ?y WHERE {
    GRAPH <urn:kinship:asserted> {
        VALUES ?cp { kin:hasChild kin:hasBloodChild kin:hasAdoptiveChild
                     kin:hasParent kin:hasBloodParent kin:hasAdoptiveParent }
        ?x ?cp ?y .
        ?y ?cp ?x .
        FILTER(STR(?x) < STR(?y))
    }
}
```

**Q-MATS-CIR2** — Generational cycle (depth 2), all 8 forms. Severity:
High. Complexity: O(n³).

```sparql
SELECT DISTINCT ?x ?y ?z WHERE {
    GRAPH <urn:kinship:asserted> {
        VALUES ?cp { kin:hasChild kin:hasBloodChild kin:hasAdoptiveChild }
        VALUES ?pp { kin:hasParent kin:hasBloodParent kin:hasAdoptiveParent }
        {   ?x ?cp ?y . ?y ?cp ?z . ?z ?cp ?x . } UNION  # form 1 all hasChild
        {   ?x ?pp ?y . ?y ?pp ?z . ?z ?pp ?x . } UNION  # form 2 all hasParent
        {   ?x ?cp ?y . ?y ?cp ?z . ?x ?pp ?z . } UNION  # form 3
        {   ?x ?cp ?y . ?z ?pp ?y . ?z ?cp ?x . } UNION  # form 4
        {   ?x ?cp ?y . ?z ?pp ?y . ?x ?pp ?z . } UNION  # form 5
        {   ?y ?pp ?x . ?y ?cp ?z . ?x ?pp ?z . } UNION  # form 6
        {   ?y ?pp ?x . ?y ?cp ?z . ?z ?cp ?x . } UNION  # form 7
        {   ?x ?pp ?y . ?z ?cp ?y . ?z ?pp ?x . }        # form 8
        FILTER(?x != ?y && ?y != ?z && ?x != ?z)
    }
}
```

#### Q-MATS-CAR — Cardinality violation

**Q-MATS-CAR1** — More than 2 biological parents. Severity: High.
Complexity: O(n).

```sparql
SELECT ?c (COUNT(DISTINCT ?p) AS ?nb) WHERE {
    GRAPH <urn:kinship:asserted> {
        {   ?c kin:hasBloodParent ?p . } UNION
        {   ?p kin:hasBloodChild  ?c . }
    }
} GROUP BY ?c
HAVING (COUNT(DISTINCT ?p) > 2)
```

**Q-MATS-CAR2** — Gendered blood parent conflict. Severity: High.
Complexity: O(n).

```sparql
SELECT DISTINCT ?c ?gender (COUNT(DISTINCT ?p) AS ?nb) WHERE {
    GRAPH <urn:kinship:asserted> {
        VALUES ?gender { kin:Male kin:Female }
        {   ?c kin:hasBloodParent ?p . } UNION
        {   ?p kin:hasBloodChild  ?c . }
        ?p kin:hasGender ?gender .
    }
} GROUP BY ?c ?gender
HAVING (COUNT(DISTINCT ?p) > 1)
```

#### Q-MATS-RED — Redundancy assertion

**Q-MATS-RED1** — Superproperty + subproperty redundancy. Severity:
warning — data quality, not blocking. Complexity: O(n).

```sparql
SELECT DISTINCT ?x ?y ?sub ?super WHERE {
    GRAPH <urn:kinship:asserted> {
        VALUES (?sub ?super) {
            (kin:hasBloodChild     kin:hasChild)
            (kin:hasAdoptiveChild  kin:hasChild)
            (kin:hasBloodParent    kin:hasParent)
            (kin:hasAdoptiveParent kin:hasParent)
            (kin:hasSpouse         kin:hasPartner)
            (kin:hasCivilPartner   kin:hasPartner)
            (kin:hasLifePartner    kin:hasPartner)
        }
        ?x ?sub   ?y .
        ?x ?super ?y .
    }
}
```

**Q-MATS-RED2** — Inverse sub/super/property redundancy. Severity:
warning. Complexity: O(n).

```sparql
SELECT DISTINCT ?x ?y ?p ?q WHERE {
    GRAPH <urn:kinship:asserted> {
        VALUES (?p ?q) {
            (kin:hasChild          kin:hasParent)
            (kin:hasBloodChild     kin:hasBloodParent)
            (kin:hasAdoptiveChild  kin:hasAdoptiveParent)
            (kin:hasBloodChild     kin:hasParent)
            (kin:hasAdoptiveChild  kin:hasParent)
            (kin:hasBloodParent    kin:hasChild)
            (kin:hasAdoptiveParent kin:hasChild)
        }
        ?x ?p ?y .
        ?y ?q ?x .
    }
}
```

> The first three pairs are direct `owl:inverseOf` pairs; the symmetric
> direction (e.g. `(hasBloodParent, hasBloodChild)`) is intentionally
> omitted to avoid duplicate result rows for the same redundancy — see
> Document 3 for the underlying rationale once the meta-query
> generalization is described.

**Q-MATS-RED3** — Symmetric property both directions. Severity: warning.
Complexity: O(n).

```sparql
SELECT DISTINCT ?x ?y ?p WHERE {
    GRAPH <urn:kinship:asserted> {
        VALUES ?p {
            kin:hasPartner kin:hasSpouse kin:hasCivilPartner
            kin:hasLifePartner kin:hasTwin
        }
        ?x ?p ?y .
        ?y ?p ?x .
        FILTER(STR(?x) < STR(?y))
    }
}
```

#### Q-MATS-TWI — Twinship-specific inconsistencies

**Q-MATS-TWI1** — Twins sharing no biological parent. Severity: High.
Complexity: O(n).

```sparql
SELECT ?t1 ?t2 WHERE {
    GRAPH <urn:kinship:asserted> {
        ?t1 kin:hasTwin ?t2 .
        FILTER(STR(?t1) < STR(?t2))
        FILTER NOT EXISTS {
            {   ?p kin:hasBloodChild  ?t1 . ?p kin:hasBloodChild  ?t2 . } UNION
            {   ?t1 kin:hasBloodParent ?p . ?t2 kin:hasBloodParent ?p . } UNION
            {   ?p kin:hasBloodChild  ?t1 . ?t2 kin:hasBloodParent ?p . } UNION
            {   ?t1 kin:hasBloodParent ?p . ?p kin:hasBloodChild  ?t2 . }
        }
    }
}
```

**Q-MATS-TWI2** — Twins with only one common biological parent. Severity:
High. Complexity: O(n²).

```sparql
SELECT ?t1 ?t2 (COUNT(DISTINCT ?p) AS ?sharedParents) WHERE {
    GRAPH <urn:kinship:asserted> {
        ?t1 kin:hasTwin ?t2 .
        FILTER(STR(?t1) < STR(?t2))
        {   ?p kin:hasBloodChild  ?t1 . ?p kin:hasBloodChild  ?t2 . } UNION
        {   ?t1 kin:hasBloodParent ?p . ?t2 kin:hasBloodParent ?p . } UNION
        {   ?p kin:hasBloodChild  ?t1 . ?t2 kin:hasBloodParent ?p . } UNION
        {   ?t1 kin:hasBloodParent ?p . ?p kin:hasBloodChild  ?t2 . }
    }
} GROUP BY ?t1 ?t2
HAVING (COUNT(DISTINCT ?p) = 1)
```

#### Q-MATS-PAR — Partnership-specific inconsistencies

**Q-MATS-PAR1** — Partnership + direct parental conflict. Severity: High.
Complexity: O(n²).

```sparql
SELECT DISTINCT ?x ?y ?partner ?rel WHERE {
    GRAPH <urn:kinship:asserted> {
        VALUES ?partner { kin:hasPartner kin:hasSpouse kin:hasCivilPartner kin:hasLifePartner }
        VALUES ?cp  { kin:hasChild  kin:hasBloodChild  kin:hasAdoptiveChild  }
        VALUES ?pp  { kin:hasParent kin:hasBloodParent kin:hasAdoptiveParent }
        ?x ?partner ?y .
        {   ?x ?cp ?y . BIND(?cp AS ?rel) } UNION
        {   ?x ?pp ?y . BIND(?pp AS ?rel) } UNION
        {   ?y ?cp ?x . BIND(?cp AS ?rel) } UNION
        {   ?y ?pp ?x . BIND(?pp AS ?rel) }
    }
}
```

**Q-MATS-PAR2** — Partnership + lineage conflict (depth 2). Severity:
High. Complexity: O(n³).

```sparql
SELECT DISTINCT ?x ?y ?z WHERE {
    GRAPH <urn:kinship:asserted> {
        VALUES ?partner { kin:hasPartner kin:hasSpouse kin:hasCivilPartner kin:hasLifePartner }
        VALUES ?cp { kin:hasChild  kin:hasBloodChild  kin:hasAdoptiveChild  }
        VALUES ?pp { kin:hasParent kin:hasBloodParent kin:hasAdoptiveParent }
        ?x ?partner ?y .
        {
            { ?x ?pp ?z . ?z ?pp ?y . } UNION
            { ?x ?pp ?z . ?y ?cp ?z . } UNION
            { ?z ?cp ?x . ?z ?pp ?y . } UNION
            { ?z ?cp ?x . ?y ?cp ?z . }
        } UNION {
            { ?x ?cp ?z . ?z ?cp ?y . } UNION
            { ?x ?cp ?z . ?y ?pp ?z . } UNION
            { ?z ?pp ?x . ?z ?cp ?y . } UNION
            { ?z ?pp ?x . ?y ?pp ?z . }
        }
        FILTER(?z != ?x && ?z != ?y)
    }
}
```

**Q-MATS-PAR3** — Twin + partnership conflict. Severity: High.
Complexity: O(n²).

```sparql
SELECT DISTINCT ?t1 ?t2 WHERE {
    GRAPH <urn:kinship:asserted> {
        ?t1 kin:hasTwin ?t2 .
        FILTER(STR(?t1) < STR(?t2))
        VALUES ?partner { kin:hasPartner kin:hasSpouse kin:hasCivilPartner kin:hasLifePartner }
        {   ?t1 ?partner ?t2 . } UNION
        {   ?t2 ?partner ?t1 . }
    }
}
```

### 4.4 Steps within the MATS Gate

Steps are an internal execution ordering of the MATS gate — not separate
gates. Each step runs only after the previous one has returned clean.

| Step | Query | Detects | Complexity | Blocking |
| --- | --- | --- | --- | --- |
| 1 | Q-MATS-IRR | Self-referential assertions | O(n) | yes |
| 1 | Q-MATS-CON3 | Gender conflict | O(n) | yes |
| 2 | Q-MATS-CON1 | Blood/adoptive type conflict | O(n) | yes |
| 2 | Q-MATS-CAR1 | More than 2 blood parents | O(n) | yes |
| 2 | Q-MATS-CAR2 | More than 1 parent of same gender | O(n) | yes |
| 3 | Q-MATS-CON2 | Simultaneous child and parent | O(n²) | yes |
| 3 | Q-MATS-CIR1 | Mutual parent/child cycle depth 1 | O(n²) | yes |
| 4 | Q-MATS-TWI1 | Twins without common blood parent | O(n) | yes |
| 4 | Q-MATS-TWI2 | Twins with only one common blood parent | O(n²) | yes |
| 4 | Q-MATS-CON4 | Twin + generational conflict | O(n²) | yes |
| 4 | Q-MATS-PAR3 | Partnership + twin relationship | O(n²) | yes |
| 4 | Q-MATS-PAR1 | Partnership + direct parental | O(n²) | yes |
| 5 | Q-MATS-CIR2 | Generational cycle depth 2 | O(n³) | yes |
| 5 | Q-MATS-PAR2 | Partnership + grandparent/grandchild | O(n³) | yes |
| 6 | Q-MATS-RED1 | Superproperty redundancy | O(n) | warning |
| 6 | Q-MATS-RED2 | Inverse property redundancy | O(n) | warning |
| 6 | Q-MATS-RED3 | Symmetric property both directions | O(n) | warning |

Step rationale:

- **Step 1** — O(n) blocking, single-node checks. Cheapest possible.
- **Step 2** — O(n) blocking, pair checks not requiring a join across
  relationship types.
- **Step 3** — O(n²) blocking. CON2 and CIR1 are the most likely data
  entry errors after IRR.
- **Step 4** — O(n)–O(n²) blocking, domain-specific (twin and partnership
  checks). More selective patterns, lower false positive risk.
- **Step 5** — O(n³) blocking, expensive multi-hop queries. Run only after
  steps 1-4 pass to avoid compounding errors.
- **Step 6** — O(n) warnings, non-blocking. Run last or asynchronously —
  results go to a quality report, not a blocking step.

Steps 1-2 are typically run as a pre-commit hard block. Steps 3-5 as a
pre-materialization block. Step 6 as an asynchronous quality report.

---

## 5. OATS Gate

### 5.1 Scope

The Optional Assertion Types Set includes the following properties:

- `hasSibling`, `hasHalfSibling`, `hasCousin`
- `hasSiblingNibling`, `hasSiblingUncleAunt`
- `hasGrandparent`, `hasGrandchild`, `hasGreatGrandparent`,
  `hasGreatGrandchild`
- `hasChildInLaw`, `hasParentInLaw`, `hasSiblingInLaw`, `hasNiblingInLaw`,
  `hasUncleAuntInLaw`
- `hasStepChild`, `hasStepParent`, `hasStepSibling`

The ceremonial group is excluded from this scope — see §4.1 note above.

### 5.2 Two layers

The OATS gate operates in two layers:

- **Layer A — OATS vs MATS.** Checks whether an OATS triple connects two
  persons already linked in the MATS-derived closure M
  (`<urn:kinship:mats-closure>`). Layer A is implemented as a single
  generated SPARQL query reading two graphs via explicit `GRAPH` clauses:
  `<urn:kinship:oats>` (O, the candidate) and `<urn:kinship:mats-closure>`
  (M, the trusted evidence). Its structural isolation requirement is
  detailed in Document 1; the query is specified here.

The query has four branches, each detecting a distinct class of cross-set
conflict:

```sparql
SELECT ?s ?p ?o ?groupLabel ?existingRel WHERE {
    GRAPH <urn:kinship:oats> {
        VALUES (?p ?groupLabel) {
            ## generated from assertionSet OATS + subPropertyOf group
            (kin:hasSibling           "collateral")
            (kin:hasHalfSibling       "collateral")
            (kin:hasCousin            "collateral")
            (kin:hasSiblingNibling    "collateral")
            (kin:hasSiblingUncleAunt  "collateral")
            (kin:hasGrandparent       "collateral")
            (kin:hasGrandchild        "collateral")
            (kin:hasGreatGrandparent  "collateral")
            (kin:hasGreatGrandchild   "collateral")
            (kin:hasChildInLaw        "in-law")
            (kin:hasParentInLaw       "in-law")
            (kin:hasSiblingInLaw      "in-law")
            (kin:hasNiblingInLaw      "in-law")
            (kin:hasUncleAuntInLaw    "in-law")
            (kin:hasStepChild         "step")
            (kin:hasStepParent        "step")
            (kin:hasStepSibling       "step")
        }
        ?s ?p ?o .
    }
    GRAPH <urn:kinship:mats-closure> {
        ## Branch 1 — lineage closure
        {   ?s kin:hasLineageRelative ?o .
            BIND(kin:hasLineageRelative AS ?existingRel) }
        UNION
        ## Branch 2 — partnership
        {   ?s kin:hasPartner ?o .
            BIND(kin:hasPartner AS ?existingRel) }
        UNION
        ## Branch 3 — cross-set declared disjointness (same depth/direction)
        {   ?s ?mats ?o .
            BIND(?mats AS ?existingRel)
            GRAPH <urn:kinship:ontology> {
                ?p owl:propertyDisjointWith ?mats .
                ?mats kin:assertionSet kin:MATS .
            }
        }
        UNION
        ## Branch 4 — cross-set generational direction conflict
        {   ?s ?mats ?o .
            BIND(?mats AS ?existingRel)
            GRAPH <urn:kinship:ontology> {
                ?p    kin:assertionSet kin:OATS ;
                      kin:generationalDirection ?oatsDir .
                ?mats kin:assertionSet kin:MATS ;
                      kin:generationalDirection ?matsDir .
                FILTER(?oatsDir != ?matsDir)
            }
        }
    }
}
```

> **Branch coverage note.** Branches 1 and 2 are architectural anchors
> (direct expression of the MATS Primacy Principle). Branch 3 covers
> same-depth/same-direction conflicts via declared `owl:propertyDisjointWith`
> axioms. Branch 4 covers opposing-direction conflicts via
> `kin:generationalDirection` metadata; it partially overlaps with Branch 1
> for MATS properties already under `hasLineageRelative`, providing a
> redundant detection path for that subset.

- **Layer B — OATS vs OATS.** Validates conflicts between distinct OATS
  assertions that involve no pre-existing MATS link. This catalog covers
  Layer B exclusively.

This catalog covers conflicts internal to the OATS set itself.

### 5.3 Erroneous data patterns (Layer B)

5 categories have been identified:

- 3 ontology violations
  - OATS Irreflexive self (IRR)
  - OATS Contradictory assertion (CON)
  - OATS Circular relationship (CIR)
- 1 redundancy
  - OATS Redundant assertion (RED)
- 1 domain-specific consistency
  - OATS Partnership-specific relationship inconsistencies (PAR)

#### OATS-IRR — Irreflexive self

Nature: universal impossibility.
Ontology violation: `IrreflexiveProperty`.

**own blood-related**:

```turtle
:x (:hasSibling | :hasHalfSibling | :hasCousin | :hasSiblingNibling |
   :hasSiblingUncleAunt | :hasGrandparent | :hasGrandchild |
   :hasGreatGrandparent | :hasGreatGrandchild) :x .
```

**own in-law**:

```turtle
:x (:hasChildInLaw | :hasParentInLaw | :hasSiblingInLaw |
   :hasNiblingInLaw | :hasUncleAuntInLaw) :x .
```

**own step**:

```turtle
:x (:hasStepChild | :hasStepParent | :hasStepSibling) :x .
```

#### OATS-CON — Contradicting assertion

Nature: universal impossibility — two assertions place the same pair of
individuals in two mutually exclusive generational or relational roles.
Unlike MATS-CON1, no blood/adoptive type duality exists within the OATS
set itself — each pattern below is a single direct form rather than a
direct/indirect/mixed family.
Ontology violation: disjointness axiom (`owl:inverseOf` misuse).

##### OATS-CON1 — role conflict between inverse properties

A person is assigned both ends of an inverse property pair with the same
individual. Violates `hasGrandparent ⊥ hasGrandchild`,
`hasGreatGrandparent ⊥ hasGreatGrandchild`, `hasSiblingNibling ⊥
hasSiblingUncleAunt`, `hasChildInLaw ⊥ hasParentInLaw`, `hasNiblingInLaw ⊥
hasUncleAuntInLaw`, `hasStepChild ⊥ hasStepParent`.

```turtle
:x :hasGrandparent :y .
:x :hasGrandchild  :y .
```

```turtle
:x :hasGreatGrandparent :y .
:x :hasGreatGrandchild  :y .
```

```turtle
:x :hasSiblingNibling   :y .
:x :hasSiblingUncleAunt :y .
```

```turtle
:x :hasChildInLaw  :y .
:x :hasParentInLaw :y .
```

```turtle
:x :hasNiblingInLaw   :y .
:x :hasUncleAuntInLaw :y .
```

```turtle
:x :hasStepChild  :y .
:x :hasStepParent :y .
```

##### OATS-CON2 — cross-depth generational conflict

A person is assigned two generational roles of different depth that
cannot both hold for the same pair. Violates `hasGrandparent ⊥
hasGreatGrandchild` and `hasGreatGrandparent ⊥ hasGrandchild`.

```turtle
:x :hasGrandparent      :y .
:x :hasGreatGrandchild  :y .
```

```turtle
:x :hasGreatGrandparent :y .
:x :hasGrandchild       :y .
```

> Further cross-depth combinations follow the same logic but are not
> exhaustively catalogued here, in the same way the cross-group
> disjointness catalog between OATS groups remains an open item.

#### OATS-CIR — Circular relationship

Nature: universal impossibility — applies to every OATS property pair
that encodes a generational or directional relationship. Patterns cover
both the 2-node mutual case and the 3-node cycle case, mirroring the
MATS-CIR treatment of the filiation chain.
Ontology violation: disjointness axiom (transitive entailment of mutual
ancestry).

##### OATS-CIR1 — mutual same-property assertion (depth 1)

Both individuals assert the same directional property toward each other.
Violates the asymmetry inherent to every directional OATS property.

```turtle
:x :hasGrandparent :y .  :y :hasGrandparent :x .
```

```turtle
:x :hasGrandchild :y .  :y :hasGrandchild :x .
```

```turtle
:x :hasGreatGrandparent :y .  :y :hasGreatGrandparent :x .
```

```turtle
:x :hasGreatGrandchild :y .  :y :hasGreatGrandchild :x .
```

```turtle
:x :hasSiblingNibling :y .  :y :hasSiblingNibling :x .
```

```turtle
:x :hasSiblingUncleAunt :y .  :y :hasSiblingUncleAunt :x .
```

```turtle
:x :hasChildInLaw :y .  :y :hasChildInLaw :x .
```

```turtle
:x :hasParentInLaw :y .  :y :hasParentInLaw :x .
```

```turtle
:x :hasNiblingInLaw :y .  :y :hasNiblingInLaw :x .
```

```turtle
:x :hasUncleAuntInLaw :y .  :y :hasUncleAuntInLaw :x .
```

```turtle
:x :hasStepChild :y .  :y :hasStepChild :x .
```

```turtle
:x :hasStepParent :y .  :y :hasStepParent :x .
```

##### OATS-CIR2 — generational cycle (depth 2), 8 forms

Own grandparent/grandchild through a 3-node cycle, mirroring MATS-CIR2.
3 edges × 2 expression options each = 8 combinations, named by the
position of the ascending (`hasGrandparent`) expression(s) in the cycle
x→y→z→x.

**form 1 — all descending (hasGrandchild)**:

```turtle
:x :hasGrandchild :y . :y :hasGrandchild :z . :z :hasGrandchild :x .
```

**form 2 — all ascending (hasGrandparent)**:

```turtle
:x :hasGrandparent :y . :y :hasGrandparent :z . :z :hasGrandparent :x .
```

**form 3 — ascending at edge 3**:

```turtle
:x :hasGrandchild  :y . :y :hasGrandchild  :z . :x :hasGrandparent :z .
```

**form 4 — ascending at edge 2**:

```turtle
:x :hasGrandchild  :y . :z :hasGrandparent :y . :z :hasGrandchild  :x .
```

**form 5 — ascending at edges 2 and 3**:

```turtle
:x :hasGrandchild  :y . :z :hasGrandparent :y . :x :hasGrandparent :z .
```

**form 6 — ascending at edge 1**:

```turtle
:y :hasGrandparent :x . :y :hasGrandchild  :z . :x :hasGrandparent :z .
```

**form 7 — ascending at edges 1 and 3**:

```turtle
:y :hasGrandparent :x . :y :hasGrandchild  :z . :z :hasGrandchild  :x .
```

**form 8 — ascending at edges 1 and 2**:

```turtle
:x :hasGrandparent :y . :z :hasGrandchild  :y . :z :hasGrandparent :x .
```

> The same 8-form pattern applies verbatim to the great-grandparent
> family, substituting `hasGrandchild → hasGreatGrandchild` and
> `hasGrandparent → hasGreatGrandparent`. Not repeated here for brevity —
> the detection query below covers both families in one pass.

#### OATS-RED — Redundant assertion

Nature: valid but superfluous — not an inconsistency but a data quality
issue. One assertion is entailed by the other via `subPropertyOf` or
`owl:inverseOf`.
Ontology violation: none.

##### OATS-RED1 — subproperty + superproperty

```turtle
:x :hasHalfSibling :y .
:x :hasSibling     :y .
```

##### OATS-RED2 — inverse assertion

```turtle
:x :hasGrandparent :y .
:y :hasGrandchild  :x .
```

```turtle
:x :hasGreatGrandparent :y .
:y :hasGreatGrandchild  :x .
```

```turtle
:x :hasSiblingNibling   :y .
:y :hasSiblingUncleAunt :x .
```

```turtle
:x :hasChildInLaw  :y .
:y :hasParentInLaw :x .
```

```turtle
:x :hasNiblingInLaw   :y .
:y :hasUncleAuntInLaw :x .
```

```turtle
:x :hasStepChild  :y .
:y :hasStepParent :x .
```

##### OATS-RED3 — symmetric property

```turtle
:x :hasSibling      :y . :y :hasSibling      :x .
:x :hasHalfSibling  :y . :y :hasHalfSibling  :x .
:x :hasCousin       :y . :y :hasCousin       :x .
:x :hasSiblingInLaw :y . :y :hasSiblingInLaw :x .
:x :hasStepSibling  :y . :y :hasStepSibling  :x .
```

#### OATS-PAR — Partnership-specific relationship inconsistencies

Nature: legal/social convention, with one definitional exception (see
OATS-PAR1). Collateral relations are reached through a shared blood or
adoptive parent; in-law and step relations are reached through a
partnership link, even though no partnership property is itself part of
the OATS set. A pair connected by two mutually exclusive paths for what is
nominally the same role is generally inconsistent.
Ontology violation: disjointness axiom (cross-group, convention-based).

##### OATS-PAR1 — sibling-type cross-group conflict

```turtle
:x :hasSibling      :y .
:x :hasSiblingInLaw :y .
```

`hasStepSibling` is defined as sharing no common parent; `hasSibling`
requires sharing at least one — the two are mutually exclusive by
**definition**, not merely by convention:

```turtle
:x :hasSibling     :y .
:x :hasStepSibling :y .
```

```turtle
:x :hasSiblingInLaw :y .
:x :hasStepSibling  :y .
```

##### OATS-PAR2 — nibling/uncle-aunt-type cross-group conflict

```turtle
:x :hasSiblingNibling :y .
:x :hasNiblingInLaw   :y .
```

```turtle
:x :hasSiblingUncleAunt :y .
:x :hasUncleAuntInLaw   :y .
```

##### Identified non-violations

The following cross-group combinations were analyzed and found not to be
systematically inconsistent — they are deliberately excluded from the
detection queries:

- `hasChildInLaw` and `hasStepChild` on the same pair: possible when the
  individual is both a child's partner and a former partner's child.
- `hasParentInLaw` and `hasStepParent` on the same pair: possible in
  blended family structures with no logical contradiction.

### 5.4 SPARQL detection queries (Layer B)

The queries below run against `<urn:kinship:oats>`, the OATS quarantine
graph, independently of the MATS graph and of Layer A.

#### Q-OATS-IRR — Irreflexive self

Severity: High. Complexity: O(n).

```sparql
SELECT ?x ?p WHERE {
    GRAPH <urn:kinship:oats> {
        VALUES ?p {
            kin:hasSibling kin:hasHalfSibling kin:hasCousin
            kin:hasSiblingNibling kin:hasSiblingUncleAunt
            kin:hasGrandparent kin:hasGrandchild
            kin:hasGreatGrandparent kin:hasGreatGrandchild
            kin:hasChildInLaw kin:hasParentInLaw
            kin:hasSiblingInLaw
            kin:hasNiblingInLaw kin:hasUncleAuntInLaw
            kin:hasStepChild kin:hasStepParent kin:hasStepSibling
        }
        ?x ?p ?x .
    }
}
```

#### Q-OATS-CON — Contradicting assertion

**Q-OATS-CON1** — Role conflict between inverse properties. Severity:
High. Complexity: O(n).

```sparql
SELECT DISTINCT ?x ?y ?p ?q WHERE {
    GRAPH <urn:kinship:oats> {
        VALUES (?p ?q) {
            (kin:hasGrandparent      kin:hasGrandchild)
            (kin:hasGreatGrandparent kin:hasGreatGrandchild)
            (kin:hasSiblingNibling   kin:hasSiblingUncleAunt)
            (kin:hasChildInLaw       kin:hasParentInLaw)
            (kin:hasNiblingInLaw     kin:hasUncleAuntInLaw)
            (kin:hasStepChild        kin:hasStepParent)
        }
        ?x ?p ?y .
        ?x ?q ?y .
    }
}
```

**Q-OATS-CON2** — Cross-depth generational conflict. Severity: High.
Complexity: O(n).

```sparql
SELECT DISTINCT ?x ?y ?p ?q WHERE {
    GRAPH <urn:kinship:oats> {
        VALUES (?p ?q) {
            (kin:hasGrandparent      kin:hasGreatGrandchild)
            (kin:hasGreatGrandparent kin:hasGrandchild)
        }
        ?x ?p ?y .
        ?x ?q ?y .
    }
}
```

#### Q-OATS-CIR — Circular relationship

**Q-OATS-CIR1** — Mutual same-property assertion (depth 1). Severity:
High. Complexity: O(n²).

```sparql
SELECT DISTINCT ?x ?y ?p WHERE {
    GRAPH <urn:kinship:oats> {
        VALUES ?p {
            kin:hasGrandparent kin:hasGrandchild
            kin:hasGreatGrandparent kin:hasGreatGrandchild
            kin:hasSiblingNibling kin:hasSiblingUncleAunt
            kin:hasChildInLaw kin:hasParentInLaw
            kin:hasNiblingInLaw kin:hasUncleAuntInLaw
            kin:hasStepChild kin:hasStepParent
        }
        ?x ?p ?y .
        ?y ?p ?x .
        FILTER(STR(?x) < STR(?y))
    }
}
```

**Q-OATS-CIR2** — Generational cycle (depth 2), grandparent and
great-grandparent families, all 8 forms. Severity: High.
Complexity: O(n³).

```sparql
SELECT DISTINCT ?x ?y ?z ?asc ?desc WHERE {
    GRAPH <urn:kinship:oats> {
        VALUES (?desc ?asc) {
            (kin:hasGrandchild      kin:hasGrandparent)
            (kin:hasGreatGrandchild kin:hasGreatGrandparent)
        }
        {   ?x ?desc ?y . ?y ?desc ?z . ?z ?desc ?x . } UNION  # form 1
        {   ?x ?asc  ?y . ?y ?asc  ?z . ?z ?asc  ?x . } UNION  # form 2
        {   ?x ?desc ?y . ?y ?desc ?z . ?x ?asc  ?z . } UNION  # form 3
        {   ?x ?desc ?y . ?z ?asc  ?y . ?z ?desc ?x . } UNION  # form 4
        {   ?x ?desc ?y . ?z ?asc  ?y . ?x ?asc  ?z . } UNION  # form 5
        {   ?y ?asc  ?x . ?y ?desc ?z . ?x ?asc  ?z . } UNION  # form 6
        {   ?y ?asc  ?x . ?y ?desc ?z . ?z ?desc ?x . } UNION  # form 7
        {   ?x ?asc  ?y . ?z ?desc ?y . ?z ?asc  ?x . }        # form 8
        FILTER(?x != ?y && ?y != ?z && ?x != ?z)
    }
}
```

#### Q-OATS-RED — Redundancy assertion

**Q-OATS-RED1** — Subproperty + superproperty redundancy. Severity:
warning. Complexity: O(n).

```sparql
SELECT DISTINCT ?x ?y WHERE {
    GRAPH <urn:kinship:oats> {
        ?x kin:hasHalfSibling ?y .
        ?x kin:hasSibling     ?y .
    }
}
```

**Q-OATS-RED2** — Inverse property redundancy. Severity: warning.
Complexity: O(n).

```sparql
SELECT DISTINCT ?x ?y ?p ?q WHERE {
    GRAPH <urn:kinship:oats> {
        VALUES (?p ?q) {
            (kin:hasGrandparent      kin:hasGrandchild)
            (kin:hasGreatGrandparent kin:hasGreatGrandchild)
            (kin:hasSiblingNibling   kin:hasSiblingUncleAunt)
            (kin:hasChildInLaw       kin:hasParentInLaw)
            (kin:hasNiblingInLaw     kin:hasUncleAuntInLaw)
            (kin:hasStepChild        kin:hasStepParent)
        }
        ?x ?p ?y .
        ?y ?q ?x .
    }
}
```

**Q-OATS-RED3** — Symmetric property both directions. Severity: warning.
Complexity: O(n).

```sparql
SELECT DISTINCT ?x ?y ?p WHERE {
    GRAPH <urn:kinship:oats> {
        VALUES ?p {
            kin:hasSibling kin:hasHalfSibling kin:hasCousin
            kin:hasSiblingInLaw kin:hasStepSibling
        }
        ?x ?p ?y .
        ?y ?p ?x .
        FILTER(STR(?x) < STR(?y))
    }
}
```

#### Q-OATS-PAR — Partnership-specific inconsistencies

**Q-OATS-PAR1** — Sibling-type cross-group conflict. Severity: High
(definitional for sibling/step-sibling), convention-level for the other
two pairs. Complexity: O(n).

```sparql
SELECT DISTINCT ?x ?y ?p ?q WHERE {
    GRAPH <urn:kinship:oats> {
        VALUES (?p ?q) {
            (kin:hasSibling      kin:hasSiblingInLaw)
            (kin:hasSibling      kin:hasStepSibling)
            (kin:hasSiblingInLaw kin:hasStepSibling)
        }
        ?x ?p ?y .
        ?x ?q ?y .
    }
}
```

**Q-OATS-PAR2** — Nibling/uncle-aunt-type cross-group conflict. Severity:
convention-level. Complexity: O(n).

```sparql
SELECT DISTINCT ?x ?y ?p ?q WHERE {
    GRAPH <urn:kinship:oats> {
        VALUES (?p ?q) {
            (kin:hasSiblingNibling   kin:hasNiblingInLaw)
            (kin:hasSiblingUncleAunt kin:hasUncleAuntInLaw)
        }
        ?x ?p ?y .
        ?x ?q ?y .
    }
}
```

### 5.5 Steps within the OATS Gate (Layer B)

| Step | Query | Detects | Complexity | Blocking |
| --- | --- | --- | --- | --- |
| 1 | Q-OATS-IRR | Self-referential assertions | O(n) | yes |
| 2 | Q-OATS-CON1 | Role conflict between inverse properties | O(n) | yes |
| 2 | Q-OATS-CON2 | Cross-depth generational conflict | O(n) | yes |
| 2 | Q-OATS-PAR1 | Sibling-type cross-group conflict | O(n) | yes |
| 2 | Q-OATS-PAR2 | Nibling/uncle-aunt cross-group conflict | O(n) | yes |
| 3 | Q-OATS-CIR1 | Mutual same-property assertion depth 1 | O(n²) | yes |
| 4 | Q-OATS-CIR2 | Generational cycle depth 2 | O(n³) | yes |
| 5 | Q-OATS-RED1 | Superproperty redundancy | O(n) | warning |
| 5 | Q-OATS-RED2 | Inverse property redundancy | O(n) | warning |
| 5 | Q-OATS-RED3 | Symmetric property both directions | O(n) | warning |

Layer B's steps run after Layer A has passed for the candidate OATS triple
(see Document 1 for the exact precondition chain between Layer A, Layer B,
and materialization).

---

## 6. SHACL Gate — pointer

After the MATS and OATS gates have passed and Materialization Step 2 has
produced `<urn:kinship:full>` (MO), the SHACL Gate operates on this full
closure to catch any non-minimal-assertion (NMA) conflict that escaped the
preceding steps. Its detailed shapes and queries are a separate, less
mature specification to be revisited (Document 2bis).

Its role in the pipeline, per Document 1: a safety net, not a primary
consistency mechanism. The entire architecture of the gates described
above is designed so that data reaching this layer should already be
clean; a violation surfacing here signals either a gap in the
pre-materialization catalog above or a regression in the pipeline, not an
expected outcome of normal operation.
