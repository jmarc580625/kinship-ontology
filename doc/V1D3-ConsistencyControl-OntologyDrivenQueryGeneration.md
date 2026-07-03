# Volume 1: Consistency Control — Document 3: Ontology-Driven Query Generation

## 1. Purpose

The MATS and OATS pattern catalogs (Document 2: Gate Pipelines and Pattern
Catalogs) hand-enumerate detection queries property by property. This is
exhaustive and auditable, but every new property added to the ontology
requires a corresponding manual addition to the catalog, and several
detection families (irreflexivity, redundancy, role conflicts) follow a
mechanical pattern that the ontology itself already encodes.

This document describes the query generator implemented on top of
`consistency-foundation.ttl` (the vocabulary: `assertionSet`,
`generationalDepth`, `generationalDirection`, `disjointnessNature`) and
`kinship-consistency.ttl` (the application of that vocabulary to every
property in the kinship ontology). Rather than maintaining `VALUES` lists
by hand, the generator queries the TBox (`<urn:kinship:ontology>` graph) for
the relevant OWL characteristics and metadata, and produces the SPARQL
detection queries from the result. The hand-maintained catalogs in Document 2
remain the reference documentation of *what* is detected and *why*; this
generator is the mechanism that keeps the *queries themselves* synchronized
with the ontology automatically.

## 2. Architecture

```text
TBox (consistency-foundation.ttl + kinship-consistency.ttl
      + core-neutral.ttl + extended-neutral.ttl + ... )
        ↓
   Meta-queries (read-only, run once per TBox change)
        ↓
   Query templates (parameterized SPARQL strings)
        ↓
   Target graph binding (urn:kinship:asserted | urn:kinship:oats)
        ↓
   Generated, ready-to-run detection queries
        ↓
   Pipeline execution (unchanged from Document 1's architecture)
```

The TBox is reasoned and materialized once, infrequently — only when the
ontology itself changes. The ABox (MATS or OATS quarantine graph) is never
reasoned over; the generated queries run against it exactly as the
hand-written ones did. This preserves every guarantee already established
for the pipeline (no-inference detection, graph isolation between
`<urn:kinship:asserted>` and `<urn:kinship:oats>`).

Two integration modes are supported by the implementation:

- **On-the-fly join**: a single query joins the ontology graph and the data
  graph in one execution. Simplest to reason about, slightly more costly per
  call.
- **Generate-then-cache**: the meta-queries run once, the resulting concrete
  SPARQL strings (with the ontology-derived `VALUES` already substituted)
  are cached and reused across every pipeline run until the TBox changes.
  Recommended for the pipeline, since the MATS Gate's steps and the OATS
  layers run repeatedly against a TBox that changes far less often than
  the ABox.

## 3. Foundation vocabulary and what it drives

| Vocabulary element | Source | Drives |
| --- | --- | --- |
| `owl:IrreflexiveProperty` / `owl:AsymmetricProperty` | OWL 2 native | IRR generation |
| `owl:AsymmetricProperty` | OWL 2 native | CIR1 (mutual, depth 1) generation |
| `owl:inverseOf` | OWL 2 native | RED2 and the "true inverse" branch of CON generation |
| `rdfs:subPropertyOf` (transitive, via `+`) | OWL 2 / RDFS native | RED1 generation |
| `owl:propertyDisjointWith` | OWL 2 native | TBox axioms consulted by the SHACL Gate's post-inference shapes; out of scope for this document's pre-inference generator (see Document 2bis) |
| `owl:maxCardinality` / `owl:maxQualifiedCardinality` | OWL 2 native | CAR generation |
| `:assertionSet` | `consistency-foundation.ttl` | target-graph binding (MATS vs OATS vs FATS) |
| `:generationalDepth` / `:generationalDirection` | `consistency-foundation.ttl` | generic CON generation (role conflict, cross-depth, cross-family) |
| `:disjointnessNature` | `consistency-foundation.ttl` | diagnostic message wording and severity, attached via RDF-star to specific `propertyDisjointWith` triples |

## 4. Retrieving the full assertion set inventory

The complete inventory of each assertion set — properties used as
predicates and classes used as `rdf:type` objects — is derived from a
single meta-query against `<urn:kinship:ontology>`. This meta-query is the
entry point of the generator. It reads this list once and its output drives
every downstream query family described in §5.

### Unified inventory meta-query

```sparql
SELECT ?r ?set ?kind WHERE {
    GRAPH <urn:kinship:ontology> {
        ?r kin:assertionSet ?set .
        BIND(
            IF(EXISTS { ?r a owl:Class },
               "class", "property")
            AS ?kind)
    }
}
ORDER BY ?set ?kind ?r
```

The `?kind` discriminant is derived from the OWL declaration of each
resource — no separate annotation is needed. Every IRI in
`kinship-consistency.ttl` that carries `kin:assertionSet` is either
declared `a owl:Class` (class assertion, governed as `rdf:type` object) or
`a owl:ObjectProperty` / `a owl:DatatypeProperty` (predicate assertion).

### Expected structure of results

```text
?set        ?kind       ?r
──────────  ──────────  ──────────────────────────────────────────
kin:FATS    class       kin:FemalePerson
kin:FATS    class       kin:MalePerson
kin:FATS    property    kin:hasAncestor
kin:FATS    property    kin:hasCeremonialBond
kin:FATS    property    kin:hasCollateralRelative
kin:FATS    property    kin:hasDescendant
kin:FATS    property    kin:hasInLawRelative
kin:FATS    property    kin:hasLineageRelative
kin:FATS    property    kin:hasNibling
kin:FATS    property    kin:hasRelative
kin:FATS    property    kin:hasStepRelative
kin:FATS    property    kin:hasUncleAunt
kin:FATS    property    kin:hasMother  ...  (all gendered properties)
kin:MATS    class       kin:Person
kin:MATS    property    kin:hasAdoptiveChild
kin:MATS    property    kin:hasAdoptiveParent
kin:MATS    property    kin:hasBloodChild
kin:MATS    property    kin:hasBloodParent
kin:MATS    property    kin:hasChild
kin:MATS    property    kin:hasCivilPartner
kin:MATS    property    kin:hasGender
kin:MATS    property    kin:hasGodchild
kin:MATS    property    kin:hasGodparent
kin:MATS    property    kin:hasLifePartner
kin:MATS    property    kin:hasParent
kin:MATS    property    kin:hasPartner
kin:MATS    property    kin:hasSpouse
kin:MATS    property    kin:hasTwin
kin:MATS    property    kin:hasWitness
kin:MATS    property    kin:hasWitnessed
kin:OATS    property    kin:hasChildInLaw
kin:OATS    property    kin:hasCousin ... (all OATS properties)
```

### How the generator uses this inventory

The `?kind` column drives which detection template is applied, and the
`?set` column drives both detection and routing — the inventory is the
single source that governs the complete lifecycle of an incoming triple:

| `?set` | `?kind` | Detection | Routing destination |
| --- | --- | --- | --- |
| `kin:FATS` | `property` | FATS rejection query | discard |
| `kin:FATS` | `class` | FATS rejection query | discard |
| `kin:MATS` | `property` | MATS Gate meta-queries | `<urn:kinship:asserted>` (A) |
| `kin:MATS` | `class` | — (class assertions not further validated) | `<urn:kinship:asserted>` (A) |
| `kin:OATS` | `property` | OATS Gate meta-queries | `<urn:kinship:oats>` (O) |

The routing queries generated from the inventory are executed by the
ingestion pipeline against `<urn:kinship:intake>` after the FATS rejection
pass. Each routing query moves triples from the intake graph to the
appropriate target graph.

**Routing to A — MATS triples:**

```sparql
INSERT {
    GRAPH <urn:kinship:asserted> { ?s ?p ?o }
}
WHERE {
    GRAPH <urn:kinship:intake> {
        ?s ?p ?o .
        {
            VALUES ?p { <substituted MATS properties> }
        }
        UNION
        {
            VALUES ?o { <substituted MATS classes> }
            FILTER(?p = rdf:type)
        }
    }
}
```

**Routing to O — OATS triples:**

```sparql
INSERT {
    GRAPH <urn:kinship:oats> { ?s ?p ?o }
}
WHERE {
    GRAPH <urn:kinship:intake> {
        ?s ?p ?o .
        {
            VALUES ?p { <substituted OATS properties> }
        }
        UNION
        {
            ## Class assertions routed to O.
            ## VALUES ?c { } is valid SPARQL 1.1 — produces zero bindings
            ## when the OATS class list is empty, making this branch a no-op.
            ## The branch structure is retained so that adding a class to
            ## kin:assertionSet kin:OATS in kinship-consistency.ttl
            ## immediately takes effect without modifying the query template.
            VALUES ?c { <substituted OATS classes, possibly empty> }
            FILTER(?p = rdf:type)
            ?s a ?c .
        }
    }
}
```

> **Empty VALUES robustness.** All routing and detection queries generated
> by this framework are designed to function correctly when any substituted
> `VALUES` list is empty. An empty list produces zero bindings for that
> branch, making it a no-op without invalidating the query. This ensures
> that adding a new class or property to any assertion set in
> `kinship-consistency.ttl` takes effect immediately at the next generator
> run, with no structural change to the query templates.

Both routing queries are generated from the same inventory result —
`VALUES` lists for MATS properties, MATS classes, OATS properties,
and OATS classes (empty for OATS classes when no OATS classes exist)
are substituted directly from the `?set`-filtered inventory results
(see per-set filtered queries above). No separate routing table is
maintained.

After the two routing inserts, `<urn:kinship:intake>` should contain only
FATS triples (already flagged by the rejection query) and any triple
whose predicate is not classified in the ontology. The latter case signals
a property absent from `kinship-consistency.ttl` — a maintenance gap to
be flagged rather than silently routed.

```sparql
## Unclassified triple detection — maintenance diagnostic
SELECT ?s ?p ?o WHERE {
    GRAPH <urn:kinship:intake> { ?s ?p ?o }
    FILTER NOT EXISTS {
        GRAPH <urn:kinship:ontology> {
            ?p kin:assertionSet ?any .
        }
    }
    FILTER(?p != rdf:type)   ## rdf:type handled via class assertionSet
}
```

### Per-set filtered queries

For gates that target a single set, the inventory query is filtered by
`?set`:

```sparql
## MATS properties only — used by MATS Gate meta-queries
SELECT ?r WHERE {
    GRAPH <urn:kinship:ontology> {
        ?r kin:assertionSet kin:MATS .
        FILTER NOT EXISTS { ?r a owl:Class }
    }
}

## FATS complete (properties + classes) — used by FATS Gate
SELECT ?r ?kind WHERE {
    GRAPH <urn:kinship:ontology> {
        ?r kin:assertionSet kin:FATS .
        BIND(IF(EXISTS { ?r a owl:Class }, "class", "property") AS ?kind)
    }
}

## OATS properties only — used by OATS Gate Layer B meta-queries
SELECT ?r WHERE {
    GRAPH <urn:kinship:ontology> {
        ?r kin:assertionSet kin:OATS .
        FILTER NOT EXISTS { ?r a owl:Class }
    }
}
```

Even though the OATS filter does not need to exclude classes (no class carries
`kin:assertionSet kin:OATS` in the current ontology, since no class assertion
is optional), the filter is still useful for consistency and future-proofing.

## 5. Generated query families

### 5.1 FATS — Forbidden assertion detection

The FATS gate query is derived directly from `kinship-consistency.ttl`:
every property and class annotated `kin:assertionSet kin:FATS` constitutes
the rejection list.

Generated detection query — runs against `<urn:kinship:intake>`, the
landing graph for all incoming triples.

```sparql
SELECT ?s ?p ?o WHERE {
    GRAPH <urn:kinship:intake> {
        {
            VALUES ?p { <substituted properties with assertionSet FATS> }
            ?s ?p ?o .
        }
        UNION
        {
            VALUES ?c { <substituted classes with assertionSet FATS> }
            ?s a ?c .
            BIND(rdf:type AS ?p) .
            BIND(?c AS ?o) .
        }
    }
}
```

### 5.2 IRR — Irreflexivity

Two OWL 2 characteristics are relevant to this family:
`owl:IrreflexiveProperty` and `owl:AsymmetricProperty`. Semantically, any
asymmetric property forbids reflexive instances in every valid model — but
this is a model-theoretic constraint, not a production rule. No OWL 2 RL
reasoner materializes an `owl:IrreflexiveProperty` triple from an
`owl:AsymmetricProperty` declaration; the standard OWL 2 RL asymmetry rule
(`prp-asyp`) only fires on actual data, flagging `P(x,y)` and `P(y,x)`
co-occurring as inconsistent — it produces no new TBox triple. This was
verified empirically against both rdflib (owl-rl) and GraphDB, neither of
which infers one characteristic from the other.

The equivalence used here — that both characteristics justify the same
downstream IRR check — is therefore encoded in the query generator itself,
not derived by any reasoner. The meta-query below requires no inference: it
reads both declarations as plainly asserted TBox triples and combines the
two candidate sets via UNION at the generator level.

Meta-query:

```sparql
SELECT ?p ?set WHERE {
    GRAPH <urn:kinship:ontology> {
        { ?p a owl:IrreflexiveProperty . }
        UNION
        { ?p a owl:AsymmetricProperty . }
        ?p kin:assertionSet ?set .
    }
}
```

Generated detection query, one per target graph, with the meta-query result
substituted into `VALUES`:

```sparql
SELECT ?x ?p WHERE {
    VALUES ?p { <substituted from meta-query, filtered by ?set> }
    GRAPH <target graph URI> { ?x ?p ?x . }
}
```

`hasDescendant` and `hasAncestor` are excluded from the `AsymmetricProperty`
branch — OWL 2 DL forbids declaring a transitive property asymmetric, since
asymmetry combined with transitivity over more than one step is
unsatisfiable for any property relating more than a single pair. They keep
their existing standalone `owl:IrreflexiveProperty` declaration instead,
picked up by the first branch of the UNION above.

### 5.3 RED1 — Duplicate sub/superproperty

Meta-query, using the transitive property-path operator so multi-level
hierarchies (e.g. `hasBloodChild → hasChild → hasRelative`) are covered
without enumerating each intermediate level:

```sparql
SELECT ?sub ?super WHERE {
    GRAPH <urn:kinship:ontology> {
        ?sub rdfs:subPropertyOf+ ?super .
        ?sub kin:assertionSet ?subSet .
        ?super kin:assertionSet ?superSet .
        FILTER(?subSet = ?superSet)
    }
}
```

The `FILTER(?subSet = ?superSet)` clause prevents the generator from
producing a cross-set pair (for instance, `hasTwin` MATS under `hasSibling`
OATS would otherwise be picked up as a spurious RED1 candidate — excluded
correctly here, since asserting `hasTwin` is never redundant with asserting
`hasSibling`, they capture different facts).

Generated detection query — identical shape to the hand-written version,
with the `(?sub, ?super)` pairs substituted:

```sparql
SELECT DISTINCT ?x ?y ?sub ?super WHERE {
    VALUES (?sub ?super) { <substituted pairs> }
    GRAPH <target graph URI> {
        ?x ?sub   ?y .
        ?x ?super ?y .
    }
}
```

### 5.4 RED2 — Duplicate inverse sub/super/property

Covers duplicate assertion of an inverse property and its inverse property,
inverse superproperty, or inverse subproperty — not only direct
`owl:inverseOf` pairs. A pair like `hasBloodChild`/`hasParent` belongs to
this family: `hasBloodChild owl:inverseOf hasBloodParent`, and
`hasBloodParent rdfs:subPropertyOf hasParent`, so asserting both
`hasBloodChild` and `hasParent` on the same pair is redundant even though
neither is the other's direct inverse.

Meta-query:

```sparql
SELECT DISTINCT ?p ?q WHERE {
    GRAPH <urn:kinship:ontology> {
        {
            ?p owl:inverseOf ?q .
        }
        UNION
        {
            ?p owl:inverseOf ?pInverse .
            { ?pInverse rdfs:subPropertyOf ?q } UNION { ?q rdfs:subPropertyOf ?pInverse }
            FILTER(?pInverse != ?q)
        }
        ?p kin:assertionSet ?set .
        ?q kin:assertionSet ?set .
        FILTER(STR(?p) < STR(?q))
    }
}
```

Generated query — identical shape to the hand-written version.

```sparql
SELECT DISTINCT ?x ?y ?p ?q WHERE {
    VALUES (?p ?q) { <substituted pairs> }
    GRAPH <target graph URI> {
        ?x ?p ?y .
        ?y ?q ?x .
    }
}
```

### 5.5 RED3 — Symmetric property both directions

Meta-query:

```sparql
SELECT ?p ?set WHERE {
    GRAPH <urn:kinship:ontology> {
        ?p a owl:SymmetricProperty ;
           kin:assertionSet ?set .
    }
}
```

Generated query — identical shape to the hand-written version.

```sparql
SELECT DISTINCT ?x ?y ?p WHERE {
    VALUES ?p { <substituted from meta-query, filtered by ?set> }
    GRAPH <target graph URI> {
        ?x ?p ?y .
        ?y ?p ?x .
        FILTER(STR(?x) < STR(?y))
    }
}
```

### 5.6 CON — Generic role and cross-depth conflict (unifies former CON1/CON2)

This is the family where ontology-driven generation produces something
richer than the hand-maintained catalog, not merely a mechanical
restatement of it.

Meta-query:

```sparql
SELECT ?asc ?desc ?nature WHERE {
    GRAPH <urn:kinship:ontology> {
        ?asc  kin:generationalDirection kin:Ascending  ;
              kin:generationalDepth ?ascDepth ;
              kin:assertionSet ?set .
        ?desc kin:generationalDirection kin:Descending ;
              kin:generationalDepth ?descDepth ;
              kin:assertionSet ?set .       ## ← même assertionSet imposé
        FILTER(?set != kin:FATS)
        BIND(
            IF(EXISTS { ?asc owl:inverseOf ?desc },
               kin:UniversalImpossibility, kin:LegalConvention)
            AS ?nature
        )
    }
}
```

Every pairing of an ascending property and a descending property is a
candidate conflict — regardless of whether they belong to the same family
(e.g. `hasGrandparent`/`hasGrandchild`) or different families (e.g.
`hasSiblingNibling`/`hasUncleAuntInLaw`). The nature is derived
automatically: if the pair is a true `owl:inverseOf` pair, the conflict is
a structural impossibility regardless of context; otherwise, it is
classified as a convention-level conflict, since the two properties reach
their generational position through different paths that could, in
sufficiently unusual family structures, both hold.

Generated detection query — a single query replaces the former MATS-CON2,
OATS-CON1, and OATS-CON2 patterns entirely:

```sparql
SELECT DISTINCT ?x ?y ?asc ?desc ?nature WHERE {
    VALUES (?asc ?desc ?nature) { <substituted triples> }
    GRAPH <target graph URI> {
        ?x ?asc  ?y .
        ?x ?desc ?y .
    }
}
```

**Cross-family detections discovered by this generalization.** The
hand-written catalog only tested role conflicts within matching families
(an inverse pair, or two properties of the same generational chain). The
generic rule additionally catches pairs the catalog never enumerated, for
example:

```turtle
:alice :hasSiblingNibling :carol .   # carol is 1 generation below alice
:alice :hasUncleAuntInLaw :carol .   # carol is 1 generation above alice
```

Both relate `alice` and `carol` with depth 1 but opposite direction — a
contradiction the generic rule flags automatically, classified
`LegalConvention` since `hasSiblingNibling` and `hasUncleAuntInLaw` are not
a true inverse pair. This and similar cross-family pairs (e.g.
`hasChildInLaw` vs `hasSiblingUncleAunt`, `hasStepChild` vs
`hasSiblingUncleAunt`) were not part of the original OATS-PAR catalog and
represent a genuine extension of detection coverage obtained directly from
adding the `:generationalDepth`/`:generationalDirection` metadata, with no
additional query-writing effort.

### 5.7 CIR1 — Mutual generational same-property assertion (depth 1)

Meta-query — `generationalDirection` presence (not value) is used as a
filter, not for its content: it excludes asymmetric properties with no
fixed generational position, such as the ceremonial group
(`hasGodparent`/`hasGodchild`/`hasWitness`/`hasWitnessed`), for which
mutual assertion is not a generational contradiction in the same sense it
is for filiation properties.

```sparql
SELECT ?p ?set WHERE {
    GRAPH <urn:kinship:ontology> {
        ?p a owl:AsymmetricProperty ;
           kin:assertionSet ?set ;
           kin:generationalDirection ?dir .
    }
}
```

Generated query — identical shape to the hand-written version. Each
asymmetric property is tested independently against its own mutual
assertion:

```sparql
SELECT DISTINCT ?x ?y ?p WHERE {
    VALUES ?p { <substituted from meta-query, filtered by ?set> }
    GRAPH <target graph URI> {
        ?x ?p ?y .
        ?y ?p ?x .
        FILTER(STR(?x) < STR(?y))
    }
}
```

### 5.8 CAR — Cardinality violations

Meta-query — retrieves the inverse property alongside the restriction,
via `OPTIONAL` since not every restricted property has one (`hasGender`
does not, as it relates `Person` to `GenderIdentity` rather than `Person`
to `Person`):

```sparql
SELECT ?prop ?inverse ?max ?onClass ?set WHERE {
    GRAPH <urn:kinship:ontology> {
        ?restriction a owl:Restriction ;
            owl:onProperty ?prop .
        { ?restriction owl:maxCardinality ?max }
        UNION
        { ?restriction owl:maxQualifiedCardinality ?max ;
                       owl:onClass ?onClass }
        OPTIONAL { ?prop owl:inverseOf ?inverse }
        ?prop kin:assertionSet ?set .
    }
}
```

`?prop` is always the property directly named by `owl:onProperty` in the
restriction — it defines the counting direction (e.g. "at most 2
`hasBloodParent`", not "at most 2 `hasBloodChild`"). `?inverse`, when
present, is only used to also capture assertions expressed in the opposite
direction (`:parent hasBloodChild :person` counting toward the same
restriction on `:person`). There is no ambiguity to resolve at generation
time — the restriction's own structure already fixes which property is
which.

Generated detection query — the target graph is derived from `?set` exactly
as for all other query families. The inverse branch of the `UNION` is
omitted when the meta-query result has no `?inverse` binding. The
`FILTER EXISTS` clause is omitted for unqualified cardinality restrictions.

In the current ontology, all cardinality restrictions are declared on MATS
properties (`hasBloodParent`, `hasGender`), so the target graph resolves to
`<urn:kinship:asserted>` in practice. Should a cardinality restriction be
added to an OATS property in the future, the generator produces the correct
query targeting `<urn:kinship:oats>` without modification — the
`:assertionSet` annotation on the property drives the substitution.

```sparql
SELECT ?c (COUNT(DISTINCT ?p) AS ?nb) WHERE {
    GRAPH <target graph URI> {    ## resolved from ?prop kin:assertionSet ?set
        { ?c <substituted prop> ?p . }
        UNION
        { ?p <substituted inverse> ?c . }   ## omitted if no inverse
        FILTER EXISTS { ?p a <substituted onClass> }   ## omitted if unqualified
    }
} GROUP BY ?c
HAVING (COUNT(DISTINCT ?p) > <substituted max>)
```

### 5.9 OATS Gate Layer A — partial generation

Layer A is not fully hand-written. Two of its three branches benefit from
ontology introspection.

**Branch 3 — cross-set disjointness (generated).**
The set of MATS properties declared `owl:propertyDisjointWith` an OATS
candidate is read directly from the TBox. This branch requires no
hard-coded property list:

```sparql
## Fragment of the generated Layer A query — Branch 3
GRAPH <urn:kinship:mats-closure> {
    ?s ?mats ?o .
    BIND(?mats AS ?existingRel)
    GRAPH <urn:kinship:ontology> {
        ?p owl:propertyDisjointWith ?mats .
        ?mats kin:assertionSet kin:MATS .
    }
}
```

**VALUES list — 17 OATS properties (generated).**
The candidate property list is derived from the `kin:assertionSet kin:OATS`
annotation on properties that are members of the three OATS structural
groups. The group label is preserved for diagnostic messages:

```sparql
SELECT ?p ?groupLabel WHERE {
    GRAPH <urn:kinship:ontology> {
        VALUES (?group ?groupLabel) {
            (kin:hasCollateralRelative "collateral")
            (kin:hasInLawRelative      "in-law")
            (kin:hasStepRelative       "step")
        }
        ?p rdfs:subPropertyOf ?group ;
           kin:assertionSet kin:OATS .
    }
}
```

**Branches 1 and 2 — architectural anchors (hand-written).**
`hasLineageRelative` and `hasPartner` are not derived from a mechanical
pattern — they are the direct expression of the MATS Primacy Principle
(Document 1). Any MATS-derived link under `hasLineageRelative` or any
`hasPartner` assertion represent a fully established kinship structure that
OATS cannot redefine. These two anchors remain fixed regardless of ontology
evolution.

**Branch 4 — cross-set generational direction conflict (generated).**
Produced by the meta-query described above (§… of this document — see cross-
set CON analysis). Reads the OATS candidate from O and the conflicting MATS
property from M, guided by `kin:generationalDirection` annotations.

## 5. What remains hand-written

Three parts of the catalog are not generated, by design.

**CIR2 — the 8-form generational cycle.** The combinatorial structure
(3 edges × 2 expression options per edge) is itself generalizable as an
algorithm parameterized by an `(ascending, descending)` property pair — the
generator does construct the 8-`UNION` query body programmatically from the
pair, the same way it is hand-built for the grandparent and great-grandparent
families in the existing catalog. What is not derived from the ontology is
*which* property pairs warrant this 3-node treatment: this is a judgment
call (only chains with meaningful multi-hop semantics, in practice the
direct generational families) rather than a mechanically extractable
ontology fact, and remains a short, explicit list maintained alongside the
generator configuration.

**Alternative for CIR2 — arbitrary-length cycle detection via graph
algorithm.** Rather than generating the 8-form combinatorial SPARQL query
for each (ascending, descending) property pair, an algorithmic alternative
extracts the relevant assertions as a directed graph and delegates cycle
detection to a graph library. This approach has no depth limit and produces
the actual edge sequence of each cycle, giving the user directly actionable
root-cause information (which specific triples to remove).

The properties to include in the extraction are derived from the same
ontology metadata as the CIR1 meta-query: `owl:AsymmetricProperty` with
`kin:generationalDirection` declared and `kin:assertionSet` matching the
target set (MATS or OATS). Direction normalization (converting
`hasBloodChild` assertions to the `hasBloodParent` edge direction) is driven
by the `kin:generationalDirection` annotation, eliminating the need to
enumerate the 2^N assertion forms that the 8-form SPARQL query covers.

Two levels of output:

- `simple_cycles()` — enumerates all distinct cycles; each result is an
  ordered list of nodes (the cycle path). Directly actionable for root-cause
  diagnosis.
- `strongly_connected_components()` (SCC) as a pre-filter — identifies node
  sets involved in cycles without enumerating them; limits `simple_cycles()`
  to cyclic subgraphs, reducing cost on larger datasets. Recommended above a
  few thousand individuals.

This alternative is not adopted as the default in the current
implementation, which retains the generated SPARQL CIR2 query for
consistency with the rest of the pipeline (all other detection steps are
pure SPARQL) and for auditability (the query is directly inspectable
without a Python dependency). The algorithmic approach is available as a
complement for exhaustive validation or root-cause diagnosis when the SPARQL
CIR2 query has already confirmed a cycle exists.

**Documented non-violations.** `hasChildInLaw`/`hasStepChild` and
`hasParentInLaw`/`hasStepParent` were analyzed and found not to be
systematic conflicts (see Document 2, OATS pattern catalog). No ontology
characteristic distinguishes this case from a genuine conflict — both pairs
share generational depth and opposite direction, which is exactly the
generic CON rule's trigger condition. Left unaddressed, the generic
generator would produce a false-positive query for these two pairs. The
implementation excludes them via an explicit suppression list, checked
against the generated `(ascending, descending)` candidate set before query
emission. This is the one place where the generator's output must be
post-filtered by a hand-maintained exception list rather than derived
purely from the TBox.

**SHACL Gate shapes.** The post-inference shapes consumed by the SHACL Gate
are not produced by this generator. They remain a separate, less mature
specification (Document 2bis) to be revisited.

## 6. Severity and target-graph binding

Every generated query inherits two pieces of information from the
meta-query result, without further hand annotation:

- **Target graph**: derived from `:assertionSet` — a query whose properties
  are all `:MATS` runs against `<urn:kinship:asserted>`; a query whose
  properties are all `:OATS` runs against `<urn:kinship:oats>`; a query
  spanning both sets (as in the cross-set CON detections) runs against the
  union of the two graphs.
- **Severity wording**: derived from `:disjointnessNature` when present, or
  defaulted to `UniversalImpossibility` for true inverse pairs and
  `LegalConvention` for the generic cross-family CON rule's non-inverse
  pairs, as described above.

This removes the need to hand-tag each generated query with a severity
level, which was previously a manual judgment call repeated once per
pattern in the catalog documents.

## 7. Relationship to the pipeline architecture

This generator changes how the queries within the MATS Gate's steps and
the OATS Layer A/B queries are produced. It does not change the pipeline's
structure, ordering, or graph isolation requirements established in
Document 1:

```text
FATS Gate    — :assertionSet = :FATS list, generated directly from kinship-consistency.ttl
MATS Gate    — IRR, RED1-3, CON (generic), CIR1, CIR2 (hybrid), CAR — generated, target <urn:kinship:asserted>
OATS Layer A — unchanged, the unified rule against hasLineageRelative/hasPartner closure (Document 1)
OATS Layer B — IRR, RED1-3, CON (generic), CIR1, CIR2 (hybrid) — generated, target <urn:kinship:oats>
```

The hand-maintained pattern catalog in Document 2 remains the authoritative
documentation of intent — it describes *why* each pattern matters and its
nature. The generator described here is the mechanism that keeps the
*executable* queries synchronized with the ontology as it evolves, reducing
the catalog's maintenance burden to the cases that genuinely require human
judgment: CIR2 scope selection and the documented non-violation exceptions.
