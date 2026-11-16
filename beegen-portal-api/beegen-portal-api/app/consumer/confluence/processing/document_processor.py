import asyncio
import base64
import logging
import mimetypes
import os
import tempfile
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from beedoc_v3.engine import BeedocEngine
from beedoc_v3.models.document import Document as BeeDocument
from bs4 import BeautifulSoup

from app.service.chunk import chunk


logger = logging.getLogger(__name__)


async def prepare_job_item(
    document_id: str,
    content_path: str | None,
    sync_version: str,
    dispatch_status: str,
    error_detail: str,
    bot_id: str,
) -> dict[str, Any]:
    message_item = {
        "document_id": document_id,
        "content_path": content_path,
        "sync_version": sync_version,
        "dispatch_status": dispatch_status,
        "error_detail": error_detail,
        "bot_id": bot_id,
    }
    bucket, object_key, file_name = "", "", ""
    if message_item["dispatch_status"] == "READY":
        parsed = urlparse(message_item["content_path"])
        bucket, object_key = parsed.netloc, unquote(parsed.path.lstrip("/"))
        file_name = PurePosixPath(object_key).name
    return {
        "message_item": message_item,
        "s3_bucket": bucket,
        "s3_object_key": object_key,
        "s3_file_name": file_name,
        "document_query": {
            "_id": message_item["document_id"],
            "bot_id": message_item["bot_id"],
            "source": "confluence",
            "deleted": {"$ne": True},
        },
    }


async def select_job_item_route(
    message_item: dict[str, Any], document: dict[str, Any] | None
) -> dict[str, str]:
    if not document:
        raise RuntimeError(f"Document not found: {message_item['document_id']}")
    if message_item["dispatch_status"] == "ERROR":
        return {"route": "producer_error"}
    if (
        document.get("sync_status") == "done"
        and str(document.get("sync_version")) == str(message_item["sync_version"])
    ):
        return {"route": "skip"}
    return {"route": "process"}


@lru_cache()
def get_beedoc_engine() -> BeedocEngine:
    return BeedocEngine()


async def extract_confluence_document(
    document_bytes: bytes,
) -> dict[str, Any]:
    """Extract BeeDoc reconstructed content while retaining the source HTML for images."""
    html_content = document_bytes.decode("utf-8-sig")
    temp_path = ""

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix="confluence-",
            suffix=".html",
            delete=False,
        ) as temp_file:
            temp_file.write(document_bytes)
            temp_path = temp_file.name

        document: BeeDocument = await get_beedoc_engine().process(temp_path)
        reconstructed = (
            (document.reconstructed_content or "").strip() if document else ""
        )
        zones = []
        if not reconstructed and document:
            for page in document.pages or []:
                sheet_name = (
                    page.metadata.get("sheet_name", "") if page.metadata else ""
                )
                for zone in page.content or []:
                    if zone and zone.content:
                        zones.append(
                            {"content": zone.content, "sheet_name": sheet_name}
                        )

        return {
            "html_content": html_content,
            "reconstructed": reconstructed,
            "zones": zones,
        }
    finally:
        if temp_path and os.path.isfile(temp_path):
            os.remove(temp_path)


async def run_chunk(
    reconstructed: str,
    zones: list[dict[str, Any]],
    file_name: str,
    message_item: dict[str, Any],
) -> dict[str, Any]:
    try:
        result = await asyncio.wait_for(
            chunk(
                reconstructed=reconstructed,
                zones=zones,
                file_name=file_name,
                chunk_type="hierarchical",
                extract_keywords=False,
            ),
            timeout=10 * 60,
        )
        chunks = result.get("chunks", []) if isinstance(result, dict) else result
        if not isinstance(chunks, list):
            raise ValueError("chunk must return a chunks list")
        return {
            "chunk_documents": chunks,
            "chunk_status": "success",
            "chunk_error_message": "",
        }
    except asyncio.TimeoutError:
        logger.exception(
            "Chunk timed out after 10 minutes document_id=%s",
            message_item.get("document_id"),
        )
        return {
            "chunk_documents": [],
            "chunk_status": "error",
            "chunk_error_message": "Chunk processing timed out after 10 minutes",
        }
    except Exception as exc:
        logger.exception("Chunk failed document_id=%s", message_item.get("document_id"))
        return {
            "chunk_documents": [],
            "chunk_status": "error",
            "chunk_error_message": str(exc),
        }


async def prepare_document_data(
    chunk_documents: list, message_item: dict[str, Any]
) -> dict[str, Any]:
    document_data_rows = [
        {
            "_id": str(uuid.uuid4()),
            "document_id": message_item["document_id"],
            "content": chunk["content"],
            "index": index,
            "created_at": datetime.now(timezone.utc),
            "bot_id": message_item["bot_id"],
        }
        for index, chunk in enumerate(chunk_documents)
    ]
    return {
        "document_data_rows": document_data_rows,
        "has_document_data_rows": bool(document_data_rows),
    }


async def build_chunk_success_update(insert_status: str = "success") -> dict[str, Any]:
    if insert_status != "success":
        raise RuntimeError("Could not insert Chunk document_data")
    return {
        "mongo_update": {
            "$set": {
                "status": "DONE",
                "sync_status": "done",
                "chunk_type": "hierarchical",
                "is_trained": False,
                "training_status": "NOT_TRAINING",
                "changed_chunking": False,
                "source_type": "confluence",
            },
            "$unset": {
                "error_message": "",
                "trained_at": "",
                "valid_from": "",
                "valid_to": "",
                "role_ids": "",
            },
        }
    }


async def build_chunk_error_update(error_message: str) -> dict[str, Any]:
    return {
        "mongo_update": {
            "$set": {
                "status": "ERROR",
                "sync_status": "error",
                "error_message": error_message or "Chunk processing failed",
            }
        }
    }


async def build_document_job_result(
    message_item: dict[str, Any],
    document: dict[str, Any],
    result_status: str,
    error_message: str | None = None,
    document_update_status: str | None = None,
    html_delete_status: str | None = None,
) -> dict[str, Any]:
    if document_update_status is not None and document_update_status != "success":
        raise RuntimeError("Could not update final Chunk document status")
    if html_delete_status is not None and html_delete_status != "success":
        raise RuntimeError("Could not delete processed Confluence HTML")
    return {
        "chunk_result_item": {
            "doc_id": message_item["document_id"],
            "doc_name": document.get("doc_name"),
            "version": str(message_item["sync_version"]),
            "updated_by": document.get("updated_by"),
            "status": result_status,
            "error_detail": (
                message_item.get("error_detail", "")
                if error_message is None
                else error_message
            ),
        }
    }


async def build_aggregate_job_response(
    current_job_id: str,
    current_bot_id: str,
    job_items: list,
    loop_results: list,
) -> dict[str, Any]:
    results = []
    for index, item in enumerate(job_items):
        loop_result = loop_results[index] if index < len(loop_results) else {}
        result = loop_result.get("chunk_result_item") if isinstance(loop_result, dict) else None
        if not isinstance(result, dict):
            result = {
                "doc_id": item["document_id"],
                "doc_name": None,
                "version": str(item["sync_version"]),
                "updated_by": None,
                "status": "error",
                "error_detail": "Chunk workflow did not reach a terminal result",
            }
        results.append(result)
    success_count = sum(item["status"] == "success" for item in results)
    failed_count = len(results) - success_count
    logger.info(
        "Chunk job complete job_id=%s total=%s success=%s failed=%s",
        current_job_id, len(results), success_count, failed_count,
    )
    return {
        "response_key": str(current_bot_id),
        "response_value": {
            "message_type": "job_response",
            "bot_id": str(current_bot_id),
            "classify": "confluence_sync",
            "job_id": str(current_job_id),
            "summary": {"total": len(results), "success": success_count, "failed": failed_count},
            "data": results,
        },
    }


async def complete_chunk_job(response_status: str) -> dict[str, Any]:
    if response_status != "success":
        raise RuntimeError("Could not publish aggregate Chunk job_response")
    return {"processing_completed": True}


def _image_extension(content_type: str) -> str:
    if content_type == "image/jpeg":
        return ".jpg"
    return mimetypes.guess_extension(content_type) or ".bin"


async def prepare_chunk_image_uploads(
    chunk_documents: list,
    html_content: str,
    message_item: dict[str, Any],
    document: dict[str, Any],
) -> dict[str, Any]:
    marker_ids = []
    for chunk_document in chunk_documents:
        chunk_html = BeautifulSoup(chunk_document["content"], "html.parser")
        for image in chunk_html.select("img[data-image-id]"):
            image_id = image["data-image-id"]
            if image_id not in marker_ids:
                marker_ids.append(image_id)

    if not marker_ids:
        return {"image_upload_batch": [], "new_multimedia_ids": []}

    source_html = BeautifulSoup(html_content, "html.parser")
    image_dir = tempfile.mkdtemp(prefix="confluence-chunk-images-")
    document_id = str(document["_id"])
    bot_id = str(message_item["bot_id"])
    bucket = "ai-text-raw"
    s3_prefix = os.environ["CONFLUENCE_IMAGE_S3_PREFIX"].strip("/")
    upload_batch = []

    for image_id in marker_ids:
        source_image = source_html.find("img", attrs={"data-image-id": image_id})
        if source_image is None:
            raise ValueError(f"Image marker {image_id} is missing from Confluence HTML")

        metadata, encoded = source_image["src"].split(",", 1)
        content_type = metadata.removeprefix("data:").split(";", 1)[0]
        extension = _image_extension(content_type)
        local_file_path = os.path.join(image_dir, f"{image_id}{extension}")
        multimedia_id = str(uuid.uuid4())
        file_name = f"{multimedia_id}{extension}"
        object_key = f"{s3_prefix}/{bot_id}/{document_id}/{file_name}"

        image_bytes = base64.b64decode(encoded)
        with open(local_file_path, "wb") as image_file:
            image_file.write(image_bytes)

        now = datetime.now(timezone.utc)
        upload_batch.append({
            "bucket": bucket,
            "local_file_path": local_file_path,
            "key": object_key,
            "content_type": content_type,
            "multimedia_document": {
                "_id": multimedia_id,
                "_class": "vn.com.mbbank.aicenter.beegen.portal.entity.document.Multimedia",
                "bot_id": bot_id,
                "document_id": document_id,
                "content_type": content_type,
                "created_at": now,
                "created_by": "system",
                "file_name": file_name,
                "path": object_key,
                "size": "",
                "type": "MULTIMEDIA",
                "updated_at": now,
                "updated_by": "system",
                "user_id": "system",
                "user_name": "system",
                "version": 1,
            },
        })

    return {
        "image_upload_batch": upload_batch,
        "new_multimedia_ids": [
            upload["multimedia_document"]["_id"] for upload in upload_batch
        ],
    }


async def replace_chunk_image_markers(
    chunk_documents: list,
    image_upload_batch: list,
    image_upload_results: list,
) -> dict[str, Any]:
    try:
        if any(result.get("status") != "success" for result in image_upload_results):
            return {
                "chunk_documents_with_image_paths": chunk_documents,
                "image_processing_failed": True,
                "image_processing_error_message": (
                    "Could not upload Confluence image or save multimedia metadata"
                ),
            }

        if image_upload_batch:
            public_download_url = os.environ[
                "CONFLUENCE_IMAGE_PUBLIC_DOWNLOAD_URL"
            ].rstrip("/")
            image_paths = {
                os.path.splitext(os.path.basename(upload["local_file_path"]))[0]: (
                    f"{public_download_url}/{upload['multimedia_document']['_id']}"
                )
                for upload in image_upload_batch
            }

            for chunk_document in chunk_documents:
                chunk_html = BeautifulSoup(chunk_document["content"], "html.parser")
                for image in chunk_html.select("img[data-image-id]"):
                    image["src"] = image_paths[image["data-image-id"]]
                    image["loading"] = "lazy"
                    image["alt"] = "Uploaded Image"
                    del image["data-image-id"]
                chunk_document["content"] = str(chunk_html)

        return {
            "chunk_documents_with_image_paths": chunk_documents,
            "image_processing_failed": False,
            "image_processing_error_message": "",
        }
    finally:
        image_dirs = set()
        for upload in image_upload_batch:
            local_file_path = upload["local_file_path"]
            image_dirs.add(os.path.dirname(local_file_path))
            if os.path.isfile(local_file_path):
                os.remove(local_file_path)
        for image_dir in image_dirs:
            if os.path.isdir(image_dir):
                os.rmdir(image_dir)


