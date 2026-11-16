from typing import Any, Callable, Optional, Union
from beegen.tools.parsers.callable_parser import parse_callable, ParsedCallable
from beegen.tools.schema.function_info import FunctionInfo


class CallableAnalyzer:
    """High-level service for analyzing functions and converting to schemas."""
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self.__class__._initialized = True
            
    def analyze(self, func: Callable) -> 'FunctionInfo':
        """Analyze a function and return structured information."""
        from beegen.tools.schema.param import Param, ParamSet
        
        # Parse function information
        parsed = parse_callable(func)
        
        # Convert to domain model
        input_builder = ParamSet.new()
        for name, info in parsed.parameters.items():
            param = Param(
                type=info["type"],
                required=info["required"],
                default=info["default"],
                description=info["description"]
            )
            input_builder.add_param(name, param)
        input_schema = input_builder.build()
        
        output_builder = ParamSet.new()
        if parsed.return_info:
            for name, type in parsed.return_info.items():
                output_builder.add_param(name, Param(type=type, required=True))
            output_schema = output_builder.build()
        else:
            output_schema = None
            
        return FunctionInfo(
            name=parsed.name,
            input_schema=input_schema,
            output_schema=output_schema,
            description=parsed.description,
            source=parsed.source
        )
        
        
CALLABLE_ANALYZER = CallableAnalyzer()


def analyze_callable(func: Callable) -> 'FunctionInfo':
    """Convenience function to analyze a callable."""
    return CALLABLE_ANALYZER.analyze(func)


if __name__ == "__main__":
    from typing import List, Dict
    
    # Example function to analyze
    def create_user(name: str, age: int = 25, active: bool = True, tags: List[str] = None) -> Dict[str, Any]:
        """
        Create a new user with the given parameters.
        
        Args:
            name: The name of the user
            age: The age of the user, defaults to 25
            active: Whether the user is active
            tags: List of tags for the user
            
        Return keys:
            user (dict): The created user object
        """
        if tags is None:
            tags = []
        
        return {
            "user": {
                "name": name,
                "age": age,
                "active": active,
                "tags": tags
            }
        }
        
    func_info = analyze_callable(create_user)
    
    print(func_info)