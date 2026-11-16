"""Unit tests for HumanNode.

Based on human_node.py:
1) Initialize Node
2) Create Indexer and attach Node to the graph
3) Initialize State with request_id
4) Execute node.run(state)
5) Verify result output dict
6) Verify saved value in state

Run:
    pytest tests/beeflow/nodes/human/test_human_node.py -v
"""

import asyncio
import json

import pytest

from beeflow.nodes.human.human_node import HumanNode
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.workflow_state import WorkflowState
from beeflow.utils.streaming import STREAM_SERVICE


class MockStreamService:
    """Mock STREAM_SERVICE for testing without Redis."""

    def __init__(self, response_data=None):
        self.response_data = response_data or []
        self.pushed_data = []
        self.ended_channels = []

    async def push(self, request_id, channel_name, data):
        self.pushed_data.append({"request_id": request_id, "channel_name": channel_name, "data": data})

    async def get(self, request_id, _channel, **_kwargs):
        if self.response_data:
            for data in self.response_data:
                yield data
        else:
            # Never yield to simulate waiting forever (until timeout)
            await asyncio.sleep(1000)

    async def end(self, request_id, channel):
        self.ended_channels.append({"request_id": request_id, "channel": channel})

    def close(self):
        pass


def setup_mock_stream_service(mock_service: MockStreamService):
    """Helper to set up mock on STREAM_SERVICE."""
    STREAM_SERVICE.push = mock_service.push
    STREAM_SERVICE.get = mock_service.get
    STREAM_SERVICE.end = mock_service.end
    STREAM_SERVICE.close = mock_service.close


@pytest.mark.asyncio
async def test_human_node_basic_flow():
    """Test the complete end-to-end flow of HumanNode.

    This test verifies that:
    1. HumanNode can be initialized with a name
    2. Node can be attached to WorkflowIndexer
    3. State is properly initialized with request_id
    4. node.run() executes and waits for user input
    5. Response from frontend is captured correctly
    6. Result is stored in both return value and WorkflowState
    """
    # Set up mock with response data
    mock_service = MockStreamService(
        response_data=[{"content": "I confirm and agree to pay this amount!"}]
    )
    setup_mock_stream_service(mock_service)

    # 1. Initialize Node
    human_node = HumanNode(name="ask_user_confirm")

    # 2. Create Indexer and attach Node to the graph
    indexer = WorkflowIndexer("test_workflow").add_node(human_node).build()

    # 3. Initialize State with fixed request_id
    state = WorkflowState(
        indexer=indexer,
        request_id="req_test_human_999"
    )

    # 4. Execute Human Node
    result = await human_node.run(state)

    # 5. Verify result output dict
    assert "human_input" in result
    assert result["human_input"] == "I confirm and agree to pay this amount!"

    # 6. Verify saved value in state
    saved_value = state[human_node.name, "human_input", None]
    assert saved_value == "I confirm and agree to pay this amount!"


@pytest.mark.asyncio
async def test_human_node_signal_pushed():
    """Test that human_in_the_loop signal is pushed to stream service.

    Verifies:
    - Signal is pushed to 'human_request' channel
    - Request ID is correctly set
    - Signal contains 'type': 'human_in_the_loop'
    - Node name, message, and options are included in signal
    """
    mock_service = MockStreamService(
        response_data=[{"content": "user response"}]
    )
    setup_mock_stream_service(mock_service)

    node = HumanNode(name="test_node")
    indexer = WorkflowIndexer("test").add_node(node).build()
    state = WorkflowState(indexer=indexer, request_id="req_001")

    # Set input values in state
    state.inject_inputs(node.name, {"message": "Test question?", "options": ["Yes", "No"]})

    await node.run(state)

    # Verify signal was pushed
    assert len(mock_service.pushed_data) == 1
    pushed = mock_service.pushed_data[0]
    assert pushed["request_id"] == "req_001"
    assert pushed["channel_name"] == "human_request"

    # Verify signal contains human_in_the_loop type
    data = pushed["data"]
    content = data.choices[0].delta.content
    signal = json.loads(content)
    assert signal["type"] == "human_in_the_loop"
    assert signal["node"] == "test_node"
    assert signal["message"] == "Test question?"
    assert signal["options"] == ["Yes", "No"]


@pytest.mark.asyncio
async def test_human_node_timeout_with_default():
    """Test timeout behavior when default_value is set.

    Scenario: Frontend does not respond within timeout period.
    Expected: Node returns the configured default_value instead of blocking forever.
    """
    mock_service = MockStreamService(response_data=[])  # No response
    setup_mock_stream_service(mock_service)

    node = HumanNode(name="timeout_test")
    indexer = WorkflowIndexer("test").add_node(node).build()
    state = WorkflowState(indexer=indexer, request_id="req_timeout_001")

    # Set input values in state
    state.inject_inputs(node.name, {"timeout": 1, "default_value": "default answer"})

    result = await node.run(state)

    # Should return default_value on timeout
    assert result["human_input"] == "default answer"
    saved_value = state[node.name, "human_input", None]
    assert saved_value == "default answer"


@pytest.mark.asyncio
async def test_human_node_timeout_without_default():
    """Test timeout behavior when no default_value is configured.

    Scenario: Frontend does not respond within timeout period and no default_value set.
    Expected: Node returns 'TIMEOUT_NO_RESPONSE' sentinel value to prevent blocking.
    """
    mock_service = MockStreamService(response_data=[])  # No response
    setup_mock_stream_service(mock_service)

    node = HumanNode(name="timeout_no_default")
    indexer = WorkflowIndexer("test").add_node(node).build()
    state = WorkflowState(indexer=indexer, request_id="req_timeout_002")

    # Set timeout (no default_value)
    state.inject_inputs(node.name, {"timeout": 1})

    result = await node.run(state)

    # Should return TIMEOUT_NO_RESPONSE
    assert result["human_input"] == "TIMEOUT_NO_RESPONSE"


@pytest.mark.asyncio
async def test_human_node_default_message():
    """Test default fallback message when 'message' input is not provided.

    Scenario: HumanNode is created without explicit message input.
    Expected: Signal uses "Waiting for user confirmation..." as default message.
    """
    mock_service = MockStreamService(
        response_data=[{"content": "response"}]
    )
    setup_mock_stream_service(mock_service)

    node = HumanNode(name="default_msg_test")  # No message provided
    indexer = WorkflowIndexer("test").add_node(node).build()
    state = WorkflowState(indexer=indexer, request_id="req_msg_001")

    await node.run(state)

    # Verify default message in signal
    pushed = mock_service.pushed_data[0]
    content = pushed["data"].choices[0].delta.content
    signal = json.loads(content)
    assert signal["message"] == "Waiting for user confirmation..."


@pytest.mark.asyncio
async def test_human_node_no_options():
    """Test default empty options list when 'options' input is not provided.

    Scenario: HumanNode is created without explicit options.
    Expected: Signal includes empty options array [] in the payload.
    """
    mock_service = MockStreamService(
        response_data=[{"content": "response"}]
    )
    setup_mock_stream_service(mock_service)

    node = HumanNode(name="no_opts_test")  # No options provided
    indexer = WorkflowIndexer("test").add_node(node).build()
    state = WorkflowState(indexer=indexer, request_id="req_opts_001")

    await node.run(state)

    # Verify empty options in signal
    pushed = mock_service.pushed_data[0]
    content = pushed["data"].choices[0].delta.content
    signal = json.loads(content)
    assert signal["options"] == []


@pytest.mark.asyncio
async def test_human_node_channel_name():
    """Test that correct Redis channel name is used for response collection.

    Verifies:
    - Response channel follows pattern: 'human_response:{node_name}'
    - STREAM_SERVICE.get() receives the correct channel parameter
    """
    node_name = "my_human_node"
    expected_channel = f"human_response:{node_name}"

    mock_service = MockStreamService(
        response_data=[{"content": "test"}]
    )
    setup_mock_stream_service(mock_service)

    node = HumanNode(name=node_name)
    indexer = WorkflowIndexer("test").add_node(node).build()
    state = WorkflowState(indexer=indexer, request_id="req_channel_001")

    # Capture the channel used in get()
    channels_used = []

    async def capture_get(request_id, channel, **_kwargs):
        channels_used.append(channel)
        async for data in mock_service.get(request_id, channel):
            yield data

    STREAM_SERVICE.get = capture_get
    await node.run(state)

    assert channels_used[0] == expected_channel


@pytest.mark.asyncio
async def test_human_node_custom_timeout():
    """Test that custom timeout value can be configured via state inputs.

    Verifies:
    - Timeout parameter is read from state via get_inputs()
    - Node accepts timeout values passed through inject_inputs()
    """
    mock_service = MockStreamService(
        response_data=[{"content": "response"}]
    )
    setup_mock_stream_service(mock_service)

    custom_timeout = 60
    node = HumanNode(name="custom_timeout_test")
    indexer = WorkflowIndexer("test").add_node(node).build()
    state = WorkflowState(indexer=indexer, request_id="req_timeout_003")

    # Set custom timeout
    state.inject_inputs(node.name, {"timeout": custom_timeout})

    result = await node.run(state)

    # Verify result works with custom timeout
    assert result["human_input"] == "response"
