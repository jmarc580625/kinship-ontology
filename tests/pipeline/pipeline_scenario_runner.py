"""
pipeline_scenario_runner.py
---------------------------
Data-driven test runner for the kinship consistency pipeline.

Each scenario is a self-contained JSON file under tests/pipeline/scenarios/.
The runner loads the scenario, builds the backend, calls pipeline.run(), then
compares each reported stage against the declared expectations.

Comparison semantics
--------------------
For every key declared inside an expected stage block:

  status                 exact string match ("ok", "warning", "violation",
                         "blocked", "skipped")
  mats_count             exact integer match
  oats_count             exact integer match
  fats_rejected          exact integer match
  unclassified_rejected  exact integer match
  mats_count_min         actual >= N
  oats_count_min         actual >= N
  fats_property_triples  [] -> must be empty  |  [...] -> order-insensitive match
  fats_class_triples     same
  unclassified_triples   same
  violations             {} -> list must be empty
                         {"Q-IRR": {"count": N}} -> query present with that count
                         {"Q-IRR": {"count": N, "triples": [...]}} -> + row match
  warnings               same as violations

Absent keys in expected -> field not checked.
Absent stage key in expected -> stage not checked at all.

CLI usage
---------
  python tests/pipeline/pipeline_scenario_runner.py --all
  python tests/pipeline/pipeline_scenario_runner.py --scenario pipeline-mats-violations
  python tests/pipeline/pipeline_scenario_runner.py --all --backend graphdb
  python tests/pipeline/pipeline_scenario_runner.py --list
"""

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------

_PIPELINE_DIR = Path(__file__).resolve().parent
_TESTS_DIR    = _PIPELINE_DIR.parent
_PROJECT_ROOT = _TESTS_DIR.parent
_SRC_DIR      = _PROJECT_ROOT / "src"
_SCENARIOS_DIR = _PIPELINE_DIR / "scenarios"
_ONTOLOGY_DIR  = _PROJECT_ROOT / "ontology" / "kinship"

if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

_KINSHIP_NS = "http://example.org/kinship#"

# Well-known namespace abbreviations used in scenario files.
_NS_ABBREV = {
    "http://example.org/kinship#":                       ":",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#":      "rdf:",
    "http://www.w3.org/2002/07/owl#":                   "owl:",
    "http://www.w3.org/2000/01/rdf-schema#":            "rdfs:",
    "http://www.w3.org/2001/XMLSchema#":                "xsd:",
}

# Default root ontology for the consistency pipeline.
# All dependent modules are resolved automatically via owl:imports DFS.
_DEFAULT_ROOT_ONTOLOGY = "ontology/kinship/kinship-consistency.ttl"


def _resolve_ontology_chain(root_file: Path) -> List[Path]:
    """Resolve the owl:imports chain depth-first from *root_file*."""
    from lib.ontology_loader import load_chain_for
    return load_chain_for(root_file, _ONTOLOGY_DIR)

# ---------------------------------------------------------------------------
# Result normalisation (mirrors test_runner.py)
# ---------------------------------------------------------------------------

def _norm(v: Any) -> Any:
    """Abbreviate well-known URIs using the namespace table above."""
    if isinstance(v, str):
        for ns, prefix in _NS_ABBREV.items():
            if v.startswith(ns):
                return prefix + v[len(ns):]
    if isinstance(v, list):
        return [_norm(i) for i in v]
    return v


def _norm_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: _norm(v) for k, v in row.items()}


def _rows_match(actual: List[Dict], expected: List[Dict]) -> bool:
    """Order-insensitive comparison of SPARQL result rows."""
    def _key(r: Dict) -> tuple:
        return tuple(sorted(r.items()))
    return sorted(_key(r) for r in actual) == sorted(_key(r) for r in expected)


# ---------------------------------------------------------------------------
# Stage comparison helpers
# ---------------------------------------------------------------------------

def _check_scalar(label: str, actual: Any, expected: Any) -> Optional[str]:
    """Return an error string or None."""
    if actual != expected:
        return f"{label}: expected {expected!r}, got {actual!r}"
    return None


def _check_triples(label: str,
                   actual_list: List[Dict],
                   expected_list: List[Dict]) -> Optional[str]:
    if expected_list == []:
        if actual_list:
            return f"{label}: expected empty, got {len(actual_list)} row(s)"
        return None
    normed = [_norm_row(r) for r in actual_list]
    if not _rows_match(normed, expected_list):
        exp_set = {tuple(sorted(r.items())) for r in expected_list}
        act_set = {tuple(sorted(r.items())) for r in normed}
        missing  = [dict(r) for r in exp_set - act_set]
        spurious = [dict(r) for r in act_set - exp_set]
        parts = []
        if missing:
            parts.append(f"missing {len(missing)}: {missing[:3]}")
        if spurious:
            parts.append(f"spurious {len(spurious)}: {spurious[:3]}")
        return f"{label}: " + "; ".join(parts)
    return None


def _check_violation_map(label: str,
                         actual_list: List[Dict],
                         expected_map: Dict[str, Any]) -> List[str]:
    """
    Compare violations or warnings list against expected map.

    expected_map == {}   -> list must be empty.
    expected_map == {Q: {count: N, triples: [...]}}
                         -> check each named query.
    """
    errors = []
    if expected_map == {}:
        if actual_list:
            names = [v["query"] for v in actual_list]
            errors.append(f"{label}: expected empty, got {names}")
        return errors

    # Index actual by query name
    actual_by_name = {v["query"]: v for v in actual_list}

    for q_name, q_exp in expected_map.items():
        if q_name not in actual_by_name:
            errors.append(f"{label}[{q_name}]: not found in report")
            continue
        actual_entry = actual_by_name[q_name]
        if "count" in q_exp:
            got = actual_entry.get("count", 0)
            if got != q_exp["count"]:
                errors.append(f"{label}[{q_name}].count: expected {q_exp['count']}, got {got}")
        if "triples" in q_exp:
            err = _check_triples(
                f"{label}[{q_name}].triples",
                actual_entry.get("triples", []),
                q_exp["triples"],
            )
            if err:
                errors.append(err)
    return errors


def _compare_stage(stage_name: str,
                   actual: Dict[str, Any],
                   expected: Dict[str, Any]) -> List[str]:
    """Compare one stage's actual report against its expectations. Return errors."""
    errors = []

    for key, exp_val in expected.items():

        # --- scalar fields ---
        if key in ("status", "fats_rejected", "unclassified_rejected",
                   "mats_count", "oats_count", "scripts"):
            err = _check_scalar(f"{stage_name}.{key}", actual.get(key), exp_val)
            if err:
                errors.append(err)

        # --- minimum-count fields ---
        elif key == "mats_count_min":
            got = actual.get("mats_count", 0)
            if got < exp_val:
                errors.append(f"{stage_name}.mats_count: expected >= {exp_val}, got {got}")

        elif key == "oats_count_min":
            got = actual.get("oats_count", 0)
            if got < exp_val:
                errors.append(f"{stage_name}.oats_count: expected >= {exp_val}, got {got}")

        # --- triple list fields ---
        elif key in ("fats_property_triples", "fats_class_triples", "unclassified_triples"):
            err = _check_triples(f"{stage_name}.{key}", actual.get(key, []), exp_val)
            if err:
                errors.append(err)

        # --- violations / warnings maps ---
        elif key in ("violations", "warnings"):
            errs = _check_violation_map(
                f"{stage_name}.{key}",
                actual.get(key, []),
                exp_val,
            )
            errors.extend(errs)

    return errors


# ---------------------------------------------------------------------------
# Scenario execution
# ---------------------------------------------------------------------------

def _make_backend(backend_name: str,
                  ontology_files: List[Path],
                  graphdb_url: str = "http://localhost:7200",
                  graphdb_repo: str = "kinship-pipeline-scenario-test"):
    if backend_name == "rdflib":
        from kinship_pipeline.backends import RDFLibKinshipBackend
        b = RDFLibKinshipBackend(ontology_files=ontology_files)
        b.initialize()
        return b
    if backend_name == "graphdb":
        from kinship_pipeline.backends import GraphDBKinshipBackend
        b = GraphDBKinshipBackend(
            ontology_files=ontology_files,
            repository_id=graphdb_repo,
            graphdb_url=graphdb_url,
        )
        b.initialize()
        return b
    raise ValueError(f"Unknown backend: {backend_name!r}")


def run_scenario(scenario_path: Path,
                 backend_name: str = "rdflib",
                 verbose: bool = False) -> Tuple[int, int]:
    """
    Run one scenario file.

    Returns (pass_count, fail_count).
    """
    from kinship_pipeline.materialization_engine import MaterializationEngine
    from kinship_pipeline.pipeline import ConsistencyPipeline
    from kinship_pipeline.query_generator import QueryGenerator

    with open(scenario_path, encoding="utf-8") as f:
        scenario = json.load(f)

    name        = scenario.get("scenario", scenario_path.stem)
    description = scenario.get("description", "")
    root_rel    = scenario.get("ontology_root", _DEFAULT_ROOT_ONTOLOGY)
    intake_rel  = scenario.get("intake_file", "")
    expected    = scenario.get("expected", {})

    onto_paths  = _resolve_ontology_chain(_PROJECT_ROOT / root_rel)
    intake_path = _PROJECT_ROOT / intake_rel if intake_rel else None

    print(f"\n{'='*70}")
    print(f"Scenario: {name}")
    if description:
        print(f"  {description}")
    print(f"  Backend : {backend_name}")
    print(f"  Dataset : {Path(intake_rel).name if intake_rel else '(none)'}")
    print("="*70)

    # Build pipeline
    backend = _make_backend(backend_name, onto_paths)
    try:
        if intake_path:
            backend.load_data(intake_path, graph="urn:kinship:intake")

        qg     = QueryGenerator(backend)
        engine = MaterializationEngine(backend)
        pipe   = ConsistencyPipeline(backend, qg, engine)
        report = pipe.run(verbose=verbose)
    finally:
        if hasattr(backend, "cleanup"):
            backend.cleanup()

    # Compare each expected stage
    passes = fails = 0
    stages_actual = report.get("stages", {})

    for stage_name, stage_exp in expected.items():
        stage_actual = stages_actual.get(stage_name, {})
        errors = _compare_stage(stage_name, stage_actual, stage_exp)
        if errors:
            fails += 1
            print(f"  [FAIL] {stage_name}")
            for e in errors:
                print(f"      {e}")
        else:
            passes += 1
            print(f"  [PASS] {stage_name}")

    if not expected:
        print("  (no expectations declared — smoke-test only)")
        passes += 1

    return passes, fails


def run_all_scenarios(backend_name: str = "rdflib",
                      scenarios_dir: Path = _SCENARIOS_DIR,
                      verbose: bool = False) -> int:
    """Run every *.json scenario. Return total failure count."""
    files = sorted(scenarios_dir.glob("*.json"))
    if not files:
        print(f"[WARN] No scenario files found in {scenarios_dir}")
        return 0

    total_pass = total_fail = 0
    for f in files:
        p, ff = run_scenario(f, backend_name=backend_name, verbose=verbose)
        total_pass += p
        total_fail += ff

    print(f"\n{'='*70}")
    print(f"PIPELINE SCENARIO RESULTS: {total_pass} passed | {total_fail} failed")
    print("="*70)
    if total_fail:
        print(f"[FAIL] {total_fail} expectation(s) did not pass.")
    else:
        print("[PASS] All scenario expectations passed.")
    return total_fail


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=textwrap.dedent("""\
            Data-driven test runner for the kinship consistency pipeline.
            Discovers scenario JSON files under tests/pipeline/scenarios/ and
            runs each through pipeline.run(), comparing results to expectations.
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument("--all",      action="store_true", help="Run all scenarios.")
    mode.add_argument("--scenario", metavar="NAME",
                      help="Run a single scenario by name (stem of the JSON file).")
    mode.add_argument("--list",     action="store_true",
                      help="List available scenario files and exit.")
    p.add_argument("--backend",  default="rdflib", choices=["rdflib", "graphdb"])
    p.add_argument("--verbose",  action="store_true",
                   help="Print verbose pipeline output for each scenario.")
    p.add_argument("--scenarios-dir", default=None,
                   help="Override the scenarios directory path.")
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    scenarios_dir = Path(args.scenarios_dir) if args.scenarios_dir else _SCENARIOS_DIR

    if args.list:
        files = sorted(scenarios_dir.glob("*.json"))
        print(f"Scenarios in {scenarios_dir}:")
        for f in files:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            print(f"  {f.stem:<45}  {d.get('description','')[:60]}")
        return

    if not args.all and not args.scenario:
        parser.print_usage()
        print("error: one of --all, --scenario, or --list is required")
        sys.exit(1)

    if args.scenario:
        path = scenarios_dir / f"{args.scenario}.json"
        if not path.exists():
            sys.exit(f"Scenario file not found: {path}")
        _, fails = run_scenario(path, backend_name=args.backend, verbose=args.verbose)
        sys.exit(1 if fails else 0)

    fails = run_all_scenarios(
        backend_name=args.backend,
        scenarios_dir=scenarios_dir,
        verbose=args.verbose,
    )
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
