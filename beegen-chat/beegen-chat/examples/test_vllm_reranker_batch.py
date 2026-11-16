import asyncio
import time
import statistics
import numpy as np
from typing import List, Any, Tuple
from beegenerate.utils.common import configure_event_loop
from beegenerate.reranks import VLLMReranker
from beegenerate.configs import RerankingConfig

# Sample data for reranking
SAMPLE_TEXTS = [
    """File tài liệu: Quy định về giao dịch chuyển tiền nhanh 247
Câu hỏi: Thời gian xử lý tra soát giao dịch chuyển 
tiền nhanh 247 qua Napas là bao lâu?
Câu trả lời: Tối đa 04 ngày làm việc (không tính thứ 7, chủ nhật và ngày nghỉ lễ)""",

    """File tài liệu: Hướng dẫn giao dịch ngân hàng điện tử
Câu hỏi: Phí giao dịch chuyển tiền nhanh 247 là bao nhiêu?
Câu trả lời: Miễn phí cho giao dịch dưới 500.000 VND, 11.000 VND cho giao dịch trên 500.000 VND""",

    """File tài liệu: Chính sách khách hàng ưu tiên
Câu hỏi: Khách hàng VIP được ưu đãi gì khi chuyển tiền 247?
Câu trả lời: Miễn phí toàn bộ giao dịch chuyển tiền 247, không giới hạn số tiền""",

    """File tài liệu: Quy trình xử lý khiếu nại
Câu hỏi: Quy trình xử lý tra soát giao dịch lỗi là gì?
Câu trả lời: Tiếp nhận yêu cầu, xác minh thông tin trong 24h, phản hồi kết quả trong 04 ngày làm việc""",

    """File tài liệu: Hạn mức giao dịch
Câu hỏi: Hạn mức chuyển tiền 247 qua Napas là bao nhiêu?
Câu trả lời: Tối đa 500 triệu VND/giao dịch và 2 tỷ VND/ngày""",

    """File tài liệu: Thời gian hoạt động dịch vụ
Câu hỏi: Thời gian hoạt động của dịch vụ chuyển tiền 247?
Câu trả lời: Hoạt động 24/7, kể cả ngày nghỉ và ngày lễ""",

    """File tài liệu: Hướng dẫn tra soát giao dịch
Câu hỏi: Cách thức gửi yêu cầu tra soát giao dịch?
Câu trả lời: Khách hàng có thể gửi yêu cầu qua email, tổng đài 24/7 hoặc trực tiếp tại quầy""",

    """File tài liệu: Quy định về bằng chứng giao dịch
Câu hỏi: Giấy báo có được cung cấp như thế nào?
Câu trả lời: Được cung cấp qua email trong vòng 04 ngày làm việc sau khi nhận yêu cầu""",

    """File tài liệu: Chính sách hoàn tiền
Câu hỏi: Thời gian hoàn tiền cho giao dịch lỗi?
Câu trả lời: Tối đa 07 ngày làm việc sau khi có kết quả tra soát""",

    """File tài liệu: Quy định về xác thực giao dịch
Câu hỏi: Phương thức xác thực giao dịch chuyển tiền 247?
Câu trả lời: Soft OTP hoặc Smart OTP, tùy theo đăng ký của khách hàng"""
]

# Sample queries for reranking
SAMPLE_QUERIES = [
    "Thời gian xử lý và cung cấp giấy báo có cho giao dịch chuyển tiền nhanh 247 qua Napas là bao lâu?",
    "Phí giao dịch chuyển tiền nhanh 247 là bao nhiêu?",
    "Khách hàng VIP được ưu đãi gì khi chuyển tiền?",
    "Cách tra soát giao dịch chuyển tiền bị lỗi?",
    "Hạn mức chuyển tiền tối đa qua Napas?",
    "Dịch vụ chuyển tiền 247 hoạt động vào ngày lễ không?",
    "Làm thế nào để tra soát giao dịch?",
    "Thời gian cung cấp giấy báo có?",
    "Thời gian hoàn tiền cho giao dịch lỗi?",
    "Cách xác thực giao dịch chuyển tiền 247?"
]

async def rerank_batch(reranker: VLLMReranker, batch_size: int = 10) -> Tuple[List[Any], float]:
    """Rerank a batch of queries and texts and return the time taken"""
    # For each request in the batch, we'll use a random query from our sample queries
    # We'll reuse the same texts for each request to simulate real-world usage
    queries = [SAMPLE_QUERIES[i % len(SAMPLE_QUERIES)] for i in range(batch_size)]
    
    # Time the reranking operations for the entire batch
    start_time = time.time()
    
    # Create tasks for each query in the batch
    tasks = []
    for query in queries:
        task = reranker.run(
            query=query,
            texts=SAMPLE_TEXTS,
            top_k=5,
            threshold=0.0
        )
        tasks.append(task)
    
    # Run all reranking operations in the batch concurrently
    results = await asyncio.gather(*tasks)
    
    elapsed_time = time.time() - start_time
    return results, elapsed_time

async def main() -> None:
    """Main function for testing and demonstration."""
    # Configure event loop
    configure_event_loop()
    
    # Total number of requests and batch configuration
    TOTAL_REQUESTS = 1000
    BATCH_SIZE = 5
    NUM_BATCHES = TOTAL_REQUESTS // BATCH_SIZE
    
    overall_start_time = time.time()
    print(f"Starting reranking test with {NUM_BATCHES} batches, {BATCH_SIZE} queries per batch...")
    
    # Initialize the reranker
    reranker = VLLMReranker(RerankingConfig.default())
    
    # Create and collect tasks for all batches
    batch_latencies = []
    errors = 0
    
    # Process batches in groups to avoid overwhelming the system
    CONCURRENT_BATCHES = 50  # Process 10 batches at a time (adjust based on your system capacity)
    for i in range(0, NUM_BATCHES, CONCURRENT_BATCHES):
        batch_group = min(CONCURRENT_BATCHES, NUM_BATCHES - i)
        print(f"Processing batch group {i//CONCURRENT_BATCHES + 1}, batches {i+1}-{i+batch_group}")
        
        # Create tasks for this group of batches
        tasks = [rerank_batch(reranker, BATCH_SIZE) for _ in range(batch_group)]
        
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
    print("\nReranking Test Results:")
    print(f"Total batches: {NUM_BATCHES}")
    print(f"Queries per batch: {BATCH_SIZE}")
    print(f"Total reranking requests: {TOTAL_REQUESTS}")
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
        
        # Calculate per-query metrics
        avg_per_query = statistics.mean(batch_latencies) / BATCH_SIZE
        print(f"\nPer-query metrics (estimated):")
        print(f"Average per-query latency: {avg_per_query:.3f}s")
        
        # Calculate real throughput based on actual elapsed time
        throughput = TOTAL_REQUESTS / total_elapsed_time
        print(f"Overall throughput: {throughput:.1f} queries/second")

if __name__ == "__main__":
    asyncio.run(main())