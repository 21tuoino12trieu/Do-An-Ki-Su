# Tutorial 3: ReAct Agent

**Build an autonomous agent with iterative reasoning and tool calling**

⏱️ **Time:** ~60 minutes  
⭐ **Level:** Advanced  
🔧 **Nodes:** `ReactAgentNode`, `CodeNode`, `WhileLoopNode`, `BranchNode`, `ToolExecutorNode`

---

## 🎯 What You'll Build

An intelligent ReAct (Reasoning and Acting) agent that can:
- Break down complex problems into steps
- Reason about what to do next
- Call appropriate tools to gather information
- Iterate until it finds the answer
- Handle errors and max iteration limits

**Input:**
```python
"Calculate (15 + 7) * (20 - 5) / 3"
```

**Process (Iterative ReAct Loop):**
```
Iteration 1:
  Thought: "I need to calculate 15 + 7 first"
  Action: add
  Params: {"a": 15, "b": 7}
  Observation: 22

Iteration 2:
  Thought: "Now I need to calculate 20 - 5"
  Action: add
  Params: {"a": 20, "b": -5}
  Observation: 15

Iteration 3:
  Thought: "Now multiply 22 * 15"
  Action: multiply
  Params: {"a": 22, "b": 15}
  Observation: 330

Iteration 4:
  Thought: "Finally divide 330 / 3"
  Action: divide
  Params: {"a": 330, "b": 3}
  Observation: 110
  
  Thought: "I have the final answer"
  Answer: "The result is 110"
```

**Output:**
```python
{
    "Answer": "The result is 110"
}
```

---

## 📚 Prerequisites

### ✅ Completed
- [Tutorial 1: Basic LLM Chain](01-basic-llm-chain.md)
- [Tutorial 2: RAG Pipeline](02-rag-pipeline.md)
- [Quickstart Guide](../quickstart.md)

### ✅ Knowledge
- Understanding of LLM reasoning
- Familiarity with function/tool calling
- Loop control flow concepts

### ✅ System Requirements
- Python 3.9+
- LLM API key (preferably GPT-4 for best reasoning)
- Beeflow installed: `pip install beeflow`

> **📞 Setup Note:** For `RESOURCE_HUB` configuration, contact **Mr. Cương**.

---

## 🏗️ Architecture

### High-Level ReAct Pattern

The ReAct agent follows this iterative cycle:

```
┌─────────────────────────────────────────────────────────┐
│                   User Query                            │
│         "Calculate (15 + 7) * (20 - 5)"                 │
└────────────────────┬────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────┐
│  ReactAgentNode: "math_agent"                           │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Internal WhileLoopNode (max 5 iterations)        │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │  1. LLMNode: Reason                         │  │  │
│  │  │     - Think about next step                 │  │  │
│  │  │     - Decide which tool to use              │  │  │
│  │  │     Output: Thought, Action, Params         │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  │                    ↓                              │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │  2. ParserNode: Extract                     │  │  │
│  │  │     Parse: Thought, Action, Params, Answer  │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  │                    ↓                              │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │  3. BranchNode: Check Answer                │  │  │
│  │  │     If Answer found → EXIT                  │  │  │
│  │  │     If iteration < 5 → CONTINUE             │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  │          ↓ (continue)          ↓ (exit)           │  │
│  │  ┌─────────────────┐     ┌───────────────┐        │  │
│  │  │ 4. Execute Tool │     │  Final Answer │        │  │
│  │  │ ToolExecutorNode│     └───────────────┘        │  │
│  │  └─────────────────┘                              │  │
│  │          ↓                                        │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │  5. Update Messages                         │  │  │
│  │  │     Add "Observation: <result>"             │  │  │
│  │  │     Loop back to step 1                     │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ↓
┌─────────────────────────────────────────────────────────┐
│              Final Answer Output                        │
└─────────────────────────────────────────────────────────┘
```

### Key Components

1. **WhileLoopNode** - Handles iteration until answer found or max iterations
2. **LLMNode** - Generates reasoning (Thought, Action, Params)
3. **ParserNode** - Extracts structured fields from LLM output
4. **BranchNode** - Decides whether to continue or exit
5. **ToolExecutorNode** - Dynamically calls the specified tool
6. **CodeNode** - Updates conversation with observations

---

## 💻 Step-by-Step Implementation

### Step 1: Define Your Tools

Tools are simply functions wrapped in nodes. Let's create math tools:

```python
from beeflow.nodes import CodeNode

def add(a: int, b: int) -> int:
    """Add two integers and return the result.
    
    Args:
        a (int): First number to add
        b (int): Second number to add
    
    Returns:
        sum (int): Sum of a and b
    """
    return {"sum": a + b}


def multiply(a: int, b: int) -> int:
    """Multiply two integers and return the result.
    
    Args:
        a (int): First number to multiply
        b (int): Second number to multiply
    
    Returns:
        product (int): Product of a and b
    """
    return {"product": a * b}


def divide(a: float, b: float) -> float:
    """Divide two numbers and return the result.
    
    Args:
        a (float): Numerator
        b (float): Denominator
    
    Returns:
        quotient (float): Result of a divided by b
    """
    if b == 0:
        return {"quotient": None, "error": "Cannot divide by zero"}
    return {"quotient": a / b}


# Wrap functions in CodeNodes
calculator_tool = CodeNode(name="calculator", code_fn=add)
multiply_tool = CodeNode(name="multiply", code_fn=multiply)
divide_tool = CodeNode(name="divide", code_fn=divide)
```

**Important Notes:**
- ✅ **Docstrings are crucial** - The agent reads them to understand what tools do
- ✅ **Type hints required** - Help the agent understand parameters
- ✅ **Clear descriptions** - Explain what the tool does and returns
- ✅ **Return dict** - Always return a dictionary with named outputs

---

### Step 2: Create the ReAct Agent

Now let's build the agent with our tools:

```python
import asyncio
from beeflow import WorkflowEngine
from beeflow.nodes import ReactAgentNode, CodeNode, START, END, INPUT, OUTPUT

# Define tools (from Step 1)
add_tool = CodeNode(
    name="add",
    code_fn=lambda a, b: {"sum": a + b},
    description="Add two numbers together"
)

multiply_tool = CodeNode(
    name="multiply", 
    code_fn=lambda a, b: {"product": a * b},
    description="Multiply two numbers"
)

divide_tool = CodeNode(
    name="divide",
    code_fn=lambda a, b: {"quotient": a / b if b != 0 else None},
    description="Divide first number by second number"
)

async def main():
    with WorkflowEngine(name="math-agent-workflow") as workflow:
        
        # Create ReAct Agent
        agent = ReactAgentNode(
            name="math_agent",
            resource_key="gpt-4o",           # Use GPT-4 for best reasoning
            tools=[add_tool, multiply_tool, divide_tool],  # Available tools
            max_iterations=5,                # Maximum reasoning steps
            context_prompt="You are a helpful math assistant.",  # Agent personality
            inputs={"query": INPUT},
            outputs={"Answer": OUTPUT}
        )
        
        # Simple flow - agent handles all the complexity
        START >> agent >> END
    
    workflow.compile()
    
    # Test the agent
    result = await workflow.run(
        inputs={"query": "Calculate (15 + 7) * (20 - 5) / 3"}
    )
    
    print(f"Final Answer: {result['Answer']}")

if __name__ == "__main__":
    asyncio.run(main())
```

**That's it!** The `ReactAgentNode` handles all the complex internal logic:
- ✅ Formats the ReAct prompt automatically
- ✅ Manages the reasoning loop
- ✅ Calls tools dynamically
- ✅ Updates conversation history
- ✅ Checks for completion

---

### Step 3: Understanding What Happens Internally

When you run the agent, here's what happens inside:

#### Iteration 1: First Calculation

**LLM Reasoning:**
```yaml
Thought: "I need to solve (15 + 7) * (20 - 5) / 3 step by step. First, calculate 15 + 7."
Action: add
Params:
  a: 15
  b: 7
```

**Tool Execution:**
```python
add_tool.run(a=15, b=7)
# Returns: {"sum": 22}
```

**Observation Added:**
```
Observation: 22
```

#### Iteration 2: Second Calculation

**LLM Reasoning:**
```yaml
Thought: "Now I need to calculate 20 - 5. I'll use add with negative number."
Action: add
Params:
  a: 20
  b: -5
```

**Tool Execution:**
```python
add_tool.run(a=20, b=-5)
# Returns: {"sum": 15}
```

**Observation Added:**
```
Observation: 15
```

#### Iteration 3: Multiplication

**LLM Reasoning:**
```yaml
Thought: "Now multiply 22 * 15"
Action: multiply
Params:
  a: 22
  b: 15
```

**Tool Execution:**
```python
multiply_tool.run(a=22, b=15)
# Returns: {"product": 330}
```

**Observation Added:**
```
Observation: 330
```

#### Iteration 4: Division & Answer

**LLM Reasoning:**
```yaml
Thought: "Finally, divide 330 by 3"
Action: divide
Params:
  a: 330
  b: 3
```

**Tool Execution:**
```python
divide_tool.run(a=330, b=3)
# Returns: {"quotient": 110.0}
```

**Observation Added:**
```
Observation: 110.0
```

#### Iteration 5: Final Answer

**LLM Reasoning:**
```yaml
Thought: "I have completed all calculations. The final answer is 110."
Answer: "The result of (15 + 7) * (20 - 5) / 3 is 110."
```

**Exit Condition Met** ✅ (Answer field is present)

---

## 🔍 Internal Architecture of ReactAgentNode

The `ReactAgentNode` is actually a **GraphNode** that wraps a complex internal workflow:

```python
# Simplified internal structure of ReactAgentNode
class ReactAgentNode(GraphNode):
    def _build_graph(self):
        with self:
            # Format ReAct prompt with tools
            react_prompt = CodeNode(
                name="react_prompt",
                code_fn=format_react_messages,
                inputs={"query": INPUT, "system_prompt": REACT_PROMPT}
            )
            
            # The reasoning loop
            with WhileLoopNode(
                name="while",
                inputs={"messages": react_prompt, "iteration_count": 0},
                outputs={"Answer": OUTPUT}
            ) as loop:
                
                # 1. Generate reasoning
                reason = LLMNode(
                    name="reason",
                    resource_key=self.resource_key,
                    inputs={"messages": INPUT},
                    stream=True
                )
                
                # 2. Parse structured output
                parser = ParserNode(
                    name="parser",
                    format="yaml",
                    extract_schema=["Thought", "Action", "Params", "Answer"],
                    inputs={"text": reason["content"]},
                    outputs={"Answer": OUTPUT}
                )
                
                # 3. Check if we should continue or exit
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
                
                # 4. Execute the chosen tool
                tool_manager = ToolExecutorNode(
                    name="tool_manager",
                    tools=self.tools,
                    inputs={
                        "tool_name": parser["Action"],
                        "tool_params": parser["Params"]
                    }
                )
                
                # 5. Update messages with observation
                update_while = CodeNode(
                    name="update",
                    code_fn=update_messages,
                    inputs={
                        "messages": INPUT,
                        "iteration_count": INPUT,
                        "llm_reasoning": reason["content"],
                        "tool_result": tool_manager["result"],
                        "tool_error": tool_manager["error"],
                        "tool_success": tool_manager["success"]
                    },
                    outputs={
                        "out_messages": INPUT["messages"],
                        "out_iteration_count": INPUT["iteration_count"]
                    }
                )
                
                # Define loop flow
                START >> reason >> parser >> verify_loop >> [tool_manager, END]
                tool_manager >> update_while >> CONTINUE
            
            START >> react_prompt >> loop >> END
```

**Key Insights:**
- Uses `WhileLoopNode` for iteration control
- `BranchNode` checks if "Answer" is found
- `ToolExecutorNode` dynamically calls tools by name
- Messages accumulate: Query → Thought → Action → Observation → Thought → ...

---

## 🧪 Testing Your Agent

### Test Case 1: Simple Math

```python
result = await workflow.run(
    inputs={"query": "What is 25 + 37?"}
)

# Expected:
# Iteration 1:
#   Thought: "I need to add 25 and 37"
#   Action: add
#   Params: {a: 25, b: 37}
#   Observation: 62
#   Answer: "25 + 37 equals 62"
```

### Test Case 2: Multi-Step Problem

```python
result = await workflow.run(
    inputs={"query": "If I have 3 boxes with 4 items each, how many items total?"}
)

# Expected:
# Iteration 1:
#   Thought: "I need to multiply 3 boxes by 4 items"
#   Action: multiply
#   Params: {a: 3, b: 4}
#   Observation: 12
#   Answer: "You have 12 items in total"
```

### Test Case 3: Complex Chain

```python
result = await workflow.run(
    inputs={"query": "Calculate ((10 + 5) * 2) / 3"}
)

# Expected: Multiple iterations
# 1. add(10, 5) → 15
# 2. multiply(15, 2) → 30
# 3. divide(30, 3) → 10
# Answer: "The result is 10"
```

### Test Case 4: Max Iterations

```python
result = await workflow.run(
    inputs={"query": "Calculate factorial of 10"}
)

# Expected: Hits max iterations (5)
# Agent will admit it can't complete the task:
# "I've reached the maximum iterations. The task requires more steps than allowed."
```

---

## 🎨 Advanced: Custom Tools

### Example 1: Web Search Tool

```python
def search_web(query: str) -> dict:
    """Search the web for information.
    
    Args:
        query (str): Search query
    
    Returns:
        results (str): Search results summary
    """
    # Implement actual web search
    results = perform_search(query)
    return {"results": results}

search_tool = CodeNode(name="search", code_fn=search_web)

# Create agent with search capability
agent = ReactAgentNode(
    name="research_agent",
    resource_key="gpt-4o",
    tools=[search_tool],
    context_prompt="You are a research assistant with web search access."
)
```

### Example 2: Database Query Tool

```python
def query_database(sql: str) -> dict:
    """Execute SQL query on database.
    
    Args:
        sql (str): SQL query to execute
    
    Returns:
        data (list): Query results
    """
    results = execute_sql(sql)
    return {"data": results}

db_tool = CodeNode(name="database", code_fn=query_database)
```

### Example 3: API Call Tool

```python
def call_api(endpoint: str, params: dict) -> dict:
    """Make API call to external service.
    
    Args:
        endpoint (str): API endpoint URL
        params (dict): Request parameters
    
    Returns:
        response (dict): API response data
    """
    response = requests.get(endpoint, params=params)
    return {"response": response.json()}

api_tool = CodeNode(name="api", code_fn=call_api)
```

---

## 🚨 Troubleshooting

### Issue 1: Agent doesn't use tools

**Symptom:**
Agent tries to solve everything without calling tools.

**Possible Causes:**
1. Tool descriptions are unclear
2. LLM model is not capable enough (use GPT-4)
3. Context prompt doesn't emphasize tool usage

**Solution:**
```python
# Improve tool descriptions
def add(a: int, b: int) -> int:
    """Add two integers. USE THIS for any addition operation.
    
    Args:
        a (int): First number
        b (int): Second number
    
    Returns:
        sum (int): a + b
    """
    return {"sum": a + b}

# Emphasize in context
agent = ReactAgentNode(
    context_prompt="You MUST use the provided tools. Do NOT try to calculate in your head.",
    ...
)
```

---

### Issue 2: Agent hits max iterations

**Symptom:**
```
Answer: "I've reached maximum iterations..."
```

**Possible Causes:**
1. Problem requires many steps
2. Agent is inefficient in tool usage
3. Agent gets stuck in a loop

**Solution:**
```python
# Increase max_iterations
agent = ReactAgentNode(
    max_iterations=10,  # Allow more steps
    ...
)

# Or break down the problem
result1 = await agent.run(inputs={"query": "First, calculate A + B"})
result2 = await agent.run(inputs={"query": f"Now multiply {result1['Answer']} by C"})
```

---

### Issue 3: Parser fails to extract fields

**Symptom:**
```
parser["Action"] = None
```

**Possible Causes:**
1. LLM output format is inconsistent
2. LLM doesn't follow YAML format

**Solution:**
The `ReactAgentNode` already has a robust YAML parser. If this happens:
- Use GPT-4 or similar capable model
- Check if your tools have clear docstrings
- The prompt template emphasizes format compliance

---

### Issue 4: Tool execution errors

**Symptom:**
```
Observation: Error - Cannot divide by zero
```

**Solution:**
Implement error handling in tools:
```python
def divide(a: float, b: float) -> dict:
    """Divide a by b."""
    if b == 0:
        return {
            "quotient": None,
            "error": "Cannot divide by zero. Try a different approach."
        }
    return {"quotient": a / b}
```

The agent will see the error and adapt its strategy!

---

## 🚀 Enhancements & Next Steps

### Enhancement 1: Memory/Context

Add conversation history:

```python
agent = ReactAgentNode(
    name="agent_with_memory",
    inputs={
        "query": INPUT["query"],
        "history": INPUT["conversation_history"]  # Previous exchanges
    }
)
```

### Enhancement 2: Conditional Tool Access

Control which tools are available:

```python
with WorkflowEngine(name="adaptive-agent") as workflow:
    # Choose tools based on query type
    tool_selector = BranchNode(
        name="select_tools",
        cases={
            "'math' in query": "math_agent",
            "'search' in query": "search_agent"
        }
    )
    
    math_agent = ReactAgentNode(
        name="math_agent",
        tools=[add_tool, multiply_tool, divide_tool]
    )
    
    search_agent = ReactAgentNode(
        name="search_agent",
        tools=[search_tool, summarize_tool]
    )
```

### Enhancement 3: Multi-Agent Collaboration

Chain multiple agents:

```python
# Agent 1: Research
researcher = ReactAgentNode(
    name="researcher",
    tools=[search_tool, scrape_tool],
    outputs={"Answer": "research_findings"}
)

# Agent 2: Analyze
analyzer = ReactAgentNode(
    name="analyzer",
    tools=[calculate_tool, visualize_tool],
    inputs={"query": researcher["Answer"]}
)
```

### Enhancement 4: Streaming Observations

Watch the agent think in real-time:

```python
agent = ReactAgentNode(
    name="agent",
    stream=True,  # Enable streaming
    ...
)

# Stream the reasoning process
from beeflow.utils.streaming import STREAM_SERVICE

async for channel in STREAM_SERVICE.get_channels(request_id):
    async for chunk in STREAM_SERVICE.get(request_id, channel):
        print(chunk.choices[0].delta.content, end="", flush=True)
```

---

## 💡 Key Takeaways

Congratulations! You've built an autonomous ReAct agent. Here's what you learned:

### ✅ Core Concepts
1. **ReAct Pattern** - Reasoning + Acting iteratively
2. **ReactAgentNode** - High-level template for agents
3. **Tool Definition** - Functions with clear docstrings
4. **Iteration Control** - Max iterations and exit conditions
5. **Dynamic Tool Calling** - Agent chooses tools on the fly

### ✅ Agent Components
1. **WhileLoopNode** - Iteration control
2. **LLMNode** - Generates reasoning
3. **ParserNode** - Extracts structured output (YAML)
4. **BranchNode** - Checks completion
5. **ToolExecutorNode** - Executes tools dynamically
6. **CodeNode** - Updates conversation

### ✅ Best Practices
- ✅ Use GPT-4 or similar for best reasoning
- ✅ Write clear, detailed tool docstrings
- ✅ Include type hints in tool functions
- ✅ Handle tool errors gracefully
- ✅ Set appropriate max_iterations
- ✅ Test with progressively harder problems

### ✅ When to Use ReAct Agents
- ✅ Multi-step problem solving
- ✅ Tasks requiring tool/function calls
- ✅ Uncertain number of steps needed
- ✅ Problems requiring exploration
- ✅ Need for transparent reasoning

### ✅ When NOT to Use ReAct Agents
- ❌ Simple single-step tasks (use BasicChainNode)
- ❌ Fixed workflow (use regular GraphNode)
- ❌ Real-time latency critical (agents are iterative)

---

## 📚 What's Next?

Now that you can build autonomous agents, you can:

1. **Tutorial 4: Batch Processing** - Process multiple items in parallel
   - Learn ForLoopNode for batch operations
   - Handle parallel tool executions
   - Aggregate agent results

2. **Tutorial 5: Production Deployment** - Deploy with observability
   - Monitor agent iterations with Langfuse
   - Track tool usage and costs
   - Debug agent reasoning

3. **Explore Advanced Patterns** - Check the [Guides](../guides/)
   - Multi-agent systems
   - Agent planning strategies
   - Error recovery patterns
   - Performance optimization

---

## 📝 Complete Code

Here's the full working ReAct agent:

```python
import asyncio
from beeflow import WorkflowEngine
from beeflow.nodes import ReactAgentNode, CodeNode, START, END, INPUT, OUTPUT

# Define tools
add_tool = CodeNode(
    name="add",
    code_fn=lambda a, b: {"sum": a + b},
    description="Add two numbers together"
)

multiply_tool = CodeNode(
    name="multiply",
    code_fn=lambda a, b: {"product": a * b},
    description="Multiply two numbers"
)

divide_tool = CodeNode(
    name="divide",
    code_fn=lambda a, b: {"quotient": a / b if b != 0 else None},
    description="Divide first number by second"
)

async def main():
    # Create workflow
    with WorkflowEngine(name="math-agent") as workflow:
        agent = ReactAgentNode(
            name="math_agent",
            resource_key="gpt-4o",
            tools=[add_tool, multiply_tool, divide_tool],
            max_iterations=5,
            context_prompt="You are a helpful math assistant.",
            inputs={"query": INPUT},
            outputs={"Answer": OUTPUT}
        )
        
        START >> agent >> END
    
    workflow.compile()
    
    # Test
    result = await workflow.run(
        inputs={"query": "Calculate (15 + 7) * (20 - 5) / 3"}
    )
    
    print(f"Answer: {result['Answer']}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

**🎉 Excellent work completing Tutorial 3! Ready for batch processing?**

**→ [Next: Tutorial 4 - Batch Processing](04-batch-processing.md)**