"""Data-driven pipeline tests.

This module is a thin unittest adapter over the scenario-based pipeline runner.
All actual test logic lives in the scenario JSON files under scenarios/ and is
evaluated by pipeline_scenario_runner.run_all_scenarios().

Adding a new test case requires only a new JSON file in scenarios/ -- no Python
changes needed.
"""

import sys
import unittest
from pathlib import Path

import requests

# Make the pipeline packages importable.
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
TESTS_PIPELINE = Path(__file__).resolve().parent

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(TESTS_PIPELINE) not in sys.path:
    sys.path.insert(0, str(TESTS_PIPELINE))

from pipeline_scenario_runner import run_all_scenarios  # noqa: E402


class PipelineScenarioTest(unittest.TestCase):
    """Run all pipeline scenario files with the rdflib backend."""

    def test_all_scenarios_rdflib(self):
        failures = run_all_scenarios(backend_name="rdflib")
        self.assertEqual(failures, 0, f"{failures} scenario expectation(s) failed")


def _graphdb_available(url: str = "http://localhost:7200") -> bool:
    try:
        response = requests.get(f"{url}/rest/repositories", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


@unittest.skipUnless(_graphdb_available(), "GraphDB not reachable at http://localhost:7200")
class GraphDBPipelineScenarioTest(unittest.TestCase):
    """Run all pipeline scenario files with the GraphDB backend."""

    def test_all_scenarios_graphdb(self):
        failures = run_all_scenarios(backend_name="graphdb")
        self.assertEqual(failures, 0, f"{failures} scenario expectation(s) failed")


if __name__ == "__main__":
    unittest.main()
