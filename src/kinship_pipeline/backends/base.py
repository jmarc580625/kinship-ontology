"""
Abstract backend contract for the kinship consistency pipeline.

A backend must provide named-graph operations and the ability to load
TBox/ABox data, execute SPARQL, and run SPARQL UPDATEs.  The pipeline
never reads or writes files directly; all state is managed through the
backend.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


class KinshipBackend(ABC):
    """Backend interface used by the consistency pipeline."""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def initialize(self) -> None:
        """Create connection, repository, or in-memory structures."""
        ...

    @abstractmethod
    def clear_graph(self, graph_uri: str) -> None:
        """Remove all triples from the named graph ``graph_uri``."""
        ...

    @abstractmethod
    def cleanup(self) -> None:
        """Release resources (close connections, delete repositories)."""
        ...

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @abstractmethod
    def load_ontology(self, files: Union[str, Path, List[Union[str, Path]]],
                      *, graph: str = "urn:kinship:ontology") -> None:
        """Load TBox TTL file(s) into the ontology graph."""
        ...

    @abstractmethod
    def load_data(self, files: Union[str, Path, List[Union[str, Path]]],
                  *, graph: str = "urn:kinship:mats") -> None:
        """Load ABox TTL file(s) into the target named graph."""
        ...

    # ------------------------------------------------------------------
    # Graph operations
    # ------------------------------------------------------------------

    @abstractmethod
    def copy_graph(self, source: str, target: str) -> None:
        """Copy all triples from ``source`` to ``target``."""
        ...

    @abstractmethod
    def move_graph(self, source: str, target: str) -> None:
        """Move all triples from ``source`` to ``target``."""
        ...

    @abstractmethod
    def add_to_graph(self, source: str, target: str) -> None:
        """Add all triples from ``source`` into ``target`` (union)."""
        ...

    @abstractmethod
    def graph_size(self, graph: Optional[str] = None) -> int:
        """Return the number of triples in the given graph."""
        ...

    def export_graph(self, graph: str) -> str:
        """Serialize a named graph as NTriples and return the string.

        Used by the pipeline to stash/restore graphs when isolation is needed.
        Default implementation uses CONSTRUCT query; backends may override.
        """
        rows = self.execute_query(
            f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }}"
        )
        # Fallback: shouldn't be reached if backends override properly.
        raise NotImplementedError("Backend must implement export_graph")

    def import_graph(self, graph: str, ntriples: str) -> None:
        """Load NTriples data into a named graph.

        Used by the pipeline to restore previously stashed graphs.
        Default implementation is not provided; backends must override.
        """
        raise NotImplementedError("Backend must implement import_graph")

    # ------------------------------------------------------------------
    # Query / update
    # ------------------------------------------------------------------

    @abstractmethod
    def execute_query(self, sparql: str) -> List[Dict[str, Any]]:
        """Execute a SPARQL SELECT/ASK and return bindings."""
        ...

    @abstractmethod
    def execute_update(self, sparql: str) -> Optional[int]:
        """Execute a SPARQL UPDATE and return the number of triples added."""
        ...

    @abstractmethod
    def trigger_reasoning(self, graph: Optional[str] = None) -> int:
        """Apply OWL-RL/RDFS reasoning and return the number of inferred triples.

        When ``graph`` is provided, the backend should reason on the union of
        the ontology graph and that named graph.  Otherwise it reasons over
        the entire dataset.
        """
        ...

    @abstractmethod
    def run_shacl_validation(
        self,
        shapes_graph: str = "urn:kinship:shapes",
        report_graph: str = "urn:kinship:validation",
    ) -> Tuple[bool, int]:
        """Run SHACL validation over the whole dataset and store the report.

        Returns ``(conforms, violation_count)``.  The report triples
        (``sh:ValidationResult``) are written into ``report_graph``.
        """
        ...

    # ------------------------------------------------------------------
    # Inference control
    # ------------------------------------------------------------------

    def disable_inference(self) -> None:
        """Turn off automatic/explicit reasoning.

        After this call, no new inferences should be produced when data
        is loaded or SPARQL UPDATEs are executed.  ``trigger_reasoning``
        becomes a no-op until ``enable_inference`` is called.

        The pipeline calls this before loading data and after
        materialization phases to prevent cross-graph contamination.
        """

    def enable_inference(self) -> None:
        """Re-enable reasoning and infer over all data currently in the store.

        This effectively runs a full reasoning pass over whatever data
        is present at the moment of the call.
        """

