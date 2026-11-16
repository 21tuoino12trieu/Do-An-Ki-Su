import re
from typing import Dict, List, Any, Optional, Callable, Type, Set, Union, TypeVar
from pydantic import Field, model_serializer, ConfigDict
from beegenerate.configs.yaml_model import YamlModel
from typeguard import check_type


class Param(YamlModel):
    """Schema definition for a single variable/parameter."""
    type: str = Field(..., description="String representation of the expected type")
    required: bool = Field(False, description="Whether this variable is required")
    default: Optional[Any] = Field(None, description="Default value if not provided")
    description: Optional[str] = Field(None, description="Description of the variable")

    def validate(self, value: Any) -> Any:
        """Validate a value against this schema."""
        if value is None:
            if self.required:
                raise ValueError("Value is required but received None")
            return self.default if self.default is not None else None

        try:
            check_type(value, eval(self.type))
            return value
        except Exception as e:
            raise TypeError(str(e))
        
        
class ParamSet(YamlModel):
    
    params: Dict[str, Param]
    
    @classmethod
    def new(cls) -> 'ParamSetBuilder':
        """Create a new builder for this param set."""
        return ParamSetBuilder()
    
    def validate(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate input dictionary against parameter specifications.
        
        Args:
            inputs: Dictionary of input parameters to validate
            
        Returns:
            Dictionary of validated parameters
            
        Raises:
            ValueError: If required parameter is missing or validation fails
            TypeError: If parameter type is invalid
        """
        result = {}
        
        for name, param in self.params.items():
            # Early continue if parameter can be skipped
            if name not in inputs:
                if param.required:
                    raise ValueError(f"Missing required parameter: {name}")
                if not hasattr(param, 'default') or param.default is None:
                    continue
                
            try:
                value = inputs.get(name)
                if validated := param.validate(value):  # Using walrus operator
                    result[name] = validated
                    
            except (ValueError, TypeError) as e:
                raise type(e)(f"Invalid parameter '{name}': {str(e)}")
        
        return result
    
    def list_vars(self) -> List[str]:
        """Returns a string representation of parameter metadata."""
        lines = []
        
        for name, param in self.params.items():
            type_str = param.type
            required_str = " (required)" if param.required else ""
            description_str = f" - {param.description}" if param.description else ""
            
            param_info = f"{name}: {type_str}{required_str}{description_str}"
            lines.append(param_info)
        
        return lines   
    
    def __add__(self, other: 'ParamSet') -> 'ParamSet':
        """Combine two parameter sets.
        
        Args:
            other: Another ParamSet instance to combine with
            
        Returns:
            A new ParamSet containing parameters from both sets
            
        Raises:
            TypeError: If other is not a ParamSet instance
        """
        if not isinstance(other, ParamSet):
            raise TypeError(f"Cannot add ParamSet with {type(other).__name__}")
        
        # Create a new ParamSet with combined parameters
        result = ParamSet(params={})
        
        # Copy parameters from self
        for name, param in self.params.items():
            result.params[name] = param
        
        # Add or update parameters from other
        for name, param in other.params.items():
            result.params[name] = param
        
        return result
    
    
class ParamSetBuilder:
    def __init__(self):
        self.params = {}

    def var(self, spec: str, desc: str = None, required: bool = None) -> 'ParamSetBuilder':
        """
        Parse a type annotation string like "name: str", "scores: list[int]", or "tags: list[str] = ['user']"
        to create a Param with an optional description and required flag.
        
        Args:
            spec: String specification in the format "name: type" or "name: type = default"
            desc: Optional description of the parameter
            required: Explicitly set whether the parameter is required (overrides the default behavior)
        """
        # Regular expression to parse "name: type = default" format
        pattern = r'^\s*(\w+)\s*:\s*([^=]+?)(?:\s*=\s*(.+))?\s*$'
        match = re.match(pattern, spec)
        
        if not match:
            raise ValueError(f"Invalid parameter specification: '{spec}'. Expected format: 'name: type' or 'name: type = default'")
        
        name, type_str, default_str = match.groups()
        
        # Clean up type string and make it Python-compatible
        type_str = type_str.strip()
        
        # Convert Python type format to string representation
        # e.g. "list[int]" to "List[int]", "dict[str, int]" to "Dict[str, int]"
        type_str = type_str.replace('list[', 'List[').replace('dict[', 'Dict[').replace('set[', 'Set[')
        
        # Parse default value if provided
        default = None
        if default_str:
            try:
                default = eval(default_str)
            except Exception as e:
                raise ValueError(f"Invalid default value in '{spec}': {str(e)}")
        
        # Check if the type is valid
        try:
            eval(type_str)  # Just to validate, not using the result
        except Exception as e:
            raise TypeError(f"Invalid type '{type_str}' in '{spec}': {str(e)}")
        
        # Determine if parameter is required
        # If required is explicitly set, use that value
        # Otherwise, it's required if no default is provided
        is_required = required if required is not None else False
            
        # Create the parameter
        self.params[name] = Param(
            type=type_str,
            required=is_required,
            default=default,
            description=desc
        )
        
        return self

    def build(self) -> ParamSet:
        return ParamSet(params=self.params)


async def test_multiple():
    # Basic schema with different types
    input_schema = (
        ParamSet.new()
            .var("prompt: str", required=True)
            .var("system_message: str", required=False)
            .build()
    )
    
    user_schema = (
        ParamSet.new()
            .var("name: str", required=True)
            .var("age: int = 18", required=False)
            .var("tags: List[str] = []", "User tags")
            .var("metadata: Dict = {}", "Additional user information")
            .build()
    )
    
    print(str(user_schema))

    # Valid inputs with all fields
    print("Basic validation:")
    print(user_schema.validate({
        "name": "John",
        # "age": 25,
        "tags": ["user", "admin"],
        "metadata": {"joined": "2024-01-01"},
        "extra_field": "ignored"  # Extra field is ignored
    }))

    # Optional fields omitted
    print("\nOptional fields omitted:")
    print(user_schema.validate({
        "name": "Alice"  # Only required field
    }))

    # Nested schema example
    config_schema = (
        ParamSet.new()
            .var("database: Dict[str, str]", required=True)
            .var("allowed_ips: List[str]", "Allowed IP addresses")
            .var("options: Dict", "Configuration options")
            .build()
    )

    print("\nNested schema:")
    print(config_schema.validate({
        "database": {
            "host": "localhost",
            "port": "5432"
        },
        # "allowed_ips": ["127.0.0.1", "192.168.1.1"],
        # "options": {"timeout": 30}
    }))

    # MongoDB-style schema
    find_schema = (
        ParamSet.new()
            .var("query: Dict = {}", "MongoDB query filter")
            .var("projection: Dict = None", "Fields to project", required=False)
            .var("skip: int = 0", "Number of documents to skip")
            .var("limit: int = 0", "Max number of documents to return")
            .build()
    )

    print("\nMongoDB-style query:")
    print(find_schema.validate({
        "query": {"status": "active"},
        "limit": 10,
        "hint": {"status": 1}  # Extra MongoDB-specific option
    }))

    # Error examples
    print("\nError examples:")
    try:
        # Missing required field
        user_schema.validate({
            "age": 25  # Missing required 'name'
        })
    except ValueError as e:
        print(f"Missing required field: {e}")

    try:
        # Type mismatch
        user_schema.validate({
            "name": "John",
            "age": "not a number"
        })
    except TypeError as e:
        print(f"Type mismatch: {e}")

    try:
        # Invalid list element type
        user_schema.validate({
            "name": "John",
            "tags": ["user", 123]  # Should be all strings
        })
    except TypeError as e:
        print(f"Invalid list element: {e}")

    # Complex schema with unions and optionals
    # Note: We'll need to implement Union type support
    advanced_schema = (
        ParamSet.new()
            .var("id: str", required=True)
            .var("status: Union[str, int] = 'active'", "Status indicator")
            .var("data: Dict = None", "Optional data payload", required=False)
            .var("items: List[Dict[str, Any]] = []", "Collection of items")
            .build()
    )

    print("\nAdvanced schema:")
    print(advanced_schema.validate({
        "id": "12345",
        "status": "pending",
        "data": {"key": "value"},
        "items": [{"name": "item1"}, {"name": "item2"}]
    }))
    
    
async def main():
    # Basic schema with different types
    input_schema_1 = (
        ParamSet.new()
            .var("prompt: str", required=True)
            .var("system_message: str", required=False)
            .build()
    )
    
    input_schema_2 = (
        ParamSet.new()
            .var("name: str", required=True)
            .var("age: int = 18", required=False)
            .var("tags: List[str] = []", "User tags")
            .var("metadata: Dict = {}", "Additional user information")
            .build()
    )
    
    input_schema = ParamSet.new().build()
    
    input_schema += input_schema_1
    input_schema += input_schema_2
    
    for name, param in input_schema.params.items():
        print(name, param)
        
    for key in input_schema.params:
        print(key)
        print(input_schema.params[key])


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())