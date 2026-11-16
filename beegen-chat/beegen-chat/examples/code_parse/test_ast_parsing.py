import ast
import inspect
import textwrap
import types
from typing import Dict, Set, List, Tuple, Callable, Any


class FuncExporter:
    """
    Utility for exporting a function's source code with its dependencies and minimal imports.
    """

    def extract_calls(self, tree: ast.AST) -> Set[str]:
        """Extract function and method calls from AST."""
        calls = set()
        
        class CallVisitor(ast.NodeVisitor):
            def visit_Call(self, node):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
                self.generic_visit(node)
                
        CallVisitor().visit(tree)
        return calls

    def extract_imports(self, tree: ast.AST) -> List[Tuple[str, ast.AST]]:
        """Extract import statements from AST."""
        imports = []
        
        class ImportVisitor(ast.NodeVisitor):
            def visit_Import(self, node):
                imports.append((ast.unparse(node), node))
                
            def visit_ImportFrom(self, node):
                imports.append((ast.unparse(node), node))
                
        ImportVisitor().visit(tree)
        return imports

    def extract_names(self, tree: ast.AST) -> Set[str]:
        """Extract variable and attribute names from AST."""
        names = set()
        
        class NameVisitor(ast.NodeVisitor):
            def visit_Name(self, node):
                names.add(node.id)
                self.generic_visit(node)
                
            def visit_Attribute(self, node):
                if isinstance(node.value, ast.Name):
                    names.add(node.value.id)
                names.add(node.attr)
                self.generic_visit(node)
                
        NameVisitor().visit(tree)
        return names

    def filter_imports(self, imports: List[Tuple[str, ast.AST]], used_names: Set[str]) -> List[str]:
        """Filter imports to include only those relevant to used names."""
        direct_imports = set()
        from_imports = {}
        
        for _, node in imports:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split('.')[0]
                    if module in used_names:
                        direct_imports.add(module)
            elif isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
                for alias in node.names:
                    if alias.name in used_names:
                        from_imports.setdefault(module, set()).add(alias.name)
        
        result = []
        for module in direct_imports:
            result.append(f"import {module}")
            
        for module, names in from_imports.items():
            result.append(f"from {module} import {', '.join(sorted(names))}")
            
        return sorted(result)

    def export(self, function: Callable) -> str:
        """
        Export a function with its dependencies and minimal imports.
        
        Args:
            function: The function to export
            
        Returns:
            Complete source code with dependencies and imports
        """
        module = inspect.getmodule(function)
        module_source = textwrap.dedent(inspect.getsource(module))
        module_tree = ast.parse(module_source)
        
        # Get all module functions
        module_funcs = {
            name: obj for name, obj in vars(module).items()
            if isinstance(obj, types.FunctionType)
        }
        
        imports = self.extract_imports(module_tree)
        processed_funcs = set()
        code_snippets = []
        used_names = set()
        
        def process_function(func):
            if func.__name__ in processed_funcs:
                return
                
            processed_funcs.add(func.__name__)
            func_source = textwrap.dedent(inspect.getsource(func))
            func_tree = ast.parse(func_source)
            
            # Update used names
            used_names.update(self.extract_names(func_tree))
            code_snippets.append(func_source)
            
            # Process called functions
            for call in self.extract_calls(func_tree):
                if call in module_funcs:
                    process_function(module_funcs[call])
        
        # Start processing from the target function
        process_function(function)
        
        # Get relevant imports and combine everything
        filtered_imports = self.filter_imports(imports, used_names)
        return "\n".join(filtered_imports) + "\n\n" + "\n\n".join(reversed(code_snippets))


# Example usage
if __name__ == "__main__":
    import datetime
    
    def log_analytics(query: str, history: List[str]) -> Dict[str, Any]:
        """Log query analytics."""
        print(f"ANALYTICS: Logging query: {query}")
        return {
            "logged_at": datetime.datetime.now().isoformat(),
            "query_length": len(query),
            "history_count": len(history)
        }
    
    print(FuncExporter().export(log_analytics))