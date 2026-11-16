from typing import Dict, List, Any, Optional
from beeflow.configs.node_config import NodeType
from beeflow.nodes import GraphNode, BaseNode
from beegen.tools.schema.param import ParamSet

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
Thought: "[Your reasoning about what to do next - be specific]"
Action: [EXACTLY ONE tool name from: {tool_names}]
Params: {{"parameter": "value"}}
```

After each action, you will receive:
```
Observation: [tool response]
```

When you have enough information, conclude with:
```
Thought: "[Explain why you can now answer]"
Answer: "[Your final answer in Vietnamese]"
```

If you cannot complete the task:
```
Thought: "[Explain why you cannot proceed]"
Answer: "[Explanation in Vietnamese about limitations]"
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
Answer: "Kết quả của (8 + 1) x (12 + 10) là 198."

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


def format_react_messages(query: str, system_prompt: str) -> Dict[str, Any]:
    """
    Returns:
        messages (List): messages after formatting with system prompt
    """
    formatted_messages = [{"role": "user", "content": query}]
    formatted_messages.insert(0, {"role": "system", "content": system_prompt})
    
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


class ReactAgentNode(GraphNode):
    """
    ReAct Agent node that implements the Reasoning and Acting pattern.
    
    This node creates an internal graph that handles the iterative ReAct cycle:
    1. Thought - LLM reasons about what to do next
    2. Action - LLM decides on an action and inputs
    3. Observation - Execute the action and observe results
    4. Repeat until final answer or max iterations
    
    The agent can use any available tools/functions and maintains conversation
    history throughout the reasoning process.
    """
    
    type: NodeType = "react-agent"
    
    def __init__(
        self,
        resource_key: str,
        tools: List[BaseNode],
        max_iterations: int = 5,
        context_prompt: str = "",
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        
        self.resource_key = resource_key
        self.tools = self._clone_tools_with_namespace(tools)
        self.max_iterations = max_iterations
        self.context_prompt = context_prompt
        self._build_graph()

    def _clone_tools_with_namespace(self, tools: List[BaseNode]) -> List[BaseNode]:
        """
        Clone tools add agent name prefix to avoid namespace collision.
        """
        cloned_tools = []
        for tool in tools:
            tool_class = tool.__class__

            clone_kwargs = {
                'name': f"{self.name}_{tool.name}",
                'description': tool.description,
            }

            if hasattr(tool, 'code_fn'):
                clone_kwargs['code_fn'] = tool.code_fn
                if hasattr(tool, 'return_keys'):
                    clone_kwargs['return_keys'] = tool.return_keys

            if hasattr(tool, 'resource_key'):
                clone_kwargs['resource_key'] = tool.resource_key

            if hasattr(tool, 'operation'):
                clone_kwargs['operation'] = tool.operation

            cloned = tool_class(**clone_kwargs)
            cloned_tools.append(cloned)

            from beegen.loggings import LOGGER
            LOGGER.debug(f"Cloned tool '{tool.name}' -> '{cloned.name}' for agent '{self.name}'")

        return cloned_tools
        
    def _create_react_prompt(self) -> str:
        
        def desc(tool: BaseNode) -> str:
            tool_desc = TOOL_FORMAT_PROMPT.format(
                tool_name = tool.name,
                tool_description = tool.description,
                tool_argument = tool.get_openai_function_schema()["parameters"]
            )
            
            return tool_desc
        
        tools_desc = [desc(tool) for tool in self.tools]
        tool_names = [tool.name for tool in self.tools]
        
        return LLAMAINDEX_REACT_PROMPT.format(
            tool_desc = '\n'.join(tools_desc),
            tool_names = ', '.join(tool_names),
            context_prompt = self.context_prompt
        )
        
    def _build_graph(self):
        """Build the internal ReAct agent graph."""
        from beeflow.nodes import (
            CodeNode, START, END, INPUT, OUTPUT, CONTINUE, PromptNode,
            LLMNode, ParserNode, BranchNode, ToolExecutorNode, DataNode,
            WhileLoopNode
        )
        
        with self:
            react_prompt = CodeNode(
                name="react_prompt",
                code_fn=format_react_messages,
                inputs={
                    "query": INPUT, 
                    "system_prompt": self._create_react_prompt()
                }
            )
            with WhileLoopNode(
                name="while",
                description="đây là luồng test while node",
                inputs={"messages": react_prompt, "iteration_count": 0},
                outputs={"Answer": OUTPUT}
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
                        "Answer is None and iteration_count < max_iterations": "tool_manager",
                    },
                    default=END,
                    inputs={
                        "iteration_count": INPUT,
                        "max_iterations": self.max_iterations,
                        "Answer": parser
                    }
                )
                tool_manager = ToolExecutorNode(
                    name="tool_manager",
                    tools=self.tools,
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
            
            START >> react_prompt >> while_node >> END
        
        self.build()
        

async def main():
    
    from beeflow.nodes import CodeNode, INPUT, SQLNode
    from beegen.configs.storage.sql_config import SQLOperation
    from beeflow.states import WorkflowIndexer, WorkflowState
    
    def multiply(a: int, b: int) -> int:
        """Multiply two integers and returns the result integer
        Args:
            a(int): first argument of the multiply
            b(int): second argument of the multiply
        
        Returns:
            mul(int): multiply of a and b
        """
        return {"mul": int(a) * int(b)}


    def add(a: int, b: int) -> int:
        """Add two integers and returns the result integer
        Args:
            a(int): first argument of the sum
            b(int): second argument of the sum
        
        Returns:
            sum(int): sum of the a and b
        """
        return {"sum": int(a) + int(b)}
    
    # Tools
    n_add = CodeNode(code_fn=add)
    n_mul = CodeNode(code_fn=multiply)
    sql_executor = SQLNode(
        name="sql_executor",
        description="Đây là tool giúp executor câu lệnh SQL và trả về kết quả",
        resource_key="anapp",                 # matches a SQL adapter key in ResourceHub
        operation=SQLOperation.QUERY,
    )
    
    agent = ReactAgentNode(
        name="react_agent",
        resource_key="qwen-instruction-chat",
        tools=[n_add, n_mul, sql_executor],
        max_iterations=5,
        context_prompt="Bạn là một agent trả lời câu hỏi sử dụng tool sẵn có",
        inputs=INPUT
    )
    
    indexer = WorkflowIndexer("workflow01").add_node(agent).build()
        
    state = WorkflowState(
        indexer=indexer,
        inputs = {
            "query": "Kết quả SELECT * FROM agent_ai.behavior_in_app"
        }
    )
        
    result = await agent.run(state=state)
    
    print(result)
    
    
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())