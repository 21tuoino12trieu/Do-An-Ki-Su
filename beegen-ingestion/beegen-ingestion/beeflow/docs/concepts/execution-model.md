# Execution Model

**How workflows execute asynchronously**

⏱️ **Time:** ~15 minutes  
🎯 **Goal:** Understand async execution, parallelism, and dependency resolution

---

## 🎯 Core Principles

Beeflow's execution model is built on three principles:

1. **Async Native** - Everything runs asynchronously
2. **Dependency-Driven** - Nodes execute when dependencies are ready
3. **Parallel by Default** - Independent nodes run concurrently

```python
# Sequential (slow)
result_a = await node_a.run()
result_b = await node_b.run()
result_c = await node_c.run()

# Beeflow parallel (fast) ⚡
START >> splitter >> [node_a, node_b, node_c] >> combiner >> END
# All three run at the same time!
```

---

## 🔄 Execution Phases

### Phase 1: Graph Construction (Declaration)

```python
with WorkflowEngine(name="chatbot") as workflow:
    prompt = PromptNode(...)
    llm = LLMNode(...)
    parser = ParserNode(...)
    
    START >> prompt >> llm >> parser >> END
```

**What happens:**
- Nodes register with GraphNode
- Edges create dependency relationships
- Topology built (prevs/nexts maps)

---

### Phase 2: Compilation

```python
workflow.compile()
```

**What happens:**
- WorkflowIndexer created
- Variables mapped to indices
- Dependencies resolved
- Indices distributed to nodes

---

### Phase 3: Runtime Execution

```python
result = await workflow.run(inputs={"query": "Hello"})
```

**What happens:**
- WorkflowState created
- Input values injected
- Graph execution starts
- Results collected and returned

---

## ⚙️ The Execution Algorithm

### How GraphNode Executes

```python
async def run(self, state: WorkflowState, context_id: str):
    # 1. Initialize tracking
    active_tasks = {}  # Currently running nodes
    ready_count = {    # Remaining dependencies per node
        node: len(self.prevs[node]) 
        for node in self._nodes
    }
    
    # 2. Start with entry nodes (no dependencies)
    for entry in self.entries:
        active_tasks[entry] = asyncio.create_task(
            self._nodes[entry].run(state, context_id)
        )
    
    # 3. Process nodes as they complete
    while active_tasks:
        done, _ = await asyncio.wait(
            active_tasks.values(),
            return_when=asyncio.FIRST_COMPLETED
        )
        
        for task in done:
            node_name = task.get_name()
            active_tasks.pop(node_name)
            
            # 4. Activate next nodes when ready
            for next_node in self.nexts[node_name]:
                ready_count[next_node] -= 1
                
                # All dependencies satisfied?
                if ready_count[next_node] == 0:
                    active_tasks[next_node] = asyncio.create_task(
                        self._nodes[next_node].run(state, context_id)
                    )
```

**Key insight:** Nodes run as soon as all their dependencies complete.

---

## 🚀 Parallel Execution

### Pattern 1: Fan-Out (Parallel Start)

```python
# These run concurrently
START >> splitter >> [worker_a, worker_b, worker_c] >> combiner
```

**Timeline:**
```
Time →
t0: splitter runs
t1: worker_a, worker_b, worker_c START TOGETHER ⚡
t2: All complete (or fastest finishes first)
t3: combiner waits for ALL to finish
t4: combiner runs
```

**Use case:** Parallel retrieval from multiple sources

---

### Pattern 2: Independent Chains

```python
START >> [chain_a, chain_b, chain_c]
```

**Timeline:**
```
Time →
t0: All three chains START TOGETHER ⚡
t1: chain_a: step1 | chain_b: step1 | chain_c: step1
t2: chain_a: step2 | chain_b: step2 | chain_c: step2
t3: All complete independently
```

**Use case:** Batch processing without coordination

---

### Pattern 3: Diamond (Parallel then Merge)

```python
START >> node_a >> [node_b, node_c] >> node_d >> END
```

**Timeline:**
```
Time →
t0: node_a runs
t1: node_b and node_c START TOGETHER ⚡
t2: Both complete (or one finishes first)
t3: node_d waits for BOTH
t4: node_d runs
```

**Use case:** Multiple preprocessing paths that merge

---

## 🌿 Branch Execution

### How BranchNode Works

```python
branch = BranchNode(
    name="router",
    cases={
        "priority == 'high'": urgent_path,
        "priority == 'low'": normal_path
    },
    default=fallback_path
)

START >> classifier >> branch >> [urgent_path, normal_path, fallback_path] >> END
```

**Execution logic:**
1. BranchNode evaluates conditions
2. Selects ONE target node
3. Updates `ready_count` for only the selected node
4. Other paths DON'T execute

**Timeline:**
```
Time →
t0: classifier runs → outputs priority="high"
t1: branch evaluates conditions
t2: Only urgent_path runs ✓
t3: normal_path skipped ✗
t4: fallback_path skipped ✗
```

---

### Branch Convergence (The Tricky Part)

**Problem:** What if branches converge?

```python
START >> branch >> [path_a, path_b] >> merge >> END
```

**Solution:** Active path tracking

```python
# Initial state
ready_count["merge"] = 2  # Two predecessors

# If branch selects path_a:
# 1. path_a runs and completes
ready_count["merge"] -= 1  # Now 1

# 2. path_b never runs (not selected)
# But merge still waiting for path_b! ❌ BUG!
```

**Beeflow's fix:** Only count active predecessors

```python
# When branch selects path_a:
next_nodes = [path_a]  # Only the selected path

# Merge only waits for path_a now ✓
ready_count["merge"] = 1  # Updated dynamically
```

---

## 🔁 Loop Execution

### ForLoopNode (Parallel Iterations)

```python
with ForLoopNode(name="batch", inputs={"batch_data": INPUT}) as loop:
    processor = LLMNode(...)
    START >> processor >> END

# Execute
batch_data = [item1, item2, item3]
```

**Execution:**
```python
active_tasks = []

for i, item in enumerate(batch_data):
    context_id = f"for[{i}]"
    
    # Inject input with context
    state.inject_inputs(
        node=processor.full_name,
        inputs=item,
        context_id=context_id
    )
    
    # Start task (don't await yet!)
    task = asyncio.create_task(
        processor.run(state, context_id)
    )
    active_tasks.append(task)

# Wait for all to complete
results = await asyncio.gather(*active_tasks)
```

**Timeline:**
```
Time →
t0: All iterations START TOGETHER ⚡
t1: for[0] processing | for[1] processing | for[2] processing
t2: All complete (or fastest first)
```

**Key:** Context isolation via `context_id` prevents data races.

---

### WhileLoopNode (Sequential Iterations)

```python
with WhileLoopNode(name="agent", inputs={"messages": INPUT}) as loop:
    reason = LLMNode(...)
    check = BranchNode(
        cases={"Answer is None": "tool"},
        default=END
    )
    tool = ToolExecutorNode(...)
    
    START >> reason >> check >> [tool, END]
    tool >> CONTINUE
```

**Execution:**
```python
_continue = True
step_count = 0
step_inputs = initial_inputs

while _continue:
    context_id = f"while-{step_count}"
    
    # Inject inputs for this iteration
    state.inject_inputs(
        node=graph.full_name,
        inputs=step_inputs,
        context_id=context_id
    )
    
    # Run iteration (await - sequential!)
    _outputs = await graph.run(state, context_id)
    
    # Check continue condition
    _continue = _outputs.get("continue_loop", False)
    
    # Get inputs for next iteration
    step_inputs = graph.get_inputs(state, context_id)
    step_count += 1
```

**Timeline:**
```
Time →
t0: while-0 starts
t1: while-0 completes → check continue
t2: while-1 starts (if continue=True)
t3: while-1 completes → check continue
t4: while-2 starts (if continue=True)
...
```

**Key:** Sequential execution, one iteration at a time.

---

## 🎯 Dependency Resolution

### Simple Chain

```python
START >> node_a >> node_b >> node_c >> END
```

**Dependencies:**
- `node_a`: depends on START (always ready)
- `node_b`: depends on `node_a`
- `node_c`: depends on `node_b`
- END: depends on `node_c`

**Execution order:** a → b → c (sequential)

---

### Parallel with Merge

```python
START >> node_a >> [node_b, node_c] >> node_d >> END
```

**Dependencies:**
- `node_b`: depends on `node_a`
- `node_c`: depends on `node_a`
- `node_d`: depends on BOTH `node_b` AND `node_c`

**Execution order:** a → (b + c in parallel) → d

---

### Complex DAG

```python
START >> node_a >> [node_b, node_c]
node_b >> node_d
node_c >> node_d
node_d >> node_e >> END
```

**Dependencies:**
- `node_d`: waits for both `node_b` and `node_c`
- `node_e`: waits for `node_d`

**Timeline:**
```
t0: node_a
t1: node_b and node_c (parallel)
t2: node_d (after both complete)
t3: node_e
```

---

## ⏱️ Performance Characteristics

### Sequential vs Parallel

```python
# Sequential (slow)
START >> step1 >> step2 >> step3 >> END
# Total time: t1 + t2 + t3

# Parallel (fast)
START >> [step1, step2, step3] >> END
# Total time: max(t1, t2, t3)

# Speedup: up to 3x in this case!
```

### Best Case Parallelism

```python
# 10 independent tasks
START >> [t1, t2, t3, t4, t5, t6, t7, t8, t9, t10] >> END

# Sequential: 10 * avg_time
# Parallel: max(all_times) ≈ avg_time

# Speedup: ~10x! ⚡
```

### Worst Case (Sequential)

```python
# Deep chain (no parallelism possible)
START >> a >> b >> c >> d >> e >> f >> g >> h >> i >> j >> END

# No speedup possible - dependencies force sequential execution
```

---

## 🔍 Debugging Execution

### View Execution Order

```python
# After execution
print(state.execution_order)

# Output:
# [
#   {"node": "prompt", "parent": "workflow", "context_id": "main"},
#   {"node": "llm", "parent": "workflow", "context_id": "main"},
#   {"node": "parser", "parent": "workflow", "context_id": "main"}
# ]
```

### Trace Node Timing

```python
# Each node records timing
node_data = node.trace_data(state, context_id)

print(node_data["start_time"])   # When node started
print(node_data["end_time"])     # When node completed

# Calculate duration
duration = node_data["end_time"] - node_data["start_time"]
print(f"Node took {duration.total_seconds()}s")
```

### Identify Bottlenecks

```python
# Find slowest nodes
for execution in state.execution_order:
    node_name = execution["node"]
    context_id = execution["context_id"]
    
    start = state[node_name, "start_time", context_id]
    end = state[node_name, "end_time", context_id]
    duration = (end - start).total_seconds()
    
    print(f"{node_name}: {duration:.2f}s")

# Output:
# prompt: 0.01s
# llm: 2.34s  ← Bottleneck!
# parser: 0.05s
```

---

## 💡 Best Practices

### 1. Parallelize When Possible

```python
# ✅ Good - parallel retrieval
START >> query >> [retriever_a, retriever_b, retriever_c] >> combine

# ❌ Slow - sequential retrieval
START >> query >> retriever_a >> retriever_b >> retriever_c >> combine
```

### 2. Avoid Unnecessary Dependencies

```python
# ✅ Good - independent paths
START >> [processor_a, processor_b] >> END

# ❌ Bad - false dependency
START >> processor_a >> processor_b >> END
# If processor_b doesn't need processor_a output, don't chain!
```

### 3. Batch When Appropriate

```python
# ✅ Good - batch processing with ForLoopNode
with ForLoopNode(inputs={"batch": INPUT}) as loop:
    processor = LLMNode(...)
    START >> processor >> END

# ❌ Slow - sequential processing
for item in batch:
    await processor.run(state, context_id="main")  # One by one!
```

### 4. Use Context IDs in Loops

```python
# ✅ Correct - isolated contexts
for i, item in enumerate(batch):
    context_id = f"iter_{i}"
    await node.run(state, context_id)

# ❌ Wrong - shared context (data overwrites)
for item in batch:
    await node.run(state, context_id="main")
```

---

## 🚨 Common Pitfalls

### Pitfall 1: Blocking Operations

```python
# ❌ Bad - blocks event loop
def sync_function():
    time.sleep(5)  # Blocks everything!
    return "done"

# ✅ Good - async
async def async_function():
    await asyncio.sleep(5)  # Other nodes can run
    return "done"
```

### Pitfall 2: Circular Dependencies

```python
# ❌ Impossible - circular dependency
node_a.inputs = {"data": node_b}
node_b.inputs = {"data": node_a}

# Runtime error: Cannot resolve dependencies!
```

### Pitfall 3: Missing await

```python
# ❌ Wrong - creates task but doesn't wait
async def run_workflow():
    workflow.run(inputs={...})  # Fire and forget - wrong!

# ✅ Correct - wait for completion
async def run_workflow():
    result = await workflow.run(inputs={...})
```

---

## 📊 Execution Patterns Summary

| Pattern | Parallelism | Use Case |
|---------|-------------|----------|
| Sequential Chain | None | Linear pipeline |
| Fan-Out | High | Parallel retrieval |
| Diamond | Medium | Split-process-merge |
| Branch | Low | Conditional logic |
| ForLoop | High | Batch processing |
| WhileLoop | None | Iterative agents |

---

## 📚 What's Next?

Now that you understand execution:

1. **Add Production Features:**
   - [Streaming and Observability](streaming-and-observability.md) - Real-time output and monitoring

2. **Optimize Performance:**
   - [Performance Optimization](../advanced/performance-optimization.md) - Advanced techniques

3. **Build Something:**
   - [Tutorials](../tutorials/_index.md) - Apply what you learned

---

## 💡 Key Takeaways

### Execution Principles
- **Async Native** - Non-blocking by default
- **Dependency-Driven** - Nodes run when ready
- **Parallel by Default** - Independent nodes run together

### Execution Flow
1. **Construction** - Build graph topology
2. **Compilation** - Resolve dependencies
3. **Runtime** - Execute with active task tracking

### Parallelism
- **Fan-Out** - Multiple nodes start from one
- **Fan-In** - Multiple nodes converge to one
- **ForLoop** - Parallel iterations with context isolation
- **WhileLoop** - Sequential iterations

### Performance
- Parallelize independent nodes for speedup
- Use ForLoopNode for batch processing
- Profile with execution_order and timing data

---

**Ready for production features? Continue to [Streaming and Observability](streaming-and-observability.md) →**