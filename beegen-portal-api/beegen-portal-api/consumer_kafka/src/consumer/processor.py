"""
Message Processor – Orchestrator chính của Consumer Service.

Luồng xử lý:
    ┌─────────────────────────────────────────────────────────┐
    │  Bước 1: Parse & Validate Kafka message                 │
    │    ├─ JSON decode error   → ErrorCode 1000, INVALID     │
    │    │    └─ publish Kafka OUT (error) + save log         │
    │    └─ Schema validation   → ErrorCode 1000, INVALID     │
    │         └─ publish Kafka OUT (error) + save log         │
    ├─────────────────────────────────────────────────────────┤
    │  Bước 2: Resolve DAG ID                                 │
    │    └─ process_type không tồn tại → ErrorCode 1001       │
    │         └─ publish Kafka OUT (error) + save log         │
    ├─────────────────────────────────────────────────────────┤
    │  Bước 3: Trigger Airflow DAG (có retry)                 │
    │    ├─ Network/Timeout     → retry → ErrorCode 9002/9001 │
    │    ├─ HTTP 5xx            → retry → ErrorCode 9003      │
    │    ├─ HTTP 4xx            → NO retry → ErrorCode 9003   │
    │    │    └─ (mọi lỗi bước 3) publish Kafka OUT + save    │
    │    │         → KHÔNG commit → Kafka re-deliver          │
    │    └─ Thành công          → status = TRIGGERED          │
    │         └─ CHỈ save log, KHÔNG publish Kafka OUT        │
    ├─────────────────────────────────────────────────────────┤
    │  Bước 4 (error only): Publish error ra APP_AI_CUA_OUT   │
    ├─────────────────────────────────────────────────────────┤
    │  Bước 5: Lưu log vào MongoDB                            │
    │    └─ Write failed        → ErrorCode 9004 (log only)   │
    └─────────────────────────────────────────────────────────┘

Return: ProcessingResult (success/fail + error_code + retry_count)
"""

import json
from typing import Any

import structlog
from pydantic import ValidationError

from src.models.message import (
    KafkaInputMessage,
    KafkaOutputMessage,
    ProcessingResult,
    ProcessStatus,
    WorkflowLog,
    ErrorCode,
    ERROR_MESSAGES,
    USER_MESSAGES,
)
from src.models.exceptions import (
    CUABaseException,
    InvalidMessageFormatError,
    ProcessTypeNotFoundError,
    AirflowUnavailableError,
    AirflowTimeoutError,
    AirflowBadResponseError,
    MongoWriteFailedError,
    InternalError,
)
from src.router.dag_resolver import resolve_dag_id
from src.services.airflow_client import airflow_client, NON_RETRYABLE_HTTP_CODES
from src.services.mongo_service import mongo_service
from src.services.kafka_producer import kafka_producer

logger = structlog.get_logger(__name__)


def _get_user_message(e: CUABaseException) -> str:
    """
    Lấy user_message từ exception.
    AirflowBadResponseError tự resolve theo status_code (404, 403, ...).
    Các exception khác fallback về USER_MESSAGES theo error_code.
    """
    if hasattr(e, "user_message"):
        return e.user_message
    return USER_MESSAGES.get(e.error_code, "Đã xảy ra lỗi, vui lòng thử lại sau.")


class MessageProcessor:
    """
    Async processor. Mỗi lần gọi process() xử lý một Kafka message.
    Luôn trả về ProcessingResult — không raise exception ra ngoài.

    Publish Kafka OUT chỉ khi có lỗi.
    Trigger thành công → chỉ save log MongoDB.
    """

    async def process(self, raw_message: bytes) -> ProcessingResult:
        """
        Xử lý một message từ Kafka (async).

        Args:
            raw_message: Raw bytes từ Kafka consumer.

        Returns:
            ProcessingResult chứa trạng thái và error_code nếu thất bại.
        """

        # ══════════════════════════════════════════════════════════════════════
        # BƯỚC 1: Parse & Validate
        # ══════════════════════════════════════════════════════════════════════
        raw_payload       = self._extract_raw_payload(raw_message)
        raw_request_id    = raw_payload.get("request_id", "unknown") if raw_payload else "unknown"
        raw_client_msg_id = raw_payload.get("client_message_id", "unknown") if raw_payload else "unknown"
        raw_channel       = raw_payload.get("channel") if raw_payload else None
        raw_process_type  = raw_payload.get("process_type", "unknown") if raw_payload else "unknown"

        try:
            message = self._parse_and_validate(raw_payload if raw_payload is not None else raw_message)
        except InvalidMessageFormatError as e:
            logger.error(
                "step1_invalid_message",
                request_id=raw_request_id,
                client_message_id=raw_client_msg_id,
                error=str(e),
            )
            result = ProcessingResult(
                success=False,
                request_id=raw_request_id,
                client_message_id=raw_client_msg_id,
                dag_id=None,
                status=ProcessStatus.INVALID,
                error_code=e.error_code,
                error_message=str(e),
                user_message=USER_MESSAGES.get(e.error_code, ""),
            )
            await self._publish_invalid(result, channel=raw_channel, process_type=raw_process_type)
            await self._try_save_log_for_unknown(result)
            return result

        log = logger.bind(
            request_id=message.request_id,
            client_message_id=message.client_message_id,
            process_type=message.process_type.value,
            channel=message.channel,
        )
        log.info("step1_message_parsed_ok")

        # ══════════════════════════════════════════════════════════════════════
        # BƯỚC 2: Resolve DAG ID
        # ══════════════════════════════════════════════════════════════════════
        try:
            dag_id = resolve_dag_id(message.process_type, message.channel)
            log.info("step2_dag_resolved", dag_id=dag_id)
        except ProcessTypeNotFoundError as e:
            log.error("step2_process_type_not_found", error=str(e))
            result = ProcessingResult(
                success=False,
                request_id=message.request_id,
                client_message_id=message.client_message_id,
                dag_id=None,
                status=ProcessStatus.INVALID,
                error_code=e.error_code,
                error_message=str(e),
                user_message=USER_MESSAGES.get(e.error_code, ""),
            )
            await self._publish_and_save(message=message, result=result)
            return result

        # ══════════════════════════════════════════════════════════════════════
        # BƯỚC 3: Trigger Airflow
        # ══════════════════════════════════════════════════════════════════════
        doc_results = airflow_client.trigger_dag_for_each_document(
            dag_id=dag_id,
            message=message,
        )

        dag_run_ids: list[str] = []
        has_failure = False
        has_retryable_failure = False

        for doc_result in doc_results:
            doc_id = doc_result["doc_id"]

            if doc_result["success"]:
                dag_run_ids.append(doc_result["dag_run_id"])
                log.info("step3_doc_triggered_ok", dag_id=dag_id, doc_id=doc_id, dag_run_id=doc_result["dag_run_id"])
                continue

            has_failure = True
            e = doc_result["exception"]

            if isinstance(e, AirflowBadResponseError):
                is_client_error = e.status_code in NON_RETRYABLE_HTTP_CODES
                retry_count     = 0 if is_client_error else airflow_client._max_attempts
                process_status  = ProcessStatus.INVALID if is_client_error else ProcessStatus.FAILED
                error_code      = e.error_code
                error_message   = str(e)
                user_message    = _get_user_message(e)
                if not is_client_error:
                    has_retryable_failure = True
            elif isinstance(e, (AirflowUnavailableError, AirflowTimeoutError)):
                retry_count    = airflow_client._max_attempts
                process_status = ProcessStatus.FAILED
                error_code     = e.error_code
                error_message  = str(e)
                user_message   = _get_user_message(e)
                has_retryable_failure = True
            elif isinstance(e, CUABaseException):
                retry_count    = airflow_client._max_attempts if e.retryable else 0
                process_status = ProcessStatus.FAILED
                error_code     = e.error_code
                error_message  = str(e)
                user_message   = _get_user_message(e)
                if e.retryable:
                    has_retryable_failure = True
            else:
                retry_count    = 0
                process_status = ProcessStatus.FAILED
                error_code     = ErrorCode.INTERNAL_ERROR
                error_message  = f"Lỗi không xác định: {e}"
                user_message   = USER_MESSAGES[ErrorCode.INTERNAL_ERROR]
                has_retryable_failure = True

            log.error(
                "step3_doc_trigger_failed",
                dag_id=dag_id,
                doc_id=doc_id,
                error_code=error_code,
                process_status=process_status.value,
                error=error_message,
            )

            doc_fail_result = ProcessingResult(
                success=False,
                request_id=message.request_id,
                client_message_id=message.client_message_id,
                dag_id=dag_id,
                doc_id=doc_id,
                status=process_status,
                error_code=error_code,
                error_message=error_message,
                user_message=user_message,
                retry_count=retry_count,
            )
            await self._publish_and_save(message=message, result=doc_fail_result)
        
        # ── Tổng kết batch ──
        if not has_failure:
            result = ProcessingResult(
                success=True,
                request_id=message.request_id,
                client_message_id=message.client_message_id,
                dag_id=dag_id,
                dag_run_ids=dag_run_ids,
                status=ProcessStatus.TRIGGERED,
            )
        else:
            overall_status = ProcessStatus.FAILED if has_retryable_failure else ProcessStatus.INVALID
            result = ProcessingResult(
                success=False,
                request_id=message.request_id,
                client_message_id=message.client_message_id,
                dag_id=dag_id,
                dag_run_ids=dag_run_ids,
                status=overall_status,
                error_code=ErrorCode.INTERNAL_ERROR,
                error_message="Một hoặc nhiều document trigger thất bại",
                retry_count=0,
            )

        # ══════════════════════════════════════════════════════════════════════
        # BƯỚC 4 + 5: Publish (chỉ khi lỗi) & Lưu log MongoDB
        # ══════════════════════════════════════════════════════════════════════
        if result.success:
            self._save_log(message=message, result=result)
            log.info(
                "processing_completed_success",
                dag_id=result.dag_id,
                dag_run_ids=result.dag_run_ids,
            )
        else:
            log.error(
                "processing_completed_with_failures",
                dag_id=result.dag_id,
                overall_status=result.status.value,
                failed_count=len([r for r in doc_results if not r["success"]]),
                success_count=len([r for r in doc_results if r["success"]]),
            )

        return result

    # ─── Private helpers ──────────────────────────────────────────────────────

    def _parse_and_validate(self, raw: bytes | dict | str) -> KafkaInputMessage:
        raw_type = type(raw).__name__
        logger.debug("parse_raw_message", raw_type=raw_type)

        try:
            if isinstance(raw, dict):
                payload = raw
            elif isinstance(raw, bytes):
                payload = json.loads(raw.decode("utf-8"))
            elif isinstance(raw, str):
                payload = json.loads(raw)
            else:
                raise InvalidMessageFormatError(
                    f"Kiểu dữ liệu message không hỗ trợ: {raw_type}"
                )
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise InvalidMessageFormatError(f"Không thể decode JSON: {e}", cause=e)

        try:
            return KafkaInputMessage.model_validate(payload)
        except ValidationError as e:
            raise InvalidMessageFormatError(f"Schema validation thất bại: {e}", cause=e)

    async def _publish_and_save(
        self,
        message: KafkaInputMessage,
        result: ProcessingResult,
    ) -> None:
        """Publish error ra Kafka OUT + lưu log MongoDB. Chỉ gọi khi result.success=False."""
        output_message = KafkaOutputMessage.from_result(
            result=result,
            input_message=message,
        )
        published = await kafka_producer.publish(output_message)
        if not published:
            logger.error(
                "step4_kafka_publish_failed",
                request_id=result.request_id,
                status=result.status.value,
                error_code=result.error_code,
            )
        self._save_log(message=message, result=result)

    def _save_log(self, message: KafkaInputMessage, result: ProcessingResult) -> None:
        log_doc = WorkflowLog(
            request_id=message.request_id,
            client_message_id=message.client_message_id,
            process_type=message.process_type.value,
            channel=message.channel,
            dag_id=result.dag_id or "unknown",
            dag_run_id=result.dag_run_id,
            status=result.status.value,
            error_code=result.error_code.value if result.error_code else None,
            error_message=result.error_message,
            retry_count=result.retry_count,
            s3_documents=[
                doc.model_dump() if hasattr(doc, "model_dump") else doc
                for doc in message.s3_raw
            ],
            doc_id=result.doc_id,
        )
        try:
            mongo_service.save_log(log_doc)
        except MongoWriteFailedError as e:
            logger.error(
                "step5_mongo_write_failed",
                request_id=message.request_id,
                error_code=ErrorCode.MONGO_WRITE_FAILED,
                error=str(e),
            )

    async def _publish_invalid(
        self,
        result: ProcessingResult,
        channel: str | None = None,
        process_type: str = "unknown",
    ) -> None:
        """Publish error khi bước 1 thất bại — dùng from_invalid vì chưa có KafkaInputMessage."""
        try:
            output_message = KafkaOutputMessage.from_invalid(
                result,
                channel=channel,
                process_type=process_type,
            )
            published = await kafka_producer.publish(output_message)
            if not published:
                logger.error(
                    "step1_kafka_publish_failed",
                    request_id=result.request_id,
                    error_code=result.error_code,
                )
        except Exception as e:
            logger.error("step1_publish_invalid_error", error=str(e))

    def _extract_raw_payload(self, raw: bytes | dict | str) -> dict | None:
        """Parse raw message thành dict không validate schema. Best-effort."""
        try:
            if isinstance(raw, dict):
                return raw
            elif isinstance(raw, bytes):
                return json.loads(raw.decode("utf-8"))
            elif isinstance(raw, str):
                return json.loads(raw)
        except Exception:
            pass
        return None

    async def _try_save_log_for_unknown(self, result: ProcessingResult) -> None:
        """Lưu log khi bước 1 thất bại hoàn toàn (request_id = unknown)."""
        log_doc = WorkflowLog(
            request_id="unknown",
            client_message_id="unknown",
            process_type="unknown",
            channel=None,
            dag_id="unknown",
            dag_run_id=None,
            status=result.status.value,
            error_code=result.error_code.value if result.error_code else None,
            error_message=result.error_message,
        )
        try:
            mongo_service.save_log(log_doc)
        except MongoWriteFailedError:
            logger.error("step5_mongo_write_failed_unknown_message")