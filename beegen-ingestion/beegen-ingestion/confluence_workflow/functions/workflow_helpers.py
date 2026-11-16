"""
Workflow helper functions for BeeFlow nodes.

This module provides helper functions for workflow operations.
"""

import re
import asyncio
import base64
import hashlib
import os
import shutil
import unicodedata
from datetime import datetime, timezone
from html import escape, unescape
from typing import Dict, Any
import pyotp
import requests
from bs4 import BeautifulSoup
from confluence_workflow.utils.logger import get_logger
from confluence_workflow.functions.mongo_processor import MongoDBConnection
from urllib.parse import unquote, urljoin, urlparse

logger = get_logger('workflow_helpers')


def compute_content_hash(content: str) -> str:
    """Compute an MD5 hash for Confluence content comparison."""
    return hashlib.md5((content or "").encode("utf-8")).hexdigest()


def normalize_doc_name(doc_name: str | None) -> str:
    """Normalize document names the same way legacy Mongo storage does."""
    if not doc_name:
        return ""
    # Xử lý dấu trong tiếng việt và đặc biệt là chữ đ -> d
    normalized = unicodedata.normalize("NFD", str(doc_name).lower())
    ascii_name = "".join(
        character for character in normalized
        if unicodedata.category(character) != "Mn"
    ).replace("\u0111", "d") 
    return re.sub(r"\s+", "_", ascii_name.strip()).lower()


def normalize_s3_file_stem(doc_name: str) -> str:
    """Remove path-unsafe characters while preserving the document name."""
    return re.sub(r"[^\w ]", "", doc_name).strip()


def normalize_utc_datetime(value: Any) -> datetime:
    """Normalize ISO datetime/string/None to UTC-aware datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if isinstance(value, str) and value:
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass

    return datetime.now(timezone.utc)


def build_metadata_update_batches(pages: list | None, bot_id: str) -> Dict[str, Any]:
    """Update title metadata without reprocessing content or changing sync_mode."""
    batch_data = []
    for page in pages or []:
        if not isinstance(page, dict) or page.get("id") is None:
            continue

        page_id = str(page["id"])
        title = page.get("title", "")
        version = page.get("version", {}).get("number", 1)
        source_link = page.get("_links", {}).get("webui", "")
        updated_by = page.get("version", {}).get("by", {}).get("username", "Unknown")
        updated_at_raw = page.get("version", {}).get("when")
        updated_at = (
            normalize_utc_datetime(updated_at_raw)
            if updated_at_raw
            else datetime.now(timezone.utc)
        )

        batch_data.append({
            "sql_query": """
                UPDATE knowledge_base.documents
                SET title = %s,
                    version_number = %s,
                    source_link = %s,
                    updated_by = %s,
                    updated_at = %s::TIMESTAMPTZ
                WHERE bot_id = %s AND page_id = %s
            """,
            "sql_params": (
                title,
                version,
                source_link,
                updated_by,
                updated_at,
                bot_id,
                page_id,
            ),
            "mongo_filter": {"bot_id": bot_id, "external_id": page_id},
            "mongo_update": {
                "$set": {
                    "doc_name": title,
                    "doc_name_normalize": normalize_doc_name(title),
                    "sync_version": str(version),
                    "source_link": source_link,
                    "updated_by": updated_by,
                    "updated_at": updated_at,
                },
                "$currentDate": {"sync_at": True},
            },
        })

    logger.info("Built %s metadata-only update batches", len(batch_data))
    return {
        "batch_data": batch_data,
        "metadata_updated_count": len(batch_data),
    }


def normalize_page_ids(
    page_ids: list | None,
    page_id_keys: tuple[str, ...] = ("confluence_page_id", "external_id", "page_id", "id"),
) -> set[str]:
    """Normalize page IDs from scalar rows or dict rows to a string set."""
    normalized_ids = set()

    for item in page_ids or []:
        if item is None:
            continue

        if isinstance(item, dict):
            page_id = next(
                (item.get(key) for key in page_id_keys if item.get(key) is not None),
                None,
            )
            if page_id is not None:
                normalized_ids.add(str(page_id))
            continue

        normalized_ids.add(str(item))

    return normalized_ids


async def build_deleted_page_cleanup_inputs(
    primary_page_ids: list | None = None,
    additional_page_ids: list | None = None,
    bot_id: str | None = None,
) -> dict:
    """Build merged deleted page ids, SQL params, and Mongo selector."""
    page_ids = []
    seen_ids = set()

    for page_id in (primary_page_ids or []) + (additional_page_ids or []):
        if page_id is None:
            continue

        normalized_page_id = str(page_id)
        if normalized_page_id in seen_ids:
            continue

        seen_ids.add(normalized_page_id)
        page_ids.append(normalized_page_id)

    selector: Dict[str, Any] = {"external_id": {"$in": page_ids}}
    if bot_id is not None:
        selector["bot_id"] = bot_id

    return {
        "page_ids": page_ids,
        "params": (page_ids, bot_id),
        "selector": selector,
    }


async def extract_job_id(create_job_result: Dict[str, Any]) -> Dict[str, Any]:
    """Extract scalar job_id from SQL EXECUTE result rows."""
    if isinstance(create_job_result, list):
        rows = create_job_result
    else:
        rows = []

    if not rows:
        raise ValueError("Failed to create sync job: no returned id")
    first_row = rows[0]
    job_id = first_row.get("id")
    if job_id is None:
        raise ValueError("Failed to create sync job: missing id field")

    return {"job_id": str(job_id)}

async def update_sync_time(bot_id: str, sync_mode: str, page_ids: list | None = None) -> Dict[str, Any]:
    """Run legacy sync_at update logic based on sync mode."""
    normalized_mode = sync_mode.upper()

    if normalized_mode == "FIRST":
        logger.info("Skipping bulk sync_at update for FIRST mode")
        return {"updated_count": 0, "skipped": True}

    if normalized_mode == "AUTO":
        logger.info(
            "Skipping bulk sync_at update for AUTO mode; changed pages update sync_at in their own branches"
        )
        return {"updated_count": 0, "skipped": True}

    mongo_conn = MongoDBConnection()
    await mongo_conn.connect()
    try:
        if normalized_mode == "PARTIAL":
            updated_count = await mongo_conn.update_sync_time_partial_mode(
                bot_id=bot_id,
                page_ids=page_ids or [],
            )
        else:
            logger.warning("Unknown sync mode for sync_at update: %s", sync_mode)
            return {"updated_count": 0, "skipped": True}

        logger.info("Updated sync_at for %s documents in %s mode", updated_count, normalized_mode)
        return {"updated_count": updated_count, "skipped": False}
    finally:
        await mongo_conn.disconnect()

async def forward_mode_output(
    current_updated_pages: list,
    current_pages_no_change: list | None = None,
    current_total_processed: int = 0,
    current_total_updated: int = 0,
    current_total_deleted: int = 0,
) -> Dict[str, Any]:
    return {
        "updated_pages": current_updated_pages,
        "pages_no_change": current_pages_no_change,
        "total_processed": current_total_processed,
        "total_updated": current_total_updated,
        "total_deleted": current_total_deleted,
    }


async def build_empty_mode_output() -> Dict[str, Any]:
    """Return an empty mode payload for short-circuit graph branches."""
    return {
        "updated_pages": [],
        "pages_no_change": [],
        "total_processed": 0,
        "total_updated": 0,
        "total_deleted": 0,
    }


async def build_first_mode_stats(
    total_count: int,
    deleted_page_ids: list | None = None,
) -> Dict[str, Any]:
    """Build FIRST mode counters for added and removed root trees."""
    deleted_count = len(deleted_page_ids or [])
    return {
        "total_processed": (total_count or 0) + deleted_count,
        "total_updated": total_count or 0,
        "total_deleted": deleted_count,
    }


async def build_partial_mode_stats(
    fetched_pages: list | None,
    inserted_count: int = 0,
    updated_count: int = 0,
    metadata_updated_count: int = 0,
    deleted_count: int = 0,
) -> Dict[str, Any]:
    """Build PARTIAL mode counters matching legacy execute()."""
    unique_page_ids = {
        str(page.get("id"))
        for page in (fetched_pages or [])
        if isinstance(page, dict) and page.get("id") is not None
    }
    return {
        "total_processed": len(unique_page_ids),
        "total_updated": (
            (inserted_count or 0)
            + (updated_count or 0)
            + (metadata_updated_count or 0)
        ),
        "total_deleted": deleted_count or 0,
    }


async def build_auto_mode_stats(
    inserted_count: int = 0,
    updated_count: int = 0,
    metadata_updated_count: int = 0,
    moved_count: int = 0,
    deleted_page_ids: list | None = None,
) -> Dict[str, Any]:
    """Build AUTO mode counters matching legacy execute()."""
    deleted_count = len(deleted_page_ids or [])
    return {
        "total_processed": (
            (inserted_count or 0)
            + (updated_count or 0)
            + (metadata_updated_count or 0)
            + (moved_count or 0)
            + deleted_count
        ),
        "total_updated": (
            (inserted_count or 0)
            + (updated_count or 0)
            + (metadata_updated_count or 0)
        ),
        "total_deleted": deleted_count,
    }


async def build_bot_sync_mode_query(bot_id: str) -> Dict[str, Any]:
    """Build Mongo query for active Confluence sync_mode documents of a bot."""
    return {"query": {"bot_id": bot_id, "source": "confluence", "sync_mode": True}}


async def build_bot_selector(bot_id: str) -> Dict[str, Any]:
    """Build a Mongo query for Confluence documents of a bot."""
    return {"query": {"bot_id": bot_id, "source": "confluence"}}


async def forward_sync_context(
    current_job_id: str,
    current_bot_id: str,
    current_sync_mode: str,
    current_page_ids: list | None = None,
    current_updated_pages: list | None = None,
    current_total_processed: int = 0,
    current_total_updated: int = 0,
    current_total_deleted: int = 0,
    current_status: str = "COMPLETED",
    current_error: str | None = None,
) -> Dict[str, Any]:
    """Pass workflow context through a graph without input/output name collisions."""
    return {
        "job_id": current_job_id,
        "bot_id": current_bot_id,
        "sync_mode": current_sync_mode,
        "page_ids": current_page_ids,
        "updated_pages": current_updated_pages,
        "total_processed": current_total_processed,
        "total_updated": current_total_updated,
        "total_deleted": current_total_deleted,
        "status": current_status,
        "error": current_error,
    }


async def build_finalize_payload(
    job_id: str,
    status: str | None,
    total_processed: int,
    total_updated: int,
    total_deleted: int,
    error: str | None = None,
    updated_pages: list | None = None,
) -> Dict[str, Any]:
    """Build SQL params and final result payload for finalize graph."""
    normalized_status = status or "COMPLETED"
    normalized_error = error or ""
    finished_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "params": (
            normalized_status,
            total_processed or 0,
            total_updated or 0,
            total_deleted or 0,
            normalized_error,
            job_id,
        ),
        "result": {
            "job_id": job_id,
            "status": normalized_status,
            "total_processed": total_processed or 0,
            "total_updated": total_updated or 0,
            "total_deleted": total_deleted or 0,
            "updated_pages": updated_pages or [],
            "error": normalized_error,
            "finished_at": finished_at,
        },
    }


async def select_mode_output(
    current_sync_mode: str,
    current_job_id: str,
    current_bot_id: str,
    current_page_ids: list | None = None,
    current_confluence_config: Dict[str, Any] | None = None,
    first_updated_pages: list | None = None,
    first_pages_no_change: list | None = None,
    first_total_processed: int | None = None,
    first_total_updated: int | None = None,
    first_total_deleted: int | None = None,
    partial_updated_pages: list | None = None,
    partial_pages_no_change: list | None = None,
    partial_total_processed: int | None = None,
    partial_total_updated: int | None = None,
    partial_total_deleted: int | None = None,
    auto_updated_pages: list | None = None,
    auto_pages_no_change: list | None = None,
    auto_total_processed: int | None = None,
    auto_total_updated: int | None = None,
    auto_total_deleted: int | None = None,
) -> Dict[str, Any]:
    """Select the active mode outputs and package them for downstream graphs."""
    normalized_mode = str(current_sync_mode or "").upper()

    if normalized_mode == "FIRST":
        updated_pages = first_updated_pages or []
        pages_no_change = first_pages_no_change or []
        total_processed = first_total_processed or 0
        total_updated = first_total_updated or 0
        total_deleted = first_total_deleted or 0
        mode_missing = (
            first_updated_pages is None
            and first_pages_no_change is None
            and first_total_processed is None
            and first_total_updated is None
            and first_total_deleted is None
        )
    elif normalized_mode == "AUTO":
        updated_pages = auto_updated_pages or []
        pages_no_change = auto_pages_no_change or []
        total_processed = auto_total_processed or 0
        total_updated = auto_total_updated or 0
        total_deleted = auto_total_deleted or 0
        mode_missing = (
            auto_updated_pages is None
            and auto_pages_no_change is None
            and auto_total_processed is None
            and auto_total_updated is None
            and auto_total_deleted is None
        )
    else:
        updated_pages = partial_updated_pages or []
        pages_no_change = partial_pages_no_change or []
        total_processed = partial_total_processed or 0
        total_updated = partial_total_updated or 0
        total_deleted = partial_total_deleted or 0
        mode_missing = (
            partial_updated_pages is None
            and partial_pages_no_change is None
            and partial_total_processed is None
            and partial_total_updated is None
            and partial_total_deleted is None
        )

    status = "FAILED" if mode_missing else "COMPLETED"
    error = f"{normalized_mode or 'UNKNOWN'} mode graph failed to produce outputs" if mode_missing else ""

    return {
        "job_id": current_job_id,
        "bot_id": current_bot_id,
        "sync_mode": normalized_mode,
        "page_ids": current_page_ids or [],
        "confluence_config": current_confluence_config or {},
        "updated_pages": updated_pages,
        "pages_no_change": pages_no_change,
        "total_processed": total_processed,
        "total_updated": total_updated,
        "total_deleted": total_deleted,
        "status": status,
        "error": error,
        "should_continue": status != "FAILED",
    }


async def validate_stage_context(
    stage_name: str,
    current_job_id: str | None = None,
    current_bot_id: str | None = None,
    current_sync_mode: str | None = None,
    current_page_ids: list | None = None,
    current_updated_pages: list | None = None,
    current_total_processed: int | None = None,
    current_total_updated: int | None = None,
    current_total_deleted: int | None = None,
    current_status: str | None = None,
    current_error: str | None = None,
    fallback_job_id: str | None = None,
    fallback_bot_id: str | None = None,
    fallback_sync_mode: str | None = None,
    fallback_page_ids: list | None = None,
    fallback_updated_pages: list | None = None,
    fallback_total_processed: int | None = None,
    fallback_total_updated: int | None = None,
    fallback_total_deleted: int | None = None,
    fallback_status: str | None = None,
    fallback_error: str | None = None,
) -> Dict[str, Any]:
    """Validate stage outputs and keep enough context to finalize FAILED jobs."""
    if current_job_id is None:
        status = "FAILED"
        error = current_error or fallback_error or f"{stage_name} failed to produce outputs"
        return {
            "job_id": fallback_job_id,
            "bot_id": fallback_bot_id,
            "sync_mode": fallback_sync_mode,
            "page_ids": fallback_page_ids or [],
            "updated_pages": fallback_updated_pages or [],
            "total_processed": fallback_total_processed or 0,
            "total_updated": fallback_total_updated or 0,
            "total_deleted": fallback_total_deleted or 0,
            "status": status,
            "error": error,
            "should_continue": False,
        }

    status = current_status or fallback_status or "COMPLETED"
    error = current_error or fallback_error or ""
    if status == "FAILED":
        return {
            "job_id": current_job_id,
            "bot_id": current_bot_id or fallback_bot_id,
            "sync_mode": current_sync_mode or fallback_sync_mode,
            "page_ids": current_page_ids or fallback_page_ids or [],
            "updated_pages": current_updated_pages or fallback_updated_pages or [],
            "total_processed": current_total_processed if current_total_processed is not None else (fallback_total_processed or 0),
            "total_updated": current_total_updated if current_total_updated is not None else (fallback_total_updated or 0),
            "total_deleted": current_total_deleted if current_total_deleted is not None else (fallback_total_deleted or 0),
            "status": status,
            "error": error,
            "should_continue": False,
        }

    return {
        "job_id": current_job_id,
        "bot_id": current_bot_id or fallback_bot_id,
        "sync_mode": current_sync_mode or fallback_sync_mode,
        "page_ids": current_page_ids or fallback_page_ids or [],
        "updated_pages": current_updated_pages if current_updated_pages is not None else (fallback_updated_pages or []),
        "total_processed": current_total_processed if current_total_processed is not None else (fallback_total_processed or 0),
        "total_updated": current_total_updated if current_total_updated is not None else (fallback_total_updated or 0),
        "total_deleted": current_total_deleted if current_total_deleted is not None else (fallback_total_deleted or 0),
        "status": status,
        "error": error,
        "should_continue": True,
    }


async def select_finalize_context(
    mode_job_id: str | None = None,
    mode_status: str | None = None,
    mode_total_processed: int | None = None,
    mode_total_updated: int | None = None,
    mode_total_deleted: int | None = None,
    mode_error: str | None = None,
    mode_updated_pages: list | None = None,
    resolve_job_id: str | None = None,
    resolve_status: str | None = None,
    resolve_total_processed: int | None = None,
    resolve_total_updated: int | None = None,
    resolve_total_deleted: int | None = None,
    resolve_error: str | None = None,
    resolve_updated_pages: list | None = None,
    calculate_job_id: str | None = None,
    calculate_status: str | None = None,
    calculate_total_processed: int | None = None,
    calculate_total_updated: int | None = None,
    calculate_total_deleted: int | None = None,
    calculate_error: str | None = None,
    calculate_updated_pages: list | None = None,
    sync_job_id: str | None = None,
    sync_status: str | None = None,
    sync_total_processed: int | None = None,
    sync_total_updated: int | None = None,
    sync_total_deleted: int | None = None,
    sync_error: str | None = None,
    sync_updated_pages: list | None = None,
    fetch_job_id: str | None = None,
    fetch_status: str | None = None,
    fetch_total_processed: int | None = None,
    fetch_total_updated: int | None = None,
    fetch_total_deleted: int | None = None,
    fetch_error: str | None = None,
    fetch_updated_pages: list | None = None,
) -> Dict[str, Any]:
    """Pick the latest available context for finalization."""
    candidates = [
        {
            "job_id": fetch_job_id,
            "status": fetch_status,
            "total_processed": fetch_total_processed,
            "total_updated": fetch_total_updated,
            "total_deleted": fetch_total_deleted,
            "error": fetch_error,
            "updated_pages": fetch_updated_pages,
        },
        {
            "job_id": sync_job_id,
            "status": sync_status,
            "total_processed": sync_total_processed,
            "total_updated": sync_total_updated,
            "total_deleted": sync_total_deleted,
            "error": sync_error,
            "updated_pages": sync_updated_pages,
        },
        {
            "job_id": calculate_job_id,
            "status": calculate_status,
            "total_processed": calculate_total_processed,
            "total_updated": calculate_total_updated,
            "total_deleted": calculate_total_deleted,
            "error": calculate_error,
            "updated_pages": calculate_updated_pages,
        },
        {
            "job_id": resolve_job_id,
            "status": resolve_status,
            "total_processed": resolve_total_processed,
            "total_updated": resolve_total_updated,
            "total_deleted": resolve_total_deleted,
            "error": resolve_error,
            "updated_pages": resolve_updated_pages,
        },
        {
            "job_id": mode_job_id,
            "status": mode_status,
            "total_processed": mode_total_processed,
            "total_updated": mode_total_updated,
            "total_deleted": mode_total_deleted,
            "error": mode_error,
            "updated_pages": mode_updated_pages,
        },
    ]

    selected = next((candidate for candidate in candidates if candidate["job_id"] is not None), None)
    if selected is None:
        return {
            "job_id": None,
            "status": "FAILED",
            "total_processed": 0,
            "total_updated": 0,
            "total_deleted": 0,
            "error": "Workflow failed before a sync job context was available",
            "updated_pages": [],
        }

    return {
        "job_id": selected["job_id"],
        "status": selected["status"] or "COMPLETED",
        "total_processed": selected["total_processed"] or 0,
        "total_updated": selected["total_updated"] or 0,
        "total_deleted": selected["total_deleted"] or 0,
        "error": selected["error"] or "",
        "updated_pages": selected["updated_pages"] or [],
    }


async def select_pages_for_chunk_processing(
    confluence_config: Dict[str, Any],
    bot_id: str,
    updated_pages: list,
) -> Dict[str, Any]:
    """Select pages that need per-page download and chunk processing."""
    pages_for_chunk_processing = []

    for page_info in updated_pages:
        if page_info["sync_status"] not in ("NEW", "UPDATED", "MOVED"):
            continue

        pages_for_chunk_processing.append({
            "page_id": str(page_info["page_id"]),
            "bot_id": bot_id,
            "title": page_info["title"],
            "version": page_info["version"],
            "page_content": page_info["content"],
            "source_link": page_info["source_link"],
            "updated_by": page_info["updated_by"],
            "sync_status": page_info["sync_status"],
            "confluence_config": confluence_config,
        })

    logger.info("Selected %s Confluence pages for chunk processing", len(pages_for_chunk_processing))
    return {
        "pages_for_chunk_processing": pages_for_chunk_processing,
        "has_pages_for_chunk_processing": len(pages_for_chunk_processing) > 0,
    }


def _confluence_html_download_dir() -> str:
    output_dir = os.getenv("CONFLUENCE_HTML_DOWNLOAD_DIR")
    if output_dir:
        return os.path.abspath(output_dir)
    return os.path.abspath(os.path.join(os.getcwd(), "tmp", "confluence_html_downloads"))


def _write_html_to_temp_file(html_content: str, page_id: str) -> str:
    """Write HTML content to a local debug folder and return its path."""
    output_dir = _confluence_html_download_dir()
    os.makedirs(output_dir, exist_ok=True)

    file_path = os.path.join(output_dir, f"{page_id}.html")

    with open(file_path, "w", encoding="utf-8") as html_file:
        html_file.write(html_content)

    return file_path


def _build_confluence_html_document(html_fragment: str, title: str | None) -> str:
    """Wrap Confluence export_view HTML as a complete HTML document."""
    page_title = escape(str(title or "Confluence page"), quote=True)
    fragment = str(html_fragment or "")

    if "<html" in fragment[:500].lower():
        return fragment

    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f"<title>{page_title}</title></head><body>{fragment}</body></html>"
    )


def _build_confluence_download_session(confluence_config: Dict[str, Any]) -> requests.Session:
    session = requests.Session()
    token = str((confluence_config or {}).get("token") or "").strip()
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    return session


def _confluence_destination_from_url(absolute_url: str) -> str:
    parsed = urlparse(str(absolute_url or ""))
    destination = parsed.path or "/"
    if parsed.query:
        destination = f"{destination}?{parsed.query}"
    return destination


def _resolve_html_resource_url(base_url: str, resource_url: str) -> str:
    resource_url = str(resource_url or "").strip()
    if not resource_url:
        return ""

    parsed = urlparse(resource_url)
    if parsed.scheme and parsed.netloc:
        return resource_url

    return urljoin(base_url.rstrip("/") + "/", resource_url.lstrip("/"))


def _normalize_confluence_attachment_name(value: str | None) -> str:
    normalized = unquote(str(value or "").strip())
    for _ in range(2):
        decoded = unescape(normalized)
        if decoded == normalized:
            break
        normalized = decoded
    return unicodedata.normalize("NFC", normalized)


def _candidate_confluence_attachment_names(value: str | None) -> set[str]:
    raw_value = str(value or "").strip()
    parsed = urlparse(raw_value)
    path_name = _normalize_confluence_attachment_name(os.path.basename(parsed.path or ""))
    raw_name = _normalize_confluence_attachment_name(os.path.basename(raw_value))
    return {name for name in {path_name, raw_name} if name}


def _extract_storage_attachment_names(storage_html: str | None) -> list[str]:
    filenames = re.findall(
        r"<ri:attachment\b[^>]*\bri:filename=[\"']([^\"']+)[\"']",
        str(storage_html or ""),
        flags=re.IGNORECASE,
    )
    return list(dict.fromkeys(_normalize_confluence_attachment_name(name) for name in filenames))


def _extract_html_attachment_names(soup: BeautifulSoup) -> list[str]:
    filenames = []

    for element in soup.select('[data-linked-resource-type="attachment"]'):
        alias = str(element.get("data-linked-resource-default-alias") or "").strip()
        if alias:
            filenames.append(_normalize_confluence_attachment_name(alias))
            continue

        resource_url = str(element.get("href") or element.get("src") or "").strip()
        filenames.extend(_candidate_confluence_attachment_names(resource_url))

    for image in soup.find_all("img"):
        for attr_name in ("data-linked-resource-default-alias", "data-image-src", "data-src", "src"):
            filenames.extend(_candidate_confluence_attachment_names(str(image.get(attr_name) or "")))

    return list(dict.fromkeys(name for name in filenames if name))


def _build_confluence_attachment_download_map(
    confluence: Any,
    page_id: str,
    soup: BeautifulSoup,
    storage_html: str | None,
) -> Dict[str, str]:
    referenced_names = set(_extract_storage_attachment_names(storage_html))
    referenced_names.update(_extract_html_attachment_names(soup))
    if not referenced_names:
        return {}

    try:
        attachments = confluence.get_attachments_from_content(
            page_id,
            limit=200,
            expand="metadata",
        )
    except Exception as exc:
        logger.warning("Failed to fetch Confluence attachments for page_id=%s: %s", page_id, exc)
        return {}

    download_map = {}
    for item in (attachments or {}).get("results", []):
        if not isinstance(item, dict):
            continue

        title = _normalize_confluence_attachment_name(item.get("title"))
        if not title or title not in referenced_names:
            continue

        download_path = str((item.get("_links") or {}).get("download") or "").strip()
        if download_path:
            download_map[title] = download_path

    logger.info(
        "Resolved Confluence image attachments for page_id=%s: referenced=%s matched=%s",
        page_id,
        len(referenced_names),
        len(download_map),
    )
    return download_map


def _require_confluence_image_web_credentials(confluence_config: Dict[str, Any]) -> tuple[str, str, str]:
    username = str((confluence_config or {}).get("username") or "").strip()
    password = str((confluence_config or {}).get("password") or "")
    otp_secret = str((confluence_config or {}).get("otp_secret") or "").strip()
    if not username or not password:
        raise RuntimeError(
            "Confluence image download requires web authentication. "
            "Configure CONFLUENCE_USERNAME and CONFLUENCE_PASSWORD."
        )
    return username, password, otp_secret


def _submit_confluence_image_totp(
    session: requests.Session,
    response: requests.Response,
    otp_secret: str,
) -> requests.Response:
    if not otp_secret:
        raise RuntimeError(
            "Confluence image download requires Mobile Authenticator. "
            "Configure CONFLUENCE_OTP_SECRET."
        )

    otp_response = session.post(
        response.url,
        data={
            "validate_otp": pyotp.TOTP(otp_secret).now(),
            "Validate": "X\u00e1c nh\u1eadn m\u00e3",
        },
        headers={
            "Referer": response.url,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        allow_redirects=True,
        timeout=30,
    )
    otp_response.raise_for_status()
    if _is_confluence_otp_response(otp_response):
        raise RuntimeError("Confluence rejected the generated TOTP code.")
    return otp_response


def _authenticate_confluence_image_session(
    session: requests.Session,
    base_url: str,
    confluence_config: Dict[str, Any],
    destination: str,
) -> None:
    username, password, otp_secret = _require_confluence_image_web_credentials(confluence_config)
    response = session.post(
        _resolve_confluence_url(base_url, "/dologin.action"),
        data={
            "os_username": username,
            "os_password": password,
            "os_cookie": "true",
            "os_destination": destination,
            "login": "Log in",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        allow_redirects=True,
        timeout=30,
    )
    response.raise_for_status()
    if _is_confluence_login_response(response):
        raise RuntimeError("Confluence web login failed for image download.")
    if _is_confluence_otp_response(response):
        _submit_confluence_image_totp(session, response, otp_secret)


def _download_confluence_html_image(
    pat_session: requests.Session,
    web_session: requests.Session,
    web_auth_state: Dict[str, bool],
    base_url: str,
    confluence_config: Dict[str, Any],
    image_url: str,
) -> requests.Response:
    response = pat_session.get(image_url, allow_redirects=True, timeout=30, verify=False)
    needs_web_auth = (
        response.status_code in {401, 403}
        or _is_confluence_login_response(response)
        or _is_confluence_otp_response(response)
    )

    if not needs_web_auth:
        response.raise_for_status()
        return response

    destination = _confluence_destination_from_url(image_url)
    if not web_auth_state.get("authenticated"):
        _authenticate_confluence_image_session(
            web_session,
            base_url,
            confluence_config,
            destination,
        )
        web_auth_state["authenticated"] = True

    response = web_session.get(image_url, allow_redirects=True, timeout=30, verify=False)
    if (
        response.status_code in {401, 403}
        or _is_confluence_login_response(response)
        or _is_confluence_otp_response(response)
    ):
        web_auth_state["authenticated"] = False
        _authenticate_confluence_image_session(
            web_session,
            base_url,
            confluence_config,
            destination,
        )
        web_auth_state["authenticated"] = True
        response = web_session.get(image_url, allow_redirects=True, timeout=30, verify=False)

    response.raise_for_status()
    if _is_confluence_login_response(response) or _is_confluence_otp_response(response):
        raise RuntimeError("Confluence web authentication did not grant access to the image.")
    return response


def _image_response_to_data_uri(response: requests.Response, resource_url: str) -> str:
    content_type = str(response.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not content_type:
        path = urlparse(resource_url).path.lower()
        if path.endswith(".png"):
            content_type = "image/png"
        elif path.endswith((".jpg", ".jpeg")):
            content_type = "image/jpeg"
        elif path.endswith(".gif"):
            content_type = "image/gif"
        elif path.endswith(".webp"):
            content_type = "image/webp"
        elif path.endswith(".svg"):
            content_type = "image/svg+xml"

    if not content_type.startswith("image/"):
        raise ValueError(f"Resource is not an image: {content_type or 'unknown content type'}")

    encoded = base64.b64encode(response.content).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def _inline_confluence_html_images(
    html_content: str,
    confluence_config: Dict[str, Any],
    page_id: str | None = None,
    storage_html: str | None = None,
    confluence: Any | None = None,
) -> str:
    """Replace Confluence image URLs in HTML with base64 data URIs."""
    if not html_content or not html_content.strip():
        return html_content

    base_url = _normalize_confluence_base_url((confluence_config or {}).get("url"))
    if not base_url:
        logger.warning("Skip HTML image base64 conversion because Confluence base URL is empty")
        return html_content

    soup = BeautifulSoup(html_content, "html.parser")
    pat_session = _build_confluence_download_session(confluence_config or {})
    web_session = requests.Session()
    web_auth_state = {"authenticated": False}
    attachment_download_map = {}
    if page_id and confluence is not None:
        attachment_download_map = _build_confluence_attachment_download_map(
            confluence=confluence,
            page_id=str(page_id),
            soup=soup,
            storage_html=storage_html,
        )
    inlined_count = 0
    failed_count = 0

    for image in soup.find_all("img"):
        source_attr = ""
        source_value = ""
        image_candidate_names = set()

        for attr_name in ("data-image-src", "data-src", "src"):
            attr_value = str(image.get(attr_name) or "").strip()
            if not attr_value or attr_value.startswith("data:"):
                continue
            image_candidate_names.update(_candidate_confluence_attachment_names(attr_value))
            source_attr = attr_name
            source_value = attr_value
            break

        alias = str(image.get("data-linked-resource-default-alias") or "").strip()
        if alias:
            image_candidate_names.add(_normalize_confluence_attachment_name(alias))

        if not source_value:
            continue

        attachment_download_path = next(
            (
                attachment_download_map[name]
                for name in image_candidate_names
                if name in attachment_download_map
            ),
            "",
        )
        image_url = _resolve_html_resource_url(base_url, attachment_download_path or source_value)
        if not image_url:
            continue

        try:
            response = _download_confluence_html_image(
                pat_session,
                web_session,
                web_auth_state,
                base_url,
                confluence_config or {},
                image_url,
            )
            data_uri = _image_response_to_data_uri(response, image_url)
            image["data-image-id"] = hashlib.sha256(response.content).hexdigest()
            image[source_attr] = data_uri
            image["src"] = data_uri
            inlined_count += 1
        except Exception as exc:
            failed_count += 1
            logger.warning(
                "Could not inline Confluence image for HTML upload. url=%s error=%s",
                image_url,
                exc,
            )

    logger.info(
        "Confluence HTML image base64 conversion completed: inlined=%s failed=%s",
        inlined_count,
        failed_count,
    )
    return str(soup)


def _fetch_confluence_page_html(confluence_config: Dict[str, Any], page_id: str) -> Dict[str, str]:
    """Fetch one Confluence page as export_view HTML."""
    from confluence_workflow.functions.confluence_processor import _get_confluence_client

    normalized_page_id = str(page_id or "").strip()
    if not normalized_page_id:
        raise ValueError("page_id is required.")

    confluence = _get_confluence_client(confluence_config or {})
    page = confluence.get_page_by_id(
        normalized_page_id,
        expand="body.export_view,body.storage",
    )

    title = unquote(str(page.get("title") or normalized_page_id))
    export_html = (
        page.get("body", {})
        .get("export_view", {})
        .get("value", "")
    )
    storage_html = (
        page.get("body", {})
        .get("storage", {})
        .get("value", "")
    )

    if not export_html:
        export_html = storage_html

    html = _build_confluence_html_document(export_html, title)
    html = _inline_confluence_html_images(
        html,
        confluence_config or {},
        page_id=normalized_page_id,
        storage_html=storage_html,
        confluence=confluence,
    )

    return {
        "title": title,
        "html": html,
    }


def _normalize_confluence_base_url(url: str | None) -> str:
    raw_url = (url or "").strip()
    if not raw_url:
        return ""

    parsed = urlparse(raw_url)
    if not parsed.scheme or not parsed.netloc:
        return raw_url

    normalized_path = "/wiki" if (parsed.path or "").rstrip("/").startswith("/wiki") else ""
    return f"{parsed.scheme}://{parsed.netloc}{normalized_path}"


def _resolve_confluence_url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", str(path or "").lstrip("/"))


def _is_confluence_html_response(response: requests.Response) -> bool:
    return "html" in (response.headers.get("Content-Type") or "").lower()


def _is_confluence_otp_response(response: requests.Response) -> bool:
    return _is_confluence_html_response(response) and 'id="otp-validate-form"' in response.text


def _is_confluence_login_response(response: requests.Response) -> bool:
    return _is_confluence_html_response(response) and 'action="/dologin.action"' in response.text


async def download_page_from_confluence(
    confluence_config: Dict[str, Any],
    input_page_id: str,
    input_bot_id: str | None = None,
    input_title: str | None = None,
    input_version: int | None = None,
    input_content: str | None = None,
    input_source_link: str | None = None,
    input_updated_by: str | None = None,
    input_sync_status: str | None = None,
) -> Dict[str, Any]:
    """Download one Confluence page as HTML to a temp file."""
    page_info = {
        "page_id": input_page_id,
        "bot_id": input_bot_id,
        "title": input_title,
        "version": input_version,
        "content": input_content,
        "source_link": input_source_link,
        "updated_by": input_updated_by,
        "sync_status": input_sync_status,
    }

    try:
        html_result = await asyncio.to_thread(
            _fetch_confluence_page_html,
            confluence_config or {},
            str(input_page_id),
        )
        html_file_path = await asyncio.to_thread(
            _write_html_to_temp_file,
            html_result["html"],
            str(input_page_id),
        )

        logger.info("Prepared Confluence page_id=%s HTML temp file", input_page_id)
        return {
            **page_info,
            "title": html_result["title"],
            "file_path": html_file_path,
            "has_downloaded_page": True,
            "has_download_error": False,
            "download_error_message": "",
        }
    except Exception as exc:
        logger.exception("Failed to download Confluence page_id=%s", input_page_id)
        return {
            **page_info,
            "file_path": None,
            "has_downloaded_page": False,
            "has_download_error": True,
            "download_error_message": str(exc),
        }


async def build_chunk_dispatch_payload(
    document: dict,
    bot_id: str,
    version: int | str,
    file_path: str,
) -> Dict[str, Any]:
    """Build the S3 upload and Kafka request for one Confluence HTML file."""
    document_id = str(document["_id"])
    normalized_version = str(version)
    file_stem = normalize_s3_file_stem(document["doc_name"])
    bucket = "ai-text-raw"
    prefix = "chatbot_beegen_portal"
    object_key = f"{prefix}/{bot_id}/{document_id}/{file_stem}.html"

    return {
        "upload_file_path": file_path,
        "upload_bucket": bucket,
        "upload_object_key": object_key,
        "upload_content_type": "text/html; charset=utf-8",
        "chunk_job_item": {
            "document_id": document_id,
            "content_path": f"s3://{bucket}/{object_key}",
            "sync_version": normalized_version,
            "dispatch_status": "READY",
            "error_detail": "",
        },
    }


async def finalize_chunk_job_ready_item(
    prepared_item: dict,
    document_update_status: str,
) -> Dict[str, Any]:
    """Expose a READY item only after its document was marked processing."""
    if document_update_status != "success":
        raise RuntimeError("Could not mark document as processing before Chunk dispatch")
    return {"chunk_job_item": prepared_item}


async def build_chunk_job_error_item(
    document: dict,
    version: int | str,
    error_message: str,
    document_update_status: str,
) -> Dict[str, Any]:
    """Represent a Producer-side page failure in the aggregate Chunk job."""
    if document_update_status != "success":
        raise RuntimeError("Could not persist Producer-side document error")
    return {
        "chunk_job_item": {
            "document_id": str(document["_id"]),
            "content_path": None,
            "sync_version": str(version),
            "dispatch_status": "ERROR",
            "error_detail": error_message,
        }
    }


async def build_chunk_job_message(
    current_job_id: str,
    current_bot_id: str,
    page_results: list,
) -> Dict[str, Any]:
    """Build one Kafka message containing every page result from the Producer loop."""
    items = [
        result["chunk_job_item"]
        for result in (page_results or [])
        if isinstance(result, dict) and isinstance(result.get("chunk_job_item"), dict)
    ]
    if not items:
        raise RuntimeError("Chunk job contains no page results")
    if len(items) != len(page_results):
        raise RuntimeError(
            f"Chunk job is incomplete: prepared={len(items)} expected={len(page_results)}"
        )
    return {
        "chunk_job_key": str(current_bot_id),
        "chunk_job_value": {
            "message_type": "CHUNKING",
            "system": "CONFLUENCE",
            "job_id": str(current_job_id),
            "data": items,
        },
    }


async def validate_chunk_job_produced(produce_status: str) -> Dict[str, bool]:
    """Prevent local cleanup and finalization when Kafka produce failed."""
    if produce_status != "success":
        raise RuntimeError("Could not publish aggregate CHUNKING_JOB")
    return {"chunk_job_produced": True}


async def build_chunk_dispatch_document_update() -> Dict[str, Any]:
    """Mark a document as waiting for asynchronous chunk processing."""
    return {
        "update": {
            "$set": {
                "status": "PROCESS",
                "sync_status": "processing",
            },
            "$unset": {"error_message": ""},
        }
    }


async def cleanup_page_batch_temp_files(
    pages_for_chunk_processing: list,
    chunk_job_produced: bool = True,
) -> Dict[str, Any]:
    """Delete HTML and decoded-image temp files after the page loop finishes."""
    if chunk_job_produced is not True:
        raise RuntimeError("Cannot clean temp files before CHUNKING_JOB is published")
    deleted_count = 0
    html_download_dir = _confluence_html_download_dir()
    images_root = os.path.join(html_download_dir, "images")

    for page in pages_for_chunk_processing:
        page_id = str(page["page_id"])
        file_path = os.path.abspath(
            os.path.join(html_download_dir, f"{page_id}.html")
        )
        image_dir = os.path.abspath(os.path.join(images_root, page_id))

        try:
            if os.path.commonpath([file_path, html_download_dir]) == html_download_dir:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    deleted_count += 1

            if os.path.commonpath([image_dir, images_root]) == images_root:
                if os.path.isdir(image_dir):
                    shutil.rmtree(image_dir)
                    deleted_count += 1
        except OSError as exc:
            logger.warning(
                "Could not clean Confluence page temp files. page_id=%s error=%s",
                page_id,
                exc,
            )

    logger.info(
        "Cleaned Confluence page batch temp files: pages=%s deleted=%s",
        len(pages_for_chunk_processing),
        deleted_count,
    )
    return {"deleted_temp_paths": deleted_count}


async def build_page_document_query(bot_id: str, page_id: str) -> Dict[str, Any]:
    """Build Mongo query to find the active Confluence document for one page."""
    return {
        "query": {
            "bot_id": bot_id,
            "source": "confluence",
            "external_id": str(page_id),
            "deleted": {"$ne": True},
        }
    }


async def build_sync_error_document_update(error_message: str | None) -> Dict[str, Any]:
    """Mark the overall document sync as failed without changing Chunk API status."""
    return {
        "update": {
            "$set": {
                "error_message": error_message or "Document sync failed",
                "sync_status": "error",
            }
        }
    }

