from typing import Callable, Dict, Any, List, Optional
from beeflow.nodes.base_node import BaseNode
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.configs import NodeType
from beeflow.states.workflow_state import WorkflowState
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.utils.context import _current_graph
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.tools.schema.param import Param
from beegen.utils.common import fake_chunk_from
from beegen.loggings import LOGGER
import asyncio
import traceback
from datetime import datetime



class WhileLoopNode(BaseNode):
    """A node that iterates over a condition"""
    
    type: NodeType = "while"
    
    def __init__(self, **kwargs):
        """Initialize a GraphNode with a name"""
        super().__init__(**kwargs)
        self._graph: GraphNode = GraphNode(name=BaseNode.INNER_PROCESS)
        self._graph.father = self
        self._token = None
    
    def __enter__(self):
        """Enter context manager mode - set ForLoopNode as current context"""
        self._token = _current_graph.set(self._graph)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager and delegate to inner graph"""
        _current_graph.reset(self._token)
        # Build the inner graph
                        
    def build(self):
        self._graph.build()

        self.input_schema = self._graph.input_schema
        self.output_schema = self._graph.output_schema
        
        for key in self.inputs:
            if key not in self.input_schema:
                self.input_schema.params[key] = Param(type="Any", required=True)

        self._post_init()
        
    def add_node(self, node: BaseNode) -> BaseNode:
        """Delegate node addition to inner graph"""
        return self._graph.add_node(node)
    
    def add_edge(self, source: str, target: str, type=None):
        """Delegate edge addition to inner graph"""
        return self._graph.add_edge(source, target, type)
    
    async def run(
        self,
        state: WorkflowState,
        context_id: Optional[str] = None
    ) -> Dict[str, Any]:
        
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
            
            _continue = True
            step_count = 0
            
            step_inputs = _inputs
            
            while _continue:
                step_name = f"{context_id}_while[{step_count}]" if context_id else f"while[{step_count}]"
            
                state.inject_inputs(
                    node=self._graph.full_name,
                    inputs=step_inputs,
                    context_id=step_name
                )
                
                _outputs = await self._graph.run(state, context_id=step_name)
                
                step_inputs = self._graph.get_inputs(state, context_id=step_name)
                step_count += 1
                
                _continue = _outputs.get("continue_loop", False)
            
        except Exception as e:
            error_msg = traceback.format_exc()
            LOGGER.error(f"Error in node {self.name}: {str(e)}")
            LOGGER.error(error_msg)
            # Propagate the error but ensure metrics are recorded
            state[self.full_name, "error", context_id] = error_msg
            
            if self.stream:
                asyncio.create_task(STREAM_SERVICE.push(
                    request_id=request_id,
                    channel_name=self.identity(context_id),
                    data=fake_chunk_from(
                        content='Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại sau.',
                        model="error"
                    )
                ))
        finally:
            # Always record timing metrics            
            await asyncio.sleep(0.000001)
            end_time = datetime.now()
            state.set_by_index(self.metrics['start_time'], start_time, context_id=context_id)
            state.set_by_index(self.metrics['end_time'], end_time, context_id=context_id)
            self.store_result(state, _outputs, context_id=context_id)
            if self.stream:
                asyncio.create_task(STREAM_SERVICE.end(request_id, self.identity(context_id)))
            return _outputs
        
        
async def main():
    from beeflow.nodes import (
        CodeNode, START, END, INPUT, OUTPUT, CONTINUE, PromptNode,
        LLMNode, ParserNode, BranchNode, ToolExecutorNode, DataNode
    )
    
    def multiply(a: int, b: int) -> int:
        """Multiply two integers and returns the result integer
        Args:
            a(int): first argument of the multiply
            b(int): second argument of the multiply
        
        Returns:
            mul(int): multiply of a and b
        """
        return {"mul": a * b}


    def add(a: int, b: int) -> int:
        """Add two integers and returns the result integer
        Args:
            a(int): first argument of the sum
            b(int): second argument of the sum
        
        Returns:
            sum(int): sum of the a and b
        """
        return {"sum": a + b}
    
    # Tools
    n_add = CodeNode(name="add", code_fn=add)
    n_mul = CodeNode(name="mul", code_fn=multiply)
    
    LLAMAINDEX_REACT_PROMPT = """You are a ReAct (Reasoning and Acting) agent designed to help with tasks by breaking them down into sequential steps. You must think step-by-step and use tools one at a time.

## Available Tools
You have access to the following tools:
{tool_desc}

## Context
{context_prompt}

## Critical Rules - MUST FOLLOW
1. Execute ONLY ONE tool per step - NEVER use parallel execution
2. Always start with "Thought:" to reason about what you need to do
3. Use exactly ONE tool with "Action:" and "Params:"
4. Wait for "Observation:" before proceeding to next step
5. Continue until you can answer without more tools
6. Answer in Vietnamese (or the user's language)

## Required Format
You MUST follow this exact format:

```
Thought: [Your reasoning about what to do next - be specific]
Action: [EXACTLY ONE tool name from: {tool_names}]
Params: {{"parameter": "value"}}
```

After each action, you will receive:
```
Observation: [tool response]
```

When you have enough information, conclude with:
```
Thought: [Explain why you can now answer]
Answer: [Your final answer in Vietnamese]
```

If you cannot complete the task:
```
Thought: [Explain why you cannot proceed]
Answer: [Explanation in Vietnamese about limitations]
```

## Example Walkthrough
Human: Tính (8 + 1) x (12 + 10)?

Thought: "Tôi cần tính biểu thức này từng bước. Đầu tiên, tôi sẽ tính 8 + 1."
Action: add
Params: {{"a": 8, "b": 1}}

Observation: 9

Thought: "Bây giờ tôi cần tính 12 + 10."
Action: add
Params: {{"a": 12, "b": 10}}

Observation: 22

Thought: "Cuối cùng, tôi cần nhân 9 x 22."
Action: mul
Params: {{"a": 9, "b": 22}}

Observation: 198

Thought: "Tôi đã có đủ thông tin để trả lời câu hỏi."
Answer: Kết quả của (8 + 1) x (12 + 10) là 198.

## Important Reminders
- DO NOT use ':' in Thought
- DO NOT use multi_tool_use.parallel or any parallel execution
- DO NOT try to use multiple tools in one step
- DO NOT skip the Thought step
- DO NOT surround your entire response with markdown code blocks
- Always wait for Observation before next Action
- Be patient and methodical - this is the strength of ReAct

## Current Conversation
Below is the current conversation:"""

    TOOL_FORMAT_PROMPT = """
> Tool name: {tool_name}
Tool Description: {tool_description}
Tool Args: {tool_argument}
"""
    
    def create_react_prompt(
        tools: List[BaseNode]
    ) -> str:
        def desc(tool: BaseNode) -> str:
            tool_desc = TOOL_FORMAT_PROMPT.format(
                tool_name = tool.name,
                tool_description = tool.description,
                tool_argument = tool.get_openai_function_schema()["parameters"]
            )
            
            return tool_desc
        
        tools_desc = [desc(tool) for tool in tools]
        tool_names = [tool.name for tool in tools]
        
        return LLAMAINDEX_REACT_PROMPT.format(
            tool_desc = '\n'.join(tools_desc),
            tool_names = ', '.join(tool_names),
            context_prompt = "You are a helpful math assistant."
        )
        
    def format_react_messages(query: str) -> Dict[str, Any]:
        """
        Returns:
            messages (List): messages after formatting with system prompt
        """
        formatted_messages = [{"role": "user", "content": query}]
        formatted_messages.insert(0, {"role": "system", 
                                      "content": create_react_prompt([n_add, n_mul])})
        
        return {
            "messages": formatted_messages
        }
        
    def update(
        messages: List[Dict],
        llm_reasoning: str,
        tool_result: Any,
        tool_error: str,
        tool_success: bool,
        iteration_count: int 
    ) -> Dict[str, Any]:
        # Add the assistant's action
        messages.append({
            "role": "assistant", 
            "content": llm_reasoning
        })
        
        # Add the observation
        if tool_success:
            observation = f"Observation: {tool_result}"
        else:
            observation = f"Observation: Error - {tool_error}"
        
        messages.append({
            "role": "user",
            "content": observation
        })
        
        return {
            "out_messages": messages,
            "out_iteration_count": iteration_count + 1
        }


    with WhileLoopNode(
        name="while",
        description="đây là luồng test while node",
        inputs={"messages": INPUT, "iteration_count": 0}
    ) as while_node:
        reason = LLMNode(
            name="reason",
            resource_key="gpt-4o",
            inputs={"messages": INPUT},
            stream=True
        )
        parser = ParserNode(
            name="parser",
            format="yaml",
            inputs={"text": reason["content"]},
            extract_schema=["Thought", "Action", "Params", "Answer"],
            outputs={"Answer": OUTPUT}
        )
        verify_loop = BranchNode(
            name="check_for_answer",
            cases={
                "Answer is None and iteration_count < 5": "tool_manager",
            },
            default=END,
            inputs={
                "iteration_count": INPUT,
                "Answer": parser
            }
        )
        tool_manager = ToolExecutorNode(
            name="tool_manager",
            tools=[n_add, n_mul],
            inputs={
                "tool_name": parser["Action"],
                "tool_params": parser["Params"]
            }
        )
        update_while = CodeNode(
            name="update",
            code_fn=update,
            inputs={
                "messages": INPUT,
                "iteration_count": INPUT,
                "llm_reasoning": reason["content"],
                "tool_result": tool_manager["result"],
                "tool_error": tool_manager["error"],
                "tool_success": tool_manager["success"]
            },
            return_keys=["out_messages", "out_iteration_count"],
            outputs={
                "out_messages": INPUT["messages"],
                "out_iteration_count": INPUT["iteration_count"]
            }
        )
        
        START >> reason >> parser >> verify_loop >> [tool_manager, 
                                                     END] 
        tool_manager >> update_while >> CONTINUE
    
    # print(while_node.input_schema)
    # print(while_node.output_schema)
    
    while_node.build()
    
    
    messages = format_react_messages("hãy tính (8 + 1) * (12 + 5 * 10)")
    
    indexer = WorkflowIndexer("workflow01").add_node(while_node).build()
        
    state = WorkflowState(
        indexer=indexer,
        inputs = {
            "messages": messages["messages"]
        }
    )
    
    result = await while_node.run(state=state)
    
    print(while_node.get_outputs(state, None))
    

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())