# Tutorial 5: Production Deployment

**Deploy your workflow with observability and error handling**

⏱️ **Time:** ~60 minutes  
⭐ **Level:** Advanced  
🔧 **Focus:** Langfuse traces, error handling, streaming setup, debugging

---

## 🎯 What You'll Learn

How to take your workflow to production with:
- ✅ Automatic trace hierarchy in Langfuse
- ✅ Error handling and recovery patterns
- ✅ Redis streaming configuration
- ✅ Token usage and cost tracking
- ✅ Debugging production issues

**Note:** This tutorial covers the current production features in Beeflow. For advanced features like rate limiting, caching, or scaling, you'll need to implement them at the application/infrastructure level.

---

## 📚 Prerequisites

### ✅ Completed
- [Tutorial 1: Basic LLM Chain](01-basic-llm-chain.md)
- Understanding of any tutorial workflow

### ✅ System Requirements
- Langfuse account (for observability)
- Redis server (for streaming)
- Production LLM API key

> **📞 Setup Note:** For complete infrastructure and `RESOURCE_HUB` configuration, contact **Mr. Cương**.

---

## 🏗️ Architecture

### Production Workflow with Observability

```
┌─────────────────────────────────────────────────────────┐
│                User Request                             │
│  {user_id, session_id, request_id, inputs}              │
└────────────────────┬────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────┐
│  WorkflowEngine.run()                                   │
│  ┌───────────────────────────────────────────────────┐  │
│  │  1. Create WorkflowState with IDs                 │  │
│  │  2. Execute workflow nodes                        │  │
│  │  3. Track execution order                         │  │
│  │  4. Store errors in state                         │  │
│  │  5. Return results                                │  │
│  └───────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────┐
│  workflow.flush() - Fire & Forget                       │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Build Langfuse trace hierarchy:                  │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │  Trace (Root)                               │  │  │
│  │  │    ├─ Span (Node execution)                 │  │  │
│  │  │    ├─ Generation (LLM call)                 │  │  │
│  │  │    │    └─ Token usage                      │  │  │
│  │  │    ├─ Span (Another node)                   │  │  │
│  │  │    └─ Error tracking                        │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────┐
│              Langfuse Dashboard                         │
│  - View trace hierarchy                                 │
│  - Track token usage & costs                            │
│  - Debug errors                                         │
│  - Monitor performance                                  │
└─────────────────────────────────────────────────────────┘
```

---

## 💻 Step-by-Step Implementation

### Step 1: Basic Production Workflow

Start with a simple workflow that has production IDs:

```python
import asyncio
from beeflow import WorkflowEngine
from beeflow.nodes import BasicChainNode, START, END, INPUT, OUTPUT

async def main():
    with WorkflowEngine(name="production-chatbot") as workflow:
        
        chatbot = BasicChainNode(
            name="chatbot",
            resource_key="gpt-4o",
            user_prompt="You are a helpful assistant. Answer: {query}",
            inputs={"query": INPUT},
            outputs={"content": OUTPUT["answer"]},
            stream=True
        )
        
        START >> chatbot >> END
    
    workflow.compile()
    
    # Run with production IDs
    result = await workflow.run(
        inputs={"query": "What is Python?"},
        user_id="user_12345",           # Track which user
        session_id="session_67890",     # Track conversation
        request_id="req_abcdef"         # Track this specific request
    )
    
    print(f"Answer: {result['answer']}")
    # Traces automatically sent to Langfuse! ✨

if __name__ == "__main__":
    asyncio.run(main())
```

**What happens:**
1. Workflow executes normally
2. `workflow.flush()` runs in background (fire-and-forget)
3. Traces automatically sent to Langfuse
4. View in Langfuse dashboard

---

### Step 2: Understanding Trace Hierarchy

Beeflow automatically creates the right Langfuse primitive for each node:

```python
# Trace Hierarchy Created:
Trace (request_id: "req_abcdef")
├─ user_id: "user_12345"
├─ session_id: "session_67890"
│
├─ Span: "chatbot:prompt"
│   ├─ start_time: 2024-01-15 10:00:00
│   ├─ end_time: 2024-01-15 10:00:00.1
│   ├─ input: {"query": "What is Python?"}
│   └─ output: {"messages": [...]}
│
├─ Generation: "chatbot:llm"  ⭐ (LLM nodes use Generation)
│   ├─ model: "gpt-4o"
│   ├─ input: {"messages": [...]}
│   ├─ output: {"content": "Python is..."}
│   ├─ usage:
│   │   ├─ prompt_tokens: 15
│   │   ├─ completion_tokens: 42
│   │   └─ total_tokens: 57
│   └─ cost: $0.0012  (calculated by Langfuse)
│
└─ Span: "chatbot:parser"
    ├─ input: {"text": "Python is..."}
    └─ output: {"answer": "Python is..."}
```

**Key Differences:**
- **Generation** = LLM nodes (tracks tokens, model, costs)
- **Span** = All other nodes (tracks timing, I/O)

---

### Step 3: Error Handling

Errors are automatically tracked in state and Langfuse:

```python
from beeflow.nodes import CodeNode

def risky_operation(value: int) -> dict:
    """Function that might fail"""
    if value < 0:
        raise ValueError("Value must be positive!")
    return {"result": value * 2}

async def main():
    with WorkflowEngine(name="error-handling-demo") as workflow:
        
        processor = CodeNode(
            name="processor",
            code_fn=risky_operation,
            inputs={"value": INPUT}
        )
        
        chatbot = BasicChainNode(
            name="chatbot",
            resource_key="gpt-4o",
            user_prompt="Process this: {result}",
            inputs={"result": processor},
            outputs=OUTPUT
        )
        
        START >> processor >> chatbot >> END
    
    workflow.compile()
    
    # This will fail
    try:
        result = await workflow.run(
            inputs={"value": -5},
            request_id="req_error_test"
        )
    except Exception as e:
        print(f"Workflow failed: {e}")
        # Error is still tracked in Langfuse! ✅

# Check Langfuse dashboard:
# - Trace shows error at "processor" node
# - Full stack trace captured
# - Subsequent nodes didn't execute
```

**Error Information in Langfuse:**
```
Span: "processor"
├─ level: "ERROR"  ⚠️
├─ input: {"value": -5}
├─ output: null
└─ metadata:
    └─ error: "ValueError: Value must be positive!\n  File..."
```

---

### Step 4: Graceful Error Recovery

Handle errors gracefully with try-catch in your functions:

```python
def safe_operation(value: int) -> dict:
    """Operation with error handling"""
    try:
        if value < 0:
            raise ValueError("Negative value")
        result = value * 2
        return {
            "result": result,
            "success": True,
            "error": None
        }
    except Exception as e:
        return {
            "result": None,
            "success": False,
            "error": str(e)
        }

# Use in workflow
with WorkflowEngine(name="graceful-errors") as workflow:
    processor = CodeNode(
        name="processor",
        code_fn=safe_operation,
        inputs={"value": INPUT}
    )
    
    # Check if processing succeeded
    checker = BranchNode(
        name="check_success",
        cases={"success == True": "chatbot"},
        default="error_handler",
        inputs={"success": processor}
    )
    
    chatbot = BasicChainNode(...)  # Normal path
    
    error_handler = BasicChainNode(
        name="error_handler",
        user_prompt="Apologize for error: {error}",
        inputs={"error": processor}
    )
    
    START >> processor >> checker >> [chatbot, error_handler] >> END
```

---

### Step 5: Streaming Setup

Redis streaming is already configured in your workflow:

```python
async def streaming_workflow():
    with WorkflowEngine(name="streaming-chat") as workflow:
        chatbot = BasicChainNode(
            resource_key="gpt-4o",
            user_prompt="Answer: {query}",
            inputs=INPUT,
            outputs=OUTPUT,
            stream=True  # ✨ Enable streaming
        )
        
        START >> chatbot >> END
    
    workflow.compile()
    
    # Start workflow (non-blocking)
    request_id = "req_stream_123"
    asyncio.create_task(workflow.run(
        inputs={"query": "Explain quantum computing"},
        request_id=request_id
    ))
    
    # Consume stream
    from beeflow.utils.streaming import STREAM_SERVICE
    
    print("Answer: ", end="")
    async for channel in STREAM_SERVICE.get_channels(request_id):
        async for chunk in STREAM_SERVICE.get(request_id, channel):
            content = chunk.choices[0].delta.content
            if content:
                print(content, end="", flush=True)
    print()

if __name__ == "__main__":
    asyncio.run(streaming_workflow())
```

**Streaming Channels in Langfuse:**
Each streaming node creates a channel: `workflow_name.node_name[context_id]`

---

### Step 6: Token Usage Tracking

LLM nodes automatically track token usage:

```python
# After running workflow, check Langfuse:
Generation: "chatbot:llm"
├─ model: "gpt-4o"
├─ usage:
│   ├─ prompt_tokens: 245
│   ├─ completion_tokens: 156
│   └─ total_tokens: 401
├─ cost: $0.0082  (auto-calculated)
└─ latency: 1.2s

# Access programmatically:
state = workflow_state
token_usage = state["chatbot.llm", "usage", None]
print(f"Tokens: {token_usage['total_tokens']}")
print(f"Cost: ${token_usage['total_tokens'] * 0.00002:.4f}")  # Estimate
```

---

## 🔍 Debugging Production Issues

### Issue 1: Find Slow Nodes

**Langfuse Dashboard:**
1. Go to your trace
2. Sort spans by duration
3. Identify bottlenecks

```
Spans by Duration:
├─ llm: 2.5s  ⚠️ (slowest)
├─ retriever: 0.8s
├─ parser: 0.1s
└─ prompt: 0.01s

Action: Consider caching LLM results or using faster model
```

### Issue 2: Track User Sessions

**Query Langfuse:**
```python
# Find all requests from a user
SELECT * FROM traces 
WHERE user_id = 'user_12345' 
ORDER BY timestamp DESC;

# Find problematic sessions
SELECT session_id, COUNT(*) as errors
FROM traces 
WHERE level = 'ERROR'
GROUP BY session_id
ORDER BY errors DESC;
```

### Issue 3: Debug Context Issues (ForLoopNode)

**In Langfuse, each loop iteration is separate:**
```
Trace: "batch-processor"
├─ Span: "batch_processor[for[0]]"  ⭐ Context 0
│   └─ Generation: "batch_processor.__inner__.llm[for[0]]"
├─ Span: "batch_processor[for[1]]"  ⭐ Context 1
│   └─ Generation: "batch_processor.__inner__.llm[for[1]]"
└─ Span: "batch_processor[for[2]]"  ⭐ Context 2
    └─ Generation: "batch_processor.__inner__.llm[for[2]]"

# Each context tracked separately!
```

---

## 🚨 Common Production Issues

### Issue 1: Traces not appearing in Langfuse

**Possible Causes:**
1. Langfuse not configured in `RESOURCE_HUB`
2. Network issues
3. Invalid API keys

**Solution:**
> **📞 Contact Mr. Cương** to verify Langfuse configuration in `RESOURCE_HUB`.

Check if traces are queued:
```python
# Traces sent asynchronously, may take a few seconds
await asyncio.sleep(5)  # Wait for flush to complete
```

---

### Issue 2: High token costs

**Symptom:**
Bill is higher than expected.

**Debug:**
1. Check Langfuse for token usage per trace
2. Identify nodes using most tokens
3. Look for repeated calls

**Solutions:**
```python
# 1. Use cheaper models for simple tasks
quick_scan = BasicChainNode(
    resource_key="gpt-4o-mini",  # Cheaper
    ...
)

# 2. Reduce prompt size
user_prompt="Answer briefly: {query}"  # vs long prompt

# 3. Cache results (implement at app level)
```

---

### Issue 3: Streaming not working

**Symptom:**
No real-time output.

**Checks:**
```python
# 1. Is Redis running?
# 2. Is stream=True set?
llm = LLMNode(stream=True, ...)

# 3. Are you consuming the stream?
from beeflow.utils.streaming import STREAM_SERVICE
async for channel in STREAM_SERVICE.get_channels(request_id):
    ...
```

> **📞 For Redis setup issues:** Contact **Mr. Cương**.

---

## 💡 Best Practices

### 1. Always Use Production IDs

```python
# ✅ Good
result = await workflow.run(
    inputs={...},
    user_id=get_current_user_id(),
    session_id=get_session_id(),
    request_id=generate_unique_id()
)

# ❌ Bad
result = await workflow.run(inputs={...})  # Missing IDs
```

### 2. Monitor Token Usage

```python
# Track costs per user
SELECT user_id, SUM(total_tokens) as tokens
FROM generations
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY user_id
ORDER BY tokens DESC;
```

### 3. Error Context

```python
# Include helpful context in errors
def process_data(data: dict) -> dict:
    try:
        result = risky_operation(data)
        return {"result": result, "success": True}
    except Exception as e:
        return {
            "result": None,
            "success": False,
            "error": str(e),
            "data_id": data.get("id", "unknown"),  # ✅ Context
            "timestamp": datetime.now().isoformat()
        }
```

### 4. Graceful Degradation

```python
# Fallback to simpler model on error
try:
    result = await expensive_model.run(...)
except Exception as e:
    logger.warning(f"Primary model failed: {e}")
    result = await fallback_model.run(...)  # Cheaper/faster
```

---

## 🚀 Production Checklist

Before deploying to production:

### Infrastructure
- [ ] Redis server running and accessible
- [ ] Langfuse account created and configured
- [ ] LLM API keys valid and funded
- [ ] Database connections stable (Milvus, MongoDB if using RAG)

### Code
- [ ] Error handling in all custom functions
- [ ] Production IDs (user_id, session_id, request_id) implemented
- [ ] Streaming enabled where needed
- [ ] Resource keys correct (refer to Mr. Cương's setup)

### Monitoring
- [ ] Langfuse dashboard accessible
- [ ] Token usage alerts configured
- [ ] Error notifications set up (external tool)
- [ ] Performance baselines established

### Testing
- [ ] Tested with production-like data
- [ ] Load tested with expected concurrency
- [ ] Error scenarios tested
- [ ] Streaming tested end-to-end

> **📞 For production deployment assistance:** Contact **Mr. Cương** for infrastructure setup, scaling considerations, and configuration best practices.

---

## 📚 What's Next?

You've completed all tutorials! 🎉 Now you can:

1. **Build Real Applications**
   - Combine patterns (RAG + Agent + Batch)
   - Deploy to production
   - Monitor and optimize

2. **Deep Dive into Architecture**
   - [Architecture Overview](../concepts/architecture-overview.md)
   - [State Management](../concepts/state-management.md)
   - [Execution Model](../concepts/execution-model.md)

3. **Advanced Topics** (Coming soon)
   - [Custom Node Development](../advanced/custom-node-development.md)
   - [Performance Optimization](../advanced/performance-optimization.md)
   - [Internals](../advanced/internals-state-indexer.md)

4. **Explore Examples**
   - [Complete Examples](../../examples/)
   - Real-world use cases
   - Production patterns

---

## 💡 Key Takeaways

### ✅ What You Learned
1. **Langfuse Integration** - Automatic trace hierarchy
2. **Trace Primitives** - Generations (LLM) vs Spans (other nodes)
3. **Error Handling** - Tracked in state and Langfuse
4. **Streaming** - Redis-based real-time output
5. **Token Tracking** - Automatic usage monitoring
6. **Production IDs** - User, session, request tracking

### ✅ Production Features Available
- ✅ Automatic observability with Langfuse
- ✅ Error tracking and debugging
- ✅ Token usage and cost monitoring
- ✅ Real-time streaming via Redis
- ✅ Context-aware tracing (loop iterations)
- ✅ User/session/request tracking

### ✅ What Requires External Implementation
- Rate limiting (use API gateway or application logic)
- Caching (implement with Redis at app level)
- Horizontal scaling (use load balancers)
- Advanced monitoring (integrate external APM tools)
- Cost alerts (use Langfuse or custom dashboards)

---

**🎉 Congratulations on completing all Beeflow tutorials!**

You now have the knowledge to build production-grade AI applications with Beeflow. Happy building! 🚀

---

## 📝 Complete Production Example

```python
import asyncio
from beeflow import WorkflowEngine
from beeflow.nodes import BasicChainNode, START, END, INPUT, OUTPUT

async def production_chatbot():
    """Production-ready chatbot with full observability"""
    
    with WorkflowEngine(
        name="production-chatbot",
        langfuse="beegen"  # Langfuse key in RESOURCE_HUB
    ) as workflow:
        
        chatbot = BasicChainNode(
            name="chatbot",
            resource_key="gpt-4o",
            system_prompt="You are a helpful customer service assistant.",
            user_prompt="{query}",
            inputs={"query": INPUT},
            outputs={"content": OUTPUT["answer"]},
            stream=True
        )
        
        START >> chatbot >> END
    
    workflow.compile()
    
    # Run with production IDs
    result = await workflow.run(
        inputs={"query": "How do I reset my password?"},
        user_id="user_abc123",
        session_id="session_xyz789",
        request_id="req_unique_id"
    )
    
    return result

if __name__ == "__main__":
    result = asyncio.run(production_chatbot())
    print(f"Answer: {result['answer']}")
    # Check Langfuse dashboard for traces! ✨
```

---

**Happy deploying! 🚀**