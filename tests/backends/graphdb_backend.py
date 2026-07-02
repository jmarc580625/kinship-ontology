"""
GraphDB backend for testing with full OWL2-RL reasoning.
"""

import platform
import re
import requests
import time
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

_URN_ASSERTED   = "urn:kinship:asserted"
_URN_VALIDATION = "urn:kinship:validation"


TBOX_GRAPH = "urn:tbox"


class GraphDBBackend:
    """GraphDB backend with REST API integration."""

    def __init__(
        self,
        ontology_files: Union[str, List[str]],
        data_files: List[str] = None,
        graphdb_url: str = "http://localhost:7200",
        repository_id: str = "family-ontology-test",
        ruleset: str = "owl2-rl",
        shacl_shapes: Optional[str] = None,
    ):
        """
        Initialize GraphDB backend.

        Parameters
        ----------
        ontology_files:
            One or more TTL files that form the TBox.  A single string is
            also accepted for backward compatibility.
        data_files:
            TTL files that form the ABox (instance/assertion data).
        graphdb_url:
            GraphDB server URL.
        repository_id:
            Repository name.
        ruleset:
            Inference ruleset (owl2-rl, rdfs, etc.).
        shacl_shapes:
            Optional path to a SHACL shapes TTL file.  When provided the
            backend also loads ABox data into <urn:kinship:asserted> and
            exposes run_shacl_validation().
        """
        if isinstance(ontology_files, str):
            ontology_files = [ontology_files]
        self.ontology_files: List[str] = ontology_files
        self.data_files: List[str] = data_files or []
        self.shacl_shapes: Optional[str] = shacl_shapes
        self.graphdb_url = graphdb_url.rstrip('/')
        self.repository_id = repository_id
        self.ruleset = ruleset
        self.repo_url = f"{self.graphdb_url}/repositories/{self.repository_id}"
        
    def _wait_for_graphdb(self, timeout: int = 60):
        """Wait for GraphDB to be ready."""
        print(f"Waiting for GraphDB at {self.graphdb_url} (timeout {timeout}s)...")
        start_time = time.time()

        while True:
            elapsed = int(time.time() - start_time)
            try:
                response = requests.get(
                    f"{self.graphdb_url}/rest/repositories", timeout=5,
                )
                if response.status_code == 200:
                    print("[OK] GraphDB is ready")
                    return True
            except requests.exceptions.RequestException:
                pass

            if elapsed >= timeout:
                break
            remaining = timeout - elapsed
            print(f"  ... no response ({remaining}s remaining)", flush=True)
            time.sleep(2)

        self._print_graphdb_help()
        raise SystemExit(1)

    @staticmethod
    def _print_graphdb_help():
        """Print platform-specific instructions for starting GraphDB."""
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
        """Check if repository exists."""
        try:
            response = requests.get(f"{self.graphdb_url}/rest/repositories/{self.repository_id}")
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    
    def _delete_repository(self):
        """Delete existing repository."""
        if self._repository_exists():
            print(f"Deleting repository: {self.repository_id}")
            response = requests.delete(f"{self.graphdb_url}/rest/repositories/{self.repository_id}")
            if response.status_code in [200, 204]:
                print("[OK] Repository deleted")
                time.sleep(2)  # Wait for deletion to complete
            else:
                raise RuntimeError(f"Failed to delete repository: {response.status_code} {response.text}")
    
    def _create_repository(self):
        """Create new repository with specified ruleset."""
        print(f"Creating repository: {self.repository_id} with ruleset: {self.ruleset}")
        
        # Repository configuration in JSON format for GraphDB 10.x REST API
        config = {
            "id": self.repository_id,
            "title": "Family Ontology Test Repository",
            "type": "graphdb",
            "params": {
                "ruleset": {
                    "label": "Ruleset",
                    "name": "ruleset",
                    "value": self.ruleset
                },
                "baseURL": {
                    "label": "Base URL",
                    "name": "baseURL",
                    "value": "http://example.org/family#"
                },
                "defaultNS": {
                    "label": "Default namespaces for imports(';' delimited)",
                    "name": "defaultNS",
                    "value": ""
                },
                "imports": {
                    "label": "Imported RDF files(';' delimited)",
                    "name": "imports",
                    "value": ""
                }
            }
        }
        
        headers = {'Content-Type': 'application/json'}
        response = requests.post(
            f"{self.graphdb_url}/rest/repositories",
            json=config,
            headers=headers
        )
        
        if response.status_code in [200, 201]:
            print("[OK] Repository created")
            time.sleep(2)  # Wait for creation to complete
        else:
            raise RuntimeError(f"Failed to create repository: {response.status_code} {response.text}")
    
    def _load_file(self, file_path: str, context: str = None):
        """Load RDF file into repository."""
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        print(f"Loading: {file_path}" + (f" → <{context}>" if context else ""))

        with open(file_path, 'rb') as f:
            data = f.read()

        headers = {'Content-Type': 'text/turtle'}
        params = {}
        if context:
            params['context'] = f"<{context}>"

        response = requests.post(
            f"{self.repo_url}/statements",
            data=data,
            headers=headers,
            params=params
        )

        if response.status_code in [200, 204]:
            print(f"[OK] Loaded: {Path(file_path).name}")
        else:
            raise RuntimeError(f"Failed to load file: {response.status_code} {response.text}")

    def _get_size(self) -> int:
        """Return current total triple count in the repository."""
        try:
            response = requests.get(f"{self.repo_url}/size")
            if response.status_code == 200:
                return int(response.text)
        except Exception:
            pass
        return 0
    
    def initialize(self):
        """Initialize GraphDB repository and load data."""
        self._wait_for_graphdb()
        self._delete_repository()
        self._create_repository()

        # TBox -- named graph only.
        # GraphDB reasons globally across all graphs, so OWL-RL inferences
        # (inverseOf, propertyChain, etc.) are derived from TBox axioms here
        # even though they are not in the default graph.
        for ontology_file in self.ontology_files:
            self._load_file(ontology_file, TBOX_GRAPH)

        # ABox -- default graph only.
        # execute_query() (no FROM) sees: default graph (ABox) + implicit
        # graph (all inferences).  execute_tbox_query() targets <urn:tbox>.
        for data_file in self.data_files:
            self._load_file(data_file)

        # When SHACL shapes are declared, also load ABox into a named graph
        # so that SPARQL constraints can use GRAPH <urn:kinship:asserted>.
        if self.shacl_shapes:
            for data_file in self.data_files:
                self._load_file(data_file, context=_URN_ASSERTED)

        time.sleep(2)  # let reasoner settle

        stats = self.get_stats()
        print(f"[OK] Repository initialized with {stats.get('total_statements', '?')} statements")
    
    def execute_tbox_query(self, sparql_query: str) -> List[Dict[str, Any]]:
        """
        Execute a SPARQL SELECT query against the TBox only (pre-reasoning).

        Injects a ``FROM <urn:tbox>`` clause so that only explicitly loaded
        ontology triples are queried (no ABox data, no inferred triples).
        """
        modified = re.sub(
            r'\bWHERE\b',
            f'FROM <{TBOX_GRAPH}> WHERE',
            sparql_query,
            count=1,
            flags=re.IGNORECASE,
        )
        return self.execute_query(modified)

    def execute_abox_query(self, sparql_query: str) -> List[Dict[str, Any]]:
        """
        Execute a SPARQL SELECT query against the ABox only (no inference).

        Injects ``FROM <http://www.ontotext.com/explicit>`` — the GraphDB
        virtual graph that contains **only** explicitly asserted triples.
        OWL-RL inferred triples (including inverseOf derivations) are
        structurally absent from this graph, so no ``includeInferred``
        parameter is needed.
        """
        _EXPLICIT = 'http://www.ontotext.com/explicit'
        modified = re.sub(
            r'\bWHERE\b',
            f'FROM <{_EXPLICIT}> WHERE',
            sparql_query,
            count=1,
            flags=re.IGNORECASE,
        )
        return self.execute_query(modified)

    def execute_query(self, sparql_query: str) -> List[Dict[str, Any]]:
        """
        Execute SPARQL SELECT or ASK query and return results.

        Returns
        -------
        List of result bindings as dictionaries.  ASK queries return
        ``[{"result": True/False}]``.
        """
        headers = {
            'Accept': 'application/sparql-results+json',
            'Content-Type': 'application/sparql-query',
        }

        response = requests.post(
            self.repo_url,
            data=sparql_query.encode('utf-8'),
            headers=headers
        )

        if response.status_code != 200:
            raise RuntimeError(f"Query failed: {response.status_code} {response.text}")

        result = response.json()

        if 'boolean' in result:
            return [{'result': result['boolean']}]

        if 'results' in result and 'bindings' in result['results']:
            return [
                {var: binding[var]['value'] for var in binding}
                for binding in result['results']['bindings']
            ]

        return []
    
    def execute_update(self, sparql_update: str) -> int:
        """
        Execute SPARQL UPDATE query and return number of triples added.

        Returns
        -------
        Number of triples added (negative if triples were deleted on net).
        """
        before = self._get_size()

        headers = {'Content-Type': 'application/sparql-update'}
        response = requests.post(
            f"{self.repo_url}/statements",
            data=sparql_update.encode('utf-8'),
            headers=headers
        )

        if response.status_code not in [200, 204]:
            raise RuntimeError(f"Update failed: {response.status_code} {response.text}")

        added = self._get_size() - before
        print(f"[OK] Update executed (+{added} triples)")
        return added
    
    def reset(self):
        """Reset repository (delete and reload data)."""
        self.initialize()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get repository statistics."""
        total = self._get_size()
        return {
            "backend":          "graphdb",
            "repository":       self.repository_id,
            "total_statements": total,
            "working":          total,
            "url":              self.graphdb_url,
        }
    
    def run_shacl_validation(self):
        """Run SHACL validation via GraphDB bulk validation REST API.

        Uploads the shapes file, receives the validation report as Turtle,
        and stores it in <urn:kinship:validation>.
        """
        if not self.shacl_shapes or not Path(self.shacl_shapes).exists():
            raise RuntimeError(
                f"SHACL shapes file not found: {self.shacl_shapes}"
            )

        # Clear previous validation report
        clear_query = f"CLEAR GRAPH <{_URN_VALIDATION}>"
        headers = {'Content-Type': 'application/sparql-update'}
        resp = requests.post(
            f"{self.repo_url}/statements",
            data=clear_query.encode('utf-8'),
            headers=headers,
        )
        if resp.status_code not in [200, 204]:
            print(f"  Warning: could not clear validation graph: {resp.status_code}")

        # Bulk validation via file upload
        print(f"Running SHACL validation with {self.shacl_shapes}...")
        with open(self.shacl_shapes, 'rb') as f:
            resp = requests.post(
                f"{self.graphdb_url}/rest/repositories/"
                f"{self.repository_id}/validate/file",
                files={'file': (Path(self.shacl_shapes).name, f,
                                'text/turtle')},
                headers={'Accept': 'text/turtle'},
            )

        if resp.status_code != 200:
            raise RuntimeError(
                f"SHACL validation failed: {resp.status_code} "
                f"{resp.text[:500]}"
            )

        # Replace GraphDB built-in rdf4j:nil with standard rdf:nil
        # so the report can be stored as regular data.
        # Handle both full-URI and prefixed forms.
        report_turtle = resp.text
        report_turtle = report_turtle.replace(
            '<http://rdf4j.org/schema/rdf4j#nil>',
            '<http://www.w3.org/1999/02/22-rdf-syntax-ns#nil>')
        report_turtle = re.sub(
            r'\brdf4j:nil\b', 'rdf:nil', report_turtle)

        # Store the validation report in <urn:kinship:validation>
        store_resp = requests.post(
            f"{self.repo_url}/statements",
            data=report_turtle.encode('utf-8'),
            headers={'Content-Type': 'text/turtle'},
            params={'context': f'<{_URN_VALIDATION}>'},
        )
        if store_resp.status_code not in [200, 204]:
            raise RuntimeError(
                f"Failed to store validation report: {store_resp.status_code} "
                f"{store_resp.text[:500]}"
            )

        # Count results
        count_query = (
            "PREFIX sh: <http://www.w3.org/ns/shacl#> "
            f"SELECT (COUNT(?r) AS ?cnt) WHERE {{ "
            f"GRAPH <{_URN_VALIDATION}> {{ "
            f"?r a sh:ValidationResult . }} }}"
        )
        count_result = self.execute_query(count_query)
        result_count = int(count_result[0].get('cnt', '0')) if count_result else 0
        conforms = result_count == 0
        status = "conforms" if conforms else f"{result_count} violation(s)"
        print(f"  SHACL validation: {status}")

        return conforms, result_count

    def cleanup(self):
        """Cleanup resources (optionally delete repository)."""
        # Keep repository for inspection unless explicitly deleted
        pass