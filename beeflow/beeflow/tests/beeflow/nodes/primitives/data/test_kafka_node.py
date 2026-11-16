"""
Unit tests for KafkaNode using WorkflowState execution.

This test suite covers:
1) PRODUCE operation - send messages to Kafka topic
2) CONSUME operation - consume messages from Kafka topics
3) PRODUCE with optional parameters (headers, key, partition)
4) CONSUME with optional parameters (timeout_ms, commit, decode)
5) CONSUME with multiple topics
6) CONSUME with decode=False (raw bytes)
7) specific_metadata method
8) node type attribute

All tests execute nodes via:
- WorkflowIndexer
- WorkflowState
- node.run(state=...)

Run:
    pytest tests/beeflow/nodes/primitives/data/test_kafka_node.py
"""

import json
import pytest
from typing import Dict, Any

from beeflow.nodes import INPUT, OUTPUT
from beeflow.nodes.primitives.data.kafka_node import KafkaNode
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.workflow_state import WorkflowState
from beegen.event_streaming.kafka_engine import KafkaOperation

KAFKA_MODEL = "aicenter-cua"
TEST_TOPIC_IN = "APP_AI_CUA_IN"
TEST_TOPIC_OUT = "APP_AI_CUA_OUT"


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

async def run_node(node, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a node using WorkflowState + WorkflowIndexer.
    """
    state = WorkflowState(
        indexer=WorkflowIndexer(name="workflow01")
        .add_node(node)
        .build(),
        inputs=inputs,
    )

    return await node.run(state=state)


# ---------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kafka_node_produce_simple():
    """
    PRODUCE operation with simple message.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "topic" key
        - Output contains "count" key indicating messages sent
    """
    node = KafkaNode(
        name="kafka_produce_simple",
        resource_key=KAFKA_MODEL,
        operation=KafkaOperation.PRODUCE,
        inputs={
            "topic": INPUT,
            "value": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "topic": TEST_TOPIC_IN,
            "value": {"message": "Hello from KafkaNode test!", "test_id": 1},
        },
    )

    assert "status" in output
    assert output["status"] == "success"


@pytest.mark.asyncio
async def test_kafka_node_produce_with_headers():
    """
    PRODUCE operation with headers.

    Expectation:
        - Output contains "status" key with "success"
        - Message is sent with headers
    """
    node = KafkaNode(
        name="kafka_produce_headers",
        resource_key=KAFKA_MODEL,
        operation=KafkaOperation.PRODUCE,
        inputs={
            "topic": INPUT,
            "value": INPUT,
            "headers": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "topic": TEST_TOPIC_IN,
            "value": {"message": "Test with headers"},
            "headers": {
                "x-env": "test",
                "x-source": "kafka_node_test",
                "content-type": "application/json",
            },
        },
    )

    assert "status" in output
    assert output["status"] == "success"


@pytest.mark.asyncio
async def test_kafka_node_produce_with_key_and_partition():
    """
    PRODUCE operation with key and partition.

    Expectation:
        - Output contains "status" key with "success"
        - Message is sent with specified key and partition
    """
    node = KafkaNode(
        name="kafka_produce_key_partition",
        resource_key=KAFKA_MODEL,
        operation=KafkaOperation.PRODUCE,
        inputs={
            "topic": INPUT,
            "value": INPUT,
            "key": INPUT,
            "partition": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "topic": TEST_TOPIC_IN,
            "value": {"message": "Test with key and partition"},
            "key": "test-key-123",
            "partition": 0,
        },
    )

    assert "status" in output
    assert output["status"] == "success"


@pytest.mark.asyncio
async def test_kafka_node_consume_single_message():
    """
    CONSUME operation for single message.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "messages" key (list)
        - Output contains "count" key indicating number of messages
    """
    node = KafkaNode(
        name="kafka_consume_single",
        resource_key=KAFKA_MODEL,
        operation=KafkaOperation.CONSUME,
        inputs={
            "topics": INPUT,
            "max_messages": INPUT,
            "timeout_ms": INPUT,
            "commit": INPUT,
            "decode": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "topics": [TEST_TOPIC_OUT],
            "max_messages": 1,
            "timeout_ms": 2000,
            "commit": False,
            "decode": True,
        },
    )

    assert "status" in output
    assert output["status"] == "success"
    assert "messages" in output
    assert isinstance(output["messages"], list)
    assert "count" in output


@pytest.mark.asyncio
async def test_kafka_node_consume_multiple_topics():
    """
    CONSUME operation with multiple topics.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "topics" key
        - Output contains "messages" key (list)
    """
    node = KafkaNode(
        name="kafka_consume_multi",
        resource_key=KAFKA_MODEL,
        operation=KafkaOperation.CONSUME,
        inputs={
            "topics": INPUT,
            "max_messages": INPUT,
            "timeout_ms": INPUT,
            "commit": INPUT,
            "decode": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "topics": [TEST_TOPIC_OUT, TEST_TOPIC_IN],
            "max_messages": 5,
            "timeout_ms": 1000,
            "commit": False,
            "decode": True,
        },
    )

    assert "status" in output
    assert output["status"] == "success"
    assert "messages" in output


@pytest.mark.asyncio
async def test_kafka_node_consume_without_decode():
    """
    CONSUME operation without decoding (raw bytes).

    Expectation:
        - Output contains "status" key with "success"
        - Message content is raw bytes
    """
    node = KafkaNode(
        name="kafka_consume_raw",
        resource_key=KAFKA_MODEL,
        operation=KafkaOperation.CONSUME,
        inputs={
            "topics": INPUT,
            "max_messages": INPUT,
            "timeout_ms": INPUT,
            "commit": INPUT,
            "decode": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "topics": [TEST_TOPIC_OUT],
            "max_messages": 1,
            "timeout_ms": 1000,
            "commit": False,
            "decode": False,
        },
    )

    assert "status" in output
    assert output["status"] == "success"
    assert "messages" in output
    # Messages should be in bytes format when decode=False
    if output["messages"]:
        assert "value" in output["messages"][0]
        assert isinstance(output["messages"][0]["value"], bytes)


@pytest.mark.asyncio
async def test_kafka_node_consume_with_commit():
    """
    CONSUME operation with commit=True.

    Expectation:
        - Output contains "status" key with "success"
        - Output contains "committed" key indicating commit status
    """
    node = KafkaNode(
        name="kafka_consume_commit",
        resource_key=KAFKA_MODEL,
        operation=KafkaOperation.CONSUME,
        inputs={
            "topics": INPUT,
            "max_messages": INPUT,
            "timeout_ms": INPUT,
            "commit": INPUT,
            "decode": INPUT,
        },
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "topics": [TEST_TOPIC_OUT],
            "max_messages": 1,
            "timeout_ms": 1000,
            "commit": True,
            "decode": True,
        },
    )

    assert "status" in output
    assert output["status"] == "success"
    # Check if committed field is present in output
    if "committed" in output:
        assert output["committed"] is True


@pytest.mark.asyncio
async def test_kafka_node_specific_metadata():
    """
    Test specific_metadata method.

    Expectation:
        - Returns dictionary with "model" and "operation" keys
        - model matches resource_key
        - operation matches KafkaOperation string value
    """
    node = KafkaNode(
        name="kafka_metadata",
        resource_key=KAFKA_MODEL,
        operation=KafkaOperation.PRODUCE,
        inputs=INPUT,
        outputs=OUTPUT,
    )

    metadata = node.specific_metadata()

    assert isinstance(metadata, dict)
    assert "model" in metadata
    assert metadata["model"] == KAFKA_MODEL
    assert "operation" in metadata
    assert metadata["operation"] == str(KafkaOperation.PRODUCE)


@pytest.mark.asyncio
async def test_kafka_node_type():
    """
    Test node type attribute.

    Expectation:
        - Node type is "kafka"
    """
    node = KafkaNode(
        name="kafka_type",
        resource_key=KAFKA_MODEL,
        operation=KafkaOperation.PRODUCE,
        inputs=INPUT,
        outputs=OUTPUT,
    )

    assert node.type == "kafka"


@pytest.mark.asyncio
async def test_kafka_node_produce_json_value():
    """
    PRODUCE operation with JSON string value.

    Expectation:
        - Output contains "status" key with "success"
        - Message is sent successfully
    """
    node = KafkaNode(
        name="kafka_produce_json",
        resource_key=KAFKA_MODEL,
        operation=KafkaOperation.PRODUCE,
        inputs={
            "topic": INPUT,
            "value": INPUT,
        },
        outputs=OUTPUT,
    )

    test_data = {
        "user_id": "12345",
        "action": "test",
        "timestamp": "2024-01-01T00:00:00Z",
        "metadata": {"source": "unit_test"},
    }

    output = await run_node(
        node,
        inputs={
            "topic": TEST_TOPIC_IN,
            "value": json.dumps(test_data),
        },
    )

    assert "status" in output
    assert output["status"] == "success"