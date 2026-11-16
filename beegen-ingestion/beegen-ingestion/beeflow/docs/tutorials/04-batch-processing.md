# Tutorial 4: Batch Processing

**Process multiple items in parallel with context isolation and streaming**

⏱️ **Time:** ~40 minutes  
⭐ **Level:** Intermediate  
🔧 **Nodes:** `ForLoopNode`, `CodeNode`, `BasicChainNode`, `BranchNode`

---

## 🎯 What You'll Build

A batch processing workflow that:
- Takes a list of items (e.g., 100 product reviews)
- Processes each item independently in parallel
- Maintains context isolation (no data conflicts)
- Streams results in real-time from multiple executions
- Aggregates all results into a list

**Input:**
```python
{
    "batch_data": [
        {"review": "Great product!", "product_id": 1},
        {"review": "Terrible quality", "product_id": 2},
        {"review": "It's okay", "product_id": 3},
        # ... 97 more reviews
    ]
}
```

**Process:**
```
Parallel Execution:
  Task[0] → Analyze review #1 → Result #1
  Task[1] → Analyze review #2 → Result #2
  Task[2] → Analyze review #3 → Result #3
  ... all running simultaneously ...
  Task[99] → Analyze review #100 → Result #100
```

**Output:**
```python
{
    "batch_result": [
        {"product_id": 1, "sentiment": "positive", "score": 0.95},
        {"product_id": 2, "sentiment": "negative", "score": 0.12},
        {"product_id": 3, "sentiment": "neutral", "score": 0.55},
        # ... 97 more results
    ]
}
```

---

## 📚 Prerequisites

### ✅ Completed
- [Tutorial 1: Basic LLM Chain](01-basic-llm-chain.md)
- [Quickstart Guide](../quickstart.md)

### ✅ Knowledge
- Understanding of async/await
- Basic list comprehensions
- Familiarity with parallel execution concepts

### ✅ System Requirements
- Python 3.9+
- LLM API key
- Redis (for streaming)
- Beeflow installed: `pip install beeflow`

> **📞 Setup Note:** For `RESOURCE_HUB` configuration, contact **Mr. Cương**.

---

## 🏗️ Architecture

### High-Level Overview

```
┌────────────────────────────────────────────────────────────┐
│              Batch Input (List of Items)                   │
│  [item1, item2, item3, ..., item100]                       │
└────────────────────┬───────────────────────────────────────┘
                     │
                     ↓
┌────────────────────────────────────────────────────────────┐
│  ForLoopNode: "batch_processor"                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  Internal Graph (executed for each item)            │ │
│  │  ┌────────────────────────────────────────────────┐ │ │
│  │  │  PromptNode → LLMNode → ParserNode → Output   │ │ │
│  │  └────────────────────────────────────────────────┘ │ │
│  │                                                      │ │
│  │  Parallel Execution:                                │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │ │
│  │  │ Task for[0]  │  │ Task for[1]  │  │  for[2]  │ │ │
│  │  │ item1        │  │ item2        │  │  item3   │ │ │
│  │  │ context_id:  │  │ context_id:  │  │ context  │ │ │
│  │  │ "for[0]"     │  │ "for[1]"     │  │ "for[2]" │ │ │
│  │  └──────────────┘  └──────────────┘  └──────────┘ │ │
│  │         ↓                  ↓                ↓       │ │
│  │    result[0]          result[1]        result[2]   │ │
│  │                                                      │ │
│  │  asyncio.gather(*all_tasks) → [r0, r1, r2, ...]   │ │
│  └──────────────────────────────────────────────────────┘ │
└────────────────────┬───────────────────────────────────────┘
                     │
                     ↓
┌────────────────────────────────────────────────────────────┐
│           Batch Results (List, Same Order)                 │
│  [result1, result2, result3, ..., result100]               │
└────────────────────────────────────────────────────────────┘
```

### Key Concepts

1. **Context Isolation**: Each iteration gets unique `context_id = f"for[{i}]"`
2. **Parallel Execution**: All tasks run simultaneously with `asyncio.gather`
3. **Order Preservation**: Results returned in same order as input
4. **Streaming**: Each task can stream independently
5. **State Management**: Variables tracked per context

---

## 💻 Step-by-Step Implementation

### Step 1: Simple Batch Processing

Let's start with a simple example - analyzing multiple reviews:

```python
import asyncio
from beeflow import WorkflowEngine
from beeflow.nodes import (
    ForLoopNode,
    PromptNode,
    LLMNode,
    ParserNode,
    START,
    END,
    INPUT,
    OUTPUT
)

# Define the review analysis prompt
REVIEW_PROMPT = """Analyze this product review:

Review: {review}
Product ID: {product_id}

Return analysis in XML format:
<sentiment>positive/negative/neutral</sentiment>
<score>0.0 to 1.0</score>
<key_points>Brief summary of key points</key_points>"""

async def main():
    with WorkflowEngine(name="batch-review-analyzer") as workflow:
        
        # ForLoopNode with internal graph
        with ForLoopNode(
            name="batch_processor",
            inputs={"batch_data": INPUT}  # Takes list of items
        ) as batch:
            
            # Define processing for EACH item
            prompt = PromptNode(
                name="prompt",
                user_prompt=REVIEW_PROMPT,
                inputs=INPUT  # Gets individual item from batch
            )
            
            llm = LLMNode(
                name="llm",
                resource_key="gpt-4o",
                inputs={"messages": prompt}
            )
            
            parser = ParserNode(
                name="parser",
                format="xml",
                extract_schema=[
                    "sentiment: str",
                    "score: float",
                    "key_points: str"
                ],
                inputs={"text": llm["content"]},
                outputs=OUTPUT  # Each item's output
            )
            
            # Define flow INSIDE the loop
            START >> prompt >> llm >> parser >> END
        
        # Build the ForLoopNode
        batch.build()
        
        # Simple workflow: just the batch processor
        START >> batch >> END
    
    workflow.compile()
    
    # Test with sample data
    sample_reviews = [
        {"review": "Excellent product! Highly recommend.", "product_id": 1},
        {"review": "Broke after one day. Waste of money.", "product_id": 2},
        {"review": "It's okay, nothing special.", "product_id": 3},
    ]
    
    result = await workflow.run(
        inputs={"batch_data": sample_reviews}
    )
    
    print("Batch Results:")
    for i, analysis in enumerate(result["batch_result"]):
        print(f"\nReview {i+1}:")
        print(f"  Sentiment: {analysis['sentiment']}")
        print(f"  Score: {analysis['score']}")
        print(f"  Key Points: {analysis['key_points']}")

if __name__ == "__main__":
    asyncio.run(main())
```

**What happens internally:**

```python
# ForLoopNode execution
batch_data = [item1, item2, item3]

# Create parallel tasks
tasks = []
for i, item in enumerate(batch_data):
    context_id = f"for[{i}]"  # Unique context
    
    # Inject item into state with context
    state.inject_inputs(
        node="batch_processor.__inner__",
        inputs=item,  # {review: "...", product_id: 1}
        context_id=context_id
    )
    
    # Run internal graph with this context
    task = self._graph.run(state, context_id)
    tasks.append(task)

# Execute all in parallel
results = await asyncio.gather(*tasks)
# Returns: [result0, result1, result2] in same order
```

---

### Step 2: Understanding Context Isolation

Each iteration has its own isolated context:

```python
# During execution:
State Storage:
┌─────────────────────────────────────────────────────────┐
│ Context: "for[0]" (Review #1)                           │
│   prompt.review = "Excellent product!"                  │
│   llm.content = "<sentiment>positive</sentiment>..."    │
│   parser.sentiment = "positive"                         │
├─────────────────────────────────────────────────────────┤
│ Context: "for[1]" (Review #2)                           │
│   prompt.review = "Broke after one day"                 │
│   llm.content = "<sentiment>negative</sentiment>..."    │
│   parser.sentiment = "negative"                         │
├─────────────────────────────────────────────────────────┤
│ Context: "for[2]" (Review #3)                           │
│   prompt.review = "It's okay"                           │
│   llm.content = "<sentiment>neutral</sentiment>..."     │
│   parser.sentiment = "neutral"                          │
└─────────────────────────────────────────────────────────┘
```

**No data conflicts!** Each context tracks its own variables independently.

---

### Step 3: Pre-Processing and Post-Processing

Often you need to prepare data before batch processing and aggregate after:

```python
from beeflow.nodes import CodeNode

def prepare_batch(reviews: list) -> dict:
    """Convert reviews to batch_data format"""
    batch_data = []
    for i, review in enumerate(reviews):
        batch_data.append({
            "review": review["text"],
            "product_id": review["id"],
            "timestamp": review.get("timestamp", "unknown")
        })
    return {"batch_data": batch_data}


def aggregate_results(batch_result: list) -> dict:
    """Aggregate batch results into summary"""
    total = len(batch_result)
    positive = sum(1 for r in batch_result if r["sentiment"] == "positive")
    negative = sum(1 for r in batch_result if r["sentiment"] == "negative")
    neutral = total - positive - negative
    
    avg_score = sum(r["score"] for r in batch_result) / total if total > 0 else 0
    
    return {
        "summary": {
            "total_reviews": total,
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
            "average_score": avg_score
        },
        "detailed_results": batch_result
    }


async def main():
    with WorkflowEngine(name="batch-with-aggregation") as workflow:
        
        # Pre-process: Prepare data
        preprocessor = CodeNode(
            name="prepare",
            code_fn=prepare_batch,
            inputs={"reviews": INPUT}
        )
        
        # Batch process
        with ForLoopNode(
            name="batch_processor",
            inputs={"batch_data": preprocessor}
        ) as batch:
            # ... internal graph (same as before) ...
            prompt = PromptNode(...)
            llm = LLMNode(...)
            parser = ParserNode(...)
            START >> prompt >> llm >> parser >> END
        
        batch.build()
        
        # Post-process: Aggregate results
        aggregator = CodeNode(
            name="aggregate",
            code_fn=aggregate_results,
            inputs={"batch_result": batch},
            outputs=OUTPUT
        )
        
        # Complete flow
        START >> preprocessor >> batch >> aggregator >> END
    
    workflow.compile()
    
    result = await workflow.run(inputs={"reviews": raw_reviews})
    
    print("Summary:", result["summary"])
```

---

### Step 4: Adding Streaming

Watch results stream in real-time from all parallel tasks:

```python
async def main_with_streaming():
    with WorkflowEngine(name="streaming-batch") as workflow:
        
        with ForLoopNode(
            name="batch_processor",
            inputs={"batch_data": INPUT}
        ) as batch:
            prompt = PromptNode(...)
            
            llm = LLMNode(
                name="llm",
                resource_key="gpt-4o",
                inputs={"messages": prompt},
                stream=True  # ✨ Enable streaming
            )
            
            parser = ParserNode(...)
            
            START >> prompt >> llm >> parser >> END
        
        batch.build()
        START >> batch >> END
    
    workflow.compile()
    
    # Start processing (non-blocking)
    request_id = "req_batch_123"
    asyncio.create_task(workflow.run(
        inputs={"batch_data": sample_reviews},
        request_id=request_id
    ))
    
    # Stream from ALL parallel tasks
    from beeflow.utils.streaming import STREAM_SERVICE
    
    print("Streaming from parallel executions:")
    
    async for channel in STREAM_SERVICE.get_channels(request_id):
        print(f"\n--- Channel: {channel} ---")
        async for chunk in STREAM_SERVICE.get(request_id, channel):
            content = chunk.choices[0].delta.content
            if content:
                print(content, end="", flush=True)
        print()

if __name__ == "__main__":
    asyncio.run(main_with_streaming())
```

**Output:**
```
Streaming from parallel executions:

--- Channel: batch_processor.__inner__.llm[for[0]] ---
The review expresses strong positive sentiment...

--- Channel: batch_processor.__inner__.llm[for[1]] ---
This review shows clear negative sentiment...

--- Channel: batch_processor.__inner__.llm[for[2]] ---
The review indicates a neutral stance...
```

Each task streams independently! 🎉

---

### Step 5: Conditional Processing with BranchNode

Process items differently based on conditions:

```python
with WorkflowEngine(name="conditional-batch") as workflow:
    
    with ForLoopNode(
        name="batch_processor",
        inputs={"batch_data": INPUT}
    ) as batch:
        
        # Initial quick analysis
        quick_scan = BasicChainNode(
            name="quick_scan",
            resource_key="gpt-4o-mini",  # Faster, cheaper model
            user_prompt="Rate sentiment 1-5: {review}",
            extract_schema=["rating: int"],
            inputs=INPUT
        )
        
        # Branch based on rating
        router = BranchNode(
            name="router",
            cases={
                "rating <= 2": "negative_handler",
                "rating >= 4": "positive_handler"
            },
            default="neutral_handler",
            inputs={"rating": quick_scan}
        )
        
        # Different handlers for different sentiments
        negative_handler = BasicChainNode(
            name="negative_handler",
            user_prompt="Deep analysis of negative review: {review}",
            extract_schema=["issues: list", "severity: str"],
            inputs=INPUT,
            outputs=OUTPUT
        )
        
        positive_handler = BasicChainNode(
            name="positive_handler",
            user_prompt="Extract highlights: {review}",
            extract_schema=["highlights: list"],
            inputs=INPUT,
            outputs=OUTPUT
        )
        
        neutral_handler = BasicChainNode(
            name="neutral_handler",
            user_prompt="Standard analysis: {review}",
            extract_schema=["summary: str"],
            inputs=INPUT,
            outputs=OUTPUT
        )
        
        # Flow
        START >> quick_scan >> router >> [
            negative_handler,
            positive_handler,
            neutral_handler
        ] >> END
    
    batch.build()
    START >> batch >> END
```

---

## 🔍 Performance Characteristics

### Execution Time Comparison

**Sequential Processing** (traditional):
```python
results = []
for item in batch_data:  # One at a time
    result = await process_item(item)
    results.append(result)

# Time: N * T (where N=items, T=time per item)
# Example: 100 items * 2s each = 200 seconds
```

**Parallel Processing** (ForLoopNode):
```python
with ForLoopNode(...) as batch:
    # All items process simultaneously
    pass

# Time: T (longest individual task)
# Example: 100 items in ~2 seconds (fastest finishes in 2s)
```

**Speedup:** ~100x for embarrassingly parallel tasks! 🚀

### Memory Usage

```python
# Each context maintains its own variables
Memory = Base + (N * Variables_Per_Context)

# Example:
# - Base workflow: 1MB
# - 100 items × 10KB per context = 1MB
# - Total: ~2MB

# Very efficient! No data duplication due to zero-copy indexing
```

---

## 🧪 Testing Your Batch Workflow

### Test Case 1: Small Batch

```python
small_batch = [
    {"review": "Great!", "product_id": 1},
    {"review": "Terrible!", "product_id": 2},
]

result = await workflow.run(inputs={"batch_data": small_batch})

assert len(result["batch_result"]) == 2
assert result["batch_result"][0]["product_id"] == 1
assert result["batch_result"][1]["product_id"] == 2
```

### Test Case 2: Empty Batch

```python
result = await workflow.run(inputs={"batch_data": []})
assert result["batch_result"] == []
```

### Test Case 3: Large Batch

```python
# Generate 1000 reviews
large_batch = [
    {"review": f"Review #{i}", "product_id": i}
    for i in range(1000)
]

import time
start = time.time()
result = await workflow.run(inputs={"batch_data": large_batch})
duration = time.time() - start

print(f"Processed {len(large_batch)} items in {duration:.2f}s")
# Expected: ~2-5 seconds (vs 2000s sequential!)
```

### Test Case 4: Error Handling

```python
# One item causes error
batch_with_error = [
    {"review": "Good", "product_id": 1},
    {"review": None, "product_id": 2},  # Will cause error
    {"review": "Bad", "product_id": 3},
]

result = await workflow.run(inputs={"batch_data": batch_with_error})

# Other items still process successfully
assert result["batch_result"][0] is not None
assert result["batch_result"][2] is not None
# Item 2 might have error, but doesn't block others
```

---

## 🚨 Troubleshooting

### Issue 1: Out of order results

**Symptom:**
Results don't match input order.

**Cause:**
Using wrong collection method.

**Solution:**
ForLoopNode automatically uses `asyncio.gather` which preserves order. Results will always match input order, even if tasks complete at different times.

```python
# This is handled automatically:
results = await asyncio.gather(*tasks)  # Preserves order ✅
```

---

### Issue 2: Context data conflicts

**Symptom:**
Items getting mixed data from other items.

**Cause:**
Not using proper context isolation.

**Solution:**
ForLoopNode automatically creates unique context IDs (`for[i]`). Make sure you're not accessing global state outside the loop.

```python
# ❌ Don't do this
global_cache = {}

def process(item):
    global_cache[item["id"]] = item  # Race condition!

# ✅ Do this - return data, don't use global state
def process(item):
    return {"id": item["id"], "result": ...}
```

---

### Issue 3: Memory issues with large batches

**Symptom:**
```
MemoryError: Cannot allocate memory
```

**Cause:**
Processing too many items simultaneously.

**Solution:**
Break into smaller batches:

```python
def chunk_list(data, chunk_size):
    """Split list into chunks"""
    for i in range(0, len(data), chunk_size):
        yield data[i:i + chunk_size]

# Process in chunks of 100
all_results = []
for chunk in chunk_list(large_data, 100):
    result = await workflow.run(inputs={"batch_data": chunk})
    all_results.extend(result["batch_result"])
```

---

### Issue 4: Slow performance

**Symptom:**
Batch processing not much faster than sequential.

**Possible Causes:**
1. Bottleneck in shared resource (database, API rate limit)
2. Too few items to benefit from parallelism
3. CPU-bound tasks (not I/O bound)

**Solutions:**
```python
# 1. Add rate limiting for shared resources
import asyncio

async def rate_limited_call(item):
    async with rate_limiter:  # Semaphore
        return await process(item)

# 2. Use batch processing only for I/O-bound tasks
# (LLM calls, database queries, API calls)

# 3. For CPU-bound tasks, use ProcessPoolExecutor instead
from concurrent.futures import ProcessPoolExecutor

with ProcessPoolExecutor() as executor:
    results = await loop.run_in_executor(
        executor, 
        cpu_intensive_function, 
        data
    )
```

---

## 🚀 Enhancements & Next Steps

### Enhancement 1: Dynamic Batch Sizing

Adjust batch size based on system load:

```python
def adaptive_batch_size(data, max_batch=100):
    """Dynamically determine optimal batch size"""
    import psutil
    
    memory_usage = psutil.virtual_memory().percent
    if memory_usage > 80:
        return min(10, len(data))  # Small batch
    elif memory_usage > 60:
        return min(50, len(data))  # Medium batch
    else:
        return min(max_batch, len(data))  # Full batch
```

### Enhancement 2: Progress Tracking

Track batch progress:

```python
from tqdm.asyncio import tqdm

async def batch_with_progress(workflow, batch_data):
    """Run batch with progress bar"""
    results = []
    
    for chunk in tqdm(
        chunk_list(batch_data, 100),
        total=len(batch_data)//100,
        desc="Processing batches"
    ):
        result = await workflow.run(inputs={"batch_data": chunk})
        results.extend(result["batch_result"])
    
    return results
```

### Enhancement 3: Retry Failed Items

Retry items that failed:

```python
def separate_results(batch_result):
    """Separate successful and failed results"""
    success = []
    failed = []
    
    for i, result in enumerate(batch_result):
        if result.get("error"):
            failed.append((i, result))
        else:
            success.append(result)
    
    return success, failed

# Retry failed items
success, failed = separate_results(result["batch_result"])

if failed:
    print(f"Retrying {len(failed)} failed items...")
    retry_data = [original_batch[i] for i, _ in failed]
    retry_result = await workflow.run(inputs={"batch_data": retry_data})
    success.extend(retry_result["batch_result"])
```

### Enhancement 4: Nested Batch Processing

Process batches of batches:

```python
with WorkflowEngine(name="nested-batch") as workflow:
    
    # Outer loop: Process each category
    with ForLoopNode(name="category_loop", inputs=INPUT) as outer:
        
        # Inner loop: Process items in category
        with ForLoopNode(name="item_loop", inputs=INPUT) as inner:
            processor = BasicChainNode(...)
            START >> processor >> END
        
        inner.build()
        START >> inner >> END
    
    outer.build()
    START >> outer >> END
```

---

## 💡 Key Takeaways

Congratulations! You've mastered batch processing with Beeflow. Here's what you learned:

### ✅ Core Concepts
1. **ForLoopNode** - Parallel iteration over lists
2. **Context Isolation** - Each item has unique context_id
3. **Parallel Execution** - All tasks run simultaneously
4. **Order Preservation** - Results match input order
5. **Streaming** - Real-time output from all tasks

### ✅ Best Practices
- ✅ Use ForLoopNode for I/O-bound tasks (LLM, DB, API)
- ✅ Pre-process data before batch
- ✅ Aggregate results after batch
- ✅ Handle errors gracefully per item
- ✅ Monitor memory usage for large batches
- ✅ Use streaming for better UX

### ✅ Performance Tips
- 🚀 **100x+ speedup** for embarrassingly parallel tasks
- 💾 **Memory efficient** due to zero-copy indexing
- 📊 **Monitor**: Track individual task performance
- ⚖️ **Balance**: Batch size vs memory usage
- 🔄 **Retry**: Separate failed items and retry

### ✅ When to Use ForLoopNode
- ✅ Processing multiple similar items
- ✅ Each item is independent
- ✅ I/O-bound operations (LLM, DB, API)
- ✅ Need to preserve order
- ✅ Want streaming from all tasks

### ✅ When NOT to Use
- ❌ Items depend on each other
- ❌ Sequential processing required
- ❌ CPU-bound tasks (use ProcessPoolExecutor)
- ❌ Very large batches (chunk them first)

---

## 📚 What's Next?

Now that you can process data at scale, you can:

1. **Tutorial 5: Production Deployment** - Deploy with full observability
   - Monitor batch performance with Langfuse
   - Track token usage across parallel tasks
   - Debug context-specific issues
   - Handle production errors

2. **Combine Patterns** - Mix batch + agent + RAG
   - Batch process user queries
   - Each uses RAG for context
   - Agent handles complex items
   
3. **Explore Advanced Patterns** - Check the [Guides](../guides/)
   - Dynamic batch sizing
   - Priority queues
   - Graceful degradation
   - Cost optimization

---

## 📝 Complete Code

Here's the full batch processing workflow:

```python
import asyncio
from beeflow import WorkflowEngine
from beeflow.nodes import (
    ForLoopNode,
    PromptNode,
    LLMNode,
    ParserNode,
    CodeNode,
    START,
    END,
    INPUT,
    OUTPUT
)

REVIEW_PROMPT = """Analyze this product review:

Review: {review}
Product ID: {product_id}

Return in XML:
<sentiment>positive/negative/neutral</sentiment>
<score>0.0 to 1.0</score>
<key_points>Brief summary</key_points>"""

def aggregate_results(batch_result):
    """Aggregate batch results"""
    total = len(batch_result)
    positive = sum(1 for r in batch_result if r["sentiment"] == "positive")
    avg_score = sum(r["score"] for r in batch_result) / total if total > 0 else 0
    
    return {
        "summary": {
            "total": total,
            "positive": positive,
            "average_score": avg_score
        },
        "details": batch_result
    }

async def main():
    with WorkflowEngine(name="batch-analyzer") as workflow:
        
        # Batch processor
        with ForLoopNode(
            name="batch_processor",
            inputs={"batch_data": INPUT}
        ) as batch:
            prompt = PromptNode(
                name="prompt",
                user_prompt=REVIEW_PROMPT,
                inputs=INPUT
            )
            
            llm = LLMNode(
                name="llm",
                resource_key="gpt-4o",
                inputs={"messages": prompt},
                stream=True
            )
            
            parser = ParserNode(
                name="parser",
                format="xml",
                extract_schema=["sentiment: str", "score: float", "key_points: str"],
                inputs={"text": llm["content"]},
                outputs=OUTPUT
            )
            
            START >> prompt >> llm >> parser >> END
        
        batch.build()
        
        # Aggregator
        aggregator = CodeNode(
            name="aggregate",
            code_fn=aggregate_results,
            inputs={"batch_result": batch},
            outputs=OUTPUT
        )
        
        START >> batch >> aggregator >> END
    
    workflow.compile()
    
    # Test
    sample_data = [
        {"review": "Excellent!", "product_id": 1},
        {"review": "Terrible", "product_id": 2},
        {"review": "It's okay", "product_id": 3},
    ]
    
    result = await workflow.run(inputs={"batch_data": sample_data})
    print("Summary:", result["summary"])
    print(f"Processed {len(result['details'])} reviews")

if __name__ == "__main__":
    asyncio.run(main())
```

---

**🎉 Amazing work completing Tutorial 4! Ready for production deployment?**

**→ [Next: Tutorial 5 - Production Deployment](05-production-deployment.md)**