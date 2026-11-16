# Transform Nodes

**Data processing, parsing, and document handling**

---

## CodeNode

**Purpose:** Execute custom Python functions for data transformation.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code_fn` | Callable | ✓ | Function to execute |
| `return_keys` | List[str] | - | Output schema (if not in docstring) |
| `inputs` | dict | - | Input variable mappings |
| `outputs` | dict | - | Output variable mappings |

### Example: Simple Transform

```python
def calculate_metrics(products: List[Dict]) -> Dict[str, Any]:
    """Calculate product metrics.
    
    Args:
        products: List of product dicts
        
    Returns:
        total_price (float): Sum of prices
        avg_price (float): Average price
        count (int): Number of products
    """
    total = sum(p.get('price', 0) for p in products)
    return {
        'total_price': total,
        'avg_price': total / len(products) if products else 0,
        'count': len(products)
    }

code = CodeNode(
    name="metrics",
    code_fn=calculate_metrics,
    inputs={"products": INPUT}
)
```

### Example: With External Libraries

```python
def process_dataframe(data: List[Dict]) -> Dict:
    """Process data using pandas."""
    import pandas as pd
    
    df = pd.DataFrame(data)
    df['normalized'] = (df['value'] - df['value'].mean()) / df['value'].std()
    
    return {
        "result": df.to_dict('records'),
        "stats": {
            "mean": df['value'].mean(),
            "std": df['value'].std()
        }
    }

code = CodeNode(code_fn=process_dataframe, inputs=INPUT)
```

### Notes

- **Docstring schemas** auto-detected (Google/NumPy style)
- Use `return_keys` if no docstring: `["result: Dict", "count: int"]`
- Sync and async functions both supported
- Input schema auto-detected from function signature

---

## LambdaNode

**Purpose:** Quick inline transformations without function definition.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code_fn` | lambda | ✓ | Lambda function |
| `return_keys` | List[str] | ✓ | Output variable types |

### Example: Simple Lambda

```python
# Extract field
extract = LambdaNode(
    name="extract_id",
    code_fn=lambda doc: {"id": doc.get("_id")},
    return_keys=["id: str"],
    inputs={"doc": mongo["data"][0]}
)

# Calculate expression
calc = LambdaNode(
    code_fn=lambda a, b: {"result": a * b + 10},
    return_keys=["result: float"],
    inputs={"a": INPUT["x"], "b": INPUT["y"]}
)
```

### Example: List Processing

```python
# Filter and map
process = LambdaNode(
    code_fn=lambda items: {
        "filtered": [x for x in items if x['score'] > 0.5],
        "count": len(items)
    },
    return_keys=["filtered: List", "count: int"],
    inputs={"items": search_results}
)
```

### Notes

- **Always requires `return_keys`** (cannot infer from lambda)
- Best for **simple one-liners**
- Use CodeNode for complex logic

---

## ParserNode

**Purpose:** Extract structured data from LLM text outputs.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `extract_schema` | List[str] | ✓ | Fields to extract |
| `format` | ParserType | - | Format (default: xml) |
| `inputs` | dict | - | Must include `text` |

### Supported Formats

```python
from beegen.configs import ParserType

ParserType.XML       # <tag>value</tag>
ParserType.JSON      # {"key": "value"}
ParserType.YAML      # key: value
```

### Example: XML Parsing

```python
parser = ParserNode(
    name="extract",
    format="xml",
    extract_schema=["sentiment: str", "confidence: float"],
    inputs={"text": llm["content"]}
)

# Input text:
# <sentiment>positive</sentiment>
# <confidence>0.95</confidence>

# Output: {"sentiment": "positive", "confidence": 0.95}
```

### Example: Nested Fields

```python
parser = ParserNode(
    extract_schema=[
        "user.name: str",           # Extracts nested field
        "user.age: int",
        "company.address.city: str"
    ],
    inputs={"text": llm["content"]}
)

# Input (JSON):
# {"user": {"name": "John", "age": 30}, "company": {"address": {"city": "NYC"}}}

# Output: {"name": "John", "age": 30, "city": "NYC"}
```

### Notes

- **Nested paths** supported: `"parent.child.field: type"`
- **Type casting** automatic: `str`, `int`, `float`, `bool`, `List`, `Dict`
- Use with LLM outputs for structured extraction

---

## PromptNode

**Purpose:** Build LLM message arrays from templates.

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `user_prompt` | str | User message template |
| `system_prompt` | str | System message template |
| `messages_template` | List[Dict] | Complex multi-message template |

### Example: Simple Prompts

```python
prompt = PromptNode(
    name="format",
    system_prompt="You are a helpful assistant.",
    user_prompt="Analyze: {query} with context {docs}",
    inputs={
        "query": INPUT["query"],
        "docs": retriever["docs"]
    }
)

# Output: {"messages": [
#   {"role": "system", "content": "You are..."},
#   {"role": "user", "content": "Analyze: ..."}
# ]}
```

### Example: With History

```python
prompt = PromptNode(
    user_prompt="Continue: {new_message}",
    inputs={
        "new_message": INPUT["query"],
        "conversation_history": INPUT["history"]  # Auto-inserted
    }
)

# History automatically inserted before user message
```

### Example: Vision Messages

```python
prompt = PromptNode(
    messages_template=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze: {task}"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,{image}"}}
            ]
        }
    ],
    inputs={
        "task": INPUT["task"],
        "image": INPUT["image_b64"]
    }
)
```

### Notes

- **Variables** in `{braces}` auto-detected
- **conversation_history** auto-inserted if provided
- **tool_results** auto-appended if provided

---

## DocumentIONode

**Purpose:** Convert documents (PDF, images) to text/images for processing.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `document_type` | DocumentType | PDF | Input type |
| `output_format` | OutputFormat | TEXT | Output format |
| `max_dimension` | int | 1200 | Image resize limit |

### Example: PDF to Text

```python
doc_io = DocumentIONode(
    name="pdf_reader",
    document_type="pdf",
    output_format="text",
    inputs={"path": INPUT["pdf_path"]}
)

# Output: {
#   "document_name": "file.pdf",
#   "total_pages": 10,
#   "pages": [
#     {"page_number": 1, "text_data": "...", "width": 595, "height": 842},
#     ...
#   ]
# }
```

### Example: Image to Base64

```python
doc_io = DocumentIONode(
    document_type="image",
    output_format="base64",
    max_dimension=800,
    inputs={"path": INPUT["image_path"]}
)

# Use with vision LLM
prompt = PromptNode(
    messages_template=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe image"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{doc_io['pages'][0]['image_data']}"}}
        ]
    }]
)
```

### Notes

- **Supports:** PDF, JPEG, PNG, BMP, TIFF
- **Outputs:** TEXT, BASE64, NUMPY
- Use for OCR, vision tasks, document processing

---

## DataNode

**Purpose:** Store/pass data without processing (checkpoint/hub).

### Example

```python
# Store intermediate results
checkpoint = DataNode(
    name="checkpoint",
    inputs={
        "query": INPUT["query"],
        "results": search["results"],
        "timestamp": INPUT["timestamp"]
    }
)

# Fan-out to multiple consumers
node_a = NodeA(inputs={"data": checkpoint["results"]})
node_b = NodeB(inputs={"data": checkpoint["results"]})
node_c = NodeC(inputs={"query": checkpoint["query"]})
```

### Notes

- **Pass-through:** Output = Input
- Use for **data checkpoints** or **fan-out hubs**

---

## 💡 Common Patterns

### Pattern: LLM → Parse → Transform

```python
# Generate structured output
llm = LLMNode(
    user_prompt="Extract entities from: {text}",
    inputs=INPUT
)

# Parse to structured data
parser = ParserNode(
    extract_schema=["entities: List", "count: int"],
    inputs={"text": llm["content"]}
)

# Transform for next step
transform = CodeNode(
    code_fn=lambda entities: {
        "entity_ids": [e['id'] for e in entities],
        "names": [e['name'] for e in entities]
    },
    inputs={"entities": parser["entities"]}
)
```

### Pattern: Batch Transform

```python
def batch_normalize(items: List) -> Dict:
    """Normalize batch of items."""
    import numpy as np
    values = [x['score'] for x in items]
    mean, std = np.mean(values), np.std(values)
    
    return {
        "normalized": [
            {**item, 'norm_score': (item['score'] - mean) / std}
            for item in items
        ]
    }

normalize = CodeNode(code_fn=batch_normalize, inputs={"items": search})
```

### Pattern: Document Processing Pipeline

```python
# Read document
reader = DocumentIONode(
    document_type="pdf",
    output_format="base64",
    inputs={"path": INPUT["pdf_path"]}
)

# Extract images for each page
extract_pages = LambdaNode(
    code_fn=lambda pages: {
        "images": [p['image_data'] for p in pages]
    },
    return_keys=["images: List"],
    inputs={"pages": reader["pages"]}
)

# Process with vision LLM in loop
with ForLoopNode(inputs={"batch_data": extract_pages["images"]}) as loop:
    prompt = PromptNode(messages_template=[...])
    vlm = LLMNode(inputs={"messages": prompt})
    START >> prompt >> vlm >> END
```

---

## 📚 Related

- [AI Nodes](ai-nodes.md) - LLM, Embedding nodes
- [Flow Control](flow-control.md) - Loops, branches
- [Templates](templates.md) - Pre-built pipelines
- [Tutorial: RAG Pipeline](../../tutorials/02-rag-pipeline.md)

---

[← Back to Node Catalog](_index.md)