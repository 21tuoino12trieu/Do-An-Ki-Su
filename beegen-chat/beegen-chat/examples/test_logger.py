from beegenerate.loggings import LOGGER
import functools
from typing import Type, TypeVar, cast

T = TypeVar('T')

# Create a module-level logger configuration
LOGGER_CONFIG = LogConfig.default()

def with_logger(cls: Type[T]) -> Type[T]:
    """Class decorator that adds a logger attribute to the class."""
    cls.logger = setup_logger(
        name=f"beegen-core.{cls.__module__}.{cls.__name__}",
        config=LOGGER_CONFIG
    )
    return cls

import functools
import traceback

def log_exceptions(logger=None):
    """
    Decorator that logs any exceptions raised in the decorated function.
    If no logger is provided, it will use the class's logger (if available).
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Try to get logger from the class if not provided
            nonlocal logger
            if logger is None and args and hasattr(args[0], 'logger'):
                logger = args[0].logger
            
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if logger:
                    logger.error(f"Exception in {func.__name__}: {str(e)}")
                    logger.error(f"Traceback: {''.join(traceback.format_tb(e.__traceback__))}")
                raise  # Re-raise the exception
        return wrapper
    return decorator

# Usage with your logger setup:
@with_logger
class MyService:
    @log_exceptions()
    def risky_operation(self):
        log = self.logger
        log.info(f"hihihaha")
        # This will automatically log any exceptions
        raise ValueError("Something went wrong")
    
    
if __name__ == "__main__":
    my_service = MyService()
    my_service.risky_operation()