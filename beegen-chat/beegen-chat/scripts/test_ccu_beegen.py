import pandas as pd
import asyncio
import aiohttp
import time
import json
import uuid
from typing import List
from beechat.prompts.analysis_prompts import ANALIZE_TOPIC_AND_SENTIMENT_PROMPT
from beechat.prompts.content_filter_prompts import CONTENT_FILTER_PROMPT
from beechat.prompts.card_prompts import CARD_KEYWORD_EXTRACT_PROMPT_V2
from beechat.utils.card_tree_init import CARD_HIERARCHY_NEW

PATH_EVA_FILE = r"D:\work\beegen-chat\export-data (1).xlsx"
COLUMN_NAME = "NGƯỜI DÙNG HỎI"

df = pd.read_excel(PATH_EVA_FILE)
df.columns = df.columns.str.strip()
questions = df[COLUMN_NAME].dropna().tolist()

# Configuration
# url = "http://10.1.87.71:30252/v1/chat/completions"
url = "http://10.7.39.38:8000/v1/chat/completions_"
# url = "http://10.1.87.71:30042/v1/chat/completions"
# url = "https://10.1.13.168:8443/mbdevai/openai/deployments/azure-chat-engine-gpt-4o-base/chat/completions?api-version=2024-08-01-preview"

headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer mb123456789'
    # 'Authorization': 'Bearer REPLACE_WITH_LOCAL_SECRET'
}

async def send_request_async(session: aiohttp.ClientSession, question: str, question_id: str = None):
    """Send a single async API request"""
    if question_id is None:
        question_id = str(uuid.uuid4())
    
    payload = {
        "bot_id": "da498399-56c2-479f-80c6-b79e605dcd66",
        "topic": "default",
        "role": "L1",
        # "model": "model/beegen-model-v1",
        # "model": "model/Qwen3-235B-A22B-AWQ",
        "messages": [
            {
                "role": "user",
                # "content": CARD_KEYWORD_EXTRACT_PROMPT_V2.format(query=question, CARD_HIERARCHY=CARD_HIERARCHY_NEW)
                # "content": ANALIZE_TOPIC_AND_SENTIMENT_PROMPT.format(query=question)
                # "content": CONTENT_FILTER_PROMPT.format(query=question)
                "content": question
            }
        ]
    }
    
    async with session.post(url, headers=headers, json=payload, timeout=30) as response:
        # Handle streaming response by concatenating all chunks
        full_content = ""
        async for line in response.content.iter_chunks():
            if line:
                line_text = line[0].decode('utf-8')[6:]
                try:
                    content_json = json.loads(line_text)
                    choices = content_json["choices"]
                    if choices:
                        content = choices[0]["delta"]["content"]
                        if content:
                            full_content += content
                except Exception:
                    pass
        
        return {
            # 'id': question_id,
            # 'question': question,
            # 'status_code': response.status,
            'response': full_content,
            'success': response.status == 200
        }


async def main():
    NUM_CONCURRENT_REQUESTS = 100
    
    # Use available questions, up to NUM_CONCURRENT_REQUESTS
    # If fewer questions are available than NUM_CONCURRENT_REQUESTS, use all of them.
    # If more are available, use the first NUM_CONCURRENT_REQUESTS.
    questions_to_send = questions[:NUM_CONCURRENT_REQUESTS]
    
    actual_requests_count = len(questions_to_send)
    if actual_requests_count == 0:
        print("No questions available to send. Exiting.")
        return

    print(f"Preparing to send {actual_requests_count} concurrent requests to {url}...")
    
    # Create a single ClientSession to be reused for all requests (connection pooling)
    # Adjust connector limits if you hit issues with too many open connections for your OS/server
    # For 100 requests, default limits are usually fine.
    connector = aiohttp.TCPConnector(limit=100) # Max 100 concurrent connections
    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        tasks = []
        for i, question_text in enumerate(questions_to_send):
            # Create a unique ID for each test request for easier tracking
            test_request_id = f"ccu_test_{i+1:03d}" 
            task = asyncio.create_task(send_request_async(session, question_text, test_request_id))
            tasks.append(task)
        
        print(f"Scheduled {len(tasks)} tasks. Waiting for completion...")
        start_time_all_requests = time.time()
        
        # Gather results from all tasks
        # return_exceptions=True allows us to see individual task exceptions
        # instead of gather failing on the first one
        results = await asyncio.gather(*tasks, return_exceptions=True) 
        
        for result in results:
            print(result)
        
        end_time_all_requests = time.time()
        total_duration = end_time_all_requests - start_time_all_requests
        
        print(f"\n--- All {actual_requests_count} requests processed in {total_duration:.2f} seconds ---")
        
        successful_requests = 0
        failed_requests = 0
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_requests += 1
                print(f"Request Task {i+1} failed with Exception: {result}")
            elif result['success']:
                successful_requests += 1
                # Optionally print success details
                # print(f"  ID: {result['id']}, Status: {result['status_code']}, Success: {result['success']}, Duration: {result['duration_seconds']:.2f}s")
                # print(f"    Q: {result['question'][:50]}...")
                # print(f"    R: {result['response_text'][:70]}...")
            else:
                failed_requests += 1
                print(f"  ID: {result['id']}, Status: {result['status_code']}, Success: {result['success']}, Duration: {result['duration_seconds']:.2f}s")
                print(f"    Q: {result['question'][:50]}...")
                print(f"    Error Response: {result['response_text']}")
        
        print(f"\nSummary:")
        print(f"  Total requests attempted: {actual_requests_count}")
        print(f"  Successful requests: {successful_requests}")
        print(f"  Failed requests: {failed_requests}")
        if actual_requests_count > 0:
            print(f"  Average time per request (if all ran sequentially): {total_duration / actual_requests_count:.2f}s (approx)")
            print(f"  Effective throughput: {actual_requests_count / total_duration:.2f} requests/second (approx)")


if __name__ == "__main__":
    # Set a higher event loop policy limit on Windows if needed for many connections
    # import sys
    # if sys.platform == "win32":
    #     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())