"""
Airflow REST API Client

Thực hiện POST /api/v1/dags/{dag_id}/dagRuns với:
  - Basic Auth
  - Retry tự động cho lỗi network và 5xx
  - Không retry cho lỗi 4xx (bad request)
  - Trả về exception tương ứng với ErrorCode

curl tương đương:
    curl --location 'https://host/api/v1/dags/{dag_id}/dagRuns' \
         --header 'Content-Type: application/json' \
         --header 'Authorization: Basic REPLACE_WITH_LOCAL_SECRET' \
         --data '{...}'
"""

import base64
import time
from typing import Any

import httpx
import structlog

from src.config.settings import settings
from src.utils.aes import aes_decode
from src.models.exceptions import (
    AirflowBadResponseError,
    AirflowTimeoutError,
    AirflowUnavailableError,
    InternalError,
)

logger = structlog.get_logger(__name__)

# HTTP status codes không nên retry (lỗi do caller)
NON_RETRYABLE_HTTP_CODES = {400, 401, 403, 404, 409}


def _build_basic_auth() -> str:
    return "Basic " + aes_decode(settings.airflow_auth)

class AirflowClient:
    """
    Client giao tiếp với Airflow REST API.

    Retry strategy:
        - Network error / Connection refused → retry (AirflowUnavailableError)
        - Timeout                            → retry (AirflowTimeoutError)
        - HTTP 5xx                           → retry (AirflowBadResponseError)
        - HTTP 4xx                           → KHÔNG retry (AirflowBadResponseError)
        - HTTP 200/201                       → thành công
    """

    def __init__(self):
        self.base_url      = settings.airflow_host.rstrip("/")
        self.timeout       = settings.airflow_api_timeout
        self._auth         = _build_basic_auth()
        self._max_attempts = settings.airflow_retry_max_attempts
        self._wait_min     = settings.airflow_retry_wait_min
        self._wait_max     = settings.airflow_retry_wait_max

    # ─── Public ───────────────────────────────────────────────────────────────

    def trigger_dag_for_each_document(
        self,
        dag_id: str,
        message: Any,   # KafkaInputMessage
    ) -> list[dict]:
        """
        Trigger 1 DAG run riêng cho mỗi document trong message.s3_raw.

        Conf mỗi run khớp với format Airflow đang nhận:
            {
                "channel":         message.channel,
                "collection_name": dag_id,
                "doc_group":       message.doc_group,
                "doc_id":          doc.doc_id,
                "s3_bucket":       doc.bucket,
                "s3_key":          doc.key,
                "kafka_topic":     settings.kafka_output_topic,
            }

        Returns:
            List[dict] — response JSON của từng DAG run, thứ tự = thứ tự s3_raw.

        Raises:
            Exception từ trigger_dag() nếu bất kỳ document nào thất bại.
        """
        s3_docs = message.s3_raw

        logger.info(
            "airflow_trigger_batch_start",
            dag_id=dag_id,
            doc_count=len(s3_docs),
            request_id=message.request_id,
        )
        collection_name = f"{message.channel}_{message.process_type.value}".lower()

        results = []
        for idx, doc in enumerate(s3_docs):
            # Hỗ trợ cả S3Document (Pydantic model) lẫn dict thô
            if hasattr(doc, "bucket"):
                bucket = doc.bucket
                key    = doc.key
                doc_id = doc.doc_id
            else:
                bucket = doc.get("bucket", "")
                key    = doc.get("key", "")
                doc_id = doc.get("doc_id", "")

            conf = {
                "client_message_id": message.client_message_id,
                "request_id": message.request_id,
                "channel":         message.channel,
                "collection_name": collection_name,
                "doc_group":       message.doc_group,
                "doc_id":          doc_id,
                "s3_bucket":       bucket,
                "s3_key":          key,
                "kafka_topic":     settings.kafka_output_topic,
            }

            logger.info(
                "airflow_trigger_document",
                dag_id=dag_id,
                doc_index=idx + 1,
                doc_total=len(s3_docs),
                doc_id=doc_id,
                s3_key=key,
                request_id=message.request_id,
            )
            try:
                response = self.trigger_dag(dag_id=dag_id, conf=conf)
                results.append({
                    "success":    True,
                    "doc_id":     doc_id,
                    "dag_run_id": response.get("dag_run_id", ""),
                })
            except Exception as e:
                logger.error(
                    "airflow_trigger_document_failed",
                    dag_id=dag_id,
                    doc_id=doc_id,
                    doc_index=idx + 1,
                    error=str(e),
                    request_id=message.request_id,
                )
                results.append({
                    "success":   False,
                    "doc_id":    doc_id,
                    "exception": e,
                })
        
        success_count = sum(1 for r in results if r["success"])
        logger.info(
            "airflow_trigger_batch_done",
            dag_id=dag_id,
            total=len(results),
            success=success_count,
            failed=len(results) - success_count,
            request_id=message.request_id,
        )
        return results

    def trigger_dag(
        self,
        dag_id: str,
        conf: dict[str, Any] | None = None,
        dag_run_id: str | None = None,
    ) -> dict:
        """
        Trigger một Airflow DAG run.

        Args:
            dag_id:     ID của DAG cần trigger.
            conf:       Config dict truyền vào DAG run.
            dag_run_id: Custom run ID (Airflow tự sinh nếu không truyền).

        Returns:
            Response JSON từ Airflow (chứa dag_run_id, state, ...).

        Raises:
            AirflowUnavailableError:  Network error, connection refused.
            AirflowTimeoutError:      Request timeout.
            AirflowBadResponseError:  HTTP 4xx/5xx từ Airflow.
            InternalError:            Lỗi không xác định.
        """
        url = f"{self.base_url}/api/v1/dags/{dag_id}/dagRuns"
        payload: dict[str, Any] = {}
        if conf:
            payload["conf"] = conf
        if dag_run_id:
            payload["dag_run_id"] = dag_run_id

        last_exception: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            log = logger.bind(dag_id=dag_id, attempt=attempt, max_attempts=self._max_attempts)
            log.info("airflow_trigger_attempt", url=url)

            try:
                result = self._do_request(url, payload)
                log.info("airflow_trigger_success", dag_run_id=result.get("dag_run_id"))
                return result

            except (AirflowUnavailableError, AirflowTimeoutError) as e:
                last_exception = e
                log.warning(
                    "airflow_retryable_error",
                    error_code=e.error_code,
                    error=e.message,
                    will_retry=(attempt < self._max_attempts),
                )

            except AirflowBadResponseError as e:
                # 4xx → không retry
                if e.status_code in NON_RETRYABLE_HTTP_CODES:
                    log.error(
                        "airflow_non_retryable_http_error",
                        status_code=e.status_code,
                        error=e.message,
                    )
                    raise
                # 5xx → retry
                last_exception = e
                log.warning(
                    "airflow_5xx_error",
                    status_code=e.status_code,
                    error=e.message,
                    will_retry=(attempt < self._max_attempts),
                )

            except Exception as e:
                last_exception = InternalError(f"Lỗi không xác định khi trigger DAG: {e}", cause=e)
                log.exception("airflow_unexpected_error")

            # Chờ trước khi retry (exponential backoff, giới hạn bởi wait_max)
            if attempt < self._max_attempts:
                wait_seconds = min(self._wait_min * (2 ** (attempt - 1)), self._wait_max)
                log.info("airflow_retry_wait", wait_seconds=wait_seconds)
                time.sleep(wait_seconds)

        # Hết số lần retry
        logger.error(
            "airflow_all_retries_exhausted",
            dag_id=dag_id,
            max_attempts=self._max_attempts,
            last_error=str(last_exception),
        )
        raise last_exception  # type: ignore[misc]

    # ─── Private ──────────────────────────────────────────────────────────────

    def _do_request(self, url: str, payload: dict) -> dict:
        """Thực hiện một HTTP request đơn. Raise exception nếu thất bại."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": self._auth,
        }

        try:
            with httpx.Client(timeout=self.timeout, verify=False) as client:
                response = client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as e:
            raise AirflowTimeoutError(
                f"Request đến Airflow timeout sau {self.timeout}s", cause=e
            )
        except httpx.ConnectError as e:
            raise AirflowUnavailableError(
                f"Cannot connect to airflow: {url}", cause=e
            )
        except httpx.RequestError as e:
            raise AirflowUnavailableError(
                f"Lỗi network khi gọi Airflow: {e}", cause=e
            )

        if response.status_code not in (200, 201):
            raise AirflowBadResponseError(
                message=f"Airflow trả về HTTP {response.status_code}",
                status_code=response.status_code,
                response_body=response.text,
            )
        return response.json()


# Singleton
airflow_client = AirflowClient()