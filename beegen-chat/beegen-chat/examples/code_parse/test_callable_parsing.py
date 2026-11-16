import inspect
import ast
import textwrap
from typing import Callable, Set, Optional


class CallableToString:
    """
    Singleton class for converting callable functions to string representations
    with dependency resolution.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CallableToString, cls).__new__(cls)
            cls._instance._visited_funcs = set()
        return cls._instance

    def convert(self, func: Callable) -> str:
        """
        Convert a callable to a string representation with all dependencies and imports.
        
        Args:
            func: The callable function to convert
            
        Returns:
            str: Complete code string including imports and dependencies
        """
        # Reset visited functions for a new conversion
        self._visited_funcs = set()
        
        # Get module where the function is defined
        module = inspect.getmodule(func)
                
        # Extract imports from module
        imports = self._extract_imports(module)
                
        # Find dependencies
        deps = self._find_dependencies(func)
                
        # Get dependent function sources
        dep_sources = self._get_dependency_sources(deps, module)
        
        # Get the function's source
        func_source = inspect.getsource(func)
        func_source = self._normalize_indentation(func_source)
        
        # Combine everything into a complete code string
        return '\n'.join(imports) + '\n\n' + '\n\n'.join(dep_sources) + '\n\n' + func_source

    def _extract_imports(self, module) -> list:
        """Extract all import statements from a module."""
        try:
            module_source = inspect.getsource(module)
            module_ast = ast.parse(module_source)
            
            imports = []
            for node in module_ast.body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    imports.append(ast.unparse(node))
            
            return imports
        except (TypeError, OSError):
            # Handle built-in modules or modules without source
            return []

    def _find_dependencies(self, func: Callable, current_depth: int = 0, max_depth: int = 100) -> Set[str]:
        """Find all function dependencies recursively."""
        # Avoid infinite recursion or excessive depth
        if current_depth > max_depth:
            return set()
            
        func_name = func.__name__
        if func_name in self._visited_funcs:
            return set()
        
        self._visited_funcs.add(func_name)
        
        # Parse function to find calls
        source = inspect.getsource(func)
        # Dedent the source code to handle indentation properly
        source = self._normalize_indentation(source)
        tree = ast.parse(source)
        
        # Extract function calls
        calls = set()
        
        class CallVisitor(ast.NodeVisitor):
            def visit_Call(self, node):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                self.generic_visit(node)
        
        visitor = CallVisitor()
        visitor.visit(tree)
        
        # Get the module where function is defined
        module = inspect.getmodule(func)
        
        # Process each called function
        all_deps = set()
        for call_name in calls:
            if hasattr(module, call_name):
                called_func = getattr(module, call_name)
                if callable(called_func):
                    # Add the function itself
                    all_deps.add(call_name)
                    # Recursively find its dependencies
                    nested_deps = self._find_dependencies(
                        called_func, 
                        current_depth + 1,
                        max_depth
                    )
                    all_deps.update(nested_deps)
        
        return all_deps

    def _normalize_indentation(self, source: str) -> str:
        """Remove leading indentation from source code."""
        return textwrap.dedent(source)
        
    def _get_dependency_sources(self, deps: Set[str], module) -> list:
        """Get source code for all dependencies."""
        sources = []
        for dep_name in deps:
            if hasattr(module, dep_name):
                dep_func = getattr(module, dep_name)
                if callable(dep_func):
                    # Get source and normalize indentation
                    dep_source = inspect.getsource(dep_func)
                    dep_source = self._normalize_indentation(dep_source)
                    sources.append(dep_source)
        return sources


# Usage example:
if __name__ == "__main__":
    from beegenerate.utils.code_parser import parse_function
    from .calculate import calculate
    
    # Get the converter instance
    converter = CallableToString()
    
    # Convert the function to a string
    code_str = converter.convert(parse_function)
    print(code_str)