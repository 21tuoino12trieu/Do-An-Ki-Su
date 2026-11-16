from typing import Dict, Any, AsyncGenerator, Optional
from beeflow.utils.streaming import STREAM_SERVICE
from beeflow.configs import NodeConfig, NodeType
from beeflow.nodes.base_node import BaseNode
from beegen.registry.resource_hub import ResourceHub
from beegen.tools.schema.param import ParamSet
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from beeflow.states.workflow_state import WorkflowState
from datetime import datetime
from beegen.loggings import LOGGER
from beegen.utils.common import fake_chunk_from
import asyncio


class LLMNodeConfig(NodeConfig):
    """Configuration for a llm node node in the workflow."""
    type: NodeType = "llm"
    
    contain_generation: bool = True
    
    instant_response: bool = False
        
    model: str
    
    
class LLMNode(BaseNode):
    """Class for llm node in the beeflow graph"""    
    __slots__ = [
        'resource_key',  # The llm model name/identifier
        'instant_response'
    ]
    
    type: NodeType = "llm"
    
    input_schema: ParamSet = (
        ParamSet.new()
            # Existing parameters
            .var("messages: List", required=True)
            .var("response: Optional[str] = None")
            .var("docs: List[str] = []")
            .var("status_code: int = 200")
            
            # Generation control parameters
            .var("temperature: float = 0.0")
            .var("max_tokens: Optional[int] = None")
            .var("top_p: float = 1.0")
            .var("top_k: Optional[int] = 1")
            .var("frequency_penalty: float = 0.0")
            .var("presence_penalty: float = 0.0")
            .var("repetition_penalty: float = 1.0")
            
            # Chat template and behavior control
            .var("chat_template_kwargs: Dict[str, Any] = {'enable_thinking': False}")
            .var("stream_options: Dict[str, Any] = {'include_usage': True}")
            .var("system_prompt: Optional[str] = None")
            .var("stop_sequences: List[str] = []")
            .var("seed: Optional[int] = None")
            
            # Response format control
            .var("response_format: Optional[str] = None")  # 'json', 'text', 'structured'
            .var("json_schema: Optional[Dict] = None")
            
            # Safety and moderation
            .var("safety_settings: Dict[str, Any] = {}")
            .var("content_filter_level: str = 'default'")
            
            # Tool/function calling
            .var("tools: List[Dict] = []")
            .var("tool_choice: Optional[str] = 'none'")  # 'auto', 'none', specific tool
            
            # Context and memory
            .var("context_window: Optional[int] = None")
            .var("conversation_id: Optional[str] = None")
            .var("memory_key: Optional[str] = None")
            
            # Retry and error handling
            .var("max_retries: int = 1")
            .var("retry_delay: float = 1.0")
            .var("timeout: float = 120.0")
            
            # Resonging
            .var("reasoning_effort: Optional[str] = 'high'")

            # Custom data
            .var("custom_data: Dict[Any, Any] = {}") # Special variable: 1-to-1 mapping from input (custom_data) to output (metadata)
            
            .var("drop_params: bool = True")
            
            .build()
    )
    
    output_schema: ParamSet = (
        ParamSet.new()
            # Basic response
            .var("role: str = 'assistant'")
            .var("content: str", required=True)
            
            # Generation metadata
            .var("finish_reason: Optional[str] = None")  # 'stop', 'length', 'content_filter'
            .var("model_used: str", required=True)
            .var("tokens_used: Dict[str, int] = {}")  # {'prompt': 0, 'completion': 0, 'total': 0}
            
            # Tool usage (when available)
            .var("tool_calls: List[Dict] = []")
            
            # Thinking process (when enabled)
            .var("thinking_content: Optional[str] = None")
            
            # Context monitoring
            .var("context_used: int = 0")
            
            # Error handling
            .var("error_code: Optional[int] = None")
            .var("error_message: Optional[str] = None")
            
            # Custom data
            .var("metadata: Dict[Any, Any] = {}") # Special variable: 1-to-1 mapping from input (custom_data) to output (metadata)
            .build()
    )     
    
    def __init__(
        self, 
        resource_key: Optional[str] = None,
        instant_response: Optional[bool] = None,
        **kwargs
    ):
        """Initialize LLMNode from either config or kwargs.
        
        Args:
            model: LLM model name (required if config not provided)
            instant_response: Whether to return instant response
            **kwargs: Additional keyword arguments for NodeConfig
        """
        super().__init__(**kwargs)
        
        self.resource_key = resource_key
        self.instant_response = instant_response
        self.contain_generation = True
                
        if not self.instant_response:
            if self.stream:
                self.core = ResourceHub.self().llm(self.resource_key).stream
            else:
                self.core = ResourceHub.self().llm(self.resource_key).generate
                                                        
    async def run(
        self,
        state: WorkflowState,
        context_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run the core logic of llm node with the given state and inputs""" 
                       
        parent_name = self.father.full_name if self.father else None
        state.record_execution(self.full_name, parent_name, context_id)
        
        request_id = state.request_id
        
        start_time = datetime.now()
        
        response = ""
        thinking_content = ""  # Accumulate thinking content
        finish_reason = "stop"
        tokens_used = {"prompt": 0, "completion": 0, "total": 0}
        tool_calls = []
        thinking_content = None
        context_used = 0
        
        try:
            _inputs = self.get_inputs(state, context_id=context_id)
            
            # Log truncated inputs for debugging
            LOGGER.info("request[%s]: %s, running NODE: %s: %s, inputs = %s", 
                request_id, context_id or 'main', self.name, str(self.type).upper(), str(_inputs)[:200])
            
            if self.instant_response:
                response = _inputs.get("response", "Đây là thông báo mặc định")
                if self.stream:               
                    asyncio.create_task(STREAM_SERVICE.push(
                        request_id=request_id,
                        channel_name=self.identity(context_id),
                        data=fake_chunk_from(content=response, model=self.resource_key, chat_id=self.id, metadata=_inputs.get("custom_data", {}))
                    ))
                
            else:                
                if self.stream:
                    LOGGER.info("Streaming mode...")
                    first_chunk = True
                    finish_reason = None
                    tokens_used = {}
                    tool_calls = []
                                        
                    async for chunk in self.core(**_inputs, metadata=_inputs.get("custom_data", {})):
                        if first_chunk:
                            state.set_by_index(
                                index=self.metrics["completion_start_time"], 
                                value=datetime.now(),
                                context_id=context_id
                            )
                            first_chunk = False
                        
                        # Extract data from chunk
                        if chunk.usage:
                            tokens_used = chunk.usage.model_dump()
                            state.set_by_index(
                                index=self.metrics["usage"], 
                                value=tokens_used,
                                context_id=context_id
                            )
                        
                        if chunk.choices:
                            choice = chunk.choices[0]
                            
                            # Accumulate thinking content
                            if hasattr(choice.delta, 'reasoning_content'):
                                thinking_content += choice.delta.reasoning_content
                            
                            # Accumulate main content
                            if choice.delta.content:
                                response += choice.delta.content
                            
                            # Capture finish reason
                            if choice.finish_reason:
                                finish_reason = choice.finish_reason
                            
                            # Capture tool calls
                            if choice.delta.tool_calls:
                                tool_calls.extend([tc.model_dump() for tc in choice.delta.tool_calls])
                        
                        asyncio.create_task(STREAM_SERVICE.push(
                            request_id=request_id,
                            channel_name=self.identity(context_id), 
                            data=chunk
                        ))
                        
                else:
                    LOGGER.info("Generate mode...")
                    completion = await self.core(**_inputs)
                    response = completion.choices[0].message.content or ""
                    finish_reason = completion.choices[0].finish_reason
                    
                    # Extract thinking content from non-streaming response
                    if hasattr(completion.choices[0].message, 'reasoning_content'):
                        thinking_content = completion.choices[0].message.reasoning_content or ""
                                        
                    # Extract usage info
                    if completion.usage:
                        tokens_used = completion.usage.model_dump()
                    else:
                        tokens_used = {"prompt": 0, "completion": 0, "total": 0}
                        
                    state.set_by_index(
                        index=self.metrics["usage"], 
                        value=tokens_used,
                        context_id=context_id
                    )
                        
                    # Extract tool calls
                    if completion.choices[0].message.tool_calls:
                        tool_calls = [tc.model_dump() for tc in completion.choices[0].message.tool_calls]
                    else:
                        tool_calls = []
            
            # Calculate context used (estimate based on input)
            context_used = len(str(_inputs.get("messages", []))) // 4  # Rough token estimate
            # Pass metadata
            metadata = _inputs.get("custom_data", {})
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            # Handle errors
            state.set_by_index(self.output_indexes["error_code"], 500, context_id)
            state.set_by_index(self.output_indexes["error_message"], error_msg, context_id)
            state[self.full_name, "error", context_id] = error_msg
            
            LOGGER.error(f"LLM execution failed: {e}")
                        
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
            # Always record timing metrics
            await asyncio.sleep(0.000001)            
            
            end_time = datetime.now()
            state.set_by_index(self.metrics['start_time'], start_time, context_id=context_id)
            state.set_by_index(self.metrics['end_time'], end_time, context_id=context_id)
        
            # Store all outputs
            state.set_by_index(self.output_indexes["content"], response, context_id)
            state.set_by_index(self.output_indexes["role"], "assistant", context_id)
            state.set_by_index(self.output_indexes["model_used"], self.resource_key, context_id)
            if finish_reason:
                state.set_by_index(self.output_indexes["finish_reason"], finish_reason, context_id)
            if tokens_used:
                state.set_by_index(self.output_indexes["tokens_used"], tokens_used, context_id)
            if tool_calls:
                state.set_by_index(self.output_indexes["tool_calls"], tool_calls, context_id)
            if thinking_content:
                state.set_by_index(self.output_indexes["thinking_content"], thinking_content if thinking_content else None, context_id)
            if context_used:
                state.set_by_index(self.output_indexes["context_used"], context_used, context_id)
            if metadata:
                state.set_by_index(self.output_indexes["metadata"], metadata, context_id)

            if self.stream:
                asyncio.create_task(STREAM_SERVICE.end(request_id, self.identity(context_id)))

            return self.get_result(state)
        
    def specific_metadata(self) -> Dict[str, Any]:
        """Return llm-specific metadata dictionary."""
        return {
            "model": self.resource_key
        }
        

async def main():
    
    from beeflow.states.workflow_indexer import WorkflowIndexer
    from beeflow.states.workflow_state import WorkflowState
    from beeflow.nodes.base_node import INPUT, OUTPUT
    
    llm_node = LLMNode(
        name="llm0",
        # instant_response=True,
        resource_key="gpt-5.1-chat",
        inputs=INPUT,
        outputs=OUTPUT,
        # stream=True
    )
        
    indexer = WorkflowIndexer(name="workflow01").add_node(llm_node).build()
    
    state = WorkflowState(
        indexer=indexer, 
        inputs={
            "messages": [{"role": "user", "content": "xin chào"}],
            "custom_data": {"env": "production"},
            # "response": "hahah"
        }
    )
    
    async def publish():
        await llm_node.run(state=state)
        await STREAM_SERVICE.end_request(state.request_id)
            
    asyncio.create_task(publish())

    
    async for channel_name in STREAM_SERVICE.get_channels(state.request_id):
        print(f"\nChannel: {channel_name}")
        async for chunk in STREAM_SERVICE.get(state.request_id, channel_name):
            print(chunk.choices[0].delta.content, end="", flush=True)
        print()
    
    # async for chunk in STREAM_SERVICE.get(state.request_id):
    #     print(chunk.choices[0].delta.content)
    
    # print(llm_node.trace_data(state, None))
    

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
