from typing import Dict, Any, Optional
from beeflow.nodes.base_node import BaseNode
from beeflow.configs import NodeConfig, NodeType
from beegen.registry.resource_hub import ResourceHub
from beegen.tools.schema.param import ParamSet
from beegen.configs.cache.redis_config import (
    RedisOperation,
    REDIS_OPERATION_INPUTS,
    REDIS_OPERATION_OUTPUTS,
)


class RedisNode(BaseNode):
    """Class for redis node in the beeflow graph."""
    type: NodeType = "data"

    __slots__ = [
        'resource_key',   # The Redis model/resource identifier
        'operation',      # The Redis operation (enum)
        'core'            # Callable resolved from ResourceHub.operation_map[operation]
    ]

    def __init__(
        self,
        resource_key: Optional[str] = None,
        operation: Optional[RedisOperation] = None,
        **kwargs: Any
    ):
        """
        Initialize RedisNode from either config or kwargs.

        Args:
            resource_key: Redis model/resource key (required if not provided via config)
            operation: Redis operation type (required if not provided via config)
            **kwargs: Additional keyword arguments for NodeConfig
        """
        super().__init__(**kwargs)

        # When constructed via NodeConfig, these are injected by BaseNode from self.config
        # Fallback to explicit kwargs if present.
        self.resource_key = getattr(self, "model", None) or resource_key
        self.operation = getattr(self, "operation", None) or operation

        if self.resource_key is None or self.operation is None:
            raise ValueError("RedisNode requires both 'resource_key/model' and 'operation'.")

        # Bind IO schemas according to the chosen operation
        self.input_schema = REDIS_OPERATION_INPUTS.get(self.operation)
        self.output_schema = REDIS_OPERATION_OUTPUTS.get(self.operation)

        if self.input_schema is None or self.output_schema is None:
            raise ValueError(f"Unsupported or unregistered Redis operation: {self.operation}")

        # Resolve the concrete callable for this operation from ResourceHub
        self.core = ResourceHub.self().redis(self.resource_key).operation_map[self.operation]

    def specific_metadata(self) -> Dict[str, Any]:
        """Return redis-specific metadata dictionary."""
        return {
            "model": self.resource_key,
            "operation": str(self.operation)
        }

    # async def run(self, state) -> Dict[str, Any]:
    #     """
    #     Execute the configured Redis operation.

    #     This method expects inputs to match `self.input_schema`. The resolved
    #     `self.core` callable is responsible for performing the actual operation.

    #     Returns
    #     -------
    #     Dict[str, Any]
    #         {"redis_result": <raw result from the operation>}
    #     """
    #     # Collect arguments for the operation from state via BaseNode input mapping
    #     args = self.collect_inputs(state)  # returns a dict of validated inputs
    #     # `self.core` should accept **args and perform the Redis operation
    #     result = self.core(**args)
    #     outputs = {"redis_result": result}
    #     self.assign_outputs(state, outputs)
    #     return outputs


# ---- Example usage (mirrors your Mongo main) --------------------------------

async def main():
    from beeflow.states.workflow_indexer import WorkflowIndexer
    from beeflow.states.workflow_state import WorkflowState
    from beeflow.nodes.base_node import INPUT, OUTPUT

    # Example 1: SET with TTL
    set_node = RedisNode(
        name="redis_set",
        resource_key="aicenter-chatbot",             
        operation=RedisOperation.SET,
        inputs={
            "key": INPUT,
            "value": INPUT
        },
        outputs=OUTPUT
    )

    # Example 2: GET
    get_node = RedisNode(
        name="redis_get",
        resource_key="aicenter-chatbot",
        operation=RedisOperation.GET,
        inputs={
            "key": INPUT
        },
        outputs=OUTPUT
    )

    indexer = WorkflowIndexer(name="wf_redis_ops")\
        .add_node(get_node)\
        .build()

    # Initial workflow inputs for both nodes
    state = WorkflowState(
        indexer=indexer,
        inputs={
            # for redis_set
            "key": "demo:key",
            "value": "Hello Redis from RedisNode!"
        }
    )

    result = await get_node.run(state=state)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())