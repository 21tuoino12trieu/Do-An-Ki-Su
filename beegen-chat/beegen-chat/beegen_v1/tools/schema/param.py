from __future__ import annotations
import re
from typing import Dict, List, Any, Optional, Callable, Type, Set, Union, TypeVar, Tuple
from pydantic import Field
from pydantic import BaseModel
from typeguard import check_type


class Param(BaseModel):
    """Domain model representing a single function parameter."""
    
    type: str = Field(..., description="String representation of the expected type")
    required: bool = Field(False, description="Whether this parameter is required")
    default: Optional[Any] = Field(None, description="Default value if not provided")
    description: Optional[str] = Field(None, description="Description of the parameter")

    def validate_value(self, value: Any) -> Any:
        """Validate a value against this parameter's type."""
        if value is None:
            if self.required:
                raise ValueError("Value is required but received None")
            return self.default if self.default is not None else None

        try:
            check_type(value, eval(self.type))
            return value
        except Exception as e:
            raise TypeError(f"Expected {self.type}, got {type(value).__name__}: {str(e)}")
        

class ParamSet(BaseModel):
    """Domain model representing a collection of function parameters."""
    
    params: Dict[str, Param] = Field(default_factory=dict)
    
    @classmethod
    def new(cls) -> 'ParamSetBuilder':
        """Create a new builder for this param set."""
        return ParamSetBuilder()
    
    def get_defaults(self) -> Dict[str, Any]:
        """Get all parameters with default values."""
        return {
            name: param.default 
            for name, param in self.params.items() 
            if param.default is not None
        }
        
    def validate_inputs(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate input dictionary against parameter specifications."""
        result = {}
        
        for name, param in self.params.items():
            if name not in inputs:
                if param.required:
                    raise ValueError(f"Missing required parameter: {name}")
                if param.default is not None:
                    result[name] = param.default
                continue
                
            try:
                result[name] = param.validate_value(inputs[name])
            except (ValueError, TypeError) as e:
                raise type(e)(f"Invalid parameter '{name}': {str(e)}")
        
        return result
    
    def get_parameter_info(self) -> List[str]:
        """Get human-readable parameter information."""
        lines = []
        for name, param in self.params.items():
            required_str = " (required)" if param.required else ""
            description_str = f" - {param.description}" if param.description else ""
            lines.append(f"{name}: {param.type}{required_str}{description_str}")
        return lines
    
    def get_parameter_names(self) -> List[str]:
        """Get list of all parameter names."""
        return list(self.params.keys())
    
    def __add__(self, other: 'ParamSet') -> 'ParamSet':
        """Create a new ParamSet by merging with another."""
        if not isinstance(other, ParamSet):
            raise TypeError(f"Cannot merge ParamSet with {type(other).__name__}")
        
        merged_params = {**self.params, **other.params}
        return ParamSet(params=merged_params)
    
    def __iter__(self):
        """Enable iteration over parameter names."""
        return iter(self.params)
    
    def __getitem__(self, name):
        """Enable dictionary-like access to parameters."""
        if name not in self.params:
            raise KeyError(f"Parameter '{name}' not found")
        return self.params[name]
    
    def __setitem__(self, name, param):
        """Enable dictionary-like assign value."""
        self.params[name] = param
        
    @classmethod
    def from_dict(cls, param_dict: Dict[str, Dict[str, Any]]) -> 'ParamSet':
        """Create a ParamSet from a dictionary of parameter definitions.
        
        Args:
            param_dict: Dictionary where keys are parameter names and values are
                    dictionaries containing 'type', 'default', 'description', 'required'
                    
        Example:
            param_dict = {
                'name': {
                    'type': 'str', 
                    'default': None, 
                    'description': "The person's name", 
                    'required': True
                },
                'age': {
                    'type': 'int', 
                    'default': 25, 
                    'description': "The person's age", 
                    'required': False
                }
            }
            param_set = ParamSet.from_dict(param_dict)
        """
        params = {}
        
        for param_name, param_info in param_dict.items():
            # Extract parameter properties with defaults
            param_type = param_info.get('type', 'Any')
            default_value = param_info.get('default')
            description = param_info.get('description')
            required = param_info.get('required', True)
            
            # Create Param instance
            param = Param(
                type=param_type,
                required=required,
                default=default_value,
                description=description
            )
            
            params[param_name] = param
        
        return cls(params=params)
        

class ParamSetBuilder:
    """Builder for constructing ParamSet instances with a fluent interface."""
    
    def __init__(self):
        self._params: Dict[str, Param] = {}

    def var(self, spec: str, description: str = None, required: bool = None) -> 'ParamSetBuilder':
        """
        Add a parameter from a type annotation string.
        
        Examples:
            .add_param("name: str", required=True)
            .add_param("age: int = 18", "User's age")
            .add_param("tags: List[str] = []", "User tags")
        """
        name, param_type, default_value = self._parse_param_spec(spec)
        
        # Determine if required (explicit setting overrides default behavior)
        is_required = required if required is not None else (default_value is None)
        
        self._params[name] = Param(
            type=param_type,
            required=is_required,
            default=default_value,
            description=description
        )
        return self

    def add_param(self, name: str, param: Param) -> 'ParamSetBuilder':
        """Add a parameter directly."""
        self._params[name] = param
        return self

    def build(self) -> ParamSet:
        """Build the final ParamSet."""
        return ParamSet(params=self._params.copy())

    def _parse_param_spec(self, spec: str) -> tuple[str, str, Any]:
        """Parse parameter specification string."""
        pattern = r'^\s*(\w+)\s*:\s*([^=]+?)(?:\s*=\s*(.+))?\s*$'
        match = re.match(pattern, spec)
        
        if not match:
            raise ValueError(f"Invalid parameter specification: '{spec}'. Expected 'name: type' or 'name: type = default'")
        
        name, type_str, default_str = match.groups()
        
        # Normalize type string for Python compatibility
        type_str = self._normalize_type_string(type_str.strip())
        
        # Parse default value
        default_value = None
        if default_str:
            try:
                default_value = eval(default_str)
            except Exception as e:
                raise ValueError(f"Invalid default value in '{spec}': {str(e)}")
        
        # Validate type string
        try:
            eval(type_str)
        except Exception as e:
            raise TypeError(f"Invalid type '{type_str}' in '{spec}': {str(e)}")
        
        return name, type_str, default_value

    def _normalize_type_string(self, type_str: str) -> str:
        """Convert type string to Python-compatible format."""
        return (type_str
                .replace('list[', 'List[')
                .replace('dict[', 'Dict[')
                .replace('set[', 'Set[')
                .replace('tuple[', 'Tuple['))