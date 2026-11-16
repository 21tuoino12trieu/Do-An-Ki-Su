from beeflow.nodes.base_node import BaseNode
from beeflow.configs import NodeConfig, NodeType
from beegen.loggings.loggers import LOGGER
from beegen.tools.schema.param import ParamSet
from beegen.utils.common import ensure_async
from typing import Dict, Any, Optional, List, Set
from functools import lru_cache, cached_property
import re


# region============= Optimized Utility Classes =============

class VariableExtractor:
    """Efficiently extracts and caches template variables."""
    
    @staticmethod
    @lru_cache(maxsize=128)
    def from_string(template: str) -> Set[str]:
        return set(re.findall(r'{([^}]*)}', template))
    
    @classmethod
    def from_content(cls, content: Any) -> Set[str]:
        variables = set()
        
        if isinstance(content, str):
            variables.update(cls.from_string(content))
        elif isinstance(content, list):
            for item in content:
                variables.update(cls.from_content(item))
        elif isinstance(content, dict):
            for value in content.values():
                variables.update(cls.from_content(value))
        
        return variables


class OptimizedMessageFormatter:
    """Optimized message formatting with minimal overhead."""
    
    @staticmethod
    def format_value(value: Any, context: Dict[str, Any]) -> Any:
        """Optimized recursive formatter with type-specific handling."""
        value_type = type(value)
        
        if value_type is str:
            # Fast path for strings - avoid try/except for performance
            return value.format_map(context)  # format_map is faster than format(**context)
        elif value_type is dict:
            # Pre-allocate dict with known size
            return {k: OptimizedMessageFormatter.format_value(v, context) for k, v in value.items()}
        elif value_type is list:
            # Use list comprehension for speed
            return [OptimizedMessageFormatter.format_value(item, context) for item in value]
        
        return value
    
    @staticmethod
    def format_message(template: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Format a complete message template with minimal copying."""
        return OptimizedMessageFormatter.format_value(template, context)


class PrecompiledMessageBuilder:
    """Pre-compiled message builder that avoids repeated work."""
    
    def __init__(self,
                 system_prompt: Optional[str] = None,
                 user_prompt: Optional[str] = None,
                 messages_template: Optional[List[Dict[str, Any]]] = None):
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.messages_template = messages_template
        
        # Pre-compile templates for faster execution
        self._precompiled_templates = None
        self._simple_system_template = None
        self._simple_user_template = None
        
        self._precompile()
    
    def _precompile(self):
        """Pre-compile templates to avoid repeated parsing."""
        if self.messages_template:
            # Pre-parse templates to identify which parts need formatting
            self._precompiled_templates = []
            for template in self.messages_template:
                compiled = self._precompile_single_template(template)
                self._precompiled_templates.append(compiled)
        
        # Pre-compile simple templates
        if self.system_prompt:
            self._simple_system_template = self._precompile_string(self.system_prompt)
        if self.user_prompt:
            self._simple_user_template = self._precompile_string(self.user_prompt)
    
    def _precompile_string(self, template: str):
        """Pre-compile a string template for faster formatting."""
        # Check if template has variables
        if '{' not in template:
            return {'static': template, 'needs_formatting': False}
        return {'template': template, 'needs_formatting': True}
    
    def _precompile_single_template(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """Pre-compile a single message template."""
        compiled = {}
        for key, value in template.items():
            if isinstance(value, str) and '{' in value:
                compiled[key] = {'template': value, 'needs_formatting': True}
            elif isinstance(value, (dict, list)):
                compiled[key] = {'value': value, 'needs_formatting': True}
            else:
                compiled[key] = {'value': value, 'needs_formatting': False}
        return compiled
    
    def build_messages(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build messages using pre-compiled templates."""
        messages = []
        
        if self._precompiled_templates:
            # Use pre-compiled complex templates
            for compiled_template in self._precompiled_templates:
                message = {}
                for key, compiled_value in compiled_template.items():
                    if compiled_value['needs_formatting']:
                        if 'template' in compiled_value:
                            message[key] = compiled_value['template'].format_map(context)
                        else:
                            message[key] = OptimizedMessageFormatter.format_value(compiled_value['value'], context)
                    else:
                        message[key] = compiled_value['value']
                messages.append(message)
        else:
            # Use simple templates (faster path)
            if self._simple_system_template:
                if self._simple_system_template['needs_formatting']:
                    content = self._simple_system_template['template'].format_map(context)
                else:
                    content = self._simple_system_template['static']
                messages.append({"role": "system", "content": content})
            
            if self._simple_user_template:
                if self._simple_user_template['needs_formatting']:
                    content = self._simple_user_template['template'].format_map(context)
                else:
                    content = self._simple_user_template['static']
                messages.append({"role": "user", "content": content})
        
        return messages
    
    def insert_conversation_history(self, messages: List[Dict[str, Any]], history: List[Dict[str, Any]]) -> None:
        """Insert conversation history in-place for memory efficiency."""
        if not history:
            return
        
        # Find last user message index (optimized reverse search)
        last_user_idx = None
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get('role') == 'user':
                last_user_idx = i
                break
        
        if last_user_idx is None:
            # No user message, extend at the end
            messages.extend(history)
        else:
            # Insert history before last user message
            messages[last_user_idx:last_user_idx] = history

# endregion


class PromptNodeConfig(NodeConfig):
    """Enhanced configuration for flexible prompt building."""
    type: NodeType = "prompt"
    
    # Flexible message building (new approach)
    messages_template: Optional[List[Dict[str, Any]]] = None
    
    # Simple templates (backward compatibility)
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None


class PromptNode(BaseNode):
    """Ultra-optimized node for flexible prompt and conversation building."""
    
    __slots__ = ["system_prompt", "user_prompt", "messages_template", "_message_builder"]
    
    type: NodeType = "prompt"
    
    output_schema: ParamSet = (
        ParamSet.new()
            .var("messages: List", required=True)
            .build()
    )
    
    def __init__(
        self,
        # Simple mode (backward compatibility)
        user_prompt: Optional[str] = None,
        system_prompt: Optional[str] = None,
        # Complex mode
        messages_template: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ):
        """Initialize PromptNode with optimized pre-compilation."""
        
        super().__init__(**kwargs)
        
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.messages_template = messages_template
        
        # Pre-compile message builder for maximum speed
        self._message_builder = PrecompiledMessageBuilder(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            messages_template=messages_template
        )
        
        self._build_input_schema()
        
        # Assign core functionality
        self.core = ensure_async(self.format)
        
    def _build_input_schema(self) -> ParamSet:
        """Build input schema based on extracted variables."""
        _schema = ParamSet.new()
        
        # Add extracted variables
        for variable in self._extract_variables():
            try:
                _schema = _schema.var(f"{variable}: Any", required=True)
            except ValueError:
                LOGGER.warning(f"Get parsing error at: {variable}, ignore!!")
        
        # Add optional enhanced features
        _schema = _schema.var("conversation_history: List = []")
        
        _schema = _schema.var("tool_results: List = []")
        
        self.input_schema = _schema.build()
        
    def _extract_variables(self) -> Set[str]:
        """Extract template variables."""
        variables = set()
        
        # Extract from messages_template
        if self.messages_template:
            for msg in self.messages_template:
                variables.update(VariableExtractor.from_content(msg))
        
        # Extract from simple prompts
        if self.user_prompt:
            variables.update(VariableExtractor.from_string(self.user_prompt))
        
        if self.system_prompt:
            variables.update(VariableExtractor.from_string(self.system_prompt))
        
        return variables
    
    def format(self, **kwargs) -> Dict[str, Any]:
        """Ultra-optimized message building with minimal overhead."""
        # Build base messages using pre-compiled templates
        messages = self._message_builder.build_messages(kwargs)
        
        # Add conversation history (in-place for memory efficiency)
        history = kwargs.get('conversation_history')
        if history:  # Check existence before processing
            self._message_builder.insert_conversation_history(messages, history)
        
        # Add tool results (direct extend for speed)
        tool_results = kwargs.get('tool_results')
        if tool_results:  # Check existence before processing
            messages.extend(tool_results)
        
        return {"messages": messages}
    
    def specific_metadata(self) -> Dict[str, Any]:
        """Return prompt-specific metadata."""
        metadata = {}
        
        if self.messages_template:
            metadata["messages_template"] = self.messages_template
        else:
            if self.system_prompt:
                metadata["system_prompt"] = self.system_prompt
            if self.user_prompt:
                metadata["user_prompt"] = self.user_prompt
        
        return metadata


# ============= Performance Comparison Example =============

async def benchmark_example():
    """Benchmark the optimized version."""
    import time
    
    # Create a complex prompt node
    prompt_node = PromptNode(
        name="benchmark_prompt",
        messages_template=[
            {
                "role": "system",
                "content": "You are {assistant_name}. Current time: {current_time}. Session: {session_id}"
            },
            {
                "role": "user",
                "content": "Help me with {task}. Priority: {priority}. Context: {context}"
            }
        ],
        include_conversation_history=True,
        include_tool_results=True
    )
    
    # Prepare test data
    test_data = {
        "assistant_name": "Claude",
        "current_time": "2024-01-15 14:30:00",
        "session_id": "sess_12345",
        "task": "code review",
        "priority": "high",
        "context": "Python web application",
        "conversation_history": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ],
        "tool_results": [
            {"role": "tool", "content": "Analysis complete", "tool_call_id": "call_1"}
        ]
    }
    
    # Warm up
    for _ in range(10):
        await prompt_node.simulate(inputs=test_data)
    
    # Benchmark
    iterations = 100
    start_time = time.time()
    
    for _ in range(iterations):
        result = await prompt_node.simulate(inputs=test_data)
    
    end_time = time.time()
    
    print(f"Optimized version:")
    print(f"  {iterations} iterations in {end_time - start_time:.4f} seconds")
    print(f"  Average: {(end_time - start_time) / iterations * 1000:.4f} ms per call")
    print(f"  Throughput: {iterations / (end_time - start_time):.0f} calls/second")


# ============= Examples (same as before but work with optimized version) =============

async def example_1_simple():
    """Example 1: Simple backward-compatible usage"""
    print("=== Example 1: Simple Usage ===")
    
    prompt_node = PromptNode(
        name="simple_prompt",
        system_prompt="You are {name}, a helpful AI assistant.",
        user_prompt="Help me with {task}. I need {urgency} assistance."
    )
    
    result = await prompt_node.simulate(inputs={
        "name": "Claude",
        "task": "writing Python code",
        "urgency": "urgent"
    })
    
    return result


async def example_2_conversation():
    """Example 2: With conversation history"""
    print("\n=== Example 2: With Conversation History ===")
    
    prompt_node = PromptNode(
        name="conversation_prompt",
        system_prompt="You are {assistant_name}.",
        user_prompt="Continue our conversation: {new_message}",
    )
    
    result = await prompt_node.simulate(inputs={
        "assistant_name": "Claude",
        "new_message": "What was my previous question?",
        "conversation_history": [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language..."},
            {"role": "user", "content": "Can you give me an example?"},
            {"role": "assistant", "content": "Sure! Here's a simple example..."}
        ]
    })
    
    print("Result:", result)
    return result


async def example_3_complex_template():
    """Example 3: Complex template with images and tools"""
    print("\n=== Example 3: Complex Template ===")
    
    prompt_node = PromptNode(
        name="complex_prompt",
        messages_template=[
            {
                "role": "system",
                "content": "You are {assistant_name}. Current time: {current_time}. You have access to tools."
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this image and tell me about {analysis_focus}:"},
                    {
                        "type": "image_url", 
                        "image_url": {
                            "url": "{image_url}",
                            "detail": "high"
                        }
                    }
                ]
            }
        ]
    )
    
    result = await prompt_node.simulate(inputs={
        "assistant_name": "Vision Expert",
        "current_time": "2024-01-15 14:30",
        "analysis_focus": "architectural features",
        "image_url": "data:image/jpeg;base64,/9j/4AAQSkZJRgABA...",
        "tool_results": [
            {
                "role": "tool",
                "content": "Image analysis complete: Modern building with glass facade",
                "tool_call_id": "call_123"
            }
        ]
    })
    
    print("Result:", result)
    return result


async def example_4_full_conversation():
    """Example 4: Full conversation with everything"""
    print("\n=== Example 4: Full Conversation ===")
    
    prompt_node = PromptNode(
        name="full_conversation",
        messages_template=[
            {
                "role": "system",
                "content": "You are {assistant_name}, an expert in {domain}. Current session: {session_id}"
            },
            {
                "role": "assistant",
                "content": "I understand you want to {goal}. Let me help you with that."
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "{user_message}"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "{image_url}"}
                    }
                ]
            }
        ]
    )
    
    result = await prompt_node.simulate(inputs={
        "assistant_name": "Dr. Smith",
        "domain": "medical imaging",
        "session_id": "sess_2024_001",
        "goal": "analyze medical scans",
        "user_message": "Please review this X-ray and compare it with previous results:",
        "image_url": "data:image/jpeg;base64,medical_xray_data...",
        "conversation_history": [
            {"role": "user", "content": "I have some concerning symptoms"},
            {"role": "assistant", "content": "I understand your concerns. Let's review your case systematically."},
        ],
        "tool_results": [
            {
                "role": "tool",
                "content": "Previous scan from 2023-12-01 shows normal findings",
                "tool_call_id": "call_history_lookup"
            },
            {
                "role": "tool", 
                "content": "Current vital signs: BP 120/80, HR 72",
                "tool_call_id": "call_vitals"
            }
        ]
    })
    
    print("Result:", result)
    return result


async def main():
    """Run all examples from simple to complex"""
    await example_1_simple()
    await example_2_conversation() 
    await example_3_complex_template()
    await example_4_full_conversation()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())