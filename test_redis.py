"""Kiểm tra RedisEngine từ config/redis.yaml; chỉ PING, không ghi dữ liệu."""

import logging
from pathlib import Path
import sys


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    workspace = Path(__file__).resolve().parent
    sys.path.insert(0, str(workspace / "beeflow" / "beeflow"))
    logging.disable(logging.CRITICAL)
    engine = None
    try:
        from beegen.const import BEEGEN_ROOT
        from beegen.configs.cache.redis_config import RedisConfig
        from beegen.cache.redis_engine import RedisEngine

        path = (BEEGEN_ROOT / "config" / "redis.yaml").resolve()
        if path != (workspace / "config" / "redis.yaml").resolve():
            raise RuntimeError("BEEGEN_ROOT chưa trỏ tới config/redis.yaml của workspace.")
        config = RedisConfig.default()
        print("Config:", path, flush=True)
        print(f"Redis: {config.host}:{config.port}, db={config.db}, ssl={config.ssl}", flush=True)
        engine = RedisEngine(config)
        if not engine.client.ping():
            raise RuntimeError("Redis không phản hồi PING thành công.")
        print("PONG — RedisEngine kết nối thành công.")
        print("Không ghi dữ liệu Redis hoặc đăng ký resource vào MongoDB.")
        return 0
    except Exception as exc:
        # Không in cấu hình hoặc exception chứa thông tin xác thực.
        print("THẤT BẠI:", type(exc).__name__)
        print("Kiểm tra container doan-redis đang chạy và cổng 6379 đã mở trên máy.")
        print("Nếu vẫn lỗi, cần kiểm tra riêng import/dependency và RedisConfig.")
        return 1
    finally:
        if engine is not None:
            engine.client.close()
            engine.client.connection_pool.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
