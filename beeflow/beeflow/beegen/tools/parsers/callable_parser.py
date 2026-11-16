from abc import ABC, abstractmethod
import textwrap
from typing import Dict, Any, Set, Optional, List, Callable, get_type_hints
from dataclasses import dataclass
from .docstring_parser import DocstringParser
import inspect
import ast
 
 
@dataclass
class ParsedCallable:
    """Data class representing parsed callable information."""
    name: str
    parameters: Dict[str, Dict[str, Any]]  # param_name -> {type, default, description, required}
    return_info: Optional[Dict[str, str]] = None
    description: Optional[str] = None
    calls: Optional[Set[str]] = None
    callable: Optional[Callable] = None
    source: Optional[str] = None
    
    def execute(self, *args, **kwargs) -> Any:
        """Execute the callable with given arguments."""
        if self.callable is None:
            raise ValueError(f"Callable '{self.name}' is not available")
        return self.callable(*args, **kwargs)
    
    def is_callable(self) -> bool:
        """Check if the callable is available."""
        return self.callable is not None
 
 
class CallableParser(ABC):
    """Abstract base class for callable parsers."""
    
    @abstractmethod
    def parse_callable(self, func: Callable) -> ParsedCallable:
        """Parse callable information from a callable object."""
        pass
 
 
class InspectCallableParser(CallableParser):
    """Concrete parser using Python inspect module for callable analysis."""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self.docstring_parser = DocstringParser()
            self._initialized = True
    
    @classmethod
    def self(cls):
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def parse_callable(self, func: Callable) -> ParsedCallable:
        """Parse callable information from a callable object using inspect."""
        if not callable(func):
            raise ValueError("Provided object is not callable")
        
        # Get function metadata
        func_name = getattr(func, '__name__', str(func))
        docstring = inspect.getdoc(func)
        
        # Get signature and parameters
        try:
            signature = inspect.signature(func)
            parameters = self._extract_parameters(signature, docstring, func)
        except (ValueError, TypeError) as e:
            # Fallback for built-ins or special callables
            parameters = {}
        
        # Parse return information from docstring and type hints
        return_info = self._extract_return_info(func, docstring)
        
        # Parse description from docstring
        description = self.docstring_parser.parse_description(docstring) if docstring else None
        
        # Get source code if possible
        source = self._get_source_code(func)
        
        # Analyze function calls if source is available
        calls = self._analyze_function_calls(source) if source else set()
        
        return ParsedCallable(
            name=func_name,
            parameters=parameters,
            return_info=return_info,
            description=description,
            calls=calls,
            callable=func,
            source=textwrap.dedent(source)
        )
    
    def _extract_parameters(self, signature: inspect.Signature, docstring: Optional[str], func: Callable) -> Dict[str, Dict[str, Any]]:
        """Extract parameter information from function signature."""
        parameters = {}
        
        # Get parameter descriptions from docstring
        descriptions = self.docstring_parser.parse_parameter_descriptions(docstring or "")
        
        # Get type hints
        try:
            type_hints = get_type_hints(func)
        except (NameError, AttributeError, TypeError):
            type_hints = {}
        
        for param_name, param in signature.parameters.items():
            # Skip *args and **kwargs for now, but could be enhanced
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            
            # Get type information
            param_type = self._format_type(type_hints.get(param_name, param.annotation))
            
            # Get default value
            has_default = param.default is not param.empty
            default_value = param.default if has_default else None
            
            parameters[param_name] = {
                'type': param_type,
                'default': default_value,
                'description': descriptions.get(param_name),
                'required': not has_default,
                'kind': param.kind.name  # Additional info: POSITIONAL_ONLY, POSITIONAL_OR_KEYWORD, etc.
            }
        
        return parameters
    
    def _format_type(self, annotation) -> str:
        """Format type annotation as string."""
        if annotation is inspect.Parameter.empty:
            return 'Any'
        
        if hasattr(annotation, '__name__'):
            return annotation.__name__
        
        # Handle complex types like typing.List, Union, etc.
        return str(annotation).replace('typing.', '')
    
    def _extract_return_info(self, func: Callable, docstring: Optional[str]) -> Optional[Dict[str, str]]:
        """Extract return information from type hints and docstring."""
        return_info = {}
        
        # Get return description from docstring
        docstring_return_info = self.docstring_parser.parse_return_info(docstring)
        if docstring_return_info:
            return_info.update(docstring_return_info)
        
        return return_info if return_info else None
    
    def _get_source_code(self, func: Callable) -> Optional[str]:
        """Attempt to get source code of the function."""
        try:
            return inspect.getsource(func)
        except (OSError, TypeError):
            # Built-ins, C extensions, or dynamically created functions
            return None
    
    def _analyze_function_calls(self, source: str) -> Set[str]:
        """Analyze function calls in source code using AST."""
        if not source:
            return set()
        
        try:
            tree = ast.parse(source)
            calls = set()
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
            
            return calls
        except (SyntaxError, ValueError):
            return set()
 
 
# Singleton instance
CALLABLE_PARSER = InspectCallableParser.self()
 
 
def parse_callable(func: Callable) -> ParsedCallable:
    """Convenience function to parse a callable."""
    return CALLABLE_PARSER.parse_callable(func)
 
 
def main():
    from typing import List
    
    # Example function to analyze
    def create_user(name: str, age: int = 25, active: bool = True, tags: List[str] = None) -> Dict[str, Any]:
        """
        Create a new user with the given parameters.
        
        Args:
            name: The name of the user
            age: The age of the user, defaults to 25
            active: Whether the user is active
            tags: List of tags for the user
        
        Returns:
            user (str): user id
        """
        if tags is None:
            tags = []
        
        return {
            "user": name + str(age)
        }
    
    # Test the callable analyzer
    parsed_func = parse_callable(create_user)
    
    print(f"Function name: {parsed_func.name}")
    print(f"Description: {parsed_func.description}")
    print(f"Parameters: {list(parsed_func.parameters.keys())}")
    print(f"Return type: {parsed_func.return_info}")
    print(f"Function calls: {parsed_func.calls}")
    
    print(f"Source: {parsed_func.source}")
 
 
if __name__ == "__main__":
    main()
 