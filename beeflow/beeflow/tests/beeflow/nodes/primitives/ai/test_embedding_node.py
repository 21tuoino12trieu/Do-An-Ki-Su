"""
Unit tests for EmbeddingNode using WorkflowState execution.

This test suite covers:
1) Basic text embedding (single string)
2) Batch text embedding (list of strings)
3) Empty text handling

All tests execute nodes via:
- WorkflowIndexer
- WorkflowState
- node.run(state=...)

Run:
    pytest tests\beeflow\nodes\primitives\ai\test_embedding_node.py
"""

import pytest
from typing import Dict, Any

from beeflow.nodes import INPUT, OUTPUT
from beeflow.nodes.primitives.ai.embedding_node import EmbeddingNode
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
async def test_embedding_node_single_text():
    """
    Single text embedding flow.

    Expectation:
        - Output contains "embeddings" key
        - embeddings is a list of list of floats
        - Each embedding vector has expected dimensionality
    """
    node = EmbeddingNode(
        name="emb0",
        resource_key="qwen-embedding",
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    output = await run_node(
        node,
        inputs={
            "texts": "chương trình tình nguyện xanh ở MB có hay lắm không?"
        },
    )

    assert "embeddings" in output
    assert isinstance(output["embeddings"], list)
    assert len(output["embeddings"]) == 1
    assert isinstance(output["embeddings"][0], list)
    assert all(isinstance(x, float) for x in output["embeddings"][0])


@pytest.mark.asyncio
async def test_embedding_node_batch_texts():
    """
    Batch text embedding flow (list of strings).

    Expectation:
        - Output contains "embeddings" key
        - embeddings is a list of list of floats
        - Number of embeddings matches input texts count
        - All embedding vectors have same dimensionality
    """
    node = EmbeddingNode(
        name="emb_batch",
        resource_key="qwen-embedding",
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    texts = [
        "chương trình tình nguyện xanh ở MB có hay lắm không?",
        "Artificial intelligence is transforming the world.",
        "Học Python thật thú vị và bổ ích.",
    ]

    output = await run_node(
        node,
        inputs={"texts": texts},
    )

    assert "embeddings" in output
    assert isinstance(output["embeddings"], list)
    assert len(output["embeddings"]) == len(texts)

    # Check all embeddings are lists of floats with same dimension
    vector_dims = [len(emb) for emb in output["embeddings"]]
    assert all(dims == vector_dims[0] for dims in vector_dims), "All embeddings should have same dimension"
    assert all(isinstance(x, float) for emb in output["embeddings"] for x in emb)


@pytest.mark.asyncio
async def test_embedding_node_empty_text():
    """
    Empty text embedding flow.

    Expectation:
        - Output contains "embeddings" key
        - Empty string still produces valid embedding vector
    """
    node = EmbeddingNode(
        name="emb_empty",
        resource_key="qwen-embedding",
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    output = await run_node(
        node,
        inputs={"texts": ""},
    )

    assert "embeddings" in output
    assert isinstance(output["embeddings"], list)
    assert len(output["embeddings"]) == 1
    assert isinstance(output["embeddings"][0], list)
    assert len(output["embeddings"][0]) > 0  # Empty string should still produce embedding


@pytest.mark.asyncio
async def test_embedding_node_specific_metadata():
    """
    Test specific_metadata method.

    Expectation:
        - Returns dictionary with model key matching resource_key
    """
    node = EmbeddingNode(
        name="emb_metadata",
        resource_key="qwen-embedding",
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    metadata = node.specific_metadata()

    assert isinstance(metadata, dict)
    assert "model" in metadata
    assert metadata["model"] == "qwen-embedding"


@pytest.mark.asyncio
async def test_embedding_node_type():
    """
    Test node type attribute.

    Expectation:
        - Node type is "embedding"
    """
    node = EmbeddingNode(
        name="emb_type",
        resource_key="qwen-embedding",
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    assert node.type == "embedding"
