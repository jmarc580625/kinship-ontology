# Kinship Ontology

An OWL 2 ontology for modelling kinship relationships — biological, social, and gendered — with a modular, test-driven architecture built on RDF/SPARQL.

## Overview

The ontology is organised as a set of composable **Turtle modules** under `ontology/kinship/`, layered from abstract foundations to concrete gendered and social roles:

| Layer | Modules |
| --- | --- |
| **Foundations** | `foundation`, `gender-foundation`, `lineage-foundation`, `materialization-foundation`, `temporal-foundation` |
| **Neutral core** | `core-neutral`, `anchored-neutral`, `extended-neutral`, `blended-neutral`, `allied-neutral` |
| **Specialisations** | `gendered`, `social`, `kinship-events` |
| **Integrity** | `shapes` (SHACL constraints) |
| **Entry point** | `kinship` (imports all modules) |

## Project structure

```text
ontology/kinship/   # OWL 2 / Turtle modules
src/kinship_pipeline/ # V1D1–V1D4 consistency-control pipeline
  backends/         # RDFLib / GraphDB backend abstraction
  gates/            # FATS, MATS, OATS Layer A/B gates
  query_generator.py
  materialization_engine.py
  pipeline.py
tests/
  backends/         # rdflib (in-memory) and GraphDB backends
  data/             # ABox test data (.ttl)
  definitions/      # Data-driven test definitions (.json)
  lib/              # Test framework utilities
  pipeline/         # Pipeline integration tests
  test_runner.py    # Module-aligned test runner
doc/                # Design documentation
```

## Getting started

### Prerequisites

- Python 3.10+
- (Optional) Docker, for the GraphDB backend

### Installation

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Running the tests

```bash
# Run all modules
python tests/test_runner.py --all --verbose

# Run a single module
python tests/test_runner.py --module core-neutral --verbose

# Cumulative run up to a module
python tests/test_runner.py --upto blended-neutral --verbose

# Use the GraphDB backend (requires Docker)
docker compose up -d
python tests/test_runner.py --all --backend graphdb
```

See `python tests/test_runner.py -h` for all options.

## Consistency pipeline

The `src/kinship_pipeline/` package implements the V1D1–V1D4 consistency-control pipeline:

```text
Intake → FATS Gate → MATS Gate → Materialization Step 1 → OATS Layer A
       → OATS Layer B → Materialization Step 2
```

Run the pipeline integration tests:

```bash
python -m unittest tests.pipeline.test_pipeline -v
```

Use the pipeline programmatically:

```python
import sys
sys.path.insert(0, "src")
from kinship_pipeline.backends import RDFLibKinshipBackend
from kinship_pipeline.query_generator import QueryGenerator
from kinship_pipeline.materialization_engine import MaterializationEngine
from kinship_pipeline.pipeline import ConsistencyPipeline

backend = RDFLibKinshipBackend(
    ontology_files=[
        "ontology/kinship/foundation.ttl",
        "ontology/kinship/core-neutral.ttl",
        "ontology/kinship/kinship-consistency.ttl",
        # ... other modules as needed
    ],
    shacl_shapes="ontology/kinship/kinship-shapes.ttl",
    data_files=["tests/data/core-data.ttl"],
)
backend.initialize()

pipeline = ConsistencyPipeline(
    backend,
    QueryGenerator(backend),
    MaterializationEngine(backend),
)
report = pipeline.run()
print(report["status"])  # "ok" or "violation"
```

## Documentation

- [Kinship relationships](doc/kinship-relationships.md)
- [Relationships consistency](doc/kinship-relationships-consistency.md)
- [Kinship events](doc/kinship-events.md)
- [Consistency control pipeline architecture](doc/V1D1-ConsistencyControl–-GatesPipelineArchitecture.md)
- [Gate pipelines and pattern catalogs](doc/V1D2-GatePipelinesAndPatternCatalogs.md)
- [Ontology-driven query generation](doc/V1D3-OntologyDrivenQueryGeneration.md)
- [Implementation paths](doc/V1D4-ImplementationPaths.md)

## License

This project is licensed under the [MIT License](LICENSE).
