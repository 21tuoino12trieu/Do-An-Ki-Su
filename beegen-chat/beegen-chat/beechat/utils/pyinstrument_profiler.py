import functools
import contextlib
from pyinstrument import Profiler
from beegenerate.loggings import LOGGER


@contextlib.asynccontextmanager
async def profile_async_block(block_name: str = "Async Block"):
    """
    Async context manager to profile a block of code using pyinstrument 
    and log the resulting stack trace & timing report at DEBUG level.
    Safely handles nested profiling calls.
    """
    profiler = Profiler(async_mode='enabled')
    started = False
    try:
        profiler.start()
        started = True
    except RuntimeError:
        LOGGER.debug(f"Pyinstrument profiler already active, skipping nested start for '{block_name}'")

    try:
        yield profiler
    finally:
        if started and profiler.is_running:
            profiler.stop()
            report = profiler.output_text(unicode=True, color=False)
            LOGGER.debug(f"\n[Pyinstrument Profile Report - {block_name}]:\n{report}")


def profile_async_func(name: str = None):
    """
    Decorator to profile an async function using pyinstrument 
    and log the debug report after function execution finishes.
    """
    def decorator(func):
        func_name = name or func.__qualname__

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            async with profile_async_block(func_name):
                return await func(*args, **kwargs)

        return wrapper

    return decorator
