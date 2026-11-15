"""python test_infra_resources.py [--register].

Đăng ký lần đầu hoặc kiểm tra Kafka/S3 qua ResourceHub thật.
Không ghi đè config khác đã tồn tại, không in secret, không ghi dữ liệu nghiệp vụ.
"""
import argparse
import asyncio
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent


async def run(register):
    sys.path.insert(0, str(ROOT / "beeflow/beeflow"))
    logging.disable(logging.CRITICAL)
    from beegen.registry.resource_hub import RESOURCE_HUB as hub
    from beegen.configs.event_streaming.kafka_config import KafkaConfig
    from beegen.configs.storage.s3_config import S3Config
    producer = None
    try:
        if hub._mongo_collection is None or hub._mongo_collection.full_name != "cuong.beegen_resource_configs":
            raise RuntimeError("ResourceHub chưa kết nối đúng cuong.beegen_resource_configs.")
        env = dict(line.strip().split("=", 1) for line in (ROOT / "infra/minio/.env").read_text().splitlines()
                   if line.strip() and not line.lstrip().startswith("#"))
        configs = {
            "kafka:knowledge": KafkaConfig(bootstrap_servers=["127.0.0.1:9092"],
                client_id="doan-knowledge", group_id="doan-knowledge-ingestion",
                auto_offset_reset="earliest", enable_auto_commit=False, request_timeout_ms=15000),
        }
        for bucket in ("knowledge-raw", "knowledge-processed"):
            configs["s3:" + bucket] = S3Config(bucket=bucket, region="us-east-1",
                access_key=env["MINIO_ROOT_USER"], secret_key=env["MINIO_ROOT_PASSWORD"],
                endpoint_url="http://127.0.0.1:9000", addressing_style="path")
        # Kiểm tra xung đột trước khi thêm bất kỳ config nào.
        for key, config in configs.items():
            if hub._mongo_collection.find_one({"_id": key}, {"_id": 1}):
                if hub.get(key).config.model_dump() != config.model_dump():
                    raise RuntimeError("Cấu hình hiện có khác dự kiến: " + key + "; chưa ghi đè.")
            elif not register:
                raise RuntimeError("Thiếu " + key + "; chạy --register để tạo.")
        for key, config in configs.items():
            if hub._mongo_collection.find_one({"_id": key}, {"_id": 1}) is None:
                hub.register(config, registry_key=key)
                print("Đã đăng ký:", key, flush=True)
            stored = hub._mongo_collection.find_one({"_id": key}, {"_id": 1, "config_class": 1})
            if stored != {"_id": key, "config_class": type(config).__name__}:
                raise RuntimeError("Chưa xác nhận lưu cấu hình: " + key)
        for bucket in ("knowledge-raw", "knowledge-processed"):
            engine = hub.s3(bucket)
            async with await engine._get_client() as client:
                await client.head_bucket(Bucket=bucket)
                versioning = await client.get_bucket_versioning(Bucket=bucket)
                if versioning.get("Status") != "Enabled":
                    raise RuntimeError("Bucket chưa bật versioning: " + bucket)
            print("OK: s3:" + bucket + " — kết nối và versioning Enabled.", flush=True)
        kafka = hub.kafka("knowledge")
        producer = await asyncio.wait_for(kafka._get_producer(), timeout=30)
        partitions = await asyncio.wait_for(producer.partitions_for("doan.infra.smoke.v1"), timeout=30)
        if partitions != {0, 1, 2}:
            raise RuntimeError("Kafka chưa trả đủ ba partition của topic demo.")
        print("OK: kafka:knowledge — producer kết nối, metadata đủ 3 partition.")
        print("THÀNH CÔNG. Không gửi message hoặc thay consumer offset trong test này.")
        print("Các resource hiện có:")
        for row in hub._mongo_collection.find({}, {"_id": 1, "config_class": 1}).sort("_id", 1):
            print("  " + row["_id"] + " (" + row.get("config_class", "?") + ")")
        return 0
    except Exception as exc:
        print("THẤT BẠI:", type(exc).__name__)
        if isinstance(exc, RuntimeError):
            print(str(exc))
        return 1
    finally:
        if producer is not None:
            await producer.stop()
        hub.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.register)))
