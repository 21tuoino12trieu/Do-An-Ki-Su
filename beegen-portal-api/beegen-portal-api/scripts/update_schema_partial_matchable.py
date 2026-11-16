"""Standalone admin script: set `partialMatchable: true` on every text field of
the Vertex AI Search (Discovery Engine) Data Store's user Schema.

WHY THIS EXISTS
---------------
`vertex_search_client._build_struct_data` writes `partialMatchable: True` into
each Document's structData (see app/utils/vertex_search_client.py). That is the
wrong layer: `partialMatchable` is a field-level property of the Data Store's
JSON *Schema*, not a per-document value. Setting it on structData has no effect.
This script fixes the Schema itself so token-based partial matching (and the
CONTAINS filter operator) actually work on the configured fields.

WHAT IT DOES
------------
1. Loads connection settings from a config.env file (the same one the L01 pod
   mounts as a ConfigMap) — DATA_STORE_ID, GCS_PROJECT_ID, DATA_STORE_LOCATION,
   GCS_PROXY_HOST/PORT, GOOGLE_APPLICATION_CREDENTIALS.
2. Builds a SchemaServiceClient authenticated with the service account.
3. Mounts the F5 gateway proxy onto the client's transport sessions, following
   the exact mutate-session-in-place pattern documented in
   vertex_search_client.py (never reassign transport._session — mount the proxy
   adapter onto the existing AuthorizedSession and its _auth_request_session).
4. GETs the current Schema, parses its jsonSchema, and adds
   `"partialMatchable": true` to every text-typed field that doesn't already
   have it. Non-text fields (boolean, timestamp/number) are left alone because
   partial-match tokenization only applies to text.
5. PATCHes the Schema back. updateSchema is a long-running operation, so the
   script polls until it completes and reports success/failure.

USAGE
-----
    # From inside beegen-portal-api/ (paths resolve relative to that dir):
    python scripts/update_schema_partial_matchable.py --dry-run

    # From repo root (script auto-finds the portal-api dir):
    python beegen-portal-api/scripts/update_schema_partial_matchable.py --dry-run

    # Override any setting via flags
    python scripts/update_schema_partial_matchable.py \
        --config cicd/tanzu-dev/L01/configmap-k8s/config.env \
        --service-account secrets/service-account.json \
        --dry-run

Run with --dry-run first to preview the field changes without writing.
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

# Make the script runnable both from repo root and from its own directory:
# vertex_search_client's proxy helper (mount_f5_proxy) is imported from the
# portal-api package, so add the portal-api root to sys.path when needed.
_HERE = Path(__file__).resolve().parent
_PORTAL_API_ROOT = _HERE.parent
if str(_PORTAL_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_PORTAL_API_ROOT))

# Default config / secret paths anchored to the portal-api root, NOT to the
# user's CWD — the script works identically from repo root or from inside
# beegen-portal-api/ without passing any flags.
_DEFAULT_CONFIG = _PORTAL_API_ROOT / "cicd" / "tanzu-dev" / "L01" / "configmap-k8s" / "config.env"
_DEFAULT_SA = _PORTAL_API_ROOT / "secrets" / "service-account.json"

from google.cloud import discoveryengine_v1alpha
from google.oauth2 import service_account

# Reuse the SAME F5 proxy mounting helper the production client uses, so this
# script routes through the gateway identically and stays in sync if the proxy
# wiring ever changes.
from app.utils.f5_proxy import mount_f5_proxy

logger = logging.getLogger("update_schema_partial_matchable")

DISCOVERYENGINE_PINNED_HOST = "discoveryengine.googleapis.com"
OAUTH2_PINNED_HOST = "oauth2.googleapis.com"

# Field types that don't benefit from token-based partial matching. We only
# touch string fields; everything else (booleans, numbers, dates stored as
# numbers/strings in ISO form) is skipped to avoid nonsensical tokenization.
_TEXT_TYPES = {"string"}

# Schema fields to never mark partialMatchable even if they happen to be
# strings — created_at is an ISO timestamp, partial-tokenizing a date is noise.
# "partialMatchable" itself is the SPURIOUS field auto-created by Discovery
# Engine because vertex_search_client._build_struct_data writes it into each
# document's structData (bug at line 239 of app/utils/vertex_search_client.py):
# Discovery Engine sees an unknown key in structData and adds it to the schema
# as a boolean data field. It is NOT a real data field and must never carry the
# partialMatchable property (it's a property NAME, not a field).
_SKIP_FIELDS = {"created_at", "partialMatchable"}


# --------------------------------------------------------------------------- #
# Config loading
# --------------------------------------------------------------------------- #
def _parse_config_env(path: Path) -> dict[str, str]:
    """Parses a shell-style config.env into a flat {key: value} dict.

    config.env is not real POSIX shell — it's KEY=value lines, some quoted,
    some with inline comments. We only need the subset this project actually
    writes, so a tolerant parser is enough and avoids pulling in python-dotenv.
    """
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip a trailing inline comment that follows a value, but only when
        # the value isn't quoted (a `#` inside quotes is data, not a comment).
        if value and value[0] in "\"'" and value[-1] == value[0]:
            value = ast.literal_eval(value)
        elif "#" in value:
            value = value.split("#", 1)[0].strip()
        env[key] = value
    return env


def _resolve_config(args: argparse.Namespace) -> dict[str, str]:
    """Returns the merged config (flag overrides > config.env > env)."""
    config_env = _parse_config_env(Path(args.config))
    # Precedence: real process env > config.env, so an operator can override a
    # single value without editing the file. CLI flags override both (applied
    # later by the caller).
    merged = {**config_env, **{k: v for k, v in os.environ.items()}}
    return merged


# --------------------------------------------------------------------------- #
# Client construction (F5 proxy wired exactly like vertex_search_client)
# --------------------------------------------------------------------------- #
def _build_schema_service_client(
    config: dict[str, str], credentials_path: Path
) -> discoveryengine_v1alpha.SchemaServiceClient:
    """Builds a SchemaServiceClient whose REST transport routes Discovery
    Engine + oauth2 traffic through the F5 gateway.

    This mirrors `_get_document_service_client` in vertex_search_client.py.
    SchemaServiceClient shares the same transport internals
    (DocumentServiceRestTransport-style: its own AuthorizedSession + a separate
    _auth_request_session for token refresh), so the same mutate-in-place rule
    applies: mount the proxy adapter onto the existing sessions, never replace
    them.
    """
    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_path),
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )

    transport = (
        discoveryengine_v1alpha.services.schema_service.transports.SchemaServiceRestTransport(
            credentials=credentials
        )
    )

    proxy_host = config.get("GCS_PROXY_HOST")
    if proxy_host:
        proxy_port = int(config.get("GCS_PROXY_PORT", "443"))

        transport._session.trust_env = False
        mount_f5_proxy(
            transport._session,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            pinned_host=DISCOVERYENGINE_PINNED_HOST,
        )

        auth_request_session = transport._session._auth_request_session
        auth_request_session.trust_env = False
        mount_f5_proxy(
            auth_request_session,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            pinned_host=OAUTH2_PINNED_HOST,
        )

    client = discoveryengine_v1alpha.SchemaServiceClient(transport=transport)

    if proxy_host:
        proxy_port = int(config.get("GCS_PROXY_PORT", "443"))
        # Operations client (for polling updateSchema LRO) builds its own
        # transport on first access — same reason as in vertex_search_client.
        ops_transport = client.transport.operations_client._transport
        ops_transport._session.trust_env = False
        mount_f5_proxy(
            ops_transport._session,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            pinned_host=DISCOVERYENGINE_PINNED_HOST,
        )
        ops_auth_session = ops_transport._session._auth_request_session
        ops_auth_session.trust_env = False
        mount_f5_proxy(
            ops_auth_session,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            pinned_host=OAUTH2_PINNED_HOST,
        )

    return client


# --------------------------------------------------------------------------- #
# Schema resource naming + read/modify/write
# --------------------------------------------------------------------------- #
def _data_store_parent(config: dict[str, str]) -> str:
    """Full resource name of the Data Store (parent of its schemas)."""
    project_id = config["GCS_PROJECT_ID"]
    data_store_id = config["DATA_STORE_ID"]
    location = config.get("DATA_STORE_LOCATION", "global")
    return (
        f"projects/{project_id}/locations/{location}/collections/default_collection/"
        f"dataStores/{data_store_id}"
    )


def _find_schema_name(
    client: discoveryengine_v1alpha.SchemaServiceClient, config: dict[str, str]
) -> str | None:
    """Returns the name of the Data Store's single user Schema, or None.

    Unlike Document/Branch (which use fixed "default_branch" / "__default__"
    names), the Schema resource's name is NOT fixed: Discovery Engine names it
    "default_schema" for auto-generated ones, but user-created schemas can have
    arbitrary names. So we must list and pick the first (a Data Store has at
    most one Schema)."""
    parent = _data_store_parent(config)
    for schema in client.list_schemas(
        request=discoveryengine_v1alpha.ListSchemasRequest(parent=parent)
    ):
        return schema.name
    return None


def _select_fields_to_update(json_schema: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Returns (field_name, field_def) pairs that should get partialMatchable.

    A field is a candidate when: it lives under json_schema["properties"], its
    "type" is string, its name isn't in _SKIP_FIELDS, and it doesn't already
    have partialMatchable set to true.
    """
    properties = json_schema.get("properties", {}) or {}
    selected: list[tuple[str, dict[str, Any]]] = []
    for name, definition in properties.items():
        if not isinstance(definition, dict):
            continue
        if name in _SKIP_FIELDS:
            continue
        if definition.get("type") not in _TEXT_TYPES:
            continue
        if definition.get("partialMatchable") is True:
            continue
        selected.append((name, definition))
    return selected


def _patch_schema(
    client: discoveryengine_v1alpha.SchemaServiceClient,
    schema_name: str,
    json_schema: dict[str, Any],
    updated_fields: list[str],
) -> None:
    """PATCHes the Schema and blocks until the long-running operation completes.

    SchemaService has no partial-update mask for the jsonSchema blob: the whole
    jsonSchema string is replaced, so we send the full (modified) schema back.
    allow_missing=True so the first call on a Data Store whose Schema resource
    was never explicitly written still creates it.
    """
    schema = discoveryengine_v1alpha.Schema(
        name=schema_name,
        json_schema=json.dumps(json_schema, ensure_ascii=False),
    )

    operation = client.update_schema(
        request=discoveryengine_v1alpha.UpdateSchemaRequest(
            schema=schema,
            allow_missing=True,
        )
    )
    operation_name = operation.operation.name
    logger.info("updateSchema LRO started: %s", operation_name)

    # Poll the LRO. update_schema returns a gapic LRO future; calling
    # .result() blocks until done OR raises on failure. We wrap it with a
    # deadline so the script can't hang indefinitely on a network blip. The
    # future's .result() re-raises the operation's error as a
    # google.api_core.exceptions.GoogleAPICallError when the op failed, so a
    # clean return here means success.
    deadline = time.time() + 600  # 10 min is plenty for a schema patch
    remaining = max(1.0, deadline - time.time())
    try:
        operation.result(timeout=remaining)
    except Exception as exc:  # noqa: BLE001 — surface any LRO failure verbatim
        raise RuntimeError(f"updateSchema operation {operation_name} failed: {exc}") from exc

    logger.info(
        "updateSchema completed. Fields now partialMatchable: %s",
        ", ".join(updated_fields) or "(none)",
    )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mark text fields of the Vertex AI Search Data Store Schema "
        "as partialMatchable.",
    )
    parser.add_argument(
        "--config",
        default=str(_DEFAULT_CONFIG),
        help="Path to the config.env (ConfigMap) with DATA_STORE_ID etc. "
        "Default: <portal-api>/cicd/tanzu-dev/L01/configmap-k8s/config.env.",
    )
    parser.add_argument(
        "--service-account",
        default=str(_DEFAULT_SA),
        help="Path to the GCP service-account JSON. Default: "
        "<portal-api>/secrets/service-account.json.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the field changes that would be made, then exit without "
        "calling updateSchema.",
    )
    parser.add_argument(
        "--remove-spurious-field",
        action="store_true",
        help="DEPRECATED/NO-OP: Discovery Engine does not allow removing fields "
        "from a schema once indexed, so the spurious boolean field "
        "'partialMatchable' cannot be deleted here. Kept only so old invocations "
        "don't crash; the flag now logs a warning and is ignored. The right fix "
        "is to stop writing partialMatchable into structData (see "
        "vertex_search_client.py).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = _resolve_config(args)

    missing = [k for k in ("GCS_PROJECT_ID", "DATA_STORE_ID") if not config.get(k)]
    if missing:
        parser.error(
            f"Missing required config keys: {', '.join(missing)}. "
            f"Check --config {args.config}."
        )

    credentials_path = Path(args.service_account)
    if not credentials_path.is_file():
        parser.error(f"Service account file not found: {credentials_path}")

    client = _build_schema_service_client(config, credentials_path)

    schema_name = _find_schema_name(client, config)
    if schema_name is None:
        logger.error(
            "No user Schema found on Data Store %s. The Data Store has no "
            "explicit Schema resource, so there is nothing to patch. Create one "
            "in the Console first.", _data_store_parent(config),
        )
        return 2
    logger.info("Target Schema: %s", schema_name)
    logger.info("Proxy: %s:%s", config.get("GCS_PROXY_HOST", "(none)"),
                config.get("GCS_PROXY_PORT", "443"))

    # ---- Read current schema -------------------------------------------------
    schemas = list(client.list_schemas(
        request=discoveryengine_v1alpha.ListSchemasRequest(
            parent=_data_store_parent(config)
        )
    ))
    # _find_schema_name already located the single schema; fetch its full body.
    current = next(s for s in schemas if s.name == schema_name)

    if not current.json_schema:
        logger.error(
            "Schema %s has no json_schema field. Nothing to patch.", schema_name
        )
        return 2

    json_schema = json.loads(current.json_schema)
    if "properties" not in json_schema or not isinstance(json_schema["properties"], dict):
        logger.error(
            "Schema json_schema has no 'properties' object. Got: %s",
            json.dumps(json_schema)[:200],
        )
        return 2

    # ---- Decide changes ------------------------------------------------------
    to_update = _select_fields_to_update(json_schema)
    spurious_present = "partialMatchable" in (json_schema.get("properties") or {})

    if not to_update and not (args.remove_spurious_field and spurious_present):
        logger.info("No changes needed — all text fields already have partialMatchable.")
        return 0
    if not to_update:
        # Only the no-op remove flag was passed; nothing to write.
        logger.info("No field updates to apply.")
        return 0

    logger.info("Fields to mark partialMatchable=true:")
    for name, definition in to_update:
        logger.info("  - %s (type=%s)", name, definition.get("type"))

    if args.remove_spurious_field and spurious_present:
        logger.warning(
            "--remove-spurious-field is a no-op: Discovery Engine does not allow "
            "removing schema fields. The boolean field 'partialMatchable' will be "
            "left in place. Stop writing it into structData (see "
            "vertex_search_client.py) to prevent new documents from populating it."
        )

    if args.dry_run:
        logger.info("--dry-run set: no changes written.")
        return 0

    # ---- Apply ---------------------------------------------------------------
    for name, definition in to_update:
        definition["partialMatchable"] = True

    # ---- Apply ---------------------------------------------------------------
    for name, definition in to_update:
        definition["partialMatchable"] = True

    _patch_schema(
        client,
        schema_name,
        json_schema,
        updated_fields=[name for name, _ in to_update],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
