# HumanNode - Frontend Integration Guide

## Overview

`HumanNode` là node cho phép workflow dừng lại chờ input từ người dùng (human-in-the-loop). Khi workflow chạy đến node này, BE sẽ gửi signal đến FE và chờ response.

## Flow

```
┌─────────┐                    ┌─────────┐                    ┌─────────┐
│   BE    │ ──push signal──►   │   FE    │ ──push response──► │   BE    │
│ Workflow│                    │  (User) │                    │ Workflow│
└─────────┘                    └─────────┘                    └─────────┘
     │                              │                              │
     │  SSE (ChatCompletionChunk)   │  {"content": "user answer"} │
     │  type: human_in_the_loop     │                              │
     │  + node                      │                              │
     │  + message                   │                              │
     │  + options                   │                              │
```

## 1. Nhận Signal từ BE

### Redis Channel

- **Signal channel**: `stream:{request_id}:human_request`
- **Response channel**: `stream:{request_id}:human_response:{node_name}`

### Signal Data Structure

BE push data dưới dạng SSE chunk (ChatCompletionChunk format):

```json
{
  "id": "request_id",
  "object": "chat.completion.chunk",
  "model": "node_name",
  "choices": [
    {
      "delta": {
        "content": "{\"type\": \"human_in_the_loop\", \"node\": \"ask_user_confirm\", \"message\": \"Bạn có đồng ý thanh toán 500,000 VND không?\", \"options\": [\"Đồng ý\", \"Từ chối\"]}"
      },
      "index": 0
    }
  ],
  "created": 1700000000
}
```

**Nội dung trong `delta.content`** (parse JSON):

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Luôn là `"human_in_the_loop"` |
| `node` | string | Tên node đang chờ input |
| `message` | string | Câu hỏi hiển thị cho user |
| `options` | array | Danh sách buttons (optional) |

### Code Example (FE - Python)

```python
import asyncio
import json
from beeflow.utils.streaming import STREAM_SERVICE

async def listen_for_human_input(request_id: str):
    """Listen for human_in_the_loop signals."""
    channel = "human_request"

    async for chunk_dict in STREAM_SERVICE.get(request_id, channel, json_mode=True):
        if chunk_dict:
            # Parse the content from delta
            content = chunk_dict.get("content", "")
            if content:
                data = json.loads(content)
                if data.get("type") == "human_in_the_loop":
                    print(f"Node: {data['node']}")
                    print(f"Message: {data['message']}")
                    print(f"Options: {data['options']}")
                    return data
    return None
```

## 2. Gửi Response về BE

### Response Channel

- **Redis key**: `stream:{request_id}:human_response:{node_name}`

### Response Format

```json
{
  "content": "Đồng ý thanh toán"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `content` | string | Response của user |

### Code Example (FE - Python)

```python
import json
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.configs.cache.redis_config import RedisOperation

def send_human_response(request_id: str, node_name: str, user_response: str):
    """Send user response back to workflow."""
    channel = f"human_response:{node_name}"
    redis_key = f"stream:{request_id}:{channel}"

    payload = {"content": user_response}

    STREAM_SERVICE.redis_conn.run(
        operation_type=RedisOperation.LPUSH,
        params={"key": redis_key, "values": [json.dumps(payload)]}
    )
    print(f"Sent response to {channel}: {payload}")
```

## 3. Integration Example (JavaScript/TypeScript)

```javascript
// FE client code using Redis client (ioredis)
class HumanNodeClient {
  constructor(redisClient) {
    this.redis = redisClient;
  }

  async listen(requestId, onHumanInTheLoop) {
    // Listen to human_request channel for signals
    const streamKey = `stream:${requestId}:human_request`;

    // Use BLPOP or subscribe to receive messages
    // The signal comes as a ChatCompletionChunk JSON string in delta.content
    while (true) {
      const message = await this.redis.lpop(streamKey);
      if (message) {
        const chunk = JSON.parse(message);
        const content = chunk.choices?.[0]?.delta?.content;

        if (content) {
          const data = JSON.parse(content);
          if (data.type === "human_in_the_loop") {
            onHumanInTheLoop(data);
          }
        }
      }
      // Small delay to avoid tight loop
      await new Promise(r => setTimeout(r, 100));
    }
  }

  async sendResponse(requestId, nodeName, response) {
    // Push response to human_response channel
    const channel = `human_response:${nodeName}`;
    const redisKey = `stream:${requestId}:${channel}`;
    const payload = JSON.stringify({ content: response });

    await this.redis.lpush(redisKey, payload);
  }
}

// Usage
const client = new HumanNodeClient(redisClient);

client.listen('req_123', async (signal) => {
  // Show modal to user
  const response = await showConfirmationModal(signal.message, signal.options);

  // Send response back
  await client.sendResponse('req_123', signal.node, response);
});
```

## 4. Timeout Handling

| Scenario | Behavior |
|----------|----------|
| User respond in time | Workflow continues with user input |
| Timeout occurs + `default_value` set | Workflow continues with `default_value` |
| Timeout occurs + no `default_value` | Workflow continues with `"TIMEOUT_NO_RESPONSE"` |

**Config timeout**: Set `timeout` parameter (seconds) when creating HumanNode (default: 1s).

## 5. Full Example

```python
import asyncio
import json
from beeflow.nodes.human.human_node import HumanNode
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.workflow_state import WorkflowState
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.configs.cache.redis_config import RedisOperation

async def simulate_frontend(request_id: str, node_name: str, user_response: str):
    """Simulate FE sending user response."""
    channel = f"human_response:{node_name}"
    redis_key = f"stream:{request_id}:{channel}"

    payload = {"content": user_response}
    STREAM_SERVICE.redis_conn.run(
        operation_type=RedisOperation.LPUSH,
        params={"key": redis_key, "values": [json.dumps(payload)]}
    )
    print(f"[Frontend] Sent: {payload}")

async def main():
    request_id = "req_payment_001"

    # Initialize Node
    human_node = HumanNode(
        name="ask_user_confirm",
        message="Xác nhận thanh toán 500,000 VND?",
        options=["Xác nhận", "Hủy"],
        timeout=30
    )

    # Setup indexer and state
    indexer = WorkflowIndexer("payment_workflow").add_node(human_node).build()
    state = WorkflowState(indexer=indexer, request_id=request_id)

    # Simulate FE response (runs in parallel)
    asyncio.create_task(
        simulate_frontend(request_id, human_node.name, "Xác nhận thanh toán")
    )

    # Execute Human Node (blocks until response or timeout)
    print("[*] Executing Node...")
    result = await human_node.run(state)

    print("=== RESULT ===")
    print(f"human_input: {result['human_input']}")

    STREAM_SERVICE.close()

if __name__ == "__main__":
    asyncio.run(main())
```

## 6. HumanNode Input Schema

```python
HumanNode(
    name="node_name",
    message="Question to display to user",      # Required
    options=["Opt1", "Opt2"],                   # Optional: button options
    timeout=30,                                 # Optional: wait time in seconds (default: 1)
    default_value="default response"            # Optional: value if timeout
)
```

## Summary

| Action | Redis Key Pattern | Data Format |
|--------|-------------------|-------------|
| BE → FE signal | `stream:{request_id}:human_request` | SSE chunk with JSON in `delta.content` |
| FE → BE response | `stream:{request_id}:human_response:{node_name}` | `{"content": "..."}` |

**Output**: HumanNode returns `{"human_input": "user response or timeout value"}`
