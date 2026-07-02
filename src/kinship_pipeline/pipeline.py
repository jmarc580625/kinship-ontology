"""
Consistency pipeline orchestrator.

Implements the V1D1/V1D2 pipeline:

    Intake
      → FATS Gate
      → MATS Gate
      → Materialization Step 1  (A → M)
      → OATS Layer A
      → OATS Layer B
      → Materialization Step 2  (A ∪ O → MO)

The pipeline is backend-agnostic and operates through the ``KinshipBackend``
interface.  It returns a structured report for each stage.
"""

from typing import Any, Dict

from .backends.base import KinshipBackend
from .gates.fats import FatsGate
from .gates.mats import MatsGate
from .gates.oats_layer_a import OatsLayerA
from .gates.oats_layer_b import OatsLayerB
from .materialization_engine import MaterializationEngine
from .query_generator import QueryGenerator


class ConsistencyPipeline:
    """Run the full kinship consistency pipeline."""

    def __init__(
        self,
        backend: KinshipBackend,
        query_generator: QueryGenerator,
        materialization_engine: MaterializationEngine,
    ) -> None:
        self.backend = backend
        self.query_generator = query_generator
        self.materialization_engine = materialization_engine
        self.fats_gate = FatsGate(backend)
        self.mats_gate = MatsGate(backend, query_generator)
        self.oats_layer_a = OatsLayerA(backend)
        self.oats_layer_b = OatsLayerB(backend, query_generator)

    def run(
        self,
        *,
        intake_graph: str = "urn:kinship:intake",
        asserted_graph: str = "urn:kinship:asserted",
        oats_graph: str = "urn:kinship:oats",
        mats_closure_graph: str = "urn:kinship:mats-closure",
        full_graph: str = "urn:kinship:full",
        reason_after_each: bool = False,
    ) -> Dict[str, Any]:
        """Execute the pipeline and return a report."""
        report: Dict[str, Any] = {
            "status": "ok",
            "stages": {},
        }

        # 1. FATS Gate
        fats_report = self.fats_gate.run(intake_graph, asserted_graph, oats_graph)
        report["stages"]["FATS"] = fats_report
        if fats_report.get("status") != "ok":
            report["status"] = "warning"

        # 2. MATS Gate
        mats_report = self.mats_gate.run(asserted_graph)
        report["stages"]["MATS"] = mats_report
        if mats_report.get("status") != "ok":
            report["status"] = "violation"

        # 3. Materialization Step 1: A → M
        mats_scripts = self.materialization_engine.step1(
            source_graph=asserted_graph,
            target_graph=mats_closure_graph,
            reason_after_each=reason_after_each,
        )
        report["stages"]["MATS_MATERIALIZATION"] = {
            "status": "ok",
            "scripts": len(mats_scripts),
            "details": mats_scripts,
        }

        # 4. OATS Layer A
        layer_a = self.oats_layer_a.run(oats_graph, mats_closure_graph)
        report["stages"]["OATS_LAYER_A"] = layer_a
        if layer_a.get("status") != "ok":
            report["status"] = "violation"

        # 5. OATS Layer B
        layer_b = self.oats_layer_b.run(oats_graph)
        report["stages"]["OATS_LAYER_B"] = layer_b
        if layer_b.get("status") != "ok":
            report["status"] = "violation"

        # 6. Materialization Step 2: A ∪ O → MO
        full_scripts = self.materialization_engine.step2(
            asserted_graph=asserted_graph,
            oats_graph=oats_graph,
            target_graph=full_graph,
            reason_after_each=reason_after_each,
        )
        report["stages"]["FULL_MATERIALIZATION"] = {
            "status": "ok",
            "scripts": len(full_scripts),
            "details": full_scripts,
        }

        return report
