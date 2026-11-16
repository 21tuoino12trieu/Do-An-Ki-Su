"""Unit tests for BasicChainNode template.

This test suite covers:
1) Two-stage text generation (Prompt → LLM)
2) Three-stage structured output with XML parsing (Prompt → LLM → Parser(xml))
3) Vision-language template flow with an image in messages_template
4) type_responses feature (answer, status_update, disclaimer)
5) Auto-variable detection in prompt templates

Run:
  pytest tests/beeflow/nodes/templates/test_basic_chain_node.py -v
"""

import pytest

from typing import Dict, Any
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.workflow_state import WorkflowState
from beeflow.nodes.base_node import INPUT, OUTPUT
from beegen.utils.common import vars_of_prompt

from beeflow.nodes.templates.basic_chain_node import BasicChainNode

# Test constants
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


@pytest.mark.asyncio
async def test_basic_chain_text_generation():
    """Two-stage mode (Prompt → LLM).

    Expectation:
        - The final result contains a "content" field from the LLM.
        - Node name is "summarizer".
    """
    summarizer = BasicChainNode(
        name="summarizer",
        description="Pipeline for text summarization",
        resource_key="gemini-2.5-flash-chat",
        system_prompt=SUMMARIZE_SYSTEM,
        user_prompt=SUMMARIZE_USER,
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    indexer = WorkflowIndexer(name="workflow01").add_node(summarizer).build()

    state = WorkflowState(
        indexer=indexer,
        inputs={
            "text": (
                "Artificial intelligence (AI) is intelligence demonstrated by machines, "
                "in contrast to the natural intelligence displayed by animals and humans."
            ),
            "docs": [],
            "status_code": 200,
        },
    )

    await summarizer.run(state=state)
    result = summarizer.get_result(state)

    assert result is not None
    assert "content" in result
    assert isinstance(result["content"], (str, list))


@pytest.mark.asyncio
async def test_basic_chain_structured_output_xml():
    """Three-stage mode (Prompt → LLM → Parser(xml)).

    Expectation:
        - The final result contains parsed fields from XML:
          "filter_type" and "confidence".
        - Node name is "content_filter".
    """
    content_filter = BasicChainNode(
        name="content_filter",
        description="Pipeline for filtering inappropriate content",
        resource_key="gemini-2.5-flash-chat",
        user_prompt=FILTER_USER_XML,
        extract_schema=["filter_type: str", "confidence: float"],
        parser="xml",
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    indexer = WorkflowIndexer(name="workflow01").add_node(content_filter).build()

    state = WorkflowState(
        indexer=indexer,
        inputs={"query": "thằng khốn, tao kill mày"},
    )

    await content_filter.run(state=state)
    result = content_filter.get_result(state)

    assert result is not None
    assert "filter_type" in result
    assert "confidence" in result


@pytest.mark.asyncio
async def test_basic_chain_vlm_template():
    """VLM flow (messages_template with an image).

    Expectation:
        - The final result contains a "content" field.
        - Node name is "ocr".
    """
    ocr = BasicChainNode(
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
                        "image_url": {"url": "data:image/png;base64,{image_data}"},
                    },
                ],
            },
        ],
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    indexer = WorkflowIndexer(name="workflow01").add_node(ocr).build()

    state = WorkflowState(
        indexer=indexer,
        inputs={
            "image_data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC",
        },
    )

    await ocr.run(state=state)
    result = ocr.get_result(state)

    assert result is not None
    assert "content" in result
    assert isinstance(result["content"], (str, list))


@pytest.mark.asyncio
async def test_basic_chain_type_responses_answer_only():
    """Test type_responses with only 'answer' (default behavior).

    Expectation:
        - Only the answer branch runs.
        - Result contains "content" field.
    """
    answer_node = BasicChainNode(
        name="answer_node",
        resource_key="gemini-2.5-flash-chat",
        user_prompt="Say hello in one word: {name}",
        type_responses=["answer"],
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    indexer = WorkflowIndexer(name="workflow01").add_node(answer_node).build()

    state = WorkflowState(
        indexer=indexer,
        inputs={"name": "World", "docs": [], "status_code": 200},
    )

    await answer_node.run(state=state)
    result = answer_node.get_result(state)

    assert result is not None
    assert "content" in result


@pytest.mark.asyncio
async def test_basic_chain_type_responses_with_status():
    """Test type_responses with 'answer' and 'status_update'.

    Expectation:
        - Answer branch produces content.
        - Status branch produces status_response.
    """
    multi_response = BasicChainNode(
        name="multi_response",
        resource_key="gemini-2.5-flash-chat",
        user_prompt="Return a brief introduction: {name}",
        type_responses=["answer", "status_update"],
        status_response="Processing complete",
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    indexer = WorkflowIndexer(name="workflow01").add_node(multi_response).build()

    state = WorkflowState(
        indexer=indexer,
        inputs={"name": "Alice", "docs": [], "status_code": 200},
    )

    await multi_response.run(state=state)
    result = multi_response.get_result(state)

    assert result is not None
    assert "content" in result
    assert "status_respone" in result
    assert result["status_respone"] == "Processing complete"


@pytest.mark.asyncio
async def test_basic_chain_type_responses_with_disclaimer():
    """Test type_responses with 'answer' and 'disclaimer'.

    Expectation:
        - Answer branch produces content.
        - Disclaimer branch produces disclaimer_response.
    """
    disclaimer_node = BasicChainNode(
        name="disclaimer_node",
        resource_key="gemini-2.5-flash-chat",
        user_prompt="Give me a fact: {topic}",
        type_responses=["answer", "disclaimer"],
        disclaimer_response="This is for informational purposes only.",
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    indexer = WorkflowIndexer(name="workflow01").add_node(disclaimer_node).build()

    state = WorkflowState(
        indexer=indexer,
        inputs={"topic": "science", "docs": [], "status_code": 200},
    )

    await disclaimer_node.run(state=state)
    result = disclaimer_node.get_result(state)

    assert result is not None
    assert "content" in result
    assert "disclamer_response" in result
    assert result["disclamer_response"] == "This is for informational purposes only."


@pytest.mark.asyncio
async def test_basic_chain_all_response_types():
    """Test all three response types: answer, status_update, disclaimer.

    Expectation:
        - All three branches produce output.
    """
    full_node = BasicChainNode(
        name="full_node",
        resource_key="gemini-2.5-flash-chat",
        user_prompt="Tell me a joke: {category}",
        type_responses=["answer", "status_update", "disclaimer"],
        status_response="Done",
        disclaimer_response="Not financial advice.",
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    indexer = WorkflowIndexer(name="workflow01").add_node(full_node).build()

    state = WorkflowState(
        indexer=indexer,
        inputs={"category": "programming", "docs": [], "status_code": 200},
    )

    await full_node.run(state=state)
    result = full_node.get_result(state)

    assert result is not None
    assert "content" in result
    assert "status_respone" in result
    assert "disclamer_response" in result


@pytest.mark.asyncio
async def test_basic_chain_llm_configs_filtering():
    """Test that llm_configs filters out invalid keys.

    Expectation:
        - Only allowed keys are passed to LLMNode.
        - Node executes successfully with valid config overrides.
    """
    config_filter = BasicChainNode(
        name="config_filter",
        resource_key="gemini-2.5-flash-chat",
        user_prompt="Explain {topic} in one sentence",
        llm_configs={
            "temperature": 0.7,
            "max_tokens": 100,
            "invalid_key": "should_be_ignored",
            "messages": "should_not_be_passed",
        },
        inputs=INPUT,
        outputs=OUTPUT,
        stream=False,
    )

    indexer = WorkflowIndexer(name="workflow01").add_node(config_filter).build()

    state = WorkflowState(
        indexer=indexer,
        inputs={"topic": "quantum physics", "docs": [], "status_code": 200},
    )

    await config_filter.run(state=state)
    result = config_filter.get_result(state)

    assert result is not None
    assert "content" in result


@pytest.mark.asyncio
async def test_prompt_vars_detection():
    """Test auto-variable detection on user_prompt.

    This test does not invoke any model; it only verifies that placeholder
    variables are correctly discovered by vars_of_prompt().
    """
    user_prompt = "Xin chào {name}, hôm nay là {date}."
    vars_found = vars_of_prompt(user_prompt)
    assert set(vars_found) == {"name", "date"}


@pytest.mark.asyncio
async def test_prompt_vars_detection_nested():
    """Test variable detection with nested braces in template."""
    user_prompt = "Translate '{phrase}' to {target_lang}."
    vars_found = vars_of_prompt(user_prompt)
    assert set(vars_found) == {"phrase", "target_lang"}
