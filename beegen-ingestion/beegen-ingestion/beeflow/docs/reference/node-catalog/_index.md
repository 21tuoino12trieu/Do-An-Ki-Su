# Node Catalog

**Complete reference for all Beeflow nodes**

---

## 📚 Overview

This catalog documents all available nodes in Beeflow. Each node is a building block for your workflows.

**Quick finder:** Use Ctrl+F to search for a node by name.

---

## 🗂️ Node Categories

### [AI Nodes](ai-nodes.md) - Intelligence & Models
LLM calls, embeddings, and reranking for AI tasks.

| Node | Purpose | Key Parameters |
|------|---------|----------------|
| **LLMNode** | Call language models | `resource_key`, `stream` |
| **EmbeddingNode** | Generate embeddings | `resource_key` |
| **RerankNode** | Rerank search results | `resource_key`, `top_k` |

**Common use cases:** Chat, generation, RAG, semantic search

---

### [Data Nodes](data-nodes.md) - Storage & Retrieval
Database operations for MongoDB, Milvus, and S3.

| Node | Purpose | Key Parameters |
|------|---------|----------------|
| **MongoNode** | MongoDB operations | `resource_key`, `operation` |
| **MilvusNode** | Vector search | `resource_key`, `operation` |
| **S3Node** | S3 file operations | `resource_key`, `operation` |

**Common use cases:** RAG retrieval, document storage, vector search

---

### [Transform Nodes](transform-nodes.md) - Processing & Formatting
Data transformation and text processing.

| Node | Purpose | Key Parameters |
|------|---------|----------------|
| **PromptNode** | Format prompts | `user_prompt`, `system_prompt` |
| **ParserNode** | Extract structured data | `format`, `extract_schema` |
| **CodeNode** | Custom Python logic | `code_fn` |
| **LambdaNode** | Simple transformations | `code_fn`, `return_keys` |
| **DataNode** | Store/pass data | `inputs` |

**Common use cases:** Prompt formatting, parsing LLM output, custom logic

---

### [Flow Control](flow-control.md) - Execution Control
Control workflow execution with branching and loops.

| Node | Purpose | Key Parameters |
|------|---------|----------------|
| **BranchNode** | Conditional routing | `cases`, `default` |
| **ForLoopNode** | Batch processing | `inputs` |
| **WhileLoopNode** | Iterative loops | `inputs` |

**Common use cases:** Conditional logic, batch processing, agents

---

### [Templates](templates.md) - Pre-built Components
Ready-to-use composite nodes for common patterns.

| Node | Purpose | Key Parameters |
|------|---------|----------------|
| **BasicChainNode** | Prompt→LLM→Parse | `resource_key`, `user_prompt`, `extract_schema` |
| **RetrieverNode** | Complete RAG pipeline | `embedding`, `milvus`, `mongo` |
| **ReactAgentNode** | ReAct reasoning agent | `resource_key`, `tools` |
| **ToolExecutorNode** | Dynamic tool execution | `tools` |

**Common use cases:** Quick prototyping, standard patterns

---

## 🔍 Quick Reference

### By Use Case

**"I need to call an LLM"**
→ [LLMNode](ai-nodes.md#llmnode) or [BasicChainNode](templates.md#basicchainnode)

**"I need to retrieve documents"**
→ [MilvusNode](data-nodes.md#milvusnode) + [MongoNode](data-nodes.md#mongonode) or [RetrieverNode](templates.md#retrievernode)

**"I need to parse LLM output"**
→ [ParserNode](transform-nodes.md#parsernode)

**"I need custom logic"**
→ [CodeNode](transform-nodes.md#codenode) or [LambdaNode](transform-nodes.md#lambdanode)

**"I need conditional routing"**
→ [BranchNode](flow-control.md#branchnode)

**"I need to process a batch"**
→ [ForLoopNode](flow-control.md#forloopnode)

**"I need an agent"**
→ [ReactAgentNode](templates.md#reactagentnode)

---

## 📖 How to Read Node Documentation

Each node page follows this structure:

```markdown
## NodeName

**Purpose:** What the node does

**Parameters:**
- param1: Description
- param2: Description

**Example:**
[Code example]

**Notes:**
Important details
```

---

## 🎯 Common Patterns

### Pattern 1: Simple LLM Call
```python
chain = BasicChainNode(
    resource_key="gpt-4o",
    user_prompt="Answer: {query}"
)
```

### Pattern 2: RAG Pipeline
```python
retriever = RetrieverNode(
    embedding="bge-m3",
    milvus="chatbot-libra",
    mongo="aicenter-chatbot"
)
answer = BasicChainNode(
    user_prompt="Answer using {docs}: {query}",
    inputs={"docs": retriever, "query": INPUT}
)
```

### Pattern 3: Conditional Flow
```python
classifier = BasicChainNode(...)
branch = BranchNode(
    cases={"category == 'A'": path_a},
    default=path_b
)
START >> classifier >> branch >> [path_a, path_b]
```

### Pattern 4: Batch Processing
```python
with ForLoopNode(inputs={"batch": INPUT}) as loop:
    processor = LLMNode(...)
    START >> processor >> END
```

---

## 💡 Tips

### Choosing Between Similar Nodes

**LLMNode vs BasicChainNode?**
- Use **BasicChainNode** for simple prompt→LLM→parse
- Use **LLMNode** when you need fine control

**CodeNode vs LambdaNode?**
- Use **LambdaNode** for simple one-liners
- Use **CodeNode** for complex logic with docstrings

**Custom nodes vs Templates?**
- Start with **Templates** (faster)
- Build **Custom nodes** when you need reusability

---

## 📚 Related Documentation

- [Concepts: Nodes and Graphs](../../concepts/nodes-and-graphs.md) - Understanding nodes
- [Tutorials](../../tutorials/_index.md) - Learn by doing
- [API Reference](../api-reference.md) - Core classes

---

## 🔗 Node Index (Alphabetical)

| Node | Category | Page |
|------|----------|------|
| BasicChainNode | Template | [templates.md](templates.md#basicchainnode) |
| BranchNode | Flow Control | [flow-control.md](flow-control.md#branchnode) |
| CodeNode | Transform | [transform-nodes.md](transform-nodes.md#codenode) |
| DataNode | Transform | [transform-nodes.md](transform-nodes.md#datanode) |
| EmbeddingNode | AI | [ai-nodes.md](ai-nodes.md#embeddingnode) |
| ForLoopNode | Flow Control | [flow-control.md](flow-control.md#forloopnode) |
| LambdaNode | Transform | [transform-nodes.md](transform-nodes.md#lambdanode) |
| LLMNode | AI | [ai-nodes.md](ai-nodes.md#llmnode) |
| MilvusNode | Data | [data-nodes.md](data-nodes.md#milvusnode) |
| MongoNode | Data | [data-nodes.md](data-nodes.md#mongonode) |
| ParserNode | Transform | [transform-nodes.md](transform-nodes.md#parsernode) |
| PromptNode | Transform | [transform-nodes.md](transform-nodes.md#promptnode) |
| ReactAgentNode | Template | [templates.md](templates.md#reactagentnode) |
| RerankNode | AI | [ai-nodes.md](ai-nodes.md#reranknode) |
| RetrieverNode | Template | [templates.md](templates.md#retrievernode) |
| S3Node | Data | [data-nodes.md](data-nodes.md#s3node) |
| ToolExecutorNode | Template | [templates.md](templates.md#toolexecutornode) |
| WhileLoopNode | Flow Control | [flow-control.md](flow-control.md#whileloopnode) |

---

**Ready to explore? Pick a category above or search for a specific node!** 🚀