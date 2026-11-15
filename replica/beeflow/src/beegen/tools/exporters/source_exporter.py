from abc import abstractmethod, ABC
import ast
import inspect
import sys
from typing import Callable, Dict, List, Optional, Set, Tuple


class SourceExtractor(ABC):
    """Abstract base class for source code extractors."""
    
    @abstractmethod
    def extract_source(self, function: Callable) -> str:
        """Extract source code for a function with dependencies."""
        pass
    
    
class DependencySourceExtractor(SourceExtractor):
    """Extracts source code for functions with their dependencies."""
    
    def extract_source(self, function: Callable) -> str:
        """Extract function source code with all dependencies."""
        module = self._get_function_module(function)
        if not module:
            raise ValueError(f"Cannot find module for function {function.__name__}")
        
        try:
            module_source = inspect.getsource(module)
        except OSError:
            raise ValueError(f"Cannot get source for module {module.__name__}")
        
        return self._extract_function_with_dependencies(module_source, function.__name__)
    
    def _get_function_module(self, function: Callable):
        """Get the module containing the function."""
        module = inspect.getmodule(function)
        if module:
            return module
        
        # Fallback: search in sys.modules
        partial_module_name = getattr(function, "__module__", None)
        if not partial_module_name:
            return None
        
        for full_module_name, module_obj in list(sys.modules.items()):
            if module_obj is None:
                continue
            
            if (full_module_name.endswith("." + partial_module_name) or 
                full_module_name == partial_module_name):
                if hasattr(module_obj, function.__name__):
                    if getattr(module_obj, function.__name__) is function:
                        return module_obj
        
        return None
    
    def _extract_function_with_dependencies(self, module_source: str, target_function: str) -> str:
        """Extract function and its dependencies from module source."""
        tree = ast.parse(module_source)
        
        # Extract all function definitions and imports
        extractor = self._DependencyExtractor()
        extractor.visit(tree)
        
        # Build dependency graph and extract needed functions
        needed_functions = extractor.get_dependencies(target_function)
        
        # Combine imports and functions
        imports = extractor.get_filtered_imports(needed_functions)
        function_sources = [extractor.get_function_source(func) for func in needed_functions]
        
        return "\n".join(imports) + "\n\n" + "\n\n".join(reversed(function_sources))
    
    class _DependencyExtractor(ast.NodeVisitor):
        """Extract function dependencies from AST."""
        
        def __init__(self):
            self.functions: Dict[str, ast.FunctionDef] = {}
            self.imports: List[Tuple[str, ast.AST]] = []
            self.calls: Dict[str, Set[str]] = {}
            self.names: Dict[str, Set[str]] = {}
            self.current_func: Optional[str] = None

        def visit_FunctionDef(self, node: ast.FunctionDef):
            """Visit function definitions."""
            self.functions[node.name] = node
            self.current_func = node.name
            self.calls[node.name] = set()
            self.names[node.name] = set()
            
            # Extract names and calls from this function
            name_visitor = DependencySourceExtractor._NameExtractor()
            name_visitor.visit(node)
            self.names[node.name] = name_visitor.names
            
            self.generic_visit(node)
            self.current_func = None

        def visit_Call(self, node: ast.Call):
            """Visit function calls."""
            if isinstance(node.func, ast.Name) and self.current_func:
                self.calls[self.current_func].add(node.func.id)
            self.generic_visit(node)

        def visit_Import(self, node: ast.Import):
            """Visit import statements."""
            self.imports.append((ast.unparse(node), node))

        def visit_ImportFrom(self, node: ast.ImportFrom):
            """Visit from-import statements."""
            self.imports.append((ast.unparse(node), node))

        def get_dependencies(self, target_function: str) -> List[str]:
            """Get all dependencies for a target function."""
            if target_function not in self.functions:
                return []
            
            visited = set()
            result = []
            
            def visit_func(func_name: str):
                if func_name in visited or func_name not in self.functions:
                    return
                
                visited.add(func_name)
                
                # Visit dependencies first
                for called_func in self.calls.get(func_name, set()):
                    visit_func(called_func)
                
                result.append(func_name)
            
            visit_func(target_function)
            return result

        def get_function_source(self, func_name: str) -> str:
            """Get source code for a function."""
            if func_name not in self.functions:
                return ""
            
            try:
                return ast.unparse(self.functions[func_name])
            except:
                return f"# Could not extract source for {func_name}"

        def get_filtered_imports(self, needed_functions: List[str]) -> List[str]:
            """Get imports needed for the functions."""
            used_names = set()
            for func_name in needed_functions:
                used_names.update(self.names.get(func_name, set()))
            
            # Group imports by module and collect only used names
            module_imports = {}
            
            for import_str, import_node in self.imports:
                if isinstance(import_node, ast.ImportFrom) and import_node.module:
                    module_name = import_node.module
                    if module_name not in module_imports:
                        module_imports[module_name] = set()
                    
                    for alias in import_node.names:
                        if alias.name in used_names:
                            module_imports[module_name].add(alias.name)
                
                elif isinstance(import_node, ast.Import):
                    for alias in import_node.names:
                        module = alias.name.split('.')[0]
                        if module in used_names:
                            if 'direct' not in module_imports:
                                module_imports['direct'] = []
                            module_imports['direct'].append(import_str)
            
            # Build filtered import statements
            filtered_imports = []
            
            # Add direct imports
            if 'direct' in module_imports:
                filtered_imports.extend(module_imports['direct'])
            
            # Add from imports (merged by module)
            for module_name, names in module_imports.items():
                if module_name != 'direct' and names:
                    names_list = sorted(names)
                    filtered_imports.append(f"from {module_name} import {', '.join(names_list)}")
            
            return sorted(filtered_imports)

        def _import_is_needed(self, import_node: ast.AST, used_names: Set[str]) -> bool:
            """Check if an import statement is needed."""
            if isinstance(import_node, ast.Import):
                for alias in import_node.names:
                    module = alias.name.split('.')[0]
                    if module in used_names:
                        return True
            elif isinstance(import_node, ast.ImportFrom) and import_node.module:
                for alias in import_node.names:
                    if alias.name in used_names:
                        return True
            
            return False

    class _NameExtractor(ast.NodeVisitor):
        """Extract all names used in a function."""
        
        def __init__(self):
            self.names: Set[str] = set()

        def visit_Name(self, node: ast.Name):
            """Visit name nodes."""
            self.names.add(node.id)
            self.generic_visit(node)

        def visit_Attribute(self, node: ast.Attribute):
            """Visit attribute access."""
            if isinstance(node.value, ast.Name):
                self.names.add(node.value.id)
            self.names.add(node.attr)
            self.generic_visit(node)


def main():
    # Create some test functions with dependencies
    from typing import List, Dict, Any
    
    def helper_function(x: List):
        return x * 2
    
    def another_helper(y: int):
        return y + 1
    
    def main_function(a, b):
        result1 = helper_function(a)
        result2 = another_helper(b)
        return result1 + result2
    
    # Test the extractor
    extractor = DependencySourceExtractor()
    
    try:
        extracted_source = extractor.extract_source(main_function)
        print("Extracted source code:")
        print("=" * 50)
        print(extracted_source)
        print("=" * 50)
    except Exception as e:
        print(f"Error: {e}")
        

if __name__ == "__main__":
    main()