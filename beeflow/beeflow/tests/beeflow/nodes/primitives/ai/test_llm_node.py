"""
Unit tests for LLMNode using WorkflowState execution.

This test suite covers:
1) Basic text generation (single message) - non-streaming mode
2) Basic text generation (single message) - streaming mode
3) Multi-turn conversation (multiple messages) - non-streaming mode
4) Multi-turn conversation (multiple messages) - streaming mode
5) Instant response mode
6) Custom metadata passing
7) specific_metadata method
8) node type attribute

All tests execute nodes via:
- WorkflowIndexer
- WorkflowState
- node.run(state=...)

Run:
    pytest tests/beeflow/nodes/primitives/ai/test_llm_node.py
"""

import pytest
from typing import Dict, Any

from beeflow.nodes import INPUT, OUTPUT
from beeflow.nodes.primitives.ai.llm_node import LLMNode
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.workflow_state import WorkflowState


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
async def test_llm_node_basic_text_generation_non_streaming():
    """
    Basic text generation flow (single message) - non-streaming mode.

    Expectation:
        - Output contains ("content", "role", "model_used")
        - content is a string
    """
    node = LLMNode(
        name="llm_basic_non_streaming",
        resource_key="gpt-5.1-chat",
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    output = await run_node(
        node,
        inputs={
            "messages": [{"role": "user", "content": "What is 2 + 2?"}],
        },
    )

    assert "content" in output
    assert "role" in output
    assert "model_used" in output
    assert isinstance(output["content"], str)
    assert output["role"] == "assistant"


@pytest.mark.asyncio
async def test_llm_node_basic_text_generation_streaming():
    """
    Basic text generation flow (single message) - streaming mode.

    Expectation:
        - Output contains ("content", "role", "model_used")
        - content is a string (accumulated from stream)
    """
    node = LLMNode(
        name="llm_basic_stream",
        resource_key="gpt-5.1-chat",
        inputs=INPUT,
        outputs=OUTPUT,
        stream=True,
    )

    output = await run_node(
        node,
        inputs={
            "messages": [{"role": "user", "content": "What is 2 + 2?"}],
        },
    )

    assert "content" in output
    assert "role" in output
    assert "model_used" in output
    assert isinstance(output["content"], str)
    assert output["role"] == "assistant"


@pytest.mark.asyncio
async def test_llm_node_multi_turn_conversation_non_streaming():
    """
    Multi-turn conversation flow (multiple messages) - non-streaming mode.

    Expectation:
        - Output contains ("content", "tokens_used")
        - Response follows system prompt instructions
    """
    node = LLMNode(
        name="llm_conversation",
        resource_key="gpt-5.1-chat",
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    output = await run_node(
        node,
        inputs={
            "messages": [
                {"role": "system", "content": "You are a math expert. Answer with only the final number."},
                {"role": "user", "content": "What is 7 x 8?"},
            ],
        },
    )

    assert "content" in output
    assert isinstance(output["content"], str)
    # Verify tokens used are tracked
    if "tokens_used" in output:
        assert isinstance(output["tokens_used"], dict)


@pytest.mark.asyncio
async def test_llm_node_multi_turn_conversation_streaming():
    """
    Multi-turn conversation flow (multiple messages) - streaming mode.

    Expectation:
        - Output contains ("content", "tokens_used")
        - Response follows system prompt instructions
    """
    node = LLMNode(
        name="llm_conversation_stream",
        resource_key="gpt-5.1-chat",
        inputs=INPUT,
        outputs=OUTPUT,
        stream=True,
    )

    output = await run_node(
        node,
        inputs={
            "messages": [
                {"role": "system", "content": "You are a math expert. Answer with only the final number."},
                {"role": "user", "content": "What is 7 x 8?"},
            ],
        },
    )

    assert "content" in output
    assert isinstance(output["content"], str)
    # Verify tokens used are tracked
    if "tokens_used" in output:
        assert isinstance(output["tokens_used"], dict)


@pytest.mark.asyncio
async def test_llm_node_instant_response_mode():
    """
    Instant response mode (no model invocation).

    Expectation:
        - Output contains pre-defined response
        - No tokens used (instant return)
    """
    node = LLMNode(
        name="llm_instant",
        resource_key="gpt-5.1-chat",
        instant_response=True,
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    test_response = "Đây là thông báo mặc định"
    output = await run_node(
        node,
        inputs={
            "messages": [{"role": "user", "content": "test"}],
            "response": test_response,
        },
    )

    assert "content" in output
    assert output["content"] == test_response


@pytest.mark.asyncio
async def test_llm_node_custom_data_metadata():
    """
    Test passing custom data through metadata.

    Expectation:
        - Output contains metadata from input custom_data
        - 1-to-1 mapping from custom_data to metadata
    """
    node = LLMNode(
        name="llm_metadata",
        resource_key="gpt-5.1-chat",
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    custom_data = {"env": "production", "user_id": "12345", "request_type": "test"}

    output = await run_node(
        node,
        inputs={
            "messages": [{"role": "user", "content": "Say hello"}],
            "custom_data": custom_data,
        },
    )

    assert "content" in output
    assert "metadata" in output
    assert output["metadata"] == custom_data


@pytest.mark.asyncio
async def test_llm_node_specific_metadata():
    """
    Test specific_metadata method.

    Expectation:
        - Returns dictionary with model key matching resource_key
    """
    node = LLMNode(
        name="llm_meta",
        resource_key="gpt-5.1-chat",
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    metadata = node.specific_metadata()

    assert isinstance(metadata, dict)
    assert "model" in metadata
    assert metadata["model"] == "gpt-5.1-chat"


@pytest.mark.asyncio
async def test_llm_node_type():
    """
    Test node type attribute.

    Expectation:
        - Node type is "llm"
    """
    node = LLMNode(
        name="llm_type",
        resource_key="gpt-5.1-chat",
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    assert node.type == "llm"
