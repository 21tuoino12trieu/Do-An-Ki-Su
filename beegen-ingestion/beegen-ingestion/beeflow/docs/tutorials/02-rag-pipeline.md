# Tutorial 2: RAG Pipeline

**Build a document Q&A system with retrieval-augmented generation**

⏱️ **Time:** ~45 minutes  
⭐ **Level:** Intermediate  
🔧 **Nodes:** `RetrieverNode`, `BasicChainNode`, `EmbeddingNode`, `MilvusNode`, `MongoNode`, `RerankNode`

---

## 🎯 What You'll Build

A production-ready RAG (Retrieval-Augmented Generation) chatbot that:
- Embeds user queries into vectors
- Searches for relevant documents in Milvus
- Fetches full document content from MongoDB
- Reranks results for better relevance
- Generates contextual answers using an LLM

**Input:**
```python
"What is your return policy?"
```

**Process:**
```
1. Embed query → [0.123, -0.456, 0.789, ...]
2. Vector search → Find top 10 similar chunks
3. Fetch documents → Get full content from MongoDB
4. Rerank → Select top 3 most relevant
5. Generate answer → Use context to answer question
```

**Output:**
```python
"Our return policy allows returns within 30 days of purchase for a full refund. 
Items must be unused and in original packaging. Please contact customer service 
to initiate a return."
```

---

## 📚 Prerequisites

> **🚀 Quick Setup:** For complete infrastructure setup, data preparation, and `RESOURCE_HUB` configuration, please contact **Mr. Cương**. This tutorial focuses on building the workflow, assuming your infrastructure is ready.

### ✅ Completed
- [Tutorial 1: Basic LLM Chain](01-basic-llm-chain.md)
- [Quickstart Guide](../quickstart.md)

### ✅ Knowledge
- Understanding of embeddings and vector search
- Basic database concepts (collections, queries)
- Async Python

### ✅ System Requirements
- Python 3.9+
- **Milvus** server running (vector database)
- **MongoDB** server running (document storage)
- LLM API key (OpenAI, Azure, etc.)
- Beeflow installed: `pip install beeflow`

### ✅ Infrastructure Setup

> **📞 Note:** For complete infrastructure setup (Milvus, MongoDB, embedding models, and sample data preparation), please contact **Mr. Cương**. This tutorial assumes you have:
> - Milvus collection with indexed documents
> - MongoDB with document storage
> - Resource configurations registered in `RESOURCE_HUB`

---

## 🏗️ Architecture

### High-Level Overview

```
┌────────────────────────────────────────────────────────────┐
│                    User Query                              │
│              "What is your return policy?"                 │
└─────────────────────┬──────────────────────────────────────┘
                      │
                      ↓
┌────────────────────────────────────────────────────────────┐
│  RetrieverNode: "retriever"                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  1. EmbeddingNode → Convert query to vector          │  │
│  │     [0.123, -0.456, 0.789, ...]                      │  │
│  │                                                      │  │
│  │  2. MilvusNode → Search for similar vectors          │  │
│  │     Returns top 10 chunk IDs                         │  │
│  │                                                      │  │
│  │  3. MongoNode → Fetch full document content          │  │
│  │     Get text from chunk IDs                          │  │
│  │                                                      │  │
│  │  4. RerankNode → Rerank by relevance                 │  │
│  │     Select top 3 most relevant docs                  │  │
│  │                                                      │  │
│  │  Output: List of relevant documents                  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────┬──────────────────────────────────────┘
                      │ docs
                      ↓
┌────────────────────────────────────────────────────────────┐
│  BasicChainNode: "answer_generator"                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  PromptNode → Format context + question              │  │
│  │  LLMNode → Generate contextual answer                │  │
│  │  ParserNode → Extract structured response            │  │
│  │                                                      │  │
│  │  Output: Final answer with citations                 │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────┬──────────────────────────────────────┘
                      │
                      ↓
┌────────────────────────────────────────────────────────────┐
│              Final Answer with Context                     │
└────────────────────────────────────────────────────────────┘
```

### Data Flow

```
Query Text
    ↓ (embed)
Query Vector [768 dims]
    ↓ (vector search)
Chunk IDs ["chunk_1", "chunk_2", ...]
    ↓ (fetch from MongoDB)
Full Documents [{"id": "chunk_1", "content": "..."}, ...]
    ↓ (rerank)
Top N Documents [{"id": "chunk_1", "score": 0.95, "content": "..."}, ...]
    ↓ (inject into prompt)
Contextualized Answer
```

---

## 💻 Step-by-Step Implementation

### Step 1: Import Dependencies

Create `rag_chatbot.py`:

```python
import asyncio
from beeflow import WorkflowEngine
from beeflow.nodes import (
    RetrieverNode,
    BasicChainNode,
    START,
    END,
    INPUT,
    OUTPUT
)

# Resources are already configured by Mr. Cương's setup
# No need to configure RESOURCE_HUB manually
```

---

### Step 2: Build the RAG Pipeline

Now let's create the workflow:

```python
# Define the RAG prompt
RAG_PROMPT = """You are a helpful customer service assistant. Answer the user's question based on the provided context.

Context Documents:
{docs}

User Question: {query}

Instructions:
- Answer based ONLY on the provided context
- If the context doesn't contain the answer, say "I don't have information about that"
- Be concise and helpful
- Cite which document you used (if applicable)

Answer:"""

async def create_rag_workflow():
    with WorkflowEngine(name="rag-chatbot") as workflow:
        
        # Node 1: Retrieve relevant documents
        retriever = RetrieverNode(
            name="retriever",
            embedding="bge-m3",              # Embedding model
            rerank="bge-m3",                 # Reranking model
            milvus="chatbot-docs",           # Milvus collection
            mongo="chatbot-storage",         # MongoDB database
            use_rerank=True,                 # Enable reranking
            inputs={
                "query": INPUT["query"],
                "collection": "document_chunks",
                "partition_names": [],       # Search all partitions
                "bot_id": "demo_bot",
                "allowed_roles": ["user"],
                "top_k": 10,                 # Retrieve top 10
                "threshold": 0.0,
                "output_fields": ["chunk_id"],
                "rerank_top_k": 3,          # Rerank to top 3
                "rerank_threshold": 0.0
            }
        )
        
        # Node 2: Generate answer with context
        answer_generator = BasicChainNode(
            name="answer_generator",
            resource_key="gpt-4o",
            user_prompt=RAG_PROMPT,
            inputs={
                "docs": retriever["docs"],   # Retrieved documents
                "query": INPUT["query"]       # Original query
            },
            outputs={"content": OUTPUT["answer"]},
            stream=True                      # Enable streaming
        )
        
        # Define flow
        START >> retriever >> answer_generator >> END
    
    # Compile
    workflow.compile()
    return workflow
```

**Let's break down the RetrieverNode:**

```python
retriever = RetrieverNode(
    name="retriever",
    embedding="bge-m3",              # Which embedding model to use
    rerank="bge-m3",                 # Which reranking model to use
    milvus="chatbot-docs",           # Milvus connection key
    mongo="chatbot-storage",         # MongoDB connection key
    use_rerank=True,                 # Enable reranking step
    inputs={
        "query": INPUT["query"],     # User's question
        "collection": "document_chunks",  # Milvus collection name
        "top_k": 10,                 # Initial retrieval count
        "rerank_top_k": 3,          # Final count after reranking
        # ... other configuration ...
    }
)
```

**Internal Pipeline of RetrieverNode:**
1. **Embed** query → vector
2. **Search** Milvus → chunk IDs
3. **Fetch** documents from MongoDB
4. **Rerank** by relevance → top N
5. **Output** formatted documents

---

### Step 3: Run the RAG System

Complete execution code:

```python
async def main():
    # Create workflow
    workflow = await create_rag_workflow()
    
    # Test query
    query = "What is your return policy?"
    
    print(f"Query: {query}\n")
    
    # Run workflow
    result = await workflow.run(
        inputs={"query": query}
    )
    
    print(f"Answer: {result['answer']}")

if __name__ == "__main__":
    asyncio.run(main())
```

**Expected Output:**
```
Query: What is your return policy?

Answer: Our return policy allows customers to return items within 30 days 
of purchase for a full refund. Items must be in original condition with 
tags attached. [Source: policy_doc_1]
```

---

### Step 4: Add Streaming

Make the response stream in real-time:

```python
async def main_with_streaming():
    workflow = await create_rag_workflow()
    
    query = "What is your return policy?"
    request_id = "req_123"
    
    # Start workflow (non-blocking)
    asyncio.create_task(workflow.run(
        inputs={"query": query},
        request_id=request_id
    ))
    
    # Stream response
    from beeflow.utils.streaming import STREAM_SERVICE
    
    print(f"Query: {query}\n")
    print("Answer: ", end="")
    
    async for channel in STREAM_SERVICE.get_channels(request_id):
        async for chunk in STREAM_SERVICE.get(request_id, channel):
            # Print each token as it arrives
            content = chunk.choices[0].delta.content
            if content:
                print(content, end="", flush=True)
    
    print()  # New line after streaming completes

if __name__ == "__main__":
    asyncio.run(main_with_streaming())
```

---

## 🔍 Understanding the Retrieval Process

Let's trace what happens for the query "What is your return policy?":

### 1. Embedding Stage
```python
Query: "What is your return policy?"
    ↓ (EmbeddingNode)
Vector: [0.123, -0.456, 0.789, ..., 0.321]  # 768 dimensions
```

### 2. Vector Search Stage
```python
Vector: [0.123, -0.456, ...]
    ↓ (MilvusNode: cosine similarity search)
Results: [
    {"chunk_id": "doc_1_chunk_1", "score": 0.89},
    {"chunk_id": "doc_4_chunk_1", "score": 0.65},
    {"chunk_id": "doc_2_chunk_1", "score": 0.52},
    # ... 7 more results
]  # Top 10
```

### 3. Document Fetch Stage
```python
Chunk IDs: ["doc_1_chunk_1", "doc_4_chunk_1", ...]
    ↓ (MongoNode: fetch full content)
Documents: [
    {
        "id": "doc_1_chunk_1",
        "content": "Our return policy allows customers to return items within 30 days...",
        "metadata": {...}
    },
    # ... 9 more documents
]
```

### 4. Reranking Stage
```python
Documents: [10 documents]
    ↓ (RerankNode: deep semantic matching)
Reranked: [
    {"id": "doc_1_chunk_1", "score": 0.95, "content": "Our return policy..."},
    {"id": "doc_4_chunk_1", "score": 0.71, "content": "Customer service..."},
    {"id": "doc_3_chunk_1", "score": 0.68, "content": "We offer a 1-year warranty..."}
]  # Top 3
```

### 5. Context Injection
```python
Top Documents: [3 documents]
    ↓ (Format into prompt)
Context: """
Context Documents:
1. Our return policy allows customers to return items within 30 days...
2. Customer service is available Monday-Friday 9AM-5PM EST...
3. We offer a 1-year warranty on all electronic products...

User Question: What is your return policy?
"""
```

### 6. Answer Generation
```python
Prompt with Context
    ↓ (LLMNode: GPT-4)
Answer: "Our return policy allows customers to return items within 30 days 
of purchase for a full refund. Items must be in original condition with 
tags attached."
```

---

## 🧪 Testing Your RAG System

### Test Case 1: Direct Match

```python
result = await workflow.run(
    inputs={"query": "How long does shipping take?"}
)

# Expected: References doc_2_chunk_1
# "Shipping typically takes 3-5 business days for domestic orders."
```

### Test Case 2: No Relevant Context

```python
result = await workflow.run(
    inputs={"query": "What is your refund policy for gift cards?"}
)

# Expected: Honest admission
# "I don't have information about gift card refunds in the provided documents."
```

### Test Case 3: Multi-Document Answer

```python
result = await workflow.run(
    inputs={"query": "How can I get help with a defective product?"}
)

# Expected: Combines warranty + support info
# "If you have a defective product, it's covered under our 1-year warranty 
# for manufacturing defects. Contact customer service Monday-Friday 9AM-5PM EST 
# via phone, email, or live chat."
```

---

## 🎨 Advanced: Custom Retrieval Pipeline

Want more control? Build the retrieval pipeline manually:

```python
from beeflow.nodes import (
    EmbeddingNode,
    MilvusNode,
    MongoNode,
    RerankNode,
    CodeNode
)

def format_docs(reranks):
    """Format documents for the prompt"""
    formatted = []
    for i, doc in enumerate(reranks["docs"], 1):
        formatted.append(f"{i}. {doc['content']}")
    return {"docs": "\n\n".join(formatted)}

with WorkflowEngine(name="custom-rag") as workflow:
    # Step 1: Embed query
    embed = EmbeddingNode(
        name="embed",
        resource_key="bge-m3",
        inputs={"texts": INPUT["query"]}
    )
    
    # Step 2: Vector search
    search = MilvusNode(
        name="search",
        resource_key="chatbot-docs",
        operation="search",
        inputs={
            "query_vectors": embed["embeddings"],
            "collection_name": "document_chunks",
            "top_k": 10,
            "output_fields": ["chunk_id"]
        }
    )
    
    # Step 3: Fetch documents
    fetch = MongoNode(
        name="fetch",
        resource_key="chatbot-storage",
        operation="find",
        inputs={
            "query": {"chunk_id": {"$in": search["results"]}},
            "collection_name": "chunks"
        }
    )
    
    # Step 4: Rerank
    rerank = RerankNode(
        name="rerank",
        resource_key="bge-m3",
        inputs={
            "query": INPUT["query"],
            "documents": fetch["data"],
            "top_k": 3
        }
    )
    
    # Step 5: Format for prompt
    format_node = CodeNode(
        name="format",
        code_fn=format_docs,
        inputs={"reranks": rerank}
    )
    
    # Step 6: Generate answer
    answer = BasicChainNode(
        name="answer",
        resource_key="gpt-4o",
        user_prompt=RAG_PROMPT,
        inputs={
            "docs": format_node["docs"],
            "query": INPUT["query"]
        },
        outputs=OUTPUT
    )
    
    # Define flow
    START >> embed >> search >> fetch >> rerank >> format_node >> answer >> END
```

This gives you full control over each step!

---

## 🚨 Troubleshooting

### Issue 1: No documents retrieved

**Symptom:**
```python
retriever["docs"] = []
```

**Possible Causes:**
1. Milvus collection is empty or not indexed
2. Query doesn't match any documents
3. Threshold is too high

**Solution:**
```python
# Lower the threshold
inputs={
    "threshold": 0.0,  # Accept all results
    "top_k": 20        # Retrieve more documents
}
```

> **📞 For data indexing issues:** Contact **Mr. Cương** to verify your documents are properly indexed in Milvus and MongoDB.

---

### Issue 2: Low quality answers

**Symptom:**
LLM returns generic or irrelevant answers.

**Possible Causes:**
1. Retrieved documents are not relevant
2. Reranking is disabled or not working
3. Prompt needs improvement

**Solution:**
```python
# Enable reranking with higher threshold
retriever = RetrieverNode(
    use_rerank=True,
    inputs={
        "top_k": 20,              # Cast wider net initially
        "rerank_top_k": 3,        # Then narrow down
        "rerank_threshold": 0.5   # Only keep high-quality matches
    }
)

# Improve prompt
RAG_PROMPT = """...
Instructions:
- Answer ONLY using the provided context
- Quote relevant parts of the context
- If unsure, say "I don't have enough information"
..."""
```

---

### Issue 3: Slow retrieval

**Symptom:**
Workflow takes too long to complete.

**Possible Causes:**
1. Too many documents to rerank
2. Large `top_k` value
3. Database connection is slow

**Solution:**
```python
# Optimize retrieval parameters
inputs={
    "top_k": 5,           # Retrieve fewer documents
    "rerank_top_k": 2,    # Rerank fewer documents
}

# Or disable reranking for speed
retriever = RetrieverNode(
    use_rerank=False,  # Skip reranking step
    ...
)
```

> **📞 For infrastructure performance issues:** Contact **Mr. Cương** to optimize your Milvus/MongoDB setup.

---

### Issue 4: Connection errors

**Symptom:**
```
"ConnectionError: Cannot connect to Milvus/MongoDB" or "key '{key}' not existed in registry!"
```

**Solution:**
Verify your services are running and properly configured in `RESOURCE_HUB`.

> **📞 For configuration help:** Contact **Mr. Cương** for proper `RESOURCE_HUB` setup.


**🎉 Excellent work completing Tutorial 2! Ready for React Agent?**

**→ [Next: Tutorial 3 - React Agent](03-react-agent.md)**