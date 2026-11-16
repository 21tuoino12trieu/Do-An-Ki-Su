# API Reference

**Core APIs for workflow building and execution**

---

## WorkflowEngine

**Purpose:** Main entry point for building and running workflows.

### Constructor

```python
WorkflowEngine(
    name: str,                    # Workflow identifier
    description: str = "",        # Workflow description
    langfuse: str = "beegen",    # Observability client
    **kwargs
)
```

### Methods

#### `compile()`
Build workflow index and prepare for execution.

```python
with WorkflowEngine(name="my_workflow") as wf:
    # Define nodes and connections
    START >> node1 >> node2 >> END

wf.compile()  # Must call before run()
```

#### `run()`
Execute workflow with inputs.

```python
result = await wf.run(
    inputs: Dict[str, Any],           # Input variables
    user_id: str = None,              # User identifier
    session_id: str = None,           # Session identifier
    request_id: str = None            # Request identifier
)
# Returns: Dict[str, Any] - workflow outputs
```

### Example

```python
with WorkflowEngine(name="chatbot") as wf:
    retriever = RetrieverNode(inputs=INPUT)
    llm = BasicChainNode(
        resource_key="gpt-4o",
        user_prompt="Answer: {query} using {docs}",
        inputs={"query": INPUT, "docs": retriever}
    )
    START >> retriever >> llm >> END

wf.compile()

result = await wf.run(
    inputs={"query": "What is RAG?", "collection": "docs"},
    user_id="user123",
    request_id="req456"
)
```

---

## WorkflowState

**Purpose:** Manages workflow execution state and variable storage.

### Properties

```python
state.request_id    # Request identifier
state.user_id       # User identifier
state.session_id    # Session identifier
state.name          # Workflow name
```

### Methods

#### Get/Set Values

```python
# Get variable value
value = state[node_name, var_name, context_id]

# Set variable value
state[node_name, var_name, context_id] = value

# Get by index (fast)
value = state.get_by_index(index, context_id)
state.set_by_index(index, value, context_id)
```

#### Inject Inputs

```python
state.inject_inputs(
    node: str,                     # Target node name
    inputs: Dict[str, Any],        # Input variables
    context_id: str = None         # Context (for loops)
)
```

### Example

```python
indexer = WorkflowIndexer("workflow").add_node(node).build()

state = WorkflowState(
    indexer=indexer,
    inputs={"query": "Hello"},
    user_id="user123"
)

# Access values
query = state["workflow", "query", None]

# For loops - different contexts
state.inject_inputs("node", {"item": data[0]}, context_id="loop[0]")
state.inject_inputs("node", {"item": data[1]}, context_id="loop[1]")
```

---

## Node Connection Operators

### `>>` (Right Shift)

Connect nodes in workflow.

```python
# Single connection
node1 >> node2

# Multiple targets
node1 >> [node2, node3]

# Chain
START >> node1 >> node2 >> node3 >> END
```

### `<<` (Left Shift)

Reverse connection (rarely used).

```python
# Equivalent to: node1 >> node2
node2 << node1

# Multiple sources
[node1, node2] << node3
```

---

## Special Markers

### START / END / CONTINUE

Control flow boundaries.

```python
from beeflow.nodes import START, END, CONTINUE

# Mark workflow boundaries
START >> first_node
last_node >> END

# In loops - mark continuation point
with WhileLoopNode() as loop:
    check >> END                    # Stop loop
    process >> update >> CONTINUE   # Continue loop
```

### INPUT / OUTPUT

Reference workflow inputs/outputs.

```python
from beeflow.nodes import INPUT, OUTPUT

# Map to workflow inputs
node = Node(inputs={"query": INPUT["query"]})

# Map to workflow outputs
node = Node(outputs={"result": OUTPUT["final_result"]})
```

---

## Variable References

### Node Reference

Reference entire node output.

```python
llm = LLMNode(inputs={"messages": prompt_node})
# Equivalent to: {"messages": prompt_node["messages"]}
```

### Variable Reference

Reference specific variable.

```python
parser = ParserNode(inputs={"text": llm["content"]})
# Only gets "content" field from llm
```

### Multi-Variable

Map multiple inputs/outputs.

```python
node = Node(
    inputs={
        ("query", "docs"): INPUT  # Both from workflow input
    },
    outputs={
        ("result", "score"): OUTPUT  # Both to workflow output
    }
)
```

---

## Streaming

### STREAM_SERVICE

Real-time token streaming via Redis.

```python
from beeflow.utils.streaming import STREAM_SERVICE

# Producer (automatic for stream=True nodes)
llm = LLMNode(stream=True, ...)

# Consumer
async for channel in STREAM_SERVICE.get_channels(request_id):
    print(f"Channel: {channel}")
    async for chunk in STREAM_SERVICE.get(request_id, channel):
        print(chunk.choices[0].delta.content, end="")
```

### Enable Streaming

```python
# On node
node = LLMNode(
    stream=True,                    # Enable streaming
    status_message="Processing..."  # Status message
)

# Multiple streaming nodes
with ForLoopNode() as loop:
    llm1 = LLMNode(stream=True)
    llm2 = LLMNode(stream=True)
    # Each gets own channel: "workflow.loop.llm1[loop[0]]"
```

---

## Observability

### Trace Export

Automatic export to Langfuse.

```python
# Configured in WorkflowEngine
wf = WorkflowEngine(
    name="my_workflow",
    langfuse="beegen"  # Langfuse client key
)

# After execution, traces auto-flushed
await wf.run(inputs={...})
# → Trace hierarchy created in Langfuse
```

### Trace Data

Access execution traces.

```python
# Get node trace
trace = node.trace_data(state, context_id)

# Returns:
{
    "name": "node_name",
    "start_time": datetime,
    "end_time": datetime,
    "input": {...},
    "output": {...},
    "level": "DEFAULT" | "ERROR",
    "metadata": {...}
}
```

---

## Configuration

### Resource Keys

Reference registered resources (models, databases).

```python
# LLM models
llm = LLMNode(resource_key="gpt-4o")
llm = LLMNode(resource_key="Qwen3-30B")

# Embeddings
embed = EmbeddingNode(resource_key="bge-m3")

# Databases
mongo = MongoNode(resource_key="aicenter-chatbot")
milvus = MilvusNode(resource_key="chatbot-libra")
s3 = S3Node(resource_key="aicenter-cua")
```

**Note:** Contact Mr. Cương for resource registration.

### Operations

Specify database operations.

```python
from beegen.configs import MongoOperation, MilvusOperation, S3Operation

mongo = MongoNode(
    operation=MongoOperation.FIND,
    # or: INSERT, UPDATE, DELETE, AGGREGATE
)

milvus = MilvusNode(
    operation=MilvusOperation.SEARCH,
    # or: INSERT, DELETE
)

s3 = S3Node(
    operation=S3Operation.READ,
    # or: WRITE, LIST_PATHS, DELETE
)
```

---

## Error Handling

### Try-Catch Pattern

```python
def safe_process(data):
    try:
        result = complex_operation(data)
        return {"result": result, "error": None}
    except Exception as e:
        return {"result": None, "error": str(e)}

processor = CodeNode(code_fn=safe_process)

branch = BranchNode(
    cases={"error is None": "success_handler"},
    default="error_handler",
    inputs={"error": processor["error"]}
)
```

### State Error Access

```python
# Errors auto-stored in state
error = state[node_name, "error", context_id]

if error:
    print(f"Node failed: {error}")
```

---

## Best Practices

### 1. Always Compile

```python
# ✅ Good
wf.compile()
result = await wf.run(inputs={...})

# ❌ Bad - will fail
result = await wf.run(inputs={...})  # No compile()
```

### 2. Use Descriptive Names

```python
# ✅ Good
retriever = RetrieverNode(name="doc_retriever")
classifier = BasicChainNode(name="intent_classifier")

# ❌ Bad
node1 = RetrieverNode(name="n1")
node2 = BasicChainNode(name="n2")
```

### 3. Type Hints in Schemas

```python
# ✅ Good
extract_schema=["sentiment: str", "score: float", "entities: List"]

# ❌ Bad (but works)
extract_schema=["sentiment", "score", "entities"]
```

### 4. Context IDs for Loops

```python
# ✅ Good - unique context per iteration
with ForLoopNode() as loop:
    # Each item gets "for[0]", "for[1]", etc.
    
with WhileLoopNode() as loop:
    # Each iteration gets "while-0", "while-1", etc.

# This enables state isolation
```

---

## 📚 Related

- [Node Catalog](node-catalog/_index.md) - All available nodes
- [Concepts: State Management](../concepts/state-management.md)
- [Concepts: Execution Model](../concepts/execution-model.md)
- [Tutorial: Basic LLM Chain](../tutorials/01-basic-llm-chain.md)

---

[← Back to Reference](../reference/)