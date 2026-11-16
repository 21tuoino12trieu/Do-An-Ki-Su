from datetime import datetime, timezone
import asyncio
from typing import Any
from uuid import uuid4

from confluence_workflow.functions.workflow_helpers import normalize_doc_name, normalize_utc_datetime
from confluence_workflow.utils.logger import get_logger

logger = get_logger("first_mode_processor")


async def _classify_first_mode_roots(
    active_root_ids: list,
    existing_documents: list,
    bot_id: str,
) -> dict:
    """Classify selected root trees into add, keep, and delete groups."""
    normalized_active_root_ids = list(dict.fromkeys(
        str(page_id)
        for page_id in (active_root_ids or [])
        if page_id is not None
    ))
    active_root_id_set = set(normalized_active_root_ids)

    documents_by_page_id = {
        str(document["external_id"]): document
        for document in (existing_documents or [])
        if isinstance(document, dict) and document.get("external_id") is not None
    }
    all_root_ids = {
        page_id
        for page_id, document in documents_by_page_id.items()
        if document.get("level") == 0
    }
    existing_active_root_ids = {
        page_id
        for page_id in all_root_ids
        if documents_by_page_id[page_id].get("deleted") is not True
    }

    new_root_ids = [
        page_id
        for page_id in normalized_active_root_ids
        if page_id not in existing_active_root_ids
    ]
    kept_root_ids = [
        page_id
        for page_id in normalized_active_root_ids
        if page_id in existing_active_root_ids
    ]
    removed_root_ids = all_root_ids - active_root_id_set

    children_by_parent_id: dict[str, list[str]] = {}
    for page_id, document in documents_by_page_id.items():
        parent_id = document.get("external_parent_id")
        if parent_id is not None:
            children_by_parent_id.setdefault(str(parent_id), []).append(page_id)

    deleted_page_ids = []
    pending_page_ids = list(removed_root_ids)
    seen_page_ids = set()
    while pending_page_ids:
        page_id = pending_page_ids.pop()
        if page_id in seen_page_ids:
            continue
        seen_page_ids.add(page_id)
        deleted_page_ids.append(page_id)
        pending_page_ids.extend(children_by_parent_id.get(page_id, []))

    logger.info(
        "FIRST root selection: add=%s keep=%s delete_roots=%s delete_pages=%s",
        len(new_root_ids),
        len(kept_root_ids),
        len(removed_root_ids),
        len(deleted_page_ids),
    )
    return {
        "new_root_ids": new_root_ids,
        "kept_root_ids": kept_root_ids,
        "deleted_page_ids": deleted_page_ids,
        "deleted_document_query": {
            "bot_id": bot_id,
            "source": "confluence",
            "external_id": {"$in": deleted_page_ids},
        },
        "postgres_delete_params": (deleted_page_ids, bot_id),
    }


def _append_page(page: Any, all_pages: list) -> None:
    """Append a valid Confluence page, preserving legacy FIRST-mode duplicates."""
    if not isinstance(page, dict):
        return

    page_id = page.get("id")
    if page_id is None:
        return

    all_pages.append(page)


async def _fetch_confluence_pages_first_mode(
    parent_ids: list,
    confluence_config: dict,
    batch_size: int = 50,
) -> dict:
    """Fetch parent pages + all descendants for FIRST mode."""
    from confluence_workflow.functions import fetch_descendants_flat
    from confluence_workflow.functions.confluence_processor import _get_confluence_client

    normalized_parent_ids = [str(parent_id) for parent_id in (parent_ids or []) if parent_id is not None]

    logger.info(
        "FIRST mode fetch start: parent_ids=%s, batch_size=%s",
        len(normalized_parent_ids),
        batch_size,
    )
    if not normalized_parent_ids:
        return {"confluence_pages": [], "total_count": 0}

    progress = {"fetched": 0, "next_log": 100}
    fetch_semaphore = asyncio.Semaphore(4)

    async def fetch_root(root_index: int, parent_id: str) -> list:
        async with fetch_semaphore:
            confluence = _get_confluence_client(confluence_config or {})
            root_pages = []
            logger.info(
                "FIRST mode fetching root %s/%s: page_id=%s",
                root_index,
                len(normalized_parent_ids),
                parent_id,
            )

            parent_page = await asyncio.to_thread(
                confluence.get_page_by_id,
                page_id=parent_id,
                expand="body.storage,version,ancestors,history.lastUpdated",
            )
            _append_page(parent_page, root_pages)
            progress["fetched"] += 1

            descendants = await fetch_descendants_flat(
                confluence=confluence,
                parent_id=parent_id,
                batch_size=batch_size,
                progress=progress,
            )

            for page in descendants or []:
                _append_page(page, root_pages)

            logger.info(
                "FIRST mode completed root %s/%s: page_id=%s pages=%s fetched_total=%s",
                root_index,
                len(normalized_parent_ids),
                parent_id,
                len(root_pages),
                progress["fetched"],
            )
            return root_pages

    root_results = await asyncio.gather(
        *(
            fetch_root(root_index, parent_id)
            for root_index, parent_id in enumerate(normalized_parent_ids, start=1)
        )
    )
    all_pages = [page for root_pages in root_results for page in root_pages]

    logger.info("FIRST mode fetched total pages: %s", len(all_pages))
    return {"confluence_pages": all_pages, "total_count": len(all_pages)}


async def _process_inserts_first_mode(
    pages: list,
    bot_id: str,
    parent_page_ids: list | None = None,
) -> dict:
    """Build INSERT/UPSERT batch payload for FIRST mode."""
    logger.info("FIRST mode processing inserts for %s pages", len(pages or []))

    batch_data = []
    parent_page_index_map = {
        str(parent_id): index
        for index, parent_id in enumerate(parent_page_ids or [], start=1)
        if parent_id is not None
    }

    for page in pages or []:
        page_id = str(page.get("id"))
        title = page.get("title", "")
        content = page.get("body", {}).get("storage", {}).get("value", "")
        version_number = page.get("version", {}).get("number", 1)
        page_index = parent_page_index_map.get(page_id)
        ancestors = page.get("ancestors", [])
        parent_page_id = str(ancestors[-1].get("id")) if ancestors else None
        source_link = page.get("_links", {}).get("webui", "")
        created_by = page.get("history", {}).get("createdBy", {}).get("displayName", "Unknown")
        created_at = normalize_utc_datetime(page.get("history", {}).get("createdDate"))
        updated_by = page.get("version", {}).get("by", {}).get("username", created_by)
        updated_at_raw = page.get("version", {}).get("when")
        updated_at = normalize_utc_datetime(updated_at_raw) if updated_at_raw else created_at

        mongo_set = {
            "bot_id": bot_id,
            "doc_name": title,
            "doc_name_normalize": normalize_doc_name(title),
            "created_by": created_by,
            "created_at": created_at,
            "updated_by": updated_by,
            "updated_at": updated_at,
            "sync_version": str(version_number),
            "sync_status": "processing",
            "sync_at": datetime.now(timezone.utc),
            "sync_mode": True,
            "source_link": source_link,
            "source_type": "confluence",
            "source": "confluence",
            "external_parent_id": parent_page_id,
            "external_id": page_id,
        }
        if page_index is not None:
            mongo_set["index"] = page_index

        batch_data.append(
            {
                "sql_query": """
                    INSERT INTO knowledge_base.documents (
                        bot_id, page_id, title, content, content_hash, version_number, source_link,
                        parent_id, sync_status, create_by, create_at,
                        updated_by, updated_at, source_type
                    ) VALUES (
                        %s, %s, %s, %s, MD5(%s), %s, %s, %s, 'SYNCED',
                        %s, %s::TIMESTAMPTZ, %s, %s::TIMESTAMPTZ, %s
                    )
                    ON CONFLICT (bot_id, page_id)
                    DO UPDATE SET
                        title = EXCLUDED.title,
                        content = EXCLUDED.content,
                        content_hash = EXCLUDED.content_hash,
                        version_number = EXCLUDED.version_number,
                        source_link = EXCLUDED.source_link,
                        parent_id = EXCLUDED.parent_id,
                        sync_status = EXCLUDED.sync_status,
                        create_by = EXCLUDED.create_by,
                        create_at = EXCLUDED.create_at,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = EXCLUDED.updated_at,
                        is_deleted = FALSE,
                        source_type = EXCLUDED.source_type
                    RETURNING id
                """,
                "sql_params": (
                    bot_id,
                    page_id,
                    title,
                    content,
                    content,
                    version_number,
                    source_link,
                    parent_page_id,
                    created_by,
                    created_at,
                    updated_by,
                    updated_at,
                    "CONFLUENCE",
                ),
                "mongo_query": {"bot_id": bot_id, "external_id": page_id},
                "mongo_update": {
                    "$setOnInsert": {
                        "_id": str(uuid4()),
                        "level": 0,
                        "parent_id": None,
                    },
                    "$set": mongo_set,
                    "$unset": {
                        "deleted": "",
                        "status": "",
                    },
                },
                "mongo_upsert": True,
            }
        )

    return {"batch_data": batch_data}


async def _build_updated_pages_first_mode(confluence_pages: list) -> dict:
    """Build chunk-processing payload for pages in newly selected root trees."""
    updated_pages = []

    for page in confluence_pages or []:
        if not isinstance(page, dict):
            continue

        page_id = page.get("id")
        if page_id is None:
            continue

        normalized_page_id = str(page_id)
        updated_pages.append(
            {
                "page_id": normalized_page_id,
                "title": page.get("title", ""),
                "version": page.get("version", {}).get("number", 0),
                "content": page.get("body", {}).get("storage", {}).get("value", ""),
                "source_link": page.get("_links", {}).get("webui", ""),
                "updated_by": page.get("version", {}).get("by", {}).get("username", "Unknown"),
                "sync_status": "NEW",
            }
        )

    logger.info("FIRST mode built updated_pages: %s", len(updated_pages))
    return {"updated_pages": updated_pages}
