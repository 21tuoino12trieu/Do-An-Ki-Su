# Core Concepts

**Understanding Beeflow's architecture and design principles**

---

## 📚 Overview

This section explains the fundamental concepts behind Beeflow. Whether you're building your first workflow or optimizing for production, understanding these concepts will help you build better AI applications.

**Reading Path:**
1. Start with **Architecture Overview** for the big picture
2. Dive into specific topics based on your needs
3. Refer back as you build more complex workflows

---

## 🗺️ Concept Map

```
┌─────────────────────────────────────────────────────────────┐
│                   ARCHITECTURE OVERVIEW                     │
│                    (Start Here!)                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  • What is Beeflow?                                  │   │
│  │  • Design Philosophy                                 │   │
│  │  • High-Level Architecture                           │   │
│  │  • Component Overview                                │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
              ↓                    ↓                    ↓
    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
    │  NODES & GRAPHS │  │ STATE MGMT      │  │ EXECUTION MODEL │
    ├─────────────────┤  ├─────────────────┤  ├─────────────────┤
    │ • BaseNode      │  │ • WorkflowState │  │ • Graph Exec    │
    │ • GraphNode     │  │ • VariableCell  │  │ • Async Model   │
    │ • Node Types    │  │ • Indexer       │  │ • Dependencies  │
    │ • Connections   │  │ • Zero-Copy     │  │ • Parallelism   │
    └─────────────────┘  └─────────────────┘  └─────────────────┘
                                   ↓
                    ┌──────────────────────────────┐
                    │  STREAMING & OBSERVABILITY   │
                    ├──────────────────────────────┤
                    │ • Redis Streaming            │
                    │ • Langfuse Integration       │
                    │ • Token Tracking             │
                    │ • Error Handling             │
                    └──────────────────────────────┘
```

---

## 📖 Concepts Guide

### 1. [Architecture Overview](architecture-overview.md) 🌟 **START HERE**

**The big picture of how Beeflow works**

Learn about:
- Beeflow's design philosophy (DAG-based, zero-copy, declarative)
- High-level architecture and component interaction
- How workflows execute from end-to-end
- When to use Beeflow vs other frameworks

**Best for:** Understanding the overall system before diving into specifics

**Time:** ~15 minutes

---

### 2. [Nodes and Graphs](nodes-and-graphs.md)

**The building blocks of Beeflow workflows**

Learn about:
- What nodes are and how they work
- Node types (LLM, Code, Data, Transform, Flow Control)
- GraphNode for composable sub-workflows
- Node connections and dependencies
- Input/output schemas

**Best for:** Building and connecting workflow components

**Time:** ~20 minutes

**Key Topics:**
```python
# Node basics
node = LLMNode(name="llm", resource_key="gpt-4o")

# Node connections
START >> node_a >> node_b >> END

# Variable references
node_b.inputs = {"data": node_a["output"]}

# Graph nesting
with GraphNode(name="subgraph") as graph:
    # Nested workflow
    ...
```

---

### 3. [State Management](state-management.md)

**How Beeflow manages workflow data efficiently**

Learn about:
- WorkflowState architecture
- VariableCell for context isolation
- WorkflowIndexer for zero-copy variable sharing
- State lifecycle and memory management
- Debugging state issues

**Best for:** Understanding data flow and optimizing memory usage

**Time:** ~20 minutes

**Key Topics:**
```python
# State indexing
state["node_name", "variable", "context_id"] = value

# Zero-copy references
node_b.inputs = {"data": node_a}  # Shares same index

# Context isolation (loops)
for i in range(3):
    state["node", "var", f"loop_{i}"] = data[i]
```

---

### 4. [Execution Model](execution-model.md)

**How workflows execute asynchronously**

Learn about:
- Async execution and concurrency
- Dependency resolution
- Parallel node execution
- Branch convergence handling
- Loop execution (ForLoopNode, WhileLoopNode)
- Error propagation

**Best for:** Optimizing workflow performance and understanding timing

**Time:** ~20 minutes

**Key Topics:**
```python
# Parallel execution
node_a >> [node_b, node_c]  # b and c run in parallel

# Branch convergence
branch >> [path_a, path_b] >> merge  # Correct handling

# Loop contexts
for i, item in enumerate(batch):
    await node.run(state, context_id=f"loop_{i}")
```

---

### 5. [Streaming and Observability](streaming-and-observability.md)

**Production features for monitoring and real-time output**

Learn about:
- Redis streaming architecture
- Langfuse trace hierarchy
- Token usage tracking
- Error tracking and debugging
- Performance monitoring
- Production best practices

**Best for:** Deploying workflows to production

**Time:** ~25 minutes

**Key Topics:**
```python
# Enable streaming
node = LLMNode(stream=True, ...)

# Consume streams
async for channel in STREAM_SERVICE.get_channels(request_id):
    async for chunk in STREAM_SERVICE.get(request_id, channel):
        print(chunk.choices[0].delta.content)

# Langfuse traces (automatic)
result = await workflow.run(
    inputs={...},
    user_id="user_123",
    session_id="session_456",
    request_id="req_789"
)
```

---

## 🎯 Quick Reference

### By Use Case

**"I want to understand how everything works"**
→ Start with [Architecture Overview](architecture-overview.md)

**"I'm building a complex workflow with sub-graphs"**
→ Read [Nodes and Graphs](nodes-and-graphs.md)

**"My workflow is using too much memory"**
→ Study [State Management](state-management.md)

**"My workflow is slow, I need parallelism"**
→ Check [Execution Model](execution-model.md)

**"I need real-time streaming and monitoring"**
→ Review [Streaming and Observability](streaming-and-observability.md)

---

### By Role

**Data Scientists / ML Engineers**
1. Architecture Overview → Quick mental model
2. Nodes and Graphs → Build workflows
3. Streaming and Observability → Monitor experiments

**Backend Engineers**
1. Architecture Overview → System design
2. State Management → Performance optimization
3. Execution Model → Concurrency patterns
4. Streaming and Observability → Production deployment

**DevOps / SRE**
1. Architecture Overview → Infrastructure needs
2. Execution Model → Resource planning
3. Streaming and Observability → Monitoring setup

---

## 🔗 Related Resources

**Hands-On Learning:**
- [Tutorials](../tutorials/_index.md) - Step-by-step guides
- [Examples](../../examples/) - Working code samples

**Reference:**
- [Node Catalog](../reference/node-catalog/_index.md) - All available nodes
- [API Reference](../reference/api-reference.md) - Detailed API docs

**Advanced:**
- [Custom Node Development](../advanced/custom-node-development.md)
- [Performance Optimization](../advanced/performance-optimization.md)
- [Internals](../advanced/internals-state-indexer.md)

---

## 💡 Key Principles

Throughout these concept docs, you'll see these core principles:

1. **Declarative First** - Define what you want, not how to do it
2. **Zero-Copy** - Share data via references, not copies
3. **Async Native** - Built for concurrent execution
4. **Observable** - Built-in tracing and monitoring
5. **Composable** - Nest and reuse workflow components

---

## 📝 Notation & Conventions

In these docs, we use:

```python
# ✅ Recommended pattern
node_a >> node_b

# ❌ Anti-pattern (avoid)
node_a.targets.append(node_b.name)

# 🔍 Explanation of internal behavior
# The >> operator calls graph.add_edge(...)

# ⚠️ Important gotcha
# Don't modify state directly outside workflow
```

**Visual Elements:**
- 📦 = Component/Module
- 🔄 = Process/Flow
- 💾 = Data/State
- ⚡ = Performance consideration
- 🎯 = Best practice

---

**Ready to dive in? Start with [Architecture Overview](architecture-overview.md)! 🚀**