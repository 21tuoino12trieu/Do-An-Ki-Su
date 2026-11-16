# 🚀 Quickstart Guide

Get your first Beeflow workflow running in 5 minutes.

---

## 📦 Installation

```bash
pip install beeflow
```

**Requirements:**
- Python 3.9 or higher
- Redis server (for streaming)
- MongoDB (for data storage)
- Milvus (for vector search)
- S3-compatible storage (optional)
- Kafka (for event streaming)
- Langfuse account (for observability)

> **💡 Tip:** For local development, you can use Docker Compose to run all services:
> ```bash
> docker-compose up -d redis mongodb milvus
> ```

---

## 🎯 Your First Workflow

Let's build a simple chatbot that answers questions using an LLM.

### Step 1: Import Beeflow

```python
from beeflow import WorkflowEngine, PromptNode, LLMNode
from beeflow.nodes import START, END, INPUT, OUTPUT
```

### Step 2: Define Your Workflow

```python
# Create a workflow engine
with WorkflowEngine(name="my-first-chatbot") as workflow:
    # Node 1: Format the prompt
    prompt = PromptNode(
        name="prompt",
        user_prompt="You are a helpful assistant. Answer: {question}",
        inputs={"question": INPUT}  # Connect to workflow input
    )
    
    # Node 2: Call the LLM
    llm = LLMNode(
        name="llm",
        resource_key="gpt-4o",
        inputs={"messages": prompt},  # Connect to prompt node output
        outputs={"content": OUTPUT}   # Connect to workflow output
    )
    
    # Define execution flow
    START >> prompt >> llm >> END

# Compile the workflow
workflow.compile()
```

### Step 3: Run Your Workflow

```python
# Run with input
result = await workflow.run(
    inputs={"question": "What is the capital of France?"}
)

print(result["content"])
# Output: "The capital of France is Paris."
```

**🎉 Congratulations!** You just built your first Beeflow workflow!

---

## 🔗 Understanding Node Connections

Beeflow's power comes from how nodes connect and share data. Here's how it works:

### The Connection Patterns

All connections use the `inputs` and `outputs` parameters:

```python
node = SomeNode(
    inputs={...},   # How THIS node receives data
    outputs={...}   # Where THIS node sends data
)
```

### 📥 Input Connections (How Nodes Receive Data)

#### Pattern 1: Connect to Specific Variable
```python
inputs={"var": node["var1"]}
```
Connect current node's `var` to a specific variable `var1` from another node.

**Example:**
```python
parser = ParserNode(
    name="parser",
    inputs={"text": llm["content"]}  # Get 'content' from llm node
)
```

---

#### Pattern 2: Connect to Same-Named Variable
```python
inputs={"var": node}
```
Connect current node's `var` to the variable with the same name from another node.

**Example:**
```python
processor = ProcessorNode(
    name="processor",
    inputs={"messages": prompt_node}  # Get 'messages' from prompt_node
)
```

---

#### Pattern 3: Connect to Specific Workflow/Parent Variable
```python
inputs={"var": INPUT["var1"]}
```
Connect to a specific variable from the workflow input (or parent node if inside a subgraph).

**Example:**
```python
prompt = PromptNode(
    name="prompt",
    inputs={
        "query": INPUT["user_question"],  # Get 'user_question' from workflow
        "context": INPUT["background"]     # Get 'background' from workflow
    }
)
```

---

#### Pattern 4: Connect to Same-Named Workflow Variable
```python
inputs={"var": INPUT}
```
Connect to a variable with the same name from the workflow input.

**Example:**
```python
prompt = PromptNode(
    name="prompt",
    inputs={"query": INPUT}  # Get 'query' from workflow input
)
```

---

### 📤 Output Connections (Where Nodes Send Data)

The same patterns apply to outputs:

#### Pattern 1: Send to Specific Variable
```python
outputs={"result": OUTPUT["final_answer"]}
```
Send this node's `result` to workflow's `final_answer` variable.

---

#### Pattern 2: Send to Same-Named Variable
```python
outputs={"result": OUTPUT}
```
Send this node's `result` to workflow's `result` variable (same name).

---

### 🔄 The Magic: Shared Values

**Key Insight:** Connected variables **share the same value** via zero-copy references.

```python
# These two variables point to the SAME memory location:
llm.output_indexes["content"] = 42      # Index in workflow array
parser.input_indexes["text"] = 42       # Same index!

# When llm writes to index 42, parser reads from index 42
# → Zero data copying! 🚀
```

---

## 💡 Practical Examples

### Example 1: Linear Pipeline

```python
with WorkflowEngine(name="linear-pipeline") as workflow:
    # Each node connects to the previous one
    node_a = NodeA(inputs={"data": INPUT})
    node_b = NodeB(inputs={"data": node_a})  # Same name connection
    node_c = NodeC(inputs={"data": node_b["result"]})  # Specific var
    
    START >> node_a >> node_b >> node_c >> END
```

**Data Flow:**
```
workflow.input["data"] → node_a["data"] → node_b["data"] 
    → node_b["result"] → node_c["data"]
```

---

### Example 2: Multiple Inputs

```python
with WorkflowEngine(name="multi-input") as workflow:
    retriever = RetrieverNode(
        inputs={"query": INPUT}  # From workflow
    )
    
    generator = LLMNode(
        inputs={
            "query": INPUT,                    # From workflow
            "context": retriever["docs"],      # From retriever
            "temperature": 0.7                 # Literal value
        }
    )
    
    START >> retriever >> generator >> END
```

**Data Flow:**
```
workflow.input["query"] ──┬──> retriever["query"]
                          └──> generator["query"]

retriever["docs"] ────────> generator["context"]
```

---

### Example 3: Multiple Outputs

```python
with WorkflowEngine(name="multi-output") as workflow:
    analyzer = AnalyzerNode(
        inputs={"text": INPUT}
    )
    
    formatter = FormatterNode(
        inputs={
            "sentiment": analyzer["sentiment"],
            "confidence": analyzer["confidence"]
        },
        outputs={
            "report": OUTPUT["final_report"],
            "score": OUTPUT["sentiment_score"]
        }
    )
    
    START >> analyzer >> formatter >> END

workflow.compile()
result = await workflow.run(inputs={"text": "I love this!"})

print(result["final_report"])    # formatter's 'report' output
print(result["sentiment_score"])  # formatter's 'score' output
```

---

## 🌊 Adding Streaming

Make your workflow stream results in real-time:

```python
with WorkflowEngine(name="streaming-chat") as workflow:
    prompt = PromptNode(
        user_prompt="Answer: {question}",
        inputs={"question": INPUT}
    )
    
    llm = LLMNode(
        resource_key="gpt-4o",
        inputs={"messages": prompt},
        stream=True,  # ✨ Enable streaming
        outputs={"content": OUTPUT}
    )
    
    START >> prompt >> llm >> END

workflow.compile()

# Publish to stream (non-blocking)
import asyncio
request_id = "req_123"
asyncio.create_task(workflow.run(
    inputs={"question": "Explain quantum computing"},
    request_id=request_id
))

# Consume stream in real-time
from beeflow.utils.streaming import STREAM_SERVICE

async for channel in STREAM_SERVICE.get_channels(request_id):
    print(f"\nStreaming from: {channel}")
    async for chunk in STREAM_SERVICE.get(request_id, channel):
        print(chunk.choices[0].delta.content, end="", flush=True)
```

**Output:**
```
Streaming from: workflow:my-first-chatbot.llm
Quantum computing is a revolutionary approach to computation...
```

---

## 🎨 Visualization: Connection Patterns

```
┌─────────────────────────────────────────────────────────┐
│  Workflow Input                                         │
│  {"query": "Hello", "context": "Background"}            │
└────────────┬────────────────────────┬───────────────────┘
             │                        │
             │ INPUT["query"]         │ INPUT["context"]
             ↓                        ↓
        ┌─────────┐              ┌─────────┐
        │ Node A  │──────────────→│ Node B  │
        │         │  node_a       │         │
        └─────────┘               └─────────┘
             │                        │
             │ node_a["result"]       │ node_b["output"]
             ↓                        ↓
        ┌─────────────────────────────────┐
        │        Node C                   │
        │  inputs:                        │
        │    - x: node_a["result"]        │
        │    - y: node_b["output"]        │
        └────────────┬────────────────────┘
                     │
                     │ OUTPUT["final"]
                     ↓
        ┌────────────────────────────┐
        │  Workflow Output           │
        │  {"final": "..."}          │
        └────────────────────────────┘
```

---

## 🔧 Configuration

### Setup LLM Provider

```python
from beegen.registry import ResourceHub
from beegen.configs import OpenAIConfig

ResourceHub.register(
    register_key="gpt-4o",
    config=OpenAIConfig(
        api_key="sk-...",
        model="gpt-4o"
    )
)
```

### Setup Redis for Streaming

```python
from beegen.configs import RedisConfig

ResourceHub.register(
    register_key="nlp-user",
    config=RedisConfig(
        host="localhost",
        port=6379,
        db=0
    )
)
```

### Setup Langfuse for Observability

```python
from beegen.configs import LangfuseConfig

ResourceHub.register(
    register_key="beegen",
    config=LangfuseConfig(
        public_key="pk-...",
        secret_key="sk-...",
        host="https://cloud.langfuse.com"
    )
)
```

---

## ✅ Checklist: You're Ready When...

- ✅ You can create a workflow with `WorkflowEngine`
- ✅ You understand the 4 input connection patterns
- ✅ You can connect nodes with `>>`
- ✅ You can run a workflow with `await workflow.run()`
- ✅ You know how to enable streaming
- ✅ You understand that connected variables share values

---

## 🎯 Next Steps

Now that you understand the basics, dive deeper:

| Topic | Link |
|-------|------|
| **Learn the Architecture** | [Architecture Overview](concepts/architecture-overview.md) |
| **Build a RAG Pipeline** | [Tutorial: RAG System](tutorials/02-rag-pipeline.md) |
| **Explore All Nodes** | [Node Catalog](reference/node-catalog/) |
| **Advanced Patterns** | [Guides](guides/) |

---

## 🆘 Troubleshooting

### Issue: "KeyError: ('node_name', 'var_name')"

**Cause:** Variable not registered in workflow indexer.

**Solution:** Make sure the node is added to the workflow and `compile()` is called:
```python
workflow.compile()  # Don't forget this!
```

---

### Issue: "ValueError: input variable 'x' not defined in schema"

**Cause:** You're trying to connect to a variable that doesn't exist in the node's schema.

**Solution:** Check the node's `input_schema` or documentation:
```python
print(node.input_schema.keys())  # See available variables
```

---

### Issue: Streaming not working

**Cause:** Redis not configured or node doesn't have `stream=True`.

**Solution:**
```python
# 1. Enable streaming on the node
llm = LLMNode(stream=True, ...)

# 2. Make sure Redis is configured
ResourceHub.register_redis(...)

# 3. Use STREAM_SERVICE to consume
from beeflow.utils.streaming import STREAM_SERVICE
```

---

## 💬 Questions?

- 📖 Check the [full documentation](../README.md)
- 💡 See more [examples](../../examples/)
- 🐛 [Report issues](https://github.com/yourusername/beeflow/issues)

---

**Ready to build something awesome? Let's go! 🚀**