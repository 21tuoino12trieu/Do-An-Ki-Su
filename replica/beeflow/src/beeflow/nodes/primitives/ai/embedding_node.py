from beeflow.nodes.base_node import BaseNode
from beeflow.configs import NodeConfig, NodeType
from beegen.tools.schema.param import ParamSet
from beegen.registry.resource_hub import ResourceHub
from typing import Dict, Any, Optional


class EmbeddingNodeConfig(NodeConfig):
    """Configuration for embedding node in the workflow."""        
    model: str

class EmbeddingNode(BaseNode):
    """Class for embedding node in the beeflow graph"""
    
    __slots__ = [
        'resource_key'  # The embedding model name/identifier
    ]
    
    type: NodeType = "embedding"
    
    input_schema: ParamSet = (
        ParamSet.new()
            .var("texts: Union[str, List[str]]", required=True)
            .build()
    )
    
    output_schema: ParamSet = (
        ParamSet.new()
            .var("embeddings: List[List[float]]", required=True)
            .build()
    )
    
    def __init__(
        self,
        resource_key: Optional[str] = None,
        **kwargs
    ):
        """Initialize EmbeddingNode from either config or kwargs.
        
        Args:
            model: Embedding model name (required if config not provided)
            **kwargs: Additional keyword arguments for NodeConfig
        """
        super().__init__(**kwargs) 
                
        # Get model from config (which is now guaranteed to exist after super().__init__)
        self.resource_key = resource_key
        
        self.core = ResourceHub.self().embedding(self.resource_key).run
                        
    def specific_metadata(self) -> Dict[str, Any]:
        """Return embedding-specific metadata dictionary."""
        return {
            "model": self.resource_key
        }
        

    

