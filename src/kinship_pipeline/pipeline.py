"""
Consistency pipeline orchestrator.

Implements the V1D1/V1D2 pipeline:

    Intake
      -> FATS Gate
      -> MATS Gate                (blocks on "violation")
      -> Materialization Step 1   (A -> M)
      -> OATS Layer A             (blocks on "violation")
      -> OATS Layer B
      -> Materialization Step 2   (A+O -> MO)
      -> SHACL Gate               (warning only; MO remains usable)

Blocking rules
--------------
FATS   "blocked"   -> pipeline stops (nothing survived routing)
MATS   "violation" -> pipeline stops (graph invalid; do not materialise)
OATS_A "violation" -> pipeline stops (quarantine graph compromised)
SHACL  "warning"  -> pipeline continues; MO is usable but flagged

Stages that did not run appear in the report as {"status": "skipped", "reason": "..."}.

Pass ``verbose=True`` to ``run()`` to print a human-readable summary to stdout.
"""

from typing import Any, Dict, List

from .backends.base import KinshipBackend
from .gates.fats import FatsGate
from .gates.mats import MatsGate
from .gates.oats_layer_a import OatsLayerA
from .gates.oats_layer_b import OatsLayerB
from .gates.shacl import ShaclGate
from .materialization_engine import MaterializationEngine
from .query_generator import QueryGenerator


_KIN = "http://example.org/kinship#"

_SKIPPED = "skipped"


def _skipped(reason: str) -> Dict[str, Any]:
    return {"status": _SKIPPED, "reason": reason}


def _stash_oats(backend: "KinshipBackend", oats_graph: str) -> str:
    """Extract OATS graph as serialized NTriples, then clear it.

    Returns the NTriples string (empty string if OATS was empty).
    """
    if backend.graph_size(oats_graph) == 0:
        return ""
    ntriples = backend.export_graph(oats_graph)
    backend.clear_graph(oats_graph)
    return ntriples


def _restore_oats(backend: "KinshipBackend", oats_graph: str, data: str) -> None:
    """Re-insert previously stashed OATS triples."""
    backend.import_graph(oats_graph, data)


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
        self.shacl_gate = ShaclGate(backend)

    def run(
        self,
        *,
        intake_graph: str = "urn:kinship:intake",
        asserted_graph: str = "urn:kinship:asserted",
        oats_graph: str = "urn:kinship:oats",
        mats_closure_graph: str = "urn:kinship:mats-closure",
        full_graph: str = "urn:kinship:full",
        reason_after_each: bool = False,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """Execute the pipeline and return a structured report.

        The top-level ``status`` is the worst status seen across all stages
        that actually ran:
          "ok"        all gates clean
          "warning"   only RED warnings found
          "violation" at least one blocking family hit
          "blocked"   FATS routing left nothing to validate

        Stages that did not run (because an upstream gate blocked) carry
        ``{"status": "skipped", "reason": "..."}`` in the report.

        Parameters
        ----------
        verbose:
            If True, print a human-readable summary to stdout after each stage.
        """
        report: Dict[str, Any] = {"status": "ok", "stages": {}}

        # ------------------------------------------------------------------
        # 1. FATS Gate
        # ------------------------------------------------------------------
        fats_report = self.fats_gate.run(intake_graph, asserted_graph, oats_graph)
        report["stages"]["FATS"] = fats_report
        if verbose:
            _print_fats(fats_report)

        fats_status = fats_report.get("status", "ok")
        if fats_status == "blocked":
            report["status"] = "blocked"
            for stage in ("MATS", "MATS_MATERIALIZATION",
                          "OATS_LAYER_A", "OATS_LAYER_B", "FULL_MATERIALIZATION"):
                report["stages"][stage] = _skipped("FATS gate blocked: no triples routed")
            if verbose:
                _print_banner("blocked")
            return report
        if fats_status == "warning":
            report["status"] = "warning"

        # ------------------------------------------------------------------
        # 2. Isolate OATS graph
        # ------------------------------------------------------------------
        # OATS triples must be physically absent from the store during
        # MATS gate checks and materialization Step 1.  This guarantees
        # that M is derived purely from A, regardless of backend.
        oats_stash_data = _stash_oats(self.backend, oats_graph)

        # ------------------------------------------------------------------
        # 3. MATS Gate
        # ------------------------------------------------------------------
        mats_report = self.mats_gate.run(asserted_graph)
        report["stages"]["MATS"] = mats_report
        if verbose:
            _print_violation_gate("MATS Gate", mats_report)

        mats_status = mats_report.get("status", "ok")
        if mats_status == "violation":
            report["status"] = "violation"
            # Restore OATS before returning so the repo is left intact.
            if oats_stash_data:
                _restore_oats(self.backend, oats_graph, oats_stash_data)
            for stage in ("MATS_MATERIALIZATION",
                          "OATS_LAYER_A", "OATS_LAYER_B", "FULL_MATERIALIZATION"):
                report["stages"][stage] = _skipped("MATS gate violation: graph not materialised")
            if verbose:
                _print_banner("violation")
            return report
        if mats_status == "warning" and report["status"] == "ok":
            report["status"] = "warning"

        # ------------------------------------------------------------------
        # 4. Enable inference (MATS-only: ontology + asserted)
        # ------------------------------------------------------------------
        self.backend.enable_inference()

        # ------------------------------------------------------------------
        # 5. Materialization Step 1: A -> M
        # ------------------------------------------------------------------
        mats_scripts = self.materialization_engine.step1(
            source_graph=asserted_graph,
            target_graph=mats_closure_graph,
            reason_after_each=reason_after_each,
        )
        mat1_report = {
            "status": "ok",
            "scripts": len(mats_scripts),
            "details": mats_scripts,
        }
        report["stages"]["MATS_MATERIALIZATION"] = mat1_report
        if verbose:
            _print_materialization("Materialization Step 1 (A -> M)", mat1_report)

        # ------------------------------------------------------------------
        # 6. Disable inference (freeze M before OATS re-enters)
        # ------------------------------------------------------------------
        self.backend.disable_inference()

        # ------------------------------------------------------------------
        # 7. Restore OATS graph
        # ------------------------------------------------------------------
        if oats_stash_data:
            _restore_oats(self.backend, oats_graph, oats_stash_data)

        # ------------------------------------------------------------------
        # 8. OATS Layer A
        # ------------------------------------------------------------------
        layer_a = self.oats_layer_a.run(oats_graph, mats_closure_graph)
        report["stages"]["OATS_LAYER_A"] = layer_a
        if verbose:
            _print_oats_layer_a(layer_a)

        if layer_a.get("status") == "violation":
            report["status"] = "violation"
            for stage in ("OATS_LAYER_B", "FULL_MATERIALIZATION"):
                report["stages"][stage] = _skipped("OATS Layer A violation: quarantine graph compromised")
            if verbose:
                _print_banner("violation")
            return report

        # ------------------------------------------------------------------
        # 9. OATS Layer B
        # ------------------------------------------------------------------
        layer_b = self.oats_layer_b.run(oats_graph)
        report["stages"]["OATS_LAYER_B"] = layer_b
        if verbose:
            _print_violation_gate("OATS Layer B", layer_b)

        layer_b_status = layer_b.get("status", "ok")
        if layer_b_status == "violation":
            report["status"] = "violation"
        elif layer_b_status == "warning" and report["status"] == "ok":
            report["status"] = "warning"

        # ------------------------------------------------------------------
        # 10. Enable inference (full: ontology + asserted + oats)
        # ------------------------------------------------------------------
        self.backend.enable_inference()

        # ------------------------------------------------------------------
        # 11. Materialization Step 2: A+O -> MO
        # ------------------------------------------------------------------
        full_scripts = self.materialization_engine.step2(
            asserted_graph=asserted_graph,
            oats_graph=oats_graph,
            target_graph=full_graph,
            reason_after_each=reason_after_each,
        )
        mat2_report = {
            "status": "ok",
            "scripts": len(full_scripts),
            "details": full_scripts,
        }
        report["stages"]["FULL_MATERIALIZATION"] = mat2_report
        if verbose:
            _print_materialization("Materialization Step 2 (A+O -> MO)", mat2_report)

        # ------------------------------------------------------------------
        # 12. SHACL Gate (post-inference safety net, warning only)
        # ------------------------------------------------------------------
        shacl_report = self.shacl_gate.run(
            shapes_graph="urn:kinship:shapes",
            report_graph="urn:kinship:validation",
        )
        report["stages"]["SHACL_GATE"] = shacl_report
        if verbose:
            _print_shacl_gate(shacl_report)

        shacl_status = shacl_report.get("status", "ok")
        if shacl_status == "warning" and report["status"] == "ok":
            report["status"] = "warning"

        if verbose:
            _print_banner(report["status"])

        return report


# ---------------------------------------------------------------------------
# Verbose rendering helpers
# ---------------------------------------------------------------------------

_W = 70


def _short(uri: str) -> str:
    if uri and uri.startswith(_KIN):
        return "kin:" + uri[len(_KIN):]
    return uri


def _fmt_row(t: Dict[str, Any]) -> str:
    parts = [f"{k}={_short(str(v))}" for k, v in sorted(t.items())]
    return "  (" + ", ".join(parts) + ")"


def _sep(char: str = "-") -> str:
    return char * _W


def _status_tag(status: str) -> str:
    tags = {
        "ok":        "[OK]",
        "warning":   "[WARN]",
        "violation": "[FAIL]",
        "blocked":   "[BLOCKED]",
        "skipped":   "[SKIPPED]",
    }
    return tags.get(status, f"[{status.upper()}]")


def _print_fats(r: Dict[str, Any]) -> None:
    tag = _status_tag(r["status"])
    print()
    print(_sep("="))
    print(f" FATS Gate  {tag}")
    print(_sep("-"))
    print(f"  MATS triples routed  : {r['mats_count']}")
    print(f"  OATS triples routed  : {r['oats_count']}")

    prop_triples: List = r.get("fats_property_triples", [])
    cls_triples:  List = r.get("fats_class_triples", [])
    unc_triples:  List = r.get("unclassified_triples", [])

    if prop_triples:
        print(f"  FATS property rejected ({len(prop_triples)}):")
        for t in prop_triples:
            print(_fmt_row(t))
    else:
        print("  FATS property rejected : 0")

    if cls_triples:
        print(f"  FATS class rejected    ({len(cls_triples)}):")
        for t in cls_triples:
            print(_fmt_row(t))
    else:
        print("  FATS class rejected    : 0")

    if unc_triples:
        by_pred: Dict[str, List] = {}
        for t in unc_triples:
            p = _short(t.get("p", "?p"))
            by_pred.setdefault(p, []).append(t)
        print(f"  Unclassified rejected  ({len(unc_triples)}) -- {len(by_pred)} distinct predicates:")
        for pred, triples in sorted(by_pred.items()):
            print(f"    {pred}  ({len(triples)} triple(s))")
            for t in triples:
                print("      " + _fmt_row(t).strip())
    else:
        print("  Unclassified rejected  : 0")


def _print_violation_gate(label: str, r: Dict[str, Any]) -> None:
    tag = _status_tag(r["status"])
    violations: List = r.get("violations", [])
    warnings:   List = r.get("warnings", [])
    print()
    print(_sep("="))
    print(f" {label}  {tag}")
    print(_sep("-"))
    if not violations and not warnings:
        print("  No violations detected.")
        return
    for v in violations:
        print(f"  {v['query']}  -- {v['count']} violation(s):")
        if "cycles" in v:
            for cyc in v["cycles"]:
                path = " -> ".join(_short(n) for n in cyc)
                print(f"    cycle: {path}")
        else:
            for t in v.get("triples", []):
                print(_fmt_row(t))
    for w in warnings:
        print(f"  {w['query']}  -- {w['count']} warning(s) [redundancy]:")
        for t in w.get("triples", []):
            print(_fmt_row(t))


def _print_oats_layer_a(r: Dict[str, Any]) -> None:
    tag = _status_tag(r["status"])
    count = r.get("count", 0)
    print()
    print(_sep("="))
    print(f" OATS Layer A  {tag}")
    print(_sep("-"))
    print(f"  Candidates checked  : {count}")
    if count:
        for row in r.get("violations", []):
            print(_fmt_row(row))


def _print_materialization(label: str, r: Dict[str, Any]) -> None:
    tag = _status_tag(r["status"])
    print()
    print(_sep("="))
    print(f" {label}  {tag}")
    print(_sep("-"))
    details: List = r.get("details", [])
    if not details:
        print("  No materialization scripts executed.")
        return
    for d in details:
        prop     = _short(d.get("property", "?"))
        added    = d.get("triples_added", "?")
        inferred = d.get("inferred_triples", 0)
        inf_str  = f"  (+{inferred} inferred)" if inferred else ""
        print(f"  {prop:<45}  +{added} triples{inf_str}")


def _print_shacl_gate(r: Dict[str, Any]) -> None:
    tag = _status_tag(r["status"])
    print()
    print(_sep("="))
    print(f" SHACL Gate  {tag}")
    print(_sep("-"))
    if r.get("status") == "ok":
        print("  No SHACL violations detected.")
        return
    print(f"  Total violations : {r.get('total_count', 0)}")
    print(f"  Coverage gap     : {r.get('coverage_gap', 0)}")
    for v in r.get("violations", []):
        shape = v.get("shape", "?")
        node = _short(v.get("node", ""))
        detail = _short(v.get("detail", ""))
        detail_str = f" (related: {detail})" if detail else ""
        print(f"  {shape}: {node}{detail_str}")


def _print_banner(overall_status: str) -> None:
    tag = _status_tag(overall_status)
    print()
    print(_sep("="))
    print(f" PIPELINE RESULT  {tag}")
    print(_sep("="))
    print()
