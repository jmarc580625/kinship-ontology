# Kinship events — structural design choices

## Overview

The kinship-events layer captures *when* kinship facts begin and end. It is
composed of two modules: a standalone temporal vocabulary
(`temporal-foundation.ttl`) and an event-centric module
(`kinship-events.ttl`) that reifies kinship facts as datable occurrences.
Together they add a temporal dimension to the otherwise static relationship
graph of the core ontology.

### Goal

Model the chronological reality of family life — births, deaths, marriages,
divorces, adoptions — as first-class entities that can carry dates, precision
metadata, and causal links, while keeping the temporal machinery independent
from the relationship axioms defined in the core modules.

### Approach

The design separates concerns into two layers:

1. **Temporal foundation** — a minimal, import-free vocabulary of time
   intervals and date estimates reusable by any module.
2. **Kinship events** — a class hierarchy of events linked to people via
   participation properties and to time via validity intervals.

Inferences that exceed OWL 2 RL expressivity (e.g., deriving a partnership
dissolution from a death) are handled through embedded SPARQL materialization
scripts, following the same pattern as the core ontology.

## Articulation with the kinship ontology

### Import graph position

```text
kinship-events.ttl
├── owl:imports  temporal-foundation.ttl
├── owl:imports  gender-foundation.ttl       (for :Person)
└── owl:imports  materialization-foundation.ttl (for :MaterializationReason / :MaterializationScript)
```

`kinship-events` does **not** import the core relationship modules
(`core-neutral`, `gendered`, etc.). It depends only on foundation-level
concepts. This means it can be loaded and validated independently of any
relationship axiom — the event layer and the relationship layer are
structurally orthogonal.

### Bridge between events and relationships

The articulation with the relationship graph operates through two mechanisms:

- **Materialization source** — event-level properties serve as the raw data
  from which person-level relationships are materialized. For example,
  `:hasEventGodparent` on a `:Birth` event feeds the materialization of
  `:hasGodparent` (defined in `anchored-neutral.ttl`), and `:hasWitnessed` on
  a `:Marriage` event feeds `:hasWitness`.
- **Temporal validity for relationships** — partnership events
  (`:PartnershipStart`, `:PartnershipEnd`) carry the validity interval that
  determines when a partnership relationship is active, enabling temporal
  queries over the otherwise time-agnostic relationship triples.

### Named graph convention

Materialized events are stored in a dedicated named graph
(`<urn:kinship:materialized:events>`) separate from user-asserted events
(`<urn:kinship:events>`), preserving provenance.

## Temporal foundation module

`temporal-foundation.ttl` is a self-contained module with **no imports**. It
defines two independent concepts.

### Validity interval

`:ValidityInterval` models a time span during which a fact holds:

| Property | Range | Semantics |
| --- | --- | --- |
| `:validFrom` | `xsd:date` | Start date of validity |
| `:validTo` | `xsd:date` | End date of validity; **absent = currently valid** (open interval) |

The open-interval convention avoids the need for sentinel future dates; an
event without `:validTo` is considered ongoing.

### Temporal estimate

`:TemporalEstimate` handles imprecise or uncertain dates common in
genealogical research:

| Property | Range | Semantics |
| --- | --- | --- |
| `:estimatedDate` | `xsd:date` | Best-guess date |
| `:precision` | `:PrecisionLevel` | Qualitative confidence level |
| `:marginYears` | `xsd:integer` | ± N years around `:estimatedDate` |

`:PrecisionLevel` is an enumerated class with four named individuals:

- **`:Exact`** — date is known precisely
- **`:Circa`** — approximate, bounded by `:marginYears`
- **`:Decade`** — only the decade is known
- **`:Unknown`** — no date information available

This graduated precision model lets downstream tools decide how to interpret
date assertions without losing information through premature rounding.

## Event class hierarchy

All event classes descend from a single abstract root:

```text
:KinshipEvent
├── :Birth
├── :Death
├── :PartnershipEvent
│   ├── :PartnershipStart
│   │   └── :Marriage
│   └── :PartnershipEnd
│       ├── :Divorce
│       └── :PartnershipEndByDeath   (materialized)
└── :Adoption
```

Design rules:

- **`:KinshipEvent` is never instantiated directly** — it serves only as a
  polymorphic query target.
- **`:PartnershipEvent`** groups start and end events, allowing queries
  over the full lifecycle of a partnership.
- **`:PartnershipEndByDeath`** is the only class that is never asserted
  manually — it is produced exclusively by materialization.

## Participation properties

Events are linked to participants through a rooted property hierarchy:

```text
:hasPrincipal           (domain: KinshipEvent, range: Person)
├── :hasPartner1        (domain: PartnershipEvent)
├── :hasPartner2        (domain: PartnershipEvent)
├── :hasBeenAdopted     (domain: Adoption)
└── :hasAdopted         (domain: Adoption)
```

Key design rules:

- **`:hasPrincipal`** is the root — any SPARQL query using `:hasPrincipal`
  retrieves all participants of any event type.
- **Partner ordering** — `:hasPartner1` / `:hasPartner2` introduce an
  arbitrary but stable ordering (useful for deterministic IRI generation in
  materialization scripts). They are not semantically asymmetric.
- **Adoption roles** — `:hasBeenAdopted` and `:hasAdopted` distinguish
  adoptee from adopter within the same event.

## Event-level vs. person-level properties

A deliberate duplication exists between event properties and person-level
relationship properties:

| Event property | Person-level counterpart | Module |
| --- | --- | --- |
| `:hasEventGodparent` | `:hasGodparent` | `anchored-neutral.ttl` |
| `:hasWitnessed` | `:hasWitness` | `anchored-neutral.ttl` |
| `:hasPartner1` / `:hasPartner2` | `:hasPartner` | `core-neutral.ttl` |
| `:hasBeenAdopted` / `:hasAdopted` | `:hasAdoptiveChild` / `:hasAdoptiveParent` | `core-neutral.ttl` |

Rationale: event properties carry temporal context (which event, which date)
that the person-level properties discard in favor of direct person-to-person
navigation. Materialization bridges the two by projecting event-level
assertions into the relationship graph.

## Materialization: PartnershipEndByDeath

The most complex materialization in the ontology infers partnership
dissolution from a death event. It is annotated with
`:MaterializationReason :ComplexPathLimitation`.

### Logic

```sparql
INSERT {
    <generated-IRI>  a :PartnershipEndByDeath ;
        :hasPartner1 ?p1 ;
        :hasPartner2 ?p2 ;
        :causedBy    ?deathEvent ;
        :hasValidity [ a :ValidityInterval ; :validFrom ?deathDate ] .
}
WHERE {
    -- Active partnership
    ?start a :PartnershipStart ;
        :hasPartner1 ?p1 ; :hasPartner2 ?p2 ;
        :hasValidity/:validFrom ?startDate .
    -- Death of one partner
    ?deathEvent a :Death ;
        :hasPrincipal ?deceased ;
        :hasValidity/:validFrom ?deathDate .
    FILTER(?deceased IN (?p1, ?p2))
    FILTER(?deathDate > ?startDate)
    -- No pre-existing dissolution
    FILTER NOT EXISTS { ... }
}
```

### Design decisions

- **Deterministic IRI** — generated via `IRI(CONCAT(...))` from partner IRIs
  and death date, making the script idempotent (re-running produces the same
  triples).
- **Temporal ordering** — `FILTER(?deathDate > ?startDate)` ensures the death
  post-dates the partnership start.
- **Pre-existing dissolution guard** — `FILTER NOT EXISTS` prevents generating
  a death-based dissolution if the partnership was already ended (by divorce
  or earlier death).
- **`:causedBy`** — a dedicated property links the dissolution event to the
  specific `:Death` event, enabling provenance tracing.

## Why OWL reasoning is insufficient

The `:PartnershipEndByDeath` inference requires:

1. **Negation** — checking that no prior dissolution exists (`FILTER NOT
   EXISTS`), which is outside OWL 2 RL's monotonic semantics.
2. **Date comparison** — temporal ordering between events requires arithmetic
   filters unavailable in OWL property chains.
3. **Disjunctive participant matching** — `FILTER(?deceased IN (?p1, ?p2))`
   expresses a union pattern not representable as a single property chain.

These three limitations combined justify the `:ComplexPathLimitation`
annotation and the use of SPARQL materialization.

## Summary of structural choices

| Axis | Decision | Consequence |
| --- | --- | --- |
| Modularity | Temporal foundation has zero imports | Reusable outside kinship context |
| Uncertainty | Graduated precision model (Exact → Unknown) | No information loss on imprecise dates |
| Open intervals | Absent `:validTo` = ongoing | No sentinel dates needed |
| Event reification | Facts modeled as event instances | Temporal queries without rewriting relationship triples |
| Participation hierarchy | Single root `:hasPrincipal` | Polymorphic event queries |
| Event vs. person properties | Deliberate duplication | Separation of temporal context from navigational convenience |
| Materialized dissolution | SPARQL with negation and date arithmetic | Correct handling of death-induced partnership end |
| Named graph separation | Materialized events in dedicated graph | Clean provenance boundary |
