# Volume 1: Consistency Control — Document 0: Consistency Control Strategy and Architecture

## 1. Overview and Purpose

This document defines a comprehensive strategy for identifying and catching errors that would break the consistency of family relationship data sets in the context of the kinship ontology.

The kinship ontology is an attempt to express kinship western culture family relationships in its full complexity.

Its purpose is to provide a formal representation of these relationships that can be used for reasoning and inference. The kinship ontology includes a few class definitions and a rich set of around 80 properties definitions to express the full richness of family relationships.

To manage the high complexity of controlling consistency across such a vast axiom space, this strategy avoids treating constraints as a long, flat list. Instead, it establishes a framework that classifies every ontology property according to its role in the data lifecycle, segregating them into three distinct Assertion Type Sets.

---

## 2. Kinship Assertion Type Sets

### 2.1 MATS — Minimal Assertion Type Set

For most users, a rich set of 80 axioms would be hard to master and opens up the possibility for many errors especially while describing large family networks. To mitigate this, the Minimal Assertion Type Set (MATS) defines a core subset sufficient to describe a family tree of any size and infer its full kinship network:

* **Person declaration** (class assignment)
* **Gender assignment**
  * `hasGender`
* **Nuclear family relationships between persons**
  * *Partnership:* `hasPartner`, `hasSpouse`, `hasCivilPartner`, `hasLifePartner`
  * *Filiation:* `hasParent`, `hasBloodParent`, `hasAdoptiveParent`, `hasChild`, `hasBloodChild`, `hasAdoptiveChild`
  * *Twinship:* `hasTwin`
  * *Ceremonial:* `hasGodparent`, `hasGodchild`, `hasWitness`, `hasWitnessed`

All other family relationships are systematically derivable from this core through OWL inference and SPARQL materialization.

### 2.2 OATS — Optional Assertion Type Set

Relationships normally inferred from MATS may nonetheless need to be asserted directly under specific exceptional contexts:

* When missing data prevents reconstructing the full MATS chain (e.g., for a sparse network with many individuals and few connections).
* When entering the complete nuclear chain would be disproportionate for a collateral or distant branch of the family tree.

These assertions represent intentional approximations rather than errors; their existence is precisely justified when they are not derivable. The OATS set is structurally organized into four distinct groups mirroring their respective abstract superproperties:

| Group | Superproperty | Members |
| --- | --- | --- |
| **Collateral** | `hasCollateralRelative` | `hasSibling`, `hasHalfSibling`, `hasCousin`, `hasSiblingNibling`, `hasSiblingUncleAunt`, `hasGrandparent`, `hasGrandchild`, `hasGreatGrandparent`, `hasGreatGrandchild` |
| **In-law** | `hasInLawRelative` | `hasChildInLaw`, `hasParentInLaw`, `hasSiblingInLaw`, `hasNiblingInLaw`, `hasUncleAuntInLaw` |
| **Step** | `hasStepRelative` | `hasStepChild`, `hasStepParent`, `hasStepSibling` |

### 2.3 FATS — Forbidden Assertion Type Set

To prevent data redundancy and maintain a clean separation between asserted and inferred structures, certain assertion types must never appear in the input graph under any circumstances:

| Category | Properties / Classes | Reason |
| --- | --- | --- |
| **Derived classes** | `MalePerson`, `FemalePerson` | Inferred via the GCI pattern from `hasGender`. Direct assertion bypasses the gender firewall. |
| **Abstract superproperties** | `hasRelative`, `hasLineageRelative`, `hasCeremonialBond`, `hasCollateralRelative`, `hasInLawRelative`, `hasStepRelative` | Always subsumed by a more specific property; their position in the hierarchy is the documentation. Asserting them directly adds no information and loses precision. |
| **Transitive closures** | `hasDescendant`, `hasAncestor` | Must be materialized, never asserted directly. |
| **Properties ambiguous by construction** | `hasNibling`, `hasUncleAunt` | Direct assertion erases the structural distinction between blood and alliance. |
| **Gendered properties** | All of them (`hasMother`, `hasWife`, `hasBrother`...) | Direct consequence of the gender firewall. Best practice is to decompose into a neutral property + a gender assertion. |

---

## 3. The Three Validation Gates Framework

The lifecycle of data validation is mapped directly to the assertion sets. The framework derives a validation strategy executed as three successive chronological gates, moving from the simplest validation to the most complex:

```text
FATS Gate  →  MATS Gate  →  OATS Gate
```

### 3.1 FATS Gate

* **Criterion:** No assertion must belong to FATS.
* **Benefit:** Immediately reduces the inconsistency risk surface, as FATS represents roughly 50 of the 80 total properties.

### 3.2 MATS Gate

* **Criterion:** MATS assertions must be internally consistent.
* **Benefit:** The small number of assertion types (about 15) makes exhaustive detection achievable. MATS inconsistencies are the root causes of most downstream issues.

### 3.3 OATS Gate

* **Criterion:** OATS assertions must not contradict the already-validated MATS graph, nor contradict each other.
* **Benefit:** Covers ~17 OATS properties without requiring a manual catalogue of every single potential property combination.

The OATS gate is split into two operational layers:

1. **Layer A — OATS vs MATS:** Enforces that no OATS assertion in the collateral, in-law, or step groups may connect two persons already linked by `hasLineageRelative`, `hasPartner`, or any MATS property declared `owl:propertyDisjointWith` that specific OATS property.
2. **Layer B — OATS vs OATS:** Validates conflicts between distinct OATS assertions that involve no pre-existing MATS links.

---

## 4. Detection Architecture and Execution Pipeline

### 4.1 Inconsistency Identification Principles

Triplestores do not naturally treat OWL/RDFS constraints as integrity constraints, but as semantic rules intended for inference. To achieve explicit violation detection, an hybrid SPARQL-SHACL approach is implemented:

1. **SPARQL Queries:** Authoritative detection path executing directly on asserted triples without relying on inference, covering subproperty variants via `VALUES` clauses.
2. **SHACL Validation:** Secondary layer providing standardized consistency reporting, rich diagnostic explainability, and structural error catching on materialized, inferred triples.

## 5. Next Steps: Architectural Enforcement

With the core strategy, validation sets (MATS, OATS, FATS), and gate-ordering rationale defined, the immediate operational requirement is to enforce structural boundaries that prevent data contamination during checking.

To explore how these boundaries are mathematically defined and isolated within the storage layer, proceed to **Document 1: Named Graphs Strategy**, which establishes the named graph architecture governing the data lifecycle.

## 6. Corpus Architecture and Roadmap

This document establishes the overarching strategic vision and classification criteria for consistency control. To bridge the gap between this high-level rationale and its concrete execution, the remaining corpus is organized into specialized modules:

* **Document 1: Named Graphs Strategy**
    Details the formal isolation boundaries ($A$, $O$, $M$, $MO$) and structural invariants required to execute validation rules without cross-contamination.
* **Document 2: The Validation Gate Pipelines & Pattern Catalogs**
    Examines the sequential execution of the validation gates (FATS, MATS, OATS) and lists the hand-maintained SPARQL pattern catalogs, internal query ordering, and computational complexities.
* **Document 3: Ontology-Driven Query Generation**
    Describes the meta-modeling framework used to dynamically generate validation queries directly from the TBox axioms, automating long-term catalog maintenance.
* **Document 4: Specification and Implementation Paths**
    Focuses on the low-level technical deployment across targeted triplestores (`rdflib` and `GraphDB`), addressing transactional atomicity and programmatic graph evaluations.
