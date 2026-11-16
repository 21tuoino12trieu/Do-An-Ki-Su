# State Management

**How Beeflow manages workflow data efficiently**

⏱️ **Time:** ~15 minutes  
🎯 **Goal:** Understand zero-copy state and context isolation

---

## 🎯 The Problem

Traditional workflows copy data between steps:

```python
# Traditional approach (inefficient)
prompt_output = format_prompt(input)        # Copy 1
llm_input = prompt_output                   # Copy 2
llm_output = call_llm(llm_input)           # Copy 3
parser_input = llm_output                   # Copy 4

# With large data: 4 copies in memory! 💾💾💾💾
```

**Beeflow's solution:** Variables share memory via index references (zero-copy).

---

## 🏗️ Architecture

### The Three Components

```
┌──────────────────────────────────────────────────────┐
│            1. WorkflowIndexer                        │
│  Maps (node, variable) → array index                 │
│  ┌────────────────────────────────────────────────┐  │
│  │ ("prompt", "messages") → index 0               │  │
│  │ ("llm", "messages") → index 0  (same!)         │  │
│  │ ("llm", "content") → index 1                   │  │
│  │ ("parser", "text") → index 1   (same!)         │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────┐
│            2. WorkflowState                          │
│  Runtime storage (created when workflow runs)        │
│  ┌────────────────────────────────────────────────┐  │
│  │ _values[0] = VariableCell([...messages...])    │  │
│  │ _values[1] = VariableCell("LLM response")      │  │
│  │ _values[2] = VariableCell({"answer": "..."})   │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
                        ↓
┌──────────────────────────────────────────────────────┐
│            3. VariableCell                           │
│  Holds multiple values (context isolation)           │
│  ┌────────────────────────────────────────────────┐  │
│  │ contexts = {                                   │  │
│  │   "main": "value for main execution",          │  │
│  │   "for[0]": "value for loop iteration 0",      │  │
│  │   "for[1]": "value for loop iteration 1"       │  │
│  │ }                                              │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

---

## 📦 Component 1: WorkflowIndexer

**Purpose:** Create a mapping from variables to array indices (compilation phase).

### How It Works

```python
class WorkflowIndexer:
    def __init__(self, name: str):
        self._indices: Dict[Tuple[str, str], int] = {}  # (node, var) -> index
        self._values: List[Any] = []                     # Default values
    
    def _allocate(self, node: str, var: str) -> int:
        """Allocate an index for a variable"""
        if (node, var) not in self._indices:
            index = len(self._values)
            self._indices[node, var] = index
            self._values.append(None)
        return self._indices[node, var]
    
    def _link(self, node: str, var: str, ref_node: str, ref_var: str):
        """Share the same index (zero-copy reference)"""
        self._indices[node, var] = self._allocate(ref_node, ref_var)
```

### Example: Zero-Copy Linking

```python
# User code
llm_node.inputs = {"messages": prompt_node}

# What indexer does during compilation:
# 1. Allocate index for prompt output
indexer._allocate("prompt", "messages")  # Returns index 5

# 2. Link LLM input to same index
indexer._link("llm", "messages", "prompt", "messages")
# Result: both use index 5!

# Final mapping:
# ("prompt", "messages") -> 5
# ("llm", "messages") -> 5  ← Same index = zero-copy!
```

### Index Distribution

After compilation, indices are distributed to nodes for O(1) access:

```python
# Indexer distributes to nodes
prompt_node.output_indexes["messages"] = 5
llm_node.input_indexes["messages"] = 5

# Now nodes can directly access state array:
state.get_by_index(5, context_id)  # O(1) lookup!
```

---

## 💾 Component 2: WorkflowState

**Purpose:** Runtime storage for workflow execution.

### How It Works

```python
class WorkflowState:
    def __init__(self, indexer: WorkflowIndexer, inputs: dict):
        self._indexer = indexer
        # Create VariableCell for each index slot
        self._values = [VariableCell(v) for v in indexer._values]
        self._execution_order = []  # Track node execution
    
    # Access by (node, variable, context_id)
    def __setitem__(self, key: Tuple[str, str, str], value: Any):
        node, var, context_id = key
        index = self._indexer[node, var]
        self._values[index][context_id] = value
    
    def __getitem__(self, key: Tuple[str, str, str]) -> Any:
        node, var, context_id = key
        index = self._indexer[node, var]
        return self._values[index][context_id]
    
    # Direct access by index (used by nodes for performance)
    def get_by_index(self, index: int, context_id: str) -> Any:
        return self._values[index][context_id]
    
    def set_by_index(self, index: int, value: Any, context_id: str):
        self._values[index][context_id] = value
```

### Usage Example

```python
# Create state at runtime
state = WorkflowState(
    indexer=indexer,
    inputs={"query": "Hello"}
)

# Nodes use O(1) index access
class LLMNode:
    async def run(self, state, context_id):
        # Get input (O(1) - direct array access)
        messages = state.get_by_index(
            self.input_indexes["messages"],
            context_id
        )
        
        # Generate response
        response = await llm_call(messages)
        
        # Store output (O(1) - direct array write)
        state.set_by_index(
            self.output_indexes["content"],
            response,
            context_id
        )
```

---

## 🔄 Component 3: VariableCell

**Purpose:** Store multiple values for different contexts (loop iterations).

### Why Context Isolation?

```python
# Without context isolation (broken):
for i, item in enumerate(batch):
    state["processor", "input"] = item    # Overwrites previous!
    state["processor", "output"] = result

# Result: Only last iteration's data survives

# With context isolation (correct):
for i, item in enumerate(batch):
    context_id = f"for[{i}]"
    state["processor", "input", context_id] = item
    state["processor", "output", context_id] = result

# Result: Each iteration's data preserved!
```

### How It Works

```python
class VariableCell:
    def __init__(self, default_value: Any = None):
        self.contexts: Dict[str, Any] = {}    # context_id -> value
        self.versions: List[str] = []         # Track order
        self.DEFAULT_VALUE = default_value
    
    def __setitem__(self, context_id: str, value: Any):
        """Store value for a specific context"""
        if context_id not in self.versions:
            self.versions.append(context_id)
        self.contexts[context_id] = value
    
    def __getitem__(self, context_id: str) -> Any:
        """Get value for a specific context"""
        return self.contexts.get(context_id, self.DEFAULT_VALUE)
    
    def get(self) -> Any:
        """Get most recent value (latest context)"""
        if self.versions:
            return self.contexts[self.versions[-1]]
        return self.DEFAULT_VALUE
```

### Example: ForLoopNode

```python
# ForLoopNode execution
batch_data = [{"id": 1}, {"id": 2}, {"id": 3}]

for i, item in enumerate(batch_data):
    context_id = f"for[{i}]"
    
    # Each iteration gets its own context
    state["processor", "input", context_id] = item
    result = await processor.run(state, context_id)
    state["processor", "output", context_id] = result

# VariableCell now contains:
# {
#   "for[0]": {"id": 1, "processed": True},
#   "for[1]": {"id": 2, "processed": True},
#   "for[2]": {"id": 3, "processed": True}
# }

# All iterations preserved! ✅
```

---

## 🔄 Complete Flow Example

### Step 1: Compilation (WorkflowIndexer)

```python
with WorkflowEngine(name="chatbot") as workflow:
    prompt = PromptNode(user_prompt="Answer: {query}", inputs=INPUT)
    llm = LLMNode(inputs={"messages": prompt})
    parser = ParserNode(inputs={"text": llm["content"]}, outputs=OUTPUT)
    START >> prompt >> llm >> parser >> END

workflow.compile()

# Indexer creates mappings:
# ("chatbot", "query") -> 0
# ("prompt", "query") -> 0        (linked to INPUT)
# ("prompt", "messages") -> 1
# ("llm", "messages") -> 1        (linked to prompt)
# ("llm", "content") -> 2
# ("parser", "text") -> 2         (linked to llm)
# ("parser", "answer") -> 3
# ("chatbot", "answer") -> 3      (linked to OUTPUT)
```

### Step 2: Runtime (WorkflowState)

```python
# Run workflow
result = await workflow.run(inputs={"query": "What is AI?"})

# State operations during execution:

# 1. Inject input
state.set_by_index(0, "What is AI?", context_id="main")

# 2. PromptNode reads input (index 0) and writes output (index 1)
state.set_by_index(1, [{"role": "user", "content": "..."}], "main")

# 3. LLMNode reads messages (index 1) and writes content (index 2)
state.set_by_index(2, "AI is artificial intelligence...", "main")

# 4. ParserNode reads text (index 2) and writes answer (index 3)
state.set_by_index(3, {"answer": "AI is..."}, "main")

# 5. Return output
return state.get_by_index(3, "main")  # {"answer": "AI is..."}
```

---

## 🎯 Key Benefits

### 1. Zero-Copy Efficiency

```python
# Traditional (4 copies):
step1_out = step1(input)           # Copy 1
step2_in = step1_out               # Copy 2
step2_out = step2(step2_in)        # Copy 3
step3_in = step2_out               # Copy 4

# Beeflow (0 copies):
# All nodes reference same memory location via shared index
state[5] = data  # Only one copy exists!
```

**Result:** 4x less memory usage for data passing.

---

### 2. O(1) Access Time

```python
# Traditional dictionary access: O(k) where k = key length
value = state["my_long_node_name"]["some_variable"]  # String comparison

# Beeflow index access: O(1)
value = state.get_by_index(42, context_id)  # Direct array lookup
```

**Result:** Faster state access, especially with many variables.

---

### 3. Context Isolation

```python
# Parallel execution with isolated contexts
with ForLoopNode(inputs={"batch": INPUT}) as loop:
    processor = LLMNode(...)
    START >> processor >> END

# Each iteration isolated:
# VariableCell.contexts = {
#   "for[0]": result_0,
#   "for[1]": result_1,
#   "for[2]": result_2
# }
```

**Result:** Safe parallel execution without data races.

---

## 🔍 Debugging State

### View All Variables

```python
state.show()

# Output:
# workflow.query → "What is AI?"
# prompt.query → "What is AI?"
# prompt.messages → [{"role": "user", ...}]
# llm.messages → [{"role": "user", ...}]
# llm.content → "AI is artificial intelligence..."
# parser.text → "AI is artificial intelligence..."
# parser.answer → {"answer": "AI is..."}
```

### Check Specific Variable

```python
# Method 1: By (node, var, context)
value = state["llm", "content", "main"]

# Method 2: By index (if you know it)
value = state.get_by_index(2, "main")

# Method 3: Access VariableCell directly
cell = state.get("llm", "content")
print(cell.contexts)  # All context values
```

### Inspect Context Isolation

```python
# After ForLoopNode execution
cell = state.get("processor", "output")

print(f"Contexts: {cell.versions}")
# Output: ["for[0]", "for[1]", "for[2]"]

for ctx in cell.versions:
    print(f"{ctx}: {cell[ctx]}")
# Output:
# for[0]: {"result": ...}
# for[1]: {"result": ...}
# for[2]: {"result": ...}
```

---

## 💡 Best Practices

### 1. Trust the Indexer

```python
# ✅ Let indexer handle linking
llm.inputs = {"messages": prompt}

# ❌ Don't manually manage indices
# llm.input_indexes["messages"] = 42  # Don't do this!
```

### 2. Use Context IDs for Loops

```python
# ✅ Always provide context for loops
for i, item in enumerate(batch):
    context_id = f"loop_{i}"
    await node.run(state, context_id)

# ❌ Don't use same context (data overwrites)
for item in batch:
    await node.run(state, context_id="main")  # All overwrite!
```

### 3. Access via Indices in Nodes

```python
# ✅ Use distributed indices (O(1))
class CustomNode(BaseNode):
    async def run(self, state, context_id):
        value = state.get_by_index(
            self.input_indexes["data"],
            context_id
        )

# ❌ Avoid dictionary access (slower)
value = state[self.full_name, "data", context_id]
```

---

## 📊 Performance Comparison

| Operation | Traditional | Beeflow | Speedup |
|-----------|------------|---------|---------|
| Variable access | O(k) dict lookup | O(1) array access | ~10x |
| Data passing | Copy data | Share index | ~100x |
| Memory usage | N copies | 1 copy | Nx |
| Context isolation | Manual locks | VariableCell | Built-in |

---

## 🚨 Common Pitfalls

### Pitfall 1: Forgetting Context ID

```python
# ❌ Wrong - context_id=None in a loop
for item in batch:
    state["node", "var", None] = item  # Overwrites!

# ✅ Correct - unique context per iteration
for i, item in enumerate(batch):
    state["node", "var", f"iter_{i}"] = item
```

### Pitfall 2: Accessing Before Compilation

```python
# ❌ Wrong - indices not distributed yet
result = await workflow.run(inputs={...})
# workflow.compile() not called!

# ✅ Correct - compile first
workflow.compile()
result = await workflow.run(inputs={...})
```

### Pitfall 3: Modifying State Externally

```python
# ❌ Don't modify state outside workflow execution
state._values[5] = "hacked value"  # Breaks everything!

# ✅ Use proper injection
state.inject_inputs(node="my_node", inputs={"var": "value"})
```

---

## 📚 What's Next?

Now that you understand state management:

1. **Learn Execution:**
   - [Execution Model](execution-model.md) - How async execution works

2. **Add Observability:**
   - [Streaming and Observability](streaming-and-observability.md) - Production features

3. **Deep Dive:**
   - [Internals: State Indexer](../advanced/internals-state-indexer.md) - Implementation details

---

## 💡 Key Takeaways

### Architecture
- **WorkflowIndexer** - Compilation-time mapping (variable → index)
- **WorkflowState** - Runtime storage (array of VariableCells)
- **VariableCell** - Context isolation (context_id → value)

### Benefits
- **Zero-Copy** - Variables share memory via indices
- **O(1) Access** - Direct array lookup, no string comparison
- **Context Isolation** - Safe parallel execution in loops

### Best Practices
- Trust the indexer for variable linking
- Always use context IDs in loops
- Access via indices for performance
- Use `state.show()` for debugging

---

**Ready to understand execution? Continue to [Execution Model](execution-model.md) →**