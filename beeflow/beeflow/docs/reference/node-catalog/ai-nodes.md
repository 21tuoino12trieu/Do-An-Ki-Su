# AI Nodes

**Intelligence and model operations**

---

## LLMNode

**Purpose:** Call language models for text generation.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `resource_key` | str | Required | Model identifier from RESOURCE_HUB |
| `stream` | bool | `False` | Enable real-time streaming |
| `inputs` | dict | `{}` | Input variable mappings |
| `outputs` | dict | `{}` | Output variable mappings |

### Input Schema

```python
{
    "messages": List[Dict],              # Required: Chat messages
    "temperature": float = 0.0,          # Sampling temperature
    "max_tokens": int = None,            # Max output tokens
    "top_p": float = 1.0,                # Nucleus sampling
    "tools": List[Dict] = [],            # Function calling tools
    "chat_template_kwargs": Dict = {}    # e.g. {"enable_thinking": True}
}
```

### Output Schema

```python
{
    "role": str = "assistant",           # Message role
    "content": str,                      # Generated text
    "model_used": str,                   # Model name
    "tokens_used": Dict[str, int],       # Token counts
    "finish_reason": str = None          # "stop", "length", etc.
}
```

### Example: Basic Usage

```python
llm = LLMNode(
    name="generator",
    resource_key="gpt-4o",
    inputs={"messages": prompt_node}
)
```

### Example: With Streaming

```python
llm = LLMNode(
    name="streamer",
    resource_key="gpt-4o",
    inputs={"messages": INPUT},
    stream=True  # Enable real-time output
)

# Consume stream
async for channel in STREAM_SERVICE.get_channels(request_id):
    async for chunk in STREAM_SERVICE.get(request_id, channel):
        print(chunk.choices[0].delta.content, end="")
```

### Example: With Tool Calling

```python
llm = LLMNode(
    name="tool_caller",
    resource_key="gpt-4o",
    inputs={
        "messages": prompt_node,
        "tools": [calculator.get_openai_tool_schema()],
        "tool_choice": "auto"
    }
)
```

### Notes

- Token usage automatically tracked in Langfuse
- Use `stream=True` for better UX on long generations
- Available models depend on RESOURCE_HUB configuration
- Contact Mr. Cương for model access

---

## EmbeddingNode

**Purpose:** Generate vector embeddings for text.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `resource_key` | str | Required | Embedding model identifier |
| `inputs` | dict | `{}` | Input variable mappings |
| `outputs` | dict | `{}` | Output variable mappings |

### Input Schema

```python
{
    "texts": Union[str, List[str]]  # Required: Text(s) to embed
}
```

### Output Schema

```python
{
    "embeddings": List[List[float]]  # Vector embeddings
}
```

### Example: Single Text

```python
embed = EmbeddingNode(
    name="embedder",
    resource_key="bge-m3",
    inputs={"texts": INPUT["query"]}
)
```

### Example: Batch Embedding

```python
embed = EmbeddingNode(
    name="batch_embedder",
    resource_key="bge-m3",
    inputs={"texts": ["text1", "text2", "text3"]}
)
```

### Example: In RAG Pipeline

```python
embed = EmbeddingNode(
    name="query_embed",
    resource_key="bge-m3",
    inputs={"texts": rewriter["query"]}
)

search = MilvusNode(
    name="vector_search",
    inputs={"query_vectors": embed["embeddings"]}
)
```

### Notes

- Returns list of embeddings (even for single text)
- Dimension depends on model (e.g., bge-m3: 1024)
- Use same model for indexing and querying

---

## RerankNode

**Purpose:** Rerank search results by relevance to query.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `resource_key` | str | Required | Reranker model identifier |
| `inputs` | dict | `{}` | Input variable mappings |
| `outputs` | dict | `{}` | Output variable mappings |

### Input Schema

```python
{
    "query": str,                    # Required: Search query
    "documents": List,               # Required: Docs to rerank
    "top_k": int = -1,              # Number to return (-1 = all)
    "threshold": float = 0.0         # Minimum score threshold
}
```

### Output Schema

```python
{
    "reranks": List[Dict]  # Reranked documents with scores
}
```

### Example: Basic Reranking

```python
rerank = RerankNode(
    name="reranker",
    resource_key="bge-m3",
    inputs={
        "query": INPUT["query"],
        "documents": retriever["docs"],
        "top_k": 5
    }
)
```

### Example: With Threshold

```python
rerank = RerankNode(
    name="filtered_rerank",
    resource_key="bge-m3",
    inputs={
        "query": INPUT["query"],
        "documents": retriever["docs"],
        "top_k": 10,
        "threshold": 0.5  # Only docs with score > 0.5
    }
)
```

### Example: String Documents

```python
# Input: List[str]
documents = ["Doc 1 text", "Doc 2 text", "Doc 3 text"]

# Output format:
[
    {"content": "Doc 1 text", "score": 0.92},
    {"content": "Doc 3 text", "score": 0.85},
    {"content": "Doc 2 text", "score": 0.71}
]
```

### Example: Dict Documents

```python
# Input: List[Dict]
documents = [
    {"id": 1, "content": "Doc 1 text"},
    {"id": 2, "content": "Doc 2 text"}
]

# Output format (preserves original fields):
[
    {"id": 1, "content": "Doc 1 text", "score": 0.92},
    {"id": 2, "content": "Doc 2 text", "score": 0.71}
]
```

### Notes

- Documents must have `content` field (string or dict)
- Scores are between 0 and 1
- `top_k=-1` returns all documents
- Use after vector search for better ranking

---

## 💡 Common Patterns

### Pattern: RAG with Reranking

```python
# 1. Embed query
embed = EmbeddingNode(
    resource_key="bge-m3",
    inputs={"texts": INPUT["query"]}
)

# 2. Vector search (get top 50)
search = MilvusNode(
    inputs={
        "query_vectors": embed["embeddings"],
        "top_k": 50
    }
)

# 3. Rerank (narrow to top 5)
rerank = RerankNode(
    resource_key="bge-m3",
    inputs={
        "query": INPUT["query"],
        "documents": search["results"],
        "top_k": 5
    }
)

# 4. Generate answer
answer = LLMNode(
    resource_key="gpt-4o",
    inputs={
        "messages": format_prompt(
            query=INPUT["query"],
            docs=rerank["reranks"]
        )
    }
)
```

### Pattern: Streaming Chat

```python
prompt = PromptNode(
    system_prompt="You are a helpful assistant.",
    user_prompt="{query}",
    inputs={"query": INPUT}
)

llm = LLMNode(
    resource_key="gpt-4o",
    inputs={"messages": prompt},
    stream=True,  # Real-time output
    outputs=OUTPUT
)

START >> prompt >> llm >> END
```

### Pattern: Batch Embedding

```python
# Embed multiple texts at once
embed = EmbeddingNode(
    resource_key="bge-m3",
    inputs={"texts": INPUT["texts"]}  # List[str]
)

# Returns embeddings in same order
# embeddings[i] corresponds to texts[i]
```

---

## 📚 Related

- [Transform Nodes](transform-nodes.md) - PromptNode for formatting
- [Data Nodes](data-nodes.md) - MilvusNode for vector search
- [Templates](templates.md) - BasicChainNode for quick LLM calls
- [Concepts: Streaming](../../concepts/streaming-and-observability.md)

---

[← Back to Node Catalog](_index.md)