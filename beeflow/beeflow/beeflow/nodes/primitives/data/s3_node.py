import io
from typing import Dict, Any, Optional
from beeflow.configs import NodeConfig, NodeType
from beegen.configs import S3Config, S3Operation, S3_OPERATION_INPUTS, S3_OPERATION_OUTPUTS
from beegen.tools.schema.param import ParamSet
from beegen.utils.common import ensure_async
from ....nodes.base_node import BaseNode
from beegen.registry.resource_hub import ResourceHub



class S3NodeConfig(NodeConfig):
    """
    Configuration for S3 node in the workflow.
    
    This configuration is focused on executing a list of operations,
    each with a clearly defined structure.
    """
        
    model: str
    
    operation: S3Operation


class S3Node(BaseNode):
    """Class for s3 node in the beeflow graph"""
    type: NodeType = "s3"
    
    __slots__ = [
        'resource_key',      # The S3 model name/identifier
        'operation',  # The operation to perform (list_paths, read, write, delete, etc.)
        'func'        # The specific function to call based on operation
    ]
    
    def __init__(
        self,
        resource_key: Optional[str] = None,
        operation: Optional[S3Operation] = None,
        **kwargs
    ):        
        super().__init__(**kwargs)
        
        self.resource_key = resource_key
        self.operation = operation
        self.input_schema = S3_OPERATION_INPUTS.get(self.operation)
        self.output_schema = S3_OPERATION_OUTPUTS.get(self.operation)        
        self.func = ResourceHub.self().s3(self.resource_key).operation_map[self.operation]
        self.core = ensure_async(func=self.func)
            
    def specific_metadata(self) -> Dict[str, Any]:
        """Return s3-specific metadata dictionary."""
        return {
            "model": self.resource_key,
            "operation": str(self.operation)
        }
        

async def main():
    from beeflow.states.workflow_indexer import WorkflowIndexer
    from beeflow.states.workflow_state import WorkflowState
    from beeflow.nodes.base_node import INPUT, OUTPUT
    from beegen.configs import S3Operation

    file_paths = [
        "rnd/thaivd/work/ocr/origin/sample/sample1.jpg",
        "rnd/thaivd/work/flash-sale-bot/data/product_profile/product_profile.csv",
        "rnd/thaivd/work/flash-sale-bot/data/product_profile/65-product_mapping_interaction.csv"
    ]

    s3_node = S3Node(
        name="s30",
        resource_key="aicenter-cua",
        operation=S3Operation.READ,
        inputs={"key": INPUT},
        outputs=OUTPUT
    )
    
    indexer = WorkflowIndexer(name="workflow01")\
        .add_node(s3_node).build()
    
    state = WorkflowState(
        indexer=indexer, 
        inputs={
            "key": "rnd/thaivd/work/ocr/origin/sample/sample2.pdf"
        }
    )
    
    await s3_node.run(state=state)
    
    print(s3_node.get_outputs(state, None))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())