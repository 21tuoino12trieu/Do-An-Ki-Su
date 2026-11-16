import functools
import asyncio
import inspect
from typing import Callable, Any, Literal, Optional
from .emitters import emitter
from ag_ui.core import EventType
from contextlib import contextmanager, asynccontextmanager


# === Helpers: chạy hàm async trong cả môi trường sync/async ===
def _run_awaitable(coro):
    """
    Chạy 1 coroutine trong ngữ cảnh hiện tại:
    - Nếu đang ở trong event loop: block tạm bằng chạy task và chờ kết quả.
    - Nếu không có loop: tạo loop tạm và chạy coro.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Không có loop -> chạy mới
        return asyncio.run(coro)
    else:
        # Đang ở trong loop -> chạy và chờ
        return loop.run_until_complete(coro) if not loop.is_running() else \
            asyncio.get_event_loop_policy().get_event_loop().run_until_complete(coro)


async def _emit_started_event(step_name: str,
                              type: Literal[EventType.STEP_STARTED, EventType.TOOL_CALL_START] = EventType.STEP_STARTED,
                              raw_event: Optional[Any] = None):
    if (type == EventType.TOOL_CALL_START):
        return await emitter.emit_tool_call_start(step_name, raw_event)
    return await emitter.emit_step_started(step_name, raw_event)


async def _emit_finished_event(step_name: str, type: Literal[
    EventType.STEP_STARTED, EventType.TOOL_CALL_START] = EventType.STEP_STARTED, raw_event: Optional[Any] = None):
    if (type == EventType.TOOL_CALL_START):
        return await emitter.emit_tool_call_end(step_name, raw_event)
    return await emitter.emit_step_finished(step_name, raw_event)


# === Context managers ===

@contextmanager
def agui_step_event(step_name: str,
                    type: Literal[EventType.STEP_STARTED, EventType.TOOL_CALL_START] = EventType.STEP_STARTED,
                    raw_event: Optional[Any] = None):
    """
    Context manager cho code SYNC:
        with step_event("MyStep"):
            ... do something ...
    """
    try:
        _run_awaitable(_emit_started_event(step_name, type, raw_event))
        yield
        _run_awaitable(_emit_finished_event(step_name, type, raw_event))
    except Exception as e:
        # vẫn phát finished, kèm thông tin lỗi trong raw_event (nếu bạn muốn)
        err_raw = {"status": "error", "exception": repr(e)}
        if raw_event is not None:
            err_raw = {"__raw__": raw_event, **err_raw}
        _run_awaitable(_emit_finished_event(step_name, type, err_raw))
        raise


@asynccontextmanager
async def agui_astep_event(
        step_name: str,
        type: Literal[EventType.STEP_STARTED, EventType.TOOL_CALL_START] = EventType.STEP_STARTED,
        raw_event: Optional[Any] = None
):
    """
    Context manager cho code ASYNC:
        async with astep_event("MyStep"):
            await ...
    """
    try:
        await _emit_started_event(step_name, type, raw_event)
        yield
        await _emit_finished_event(step_name, type, raw_event)
    except Exception as e:
        err_raw = {"status": "error", "exception": repr(e)}
        if raw_event is not None:
            err_raw = {"__raw__": raw_event, **err_raw}
        await _emit_finished_event(step_name, err_raw)
        raise


# === Decorator dùng cho cả sync & async ===

def with_step(step_name: Optional[str] = None,
              type: Literal[EventType.STEP_STARTED, EventType.TOOL_CALL_START] = EventType.STEP_STARTED,
              raw_event_factory: Optional[Callable[..., Any]] = None):
    """
    Dùng:
        @with_step()                    # step_name = tên hàm
        def foo(...): ...

        @with_step("CustomStep")
        async def bar(...): ...

        @with_step(raw_event_factory=lambda *a, **kw: {"args": a, "kw": kw})
        def baz(...): ...

    - raw_event_factory (nếu có) sẽ tạo raw_event từ args/kwargs lúc runtime.
    """

    def deco(fn):
        name = step_name or fn.__name__

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def awrapper(*args, **kwargs):
                raw = raw_event_factory(*args, **kwargs) if raw_event_factory else None
                async with agui_astep_event(name, type, raw):
                    return await fn(*args, **kwargs)

            return awrapper
        else:
            @functools.wraps(fn)
            def swrapper(*args, **kwargs):
                raw = raw_event_factory(*args, **kwargs) if raw_event_factory else None
                with agui_step_event(name, type, raw):
                    return fn(*args, **kwargs)

            return swrapper

    return deco
