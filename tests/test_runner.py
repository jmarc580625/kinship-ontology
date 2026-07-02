"""
test_runner.py
--------------
Data-driven test runner for the modular kinship ontology.

Each module's ontology paths, data files and test definitions are stored in a
self-describing JSON file under ``tests/definitions/``.  The central config
(``test-config.json``) carries only backend connection settings and the
path to the definitions folder.

Modes
-----
  --module MODULE   Load that module's TTL only; run its tests in isolation.
  --upto   MODULE   Load that module's TTL (which transitively imports all
                    predecessors); run tests for all modules up to and
                    including it.
  --all             Run every module declared in module_order.

Optional flags
--------------
  --backend         rdflib (default) | graphdb
  --config          Path to test-config.json  (default: auto-detect)
  --definitions     Path to the definitions folder  (default: auto-detect)
  --project-root    Repo root (default: auto-detect from this file's location)

Exit code: 0 = all pass, 1 = any failure or error.

Usage examples
--------------
  python tests/test_runner.py --module core-neutral
  python tests/test_runner.py --upto negative
  python tests/test_runner.py --all
"""

import argparse
import json
import os
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------

_TESTS_DIR    = Path(__file__).resolve().parent
_PROJECT_ROOT = _TESTS_DIR.parent

# ---------------------------------------------------------------------------
# Module ordering  (used only for --module / --upto selection)
#
# The actual TTL load order is derived at runtime by depth-first traversal
# of owl:imports via ontology_loader.load_chain_for().  No file paths are
# hardcoded here.  The import graph is a DAG (gender-specific has 4 parents)
# and social is standalone (no imports) — both handled transparently.
# ---------------------------------------------------------------------------

MODULE_ORDER = [
    "core-neutral",
    "anchored-neutral",
    "extended-neutral",
    "blended-neutral",
    "allied-neutral",
    "gendered",
    "social",
    "consistency-control",
    "consistency-control-on-core-data",
    "owl-consistency-control",
    "owl-consistency-control-on-core-data",
    "negative",
    "boundary",
]


def _module_order(config: Optional[Dict] = None) -> List[str]:
    if config and isinstance(config.get("module_order"), list):
        return config["module_order"]
    return MODULE_ORDER


def _modules_upto(name: str, module_order: Optional[List[str]] = None) -> List[str]:
    """Return all module names up to and including *name*."""
    order = module_order if module_order is not None else MODULE_ORDER
    idx = order.index(name)
    return order[: idx + 1]


# ---------------------------------------------------------------------------
# Definition-file loader
# ---------------------------------------------------------------------------

def _resolve_query_library(mod_def: Dict, root: Path) -> None:
    """
    If *mod_def* declares a ``query_library`` path, load that JSON file and
    merge each library entry into the corresponding test definition.

    Merge rules (library provides defaults; suite-level test overrides):
    - ``query``       : library value used only when the test has no inline ``query``
    - ``description`` : library value used only when the test has no inline ``description``
    - ``abox_only``   : library value used only when the test has no inline ``abox_only``
    - ``expected`` / ``expect_empty`` : never taken from library
    """
    lib_rel = mod_def.get("query_library")
    if not lib_rel:
        return
    lib_path = root / lib_rel
    try:
        with open(lib_path, encoding="utf-8") as f:
            library: Dict[str, Dict] = json.load(f)
    except Exception as exc:
        print(f"[WARN] Cannot load query_library {lib_path}: {exc}", file=sys.stderr)
        return
    for test_id, tdef in mod_def.get("tests", {}).items():
        lib_entry = library.get(test_id, {})
        for field in ("query", "description", "abox_only"):
            if field not in tdef and field in lib_entry:
                tdef[field] = lib_entry[field]


def _load_definitions(definitions_folder: Path,
                      root: Optional[Path] = None) -> Dict[str, Dict]:
    """
    Scan *definitions_folder* for ``*.json`` files and return a mapping
    ``{module_name: module_def_dict}``.

    Each file must contain a top-level ``"module"`` key that names the
    module, plus ``"ontologies"``, ``"data_files"``, and ``"tests"``.

    If a definition declares ``"query_library"``, the referenced file is
    loaded and generic queries are merged into each test entry (see
    :func:`_resolve_query_library`).
    """
    effective_root = root if root is not None else _PROJECT_ROOT
    defs: Dict[str, Dict] = {}
    for path in sorted(definitions_folder.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                mod_def = json.load(f)
        except Exception as exc:
            print(f"[WARN] Cannot load definition file {path.name}: {exc}",
                  file=sys.stderr)
            continue
        mod_name = mod_def.get("module")
        if not mod_name:
            print(f"[WARN] {path.name} has no 'module' key - skipped",
                  file=sys.stderr)
            continue
        _resolve_query_library(mod_def, effective_root)
        defs[mod_name] = mod_def
    return defs


# ---------------------------------------------------------------------------
# Result normalisation
# ---------------------------------------------------------------------------

_KINSHIP_NS = "http://example.org/kinship#"


def _normalise_value(v):
    """Convert a full URI to a prefixed form. Handles list values recursively."""
    if isinstance(v, list):
        return [_normalise_value(item) for item in v]
    if isinstance(v, str) and v.startswith(_KINSHIP_NS):
        return ":" + v[len(_KINSHIP_NS):]
    return v


def _normalise_row(row: Dict[str, str]) -> Dict[str, str]:
    return {k: _normalise_value(v) for k, v in row.items()}


def _compare_cycles(val):
    """Transform cycle list to canonical tuple for rotation-invariant comparison."""
    if not isinstance(val, list):
        return val  # Not a list, return as-is
    if len(val) <= 1:
        return tuple(val)
    min_idx = val.index(min(val))
    rotated = val[min_idx:] + val[:min_idx]
    return tuple(rotated)


def _rows_match(actual: List[Dict], expected: List[Dict],
                compare_fn=None) -> bool:
    """Order-insensitive comparison with optional value comparison function."""
    def _key(r: Dict) -> tuple:
        return tuple(sorted(r.items()))

    # Default comparison without helper
    if compare_fn is None:
        return sorted(_key(r) for r in actual) == sorted(_key(r) for r in expected)

    # With helper: transform values before comparison
    def _transform_row(row: Dict) -> Dict:
        return {k: compare_fn(v) for k, v in row.items()}

    actual_transformed = [_transform_row(r) for r in actual]
    expected_transformed = [_transform_row(r) for r in expected]

    return sorted(_key(r) for r in actual_transformed) == \
           sorted(_key(r) for r in expected_transformed)


# ---------------------------------------------------------------------------
# Single-test execution
# ---------------------------------------------------------------------------

def _call_test_function(spec: str, backend) -> List[Dict]:
    """Import and call 'module.path:function_name' for test_function tests."""
    import importlib
    mod_path, func_name = spec.rsplit(":", 1)
    module = importlib.import_module(mod_path)
    fn = getattr(module, func_name)
    return fn(backend)

def _run_test(backend, test_id: str, test_def: Dict,
              abox_only: bool = False) -> Tuple[str, str]:
    """
    Run one test case.

    Parameters
    ----------
    abox_only:
        When True, route to ``execute_abox_query()`` instead of
        ``execute_query()`` so that OWL-RL inferred triples are excluded.

    Returns
    -------
    (status, detail) where status is 'PASS', 'FAIL', or 'ERROR'.
    """
    expect_empty = test_def.get("expect_empty", False)
    expected = test_def.get("expected", [])
    compare_fn_name = test_def.get("expected_comparison_function", None)

    # Resolve comparison function
    compare_fn = None
    if compare_fn_name:
        if compare_fn_name == "_compare_cycles":
            compare_fn = _compare_cycles
        else:
            return "ERROR", f"Unknown comparison function: {compare_fn_name}"

    try:
        # Get raw results via test_function or SPARQL query
        if "test_function" in test_def:
            raw = _call_test_function(test_def["test_function"], backend)
        else:
            query = test_def.get("query", "")
            if abox_only and hasattr(backend, "execute_abox_query"):
                raw = backend.execute_abox_query(query)
            else:
                raw = backend.execute_query(query)
        actual = [_normalise_row(r) for r in raw]
    except Exception as exc:
        return "ERROR", str(exc)

    if expect_empty:
        if not actual:
            return "PASS", ""
        return "FAIL", f"Expected empty result but got {len(actual)} row(s): {actual[:3]}"

    if _rows_match(actual, expected, compare_fn=compare_fn):
        return "PASS", ""

    # Build a diff-style detail message
    if compare_fn:
        # Use transformed values for diff when compare_fn is present
        def _transform_row(row: Dict) -> Dict:
            return {k: compare_fn(v) for k, v in row.items()}
        exp_set = set(tuple(sorted(_transform_row(r).items())) for r in expected)
        act_set = set(tuple(sorted(_transform_row(r).items())) for r in actual)
    else:
        exp_set = set(tuple(sorted(r.items())) for r in expected)
        act_set = set(tuple(sorted(r.items())) for r in actual)
    missing  = [dict(r) for r in exp_set - act_set]
    spurious = [dict(r) for r in act_set - exp_set]
    parts = []
    if missing:
        parts.append(f"Missing {len(missing)} row(s): {missing[:5]}")
    if spurious:
        parts.append(f"Spurious {len(spurious)} row(s): {spurious[:5]}")
    return "FAIL", "; ".join(parts)


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

def run(
    *,
    module: Optional[str] = None,
    upto: Optional[str] = None,
    run_all: bool = False,
    backend_name: str = "rdflib",
    config_path: Optional[str] = None,
    definitions_path: Optional[str] = None,
    project_root: Optional[str] = None,
    verbose: bool = False,
) -> int:
    """
    Execute the test suite according to the requested mode.

    Returns the number of failures (0 = all pass).
    """
    root = Path(project_root) if project_root else _PROJECT_ROOT
    cfg_file = Path(config_path) if config_path else _TESTS_DIR / "test-config.json"

    # ---- Load config (backend settings only) ------------------------------
    with open(cfg_file, encoding="utf-8") as f:
        config = json.load(f)
    module_order = _module_order(config)

    # ---- Locate and load module definition files --------------------------
    defs_dir_rel = config.get("definitions_folder", "tests/definitions")
    defs_dir = Path(definitions_path) if definitions_path else root / defs_dir_rel
    module_defs = _load_definitions(defs_dir, root)

    # ---- ontology_loader import ------------------------------------------
    from lib.ontology_loader import load_chain_for

    def _mod_ttl(mod_def: Dict) -> List[str]:
        """
        Build the deduplicated, order-preserving DFS import chain for all
        ontology entry-points declared in a module definition.

        Scan folders are resolved as follows (in priority order):
          1. Explicit ``import_scan_folders`` list in the module definition.
          2. Auto-derived: the parent directory of each declared ontology file.

        This makes each module self-contained: no global ``import_scan_folders``
        config is needed.  Cross-directory imports are handled by adding an
        explicit ``import_scan_folders`` list to the module definition.
        """
        onto_paths = [root / rel for rel in mod_def["ontologies"]]

        if "import_scan_folders" in mod_def:
            scan_dirs: List[Path] = [root / f for f in mod_def["import_scan_folders"]]
        else:
            seen_dirs: list = []
            for p in onto_paths:
                d = p.parent
                if d not in seen_dirs:
                    seen_dirs.append(d)
            scan_dirs = seen_dirs

        seen: set = set()
        combined: List[str] = []
        for onto_path in onto_paths:
            for p in load_chain_for(onto_path, scan_dirs):
                s = str(p)
                if s not in seen:
                    seen.add(s)
                    combined.append(s)
        return combined

    # ---- Determine which modules / tests to run ---------------------------
    if run_all:
        target_modules = module_order[:]
    elif upto:
        target_modules = _modules_upto(upto, module_order)
    elif module:
        target_modules = [module]
    else:
        target_modules = module_order[:]

    # ---- Build suite list -------------------------------------------------
    # Each suite: (label, onto_names, ttl_chain, data_files, test_ids,
    #              tests_dict, abox_only, shacl_shapes)
    # onto_names:   basenames of the declared ontology entry-points (for display)
    # abox_only:    when True, queries route to execute_abox_query() (no inference)
    # shacl_shapes: optional path to SHACL shapes file for pySHACL validation
    suites: List[Tuple[str, List[str], List[str], List[str], List[str], Dict, bool, Optional[str]]] = []

    for mod in target_modules:
        if mod not in module_defs:
            print(f"[WARN] No definition file found for module '{mod}' - skipped",
                  file=sys.stderr)
            continue
        md = module_defs[mod]
        shacl_rel = md.get("shacl_shapes")
        shacl_abs = str(root / shacl_rel) if shacl_rel else None
        suites.append((
            mod,
            [Path(f).name for f in md["ontologies"]],
            _mod_ttl(md),
            [str(root / f) for f in md["data_files"]],
            list(md["tests"].keys()),
            md["tests"],
            md.get("abox_only", False),
            shacl_abs,
        ))

    # ---- Run each suite ---------------------------------------------------
    total_pass = total_fail = total_error = total_skip = 0

    for suite_name, onto_names, ttl_list, dfiles, ids, tests_dict, abox_only, shacl_shapes in suites:
        print(f"\n{'='*70}")
        print(f"Suite:      {suite_name.upper()}")
        print(f"Ontologies: {onto_names}")
        print(f"Data:       {[Path(f).name for f in dfiles]}")
        if shacl_shapes:
            print(f"SHACL:      {Path(shacl_shapes).name}")
        print(f"Tests:      {len(ids)}")
        print("="*70)

        # Initialise backend
        backend = _make_backend(backend_name, ttl_list, dfiles, config, root,
                                shacl_shapes=shacl_shapes)

        # Run MaterializationManager (only when ABox data is present)
        if dfiles:
            try:
                from lib.materialization_manager import MaterializationManager
                mgr = MaterializationManager(
                    backend,
                    namespace="http://example.org/kinship#",
                )
                def _on_script(r):
                    if r["status"] == "ok":
                        line = f"  :{r['property']:<32} +{r['triples_added']} triples"
                        if r["reasoning_triggered"] and r["inferred_triples"] > 0:
                            line += f"  -> reasoning +{r['inferred_triples']} inferred"
                        print(line)
                    elif r["status"].startswith("error"):
                        print(f"  :{r['property']:<32} ERROR: {r['status']}")

                print("Materialization:")
                mat_results = mgr.execute(on_script=_on_script)
                scripts_run = sum(1 for r in mat_results if r["status"] == "ok")
                print(f"  {scripts_run}/{len(mat_results)} scripts executed.\n")
            except Exception as exc:
                print(f"[ERROR] MaterializationManager failed: {exc}", file=sys.stderr)
                total_error += len(ids)
                continue
        else:
            print("  (no data files — materialization skipped)\n")

        # Run SHACL validation (if shapes are declared)
        if shacl_shapes and hasattr(backend, "run_shacl_validation"):
            try:
                backend.run_shacl_validation()
            except Exception as exc:
                print(f"[ERROR] SHACL validation failed: {exc}", file=sys.stderr)
                total_error += len(ids)
                continue

        # Execute tests
        for tid in ids:
            tdef = tests_dict[tid]
            test_abox_only = tdef.get("abox_only", abox_only)
            status, detail = _run_test(backend, tid, tdef, abox_only=test_abox_only)

            if status == "PASS":
                total_pass += 1
                print(f"  [PASS] {tid}")
            elif status == "FAIL":
                total_fail += 1
                print(f"  [FAIL] {tid}")
                if verbose and tdef.get("description"):
                    print(f"      {tdef['description']}")
                print(f"      {detail}")
            else:
                total_error += 1
                print(f"  [ERROR] {tid}")
                if tdef.get("description"):
                    print(f"      {tdef['description']}")
                print(f"      ERROR: {detail}")

        # Backend cleanup
        if hasattr(backend, "cleanup"):
            backend.cleanup()

    # ---- Summary ----------------------------------------------------------
    total = total_pass + total_fail + total_error + total_skip
    print(f"\n{'='*70}")
    print(f"RESULTS: {total_pass} passed  |  {total_fail} failed  |  "
          f"{total_error} errors  |  {total_skip} skipped  |  {total} total")
    print("="*70)

    failures = total_fail + total_error
    if failures:
        print(f"\n[FAIL] {failures} test(s) did not pass.")
    else:
        print("\n[PASS] All tests passed.")

    return failures


# ---------------------------------------------------------------------------
# Backend factory
# ---------------------------------------------------------------------------

def _make_backend(name: str, ttl_files: List[str], data_files: List[str],
                  config: Dict, root: Path, *,
                  shacl_shapes: Optional[str] = None):
    """
    Create and initialise a backend.

    *ttl_files* is the ordered DFS-resolved list of ontology (TBox) TTL files.
    *data_files* is the list of ABox (instance data) TTL files.
    *shacl_shapes* is an optional path to a SHACL shapes TTL file.
    """
    if name == "rdflib":
        try:
            from backends.rdflib_backend import RDFLibBackend
        except ImportError as e:
            sys.exit(f"RDFLibBackend not available: {e}")
        b = RDFLibBackend(ontology_files=ttl_files, data_files=data_files,
                          shacl_shapes=shacl_shapes)
        b.initialize()
        return b

    if name == "graphdb":
        try:
            from backends.graphdb_backend import GraphDBBackend
        except ImportError as e:
            sys.exit(f"GraphDBBackend not available: {e}")
        gdb = config.get("graphdb", {})
        b = GraphDBBackend(
            ontology_files=ttl_files,
            data_files=data_files,
            graphdb_url=gdb.get("url", "http://localhost:7200"),
            repository_id=gdb.get("repository", "kinship-ontology-test"),
            ruleset=gdb.get("ruleset", "owl2-rl"),
            shacl_shapes=shacl_shapes,
        )
        b.initialize()
        return b

    sys.exit(f"Unknown backend: {name!r}. Choose 'rdflib' or 'graphdb'.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=textwrap.dedent("""\
            Module-aligned test runner for the kinship ontology.
            Load a specific module or cumulatively up to a module,
            then run the corresponding data-driven test cases.
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument(
        "--module",
        metavar="MODULE",
        help="Run tests for a single module in isolation. Valid modules are read from test-config.json.",
    )
    mode.add_argument(
        "--upto",
        metavar="MODULE",
        help="Cumulative run: load this module and run all tests up to it according to test-config.json.",
    )
    mode.add_argument(
        "--all",
        dest="run_all",
        action="store_true",
        help="Run everything: all modules listed in module_order.",
    )
    p.add_argument("--backend",   default="rdflib", choices=["rdflib", "graphdb"])
    p.add_argument("--verbose",   action="store_true", help="Print test names for passing tests too.")
    p.add_argument("--config",      default=None, help="Path to test-config.json")
    p.add_argument("--definitions", default=None, help="Path to tests/definitions folder")
    p.add_argument("--project-root", default=None, help="Repo root directory")
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if not args.module and not args.upto and not args.run_all:
        parser.print_usage(sys.stdout)
        print("error: one of the arguments --module --upto --all is required")
        sys.exit(1)
    root = Path(args.project_root) if args.project_root else _PROJECT_ROOT
    cfg_file = Path(args.config) if args.config else _TESTS_DIR / "test-config.json"
    with open(cfg_file, encoding="utf-8") as f:
        config = json.load(f)
    module_order = _module_order(config)
    for selected, option in ((args.module, "--module"), (args.upto, "--upto")):
        if selected and selected not in module_order:
            raise SystemExit(f"{option} '{selected}' is not declared in module_order: {module_order}")
    failures = run(
        module=args.module,
        upto=args.upto,
        run_all=args.run_all,
        backend_name=args.backend,
        config_path=args.config,
        definitions_path=args.definitions,
        project_root=str(root),
        verbose=args.verbose,
    )
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
