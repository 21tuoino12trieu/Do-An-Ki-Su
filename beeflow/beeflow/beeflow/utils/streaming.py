import asyncio
import json
from typing import AsyncGenerator
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from beegen.registry.resource_hub import RESOURCE_HUB
from beegen.configs.cache.redis_config import RedisOperation
from beegen.loggings import LOGGER

# --- add near the top of the file (after imports) ---
def _unwrap_value(res):
    """
    Accepts either a normalized dict ({"values": ...}) or a raw value.
    Returns the scalar value or None.
    """
    if isinstance(res, dict):
        # normalized engine outputs
        if "value" in res:
            return res["value"]
        # sometimes LRANGE/ZRANGE/SCAN might be misrouted here
        for k in ("values", "members", "keys"):
            if k in res:
                return res[k]
        return None
    return res


def _unwrap_values(res):
    """
    Accepts either a normalized dict ({"values": [...]}) or a raw list.
    Returns a list (default []).
    """
    if isinstance(res, dict):
        for k in ("values", "members", "keys"):
            if k in res and isinstance(res[k], list):
                return res[k]
        # scalar value case (shouldn't happen here, but safe)
        if "value" in res:
            v = res["value"]
            return v if isinstance(v, list) else ([] if v is None else [v])
        return []
    # raw list from a low-level client
    return res if isinstance(res, list) else ([] if res is None else [res])

class TokenStreamingService:
    """Singleton service for streaming ChatCompletionChunk tokens via Redis."""
    
    def __init__(self, registry_key):
        self.redis_conn = RESOURCE_HUB.redis(registry_key)
        LOGGER.info(f"StreamingService {registry_key} initialized")
    
    async def push(self, request_id: str, channel_name: str, data: ChatCompletionChunk) -> None:
        """Push a ChatCompletionChunk to the specified Redis channel."""
        if not request_id:
            raise ValueError("request_id cannot be None or empty")
            
        try:
            # Register channel name in LIST (only once per channel)
            # Check if channel already registered to avoid duplicates
            registry_key = f"registry:{request_id}"
            existing_res = self.redis_conn.run(
                operation_type=RedisOperation.LRANGE,
                params={"key": registry_key, "start": 0, "stop": -1}
            )
            existing = _unwrap_values(existing_res)

            if not existing or channel_name not in existing:
                self.redis_conn.run(
                    operation_type=RedisOperation.LPUSH,
                    params={"key": registry_key, "values": [channel_name]}
                )
            
            # Push data to stream
            chunk_json = json.dumps(data.model_dump())
            self.redis_conn.run(
                operation_type=RedisOperation.LPUSH,
                params={"key": f"stream:{request_id}:{channel_name}", "values": [chunk_json]}
            )
            
        except Exception as e:
            LOGGER.error(f"Error pushing chunk to {channel_name}: {e}")
            raise
    
    async def end(self, request_id: str, channel_name: str) -> None:
        """Push end signal to indicate channel streaming completion."""
        if not request_id:
            raise ValueError("request_id cannot be None or empty")
            
        try:
            self.redis_conn.run(
                operation_type=RedisOperation.LPUSH,
                params={"key": f"stream:{request_id}:{channel_name}", "values": ["END"]}
            )
            LOGGER.debug(f"Pushed END signal to channel: {channel_name}")
        except Exception as e:
            LOGGER.error(f"Error pushing END signal to {channel_name}: {e}")
            raise
    
    async def end_request(self, request_id: str) -> None:
        """Push end signal to indicate all channels for this request are complete."""
        if not request_id:
            raise ValueError("request_id cannot be None or empty")
            
        try:
            self.redis_conn.run(
                operation_type=RedisOperation.LPUSH,
                params={"key": f"registry:{request_id}", "values": ["END"]}
            )
            LOGGER.debug(f"Pushed END signal to request: {request_id}")
        except Exception as e:
            LOGGER.error(f"Error pushing END signal to request {request_id}: {e}")
            raise
    
    async def get_channels(self, request_id: str, sleep=0.01) -> AsyncGenerator[str, None]:
        """Discover and yield channel names as they become available."""
        if not request_id:
            raise ValueError("request_id cannot be None or empty")
            
        registry_key = f"registry:{request_id}"
        seen_channels = set()
        
        try:
            while True:
                # LRANGE to get all items from LIST
                members_res = self.redis_conn.run(
                    operation_type=RedisOperation.LRANGE,
                    params={"key": registry_key, "start": 0, "stop": -1}
                )
                members = _unwrap_values(members_res)
                
                if members and "END" in members:
                    for channel in members:
                        if channel != "END" and channel not in seen_channels:
                            seen_channels.add(channel)
                            yield channel
                    break
                
                if members:
                    for channel in members:
                        if channel not in seen_channels:
                            seen_channels.add(channel)
                            yield channel
                
                await asyncio.sleep(sleep)
                
        except Exception as e:
            LOGGER.error(f"Error discovering channels for {request_id}: {e}")
            raise
    
    async def get(self, request_id: str, channel_name: str, json_mode=False, sleep=0.01) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Get AsyncGenerator for consuming chunks from the specified channel."""
        if not request_id:
            raise ValueError("request_id cannot be None or empty")
            
        stream_key = f"stream:{request_id}:{channel_name}"
        
        try:
            while True:
                popped_res = self.redis_conn.run(
                    operation_type=RedisOperation.RPOP,
                    params={"key": stream_key}
                )
                chunk_data = _unwrap_value(popped_res)

                if chunk_data is None:
                    await asyncio.sleep(sleep)
                    continue
                
                if chunk_data == "END":
                    break
                
                try:
                    chunk_dict = json.loads(chunk_data)
                    if not json_mode:
                        chunk = ChatCompletionChunk(**chunk_dict)
                        yield chunk
                    else:
                        yield chunk_dict
                except Exception as e:
                    LOGGER.warning(f"Failed to deserialize chunk: {e}")
                    continue
                    
        except Exception as e:
            LOGGER.error(f"Error consuming from {channel_name}: {e}")
            raise
        finally:
            try:
                self.redis_conn.run(
                    operation_type=RedisOperation.DELETE,
                    params={"keys": [stream_key]}
                )
            except Exception as e:
                LOGGER.warning(f"Failed to cleanup stream key {stream_key}: {e}")
    
    def close(self):
        """Close Redis connection."""
        try:
            self.redis_conn.close()
            LOGGER.info("TokenStreamingService connection closed")
        except Exception as e:
            LOGGER.error(f"Error closing TokenStreamingService: {e}")


STREAM_SERVICE = TokenStreamingService("aicenter-chatbot")


async def publisher():
    """Publisher that creates multiple channels"""
    from beegen.registry.resource_hub import RESOURCE_HUB
    
    _llm = RESOURCE_HUB.llm("qwen-instruct")
    request_id = "req_123"
    
    # Publish to channel 1
    # async for chunk in _llm.stream(messages=[{"role": "user", "content": "Hello model 1"}]):
    #     await STREAM_SERVICE.push(request_id, "model_1", chunk)
    # await STREAM_SERVICE.end(request_id, "model_1")
    
    # Publish to channel 2
    async for chunk in _llm.stream(messages=[{"role": "user", "content": "Hello model 2"}]):
        await STREAM_SERVICE.push(request_id, "model_2", chunk)
    await STREAM_SERVICE.end(request_id, "model_2")
    
    # End request
    await STREAM_SERVICE.end_request(request_id)


async def main():
    request_id = "req_123"
    
    # Start publisher
    asyncio.create_task(publisher())
    
    # Discover and consume channels
    async for channel_name in STREAM_SERVICE.get_channels(request_id):
        print(f"\nChannel: {channel_name}")
        async for chunk in STREAM_SERVICE.get(request_id, channel_name):
            print(chunk.choices[0].delta.content, end="", flush=True)
        print()


if __name__ == "__main__":
    asyncio.run(main())