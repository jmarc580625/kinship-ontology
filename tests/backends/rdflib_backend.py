"""
RDFLib in-memory backend for testing.

Graph separation
----------------
TBox  -- ontology files (property definitions, axioms, materialization scripts).
         Populated from ``ontology_files`` passed to the constructor.
ABox  -- instance/assertion data.
         Populated from ``data_files`` passed to the constructor.
graph -- unified working graph (TBox + ABox + inferred triples).
         All queries and SPARQL UPDATEs operate against this graph.

Note: a dedicated MBox for materialized triples is out of scope for now;
materialised triples are written directly into ``graph`` by execute_update().
"""

from rdflib import Graph, Dataset, URIRef
from typing import List, Dict, Any, Optional, Union
import os
import sys

try:
    import owlrl
    OWLRL_AVAILABLE = True
except ImportError:
    OWLRL_AVAILABLE = False

try:
    from pyshacl import validate as pyshacl_validate
    PYSHACL_AVAILABLE = True
except ImportError:
    PYSHACL_AVAILABLE = False

_URN_MATS   = URIRef("urn:kinship:mats")
_URN_VALIDATION = URIRef("urn:kinship:validation")


class RDFLibBackend:
    """In-memory RDFLib backend for fast local testing."""

    def __init__(
        self,
        ontology_files: Union[str, List[str]],
        data_files: List[str] = None,
        shacl_shapes: Optional[str] = None,
    ):
        """
        Initialise RDFLib backend.

        Parameters
        ----------
        ontology_files:
            One or more TTL files that form the TBox (ontology axioms,
            property definitions, materialization scripts).  A single
            string is also accepted for backward compatibility.
        data_files:
            TTL files that form the ABox (instance/assertion data).
        shacl_shapes:
            Optional path to a SHACL shapes TTL file.  When provided the
            backend switches to Dataset mode (named-graph support) and
            runs pySHACL validation after materialization.
        """
        if isinstance(ontology_files, str):
            ontology_files = [ontology_files]
        self.ontology_files: List[str] = ontology_files
        self.data_files: List[str] = data_files or []
        self.shacl_shapes: Optional[str] = shacl_shapes

        self.tbox:  Graph = None   # TBox -- ontology axioms only
        self.abox:  Graph = None   # ABox -- raw instance data only
        self.graph: Graph = None   # Working graph = TBox + ABox + inferred
        self.dataset: Optional[Dataset] = None  # Dataset mode (when shacl_shapes)

    def initialize(self):
        """Load TBox and ABox into memory, then apply initial OWL-RL reasoning."""
        self.tbox  = Graph()
        self.abox  = Graph()
        self.graph = Graph()

        # --- TBox ---
        for ttl in self.ontology_files:
            if not os.path.exists(ttl):
                print(f"\n Error: Ontology file not found: {ttl}", file=sys.stderr)
                sys.exit(1)
            print(f"Loading ontology: {ttl}")
            self._parse_into(ttl, self.tbox)

        # --- ABox ---
        for ttl in self.data_files:
            if not os.path.exists(ttl):
                print(f"\n Error: Data file not found: {ttl}", file=sys.stderr)
                sys.exit(1)
            print(f"Loading data:     {ttl}")
            self._parse_into(ttl, self.abox)

        # Build unified working graph (TBox + ABox)
        for triple in self.tbox:
            self.graph.add(triple)
        for triple in self.abox:
            self.graph.add(triple)

        # Copy namespace bindings
        for prefix, ns in self.tbox.namespaces():
            if prefix:
                self.graph.bind(prefix, ns)

        # Apply initial OWL-RL reasoning (single pass - owlrl reaches fixpoint internally)
        self.trigger_reasoning(initial_load=True)

        # --- Dataset mode (when SHACL shapes are declared) ---
        if self.shacl_shapes:
            self._init_dataset()

    def _init_dataset(self):
        """Build a Dataset with named graphs for SHACL validation.

        Named graphs populated:
          <urn:kinship:mats>   — raw ABox data (before inference)
          default graph            — full working graph (TBox + ABox + inferred)
        """
        self.dataset = Dataset()

        # Populate the asserted named graph with ABox data
        asserted_g = self.dataset.graph(_URN_MATS)
        for triple in self.abox:
            asserted_g.add(triple)

        # Populate the default graph with the full working graph
        default_g = self.dataset.default_context
        for triple in self.graph:
            default_g.add(triple)

        # Copy namespace bindings
        for prefix, ns in self.graph.namespaces():
            if prefix:
                self.dataset.bind(prefix, ns)
                asserted_g.bind(prefix, ns)

    def run_shacl_validation(self):
        """Run pySHACL validation and store the report in <urn:kinship:validation>.

        Requires the Dataset to be initialised (call after materialization).
        """
        if not PYSHACL_AVAILABLE:
            raise RuntimeError(
                "pySHACL is not installed. pip install pyshacl"
            )
        if not self.dataset:
            raise RuntimeError(
                "Dataset not initialised. Ensure shacl_shapes is set."
            )
        if not self.shacl_shapes or not os.path.exists(self.shacl_shapes):
            raise RuntimeError(
                f"SHACL shapes file not found: {self.shacl_shapes}"
            )

        # Refresh the default graph in the dataset with current working graph
        # (which now includes materialized triples)
        default_g = self.dataset.default_context
        for triple in self.graph:
            default_g.add(triple)

        # Load shapes
        shapes_graph = Graph()
        shapes_graph.parse(self.shacl_shapes, format="turtle")

        print(f"Running pySHACL validation with {self.shacl_shapes}...")
        try:
            result = pyshacl_validate(
                data_graph=self.dataset,
                shacl_graph=shapes_graph,
                advanced=True,
                inference="none",
            )
        except Exception as exc:
            raise RuntimeError(f"pySHACL validate() raised: {type(exc).__name__}: {exc}") from exc

        # pyshacl.validate returns a 3-tuple (conforms, report_graph, report_text)
        if not isinstance(result, tuple):
            raise RuntimeError(
                f"pySHACL returned {type(result).__name__} instead of tuple: {result}"
            )
        conforms, report_graph, report_text = result

        # pySHACL may return a ValidationFailure object instead of a Graph
        # (see https://github.com/RDFLib/pySHACL#errors)
        if not isinstance(report_graph, Graph):
            msg = getattr(report_graph, 'message', str(report_graph))
            raise RuntimeError(
                f"pySHACL ValidationFailure: {msg}"
            )

        # Store validation report into the validation named graph
        validation_g = self.dataset.graph(_URN_VALIDATION)
        for triple in report_graph:
            validation_g.add(triple)

        # Count results
        from rdflib.namespace import SH
        result_count = sum(
            1 for _ in report_graph.subjects(
                URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
                URIRef("http://www.w3.org/ns/shacl#ValidationResult")
            )
        )
        status = "conforms" if conforms else f"{result_count} violation(s)"
        print(f"  SHACL validation: {status}")

        return conforms, result_count

    def trigger_reasoning(self, initial_load=False):
        """Apply OWL-RL reasoning over the unified working graph."""
        if not self.graph:
            return 0

        if OWLRL_AVAILABLE:
            before = len(self.graph)
            owlrl.DeductiveClosure(owlrl.RDFS_OWLRL_Semantics).expand(self.graph)
            inferred = len(self.graph) - before
            if initial_load:
                print(
                    f"TBox {len(self.tbox)} triples | ABox {len(self.abox)} triples"
                    f" | inferred {inferred} additional triples"
                )
            return inferred
        else:
            if initial_load:
                print(
                    f"TBox {len(self.tbox)} triples | ABox {len(self.abox)} triples"
                    " (OWL-RL reasoning not available -- pip install owlrl)"
                )
            return 0

    @staticmethod
    def _strip_rdfstar(file_path: str) -> str:
        """Return file content with RDF-star quoted-triple statements removed.

        Lines containing ``<< ... >>`` subject annotations (RDF-star / Turtle-star)
        are dropped because rdflib's Turtle parser does not support them.
        Multi-line statements starting with ``<<`` are consumed until their
        terminating ``.``.
        """
        import re
        out_lines = []
        inside_star = False
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if inside_star:
                    # Consume continuation lines until statement-ending '.'
                    if re.search(r"\.\s*$", line):
                        inside_star = False
                    continue
                if re.match(r"\s*<<", line):
                    # RDF-star statement start
                    if not re.search(r"\.\s*$", line):
                        inside_star = True
                    continue
                out_lines.append(line)
        return "".join(out_lines)

    def _parse_into(self, file_path: str, graph: Graph):
        """Parse a TTL file into *graph* with enhanced error reporting.

        Falls back to stripping RDF-star quoted triples (``<< … >>``) when the
        standard Turtle parser rejects the file, since rdflib does not yet
        support Turtle-star.
        """
        import logging as _logging
        _rdflib_logger = _logging.getLogger("rdflib.term")
        _prev_level = _rdflib_logger.level
        _rdflib_logger.setLevel(_logging.ERROR)
        try:
            graph.parse(file_path, format="turtle")
            return
        except Exception as exc:
            # --- Fallback: strip RDF-star and retry --------------------------
            import re as _re
            with open(file_path, "r", encoding="utf-8") as _f:
                _has_star = any(_re.match(r"\s*<<", ln) for ln in _f)
            if _has_star:
                cleaned = self._strip_rdfstar(file_path)
                try:
                    from io import StringIO
                    graph.parse(StringIO(cleaned), format="turtle")
                    print(f"  [INFO] {os.path.basename(file_path)}: "
                          "RDF-star annotations stripped (unsupported by rdflib)")
                    return
                except Exception:
                    pass  # Fall through to original error reporting
            # --- Original error reporting ------------------------------------
            msg = f"\n{'='*80}\nTURTLE SYNTAX ERROR\n{'='*80}\nFile: {file_path}\n"
            err = str(exc)
            if hasattr(exc, "lines"):
                msg += f"Line: {exc.lines}\n"
            msg += "\nCommon issues to check:\n"
            msg += "  * Missing period (.) at end of statement\n"
            msg += "  * Missing semicolon (;) between properties\n"
            msg += "  * Unclosed brackets [ ] or ( )\n"
            msg += "  * Invalid prefix or namespace\n"
            msg += "  * Special characters in URIs not escaped\n"
            if hasattr(exc, "lines") and exc.lines:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    ln = exc.lines
                    msg += f"\nContext around line {ln}:\n" + "-" * 80 + "\n"
                    for i in range(max(0, ln - 4), min(len(lines), ln + 3)):
                        marker = ">>> " if i == ln - 1 else "    "
                        msg += f"{marker}{i+1:4d} | {lines[i]}"
                    msg += "-" * 80 + "\n"
                except Exception:
                    pass
            msg += f"\nOriginal error: {err}\n{'='*80}\n"
            raise RuntimeError(msg) from exc
        finally:
            _rdflib_logger.setLevel(_prev_level)

    def execute_tbox_query(self, sparql_query: str) -> List[Dict[str, Any]]:
        """Execute a SPARQL SELECT query against the TBox only (pre-reasoning)."""
        if not self.tbox:
            return []
        results = self.tbox.query(sparql_query)
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

    def execute_abox_query(self, sparql_query: str) -> List[Dict[str, Any]]:
        """Execute a SPARQL SELECT query against the ABox only (no TBox, no inference)."""
        if not self.abox:
            raise RuntimeError("Backend not initialized. Call initialize() first.")
        results = self.abox.query(sparql_query)
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

    def execute_query(self, sparql_query: str) -> List[Dict[str, Any]]:
        """Execute a SPARQL SELECT or ASK query and return results.

        When the backend is in Dataset mode and the query contains GRAPH
        clauses, queries are routed to the Dataset for named-graph support.
        Otherwise queries run against the flat working graph.
        """
        if not self.graph:
            raise RuntimeError("Backend not initialized. Call initialize() first.")

        # Route to dataset when GRAPH clauses are present
        target = self.graph
        if self.dataset and "GRAPH" in sparql_query:
            target = self.dataset

        results = target.query(sparql_query)
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

    def execute_update(self, sparql_update: str) -> int:
        """Execute a SPARQL UPDATE (INSERT/DELETE) and return triples added."""
        if not self.graph:
            raise RuntimeError("Backend not initialized. Call initialize() first.")
        before = len(self.graph)
        self.graph.update(sparql_update)
        return len(self.graph) - before

    def reset(self):
        """Reset all graphs and reload from scratch."""
        self.tbox = self.abox = self.graph = self.dataset = None
        self.initialize()

    def get_stats(self) -> Dict[str, Any]:
        """Return triple counts for each graph layer."""
        if not self.graph:
            return {"status": "not initialized"}
        return {
            "backend":    "rdflib",
            "tbox":       len(self.tbox)  if self.tbox  else 0,
            "abox":       len(self.abox)  if self.abox  else 0,
            "working":    len(self.graph),
            "namespaces": list(dict(self.graph.namespaces()).keys()),
        }

    def cleanup(self):
        """Release all graph resources."""
        self.tbox = self.abox = self.graph = self.dataset = None
