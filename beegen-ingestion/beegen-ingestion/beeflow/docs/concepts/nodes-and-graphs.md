# Nodes and Graphs

**The building blocks of Beeflow workflows**

⏱️ **Time:** ~15 minutes  
🎯 **Goal:** Understand nodes, connections, and composition

---

## 🧩 What is a Node?

A **node** is a single unit of work in your workflow. Each node:
- Has a specific job (call LLM, parse text, fetch data)
- Declares inputs and outputs
- Runs asynchronously
- Tracks execution metrics

```python
# Simple node
llm = LLMNode(
    name="chatbot",
    resource_key="gpt-4o",
    inputs={"messages": INPUT},
    outputs={"content": OUTPUT}
)
```

---

## 📚 Node Types

### 1. AI Nodes (Intelligence)

**LLMNode** - Call language models
```python
llm = LLMNode(
    name="generator",
    resource_key="gpt-4o",           # Model from RESOURCE_HUB
    inputs={"messages": prompt_node},
    stream=True                       # Enable streaming
)
```

**EmbeddingNode** - Generate embeddings
```python
embed = EmbeddingNode(
    name="embedder",
    resource_key="bge-m3",
    inputs={"texts": INPUT["query"]}
)
```

**RerankNode** - Rerank search results
```python
rerank = RerankNode(
    name="reranker",
    resource_key="bge-m3",
    inputs={
        "query": INPUT["query"],
        "documents": retriever["docs"]
    }
)
```

---

### 2. Data Nodes (Storage)

**MongoNode** - MongoDB operations
```python
mongo = MongoNode(
    name="fetch_docs",
    resource_key="aicenter-chatbot",
    operation=MongoOperation.FIND,
    inputs={
        "query": query_builder["query"],
        "collection_name": "documents"
    }
)
```

**MilvusNode** - Vector search
```python
milvus = MilvusNode(
    name="vector_search",
    resource_key="chatbot-libra",
    operation=MilvusOperation.SEARCH,
    inputs={
        "query_vectors": embed["embeddings"],
        "collection_name": INPUT["collection"]
    }
)
```

**S3Node** - S3 file operations
```python
s3 = S3Node(
    name="read_file",
    resource_key="aicenter-cua",
    operation=S3Operation.READ,
    inputs={"key": INPUT["file_path"]}
)
```

---

### 3. Transform Nodes (Processing)

**PromptNode** - Format prompts
```python
prompt = PromptNode(
    name="formatter",
    system_prompt="You are a helpful assistant.",
    user_prompt="Answer this: {query}",
    inputs={"query": INPUT}
)
```

**ParserNode** - Extract structured data
```python
parser = ParserNode(
    name="extractor",
    format="xml",                             # or "json", "yaml"
    extract_schema=["answer: str", "confidence: float"],
    inputs={"text": llm["content"]}
)
```

**CodeNode** - Custom Python logic
```python
def process(data: dict) -> dict:
    return {"result": data["value"] * 2}

code = CodeNode(
    name="processor",
    code_fn=process,
    inputs={"data": INPUT}
)
```

**LambdaNode** - Simple transformations
```python
transform = LambdaNode(
    name="transformer",
    code_fn=lambda x: {"doubled": x * 2},
    return_keys=["doubled: int"],
    inputs={"x": INPUT}
)
```

---

### 4. Flow Control Nodes

**BranchNode** - Conditional routing
```python
branch = BranchNode(
    name="router",
    cases={
        "category == 'urgent'": urgent_handler,
        "category == 'normal'": normal_handler
    },
    default=fallback_handler,
    inputs={"category": classifier}
)
```

**ForLoopNode** - Batch processing
```python
with ForLoopNode(
    name="batch_processor",
    inputs={"batch_data": INPUT}
) as loop:
    processor = LLMNode(...)
    START >> processor >> END
```

**WhileLoopNode** - Conditional iteration
```python
with WhileLoopNode(
    name="agent_loop",
    inputs={"messages": INPUT}
) as loop:
    reason = LLMNode(...)
    check = BranchNode(
        cases={"Answer is None": "tool_executor"},
        default=END
    )
    tool_executor = ToolExecutorNode(...)
    
    START >> reason >> check >> [tool_executor, END]
    tool_executor >> CONTINUE
```

---

### 5. Template Nodes (Pre-built)

**BasicChainNode** - Prompt + LLM + Parser
```python
chain = BasicChainNode(
    name="qa_chain",
    resource_key="gpt-4o",
    user_prompt="Answer: {query}",
    extract_schema=["answer: str"],  # Optional parsing
    inputs={"query": INPUT}
)
```

**RetrieverNode** - Complete RAG pipeline
```python
retriever = RetrieverNode(
    name="rag",
    embedding="bge-m3",
    milvus="chatbot-libra",
    mongo="aicenter-chatbot",
    inputs={
        "query": INPUT,
        "collection": INPUT,
        "top_k": 5
    }
)
```

**ReactAgentNode** - ReAct reasoning pattern
```python
agent = ReactAgentNode(
    name="agent",
    resource_key="gpt-4o",
    tools=[calculator, search, weather],
    inputs={"query": INPUT}
)
```

---

## 🔗 Connecting Nodes

### Basic Connection (>>)

```python
# Sequential flow
START >> node_a >> node_b >> node_c >> END
```

### Parallel Execution

```python
# Fan-out: node_a triggers both b and c (run in parallel)
START >> node_a >> [node_b, node_c] >> node_d >> END
```

### Variable References

```python
# Method 1: Entire node output
node_b.inputs = {"data": node_a}

# Method 2: Specific variable
node_b.inputs = {"data": node_a["result"]}

# Method 3: Multiple sources
node_c.inputs = {
    "data_a": node_a["result"],
    "data_b": node_b["output"]
}
```

### Workflow (or father node) input/OUTPUT

```python
# Connect to Workflow (or father node) input
prompt.inputs = {"query": INPUT}

# Connect to Workflow (or father node) output
parser.outputs = {"answer": OUTPUT}

# Both
chain.inputs = {"query": INPUT}
chain.outputs = {"answer": OUTPUT}
```

---

## 🏗️ GraphNode (Composition)

A **GraphNode** is a container for sub-workflows. Use it for reusable components.

### Basic Graph

```python
from beeflow.nodes import GraphNode

with GraphNode(name="preprocessor") as graph:
    cleaner = CodeNode(...)
    validator = CodeNode(...)
    
    START >> cleaner >> validator >> END

graph.build()  # Finalize the graph

# Use in workflow
START >> graph >> next_node >> END
```

### Nested Graphs

```python
# Outer workflow
with WorkflowEngine(name="chatbot") as workflow:
    query_rewriter = BasicChainNode(...)
    
    # Inner graph
    with GraphNode(name="rag_pipeline") as rag:
        retriever = MilvusNode(...)
        reranker = RerankNode(...)
        START >> retriever >> reranker >> END

    answer_generator = BasicChainNode(
        inputs={"docs": rag["docs"]}  # Reference nested output!
    )
    
    START >> query_rewriter >> rag >> answer_generator >> END
```

---

## 📋 Input/Output Schemas

### Defining Schemas

Schemas are automatically inferred from your node configuration, but you can be explicit:

```python
from beegen.tools.schema.param import ParamSet

node = CodeNode(
    name="processor",
    code_fn=my_function,
    input_schema=ParamSet.new()
        .var("query: str", required=True)
        .var("limit: int = 10")
        .build(),
    output_schema=ParamSet.new()
        .var("results: List[dict]", required=True)
        .var("count: int")
        .build()
)
```

### Schema Benefits

1. **Type Checking** - Catch errors early
2. **Documentation** - Self-documenting code
3. **Tool Integration** - Auto-generate OpenAI function schemas

```python
# Get OpenAI function schema
schema = node.get_openai_function_schema()
# Returns:
# {
#   "name": "processor",
#   "description": "...",
#   "parameters": {
#     "type": "object",
#     "properties": {...},
#     "required": [...]
#   }
# }
```

---

## 🎯 Best Practices

### 1. Name Your Nodes

```python
# ✅ Good - clear purpose
retriever = MilvusNode(name="vector_search", ...)
reranker = RerankNode(name="rerank_results", ...)

# ❌ Bad - generic names
node1 = MilvusNode(name="node1", ...)
node2 = RerankNode(name="node2", ...)
```

### 2. Use Template Nodes First

```python
# ✅ Start simple with templates
chain = BasicChainNode(
    resource_key="gpt-4o",
    user_prompt="Answer: {query}"
)

# ⚠️ Only break into pieces when needed
# prompt = PromptNode(...)
# llm = LLMNode(...)
# parser = ParserNode(...)
```

### 3. Explicit Variable References

```python
# ✅ Clear and explicit
answer_node.inputs = {
    "query": rewriter["rewritten_query"],
    "docs": retriever["documents"]
}

# ⚠️ Works but less clear
answer_node.inputs = {
    "query": rewriter,  # Which output variable?
    "docs": retriever
}
```

### 4. Compose with GraphNode

```python
# ✅ Reusable component
rag_pipeline = GraphNode(name="rag", ...)

# Use in multiple workflows
workflow_a: rag_pipeline >> ...
workflow_b: rag_pipeline >> ...
```

---

## 🔍 Common Patterns

### Pattern: Sequential Pipeline

```python
START >> step1 >> step2 >> step3 >> END
```

### Pattern: Parallel Processing

```python
START >> splitter >> [worker1, worker2, worker3] >> combiner >> END
```

### Pattern: Conditional Branch

```python
classifier = BasicChainNode(...)
branch = BranchNode(
    cases={"category == 'A'": path_a, "category == 'B'": path_b},
    default=path_default
)

START >> classifier >> branch >> [path_a, path_b, path_default] >> merge >> END
```

### Pattern: Iterative Agent

```python
with WhileLoopNode(name="agent") as agent:
    think = LLMNode(...)
    decide = BranchNode(
        cases={"needs_tool": "execute"},
        default=END
    )
    execute = ToolExecutorNode(...)
    
    START >> think >> decide >> [execute, END]
    execute >> CONTINUE
```

---

## 💡 Quick Reference

### Node Creation

```python
node = NodeType(
    name="unique_name",           # Required
    inputs={...},                 # Variable mappings
    outputs={...},                # Output mappings
    # Node-specific params...
)
```

### Connection Operators

```python
a >> b              # Sequential
a >> [b, c]         # Parallel (fan-out)
[a, b] >> c         # Multiple sources
START >> a >> END   # Complete flow
```

### Variable References

```python
INPUT              # Workflow (or father node) input
OUTPUT             # Workflow (or father node) output
node_a             # Entire node output
node_a["var"]      # Specific variable
{node_a: "var"}    # Explicit mapping
```

---

## 📚 What's Next?

Now that you understand nodes and graphs:

1. **Learn State Management:**
   - [State Management](state-management.md) - How data flows between nodes

2. **Understand Execution:**
   - [Execution Model](execution-model.md) - How graphs run asynchronously

3. **Add Observability:**
   - [Streaming and Observability](streaming-and-observability.md) - Production features

---

## 💡 Key Takeaways

### Node Types
- **AI** - LLM, Embedding, Rerank
- **Data** - Mongo, Milvus, S3
- **Transform** - Prompt, Parser, Code, Lambda
- **Flow** - Branch, ForLoop, WhileLoop
- **Templates** - BasicChain, Retriever, ReactAgent

### Connections
- `>>` for sequential flow
- `[a, b]` for parallel execution
- Variable references for data sharing
- INPUT/OUTPUT for workflow boundaries

### Composition
- GraphNode for reusable sub-workflows
- Nest graphs for modularity
- Reference nested outputs with `graph["output"]`

---

**Ready to understand how data flows? Continue to [State Management](state-management.md) →**