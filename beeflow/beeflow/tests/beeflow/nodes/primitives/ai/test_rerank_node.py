"""
Unit tests for RerankNode using WorkflowState execution.

This test suite covers:
1) Basic reranking with string documents (List[str])
2) Reranking with dictionary documents (List[Dict])
3) Reranking with empty documents list
4) Reranking with top_k parameter
5) Reranking with threshold parameter
6) specific_metadata method
7) node type attribute

All tests execute nodes via:
- WorkflowIndexer
- WorkflowState
- node.run(state=...)

Run:
    pytest tests/beeflow/nodes/primitives/ai/test_rerank_node.py
"""

import pytest
from typing import Dict, Any

from beeflow.nodes import INPUT, OUTPUT
from beeflow.nodes.primitives.ai.rerank_node import RerankNode
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
async def test_rerank_node_string_documents():
    """
    Basic reranking flow with string documents (List[str]).

    Expectation:
        - Output contains "reranks" key
        - reranks is a list of dictionaries
        - Each reranked document contains "content" and "score" keys
    """
    node = RerankNode(
        name="rerank0",
        resource_key="bge-m3",
        inputs=INPUT,
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "query": "Thời gian xử lý và cung cấp giấy báo có?",
            "documents": [
                "Thời gian xử lý giao dịch là tối đa 04 ngày làm việc.",
                "Phí giao dịch chuyển tiền nhanh 247 là miễn phí.",
                "Hạn mức chuyển tiền tối đa 500 triệu VND.",
            ],
            "top_k": -1,
            "threshold": 0.0,
        },
    )

    assert "reranks" in output
    assert isinstance(output["reranks"], list)
    assert len(output["reranks"]) > 0
    # Each reranked document should contain content and score
    for item in output["reranks"]:
        assert "content" in item
        assert "score" in item
        assert isinstance(item["content"], str)
        assert isinstance(item["score"], (int, float))


@pytest.mark.asyncio
async def test_rerank_node_dict_documents():
    """
    Reranking flow with dictionary documents (List[Dict]).

    Expectation:
        - Output contains "reranks" key
        - Each reranked document contains original dict fields plus "score"
    """
    node = RerankNode(
        name="rerank_dict",
        resource_key="bge-m3",
        inputs=INPUT,
        outputs=OUTPUT,
    )

    documents = [
        {"id": 1, "content": "Thời gian xử lý giao dịch là tối đa 04 ngày làm việc."},
        {"id": 2, "content": "Phí giao dịch chuyển tiền nhanh 247 là miễn phí."},
        {"id": 3, "content": "Hạn mức chuyển tiền tối đa 500 triệu VND."},
    ]

    output = await run_node(
        node,
        inputs={
            "query": "Thời gian xử lý và cung cấp giấy báo có?",
            "documents": documents,
            "top_k": -1,
            "threshold": 0.0,
        },
    )

    assert "reranks" in output
    assert isinstance(output["reranks"], list)
    assert len(output["reranks"]) > 0
    # Each reranked document should contain original fields plus score
    for item in output["reranks"]:
        assert "id" in item
        assert "content" in item
        assert "score" in item
        assert isinstance(item["score"], (int, float))


@pytest.mark.asyncio
async def test_rerank_node_empty_documents():
    """
    Reranking with empty documents list.

    Expectation:
        - Output contains "reranks" key
        - reranks is an empty list
    """
    node = RerankNode(
        name="rerank_empty",
        resource_key="bge-m3",
        inputs=INPUT,
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "query": "Test query",
            "documents": [],
            "top_k": -1,
            "threshold": 0.0,
        },
    )

    assert "reranks" in output
    assert output["reranks"] == []


@pytest.mark.asyncio
async def test_rerank_node_top_k_parameter():
    """
    Reranking with top_k parameter.

    Expectation:
        - Output contains "reranks" key
        - Number of results is limited by top_k
    """
    node = RerankNode(
        name="rerank_topk",
        resource_key="bge-m3",
        inputs=INPUT,
        outputs=OUTPUT,
    )

    documents = [
        "Document 1 about banking",
        "Document 2 about loans",
        "Document 3 about interest rates",
        "Document 4 about savings",
        "Document 5 about credit cards",
    ]

    output = await run_node(
        node,
        inputs={
            "query": "Thông tin về ngân hàng",
            "documents": documents,
            "top_k": 3,
            "threshold": 0.0,
        },
    )

    assert "reranks" in output
    assert isinstance(output["reranks"], list)
    assert len(output["reranks"]) <= 3


@pytest.mark.asyncio
async def test_rerank_node_threshold_parameter():
    """
    Reranking with threshold parameter.

    Expectation:
        - Output contains "reranks" key
        - All scores are above threshold
    """
    node = RerankNode(
        name="rerank_threshold",
        resource_key="bge-m3",
        inputs=INPUT,
        outputs=OUTPUT,
    )

    documents = [
        "Document 1 about banking",
        "Document 2 about technology",
        "Document 3 about food",
        "Document 4 about travel",
    ]

    output = await run_node(
        node,
        inputs={
            "query": "Thông tin về ngân hàng",
            "documents": documents,
            "top_k": -1,
            "threshold": 0.3,
        },
    )

    assert "reranks" in output
    assert isinstance(output["reranks"], list)
    # All scores should be above threshold
    for item in output["reranks"]:
        assert item["score"] >= 0.3


@pytest.mark.asyncio
async def test_rerank_node_specific_metadata():
    """
    Test specific_metadata method.

    Expectation:
        - Returns dictionary with model key matching resource_key
    """
    node = RerankNode(
        name="rerank_meta",
        resource_key="bge-m3",
        inputs=INPUT,
        outputs=OUTPUT,
    )

    metadata = node.specific_metadata()

    assert isinstance(metadata, dict)
    assert "model" in metadata
    assert metadata["model"] == "bge-m3"


@pytest.mark.asyncio
async def test_rerank_node_type():
    """
    Test node type attribute.

    Expectation:
        - Node type is "rerank"
    """
    node = RerankNode(
        name="rerank_type",
        resource_key="bge-m3",
        inputs=INPUT,
        outputs=OUTPUT,
    )

    assert node.type == "rerank"
