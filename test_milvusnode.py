"""python test_milvusnode.py — QUERY và SEARCH qua graph Beeflow thật.

Chỉ đọc collection demo, cần Redis/MongoDB/Milvus và Langfuse đã cấu hình.
Workflow gửi dữ liệu giả lên Langfuse, không gọi LLM/embedding.
"""
import asyncio
import logging
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parent


async def run():
    sys.path.insert(0, str(ROOT / "beeflow/beeflow"))
    logging.disable(logging.CRITICAL)
    hub = engine = langfuse = None
    try:
        from beegen.registry.resource_hub import RESOURCE_HUB
        hub = RESOURCE_HUB
        if not hub.redis("aicenter-chatbot").client.ping():
            raise RuntimeError("Redis chưa sẵn sàng.")
        engine = hub.milvus("knowledge")
        langfuse = hub.langfuse("beegen")
        from beeflow.workflow import WorkflowEngine
        from beeflow.nodes import MilvusNode, START, END, INPUT, OUTPUT
        from beegen.configs import MilvusOperation
        cases = [
            (MilvusOperation.QUERY, {"collection_name": "doan_infra_smoke_v1",
                                    "expr": "id in [1, 2, 3]", "output_fields": ["id", "text"]}),
            (MilvusOperation.SEARCH, {"collection_name": "doan_infra_smoke_v1",
                                     "query_vectors": [[1., 0., 0., 0.]], "top_k": 3,
                                     "output_fields": ["text"], "metric_type": "COSINE"}),
        ]
        for operation, payload in cases:
            name = "milvusnode-" + operation.value + "-test"
            with WorkflowEngine(name=name, inputs=INPUT, langfuse="beegen") as workflow:
                node = MilvusNode(name="milvus_" + operation.value, resource_key="knowledge",
                                  operation=operation, inputs={key: INPUT for key in payload}, outputs=OUTPUT)
                START >> node >> END
            workflow.compile()
            request_id = str(uuid.uuid4())
            result = await workflow.run(inputs=payload, request_id=request_id,
                                        user_id="local-milvusnode-test", session_id="milvusnode-setup")
            if result.get("status") != "success":
                raise RuntimeError(f"{operation.value}: node không trả success.")
            rows = result.get("results", [])
            if operation == MilvusOperation.QUERY:
                if {row["id"] for row in rows} != {1, 2, 3} or result.get("result_count") != 3:
                    raise RuntimeError("QUERY chưa đọc đủ 3 bản ghi.")
            else:
                if not rows or len(rows[0]) != 3 or rows[0][0]["id"] != 1 or rows[0][0]["distance"] < .99:
                    raise RuntimeError("SEARCH không trả đúng top-1 hoặc số lượng kết quả.")
            print(f"OK: {name}; request_id={request_id}", flush=True)
        print("THÀNH CÔNG: QUERY đủ 3 bản ghi; SEARCH top-1 id=1, cosine ≈ 1.")
        print("Workflow đã gọi flush trace. Chưa kiểm tra operation ghi hoặc phục hồi lỗi.")
        return 0
    except Exception as exc:
        print("THẤT BẠI:", type(exc).__name__)
        if isinstance(exc, RuntimeError):
            print(str(exc))
        return 1
    finally:
        if engine is not None:
            from pymilvus import connections
            connections.disconnect(engine._alias)
        if langfuse is not None:
            langfuse.shutdown()
        if hub is not None:
            redis = hub._instances.get("redis:aicenter-chatbot")
            if redis is not None:
                redis.client.close()
                redis.client.connection_pool.disconnect()
            hub.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(asyncio.run(run()))
