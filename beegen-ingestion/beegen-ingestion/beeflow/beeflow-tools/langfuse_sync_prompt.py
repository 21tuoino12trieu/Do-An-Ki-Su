#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, Iterable, Mapping, Any

import httpx
from langfuse import Langfuse

# =========================
# ENV / PROXY SAFETY
# =========================
for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.setdefault(k, "NO_PROXY")
os.environ.setdefault("NO_PROXY", "*")
os.environ.setdefault("no_proxy", "*")

DEFAULT_PAGE_SIZE = 100


# =========================
# ARG PARSER
# =========================
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync Langfuse prompts from DEV to LIVE"
    )

    parser.add_argument("--dev-host", default="https://ai-langfuse-dev.mbbank.com.vn") #FIXME
    parser.add_argument("--live-host", default="https://ai-langfuse-uat.mbbank.com.vn") #FIXME
 
    parser.add_argument("--dev-public-key", default="pk-lf-ee640257-5279-4e3c-a22e-5830b58d7dc5") #FIXME
    parser.add_argument("--dev-secret-key", default="REPLACE_WITH_LOCAL_SECRET") #FIXME

    parser.add_argument("--live-public-key", default="pk-lf-634648aa-c5cd-4880-9c8f-a8ae5edc1ae6") #FIXME
    parser.add_argument("--live-secret-key", default="REPLACE_WITH_LOCAL_SECRET") #FIXME

    parser.add_argument("--prefix", help="Prompt name prefix (e.g. BEECHAT_)", default="") #FIXME
    parser.add_argument("--label", default="production", help="Prompt label to sync") #FIXME

    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)

    parser.add_argument("--verify-ssl", action="store_true", default=False)

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")

    args = parser.parse_args()

    for key in (
        "dev_public_key",
        "dev_secret_key",
        "live_public_key",
        "live_secret_key",
    ):
        if not getattr(args, key):
            parser.error(f"Missing {key} (arg or env)")

    return args


# =========================
# LANGFUSE CLIENT
# =========================
def create_client(host: str, pk: str, sk: str, verify_ssl: bool) -> Langfuse:
    http_client = httpx.Client(verify=verify_ssl, timeout=30)
    return Langfuse(
        public_key=pk,
        secret_key=sk,
        host=host,
        httpx_client=http_client,
    )


# =========================
# FETCH DEV PROMPTS
# =========================
def fetch_prompt_names(
    client: Langfuse,
    prefix: str,
    label: str | None,
    page_size: int,
) -> list[str]:
    page = 1
    names: list[str] = []

    while True:
        resp = client.api.prompts.list(page=page, limit=page_size, label=label)
        names.extend(
            m.name for m in resp.data if m.name.startswith(prefix)
        )

        if page >= resp.meta.total_pages:
            break
        page += 1

    return sorted(set(names))


def serialize_prompt(prompt: Any) -> str:
    if isinstance(prompt, str):
        return prompt
    return json.dumps(prompt, ensure_ascii=False, indent=2)


def fetch_prompts(
    client: Langfuse,
    names: Iterable[str],
    label: str | None,
) -> Dict[str, str]:
    result: Dict[str, str] = {}

    for name in names:
        try:
            p = client.get_prompt(name, label=label)
            result[name] = serialize_prompt(p.prompt)
            print(f"[DEV ✓] {name}")
        except Exception as e:
            print(f"[DEV ✗] {name}: {e}", file=sys.stderr)

    return result


# =========================
# UPSERT LIVE
# =========================
def upsert_live(
    client: Langfuse,
    prompts: Mapping[str, str],
    dry_run: bool,
):
    for name, content in prompts.items():
        if dry_run:
            print(f"[DRY-RUN] Would sync: {name}")
            continue

        try:
            client.create_prompt(
                name=name,
                prompt=content,
                labels=["production"],
            )
            print(f"[LIVE ✓] Synced: {name}")
        except Exception as e:
            print(f"[LIVE ✗] {name}: {e}", file=sys.stderr)


# =========================
# MAIN
# =========================
def main():
    args = parse_args()

    print("🔌 Connecting DEV...")
    dev = create_client(
        args.dev_host,
        args.dev_public_key,
        args.dev_secret_key,
        args.verify_ssl,
    )

    print("🔌 Connecting LIVE...")
    live = create_client(
        args.live_host,
        args.live_public_key,
        args.live_secret_key,
        args.verify_ssl,
    )

    print("📥 Fetching DEV prompt names...")
    names = fetch_prompt_names(
        dev,
        prefix=args.prefix,
        label=args.label,
        page_size=args.page_size,
    )

    if not names:
        print("⚠️ No prompts found. Abort.")
        return

    print(f"📦 Found {len(names)} prompts")

    prompts = fetch_prompts(dev, names, args.label)

    print("🚀 Syncing to LIVE...")
    upsert_live(live, prompts, dry_run=args.dry_run)

    print("✅ Done")


if __name__ == "__main__":
    main()
