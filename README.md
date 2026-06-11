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
tests/
  backends/         # rdflib (in-memory) and GraphDB backends
  data/             # ABox test data (.ttl)
  definitions/      # Data-driven test definitions (.json)
  lib/              # Test framework utilities
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

## Documentation

- [Kinship relationships](doc/kinship-relationships.md)
- [Relationships consistency](doc/kinship-relationships-consistency.md)
- [Kinship events](doc/kinship-events.md)

## License

This project is licensed under the [MIT License](LICENSE).
