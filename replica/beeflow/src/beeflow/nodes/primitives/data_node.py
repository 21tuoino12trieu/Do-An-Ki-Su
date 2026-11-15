from beeflow.nodes.base_node import BaseNode
from beeflow.configs import NodeConfig, NodeType
from beegen.tools.schema.param import ParamSet
from beegen.loggings.loggers import LOGGER
from typing import List, Optional, Dict, Any


class DataNode(BaseNode):
    """
    A simple data storage node that passes input data to output without processing.
    
    This node is useful for:
    - Storing intermediate data in workflows
    - Creating data checkpoints
    - Reformatting data structure 
    - Acting as a data hub for multiple downstream nodes
    
    The node simply copies all input values to corresponding output values,
    making it a pass-through data container.
    
    Input and output schemas are automatically created from the provided inputs,
    so you don't need to define them separately.
    """
    
    type: NodeType = "data"
    
    __slots__ = []  # No additional instance attributes beyond BaseNode
    
    def __init__(
        self,
        **kwargs
    ):
        """Initialize DataNode with automatic schema creation.
        
        Args:
            name: Node name (required)
            inputs: Input variable mappings - schema will be auto-created from these
            **kwargs: Additional keyword arguments for NodeConfig
        """
        if "name" not in kwargs:
            raise ValueError("DataNode requires a name")
        
        if "inputs" not in kwargs:
            raise ValueError("DataNode requires inputs to create schema")
                
        # Initialize base node
        super().__init__(**kwargs)
        
        self._build_schema()
        
        # Set up simple pass-through core function
        self.core = self._pass_through_data
        
    def _build_schema(self) -> NodeConfig:
        """Create NodeConfig with auto-generated input/output schemas."""
        
        # Extract input variable names from inputs dict
        input_vars = list(self.inputs.keys())
        
        # Create input schema - all variables are required with Any type
        input_schema = ParamSet.new()
        for var_name in input_vars:
            input_schema = input_schema.var(f"{var_name}: Any", required=True)
        
        # Output schema is identical to input schema for pass-through
        output_schema = ParamSet.new()
        for var_name in input_vars:
            output_schema = output_schema.var(f"{var_name}: Any", required=True)
        
        # Set the schemas
        self.input_schema = input_schema.build()
        self.output_schema = output_schema.build()
                
    def _pass_through_data(self, **inputs) -> Dict[str, Any]:
        """
        Simple pass-through function that copies inputs to outputs.
        
        Args:
            **inputs: All input values
            
        Returns:
            Dict containing the same data
        """
        # Simply return all inputs as outputs
        return inputs
        
    def specific_metadata(self) -> Dict[str, Any]:
        """Return data node specific metadata."""
        return {
            "node_purpose": "data_storage_passthrough",
            "variables": self.get_input_variables()
        }




