# Streaming and Observability

**Production features for monitoring and real-time output**

⏱️ **Time:** ~15 minutes  
🎯 **Goal:** Understand streaming, tracing, and production monitoring

---

## 🎯 Overview

Beeflow provides two key production features:

1. **Redis Streaming** - Real-time output from LLM nodes
2. **Langfuse Tracing** - Automatic observability and monitoring

Both work automatically with minimal configuration.

---

## 🌊 Redis Streaming

### Why Streaming?

```python
# Without streaming (wait for everything)
result = await workflow.run(inputs={"query": "Long question..."})
print(result["answer"])  # User waits 30 seconds 😴

# With streaming (real-time output)
asyncio.create_task(workflow.run(inputs={"query": "Long question..."}))
async for chunk in stream:
    print(chunk, end="")  # User sees progress immediately! ⚡
```

---

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Workflow Execution                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐         │
│  │  Node A    │→ │  LLM Node  │→ │  Node C    │         │
│  │  (prompt)  │  │  (stream)  │  │  (parser)  │         │
│  └────────────┘  └──────┬─────┘  └────────────┘         │
└─────────────────────────┼───────────────────────────────┘
                          │
                          ↓ Push chunks to Redis
              ┌───────────────────────┐
              │    Redis Streams      │
              │  ┌─────────────────┐  │
              │  │ Channel: llm[0] │  │
              │  │ Channel: llm[1] │  │
              │  │ Channel: llm[2] │  │
              │  └─────────────────┘  │
              └───────────────────────┘
                          │
                          ↓ Consumer pulls chunks
              ┌───────────────────────┐
              │   STREAM_SERVICE      │
              │   .get_channels()     │
              │   .get(channel)       │
              └───────────────────────┘
                          │
                          ↓
              ┌───────────────────────┐
              │    User Application   │
              │  async for chunk in:  │
              │    print(chunk)       │
              └───────────────────────┘
```

---

### Enable Streaming

```python
# 1. Enable streaming on LLM node
llm = LLMNode(
    name="generator",
    resource_key="gpt-4o",
    stream=True  # ✨ Enable streaming
)

# 2. Start workflow (don't await!)
request_id = "req_123"
asyncio.create_task(
    workflow.run(inputs={"query": "..."}, request_id=request_id)
)

# 3. Consume stream
from beeflow.utils.streaming import STREAM_SERVICE

async for channel in STREAM_SERVICE.get_channels(request_id):
    print(f"\n{channel}:")
    async for chunk in STREAM_SERVICE.get(request_id, channel):
        content = chunk.choices[0].delta.content
        if content:
            print(content, end="", flush=True)
```

---

### Channel Names

Each streaming node creates a channel: `node_path[context_id]`

```python
# Simple workflow
workflow.llm[main] → "workflow_name.llm[main]"

# Nested graph
workflow.subgraph.llm[main] → "workflow_name.subgraph.llm[main]"

# ForLoop context
workflow.batch.llm[for[0]] → "workflow_name.batch.__inner__.llm[for[0]]"
workflow.batch.llm[for[1]] → "workflow_name.batch.__inner__.llm[for[1]]"
```

---

### Multiple Streaming Nodes

```python
with WorkflowEngine(name="multi-stream") as workflow:
    llm1 = LLMNode(name="llm1", stream=True)
    llm2 = LLMNode(name="llm2", stream=True)
    
    START >> llm1 >> llm2 >> END

# Consume both streams
async for channel in STREAM_SERVICE.get_channels(request_id):
    print(f"\n=== {channel} ===")
    async for chunk in STREAM_SERVICE.get(request_id, channel):
        print(chunk.choices[0].delta.content, end="")
```

**Output:**
```
=== multi-stream.llm1[main] ===
First LLM output...

=== multi-stream.llm2[main] ===
Second LLM output...
```

---

### Streaming in Loops

```python
with ForLoopNode(name="batch") as loop:
    llm = LLMNode(name="processor", stream=True)
    START >> llm >> END

# Each iteration gets its own channel
# Channels: batch.__inner__.processor[for[0]]
#           batch.__inner__.processor[for[1]]
#           batch.__inner__.processor[for[2]]

async for channel in STREAM_SERVICE.get_channels(request_id):
    print(f"\n{channel}:")
    async for chunk in STREAM_SERVICE.get(request_id, channel):
        print(chunk.choices[0].delta.content, end="")
```

---

## 📊 Langfuse Tracing

### Why Observability?

Without tracing:
- ❌ Can't see what went wrong
- ❌ Don't know which node is slow
- ❌ No token usage tracking
- ❌ Hard to debug production issues

With Langfuse:
- ✅ Full execution trace
- ✅ Timing for every node
- ✅ Token usage and costs
- ✅ Error tracking with stack traces

---

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Workflow Execution                         │
│  Node A → Node B → Node C                               │
│  Record execution order and metrics                     │
└────────────────────┬────────────────────────────────────┘
                     │
                     ↓ Fire-and-forget flush
        ┌────────────────────────────┐
        │  WorkflowEngine.flush()    │
        │  (background task)         │
        └────────────────────────────┘
                     │
                     ↓ Build trace hierarchy
        ┌────────────────────────────┐
        │   Langfuse Trace Builder   │
        │  • Create Trace (root)     │
        │  • Add Spans (nodes)       │
        │  • Add Generations (LLMs)  │
        │  • Track metrics           │
        └────────────────────────────┘
                     │
                     ↓ Send to Langfuse
        ┌────────────────────────────┐
        │    Langfuse Dashboard      │
        │  • View traces             │
        │  • Track costs             │
        │  • Debug errors            │
        │  • Monitor performance     │
        └────────────────────────────┘
```

---

### Automatic Tracing

```python
# Just provide IDs - tracing happens automatically!
result = await workflow.run(
    inputs={"query": "Hello"},
    user_id="user_123",      # Track user
    session_id="session_456", # Track conversation
    request_id="req_789"     # Track request
)

# Traces automatically sent to Langfuse! ✨
# Check your Langfuse dashboard
```

---

### Trace Hierarchy

Beeflow creates the right Langfuse primitive for each node:

```
Trace (request_id: "req_789")
├─ user_id: "user_123"
├─ session_id: "session_456"
│
├─ Span: "prompt"
│   ├─ start_time: 10:00:00
│   ├─ end_time: 10:00:00.1
│   ├─ input: {"query": "Hello"}
│   └─ output: {"messages": [...]}
│
├─ Generation: "llm" ⭐ (LLM nodes)
│   ├─ model: "gpt-4o"
│   ├─ input: {"messages": [...]}
│   ├─ output: {"content": "Hi there!"}
│   ├─ usage:
│   │   ├─ prompt_tokens: 15
│   │   ├─ completion_tokens: 8
│   │   └─ total_tokens: 23
│   └─ cost: $0.00046 (auto-calculated)
│
└─ Span: "parser"
    ├─ input: {"text": "Hi there!"}
    └─ output: {"answer": "Hi there!"}
```

**Key Difference:**
- **Span** = Regular nodes (timing, I/O)
- **Generation** = LLM nodes (tokens, cost, model)

---

### Nested Traces

Nested graphs create nested spans:

```python
with GraphNode(name="rag") as rag:
    retriever = MilvusNode(...)
    reranker = RerankNode(...)
    START >> retriever >> reranker >> END

with WorkflowEngine(name="chatbot") as workflow:
    START >> rag >> answer >> END
```

**Langfuse hierarchy:**
```
Trace: "chatbot"
├─ Span: "rag"
│   ├─ Span: "rag.retriever"
│   └─ Span: "rag.reranker"
└─ Generation: "answer"
```

---

### Loop Traces

Each loop iteration gets its own span:

```python
with ForLoopNode(name="batch") as loop:
    processor = LLMNode(...)
    START >> processor >> END
```

**Langfuse hierarchy:**
```
Trace: "workflow"
└─ Span: "batch"
    ├─ Span: "batch[for[0]]"
    │   └─ Generation: "batch.__inner__.processor[for[0]]"
    ├─ Span: "batch[for[1]]"
    │   └─ Generation: "batch.__inner__.processor[for[1]]"
    └─ Span: "batch[for[2]]"
        └─ Generation: "batch.__inner__.processor[for[2]]"
```

---

## 🔍 Debugging with Traces

### Find Slow Nodes

**In Langfuse:**
1. Open your trace
2. Sort spans by duration
3. Identify bottleneck

```
Spans sorted by duration:
├─ llm: 2.5s ⚠️ (slowest!)
├─ retriever: 0.8s
├─ parser: 0.1s
└─ prompt: 0.01s

Action: Cache results or use faster model
```

---

### Track Token Usage

**Per request:**
```
Generation: "llm"
├─ model: "gpt-4o"
├─ usage:
│   ├─ prompt_tokens: 245
│   ├─ completion_tokens: 156
│   └─ total_tokens: 401
└─ cost: $0.0082
```

**Aggregate across sessions:**
```sql
-- In Langfuse dashboard
SELECT 
    user_id,
    SUM(total_tokens) as tokens,
    SUM(cost) as total_cost
FROM generations
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY user_id
ORDER BY total_cost DESC
```

---

### Debug Errors

**Error information captured:**
```
Span: "processor"
├─ level: "ERROR" ⚠️
├─ input: {"value": -5}
├─ output: null
└─ metadata:
    └─ error: "ValueError: Value must be positive!
                File 'workflow.py', line 42
                  result = process(value)
                ..."
```

**Full stack trace preserved for debugging!**

---

### Track User Sessions

```sql
-- Find all requests from a user
SELECT * FROM traces 
WHERE user_id = 'user_123'
ORDER BY timestamp DESC

-- Find error-prone sessions
SELECT session_id, COUNT(*) as errors
FROM traces
WHERE level = 'ERROR'
GROUP BY session_id
ORDER BY errors DESC
```

---

## 🎯 Best Practices

### 1. Always Provide IDs

```python
# ✅ Good - traceable
result = await workflow.run(
    inputs={...},
    user_id=get_current_user(),
    session_id=get_session_id(),
    request_id=generate_unique_id()
)

# ❌ Bad - can't trace back to user
result = await workflow.run(inputs={...})
```

---

### 2. Use Descriptive Node Names

```python
# ✅ Good - clear in traces
query_rewriter = BasicChainNode(name="query_rewriter", ...)
vector_search = MilvusNode(name="vector_search", ...)

# ❌ Bad - unclear in traces
node1 = BasicChainNode(name="node1", ...)
node2 = MilvusNode(name="node2", ...)
```

---

### 3. Monitor Token Usage

```python
# Set up cost alerts in Langfuse:
# - Alert if single request > $1
# - Alert if daily usage > $100
# - Track usage per user
```

---

### 4. Stream Long-Running Nodes

```python
# ✅ Good - immediate feedback
llm = LLMNode(stream=True)

# ⚠️ User waits with no feedback
llm = LLMNode(stream=False)
```

---

## 📊 Monitoring Checklist

### Development
- [ ] Test with streaming enabled
- [ ] Verify traces appear in Langfuse
- [ ] Check token usage estimates
- [ ] Test error scenarios

### Production
- [ ] User/session/request IDs implemented
- [ ] Token usage alerts configured
- [ ] Error notifications set up
- [ ] Performance baselines established
- [ ] Cost budgets defined

---

## 🚨 Common Issues

### Issue 1: Traces Not Appearing

**Possible causes:**
- Langfuse not configured in RESOURCE_HUB
- Network issues
- Invalid API keys

**Solution:**
> Contact Mr. Cương for Langfuse configuration

---

### Issue 2: Streaming Not Working

**Checks:**
```python
# 1. Is stream=True?
llm = LLMNode(stream=True)

# 2. Is Redis running?
# Contact Mr. Cương for Redis setup

# 3. Are you consuming the stream?
async for channel in STREAM_SERVICE.get_channels(request_id):
    async for chunk in STREAM_SERVICE.get(request_id, channel):
        print(chunk.choices[0].delta.content)
```

---

### Issue 3: High Costs

**Debug:**
1. Check Langfuse for top cost users
2. Identify nodes with high token usage
3. Look for repeated calls

**Solutions:**
```python
# Use cheaper models
quick = BasicChainNode(resource_key="gpt-4o-mini")

# Reduce prompt size
user_prompt="Brief answer: {query}"

# Cache results (implement at app level)
```

---

## 💡 Quick Reference

### Streaming Setup

```python
# 1. Enable on node
node = LLMNode(stream=True)

# 2. Start workflow
asyncio.create_task(workflow.run(..., request_id=req_id))

# 3. Consume stream
async for channel in STREAM_SERVICE.get_channels(req_id):
    async for chunk in STREAM_SERVICE.get(req_id, channel):
        print(chunk.choices[0].delta.content, end="")
```

### Tracing Setup

```python
# Just provide IDs!
result = await workflow.run(
    inputs={...},
    user_id="user_123",
    session_id="session_456",
    request_id="req_789"
)
# Traces automatic! ✨
```

---

## 📚 What's Next?

You've completed the core concepts! Now:

1. **Build Production Apps:**
   - [Tutorial 5: Production Deployment](../tutorials/05-production-deployment.md)
   - Apply observability in practice

2. **Explore Advanced Topics:**
   - [Performance Optimization](../advanced/performance-optimization.md)
   - [Custom Node Development](../advanced/custom-node-development.md)

3. **Study Examples:**
   - [Working Examples](../../examples/)
   - Real production patterns

---

## 💡 Key Takeaways

### Streaming
- **Enable:** Set `stream=True` on LLM nodes
- **Consume:** Use `STREAM_SERVICE.get_channels()` and `.get()`
- **Channels:** Named by node path and context
- **Benefit:** Real-time feedback to users

### Tracing
- **Automatic:** Just provide user/session/request IDs
- **Hierarchy:** Traces → Spans (nodes) → Generations (LLMs)
- **Metrics:** Token usage, costs, timing, errors
- **Benefit:** Full observability with zero code

### Production
- Always provide tracing IDs
- Use descriptive node names
- Monitor token usage and costs
- Stream long-running operations
- Set up alerts and budgets

---

**Congratulations! You now understand all core Beeflow concepts! 🎉**

Ready to build production applications with confidence! 🚀