"""
Kafka Producer Service (aiokafka)

Publish kết quả xử lý ra topic APP_AI_CUA_OUT.
Hỗ trợ SASL_PLAINTEXT / SCRAM-SHA-512.
"""

import json
import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from src.config.settings import settings
from src.models.message import KafkaOutputMessage
from src.utils.aes import aes_decode

logger = structlog.get_logger(__name__)


def _build_sasl_kwargs() -> dict:
    if settings.kafka_user and settings.kafka_password:
        return {
            "security_protocol":   settings.kafka_security_protocol,
            "sasl_mechanism":      settings.kafka_sasl_mechanism,
            "sasl_plain_username": settings.kafka_user,
            "sasl_plain_password": aes_decode(settings.kafka_password),
        }
    return {}


class CUAProducer:
    def __init__(self):
        self._producer: AIOKafkaProducer | None = None

    async def start(self):
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            acks="all",
            linger_ms=10,
            compression_type="gzip",
            **_build_sasl_kwargs(),
        )
        await self._producer.start()
        logger.info("kafka_producer_started", output_topic=settings.kafka_output_topic)

    async def stop(self):
        if self._producer:
            await self._producer.stop()
            logger.info("kafka_producer_stopped")

    async def publish(self, output_message: KafkaOutputMessage) -> bool:
        payload     = output_message.model_dump(mode="json")
        key         = output_message.request_id
        key_bytes   = key.encode("utf-8") if isinstance(key, str) else key
        value_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        log = logger.bind(
            request_id=key,
            status=output_message.status.value,
            topic=settings.kafka_output_topic,
        )

        try:
            record_metadata = await self._producer.send_and_wait(
                topic=settings.kafka_output_topic,
                key=key_bytes,
                value=value_bytes,
            )
            log.info(
                "kafka_output_published",
                partition=record_metadata.partition,
                offset=record_metadata.offset,
            )
            return True
        except KafkaError as e:
            log.error("kafka_publish_failed", error=str(e))
            return False
        except Exception as e:
            log.error("kafka_publish_unexpected_error", error=str(e))
            return False


# Singleton
kafka_producer = CUAProducer()