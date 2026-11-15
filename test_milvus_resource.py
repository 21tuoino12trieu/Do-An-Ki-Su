"""Kiểm tra resource: python test_milvus_resource.py.

Đăng ký lần đầu: python test_milvus_resource.py --register
Không ghi đè resource hiện có nếu khác cấu hình mong đợi.
"""
import argparse
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
KEY = "milvus:knowledge"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "beeflow/beeflow"))
    logging.disable(logging.CRITICAL)
    from beegen.registry.resource_hub import RESOURCE_HUB as hub
    from beegen.configs.storage.vectordb.milvus_config import MilvusConfig
    from pymilvus import utility, Collection, connections

    engine = None
    try:
        if hub._mongo_collection is None:
            raise RuntimeError("ResourceHub chưa kết nối MongoDB.")
        if hub._mongo_collection.full_name != "cuong.beegen_resource_configs":
            raise RuntimeError("Database/collection cấu hình không đúng dự kiến.")
        config = MilvusConfig(
            alias="knowledge", uri="http://127.0.0.1:19530",
            username="", password="", db_name="default", timeout=30,
            index_params={"index_type": "FLAT", "metric_type": "COSINE", "params": {}},
            search_params={"metric_type": "COSINE", "params": {}},
        )
        existing = hub._mongo_collection.find_one({"_id": KEY}, {"_id": 1, "config_class": 1})
        if existing is None:
            if not args.register:
                raise RuntimeError("Chưa có resource; chạy thêm --register để tạo.")
            hub.register(config, registry_key=KEY)
            print("[1] Đã đăng ký", KEY, "vào cuong.beegen_resource_configs.")
        else:
            print("[1] Resource đã có; không ghi đè.")
        engine = hub.milvus("knowledge")
        if engine.config.model_dump() != config.model_dump():
            raise RuntimeError("Resource hiện có khác cấu hình local dự kiến; chưa sửa cấu hình cũ.")
        stored = hub._mongo_collection.find_one({"_id": KEY}, {"_id": 1, "config_class": 1})
        if stored != {"_id": KEY, "config_class": "MilvusConfig"}:
            raise RuntimeError("Chưa xác nhận được document cấu hình đã lưu.")
        print("[2] ResourceHub tải đúng MilvusConfig; URI local, database default.")
        name = "doan_infra_smoke_v1"
        if not utility.has_collection(name, using=engine._alias):
            raise RuntimeError("Thiếu collection demo; chạy test_milvus.py trước.")
        collection = Collection(name, using=engine._alias)
        rows = collection.query(expr="id in [1, 2, 3]", output_fields=["id", "text"], consistency_level="Strong")
        if {row["id"] for row in rows} != {1, 2, 3}:
            raise RuntimeError("Không đọc đủ ba bản ghi demo.")
        print("[3] Đọc đủ 3 bản ghi demo qua kết nối do ResourceHub tạo.")
        print("THÀNH CÔNG. MilvusNode dùng resource_key='knowledge'.")
        print("Chưa thực thi graph MilvusNode; không thay đổi dữ liệu vector.")
        return 0
    except Exception as exc:
        print("THẤT BẠI:", type(exc).__name__)
        if isinstance(exc, RuntimeError):
            print(str(exc))
        return 1
    finally:
        if engine is not None:
            connections.disconnect(engine._alias)
        hub.close()


if __name__ == "__main__":
    raise SystemExit(main())
