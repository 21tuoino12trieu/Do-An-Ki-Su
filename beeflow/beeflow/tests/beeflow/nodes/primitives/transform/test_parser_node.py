"""
Unit tests for ParserNode using WorkflowState execution.

This test suite covers:
1) XML parser - default format
2) YAML parser
3) JSON parser
4) Key-Value parser
5) Regex parser
6) Structured parser
7) Extract field path traversal
8) specific_metadata method
9) node type attribute

Run:
    pytest tests/beeflow/nodes/primitives/transform/test_parser_node.py
"""

import pytest
from typing import Dict, Any

from beeflow.nodes import INPUT, OUTPUT
from beeflow.nodes.primitives.transform.parser_node import ParserNode
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.workflow_state import WorkflowState
from beegen.configs import ParserType


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
async def test_parser_node_xml_format():
    """
    Test XML parser format (default).

    Expectation:
        - Output contains extracted fields from XML
    """
    node = ParserNode(
        name="parser_xml",
        format=ParserType.XML,
        extract_schema=["xml.name: str", "xml.age: str"],
        inputs=INPUT,
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "text": """<xml>
<name>John & Doe</name>
<age>30</age>
</xml>"""
        },
    )

    assert "name" in output
    assert "age" in output
    assert output["name"] == "John & Doe"
    assert output["age"] == "30"


@pytest.mark.asyncio
async def test_parser_node_yaml_format():
    """
    Test YAML parser format.

    Expectation:
        - Output contains extracted fields from YAML
    """
    node = ParserNode(
        name="parser_yaml",
        format=ParserType.YAML,
        extract_schema=["name: str", "bank_number: str"],
        inputs=INPUT,
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "text": """```yaml
name: Khuat nguyen cuong
bank_number: 05225222
```"""
        },
    )

    assert "name" in output
    assert "bank_number" in output
    assert output["name"] == "Khuat nguyen cuong"
    assert output["bank_number"] == "05225222"


@pytest.mark.asyncio
async def test_parser_node_json_format():
    """
    Test JSON parser format.

    Expectation:
        - Output contains extracted fields from JSON
    """
    node = ParserNode(
        name="parser_json",
        format=ParserType.JSON,
        extract_schema=["name: str", "email: str"],
        inputs=INPUT,
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "text": """{"name": "Jane Doe", "email": "jane@example.com"}"""
        },
    )

    assert "name" in output
    assert "email" in output
    assert output["name"] == "Jane Doe"
    assert output["email"] == "jane@example.com"


@pytest.mark.asyncio
async def test_parser_node_key_value_format():
    """
    Test Key-Value parser format.

    Expectation:
        - Output contains extracted fields from key-value pairs
    """
    node = ParserNode(
        name="parser_kv",
        format=ParserType.KEY_VALUE,
        extract_schema=["key1: str", "key2: str"],
        separator="=",
        inputs=INPUT,
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "text": """key1=value1
key2=value2"""
        },
    )

    assert "key1" in output
    assert "key2" in output
    assert output["key1"] == "value1"
    assert output["key2"] == "value2"


@pytest.mark.asyncio
async def test_parser_node_regex_format():
    """
    Test REGEX parser format.

    Expectation:
        - Output contains extracted fields matching regex pattern
    """
    node = ParserNode(
        name="parser_regex",
        format=ParserType.REGEX,
        extract_schema=["email: str"],
        pattern=r"(?P<email>[\w\.-]+@[\w\.-]+\.\w+)",
        inputs=INPUT,
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "text": "support@example.com Please contact us for help"
        },
    )

    assert "email" in output
    assert output["email"] == "support@example.com"


@pytest.mark.asyncio
async def test_parser_node_structured_format():
    """
    Test Structured parser format.

    Expectation:
        - Output contains extracted fields based on template
    """
    node = ParserNode(
        name="parser_structured",
        format=ParserType.STRUCTURED,
        extract_schema=["label: str"],
        template="<output>{label}</output>",
        inputs=INPUT,
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "text": "<output>co_lien_quan</output>"
        },
    )

    assert "label" in output
    assert output["label"] == "co_lien_quan"


@pytest.mark.asyncio
async def test_parser_node_nested_path():
    """
    Test nested path extraction with dot notation.

    Expectation:
        - Output contains nested field extracted using chain path
    """
    node = ParserNode(
        name="parser_nested",
        format=ParserType.JSON,
        extract_schema=["company.user.address: str"],
        inputs=INPUT,
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "text": """{
                "company": {
                    "user": {
                        "address": "123 Main St"
                    }
                }
            }"""
        },
    )

    assert "address" in output
    assert output["address"] == "123 Main St"


@pytest.mark.asyncio
async def test_parser_node_empty_text():
    """
    Test empty text input.

    Expectation:
        - Returns empty dict
    """
    node = ParserNode(
        name="parser_empty",
        format=ParserType.XML,
        extract_schema=["name: str"],
        inputs=INPUT,
        outputs=OUTPUT,
    )

    output = await run_node(
        node,
        inputs={
            "text": ""
        },
    )

    assert output == {}


@pytest.mark.asyncio
async def test_parser_node_specific_metadata():
    """
    Test specific_metadata method.

    Expectation:
        - Returns dictionary with format, separator, template, pattern
    """
    node = ParserNode(
        name="parser_meta",
        format=ParserType.YAML,
        extract_schema=["name: str"],
        separator="=",
        template=None,
        pattern=None,
        inputs=INPUT,
        outputs=OUTPUT,
    )

    metadata = node.specific_metadata()

    assert isinstance(metadata, dict)
    assert "format" in metadata
    assert metadata["format"] == ParserType.YAML
    assert metadata["separator"] == "="


@pytest.mark.asyncio
async def test_parser_node_type():
    """
    Test node type attribute.

    Expectation:
        - Node type is "parser"
    """
    node = ParserNode(
        name="parser_type",
        format=ParserType.XML,
        extract_schema=["name: str"],
        inputs=INPUT,
        outputs=OUTPUT,
    )

    assert node.type == "parser"


@pytest.mark.asyncio
async def test_parser_node_missing_extract_schema():
    """
    Test that missing extract_schema raises TypeError.

    Expectation:
        - Raises TypeError with appropriate message
    """
    with pytest.raises(TypeError) as exc_info:
        ParserNode(
            name="parser_no_schema",
            format=ParserType.XML,
            inputs=INPUT,
            outputs=OUTPUT,
        )

    assert "extract_schema" in str(exc_info.value)
