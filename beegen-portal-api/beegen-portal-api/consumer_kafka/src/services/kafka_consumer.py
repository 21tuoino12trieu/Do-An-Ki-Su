"""
Kafka Consumer Loop (aiokafka)

- Lắng nghe topic APP_AI_CUA_IN bằng AIOKafkaConsumer
- Manual commit: chỉ commit offset sau khi xử lý xong
- Graceful shutdown khi nhận SIGINT/SIGTERM
- Xử lý message song song theo partition (asyncio.Task)
"""

import asyncio
import signal
import structlog
from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.errors import KafkaError, CommitFailedError
import ujson as json
import platform

from src.config.settings import settings
from src.consumer.processor import MessageProcessor
from src.models.message import ProcessStatus
from src.services.mongo_service import mongo_service
from src.services.kafka_producer import kafka_producer
from src.utils.aes import aes_decode

logger = structlog.get_logger(__name__)


class CUAConsumer:
    def __init__(self):
        self._consumer: AIOKafkaConsumer | None = None
        self._processor = MessageProcessor()
        self._running = False
        self._semaphore = asyncio.Semaphore(settings.kafka_max_concurrent_tasks)

    async def start(self):
        """Khởi động consumer. Block cho đến khi stop() được gọi."""
        self._setup_signal_handlers()

        mongo_service.connect()

        # Khởi động producer trước
        await kafka_producer.start()

        # Khởi động consumer
        self._consumer = AIOKafkaConsumer(
            settings.kafka_input_topic,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_deserializer=self._safe_deserializer,
            security_protocol="SASL_PLAINTEXT",
            sasl_mechanism="SCRAM-SHA-512",
            sasl_plain_username=settings.kafka_user,
            sasl_plain_password=aes_decode(settings.kafka_password),
            key_deserializer=lambda x: x.decode("utf-8") if x else None,
            max_poll_records=settings.kafka_consumer_batch_size,
            group_id=settings.kafka_group_id,
            auto_offset_reset=settings.kafka_auto_offset_reset,
            enable_auto_commit=False,   # Manual commit để kiểm soát at-least-once
            max_poll_interval_ms=settings.kafka_max_poll_interval_ms,
            session_timeout_ms=settings.kafka_session_timeout_ms,
            heartbeat_interval_ms=settings.kafka_heartbeat_interval_ms,
        )
        await self._consumer.start()
        self._running = True

        logger.info(
            "consumer_started",
            input_topic=settings.kafka_input_topic,
            output_topic=settings.kafka_output_topic,
            group_id=settings.kafka_group_id,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            max_concurrent_tasks=settings.kafka_max_concurrent_tasks,
        )

        try:
            await self._consume_loop()
        finally:
            await self._shutdown()

    def stop(self):
        logger.info("consumer_stop_requested")
        self._running = False

    @staticmethod
    def _safe_deserializer(m):
        raw = m.decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception as e:
            logger.error("json_decode_error", raw=raw, error=str(e))
            return {"_error": "invalid_json", "raw": raw}

    # ─── Consume loop ─────────────────────────────────────────────────────────

    async def _consume_loop(self):
        """
        Poll message và tạo asyncio.Task cho mỗi message.

        Tại sao dùng Task:
          Nếu await processor.process() chạy lâu (retry Airflow 30-60s),
          event loop bị block → heartbeat coroutine không được schedule
          → broker báo session expired / UnknownMemberIdError.
          Tạo Task riêng → poll loop + heartbeat luôn được chạy xen kẽ.
        """
        pending_tasks: set[asyncio.Task] = set()

        async for kafka_msg in self._consumer:
            if not self._running:
                logger.info("consumer_loop_stopped")
                break

            log = logger.bind(
                topic=kafka_msg.topic,
                partition=kafka_msg.partition,
                offset=kafka_msg.offset,
            )
            log.info("kafka_message_received")

            # Tạo Task xử lý độc lập → poll loop không bị block
            task = asyncio.create_task(
                self._handle_message(kafka_msg, log),
                name=f"msg-{kafka_msg.partition}-{kafka_msg.offset}",
            )
            pending_tasks.add(task)
            task.add_done_callback(pending_tasks.discard)

        # Chờ tất cả task hoàn thành trước khi shutdown
        if pending_tasks:
            logger.info("waiting_pending_tasks", count=len(pending_tasks))
            await asyncio.gather(*pending_tasks, return_exceptions=True)

    async def _handle_message(self, kafka_msg, log) -> None:
        """Xử lý 1 message trong Task riêng, giới hạn đồng thời bằng Semaphore."""
        async with self._semaphore:
            try:
                result = await self._processor.process(kafka_msg.value)

                if result.success:
                    await self._safe_commit(kafka_msg, log)
                    log.info(
                        "kafka_offset_committed",
                        request_id=result.request_id,
                        dag_run_id=result.dag_run_id,
                    )
                else:
                    log.error(
                        "message_processing_failed",
                        request_id=result.request_id,
                        client_message_id=result.client_message_id,
                        error_code=result.error_code,
                        error_name=result.error_code.name if result.error_code else None,
                        error_message=result.error_message,
                        retry_count=result.retry_count,
                        status=result.status.value,
                    )

                    # Lỗi input không thể fix → commit để skip, không retry
                    await self._safe_commit(kafka_msg, log)
                    log.warning(
                        "invalid_message_skipped",
                        reason="Message không hợp lệ hoặc lỗi khi verify",
                        error_code=result.error_code,
                    )

            except CommitFailedError as e:
                log.warning(
                    "commit_failed_will_rejoin",
                    error=str(e),
                    note="Consumer sẽ tự rejoin group và re-deliver message",
                )
            except Exception:
                log.exception("unhandled_exception_in_handle_message")

    async def _safe_commit(self, kafka_msg, log) -> None:
        """
        Commit offset của message cụ thể theo TopicPartition.
        Tránh race condition khi nhiều Task commit cùng lúc.
        """
        try:
            tp = TopicPartition(kafka_msg.topic, kafka_msg.partition)
            await self._consumer.commit({tp: kafka_msg.offset + 1})
        except CommitFailedError as e:
            log.warning(
                "safe_commit_failed",
                error=str(e),
                note="Consumer sẽ tự rejoin và retry message",
            )
        except Exception as e:
            log.error("safe_commit_error", error=str(e))

    # ─── Signal handlers ──────────────────────────────────────────────────────

    def _setup_signal_handlers(self):
        """
        Đăng ký signal handler tương thích cả Linux/Mac và Windows.
        - Linux/Mac: dùng loop.add_signal_handler (async-safe, hỗ trợ SIGTERM)
        - Windows:   dùng signal.signal (chỉ hỗ trợ SIGINT, không có SIGTERM)
        """
        if platform.system() == "Windows":
            signal.signal(signal.SIGINT, self._windows_signal_handler)
            logger.info("signal_handler_registered", mode="windows")
        else:
            loop = asyncio.get_event_loop()
            loop.add_signal_handler(signal.SIGINT,  self._handle_signal)
            loop.add_signal_handler(signal.SIGTERM, self._handle_signal)
            logger.info("signal_handler_registered", mode="unix")

    def _handle_signal(self):
        logger.info("shutdown_signal_received")
        self.stop()

    def _windows_signal_handler(self, signum, frame):
        logger.info("shutdown_signal_received", signum=signum)
        self.stop()

    async def _shutdown(self):
        if self._consumer:
            await self._consumer.stop()
        await kafka_producer.stop()
        mongo_service.disconnect()
        logger.info("consumer_shutdown_complete")