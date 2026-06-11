# Consistency control

## Overview

This document defines a strategy for identifying and catching errors that would
break the consistency of family relationship data sets in the context of the
kinship ontology.

### Goal

In the context of the kinship ontology, this document aims to define a strategy
for identifying and catching errors that would break the consistency of family
relationship data sets.

The identification strategy depends on a data entry minimization approach for
describing family relationships. This minimization is based on limiting
assertions to only partnership links, filiation, twinship, and gender.

### Approach

The approach consists of:

1. categorizing and identifying erroneous data patterns
2. identifying mechanisms to detect these patterns
3. defining optimal detection strategy

## Erroneous data patterns catalog

This section presents the catalog of identified erroneous data patterns
organized into categories. Its objectives are:

- to identify the exhaustiveness of assertion forms (direct + indirect via
inverseOf);
- to ensure independence from inference and materialization mechanisms;
- to establish a clear hierarchy by problem family;
- to account for blocking errors as well as data entry anomalies (semantic
redundancies, etc.).

### Assertion scope

The catalog focuses on the minimal set of kinship assertion types that is
needed to describe family relationship networks. When combined in wrong ways,
they can produce redundancies and worse, inconsistencies within family network
descriptions.

The following assertion types comprise the scope:

- kinship ties:
  - Partnership links (:hasPartner, :hasSpouse, :hasCivilPartner,
  :hasLifePartner)
  - Filiation (:hasChild, :hasBloodChild, :hasAdoptiveChild, :hasParent,
  :hasBloodParent, :hasAdoptiveParent)
  - Twinship (:hasTwin)
- gender declaration:
  - Gender (:hasGender)

Although the assertion scope focuses on these assertion types, the catalog
also includes patterns that would lead to inconsistencies through inferred
relationships beyond the scope of these basic relationships (e.g., :hasSibling,
:hasUncleAunt, hasGrandparent) to ensure comprehensive coverage of erroneous
data patterns.

The in-scope kinship ties form a subset of the core-neutral module of the
kinship ontology: <http://example.org/kinship/core-neutral>. All the other
relationships of the kinship ontology are excluded from this assertion scope
as they can be derived from these basic relationships through logical
inferences or materialization.

### Notation

Patterns use SPARQL property path syntax as a conceptual shorthand, not valid
Turtle.
(:hasChild | :hasBloodChild | :hasAdoptiveChild) means "any of these properties".

Each pattern represents a minimal set of assertions that, taken together, are
inconsistent or redundant.

Patterns cover all assertion forms (direct and inverse via owl:inverseOf) to
enable SPARQL detection without relying on inference or materialization.

### Erroneous data patterns categories

7 categories have been identified which include:

- 5 of which are ontology violation categories
  - IRR - Irreflexive self
  - RED - Redundant assertion
  - CON - Contradictory assertion
  - CIR - Circular relationship
  - CAR - Cardinality violation
- 2 of which are domain-specific consistency categories
  - TWI - Twinship-specific relationship inconsistencies
  - PAR - Partnership-specific relationship inconsistencies

The remainder of this chapter lists the identified patterns for each category.

### IRR - Irreflexive self

Nature: universal impossibility
Ontology violation: IrreflexiveProperty

#### own child

```turtle
:c (:hasChild | :hasBloodChild | :hasAdoptiveChild) :c .
```

#### own parent

```turtle
:p (:hasParent | :hasBloodParent | :hasAdoptiveParent) :p .
```

#### own partner

```turtle
:s (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :s .
```

#### own twin

```turtle
:t :hasTwin :t .
```

### RED - Redundant assertion

Nature: valid but superfluous

- Not an inconsistency but a data quality issue.
- Other assertions are inferred from the first assertion.
- Strictly identical triples declarations within a turtle file are excluded
since RDF graphs are sets. Therefore, duplicate triples are silently collapsed
and cannot be observed.

Ontology violation: none

#### RED1 - subproperty + superproperty

Duplicate assertion of a superproperty.

##### :hasBloodChild + subproperty

```turtle
:p :hasBloodChild :c .
:p :hasChild      :c .
```

##### :hasAdoptiveChild + superproperty

```turtle
:p :hasAdoptiveChild :c .
:p :hasChild         :c .
```

##### :hasBloodParent + superproperty

```turtle
:c :hasBloodParent :p .
:c :hasParent      :p .
```

##### :hasAdoptiveParent + superproperty

```turtle
:c :hasAdoptiveParent :p .
:c :hasParent         :p .
```

##### :hasSpouse + superproperty

```turtle
:s1 :hasSpouse  :s2 .
:s1 :hasPartner :s2 .
```

##### :hasCivilPartner + superproperty

```turtle
:s1 :hasCivilPartner :s2 .
:s1 :hasPartner      :s2 .
```

##### :hasLifePartner + superproperty

```turtle
:s1 :hasLifePartner :s2 .
:s1 :hasPartner     :s2 .
```

#### RED2 - inverse assertion

Duplicate assertion of inverse property or inverse superproperty

##### :hasParent + inverse

```turtle
:p :hasChild  :c .
:c :hasParent :p .
```

##### :hasBloodParent + inverse or inverse superproperty

```turtle
:p :hasBloodChild :c .
:c (:hasBloodParent | :hasParent) :p .
```

##### :hasAdoptiveParent + inverse or inverse superproperty

```turtle
:p :hasAdoptiveChild :c .
:c (:hasAdoptiveParent | :hasParent) :p .
```

##### :hasBloodChild + inverse or inverse superproperty

```turtle
:c :hasBloodParent :p .
:p (:hasBloodChild | :hasChild) :c .
```

##### :hasAdoptiveChild + inverse or inverse superproperty

```turtle
:c :hasAdoptiveParent :p .
:p (:hasAdoptiveChild | :hasChild) :c .
```

#### RED3 - symmetric property

Duplicate assertion of a symmetric property.

##### both directions of a symmetric property asserted

```turtle
:s1 :hasSpouse       :s2 . :s2 :hasSpouse      :s1 .
:s1 :hasCivilPartner :s2 . :s2 :hasCivilPartner :s1 .
:s1 :hasLifePartner  :s2 . :s2 :hasLifePartner  :s1 .
:s1 :hasPartner      :s2 . :s2 :hasPartner      :s1 .
:t1 :hasTwin         :t2 . :t2 :hasTwin         :t1 .
```

### CON - Contradicting assertion

Nature: genuine inconsistency

- Assertions violating declared disjointness axiom.

Ontology violation: disjointness axiom.

#### CON1 - child & parent type conflict

A person is both biological and adoptive child of the same person.
Violates hasBloodChild ⊥ hasAdoptiveChild & hasBloodParent ⊥ hasAdoptiveParent

##### from parent perspective

```turtle
:p :hasBloodChild    :c .
:p :hasAdoptiveChild :c .
```

##### from child perspective

```turtle
:c :hasBloodParent    :p .
:c :hasAdoptiveParent :p .
```

##### from mixed perspective

```turtle
:p :hasBloodChild     :c .
:c :hasAdoptiveParent :p .
```

```turtle
:p :hasAdoptiveChild :c .
:c :hasBloodParent   :p .
```

#### CON2 - role conflict

A person is simultaneously child and parent of the same individual.
Violates hasChild ⊥ hasParent

##### simultaneously child and parent

```turtle
:x (:hasChild | :hasBloodChild | :hasAdoptiveChild)   :y .
:x (:hasParent | :hasBloodParent | :hasAdoptiveParent) :y .
```

#### CON3 - gender conflict

A person is assigned both female and male gender.

- Design: :hasGender is the only property that establishes gender.
- It must never be inferred from relationship properties.

Violates :hasGender maxCardinality constraint = 1 declared on :Person.

##### both female and male

```turtle
:x :hasGender :Female .
:x :hasGender :Male .
```

#### CON4 - twin + generational conflict

Twin are parent/child of each other.
Violates :hasSibling ⊥ :hasChild and :hasSibling ⊥ :hasParent

##### twin of his parent (direct)

```turtle
:t1 :hasTwin :t2 .
:t1 (:hasParent | :hasBloodParent | :hasAdoptiveParent) :t2 .
```

##### twin of his parent (indirect)

```turtle
:t1 :hasTwin :t2 .
:t2 (:hasChild | :hasBloodChild | :hasAdoptiveChild) :t1 .
```

##### twin of his child (direct)

```turtle
:t1 :hasTwin :t2 .
:t1 (:hasChild | :hasBloodChild | :hasAdoptiveChild) :t2 .
```

##### twin of his child (indirect)

```turtle
:t1 :hasTwin :t2 .
:t2 (:hasParent | :hasBloodParent | :hasAdoptiveParent) :t1 .
```

### CIR - Circular generational relationship

Nature: universal impossibility

- Applies to all link types (biological, adoptive, unknown).
- Patterns cover all 2^n assertion combinations (hasChild vs hasParent for each edge)
- to enable detection without inference.

Ontology violation: disjointness axiom.

#### CIR1 - mutual parent/child (depth 1)

Violates hasChild ⊥ hasParent

##### mutually child of each other (all hasChild)

```turtle
:x (:hasChild | :hasBloodChild | :hasAdoptiveChild) :y .
:y (:hasChild | :hasBloodChild | :hasAdoptiveChild) :x .
```

##### mutually parent of each other (all hasParent)

```turtle
:x (:hasParent | :hasBloodParent | :hasAdoptiveParent) :y .
:y (:hasParent | :hasBloodParent | :hasAdoptiveParent) :x .
```

#### CIR2 - generational cycle (depth 2)

Violates :hasDescendant ⊥ :hasAncestor (by transitivity of hasBloodParent/hasBloodChild chain) & :hasGrandchild ⊥ :hasGrandparent
Own grandparent/grandchild through 8 forms

- 3 edges in cycle × 2 expression options each = 2^3 = 8 combinations
- Named by position of hasParent expression(s) in the cycle x→y→z→x

##### form 1 — all hasChild (0 hasParent)

```turtle
:x (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :y .
:y (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :z .
:z (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :x .
```

##### form 2 — all hasParent (0 hasChild)

```turtle
:x (:hasParent | :hasBloodParent | :hasAdoptiveParent) :y .
:y (:hasParent | :hasBloodParent | :hasAdoptiveParent) :z .
:z (:hasParent | :hasBloodParent | :hasAdoptiveParent) :x .
```

##### form 3 — hasParent at edge 3

```turtle
:x (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :y .
:y (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :z .
:x (:hasParent | :hasBloodParent | :hasAdoptiveParent) :z .
```

##### form 4 — hasParent at edge 2

```turtle
:x (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :y .
:z (:hasParent | :hasBloodParent | :hasAdoptiveParent) :y .
:z (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :x .
```

##### form 5 — hasParent at edges 2 and 3

```turtle
:x (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :y .
:z (:hasParent | :hasBloodParent | :hasAdoptiveParent) :y .
:x (:hasParent | :hasBloodParent | :hasAdoptiveParent) :z .
```

##### form 6 — hasParent at edge 1

```turtle
:y (:hasParent | :hasBloodParent | :hasAdoptiveParent) :x .
:y (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :z .
:z (:hasParent | :hasBloodParent | :hasAdoptiveParent) :x .
```

##### form 7 — hasParent at edges 1 and 3

```turtle
:y (:hasParent | :hasBloodParent | :hasAdoptiveParent) :x .
:y (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :z .
:z (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :x .
```

##### form 8 — hasParent at edges 1 and 2

```turtle
:x (:hasParent | :hasBloodParent | :hasAdoptiveParent) :y .
:z (:hasChild  | :hasBloodChild  | :hasAdoptiveChild)  :y .
:z (:hasParent | :hasBloodParent | :hasAdoptiveParent) :x .
```

### CAR - Cardinality violation

Rationale: Each person can have at most 2 biological parents.
Ontology violation: cardinality constraint.

#### CAR1 - more than 2 biological parents

Violates: hasBloodParent max 2

##### all via hasBloodParent

```turtle
:c :hasBloodParent :pa .
:c :hasBloodParent :pb . 
:c :hasBloodParent :pc .
```

##### all via hasBloodChild

```turtle
:pa :hasBloodChild :c .
:pb :hasBloodChild :c .
:pc :hasBloodChild :c .
```

##### 2 via hasBloodChild + 1 via hasBloodParent

```turtle
:pa :hasBloodChild  :c .
:pb :hasBloodChild  :c .
:c  :hasBloodParent :pc .
```

##### 1 via hasBloodChild + 2 via hasBloodParent

```turtle
:pa :hasBloodChild  :c .
:c  :hasBloodParent :pb .
:c  :hasBloodParent :pc .
```

#### CAR2 - Gendered blood parent conflict

Biological impossibility

- two parents of the same gender
- is incompatible with human reproduction.
- Condition: only detectable when :hasGender is asserted on both parents.

Violates maxQualifiedCardinality constraint declared on :hasBloodParent.

##### two male blood parents (direct)

```turtle
:pa :hasGender :Male .
:pb :hasGender :Male .
:c :hasBloodParent :pa .
:c :hasBloodParent :pb .
```

##### two male blood parents (indirect)

```turtle
:pa :hasGender :Male .
:pb :hasGender :Male .
:pa :hasBloodChild :c .
:pb :hasBloodChild :c .
```

##### two male blood parents (mixed)

```turtle
:pa :hasGender :Male .
:pb :hasGender :Male .
:pa :hasBloodChild  :c .
:c  :hasBloodParent :pb .
```

##### two female blood parents (direct)

```turtle
:pa :hasGender :Female .
:pb :hasGender :Female .
:c :hasBloodParent :pa .
:c :hasBloodParent :pb .
```

##### two female blood parents (indirect)

```turtle
:pa :hasGender :Female .
:pb :hasGender :Female .
:pa :hasBloodChild :c .
:pb :hasBloodChild :c .
```

##### two female blood parents (mixed)

```turtle
:pa :hasGender :Female .
:pb :hasGender :Female .
:pa :hasBloodChild  :c .
:c  :hasBloodParent :pb .
```

### TWI - Twin consistency

Rationale: Twins specific constraints.

- Twins must share both biological parent.

#### TWI1 - twins with no common biological parent - 6 forms

##### no common biological parent all via hasBloodParent

```turtle
:t1 :hasBloodParent :pa .
:t1 :hasBloodParent :pb .
:t2 :hasBloodParent :pc .
:t2 :hasBloodParent :pd .
:t1 :hasTwin :t2 .
```

##### no common biological parent all via hasBloodChild

```turtle
:pa :hasBloodChild :t1 .
:pb :hasBloodChild :t1 .
:pc :hasBloodChild :t2 .
:pd :hasBloodChild :t2 .
:t1 :hasTwin :t2 .
```

##### no common biological parent t1 via hasBloodChild, t2 via hasBloodParent

```turtle
:pa :hasBloodChild :t1 .
:pb :hasBloodChild :t1 .
:t2 :hasBloodParent :pc .
:t2 :hasBloodParent :pd .
:t1 :hasTwin :t2 .
```

##### no common biological parent t1 via hasBloodParent, t2 via hasBloodParent and hasBloodChild

```turtle
:t1 kin:hasBloodParent :pa .
:t1 kin:hasBloodParent :pb .
:t2 kin:hasBloodParent :pc  .
:pd kin:hasBloodChild :t2 .
:t1 kin:hasTwin :t2 .
```

##### no common biological parent t1 via hasBloodChild, t2 via hasBloodChild and hasBloodParent

```turtle
:pa kin:hasBloodChild :t1 .
:pb kin:hasBloodChild :t1 .
:pc kin:hasBloodChild :t2 .
:t2 kin:hasBloodParent :pd .
:t1 kin:hasTwin :t2 .
```

##### no common biological parent t1 and t2 both via hasBloodChild and hasBloodParent

```turtle
:pa kin:hasBloodChild :t1 .
:t1 kin:hasBloodParent :pb .
:pc kin:hasBloodChild :t2 .
:t2 kin:hasBloodParent :pd .
:t1 kin:hasTwin :t2 .
```

#### TWI2 - twins with only one common biological parent - 6 forms

##### only one shared biological parent all via hasBloodChild

```turtle
:pa :hasBloodChild :t1 .
:pb :hasBloodChild :t1 .
:pa :hasBloodChild :t2 .
:pc :hasBloodChild :t2 .
:t1 :hasTwin :t2 .
```

##### only one shared biological parent all via hasBloodParent

```turtle
:t1 :hasBloodParent :pa .
:t1 :hasBloodParent :pb .
:t2 :hasBloodParent :pa .
:t2 :hasBloodParent :pc .
:t1 :hasTwin :t2 .
```

##### only one shared biological parent t1 via hasBloodChild, t2 via hasBloodParent

```turtle
:pa :hasBloodChild :t1 .
:pb :hasBloodChild :t1 .
:t2 :hasBloodParent :pa .
:t2 :hasBloodParent :pc .
:t1 :hasTwin :t2 .
```

##### only one shared biological parent t1 via hasBloodParent, t2 via hasBloodParent and hasBloodChild

```turtle
:t1 :hasBloodParent :pa .
:t1 :hasBloodParent :pb .
:t2 :hasBloodParent :pa .
:pc :hasBloodChild :t2  .
:t1 :hasTwin :t2 .
```

##### only one shared biological parent t1 via hasBloodChild, t2 via hasBloodChild and hasBloodParent

```turtle
:pa :hasBloodChild :t1 .
:pb :hasBloodChild :t1 .
:pa :hasBloodChild :t2 .
:t2 :hasBloodParent :pc .
:t1 :hasTwin :t2 .
```

##### only one shared biological parent t1 and t2 via hasBloodChild and hasBloodParent  

```turtle
:t1 :hasBloodParent :pa .
:pb :hasBloodChild :t1 .
:t2 :hasBloodParent :pa .
:pc :hasBloodChild :t2  .
:t1 :hasTwin :t2 .
```

### PAR - Partnership + direct parental conflict

Nature: legal/social convention in contemporary legal systems.

#### PAR1 - Partner of his child / parent

##### partner of his child (direct)

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:x (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :y .
```

##### partner of his child (indirect)

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:y (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :x .
```

##### partner of his parent (direct)

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:x (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :y .
```

##### partner of his parent (indirect)

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:y (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :x .
```

#### PAR2 - Partner of his grandparent / grandchild

Each 2-step lineage chain has 2^2 = 4 assertion combinations (hasChild vs hasParent per edge).

##### partner of his grandparent (direct)

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:x (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :z .
:z (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :y .
```

##### partner of his grandparent (mixed form 1)

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:x (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :z .
:y (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :z .
```

##### partner of his grandparent (mixed form 2)

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:z (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :x .
:z (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :y .
```

##### partner of his grandparent (mixed form 3)

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:z (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :x .
:y (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :z .
```

##### partner of his grandchild (direct)

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:x (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :z .
:z (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :y .
```

##### partner of his grandchild (mixed form 1)

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:x (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :z .
:y (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :z .
```

##### partner of his grandchild (mixed form 2)

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:z (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :x .
:z (:hasChild   | :hasBloodChild | :hasAdoptiveChild) :y .
```

##### partner of his grandchild (mixed form 3)

```turtle
:x (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :y .
:z (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :x .
:y (:hasParent  | :hasBloodParent | :hasAdoptiveParent) :z .
```

#### PAR3 - twin partnership conflict

##### twin of his partner (direct)

```turtle
:t1 :hasTwin :t2 .
:t1 (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :t2 .
```

##### twin of his partner (symmetric)

```turtle
:t1 :hasTwin :t2 .
:t2 (:hasPartner | :hasSpouse | :hasCivilPartner | :hasLifePartner) :t1 .
```

## Identification approaches

Two approaches are available for identifying inconsistencies in triplestore data:

1. **OWL Reasoner**:
   - Use an OWL reasoner to detect inconsistencies.
   - This approach is more comprehensive but requires a reasoner.
2. **SPARQL Queries**:
   - Use SPARQL queries to detect inconsistencies.
   - This approach is more flexible and can be used with any triplestore.

### SPARQL Detection

The below SPARQL queries assume no inference and no materialization — they are designed to be run against raw asserted data before any reasoning step.

#### Property families

To be included in each query header.

```sparql
PREFIX kin: <http://example.org/kinship#>
```

#### Q-IRR — Irreflexive self

Severity: High
Complexity: O(n) — single node lookup per property

```sparql
SELECT ?x ?p WHERE {
    VALUES ?p {
        kin:hasChild kin:hasBloodChild kin:hasAdoptiveChild
        kin:hasParent kin:hasBloodParent kin:hasAdoptiveParent
        kin:hasPartner kin:hasSpouse kin:hasCivilPartner kin:hasLifePartner
        kin:hasTwin
    }
    ?x ?p ?x .
}
```

#### Q-CON1 — Child & parent type conflict

Severity: High
Complexity: O(n)

```sparql
SELECT DISTINCT ?p ?c WHERE {
    {   ?p kin:hasBloodChild    ?c . ?p kin:hasAdoptiveChild  ?c . } UNION
    {   ?c kin:hasBloodParent   ?p . ?c kin:hasAdoptiveParent ?p . } UNION
    {   ?p kin:hasBloodChild    ?c . ?c kin:hasAdoptiveParent ?p . } UNION
    {   ?p kin:hasAdoptiveChild ?c . ?c kin:hasBloodParent    ?p . }
}
```

#### Q-CON2 — Role conflict

Severity: High
Complexity: O(n²)

```sparql
SELECT DISTINCT ?x ?y ?cp ?pp WHERE {
    VALUES ?cp { kin:hasChild kin:hasBloodChild kin:hasAdoptiveChild }
    VALUES ?pp { kin:hasParent kin:hasBloodParent kin:hasAdoptiveParent }
    ?x ?cp ?y .
    ?x ?pp ?y .
}
```

#### Q-CON3 — Gender conflict

Severity: High
Complexity: O(n)

```sparql
SELECT ?x WHERE {
    ?x kin:hasGender kin:Female .
    ?x kin:hasGender kin:Male .
}
```

#### Q-CON4 — Twin + generational conflict

Severity: High
Complexity: O(n²)

```sparql
SELECT DISTINCT ?t1 ?t2 WHERE {
    ?t1 kin:hasTwin ?t2 .
    VALUES ?cp { kin:hasChild kin:hasBloodChild kin:hasAdoptiveChild }
    VALUES ?pp { kin:hasParent kin:hasBloodParent kin:hasAdoptiveParent }
    {   ?t1 ?pp ?t2 . } UNION  # t2 is parent of t1 (direct)
    {   ?t2 ?cp ?t1 . } UNION  # t2 is parent of t1 (indirect)
    {   ?t1 ?cp ?t2 . } UNION  # t2 is child of t1 (direct)
    {   ?t2 ?pp ?t1 . }        # t2 is child of t1 (indirect)
}
```

#### Q-RED1 — Superproperty + subproperty redundancy

Severity: warning — data quality, not blocking
Complexity: O(n)

```sparql
SELECT DISTINCT ?x ?y ?sub ?super WHERE {
    VALUES (?sub ?super) {
        (kin:hasBloodChild    kin:hasChild)
        (kin:hasAdoptiveChild kin:hasChild)
        (kin:hasBloodParent   kin:hasParent)
        (kin:hasAdoptiveParent kin:hasParent)
        (kin:hasSpouse        kin:hasPartner)
        (kin:hasCivilPartner  kin:hasPartner)
        (kin:hasLifePartner   kin:hasPartner)
    }
    ?x ?sub   ?y .
    ?x ?super ?y .
}
```

#### Q-RED2 — Inverse property redundancy

Severity: warning — data quality, not blocking
Complexity: O(n)

```sparql
SELECT DISTINCT ?x ?y ?p ?q WHERE {
    VALUES (?p ?q) {
        (kin:hasChild          kin:hasParent) # symetric pair excluded to avoid duplicate results
        (kin:hasBloodChild     kin:hasBloodParent) # symetric pair excluded to avoid duplicate results
        (kin:hasAdoptiveChild  kin:hasAdoptiveParent) # symetric pair excluded to avoid duplicate results
        (kin:hasBloodChild     kin:hasParent)
        (kin:hasAdoptiveChild  kin:hasParent)
        (kin:hasBloodParent    kin:hasChild)
        (kin:hasAdoptiveParent kin:hasChild)

    }
    ?x ?p ?y .
    ?y ?q ?x .
}
```

#### Q-RED3 — Symmetric property both directions

Severity: warning — data quality, not blocking
Complexity: O(n)

```sparql
SELECT DISTINCT ?x ?y ?p WHERE {
    VALUES ?p {
        kin:hasPartner kin:hasSpouse kin:hasCivilPartner
        kin:hasLifePartner kin:hasTwin
    }
    ?x ?p ?y .
    ?y ?p ?x .
    FILTER(STR(?x) < STR(?y))
}
```

#### Q-CAR1 — More than 2 biological parents

Severity: High
Complexity: O(n)

```sparql
SELECT ?c (COUNT(DISTINCT ?p) AS ?nb) WHERE {
    {   ?c kin:hasBloodParent ?p . } UNION
    {   ?p kin:hasBloodChild  ?c . }
} GROUP BY ?c
HAVING (COUNT(DISTINCT ?p) > 2)
```

#### Q-CAR2 — Gendered blood parent conflict

Severity: High
Complexity: O(n)

```sparql
SELECT DISTINCT ?c ?gender (COUNT(DISTINCT ?p) AS ?nb) WHERE {
    VALUES ?gender { kin:Male kin:Female }
    {   ?c kin:hasBloodParent ?p . } UNION
    {   ?p kin:hasBloodChild  ?c . }
    ?p kin:hasGender ?gender .
} GROUP BY ?c ?gender
HAVING (COUNT(DISTINCT ?p) > 1)
```

#### Q-TWI1 — Twins sharing no biological parent

Severity: High
Complexity: O(n)

```sparql
SELECT ?t1 ?t2 WHERE {
    ?t1 kin:hasTwin ?t2 .
    FILTER(STR(?t1) < STR(?t2))
    FILTER NOT EXISTS {
        {   ?p kin:hasBloodChild  ?t1 . ?p kin:hasBloodChild  ?t2 . } UNION
        {   ?t1 kin:hasBloodParent ?p . ?t2 kin:hasBloodParent ?p . } UNION
        {   ?p kin:hasBloodChild  ?t1 . ?t2 kin:hasBloodParent ?p . } UNION
        {   ?t1 kin:hasBloodParent ?p . ?p kin:hasBloodChild  ?t2 . }
    }
}
```

#### Q-TWI2 — Twins with only one common biological parent

Severity: High
Complexity: O(n²)

```sparql
SELECT ?t1 ?t2 (COUNT(DISTINCT ?p) AS ?sharedParents) WHERE {
    ?t1 kin:hasTwin ?t2 .
    FILTER(STR(?t1) < STR(?t2))
    {   ?p kin:hasBloodChild  ?t1 . ?p kin:hasBloodChild  ?t2 . } UNION
    {   ?t1 kin:hasBloodParent ?p . ?t2 kin:hasBloodParent ?p . } UNION
    {   ?p kin:hasBloodChild  ?t1 . ?t2 kin:hasBloodParent ?p . } UNION
    {   ?t1 kin:hasBloodParent ?p . ?p kin:hasBloodChild  ?t2 . }
} GROUP BY ?t1 ?t2
HAVING (COUNT(DISTINCT ?p) = 1)
```

#### Q-CIR1 — Mutual parent/child (depth 1)

Severity: High
Complexity: O(n²)

```sparql
SELECT DISTINCT ?x ?y WHERE {
    VALUES ?cp { kin:hasChild kin:hasBloodChild kin:hasAdoptiveChild }
    VALUES ?pp { kin:hasParent kin:hasBloodParent kin:hasAdoptiveParent }
    {   ?x ?cp ?y . ?y ?cp ?x . } UNION
    {   ?x ?pp ?y . ?y ?pp ?x . }
    FILTER(STR(?x) < STR(?y))
}
```

#### Q-CIR2 — Generational cycle (depth 2) — all 8 forms

Severity: High
Complexity: O(n³)

```sparql
SELECT DISTINCT ?x ?y ?z WHERE {
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
```

#### Q-PAR1 — Partnership + direct parental conflict

Severity: High
Complexity: O(n²)

```sparql
SELECT DISTINCT ?x ?y ?partner ?rel WHERE {
    VALUES ?partner { kin:hasPartner kin:hasSpouse kin:hasCivilPartner kin:hasLifePartner }
    VALUES ?cp  { kin:hasChild  kin:hasBloodChild  kin:hasAdoptiveChild  }
    VALUES ?pp  { kin:hasParent kin:hasBloodParent kin:hasAdoptiveParent }
    ?x ?partner ?y .
    {   ?x ?cp ?y . BIND(?cp AS ?rel) } UNION  # PAR1: y is x's child
    {   ?x ?pp ?y . BIND(?pp AS ?rel) } UNION  # PAR1: y is x's parent
    {   ?y ?cp ?x . BIND(?cp AS ?rel) } UNION  # PAR2: y is x's parent (indirect)
    {   ?y ?pp ?x . BIND(?pp AS ?rel) }        # PAR2: y is x's child (indirect)
}
```

#### Q-PAR2 — Partnership + lineage conflict (depth 2)

Severity: High
Complexity: O(n³)

```sparql
SELECT DISTINCT ?x ?y ?z WHERE {
    VALUES ?partner { kin:hasPartner kin:hasSpouse kin:hasCivilPartner kin:hasLifePartner }
    VALUES ?cp { kin:hasChild  kin:hasBloodChild  kin:hasAdoptiveChild  }
    VALUES ?pp { kin:hasParent kin:hasBloodParent kin:hasAdoptiveParent }
    ?x ?partner ?y .
    {   # y is x's grandparent — 4 forms
        { ?x ?pp ?z . ?z ?pp ?y . } UNION   # PARL1 direct
        { ?x ?pp ?z . ?y ?cp ?z . } UNION   # PARL2 form 1
        { ?z ?cp ?x . ?z ?pp ?y . } UNION   # PARL2 form 2
        { ?z ?cp ?x . ?y ?cp ?z . }         # PARL2 form 3
    } UNION {
        # y is x's grandchild — 4 forms
        { ?x ?cp ?z . ?z ?cp ?y . } UNION   # PARL1 direct
        { ?x ?cp ?z . ?y ?pp ?z . } UNION   # PARL2 form 1
        { ?z ?pp ?x . ?z ?cp ?y . } UNION   # PARL2 form 2
        { ?z ?pp ?x . ?y ?pp ?z . }         # PARL2 form 3
    }
    FILTER(?z != ?x && ?z != ?y)
}

```

#### Q-PAR3 — Twin + partnership conflict

Severity: High
Complexity: O(n²)

```sparql
SELECT DISTINCT ?t1 ?t2 WHERE {
    ?t1 kin:hasTwin ?t2 .
    FILTER(STR(?t1) < STR(?t2))
    VALUES ?partner { kin:hasPartner kin:hasSpouse kin:hasCivilPartner kin:hasLifePartner }
    {   ?t1 ?partner ?t2 . } UNION
    {   ?t2 ?partner ?t1 . }
}
```

### OWL detection

When a violation exists in the asserted data, OWL inference and SPARQL
materialization propagate it through the property hierarchy, generating
derived triples that amplify the original error. The nature of propagation
depends on the violated constraint type.

#### Irreflexivity violations (IRR)

A self-referential assertion on any property propagates through the entire
`subPropertyOf` hierarchy upward. For example, `:c :hasBloodChild :c`
generates `:c :hasChild :c`, `:c :hasDescendant :c`, and `:c :hasRelative :c`
via superproperties. Via `owl:inverseOf`, it also generates `:c :hasBloodParent
:c` and `:c :hasAncestor :c`. Via the `hasSibling` materialization chain
(`hasParent ∘ hasChild`), `:c` becomes its own sibling. In OWL reasoners,
`owl:IrreflexiveProperty` flags the ontology as inconsistent on the first
reflexive triple detected.

Post-inference detection:

```sparql
## Q-POST-IRR — Any reflexive triple on lineage or partner properties
SELECT ?x ?p WHERE {
    VALUES ?p {
        kin:hasRelative kin:hasLineageRelative
        kin:hasDescendant kin:hasAncestor
        kin:hasChild kin:hasParent
        kin:hasBloodChild kin:hasBloodParent
        kin:hasSibling kin:hasPartner
    }
    ?x ?p ?x .
}
```

#### Disjointness violations (CON, CIR)

Disjointness violations propagate differently depending on whether cycles
are involved.

**Role conflicts** (`hasChild ⊥ hasParent`): asserting `:x :hasChild :y`
and `:x :hasParent :y` generates via `owl:inverseOf` both `:y :hasParent :x`
and `:y :hasChild :x`, creating a mutual cycle. Via `hasDescendant ⊥
hasAncestor`, the reasoner immediately detects inconsistency once the cycle
closes transitively.

**Generational cycles** (CIR): a 2-step cycle `:x → :y → :z → :x` via
`hasBloodParent` causes the transitive closure of `hasDescendant` and
`hasAncestor` to make every node simultaneously an ancestor and a descendant
of every other node in the cycle. This violates `hasDescendant
owl:propertyDisjointWith hasAncestor`. In materialization-based systems
without a reasoner, the SPARQL script populating `hasDescendant` would loop
indefinitely without a depth guard.

**Sibling cascade from cycles**: via the `hasSibling` materialization chain,
all children of cyclic parents become siblings of their own parents, violating
`hasSibling owl:propertyDisjointWith hasParent`.

Post-inference detection:

```sparql
## Q-POST-CIR — Self-ancestry via transitive closure
SELECT ?x WHERE { ?x kin:hasDescendant ?x . }
SELECT ?x WHERE { ?x kin:hasAncestor  ?x . }

## Q-POST-DIS — Sibling cascade: sibling also parent or child
SELECT ?x ?y WHERE {
    ?x kin:hasSibling ?y .
    { ?x kin:hasParent ?y . } UNION { ?x kin:hasChild ?y . }
}

## Q-POST-PAR — Partner also in lineage (via inferred hasDescendant)
SELECT ?x ?y WHERE {
    ?x kin:hasPartner ?y .
    { ?x kin:hasDescendant ?y . } UNION { ?x kin:hasAncestor ?y . }
}
```

#### Cardinality violations (CAR)

**Blood parent count**: an OWL reasoner flags any `kin:Person` instance
violating `owl:maxCardinality "2"` on `hasBloodParent` as locally
inconsistent. The derived gendered properties amplify the error: three blood
parents may include two males, which additionally violates
`owl:maxQualifiedCardinality "1" owl:onClass :MalePerson`, generating a
second independent inconsistency on the same individual.

**Gender conflict** (CAR2): two blood parents of the same gender cause the
individual to be simultaneously classified as both `:MalePerson` and
`:FemalePerson` via the GCI pattern (`hasGender :Male → :MalePerson`),
violating `owl:disjointWith`. Post-inference, the materialization of gendered
relationship properties (`:hasMother`, `:hasFather`) may produce contradictory
derivations from the same set of relationships.

Post-inference detection:

```sparql
## Q-POST-CAR — Person classified as both MalePerson and FemalePerson
SELECT ?p WHERE {
    ?p a kin:MalePerson .
    ?p a kin:FemalePerson .
}

## Q-POST-GMAT — Gendered property asserted on wrong-gender individual
## (rdfs:range violation detectable post-materialization)
SELECT ?x ?wife WHERE {
    ?x kin:hasWife ?wife .
    FILTER NOT EXISTS { ?wife a kin:FemalePerson }
}
SELECT ?x ?husband WHERE {
    ?x kin:hasHusband ?husband .
    FILTER NOT EXISTS { ?husband a kin:MalePerson }
}
```

#### Summary: assertion vs post-inference detection

| Constraint              | Pre-inference (raw data)      | Post-inference (owl:Nothing)         |
|---                      |---                            |---                                   |
| IRR                     | Q-IRR on asserting properties | Q-POST-IRR on all superproperties    |
| CON disjointness        | Q-CON1, Q-CON2                | Q-POST-DIS sibling cascade           |
| CIR generational cycle  | Q-CIR1, Q-CIR2                | Q-POST-CIR self-ancestry             |
| CAR blood parent count  | Q-CAR1                        | OWL inconsistency on Person instance |
| CAR gender conflict     | Q-CAR2                        | Q-POST-CAR dual class membership     |
| PAR partnership+lineage | Q-PAR1, Q-PAR2                | Q-POST-PAR via hasDescendant         |
| TWI1 common parent      | Q-TWI1a, Q-TWI1b              | ❌ no OWL axiom — SPARQL only        |
| RED redundancy          | Q-RED1, Q-RED2, Q-RED3        | ❌ not an inconsistency              |

#### post-inference owl constraint violation existence check

Determining whether any owl constraint violations exist after reasoning
can be done by checking if any individuals are marked as `owl:Nothing` by the
reasoner.

Existence check Requires OWL RL reasoning to have been applied after
materialization. A single ASK query determines whether any individual has been
marked `owl:Nothing` by the reasoner.

**Benefit 1 — cost**: on a consistent base, this O(1) check short-circuits
all targeted post-inference queries. No targeted query is run unless a
violation is confirmed.

**Benefit 2 — coverage sentinel**: the count of `owl:Nothing` individuals
establishes a ground truth against which Gate 8 targeted queries are
verified. Any gap between the two counts signals either a missing targeted
query or a violation type not yet modelled.

**Scope limitation**: `owl:Nothing` is only inferred for violations where
an OWL axiom is declared (IRR, CON, CIR, CAR). TWI1 (no OWL axiom for
common-parent constraint) and RED (redundancy, not an inconsistency) are
outside the scope of this gate and remain under Gates 4 and 6 respectively.

Q-POST-COUNT is run only if Q-POST-EXISTS returns true.

```sparql
## Q-POST-EXISTS — Gate 7: existence check (run first)
ASK {
    ?x rdf:type owl:Nothing .
    FILTER(?x != owl:Nothing)
}

## Q-POST-COUNT — Gate 7: ground truth count for coverage verification
SELECT (COUNT(DISTINCT ?x) AS ?violatingIndividuals) WHERE {
    ?x rdf:type owl:Nothing .
    FILTER(?x != owl:Nothing)
}
```

#### post-inference targeted queries coverage

Counting the number of individuals found by all post-inference targeted queries
and comparing it against Q-POST-COUNT allows to identify any gap that indicates
incomplete coverage and triggers a diagnostic review.

```sparql
## Q-POST-COVERAGE — Gate 8 coverage verification
## Count distinct individuals found by all targeted queries combined.
## Should equal Q-POST-COUNT result. Any shortfall = uncovered violation type.
SELECT (COUNT(DISTINCT ?x) AS ?coveredIndividuals) WHERE {
    { SELECT ?x WHERE { ?x rdf:type owl:Nothing . FILTER(?x != owl:Nothing) .
                        ?x ?p ?x . } }                          # IRR
    UNION
    { SELECT ?x WHERE { ?x kin:hasDescendant ?x . } }           # CIR transitive
    UNION
    { SELECT ?x WHERE { ?x rdf:type kin:MalePerson .
                        ?x rdf:type kin:FemalePerson . } }      # CAR2
    UNION
    { SELECT ?x WHERE { ?x rdf:type owl:Nothing .               # CAR1, CON
        FILTER(?x != owl:Nothing) .
        FILTER NOT EXISTS { ?x ?p ?x . }                        # exclude IRR
        FILTER NOT EXISTS { ?x kin:hasDescendant ?x . } } }     # exclude CIR
}
```

## Detection strategy

To avoid family relationship network data to become inconsistent, there is
a need to:

- identify potential inconsistencies in the data.
- identify the root cause of the inconsistencies to understand why they
  occurred and help fix them.
- prevent inconsistencies from propagating.

To achieve these goals, the below strategy combines two complementary
detection levels:

1. **SPARQL queries**:
   - detects violations on asserted triples without relying on inference.
   - Covers all subproperty variants via VALUES clauses.
   - The authoritative detection path.
2. **OWL reasoning**:
   - detects violations after inference on superproperties.
   - Requires a reasoner and materialised inferred data.
   - Catches errors structurally but only on inferred triples.

organised in a pipeline:

- **Execution pipeline**:
  - Organises SPARQL queries into ordered gates.
  - Cheaper and more selective queries run first (fail-fast).
  - Blocking errors stop the pipeline; quality warnings are reported
    asynchronously.

The consistency rules defined in the above catalog operate at two levels:
the assertion level (detectable by the SPARQL queries listed above on raw
data) and the inference level (detectable after reasoning and
materialization).

### Execution pipeline

Queries are ordered by two criteria applied in combination:

1. Severity   — blocking errors before warnings
2. Complexity — cheaper queries first (fail fast)

Pre-inference

| Gate | Query           | Detects                              | Complexity | Blocking   |
|---   |---              |---                                   |---         |---         |
| 1    | Q-IRR           | Self-referential assertions          | O(1)/node  | yes        |
| 1    | Q-CON3          | Gender conflict                      | O(n)       | yes        |
| 2    | Q-CON1          | Blood/adoptive type conflict         | O(n)       | yes        |
| 2    | Q-CAR1          | More than 2 blood parents            | O(n)       | yes        |
| 2    | Q-CAR2          | More than 1 parent of same gender    | O(n)       | yes        |
| 3    | Q-CON2          | Simultaneous child and parent        | O(n²)      | yes        |
| 3    | Q-CIR1          | Mutual parent/child cycle depth 1    | O(n²)      | yes        |
| 4    | Q-TWI           | Twins without/with 1 common parent   | O(n²)      | yes        |
| 4    | Q-CON4          | Twin + generational conflict         | O(n²)      | yes        |
| 4    | Q-PAR3          | Partnership + twin relationship      | O(n²)      | yes        |
| 4    | Q-PAR1          | Partnership + direct parental        | O(n²)      | yes        |
| 5    | Q-CIR2          | Generational cycle depth 2           | O(n³)      | yes        |
| 5    | Q-PAR2          | Partnership + grandparent/grandchild | O(n³)      | yes        |
| 6    | Q-RED1          | Superproperty redundancy             | O(n)       | warning    |
| 6    | Q-RED2          | Inverse property redundancy          | O(n)       | warning    |
| 6    | Q-RED3          | Symmetric property both directions   | O(n)       | warning    |

Post-inference

| Gate | Query           | Detects                              | Complexity | Blocking   |
|---   |---              |---                                   |---         |---         |
| 7    | Q-POST-EXISTS   | Any owl:Nothing individual exists    | O(1)       | yes        |
| 8    | Q-POST-*        | Targeted post-inference detection    | O(n)       | yes        |
| 8    | Q-POST-COVERAGE | Gap between owl:Nothing and targeted | O(n)       | diagnostic |

#### Gate rationale

Pre-inference queries (Gates 1–5) are the authoritative detection path and
should be run before any materialization. Post-inference queries serve as a
secondary validation layer, confirming that no violation was missed in the
raw data and that materialization has not introduced new inconsistencies.

- Gate 1
  - O(1) per node / O(n) total: single-node checks, cheapest possible.
  - Run before any other check. No result expected.
- Gate 2
  - O(n) blocking: pair checks requiring no join across relationship types.
  - Catch type conflicts and cardinality violations cheaply.
- Gate 3
  - O(n²) blocking, depth 1: pair joins across different relationship types.
  - CON2 and CIR1 are the most likely data entry errors after IRR.
- Gate 4
  - O(n²) blocking, domain-specific: twin and partnership checks.
  - More selective patterns, lower false positive risk.
- Gate 5
  - O(n³) blocking: expensive multi-hop queries.
  - Run only after gates 1-4 pass to avoid compounding errors.
- Gate 6
  - O(n) warnings: data quality issues, non-blocking.
  - Run last or asynchronously — results go to a quality report, not a
  blocking gate.

The post-inference queries (Gates 7–8) relies on the triplestore
marking individual inconsistencies via `rdf:type owl:Nothing` rather than
declaring the entire ontology inconsistent. This behaviour requires an
**OWL RL / RDFS+ reasoning mode**:

- **OWL 2 DL reasoners** (HermiT, FaCT++): on first violation, the entire
  ontology becomes globally inconsistent. All individuals are inferred as
  `owl:Nothing`, making targeted detection impossible.
- **OWL RL reasoners** (GraphDB OWL RL mode, Stardog OWL RL): violations are
  marked incrementally per individual. Only the individuals directly involved
  in a violated constraint receive `rdf:type owl:Nothing`.

GraphDB and Stardog are the recommended triplestores for this strategy.
Oxigraph and Amazon Neptune do not support the required reasoning mode.

- Gate 7 — post-inference existence check
  - O(1) : cheapest possible.
  - Run before any other specific post-inference check. No result expected.

- Gate 8 — post-inference targeted detection (conditional on Gate 7)
  - Run only if Q-POST-EXISTS returns true.
  - Each targeted query identifies the individuals involved in a specific
  violation type, enabling root-cause diagnosis.
  - After all targeted queries, the union of their results is compared against
  the Gate 7 count. A gap indicates incomplete coverage and triggers a
  diagnostic review.

#### Implementation note

Gates 1-2 should be run as a pre-commit hard block.
Gates 3-5 should be run as a pre-materialization block.
Gate 6 should be run as an asynchronous quality report.
Gates 7-8 require OWL RL reasoning to be active and should be run
immediately after each materialization cycle. Gate 7 acts as a fast sentinel:
if it returns false, Gates 8 are skipped entirely. If it returns true,
Gate 8 targeted queries run and their combined coverage is compared to the
Gate 7 ground truth count. Any gap between the two counts must be investigated
before the data is considered consistent.
