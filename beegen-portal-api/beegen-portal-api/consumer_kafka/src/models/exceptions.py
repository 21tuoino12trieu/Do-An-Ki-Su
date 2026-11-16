"""
Custom exceptions cho CUA Consumer.
Mỗi exception gắn với một ErrorCode cụ thể.
"""

from src.models.message import ErrorCode


class CUABaseException(Exception):
    """Base exception cho toàn bộ service."""
    error_code: ErrorCode = ErrorCode.INTERNAL_ERROR
    retryable: bool = False

    def __init__(self, message: str, cause: Exception | None = None):
        self.message = message
        self.cause = cause
        super().__init__(message)

    def __str__(self):
        if self.cause:
            return f"[{self.error_code.name}({self.error_code.value})] {self.message} | nguyên nhân: {self.cause}"
        return f"[{self.error_code.name}({self.error_code.value})] {self.message}"


# ─── Input Errors (không retry) ───────────────────────────────────────────────

class InvalidMessageFormatError(CUABaseException):
    error_code = ErrorCode.INVALID_MESSAGE_FORMAT
    retryable = False


class ProcessTypeNotFoundError(CUABaseException):
    error_code = ErrorCode.PROCESS_TYPE_NOT_FOUND
    retryable = False


# ─── System Errors (có retry) ─────────────────────────────────────────────────

class AirflowUnavailableError(CUABaseException):
    """Không kết nối được đến Airflow (network error, connection refused)."""
    error_code = ErrorCode.AIRFLOW_UNAVAILABLE
    retryable = True


class AirflowBadResponseError(CUABaseException):
    """Airflow phản hồi HTTP lỗi (4xx/5xx)."""
    error_code = ErrorCode.AIRFLOW_BAD_RESPONSE
    retryable = True

    def __init__(self, message: str, status_code: int, response_body: str = ""):
        body_preview = ""
        if response_body:
            trimmed = response_body[:200] + "..." if len(response_body) > 200 else response_body
            body_preview = f" | phản hồi: {trimmed}"
        full_message = f"{message} | mã trạng thái: {status_code}{body_preview}"
        super().__init__(full_message)
        self.status_code = status_code
        self.response_body = response_body

    @property
    def user_message(self) -> str:
        from src.models.message import AIRFLOW_HTTP_USER_MESSAGES, USER_MESSAGES
        return AIRFLOW_HTTP_USER_MESSAGES.get(
            self.status_code,
            USER_MESSAGES[ErrorCode.AIRFLOW_BAD_RESPONSE],
        )


class AirflowTimeoutError(CUABaseException):
    """Request đến Airflow bị timeout."""
    error_code = ErrorCode.TIMEOUT
    retryable = True


class MongoWriteFailedError(CUABaseException):
    """Không ghi được vào MongoDB."""
    error_code = ErrorCode.MONGO_WRITE_FAILED
    retryable = False


class InternalError(CUABaseException):
    """Lỗi không xác định."""
    error_code = ErrorCode.INTERNAL_ERROR
    retryable = True