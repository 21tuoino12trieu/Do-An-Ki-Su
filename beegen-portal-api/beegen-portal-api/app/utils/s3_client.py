"""S3 client cho luong document-ingestion — noi luu HTML da extract.

Dung S3Engine qua ResourceHub thay vi tu dung boto3: credential nam trong
registry (Mongo, collection beegen_resource_configs) da ma hoa bang
BEEGEN_RESOURCE_HUB_SECRET, nen khong co secret nao trong repo hay trong
configmap. Cung la cach app/utils/milvus_schema.py lay config Milvus va
app/job/portal/upload_document_job.py lay S3Node.

Config s3:ai-nlp-text co bucket = None (chi giu credential + endpoint), nen
bucket phai truyen tuong minh o moi lenh — giong S3Node trong
upload_document_job.py da lam voi "ai-text-raw".

CONTENT-TYPE — quan trong, dung doi ve "text/html" neu chua doc doan nay:
Endpoint S3 noi bo (Dell EMC ViPR/ECS tai devobs01.mbbank.com.vn -> 10.1.39.64)
nam sau mot thiet bi F5 trong suot. F5 chen khoi <script id="f5_cspm"> vao MOI
response co Content-Type: text/html — do la tinh nang do hieu nang trinh duyet
cua F5, khong phan biet duoc "HTML la trang web" voi "HTML la noi dung file".

Da do thuc te (test/test_s3_content_type_probe.py, cung 1 payload 366 byte,
cung bucket, chi doi moi header):

    text/html; charset=utf-8   .html  -> 1925 byte  (F5 chen script)
    text/html; charset=utf-8   .bin   -> 1925 byte  (F5 chen script)
    text/plain; charset=utf-8  .html  ->  366 byte  (nguyen ven)
    application/octet-stream   .html  ->  366 byte  (nguyen ven)
    application/octet-stream   .bin   ->  366 byte  (nguyen ven)

Tuc la F5 quyet dinh theo Content-Type, KHONG theo duoi file — nen giu duoi
.html cho de nhan biet la duoc, chi can header khong phai text/html.

Vi vay HTML duoc luu duoi HTML_CONTENT_TYPE = "application/octet-stream": noi
dung nay la du lieu ung dung doc len de xu ly, khong phai trang web de trinh
duyet render, nen octet-stream mo ta dung ban chat hon — tranh duoc F5 la he
qua. Khi nao ha tang tat injection cho 10.1.39.64 thi doi lai hang so nay.
"""

import asyncio
import os
from typing import Any

from beegen.configs.storage.s3_config import S3Operation
from beegen.registry.resource_hub import ResourceHub

# Doi duoc bang env khi can tro toi resource key / bucket khac, khong phai sua code.
S3_RESOURCE_KEY = os.environ.get("S3_RESOURCE_KEY", "ai-nlp-text")
S3_BUCKET = os.environ.get("S3_BUCKET", "ai-text-raw")

# Prefix rieng cho HTML da extract. Khong dung "HTML/" vi prefix do da bi file
# GOC (pdf/docx) chiem — xem S3Service.uploadDocumentIngestionFile ben
# beegen-portal-be, no ghi file goc vao HTML/{stem}_{documentId}.{ext}.
HTML_PREFIX = "HTML_EXTRACTED"

# Xem doan CONTENT-TYPE o docstring dau file truoc khi doi gia tri nay.
HTML_CONTENT_TYPE = "application/octet-stream"


def html_object_key(document_id: str) -> str:
    return f"{HTML_PREFIX}/{document_id}.html"


def _engine():
    return ResourceHub.self().s3(S3_RESOURCE_KEY)


def _check(result: dict[str, Any], action: str, key: str) -> dict[str, Any]:
    """S3Engine.run bat het exception va tra ve {'status': 'error', 'message':
    <traceback>} thay vi raise, nen moi lenh phai kiem tra status — neu khong
    loi se troi qua im lang."""
    if result.get("status") != "success":
        raise RuntimeError(f"S3 {action} that bai cho key={key}: {result.get('message', '')}")
    return result


async def upload_html(document_id: str, html_content: str) -> str:
    """Ghi HTML da extract len S3, tra ve s3:// URI cua object."""
    key = html_object_key(document_id)
    result = await _engine().run(
        operation=S3Operation.WRITE,
        params={
            "bucket": S3_BUCKET,
            "key": key,
            "content": html_content.encode("utf-8"),
            "content_type": HTML_CONTENT_TYPE,
        },
    )
    _check(result, "WRITE", key)
    return result["document_path"]


def parse_s3_key(value: str) -> str:
    """Normalize an S3 reference to a bare key. Tolerates callers that send a
    full ``s3://bucket/key`` URI instead of the bare key — bucket is already
    known here (S3_BUCKET), only the key part matters."""
    value = (value or "").strip()
    if value.startswith("s3://"):
        # s3://bucket/some/key -> some/key
        value = value[len("s3://") :]
        value = value.split("/", 1)[1] if "/" in value else value
    return value


async def download_to_file(key: str, dest_path: str) -> None:
    """Download an object from the ingestion bucket to a local file path.

    Used by the extract pipeline so the source file is only fetched AFTER the
    extraction semaphore is acquired — queued documents cost no RAM/disk while
    waiting for their turn."""
    key = parse_s3_key(key)
    result = await _engine().run(
        operation=S3Operation.READ,
        params={"bucket": S3_BUCKET, "key": key},
    )
    _check(result, "READ", key)
    content = result["document_bytes"]
    with open(dest_path, "wb") as f:
        f.write(content if isinstance(content, bytes) else content.encode("utf-8"))


async def download_html(document_id: str) -> str:
    """Doc lai HTML da extract tu S3."""
    key = html_object_key(document_id)
    result = await _engine().run(
        operation=S3Operation.READ,
        params={"bucket": S3_BUCKET, "key": key},
    )
    _check(result, "READ", key)
    content = result["document_bytes"]
    return content.decode("utf-8") if isinstance(content, bytes) else content


async def delete_html(document_id: str) -> None:
    """Xoa object HTML. Khong raise neu object khong ton tai — caller goi ham
    nay khi don dep, va object thieu nghia la da don roi."""
    key = html_object_key(document_id)
    result = await _engine().run(
        operation=S3Operation.DELETE,
        params={"bucket": S3_BUCKET, "key": key},
    )
    message = result.get("message", "")
    if result.get("status") != "success" and "NoSuchKey" not in message:
        raise RuntimeError(f"S3 DELETE that bai cho key={key}: {message}")
