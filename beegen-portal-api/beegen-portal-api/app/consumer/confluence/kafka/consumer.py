import json
import logging
from pathlib import Path
from typing import Any

import yaml
from aiokafka import AIOKafkaConsumer
from dotenv import load_dotenv

load_dotenv(".env")

from beegen.loggings import LOGGER

from app.consumer.confluence.chunk_confluence_document import (
    build_chunk_confluence_document_workflow,
)


logger = logging.getLogger(__name__)

def parse_chunking_job(
    bot_id: str,
    value: dict[str, Any],
) -> dict[str, Any] | None:
    if value.get("message_type") != "CHUNKING" or value.get("system") != "CONFLUENCE":
        return None
    items = value["data"]
    return {
        "job_id": str(value["job_id"]),
        "bot_id": bot_id,
        "items": [
            {
                "document_id": item["document_id"],
                "content_path": item["content_path"],
                "sync_version": item["sync_version"],
                "dispatch_status": item["dispatch_status"],
                "error_detail": item["error_detail"],
                "bot_id": bot_id,
            }
            for item in items
        ],
    }


def load_consumer_config() -> tuple[str, dict[str, Any]]:
    with Path("config/kafka.yaml").open(encoding="utf-8") as config_file:
        kafka = yaml.safe_load(config_file)["kafka"]

    topic = kafka["kafka_topic_log"]
    if not topic:
        raise RuntimeError("kafka_topic_log is missing from Kafka config")

    consumer_kwargs = {
        "bootstrap_servers": kafka["kafka_bootstrap_servers"],
        "security_protocol": kafka["kafka_security_protocol"],
        "sasl_mechanism": kafka["kafka_sasl_mechanism"],
        "sasl_plain_username": kafka["kafka_sasl_username"],
        "sasl_plain_password": kafka["kafka_sasl_password"],
        "group_id": kafka["kafka_group_id"],
        "enable_auto_commit": False,
        "max_poll_interval_ms": 10800000,
        "key_deserializer": lambda raw: raw.decode("utf-8"),
    }
    return topic, consumer_kwargs


async def run_consumer() -> None:
    request_topic, consumer_kwargs = load_consumer_config()
    workflow = build_chunk_confluence_document_workflow()
    consumer = AIOKafkaConsumer(request_topic, **consumer_kwargs)
    await consumer.start()
    try:
        async for message in consumer:
            try:
                value = json.loads(message.value)
            except json.JSONDecodeError:
                logger.debug("Skipping invalid Kafka JSON topic=%s partition=%s offset=%s payload=%r", message.topic, message.partition, message.offset, message.value[:500])
                await consumer.commit()
                continue

            job = parse_chunking_job(bot_id=message.key, value=value)
            if job is None:
                await consumer.commit()
                continue

            LOGGER.info("Starting Confluence Beeflow workflow: job_id=%s items=%d", job["job_id"], len(job["items"]))
            result = await workflow.run(
                request_id=job["job_id"],
                inputs={
                    "job_id": job["job_id"], 
                    "bot_id": job["bot_id"],
                    "job_items": job["items"], 
                    "response_topic": request_topic,
                },
            )
            if result.get("processing_completed") is not True:
                raise RuntimeError("Chunk job did not reach a successful terminal node")
            LOGGER.info("Completed Confluence Beeflow workflow: job_id=%s", job["job_id"])
            await consumer.commit()
    finally:
        await consumer.stop()
