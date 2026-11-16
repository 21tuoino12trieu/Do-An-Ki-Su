import asyncio
import time
import numpy as np
from pymilvus import connections, Collection, MilvusClient
import statistics
from typing import List

async def search_once(client: MilvusClient) -> float:
    """Do one search and return the time taken"""
    # Generate random normalized vector
    vector = np.random.random(1024)
    vector = (vector / np.linalg.norm(vector)).tolist()
    
    start_time = time.time()
    result = await asyncio.to_thread(
        client.search,
        collection_name="bot_b10f0d26_4d91_47f5_8cac_034b87e42c7f",
        data=[vector],
        output_fields=["*"],
        limit=5,
        search_params={
            "metric_type": "COSINE",
            "params": {"nprobe": 10}
        }
    )
    return result, (time.time() - start_time)

async def main():
    # Connect using MilvusClient
    client = MilvusClient(
        uri="http://10.215.254.90:19530",
        user="chatbot_user",
        password="REPLACE_WITH_LOCAL_SECRET",
        db_name="chatbot_libra"
    )
    
    latencies = []
    errors = 0
    NUM_REQUEST = 1000

    print(f"\nStarting CCU test with {NUM_REQUEST} concurrent requests...")
    
    # Create concurrent tasks
    tasks = [search_once(client) for _ in range(NUM_REQUEST)]
    
    # Run all tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results
    for result in results:
        if isinstance(result, Exception):
            errors += 1
        else:
            _, latency = result
            latencies.append(latency)
    
    # Print statistics
    print("\nTest Results:")
    print(f"Total requests: {NUM_REQUEST}")
    print(f"Successful requests: {len(latencies)}")
    print(f"Failed requests: {errors}")
    print(f"Success rate: {(len(latencies)/NUM_REQUEST)*100:.2f}%")
    
    if latencies:
        print(f"Average latency: {statistics.mean(latencies):.3f}s")
        print(f"95th percentile latency: {np.percentile(latencies, 95):.3f}s")
        print(f"99th percentile latency: {np.percentile(latencies, 99):.3f}s")
        print(f"Min latency: {min(latencies):.3f}s")
        print(f"Max latency: {max(latencies):.3f}s")
    
    # Cleanup
    client.close()

if __name__ == "__main__":
    asyncio.run(main())