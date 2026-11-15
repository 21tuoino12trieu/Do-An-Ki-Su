"""DAG hạ tầng: mỗi giờ gửi rồi đọc lại một sự kiện Kafka giả lập."""
from datetime import datetime, timedelta, timezone
import json
import time
import uuid

from airflow.sdk import dag, task


@dag(dag_id="infra_kafka_smoke", schedule="0 * * * *", start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
     catchup=False, max_active_runs=1, is_paused_upon_creation=True,
     default_args={"retries": 1, "retry_delay": timedelta(seconds=15), "execution_timeout": timedelta(minutes=2)},
     tags=["infra", "kafka", "demo"])
def kafka_smoke():
    @task
    def send_event():
        from kafka import KafkaProducer
        from kafka.admin import KafkaAdminClient, NewTopic
        from kafka.errors import TopicAlreadyExistsError
        config = {"bootstrap_servers": "kafka:29092", "api_version": (2, 6, 0), "request_timeout_ms": 15000}
        topic = "doan.airflow.smoke.v1"
        admin = KafkaAdminClient(**config)
        try:
            try:
                admin.create_topics([NewTopic(topic, 1, 1, topic_configs={"retention.ms": "604800000"})])
            except TopicAlreadyExistsError:
                pass
        finally:
            admin.close()
        event = {"event_id": str(uuid.uuid4()), "event_type": "infra.airflow.smoke", "schema_version": 1,
                 "occurred_at": datetime.now(timezone.utc).isoformat(), "message": "Airflow gửi sự kiện giả lập"}
        producer = KafkaProducer(**config, acks="all", retries=3, max_block_ms=30000)
        try:
            metadata = producer.send(topic, key=b"AIRFLOW-DEMO", value=json.dumps(event, ensure_ascii=False).encode("utf-8")).get(timeout=30)
        finally:
            producer.close(timeout=10)
        return {"topic": topic, "partition": metadata.partition, "offset": metadata.offset, "event": event}

    @task
    def verify_event(sent):
        from kafka import KafkaConsumer, TopicPartition
        consumer = KafkaConsumer(bootstrap_servers="kafka:29092", api_version=(2, 6, 0),
                                 enable_auto_commit=False, group_id=None, request_timeout_ms=15000)
        try:
            tp = TopicPartition(sent["topic"], sent["partition"])
            consumer.assign([tp])
            consumer.seek(tp, sent["offset"])
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                records = consumer.poll(timeout_ms=1000, max_records=1).get(tp, [])
                if records:
                    record = records[0]
                    if record.offset != sent["offset"] or record.key != b"AIRFLOW-DEMO" or json.loads(record.value) != sent["event"]:
                        raise RuntimeError("Kafka trả sự kiện không khớp.")
                    print(f"Đã xác nhận sự kiện tại {tp.topic}/{tp.partition}/{record.offset}")
                    return {"verified": True, "event_id": sent["event"]["event_id"]}
            raise RuntimeError("Hết thời gian đọc sự kiện Kafka.")
        finally:
            consumer.close()

    verify_event(send_event())


kafka_smoke()
