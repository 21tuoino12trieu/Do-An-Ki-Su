# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import datetime

from beeflow.nodes import BaseNode, NodeType
from beeflow.states import WorkflowState, WorkflowIndexer, StateRegistry
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.tools.schema.param import ParamSet
from beegen.loggings import LOGGER
from beegen.mcp.base_server import BaseMCPServer
from beegen.configs.mcp.mcp_config import MCPMethod, MCPServer
from beegen.registry.resource_hub import ResourceHub
from beegen.utils.common import fake_chunk_from


class MCPGatewayNode(BaseNode):
    """
    A lightweight node that proxies calls to a local MCP server via ModelRegistry.

    This node follows the new architecture style (similar to ForLoop/ToolExecutor):
    - Implements `run(...)` (no `execute_core`)
    - Uses `get_inputs`, `store_result`, and state metrics recording
    - Emits short user-friendly error messages through STREAM_SERVICE on failure

    Parameters
    ----------
    name : str
        Node name.
    resource_key : MCPServer
        The registered MCP server identifier (e.g., MCPServer.OPENMETADATA).
    method : MCPMethod, optional
        Default method to execute when `run` is called (LIST or CALL). Default: MCPMethod.CALL.

    Inputs (input_schema)
    ---------------------
    tool_name : str
        Tool name to call when `method` is CALL. Ignored for LIST.
    tool_params : Dict[str, Any]
        Tool input payload for CALL.

    Outputs (output_schema)
    -----------------------
    result : Any
        The raw result returned by MCP server.
    success : bool
        Success flag for the MCP operation.
    error : Optional[str]
        Error message (if any).
    method : str
        The MCP method executed ("tools/list" or "tools/call").
    """

    type: NodeType = "mcp-gateway"

    # I/O schema (declarative, used by BaseNode/indexer)
    input_schema: ParamSet = (
        ParamSet.new()
        .var("tool_name: str = ''")
        .var("tool_params: Dict[str, Any] = {}")
        .build()
    )
    output_schema: ParamSet = (
        ParamSet.new()
        .var("result: Any", required=True)
        .var("success: bool", required=True)
        .var("error: Optional[str] = None")
        .var("method: str", required=True)
        .build()
    )

    def __init__(
        self,
        resource_key: str,
        method: MCPMethod = MCPMethod.CALL,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        self.resource_key: str = resource_key
        self.method: MCPMethod = method

        # Resolve MCP server from ModelRegistry
        # Convention: ModelRegistry.self().mcp("mcp:<resource_key.value>")
        key = f"mcp:{self.resource_key}"
        self.server: BaseMCPServer = ResourceHub.self().mcp(key)

    # ---------- Internal ops ----------
    def _op_tools_list(self) -> Dict[str, Any]:
        """Call MCP server to list tools in OpenAI tools schema."""
        try:
            raw = self.server.list_tools()
            tools = self.server.to_openai_tools_schema(raw)
            return {
                "result": tools,
                "success": True,
                "error": None,
                "method": MCPMethod.LIST.value
            }
        except Exception as e:  # noqa: BLE001
            LOGGER.exception("MCPGateway tools/list failed")
            return {
                "result": None,
                "success": False,
                "error": str(e),
                "method": MCPMethod.LIST.value
            }

    def _op_tools_call(
        self, tool_name: str, tool_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Call a specific MCP tool by name with provided inputs."""
        if not tool_name:
            return {
                "result": None,
                "success": False,
                "error": "'tool_name' is required for method 'tools/call'",
                "method": MCPMethod.CALL.value
            }
        try:
            result = self.server.call_tool(tool_name, tool_params)
            return {
                "result": result,
                "success": True,
                "error": None,
                "method": MCPMethod.CALL.value
            }
        except Exception as e:
            LOGGER.exception("MCPGateway tools/call error for '%s'", tool_name)
            return {
                "result": None,
                "success": False,
                "error": str(e),
                "method": MCPMethod.CALL.value
            }

    # ---------- New-arch entrypoint ----------
    async def run(
        self,
        state: WorkflowState,
        context_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute the MCP method (LIST or CALL) according to node configuration.

        - Reads `tool_name` and `tool_params` from state inputs
        - Records execution in StateRegistry
        - Stores results through `store_result`
        - Pushes a fallback error message to STREAM_SERVICE if needed
        """
        parent_name = self.father.full_name if self.father else None
        state.record_execution(self.full_name, parent_name, context_id)
        
        request_id = state.request_id
        start_time = datetime.now()
        _outputs: Dict[str, Any] = {}

        try:
            _inputs = self.get_inputs(state, context_id=context_id)
            LOGGER.info(
                "request[%s]: %s, running NODE: %s: %s, inputs = %s",
                request_id,
                context_id,
                self.full_name,
                str(self.type).upper(),
                str(_inputs)[:200],
            )

            tool_name: str = _inputs.get("tool_name", "")
            tool_params: Dict[str, Any] = _inputs.get("tool_params", {})

            # Dispatch
            if self.method == MCPMethod.LIST:
                _outputs = self._op_tools_list()
            elif self.method == MCPMethod.CALL:
                _outputs = self._op_tools_call(
                    tool_name=tool_name, tool_params=tool_params
                )
            else:
                err = f"Unknown method '{self.method.value}'. Use LIST or CALL."
                _outputs = {
                    "result": None,
                    "success": False,
                    "error": err,
                    "method": self.method.value
                }

            # If error, also prepare a user-friendly message on the stream
            if not _outputs.get("success", False):
                error_msg = _outputs.get("error") or "Unknown error"
                
                if self.stream:
                    asyncio.create_task(STREAM_SERVICE.push(
                        request_id=request_id,
                        channel_name=self.identity(context_id),
                        data=fake_chunk_from(
                            content=(
                                "Xin lỗi, có lỗi xảy ra khi gọi MCP. "
                                "Vui lòng thử lại sau hoặc kiểm tra cấu hình công cụ."
                            ),
                            model="error",
                        )
                    ))
                # Optionally map error_code/message outputs if your node defines them
                if "error_code" in self.output_indexes:
                    state.set_by_index(self.output_indexes["error_code"], 500, context_id)
                if "error_message" in self.output_indexes:
                    state.set_by_index(self.output_indexes["error_message"], error_msg, context_id)

        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            LOGGER.error("MCPGatewayNode[%s] execution failed: %s", self.full_name, e)

            # Map error fields if present in your workflow’s output schema
            if "error_code" in self.output_indexes:
                state.set_by_index(self.output_indexes["error_code"], 500, context_id)
            if "error_message" in self.output_indexes:
                state.set_by_index(self.output_indexes["error_message"], tb, context_id)

            # Fallback stream message
            if self.stream:
                asyncio.create_task(STREAM_SERVICE.push(
                    request_id=request_id,
                    channel_name=self.identity(context_id),
                    data=fake_chunk_from(
                        content=(
                            "Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu MCP của bạn. "
                            "Vui lòng thử lại sau."
                        ),
                        model="error",
                    )
                ))

            # Normalize result payload on fatal errors
            _outputs = {
                "result": None,
                "success": False,
                "error": str(e),
                "method": self.method.value
            }

        finally:            
            end_time = datetime.now()
            # Record metrics if your BaseNode configured indexes
            if "start_time" in self.metrics:
                state.set_by_index(self.metrics["start_time"], start_time, context_id=context_id)
            if "end_time" in self.metrics:
                state.set_by_index(self.metrics["end_time"], end_time, context_id=context_id)

            # Persist the final result (for both success and failure)
            self.store_result(
                state=state,
                result=_outputs,
                context_id=context_id,
            )
            
            if self.stream:
                asyncio.create_task(STREAM_SERVICE.end(request_id, self.identity(context_id)))

        return _outputs


# ------------------- Example (standalone simulate) -------------------
async def _example():
    """
    Minimal self-test using `simulate()` style. Replace with your real workflow.
    """
    from beeflow.states import WorkflowState
    from beeflow.nodes.base_node import INPUT, OUTPUT

    node_list = MCPGatewayNode(
        name="mcp_list",
        resource_key="openmetadata",
        method=MCPMethod.LIST,
    )

    node_call = MCPGatewayNode(
        name="mcp_call",
        resource_key="openmetadata",
        method=MCPMethod.CALL,
        inputs=INPUT,
        outputs=OUTPUT
    )

    indexer = WorkflowIndexer(name="wf").add_node(node_list).add_node(node_call).build()
    state = WorkflowState(
        indexer=indexer, 
        inputs={"tool_name": "search_metadata", "tool_params": {"query": "user", "entity_type": "table", "limit": 2}},
    )

    # 1) tools/list
    await node_list.run(state)
    print("=== tools/list ===")
    print(node_list.get_result(state))

    # 2) tools/call
    await node_call.run(state)
    print("=== tools/call ===")
    print(node_call.get_result(state))
    
    print(node_list.trace_data(state, None))
    
    print(node_call.trace_data(state, None))


if __name__ == "__main__":
    import asyncio
    asyncio.run(_example())
