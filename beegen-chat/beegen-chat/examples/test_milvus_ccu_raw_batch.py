import asyncio
import time
import numpy as np
from pymilvus import MilvusClient
import statistics
from typing import List, Tuple, Any

async def batch_search(client: MilvusClient, batch_size: int = 10) -> Tuple[List[Any], float]:
    """Do one batch search with multiple vectors and return the results and time taken"""
    # Generate random normalized vectors
    vectors = []
    for _ in range(batch_size):
        vector = np.random.random(1024)
        vector = (vector / np.linalg.norm(vector)).tolist()
        vectors.append(vector)
    
    start_time = time.time()
    result = await asyncio.to_thread(
        client.search,
        collection_name="bot_b10f0d26_4d91_47f5_8cac_034b87e42c7f",
        data=vectors,
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
    
    batch_latencies = []
    errors = 0
    
    # Number of batches to run (each batch contains 10 queries)
    NUM_BATCHES = 500
    BATCH_SIZE = 2
    
    total_requests = NUM_BATCHES * BATCH_SIZE
    print(f"\nStarting batch search test with {NUM_BATCHES} batches, {BATCH_SIZE} vectors per batch ({total_requests} total vectors)...")
    
    # Record the overall start time
    overall_start_time = time.time()
    
    # Create concurrent batch tasks
    tasks = [batch_search(client, BATCH_SIZE) for _ in range(NUM_BATCHES)]
    
    # Run all batch tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Calculate the total elapsed time
    total_elapsed_time = time.time() - overall_start_time
    
    # Process results
    for result in results:
        if isinstance(result, Exception):
            errors += 1
            print(f"Batch error: {result}")
        else:
            search_results, latency = result
            batch_latencies.append(latency)
            # Optionally process the search results here
    
    # Print statistics
    print("\nBatch Test Results:")
    print(f"Total batches: {NUM_BATCHES}")
    print(f"Vectors per batch: {BATCH_SIZE}")
    print(f"Total vectors searched: {total_requests}")
    print(f"Successful batches: {len(batch_latencies)}")
    print(f"Failed batches: {errors}")
    print(f"Batch success rate: {(len(batch_latencies)/NUM_BATCHES)*100:.2f}%")
    print(f"Total elapsed time: {total_elapsed_time:.3f}s")
    
    if batch_latencies:
        print(f"Average batch latency: {statistics.mean(batch_latencies):.3f}s")
        print(f"95th percentile batch latency: {np.percentile(batch_latencies, 95):.3f}s")
        print(f"99th percentile batch latency: {np.percentile(batch_latencies, 99):.3f}s")
        print(f"Min batch latency: {min(batch_latencies):.3f}s")
        print(f"Max batch latency: {max(batch_latencies):.3f}s")
        
        # Calculate per-vector metrics
        avg_per_vector = statistics.mean(batch_latencies) / BATCH_SIZE
        print(f"\nPer-vector metrics (estimated):")
        print(f"Average per-vector latency: {avg_per_vector:.3f}s")
        
        # Calculate throughput
        throughput = total_requests / total_elapsed_time
        print(f"Overall throughput: {throughput:.1f} vectors/second")
    
    # Cleanup
    client.close()

if __name__ == "__main__":
    asyncio.run(main())