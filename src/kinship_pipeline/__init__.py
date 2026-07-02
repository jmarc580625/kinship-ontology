"""
Kinship consistency-control pipeline.

This package implements the multi-stage validation pipeline described in
Volume 1 of the kinship ontology documentation (V1D0–V1D4).

Pipeline stages:
    1. FATS Gate   – classify and route incoming assertions.
    2. MATS Gate   – validate minimal assertions (IRR, CON, CIR, CAR, RED, TWI, PAR).
    3. Materialization Step 1 – compute closure of validated MATS assertions.
    4. OATS Layer A – validate OATS assertions against the MATS closure.
    5. OATS Layer B – validate internal OATS consistency.
    6. Materialization Step 2 – compute full working graph.
    7. SHACL Gate  – optional post-materialization safety net (ignored in this phase).

The pipeline is backend-agnostic: it runs on both RDFLib (in-memory) and
GraphDB (remote OWL-RL reasoning) via the backend abstraction layer.
"""

__version__ = "0.1.0"

from .pipeline import ConsistencyPipeline
from .query_generator import QueryGenerator
from .materialization_engine import MaterializationEngine

__all__ = ["ConsistencyPipeline", "QueryGenerator", "MaterializationEngine"]
