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
        

async def main():
    
    from beeflow.utils.streaming import STREAM_SERVICE
    from beeflow.states.workflow_indexer import WorkflowIndexer
    from beeflow.states.workflow_state import WorkflowState
    from beeflow.nodes.base_node import INPUT, OUTPUT
    
    emb_node=EmbeddingNode(
        name="emb0",
        resource_key="qwen-embedding",
        inputs=INPUT,
        outputs=OUTPUT,
        status_message="bố mày embedding xong rồi, dkm!",
        stream=True
    )
    
    indexer = WorkflowIndexer(name="workflow01").add_node(emb_node).build()
    
    state = WorkflowState(
        indexer=indexer, 
        inputs={
            "texts": "chương trình tình nguyện xanh ở MB có hay lắm không?"
        }
    )

    outputs = await emb_node.run(state=state)
    print(emb_node.trace_data(state, None))
    

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())