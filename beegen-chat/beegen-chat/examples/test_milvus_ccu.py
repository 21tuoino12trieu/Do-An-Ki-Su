import asyncio
import numpy as np
import time
from beegenerate.configs import MilvusConfig, MilvusOperation
from beegenerate.vectordb.milvus_v2 import MilvusExecutor
from tqdm import tqdm
import statistics

async def single_search(milvus_exec: MilvusExecutor) -> float:
    """Perform a single search operation"""
    # Generate random normalized vector
    query_vector = np.random.random(1024)
    query_vector = (query_vector / np.linalg.norm(query_vector)).tolist()
    
    try:
        start_time = time.time()
        response = await milvus_exec.run(
            operation=MilvusOperation.SEARCH,
            params={
                "collection_name": "bot_b10f0d26_4d91_47f5_8cac_034b87e42c7f",
                "query_vectors": [query_vector],
                "top_k": 5,
                "output_fields": ['chunk_id', 'role'],
                "metric_type": "COSINE"
            }
        )
        return time.time() - start_time
    except Exception as e:
        print(f"Search error: {str(e)}")
        raise

async def run_ccu_test(num_requests: int = 1000):
    """Run CCU test with specified number of concurrent requests"""
    # Initialize MilvusExecutor
    milvus_exec = MilvusExecutor(MilvusConfig.default())
    
    print(f"\nStarting CCU test with {num_requests} concurrent requests...")
    
    latencies = []
    errors = 0
    
    # Create all search tasks
    tasks = [single_search(milvus_exec) for _ in range(num_requests)]
    
    # Run searches concurrently with progress bar
    with tqdm(total=num_requests, desc="Processing requests") as pbar:
        for coro in asyncio.as_completed(tasks):
            try:
                latency = await coro
                latencies.append(latency)
            except Exception:
                errors += 1
            finally:
                pbar.update(1)
    
    # Calculate and print statistics
    if latencies:
        print("\nTest Results:")
        print(f"Total requests: {num_requests}")
        print(f"Successful requests: {len(latencies)}")
        print(f"Failed requests: {errors}")
        print(f"Success rate: {(len(latencies)/num_requests)*100:.2f}%")
        print(f"Average latency: {statistics.mean(latencies):.3f}s")
        print(f"95th percentile latency: {np.percentile(latencies, 95):.3f}s")
        print(f"99th percentile latency: {np.percentile(latencies, 99):.3f}s")
        print(f"Min latency: {min(latencies):.3f}s")
        print(f"Max latency: {max(latencies):.3f}s")
    else:
        print("\nNo successful requests completed")

async def main():
    await run_ccu_test(1000)  # Test with 1000 CCU

if __name__ == "__main__":
    asyncio.run(main())