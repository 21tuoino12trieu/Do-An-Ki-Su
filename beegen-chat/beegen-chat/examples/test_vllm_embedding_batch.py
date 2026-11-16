import asyncio
import time
import statistics
import numpy as np
from typing import List, Any, Tuple
from beegenerate.utils.common import configure_event_loop
from beegenerate.embeddings import VLLMEmbedding
from beegenerate.configs import EmbeddingConfig

async def generate_embeddings_batch(vllm_embed: VLLMEmbedding, batch_size: int = 10) -> Tuple[List[Any], float]:
    """Generate embeddings for a batch of texts and return the time taken"""
    # Create a batch of example texts
    texts = [f"Sample text for embedding generation request {i}" for i in range(batch_size)]
    
    # Time the embedding generation
    start_time = time.time()
    embeddings = await vllm_embed.run(texts=texts)
    elapsed_time = time.time() - start_time
    
    return embeddings, elapsed_time

async def main() -> None:
    """Main function for testing and demonstration."""
    configure_event_loop()
    
    # Total number of requests and batch configuration
    TOTAL_REQUESTS = 1000
    BATCH_SIZE = 10
    NUM_BATCHES = TOTAL_REQUESTS // BATCH_SIZE
    
    overall_start_time = time.time()
    print(f"Starting embedding generation test with {NUM_BATCHES} batches, {BATCH_SIZE} texts per batch...")
    
    # Initialize the embedding model
    vllm_embed = VLLMEmbedding(EmbeddingConfig.default())
    
    # Create and collect tasks for all batches
    batch_latencies = []
    errors = 0
    
    # Process batches in groups to avoid overwhelming the system
    CONCURRENT_BATCHES = 100  # Process 20 batches at a time
    for i in range(0, NUM_BATCHES, CONCURRENT_BATCHES):
        batch_group = min(CONCURRENT_BATCHES, NUM_BATCHES - i)
        print(f"Processing batch group {i//CONCURRENT_BATCHES + 1}, batches {i+1}-{i+batch_group}")
        
        # Create tasks for this group of batches
        tasks = [generate_embeddings_batch(vllm_embed, BATCH_SIZE) for _ in range(batch_group)]
        
        # Run the batch group concurrently
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results from this batch group
        for result in batch_results:
            if isinstance(result, Exception):
                errors += 1
                print(f"Batch error: {result}")
            else:
                _, latency = result
                batch_latencies.append(latency)
    
    # Calculate total elapsed time
    total_elapsed_time = time.time() - overall_start_time
    
    # Print statistics
    print("\nEmbedding Generation Test Results:")
    print(f"Total batches: {NUM_BATCHES}")
    print(f"Texts per batch: {BATCH_SIZE}")
    print(f"Total embedding requests: {TOTAL_REQUESTS}")
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
        
        # Calculate per-text metrics
        avg_per_text = statistics.mean(batch_latencies) / BATCH_SIZE
        print(f"\nPer-text metrics (estimated):")
        print(f"Average per-text latency: {avg_per_text:.3f}s")
        
        # Calculate real throughput based on actual elapsed time
        throughput = TOTAL_REQUESTS / total_elapsed_time
        print(f"Overall throughput: {throughput:.1f} texts/second")

if __name__ == "__main__":
    asyncio.run(main())