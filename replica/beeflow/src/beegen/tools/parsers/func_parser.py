from abc import ABC, abstractmethod
from typing import Dict, Any, Set, Optional, List, Callable
from dataclasses import dataclass
from .docstring_parser import DocstringParser
import ast
import textwrap


@dataclass
class ParsedFunction:
    """Data class representing parsed function information."""
    name: str
    parameters: Dict[str, Dict[str, Any]]  # param_name -> {type, default, description, required}
    return_info: Optional[Dict[str, str]] = None
    description: Optional[str] = None
    calls: Optional[Set[str]] = None
    callable: Optional[Callable] = None  # Add this field
    source: Optional[str] = None  # Add this to store the source
    
    def execute(self, *args, **kwargs) -> Any:
        """Execute the compiled function with given arguments."""
        if self.callable is None:
            raise ValueError(f"Function '{self.name}' is not compiled")
        return self.callable(*args, **kwargs)
    
    def is_callable(self) -> bool:
        """Check if the function is compiled and callable."""
        return self.callable is not None


class FunctionParser(ABC):
    """Abstract base class for function parsers."""
    
    @abstractmethod
    def parse_function(self, source: str) -> ParsedFunction:
        """Parse function information from source code."""
        pass
    
    
class ASTFunctionParser(FunctionParser):
    """Concrete parser using Python AST for function analysis."""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.docstring_parser = DocstringParser()
    
    @classmethod
    def self(cls):
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def parse_function(self, source: str) -> ParsedFunction:
        """Parse function information from source code using AST."""
        import textwrap
        
        # Clean up source
        cleaned_source = textwrap.dedent(source).strip()
        
        tree = ast.parse(cleaned_source)
        visitor = self._FunctionVisitor(self.docstring_parser)
        visitor.visit(tree)
        
        # Find the main function (entry point - not called by others)
        main_func = self._find_main_function(visitor.functions, visitor.calls)
        
        if not main_func:
            raise ValueError("No function found in source code")
        
        # Compile the function
        try:
            namespace = {}
            exec(cleaned_source, namespace)
            compiled_func = namespace.get(main_func.name)
            
            # Update the main function with compiled version and source
            main_func.callable = compiled_func
            main_func.source = cleaned_source
            
        except Exception as e:
            print(f"Warning: Could not compile function '{main_func.name}': {e}")
            main_func.callable = None
            main_func.source = cleaned_source
        
        return main_func
    
    def _find_main_function(self, functions: List[ParsedFunction], calls: Dict[str, Set[str]]) -> Optional[ParsedFunction]:
        """Find the entry point function (not called by others)."""
        if not functions:
            return None
        
        # Collect all called function names
        all_called = set()
        for called_set in calls.values():
            all_called.update(called_set)
        
        # Return first function not called by others
        for func in functions:
            if func.name not in all_called:
                return func
        
        # Fallback to first function
        return functions[0]
    
    class _FunctionVisitor(ast.NodeVisitor):
        """AST visitor for extracting function information."""
        
        def __init__(self, docstring_parser: DocstringParser):
            self.docstring_parser = docstring_parser
            self.functions: List[ParsedFunction] = []
            self.calls: Dict[str, Set[str]] = {}
            self.current_func: Optional[str] = None

        def visit_FunctionDef(self, node: ast.FunctionDef):
            """Visit function definition and extract metadata."""
            func_name = node.name
            self.current_func = func_name
            self.calls[func_name] = set()
            
            # Extract docstring
            docstring = ast.get_docstring(node)
            
            # Parse parameter information
            parameters = self._extract_parameters(node, docstring)
            
            # Parse return information
            return_info = self.docstring_parser.parse_return_info(docstring)
            
            # Parse description
            description = self.docstring_parser.parse_description(docstring)
            
            # Create parsed function
            parsed_func = ParsedFunction(
                name=func_name,
                parameters=parameters,
                return_info=return_info,
                description=description,
                calls=set()  # Will be populated during call visits
            )
            
            self.functions.append(parsed_func)
            
            # Continue visiting child nodes
            self.generic_visit(node)
            self.current_func = None

        def visit_Call(self, node: ast.Call):
            """Visit function calls to track dependencies."""
            if isinstance(node.func, ast.Name) and self.current_func:
                self.calls[self.current_func].add(node.func.id)
            self.generic_visit(node)

        def _extract_parameters(self, node: ast.FunctionDef, docstring: Optional[str]) -> Dict[str, Dict[str, Any]]:
            """Extract parameter information from function definition."""
            parameters = {}
            
            # Get parameter types from annotations
            param_types = self._get_parameter_types(node)
            
            # Get default values
            defaults = self._get_default_values(node)
            
            # Get descriptions from docstring
            descriptions = self.docstring_parser.parse_parameter_descriptions(docstring or "")
            
            # Combine all parameter information
            for param_name, param_type in param_types.items():
                parameters[param_name] = {
                    'type': param_type,
                    'default': defaults.get(param_name),
                    'description': descriptions.get(param_name),
                    'required': param_name not in defaults
                }
            
            return parameters

        def _get_parameter_types(self, node: ast.FunctionDef) -> Dict[str, str]:
            """Extract parameter type annotations."""
            param_types = {}
            
            # Regular arguments
            for arg in node.args.args:
                param_types[arg.arg] = ast.unparse(arg.annotation) if arg.annotation else 'Any'
            
            # Keyword-only arguments
            for kwarg in node.args.kwonlyargs:
                param_types[kwarg.arg] = ast.unparse(kwarg.annotation) if kwarg.annotation else 'Any'
            
            return param_types

        def _get_default_values(self, node: ast.FunctionDef) -> Dict[str, Any]:
            """Extract default values from function arguments."""
            defaults = {}
            args = node.args
            
            # Handle regular arguments with defaults
            if args.defaults:
                num_defaults = len(args.defaults)
                num_args = len(args.args)
                default_offset = num_args - num_defaults
                
                for i, default_node in enumerate(args.defaults):
                    arg_index = default_offset + i
                    if arg_index < len(args.args):
                        param_name = args.args[arg_index].arg
                        defaults[param_name] = self._evaluate_default(default_node)
            
            # Handle keyword-only arguments with defaults
            if args.kw_defaults:
                for i, default_node in enumerate(args.kw_defaults):
                    if default_node is not None and i < len(args.kwonlyargs):
                        param_name = args.kwonlyargs[i].arg
                        defaults[param_name] = self._evaluate_default(default_node)
                        
            return defaults

        def _evaluate_default(self, default_node: ast.AST) -> Any:
            """Safely evaluate default value from AST node."""
            try:
                return ast.literal_eval(default_node)
            except (ValueError, TypeError):
                # For complex defaults, store as string representation
                return ast.unparse(default_node)
            
FUNC_PARSER = ASTFunctionParser.self()
            

def main():
    
    import inspect
        
    # Create test functions with different features
    def helper_function(x: int) -> int:
        """A helper function."""
        return x * 2
    
    from typing import List, Dict, Any


    def complex_function(
        name: str,
        age: int = 25,
        items: List[str] = None,
        active: bool = True
    ) -> Dict[str, Any]:
        """
        Process person information and return a structured data dictionary.
        
        This function takes personal information, processes the age through a helper
        function, and returns a standardized dictionary containing all relevant
        person data with processed values.
        
        Args:
            name (str): The person's full name. Must be a non-empty string.
            age (int, optional): The person's age in years. Must be a positive
                integer. Defaults to 25 if not provided.
            items (List[str], optional): A list of items associated with the person.
                Can be None or an empty list. Defaults to None, which will be
                converted to an empty list in the output.
            active (bool, optional): Indicates whether the person is currently
                active in the system. Defaults to True.
        
        Returns:
            Dict[str, Any]: A dictionary containing the processed person information
                with the following keys:
                - 'name' (str): The original name provided
                - 'processed_age' (Any): The age after processing by helper_function
                - 'items' (List[str]): The items list or empty list if None was provided
                - 'active' (bool): The active status
        
        Example:
            >>> result = complex_function("John Doe", 30, ["item1", "item2"])
            >>> print(result['name'])
            'John Doe'
            >>> print(result['items'])
            ['item1', 'item2']
        """
        result = helper_function(age)
        return {
            'name': name,
            'processed_age': result,
            'items': items or [],
            'active': active
        }
    
    from beegen.tools.services.function_analyzer import FUNC_ANALYZER
    
    func_info = FUNC_ANALYZER.analyze_function(complex_function)
    
    from beegen.tools.exporters.schema_exporter import OpenAISchemaExporter
        
    openai_schema = OpenAISchemaExporter.export_function_schema(
        function_name=func_info.name,
        function_description=func_info.description,
        param_set=func_info.input_schema
    )
    
    print(openai_schema['description'])


if __name__ == "__main__":
    main()