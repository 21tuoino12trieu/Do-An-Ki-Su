from typing import Dict, List, Any, Optional, AsyncGenerator
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from beeflow.nodes import BaseNode, NodeType
from beeflow.states import WorkflowState, WorkflowIndexer, StateRegistry
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.tools.schema.param import ParamSet
from beegen.loggings import LOGGER
from collections import defaultdict
from datetime import datetime
import uuid

from beegen.utils.common import fake_chunk_from


class ToolExecutorNode(BaseNode):
    """
    Node that manages and executes tools dynamically by name.
    
    Follows the ForLoopNode pattern - manages child tools with proper state isolation
    and observability integration. Each tool execution gets its own state context.
    """
    type: NodeType = "tool-executor"
    
    input_schema: ParamSet = (
        ParamSet.new()
            .var("tool_name: str", required=True)
            .var("tool_params: Dict[str, Any]", required=True)
            .build()
    )
    
    output_schema: ParamSet = (
        ParamSet.new()
            .var("result: Any", required=True)
            .var("success: bool", required=True)
            .var("error: Optional[str] = None")
            .var("matched_tool: str", required=True)
            .build()
    )
    
    def __init__(
        self,
        tools: List[BaseNode],
        **kwargs
    ) -> None:
        """Initialize ToolExecutorNode from either config or kwargs.
        
        Args:
            config: Optional ToolExecutorNodeConfig object
            name: Node name
            tools: List of BaseNode tools (converted to dict by tool.name)
            **kwargs: Additional keyword arguments
        """
        super().__init__(**kwargs)
        
        if not tools:
            raise ValueError(f"Node {self.full_name}: tools must not be empty!!!")
        
        self._tools: Dict[str, BaseNode] = {}
        
        for tool in tools:
            tool.father = self
            self._tools[tool.name] = tool
            LOGGER.info(f"Registered tool '{tool.name}' with ToolExecutor '{self.full_name}'")

    async def run(
        self,
        state: WorkflowState,
        context_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run the core logic of tool executor node"""
            
        parent_name = self.father.full_name if self.father else None
        state.record_execution(self.full_name, parent_name, context_id)
        
        request_id = state.request_id
        
        start_time = datetime.now()
        
        _outputs = {}
        
        try:
            _inputs = self.get_inputs(state, context_id=context_id)
            
            # Log truncated inputs for debugging
            LOGGER.info("request[%s]: %s, running NODE: %s: %s, inputs = %s", 
                request_id, context_id, self.name, str(self.type).upper(), str(_inputs)[:200])

            tool_name = _inputs.get("tool_name")
            
            tool_params = _inputs.get("tool_params")
            
            if not tool_name or tool_params is None:
                missing = []
                if not tool_name:
                    missing.append("tool_name")
                if tool_params is None:
                    missing.append("tool_params")
                raise ValueError(f"Node {self.full_name}: Missing required parameters: {', '.join(missing)}")

            _tool = self._tools[tool_name]
            state.inject_inputs(
                node=_tool.full_name,
                inputs=tool_params,
                context_id=context_id
            )
                                
            _outputs = await _tool.run(state, context_id=context_id)
            
            LOGGER.info("request[%s]: %s, complete NODE: %s: %s, _outputs = %s", 
                request_id, context_id, self.name, str(self.type).upper(), str(_outputs)[:200])

        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            # Handle errors
            state.set_by_index(self.output_indexes["error_code"], 500, context_id)
            state.set_by_index(self.output_indexes["error_message"], error_msg, context_id)
            
            self.store_result(state, {
                "result": None,
                "success": False,
                "error": error_msg,
                "matched_tool": tool_name
            })
            
            LOGGER.error(f"Tool execution failed: {e}")
                        
            default_answers = 'Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại sau.'
            
            if self.stream:
                asyncio.create_task(STREAM_SERVICE.push(
                    request_id=request_id,
                    channel_name=self.identity(context_id),
                    data=fake_chunk_from(
                        content=default_answers,
                        model="error"
                    )
                ))
        finally:            
            end_time = datetime.now()
            state.set_by_index(self.metrics['start_time'], start_time, context_id=context_id)
            state.set_by_index(self.metrics['end_time'], end_time, context_id=context_id)

            self.store_result(
                state=state,
                result={
                    "result": _outputs,
                    "success": True,
                    "error": None,
                    "matched_tool": tool_name
                },
                context_id=context_id
            )
            
            if self.stream:
                asyncio.create_task(STREAM_SERVICE.end(request_id, self.identity(context_id)))
            
            return _outputs

async def main():
    from beeflow.nodes import BasicChainNode, CodeNode, LambdaNode
    from beeflow.nodes.base_node import INPUT, OUTPUT
    
    calculator_tool = LambdaNode(
        name="calculator",
        code_fn=lambda exp: {"result": eval(exp)},
        return_keys=["result: float"]
    )
    
    weather_tool = BasicChainNode(
        name="weather",
        resource_key="gpt-4o",
        user_prompt="What's the weather like in {city}, return in format <weather_info>...</weather_info>",
        parser="xml",
        extract_schema=["weather_info: str"]
    )
    
    search_tool = LambdaNode(
        name="search",
        code_fn=lambda query: {"results": f"Search results for: {query}"},
        return_keys=["results: str"]
    )
    
    tool_executor = ToolExecutorNode(
        name="tool_manager",
        tools=[calculator_tool, weather_tool, search_tool],  # List of BaseNodes,
        inputs=INPUT,
        outputs=OUTPUT
    )
        
    indexer = WorkflowIndexer(name="workflow01").add_node(tool_executor).build()
        
    state = WorkflowState(
        indexer=indexer,
        inputs={
            "tool_name": "weather",
            "tool_params": {"city": "New York"}
        }
    )
    
    # state.show()
    
    await tool_executor.run(state)
        
    # print(tool_executor.get_result(state))
    

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
       