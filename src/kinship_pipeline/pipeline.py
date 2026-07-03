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

Pass ``verbose=True`` to ``run()`` to print a human-readable summary to stdout.
"""

from typing import Any, Dict, List

from .backends.base import KinshipBackend
from .gates.fats import FatsGate
from .gates.mats import MatsGate
from .gates.oats_layer_a import OatsLayerA
from .gates.oats_layer_b import OatsLayerB
from .materialization_engine import MaterializationEngine
from .query_generator import QueryGenerator


_KIN = "http://example.org/kinship#"


def _short(uri: str) -> str:
    """Abbreviate a kinship URI to kin:LocalName."""
    if uri and uri.startswith(_KIN):
        return "kin:" + uri[len(_KIN):]
    return uri


def _fmt_row(t: Dict[str, Any]) -> str:
    """Format a SPARQL result row as a compact tuple string."""
    parts = [f"{k}={_short(v)}" for k, v in sorted(t.items())]
    return "  (" + ", ".join(parts) + ")"


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
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """Execute the pipeline and return a structured report.

        Parameters
        ----------
        verbose:
            If True, print a human-readable control summary to stdout after
            each stage completes.
        """
        report: Dict[str, Any] = {
            "status": "ok",
            "stages": {},
        }

        # 1. FATS Gate
        fats_report = self.fats_gate.run(intake_graph, asserted_graph, oats_graph)
        report["stages"]["FATS"] = fats_report
        if fats_report.get("status") != "ok":
            report["status"] = "warning"
        if verbose:
            _print_fats(fats_report)

        # 2. MATS Gate
        mats_report = self.mats_gate.run(asserted_graph)
        report["stages"]["MATS"] = mats_report
        if mats_report.get("status") != "ok":
            report["status"] = "violation"
        if verbose:
            _print_violation_gate("MATS Gate", mats_report)

        # 3. Materialization Step 1: A → M
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

        # 4. OATS Layer A
        layer_a = self.oats_layer_a.run(oats_graph, mats_closure_graph)
        report["stages"]["OATS_LAYER_A"] = layer_a
        if layer_a.get("status") != "ok":
            report["status"] = "violation"
        if verbose:
            _print_oats_layer_a(layer_a)

        # 5. OATS Layer B
        layer_b = self.oats_layer_b.run(oats_graph)
        report["stages"]["OATS_LAYER_B"] = layer_b
        if layer_b.get("status") != "ok":
            report["status"] = "violation"
        if verbose:
            _print_violation_gate("OATS Layer B", layer_b)

        # 6. Materialization Step 2: A ∪ O → MO
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

        if verbose:
            _print_banner(report["status"])

        return report


# ---------------------------------------------------------------------------
# Verbose rendering helpers
# ---------------------------------------------------------------------------

_W = 70


def _sep(char: str = "-") -> str:
    return char * _W


def _status_tag(status: str) -> str:
    tags = {"ok": "[OK]", "warning": "[WARN]", "violation": "[FAIL]"}
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
        # Group by predicate
        by_pred: Dict[str, List] = {}
        for t in unc_triples:
            p = _short(t.get("p", "?p"))
            by_pred.setdefault(p, []).append(t)
        print(f"  Unclassified rejected  ({len(unc_triples)}) — {len(by_pred)} distinct predicates:")
        for pred, triples in sorted(by_pred.items()):
            print(f"    {pred}  ({len(triples)} triple(s))")
            for t in triples:
                print("      " + _fmt_row(t).strip())
    else:
        print("  Unclassified rejected  : 0")


def _print_violation_gate(label: str, r: Dict[str, Any]) -> None:
    tag = _status_tag(r["status"])
    violations: List = r.get("violations", [])
    print()
    print(_sep("="))
    print(f" {label}  {tag}")
    print(_sep("-"))
    if not violations:
        print("  No violations detected.")
        return
    for v in violations:
        q    = v["query"]
        cnt  = v["count"]
        rows = v.get("triples", [])
        print(f"  {q}  -- {cnt} violation(s):")
        for t in rows:
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
        for row in r.get("triples", []):
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


def _print_banner(overall_status: str) -> None:
    tag = _status_tag(overall_status)
    print()
    print(_sep("="))
    print(f" PIPELINE RESULT  {tag}")
    print(_sep("="))
    print()
