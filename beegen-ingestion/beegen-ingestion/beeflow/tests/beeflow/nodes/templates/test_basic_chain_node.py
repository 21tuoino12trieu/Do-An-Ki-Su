"""Unit tests for BasicChainNode template.

This test suite covers three scenarios:
1) Two-stage text generation (Prompt → LLM)
2) Three-stage structured output with XML parsing (Prompt → LLM → Parser(xml))
3) Vision-language template flow with an image in messages_template (Prompt → VLM)

It also includes a lightweight check for auto-variable detection in prompt templates.

Run:
  pytest tests
"""

import os
import pytest
import asyncio

from typing import Dict, Any
from beeflow.nodes.graph.graph_node import GraphNode
from beegen.utils.common import vars_of_prompt

from beeflow.nodes.templates.basic_chain_node import BasicChainNode, BasicChainNodeConfig

SUMMARIZE_SYSTEM = "You are a helpful summarization assistant."
SUMMARIZE_USER = "Please summarize the following text in 1-2 sentences: {text}"

FILTER_USER_XML = (
    "Bạn là bộ lọc nội dung. Với truy vấn: {query}\n"
    "Hãy TRẢ LỜI DUY NHẤT bằng XML đúng schema dưới đây, không thêm gì khác:\n\n"
    "<output>\n"
    "  <filter_type>(safe|toxic)</filter_type>\n"
    "  <confidence>0.0~1.0</confidence>\n"
    "</output>"
)

async def execute_node(node: GraphNode, inputs: Dict[str, Any]):
    """Execute a GraphNode via its simulate() helper and return the emitted state.

    Args:
        node: The graph node under test (e.g., a BasicChainNode instance).
        inputs: A dictionary of input values the node expects.

    Returns:
        dict: The state dictionary produced by the graph execution, keyed by (node_name, field).
    """
    state = await node.simulate(inputs=inputs)
    return state

@pytest.mark.asyncio
async def test_basic_chain_text_generation():
    """Two-stage mode (Prompt → LLM).

    Expectation:
        - The final output for `<name>` contains a "content" field.
        - Here `<name>` is "summarizer", so we assert ("summarizer", "content") exists.
    """
    node = BasicChainNode(
        name="summarizer",
        description="Pipeline for text summarization",
        resource_key="Qwen3-30B-A3B",
        system_prompt=SUMMARIZE_SYSTEM,
        user_prompt=SUMMARIZE_USER,
        stream=False,
    )

    inputs = {
        "text": (
            "Artificial intelligence (AI) is intelligence demonstrated by machines, "
            "as opposed to the natural intelligence displayed by animals and humans."
        ),
        "docs": [],
        "status_code": 200,
    }
    state = await execute_node(node, inputs)

    content_key = ("summarizer", "content")

    assert content_key in state
    assert isinstance(state[content_key], (str, list))


@pytest.mark.asyncio
async def test_basic_chain_structured_output_xml():
    """Three-stage mode (Prompt → LLM → Parser(xml)).

    Expectation:
        - The final output for `<name>` contains parsed fields from the XML:
          specifically "filter_type" and "confidence".
        - Here `<name>` is "content_filter".
    """
    node = BasicChainNode(
        name="content_filter",
        description="Pipeline for filtering inappropriate content",
        resource_key="Qwen3-30B-A3B",
        user_prompt=FILTER_USER_XML,
        output_schema=["filter_type: str", "confidence: float"],
        output_response_format={"filter_type": "output", "confidence": "output"},
        parser="xml",
        stream=False,
    )

    inputs = {
        "query": "thằng khốn, tao kill mày", 
    }
    state = await execute_node(node, inputs)

    possible_ok = [
        ("content_filter", "filter_type"),
        ("content_filter", "confidence")
    ]
    assert all(k in state for k in possible_ok)


@pytest.mark.asyncio
async def test_basic_chain_vlm_template():
    """VLM flow (messages_template with an image).

    Expectation:
        - The final output for `<name>` contains a "content" field.
        - Here `<name>` is "ocr", so we assert ("ocr", "content") exists.
    """
    node = BasicChainNode(
        name="ocr",
        resource_key="gpt-4o",
        messages_template=[
            {"role": "system", "content": "Bạn là chuyên gia bóc tách thông tin trong ảnh"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Trích xuất toàn bộ thông tin có trong ảnh"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,{image_data}"}
                    }
                ]
            }
        ],
        stream=False,
    )

    inputs = {
        "image_data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
    }
    state = await execute_node(node, inputs)

    content_key = ("ocr", "content")


    assert content_key in state
    assert isinstance(state[content_key], (str, list))

@pytest.mark.asyncio
async def test_prompt_vars_detection_only():
    """Lightweight check for auto-variable detection on user_prompt/messages_template.

    This test does not invoke any model; it only verifies that placeholder variables
    are correctly discovered by vars_of_prompt().
    """
    user_prompt = "Xin chào {name}, hôm nay là {date}."
    vars_found = vars_of_prompt(user_prompt)
    assert set(vars_found) == {"name", "date"}
