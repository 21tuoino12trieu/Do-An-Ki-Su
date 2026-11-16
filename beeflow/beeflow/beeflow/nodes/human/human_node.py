import asyncio
import json
import time
from typing import Dict, Any

from openai.types.chat.chat_completion_chunk import ChatCompletionChunk, Choice, ChoiceDelta

from beeflow.nodes.base_node import BaseNode
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.loggings.loggers import LOGGER
from beegen.tools.schema.param import ParamSet, Param
from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.workflow_state import WorkflowState
from beegen.configs.cache.redis_config import RedisOperation

class HumanNode(BaseNode):
    type = "human"
    
    def __init__(self, **kwargs):
        # Extend input_schema to receive more configurations from Workflow
        if "input_schema" not in kwargs:
            kwargs["input_schema"] = {
                "message": Param(type="str", description="Question displayed to the User"),
                "options": Param(type="list", description="List of buttons (if any)"),
                "timeout": Param(type="int", description="Maximum wait time (seconds)", default=1),
                "default_value": Param(type="str", description="Default value if timeout occurs")
            }
        
        if "output_schema" not in kwargs:
            kwargs["output_schema"] = {"human_input": Param(type="str")}
            
        super().__init__(**kwargs)

    async def run(self, state: WorkflowState, context_id: str = None) -> Dict[str, Any]:
        parent_name = self.father.full_name if self.father else None
        state.record_execution(self.full_name, parent_name, context_id)
        
        request_id = state.request_id
        input_channel = f"human_response:{self.name}"
        
        # --- GET INPUTS FROM STATE OR USE DEFAULT VALUES ---
        _inputs = self.get_inputs(state, context_id)
        display_message = _inputs.get("message") or "Waiting for user confirmation..."
        options = _inputs.get("options") or []
        timeout = _inputs.get("timeout")
        default_value = _inputs.get("default_value")
        
        # 1. Notify Frontend that it's waiting for input along with the configuration
        signal_data = {
            "type": "human_in_the_loop", 
            "node": self.name, 
            "message": display_message,
            "options": options
        }
        
        chunk = ChatCompletionChunk(
            id=request_id,
            choices=[Choice(delta=ChoiceDelta(content=json.dumps(signal_data)), index=0)],
            created=int(time.time()),
            model=self.name,
            object="chat.completion.chunk"
        )
        
        await STREAM_SERVICE.push(
            request_id=request_id, 
            channel_name="human_request", 
            data=chunk
        )
        LOGGER.info(f"Node {self.name} is waiting for input from Redis channel: {input_channel} (Timeout: {timeout}s)")

        human_response = None
        
        # 2. Internal function to listen to Redis
        async def listen_to_redis():
            async for chunk_dict in STREAM_SERVICE.get(request_id, input_channel, json_mode=True):
                if chunk_dict:
                    return chunk_dict.get("content", chunk_dict)
            return None

        # 3. Wait for Frontend to push data (Timeout applied)
        try:
            human_response = await asyncio.wait_for(listen_to_redis(), timeout=timeout)
            LOGGER.info(f"Node {self.name} received input: {human_response}. Resuming execution!")
            
        except asyncio.TimeoutError:
            LOGGER.warning(f"Node {self.name} has timed out ({timeout}s).")

            try:
                await STREAM_SERVICE.end(request_id, input_channel)
            except Exception as cleanup_err:
                LOGGER.warning(f"Node {self.name}: cleanup after timeout failed: {cleanup_err}")

            # Assign default value if any, otherwise return an error string
            human_response = default_value if default_value is not None else "TIMEOUT_NO_RESPONSE"

        # 4. Return result to the graph
        _outputs = {"human_input": human_response}
        self.store_result(state, _outputs, context_id)
        
        return _outputs

async def simulate_frontend(request_id: str, node_name: str):
    """
    Simulates a Frontend process (Web/App) of the user.
    Will delay for a few seconds, then push the user's answer into Redis.
    """
    # await asyncio.sleep(1)
    print("\n[Frontend] User is typing the answer...")
    
    channel_name = f"human_response:{node_name}"
    
    # Payload that Frontend sends up
    user_reply = {
        "content": "I confirm and agree to pay this amount!"
    }
    
    # Push directly to Redis so HumanNode can catch it (exactly how STREAM_SERVICE.push does it under the hood)
    redis_key = f"stream:{request_id}:{channel_name}"
    STREAM_SERVICE.redis_conn.run(
        operation_type=RedisOperation.LPUSH,
        params={"key": redis_key, "values": [json.dumps(user_reply)]}
    )
    
    print(f"[Frontend] Sent response: '{user_reply['content']}' to channel {channel_name}\n")


async def test_human_node():
    print("=== START TESTING HUMAN NODE ===")
    
    # 1. Initialize Node
    human_node = HumanNode(name="ask_user_confirm")
    
    # 2. Create Indexer and attach Node to the graph
    indexer = WorkflowIndexer("test_workflow").add_node(human_node).build()
    
    # 3. Initialize State
    # Assign a fixed request_id to make testing the Redis flow easier to control
    state = WorkflowState(
        indexer=indexer,
        request_id="req_test_human_999"
    )
    
    print(f"[*] Request ID: {state.request_id}")
    
    # 4. Activate the simulated Frontend process (running asynchronously in parallel)
    asyncio.create_task(simulate_frontend(state.request_id, human_node.name))
    
    # 5. Execute Human Node (it will be blocked here waiting for the Frontend)
    print("[*] Executing Node...")
    result = await human_node.run(state)
    
    # 6. Print the result
    print("=== EXECUTION RESULT ===")
    print("Output Dict:", result)

    print("=== STATE STATUS ===")
    state.show()
    
    # Check if the state has actually saved the data (workflow name is 'test_workflow')
    saved_value = state[human_node.name, "human_input", None]
    print("Value saved in State:", saved_value)
    
    # Clean up Streaming service
    STREAM_SERVICE.close()

if __name__ == "__main__":
    asyncio.run(test_human_node())