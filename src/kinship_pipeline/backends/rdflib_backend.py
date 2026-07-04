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
from typing import Any, Dict, List, Optional, Union

from rdflib import Dataset, Graph, URIRef

from .base import KinshipBackend

try:
    import owlrl
    OWLRL_AVAILABLE = True
except ImportError:
    OWLRL_AVAILABLE = False


class RDFLibKinshipBackend(KinshipBackend):
    """In-memory RDFLib backend for the consistency pipeline."""

    def __init__(
        self,
        ontology_files: Optional[List[Union[str, Path]]] = None,
        data_files: Optional[List[Union[str, Path]]] = None,
    ) -> None:
        self.ontology_files: List[Union[str, Path]] = ontology_files or []
        self.data_files: List[Union[str, Path]] = data_files or []
        self.dataset: Optional[Dataset] = None
        self.ontology_graph: str = "urn:kinship:ontology"
        self._inference_enabled: bool = True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Create the Dataset and load TBox/ABox.

        Inference is disabled during loading.  The pipeline controls
        when reasoning runs via ``enable_inference()``.
        """
        self.dataset = Dataset(default_union=True)
        self._inference_enabled = False

        for ttl in self.ontology_files:
            self.load_ontology(ttl, graph=self.ontology_graph)
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

        When ``graph`` is provided, reasoning is limited to the union of the
        ontology graph and that named graph.  Otherwise the entire dataset is
        reasoned over.

        Returns 0 immediately if inference has been disabled.
        """
        if self.dataset is None or not OWLRL_AVAILABLE:
            return 0
        if not self._inference_enabled:
            return 0

        temp = Graph()
        # Always include the ontology
        for triple in self.dataset.graph(URIRef(self.ontology_graph)):
            temp.add(triple)
        if graph:
            for triple in self.dataset.graph(URIRef(graph)):
                temp.add(triple)
        else:
            for g in self.dataset.graphs():
                for triple in g:
                    temp.add(triple)

        before = len(temp)
        owlrl.DeductiveClosure(owlrl.RDFS_OWLRL_Semantics).expand(temp)
        inferred = len(temp) - before
        if inferred <= 0:
            return 0

        target = self.dataset.graph(URIRef(graph)) if graph else self.dataset.default_graph
        ontology_triples = set(self.dataset.graph(URIRef(self.ontology_graph)))
        source_triples = set(self.dataset.graph(URIRef(graph))) if graph else set()

        added = 0
        for triple in temp:
            if triple in ontology_triples or triple in source_triples:
                continue
            target_before = len(target)
            target.add(triple)
            if len(target) > target_before:
                added += 1
        return added

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
