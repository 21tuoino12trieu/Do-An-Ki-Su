from typing import Any, Callable, Dict, Optional, Union
from beegen_v1.tools.exporters.source_exporter import DependencySourceExtractor, SourceExtractor
from beegen_v1.tools.parsers.func_parser import ASTFunctionParser, FunctionParser
from beegen_v1.tools.schema.function_info import FunctionInfo


class FunctionAnalyzer:
    """High-level service for analyzing functions and converting to schemas."""
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, 
                 parser: Optional[FunctionParser] = None,
                 extractor: Optional[SourceExtractor] = None):
        if not self._initialized:
            self.parser = parser or ASTFunctionParser()
            self.extractor = extractor or DependencySourceExtractor()
            self.__class__._initialized = True
    
    @classmethod
    def self(cls):
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def analyze_function(self, function: Union[str, Callable]) -> 'FunctionInfo':
        """Analyze a function and return structured information."""
        from beegen_v1.tools.schema.param import Param, ParamSet

        if isinstance(function, Callable):
            # Extract source code
            source = self.extractor.extract_source(function)
        elif isinstance(function, str):
            source = function
        else:
            raise ValueError(f"Source must be a str or Callable!")
        
        # Parse function information
        parsed = self.parser.parse_function(source)
        
        # Convert to domain model
        input_builder = ParamSet.new()
        for name, type in parsed.parameters.items():
            param = Param(
                type=type['type'],
                required=type['required'],
                default=type['default'],
                description=type['description']
            )
            input_builder.add_param(name, param)
        
        output_schema = ParamSet.new()
        if parsed.return_info:
            for name, type in parsed.return_info.items():
                output_schema = output_schema.var(f"{name}: {type}")
            output_schema = output_schema.build()
        else:
            output_schema = None
        
        return FunctionInfo(
            name=parsed.name,
            input_schema=input_builder.build(),
            output_schema=output_schema,
            description=parsed.description,
            source=source
        )
    
    def function_to_openai_schema(self, 
                                  function: Callable,
                                  description: str = "") -> Dict[str, Any]:
        """Analyze function and convert directly to OpenAI schema."""
        from ..exporters.schema_exporter import OpenAISchemaExporter
        
        function_info = self.analyze_function(function)
        
        return OpenAISchemaExporter.export_tool_schema(
            function_info.input_schema,
            function_info.name,
            description or function_info.docstring or ""
        )


FUNC_ANALYZER = FunctionAnalyzer.self()


if __name__ == "__main__":
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
            user (dict): The created user object
        """
        if tags is None:
            tags = []
        
        return {
            "name": name,
            "age": age,
            "active": active,
            "tags": tags
        }
    
    # Analyze the function
    analyzer = FunctionAnalyzer()
    
    try:
        # Get function info
        function_info = analyzer.analyze_function(create_user)
        print("=== Function Analysis ===")
        print(f"Name: {function_info.name}")
        print(f"Parameters: {function_info.input_schema.get_parameter_info()}")
        print(f"Defaults: {function_info.input_schema.get_defaults()}")
        print(f"Sources: {function_info.source}")
        
        # Convert to OpenAI schema
        print("\n=== OpenAI Schema ===")
        schema = analyzer.function_to_openai_schema(
            create_user, 
            "Creates a new user in the system"
        )
        
        import json
        print(json.dumps(schema, indent=2))
        
        # Test validation
        print("\n=== Validation Test ===")
        test_inputs = {"name": "John", "age": 30}
        validated = function_info.input_schema.validate_inputs(test_inputs)
        print(f"Validated: {validated}")
        
    except Exception as e:
        print(f"Analysis failed: {e}")
        import traceback
        traceback.print_exc()