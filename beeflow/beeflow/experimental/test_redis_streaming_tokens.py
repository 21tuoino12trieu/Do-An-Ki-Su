import asyncio
import random
from beegen.registry.resource_hub import RESOURCE_HUB
from beegen.configs.cache.redis_config import RedisOperation

async def publish_chunks(redis_conn, stream_key, data):
    """Publish chunks to Redis list using RedisConnector"""
    
    print(f"📤 Starting to publish chunks to stream: {stream_key}")
    
    try:
        # Clear any existing data
        redis_conn.run(
            operation_type=RedisOperation.DELETE,
            params={"key": stream_key}
        )
        
        # Split data into chunks
        chunks = [data[i:i+100] for i in range(0, len(data), 100)]
        
        for i, chunk in enumerate(chunks):
            # Push chunk to list (LPUSH adds to left/head)
            redis_conn.run(
                operation_type=RedisOperation.LPUSH,
                params={"key": stream_key, "value": chunk}
            )
            print(f"📤 Published chunk {i+1}/{len(chunks)}")
            
            # Wait 0.1-0.3 seconds
            delay = random.uniform(0.1, 0.3)
            await asyncio.sleep(delay)
        
        # Send end signal
        redis_conn.run(
            operation_type=RedisOperation.LPUSH,
            params={"key": stream_key, "value": "END"}
        )
        print("✅ Publishing completed")
        
    except Exception as e:
        print(f"❌ Publisher error: {e}")

async def consume_chunks(redis_conn, stream_key):
    """Consume chunks from Redis list using RedisConnector"""
    
    try:
        print(f"📥 Starting to consume chunks from stream: {stream_key}")
        
        chunk_count = 0
        
        while True:
            # Pop chunk from right/tail (RPOP) - FIFO order
            chunk = redis_conn.run(
                operation_type=RedisOperation.RPOP,
                params={"key": stream_key}
            )
            
            if chunk is None:
                # No data available, wait a bit
                await asyncio.sleep(0.01)
                continue
            
            if chunk == "END":
                print("✅ Received END signal, stopping consumer")
                break
            
            chunk_count += 1
            print(f"📥 Consumed chunk {chunk_count}: {chunk[:50]}...")
            
            # Process your chunk here
            await asyncio.sleep(0.01)  # simulate processing
        
        print(f"Total chunks consumed: {chunk_count}")
        
    except Exception as e:
        print(f"❌ Consumer error: {e}")

async def stream_chunks(stream_key, data):
    """Run publisher and consumer concurrently using RedisConnector"""
    
    # Initialize Redis connector
    redis_conn = RESOURCE_HUB.redis("nlp-user")
    
    try:
        # Start both tasks concurrently
        publisher_task = asyncio.create_task(publish_chunks(redis_conn, stream_key, data))
        consumer_task = asyncio.create_task(consume_chunks(redis_conn, stream_key))
        
        # Wait for both to complete
        await asyncio.gather(publisher_task, consumer_task)
        
    finally:
        # Close connection
        redis_conn.close()

if __name__ == "__main__":
    # Test data
    test_data = "This is a long text that will be split into chunks and streamed through Redis using the RedisConnector class. " * 50
    
    # Run the streaming
    asyncio.run(stream_chunks("my_stream_queue", test_data))