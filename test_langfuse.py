"""Xác thực và gửi trace thử qua adapter mới, không gọi LLM.

python test_langfuse.py
python test_langfuse.py --register

--register đăng ký langfuse:beegen vào MongoDB nếu chưa có; không ghi đè.
"""

import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
import time
import uuid


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root / "beeflow" / "beeflow"))
    logging.disable(logging.CRITICAL)
    client = None
    hub = None
    stage = "đọc cấu hình"
    try:
        from importlib.metadata import version
        from beegen.configs.monitor.langfuse_config import LangfuseConfig
        from beegen.observations.bee_langfuse import BeeLangfuse

        config = LangfuseConfig.default()
        if config.host != "https://us.cloud.langfuse.com":
            raise ValueError("Địa chỉ Langfuse không khớp project US đã cấu hình.")
        print("SDK:", version("langfuse"), flush=True)
        print("Host:", config.host, flush=True)
        client = BeeLangfuse(
            host=config.host, public_key=config.public_key,
            secret_key=config.secret_key, timeout=15,
        )
        stage = "xác thực Langfuse"
        if not client.auth_check():
            raise RuntimeError("Langfuse từ chối xác thực.")
        print("AUTH: OK", flush=True)

        if args.register:
            stage = "đăng ký ResourceHub"
            from beegen.registry.resource_hub import RESOURCE_HUB

            hub = RESOURCE_HUB
            collection = hub._mongo_collection
            if collection is None:
                raise RuntimeError("ResourceHub chưa kết nối MongoDB.")
            key = "langfuse:beegen"
            existing = collection.find_one({"_id": key})
            if existing is not None:
                if existing.get("config_class") != "LangfuseConfig":
                    raise RuntimeError("Resource đã tồn tại với kiểu khác; không ghi đè.")
                if "enc" in existing:
                    if hub._crypto is None:
                        raise RuntimeError("Không giải mã được resource hiện có.")
                    saved = hub._crypto.decrypt(existing["enc"])
                else:
                    saved = existing.get("config_data", {})
                if LangfuseConfig.model_validate(saved).model_dump() != config.model_dump():
                    raise RuntimeError("Resource hiện có khác YAML; không ghi đè.")
                print("RESOURCE: đã tồn tại và khớp YAML.", flush=True)
            else:
                hub.register(config, registry_key=key)
                print("RESOURCE: đã gọi đăng ký langfuse:beegen.", flush=True)
            saved = collection.find_one({"_id": key}, {"config_class": 1})
            if not saved or saved.get("config_class") != "LangfuseConfig":
                raise RuntimeError("Chưa xác nhận được cấu hình lưu trong MongoDB.")
            print("PERSISTED: cuong.beegen_resource_configs / langfuse:beegen", flush=True)

        stage = "gửi trace kiểm tra"
        request_id = str(uuid.uuid4())
        start = datetime.now(timezone.utc)
        observation = client.trace(
            id=request_id, name="beeflow-langfuse-connection-test",
            user_id="local-setup-test", session_id="langfuse-setup",
            start_time=start, end_time=datetime.now(timezone.utc),
            input={"test": True}, output={"status": "ok"},
        )
        observation.span(
            name="connection-check", start_time=start,
            end_time=datetime.now(timezone.utc), output={"ok": True},
        )
        client.flush()
        trace_id = client.create_trace_id(seed=request_id)
        print("TRACE ID:", trace_id, flush=True)
        stage = "đọc lại observation từ Cloud"
        for _ in range(12):
            response = client.api.observations.get_many(
                trace_id=trace_id, limit=10, fields="core",
            )
            if len(response.data) >= 2:
                print("CLOUD READBACK: nhận được root và child observation.", flush=True)
                print("Trace URL:", client.get_trace_url(trace_id=trace_id), flush=True)
                return 0
            time.sleep(2)
        print("Đã flush nhưng chưa thấy đủ observation trong thời gian chờ.")
        print("Mở Tracing trong Langfuse để kiểm tra trace ID ở trên.")
        return 1
    except Exception as exc:
        print("THẤT BẠI ở bước:", stage)
        print("Loại lỗi:", type(exc).__name__)
        # Không in exception hoặc config vì có thể chứa credential.
        return 1
    finally:
        if client is not None:
            client.shutdown()
        if hub is not None:
            hub.close()


if __name__ == "__main__":
    raise SystemExit(main())
