"""Unit tests for ParserNode with output_response_format mapping.

This suite verifies that ParserNode can:
- Parse JSON, XML, and YAML inputs.
- Select a nested object via `output_response_format` path mapping.
- Return the selected object under the `address` field in the node state.

We parameterize over three formats (JSON/XML/YAML) using equivalent payloads.
The assertions check that `address.city` and `address.zip` match the expected values.

Run:
  pytest tests
"""
import pytest
from beegen.configs import ParserType
from beeflow.nodes.primitives.transform.parser_node import ParserNode

complex_expected = {
    "address": {
        "city": "New York",
        "zip": "10001"
    }
}

json_input = """
{
    "user": {
        "id": 123,
        "name": "John",
        "contacts": [
            {"type": "email", "value": "john@example.com"},
            {"type": "phone", "value": "+123456789"}
        ],
        "address": {
            "city": "New York",
            "zip": "10001"
        }
    }
}
"""

xml_input = """
<company>
    <user>
        <id>123</id>
        <name>John</name>
        <contacts>
            <item>
                <type>email</type>
                <value>john@example.com</value>
            </item>
            <item>
                <type>phone</type>
                <value>+123456789</value>
            </item>
        </contacts>
        <address>
            <city>New York</city>
            <zip>10001</zip>
        </address>
    </user>
</company>
"""

yaml_input = """
user:
  id: 123
  name: John
  contacts:
    - type: email
      value: john@example.com
    - type: phone
      value: "+123456789"
  address:
    city: New York
    zip: "10001"
"""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "parser_type, input_data, response_format",
    [
        (ParserType.JSON, json_input, {"address": "user"}),
        (ParserType.XML, xml_input, {"address": "company.user"}),
        (ParserType.YAML, yaml_input, {"address": "user"}),
    ]
)
async def test_process_with_output_response_format(parser_type, input_data, response_format):
    parser_node = ParserNode(
        name=f"parser_{parser_type}",
        format=parser_type,
        output_schema=["address: dict"],
        output_response_format=response_format
    )
    state = await parser_node.simulate(inputs={"text": input_data})
    assert state[f"parser_{parser_type}", "address"]["city"] == complex_expected["address"]["city"]
    assert state[f"parser_{parser_type}", "address"]["zip"] == complex_expected["address"]["zip"]