import asyncio
from typing import Dict, Any, Awaitable, Tuple

from beegenerate.loggings import LOGGER


class TaskService:
    """
    Service quản lý các tác vụ song song với xử lý lỗi tốt.
    Cho phép thực hiện nhiều coroutine song song và xử lý các lỗi một cách độc lập.
    """

    @staticmethod
    async def run_parallel_tasks(
            tasks: Dict[str, Awaitable],
            default_results: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Chạy nhiều tác vụ song song và xử lý lỗi riêng biệt cho từng tác vụ.
        """
        # Kết quả mặc định
        results = default_results or {name: None for name in tasks}

        # Tạo các task và theo dõi mối quan hệ giữa task và tên
        pending_tasks = []
        task_to_name = {}

        for name, coro in tasks.items():
            # Thêm log để debug
            LOGGER.debug(f"Creating task for: {name}")
            task = asyncio.create_task(coro)
            pending_tasks.append(task)
            task_to_name[task] = name

        pending = set(pending_tasks)

        # Chạy các tác vụ và xử lý kết quả
        try:
            while pending:
                done, pending = await asyncio.wait(
                    pending,
                    return_when=asyncio.FIRST_COMPLETED
                )

                # Xử lý các tác vụ đã hoàn thành
                for task in done:
                    name = task_to_name[task]
                    try:
                        results[name] = task.result()
                        LOGGER.info(f"Task '{name}' completed successfully")
                    except Exception as e:
                        LOGGER.error(f"Error in task '{name}': {str(e)}")
                        # Giữ nguyên kết quả mặc định

        except Exception as e:
            LOGGER.error(f"Error in task orchestration: {str(e)}")
            # Vẫn giữ kết quả mặc định nếu lỗi

        return results

    @staticmethod
    async def run_initial_tasks(
            summary_query_task: Awaitable,
            cache_check_task: Awaitable,
            document_retrieval_task: Awaitable
    ) -> Tuple[Any, Any, Any]:
        """
        Hàm tiện ích chuyên dùng cho các tác vụ khởi tạo trong BeeChatApp.
        Chạy 3 tác vụ song song: tổng hợp truy vấn, kiểm tra cache, truy xuất tài liệu.

        Args:
            summary_query_task: Coroutine tạo truy vấn tóm tắt
            cache_check_task: Coroutine kiểm tra cache
            document_retrieval_task: Coroutine truy xuất tài liệu

        Returns:
            Tuple (summary_query, cache_result, document_results)
        """
        # Giá trị mặc định an toàn
        default_summary = ""
        default_cache = {'check': False, 'ref': None}
        default_document = {'document_results': {}}

        # Định nghĩa tác vụ
        tasks = {
            'summary': summary_query_task,
            'cache': cache_check_task,
            'document': document_retrieval_task
        }

        # Định nghĩa kết quả mặc định
        defaults = {
            'summary': default_summary,
            'cache': default_cache,
            'document': default_document
        }

        # Chạy các tác vụ song song
        results = await TaskService.run_parallel_tasks(tasks, defaults)

        # Trích xuất document_results từ kết quả document
        document_results = results['document'].get('document_results', {})

        return results['summary'], results['cache'], document_results