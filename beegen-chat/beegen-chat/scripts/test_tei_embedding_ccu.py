import asyncio
import aiohttp
import random
import time
from datetime import datetime

# Configuration
# URL = "http://10.1.39.127:30066/v1/embeddings"
URL = "http://10.1.39.127:30044/embed"
API_KEY = "mb123456789"
CONCURRENT_USERS = 5000

# Counters for statistics
success_count = 0
error_count = 0

# Sample sentences
sentences = [
    "tổng giám đốc mb là ai?",
    "mb bank có bao nhiêu chi nhánh?",
    "lãi suất vay mb bank hiện nay là bao nhiêu?",
    "mb bank có những sản phẩm gì?",
    "địa chỉ trụ sở chính mb bank ở đâu?"
]

async def make_request(session):
    global success_count, error_count
    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json'
    }
    
    # payload = {
    #     "model": "model/bge-m3",
    #     "input": [random.choice(sentences)],
    # }
    payload = {
        # "model": "model/bge-m3",
        "inputs": [random.choice(sentences)],
    }
    
    start_time = time.time()
    try:
        async with session.post(URL, json=payload, headers=headers) as response:
            await response.json()
            success_count += 1
            duration = time.time() - start_time
            if success_count % 1000 == 0:
                print(f"Request successful - Duration: {duration:.2f}s")
    except Exception as e:
        error_count += 1
        print(f"Error: {e}")

async def run_load_test():
    print(f"Starting load test at: {datetime.now()}")
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for _ in range(CONCURRENT_USERS):
            task = asyncio.create_task(make_request(session))
            tasks.append(task)
        await asyncio.gather(*tasks)
    
    end_time = time.time()
    total_time = end_time - start_time
    total_requests = success_count + error_count
    
    print("\n=== Load Test Results ===")
    print(f"End time: {datetime.now()}")
    print(f"Total duration: {total_time:.2f} seconds")
    print(f"Total requests: {total_requests}")
    print(f"Successful requests: {success_count}")
    print(f"Failed requests: {error_count}")
    print(f"Requests per second: {total_requests/total_time:.2f}")
    print("=====================")

if __name__ == "__main__":
    print(f"Initializing load test with {CONCURRENT_USERS} concurrent users...")
    asyncio.run(run_load_test())
    