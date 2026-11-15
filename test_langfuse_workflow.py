"""Chạy graph thật với CodeNode và kiểm tra trace trên Langfuse Cloud.

python test_langfuse_workflow.py
Chỉ dùng dữ liệu giả lập, không gọi LLM hoặc đọc tài liệu nghiệp vụ.
"""

import asyncio
import logging
from pathlib import Path
import sys
import uuid


def add_one(value: int) -> dict:
    """Tăng giá trị kiểm tra lên một đơn vị."""
    return {"result": value + 1}


async def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).resolve().parent / "beeflow" / "beeflow"))
    logging.disable(logging.CRITICAL)
    from beeflow.workflow import WorkflowEngine
    from beeflow.nodes import CodeNode, START, END, INPUT, OUTPUT
    from beegen.registry.resource_hub import RESOURCE_HUB

    client = None
    try:
        with WorkflowEngine(name="langfuse-setup-workflow", langfuse="beegen", inputs=INPUT) as workflow:
            node = CodeNode(
                name="add_one", code_fn=add_one, inputs={"value": INPUT},
                return_keys=["result: int"], outputs=OUTPUT,
            )
            START >> node >> END
        workflow.compile()
        request_id = str(uuid.uuid4())
        result = await workflow.run(
            inputs={"value": 1}, request_id=request_id,
            user_id="local-setup-test", session_id="langfuse-setup",
        )
        print("WORKFLOW RESULT:", result, flush=True)
        if result.get("result") != 2:
            raise RuntimeError("Workflow không trả kết quả mong đợi.")
        client = RESOURCE_HUB.langfuse("beegen")
        trace_id = client.create_trace_id(seed=request_id)
        for _ in range(12):
            response = client.api.observations.get_many(trace_id=trace_id, limit=20, fields="core")
            if len(response.data) >= 2:
                print("WORKFLOW CLOUD OBSERVATIONS:", len(response.data), flush=True)
                print("Trace URL:", client.get_trace_url(trace_id=trace_id), flush=True)
                return 0
            await asyncio.sleep(2)
        print("Chưa thấy đủ observation trên Cloud trong thời gian chờ.")
        return 1
    except Exception as exc:
        print("FAILED:", type(exc).__name__)
        return 1
    finally:
        if client is not None:
            client.shutdown()
        RESOURCE_HUB.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
