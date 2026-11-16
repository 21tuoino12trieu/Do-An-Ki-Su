import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from confluence_workflow.functions.workflow_helpers import normalize_doc_name, normalize_page_ids, normalize_utc_datetime
from confluence_workflow.utils.logger import get_logger

logger = get_logger("auto_mode_processor")


def _append_unique_page(page: Any, all_pages: list, seen_page_ids: set[str]) -> None:
    """Append page to result list once by page id."""
    if not isinstance(page, dict):
        return

    page_id = page.get("id")
    if page_id is None:
        return

    normalized_id = str(page_id)
    if normalized_id in seen_page_ids:
        return

    seen_page_ids.add(normalized_id)
    all_pages.append(page)


async def _extract_active_page_ids(active_pages: list[dict[str, Any]] | None) -> dict:
    """Extract active Confluence page IDs from MongoNode data rows."""
    docs = active_pages or []
    active_page_ids = []
    seen_ids = set()

    for doc in docs:
        if isinstance(doc, dict):
            page_id = doc.get("external_id")
        else:
            page_id = doc

        if page_id is None:
            continue

        if page_id in seen_ids:
            continue

        seen_ids.add(page_id)
        active_page_ids.append(page_id)

    logger.info("Extracted %s active page IDs", len(active_page_ids))
    return {
        "active_page_ids": active_page_ids,
        "has_active_pages": bool(active_page_ids),
    }


async def _fetch_confluence_pages(page_ids: list | None, confluence_config: dict | None, batch_size: int = 50) -> dict:
    """Fetch configured root pages and their descendants concurrently."""
    from confluence_workflow.functions import fetch_descendants_flat
    from confluence_workflow.functions.confluence_processor import _get_confluence_client

    parent_page_ids = [str(page_id) for page_id in (page_ids or []) if page_id is not None]

    logger.info(
        "AUTO mode fetch start: parent_ids=%s, batch_size=%s",
        len(parent_page_ids),
        batch_size,
    )
    if not parent_page_ids:
        return {
            "confluence_pages": [],
            "fetch_complete": True,
            "failed_root_ids": [],
        }

    progress = {"fetched": 0, "next_log": 100}
    fetch_semaphore = asyncio.Semaphore(4)

    async def fetch_root(root_index: int, parent_id: str) -> tuple[list, str | None]:
        async with fetch_semaphore:
            confluence = _get_confluence_client(confluence_config or {})
            root_pages = []
            logger.info(
                "AUTO mode fetching root %s/%s: page_id=%s",
                root_index,
                len(parent_page_ids),
                parent_id,
            )

            try:
                parent_page = await asyncio.to_thread(
                    confluence.get_page_by_id,
                    page_id=parent_id,
                    expand="body.storage,version,ancestors,history.lastUpdated",
                )
                if parent_page.get("status") == "current":
                    root_pages.append(parent_page)
                    progress["fetched"] += 1

                descendants = await fetch_descendants_flat(
                    confluence=confluence,
                    parent_id=parent_id,
                    batch_size=batch_size,
                    progress=progress,
                )
                root_pages.extend(descendants)
            except Exception as exc:
                logger.warning(
                    "AUTO mode failed to fetch root tree. page_id=%s error=%s",
                    parent_id,
                    exc,
                )
                return root_pages, parent_id

            logger.info(
                "AUTO mode completed root %s/%s: page_id=%s pages=%s fetched_total=%s",
                root_index,
                len(parent_page_ids),
                parent_id,
                len(root_pages),
                progress["fetched"],
            )
            return root_pages, None

    root_results = await asyncio.gather(
        *(
            fetch_root(root_index, parent_id)
            for root_index, parent_id in enumerate(parent_page_ids, start=1)
        )
    )

    all_pages = []
    seen_page_ids = set()
    failed_root_ids = []
    for root_pages, failed_root_id in root_results:
        if failed_root_id is not None:
            failed_root_ids.append(failed_root_id)
        for page in root_pages:
            _append_unique_page(page, all_pages, seen_page_ids)

    logger.info(
        "AUTO mode fetch completed: pages=%s failed_roots=%s",
        len(all_pages),
        len(failed_root_ids),
    )
    return {
        "confluence_pages": all_pages,
        "fetch_complete": not failed_root_ids,
        "failed_root_ids": failed_root_ids,
    }


async def _build_postgres_pages_sql_params(bot_id: str) -> dict:
    """Build positional SQL params for loading PostgreSQL pages in AUTO mode."""
    return {"params": (bot_id,)}


async def _compare_datasets(
    confluence_pages: list[dict[str, Any]] | None,
    postgres_pages: list[dict[str, Any]] | None,
    active_page_ids: list[str] | None,
    fetch_complete: bool,
) -> dict:
    """Compare Confluence and PostgreSQL datasets for AUTO mode."""
    from confluence_workflow.functions.workflow_helpers import compute_content_hash

    conf_pages = confluence_pages or []
    pg_pages = postgres_pages or []
    active_set = {str(page_id) for page_id in (active_page_ids or []) if page_id is not None}

    logger.info(
        "AUTO compare raw inputs: confluence_pages=%s, postgres_pages=%s, active_page_ids=%s",
        len(conf_pages),
        len(pg_pages),
        len(active_set),
    )

    if not active_set:
        logger.warning("No active page IDs found in MongoDB; skip AUTO comparison")
        return {
            "to_insert": [],
            "to_update": [],
            "to_metadata_update": [],
            "to_move": [],
            "to_delete": [],
            "pages_no_change": [],
        }

    pg_map = {}
    for row in pg_pages:
        if not isinstance(row, dict):
            continue
        page_id = row.get("page_id")
        if page_id is None:
            continue
        pg_map[str(page_id)] = row

    conf_map = {}
    for page in conf_pages:
        if not isinstance(page, dict):
            continue

        page_id = page.get("id")
        if page_id is None:
            continue

        normalized_page_id = str(page_id)
        ancestors = page.get("ancestors", [])
        parent_id = ancestors[-1].get("id") if ancestors else None
        normalized_parent_id = str(parent_id) if parent_id is not None else None

        conf_map[normalized_page_id] = {
            "title": page.get("title", ""),
            "content": page.get("body", {}).get("storage", {}).get("value", ""),
            "parent_id": normalized_parent_id,
            "page": page,
        }

    logger.info(
        "AUTO compare normalized inputs: confluence_pages=%s, postgres_pages=%s",
        len(conf_map),
        len(pg_map),
    )

    to_insert = []
    to_update = []
    to_metadata_update = []
    to_move = []
    to_delete = []
    # Legacy AUTO flow only retries unchanged pages that are already in error state.
    # Plain unchanged pages must not be forwarded to chunk requests.
    pages_no_change = []

    for page_id, conf_data in conf_map.items():
        pg_page = pg_map.get(page_id)

        if not pg_page:
            logger.info(
                "AUTO page classified NEW: page_id=%s, title=%r, reason=missing_from_postgres",
                page_id,
                conf_data["title"],
            )
            to_insert.append(conf_data["page"])
            continue

        pg_parent_id = pg_page.get("parent_id")
        normalized_pg_parent_id = str(pg_parent_id) if pg_parent_id is not None else None
        conf_parent_id = conf_data["parent_id"]

        if normalized_pg_parent_id != conf_parent_id:
            if page_id in active_set:
                logger.info(
                    "AUTO page classified MOVED: page_id=%s, postgres_parent_id=%s, "
                    "confluence_parent_id=%s",
                    page_id,
                    normalized_pg_parent_id,
                    conf_parent_id,
                )
                to_move.append({"page_id": page_id, "new_parent_id": conf_parent_id})
            else:
                logger.debug(
                    "AUTO page move ignored: page_id=%s, postgres_parent_id=%s, "
                    "confluence_parent_id=%s, reason=sync_mode_disabled",
                    page_id,
                    normalized_pg_parent_id,
                    conf_parent_id,
                )

        if page_id in active_set:
            pg_hash = pg_page.get("content_hash")
            conf_hash = compute_content_hash(conf_data["content"])
            pg_title = pg_page.get("title", "")
            hash_changed = conf_hash != pg_hash
            title_changed = pg_title != conf_data["title"]

            if hash_changed:
                logger.info(
                    "AUTO page classified UPDATED: page_id=%s, hash_changed=%s, "
                    "title_changed=%s, postgres_hash=%s, confluence_hash=%s, "
                    "postgres_title=%r, confluence_title=%r",
                    page_id,
                    hash_changed,
                    title_changed,
                    pg_hash,
                    conf_hash,
                    pg_title,
                    conf_data["title"],
                )
                to_update.append(conf_data["page"])
            elif title_changed:
                logger.info(
                    "AUTO page classified METADATA_UPDATED: page_id=%s, "
                    "postgres_title=%r, confluence_title=%r",
                    page_id,
                    pg_title,
                    conf_data["title"],
                )
                to_metadata_update.append(conf_data["page"])
            else:
                logger.debug("AUTO page unchanged: page_id=%s", page_id)
        else:
            logger.debug(
                "AUTO page skipped for content comparison: page_id=%s, reason=not_active",
                page_id,
            )

    if fetch_complete:
        for page_id in pg_map.keys():
            if page_id not in conf_map and page_id in active_set:
                logger.info(
                    "AUTO page classified DELETED: page_id=%s, reason=missing_from_confluence",
                    page_id,
                )
                to_delete.append(page_id)
    else:
        logger.warning("AUTO fetch was incomplete; deleted-page detection was skipped")

    logger.info(
        "Comparison result: %s new, %s content-updated, %s metadata-updated, %s moved, %s deleted",
        len(to_insert),
        len(to_update),
        len(to_metadata_update),
        len(to_move),
        len(to_delete),
    )

    return {
        "to_insert": to_insert,
        "to_update": to_update,
        "to_metadata_update": to_metadata_update,
        "to_move": to_move,
        "to_delete": to_delete,
        "pages_no_change": pages_no_change,
    }


async def _process_inserts(pages: list, bot_id: str) -> dict:
    """Build INSERT batch payload for SQLNode + MongoNode."""
    logger.info("Processing %s new pages", len(pages or []))

    batch_data = []

    for page in pages or []:
        p_id = str(page.get("id"))
        p_title = page.get("title", "")
        p_content = page.get("body", {}).get("storage", {}).get("value", "")
        p_version = page.get("version", {}).get("number", 1)
        ancestors = page.get("ancestors", [])
        p_parent_id = ancestors[-1].get("id") if ancestors else None
        p_parent_id = str(p_parent_id) if p_parent_id is not None else None

        webui_link = page.get("_links", {}).get("webui", "")
        p_source_link = f"{webui_link}"

        p_create_by = page.get("history", {}).get("createdBy", {}).get("displayName", "Unknown")
        p_create_at = normalize_utc_datetime(page.get("history", {}).get("createdDate"))
        p_update_by = page.get("version", {}).get("by", {}).get("username", p_create_by)
        p_update_at_raw = page.get("version", {}).get("when")
        p_update_at = normalize_utc_datetime(p_update_at_raw) if p_update_at_raw else p_create_at

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
                    p_id,
                    p_title,
                    p_content,
                    p_content,
                    p_version,
                    p_source_link,
                    p_parent_id,
                    p_create_by,
                    p_create_at,
                    p_update_by,
                    p_update_at,
                    "CONFLUENCE",
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
                        "updated_by": p_update_by,
                        "updated_at": p_update_at,
                        "sync_version": str(p_version),
                        "sync_status": "processing",
                        "sync_at": datetime.now(timezone.utc),
                        "sync_mode": True,
                        "source_link": p_source_link,
                        "source_type": "confluence",
                        "source": "confluence",
                        "external_parent_id": p_parent_id,
                        "external_id": p_id,
                    },
                    "$unset": {
                        "deleted": "",
                        "status": "",
                    },
                },
                "mongo_upsert": True,
            }
        )

    return {"batch_data": batch_data, "inserted_count": len(batch_data)}


async def _process_updates(pages: list, bot_id: str) -> dict:
    """Build UPDATE batch payload for SQLNode + MongoNode."""
    logger.info("Processing %s updated pages", len(pages or []))

    batch_data = []

    for page in pages or []:
        p_id = str(page.get("id"))
        p_title = page.get("title", "")
        p_content = page.get("body", {}).get("storage", {}).get("value", "")
        p_version = page.get("version", {}).get("number", 1)
        ancestors = page.get("ancestors", [])
        p_parent_id = ancestors[-1].get("id") if ancestors else None
        p_parent_id = str(p_parent_id) if p_parent_id is not None else None

        webui_link = page.get("_links", {}).get("webui", "")
        p_source_link = f"{webui_link}"

        p_create_by = page.get("history", {}).get("createdBy", {}).get("displayName", "Unknown")
        p_create_at = normalize_utc_datetime(page.get("history", {}).get("createdDate"))
        p_update_by = page.get("version", {}).get("by", {}).get("username", p_create_by)
        p_update_at_raw = page.get("version", {}).get("when")
        p_update_at = normalize_utc_datetime(p_update_at_raw) if p_update_at_raw else p_create_at

        batch_data.append(
            {
                "sql_query": "CALL knowledge_base.sp_sync_confluence_page(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                "sql_params": (
                    bot_id,
                    p_id,
                    p_title,
                    p_content,
                    p_source_link,
                    p_version,
                    p_parent_id,
                    p_create_by,
                    p_create_at,
                    p_update_by,
                    p_update_at,
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
                        "updated_by": p_update_by,
                        "updated_at": p_update_at,
                        "sync_version": str(p_version),
                        "sync_status": "processing",
                        "sync_at": datetime.now(timezone.utc),
                        "sync_mode": True,
                        "source_link": p_source_link,
                        "source_type": "confluence",
                        "source": "confluence",
                        "external_parent_id": p_parent_id,
                        "external_id": p_id,
                    },
                    "$unset": {
                        "deleted": "",
                        "status": "",
                    },
                },
                "mongo_upsert": True,
            }
        )

    return {"batch_data": batch_data, "updated_count": len(batch_data)}


async def _build_move_batches(
    to_move: list,
    confluence_pages: list,
    active_page_ids: list,
    bot_documents: list,
    bot_id: str,
) -> dict:
    """
    Build move batches matching legacy batch_move_documents().

    Only active pages are allowed to change tree metadata in AUTO mode.
    Active pages are deleted when moved outside the bot tree; otherwise their
    parent metadata is updated. Inactive pages are ignored defensively.
    """
    active_set = normalize_page_ids(
        active_page_ids,
        page_id_keys=("external_id", "confluence_page_id"),
    )
    bot_doc_map = {
        doc.get("external_id"): doc
        for doc in (bot_documents or [])
        if isinstance(doc, dict) and (doc.get("external_id") is not None)
    }
    bot_doc_ids = set(bot_doc_map.keys())
    active_move_batch = []
    inactive_move_batch = []
    sql_move_batch = []
    move_deleted_page_ids = []

    for move_item in to_move or []:
        if not isinstance(move_item, dict):
            continue

        page_id_raw = move_item.get("page_id")
        page_id = str(page_id_raw) if page_id_raw is not None else None
        if not page_id:
            continue

        new_parent_raw = move_item.get("new_parent_id")
        new_parent_id = str(new_parent_raw) if new_parent_raw not in (None, "") else None
        current_doc = bot_doc_map.get(page_id)
        parent_doc = bot_doc_map.get(new_parent_id) if new_parent_id else None
        expected_parent_doc_id = parent_doc.get("_id") if isinstance(parent_doc, dict) else None

        sql_move_payload = {
            "sql_query": """
                UPDATE knowledge_base.documents
                SET parent_id = %s,
                    is_deleted = FALSE,
                    sync_status = 'SYNCED'
                WHERE page_id = %s AND bot_id = %s
            """,
            "sql_params": (
                new_parent_id,
                page_id,
                bot_id,
            ),
        }

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
                active_move_batch.append(
                    {
                        "mongo_filter": {
                            "bot_id": bot_id,
                            "external_id": page_id,
                        },
                        "mongo_update": {
                            "$currentDate": {"sync_at": True},
                        },
                    }
                )
                sql_move_batch.append(sql_move_payload)
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
                        },
                        "$currentDate": {"sync_at": True},
                    },
                }
            )
            sql_move_batch.append(sql_move_payload)
            continue

        logger.warning(
            "AUTO move batch ignored inactive page: page_id=%s, new_parent_id=%s",
            page_id,
            new_parent_id,
        )

    return {
        "active_move_batch": active_move_batch,
        "inactive_move_batch": inactive_move_batch,
        "sql_move_batch": sql_move_batch,
        "moved_count": len(active_move_batch) + len(inactive_move_batch),
        "move_deleted_page_ids": move_deleted_page_ids,
    }


async def _build_updated_pages(
    insert_pages: list,
    update_pages: list,
    metadata_update_pages: list,
    move_items: list,
    confluence_pages: list,
) -> dict:
    """Build updated_pages payload for downstream chunk processing."""
    updated_pages = []
    seen_page_ids = set()

    insert_ids = {
        str(page.get("id"))
        for page in (insert_pages or [])
        if isinstance(page, dict) and page.get("id") is not None
    }
    update_ids = {
        str(page.get("id"))
        for page in (update_pages or [])
        if isinstance(page, dict) and page.get("id") is not None
    }
    metadata_update_ids = {
        str(page.get("id"))
        for page in (metadata_update_pages or [])
        if isinstance(page, dict) and page.get("id") is not None
    }
    page_map = {
        str(page.get("id")): page
        for page in (confluence_pages or [])
        if isinstance(page, dict) and page.get("id") is not None
    }

    def _append(page: dict, sync_status: str) -> None:
        page_id = str(page.get("id")) if isinstance(page, dict) else None
        if not page_id or page_id in seen_page_ids:
            return
        seen_page_ids.add(page_id)
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

    for page_id in insert_ids:
        page = page_map.get(page_id)
        if page:
            _append(page, "NEW")

    for page_id in update_ids:
        page = page_map.get(page_id)
        if page:
            _append(page, "UPDATED")

    for page_id in metadata_update_ids:
        page = page_map.get(page_id)
        if page:
            _append(page, "METADATA_UPDATED")

    logger.info(
        "Built updated_pages list for AUTO: %s new, %s updated, total=%s",
        len(insert_ids),
        len(update_ids),
        len(updated_pages),
    )

    return {"updated_pages": updated_pages}

