"""
RDFLib-backed implementation of the kinship pipeline backend.

Uses ``rdflib.Dataset`` for named-graph support.  The ontology is loaded into
``<urn:kinship:ontology>`` and data is loaded into the requested named graphs.
Reasoning is performed with owl-rl.
"""

import os
import sys
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from rdflib import Dataset, Graph, URIRef

from .base import KinshipBackend

try:
    import owlrl
    OWLRL_AVAILABLE = True
except ImportError:
    OWLRL_AVAILABLE = False

try:
    import pyshacl
    PYSHACL_AVAILABLE = True
except ImportError:
    PYSHACL_AVAILABLE = False


class RDFLibKinshipBackend(KinshipBackend):
    """In-memory RDFLib backend for the consistency pipeline."""

    def __init__(
        self,
        ontology_files: Optional[List[Union[str, Path]]] = None,
        data_files: Optional[List[Union[str, Path]]] = None,
        *,
        shacl_shapes: Optional[Union[str, Path]] = None,
    ) -> None:
        self.ontology_files: List[Union[str, Path]] = ontology_files or []
        self.data_files: List[Union[str, Path]] = data_files or []
        self.shacl_shapes: Optional[Union[str, Path]] = shacl_shapes
        self.dataset: Optional[Dataset] = None
        self.ontology_graph: str = "urn:kinship:ontology"
        self.shapes_graph: str = "urn:kinship:shapes"
        self.validation_graph: str = "urn:kinship:validation"
        self._inference_enabled: bool = True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Create the Dataset and load TBox/ABox/SHACL shapes.

        Inference is disabled during loading.  The pipeline controls
        when reasoning runs via ``enable_inference()``.
        """
        self.dataset = Dataset(default_union=True)
        self._inference_enabled = False

        for ttl in self.ontology_files:
            self.load_ontology(ttl, graph=self.ontology_graph)
        if self.shacl_shapes:
            self.load_ontology(self.shacl_shapes, graph=self.shapes_graph)
        for ttl in self.data_files:
            self.load_data(ttl, graph="urn:kinship:asserted")

    def clear_graph(self, graph_uri: str) -> None:
        """Clear the named graph."""
        if self.dataset is None:
            raise RuntimeError("Backend not initialized")
        g = self.dataset.graph(URIRef(graph_uri))
        g.remove((None, None, None))

    def cleanup(self) -> None:
        """Drop the in-memory dataset."""
        self.dataset = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_ontology(self, files, *, graph="urn:kinship:ontology") -> None:
        """Load TBox TTL file(s) into the ontology graph."""
        if self.dataset is None:
            raise RuntimeError("Backend not initialized")
        g = self.dataset.graph(URIRef(graph))
        for ttl in self._as_list(files):
            self._parse_into(ttl, g)

    def load_data(self, files, *, graph="urn:kinship:asserted") -> None:
        """Load ABox TTL file(s) into the target graph."""
        if self.dataset is None:
            raise RuntimeError("Backend not initialized")
        g = self.dataset.graph(URIRef(graph))
        for ttl in self._as_list(files):
            self._parse_into(ttl, g)

    # ------------------------------------------------------------------
    # Graph operations
    # ------------------------------------------------------------------

    def copy_graph(self, source: str, target: str) -> None:
        """Copy triples from source to target."""
        if self.dataset is None:
            raise RuntimeError("Backend not initialized")
        src = self.dataset.graph(URIRef(source))
        dst = self.dataset.graph(URIRef(target))
        dst.remove((None, None, None))
        for triple in src:
            dst.add(triple)

    def move_graph(self, source: str, target: str) -> None:
        """Move triples from source to target."""
        self.copy_graph(source, target)
        self.clear_graph(source)

    def add_to_graph(self, source: str, target: str) -> None:
        """Union source into target."""
        if self.dataset is None:
            raise RuntimeError("Backend not initialized")
        src = self.dataset.graph(URIRef(source))
        dst = self.dataset.graph(URIRef(target))
        for triple in src:
            dst.add(triple)

    def graph_size(self, graph: Optional[str] = None) -> int:
        """Return triple count."""
        if self.dataset is None:
            return 0
        if graph is None:
            return sum(len(g) for g in self.dataset.graphs())
        return len(self.dataset.graph(URIRef(graph)))

    def export_graph(self, graph: str) -> str:
        """Serialize a named graph as NTriples."""
        if self.dataset is None:
            raise RuntimeError("Backend not initialized")
        g = self.dataset.graph(URIRef(graph))
        return g.serialize(format="nt")

    def import_graph(self, graph: str, ntriples: str) -> None:
        """Load NTriples data into a named graph."""
        if self.dataset is None:
            raise RuntimeError("Backend not initialized")
        g = self.dataset.graph(URIRef(graph))
        g.parse(data=ntriples, format="nt")

    # ------------------------------------------------------------------
    # Inference control
    # ------------------------------------------------------------------

    def disable_inference(self) -> None:
        """Prevent trigger_reasoning from running until re-enabled."""
        self._inference_enabled = False

    def enable_inference(self) -> None:
        """Re-enable reasoning and run a full reasoning pass now."""
        self._inference_enabled = True
        self.trigger_reasoning()

    # ------------------------------------------------------------------
    # Query / update
    # ------------------------------------------------------------------

    def execute_query(self, sparql: str) -> List[Dict[str, Any]]:
        """Run SPARQL SELECT/ASK."""
        if self.dataset is None:
            raise RuntimeError("Backend not initialized")
        results = self.dataset.query(sparql)
        if isinstance(results, bool):
            return [{"result": results}]
        out = []
        for row in results:
            row_dict = {}
            for var in results.vars:
                value = row[var]
                if value is not None:
                    row_dict[str(var)] = str(value)
            out.append(row_dict)
        return out

    def execute_update(self, sparql: str) -> Optional[int]:
        """Run SPARQL UPDATE."""
        if self.dataset is None:
            raise RuntimeError("Backend not initialized")
        before = self.graph_size()
        self.dataset.update(sparql)
        return self.graph_size() - before

    def trigger_reasoning(self, graph: Optional[str] = None) -> int:
        """Apply OWL-RL reasoning and return inferred triple count.

        Inferred triples are stored in the default (global/implicit) graph,
        matching GraphDB behavior.  Named graphs such as ``mats-closure`` and
        ``full`` therefore contain only materialized triples produced by the
        materialization scripts.

        When ``graph`` is provided, reasoning is limited to the union of the
        ontology graph and that named graph.  Otherwise the entire dataset is
        reasoned over.

        Returns 0 immediately if inference has been disabled.
        """
        if self.dataset is None or not OWLRL_AVAILABLE:
            return 0
        if not self._inference_enabled:
            return 0

        # Clear the default graph before re-reasoning so stale inferences are
        # removed.  Explicit triples are never loaded into the default graph.
        self.dataset.default_context.remove((None, None, None))

        temp = Graph()
        # Always include the ontology
        for triple in self.dataset.graph(URIRef(self.ontology_graph)):
            temp.add(triple)
        if graph:
            for triple in self.dataset.graph(URIRef(graph)):
                temp.add(triple)
        else:
            # Reason over all named graphs except the default graph, which was
            # just cleared.
            default_id = self.dataset.default_context.identifier
            for g in self.dataset.graphs():
                if g.identifier == default_id:
                    continue
                for triple in g:
                    temp.add(triple)

        before = len(temp)
        owlrl.DeductiveClosure(owlrl.RDFS_OWLRL_Semantics).expand(temp)
        inferred = len(temp) - before
        if inferred <= 0:
            return 0

        # Store inferences in the default graph, not in the target named graph.
        target = self.dataset.default_graph
        ontology_triples = set(self.dataset.graph(URIRef(self.ontology_graph)))

        added = 0
        for triple in temp:
            if triple in ontology_triples:
                continue
            target_before = len(target)
            target.add(triple)
            if len(target) > target_before:
                added += 1
        return added

    # ------------------------------------------------------------------
    # SHACL validation
    # ------------------------------------------------------------------

    def run_shacl_validation(
        self,
        shapes_graph: str = "urn:kinship:shapes",
        report_graph: str = "urn:kinship:validation",
    ) -> Tuple[bool, int]:
        """Run pySHACL over the whole dataset and store the report.

        Shapes are read from the named ``shapes_graph``; the validation
        report is written into ``report_graph``.  Returns
        ``(conforms, violation_count)``.
        """
        if not PYSHACL_AVAILABLE:
            raise RuntimeError("pySHACL is not installed")
        if self.dataset is None:
            raise RuntimeError("Backend not initialized")

        shapes_g = self.dataset.graph(URIRef(shapes_graph))
        if len(shapes_g) == 0 and not self.shacl_shapes:
            raise RuntimeError("No SHACL shapes loaded")

        self.clear_graph(report_graph)

        result = pyshacl.validate(
            data_graph=self.dataset,
            shacl_graph=shapes_g,
            advanced=True,
            inference="none",
            abort_on_first=False,
        )
        if not isinstance(result, tuple) or len(result) != 3:
            raise RuntimeError(f"pySHACL returned unexpected result: {result!r}")

        conforms, report_g, report_text = result
        if not isinstance(report_g, Graph):
            msg = getattr(report_g, "message", str(report_g))
            raise RuntimeError(f"pySHACL validation failure: {msg}")

        validation_g = self.dataset.graph(URIRef(report_graph))
        for triple in report_g:
            validation_g.add(triple)

        violation_count = sum(
            1
            for _ in report_g.subjects(
                URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
                URIRef("http://www.w3.org/ns/shacl#ValidationResult"),
            )
        )
        return bool(conforms), int(violation_count)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _as_list(files) -> List[Union[str, Path]]:
        if files is None:
            return []
        if isinstance(files, (str, Path)):
            return [files]
        return list(files)

    @staticmethod
    def _parse_into(file_path: str, graph: Graph):
        """Parse a TTL file into *graph* with RDF-star fallback."""
        import logging as _logging
        import re
        _rdflib_logger = _logging.getLogger("rdflib.term")
        _prev_level = _rdflib_logger.level
        _rdflib_logger.setLevel(_logging.ERROR)
        try:
            try:
                graph.parse(file_path, format="turtle")
                return
            except Exception as exc:
                with open(file_path, "r", encoding="utf-8") as f:
                    has_star = any(re.match(r"\s*<<", ln) for ln in f)
                if has_star:
                    cleaned = RDFLibKinshipBackend._strip_rdfstar(file_path)
                    try:
                        graph.parse(StringIO(cleaned), format="turtle")
                        print(f"  [INFO] {os.path.basename(file_path)}: "
                              "RDF-star annotations stripped (unsupported by rdflib)")
                        return
                    except Exception:
                        pass
                raise RuntimeError(f"Failed to parse {file_path}: {exc}") from exc
        finally:
            _rdflib_logger.setLevel(_prev_level)

    @staticmethod
    def _strip_rdfstar(file_path: str) -> str:
        """Return file content with RDF-star quoted-triple statements removed."""
        import re
        out_lines = []
        inside_star = False
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if inside_star:
                    if re.search(r"\.\s*$", line):
                        inside_star = False
                    continue
                if re.match(r"\s*<<", line):
                    if not re.search(r"\.\s*$", line):
                        inside_star = True
                    continue
                out_lines.append(line)
        return "".join(out_lines)
