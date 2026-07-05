"""
GraphDB-backed implementation of the kinship pipeline backend.

Communicates with a remote GraphDB repository via its REST API.  GraphDB
provides native OWL-RL reasoning, named-graph support and SPARQL UPDATE.
"""

import platform
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import requests

from .base import KinshipBackend


class GraphDBKinshipBackend(KinshipBackend):
    """Remote GraphDB backend for the consistency pipeline."""

    def __init__(
        self,
        ontology_files: Optional[List[Union[str, Path]]] = None,
        data_files: Optional[List[Union[str, Path]]] = None,
        *,
        shacl_shapes: Optional[Union[str, Path]] = None,
        graphdb_url: str = "http://localhost:7200",
        repository_id: str = "kinship-pipeline-test",
        ruleset: str = "owl2-rl",
    ) -> None:
        self.ontology_files: List[Union[str, Path]] = ontology_files or []
        self.data_files: List[Union[str, Path]] = data_files or []
        self.shacl_shapes: Optional[Union[str, Path]] = shacl_shapes
        self.graphdb_url = graphdb_url.rstrip("/")
        self.repository_id = repository_id
        self.ruleset = ruleset
        self.repo_url = f"{self.graphdb_url}/repositories/{self.repository_id}"
        self.ontology_graph = "urn:kinship:ontology"
        self.shapes_graph = "urn:kinship:shapes"
        self.validation_graph = "urn:kinship:validation"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Create the GraphDB repository and load TBox/ABox.

        The repository is created with the configured ruleset so that it
        is available, but inference is immediately switched off (empty
        ruleset) before any data is loaded.  The pipeline controls when
        inference is re-enabled via ``enable_inference()``.
        """
        self._wait_for_graphdb()
        self._delete_repository()
        self._create_repository()

        # Switch to empty ruleset BEFORE loading anything.
        self.disable_inference()

        for ttl in self.ontology_files:
            self.load_ontology(ttl, graph=self.ontology_graph)
        if self.shacl_shapes:
            self.load_ontology(self.shacl_shapes, graph=self.shapes_graph)
        for ttl in self.data_files:
            self.load_data(ttl, graph="urn:kinship:asserted")

        time.sleep(1)

    def clear_graph(self, graph_uri: str) -> None:
        """Clear the named graph."""
        self.execute_update(f"CLEAR GRAPH <{graph_uri}>")

    def cleanup(self) -> None:
        """Delete the test repository."""
        self._delete_repository()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_ontology(self, files, *, graph="urn:kinship:ontology") -> None:
        """Load TBox TTL file(s) into the ontology graph."""
        for ttl in self._as_list(files):
            self._load_file(ttl, context=graph)

    def load_data(self, files, *, graph="urn:kinship:asserted") -> None:
        """Load ABox TTL file(s) into the target graph."""
        for ttl in self._as_list(files):
            self._load_file(ttl, context=graph)

    # ------------------------------------------------------------------
    # Graph operations
    # ------------------------------------------------------------------

    def copy_graph(self, source: str, target: str) -> None:
        """Copy triples from source to target."""
        self.execute_update(f"COPY GRAPH <{source}> TO GRAPH <{target}>")

    def move_graph(self, source: str, target: str) -> None:
        """Move triples from source to target."""
        self.execute_update(f"MOVE GRAPH <{source}> TO GRAPH <{target}>")

    def add_to_graph(self, source: str, target: str) -> None:
        """Union source into target."""
        self.execute_update(f"ADD GRAPH <{source}> TO GRAPH <{target}>")

    def graph_size(self, graph: Optional[str] = None) -> int:
        """Return triple count."""
        if graph:
            query = (
                f"SELECT (COUNT(*) AS ?cnt) FROM <{graph}> WHERE "
                "{ ?s ?p ?o }"
            )
        else:
            query = "SELECT (COUNT(*) AS ?cnt) WHERE { ?s ?p ?o }"
        results = self.execute_query(query)
        if results:
            return int(results[0].get("cnt", "0"))
        return 0

    def export_graph(self, graph: str) -> str:
        """Export a named graph as NTriples via GraphDB REST API."""
        headers = {"Accept": "text/plain"}  # NTriples
        params = {"context": f"<{graph}>", "infer": "false"}
        response = requests.get(
            f"{self.repo_url}/statements",
            headers=headers,
            params=params,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Export failed: {response.status_code} {response.text}")
        return response.text

    def import_graph(self, graph: str, ntriples: str) -> None:
        """Import NTriples data into a named graph via GraphDB REST API."""
        if not ntriples.strip():
            return
        headers = {"Content-Type": "text/plain"}  # NTriples
        params = {"context": f"<{graph}>"}
        response = requests.post(
            f"{self.repo_url}/statements",
            data=ntriples.encode("utf-8"),
            headers=headers,
            params=params,
        )
        if response.status_code not in (200, 204):
            raise RuntimeError(f"Import failed: {response.status_code} {response.text}")

    # ------------------------------------------------------------------
    # Inference control
    # ------------------------------------------------------------------

    def disable_inference(self) -> None:
        """Switch to the 'empty' ruleset so no inference is produced."""
        self.execute_update(
            'PREFIX sys: <http://www.ontotext.com/owlim/system#>\n'
            'INSERT DATA { _:b sys:addRuleset "empty" . '
            '_:b sys:defaultRuleset "empty" . }'
        )

    def enable_inference(self) -> None:
        """Switch back to the configured ruleset and reinfer from scratch."""
        self.execute_update(
            'PREFIX sys: <http://www.ontotext.com/owlim/system#>\n'
            f'INSERT DATA {{ _:b sys:defaultRuleset "{self.ruleset}" . '
            '_:b sys:reinfer [] . }'
        )
        time.sleep(2)

    # ------------------------------------------------------------------
    # Backend capabilities
    # ------------------------------------------------------------------

    @property
    def scope_where_to_graph(self) -> bool:
        """GraphDB inferences live in the default graph only.

        Unscoped WHERE is required so materialization scripts can see
        inferred super-properties (e.g. hasChild from hasBloodChild).
        Graph isolation is achieved by removing OATS data before Step 1.
        """
        return False

    # ------------------------------------------------------------------
    # Query / update
    # ------------------------------------------------------------------

    def execute_query(self, sparql: str) -> List[Dict[str, Any]]:
        """Run SPARQL SELECT/ASK."""
        headers = {
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/sparql-query",
        }
        response = requests.post(
            self.repo_url,
            data=sparql.encode("utf-8"),
            headers=headers,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Query failed: {response.status_code} {response.text}")
        result = response.json()
        if "boolean" in result:
            return [{"result": result["boolean"]}]
        if "results" in result and "bindings" in result["results"]:
            return [
                {var: binding[var]["value"] for var in binding}
                for binding in result["results"]["bindings"]
            ]
        return []

    def execute_update(self, sparql: str) -> Optional[int]:
        """Run SPARQL UPDATE."""
        before = self._get_size()
        headers = {"Content-Type": "application/sparql-update"}
        response = requests.post(
            f"{self.repo_url}/statements",
            data=sparql.encode("utf-8"),
            headers=headers,
        )
        if response.status_code not in [200, 204]:
            raise RuntimeError(f"Update failed: {response.status_code} {response.text}")
        return self._get_size() - before

    def trigger_reasoning(self, graph: Optional[str] = None) -> int:
        """GraphDB reasons automatically; return the inferred triple count.

        GraphDB's OWL-RL ruleset keeps inferred triples materialised as data
        is loaded.  This method simply counts the inferred statements in the
        repository (or the given graph) using the explicit-only graph.
        """
        explicit_graph = "http://www.ontotext.com/explicit"
        if graph:
            total = self.graph_size(graph)
            explicit = self._graph_size_explicit(graph)
        else:
            total = self._get_size()
            explicit = self._graph_size_explicit()
        return max(0, total - explicit)

    # ------------------------------------------------------------------
    # SHACL validation
    # ------------------------------------------------------------------

    def run_shacl_validation(
        self,
        shapes_graph: str = "urn:kinship:shapes",
        report_graph: str = "urn:kinship:validation",
    ) -> Tuple[bool, int]:
        """Run GraphDB SHACL validation and store the report.

        The shapes are expected to be loaded in ``shapes_graph`` already.
        The bulk validation endpoint is used and the returned Turtle report
        is stored in ``report_graph``.  Returns ``(conforms, violation_count)``.
        """
        if not self.shacl_shapes or not Path(self.shacl_shapes).exists():
            raise RuntimeError(f"SHACL shapes file not found: {self.shacl_shapes}")

        self.clear_graph(report_graph)

        with open(self.shacl_shapes, "rb") as f:
            response = requests.post(
                f"{self.graphdb_url}/rest/repositories/"
                f"{self.repository_id}/validate/file",
                files={"file": (Path(self.shacl_shapes).name, f, "text/turtle")},
                headers={"Accept": "text/turtle"},
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"SHACL validation failed: {response.status_code} {response.text[:500]}"
            )

        # GraphDB uses rdf4j:nil in the report; replace with standard rdf:nil
        # so the report can be stored as regular data.
        report_turtle = response.text
        report_turtle = report_turtle.replace(
            "<http://rdf4j.org/schema/rdf4j#nil>",
            "<http://www.w3.org/1999/02/22-rdf-syntax-ns#nil>",
        )
        report_turtle = re.sub(r"\brdf4j:nil\b", "rdf:nil", report_turtle)

        store_resp = requests.post(
            f"{self.repo_url}/statements",
            data=report_turtle.encode("utf-8"),
            headers={"Content-Type": "text/turtle"},
            params={"context": f"<{report_graph}>"},
        )
        if store_resp.status_code not in (200, 204):
            raise RuntimeError(
                f"Failed to store validation report: {store_resp.status_code} "
                f"{store_resp.text[:500]}"
            )

        count_query = (
            "PREFIX sh: <http://www.w3.org/ns/shacl#> "
            f"SELECT (COUNT(?r) AS ?cnt) WHERE {{ "
            f"GRAPH <{report_graph}> {{ ?r a sh:ValidationResult . }} }}"
        )
        count_result = self.execute_query(count_query)
        result_count = int(count_result[0].get("cnt", "0")) if count_result else 0
        conforms = result_count == 0
        return conforms, result_count

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

    def _load_file(self, file_path: Union[str, Path], context: Optional[str] = None):
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        print(f"Loading: {file_path}" + (f" -> <{context}>" if context else ""))
        headers = {"Content-Type": "text/turtle"}
        params = {}
        if context:
            params["context"] = f"<{context}>"
        with open(file_path, "rb") as f:
            response = requests.post(
                f"{self.repo_url}/statements",
                data=f.read(),
                headers=headers,
                params=params,
            )
        if response.status_code in [200, 204]:
            print(f"[OK] Loaded: {file_path.name}")
        else:
            raise RuntimeError(f"Failed to load file: {response.status_code} {response.text}")

    def _get_size(self) -> int:
        try:
            response = requests.get(f"{self.repo_url}/size")
            if response.status_code == 200:
                return int(response.text)
        except Exception:
            pass
        return 0

    def _graph_size_explicit(self, graph: Optional[str] = None) -> int:
        explicit = "http://www.ontotext.com/explicit"
        if graph:
            query = (
                f"SELECT (COUNT(*) AS ?cnt) FROM <{explicit}> "
                f"WHERE {{ GRAPH <{graph}> {{ ?s ?p ?o }} }}"
            )
        else:
            query = (
                f"SELECT (COUNT(*) AS ?cnt) FROM <{explicit}> "
                "WHERE { ?s ?p ?o }"
            )
        results = self.execute_query(query)
        if results:
            return int(results[0].get("cnt", "0"))
        return 0

    def _wait_for_graphdb(self, timeout: int = 60):
        print(f"Waiting for GraphDB at {self.graphdb_url} (timeout {timeout}s)...")
        start = time.time()
        while True:
            elapsed = int(time.time() - start)
            try:
                response = requests.get(
                    f"{self.graphdb_url}/rest/repositories", timeout=5
                )
                if response.status_code == 200:
                    print("[OK] GraphDB is ready")
                    return True
            except requests.exceptions.RequestException:
                pass
            if elapsed >= timeout:
                break
            print(f"  ... no response ({timeout - elapsed}s remaining)", flush=True)
            time.sleep(2)
        self._print_graphdb_help()
        raise SystemExit(1)

    @staticmethod
    def _print_graphdb_help():
        os_name = platform.system()
        print()
        print("=" * 70)
        print("ERROR: GraphDB is not reachable.")
        print("=" * 70)
        print()
        print("1. Install Docker Desktop (if not already installed):")
        if os_name == "Windows":
            print("     https://docs.docker.com/desktop/setup/install/windows-install/")
        elif os_name == "Darwin":
            print("     https://docs.docker.com/desktop/setup/install/mac-install/")
        else:
            print("     https://docs.docker.com/desktop/setup/install/linux-install/")
        print()
        print("2. Start the GraphDB container from the project root:")
        print("     docker compose up -d")
        print()
        print("3. Re-run the tests once GraphDB is healthy:")
        print("     python tests/test_runner.py --all --backend graphdb")
        print()

    def _repository_exists(self) -> bool:
        try:
            response = requests.get(
                f"{self.graphdb_url}/rest/repositories/{self.repository_id}"
            )
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def _delete_repository(self):
        if self._repository_exists():
            print(f"Deleting repository: {self.repository_id}")
            response = requests.delete(
                f"{self.graphdb_url}/rest/repositories/{self.repository_id}"
            )
            if response.status_code in [200, 204]:
                print("[OK] Repository deleted")
                time.sleep(2)
            else:
                raise RuntimeError(
                    f"Failed to delete repository: {response.status_code} {response.text}"
                )

    def _create_repository(self):
        print(f"Creating repository: {self.repository_id} with ruleset: {self.ruleset}")
        config = {
            "id": self.repository_id,
            "title": "Kinship Pipeline Test Repository",
            "type": "graphdb",
            "params": {
                "ruleset": {"label": "Ruleset", "name": "ruleset", "value": self.ruleset},
                "baseURL": {
                    "label": "Base URL",
                    "name": "baseURL",
                    "value": "http://example.org/family#",
                },
                "defaultNS": {
                    "label": "Default namespaces for imports(';' delimited)",
                    "name": "defaultNS",
                    "value": "",
                },
                "imports": {
                    "label": "Imported RDF files(';' delimited)",
                    "name": "imports",
                    "value": "",
                },
            },
        }
        headers = {"Content-Type": "application/json"}
        response = requests.post(
            f"{self.graphdb_url}/rest/repositories",
            json=config,
            headers=headers,
        )
        if response.status_code in [200, 201]:
            print("[OK] Repository created")
            time.sleep(2)
        else:
            raise RuntimeError(
                f"Failed to create repository: {response.status_code} {response.text}"
            )
