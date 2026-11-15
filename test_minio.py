"""python test_minio.py [--read-only].

Tạo bucket private, bật versioning và kiểm tra HTML/Markdown giả lập.
Giữ object để xem trong Console. Mỗi lần chạy ghi tạo một prefix mới.
--read-only chỉ đọc các version trong manifest của lần chạy gần nhất.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "tests/output/minio_smoke_manifest.json"


def credentials():
    path = ROOT / "infra/minio/.env"
    if not path.is_file():
        raise RuntimeError("Thiếu infra/minio/.env; xem hướng dẫn setup.")
    return dict(line.strip().split("=", 1) for line in path.read_text(encoding="utf-8-sig").splitlines()
                if line.strip() and not line.lstrip().startswith("#"))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-only", action="store_true")
    args = parser.parse_args()
    env = credentials()
    client = boto3.client("s3", endpoint_url="http://127.0.0.1:9000", region_name="us-east-1",
                          aws_access_key_id=env["MINIO_ROOT_USER"], aws_secret_access_key=env["MINIO_ROOT_PASSWORD"],
                          config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                                        connect_timeout=5, read_timeout=15, retries={"max_attempts": 2}))
    try:
        if args.read_only:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        else:
            for bucket in ("knowledge-raw", "knowledge-processed"):
                try:
                    client.head_bucket(Bucket=bucket)
                except ClientError as exc:
                    if exc.response["Error"]["Code"] not in ("404", "NoSuchBucket", "NotFound"):
                        raise
                    client.create_bucket(Bucket=bucket)
                # Không thay policy hoặc xóa dữ liệu của bucket đã tồn tại.
                client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
            sys.path.insert(0, str(ROOT / "replica/beedoc/src"))
            from beedoc_v3.renders.document_render.html_render.utils.converter import convert_html
            raw = (ROOT / "tests/fixtures/beedoc_bank_sample.html").read_bytes()
            markdown = convert_html(raw.decode("utf-8")).encode("utf-8")
            prefix = "smoke/" + uuid.uuid4().hex
            objects = []
            samples = [
                ("knowledge-raw", prefix + "/source.html", raw, "text/html; charset=utf-8"),
                ("knowledge-raw", prefix + "/source.html", raw + b"\n<!-- storage version test -->", "text/html; charset=utf-8"),
                ("knowledge-processed", prefix + "/document.md", markdown, "text/markdown; charset=utf-8"),
            ]
            for bucket, key, body, content_type in samples:
                digest = hashlib.sha256(body).hexdigest()
                result = client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type,
                                           Metadata={"sha256": digest, "source": "synthetic-smoke-test"})
                version = result.get("VersionId")
                if not version or version == "null":
                    raise RuntimeError("Object chưa có version ID hợp lệ.")
                objects.append({"bucket": bucket, "key": key, "version_id": version,
                                "sha256": digest, "content_type": content_type})
            manifest = {"prefix": prefix, "objects": objects}
            MANIFEST.parent.mkdir(parents=True, exist_ok=True)
            MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            print("[1] Đã lưu hai version HTML và một Markdown; prefix:", prefix)
        for item in manifest["objects"]:
            result = client.get_object(Bucket=item["bucket"], Key=item["key"], VersionId=item["version_id"])
            try:
                body = result["Body"].read()
            finally:
                result["Body"].close()
            if hashlib.sha256(body).hexdigest() != item["sha256"]:
                raise RuntimeError("Nội dung đọc lại không khớp SHA-256.")
            if result.get("ContentType") != item["content_type"] or result.get("Metadata", {}).get("sha256") != item["sha256"]:
                raise RuntimeError("Content type hoặc metadata sai.")
        raw_item = manifest["objects"][0]
        versions = client.list_object_versions(Bucket=raw_item["bucket"], Prefix=raw_item["key"]).get("Versions", [])
        ids = {v["VersionId"] for v in versions if v["Key"] == raw_item["key"]}
        if not all(item["version_id"] in ids for item in manifest["objects"][:2]):
            raise RuntimeError("Không tìm đủ hai phiên bản HTML.")
        for bucket in ("knowledge-raw", "knowledge-processed"):
            if client.get_bucket_versioning(Bucket=bucket).get("Status") != "Enabled":
                raise RuntimeError("Bucket chưa bật versioning.")
        print("[2] Đọc đúng từng version; SHA-256, content type và metadata khớp.")
        print("THÀNH CÔNG. Console: http://localhost:9001")
        print("Manifest:", MANIFEST)
        print("Version MinIO là version lưu trữ, khác số phiên bản trang Confluence.")
        return 0
    except Exception as exc:
        print("THẤT BẠI:", type(exc).__name__)
        if isinstance(exc, RuntimeError):
            print(str(exc))
        if isinstance(exc, ClientError):
            print("S3 error code:", exc.response["Error"]["Code"])
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
