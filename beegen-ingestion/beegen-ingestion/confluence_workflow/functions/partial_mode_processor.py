from typing import Dict, List, Any, Optional
from uuid import uuid4
from confluence_workflow.functions.workflow_helpers import normalize_doc_name, normalize_page_ids, normalize_utc_datetime
from confluence_workflow.utils.logger import get_logger
from datetime import datetime, timezone

logger = get_logger('partial')

async def _build_unchanged_status_batches(page_ids: list, bot_id: str) -> dict:
    """Restore completed Mongo status for unchanged PARTIAL pages."""
    batch_data = [
        {
            "mongo_filter": {
                "bot_id": bot_id,
                "source": "confluence",
                "external_id": str(page_id),
            },
            "mongo_update": {
                "$set": {
                    "status": "DONE",
                    "sync_status": "done",
                },
                "$unset": {"error_message": ""},
            },
        }
        for page_id in (page_ids or [])
    ]
    logger.info("Built status updates for %s unchanged PARTIAL pages", len(batch_data))
    return {"batch_data": batch_data}


async def _build_metadata_completed_status_batches(pages: list, bot_id: str) -> dict:
    """Restore completed Mongo status after metadata-only updates."""
    page_ids = list(dict.fromkeys(str(page["id"]) for page in (pages or []) if isinstance(page, dict) and page.get("id") is not None))
    batch_data = [
        {
            "mongo_filter": {
                "bot_id": bot_id,
                "source": "confluence",
                "external_id": page_id,
            },
            "mongo_update": {
                "$set": {"status": "DONE", "sync_status": "done"},
                "$unset": {"error_message": ""},
            },
        }
        for page_id in page_ids
    ]
    logger.info("Built status updates for %s metadata-only PARTIAL pages", len(batch_data))
    return {"batch_data": batch_data}


async def _build_move_completed_status_batches(
    successful_page_ids: list,
    move_only_page_ids: list,
    bot_id: str,
) -> dict:
    """Restore completed Mongo status after successful move-only updates."""
    move_only_ids = {str(page_id) for page_id in (move_only_page_ids or [])}
    completed_page_ids = list(dict.fromkeys(str(page_id) for page_id in (successful_page_ids or []) if str(page_id) in move_only_ids))
    batch_data = [
        {
            "mongo_filter": {
                "bot_id": bot_id,
                "source": "confluence",
                "external_id": page_id,
            },
            "mongo_update": {
                "$set": {"status": "DONE", "sync_status": "done"},
                "$unset": {"error_message": ""},
            },
        }
        for page_id in completed_page_ids
    ]
    logger.info("Built status updates for %s move-only PARTIAL pages", len(batch_data))
    return {"batch_data": batch_data}


def _process_inserts(
    pages: list,
    bot_id: str,
) -> dict:
    """Insert new pages to PostgreSQL and MongoDB."""
    logger.info(f"Processing {len(pages)} new pages")
    
    batch_data = []
    
    for page in pages or []:
        p_id = str(page.get("id"))
        p_title = page.get("title", "")
        p_content = page.get("body", {}).get("storage", {}).get("value", "")
        p_version = page.get("version", {}).get("number", 1)
        ancestors = page.get("ancestors", [])
        webui_link = page.get("_links", {}).get("webui", "")
        p_source_link = f"{webui_link}"
        p_parent_id = ancestors[-1]["id"] if ancestors else None
        p_parent_id = str(p_parent_id) if p_parent_id is not None else None
        p_create_by = page.get("history", {}).get("createdBy", {}).get("displayName", "Unknown")
        p_create_at = normalize_utc_datetime(page.get("history", {}).get("createdDate"))
        p_update_by = page.get("version", {}).get("by", {}).get("username", p_create_by)
        p_update_at_raw = page.get("version", {}).get("when")
        p_update_at = normalize_utc_datetime(p_update_at_raw) if p_update_at_raw else p_create_at

        batch_data.append({
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
                bot_id, p_id, p_title, p_content, p_content, p_version, p_source_link,
                p_parent_id, p_create_by, p_create_at, p_update_by, p_update_at, "CONFLUENCE"
            ),
            "mongo_query": {"bot_id": bot_id, "external_id": p_id},
            "mongo_update":{
                '$setOnInsert': {
                    "_id": str(uuid4()),
                    "level": 0,
                    "parent_id": None,
                },
                '$set': {
                    "bot_id": bot_id,
                    "doc_name": p_title,
                    "doc_name_normalize": normalize_doc_name(p_title),
                    "created_by": p_create_by,
                    "created_at": p_create_at,
                    "sync_status": "processing",
                    "sync_at": datetime.now(timezone.utc),
                    "sync_mode": True,
                    "source": "confluence",
                    "source_type": "confluence",
                    "source_link": p_source_link,
                    "external_parent_id": p_parent_id,
                    "external_id": p_id,
                    "sync_version": str(p_version),
                    "updated_by": p_update_by,
                    "updated_at": p_update_at,
                },
                "$unset": {"status": ""},
            },
            "mongo_upsert": True,
        })

    return {
        "batch_data": batch_data,
        "inserted_count": len(batch_data),
    }


def _process_updates(
    pages: list,
    bot_id: str,
) -> dict:
    """Update existing pages in PostgreSQL and MongoDB."""
    logger.info(f"Processing {len(pages)} updated pages")
    
    batch_data = []
    
    for page in pages or []:
        p_id = str(page.get("id"))
        p_title = page.get("title", "")
        p_content = page.get("body", {}).get("storage", {}).get("value", "")
        p_version = page.get("version", {}).get("number", 1)
        ancestors = page.get("ancestors", [])
        webui_link = page.get("_links", {}).get("webui", "")
        p_source_link = f"{webui_link}"
        p_parent_id = ancestors[-1]["id"] if ancestors else None
        p_parent_id = str(p_parent_id) if p_parent_id is not None else None
        p_create_by = page.get("history", {}).get("createdBy", {}).get("displayName", "Unknown")
        p_create_at = normalize_utc_datetime(page.get("history", {}).get("createdDate"))
        p_update_by = page.get("version", {}).get("by", {}).get("username", p_create_by)
        p_update_at_raw = page.get("version", {}).get("when")
        p_update_at = normalize_utc_datetime(p_update_at_raw) if p_update_at_raw else p_create_at

        batch_data.append({
            "sql_query": "CALL knowledge_base.sp_sync_confluence_page(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            "sql_params": (
                bot_id, p_id, p_title, p_content, p_source_link, p_version,
                p_parent_id, p_create_by, p_create_at, p_update_by, p_update_at
            ),
            "mongo_query": {"bot_id": bot_id, "external_id": p_id},
            "mongo_update": {
                "$setOnInsert": {
                    "_id": str(uuid4()),
                    "level": 0,
                    "parent_id": None,
                },
                "$set": {
                    "bot_id": bot_id,
                    "doc_name": p_title,
                    "doc_name_normalize": normalize_doc_name(p_title),
                    "created_by": p_create_by,
                    "created_at": p_create_at,
                    "sync_status": "processing",
                    "sync_at": datetime.now(timezone.utc),
                    "source": "confluence",
                    "source_type": "confluence",
                    "source_link": p_source_link,
                    "external_parent_id": p_parent_id,
                    "external_id": p_id,
                    "sync_version": str(p_version),
                    "updated_by": p_update_by,
                    "updated_at": p_update_at,
                },
                "$unset": {"status": ""},
            },
            "mongo_upsert": True,
        })

    return {
        "batch_data": batch_data,
        "updated_count": len(batch_data),
    }

def _build_move_batches(
    to_move: list,
    fetched_pages: list,
    active_pages: list,
    bot_documents: list,
    bot_id: str,
) -> dict:
    """
    Build move batches matching legacy batch_move_documents().

    - active pages: delete when moved outside the bot tree, otherwise update external_parent_id
    - inactive pages: keep their sync_mode unchanged and only update parent metadata
    """
    active_set = normalize_page_ids(active_pages)
    bot_doc_map = {str(doc.get("external_id")): doc for doc in (bot_documents or []) if isinstance(doc, dict) and (doc.get("external_id") is not None)}
    bot_doc_ids = set(bot_doc_map.keys())
    active_move_batch = []
    inactive_move_batch = []
    # Legacy PARTIAL flow only updates Mongo metadata for moves; PostgreSQL parent_id
    # is not rewritten here unless the page is re-processed as UPDATED.
    sql_move_batch = []
    move_deleted_page_ids = []
    successful_move_page_ids = []

    for move_item in to_move or []:
        if not isinstance(move_item, dict):
            continue

        page_id = str(move_item.get("page_id")) if move_item.get("page_id") is not None else None
        if not page_id:
            continue

        new_parent_raw = move_item.get("new_parent_id")
        new_parent_id = str(new_parent_raw) if new_parent_raw not in (None, "") else None
        current_doc = bot_doc_map.get(page_id)
        parent_doc = bot_doc_map.get(new_parent_id) if new_parent_id else None
        expected_parent_doc_id = parent_doc.get("_id") if isinstance(parent_doc, dict) else None

        if page_id in active_set:
            current_level = current_doc.get("level", 1) if current_doc else 1
            current_parent_raw = (
                current_doc.get("external_parent_id")
                if current_doc
                else None
            )
            current_parent_id = str(current_parent_raw) if current_parent_raw not in (None, "") else None
            current_sync_mode = current_doc.get("sync_mode") if current_doc else None
            current_parent_doc_id = current_doc.get("parent_id") if current_doc else None

            if (
                current_sync_mode is True
                and current_parent_id == new_parent_id
                and current_parent_doc_id == expected_parent_doc_id
            ):
                successful_move_page_ids.append(page_id)
                continue

            parent_exists = expected_parent_doc_id is not None if new_parent_id else False
            should_delete = current_level == 0 or not parent_exists or new_parent_id is None
            if should_delete:
                move_deleted_page_ids.append(page_id)
                continue

            active_move_batch.append(
                {
                    "mongo_filter": {
                        "bot_id": bot_id,
                        "external_id": page_id,
                    },
                    "mongo_update": {
                        "$set": {
                            "external_parent_id": new_parent_id,
                            "parent_id": expected_parent_doc_id,
                        }
                    },
                }
            )
            successful_move_page_ids.append(page_id)
            continue

        if not current_doc:
            continue

        inactive_move_batch.append(
            {
                "mongo_filter": {
                    "bot_id": bot_id,
                    "external_id": page_id,
                },
                "mongo_update": {
                    "$set": {
                        "external_parent_id": new_parent_id,
                        "parent_id": expected_parent_doc_id,
                    },
                    "$unset": {
                        "deleted": "",
                    },
                },
                "mongo_upsert": False,
            }
        )
        successful_move_page_ids.append(page_id)

    return {
        "active_move_batch": active_move_batch,
        "inactive_move_batch": inactive_move_batch,
        "sql_move_batch": sql_move_batch,
        "moved_count": len(active_move_batch) + len(inactive_move_batch),
        "move_deleted_page_ids": move_deleted_page_ids,
        "successful_move_page_ids": list(dict.fromkeys(successful_move_page_ids)),
    }

def _build_updated_pages(
    insert_pages: list,
    update_pages: list,
    metadata_update_pages: list,
    move_items: list,
    fetched_pages: list,
) -> dict:
    """Build updated pages list for downstream chunk processing."""
    updated_pages = []
    inserted_ids = {str(page.get("id")) for page in (insert_pages or []) if isinstance(page, dict) and page.get("id")}
    updated_ids = {str(page.get("id")) for page in (update_pages or []) if isinstance(page, dict) and page.get("id")}
    metadata_updated_ids = {str(page.get("id")) for page in (metadata_update_pages or []) if isinstance(page, dict) and page.get("id")}
    moved_ids = {
        str(move_item.get("page_id"))
        for move_item in (move_items or [])
        if isinstance(move_item, dict) and move_item.get("page_id") is not None
    }
    page_map = {}
    for page in fetched_pages or []:
        if not isinstance(page, dict) or page.get("id") is None:
            continue
        page_map[str(page.get("id"))] = page

    for page_id, page in page_map.items():
        if page_id in inserted_ids:
            sync_status = "NEW"
        elif page_id in updated_ids:
            sync_status = "UPDATED"
        elif page_id in metadata_updated_ids:
            sync_status = "METADATA_UPDATED"
        else:
            sync_status = "SYNCED"

        updated_pages.append(
            {
                "page_id": page_id,
                "title": page.get("title", ""),
                "version": page.get("version", {}).get("number", 0),
                "content": page.get("body", {}).get("storage", {}).get("value", ""),
                "source_link": page.get("_links", {}).get("webui", ""),
                "updated_by": page.get("version", {}).get("by", {}).get("username", "Unknown"),
                "sync_status": sync_status,
            }
        )

    logger.info(
        "Built updated_pages list for PARTIAL: %s new, %s updated, %s moved_as_synced, total=%s",
        len(inserted_ids),
        len(updated_ids),
        len(moved_ids),
        len(updated_pages),
    )
    return {"updated_pages": updated_pages}


async def build_partial_error_retry_query(bot_id: str, page_ids: list) -> dict:
    """Build the Mongo query for requested PARTIAL pages whose last chunk failed."""
    return {
        "query": {
            "bot_id": bot_id,
            "source": "confluence",
            "external_id": {"$in": list(normalize_page_ids(page_ids))},
            "sync_status": "error",
            "deleted": {"$ne": True},
        }
    }


async def _compare_pages(
    fetched_pages: list,
    existing_pages: list,
    error_retry_documents: list,
) -> dict:
    """Compare pages for PARTIAL mode."""
    logger.info("Comparing fetched pages with existing pages")
    
    # Build maps for quick lookup
    existing_map = {str(p['page_id']): p for p in (existing_pages or [])}
    error_retry_page_ids = {
        str(document["external_id"])
        for document in (error_retry_documents or [])
        if document.get("external_id") is not None
    }
    fetched_map = {}
    for page in fetched_pages or []:
        if not isinstance(page, dict) or page.get("id") is None:
            continue
        fetched_map[str(page.get("id"))] = page
    
    to_insert = []
    to_update = []
    to_metadata_update = []
    to_move = []
    move_only_page_ids = []
    pages_no_change = []
    
    for page_id, page in fetched_map.items():
        existing = existing_map.get(page_id)
        
        if not existing:
            # New page
            to_insert.append(page)
        else:
            # Existing page - check for changes
            pg_parent_id = existing.get('parent_id')
            ancestors = page.get('ancestors', [])
            conf_parent_id = ancestors[-1]['id'] if ancestors else None
            
            # Check if moved
            page_moved = pg_parent_id != conf_parent_id
            if page_moved:
                to_move.append({
                    'page_id': page_id,
                    'new_parent_id': conf_parent_id
                })
            
            # Check if updated (legacy PARTIAL compares every fetched existing page)
            pg_hash = existing.get('content_hash')
            conf_content = page.get('body', {}).get('storage', {}).get('value', '')
            
            from confluence_workflow.functions.workflow_helpers import compute_content_hash
            conf_hash = compute_content_hash(conf_content)
            
            if page_id in error_retry_page_ids or conf_hash != pg_hash:
                to_update.append(page)
            elif existing.get('title') != page.get('title'):
                to_metadata_update.append(page)
            elif page_moved:
                move_only_page_ids.append(page_id)
            else:
                pages_no_change.append(page_id)
    
    logger.info(
        f"Comparison result: {len(to_insert)} new, "
        f"{len(to_update)} content-updated, {len(to_metadata_update)} metadata-updated, "
        f"{len(to_move)} moved, "
        f"{len(pages_no_change)} unchanged"
    )
    
    return {
        "to_insert": to_insert,
        "to_update": to_update,
        "to_metadata_update": to_metadata_update,
        "to_move": to_move,
        "move_only_page_ids": move_only_page_ids,
        "pages_no_change": pages_no_change
    }

async def _filter_deleted_page_ids(not_found: list, active_pages: list) -> dict:
    """Filter not-found pages to active pages only."""
    active_set = normalize_page_ids(active_pages)
    deleted_page_ids = [
        str(page_id)
        for page_id in (not_found or [])
        if str(page_id) in active_set
    ]

    logger.info(
        "Filtered deleted pages in PARTIAL mode: not_found=%s, active_deleted=%s",
        len(not_found or []),
        len(deleted_page_ids),
    )
    return {"deleted_page_ids": deleted_page_ids, "deleted_count": len(deleted_page_ids)}

async def _fetch_specific_pages(page_ids: list, confluence_config: dict, limit: int = 0) -> dict:
    """Fetch specific pages by IDs from Confluence."""
    from confluence_workflow.functions.confluence_processor import (
        _get_confluence_client,
        is_confluence_not_found_error,
    )
    
    confluence_config = confluence_config or {}
    normalized_page_ids = [str(page_id) for page_id in (page_ids or [])]
    if isinstance(limit, int) and limit > 0:
        normalized_page_ids = normalized_page_ids[:limit]

    logger.info(f"Fetching {len(normalized_page_ids)} specific pages")
    
    confluence = _get_confluence_client(confluence_config or {})
    
    fetched_pages = []
    not_found = []
    fetch_errors = []
    
    for page_id in normalized_page_ids:
        try:
            page = confluence.get_page_by_id(
                page_id=page_id,
                expand='body.storage,version,ancestors,history.lastUpdated'
            )
            if page:
                fetched_pages.append(page)
                logger.debug(f"Fetched page: {page_id} - {page.get('title')}")
            else:
                not_found.append(page_id)
                logger.warning(f"Page not found: {page_id}")
        except Exception as e:
            if is_confluence_not_found_error(e):
                logger.warning("Confluence page not found: page_id=%s", page_id)
                not_found.append(page_id)
            else:
                logger.error("Failed to fetch page %s without deleting it: %s", page_id, e)
                fetch_errors.append(page_id)
    
    return {
        "fetched_pages": fetched_pages,
        "not_found": not_found,
        "fetch_errors": fetch_errors,
    }


async def _build_existing_pages_sql_params(bot_id: str, page_ids: list) -> dict:
    """Build positional SQL params for existing pages query."""
    normalized_page_ids = [str(page_id) for page_id in (page_ids or [])]
    return {"params": (bot_id, normalized_page_ids)}
