from beeflow.nodes.base_node import BaseNode
from beeflow.configs import NodeConfig, NodeType
from beegen.tools.schema.param import ParamSet
from beegen.registry.resource_hub import ResourceHub
from beegen.configs import (
    MilvusOperation, 
    MILVUS_OPERATION_INPUTS, 
    MILVUS_OPERATIONS_OUTPUTS
)
from typing import Dict, Any, Optional
import asyncio

from beegen.utils.common import ensure_async


class MilvusNodeConfig(NodeConfig):
    """Configuration for Milvus node in the workflow."""
        
    model: str
    
    operation: MilvusOperation
        

class MilvusNode(BaseNode):
    """Class for milvus node in the beeflow graph"""
    
    type: NodeType = "milvus"
        
    __slots__ = [
        'resource_key',      # The Milvus model name/identifier
        'operation',  # The operation to perform (search, insert, etc.)
        'func'        # The specific function to call based on operation
    ]
    
    def __init__(
        self,
        resource_key: Optional[str] = None,
        operation: Optional[MilvusOperation] = None,
        **kwargs
    ):
        """Initialize MilvusNode from either config or kwargs.
        
        Args:
            model: Milvus model name (required if config not provided)
            operation: Milvus operation type (required if config not provided)
            **kwargs: Additional keyword arguments for NodeConfig
        """        
        super().__init__(**kwargs)
        
        self.resource_key = resource_key
        self.operation = operation
        self.input_schema = MILVUS_OPERATION_INPUTS.get(self.operation)
        self.output_schema = MILVUS_OPERATIONS_OUTPUTS.get(self.operation)
        self.func = ResourceHub.self().milvus(self.resource_key)\
            .operation_map[self.operation]
        self.core = ensure_async(func=self.func)    

    def specific_metadata(self) -> Dict[str, Any]:
        """Return milvus-specific metadata dictionary."""
        return {
            "model": self.resource_key,
            "operation": str(self.operation)
        }
        



