import asyncio
import sys
from typing import List, Optional, Dict, Any

from beegen.tools.schema.param import ParamSet
# Force use of SelectorEventLoop on Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from beeflow.configs.node_config import NodeType
from beeflow.configs.graph_config import GraphNodeConfig
from beeflow.nodes.graph.graph_node import GraphNode
    
    
class BasicChainNode(GraphNode):
    """A basic chain that combines prompt formatting, LLM generation, and optional parsing.
    
    This node creates a complete LLM processing pipeline that can handle:
    - Simple text generation (prompt → LLM)
    - Structured output generation (prompt → LLM → parser)
    
    The pipeline automatically detects the processing mode based on output_schema:
    - If output_schema is provided: Creates a 3-stage pipeline (Prompt → LLM → Parser)
    - If output_schema is empty: Creates a 2-stage pipeline (Prompt → LLM) 
    
    1. **Text Generation Mode** (when output_schema is empty):
       ```
       Input → PromptNode → LLMNode → Output
       ```
       - Takes input variables and formats them into prompts
       - Generates text using the specified LLM model
       - Returns raw LLM output (content, role, etc.)
    
    2. **Structured Output Mode** (when output_schema is provided):
       ```
       Input → PromptNode → LLMNode → ParserNode → Output
       ```
       - Takes input variables and formats them into prompts
       - Generates text using the specified LLM model
       - Parses the LLM output into structured data based on output_schema
       - Returns parsed structured data
    
    Features:
    - **Auto-variable detection**: Automatically extracts variables from prompt templates
    - **Flexible prompting**: Supports both system and user prompts
    - **Thinking mode**: Can enable/disable LLM thinking process
    - **Streaming support**: Supports real-time output streaming
    - **Parser integration**: Automatic parsing of structured outputs
    
    Args:
        model: LLM model identifier to use for generation
        user_prompt: User prompt template with {variable} placeholders
        system_prompt: Optional system prompt template
        output_schema: List of output variables for structured parsing (e.g. ["result: str", "confidence: float"])
        parser: Parser format for structured output ("xml", "json", etc.)
        llm_configs: forwards it directly (after filtering out None and invalid keys) to the LLMNode.
    
    Example Usage:
        ```python
        # Simple text generation
        pipeline = BasicChainNode(
            name="summarizer",
            model="gpt-4",
            user_prompt="Summarize this text: {text}",
            system_prompt="You are a helpful summarization assistant."
        )
        
        # Structured output generation
        pipeline = BasicChainNode(
            name="classifier",
            model="gpt-4", 
            user_prompt="Classify this text: {text}",
            output_schema=["category: str", "confidence: float"],
            parser="xml"
        )
        ```
    """
        # Allowed keys (aligned with LLMNode.input_schema)
    _LLM_ALLOWED_KEYS = {
        # Special: "messages" is assigned internally, not accepted from llm_config
        # IO & context
        "response", "type_responses"
        # Generation controls
        "temperature", "max_tokens", "top_p", "top_k",
        "frequency_penalty", "presence_penalty", "repetition_penalty",
        # Chat/template/behavior
        "chat_template_kwargs", "stream_options", "system_prompt",
        "stop_sequences", "seed",
        # Response format
        "response_format", "json_schema",
        # Safety
        "safety_settings", "content_filter_level",
        # Context & memory
        "context_window", "conversation_id", "memory_key",
        # Retry/error handling
        "max_retries", "retry_delay", "timeout",
        # Tools
        "tools", "tool_choice",
        # Reasoning
        "reasoning_effort"
    }
    
    input_schema: ParamSet = (
        ParamSet.new()
        .var("custom_data: Dict[str, Any] = {}")
        .var("status_code: int = 200")
        .var("type_responses: List[str] = []")
        .var("status_response: Optional[str] = None")
        .var("disclaimer_response: Optional[str] = None")
        .build()
    )

    def __init__(
        self,
        resource_key: Optional[str] = None,
        user_prompt: Optional[str] = None,
        system_prompt: Optional[str] = None,
        messages_template: Optional[List[Dict[str, Any]]] = None,
        extract_schema: Optional[List[str]] = None,
        parser: str = "xml",
        llm_configs: Optional[Dict[str, Any]] = None,
        type_responses: Optional[List[str]] = None,
        status_response: Optional[str] = None,
        disclaimer_response: Optional[str] = None,
        **kwargs
    ):
        """Initialize LLMPipelineNode from either config or kwargs.

        Args:
            config: Optional LLMPipelineNodeConfig object. If provided, other args are ignored.
            name: Node name
            model: LLM model identifier
            user_prompt: User prompt template with {variable} placeholders
            system_prompt: Optional system prompt template
            output_schema: List of output variables for structured parsing
            output_response_format: A dictionary where each key is a top-level field defined in output_schema, and each value is the parent path (which may be nested) used to locate that field in the output.
            parser: Parser format ("xml", "json", etc.)
            description: Node description
            inputs: Input variable mappings
            stream: Whether to enable streaming
            type_responses: List of response types to return ['answer', 'status_update', 'disclaimer']
            status_response: Static message for status_update type
            disclaimer_response: Static message for disclaimer type
            **kwargs: Additional keyword arguments
        """
        super().__init__(**kwargs)

        self.resource_key = resource_key
        self.user_prompt = user_prompt
        self.system_prompt = system_prompt
        self.messages_template = messages_template
        self.extract_schema = extract_schema
        self.parser = parser
        self.llm_configs = llm_configs or {}
        self.type_responses = type_responses or ["answer"]
        self.status_response = status_response
        self.disclaimer_response = disclaimer_response

        self._build_graph()

    @classmethod
    def _filter_llm_config(cls, cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Keep only allowed keys and values that are not None.
        Do not allow overriding 'messages' from outside.
        """
        if not cfg:
            return {}
        filtered: Dict[str, Any] = {}
        for k, v in cfg.items():
            if k == "messages":
                # 'messages' is handled internally by BasicChain
                continue
            if k in cls._LLM_ALLOWED_KEYS and v is not None:
                filtered[k] = v
        return filtered
    
    def _build_graph(self):
        """Build the internal processing graph based on configuration."""
        from beeflow.nodes import PromptNode, LLMNode, ParserNode, INPUT, START, END, OUTPUT

        def sub(suffix: str) -> str:
            """Generate sub-node name with namespace."""
            return suffix

        has_answer = "answer" in self.type_responses
        has_status = "status_update" in self.type_responses and self.status_response
        has_disclaimer = "disclaimer" in self.type_responses and self.disclaimer_response

        with self:
            # === Answer branch ===
            if has_answer:
                _prompt = PromptNode(
                    name=sub("prompt"),
                    system_prompt=self.system_prompt,
                    user_prompt=self.user_prompt,
                    messages_template=self.messages_template,
                    inputs=INPUT
                )
                llm_overrides = self._filter_llm_config(self.llm_configs)
                llm_inputs: Dict[str, Any] = {
                    "messages": _prompt,
                    "docs": INPUT,
                    "custom_data": INPUT,
                    "status_code": INPUT
                }
                llm_inputs.update(llm_overrides)

                if self.extract_schema:
                    _llm = LLMNode(
                        name=sub("llm"),
                        resource_key=self.resource_key,
                        inputs=llm_inputs,
                        stream=getattr(self, 'stream', False)
                    )
                    _parser = ParserNode(
                        name=sub("parser"),
                        format=self.parser,
                        extract_schema=self.extract_schema,
                        inputs={"text": _llm["content"]},
                        outputs=OUTPUT
                    )
                    START >> _prompt >> _llm >> _parser >> END
                else:
                    _llm = LLMNode(
                        name=sub("llm"),
                        resource_key=self.resource_key,
                        inputs=llm_inputs,
                        outputs=OUTPUT,
                        stream=getattr(self, 'stream', False)
                    )
                    START >> _prompt >> _llm >> END

            # === Status update branch ===
            if has_status:
                _llm_status = LLMNode(
                    name=sub("llm_status"),
                    resource_key="fake",
                    instant_response=True,
                    inputs={
                        "response": self.status_response,
                        "custom_data": {"type_response": "status_update"},
                    },
                    outputs={"content": {OUTPUT: "status_respone"}},
                    stream=getattr(self, 'stream', False)
                )
                START >> _llm_status >> END

            # === Disclaimer branch ===
            if has_disclaimer:
                _llm_disclaimer = LLMNode(
                    name=sub("llm_disclaimer"),
                    resource_key="fake",
                    instant_response=True,
                    inputs={
                        "response": self.disclaimer_response,
                        "custom_data": {"type_response": "disclaimer"},
                    },
                    outputs={"content": {OUTPUT: "disclamer_response"}},
                    stream=getattr(self, 'stream', False)
                )
                START >> _llm_disclaimer >> END

        # Build the internal graph
        self.build()


    

        
    


