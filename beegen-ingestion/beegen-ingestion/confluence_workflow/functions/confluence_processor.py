"""Confluence client and page-tree helpers used by the workflow."""

import asyncio
from typing import Any, Dict, List
from urllib.parse import urlparse

from atlassian import Confluence

from confluence_workflow.utils.logger import get_logger

logger = get_logger("confluence")


def is_confluence_not_found_error(exc: Exception) -> bool:
    """Return whether an Atlassian client error was caused by HTTP 404."""
    current = exc
    visited = set()

    while current is not None and id(current) not in visited:
        visited.add(id(current))
        response = getattr(current, "response", None)
        if getattr(response, "status_code", None) == 404:
            return True
        current = getattr(current, "reason", None) or getattr(current, "__cause__", None)

    return False


def normalize_confluence_base_url(url: str | None) -> str:
    """Normalize a page URL to the base URL expected by the Confluence client."""
    raw_url = (url or "").strip()
    if not raw_url:
        return ""

    parsed = urlparse(raw_url)
    if not parsed.scheme or not parsed.netloc:
        return raw_url

    path = (parsed.path or "").rstrip("/")
    normalized_path = "/wiki" if path.startswith("/wiki") else ""
    return f"{parsed.scheme}://{parsed.netloc}{normalized_path}"


def _get_confluence_client(config: Dict[str, str]) -> Confluence:
    """Create a Confluence client from workflow configuration."""
    url = normalize_confluence_base_url(config.get("url"))

    if "dev" in url:
        return Confluence(url=url, token=config.get("token"), verify_ssl=False)

    return Confluence(url=url, token=config.get("token"))


async def fetch_descendants_flat(
    confluence: Confluence,
    parent_id: str,
    batch_size: int = 50,
    progress: dict[str, int] | None = None,
) -> List[Dict[str, Any]]:
    """Fetch all descendant pages with one flat, paginated CQL query."""
    if progress is None:
        progress = {"fetched": 0, "next_log": 100}

    all_pages = []
    start = 0

    while True:
        children_payload = await asyncio.to_thread(
            confluence.get,
            "rest/api/content/search",
            params={
                "cql": f"type=page AND ancestor={parent_id}",
                "start": start,
                "limit": batch_size,
                "expand": "body.storage,version,ancestors,history.lastUpdated",
            },
        )

        search_results = children_payload["results"]

        if not search_results:
            break

        children = [
            page
            for page in search_results
            if page.get("status") == "current"
        ]
        skipped_count = len(search_results) - len(children)
        if skipped_count:
            logger.info(
                "Skipped %s non-current descendants from page %s",
                skipped_count,
                parent_id,
            )

        all_pages.extend(children)
        progress["fetched"] += len(children)
        if progress["fetched"] >= progress["next_log"]:
            logger.info(
                "Confluence fetch progress: fetched=%s pages",
                progress["fetched"],
            )
            progress["next_log"] = ((progress["fetched"] // 100) + 1) * 100
        logger.debug("Fetched %s descendants from page %s", len(children), parent_id)

        start += len(search_results)
        if start > 10000:
            logger.warning("Reached safety limit for page %s", parent_id)
            break

    return all_pages
