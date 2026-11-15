"""Kiểm tra ResourceHub của repo gốc; không đăng ký hoặc sửa tài nguyên.

Chạy bằng Python trong môi trường namcuong:
    python test_resourcehub.py
"""

import argparse
import logging
from pathlib import Path
import re
import sys
import traceback


WORKSPACE = Path(__file__).resolve().parent
SOURCE = WORKSPACE / "beeflow" / "beeflow"
EXPECTED_CONFIG = WORKSPACE / "config" / "beeflow.yaml"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    stage = "kiểm tra thư mục mã nguồn"
    hub = None
    secrets = []
    try:
        print("Python:", sys.executable, flush=True)
        if not (SOURCE / "beegen" / "registry" / "resource_hub.py").is_file():
            raise FileNotFoundError("Không tìm thấy mã nguồn Beegen trong repo gốc.")
        sys.path.insert(0, str(SOURCE))

        stage = "kiểm tra đường dẫn và nội dung cấu hình"
        from beegen.const import BEEGEN_ROOT
        import yaml

        config_path = (BEEGEN_ROOT / "config" / "beeflow.yaml").resolve()
        print("[1] File ResourceHub sẽ đọc:", config_path, flush=True)
        if config_path != EXPECTED_CONFIG.resolve():
            raise ValueError("BEEGEN_ROOT chưa trỏ đến file config của workspace.")
        data = yaml.safe_load(config_path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("Cấu hình phải là một mapping YAML.")
        uri = data.get("uri")
        if not isinstance(uri, str) or not uri.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("Thiếu URI MongoDB hợp lệ.")
        secrets.append(uri)
        database = data.get("authen_source")
        if database != "cuong":
            raise ValueError("authen_source phải là cuong theo cấu hình đã thống nhất.")
        print("    YAML hợp lệ; database dự kiến: cuong; URI được ẩn.", flush=True)

        stage = "nạp MongoConfig.default() của Beegen"
        from beegen.configs.storage.mongo_config import MongoConfig

        config = MongoConfig.default()
        if config.uri != uri or config.authen_source != database:
            raise ValueError("MongoConfig.default() không khớp file YAML đã kiểm tra.")
        print("[2] MongoConfig.default() đọc đúng cấu hình.", flush=True)

        stage = "import và khởi tạo ResourceHub"
        print("[3] Đang khởi tạo ResourceHub thật...", flush=True)
        # Hạn chế log từ thư viện trong tiến trình kiểm tra này.
        logging.disable(logging.CRITICAL)
        from beegen.registry.resource_hub import RESOURCE_HUB

        hub = RESOURCE_HUB
        if hub._mongo_client is None or hub._mongo_collection is None:
            raise RuntimeError("ResourceHub chưa tạo được kết nối MongoDB.")
        expected_collection = f"{database}.beegen_resource_configs"
        if hub._mongo_collection.full_name != expected_collection:
            raise RuntimeError("ResourceHub đang chọn sai database hoặc collection.")

        stage = "ping MongoDB bằng client của ResourceHub"
        result = hub._mongo_client.admin.command("ping")
        if result.get("ok") != 1:
            raise RuntimeError("MongoDB không trả kết quả ping thành công.")
        print("[4] PING bằng ResourceHub: OK", flush=True)

        stage = "đọc collection cấu hình"
        # Chỉ đọc _id để kiểm tra quyền; không in key hoặc nội dung cấu hình.
        document = hub._mongo_collection.find_one({}, {"_id": 1})
        print("[5] Đọc collection:", hub._mongo_collection.full_name, "OK", flush=True)
        print("    Có ít nhất một cấu hình:", document is not None, flush=True)
        print("THÀNH CÔNG: ResourceHub đọc đúng YAML và truy cập được collection.")
        print("Chưa kiểm tra đăng ký hoặc tải một resource key cụ thể.")
        return 0
    except Exception as exc:
        print(f"THẤT BẠI ở bước: {stage}", flush=True)
        print("Loại lỗi:", type(exc).__name__)
        # Không in dòng mã nguồn trong traceback vì có thể chứa thông tin kết nối.
        for frame in traceback.extract_tb(exc.__traceback__):
            print(f"  {frame.filename}:{frame.lineno} ({frame.name})")
        message = str(exc)
        for secret in secrets:
            message = message.replace(secret, "<URI đã ẩn>")
        message = re.sub(r"mongodb(?:\+srv)?://[^\s\"'<>]+", "<URI đã ẩn>", message)
        print("Chi tiết:", message)
        return 1
    finally:
        if hub is not None:
            hub.close()


if __name__ == "__main__":
    raise SystemExit(main())
