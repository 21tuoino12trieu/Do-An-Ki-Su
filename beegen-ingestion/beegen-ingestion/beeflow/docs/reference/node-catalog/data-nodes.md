# Data Nodes

**Storage and retrieval operations**

---

## MongoNode

**Purpose:** Execute MongoDB operations (find, aggregate, insert, update, delete).

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `resource_key` | str | Required | MongoDB connection identifier |
| `operation` | MongoOperation | Required | Operation type |
| `inputs` | dict | `{}` | Input variable mappings |
| `outputs` | dict | `{}` | Output variable mappings |

### Operations

```python
from beegen.configs import MongoOperation

MongoOperation.FIND       # Query documents
MongoOperation.AGGREGATE  # Aggregation pipeline
MongoOperation.INSERT     # Insert documents
MongoOperation.UPDATE     # Update documents
MongoOperation.DELETE     # Delete documents
```

### Example: Find Documents

```python
mongo = MongoNode(
    name="fetch_docs",
    resource_key="aicenter-chatbot",
    operation=MongoOperation.FIND,
    inputs={
        "query": {"chunk_id": {"$in": chunk_ids}},
        "collection_name": "chunk_data",
        "projection": {"llm_text": 1, "doc_id": 1}
    }
)

# Output: {"data": [...documents...]}
```

### Example: Aggregation Pipeline

```python
mongo = MongoNode(
    name="aggregate",
    resource_key="aicenter-chatbot",
    operation=MongoOperation.AGGREGATE,
    inputs={
        "pipeline": [
            {"$match": {"doc_id": {"$in": doc_ids}}},
            {"$lookup": {
                "from": "documents",
                "localField": "doc_id",
                "foreignField": "_id",
                "as": "doc_info"
            }},
            {"$unwind": "$doc_info"}
        ],
        "collection_name": "chunks"
    }
)
```

### Input Schemas by Operation

**FIND:**
```python
{
    "query": Dict,              # MongoDB query
    "collection_name": str,     # Collection to query
    "projection": Dict = None   # Fields to return
}
```

**AGGREGATE:**
```python
{
    "pipeline": List[Dict],     # Aggregation pipeline
    "collection_name": str      # Collection to query
}
```

### Output Schema

```python
{
    "data": List[Dict]  # Query results
}
```

### Notes

- Contact Mr. Cương for MongoDB connection setup
- Use projection to limit returned fields
- Aggregation pipelines are powerful for complex queries

---

## MilvusNode

**Purpose:** Vector database operations (search, insert, delete).

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `resource_key` | str | Required | Milvus connection identifier |
| `operation` | MilvusOperation | Required | Operation type |
| `inputs` | dict | `{}` | Input variable mappings |
| `outputs` | dict | `{}` | Output variable mappings |

### Operations

```python
from beegen.configs import MilvusOperation

MilvusOperation.SEARCH  # Vector similarity search
MilvusOperation.INSERT  # Insert vectors
MilvusOperation.DELETE  # Delete vectors
```

### Example: Vector Search

```python
milvus = MilvusNode(
    name="vector_search",
    resource_key="chatbot-libra",
    operation=MilvusOperation.SEARCH,
    inputs={
        "query_vectors": embed["embeddings"],
        "collection_name": "bot_collection",
        "output_fields": ["chunk_id", "score"],
        "top_k": 10,
        "threshold": 0.0
    }
)

# Output: {"results": [[{chunk_id: "...", score: 0.92}, ...]]}
```

### Example: With Partitions

```python
milvus = MilvusNode(
    name="partitioned_search",
    resource_key="chatbot-libra",
    operation=MilvusOperation.SEARCH,
    inputs={
        "query_vectors": embed["embeddings"],
        "collection_name": "bot_collection",
        "partition_names": ["documents", "qa"],  # Search specific partitions
        "top_k": 20
    }
)
```

### Input Schema (SEARCH)

```python
{
    "query_vectors": List[List[float]],  # Embedding vectors
    "collection_name": str,              # Milvus collection
    "output_fields": List[str],          # Fields to return
    "top_k": int,                        # Number of results
    "threshold": float = 0.0,            # Minimum similarity
    "partition_names": List[str] = None  # Specific partitions
}
```

### Output Schema

```python
{
    "results": List[List[Dict]]  # Nested: [query][results]
}
```

### Notes

- Returns nested list: `results[0]` for first query
- Scores are similarity scores (higher = more similar)
- Use partitions to narrow search scope
- Contact Mr. Cương for Milvus collection setup

---

## S3Node

**Purpose:** S3 file operations (read, write, list, delete).

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `resource_key` | str | Required | S3 connection identifier |
| `operation` | S3Operation | Required | Operation type |
| `inputs` | dict | `{}` | Input variable mappings |
| `outputs` | dict | `{}` | Output variable mappings |

### Operations

```python
from beegen.configs import S3Operation

S3Operation.READ        # Read file
S3Operation.WRITE       # Write file
S3Operation.LIST_PATHS  # List files
S3Operation.DELETE      # Delete file
```

### Example: Read File

```python
s3 = S3Node(
    name="read_file",
    resource_key="aicenter-cua",
    operation=S3Operation.READ,
    inputs={"key": "path/to/file.pdf"}
)

# Output: {"data": b"file contents..."}
```

### Example: Write File

```python
s3 = S3Node(
    name="write_file",
    resource_key="aicenter-cua",
    operation=S3Operation.WRITE,
    inputs={
        "key": "output/result.json",
        "data": json.dumps(result)
    }
)
```

### Example: List Files

```python
s3 = S3Node(
    name="list_files",
    resource_key="aicenter-cua",
    operation=S3Operation.LIST_PATHS,
    inputs={"prefix": "documents/"}
)

# Output: {"paths": ["documents/file1.pdf", "documents/file2.pdf"]}
```

### Input Schemas by Operation

**READ:**
```python
{
    "key": str  # File path in S3
}
```

**WRITE:**
```python
{
    "key": str,   # File path in S3
    "data": bytes # File contents
}
```

**LIST_PATHS:**
```python
{
    "prefix": str = ""  # Directory prefix
}
```

### Output Schemas

**READ:**
```python
{"data": bytes}
```

**WRITE:**
```python
{"success": bool}
```

**LIST_PATHS:**
```python
{"paths": List[str]}
```

### Notes

- Contact Mr. Cương for S3 bucket access
- Use for storing/loading documents, images, etc.
- READ returns raw bytes (decode as needed)

---

## 💡 Common Patterns

### Pattern: RAG Document Retrieval

```python
# 1. Embed query
embed = EmbeddingNode(
    resource_key="bge-m3",
    inputs={"texts": INPUT["query"]}
)

# 2. Vector search in Milvus
milvus = MilvusNode(
    resource_key="chatbot-libra",
    operation=MilvusOperation.SEARCH,
    inputs={
        "query_vectors": embed["embeddings"],
        "collection_name": "bot_collection",
        "output_fields": ["chunk_id"],
        "top_k": 10
    }
)

# 3. Fetch full documents from MongoDB
mongo = MongoNode(
    resource_key="aicenter-chatbot",
    operation=MongoOperation.FIND,
    inputs={
        "query": {"chunk_id": {"$in": milvus["results"][0]}},
        "collection_name": "chunk_data"
    }
)
```

### Pattern: Document Processing

```python
# 1. List PDF files
s3_list = S3Node(
    operation=S3Operation.LIST_PATHS,
    inputs={"prefix": "documents/"}
)

# 2. Process each file in loop
with ForLoopNode(inputs={"batch": s3_list["paths"]}) as loop:
    s3_read = S3Node(
        operation=S3Operation.READ,
        inputs={"key": INPUT}
    )
    process = DocumentIONode(
        inputs={"data": s3_read["data"]}
    )
    START >> s3_read >> process >> END
```

### Pattern: Aggregation + Vector Search

```python
# Complex MongoDB aggregation
mongo_agg = MongoNode(
    operation=MongoOperation.AGGREGATE,
    inputs={
        "pipeline": [
            {"$match": {"role_ids": {"$in": user_roles}}},
            {"$lookup": {...}},
            {"$project": {...}}
        ],
        "collection_name": "chunks"
    }
)

# Use results for vector search
milvus = MilvusNode(
    operation=MilvusOperation.SEARCH,
    inputs={
        "query_vectors": embed["embeddings"],
        "collection_name": filtered_by_mongo
    }
)
```

---

## 📚 Related

- [AI Nodes](ai-nodes.md) - EmbeddingNode for vector search
- [Transform Nodes](transform-nodes.md) - CodeNode for data processing
- [Templates](templates.md) - RetrieverNode for complete RAG
- [Tutorial: RAG Pipeline](../../tutorials/02-rag-pipeline.md)

---

[← Back to Node Catalog](_index.md)