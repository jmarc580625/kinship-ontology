"""Tests for the kinship consistency pipeline."""

import sys
import unittest
from pathlib import Path

import requests

# Make the pipeline package importable.
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kinship_pipeline.backends import GraphDBKinshipBackend, RDFLibKinshipBackend
from kinship_pipeline.materialization_engine import MaterializationEngine
from kinship_pipeline.pipeline import ConsistencyPipeline
from kinship_pipeline.query_generator import QueryGenerator


ONTOLOGY_FILES = [
    "ontology/kinship/materialization-foundation.ttl",
    "ontology/kinship/gender-foundation.ttl",
    "ontology/kinship/lineage-foundation.ttl",
    "ontology/kinship/foundation.ttl",
    "ontology/kinship/core-neutral.ttl",
    "ontology/kinship/kinship-consistency.ttl",
]


def _resolve(path: str) -> Path:
    return REPO_ROOT / path


class PipelineIntegrationTest(unittest.TestCase):
    """End-to-end pipeline test on the consistency-control dataset."""

    @classmethod
    def setUpClass(cls):
        cls.backend = RDFLibKinshipBackend(
            ontology_files=[_resolve(p) for p in ONTOLOGY_FILES]
        )
        cls.backend.initialize()
        cls.backend.load_data(
            _resolve("tests/data/consistency-control-data.ttl"),
            graph="urn:kinship:intake",
        )
        cls.query_generator = QueryGenerator(cls.backend)
        cls.materialization_engine = MaterializationEngine(cls.backend)
        cls.pipeline = ConsistencyPipeline(
            cls.backend, cls.query_generator, cls.materialization_engine
        )
        cls.report = cls.pipeline.run()

    @classmethod
    def tearDownClass(cls):
        cls.backend.cleanup()

    def test_fats_gate_routes_mats_only(self):
        """FATS gate classifies kinship assertions and keeps metadata."""
        fats = self.report["stages"]["FATS"]
        self.assertEqual(fats["status"], "ok")
        self.assertEqual(fats["fats_rejected"], 0)
        self.assertEqual(len(fats["fats_property_triples"]), 0)
        self.assertEqual(len(fats["fats_class_triples"]), 0)
        self.assertEqual(fats["unclassified_rejected"], 0)
        self.assertEqual(len(fats["unclassified_triples"]), 0)
        self.assertEqual(fats["oats_count"], 0)
        self.assertGreater(fats["mats_count"], 0)

    def test_mats_gate_detects_violations(self):
        """MATS gate finds all expected violations in the control dataset."""
        self.assertEqual(self.report["status"], "violation")
        mats = self.report["stages"]["MATS"]
        self.assertEqual(mats["status"], "violation")
        violations = mats["violations"]
        self.assertGreater(len(violations), 0)
        # Each violation entry must have full triples list, not just a sample
        for v in violations:
            self.assertIn("triples", v)
            self.assertIsInstance(v["triples"], list)
            self.assertEqual(v["count"], len(v["triples"]))

    def test_materialization_creates_mats_closure(self):
        """MATS materialization produces a non-empty closure graph."""
        self.assertGreater(
            self.backend.graph_size("urn:kinship:mats-closure"),
            self.backend.graph_size("urn:kinship:asserted"),
        )

    def test_oats_layers_pass_for_control_data(self):
        """OATS layers have no violations for a MATS-only control dataset."""
        layer_a = self.report["stages"]["OATS_LAYER_A"]
        layer_b = self.report["stages"]["OATS_LAYER_B"]
        self.assertEqual(layer_a["status"], "ok")
        self.assertEqual(layer_a["count"], 0)
        self.assertEqual(layer_b["status"], "ok")
        self.assertEqual(len(layer_b["violations"]), 0)




def _graphdb_available(url: str = "http://localhost:7200") -> bool:
    try:
        response = requests.get(f"{url}/rest/repositories", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


@unittest.skipUnless(_graphdb_available(), "GraphDB not reachable at http://localhost:7200")
class GraphDBPipelineIntegrationTest(unittest.TestCase):
    """End-to-end pipeline test on GraphDB using the consistency-control dataset."""

    @classmethod
    def setUpClass(cls):
        cls.backend = GraphDBKinshipBackend(
            ontology_files=[_resolve(p) for p in ONTOLOGY_FILES],
            repository_id="kinship-pipeline-graphdb-test",
        )
        cls.backend.initialize()
        cls.backend.load_data(
            _resolve("tests/data/consistency-control-data.ttl"),
            graph="urn:kinship:intake",
        )
        cls.query_generator = QueryGenerator(cls.backend)
        cls.materialization_engine = MaterializationEngine(cls.backend)
        cls.pipeline = ConsistencyPipeline(
            cls.backend, cls.query_generator, cls.materialization_engine
        )
        cls.report = cls.pipeline.run()

    @classmethod
    def tearDownClass(cls):
        cls.backend.cleanup()

    def test_fats_gate_routes_mats_only(self):
        fats = self.report["stages"]["FATS"]
        self.assertEqual(fats["status"], "ok")
        self.assertEqual(fats["fats_rejected"], 0)
        self.assertEqual(len(fats["fats_property_triples"]), 0)
        self.assertEqual(len(fats["fats_class_triples"]), 0)
        self.assertEqual(fats["unclassified_rejected"], 0)
        self.assertEqual(len(fats["unclassified_triples"]), 0)
        self.assertEqual(fats["oats_count"], 0)
        self.assertGreater(fats["mats_count"], 0)

    def test_mats_gate_detects_violations(self):
        self.assertEqual(self.report["status"], "violation")
        mats = self.report["stages"]["MATS"]
        self.assertEqual(mats["status"], "violation")
        violations = mats["violations"]
        self.assertGreater(len(violations), 0)
        for v in violations:
            self.assertIn("triples", v)
            self.assertEqual(v["count"], len(v["triples"]))

    def test_materialization_creates_mats_closure(self):
        self.assertGreater(
            self.backend.graph_size("urn:kinship:mats-closure"),
            self.backend.graph_size("urn:kinship:asserted"),
        )

    def test_oats_layers_pass_for_control_data(self):
        layer_a = self.report["stages"]["OATS_LAYER_A"]
        layer_b = self.report["stages"]["OATS_LAYER_B"]
        self.assertEqual(layer_a["status"], "ok")
        self.assertEqual(layer_a["count"], 0)
        self.assertEqual(layer_b["status"], "ok")
        self.assertEqual(len(layer_b["violations"]), 0)


if __name__ == "__main__":
    unittest.main()
