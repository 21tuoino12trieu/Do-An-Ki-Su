"""Kiểm tra hạ tầng: python test_milvus.py [--read-only].

Vector 4 chiều nhân tạo chỉ kiểm tra lưu trữ/tìm kiếm, không đánh giá RAG.
Giữ collection demo để xem trên Attu; không đụng collection nghiệp vụ.
"""
import argparse
import sys
from pymilvus import MilvusClient, DataType

COLLECTION = "doan_infra_smoke_v1"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-only", action="store_true")
    args = parser.parse_args()
    client = MilvusClient(uri="http://127.0.0.1:19530", timeout=30)
    try:
        print("[1] Kết nối Milvus OK. Collection:", COLLECTION)
        if not args.read_only:
            if not client.has_collection(COLLECTION):
                schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
                schema.add_field("id", DataType.INT64, is_primary=True)
                schema.add_field("text", DataType.VARCHAR, max_length=512)
                schema.add_field("vector", DataType.FLOAT_VECTOR, dim=4)
                indexes = client.prepare_index_params()
                indexes.add_index(field_name="vector", index_type="FLAT", metric_type="COSINE")
                client.create_collection(COLLECTION, schema=schema, index_params=indexes, consistency_level="Strong")
            client.upsert(COLLECTION, data=[
                {"id": 1, "text": "Quy trình chuyển khoản giả lập", "vector": [1., 0., 0., 0.]},
                {"id": 2, "text": "Chính sách nghỉ phép giả lập", "vector": [0., 1., 0., 0.]},
                {"id": 3, "text": "Hướng dẫn tài khoản giả lập", "vector": [0., 0., 1., 0.]},
            ])
            client.flush(COLLECTION)
            print("[2] Đã upsert và flush 3 bản ghi giả lập.")
        client.load_collection(COLLECTION)
        rows = client.query(COLLECTION, filter="id in [1, 2, 3]", output_fields=["id", "text"], consistency_level="Strong")
        if {r["id"] for r in rows} != {1, 2, 3}:
            raise RuntimeError("Thiếu dữ liệu kiểm thử.")
        results = client.search(COLLECTION, data=[[1., 0., 0., 0.]], anns_field="vector", limit=3,
                                output_fields=["text"], search_params={"metric_type": "COSINE"}, consistency_level="Strong")
        if results[0][0]["id"] != 1 or results[0][0]["distance"] < .99:
            raise RuntimeError("Kết quả tìm kiếm không đúng vector mong đợi.")
        print("[3] Query đủ 3 bản ghi; top-1 = id 1, cosine ≈ 1.0.")
        print("THÀNH CÔNG. Mở http://localhost:8000 để xem collection demo.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
