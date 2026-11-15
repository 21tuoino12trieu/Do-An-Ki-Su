"""python test_kafka.py [--read-only]. Cần kafka-python (đã có trong namcuong).

Test hạ tầng với sự kiện giả, không phải hợp đồng sự kiện nghiệp vụ cuối cùng.
Giữ topic/message/consumer group để xem trên Offset Explorer.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import uuid

from kafka import KafkaConsumer, KafkaProducer, TopicPartition
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError
from kafka.structs import OffsetAndMetadata

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "tests/output/kafka_smoke_manifest.json"
TOPIC = "doan.infra.smoke.v1"
BROKER = "127.0.0.1:9092"
COMMON = {"bootstrap_servers": BROKER, "request_timeout_ms": 15000,
          # Protocol baseline cho client kafka-python 2.2.3 hiện có.
          "api_version": (2, 6, 0)}


def read_exact(manifest):
    consumer = KafkaConsumer(**COMMON, enable_auto_commit=False, group_id=manifest["group_id"])
    try:
        tp = TopicPartition(manifest["topic"], manifest["partition"])
        consumer.assign([tp])
        consumer.seek(tp, manifest["offset"])
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            records = consumer.poll(timeout_ms=1000, max_records=1).get(tp, [])
            if records:
                record = records[0]
                if record.offset != manifest["offset"] or record.key != manifest["key"].encode("utf-8"):
                    raise RuntimeError("Offset hoặc key không khớp.")
                if json.loads(record.value.decode("utf-8")) != manifest["event"]:
                    raise RuntimeError("Nội dung sự kiện không khớp.")
                return consumer, tp
        raise RuntimeError("Không đọc được message trong 30 giây.")
    except BaseException:
        consumer.close()
        raise


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-only", action="store_true")
    args = parser.parse_args()
    consumer = None
    try:
        if args.read_only:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        else:
            admin = KafkaAdminClient(**COMMON, client_id="doan-infra-admin")
            try:
                try:
                    admin.create_topics([NewTopic(TOPIC, num_partitions=3, replication_factor=1,
                                                 topic_configs={"cleanup.policy": "delete", "retention.ms": "604800000"})])
                except TopicAlreadyExistsError:
                    pass
            finally:
                admin.close()
            event_id = str(uuid.uuid4())
            event = {"schema_version": 1, "event_id": event_id, "event_type": "infra.smoke",
                     "occurred_at": datetime.now(timezone.utc).isoformat(),
                     "page_id": "DEMO-0001", "message": "Kiểm tra Kafka cho đồ án — dữ liệu giả lập"}
            producer = KafkaProducer(**COMMON, acks="all", retries=3, max_block_ms=30000,
                                     key_serializer=lambda v: v.encode("utf-8"),
                                     value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"))
            try:
                metadata = producer.send(TOPIC, key="DEMO-0001", value=event).get(timeout=30)
                producer.flush(timeout=30)
            finally:
                producer.close(timeout=10)
            manifest = {"topic": TOPIC, "partition": metadata.partition, "offset": metadata.offset,
                        "key": "DEMO-0001", "event": event, "group_id": "doan-infra-smoke-" + event_id}
            MANIFEST.parent.mkdir(parents=True, exist_ok=True)
            MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            print("[1] Đã gửi sự kiện; broker xác nhận acks=all.")
        consumer, tp = read_exact(manifest)
        print(f"[2] Đọc đúng key/nội dung: {tp.topic}, partition={tp.partition}, offset={manifest['offset']}.")
        expected_offset = manifest["offset"] + 1
        if not args.read_only:
            # Commit offset kế tiếp sau khi xác nhận nội dung đã xử lý thành công.
            consumer.commit({tp: OffsetAndMetadata(expected_offset, "")})
        if consumer.committed(tp) != expected_offset:
            raise RuntimeError("Consumer group chưa lưu đúng committed offset.")
        print("[3] Committed offset của consumer group đúng:", expected_offset)
        print("THÀNH CÔNG. Consumer group:", manifest["group_id"])
        print("Manifest:", MANIFEST)
        return 0
    except Exception as exc:
        print("THẤT BẠI:", type(exc).__name__, str(exc))
        return 1
    finally:
        if consumer is not None:
            consumer.close()


if __name__ == "__main__":
    raise SystemExit(main())
