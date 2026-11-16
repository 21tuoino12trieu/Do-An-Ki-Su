import asyncio
import base64
import os
import re
import tempfile
import uuid
import urllib.parse
import logging
import sys
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timezone
import boto3
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()


logger = logging.getLogger(__name__)

SYSTEM_USER = "system"
MONGO_COLLECTION = "multimedia"
MULTIMEDIA_CLASS = "vn.com.mbbank.aicenter.beegen.portal.entity.document.Multimedia"


def _get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def upsert_multimedia_document_to_mongo(
    uploaded_image: dict,
    bot_id: str,
    image_desc: str = "",
) -> None:
    now = datetime.now(timezone.utc)
    file_id = uploaded_image["file_id"]
    file_name = uploaded_image["file_name"]
    content_type = uploaded_image.get("content_type", "image/png")
    document_path = uploaded_image.get("document_path", "default_doc")
    s3_beegen_folder = _get_env("S3_BEEGEN_FOLDER", "chatbot_beegen_portal").strip("/")

    doc = {
        "_id": file_id,
        "user_id": SYSTEM_USER,
        "user_name": SYSTEM_USER,
        "file_name": file_name,
        "size": str(uploaded_image.get("size", "")),
        "content_type": content_type,
        "path": f"{s3_beegen_folder}/multimedia/{bot_id}/{document_path}/{file_name}",
        "bot_id": bot_id,
        "type": "MULTIMEDIA",
        "version": 1,
        "created_by": SYSTEM_USER,
        "created_at": now,
        "updated_by": SYSTEM_USER,
        "updated_at": now,
        "_class": MULTIMEDIA_CLASS,
        "description": image_desc,
    }

    update_data = dict(doc)
    update_data.pop("_id", None)
    update_data.pop("created_at", None)

    try:
        from app.utils.db_validation import get_mongo_db
        db = get_mongo_db()
        db[MONGO_COLLECTION].update_one(
            {"_id": file_id},
            {
                "$set": update_data,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        logger.info(f"Successfully upserted multimedia metadata for file_id='{file_id}' via get_mongo_db()")
    except Exception as exc:
        logger.error(f"Failed to upsert multimedia metadata to Mongo: {exc}")


async def upsert_multimedia_document_to_mongo_async(
    uploaded_image: dict,
    bot_id: str,
    image_desc: str = "",
    mongo_resource_key: str = "aicenter-chatbot",
) -> None:
    """Upsert multimedia document metadata to Mongo using Beeflow AsyncMongoEngine with legacy fallback."""
    now = datetime.now(timezone.utc)
    file_id = uploaded_image["file_id"]
    file_name = uploaded_image["file_name"]
    content_type = uploaded_image.get("content_type", "image/png")
    document_path = uploaded_image.get("document_path", "default_doc")
    s3_beegen_folder = _get_env("S3_BEEGEN_FOLDER", "chatbot_beegen_portal").strip("/")

    doc = {
        "_id": file_id,
        "user_id": SYSTEM_USER,
        "user_name": SYSTEM_USER,
        "file_name": file_name,
        "size": str(uploaded_image.get("size", "")),
        "content_type": content_type,
        "path": f"{s3_beegen_folder}/multimedia/{bot_id}/{document_path}/{file_name}",
        "bot_id": bot_id,
        "type": "MULTIMEDIA",
        "version": 1,
        "created_by": SYSTEM_USER,
        "created_at": now,
        "updated_by": SYSTEM_USER,
        "updated_at": now,
        "_class": MULTIMEDIA_CLASS,
        "description": image_desc,
    }

    update_data = dict(doc)
    update_data.pop("_id", None)
    update_data.pop("created_at", None)

    try:
        from beegen.registry.resource_hub import ResourceHub
        from beegen.configs import MongoOperation
        mongo_engine = ResourceHub.self().mongo(mongo_resource_key)
        res = await mongo_engine.run(
            MongoOperation.UPDATE_ONE,
            {
                "collection_name": MONGO_COLLECTION,
                "filter": {"_id": file_id},
                "update": {
                    "$set": update_data,
                    "$setOnInsert": {"created_at": now},
                },
                "upsert": True,
            }
        )
        if res.get("status") == "error":
            raise RuntimeError(f"MongoEngine operation failed: {res.get('message')}")
        logger.info(f"Successfully upserted multimedia metadata for file_id='{file_id}' via Beeflow AsyncMongoEngine")
    except Exception as beeflow_exc:
        logger.warning(f"Beeflow MongoEngine upsert failed or not configured ({beeflow_exc}), falling back to direct mongo db")
        upsert_multimedia_document_to_mongo(uploaded_image, bot_id, image_desc)


DATA_IMAGE_RE = re.compile(
    r"^data:image/(?P<format>[a-zA-Z0-9.+-]+)(?:;[a-zA-Z0-9.+-]+=[^;]+)*;base64,(?P<data>.+)$",
    re.DOTALL | re.IGNORECASE,
)

IMG_TAG_SRC_RE = re.compile(
    r"""<img\b[^>]*?src=["'](?P<src>[^"']+)["'][^>]*>""",
    re.IGNORECASE,
)

MARKDOWN_IMG_RE = re.compile(
    r"""!\[(?P<alt>.*?)\]\((?P<src>[^\)]+)\)""",
)


class S3:
    def __init__(self, resource_key: str = "ai-nlp-text"):
        self.resource_key = resource_key
        self.bucket = "ai-text-raw"
        self.aws_access_key_id = None
        self.aws_secret_access_key = None
        self.endpoint_url = None

        try:
            from beegen.registry.resource_hub import ResourceHub
            s3_engine = ResourceHub.self().s3(resource_key)
            cfg = s3_engine.config
            if cfg:
                self.bucket = cfg.bucket or "ai-text-raw"
                self.aws_access_key_id = cfg.access_key
                self.aws_secret_access_key = cfg.secret_key
                self.endpoint_url = cfg.endpoint_url
        except Exception as exc:
            logger.warning(f"Could not load S3 config from ResourceHub ('{resource_key}'): {exc}")
            self.bucket = _get_env("S3_BUCKET", "ai-text-raw")
            self.aws_access_key_id = _get_env("AWS_ACCESS_KEY_ID")
            self.aws_secret_access_key = _get_env("AWS_SECRET_ACCESS_KEY")
            self.endpoint_url = _get_env("AWS_ENDPOINT_URL")

        self.s3_beegen_folder = _get_env("S3_BEEGEN_FOLDER", "chatbot_beegen_portal").strip("/")
        self.beegen_portal_url = _get_env("BEEGEN_PORTAL_URL", "https://beegen-portal-dev.mbbank.com.vn") or _get_env("S3_BASE_URL")

    def _get_boto3_client(self):
        boto_config = Config(
            signature_version="s3v4",
            s3={"payload_signing_enabled": False},
            request_checksum_calculation="when_required",
            connect_timeout=3,
            read_timeout=3,
            retries={"max_attempts": 1},
        )
        return boto3.client(
            "s3",
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            endpoint_url=self.endpoint_url,
            config=boto_config,
        )

    def format_full_s3_key(self, s3_file_path: str) -> str:
        clean_path = s3_file_path.lstrip("/")
        if self.s3_beegen_folder and not clean_path.startswith(self.s3_beegen_folder):
            return f"{self.s3_beegen_folder}/{clean_path}"
        return clean_path

    def format_url_result(self, target_bucket: str, full_key: str, file_id: Optional[str] = None) -> str:
        if file_id and self.beegen_portal_url:
            portal_base = self.beegen_portal_url.rstrip("/")
            return f"{portal_base}/beegen-portal-be/public/multimedia/download/{file_id}"
        if self.endpoint_url:
            return f"{self.endpoint_url.rstrip('/')}/{target_bucket}/{full_key}"
        return f"s3://{target_bucket}/{full_key}"

    def upload_file(
        self,
        local_file_path: str,
        s3_file_path: str,
        content_type: str = "image/png",
        bucket: Optional[str] = None,
        file_id: Optional[str] = None,
    ) -> str:
        target_bucket = bucket or self.bucket
        full_key = self.format_full_s3_key(s3_file_path)
        try:
            client = self._get_boto3_client()
            with open(local_file_path, "rb") as f:
                file_data = f.read()
            client.put_object(
                Bucket=target_bucket,
                Key=full_key,
                Body=file_data,
                ContentType=content_type,
            )
            return self.format_url_result(target_bucket, full_key, file_id=file_id)
        except Exception as exc:
            logger.error(f"Failed to upload file to S3: {exc}")
            raise exc

    def upload_bytes(
        self,
        file_data: bytes,
        s3_file_path: str,
        content_type: str = "image/png",
        bucket: Optional[str] = None,
        file_id: Optional[str] = None,
    ) -> str:
        target_bucket = bucket or self.bucket
        full_key = self.format_full_s3_key(s3_file_path)
        try:
            client = self._get_boto3_client()
            client.put_object(
                Bucket=target_bucket,
                Key=full_key,
                Body=file_data,
                ContentType=content_type,
            )
            return self.format_url_result(target_bucket, full_key, file_id=file_id)
        except Exception as exc:
            logger.error(f"Failed to upload image bytes to S3: {exc}")
            raise exc

    def check_connection(self) -> dict:
        boto_config = Config(
            signature_version="s3v4",
            s3={"payload_signing_enabled": False},
            request_checksum_calculation="when_required",
            connect_timeout=3,
            read_timeout=3,
            retries={"max_attempts": 1},
        )
        client = boto3.client(
            "s3",
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            endpoint_url=self.endpoint_url,
            config=boto_config,
        )
        try:
            client.head_bucket(Bucket=self.bucket)
            return {"status": "SUCCESS", "message": f"Connected successfully to bucket '{self.bucket}'"}
        except Exception as exc:
            return {"status": "FAILED", "message": str(exc), "endpoint": self.endpoint_url, "bucket": self.bucket}


async def upload_image_to_s3_beeflow_async(
    local_file_path: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    s3_key: str = "",
    content_type: str = "image/png",
    bucket: Optional[str] = None,
    file_id: Optional[str] = None,
    s3_resource_key: str = "ai-nlp-text",
) -> str:
    """Upload image to S3 using Beeflow S3Engine configured via ResourceHub."""
    s3_beegen_folder = _get_env("S3_BEEGEN_FOLDER", "chatbot_beegen_portal").strip("/")
    full_key = s3_key.lstrip("/")
    if s3_beegen_folder and not full_key.startswith(s3_beegen_folder):
        full_key = f"{s3_beegen_folder}/{full_key}"

    beegen_portal_url = _get_env("BEEGEN_PORTAL_URL", "https://beegen-portal-dev.mbbank.com.vn") or _get_env("S3_BASE_URL")

    try:
        from beegen.registry.resource_hub import ResourceHub
        from beegen.configs import S3Operation
        s3_engine = ResourceHub.self().s3(s3_resource_key)
        target_bucket = bucket or getattr(s3_engine.config, "bucket", None) or "ai-text-raw"

        if local_file_path:
            res = await s3_engine.run(
                S3Operation.UPLOAD_FILE,
                {
                    "local_file_path": local_file_path,
                    "key": full_key,
                    "content_type": content_type,
                    "bucket": target_bucket,
                }
            )
        else:
            res = await s3_engine.run(
                S3Operation.WRITE,
                {
                    "key": full_key,
                    "content": image_bytes,
                    "content_type": content_type,
                    "bucket": target_bucket,
                }
            )
        if res.get("status") == "error":
            raise RuntimeError(f"S3Engine operation failed: {res.get('message')}")

        if file_id and beegen_portal_url:
            portal_base = beegen_portal_url.rstrip("/")
            return f"{portal_base}/beegen-portal-be/public/multimedia/download/{file_id}"
        return res.get("document_path", f"s3://{target_bucket}/{full_key}")
    except Exception as beeflow_exc:
        logger.warning(f"Beeflow S3Engine upload failed ({beeflow_exc}), falling back to legacy S3 class with ResourceHub config")
        s3_service = S3(resource_key=s3_resource_key)
        if local_file_path:
            return s3_service.upload_file(
                local_file_path=local_file_path,
                s3_file_path=s3_key,
                content_type=content_type,
                bucket=bucket,
                file_id=file_id,
            )
        else:
            return s3_service.upload_bytes(
                file_data=image_bytes,
                s3_file_path=s3_key,
                content_type=content_type,
                bucket=bucket,
                file_id=file_id,
            )


def upload_image_bytes_to_s3(
    image_bytes: bytes,
    s3_key: str,
    content_type: str = "image/png",
    bucket: Optional[str] = None,
) -> str:
    s3_service = S3()
    return s3_service.upload_bytes(
        file_data=image_bytes,
        s3_file_path=s3_key,
        content_type=content_type,
        bucket=bucket,
    )


async def describe_image_async(
    image_bytes: Optional[bytes] = None,
    local_file_path: Optional[str] = None,
    content_type: str = "image/png",
    llm_resource_key: str = "gemini-3.1-flash-lite-chat",
) -> str:
    """Describe image content using LLMNode (multimodal)."""
    try:
        img_data = None
        if local_file_path and os.path.exists(local_file_path):
            with open(local_file_path, "rb") as f:
                img_data = f.read()
        elif image_bytes:
            img_data = image_bytes
            
        if not img_data:
            return ""
            
        import base64
        b64_str = base64.b64encode(img_data).decode("utf-8")
        image_data_url = f"data:{content_type};base64,{b64_str}"
        
        from beeflow.nodes.primitives.ai.llm_node import LLMNode
        # Instantiate LLMNode using the specified resource key
        llm_node = LLMNode(resource_key=llm_resource_key)
        
        prompt = """Bạn là trợ lý AI phân tích và mô tả hình ảnh từ tài liệu văn bản của ngân hàng.
Nhiệm vụ: Hãy mô tả ngắn gọn, chi tiết và khách quan nội dung hiển thị trong hình ảnh bằng tiếng Việt (khoảng 1-3 câu).
Ví dụ:
- Nếu ảnh hiển thị giao diện phần mềm, hãy chỉ ra tên trang giao diện và hệ thống, ví dụ: "Giao diện trang 'Báo cáo chi tiết sự vụ Tra soát' trên hệ thống CEP của MBBank." hoặc "Giao diện màn hình tạo yêu cầu tra soát trực tuyến."
- Nếu ảnh hiển thị sơ đồ quy trình, hãy mô tả ngắn gọn các bước hoặc luồng xử lý chính.
- Nếu ảnh hiển thị bảng biểu, hãy mô tả nội dung chính bảng biểu đó trình bày.
- Nếu ảnh hiển thị các tài liệu, mẫu văn bản, hãy mô tả mẫu văn bản đó là gì.

Yêu cầu cực kỳ quan trọng:
1. Chỉ trả về TRỰC TIẾP câu mô tả bằng tiếng Việt.
2. Tuyệt đối KHÔNG có tiền tố như "Mô tả ảnh:", "Hình ảnh hiển thị:", hay các thẻ XML, ký hiệu markdown.
3. Không suy diễn hoặc bịa đặt thông tin không có trong hình ảnh.
4. Nếu hình ảnh chỉ là các logo, icon nhỏ hoặc hình vẽ trang trí không có thông tin nghiệp vụ, hãy trả về chuỗi rỗng.
"""
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url
                        }
                    }
                ]
            }
        ]
        
        # Call the underlying generate method of the LLMNode core
        completion = await llm_node.core(
            messages=messages,
            temperature=0.0,
            max_tokens=1000,
        )
        description = completion.choices[0].message.content or ""
        return description.strip()
    except Exception as exc:
        logger.error(f"Failed to describe image via LLMNode: {exc}", exc_info=True)
        return ""


async def process_and_replace_s3_images_async(
    content: str,
    bot_id: str,
    document_id: str,
    bucket: Optional[str] = None,
    s3_resource_key: str = "ai-nlp-text",
    mongo_resource_key: str = "aicenter-chatbot",
    llm_resource_key: Optional[str] = "gemini-3.1-flash-lite-chat",
) -> str:
    """Detect images, upload to S3 via Beeflow S3Engine, sync Mongo multimedia metadata, and update content links."""
    if not content or not content.strip():
        return content

    bot_id = bot_id or "default_bot"
    document_id = document_id or "default_doc"
    tags_to_replace: Dict[str, str] = {}

    matches = list(IMG_TAG_SRC_RE.finditer(content)) + list(MARKDOWN_IMG_RE.finditer(content))

    for match in matches:
        original_tag = match.group(0)
        raw_src = match.group("src").strip()
        if not raw_src or original_tag in tags_to_replace:
            continue

        src_url = raw_src.strip("'\"")

        image_bytes: Optional[bytes] = None
        local_file_path: Optional[str] = None
        ext = "png"
        content_type = "image/png"

        # Case 1: Base64 data URI
        data_match = DATA_IMAGE_RE.match(src_url)
        if data_match:
            fmt = data_match.group("format").lower()
            if fmt in ("jpg", "pjpeg"):
                fmt = "jpeg"
            elif fmt == "x-png":
                fmt = "png"
            ext = "svg" if fmt == "svg+xml" else fmt
            content_type = f"image/{fmt}"
            raw_b64 = re.sub(r"\s+", "", data_match.group("data") or "")
            missing_padding = len(raw_b64) % 4
            if missing_padding:
                raw_b64 += "=" * (4 - missing_padding)
            try:
                image_bytes = base64.b64decode(raw_b64)
            except Exception as exc:
                logger.error(f"Failed to decode base64 image data: {exc}")
                continue

        # Case 2: Local file path
        else:
            clean_path = urllib.parse.unquote(src_url.replace("file://", ""))
            target_path = os.path.normpath(clean_path)
            if not os.path.exists(target_path):
                clean_no_drive = re.sub(r"^[a-zA-Z]:", "", clean_path)
                rel_path = clean_no_drive.lstrip("/\\")
                no_tmp_rel = re.sub(r"^tmp[/\\]", "", rel_path, flags=re.IGNORECASE)
                
                candidate_paths = [
                    os.path.join(tempfile.gettempdir(), rel_path),
                    os.path.join(tempfile.gettempdir(), no_tmp_rel),
                    os.path.join(os.getcwd(), rel_path),
                    os.path.join(os.getcwd(), no_tmp_rel),
                ]
                for cand in candidate_paths:
                    if os.path.exists(cand):
                        target_path = cand
                        break

            if os.path.exists(target_path) and os.path.isfile(target_path):
                ext = Path(target_path).suffix.lstrip(".").lower() or "png"
                content_type = f"image/{ext}"
                local_file_path = target_path

        if local_file_path or image_bytes:
            file_id = str(uuid.uuid4())
            s3_key = f"multimedia/{bot_id}/{document_id}/{file_id}.{ext}"

            try:
                # Describe image content using LLMNode
                image_desc = await describe_image_async(
                    image_bytes=image_bytes,
                    local_file_path=local_file_path,
                    content_type=content_type,
                    llm_resource_key=llm_resource_key,
                )

                s3_url = await upload_image_to_s3_beeflow_async(
                    local_file_path=local_file_path,
                    image_bytes=image_bytes,
                    s3_key=s3_key,
                    content_type=content_type,
                    bucket=bucket,
                    file_id=file_id,
                    s3_resource_key=s3_resource_key,
                )

                if local_file_path:
                    try:
                        os.remove(local_file_path)
                    except Exception:
                        pass

                # Build & Upsert MongoDB Multimedia record matching Beedoc workflow
                ext_clean = ext.lstrip(".").lower()
                uploaded_image_meta = {
                    "file_id": file_id,
                    "file_name": f"{file_id}.{ext_clean}",
                    "content_type": content_type,
                    "document_path": document_id,
                    "size": str(len(image_bytes)) if image_bytes else "",
                }
                await upsert_multimedia_document_to_mongo_async(
                    uploaded_image=uploaded_image_meta,
                    bot_id=bot_id,
                    image_desc=image_desc,
                    mongo_resource_key=mongo_resource_key,
                )

                # Construct updated image tag and wrap it with description
                updated_tag = original_tag.replace(raw_src, s3_url)
                wrapped_tag = f"[Hình ảnh: {updated_tag} ]"
                if image_desc:
                    wrapped_tag += f" [Mô tả ảnh: {image_desc}]"

                tags_to_replace[original_tag] = wrapped_tag
            except Exception as exc:
                logger.error(f"Failed to upload image ({raw_src}) to S3 or update Mongo: {exc}")

    replaced_content = content
    for original_tag, wrapped_tag in tags_to_replace.items():
        replaced_content = replaced_content.replace(original_tag, wrapped_tag)

    return replaced_content


def process_and_replace_s3_images(
    content: str,
    bot_id: str,
    document_id: str,
    bucket: Optional[str] = None,
    llm_resource_key: Optional[str] = None,
) -> str:
    """Synchronous entry point for process_and_replace_s3_images."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(
                process_and_replace_s3_images_async(content, bot_id, document_id, bucket, llm_resource_key=llm_resource_key)
            )
        else:
            return loop.run_until_complete(
                process_and_replace_s3_images_async(content, bot_id, document_id, bucket, llm_resource_key=llm_resource_key)
            )
    except Exception:
        return asyncio.run(
            process_and_replace_s3_images_async(content, bot_id, document_id, bucket, llm_resource_key=llm_resource_key)
        )

