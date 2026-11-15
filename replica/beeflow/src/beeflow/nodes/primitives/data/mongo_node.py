from beeflow.nodes.base_node import BaseNode
from beeflow.configs import NodeConfig, NodeType
from beegen.tools.schema.param import ParamSet
from beegen.registry.resource_hub import ResourceHub
from beegen.configs import (
    MongoOperation,
    MONGO_OPERATION_INPUTS,
    MONGO_OPERATION_OUTPUTS
)
from typing import Dict, Any, Optional


class MongoNodeConfig(NodeConfig):
    """
    Configuration for MongoDB node in the workflow.
    
    This configuration is focused on executing a list of operations,
    each with a clearly defined structure.
    """
        
    model: str
    
    operation: MongoOperation
        

class MongoNode(BaseNode):
    """Class for mongo node in the beeflow graph"""
    type: NodeType = "mongo"

    __slots__ = [
        'resource_key',      # The MongoDB model name/identifier
        'operation'   # The operation to perform (find, insert, update, etc.)
    ]
    
    def __init__(
        self,
        resource_key: Optional[str] = None,
        operation: Optional[MongoOperation] = None,
        **kwargs
    ):
        """Initialize MongoNode from either config or kwargs.
        
        Args:
            model: MongoDB model name (required if config not provided)
            operation: MongoDB operation type (required if config not provided)
            **kwargs: Additional keyword arguments for NodeConfig
        """        
        super().__init__(**kwargs) 
        
        self.resource_key = resource_key
        self.operation = operation
        self.input_schema = MONGO_OPERATION_INPUTS.get(self.operation)
        self.output_schema = MONGO_OPERATION_OUTPUTS.get(self.operation)
        self.core = ResourceHub.self().mongo(self.resource_key)\
            .operation_map[self.operation]   
            
    def specific_metadata(self) -> Dict[str, Any]:
        """Return mongo-specific metadata dictionary."""
        return {
            "model": self.resource_key,
            "operation": str(self.operation)
        }
        

    

