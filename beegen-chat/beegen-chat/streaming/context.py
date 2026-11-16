
from contextvars import ContextVar
from contextlib import asynccontextmanager
from typing import Optional
import uuid

# Các biến Context (Context Variables)
# Các biến này được sử dụng để truyền thông tin ngữ cảnh (như ID phiên, ID luồng, ID chạy)
# qua các lời gọi hàm bất đồng bộ trong cùng một luồng thực thi.
current_session_id: ContextVar[Optional[str]] = ContextVar('current_session_id', default=None)
current_thread_id: ContextVar[Optional[str]] = ContextVar('current_thread_id', default=None)
current_run_id: ContextVar[Optional[str]] = ContextVar('current_run_id', default=None)

@asynccontextmanager
async def streaming_context(
    session_id: str,
    thread_id: Optional[str] = None,
    run_id: Optional[str] = None
):
    """
    Context manager để thiết lập ngữ cảnh streaming cho toàn bộ call stack.
    Điều này đảm bảo rằng các hàm được gọi trong ngữ cảnh này có thể truy cập
    các ID phiên, luồng và chạy hiện tại mà không cần truyền chúng tường minh.

    Args:
        session_id (str): ID của phiên hiện tại.
        thread_id (Optional[str]): ID của luồng hiện tại. Nếu không được cung cấp, một UUID mới sẽ được tạo.
        run_id (Optional[str]): ID của lần chạy hiện tại. Nếu không được cung cấp, một UUID mới sẽ được tạo.

    Yields:
        dict: Một dictionary chứa các ID đã được thiết lập: session_id, thread_id, run_id.
    """
    session_token = current_session_id.set(session_id)
    thread_token = current_thread_id.set(thread_id or str(uuid.uuid4()))
    run_token = current_run_id.set(run_id or str(uuid.uuid4()))
    
    try:
        yield {
            "session_id": session_id,
            "thread_id": current_thread_id.get(),
            "run_id": current_run_id.get()
        }
    finally:
        current_session_id.reset(session_token)
        current_thread_id.reset(thread_token)
        current_run_id.reset(run_token)

def get_current_session() -> Optional[str]:
    """Lấy current session ID"""
    return current_session_id.get()

def get_current_thread() -> Optional[str]:
    """Lấy current thread ID"""
    return current_thread_id.get()

def get_current_run() -> Optional[str]:
    """Lấy current run ID"""
    return current_run_id.get()
