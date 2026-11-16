from ..schema.param import ParamSet
from typing import Dict, Any


class OpenAISchemaExporter:
    """Converts ParamSet to OpenAI function calling schema format."""
    
    @staticmethod
    def export_tool_schema(
        param_set: ParamSet, 
        function_name: str,
        function_description: str = ""
    ) -> Dict[str, Any]:
        """Export as OpenAI tool schema format."""
        return {
            "type": "function",
            "function": OpenAISchemaExporter.export_function_schema(
                param_set, function_name, function_description
            )
        }
    
    @staticmethod
    def export_function_schema(
        param_set: ParamSet,
        function_name: str, 
        function_description: str = ""
    ) -> Dict[str, Any]:
        """Export as OpenAI function schema format."""
        properties = {}
        required = []
        
        for name, param in param_set.params.items():
            property_schema = {
                "type": OpenAISchemaExporter._convert_type_to_json_schema(param.type)
            }
            
            if param.description:
                property_schema["description"] = param.description
                
            if param.default is not None and not param.required:
                property_schema["default"] = param.default
                
            properties[name] = property_schema
            
            if param.required:
                required.append(name)
        
        parameters_schema = {
            "type": "object",
            "properties": properties
        }
        
        if required:
            parameters_schema["required"] = required
        
        return {
            "name": function_name,
            "description": function_description,
            "parameters": parameters_schema
        }
    
    @staticmethod
    def _convert_type_to_json_schema(type_str: str) -> str:
        """Convert Python type string to JSON Schema type."""
        type_mapping = {
            "str": "string",
            "int": "integer", 
            "float": "number",
            "bool": "boolean",
            "list": "array",
            "dict": "object",
            "List": "array",
            "Dict": "object",
        }
        
        # Handle Optional types
        if type_str.startswith("Optional[") and type_str.endswith("]"):
            inner_type = type_str[9:-1]
            return OpenAISchemaExporter._convert_type_to_json_schema(inner_type)
        
        # Handle List/Dict with type parameters
        if any(generic in type_str for generic in ["List[", "Dict[", "list[", "dict["]):
            if "List" in type_str or "list" in type_str:
                return "array"
            if "Dict" in type_str or "dict" in type_str:
                return "object"
        
        return type_mapping.get(type_str, "string")
    
    
if __name__ == "__main__":
    # Example 1: Building a schema manually
    user_schema = (
        ParamSet.new()
        .var("name: str", "User's name", required=True)
        .var("age: int = 18", "User's age")
        .var("tags: List[str] = []", "User tags")
        .var("metadata: Dict = {}", "Additional user information")
        .build()
    )
    
    print("=== Manual Schema Building ===")
    print("Parameters:", user_schema.get_parameter_info())
    print("Defaults:", user_schema.get_defaults())
    
    # Validation example
    try:
        validated = user_schema.validate_inputs({
            "name": "John",
            "age": 25,
            "tags": ["admin", "user"]
        })
        print("Validated inputs:", validated)
    except Exception as e:
        print("Validation error:", e)
    
    # Example 2: Converting to OpenAI schema
    print("\n=== OpenAI Schema Export ===")
    openai_schema = OpenAISchemaExporter.export_tool_schema(
        user_schema,
        "create_user",
        "Creates a new user in the system"
    )
    
    import json
    print(json.dumps(openai_schema, indent=2))
    
    # Example 3: Schema merging
    print("\n=== Schema Merging ===")
    config_schema = (
        ParamSet.new()
        .var("debug: bool = False", "Enable debug mode")
        .var("timeout: int = 30", "Request timeout in seconds")
        .build()
    )
    
    combined_schema = user_schema + config_schema
    print("Combined parameters:", combined_schema.get_parameter_info())