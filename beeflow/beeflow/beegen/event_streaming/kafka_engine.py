import asyncio
import json
import traceback
from enum import Enum
from typing import Any, Dict, List, Optional

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from beegen.configs.event_streaming.kafka_config import KafkaConfig, KafkaOperation

from beegen.loggings import LOGGER


class KafkaEngine:
    """Unified Kafka engine handling PRODUCE and CONSUME operations only."""

    def __init__(self, config: KafkaConfig):
        self.config = config
        self.operation_map = {
            KafkaOperation.PRODUCE: self._produce,
            KafkaOperation.CONSUME: self._consume,
        }

    # --- Helpers -----------------------------------------------------------------
    async def _get_producer(self) -> AIOKafkaProducer:
        producer = AIOKafkaProducer(**self.config.to_aiokafka_producer_kwargs())
        await producer.start()
        return producer

    async def _get_consumer(self, topics: List[str]) -> AIOKafkaConsumer:
        consumer = AIOKafkaConsumer(*topics, **self.config.to_aiokafka_consumer_kwargs())
        await consumer.start()
        return consumer

    # --- Operations ---------------------------------------------------------------
    async def _produce(self, **params) -> Dict[str, Any]:
        """
        Send a message to a Kafka topic.

        Args:
            topic (str): Topic name.
            value (str | bytes | dict): Message payload.
            key (Optional[str | bytes]): Optional key.
            headers (Optional[Dict[str, str]]): Optional headers.
            partition (Optional[int]): Target partition.
        """
        topic: str = params["topic"]
        value = params["value"]
        key = params.get("key")
        headers: Optional[Dict[str, str]] = params.get("headers")
        partition: Optional[int] = params.get("partition")

        # Normalize payload
        if isinstance(value, dict):
            value = json.dumps(value).encode("utf-8")
        elif isinstance(value, str):
            value = value.encode("utf-8")
        elif not isinstance(value, (bytes, bytearray)):
            raise TypeError("value must be dict | str | bytes")

        if isinstance(key, str):
            key = key.encode("utf-8")

        hdrs = None
        if headers:
            hdrs = [(str(k), str(v).encode("utf-8")) for k, v in headers.items()]

        producer = await self._get_producer()
        try:
            metadata = await producer.send_and_wait(topic, value=value, key=key, headers=hdrs, partition=partition)
            return {
                "status": "success",
                "partition_written": metadata.partition,
                "offset": metadata.offset,
                "timestamp": getattr(metadata, "timestamp", None),
                "message": "Message produced successfully",
            }
        finally:
            await producer.stop()

    async def _consume(self, **params) -> Dict[str, Any]:
        """
        Consume messages from one or more topics.

        Args:
            topics (List[str] | str): Topic(s) to subscribe.
            max_messages (int): Maximum number of records to return.
            timeout_ms (int): Poll timeout in milliseconds.
            commit (bool): Whether to commit offsets after read (when group_id is set and enable_auto_commit=False).
            decode (bool): If True, try to decode value/key as UTF-8 strings.
        """
        topics = params.get("topics")
        if isinstance(topics, str):
            topics = [topics]
        if not topics:
            raise ValueError("topics is required")

        max_messages: int = params.get("max_messages", 1)
        timeout_ms: int = params.get("session_timeout_ms", 1000)
        commit: bool = params.get("commit", False)
        decode: bool = params.get("decode", True)

        consumer = await self._get_consumer(topics)
        messages: List[Dict[str, Any]] = []
        try:
            remaining = max_messages
            while remaining > 0:
                batch_map = await consumer.getmany(timeout_ms=timeout_ms, max_records=remaining)
                if not batch_map:
                    break

                for tp, records in batch_map.items():
                    for record in records:
                        item: Dict[str, Any] = {
                            "topic": record.topic,
                            "partition": record.partition,
                            "offset": record.offset,
                            "timestamp": record.timestamp,
                            "headers": {k: (v.decode("utf-8", "ignore") if isinstance(v, (bytes, bytearray)) else v) for k, v in (record.headers or [])},
                        }
                        val = record.value
                        k = record.key
                        if decode:
                            val = val.decode("utf-8", "ignore") if isinstance(val, (bytes, bytearray)) else val
                            k = k.decode("utf-8", "ignore") if isinstance(k, (bytes, bytearray)) else k
                        item["key"] = k
                        item["value"] = val
                        messages.append(item)
                        remaining -= 1
                        if remaining <= 0:
                            break
                    if remaining <= 0:
                        break

                if commit and self.config.group_id:
                    await consumer.commit()

                if len(messages) >= max_messages:
                    break

            return {"status": "success", "messages": messages, "count": len(messages), "message": "Consume completed"}
        finally:
            await consumer.stop()

    # --- Public entry ------------------------------------------------------------
    async def run(self, operation: KafkaOperation, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            func = self.operation_map.get(operation)
            if not func:
                raise ValueError(f"Unsupported operation: {operation}")
            return await func(**params)
        except Exception:
            return {"status": "error", "message": traceback.format_exc()}
        
async def main():
    from beegen.registry.resource_hub import RESOURCE_HUB
    engine = RESOURCE_HUB.kafka("aicenter-cua")

    # 1) PRODUCE
    result_produce = await engine.run(
        KafkaOperation.PRODUCE,
        params={
            "topic": "APP_AI_CUA_OUT",
            "value": {"event": "hello", "source": "beeflow", "ok": True},
            "headers": {"x-env": "dev"},
        },
    )
    print("Produce =>", result_produce)

    # 2) CONSUME (read back a message)
    result_consume = await engine.run(
        KafkaOperation.CONSUME,
        params={
            "topics": "APP_AI_CUA_IN",
            "max_messages": 10,
            "session_timeout_ms": 2000,
            "commit": False,  # set True if you want to commit and you have a group_id
            "decode": True,
        },
    )
    print("Consume =>", result_consume)

if __name__ == "__main__":
    asyncio.run(main())