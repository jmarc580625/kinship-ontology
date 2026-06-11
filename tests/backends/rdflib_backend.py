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

from rdflib import Graph
from typing import List, Dict, Any, Union
import os
import sys

try:
    import owlrl
    OWLRL_AVAILABLE = True
except ImportError:
    OWLRL_AVAILABLE = False


class RDFLibBackend:
    """In-memory RDFLib backend for fast local testing."""

    def __init__(
        self,
        ontology_files: Union[str, List[str]],
        data_files: List[str] = None,
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
        """
        if isinstance(ontology_files, str):
            ontology_files = [ontology_files]
        self.ontology_files: List[str] = ontology_files
        self.data_files: List[str] = data_files or []

        self.tbox:  Graph = None   # TBox -- ontology axioms only
        self.abox:  Graph = None   # ABox -- raw instance data only
        self.graph: Graph = None   # Working graph = TBox + ABox + inferred

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

        # Apply initial OWL-RL reasoning
        self.trigger_reasoning(initial_load=True)

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

    def _parse_into(self, file_path: str, graph: Graph):
        """Parse a TTL file into *graph* with enhanced error reporting."""
        try:
            graph.parse(file_path, format="turtle")
        except Exception as exc:
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
        """Execute a SPARQL SELECT or ASK query and return results."""
        if not self.graph:
            raise RuntimeError("Backend not initialized. Call initialize() first.")
        results = self.graph.query(sparql_query)
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
        self.tbox = self.abox = self.graph = None
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
        self.tbox = self.abox = self.graph = None
