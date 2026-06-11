"""
Test executor with level support and materialization.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from .base_runner import BaseTestRunner


class TestExecutor:
    """Executes tests with dependency level support."""
    
    def __init__(self, backend, test_file: str, config_file: str, verbose: bool = False):
        """
        Initialize test executor.
        
        Args:
            backend: Backend instance
            test_file: Path to test definitions
            config_file: Path to test configuration
            verbose: If True, show results even for passing tests
        """
        self.backend = backend
        self.runner = BaseTestRunner(backend, test_file, verbose=verbose)
        self.config = self._load_config(config_file)
    
    def _load_config(self, config_file: str) -> Dict:
        """Load test configuration."""
        with open(config_file, 'r') as f:
            return json.load(f)
    
    def _resolve_script_path(self, script_path: str) -> str:
        """Resolve script path relative to project root."""
        # If already absolute, return as-is
        if Path(script_path).is_absolute():
            return script_path
        
        # Resolve relative to project root (parent of tests directory)
        tests_dir = Path(__file__).parent.parent
        project_root = tests_dir.parent
        resolved = project_root / script_path
        
        return str(resolved)
    
    def run_level(self, level: int, materialize: List[str] = None) -> Dict:
        """
        Run tests for a specific dependency level.
        
        Args:
            level: Dependency level (0-4)
            materialize: List of materialization script paths to apply (overrides config)
            
        Returns:
            Test results
        """
        level_str = str(level)
        if level_str not in self.config['test_levels']:
            raise ValueError(f"Invalid level: {level}. Must be 0-4")
        
        level_info = self.config['test_levels'][level_str]
        test_ids = level_info['tests']
        
        print(f"\n{'='*80}")
        print(f"RUNNING LEVEL {level}: {level_info['name']}")
        print(f"{'='*80}")
        print(f"Tests to run: {', '.join(test_ids)}")
        
        # If no explicit materialization provided, use config requirements
        if materialize is None:
            materialize_raw = self.config.get('materialization_requirements', {}).get(level_str, [])
            if materialize_raw:
                print(f"\nLoaded {len(materialize_raw)} materialization requirement(s) from config")
                # Resolve relative paths from project root
                materialize = [self._resolve_script_path(p) for p in materialize_raw]
            else:
                materialize = []
                print(f"\nNo materialization requirements found in config for level {level}")
        
        # Apply materialization scripts
        if materialize:
            print(f"\nApplying {len(materialize)} materialization script(s)...")
            for script_path in materialize:
                try:
                    self.apply_materialization(script_path)
                except FileNotFoundError as e:
                    print(f"\n❌ Error: {e}")
                    print(f"   Stopping test execution.")
                    return {'total': 0, 'passed': 0, 'failed': 0, 'details': {}, 'materialization_error': str(e)}
                except Exception as e:
                    print(f"\n❌ Error applying {Path(script_path).name}: {e}")
                    print(f"   Stopping test execution.")
                    return {'total': 0, 'passed': 0, 'failed': 0, 'details': {}, 'materialization_error': str(e)}
        
        # Run tests for this level
        results = self.runner.run_tests(test_ids)
        
        return results
    
    def apply_materialization(self, script_path: str):
        """
        Apply materialization script.
        
        Args:
            script_path: Path to SPARQL UPDATE script
        """
        if not Path(script_path).exists():
            raise FileNotFoundError(f"Materialization script not found: {script_path}")
        
        print(f"  • Applying: {Path(script_path).name}")
        
        with open(script_path, 'r') as f:
            sparql_update = f.read()
        
        triples_added = self.backend.execute_update(sparql_update)
        
        if triples_added == 0:
            print(f"    ⚠️  Applied but added 0 triples (may indicate an error or no matches)")
        else:
            print(f"    ✓ Applied successfully (added {triples_added} triples)")
    
    def verify_materialization(self, script_path: str) -> bool:
        """
        Verify that a materialization script works correctly.
        
        Args:
            script_path: Path to SPARQL UPDATE script
            
        Returns:
            True if verification passed
        """
        print(f"\n{'='*80}")
        print(f"VERIFYING MATERIALIZATION: {Path(script_path).name}")
        print(f"{'='*80}")
        
        # Get statement count before
        stats_before = self.backend.get_stats()
        count_before = stats_before.get('triples', stats_before.get('total_statements', 0))
        print(f"Statements before: {count_before}")
        
        # Apply materialization
        try:
            self.apply_materialization(script_path)
        except Exception as e:
            print(f"❌ Materialization failed: {e}")
            return False
        
        # Get statement count after
        stats_after = self.backend.get_stats()
        count_after = stats_after.get('triples', stats_after.get('total_statements', 0))
        print(f"Statements after:  {count_after}")
        
        added = count_after - count_before
        print(f"\n✅ Materialization successful")
        print(f"   Added {added} new statement(s)")
        
        return True
    
    def run_all_levels(self, start_level: int = 0, materialize_per_level: Dict[int, List[str]] = None):
        """
        Run all levels sequentially.
        
        Args:
            start_level: Starting level (default: 0)
            materialize_per_level: Dict mapping level to list of materialization scripts
        """
        materialize_per_level = materialize_per_level or {}
        all_results = {}
        
        for level in range(start_level, 4):  # Levels 0-3
            materialize = materialize_per_level.get(level, [])
            results = self.run_level(level, materialize)
            all_results[f"level_{level}"] = results
            
            # Stop if tests failed
            if results['failed'] > 0:
                print(f"\n⚠️  Level {level} has failures. Fix issues before proceeding to next level.")
                break
        
        return all_results