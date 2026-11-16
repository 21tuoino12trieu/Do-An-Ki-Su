# Flow Control Nodes

**Conditional routing, loops, and graph orchestration**

---

## BranchNode

**Purpose:** Route execution flow based on conditions (if/else logic).

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cases` | Dict[str, str] | Required | Condition → target node mappings |
| `default` | str/Node | `None` | Fallback target if no conditions match |
| `candidates` | List[str] | `None` | Override auto-detected target list |
| `inputs` | dict | `{}` | Input variable mappings |
| `outputs` | dict | `{}` | Output variable mappings |

### How It Works

1. **Evaluates conditions** in order (first match wins)
2. **Routes to matched target** or default
3. **Special "anchor" input** for direct routing (bypasses conditions)

### Example: Simple If/Else

```python
branch = BranchNode(
    name="content_router",
    cases={
        "filter_type == 'SAFE'": safe_handler,
        "filter_type == 'SPAM'": spam_handler
    },
    default=default_handler,
    inputs={
        "filter_type": filter_node["filter_type"]
    }
)

# Connect to all possible targets
START >> filter_node >> branch >> [safe_handler, spam_handler, default_handler]
```

### Example: Multi-Condition

```python
branch = BranchNode(
    name="user_router",
    cases={
        "user_type == 'premium' and age >= 18": premium_flow,
        "user_type == 'free' and age >= 18": free_flow,
        "age < 18": minor_flow
    },
    default=error_handler,
    inputs={
        "user_type": INPUT["user_type"],
        "age": INPUT["age"]
    }
)
```

### Example: Anchor-Based Routing

```python
# Direct routing without condition evaluation
branch = BranchNode(
    name="dynamic_router",
    cases={
        "confidence > 0.9": high_confidence,
        "confidence > 0.5": medium_confidence
    },
    inputs={
        "anchor": route_selector["target_node"],  # Direct override
        "confidence": analyzer["confidence"]
    }
)

# If anchor is set, goes directly to that node
# Otherwise evaluates confidence conditions
```

### Input Schema

```python
{
    "anchor": str = None,    # Direct routing (bypasses conditions)
    **condition_variables    # Variables used in conditions (auto-detected)
}
```

### Output Schema

```python
{
    "target": str,    # Selected target node name
    "matched": str    # Condition string that matched (or "anchor"/"default")
}
```

### Condition Syntax

- **Comparison:** `==`, `!=`, `>`, `<`, `>=`, `<=`
- **Logical:** `and`, `or`, `not`
- **Membership:** `in`, `not in`
- **Examples:**
  ```python
  "status == 'active'"
  "score > 0.8 and category in ['A', 'B']"
  "not is_spam and confidence >= 0.5"
  ```

### Notes

- Conditions evaluated in order (first match wins)
- Use `anchor` for dynamic routing at runtime
- Variables in conditions auto-detected and added to input schema
- All target nodes must be connected with `>>` operator

---

## ForLoopNode

**Purpose:** Execute a sub-graph for each item in a batch (parallel processing).

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `inputs` | dict | `{}` | Must include `batch_data: List` |
| `outputs` | dict | `{}` | Auto-outputs `batch_result: List` |

### How It Works

1. **Receives batch_data** (list of items)
2. **Spawns parallel tasks** for each item
3. **Executes inner graph** for each task
4. **Collects results** in order
5. **Returns batch_result** (list of outputs)

### Example: Batch Query Rewriting

```python
with ForLoopNode(
    name="batch_rewrite",
    inputs={"batch_data": INPUT["queries"]}
) as loop:
    # Inner graph - runs once per query
    prompt = PromptNode(
        user_prompt="Rewrite: {query}",
        inputs=INPUT  # Each item becomes INPUT
    )
    llm = LLMNode(
        resource_key="gpt-4o",
        inputs={"messages": prompt}
    )
    parser = ParserNode(
        extract_schema=["rewritten: str"],
        inputs={"text": llm["content"]},
        outputs=OUTPUT  # Each result becomes OUTPUT
    )
    
    START >> prompt >> llm >> parser >> END

# Usage
result = await loop.run(state)
# result["batch_result"] = [{rewritten: "..."}, {rewritten: "..."}, ...]
```

### Example: Parallel Document Processing

```python
def prepare_batch(docs: List) -> Dict:
    return {
        "batch_data": [
            {"doc_id": doc["id"], "text": doc["content"]}
            for doc in docs
        ]
    }

prep = CodeNode(code_fn=prepare_batch, inputs=INPUT)

with ForLoopNode(
    name="process_docs",
    inputs={"batch_data": prep["batch_data"]}
) as loop:
    embed = EmbeddingNode(
        resource_key="bge-m3",
        inputs={"texts": INPUT["text"]}
    )
    milvus = MilvusNode(
        operation=MilvusOperation.INSERT,
        inputs={
            "vectors": embed["embeddings"],
            "doc_id": INPUT["doc_id"]
        }
    )
    START >> embed >> milvus >> END

# Processes all documents in parallel
```

### Input Schema

```python
{
    "batch_data": List[Dict]  # List of input dicts for inner graph
}
```

### Output Schema

```python
{
    "batch_result": List[Dict]  # List of outputs from inner graph
}
```

### Notes

- **Parallel execution** - all items processed simultaneously
- Each item gets isolated state context (`for[0]`, `for[1]`, etc.)
- Inner graph INPUT/OUTPUT map to batch items
- Results maintain input order
- Use for independent tasks (no cross-item dependencies)

---

## WhileLoopNode

**Purpose:** Execute a sub-graph repeatedly until a condition is met (iterative processing).

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `inputs` | dict | `{}` | Initial state for loop |
| `outputs` | dict | `{}` | Final state after loop |

### How It Works

1. **Initializes state** with inputs
2. **Runs inner graph** with current state
3. **Checks `continue_loop`** output
4. **If True:** Feeds outputs back as inputs for next iteration
5. **If False:** Returns final outputs
6. **Repeats** until `continue_loop == False`

### Example: ReAct Agent Loop

```python
with WhileLoopNode(
    name="agent_loop",
    inputs={
        "messages": INPUT["messages"],
        "iteration_count": 0
    }
) as loop:
    # Reason about next action
    reason = LLMNode(
        resource_key="gpt-4o",
        inputs={"messages": INPUT}
    )
    
    # Parse action and params
    parser = ParserNode(
        extract_schema=["Action", "Params", "Answer"],
        inputs={"text": reason["content"]}
    )
    
    # Check if should continue
    check = BranchNode(
        name="continue_check",
        cases={
            "Answer is None and iteration_count < 5": "execute_tool"
        },
        default=END,  # Stop loop
        inputs={
            "Answer": parser["Answer"],
            "iteration_count": INPUT
        }
    )
    
    # Execute tool if continuing
    tool = ToolExecutorNode(
        name="execute_tool",
        tools=[calculator, search],
        inputs={
            "tool_name": parser["Action"],
            "tool_params": parser["Params"]
        }
    )
    
    # Update state for next iteration
    update = CodeNode(
        name="update_state",
        code_fn=lambda messages, result, count: {
            "out_messages": messages + [{"role": "tool", "content": result}],
            "out_iteration_count": count + 1
        },
        inputs={
            "messages": INPUT,
            "result": tool["result"],
            "count": INPUT["iteration_count"]
        },
        outputs={
            "out_messages": INPUT["messages"],        # Feed back
            "out_iteration_count": INPUT["iteration_count"]
        }
    )
    
    START >> reason >> parser >> check >> [tool, END]
    tool >> update >> CONTINUE  # CONTINUE marks loop continuation

# Runs until Answer is found or max iterations
```

### Example: Iterative Refinement

```python
with WhileLoopNode(
    name="refine_loop",
    inputs={
        "draft": INPUT["initial_draft"],
        "score": 0.0,
        "iterations": 0
    }
) as loop:
    # Evaluate current draft
    evaluator = LLMNode(
        user_prompt="Rate this draft (0-1): {draft}",
        inputs={"draft": INPUT}
    )
    
    # Parse score
    parser = ParserNode(
        extract_schema=["score: float"],
        inputs={"text": evaluator["content"]}
    )
    
    # Check if good enough
    check = BranchNode(
        cases={"score < 0.9 and iterations < 3": "refine"},
        default=END,
        inputs={
            "score": parser["score"],
            "iterations": INPUT
        }
    )
    
    # Improve draft
    refiner = LLMNode(
        name="refine",
        user_prompt="Improve this draft: {draft}",
        inputs={"draft": INPUT}
    )
    
    update = CodeNode(
        code_fn=lambda old, new, i: {
            "out_draft": new,
            "out_iterations": i + 1
        },
        inputs={
            "old": INPUT["draft"],
            "new": refiner["content"],
            "i": INPUT["iterations"]
        },
        outputs={
            "out_draft": INPUT["draft"],
            "out_iterations": INPUT["iterations"]
        }
    )
    
    START >> evaluator >> parser >> check >> [refiner, END]
    refiner >> update >> CONTINUE

# Outputs: {"draft": "refined text", "score": 0.95, "iterations": 2}
```

### Loop Control

**To continue loop:**
```python
# Option 1: Use CONTINUE marker
node >> update >> CONTINUE

# Option 2: Set continue_loop flag
update_node.continue_loop = True
```

**To stop loop:**
```python
# Route to END
check >> END

# Loop stops when continue_loop is False (default)
```

### Input/Output Schema

- **Auto-detected** from inner graph INPUT/OUTPUT references
- **Loop state** flows through iterations
- **Final output** is state after last iteration

### Notes

- Use for **stateful iterations** (each step depends on previous)
- Contrast with ForLoopNode (parallel, independent items)
- Add **max iteration check** to prevent infinite loops
- Inner graph outputs become next iteration's inputs
- Common pattern: Agent reasoning loops, iterative refinement

---

## GraphNode

**Purpose:** Container for sub-graphs (nested workflows, reusable components).

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str | Required | Graph identifier |
| `description` | str | `""` | Graph purpose |
| `inputs` | dict | `{}` | Input variable mappings |
| `outputs` | dict | `{}` | Output variable mappings |

### How It Works

1. **Context manager** for defining nested workflow
2. **Builds internal graph** on exit
3. **Exposes INPUT/OUTPUT** for parent workflow
4. **Executes as single unit** from parent's view

### Example: Reusable Query Rewriter

```python
with GraphNode(
    name="query_rewriter",
    description="Rewrites user query with history context"
) as rewriter:
    prompt = PromptNode(
        user_prompt="Rewrite: {query} given {history}",
        inputs=INPUT  # Maps to parent's inputs
    )
    llm = LLMNode(
        resource_key="gpt-4o",
        inputs={"messages": prompt}
    )
    parser = ParserNode(
        extract_schema=["rewritten: str"],
        inputs={"text": llm["content"]},
        outputs=OUTPUT  # Maps to parent's outputs
    )
    START >> prompt >> llm >> parser >> END

rewriter.build()

# Use in parent workflow
with WorkflowEngine(name="main") as main:
    rewriter_instance = rewriter  # Reuse component
    next_step = SomeNode(
        inputs={"query": rewriter_instance["rewritten"]}
    )
    START >> rewriter_instance >> next_step >> END
```

### Example: Multi-Branch Sub-Graph

```python
with GraphNode(name="content_processor") as processor:
    classifier = LLMNode(
        user_prompt="Classify: {content}",
        inputs=INPUT
    )
    
    parse_category = ParserNode(
        extract_schema=["category: str"],
        inputs={"text": classifier["content"]}
    )
    
    branch = BranchNode(
        name="route_by_category",
        cases={
            "category == 'text'": "text_handler",
            "category == 'image'": "image_handler"
        },
        default="default_handler",
        inputs={"category": parse_category["category"]}
    )
    
    text_handler = TextNode(inputs=INPUT["content"])
    image_handler = ImageNode(inputs=INPUT["content"])
    default_handler = DefaultNode(inputs=INPUT["content"])
    
    START >> classifier >> parse_category >> branch >> [
        text_handler,
        image_handler,
        default_handler
    ]
    
    # Merge outputs
    text_handler >> END
    image_handler >> END
    default_handler >> END

processor.build()

# Single node from parent's perspective
main_workflow >> processor >> next_step
```

### Nested Graphs

```python
# Outer graph
with GraphNode(name="pipeline") as pipeline:
    # Inner graph 1
    with GraphNode(name="preprocess") as prep:
        clean = CleanNode(inputs=INPUT)
        normalize = NormalizeNode(inputs={"text": clean})
        START >> clean >> normalize >> END
    prep.build()
    
    # Inner graph 2
    with GraphNode(name="analyze") as analyze:
        embed = EmbeddingNode(inputs=INPUT)
        classify = ClassifyNode(inputs={"vectors": embed})
        START >> embed >> classify >> END
    analyze.build()
    
    # Connect sub-graphs
    START >> prep >> analyze >> END

pipeline.build()
```

### Input/Output Mapping

```python
# Inside graph: INPUT/OUTPUT refer to graph boundaries
with GraphNode(name="subgraph") as graph:
    node1 = Node1(inputs=INPUT["x"])           # From parent
    node2 = Node2(inputs={"y": node1})
    node3 = Node3(
        inputs={"z": node2},
        outputs={"result": OUTPUT["final"]}    # To parent
    )
    START >> node1 >> node2 >> node3 >> END

graph.build()

# From parent: Access graph as single node
parent_node >> graph >> next_node
value = graph["final"]  # Access graph output
```

### Notes

- Use for **reusable components**
- Enables **modular workflow design**
- **Nested graphs** for complex hierarchies
- **Single execution unit** from parent's view
- Must call `.build()` after definition

---

## 💡 Common Patterns

### Pattern: Conditional RAG Routing

```python
# Check if query needs retrieval
classifier = BasicChainNode(
    resource_key="gpt-4o",
    user_prompt="Does '{query}' need knowledge base? Answer yes/no",
    extract_schema=["needs_rag: str"],
    inputs=INPUT
)

# Route based on classification
branch = BranchNode(
    name="rag_router",
    cases={"needs_rag == 'yes'": rag_pipeline},
    default=direct_llm,
    inputs={"needs_rag": classifier["needs_rag"]}
)

# Define branches
rag_pipeline = RetrieverNode(...)  # Retrieve + LLM
direct_llm = LLMNode(...)           # Direct LLM

START >> classifier >> branch >> [rag_pipeline, direct_llm] >> END
```

### Pattern: Batch Processing with Error Handling

```python
def split_batch(items: List) -> Dict:
    return {"batch_data": [{"item": x, "retry": 0} for x in items]}

prep = CodeNode(code_fn=split_batch, inputs=INPUT)

with ForLoopNode(
    name="robust_batch",
    inputs={"batch_data": prep}
) as loop:
    # Try processing
    processor = ProcessNode(inputs=INPUT["item"])
    
    # Check for errors
    check = BranchNode(
        cases={"retry < 3 and has_error": "retry_handler"},
        default=END,
        inputs={
            "retry": INPUT["retry"],
            "has_error": processor["error"] != None
        }
    )
    
    retry_handler = CodeNode(
        code_fn=lambda item, count: {
            "item": item,
            "retry": count + 1
        },
        inputs={
            "item": INPUT["item"],
            "count": INPUT["retry"]
        }
    )
    
    START >> processor >> check >> [retry_handler, END]
    retry_handler >> processor  # Retry loop
```

### Pattern: Agent with Memory

```python
with WhileLoopNode(
    name="agent_with_memory",
    inputs={
        "messages": INPUT["messages"],
        "memory": [],
        "iteration": 0
    }
) as agent:
    # Reason
    llm = LLMNode(inputs={"messages": INPUT})
    
    # Parse
    parser = ParserNode(
        extract_schema=["action", "params", "answer"],
        inputs={"text": llm["content"]}
    )
    
    # Continue check
    check = BranchNode(
        cases={"answer is None and iteration < 10": "tool"},
        default=END,
        inputs={
            "answer": parser["answer"],
            "iteration": INPUT
        }
    )
    
    # Execute tool
    tool = ToolExecutorNode(
        tools=[search, calculator],
        inputs={
            "tool_name": parser["action"],
            "tool_params": parser["params"]
        }
    )
    
    # Update with memory
    update = CodeNode(
        code_fn=lambda msgs, mem, res, i: {
            "out_messages": msgs + [{"role": "tool", "content": res}],
            "out_memory": mem + [{"iteration": i, "action": res}],
            "out_iteration": i + 1
        },
        inputs={
            "msgs": INPUT["messages"],
            "mem": INPUT["memory"],
            "res": tool["result"],
            "i": INPUT["iteration"]
        },
        outputs={
            "out_messages": INPUT["messages"],
            "out_memory": INPUT["memory"],
            "out_iteration": INPUT["iteration"]
        }
    )
    
    START >> llm >> parser >> check >> [tool, END]
    tool >> update >> CONTINUE
```

### Pattern: Multi-Stage Pipeline

```python
with GraphNode(name="multi_stage") as pipeline:
    # Stage 1: Preprocessing
    with GraphNode(name="stage1_prep") as stage1:
        clean = CleanNode(inputs=INPUT)
        validate = ValidateNode(inputs={"text": clean})
        START >> clean >> validate >> END
    stage1.build()
    
    # Stage 2: Analysis
    with GraphNode(name="stage2_analyze") as stage2:
        embed = EmbeddingNode(inputs=INPUT)
        search = MilvusNode(
            inputs={"vectors": embed},
            operation=MilvusOperation.SEARCH
        )
        START >> embed >> search >> END
    stage2.build()
    
    # Stage 3: Generation
    with GraphNode(name="stage3_generate") as stage3:
        prompt = PromptNode(
            inputs={"query": INPUT, "docs": INPUT}
        )
        llm = LLMNode(inputs={"messages": prompt})
        START >> prompt >> llm >> END
    stage3.build()
    
    # Connect stages
    START >> stage1 >> stage2 >> stage3 >> END

pipeline.build()
```

---

## 🎯 Best Practices

### Branch Conditions

```python
# ✅ Good: Simple, clear conditions
cases = {
    "score > 0.9": high_confidence,
    "score > 0.5": medium_confidence
}

# ❌ Avoid: Complex nested logic
cases = {
    "score > 0.9 and (category == 'A' or (category == 'B' and flag))": ...
}
# Better: Split into multiple branches or use CodeNode
```

### Loop Safety

```python
# ✅ Always include max iteration check
check = BranchNode(
    cases={"not done and iteration < MAX_ITER": continue_node},
    default=END
)

# ✅ Add timeout for long-running loops
with WhileLoopNode(inputs={..., "start_time": time.time()}) as loop:
    check = BranchNode(
        cases={
            "not done and iteration < 10 and time.time() - start_time < 300": ...
        },
        default=END
    )
```

### Graph Organization

```python
# ✅ Good: Modular, reusable components
prep_graph = GraphNode(name="preprocessing")
analyze_graph = GraphNode(name="analysis")
generate_graph = GraphNode(name="generation")

# ❌ Avoid: Monolithic nested graphs
with GraphNode(name="everything") as big:
    with GraphNode(name="step1") as s1:
        with GraphNode(name="substep1") as ss1:
            ...  # Too deep
```

---

## 📚 Related

- [AI Nodes](ai-nodes.md) - LLM, Embedding nodes for intelligence
- [Transform Nodes](transform-nodes.md) - CodeNode for data processing
- [Templates](templates.md) - Pre-built patterns using flow control
- [Tutorial: ReAct Agent](../../tutorials/03-react-agent.md) - WhileLoopNode example
- [Tutorial: Batch Processing](../../tutorials/04-batch-processing.md) - ForLoopNode example

---

[← Back to Node Catalog](_index.md)