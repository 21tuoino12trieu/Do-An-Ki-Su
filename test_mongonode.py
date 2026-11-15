"""Kiểm tra MongoNode qua graph Beeflow bằng resource mongo:knowledge.

Chạy: python test_mongonode.py

Chỉ đọc hai trường _id/config_class của document cấu hình đã có trong MongoDB.
Workflow dùng Redis và gửi trace kiểm tra lên Langfuse như cấu hình hiện tại.
Không in hoặc đưa URI/credential vào input/output của graph.
"""

import argparse
import asyncio
import inspect
import logging
from pathlib import Path
import sys
import uuid


WORKSPACE = Path(__file__).resolve().parent
RESOURCE = "knowledge"
RESOURCE_KEY = "mongo:knowledge"
COLLECTION = "beegen_resource_configs"


async def run_test() -> int:
    stage = "nạp Beeflow và các resource hỗ trợ"
    hub = None
    mongo = None
    langfuse = None
    try:
        sys.path.insert(0, str(WORKSPACE / "beeflow" / "beeflow"))
        logging.disable(logging.CRITICAL)
        from beegen.registry.resource_hub import RESOURCE_HUB

        hub = RESOURCE_HUB
        if hub._mongo_collection is None:
            raise RuntimeError("ResourceHub chưa kết nối được MongoDB.")
        for key in (RESOURCE_KEY, "redis:aicenter-chatbot", "langfuse:beegen"):
            if hub._mongo_collection.find_one({"_id": key}, {"_id": 1}) is None:
                raise RuntimeError(f"Thiếu cấu hình tài nguyên {key} trong MongoDB.")
        stage = "tải Redis local; kiểm tra container doan-redis đang chạy"
        redis = hub.redis("aicenter-chatbot")
        if not redis.client.ping():
            raise RuntimeError("Redis không phản hồi ping.")
        stage = "tải resource MongoDB và Langfuse"
        mongo = hub.mongo(RESOURCE)
        langfuse = hub.langfuse("beegen")
        stage = "import các lớp workflow và node"
        from beeflow.workflow import WorkflowEngine
        from beeflow.nodes import MongoNode, START, END, INPUT, OUTPUT
        from beegen.configs.storage.mongo_config import MongoOperation

        print("[1] Đã nạp Beeflow, ResourceHub và kiểm tra Redis.", flush=True)
        stage = "dựng graph MongoNode"
        with WorkflowEngine(name="mongonode-read-test", langfuse="beegen", inputs=INPUT) as workflow:
            node = MongoNode(
                name="read_resource",
                resource_key=RESOURCE,
                operation=MongoOperation.FIND_ONE,
                inputs={
                    "collection_name": INPUT,
                    "query": INPUT,
                    "projection": INPUT,
                },
                outputs=OUTPUT,
            )
            START >> node >> END
        workflow.compile()
        if mongo.db.name != "cuong":
            raise RuntimeError("Resource MongoDB đang trỏ tới database khác cuong.")
        print("[2] Graph: START → MongoNode(FIND_ONE) → END", flush=True)
        print("    Resource:", RESOURCE_KEY, flush=True)
        print("    Collection: cuong." + COLLECTION, flush=True)

        stage = "thực thi operation qua MongoNode"
        request_id = str(uuid.uuid4())
        result = await workflow.run(
            inputs={
                "collection_name": COLLECTION,
                "query": {"_id": RESOURCE_KEY},
                "projection": {"_id": 1, "config_class": 1},
            },
            request_id=request_id,
            user_id="local-mongonode-test",
            session_id="mongonode-setup",
        )
        if not isinstance(result, dict) or result.get("status") != "success":
            raise RuntimeError("Node không trả trạng thái success; cần kiểm tra operation/binding.")
        document = result.get("data")
        if document is None:
            raise RuntimeError("Không tìm thấy mongo:knowledge trong collection.")
        expected = {"_id": RESOURCE_KEY, "config_class": "MongoConfig"}
        if document != expected:
            raise RuntimeError("Dữ liệu trả về không khớp hai trường mong đợi.")
        print("[3] Operation FIND_ONE: success", flush=True)
        print("    _id:", document["_id"], flush=True)
        print("    config_class:", document["config_class"], flush=True)
        print("THÀNH CÔNG: MongoNode lấy đúng resource và đọc qua graph.", flush=True)
        print("Request ID:", request_id, flush=True)
        print("Workflow đã gọi flush trace; có thể xem mongonode-read-test trong Langfuse.")
        print("Chưa kiểm tra các operation ghi, transaction hoặc phục hồi lỗi.")
        return 0
    except Exception as exc:
        print("THẤT BẠI ở bước:", stage, flush=True)
        print("Loại lỗi:", type(exc).__name__)
        if isinstance(exc, RuntimeError):
            print("Chi tiết:", str(exc))
        print("Cần Redis local đang chạy, kết nối Atlas/Langfuse và đủ ba resource:")
        print("mongo:knowledge, redis:aicenter-chatbot, langfuse:beegen.")
        return 1
    finally:
        if mongo is not None:
            result = mongo.close()
            if inspect.isawaitable(result):
                await result
        if langfuse is not None:
            langfuse.shutdown()
        if hub is not None:
            redis = hub._instances.get("redis:aicenter-chatbot")
            if redis is not None:
                redis.client.close()
                redis.client.connection_pool.disconnect()
            hub.close()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argparse.ArgumentParser(description=__doc__).parse_args()
    print("Python:", sys.executable, flush=True)
    return asyncio.run(run_test())


if __name__ == "__main__":
    raise SystemExit(main())
