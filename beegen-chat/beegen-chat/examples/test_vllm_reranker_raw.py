import aiohttp
import asyncio
import time
import json
import random
import statistics

# Your configuration
API_CONFIG = {
    "api_type": "vllm",
    "api_key": "mb123456789",
    "base_url": "http://10.1.87.71:30043/rerank",
    "model": "model/bge-reranker-v2-m3"
}

# Generate sample documents (30-40 words each)
SAMPLE_TEXTS = [
    "The quick brown fox jumps over the lazy dog. This sentence contains all letters of the English alphabet and is commonly used for testing fonts and keyboards. It's a simple pangram that developers often use.",
    "Machine learning models require extensive training data to perform well. The quality of the data is often more important than the quantity. Proper preprocessing and feature engineering can significantly improve model performance.",
    "Climate change is affecting ecosystems worldwide. Rising temperatures lead to more extreme weather events, including droughts and floods. Many species are struggling to adapt to these rapid environmental changes.",
    "Effective communication is essential in team environments. Clear messaging prevents misunderstandings and ensures everyone is working toward the same goal. Regular updates help maintain alignment across departments.",
    "Quantum computing leverages quantum mechanics principles to process information. Unlike classical computers that use bits, quantum computers use qubits which can exist in multiple states simultaneously, enabling parallel computation.",
    "Healthy nutrition involves balancing macronutrients and micronutrients. Proteins, carbohydrates, and fats provide energy, while vitamins and minerals support various bodily functions. Hydration is equally important for overall health.",
    "Renewable energy sources include solar, wind, hydro, and geothermal power. These technologies produce electricity with minimal environmental impact compared to fossil fuels. Many countries are increasing renewable energy investments.",
    "Artificial intelligence has applications across numerous industries including healthcare, finance, transportation, and entertainment. AI systems can analyze data, recognize patterns, and make predictions with increasing accuracy.",
    "Regular exercise improves physical and mental health. Activities like walking, swimming, and cycling strengthen the cardiovascular system. Strength training builds muscle mass and supports bone density. Exercise also reduces stress.",
    "Effective time management involves prioritizing tasks, setting realistic deadlines, and minimizing distractions. Breaking large projects into smaller steps makes them more manageable. Planning ahead prevents last-minute rushes.",
    "Cybersecurity measures protect digital systems from unauthorized access and attacks. Encryption, multi-factor authentication, and regular software updates are essential practices. User education helps prevent social engineering attacks.",
    "Urban planning considers transportation, housing, public spaces, and infrastructure. Well-designed cities promote community interaction while providing essential services. Green spaces improve air quality and resident wellbeing.",
    "Historical perspectives help us understand current social and political dynamics. Learning from past events can guide future decision-making. Primary sources provide direct evidence of historical moments and cultural contexts.",
    "Digital marketing encompasses search engine optimization, social media campaigns, email newsletters, and content creation. Analytics tools track performance metrics and guide strategy adjustments. Audience targeting improves conversion rates.",
    "Sustainable agriculture practices preserve soil health and biodiversity. Crop rotation prevents nutrient depletion, while integrated pest management reduces chemical use. Water conservation techniques minimize resource waste."
]

# Sample queries
SAMPLE_QUERIES = [
    "How does machine learning work?",
    "What are renewable energy sources?",
    "Why is cybersecurity important?",
    "How does climate change affect ecosystems?",
    "What is effective communication?"
]

async def send_rerank_request(session, query, documents, request_id):
    """Send a single rerank request and return timing information"""
    start_time = time.time()
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_CONFIG['api_key']}"
    }
    
    # Prepare the payload according to vLLM reranker format
    payload = {
        "model": API_CONFIG["model"],
        "query": query,
        "documents": documents,
    }
    
    try:
        async with session.post(API_CONFIG["base_url"], json=payload, headers=headers) as response:
            response_time = time.time() - start_time
            response_json = await response.json()
            return {
                "request_id": request_id,
                "status_code": response.status,
                "response_time": response_time,
                "success": response.status == 200,
                "error": None if response.status == 200 else response_json
            }
    except Exception as e:
        end_time = time.time()
        return {
            "request_id": request_id,
            "status_code": 0,
            "response_time": end_time - start_time,
            "success": False,
            "error": str(e)
        }

async def benchmark_reranker(num_concurrent_requests=1000):
    """Benchmark the reranker with multiple concurrent requests"""
    print(f"Starting benchmark with {num_concurrent_requests} concurrent requests...")
    
    # Create a connection pool with limits
    connector = aiohttp.TCPConnector(limit=0)  # No limit on connections
    timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout
    
    start_time = time.time()
    results = []
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = []
        
        for i in range(num_concurrent_requests):
            # Randomly select a query and 10 documents for each request
            query = random.choice(SAMPLE_QUERIES)
            documents = random.sample(SAMPLE_TEXTS, 5)
            
            # Create the task
            task = send_rerank_request(session, query, documents, i)
            tasks.append(task)
        
        # Execute all requests concurrently
        results = await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    
    # Process and report results
    successful_requests = [r for r in results if r["success"]]
    failed_requests = [r for r in results if not r["success"]]
    
    response_times = [r["response_time"] for r in successful_requests]
    
    print("\n===== BENCHMARK RESULTS =====")
    print(f"Total time: {total_time:.2f} seconds")
    print(f"Requests: {num_concurrent_requests}")
    print(f"Successful: {len(successful_requests)}")
    print(f"Failed: {len(failed_requests)}")
    
    if response_times:
        print(f"Average response time: {statistics.mean(response_times):.3f} seconds")
        print(f"Median response time: {statistics.median(response_times):.3f} seconds")
        print(f"Min response time: {min(response_times):.3f} seconds")
        print(f"Max response time: {max(response_times):.3f} seconds")
        print(f"Throughput: {num_concurrent_requests / total_time:.2f} requests/second")
    
    if failed_requests:
        print("\nFailed request examples:")
        for fail in failed_requests[:3]:  # Show up to 3 examples
            print(f"  Request {fail['request_id']}: {fail['error']}")
    
    return {
        "total_time": total_time,
        "successful_requests": len(successful_requests),
        "failed_requests": len(failed_requests),
        "response_times": response_times,
        "throughput": num_concurrent_requests / total_time if total_time > 0 else 0
    }

if __name__ == "__main__":
    # Run the benchmark
    asyncio.run(benchmark_reranker(1000))