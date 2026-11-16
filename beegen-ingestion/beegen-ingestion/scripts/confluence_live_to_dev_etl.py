"""Copy one Confluence page tree from Live to Dev.

The destination Confluence instance owns destination page IDs.  This script
persists a Live-to-Dev ID mapping so interrupted runs can be resumed without
creating the same pages again.

Attachments are intentionally out of scope.  The script copies storage-format
page bodies and rewrites page-ID references for pages inside the migrated tree.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from atlassian import Confluence

LOGGER = logging.getLogger("confluence_live_to_dev_etl")

# ---------------------------------------------------------------------------
# Connection configuration
# Fill these values directly if this script is only used locally.  Do not
# commit real tokens or passwords to Git.
# ---------------------------------------------------------------------------
LIVE_CONFLUENCE_URL = "https://confluence.mbbank.com.vn/"
LIVE_CONFLUENCE_AUTH = "token"  # "token" or "basic"
LIVE_CONFLUENCE_TOKEN = "REPLACE_WITH_LOCAL_SECRET"
LIVE_CONFLUENCE_USERNAME = ""
LIVE_CONFLUENCE_PASSWORD = ""
LIVE_CONFLUENCE_CLOUD = False
LIVE_CONFLUENCE_VERIFY_SSL = True

DEV_CONFLUENCE_URL = "https://confluence.apps.dc01-ai-platform-ocp-dev.mbbank.com.vn/#all-updates"
DEV_CONFLUENCE_AUTH = "basic"  # Self-hosted Server/Data Center
DEV_CONFLUENCE_TOKEN = ""
DEV_CONFLUENCE_USERNAME = "admin"
DEV_CONFLUENCE_PASSWORD = "Mb@123"
DEV_CONFLUENCE_VERIFY_SSL = False

LIVE_ROOT_PAGE_ID = "273238220"
DEV_PARENT_PAGE_ID = "98361"  # Usually the Home page ID of the Dev space
DEV_SPACE_KEY = "AIC"
MAPPING_FILE = Path("confluence_page_mapping.json")
BATCH_SIZE = 50
DRY_RUN = False
VERBOSE = False


@dataclass(frozen=True)
class MigrationPage:
    live_id: str
    live_parent_id: str | None
    title: str
    body: str
    depth: int


def normalize_confluence_base_url(url: str | None) -> str:
    """Normalize an explicitly configured Confluence instance base URL.

    Unlike a public Cloud URL, self-hosted Server/Data Center installations may
    use a context path such as ``/confluence``.  Preserve that path verbatim.
    """
    raw_url = (url or "").strip()
    if not raw_url:
        return ""
    parsed = urlparse(raw_url)
    if not parsed.scheme or not parsed.netloc:
        return raw_url.rstrip("/")
    path = (parsed.path or "").rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def create_client(
    url: str,
    auth_mode: str,
    token: str,
    username: str,
    password: str,
    **options: Any,
) -> Confluence:
    """Create one authenticated Confluence client."""
    normalized_url = normalize_confluence_base_url(url)
    if not normalized_url:
        raise ValueError("Confluence URL must not be empty")

    common_options = {"url": normalized_url, **options}
    if auth_mode == "token":
        if not token:
            raise ValueError(f"Token is required for {normalized_url}")
        return Confluence(token=token, **common_options)

    if auth_mode == "basic":
        if not username or not password:
            raise ValueError(
                f"Username and password are required for Basic Auth on {normalized_url}"
            )
        return Confluence(username=username, password=password, **common_options)

    raise ValueError(f"Unsupported authentication mode: {auth_mode}")


def build_live_client() -> Confluence:
    return create_client(
        LIVE_CONFLUENCE_URL,
        LIVE_CONFLUENCE_AUTH,
        LIVE_CONFLUENCE_TOKEN,
        LIVE_CONFLUENCE_USERNAME,
        LIVE_CONFLUENCE_PASSWORD,
        verify_ssl=LIVE_CONFLUENCE_VERIFY_SSL,
        cloud=LIVE_CONFLUENCE_CLOUD,
    )


def build_dev_client() -> Confluence:
    return create_client(
        DEV_CONFLUENCE_URL,
        DEV_CONFLUENCE_AUTH,
        DEV_CONFLUENCE_TOKEN,
        DEV_CONFLUENCE_USERNAME,
        DEV_CONFLUENCE_PASSWORD,
        verify_ssl=DEV_CONFLUENCE_VERIFY_SSL,
        cloud=False,
    )


def page_from_payload(payload: dict[str, Any]) -> MigrationPage:
    """Convert a Confluence REST page payload to the migration contract."""
    page_id = payload.get("id")
    if page_id is None:
        raise ValueError("Confluence page payload does not contain an id")

    ancestors = payload.get("ancestors") or []
    parent_id = ancestors[-1].get("id") if ancestors else None
    return MigrationPage(
        live_id=str(page_id),
        live_parent_id=str(parent_id) if parent_id is not None else None,
        title=str(payload.get("title") or "Untitled"),
        body=str(payload.get("body", {}).get("storage", {}).get("value") or ""),
        depth=len(ancestors),
    )


def order_and_deduplicate_pages(payloads: list[dict[str, Any]]) -> list[MigrationPage]:
    """Return unique pages ordered so every migrated parent precedes its child."""
    pages_by_id: dict[str, MigrationPage] = {}
    for payload in payloads:
        page = page_from_payload(payload)
        pages_by_id.setdefault(page.live_id, page)
    return sorted(pages_by_id.values(), key=lambda page: (page.depth, page.live_id))


def rewrite_page_ids(body: str, page_id_mapping: dict[str, str]) -> str:
    """Rewrite page IDs only in known Confluence storage/URL contexts."""
    rewritten = body
    for live_id, dev_id in sorted(
        page_id_mapping.items(), key=lambda item: len(item[0]), reverse=True
    ):
        escaped_id = re.escape(live_id)
        replacements = (
            (rf'(?P<prefix>ri:content-id\s*=\s*["\']){escaped_id}(?P<suffix>["\'])', rf'\g<prefix>{dev_id}\g<suffix>'),
            (rf'(?P<prefix>[?&]pageId=){escaped_id}(?P<suffix>(?:[&#"\']|$))', rf'\g<prefix>{dev_id}\g<suffix>'),
            (rf'(?P<prefix>/pages/){escaped_id}(?P<suffix>(?:[/#?"\']|$))', rf'\g<prefix>{dev_id}\g<suffix>'),
            (rf'(?P<prefix>/pageId/){escaped_id}(?P<suffix>(?:[/#?"\']|$))', rf'\g<prefix>{dev_id}\g<suffix>'),
        )
        for pattern, replacement in replacements:
            rewritten = re.sub(pattern, replacement, rewritten)
    return rewritten


def rewrite_storage_body(
    body: str,
    page_id_mapping: dict[str, str],
    live_url: str,
    dev_url: str,
) -> str:
    """Rewrite internal page IDs and absolute instance URLs in a storage body."""
    rewritten = rewrite_page_ids(body, page_id_mapping)
    normalized_live_url = normalize_confluence_base_url(live_url).rstrip("/")
    normalized_dev_url = normalize_confluence_base_url(dev_url).rstrip("/")
    if normalized_live_url and normalized_dev_url:
        rewritten = rewritten.replace(normalized_live_url, normalized_dev_url)
    return rewritten


def load_mapping(path: Path) -> dict[str, str]:
    """Load a previously persisted Live-to-Dev page-ID mapping."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Mapping file must contain a JSON object: {path}")
    return {str(key): str(value) for key, value in payload.items()}


def save_mapping(path: Path, mapping: dict[str, str]) -> None:
    """Atomically persist the mapping after every successful page creation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


async def extract_pages(
    live_client: Confluence,
) -> list[MigrationPage]:
    """Extract the root page and every current descendant from Live."""
    root_payload = await asyncio.to_thread(
        live_client.get_page_by_id,
        page_id=LIVE_ROOT_PAGE_ID,
        expand="body.storage,ancestors",
    )
    if not isinstance(root_payload, dict) or root_payload.get("id") is None:
        raise RuntimeError(f"Live root page was not found: {LIVE_ROOT_PAGE_ID}")

    descendants: list[dict[str, Any]] = []
    start = 0
    while True:
        payload = await asyncio.to_thread(
            live_client.get,
            "rest/api/content/search",
            params={
                "cql": f"type=page AND ancestor={LIVE_ROOT_PAGE_ID}",
                "start": start,
                "limit": BATCH_SIZE,
                "expand": "body.storage,ancestors",
            },
        )
        results = payload.get("results", []) if isinstance(payload, dict) else []
        if not results:
            break
        descendants.extend(page for page in results if page.get("status") == "current")
        start += len(results)
        LOGGER.info("Extract progress: scanned=%s current=%s", start, len(descendants))
    return order_and_deduplicate_pages([root_payload, *(descendants or [])])


def response_page_id(response: Any, title: str) -> str:
    """Read the created page ID from the atlassian-python-api response."""
    if isinstance(response, dict) and response.get("id") is not None:
        return str(response["id"])
    raise RuntimeError(f"Dev did not return an id after creating page {title!r}")


async def load_pages(
    dev_client: Confluence,
    pages: list[MigrationPage],
) -> dict[str, str]:
    """Create missing pages, then update all bodies with rewritten IDs."""
    mapping = load_mapping(MAPPING_FILE)
    migrated_ids = {page.live_id for page in pages}

    for page in pages:
        if page.live_id in mapping:
            LOGGER.info("Reuse mapping live=%s dev=%s", page.live_id, mapping[page.live_id])
            continue

        if page.live_id == LIVE_ROOT_PAGE_ID:
            dev_parent_id = DEV_PARENT_PAGE_ID
        else:
            if page.live_parent_id not in migrated_ids:
                raise RuntimeError(
                    f"Parent {page.live_parent_id} of Live page {page.live_id} "
                    "is outside the extracted tree"
                )
            dev_parent_id = mapping.get(str(page.live_parent_id))
            if dev_parent_id is None:
                raise RuntimeError(
                    f"Destination parent is not available for Live page {page.live_id}"
                )

        if DRY_RUN:
            mapping[page.live_id] = f"DRY_RUN_{page.live_id}"
            LOGGER.info(
                "[dry-run] Would create live=%s title=%r under dev_parent=%s",
                page.live_id,
                page.title,
                dev_parent_id,
            )
            continue

        response = await asyncio.to_thread(
            dev_client.create_page,
            space=DEV_SPACE_KEY,
            title=page.title,
            body="",
            parent_id=dev_parent_id,
            representation="storage",
        )
        mapping[page.live_id] = response_page_id(response, page.title)
        save_mapping(MAPPING_FILE, mapping)
        LOGGER.info("Created live=%s dev=%s", page.live_id, mapping[page.live_id])

    for page in pages:
        dev_page_id = mapping[page.live_id]
        dev_parent_id = (
            DEV_PARENT_PAGE_ID
            if page.live_id == LIVE_ROOT_PAGE_ID
            else mapping[str(page.live_parent_id)]
        )
        rewritten_body = rewrite_storage_body(
            page.body,
            mapping,
            live_url=LIVE_CONFLUENCE_URL,
            dev_url=DEV_CONFLUENCE_URL,
        )
        if DRY_RUN:
            LOGGER.info(
                "[dry-run] Would update live=%s dev=%s body_chars=%s",
                page.live_id,
                dev_page_id,
                len(rewritten_body),
            )
            continue

        await asyncio.to_thread(
            dev_client.update_page,
            page_id=dev_page_id,
            title=page.title,
            body=rewritten_body,
            parent_id=dev_parent_id,
            representation="storage",
            always_update=True,
        )
        LOGGER.info("Updated live=%s dev=%s", page.live_id, dev_page_id)

    return mapping


def validate_configuration() -> None:
    """Fail before any API call when required configuration is missing."""
    required_values = {
        "LIVE_CONFLUENCE_URL": LIVE_CONFLUENCE_URL,
        "DEV_CONFLUENCE_URL": DEV_CONFLUENCE_URL,
        "LIVE_ROOT_PAGE_ID": LIVE_ROOT_PAGE_ID,
        "DEV_PARENT_PAGE_ID": DEV_PARENT_PAGE_ID,
        "DEV_SPACE_KEY": DEV_SPACE_KEY,
    }
    missing = [name for name, value in required_values.items() if not str(value).strip()]
    if missing:
        raise ValueError(f"Missing configuration: {', '.join(missing)}")
    if BATCH_SIZE <= 0:
        raise ValueError("BATCH_SIZE must be greater than zero")


async def run() -> None:
    validate_configuration()
    live_client = build_live_client()
    dev_client = build_dev_client()
    pages = await extract_pages(live_client)
    LOGGER.info("Extracted %s unique pages from Live", len(pages))
    mapping = await load_pages(dev_client, pages)
    LOGGER.info("Migration completed: pages=%s mapping=%s", len(pages), len(mapping))


def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG if VERBOSE else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
