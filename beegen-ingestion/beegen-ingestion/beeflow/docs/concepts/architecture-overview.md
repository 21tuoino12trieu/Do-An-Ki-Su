# Architecture Overview

**The big picture of how Beeflow works**

⏱️ **Time:** ~15 minutes  
🎯 **Goal:** Understand Beeflow's design philosophy and high-level architecture

---

## 🎯 What is Beeflow?

Beeflow is a **declarative workflow orchestration framework** for building production-grade AI applications. It lets you compose complex LLM workflows using a simple, intuitive API while handling performance, observability, and state management automatically.

### The Core Idea

```python
# Instead of this (imperative):
prompt = format_prompt(user_input)
llm_response = await call_llm(prompt)
parsed = parse_response(llm_response)
return parsed

# You write this (declarative):
with WorkflowEngine(name="my-workflow") as workflow:
    prompt_node = PromptNode(user_prompt="{user_input}")
    llm_node = LLMNode(inputs={"messages": prompt_node})
    parser_node = ParserNode(inputs={"text": llm_node["content"]})
    
    START >> prompt_node >> llm_node >> parser_node >> END

# Beeflow handles: execution, state, parallelism, observability
```

---

## 🏗️ Design Philosophy

### 1. **Declarative First**
Define *what* you want, not *how* to do it. Beeflow figures out execution order, parallelism, and dependencies.

```python
# You declare structure
node_a >> [node_b, node_c] >> node_d

# Beeflow infers:
# - b and c can run in parallel
# - d waits for both b and c
# - Optimal execution order
```

### 2. **Zero-Copy State**
Variables are shared via index references, not copied. This makes workflows memory-efficient even with large data.

```python
# node_b references node_a's output (same memory location)
node_b.inputs = {"data": node_a["result"]}

# No data copying! Just index sharing
# node_a.output_indexes["result"] = 42
# node_b.input_indexes["data"] = 42  # Same index!
```

### 3. **Async Native**
Built from the ground up for concurrent execution. Nodes run in parallel when possible.

```python
# These run concurrently:
branch >> [retriever_a, retriever_b, retriever_c] >> combine
```

### 4. **Observable by Default**
Every execution is automatically traced to Langfuse. No manual instrumentation needed.

```python
# Just run your workflow
result = await workflow.run(
    inputs={...},
    user_id="user_123",
    request_id="req_456"
)

# Traces automatically appear in Langfuse! ✨
```

### 5. **Composable**
Workflows are nestable. Build reusable components and compose them.

```python
# A sub-workflow
rag_pipeline = RetrieverNode(...)

# Use it in a larger workflow
with WorkflowEngine(name="chatbot") as workflow:
    query_rewriter = BasicChainNode(...)
    rag = rag_pipeline  # Reuse!
    final_answer = BasicChainNode(...)
    
    START >> query_rewriter >> rag >> final_answer >> END
```

---

## 🏛️ High-Level Architecture

### The Big Picture

```
┌─────────────────────────────────────────────────────────────┐
│                        USER CODE                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  with WorkflowEngine(name="my-app") as workflow:     │   │
│  │      node_a = LLMNode(...)                           │   │
│  │      node_b = ParserNode(...)                        │   │
│  │      START >> node_a >> node_b >> END                │   │
│  │  workflow.compile()                                  │   │
│  │  result = await workflow.run(inputs={...})           │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                   WORKFLOW ENGINE                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  • Build graph structure (nodes + edges)             │   │
│  │  • Compile: Create WorkflowIndexer                   │   │
│  │  • Run: Create WorkflowState and execute             │   │
│  │  • Flush: Send traces to Langfuse                    │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
            ↓                    ↓                    ↓
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  GRAPH LAYER    │  │  STATE LAYER    │  │  EXECUTION      │
├─────────────────┤  ├─────────────────┤  ├─────────────────┤
│ • GraphNode     │  │ • WorkflowState │  │ • Async runner  │
│ • Node registry │  │ • VariableCell  │  │ • Dependency    │
│ • Edge tracking │  │ • Indexer       │  │   resolution    │
│ • Topology      │  │ • Zero-copy     │  │ • Parallel exec │
└─────────────────┘  └─────────────────┘  └─────────────────┘
            ↓                    ↓                    ↓
┌─────────────────────────────────────────────────────────────┐
│                     NODE LAYER                              │
│  ┌─────────┐  ┌─────────┐  ┌───────────┐  ┌─────────┐       │
│  │ LLMNode │  │CodeNode │  │BranchNode │  │ ...     │       │
│  │         │  │         │  │           │  │         │       │
│  │ .run()  │  │ .run()  │  │ .run()    │  │ .run()  │       │
│  └─────────┘  └─────────┘  └───────────┘  └─────────┘       │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                  INFRASTRUCTURE                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ RESOURCE_HUB │  │ Redis        │  │ Langfuse     │       │
│  │ • LLMs       │  │ • Streaming  │  │ • Traces     │       │
│  │ • Embeddings │  │ • Channels   │  │ • Metrics    │       │
│  │ • Databases  │  │              │  │              │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 Core Components

### 1. WorkflowEngine

**The orchestrator that ties everything together.**

```python
class WorkflowEngine:
    def __init__(self, name: str):
        self._graph = GraphNode(name=name)  # Internal graph
        self.indexer = None                 # Created on compile()
    
    def compile(self):
        # Build the workflow indexer
        self.indexer = WorkflowIndexer(name).add_node(self._graph).build()
    
    async def run(self, inputs: dict, user_id: str, request_id: str):
        # Create state and execute
        state = WorkflowState(indexer=self.indexer, inputs=inputs, ...)
        result = await self._graph.run(state)
        
        # Fire-and-forget trace flush
        asyncio.create_task(self.flush(state))
        return result
```

**Responsibilities:**
- Graph construction (during `__enter__` context)
- Compilation (create indexer)
- Execution (create state, run graph)
- Observability (flush traces to Langfuse)

---

### 2. GraphNode

**A container for nodes and their connections (DAG).**

```python
class GraphNode(BaseNode):
    def __init__(self, name: str):
        self._nodes: Dict[str, BaseNode] = {}      # Registry
        self._edges: List[EdgeConfig] = []         # Connections
        self.prevs: Dict[str, List[str]] = {}      # Predecessors
        self.nexts: Dict[str, List[str]] = {}      # Successors
    
    def add_node(self, node: BaseNode):
        self._nodes[node.name] = node
    
    def add_edge(self, source: str, target: str):
        self.nexts[source].append(target)
        self.prevs[target].append(source)
    
    async def run(self, state: WorkflowState, context_id: str):
        # Execute nodes in dependency order
        active_tasks = {}
        ready_count = {node: len(self.prevs[node]) for node in self._nodes}
        
        # Start with entry nodes (no predecessors)
        for entry in self.entries:
            active_tasks[entry] = asyncio.create_task(
                self._nodes[entry].run(state, context_id)
            )
        
        # Process nodes as they complete
        while active_tasks:
            done, _ = await asyncio.wait(
                active_tasks.values(),
                return_when=asyncio.FIRST_COMPLETED
            )
            
            for task in done:
                node_name = task.get_name()
                active_tasks.pop(node_name)
                
                # Activate successors
                for next_node in self.nexts[node_name]:
                    ready_count[next_node] -= 1
                    if ready_count[next_node] == 0:
                        active_tasks[next_node] = asyncio.create_task(
                            self._nodes[next_node].run(state, context_id)
                        )
```

**Key Features:**
- Manages node registry and topology
- Handles parallel execution
- Resolves dependencies dynamically
- Supports nested graphs (composition)

---

### 3. WorkflowIndexer

**Maps variables to array indices for zero-copy sharing.**

```python
class WorkflowIndexer:
    def __init__(self, name: str):
        self._indices: Dict[Tuple[str, str], int] = {}  # (node, var) -> index
        self._values: List[Any] = []                     # Storage array
        self._nodes: Dict[str, BaseNode] = {}            # Node registry
    
    def _allocate(self, node: str, var: str) -> int:
        """Allocate an index for (node, var)"""
        if (node, var) not in self._indices:
            index = len(self._values)
            self._indices[node, var] = index
            self._values.append(None)
            return index
        return self._indices[node, var]
    
    def _link(self, node: str, var: str, ref_node: str, ref_var: str):
        """Share the same index between two variables (zero-copy)"""
        self._indices[node, var] = self._allocate(ref_node, ref_var)
    
    def resolve(self, node: str, var: str, value: Any):
        """Resolve variable dependency"""
        if hasattr(value, "is_base_node"):
            # Link to entire node output
            self._link(node, var, value.full_name, var)
        elif isinstance(value, dict) and value:
            # Link to specific variable: {node_ref: "var_name"}
            ref_node, ref_var = next(iter(value.items()))
            self._link(node, var, ref_node.full_name, ref_var)
        else:
            # Literal value
            idx = self._allocate(node, var)
            self._values[idx] = value
```

**Zero-Copy Example:**
```python
# User code
node_b.inputs = {"data": node_a["result"]}

# What indexer does:
# node_a.output_indexes["result"] = 42
# node_b.input_indexes["data"] = 42  # Same index!

# Both access _values[42] - no copying!
```

---

### 4. WorkflowState

**Runtime state with context isolation for loops.**

```python
class WorkflowState:
    def __init__(self, indexer: WorkflowIndexer, inputs: dict):
        self._indexer = indexer
        # Create VariableCell for each slot
        self._values = [VariableCell(v) for v in indexer._values]
    
    def __setitem__(self, key: Tuple[str, str, str], value: Any):
        node, var, context_id = key
        index = self._indexer[node, var]
        self._values[index][context_id] = value
    
    def __getitem__(self, key: Tuple[str, str, str]) -> Any:
        node, var, context_id = key
        index = self._indexer[node, var]
        return self._values[index][context_id]
    
    def get_by_index(self, index: int, context_id: str) -> Any:
        """O(1) direct access"""
        return self._values[index][context_id]
    
    def set_by_index(self, index: int, value: Any, context_id: str):
        """O(1) direct write"""
        self._values[index][context_id] = value
```

**Key Features:**
- Each slot is a `VariableCell` (holds multiple context values)
- Context isolation for loops (`for[0]`, `for[1]`, etc.)
- O(1) access via pre-computed indices
- Execution tracking for observability

---

### 5. VariableCell

**Stores multiple values for different contexts (loop iterations).**

```python
class VariableCell:
    def __init__(self, default_value: Any = None):
        self.contexts: Dict[str, Any] = {}    # context_id -> value
        self.versions: List[str] = []         # Order of contexts
        self.DEFAULT_VALUE = default_value
    
    def __setitem__(self, context_id: str, value: Any):
        if context_id not in self.versions:
            self.versions.append(context_id)
        self.contexts[context_id] = value
    
    def __getitem__(self, context_id: str) -> Any:
        return self.contexts.get(context_id, self.DEFAULT_VALUE)
    
    def get(self) -> Any:
        """Get most recent value"""
        if self.versions:
            return self.contexts[self.versions[-1]]
        return self.DEFAULT_VALUE
```

**Example (ForLoopNode):**
```python
# Loop over batch
for i, item in enumerate(batch):
    context_id = f"for[{i}]"
    state["processor", "input", context_id] = item
    state["processor", "output", context_id] = process(item)

# Each iteration isolated:
# VariableCell.contexts = {
#     "for[0]": result_0,
#     "for[1]": result_1,
#     "for[2]": result_2
# }
```

---

### 6. BaseNode

**Abstract base for all nodes.**

```python
class BaseNode:
    def __init__(self, name: str, inputs: dict, outputs: dict):
        self.name = name
        self.inputs = inputs           # Variable mappings
        self.outputs = outputs
        self.input_schema = ParamSet   # Type definitions
        self.output_schema = ParamSet
        self.input_indexes: Dict[str, int] = {}   # Distributed by indexer
        self.output_indexes: Dict[str, int] = {}
        self.core: Callable = None     # Actual logic
    
    async def run(self, state: WorkflowState, context_id: str):
        # 1. Get inputs from state (O(1) via indices)
        _inputs = self.get_inputs(state, context_id)
        
        # 2. Execute core logic
        _outputs = await self.core(**_inputs)
        
        # 3. Store outputs to state (O(1) via indices)
        self.store_result(state, _outputs, context_id)
        
        return _outputs
    
    def get_inputs(self, state: WorkflowState, context_id: str) -> dict:
        return {
            k: state.get_by_index(idx, context_id)
            for k, idx in self.input_indexes.items()
        }
    
    def store_result(self, state: WorkflowState, result: dict, context_id: str):
        for key, value in result.items():
            state.set_by_index(self.output_indexes[key], value, context_id)
```

**Node Types:**
- **AI Nodes:** LLMNode, EmbeddingNode, RerankNode
- **Data Nodes:** MilvusNode, MongoNode, S3Node
- **Transform Nodes:** CodeNode, ParserNode, PromptNode
- **Flow Control:** BranchNode, ForLoopNode, WhileLoopNode
- **Templates:** BasicChainNode, RetrieverNode, ReactAgentNode

---

## 🔄 Execution Flow

### From Code to Execution

```
1. DECLARATION (User Code)
┌─────────────────────────────────────────┐
│ with WorkflowEngine(name="app"):        │
│     node_a = LLMNode(...)               │
│     node_b = ParserNode(...)            │
│     START >> node_a >> node_b >> END    │
└─────────────────────────────────────────┘
                 ↓
2. COMPILATION (workflow.compile())
┌─────────────────────────────────────────┐
│ • Create WorkflowIndexer                │
│ • Register all nodes                    │
│ • Resolve dependencies                  │
│ • Allocate indices                      │
│ • Distribute to nodes                   │
└─────────────────────────────────────────┘
                 ↓
3. RUNTIME (workflow.run(inputs={...}))
┌─────────────────────────────────────────┐
│ • Create WorkflowState                  │
│ • Inject input values                   │
│ • Execute graph asynchronously          │
│ • Track execution order                 │
└─────────────────────────────────────────┘
                 ↓
4. OBSERVABILITY (workflow.flush())
┌─────────────────────────────────────────┐
│ • Build Langfuse trace hierarchy        │
│ • Add node spans/generations            │
│ • Track token usage                     │
│ • Record errors                         │
└─────────────────────────────────────────┘
```

### Example Execution

```python
# 1. DECLARE
with WorkflowEngine(name="summarizer") as workflow:
    prompt = PromptNode(user_prompt="Summarize: {text}", inputs=INPUT)
    llm = LLMNode(resource_key="gpt-4o", inputs={"messages": prompt})
    parser = ParserNode(inputs={"text": llm["content"]}, outputs=OUTPUT)
    START >> prompt >> llm >> parser >> END

# 2. COMPILE
workflow.compile()
# Creates indexer:
# (summarizer, text) -> index 0
# (prompt, messages) -> index 1
# (llm, content) -> index 2
# (parser, result) -> index 3

# 3. RUN
result = await workflow.run(inputs={"text": "Long article..."})
# Creates state with VariableCells
# Executes: prompt -> llm -> parser
# Returns: {"result": "Summary..."}

# 4. FLUSH (automatic, background)
# Sends trace to Langfuse:
# Trace(id=req_123)
#   ├─ Span(prompt)
#   ├─ Generation(llm) [tokens: 234, cost: $0.0047]
#   └─ Span(parser)
```

---

## 🎨 Design Patterns

### Pattern 1: Sequential Processing

```python
START >> node_a >> node_b >> node_c >> END
```
**Use for:** Linear pipelines (prompt → LLM → parse)

---

### Pattern 2: Parallel Fan-Out/Fan-In

```python
START >> splitter >> [worker_a, worker_b, worker_c] >> combiner >> END
```
**Use for:** Batch processing, multi-retrieval

---

### Pattern 3: Conditional Branching

```python
START >> classifier >> branch >> [path_a, path_b, path_c] >> merge >> END
```
**Use for:** Different logic paths based on input

---

### Pattern 4: Iterative Loops

```python
with ForLoopNode() as loop:
    START >> processor >> END

START >> loop >> END
```
**Use for:** Batch processing with context isolation

---

### Pattern 5: Nested Sub-Workflows

```python
with GraphNode(name="rag_pipeline") as rag:
    START >> retriever >> reranker >> END

with WorkflowEngine(name="chatbot") as workflow:
    START >> query_rewriter >> rag >> answer_generator >> END
```
**Use for:** Reusable components, modularity

---

## 🚀 Performance Characteristics

### Time Complexity

| Operation | Complexity | Notes |
|-----------|-----------|-------|
| Variable access | O(1) | Direct index lookup |
| Variable write | O(1) | Direct index write |
| Node execution | O(nodes) | Async, parallel when possible |
| Dependency resolution | O(edges) | One-time during compilation |

### Memory Usage

```python
# Traditional approach (copying)
prompt_output = format_prompt(input)        # Copy 1
llm_input = prompt_output                   # Copy 2
llm_output = call_llm(llm_input)           # Copy 3
parser_input = llm_output                   # Copy 4

# Beeflow (zero-copy)
# All nodes reference same memory location via index
# Only one copy of data exists!
```

### Concurrency

```python
# Sequential (slow)
result_a = await node_a.run()
result_b = await node_b.run()
result_c = await node_c.run()

# Beeflow automatic parallelism (fast)
START >> splitter >> [node_a, node_b, node_c] >> combiner
# All three run concurrently! ⚡
```

---

## 🔍 When to Use Beeflow

### ✅ Great For:

- **Complex LLM Workflows** - Multi-step pipelines with LLMs
- **RAG Applications** - Retrieval + generation patterns
- **Agent Systems** - ReAct, tool use, iterative reasoning
- **Batch Processing** - Process multiple items efficiently
- **Production AI Apps** - Need observability and reliability

### ⚠️ Consider Alternatives For:

- **Simple Scripts** - Single LLM call (use SDK directly)
- **Non-AI Tasks** - Pure data processing (use Airflow, Prefect)
- **Real-Time Constraints** - Sub-10ms latency requirements
- **Stateless Functions** - No workflow state needed

---

## 🆚 Comparison with Other Frameworks

### vs LangChain

| Feature | Beeflow | LangChain |
|---------|---------|-----------|
| **Paradigm** | DAG-based | Chain-based |
| **State** | Zero-copy indices | Object copying |
| **Parallelism** | Automatic | Manual |
| **Observability** | Built-in Langfuse | LangSmith (paid) |
| **Learning Curve** | Moderate | Steeper |

### vs LlamaIndex

| Feature | Beeflow | LlamaIndex |
|---------|---------|------------|
| **Focus** | General workflows | RAG-focused |
| **Flexibility** | High | RAG-optimized |
| **Custom Logic** | Full control | Via callbacks |
| **State Management** | Explicit | Implicit |

### vs Airflow

| Feature | Beeflow | Airflow |
|---------|---------|---------|
| **Domain** | AI/LLM workflows | General ETL |
| **Execution** | In-process async | Distributed tasks |
| **Real-time** | Yes (streaming) | No |
| **Setup** | Simple | Complex |

---

## 📚 Next Steps

Now that you understand the architecture:

1. **Dive Deeper:**
   - [Nodes and Graphs](nodes-and-graphs.md) - Node types and connections
   - [State Management](state-management.md) - Zero-copy internals
   - [Execution Model](execution-model.md) - Async execution details

2. **Build Something:**
   - [Tutorial 1: Basic Chain](../tutorials/01-basic-llm-chain.md)
   - [Tutorial 2: RAG Pipeline](../tutorials/02-rag-pipeline.md)
   - [Tutorial 3: ReAct Agent](../tutorials/03-react-agent.md)

3. **Explore Examples:**
   - [Working Examples](../../examples/) - Production patterns

---

## 💡 Key Takeaways

### Core Concepts
- **Declarative** - Focus on *what*, not *how*
- **Zero-Copy** - Variables shared via indices
- **Async Native** - Parallel execution by default
- **Observable** - Automatic tracing to Langfuse
- **Composable** - Nest workflows for modularity

### Architecture Layers
1. **WorkflowEngine** - Orchestration
2. **GraphNode** - DAG management
3. **WorkflowIndexer** - Variable indexing
4. **WorkflowState** - Runtime state
5. **BaseNode** - Execution primitives

### When to Use
- ✅ Multi-step LLM workflows
- ✅ Production AI applications
- ✅ Need observability and reliability
- ⚠️ Simple scripts → use SDK directly
- ⚠️ Non-AI workflows → consider Airflow

---

**Ready to understand the building blocks? Continue to [Nodes and Graphs](nodes-and-graphs.md) →**