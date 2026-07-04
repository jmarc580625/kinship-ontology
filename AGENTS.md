# Kinship Ontology — Project Notes

## Environment

- Windows 11 / PowerShell (MSYS-like shell)
- Python virtual environment: `venv/Scripts/python.exe`

## Dependencies

```bash
pip install -r requirements.txt
```

## Running tests

```bash
# Single module
venv/Scripts/python.exe tests/test_runner.py --module core-neutral --verbose

# All modules
venv/Scripts/python.exe tests/test_runner.py --all --verbose

# GraphDB backend (requires Docker)
docker compose up -d
venv/Scripts/python.exe tests/test_runner.py --all --backend graphdb
```

## Current test status

- 163 tests pass, 0 fail, 12 errors.
- The 12 errors are from the SHACL-based NMA suites (`nma-consistency`, `nma-consistency-clean`).
- SHACL is intentionally out of scope for the current implementation plan.

## Pipeline package

- Source: `src/kinship_pipeline/`
- Installable via `pip install -e .` (uses `pyproject.toml`).
- Tests: `tests/pipeline/test_pipeline.py`
- Run tests: `python -m unittest tests.pipeline.test_pipeline -v`

## Pipeline architecture

```text
Intake → FATS Gate → Stash OATS → MATS Gate → Enable inference
       → Materialization Step 1 → Disable inference → Restore OATS
       → OATS Layer A → OATS Layer B → Enable inference
       → Materialization Step 2
```

### Inference control

The pipeline guarantees that the MATS closure `M` is derived **only from the
asserted graph `A`** (plus the ontology), never from OATS.  This is necessary
because GraphDB stores all inferred triples in the default graph and GraphDB's
default graph unions all named graphs; OATS assertions that were present
would otherwise silently influence the MATS closure.

To enforce this, both backends implement `disable_inference()` and
`enable_inference()`:

- **RDFLib**: `disable_inference()` sets a flag that makes `trigger_reasoning()`
  a no-op; `enable_inference()` clears the flag and runs OWL-RL over the whole
  dataset.  RDFLib stores inferred triples inside the target named graph.
- **GraphDB**: `disable_inference()` switches the active ruleset to `empty`;
  `enable_inference()` switches back to the configured ruleset (`owl2-rl`) and
  calls `sys:reinfer`.  GraphDB stores inferred triples in the default graph.

`initialize()` creates the store and then immediately disables inference before
loading the ontology or intake data.  The pipeline is the only caller of
`enable_inference()`:

1. After MATS gate and before Materialization Step 1 — to derive `M` from `A`.
2. After OATS Layer B and before Materialization Step 2 — to derive `MO` from
   `A ∪ O`.

Between the two phases, inference is disabled again so that restoring OATS
after Step 1 cannot alter `M`.

### Named graph scoping

- `urn:kinship:intake` — incoming assertions
- `urn:kinship:asserted` — MATS assertions
- `urn:kinship:oats` — OATS assertions
- `urn:kinship:ontology` — TBox
- `urn:kinship:mats-closure` — A → M
- `urn:kinship:full` — A ∪ O → MO

Because GraphDB puts inferences in the default graph, materialization WHERE
clauses must be unscoped for GraphDB (`scope_where_to_graph = False`) and
GRAPH-scoped for RDFLib (`scope_where_to_graph = True`).  The OATS stash/restore
sequence is the higher-level isolation mechanism that works for both backends.

## Key files

- `tests/test_runner.py` — data-driven test runner.
- `tests/lib/materialization_manager.py` — reference materialization engine.
- `tests/pipeline/test_pipeline.py` — pipeline integration tests.
- `ontology/kinship/kinship-consistency.ttl` — assertion-set classification (FATS/MATS/OATS).
- `doc/V1D1-ConsistencyControl–-GatesPipelineArchitecture.md` — named-graph pipeline architecture.
- `doc/V1D2-GatePipelinesAndPatternCatalogs.md` — validation pattern catalog.
- `doc/V1D3-OntologyDrivenQueryGeneration.md` — query generator specification.
- `doc/V1D4-ImplementationPaths.md` — backend-specific notes.

## Known design decisions

- `hasTwin` belongs to **MATS**.
- SHACL Gate is ignored in the current plan.
- Q-POST-CAR expected results were corrected to only include the explicitly dual-gender individual `:con3_x1`.
- RDF-star annotations in `kinship-consistency.ttl` are stripped by the RDFLib backend; the plain equivalent triples are used.
- The FATS gate ignores non-kinship predicates (e.g. `rdf:type`) rather than classifying them as FATS.
- The MATS gate can run slowly on the PAR-2 query for large datasets; the control-data test runs in ~70 seconds.
