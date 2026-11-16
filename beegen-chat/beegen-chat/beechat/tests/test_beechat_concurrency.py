import asyncio
import time
import statistics
import sys
from typing import List, Dict

# UTF-8 stdout configuration for Windows PowerShell
sys.stdout.reconfigure(encoding='utf-8')

from beechat.beechat import BeeChatApp, CacheManager
from beechat.services.qa_service import QAService


async def test_cache_performance():
    """Test O(1) LRU Cache performance under 50,000 rapid operations"""
    print("\n==================================================")
    print(" 1. BENCHMARKING O(1) LRU CACHE PERFORMANCE")
    print("==================================================")

    cache = CacheManager(max_size=1000, ttl=300)
    total_ops = 50000

    start_time = time.time()
    
    # 1. Fill cache & force LRU evictions
    for i in range(total_ops):
        key = f"key_{i}"
        await cache.set(key, f"value_{i}")
        if i % 2 == 0:
            await cache.get(f"key_{i // 2}")

    duration = time.time() - start_time
    ops_per_sec = total_ops / duration

    stats = await cache.get_stats()
    print(f" Executed {total_ops:,} cache operations in {duration:.4f}s")
    print(f" Throughput: {ops_per_sec:,.0f} ops/second")
    print(f" Cache Stats: Total Items={stats['total_items']}, Hit Count={stats['hit_count']}, Miss Count={stats['miss_count']}, Hit Rate={stats['hit_rate']:.2%}")
    assert stats['total_items'] <= 1000, "Cache size exceeded maximum capacity!"
    print(" Cache O(1) LRU eviction test PASSED!")


async def run_single_request(bot: BeeChatApp, session_id: str, query: str) -> Dict:
    """Helper to run a single request and collect metrics"""
    messages = [{"role": "user", "content": query}]
    start_time = time.time()
    ttft = None
    chunks_count = 0
    full_text = ""
    status_code = None

    try:
        stream = bot.run(messages, session_id=session_id)
        if hasattr(stream, '__aiter__'):
            async for chunk in stream:
                chunks_count += 1
                if ttft is None and hasattr(chunk, 'choices') and chunk.choices and chunk.choices[0].delta.content:
                    ttft = time.time() - start_time

                if hasattr(chunk, 'status_code'):
                    status_code = chunk.status_code

                if hasattr(chunk, 'choices') and chunk.choices and chunk.choices[0].delta.content:
                    full_text += chunk.choices[0].delta.content
        
        total_time = time.time() - start_time
        return {
            'status': 'success',
            'query': query,
            'total_time': total_time,
            'ttft': ttft or total_time,
            'chunks': chunks_count,
            'response_len': len(full_text),
            'status_code': status_code
        }
    except Exception as e:
        total_time = time.time() - start_time
        return {
            'status': 'error',
            'query': query,
            'total_time': total_time,
            'error': str(e)
        }


async def test_concurrent_load(concurrency_level: int = 50):
    """Simulate heavy concurrent requests hitting BeeChatApp"""
    print(f"\n==================================================")
    print(f" 2. CONCURRENCY LOAD TEST ({concurrency_level} PARALLEL REQUESTS)")
    print("==================================================")

    bot_id = "da498399-56c2-479f-80c6-b79e605dcd66"
    bot = BeeChatApp(bot_id)

    # Mixed test workload (Early exit greetings, card queries, standard questions)
    test_queries = [
        "Xin chào Bee",
        "Cảm ơn nhé",
        "Hi",
        "Thẻ tín dụng MB có bao nhiêu loại?",
        "Hạn mức chuyển tiền qua app MB",
        "Xin chào",
        "Tks",
        "Tư vấn thẻ đa năng MB"
    ]

    # Create concurrent task workload
    tasks = []
    for i in range(concurrency_level):
        query = test_queries[i % len(test_queries)]
        session_id = f"load_test_session_{i}"
        tasks.append(run_single_request(bot, session_id, query))

    print(f" Launching {concurrency_level} parallel requests...")
    overall_start = time.time()
    results = await asyncio.gather(*tasks)
    overall_duration = time.time() - overall_start

    # Metrics calculation
    successes = [r for r in results if r['status'] == 'success']
    errors = [r for r in results if r['status'] == 'error']
    
    total_times = [r['total_time'] for r in successes]
    ttft_times = [r['ttft'] for r in successes if r.get('ttft')]

    print("\n==================================================")
    print(" CONCURRENCY LOAD TEST RESULTS REPORT")
    print("==================================================")
    print(f" Total Requests: {concurrency_level}")
    print(f" Successful: {len(successes)} ({len(successes)/concurrency_level:.1%})")
    print(f" Failed/Errors: {len(errors)}")
    print(f" Total Wall Clock Time: {overall_duration:.3f}s")
    print(f" Throughput: {concurrency_level / overall_duration:.2f} requests/second")

    if total_times:
        avg_latency = statistics.mean(total_times)
        p95_latency = statistics.quantiles(total_times, n=20)[18] if len(total_times) >= 20 else max(total_times)
        min_latency = min(total_times)
        max_latency = max(total_times)

        avg_ttft = statistics.mean(ttft_times) if ttft_times else 0.0

        print(f"\n LATENCY METRICS:")
        print(f"   • Min Latency: {min_latency:.3f}s")
        print(f"   • Avg Latency: {avg_latency:.3f}s")
        print(f"   • P95 Latency: {p95_latency:.3f}s")
        print(f"   • Max Latency: {max_latency:.3f}s")
        print(f"   • Avg TTFT (First Token): {avg_ttft:.3f}s")

    print("==================================================\n")
    assert len(errors) == 0, f"Load test had {len(errors)} errors!"
    print(" ALL CONCURRENCY LOAD TESTS PASSED SUCCESSFULLY!")


async def main():
    await test_cache_performance()
    await test_concurrent_load(concurrency_level=50)


if __name__ == "__main__":
    asyncio.run(main())
