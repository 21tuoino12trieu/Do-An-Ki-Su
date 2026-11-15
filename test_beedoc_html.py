"""Chạy: python test_beedoc_html.py [--converter-only].

Mặc định kiểm thử BeedocEngine qua workflow Beeflow thật (cần MongoDB,
Redis và Langfuse đã cấu hình). Chỉ xử lý dữ liệu giả; workflow có thể gửi
nội dung mẫu lên Langfuse. Không gọi embedding, LLM hoặc OCR.
--converter-only kiểm thử bộ chuyển đổi trực tiếp, không cần các dịch vụ.
"""

import argparse
import asyncio
import hashlib
from html.parser import HTMLParser
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "tests/fixtures/beedoc_bank_sample.html"
OUTPUT = ROOT / "tests/output/beedoc_bank_sample.md"
sys.path.insert(0, str(ROOT / "replica/beedoc/src"))
# Beeflow import sẵn DocumentIONode dùng namespace beedoc cũ.
# Đặt package gốc trước để tránh alias beedoc của replica che package này;
# beedoc_v3 vẫn được lấy từ replica vì package gốc không chứa namespace đó.
sys.path.insert(0, str(ROOT / "beeflow/beeflow"))


class ImageTags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.tags.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def validate(markdown, html):
    images = ImageTags()
    images.feed(html)
    checks = {
        "Tiêu đề nhiều cấp": all(s in markdown for s in (
            "# Quy trình tiếp nhận", "## 1. Mục đích", "### 2.1. Danh sách", "#### 2.1.1.")),
        "Tiếng Việt và định dạng": all(s in markdown for s in (
            "Nguyễn Văn Mẫu", "**1.250.000 VNĐ**", "`KB-DEMO-001`", "*Lưu ý:*")),
        "Danh sách lồng nhau": any(line.startswith("  ") and "Kiểm tra mã" in line for line in markdown.splitlines()),
        "Liên kết tương đối và tuyệt đối": all(s in markdown for s in (
            "](/wiki/spaces/DEMO/pages/12345)", "](https://example.invalid/policy?", "](mailto:demo@example.invalid)")),
        "Bảng và ký tự đặc biệt": all(s in markdown for s in (
            "| Trường | Ví dụ | Ghi chú |", r"Chờ \| Đang xử lý", "Thanh toán mẫu<br>Đợt 1", "Cổng nội bộ giả lập")),
        "Giữ nguyên cả hai thẻ ảnh": len(images.tags) == 2 and all(markdown.count(tag) == 1 for tag in images.tags),
        "Khối mã và trích dẫn": '"request_id": "DEMO-0001"' in markdown and "> Nếu thiếu thông tin" in markdown,
        "Loại comment/script/style": all(s not in markdown for s in (
            "COMMENT_SHOULD_NOT_APPEAR", "SCRIPT_SHOULD_NOT_APPEAR", "max-width: 960px")),
        "Không còn token ảnh nội bộ": "BEEDOCIMAGETOKEN" not in markdown,
        "Thứ tự và nội dung cuối tài liệu": markdown.index("## 1.") < markdown.index("## 4.") and "Kết thúc tài liệu kiểm thử." in markdown,
    }
    for label, passed in checks.items():
        print(f"  {'OK' if passed else 'LỖI'}: {label}")
    if not all(checks.values()):
        raise RuntimeError("Một số tiêu chí chuyển đổi chưa đạt; xem Markdown đầu ra.")


async def run(converter_only):
    hub = None
    langfuse = None
    logging.disable(logging.CRITICAL)
    try:
        html = SOURCE.read_text(encoding="utf-8")
        if converter_only:
            from beedoc_v3.renders.document_render.html_render.utils.converter import convert_html
            markdown = convert_html(html)
            print("[1] Chế độ converter trực tiếp; chưa kiểm thử workflow.")
        else:
            from beegen.registry.resource_hub import RESOURCE_HUB
            hub = RESOURCE_HUB
            if not hub.redis("aicenter-chatbot").client.ping():
                raise RuntimeError("Redis không phản hồi PING.")
            langfuse = hub.langfuse("beegen")
            from beedoc_v3 import BeedocEngine
            from beedoc_v3.core.constants import DocumentStatus
            print("[1] Chạy BeedocEngine: HTML reader → HTML renderer → Markdown.", flush=True)
            document = await BeedocEngine().process(str(SOURCE))
            if document.status != DocumentStatus.COMPLETED:
                raise RuntimeError("BeedocEngine xử lý thất bại; kiểm tra workflow trong Langfuse.")
            if document.file_hash != hashlib.md5(SOURCE.read_bytes()).hexdigest():
                raise RuntimeError("Hash tài liệu không khớp file nguồn.")
            if document.file_size_bytes != SOURCE.stat().st_size or not document.document_id:
                raise RuntimeError("Metadata tài liệu chưa đầy đủ.")
            markdown = document.reconstructed_content
            print("    Trạng thái COMPLETED; hash, kích thước và document_id hợp lệ.")
        if not isinstance(markdown, str) or not markdown.strip():
            raise RuntimeError("Markdown đầu ra rỗng hoặc sai kiểu dữ liệu.")
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(markdown, encoding="utf-8")
        print("[2] Kiểm tra nội dung:")
        validate(markdown, html)
        print("THÀNH CÔNG. Markdown:", OUTPUT)
        print("Chưa đánh giá mọi dạng HTML; mẫu không chứa bảng gộp ô hoặc bảng lồng.")
        return 0
    except Exception as exc:
        print("THẤT BẠI:", type(exc).__name__)
        if isinstance(exc, RuntimeError):
            print(str(exc))
        print("Nếu chạy workflow: kiểm tra MongoDB, Redis và resource langfuse:beegen.")
        return 1
    finally:
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--converter-only", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.converter_only)))
