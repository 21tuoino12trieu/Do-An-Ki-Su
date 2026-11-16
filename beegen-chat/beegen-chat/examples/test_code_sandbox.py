import importlib
import sys
import os
import time
import subprocess
import concurrent.futures
import tempfile
import ast
import inspect
import contextlib
import io
from typing import Dict, List, Any, Callable, Union, Optional, Set, Tuple

class FastPythonEnvironment:
    """
    A Python environment that preloads common imports to speed up code execution.
    Provides both in-process execution and subprocess isolation options.
    """
    
    def __init__(self, preload_modules: List[str] = None):
        """
        Initialize the environment with preloaded modules.
        
        Args:
            preload_modules: List of module names to preload
        """
        # Default modules to preload if none specified
        self.preloaded_modules = preload_modules or [
            'numpy', 'pandas', 'matplotlib', 'scipy', 'sklearn', 
            'math', 'random', 'datetime', 'collections', 'itertools',
            'functools', 'os', 'sys', 'json', 're', 'pathlib',
            'time', 'csv', 'pickle', 'requests'
        ]
        
        # Namespace for preloaded modules
        self.globals = {}
        self._preload_modules()
        
        # Track execution time
        self.last_execution_time = 0
    
    def _preload_modules(self):
        """Preload all specified modules into the globals dictionary."""
        self.globals = globals().copy()  # Start with current globals
        
        # Add built-ins
        self.globals.update({
            'print': print,
            'len': len,
            'range': range,
            'list': list,
            'dict': dict,
            'set': set,
            'sum': sum,
            'min': min,
            'max': max,
            'enumerate': enumerate,
            'zip': zip,
            'map': map,
            'filter': filter,
            # Add more built-ins as needed
        })
        
        # Track which modules were successfully loaded
        self.loaded_modules = []
        self.failed_modules = []
        
        for module_name in self.preloaded_modules:
            try:
                # Try to import the module
                module = importlib.import_module(module_name)
                # Store in globals
                self.globals[module_name] = module
                self.loaded_modules.append(module_name)
            except (ImportError, ModuleNotFoundError):
                # Skip modules that aren't installed
                self.failed_modules.append(module_name)
    
    def run_code(self, code_string: str, capture_output: bool = True) -> Dict[str, Any]:
        """
        Execute Python code string in the preloaded environment.
        
        Args:
            code_string: Python code as a string
            capture_output: Whether to capture stdout/stderr
            
        Returns:
            Dictionary with execution results and metadata
        """
        # Prepare for output capturing if requested
        if capture_output:
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()
            redirect_context = contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture)
        else:
            redirect_context = contextlib.nullcontext(), contextlib.nullcontext()
        
        # Create a local namespace for this execution
        local_vars = {}
        
        # Track execution time
        start_time = time.time()
        
        # Execute the code
        result = {
            'success': True,
            'error': None,
            'error_type': None,
            'local_vars': {},
            'stdout': '',
            'stderr': '',
            'execution_time': 0
        }
        
        try:
            with redirect_context[0], redirect_context[1]:
                # Compile and execute the code
                compiled_code = compile(code_string, '<string>', 'exec')
                exec(compiled_code, self.globals.copy(), local_vars)
        except Exception as e:
            result['success'] = False
            result['error'] = str(e)
            result['error_type'] = type(e).__name__
        
        self.last_execution_time = time.time() - start_time
        result['execution_time'] = self.last_execution_time
        
        # Collect outputs
        if capture_output:
            result['stdout'] = stdout_capture.getvalue()
            result['stderr'] = stderr_capture.getvalue()
        
        # Return variables defined in the code
        result['local_vars'] = {
            k: v for k, v in local_vars.items() 
            if not k.startswith('_') and k != 'contextlib'
        }
        
        return result
    
    def run_code_isolated(self, code_string: str, timeout: int = 10) -> Dict[str, Any]:
        """
        Execute code in a separate process for isolation.
        
        Args:
            code_string: Python code as a string
            timeout: Maximum execution time in seconds
            
        Returns:
            Dictionary with execution results
        """
        # Create a temporary file with imports and code
        with tempfile.NamedTemporaryFile(suffix='.py', delete=False) as temp:
            # Add preload imports
            import_statements = []
            for module in self.loaded_modules:
                import_statements.append(f"import {module}")
            
            # Write imports and user code to file
            temp_content = "\n".join(import_statements) + "\n\n" + code_string
            temp.write(temp_content.encode())
            temp_path = temp.name
        
        result = {
            'success': True,
            'stdout': '',
            'stderr': '',
            'execution_time': 0,
            'timeout': False
        }
        
        try:
            # Run the Python code in a separate process
            start_time = time.time()
            proc = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            result['execution_time'] = time.time() - start_time
            result['stdout'] = proc.stdout
            result['stderr'] = proc.stderr
            result['returncode'] = proc.returncode
            result['success'] = proc.returncode == 0
            
        except subprocess.TimeoutExpired:
            result['success'] = False
            result['timeout'] = True
            result['error'] = f"Execution timed out after {timeout} seconds"
        except Exception as e:
            result['success'] = False
            result['error'] = str(e)
        finally:
            # Clean up the temporary file
            os.unlink(temp_path)
        
        return result
    
    def get_environment_info(self) -> Dict[str, Any]:
        """Return information about the environment."""
        return {
            'preloaded_modules': self.loaded_modules,
            'failed_modules': self.failed_modules,
            'last_execution_time': self.last_execution_time,
            'python_version': sys.version
        }

# Example usage
if __name__ == "__main__":
    # Create the environment (this is where modules are preloaded)
    env = FastPythonEnvironment()
    
    # Example 1: Simple calculation using preloaded math module
    code1 = """
import math
result = math.sin(math.pi/4)
print(f"Sin(π/4) = {result:.4f}")
"""
    
    # Example 2: Data analysis with preloaded pandas and numpy
    code2 = """
import pandas as pd
import numpy as np

# Create sample data
data = {
    'A': np.random.rand(5),
    'B': np.random.rand(5)
}
df = pd.DataFrame(data)
print(df)
print("\\nCorrelation:")
print(df.corr())
"""

    # Run examples
    print("Environment Info:")
    print(env.get_environment_info())
    print("\n" + "-"*50 + "\n")
    
    print("Example 1 (In-process):")
    result1 = env.run_code(code1)
    print(f"Output: {result1['stdout']}")
    print(f"Execution time: {result1['execution_time']:.6f} seconds")
    print("\n" + "-"*50 + "\n")
    
    print("Example 2 (In-process):")
    result2 = env.run_code(code2)
    print(f"Output: {result2['stdout']}")
    print(f"Execution time: {result2['execution_time']:.6f} seconds")
    print("\n" + "-"*50 + "\n")
    
    print("Example 1 (Isolated):")
    isolated_result = env.run_code_isolated(code1)
    print(f"Output: {isolated_result['stdout']}")
    print(f"Execution time: {isolated_result['execution_time']:.6f} seconds")