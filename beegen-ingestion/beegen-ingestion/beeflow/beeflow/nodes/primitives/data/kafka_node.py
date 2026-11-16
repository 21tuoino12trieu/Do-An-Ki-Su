import asyncio
from enum import Enum
from typing import Any, Dict, Optional

from beeflow.configs import NodeConfig, NodeType
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.workflow_state import WorkflowState
from beegen.configs.event_streaming.kafka_config import KAFKA_OPERATION_INPUTS, KAFKA_OPERATION_OUTPUTS
from beegen.event_streaming.kafka_engine import KafkaEngine, KafkaOperation
from beegen.tools.schema.param import ParamSet
from beegen.utils.common import ensure_async
from beegen.registry.resource_hub import ResourceHub
from ....nodes.base_node import BaseNode

class KafkaNodeConfig(NodeConfig):
    """
    Configuration model for KafkaNode.

    Attributes:
        model (str): Resource key (to fetch KafkaEngine via ResourceHub).
        operation (KafkaOperation): Which Kafka operation this node performs.
    """

    model: str
    operation: KafkaOperation


class KafkaNode(BaseNode):
    """Kafka node for Beeflow graph (PRODUCE & CONSUME only)."""

    type: NodeType = "kafka"

    __slots__ = [
        "resource_key",  # Key to locate Kafka resource (engine/config) in ResourceHub
        "operation",     # KafkaOperation
        "func",          # Callable bound to the engine operation
    ]

    def __init__(
        self,
        resource_key: Optional[str] = None,
        operation: Optional[KafkaOperation] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.resource_key = resource_key
        self.operation = operation

        # Bind IO schemas
        self.input_schema = KAFKA_OPERATION_INPUTS.get(self.operation)
        self.output_schema = KAFKA_OPERATION_OUTPUTS.get(self.operation)

        # Resolve engine function from ResourceHub, mirroring S3Node style
        # Expect ResourceHub.self().kafka(self.resource_key) to return a KafkaEngine instance
        engine: KafkaEngine = ResourceHub.self().kafka(self.resource_key)
        self.func = engine.operation_map[self.operation]
        self.core = ensure_async(func=self.func)

    def specific_metadata(self) -> Dict[str, Any]:
        return {
            "model": self.resource_key,
            "operation": str(self.operation),
        }

async def main():
    from beeflow.nodes.base_node import INPUT, OUTPUT

    # Example 1: PRODUCE
    producer_node = KafkaNode(
        name="kafka_produce",
        resource_key="aicenter-cua",
        operation=KafkaOperation.PRODUCE,
        inputs={
            "topic": INPUT,
            "value": INPUT,
            # Optional inputs; include only if you plan to pass them:
            "headers": INPUT,     # e.g. {"x-env": "dev"}
            # "key": INPUT,
            # "partition": INPUT,
        },
        outputs=OUTPUT,
    )

    # Example 2: CONSUME
    consumer_node = KafkaNode(
        name="kafka_consume",
        resource_key="aicenter-cua",
        operation=KafkaOperation.CONSUME,
        inputs={
            "topics": INPUT,        # str or List[str]
            "max_messages": INPUT,  # e.g., 1
            "timeout_ms": INPUT,    # e.g., 2000
            "commit": INPUT,        # e.g., False (or True if you want to commit)
            "decode": INPUT,        # True to decode bytes to UTF-8
        },
        outputs=OUTPUT,
    )

    # Build indexer (optional for this direct .run pattern; included to mirror your Redis sample)
    indexer = WorkflowIndexer(name="wf_kafka_ops") \
        .add_node(producer_node) \
        .add_node(consumer_node) \
        .build()

    # Initial workflow inputs for both nodes
    state = WorkflowState(
        indexer=indexer,
        inputs={
            # Producer inputs
            "topic": "APP_AI_CUA_IN",
            "value": {"from": "KafkaNode", "msg": "Hello from Beeflow!"},
            "headers": {"x-env": "dev"},

            # Consumer inputs
            "topics": ["APP_AI_CUA_OUT"],
            "max_messages": 1,
            "timeout_ms": 2000,
            "commit": False,
            "decode": True,
        },
    )

    # Run PRODUCE
    produce_result = await producer_node.run(state=state)
    print("Produce =>", produce_result)

    # Run CONSUME
    consume_result = await consumer_node.run(state=state)
    print("Consume  =>", consume_result)


if __name__ == "__main__":
    asyncio.run(main())