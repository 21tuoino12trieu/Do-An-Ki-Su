# 📚 Tutorials

Welcome to the Beeflow tutorial series! These hands-on guides will teach you how to build real-world AI applications step by step.

---

## 🎓 Learning Path

Follow these tutorials in order to progressively build your Beeflow skills:

```
┌─────────────────────────────────────────────────────────────┐
│  Prerequisites: Completed Quickstart Guide                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Tutorial 1: Basic LLM Chain                                │
│  ⏱️  20 mins  │  ⭐ Beginner                                
│  Learn: Prompt engineering, LLM nodes, parsing              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Tutorial 2: RAG Pipeline                                   │
│  ⏱️  45 mins  │  ⭐⭐ Intermediate                         
│  Learn: Vector search, retrieval, context injection         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Tutorial 3: ReAct Agent                                    │
│  ⏱️  60 mins  │  ⭐⭐⭐ Advanced                               
│  Learn: Tool calling, iterative reasoning, error handling   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Tutorial 4: Batch Processing                               │
│  ⏱️  40 mins  │  ⭐⭐ Intermediate                            
│  Learn: ForLoopNode, parallel execution, streaming          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Tutorial 5: Production Deployment                          │
│  ⏱️  60 mins  │  ⭐⭐⭐ Advanced                               
│  Learn: Langfuse traces, error handling, streaming setup    │
└─────────────────────────────────────────────────────────────┘
```

---

## 📖 Tutorial Overview

### [Tutorial 1: Basic LLM Chain](01-basic-llm-chain.md)
**Build a sentiment analyzer with structured output**

Learn the fundamentals of Beeflow by building a simple but complete workflow:
- 🎯 **Goal:** Create a sentiment analyzer that extracts sentiment and confidence
- 🔧 **Nodes Used:** `PromptNode`, `LLMNode`, `ParserNode`
- 📚 **Concepts:** Node connections, variable mapping, structured output
- ⏱️ **Time:** ~20 minutes
- ⭐ **Level:** Beginner

**What you'll build:**
```python
Input: "I absolutely love this product!"
Output: {
    "sentiment": "positive",
    "confidence": 0.95,
    "explanation": "Strong positive language detected"
}
```

**Skills learned:**
- Creating workflows with `WorkflowEngine`
- Connecting nodes with input/output mappings
- Using `PromptNode` for prompt engineering
- Calling LLMs with `LLMNode`
- Parsing structured outputs with `ParserNode`

---

### [Tutorial 2: RAG Pipeline](02-rag-pipeline.md)
**Build a document Q&A system with retrieval**

Build a production-ready RAG system that answers questions using your documents:
- 🎯 **Goal:** Create a chatbot that retrieves relevant docs and generates answers
- 🔧 **Nodes Used:** `EmbeddingNode`, `MilvusNode`, `MongoNode`, `RerankNode`, `BasicChainNode`
- 📚 **Concepts:** Vector search, reranking, context injection, template nodes
- ⏱️ **Time:** ~45 minutes
- ⭐ **Level:** Intermediate

**What you'll build:**
```python
Input: "What is our return policy?"
Process:
  1. Embed query → Vector search in Milvus
  2. Retrieve top 10 docs → Rerank to top 3
  3. Fetch full content from MongoDB
  4. Generate answer with context
Output: "Our return policy allows returns within 30 days..."
```

**Skills learned:**
- Working with embeddings and vector databases
- Building retrieval pipelines
- Using `RetrieverNode` (high-level template)
- Implementing reranking for better results
- Context management in prompts

---

### [Tutorial 3: ReAct Agent](03-react-agent.md)
**Build an autonomous agent with tool calling**

Create an intelligent agent that can reason and use tools to solve problems:
- 🎯 **Goal:** Build a math agent that solves complex problems step-by-step
- 🔧 **Nodes Used:** `ReactAgentNode`, `CodeNode`, `ToolExecutorNode`, `WhileLoopNode`
- 📚 **Concepts:** Iterative reasoning, tool calling, error recovery, loop control
- ⏱️ **Time:** ~60 minutes
- ⭐ **Level:** Advanced

**What you'll build:**
```python
Input: "Calculate (15 + 7) * (20 - 5) / 3"
Process:
  Thought: "I need to calculate 15 + 7 first"
  Action: calculator(15 + 7)
  Observation: 22
  
  Thought: "Now I need to calculate 20 - 5"
  Action: calculator(20 - 5)
  Observation: 15
  
  Thought: "Now multiply 22 * 15"
  Action: calculator(22 * 15)
  Observation: 330
  
  Thought: "Finally divide 330 / 3"
  Action: calculator(330 / 3)
  Observation: 110
  
  Answer: "The result is 110"
```

**Skills learned:**
- Building autonomous agents with ReAct pattern
- Creating custom tools with `CodeNode`
- Using `WhileLoopNode` for iterative execution
- Implementing tool calling with `ToolExecutorNode`
- Handling agent errors and max iterations

---

### [Tutorial 4: Batch Processing](04-batch-processing.md)
**Process multiple items in parallel with streaming**

Learn to handle batch operations efficiently with parallel execution:
- 🎯 **Goal:** Process 100 product reviews simultaneously with real-time streaming
- 🔧 **Nodes Used:** `ForLoopNode`, `BranchNode`, `BasicChainNode`
- 📚 **Concepts:** Parallel execution, streaming, context isolation, aggregation
- ⏱️ **Time:** ~40 minutes
- ⭐ **Level:** Intermediate

**What you'll build:**
```python
Input: [
    {"review": "Great product!", "id": 1},
    {"review": "Terrible experience", "id": 2},
    # ... 98 more reviews
]
Process: Analyze each review in parallel
  - Extract sentiment
  - Detect issues
  - Generate response
Output: [
    {"sentiment": "positive", "issues": [], "response": "..."},
    {"sentiment": "negative", "issues": ["quality"], "response": "..."},
    # ... results for all 100
]
```

**Skills learned:**
- Using `ForLoopNode` for batch processing
- Understanding context isolation in loops
- Streaming tokens from multiple parallel executions
- Aggregating results from parallel nodes
- Conditional routing with `BranchNode`

---

### [Tutorial 5: Production Deployment](05-production-deployment.md)
**Deploy your workflow with observability and error handling**

Take your workflow to production with proper monitoring and debugging:
- 🎯 **Goal:** Deploy a production-ready chatbot with full observability
- 🔧 **Focus:** Langfuse integration, error handling, streaming, debugging
- 📚 **Concepts:** Trace hierarchy, error recovery, Redis streaming, production setup
- ⏱️ **Time:** ~60 minutes
- ⭐ **Level:** Advanced

**What you'll build:**
- Complete production workflow with:
  - ✅ Automatic trace hierarchy in Langfuse
  - ✅ Comprehensive error handling
  - ✅ Redis streaming setup
  - ✅ Token usage tracking
  - ✅ Request/session management
  - ✅ Production configuration
  - ✅ Debugging techniques

**Skills learned:**
- Configuring Langfuse for automatic tracing
- Understanding trace hierarchy (spans vs generations)
- Implementing error handling patterns
- Setting up Redis for streaming
- Debugging workflows with traces
- Managing production configurations
- Tracking token usage and costs

---

## 🎯 Choose Your Path

Not sure where to start? Use this guide:

### 👶 **I'm New to Beeflow**
Start with **Tutorial 1** (Basic LLM Chain), then proceed sequentially through all tutorials.

### 🏃 **I've Used LangChain/LangGraph Before**
Skip Tutorial 1, start with **Tutorial 2** (RAG Pipeline) to see Beeflow's unique features.

### 🚀 **I Want to Build Agents**
Complete Tutorials 1-2, then jump to **Tutorial 3** (ReAct Agent).

### 📊 **I Need Batch Processing**
Complete Tutorial 1, then go directly to **Tutorial 4** (Batch Processing).

### 🏭 **I'm Deploying to Production**
Complete Tutorials 1-3, then **Tutorial 5** (Production Deployment).

---

## 📋 Prerequisites

Before starting these tutorials, make sure you have:

### Required Knowledge
- ✅ Python 3.9+ experience
- ✅ Basic async/await understanding
- ✅ Completed the [Quickstart Guide](../quickstart.md)

### System Requirements
- ✅ Redis server running
- ✅ MongoDB instance (Tutorials 2, 5)
- ✅ Milvus instance (Tutorial 2)
- ✅ LLM API key (OpenAI, Azure, or compatible)
- ✅ Langfuse account (Tutorial 5)

### Installation
```bash
pip install beeflow
```

---

## 🛠️ Tutorial Format

Each tutorial follows this structure:

1. **🎯 What You'll Build** - Clear goal and expected output
2. **📚 Prerequisites** - Required knowledge and setup
3. **🏗️ Architecture** - Workflow diagram and explanation
4. **💻 Step-by-Step Guide** - Detailed implementation
5. **🧪 Testing** - How to run and verify your workflow
6. **🚀 Next Steps** - Enhancements and related topics
7. **💡 Key Takeaways** - Summary of concepts learned

---

## 💡 Learning Tips

### 1. **Run the Code**
Don't just read—type out the examples and run them. Hands-on practice is the best way to learn.

### 2. **Experiment**
After completing each tutorial, try modifying the workflow:
- Change prompts
- Add new nodes
- Connect things differently

### 3. **Read the Errors**
Beeflow's error messages are designed to be helpful. When something breaks, read the full error message—it often tells you exactly what's wrong.

### 4. **Check the Traces**
Use Langfuse to visualize your workflow execution. It helps understand data flow and performance.

### 5. **Join the Community**
Get help, share your projects, and learn from others:
- GitHub Discussions
- Discord (coming soon)

---

## 📊 Complexity Matrix

| Tutorial | Lines of Code | Nodes Used | Concepts | Time |
|----------|---------------|------------|----------|------|
| 1. Basic LLM Chain | ~30 | 3 | 5 | 20 min |
| 2. RAG Pipeline | ~60 | 6 | 8 | 45 min |
| 3. ReAct Agent | ~100 | 8 | 12 | 60 min |
| 4. Batch Processing | ~80 | 6 | 10 | 40 min |
| 5. Production | ~100 | 10+ | 12 | 60 min |

---

## 🎓 After Completing Tutorials

Once you finish all tutorials, you'll be able to:
- ✅ Build complex multi-stage LLM workflows
- ✅ Implement RAG systems with retrieval and reranking
- ✅ Create autonomous agents with tool calling
- ✅ Process data in parallel with streaming
- ✅ Deploy workflows with full observability
- ✅ Debug and monitor workflow execution
- ✅ Handle errors gracefully in production

**Next Steps:**
- 📖 Read [Architecture Overview](../concepts/architecture-overview.md) for deeper understanding
- 🔧 Explore [Node Catalog](../reference/node-catalog/) for all available nodes
- 🚀 Check [Advanced Topics](../advanced/) for optimization techniques
- 💻 Study [Examples](../../examples/) for more real-world applications

**Note:** For advanced production features like rate limiting, caching, and horizontal scaling, you'll need to implement these at the application/infrastructure level. Beeflow focuses on workflow orchestration, observability, and execution.

---

## 🆘 Getting Help

Stuck on a tutorial? Here's how to get help:

1. **Check the Troubleshooting section** in each tutorial
2. **Review the [Guides](../guides/)** for specific topics
3. **Search [GitHub Issues](https://github.com/yourusername/beeflow/issues)**
4. **Ask in [GitHub Discussions](https://github.com/yourusername/beeflow/discussions)**
5. **Consult the [API Reference](../reference/api-reference.md)**

---

## 🎉 Ready to Start?

Pick your first tutorial and let's build something amazing!

**→ [Start with Tutorial 1: Basic LLM Chain](01-basic-llm-chain.md)**

---

**Happy Learning! 🚀**