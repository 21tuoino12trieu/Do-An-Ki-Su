"""
Models & Error Codes cho CUA Consumer Service.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
import uuid

from pydantic import BaseModel, Field, field_validator

# ─── Enums ────────────────────────────────────────────────────────────────────

class ProcessType(str, Enum):
    QUALITY          = "quality"
    CLASSIFICATION   = "classification"
    EXTRACTION       = "extraction"
    SCHEMA_DETECTION = "schema_detection"
    VALIDATION       = "validation"


class ProcessStatus(str, Enum):
    TRIGGERED = "triggered"   # Airflow DAG đã được kích hoạt thành công
    FAILED    = "failed"      # Trigger thất bại sau tất cả retry
    INVALID   = "invalid"     # Message không hợp lệ (không retry)

# ─── Error Codes ──────────────────────────────────────────────────────────────

class ErrorCode(int, Enum):
    # 1xxx – Lỗi input (không retry)
    INVALID_MESSAGE_FORMAT = 1000
    PROCESS_TYPE_NOT_FOUND = 1001

    # 9xxx – Lỗi hệ thống (có retry)
    INTERNAL_ERROR         = 9000
    TIMEOUT                = 9001
    AIRFLOW_UNAVAILABLE    = 9002
    AIRFLOW_BAD_RESPONSE   = 9003
    MONGO_WRITE_FAILED     = 9004


# Dành cho engineer trace — ghi vào sys_message
ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.INVALID_MESSAGE_FORMAT: "Message input không hợp lệ hoặc thiếu trường bắt buộc",
    ErrorCode.PROCESS_TYPE_NOT_FOUND: "process_type không tồn tại trong hệ thống",
    ErrorCode.INTERNAL_ERROR:         "Lỗi hệ thống nội bộ",
    ErrorCode.TIMEOUT:                "Xử lý vượt quá thời gian cho phép",
    ErrorCode.AIRFLOW_UNAVAILABLE:    "Không thể kết nối đến Airflow",
    ErrorCode.AIRFLOW_BAD_RESPONSE:   "Airflow trả về phản hồi lỗi",
    ErrorCode.MONGO_WRITE_FAILED:     "Không thể ghi log vào MongoDB",
}

# Dành cho end user — ghi vào message
USER_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.INVALID_MESSAGE_FORMAT: "Yêu cầu không hợp lệ, vui lòng kiểm tra lại dữ liệu gửi lên.",
    ErrorCode.PROCESS_TYPE_NOT_FOUND: "Loại xử lý không được hỗ trợ, vui lòng kiểm tra lại.",
    ErrorCode.INTERNAL_ERROR:         "Đã xảy ra lỗi không xác định, vui lòng liên hệ quản trị viên.",
    ErrorCode.TIMEOUT:                "Hệ thống xử lý phản hồi quá chậm, vui lòng thử lại sau.",
    ErrorCode.AIRFLOW_UNAVAILABLE:    "Hệ thống xử lý tạm thời không khả dụng, vui lòng thử lại sau.",
    ErrorCode.AIRFLOW_BAD_RESPONSE:   "Hệ thống xử lý đang gặp sự cố, vui lòng thử lại sau.",
    ErrorCode.MONGO_WRITE_FAILED:     "Đã xảy ra lỗi ghi nhận, vui lòng liên hệ quản trị viên.",
}

# Map chi tiết cho 9003 theo HTTP status code — ưu tiên hơn USER_MESSAGES khi có status_code
AIRFLOW_HTTP_USER_MESSAGES: dict[int, str] = {
    400: "Dữ liệu gửi đi không hợp lệ, vui lòng liên hệ quản trị viên.",
    401: "Hệ thống xử lý chưa được cấu hình xác thực, vui lòng liên hệ quản trị viên.",
    403: "Hệ thống xử lý chưa được cấp quyền truy cập, vui lòng liên hệ quản trị viên.",
    404: "Kênh xử lý chưa được phát triển, vui lòng liên hệ quản trị viên.",
    409: "Yêu cầu đang được xử lý, vui lòng thử lại sau.",
    # 5xx không map cụ thể → fallback về USER_MESSAGES[AIRFLOW_BAD_RESPONSE]
}

# Các error code CÓ retry
RETRYABLE_ERRORS = {
    ErrorCode.INTERNAL_ERROR,
    ErrorCode.TIMEOUT,
    ErrorCode.AIRFLOW_UNAVAILABLE,
    ErrorCode.AIRFLOW_BAD_RESPONSE,
}

# ─── Kafka Input Message ──────────────────────────────────────────────────────

class S3Document(BaseModel):
    bucket: str
    key: str
    doc_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class KafkaInputMessage(BaseModel):
    client_message_id: str   = Field(..., description="UUID4 do client tạo")
    request_id: str          = Field(..., description="UUID4 định danh request")
    timestamp: Any           = Field(..., description="ISO string hoặc unix timestamp")
    s3_raw: List[S3Document] = Field(..., description="List hoặc single S3Document")
    process_type: ProcessType
    channel: Optional[str]   = Field(default=None, description="Mã kênh: hcm, pams, ...")
    doc_group: Optional[str] = Field(default=None)

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> datetime:
        if isinstance(v, datetime):
            return v
        if isinstance(v, (int, float)):
            return datetime.utcfromtimestamp(v)
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        raise ValueError(f"Không thể parse timestamp: {v!r}")

    @field_validator("s3_raw", mode="before")
    @classmethod
    def normalize_s3_raw(cls, v: Any) -> List[Any]:
        if isinstance(v, dict):
            return [v]
        if isinstance(v, list):
            return v
        raise ValueError(f"s3_raw phải là dict hoặc list, nhận được: {type(v).__name__}")

# ─── Processing Result ────────────────────────────────────────────────────────

class ProcessingResult(BaseModel):
    success: bool
    request_id: str
    client_message_id: str = "unknown"
    dag_id: Optional[str] = None
    dag_run_ids: List[str] = []
    doc_id: Optional[str] = None
    status: ProcessStatus
    error_code: Optional[ErrorCode] = None
    error_message: Optional[str] = None   # technical — ghi vào sys_message
    user_message: Optional[str] = None    # end user — ghi vào message
    retry_count: int = 0

    @property
    def dag_run_id(self) -> Optional[str]:
        """Backward compat – trả về run_id đầu tiên."""
        return self.dag_run_ids[0] if self.dag_run_ids else None


# ─── MongoDB Log Document ─────────────────────────────────────────────────────

class WorkflowLog(BaseModel):
    request_id: str
    client_message_id: str
    process_type: str
    channel: Optional[str]
    dag_id: str
    dag_run_id: Optional[str]
    status: str
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    s3_documents: List[dict[str, Any]] = []
    doc_id: Optional[str] = None


# ─── Kafka Output Message ─────────────────────────────────────────────────────

class KafkaOutputMessage(BaseModel):
    """
    Message publish ra topic APP_AI_CUA_OUT sau khi có lỗi.

    error payload:
        {
            code:        <int>,
            name:        <str>,
            message:     <str>  ← tiếng Việt, end user đọc,
            sys_message: <str>  ← technical detail, engineer trace
        }
    """
    request_id: str
    client_message_id: str
    timestamp: str
    process_type: str
    channel: Optional[str]
    status: ProcessStatus
    dag_id: Optional[str] = None
    dag_run_ids: List[str] = []
    doc_id: str = None
    error: Optional[dict[str, Any]] = None

    @classmethod
    def from_result(
        cls,
        result: "ProcessingResult",
        input_message: "KafkaInputMessage",
    ) -> "KafkaOutputMessage":
        error_payload = None
        if not result.success and result.error_code is not None:
            error_payload = {
                "code":        result.error_code.value,
                "name":        result.error_code.name,
                "message":     result.user_message or USER_MESSAGES.get(result.error_code, ""),
                "sys_message": result.error_message or ERROR_MESSAGES.get(result.error_code, ""),
            }

        return cls(
            request_id=result.request_id,
            client_message_id=input_message.client_message_id,
            timestamp=datetime.utcnow().isoformat() + "Z",
            process_type=input_message.process_type.value,
            channel=input_message.channel,
            status=result.status,
            dag_id=result.dag_id,
            dag_run_ids=result.dag_run_ids,
            doc_id=result.doc_id,
            error=error_payload,
        )

    @classmethod
    def from_invalid(
        cls,
        result: "ProcessingResult",
        channel: Optional[str] = None,
        process_type: str = "unknown",
    ) -> "KafkaOutputMessage":
        error_payload = None
        if result.error_code is not None:
            error_payload = {
                "code":        result.error_code.value,
                "name":        result.error_code.name,
                "message":     result.user_message or USER_MESSAGES.get(result.error_code, ""),
                "sys_message": result.error_message or ERROR_MESSAGES.get(result.error_code, ""),
            }

        return cls(
            request_id=result.request_id,
            client_message_id=result.client_message_id,
            timestamp=datetime.utcnow().isoformat() + "Z",
            process_type=process_type,
            channel=channel,
            status=result.status,
            dag_id=None,
            error=error_payload,
        )