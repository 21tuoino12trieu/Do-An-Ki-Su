# beegen-core

**A LangChain-inspired framework built from scratch for building AI agents with production-grade capabilities.**

Like LangChain but implemented from the ground up with a focus on modularity, observability, and enterprise features.

## 🎯 Core Philosophy

beegen-core provides the building blocks for AI applications through a unified factory pattern and configuration-driven architecture. All components are designed to work together seamlessly while remaining independently usable.

## 🏗️ Architecture

```
beegen-core/
├── llms/              # LLM integrations (OpenAI, Gemini, Azure)
├── embeddings/        # Embedding models
├── reranks/           # Reranking engines (Cohere, TEI, VLLM)
├── vectordb/          # Vector databases (Milvus)
├── storage/           # Data persistence (MongoDB, S3)
├── cache/             # Caching layer (Redis)
├── mcp/               # MCP server protocol
├── observations/      # Observability (Langfuse)
├── registry/          # Unified factory pattern
└── configs/           # YAML-based configuration
```

## ✨ Key Features

### 🔧 Unified Factory Pattern
All components are instantiated through a single `ModelFactory`:

```python
from beegen.registry.model_factory import ModelFactory
from beegen.configs import LLMConfig, MilvusConfig

# Create any component from config
llm = ModelFactory.create(LLMConfig.from_yaml_file("llm.yaml"))
vectordb = ModelFactory.create(MilvusConfig.default())
```

### 🎨 Configuration-Driven
Everything is configured via YAML - no hardcoded values:

```yaml
# config/llms/openai.yaml
model: gpt-4o
api_key: ${OPENAI_API_KEY}
temperature: 0.7
max_tokens: 2000
```

### 🔌 Multi-Provider Support
**LLMs**: OpenAI, Azure OpenAI, Google Gemini (via Vertex AI)
**Embeddings**: Custom embedding providers
**Vector DBs**: Milvus with full CRUD operations
**Storage**: MongoDB (async), S3-compatible object storage
**Cache**: Redis with distributed support
**Reranking**: Cohere, TEI, vLLM

### 🔍 Built-in Observability
Integrated Langfuse support for tracing and monitoring:

```python
from beegen.observations.bee_langfuse import BeeLangfuse

# Singleton pattern per project
langfuse = BeeLangfuse.get_instance(
    project_codename="my-project",
    public_key=config.public_key,
    secret_key=config.secret_key,
    host=config.host
)

# Retrieve prompts
prompt = langfuse.get_prompt("PROJECT:PROMPT_NAME")
```

### 🚀 Async-First Design
All I/O operations are async-native for maximum performance:

```python
# Streaming LLM responses
async for chunk in llm.stream(
    messages=[{"role": "user", "content": "Hello!"}],
    temperature=0.7
):
    print(chunk.choices[0].delta.content)

# Parallel operations
results = await asyncio.gather(
    vectordb.search(query_vector),
    mongo.find({"status": "active"}),
    cache.get("user_session")
)
```

### 🛠️ Tool Calling Support
Native support for function calling with OpenAI/Gemini models:

```python
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string"}
            }
        }
    }
}]

completion = await llm.generate(
    messages=[{"role": "user", "content": "Weather in SF?"}],
    tools=tools
)
```

## 📦 Installation

```bash
pip install beeflow
```

**Requirements**: Python >= 3.12

## 🚀 Quick Start

### 1. Basic LLM Usage

```python
from beegen.llms.openai_sdk_model import OpenAISDKModel
from beegen.configs import LLMConfig

# Load from config
config = LLMConfig.from_yaml_file("config/llms/openai.yaml")
llm = OpenAISDKModel(config)

# Generate completion
response = await llm.generate(
    messages=[{"role": "user", "content": "Explain quantum computing"}]
)
print(response.choices[0].message.content)
```

### 2. Vector Search with Milvus

```python
from beegen.vectordb.milvus_engine import MilvusEngine
from beegen.configs import MilvusConfig

# Initialize
milvus = MilvusEngine(MilvusConfig.default())

# Create collection
await milvus.run(
    operation=MilvusOperation.CREATE_COLLECTION,
    params={
        "collection_name": "documents",
        "schema": schema,
        "index_params": index_params
    }
)

# Search
results = await milvus.run(
    operation=MilvusOperation.SEARCH,
    params={
        "collection_name": "documents",
        "query_vectors": [embedding],
        "top_k": 5
    }
)
```

### 3. Document Storage with MongoDB

```python
from beegen.storage.mongo.mongo_engine import AsyncMongoEngine
from beegen.configs import MongoConfig

mongo = AsyncMongoEngine(MongoConfig.default())

# Insert documents
await mongo.run(
    operation=MongoOperation.INSERT_MANY,
    params={
        "data": [
            {"title": "Doc 1", "content": "..."},
            {"title": "Doc 2", "content": "..."}
        ]
    }
)

# Query with aggregation
results = await mongo.run(
    operation=MongoOperation.AGGREGATE,
    params={
        "pipeline": [
            {"$match": {"status": "published"}},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}}
        ]
    }
)
```

## 🎯 Use Cases

- **RAG Applications**: Vector search + LLM generation with reranking
- **Agent Systems**: Multi-tool agents with MCP protocol support
- **Production AI**: Observability, caching, and error handling built-in
- **Multi-modal AI**: Support for text + image inputs
- **Enterprise Integration**: Keycloak auth, S3 storage, Kafka logging

## 🔐 Configuration Examples

### LLM Config
```yaml
# config/llms/azure.yaml
api_type: azure
model: gpt-4o
api_key: ${AZURE_API_KEY}
api_version: "2024-02-01"
azure_endpoint: https://your-resource.openai.azure.com
temperature: 0.7
max_tokens: 2000
```

### Vector DB Config
```yaml
# config/milvus.yaml
host: localhost
port: 19530
db_name: default
user: root
password: ${MILVUS_PASSWORD}
secure: false
```

## 🔧 Advanced Features

### Python Code Interpreter
Built-in safe Python interpreter for executing LLM-generated code:

```python
from beegen.interpreters.internal_python_interpreter import InternalPythonInterpreter

interpreter = InternalPythonInterpreter(
    action_space={"math": math, "np": np},
    import_white_list=["math", "numpy"]
)

result = interpreter.execute(code)
```

### S3 Storage Operations
Full S3-compatible storage with boto3 config:

```python
from beegen.storage.s3.s3_engine import S3Engine

s3 = S3Engine(S3Config.default())
await s3.upload_file(local_path, s3_key)
await s3.download_file(s3_key, local_path)
```

### Redis Caching
Distributed caching with TTL support:

```python
from beegen.cache.redis_connector import RedisConnector

redis = RedisConnector(RedisConfig.default())
await redis.set("key", "value", ex=3600)
value = await redis.get("key")
```

## 📊 Monitoring & Logging

### Langfuse Integration
```python
from beegen.observations.langfuse_adapter import AsyncTraceBuffer

trace_buffer = AsyncTraceBuffer(config=langfuse_config)

# Add spans with hierarchy
trace_buffer.add_span(
    request_id="req_123",
    name="root_span",
    parent=None,
    input={"query": "..."},
    user_id="user_123"
)

# Flush to Langfuse
await trace_buffer.flush("req_123")
```

### Kafka Logging
Async Kafka handler for distributed logging:

```python
from beegen.loggings import setup_logger, LogConfig

logger = setup_logger(
    config=LogConfig(
        kafka=KafkaConfig(
            bootstrap_servers=["kafka:9092"],
            topic="app-logs"
        )
    )
)
```

## 🤝 Contributing

beegen-core is built for production use at scale. Contributions are welcome!

## 📄 License

Apache License 2.0

---

**Built with ❤️ for production AI systems**