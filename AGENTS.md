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
Intake → FATS Gate → MATS Gate → Materialization Step 1 → OATS Layer A
       → OATS Layer B → Materialization Step 2
```

Named graphs:

- `urn:kinship:intake` — incoming assertions
- `urn:kinship:asserted` — MATS assertions
- `urn:kinship:oats` — OATS assertions
- `urn:kinship:ontology` — TBox
- `urn:kinship:mats-closure` — A → M
- `urn:kinship:full` — A ∪ O → MO

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
