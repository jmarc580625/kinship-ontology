# Kinship ontology — structural design choices

## Overview

This document describes the key structural decisions that shape the kinship
ontology. It covers the modular architecture, the property hierarchy, the
gender modeling strategy, the inference and materialization approach, and the
consistency safeguards embedded in the ontology itself.

### Goal

Provide a concise reference for understanding *why* the ontology is organized
the way it is: which trade-offs were made, which OWL 2 RL limitations are
worked around, and how the various modules interact.

### Approach

Each section below isolates one structural axis and explains the design
rationale, the OWL constructs used, and the consequences for data entry and
querying.

## Modular architecture

The ontology is split into independent, composable modules linked by
`owl:imports`. A single entry point (`kinship.ttl`) transitively imports every
module. The dependency graph follows a layered design:

1. **Foundation layers** (no family-relationship semantics)
   - `materialization-foundation.ttl` — annotation properties and
     materialization reason taxonomy
   - `gender-foundation.ttl` — `:Person`, `:GenderIdentity`, `:hasGender`,
     `:FemalePerson` / `:MalePerson`
   - `lineage-foundation.ttl` — `:hasRelative` root property,
     `:hasLineageRelative`, `:hasCeremonialBond`, annotation flags
     `:crossesAlliance` / `:crossesAdoption`
   - `foundation.ttl` — empty grouping module that imports
     `materialization-foundation` and `lineage-foundation`

2. **Core layer**
   - `core-neutral.ttl` — gender-neutral core relationships (filiation,
     partnership, sibling, twin, ancestor/descendant) plus disjointness and
     cardinality axioms

3. **Extension layers** (mutually independent, all import `core-neutral`)
   - `extended-neutral.ttl` — grandparent, great-grandparent, uncle/aunt,
     nibling, cousin
   - `blended-neutral.ttl` — step-child, step-parent, step-sibling,
     half-sibling
   - `anchored-neutral.ttl` — ceremonial relationships (godparent, witness)

4. **Allied layer**
   - `allied-neutral.ttl` — in-law relationships (imports `extended-neutral`)

5. **Gendered layer**
   - `gendered.ttl` — gender-specific variants of all gender-neutral
     relationships across every layer; imports all neutral modules

6. **Peripheral module**
   - `social.ttl` — non-family social bonds (friendship); fully independent
     from all other modules

This layering ensures that each module can be loaded and tested in isolation.
Triplestores that do not support `owl:imports` must load modules in a
depth-first traversal order matching the import graph.

## Property hierarchy

All kinship properties descend from a single root:

```text
:hasRelative (SymmetricProperty)
├── :hasLineageRelative
│   ├── :hasDescendant / :hasAncestor    (TransitiveProperty, blood-only)
│   ├── :hasSibling                      (SymmetricProperty, materialized)
│   │   ├── :hasTwin
│   │   └── :hasHalfSibling
│   ├── :hasGrandchild / :hasGrandparent
│   ├── :hasGreatGrandchild / :hasGreatGrandparent
│   ├── :hasSiblingNibling / :hasSiblingUncleAunt
│   └── :hasCousin                       (SymmetricProperty)
├── :hasChild / :hasParent               (inverseOf pair)
│   ├── :hasBloodChild / :hasBloodParent (subPropertyOf :hasDescendant / :hasAncestor)
│   └── :hasAdoptiveChild / :hasAdoptiveParent
├── :hasPartner                          (SymmetricProperty)
│   ├── :hasSpouse
│   ├── :hasCivilPartner
│   └── :hasLifePartner
├── :hasStepChild / :hasStepParent
├── :hasStepSibling
├── :hasChildInLaw / :hasParentInLaw
├── :hasSiblingInLaw
├── :hasNibling / :hasUncleAunt
│   ├── :hasSiblingNibling / :hasSiblingUncleAunt
│   └── :hasNiblingInLaw / :hasUncleAuntInLaw
└── :hasCeremonialBond
    ├── :hasGodchild / :hasGodparent
    └── :hasWitness / :hasWitnessed
```

Key design rules:

- **`:hasChild` / `:hasParent` are *not* subproperties of
  `:hasDescendant` / `:hasAncestor`**. Only the blood-typed variants
  (`:hasBloodChild`, `:hasBloodParent`) anchor the transitive
  ancestor/descendant chain. This prevents adoptive links from producing
  spurious blood-lineage inferences.
- **`:hasRelative`** carries `rdfs:domain :Person` and `rdfs:range :Person`,
  inherited by all subproperties.
- **Inverse pairs** are declared with `owl:inverseOf` wherever the relationship
  is directional (parent/child, grandparent/grandchild, etc.).

## Blood lineage vs. adoption separation

The ontology distinguishes three filiation knowledge levels:

| Property           | Meaning                             | Part of transitive lineage? |
|--------------------|-------------------------------------|-----------------------------|
| `:hasChild`        | child (type unknown)                | No                          |
| `:hasBloodChild`   | biological child                    | Yes (→ `:hasDescendant`)    |
| `:hasAdoptiveChild`| adoptive child                      | No                          |

`:hasBloodChild` is a subproperty of both `:hasChild` (inclusive hierarchy) and
`:hasDescendant` (transitive blood closure). `:hasAdoptiveChild` is a
subproperty of `:hasChild` only — it is deliberately excluded from
`:hasDescendant`, so that adoption never creates a blood-lineage path.

A disjointness axiom enforces mutual exclusivity:

```turtle
:hasBloodChild  owl:propertyDisjointWith :hasAdoptiveChild .
:hasBloodParent owl:propertyDisjointWith :hasAdoptiveParent .
```

Consequence: a person who is both biological and legally adoptive child of the
same parent must be modeled as `:hasBloodChild` only.

## Gender modeling — the firewall pattern

Gender is modeled as an explicitly asserted value, never as an inference side
effect.

### Single source of truth

`:hasGender` is the only property that establishes gender. It links a `:Person`
to one of two `owl:NamedIndividual` instances of `:GenderIdentity`: `:Female`
or `:Male`. A `maxQualifiedCardinality 1` restriction on `:Person` ensures at
most one gender value. `:Female` and `:Male` are declared `owl:AllDifferent`.

### One-directional GCI pattern

`:FemalePerson` and `:MalePerson` are convenience classes used as `rdfs:range`
on gendered properties (`:hasWife`, `:hasMother`, etc.). The entailment is
*one-directional*:

- `:hasGender :Female` → membership in `:FemalePerson` ✓
- membership in `:FemalePerson` → `:hasGender :Female` ✗

This is achieved via a GCI (General Class Inclusion) rather than an
equivalence axiom:

```turtle
[ a owl:Restriction ; owl:onProperty :hasGender ; owl:hasValue :Female ]
    rdfs:subClassOf :FemalePerson .
```

### Gendered properties are never asserted — only materialized

All gendered properties (`:hasWife`, `:hasFather`, `:hasSister`, etc.) carry
`:MaterializationReason :GenderFirewallLimitation` and an embedded
`:MaterializationScript`. They are produced by SPARQL INSERT rules that read
from the gender-neutral parent property *and* from `:hasGender`:

```sparql
INSERT { ?spouse :hasWife ?wife . }
WHERE  { ?wife :hasSpouse ?spouse . ?wife :hasGender :Female . }
```

This prevents `rdfs:range :FemalePerson` from back-propagating a gender
assertion through OWL inference, preserving `:hasGender` as the single
authoritative source.

## Inference and materialization strategy

The ontology targets **OWL 2 RL** reasoning. Where OWL 2 RL expressivity is
insufficient, the ontology falls back to SPARQL-based materialization.

### OWL-native inference

The following constructs are handled by standard OWL reasoning:

- **`rdfs:subPropertyOf`** — property hierarchy propagation
- **`owl:inverseOf`** — automatic inverse triple generation
- **`owl:TransitiveProperty`** — ancestor/descendant closure
  (`:hasDescendant`, `:hasAncestor`)
- **`owl:SymmetricProperty`** — bidirectional partnership, sibling, twin
- **`owl:propertyChainAxiom`** — grandparent (`hasChild ∘ hasChild`),
  great-grandparent (`hasGrandchild ∘ hasChild`), nibling
  (`hasSibling ∘ hasChild`), cousin (`hasSiblingUncleAunt ∘ hasChild`),
  child-in-law (`hasChild ∘ hasPartner`), nibling-in-law
  (`hasPartner ∘ hasSibling ∘ hasChild`)

### SPARQL materialization

Four categories of limitations are identified, each represented as a named
individual of the `:MaterializationReason` class:

| Reason | Description | Affected properties |
| --- | --- | --- |
| `:IrreflexivePropertyLimitation` | OWL property chains cannot guarantee irreflexivity | `:hasSibling` |
| `:UnionPatternLimitation` | OWL property chains are strictly linear — no branching (A or B) | `:hasSiblingInLaw` |
| `:ComplexPathLimitation` | Requires negative property assertions or counting beyond OWL 2 RL | `:hasStepChild`, `:hasStepSibling`, `:hasHalfSibling`, `:PartnershipEndByDeath` |
| `:GenderFirewallLimitation` | `rdfs:range` inference would corrupt the gender single source of truth | All gendered properties (40+ properties) |

Each affected property carries a `:MaterializationScript` annotation containing
the complete SPARQL UPDATE query to produce its triples.

## Consistency safeguards

### Disjointness axioms

The core module declares property-level disjointness to prevent logically
impossible or conventionally excluded situations:

| Axiom | Rationale |
| --- | --- |
| `:hasChild ⊥ :hasParent` | A person cannot be simultaneously child and parent of the same individual |
| `:hasDescendant ⊥ :hasAncestor` | Prevents generational cycles in blood lineage |
| `:hasSibling ⊥ :hasChild` | Sibling cannot also be child (social convention) |
| `:hasSibling ⊥ :hasParent` | Sibling cannot also be parent (social convention) |
| `:hasBloodChild ⊥ :hasAdoptiveChild` | Filiation type is exclusive |
| `:hasBloodParent ⊥ :hasAdoptiveParent` | Filiation type is exclusive |
| `:hasPartner ⊥ :hasChild` | Partner cannot be child |
| `:hasPartner ⊥ :hasParent` | Partner cannot be parent |
| `:hasPartner ⊥ :hasDescendant` | Partner cannot be blood descendant |
| `:hasPartner ⊥ :hasAncestor` | Partner cannot be blood ancestor |
| `:hasChild ⊥ :hasStepChild` | Own child cannot also be step-child |
| `:hasParent ⊥ :hasStepParent` | Own parent cannot also be step-parent |
| `:hasSibling ⊥ :hasStepSibling` | Sibling cannot also be step-sibling |
| `:hasChildInLaw ⊥ :hasChild` | Child-in-law cannot be own child |
| `:hasParentInLaw ⊥ :hasParent` | Parent-in-law cannot be own parent |

### Cardinality constraints

Three restrictions are declared on `:Person` for `:hasBloodParent`:

- **`owl:maxCardinality 2`** — at most 2 biological parents
- **`owl:maxQualifiedCardinality 1` on `:MalePerson`** — at most 1 male
  biological parent
- **`owl:maxQualifiedCardinality 1` on `:FemalePerson`** — at most 1 female
  biological parent

Additionally, `:hasGender` carries a `maxQualifiedCardinality 1` restriction
on `:GenderIdentity`, preventing conflicting gender assignments.

### Irreflexive property declarations

All properties where self-reference is impossible are typed
`owl:IrreflexiveProperty`: partnership properties, sibling properties, twin,
cousin, step-sibling, ancestor/descendant, and friendship.

## Annotation flag conventions

Two custom annotation properties serve as binary flags (presence = true,
absence = false):

- **`:crossesAlliance`** — the property path crosses at least one partnership
  link (e.g., `:hasChildInLaw`, `:hasStepChild`, `:hasSiblingInLaw`,
  `:hasNiblingInLaw`)
- **`:crossesAdoption`** — the property path crosses at least one adoptive
  link (e.g., `:hasAdoptiveChild`, `:hasAdoptiveParent`)

These flags provide machine-readable metadata for query builders and data
validation tools without adding OWL-level semantics.

## Social module independence

`social.ttl` defines non-family social relationships (`:hasFriend`,
`:hasCloseFriend`) as subproperties of `foaf:knows`. This module has no
`owl:imports` dependency on any other kinship module, making it entirely
optional and independently loadable.
