"""
Base test runner with common functionality.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional


class BaseTestRunner:
    """Base class for test runners."""
    
    def __init__(self, backend, test_file: str, verbose: bool = False):
        """
        Initialize test runner.
        
        Args:
            backend: Backend instance (RDFLibBackend or GraphDBBackend)
            test_file: Path to test definitions JSON file
            verbose: If True, show results even for passing tests
        """
        self.backend = backend
        self.test_file = test_file
        self.verbose = verbose
        self.test_suite = self._load_tests()
        self.results = {
            'total': 0,
            'passed': 0,
            'failed': 0,
            'details': {}
        }
    
    def _load_tests(self) -> Dict:
        """Load test definitions from JSON file."""
        with open(self.test_file, 'r') as f:
            return json.load(f)
    
    def normalize_results(self, results: List[Dict]) -> List[Dict]:
        """Normalize query results for comparison."""
        if not results:
            return []
        
        # Handle ASK queries
        if len(results) == 1 and 'result' in results[0]:
            return results
        
        # Normalize URIs for comparison (remove prefix variations)
        normalized = []
        for row in results:
            normalized_row = {}
            for key, value in row.items():
                # Convert value to string first (handles rdflib URIRef, Literal, etc.)
                value_str = str(value)
                
                # Normalize the value (handle different URI representations)
                # Convert full URIs to prefixed form if possible
                if 'http://example.org/kinship#' in value_str:
                    value_str = ':' + value_str.split('#')[-1]
                
                normalized_row[key] = value_str
            normalized.append(normalized_row)
        
        return normalized
    
    def _ensure_prefix(self, query: str) -> str:
        """Ensure query has the kinship ontology PREFIX declaration."""
        prefix = "PREFIX : <http://example.org/kinship#>"
        if prefix not in query and "PREFIX :" not in query:
            return f"{prefix}\n{query}"
        return query
    
    def run_test(self, test_id: str, test_case: Dict) -> bool:
        """
        Run a single test case.
        
        Args:
            test_id: Test identifier (e.g., "0.1.1")
            test_case: Test case definition
            
        Returns:
            True if test passed, False otherwise
        """
        print(f"\n{'='*80}")
        print(f"Test {test_id}: {test_case['name']}")
        print(f"Description: {test_case['description']}")
        
        try:
            # Execute query (ensure PREFIX is present)
            query = self._ensure_prefix(test_case['query'].strip())
            results = self.backend.execute_query(query)
            actual = self.normalize_results(results)
            expected = test_case['expected']
            
            # Sort both for consistent comparison (SPARQL ORDER BY can vary)
            actual_sorted = sorted(actual, key=lambda x: str(sorted(x.items())))
            expected_sorted = sorted(expected, key=lambda x: str(sorted(x.items())))
            
            # Compare results
            if actual_sorted == expected_sorted:
                print("[PASS] PASS")
                
                # Show results in verbose mode
                if self.verbose:
                    print("\nExpected:")
                    print(json.dumps(expected, indent=2))
                    print("\nActual:")
                    print(json.dumps(actual, indent=2))
                
                self.results['passed'] += 1
                self.results['details'][test_id] = {
                    'status': 'PASS',
                    'name': test_case['name'],
                    'message': 'All assertions passed'
                }
                return True
            else:
                print("[FAIL] FAIL")
                print("\nExpected:")
                print(json.dumps(expected, indent=2))
                print("\nActual:")
                print(json.dumps(actual, indent=2))
                
                self.results['failed'] += 1
                self.results['details'][test_id] = {
                    'status': 'FAIL',
                    'name': test_case['name'],
                    'expected': expected,
                    'actual': actual,
                    'message': 'Results do not match expected values'
                }
                
                # Provide analysis
                self._analyze_failure(test_id, expected, actual)
                return False
                
        except Exception as e:
            error_msg = f"[FAIL] ERROR: {str(e)}"
            print(error_msg)
            self.results['failed'] += 1
            self.results['details'][test_id] = {
                'status': 'ERROR',
                'name': test_case['name'],
                'message': str(e)
            }
            return False
    
    def _analyze_failure(self, test_id: str, expected: List, actual: List):
        """Analyze test failure and provide suggestions."""
        print("\n" + "-"*80)
        print("FAILURE ANALYSIS:")
        
        if len(actual) == 0 and len(expected) > 0:
            print("[FAIL] No results returned (expected results)")
            print("→ Possible causes:")
            print("  * Property chain axiom not supported by reasoner")
            print("  * Inference not triggered")
            print("  * Missing data")
            print("\n→ Suggested action:")
            print(f"  * Create materialization query for this relationship")
            print(f"  * Check ontology axioms for test {test_id}")
        elif len(actual) < len(expected):
            print(f"[FAIL] Partial results ({len(actual)}/{len(expected)})")
            missing = [e for e in expected if e not in actual]
            print("→ Missing results:")
            for m in missing:
                print(f"  * {m}")
        elif len(actual) > len(expected):
            print(f"[FAIL] Too many results ({len(actual)}/{len(expected)})")
            extra = [a for a in actual if a not in expected]
            print("→ Extra results:")
            for e in extra:
                print(f"  * {e}")
        else:
            print("[FAIL] Results differ in content")
            print("→ Check value formatting and URI prefixes")
        
        print("-"*80)
    
    def run_tests(self, test_ids: Optional[List[str]] = None) -> Dict:
        """
        Run multiple tests.
        
        Args:
            test_ids: List of test IDs to run. If None, run all tests.
            
        Returns:
            Results dictionary
        """
        # Get tests to run
        if test_ids:
            # Validate that all requested test IDs exist
            invalid_ids = [tid for tid in test_ids if tid not in self.test_suite['tests']]
            if invalid_ids:
                available_ids = sorted(self.test_suite['tests'].keys())
                raise ValueError(
                    f"Test ID(s) not found: {', '.join(invalid_ids)}\n"
                    f"Available test IDs: {', '.join(available_ids)}"
                )
            
            tests_to_run = [(tid, self.test_suite['tests'][tid]) for tid in test_ids]
        else:
            tests_to_run = sorted(
                self.test_suite['tests'].items(),
                key=lambda x: tuple(map(int, x[0].split('.')))
            )
        
        self.results['total'] = len(tests_to_run)
        
        # Run tests
        for test_id, test_case in tests_to_run:
            self.run_test(test_id, test_case)
        
        # Print summary
        self._print_summary()
        
        return self.results
    
    def _print_summary(self):
        """Print test execution summary."""
        print("\n" + "="*80)
        print("TEST SUITE SUMMARY")
        print("="*80)
        print(f"Backend: {self.backend.get_stats().get('backend', 'unknown')}")
        print(f"Total:   {self.results['total']}")
        print(f"Passed:  {self.results['passed']} [PASS]")
        print(f"Failed:  {self.results['failed']} [FAIL]")
        
        if self.results['failed'] > 0:
            print("\nFailed tests:")
            for test_id, details in self.results['details'].items():
                if details['status'] in ['FAIL', 'ERROR']:
                    test_name = details.get('name', '')
                    print(f"  * {test_id} ({test_name}): {details.get('message', 'Unknown error')}")
        
        print("="*80)
    
    def save_results(self, output_file: str = "test_results.json"):
        """Save test results to JSON file."""
        with open(output_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"\n📄 Results saved to: {output_file}")