from typing import (
    Optional,
    Dict,
    List, 
    Union,
    Any,
    Literal
)
from beegen.configs.yaml_model import YamlModel
from beegen.tools.exporters.schema_exporter import OpenAISchemaExporter
from beegen.tools.schema.param import ParamSet
from pydantic import Field, model_validator
import uuid
    

NodeType = Literal[
    "data",
    "llm", "embedding", "rerank", 
    "branch", "for", "while",
    "code", "lambda", "parser", "prompt", "doc-processor",
    "milvus", "mongo", 
    "graph",
    "default",
    "dummy",
    "tool-executor"
]
    
    
class Reference(YamlModel):
    id: Optional[str] = None
    field: Optional[str] = None
    value: Optional[Any] = None
    
    @model_validator(mode="before")
    def validate_reference(cls, values):
        value = values.get('value')
        id = values.get('id')
        field = values.get('field')
        
        if value is not None and (id is not None or field is not None):
            raise ValueError("Cannot specify both 'value' and ('id', 'field')")
            
        if value is None and (id is None or field is None):
            raise ValueError("Must specify either 'value' or both 'id' and 'field'")
            
        return values  


class NodeConfig(YamlModel):
    """configuration for nodes in the workflow."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)  # .hex is faster than str()
    type: NodeType = "default"
    
    contain_generation: bool = False
    name: Optional[str] = None

    description: str = ""
    
    status_message: str = ""
    
    # Ports and connections
    inputs: Dict[str, Any] = {}
    outputs: Dict[str, Any] = {}
        
    # Node connections
    sources: List[str] = []
    targets: List[str] = []
    
    # Port definitions with type information
    input_schema: Union[ParamSet, List[str]] = ParamSet.new().build()
    output_schema: Union[ParamSet, List[str]] = ParamSet.new().build()
    
    stream: bool = False
    
    start: bool = False
    end: bool = False
    
    @model_validator(mode="before")
    def convert_node_instances_to_names(cls, values):
        """Convert Node instances in inputs to their string names.
        
        Supports patterns like:
        - inputs = {"question": node_instance} -> {"question": "node_name"}
        - inputs = {"question": {node_instance: "query"}} -> {"question": {"node_name": "query"}}
        """
        if "inputs" in values and isinstance(values["inputs"], dict):
            converted_inputs = {}
            for key, value in values["inputs"].items():
                converted_inputs[key] = cls._convert_value(value)
            values["inputs"] = converted_inputs
        return values

    @classmethod 
    def _convert_value(cls, value):
        """Convert a single value, handling Node instances recursively."""
        # Check if value is a node instance (duck typing approach)
        if cls._is_node_instance(value):
            return value.name
        
        # Check if value is a dict with potential node instances as keys
        elif isinstance(value, dict):
            converted_dict = {}
            for k, v in value.items():
                # Convert node instance keys to their names
                if cls._is_node_instance(k):
                    converted_dict[k.name] = v
                else:
                    converted_dict[k] = v
            return converted_dict
        
        # Return value as-is for other types (strings, numbers, lists, etc.)
        else:
            return value
    
    @classmethod
    def _is_node_instance(cls, obj):
        """Check if an object is a Node instance using duck typing.
        
        We check for key attributes that Node instances have:
        - name: string identifier
        - type: NodeType enum
        - id: unique identifier
        - config: reference to NodeConfig
        
        This avoids circular import issues while being reasonably confident
        we're dealing with a Node instance.
        """
        return (
            hasattr(obj, 'name') and 
            hasattr(obj, 'type') and 
            hasattr(obj, 'id') and
            hasattr(obj, 'config') and
            isinstance(getattr(obj, 'name'), str)
        )
    
    def get_openai_tool_schema(self):
        return OpenAISchemaExporter.export_tool_schema(
            param_set=self.input_schema,
            function_name=self.name,
            function_description=self.description
        )
        
    def get_openai_function_schema(self):
        schema = OpenAISchemaExporter.export_function_schema(
            param_set=self.input_schema,
            function_name=self.name,
            function_description=self.description
        )
        return schema
    

