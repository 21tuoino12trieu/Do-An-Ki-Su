# Template Nodes

**Pre-built workflow patterns for common tasks**

---

## BasicChainNode

**Purpose:** Simple LLM processing pipeline (Prompt → LLM → optional Parser).

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `resource_key` | str | ✓ | LLM model identifier |
| `user_prompt` | str | - | User message template |
| `system_prompt` | str | - | System message |
| `messages_template` | List[Dict] | - | Complex message array |
| `extract_schema` | List[str] | - | Parse structured output |
| `parser` | str | - | Parser format (xml/json/yaml) |

### Example: Structured Output

```python
classifier = BasicChainNode(
    name="classify",
    resource_key="gpt-4o",
    user_prompt="Classify sentiment: {text}",
    extract_schema=["sentiment: str", "confidence: float"],
    parser="xml",
    inputs={"text": INPUT["text"]}
)

# Internally: PromptNode → LLMNode → ParserNode
# Output: {"sentiment": "positive", "confidence": 0.95}
```

### Notes

- **Auto-wires** Prompt → LLM (→ Parser if `extract_schema`)
- Use for quick LLM tasks without manual node connections

---

## ToolExecutorNode

**Purpose:** Execute tools dynamically by name (function calling).

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tools` | List[BaseNode] | ✓ | Available tools (CodeNodes) |
| `inputs` | dict | ✓ | Must include `tool_name` and `tool_params` |

### Example: Calculator + Search

```python
# Define tools
calculator = CodeNode(
    name="calculator",
    code_fn=lambda expr: {"result": eval(expr)}
)

search = CodeNode(
    name="search",
    code_fn=lambda query: {"results": f"Results for: {query}"}
)

# Tool executor
executor = ToolExecutorNode(
    name="tool_manager",
    tools=[calculator, search],
    inputs={
        "tool_name": parser["Action"],      # "calculator" or "search"
        "tool_params": parser["Params"]     # {"expr": "2+2"} or {"query": "..."}
    }
)

# Output: {"result": <tool_output>, "success": True, "matched_tool": "calculator"}
```

### Notes

- **Dynamic routing** to tool by name at runtime
- Common in **agent loops** (ReAct pattern)
- Tools must be CodeNodes or similar

---

## ReactAgentNode

**Purpose:** Complete ReAct agent (Reasoning + Acting loop).

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `resource_key` | str | ✓ | LLM model |
| `tools` | List[BaseNode] | ✓ | Available tools |
| `max_iterations` | int | - | Loop limit (default: 5) |
| `context_prompt` | str | - | Agent context/instructions |

### Example: Math Agent

```python
# Define tools
add = CodeNode(
    name="add",
    code_fn=lambda a, b: {"sum": a + b}
)

multiply = CodeNode(
    name="multiply",
    code_fn=lambda a, b: {"product": a * b}
)

# Agent
agent = ReactAgentNode(
    name="math_agent",
    resource_key="gpt-4o",
    tools=[add, multiply],
    max_iterations=5,
    context_prompt="You are a math assistant.",
    inputs={"query": INPUT["query"]}
)

# Internally: WhileLoopNode with reason → parse → tool execution → update loop
# Output: {"Answer": "The result is 42"}
```

### Notes

- **Complete agent pattern** pre-built
- **Iterative reasoning** until answer found
- Includes max iteration safety

---

## RetrieverNode

**Purpose:** Complete RAG retrieval pipeline (Embed → Vector Search → Fetch Docs → Rerank).

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `embedding` | str | "bge-m3" | Embedding model |
| `rerank` | str | "bge-m3" | Rerank model |
| `milvus` | str | "chatbot-libra" | Milvus connection |
| `mongo` | str | "aicenter-chatbot" | MongoDB connection |
| `use_rerank` | bool | True | Enable reranking |

### Example: RAG Retrieval

```python
retriever = RetrieverNode(
    name="retriever",
    embedding="bge-m3",
    rerank="bge-m3",
    milvus="chatbot-libra",
    mongo="aicenter-chatbot",
    use_rerank=True,
    inputs={
        "query": INPUT["query"],
        "collection": "bot_collection",
        "partition_names": ["documents"],
        "bot_id": INPUT["bot_id"],
        "allowed_roles": ["L1"],
        "top_k": 10,
        "rerank_top_k": 5
    }
)

# Internally: EmbedNode → MilvusNode → MongoNode → RerankNode
# Output: {"docs": [{id, doc, content, score}, ...]}
```

### Notes

- **Complete RAG pipeline** in one node
- Auto-handles role filtering, document fetching
- Contact Mr. Cương for Milvus/Mongo setup

---

## 💡 Usage Patterns

### Pattern: Agent with RAG

```python
# Retrieval
retriever = RetrieverNode(
    inputs={"query": INPUT["query"], ...}
)

# Agent with retrieved docs
agent = ReactAgentNode(
    resource_key="gpt-4o",
    tools=[search_tool, calculator],
    inputs={
        "query": INPUT["query"],
        "context_docs": retriever["docs"]
    }
)

START >> retriever >> agent >> END
```

### Pattern: Multi-Step Classification

```python
# Step 1: Content filter
filter_chain = BasicChainNode(
    resource_key="gpt-4o",
    user_prompt="Check if safe: {text}",
    extract_schema=["is_safe: bool"]
)

# Step 2: Route based on safety
branch = BranchNode(
    cases={"is_safe": "process"},
    default=END,
    inputs={"is_safe": filter_chain["is_safe"]}
)

# Step 3: Process if safe
process = BasicChainNode(
    name="process",
    resource_key="gpt-4o",
    user_prompt="Analyze: {text}",
    extract_schema=["analysis: str"]
)

START >> filter_chain >> branch >> [process, END]
```

---

## 📚 Related

- [Flow Control](flow-control.md) - Loops, branches for custom patterns
- [AI Nodes](ai-nodes.md) - Base LLM, Embedding nodes
- [Transform Nodes](transform-nodes.md) - CodeNode for custom tools
- [Tutorial: ReAct Agent](../../tutorials/03-react-agent.md)
- [Tutorial: RAG Pipeline](../../tutorials/02-rag-pipeline.md)

---

[← Back to Node Catalog](_index.md)