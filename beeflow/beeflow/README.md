# 🐝 Beeflow

**High-performance workflow orchestration framework for building production-grade AI applications**

Beeflow lets you compose complex LLM workflows using an intuitive DAG-based approach with zero-copy state management, real-time streaming, and built-in observability. Built for scale—proven at 500+ concurrent users.

```python
with WorkflowEngine(name="chatbot") as workflow:
    prompt = PromptNode(
        user_prompt="Answer this question: {query}",
        inputs={"query": INPUT}
    )
    
    llm = LLMNode(
        resource_key="gpt-4o",
        inputs={"messages": prompt},
        stream=True  # Real-time token streaming
    )
    
    parser = ParserNode(
        extract_schema=["answer: str", "confidence: float"],
        inputs={"text": llm["content"]},
        outputs=OUTPUT
    )
    
    START >> prompt >> llm >> parser >> END

workflow.compile()
result = await workflow.run(inputs={"query": "What is quantum computing?"})
```

---

## 🚀 Why Beeflow?

| Feature | Beeflow | Others |
|---------|---------|--------|
| **Zero-Copy State** | Variables shared via index references | Data copied between nodes |
| **Real-Time Streaming** | Redis-based multi-channel streaming | Limited or no streaming |
| **Performance** | 500+ CCU proven | Varies |
| **Observability** | Automatic Langfuse integration | Manual instrumentation |
| **Node Ecosystem** | 20+ production-ready nodes | Build from scratch |
| **Intuitive Syntax** | `node_a >> node_b >> node_c` | Complex configuration |

---

## ✨ Key Features

### 🎯 **Intuitive DAG Construction**
```python
# Sequential flow
START >> node_a >> node_b >> END

# Parallel execution (fan-out)
node_c >> [node_d, node_e, node_f]

# Join (fan-in)
[node_x, node_y] >> node_z

# Conditional routing
BranchNode(cases={"score > 0.8": "high_quality"})
```

### ⚡ **Zero-Copy Performance**
Instead of copying data between nodes, Beeflow uses index-based references:
```python
# Both nodes access the same memory location
llm.output_indexes["content"] = 42
parser.input_indexes["text"] = 42  # Same index!
```

### 📡 **Real-Time Streaming**
Stream tokens from multiple nodes simultaneously:
```python
async for channel in STREAM_SERVICE.get_channels(request_id):
    async for chunk in STREAM_SERVICE.get(request_id, channel):
        print(chunk.choices[0].delta.content, end="")
```

### 🎪 **Rich Node Ecosystem**

**AI/ML Nodes:**
- `LLMNode` - LLM generation with streaming
- `EmbeddingNode` - Text embeddings
- `RerankNode` - Document reranking

**Flow Control:**
- `BranchNode` - Conditional routing
- `ForLoopNode` - Batch processing
- `WhileLoopNode` - Iterative loops

**Data Operations:**
- `MilvusNode`, `MongoNode`, `S3Node` - Storage integrations
- `DocumentIONode` - PDF/image processing

**Templates:**
- `BasicChainNode` - Prompt → LLM → Parser pipeline
- `ReactAgentNode` - ReAct reasoning pattern
- `RetrieverNode` - Complete RAG retrieval

[See full node catalog →](docs/reference/node-catalog/)

### 🔍 **Built-in Observability**
Automatic tracing to Langfuse with zero configuration:
```python
# Every node execution is automatically traced with:
# - Execution time
# - Token usage (LLM nodes)
# - Input/output data
# - Error tracking
```

---

## 📦 Installation

```bash
pip install beeflow
```

**Requirements:**
- Python 3.9+
- Redis (for streaming)
- Optional: Milvus, MongoDB (for data nodes)

---

## 🏃 Quick Start

### 1. Basic LLM Chain

```python
from beeflow import WorkflowEngine, PromptNode, LLMNode, START, END, INPUT

with WorkflowEngine(name="hello-world") as workflow:
    prompt = PromptNode(
        user_prompt="Say hello to {name}!",
        inputs={"name": INPUT}
    )
    
    llm = LLMNode(
        resource_key="gpt-4o",
        inputs={"messages": prompt}
    )
    
    START >> prompt >> llm >> END

workflow.compile()
result = await workflow.run(inputs={"name": "World"})
print(result["content"])  # "Hello, World! How can I help you today?"
```

### 2. RAG Pipeline

```python
from beeflow import RetrieverNode, BasicChainNode

with WorkflowEngine(name="rag-chatbot") as workflow:
    # Retrieve relevant documents
    retriever = RetrieverNode(
        name="retriever",
        embedding="bge-m3",
        milvus="my-collection",
        inputs={"query": INPUT}
    )
    
    # Generate answer with context
    answer = BasicChainNode(
        name="answer",
        resource_key="gpt-4o",
        user_prompt="Context: {docs}\n\nQuestion: {query}",
        inputs={
            "docs": retriever["docs"],
            "query": INPUT
        },
        outputs=OUTPUT,
        stream=True
    )
    
    START >> retriever >> answer >> END

workflow.compile()
```

### 3. ReAct Agent

```python
from beeflow import ReactAgentNode, CodeNode

# Define tools
calculator = CodeNode(
    name="calculator",
    code_fn=lambda expr: {"result": eval(expr)},
    return_keys=["result: float"]
)

# Create agent
agent = ReactAgentNode(
    name="math_agent",
    resource_key="gpt-4o",
    tools=[calculator],
    max_iterations=5,
    inputs=INPUT
)
```

[More examples →](examples/)

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [**Quickstart Guide**](docs/quickstart.md) | Get started in 5 minutes |
| [**Architecture Overview**](docs/concepts/architecture-overview.md) | Understand how Beeflow works |
| [**Tutorials**](docs/tutorials/_index.md) | Step-by-step guides for common patterns |
| [**Node Catalog**](docs/reference/node-catalog/) | Complete reference of all nodes |
| [**API Reference**](docs/reference/api-reference.md) | Full API documentation |
| [**Advanced Topics**](docs/advanced/) | Performance, custom nodes, internals |

---

## 🎯 Use Cases

Beeflow excels at:

- ✅ **RAG Systems** - Complete retrieval pipelines with reranking
- ✅ **AI Agents** - ReAct, tool calling, multi-step reasoning
- ✅ **Batch Processing** - Parallel LLM calls with streaming
- ✅ **Document Processing** - PDF → embeddings → storage
- ✅ **Multi-Stage Pipelines** - Validation → processing → post-processing
- ✅ **Production Chatbots** - With streaming and observability

---

## 🔧 Configuration

### Setup Redis for Streaming
```python
from beegen.registry import ResourceHub

ResourceHub.register_redis(
    key="streaming",
    config=RedisConfig(
        host="localhost",
        port=6379,
        db=0
    )
)
```

### Setup Langfuse for Observability
```python
ResourceHub.register_langfuse(
    key="observability",
    config=LangfuseConfig(
        public_key="pk-...",
        secret_key="sk-...",
        host="https://cloud.langfuse.com"
    )
)
```

[Full configuration guide →](docs/reference/configuration.md)

---

## 🏗️ Architecture Highlights

### Zero-Copy State Management
```
Traditional:  NodeA (copy) → NodeB (copy) → NodeC
Beeflow:      NodeA ──┬──→ NodeB ──┬──→ NodeC
                      │            │
                      └─ index[42] ┘
```

### Execution Model
- **DAG-based** workflow execution
- **Parallel execution** where possible
- **Context-aware** for loops and branches
- **Streaming-first** architecture

### Observability
```
Request → Workflow Trace
    ├─ Node Span (timing, I/O)
    ├─ LLM Generation (tokens, model)
    ├─ Node Span
    └─ Error Tracking
```

[Deep dive into architecture →](docs/concepts/architecture-overview.md)

---

## 🤝 Contributing

We welcome contributions! See our [Contributing Guide](docs/advanced/contributing-guide.md) for details.

**Quick Links:**
- [Custom Node Development](docs/advanced/custom-node-development.md)
- [Performance Optimization](docs/advanced/performance-optimization.md)
- [Internals Documentation](docs/advanced/internals-state-indexer.md)

---

## 📊 Performance

Beeflow is built for production scale:

- ✅ **500+ concurrent users** in production
- ✅ **O(1) variable access** via indexed state
- ✅ **Zero-copy communication** between nodes
- ✅ **Efficient Redis streaming** for real-time output
- ✅ **Minimal memory footprint** with lazy allocation

[Performance tuning guide →](docs/advanced/performance-optimization.md)

---

## 📄 License

[Your License Here]

---

## 🙋 Support

- **Documentation:** [docs/](docs/)
- **Examples:** [examples/](examples/)
- **Issues:** [GitHub Issues](https://github.com/yourusername/beeflow/issues)
- **Discussions:** [GitHub Discussions](https://github.com/yourusername/beeflow/discussions)

---

## 🌟 Star History

If you find Beeflow useful, please consider giving it a star! ⭐

---

**Built with ❤️ for the AI community**