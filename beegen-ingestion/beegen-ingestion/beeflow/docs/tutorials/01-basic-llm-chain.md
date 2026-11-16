# Tutorial 1: Basic LLM Chain

**Build a sentiment analyzer with structured output**

⏱️ **Time:** ~20 minutes  
⭐ **Level:** Beginner  
🔧 **Nodes:** `PromptNode`, `LLMNode`, `ParserNode`

---

## 🎯 What You'll Build

In this tutorial, you'll create a sentiment analysis workflow that:
- Takes user reviews as input
- Analyzes sentiment and confidence
- Returns structured, parsed output

**Input:**
```python
"I absolutely love this product! It exceeded all my expectations."
```

**Output:**
```python
{
    "sentiment": "positive",
    "confidence": 0.95,
    "explanation": "Strong positive language with words like 'love' and 'exceeded expectations'"
}
```

---

## 📚 Prerequisites

Before starting, make sure you have:

### ✅ Completed
- [Quickstart Guide](../quickstart.md)

### ✅ Knowledge
- Basic Python (functions, async/await)
- Understanding of what an LLM is

### ✅ System Requirements
- Python 3.9+
- LLM API key (OpenAI, Azure, or compatible)
- Beeflow installed: `pip install beeflow`

---

## 🏗️ Architecture

Our workflow has three nodes in a linear chain:

```
┌────────────────────────────────────────────────────────────┐
│                    INPUT: review text                      │
└────────────────────────┬───────────────────────────────────┘
                         │
                         ↓
┌────────────────────────────────────────────────────────────┐
│  PromptNode: "prompt"                                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Takes review text                                    │  │
│  │ Formats it into a structured prompt                  │  │
│  │ Outputs: messages (list of chat messages)            │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────┬───────────────────────────────────┘
                         │ messages
                         ↓
┌────────────────────────────────────────────────────────────┐
│  LLMNode: "llm"                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Receives formatted messages                          │  │
│  │ Calls GPT-4 to analyze sentiment                     │  │
│  │ Outputs: content (raw LLM response text)             │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────┬───────────────────────────────────┘
                         │ content
                         ↓
┌────────────────────────────────────────────────────────────┐
│  ParserNode: "parser"                                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Receives raw LLM text                                │  │
│  │ Extracts sentiment, confidence, explanation          │  │
│  │ Outputs: structured data                             │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────┬───────────────────────────────────┘
                         │
                         ↓
┌────────────────────────────────────────────────────────────┐
│              OUTPUT: structured sentiment data             │
└────────────────────────────────────────────────────────────┘
```

**Key Concepts:**
1. **Linear Flow**: Each node processes data and passes it to the next
2. **Variable References**: Nodes connect via `inputs={"var": previous_node}`
3. **Structured Output**: Parser extracts specific fields from LLM text

---

## 💻 Step-by-Step Implementation

### Step 1: Setup and Imports

Create a new file `sentiment_analyzer.py`:

```python
import asyncio
from beeflow import WorkflowEngine
from beeflow.nodes import (
    PromptNode, 
    LLMNode, 
    ParserNode,
    START, 
    END, 
    INPUT, 
    OUTPUT
)

# We'll build the workflow here
```

---

### Step 2: Configure Your LLM Provider

Before creating the workflow, set up your LLM:

```python
from beegen.registry import ResourceHub
from beegen.configs import OpenAIConfig

# Configure OpenAI (or your preferred provider)
ResourceHub.register_llm(
    key="gpt-4o",
    config=OpenAIConfig(
        api_key="sk-...",  # Your API key
        model="gpt-4o"
    )
)
```

> **💡 Tip:** For other providers (Azure, local models), check the [Configuration Guide](../reference/configuration.md)

---

### Step 3: Design Your Prompt

Good prompts are key to good results. Here's our sentiment analysis prompt:

```python
SENTIMENT_PROMPT = """Analyze the sentiment of this review and provide a structured response.

Review: {review}

Return your analysis in this XML format:
<sentiment>positive/negative/neutral</sentiment>
<confidence>0.0 to 1.0</confidence>
<explanation>Brief explanation of your analysis</explanation>

Be precise and objective in your analysis."""
```

**Why this works:**
- ✅ Clear instructions
- ✅ Specific output format (XML)
- ✅ Variable placeholder `{review}` for dynamic content
- ✅ Confidence score for reliability

---

### Step 4: Build the Workflow

Now let's put it all together:

```python
async def main():
    # Create the workflow engine
    with WorkflowEngine(name="sentiment-analyzer") as workflow:
        
        # Node 1: Format the prompt
        prompt = PromptNode(
            name="prompt",
            user_prompt=SENTIMENT_PROMPT,
            inputs={"review": INPUT}  # Connect to workflow input
        )
        
        # Node 2: Call the LLM
        llm = LLMNode(
            name="llm",
            resource_key="gpt-4o",
            inputs={"messages": prompt}  # Connect to prompt output
        )
        
        # Node 3: Parse the response
        parser = ParserNode(
            name="parser",
            format="xml",  # We specified XML in the prompt
            extract_schema=[
                "sentiment: str",
                "confidence: float", 
                "explanation: str"
            ],
            inputs={"text": llm["content"]},  # Connect to LLM output
            outputs=OUTPUT  # Send to workflow output
        )
        
        # Define the execution flow
        START >> prompt >> llm >> parser >> END
    
    # Compile the workflow (creates index mappings)
    workflow.compile()
    
    return workflow

# Run it
if __name__ == "__main__":
    workflow = asyncio.run(main())
```

**Let's break down what's happening:**

#### PromptNode
```python
prompt = PromptNode(
    name="prompt",
    user_prompt=SENTIMENT_PROMPT,
    inputs={"review": INPUT}
)
```
- Takes `review` from workflow input
- Formats it into the prompt template
- Outputs `messages` (list of chat messages)

#### LLMNode
```python
llm = LLMNode(
    name="llm",
    resource_key="gpt-4o",
    inputs={"messages": prompt}
)
```
- Receives `messages` from prompt node (same-name connection)
- Calls GPT-4 with those messages
- Outputs `content` (the LLM's text response)

#### ParserNode
```python
parser = ParserNode(
    name="parser",
    format="xml",
    extract_schema=[
        "sentiment: str",
        "confidence: float",
        "explanation: str"
    ],
    inputs={"text": llm["content"]},
    outputs=OUTPUT
)
```
- Receives `content` from LLM (specific variable connection)
- Parses XML to extract the three fields
- Sends results to workflow output

#### Flow Definition
```python
START >> prompt >> llm >> parser >> END
```
- Defines execution order
- Each node runs after the previous completes
- Data flows through variable connections

---

### Step 5: Run Your Workflow

Add the execution code:

```python
async def main():
    # ... workflow creation code from above ...
    
    workflow.compile()
    
    # Test with a positive review
    result = await workflow.run(
        inputs={"review": "I absolutely love this product! It exceeded all my expectations."}
    )
    
    print("Result:")
    print(f"  Sentiment: {result['sentiment']}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Explanation: {result['explanation']}")
    
    return workflow

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 🧪 Testing Your Workflow

### Test Case 1: Positive Review

```python
result = await workflow.run(
    inputs={"review": "Amazing quality! Best purchase I've made this year."}
)

# Expected output:
# Sentiment: positive
# Confidence: 0.92
# Explanation: Strong positive language with superlatives like 'amazing' and 'best'
```

### Test Case 2: Negative Review

```python
result = await workflow.run(
    inputs={"review": "Terrible experience. Product broke after one day."}
)

# Expected output:
# Sentiment: negative
# Confidence: 0.95
# Explanation: Clear negative sentiment with words like 'terrible' and 'broke'
```

### Test Case 3: Neutral Review

```python
result = await workflow.run(
    inputs={"review": "The product is okay. It works as described."}
)

# Expected output:
# Sentiment: neutral
# Confidence: 0.88
# Explanation: Neutral tone with balanced assessment
```

---

## 🔍 Understanding the Data Flow

Let's trace what happens when you run the workflow:

### 1. Input Stage
```python
inputs={"review": "I love this product!"}
```
- Workflow receives the input
- Stored in workflow state at `workflow["review"]`

### 2. PromptNode Execution
```python
# Input: review = "I love this product!"
# Process: Format into prompt template
# Output: messages = [
#     {"role": "user", "content": "Analyze the sentiment of this review...\nReview: I love this product!\n..."}
# ]
```

### 3. LLMNode Execution
```python
# Input: messages = [{"role": "user", "content": "..."}]
# Process: Call GPT-4 API
# Output: content = "<sentiment>positive</sentiment>\n<confidence>0.9</confidence>\n<explanation>...</explanation>"
```

### 4. ParserNode Execution
```python
# Input: text = "<sentiment>positive</sentiment>..."
# Process: Parse XML, extract fields
# Output: {
#     "sentiment": "positive",
#     "confidence": 0.9,
#     "explanation": "Strong positive language detected"
# }
```

### 5. Final Output
```python
result = {
    "sentiment": "positive",
    "confidence": 0.9,
    "explanation": "Strong positive language detected"
}
```

---

## 🎨 Visualizing Variable Connections

Here's how the variables flow through your workflow:

```
Workflow State (Zero-Copy Index Array)
┌─────────────────────────────────────────┐
│ Index │ Variable              │ Value   │
├───────┼───────────────────────┼─────────┤
│   0   │ workflow.review       │ "I..." ←─── INPUT
│   1   │ prompt.review         │ same[0] │
│   2   │ prompt.messages       │ [...]   │
│   3   │ llm.messages          │ same[2] │
│   4   │ llm.content           │ "<s..." │
│   5   │ parser.text           │ same[4] │
│   6   │ parser.sentiment      │ "pos"  ───→ OUTPUT
│   7   │ parser.confidence     │ 0.9    ───→ OUTPUT
│   8   │ parser.explanation    │ "St..." ──→ OUTPUT
└─────────────────────────────────────────┘
```

Notice:
- `prompt.review` points to same index as `workflow.review` (index 0)
- `llm.messages` points to same index as `prompt.messages` (index 2)
- **Zero data copying** - just index references!

---

## 🚨 Troubleshooting

### Issue 1: "No LLM provider configured"

**Error:**
```
KeyError: 'gpt-4o'
```

**Solution:**
Make sure you called `ResourceHub.register_llm()` before creating the workflow.

---

### Issue 2: Parser can't extract fields

**Error:**
```
parser.sentiment = None
```

**Cause:** LLM didn't return proper XML format.

**Solution:** Make your prompt more explicit:
```python
SENTIMENT_PROMPT = """...

IMPORTANT: You MUST return your response in this exact XML format:
<sentiment>positive/negative/neutral</sentiment>
<confidence>0.0 to 1.0</confidence>
<explanation>Your explanation here</explanation>

Do not add any other text outside these XML tags."""
```

---

### Issue 3: Workflow not running

**Error:**
```
ValueError: Workflow not compiled
```

**Solution:** Always call `workflow.compile()` before `workflow.run()`:
```python
workflow.compile()  # Don't forget this!
result = await workflow.run(...)
```

---

## 🚀 Enhancements & Next Steps

### Enhancement 1: Add System Prompt

Give the LLM better context:

```python
prompt = PromptNode(
    name="prompt",
    system_prompt="You are an expert sentiment analyst. Provide accurate, unbiased analysis.",
    user_prompt=SENTIMENT_PROMPT,
    inputs={"review": INPUT}
)
```

### Enhancement 2: Handle Multiple Reviews

Process a batch of reviews:

```python
reviews = [
    "Great product!",
    "Terrible service.",
    "It's okay."
]

results = []
for review in reviews:
    result = await workflow.run(inputs={"review": review})
    results.append(result)
```

**Better approach:** Use `ForLoopNode` (see [Tutorial 4: Batch Processing](04-batch-processing.md))

### Enhancement 3: Add Aspect-Based Analysis

Extract sentiment about specific aspects:

```python
extract_schema=[
    "overall_sentiment: str",
    "product_quality: str",
    "customer_service: str",
    "value_for_money: str",
    "confidence: float"
]
```

### Enhancement 4: Add Validation

Use a `BranchNode` to validate confidence:

```python
validator = BranchNode(
    name="validator",
    cases={
        "confidence > 0.8": "high_confidence_path",
        "confidence > 0.5": "medium_confidence_path"
    },
    default="low_confidence_path",
    inputs={"confidence": parser}
)
```

---

## 💡 Key Takeaways

Congratulations! You've built your first Beeflow workflow. Here's what you learned:

### ✅ Core Concepts
1. **WorkflowEngine** - Container for your workflow
2. **Node Types** - PromptNode, LLMNode, ParserNode
3. **Variable Connections** - `inputs`, `outputs`, `INPUT`, `OUTPUT`
4. **Flow Definition** - Using `>>` operator
5. **Compilation** - `workflow.compile()` before running

### ✅ Best Practices
- ✅ Use clear, structured prompts
- ✅ Specify output format in prompts (XML, JSON)
- ✅ Always compile before running
- ✅ Test with diverse inputs
- ✅ Handle edge cases

### ✅ Beeflow Advantages
- 🚀 **Declarative** - Define what you want, not how
- 🔗 **Type-Safe** - Schema validation for inputs/outputs
- 📊 **Observable** - Automatic tracing (we'll explore in Tutorial 5)
- ⚡ **Efficient** - Zero-copy variable sharing

---

## 📚 What's Next?

Now that you understand the basics, you can:

1. **Tutorial 2: RAG Pipeline** - Build a document Q&A system
   - Learn vector search and retrieval
   - Work with databases (Milvus, MongoDB)
   - Implement reranking

2. **Explore More Nodes** - Check the [Node Catalog](../reference/node-catalog/)
   - Transform nodes (CodeNode, LambdaNode)
   - Flow control (BranchNode, ForLoopNode)
   - Data nodes (MilvusNode, MongoNode)

3. **Read Concepts** - [Architecture Overview](../concepts/architecture-overview.md)
   - Understand zero-copy state management
   - Learn about the execution model
   - Deep dive into the indexer

---

## 📝 Complete Code

Here's the full working code:

```python
import asyncio
from beeflow import WorkflowEngine
from beeflow.nodes import (
    PromptNode, 
    LLMNode, 
    ParserNode,
    START, 
    END, 
    INPUT, 
    OUTPUT
)
from beegen.registry import ResourceHub
from beegen.configs import OpenAIConfig

# Configure LLM
ResourceHub.register_llm(
    key="gpt-4o",
    config=OpenAIConfig(
        api_key="sk-...",
        model="gpt-4o"
    )
)

# Define prompt
SENTIMENT_PROMPT = """Analyze the sentiment of this review and provide a structured response.

Review: {review}

Return your analysis in this XML format:
<sentiment>positive/negative/neutral</sentiment>
<confidence>0.0 to 1.0</confidence>
<explanation>Brief explanation of your analysis</explanation>

Be precise and objective in your analysis."""

async def main():
    # Create workflow
    with WorkflowEngine(name="sentiment-analyzer") as workflow:
        prompt = PromptNode(
            name="prompt",
            user_prompt=SENTIMENT_PROMPT,
            inputs={"review": INPUT}
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
                "confidence: float",
                "explanation: str"
            ],
            inputs={"text": llm["content"]},
            outputs=OUTPUT
        )
        
        START >> prompt >> llm >> parser >> END
    
    workflow.compile()
    
    # Run test
    result = await workflow.run(
        inputs={"review": "I absolutely love this product!"}
    )
    
    print("Result:")
    print(f"  Sentiment: {result['sentiment']}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Explanation: {result['explanation']}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

**🎉 Great job completing Tutorial 1! Ready for Tutorial 2?**

**→ [Next: Tutorial 2 - RAG Pipeline](02-rag-pipeline.md)**