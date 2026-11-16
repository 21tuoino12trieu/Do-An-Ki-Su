import pandas as pd
from datetime import datetime
import asyncio
import time
from beegenerate.prompts import FINAL_ANSWER_PROMPT
from beegenerate.llms.core import VllmOpenAIModel, AzureOpenAIModel
from beegenerate.configs import LLMConfig, CompletionConfig
from statistics import mean


async def process_single_request(model, prompt, user_id, first_token_times):
    """Process a single request and track first token latency"""
    start_time = time.time()
    first_token_received = False
    
    async for chunk in model.stream(
        messages=[{"role": "user", "content": prompt}]
    ):
        if chunk.choices:
            content = chunk.choices[0].delta.content
            if content:
                if not first_token_received:
                    first_token_latency = time.time() - start_time
                    first_token_times[user_id] = first_token_latency
                    first_token_received = True
                # print(f"User {user_id}: {content}", end='')


async def main():
    num_users = 100
    # Load and prepare data
    df = pd.read_csv(r"D:\work\beegen-chat\scripts\results_with_answers_verify_gwen.csv")[:num_users*2]
    df = df[['question', 'docs']]

    # Create prompts
    prompts = []
    for index, row in df.iterrows():
        prompt = FINAL_ANSWER_PROMPT.format(
            question=row['question'],
            date=datetime.now().date(),
            documents=row['docs']
        )
        prompts.append(prompt)
        
    PATH_EVA_FILE = r"D:\work\beegen-chat\export-data (1).xlsx"
    COLUMN_NAME = "NGƯỜI DÙNG HỎI"

    df = pd.read_excel(PATH_EVA_FILE)
    df.columns = df.columns.str.strip()
    questions = df[COLUMN_NAME].dropna().tolist()
        
    from beegenerate.configs import LLMConfig
    from beegenerate.llms.core_v2.factory import LLMFactory
    from beegenerate.const import BEEGEN_ROOT

    model = LLMFactory.create(
        config=LLMConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/azure.yaml")
    )

    # Create tasks for concurrent users
    tasks = []
    first_token_times = {}  # Dictionary to store first token latencies
    
    # If we have fewer prompts than users, we'll cycle through the prompts
    for user_id in range(num_users):
        prompt = questions[user_id % len(questions)]
        task = process_single_request(model, prompt, user_id, first_token_times)
        tasks.append(task)

    # Start timing
    start_time = time.time()
    
    # Run all tasks concurrently
    await asyncio.gather(*tasks)
    
    # Calculate and print metrics
    end_time = time.time()
    total_time = end_time - start_time
    requests_per_second = num_users / total_time
    
    # Calculate first token latency statistics
    avg_first_token = mean(first_token_times.values())
    min_first_token = min(first_token_times.values())
    max_first_token = max(first_token_times.values())
    
    print("\n=== Test Results ===")
    print(f"Total time: {total_time:.2f} seconds")
    print(f"Requests per second: {requests_per_second:.2f}")
    print(f"Number of concurrent users: {num_users}")
    print("\n=== First Token Latency ===")
    print(f"Average: {avg_first_token:.3f} seconds")
    print(f"Min: {min_first_token:.3f} seconds")
    print(f"Max: {max_first_token:.3f} seconds")


if __name__ == "__main__":
    asyncio.run(main())