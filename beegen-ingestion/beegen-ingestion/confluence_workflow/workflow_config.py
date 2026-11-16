"""
Configuration management for Confluence workflow.

This module provides configuration loading and validation.
"""

import os
import json
import base64
from typing import Dict, Any

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Protocol.KDF import PBKDF2
from dotenv import load_dotenv

load_dotenv(".env")

AES_GCM_TAG_LEN = 16
AES_GCM_IV_LEN = 12
AES_GCM_KEY_LEN = 32
AES_GCM_ITERATIONS = 65536


def normalize_page_ids(page_ids: list | str | None) -> list:
    """Normalize page IDs passed from CLI or programmatic callers."""
    if not page_ids:
        return []

    if isinstance(page_ids, str):
        return [page_ids]

    return [str(page_id) for page_id in page_ids if page_id is not None]


async def get_active_parent_page_ids_from_mongo(bot_id: str) -> list:
    """Load active parent page IDs from botinfo.space_config.syncing_page."""
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_uri = os.getenv("MONGO_URI")
    mongo_db_name = os.getenv("MONGO_DB_NAME")

    client = AsyncIOMotorClient(mongo_uri)
    try:
        db = client[mongo_db_name]
        botinfo = await db["botinfo"].find_one(
            {"_id": bot_id},
            {"space_config": 1, "_id": 0},
        )
        space_config = (botinfo or {}).get("space_config") or {}
        syncing_pages = space_config.get("syncing_page") or []

        return [
            str(page.get("page_id"))
            for page in syncing_pages
            if isinstance(page, dict) and page.get("active") is True and page.get("page_id") is not None
        ]
    finally:
        client.close()


async def resolve_page_ids_for_mode(
    *,
    bot_id: str,
    sync_mode: str,
    page_ids: list | None,
    active_parent_page_ids_loader=None,
) -> list:
    """Resolve page_ids using the same mode contract as confluence_syncing/main.py."""
    normalized_page_ids = normalize_page_ids(page_ids)
    if normalized_page_ids:
        return normalized_page_ids

    normalized_sync_mode = (sync_mode or "").upper()

    if normalized_sync_mode == "PARTIAL":
        raise ValueError("page_ids is required for PARTIAL mode")

    if normalized_sync_mode in {"FIRST", "AUTO"}:
        if active_parent_page_ids_loader is not None:
            parent_page_ids = await active_parent_page_ids_loader(bot_id)
        else:
            parent_page_ids = await get_active_parent_page_ids_from_mongo(bot_id)

        normalized_parent_page_ids = normalize_page_ids(parent_page_ids)
        if normalized_sync_mode == "FIRST":
            return normalized_parent_page_ids

        if not normalized_parent_page_ids:
            raise ValueError(
                f"No active parent page IDs found for {normalized_sync_mode} mode and bot_id={bot_id}"
            )
        return normalized_parent_page_ids

    raise ValueError(f"Unsupported sync_mode: {sync_mode}")


async def resolve_config_page_ids(config: "WorkflowConfig") -> "WorkflowConfig":
    """Mutate config.page_ids after resolving mode-specific defaults."""
    config.page_ids = await resolve_page_ids_for_mode(
        bot_id=config.bot_id,
        sync_mode=config.sync_mode,
        page_ids=config.page_ids,
    )
    return config


def decrypt_env_value(encrypted_value: str) -> str:
    """Decrypt one Java-compatible AES-GCM ciphertext value."""
    if not encrypted_value:
        raise ValueError("Encrypted value is empty")

    password = os.getenv("AES_GCM_PASSWORD")
    salt_hex = os.getenv("AES_GCM_SALT")
    missing = [
        name
        for name, value in (
            ("AES_GCM_PASSWORD", password),
            ("AES_GCM_SALT", salt_hex),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"Missing AES-GCM env vars: {', '.join(missing)}")

    try:
        decoded = base64.b64decode(encrypted_value, validate=True)
        if len(decoded) <= AES_GCM_IV_LEN + AES_GCM_TAG_LEN:
            raise ValueError("Invalid encrypted value length")

        salt = bytes.fromhex(salt_hex)
        key = PBKDF2(
            password.encode("utf-8"),
            salt,
            dkLen=AES_GCM_KEY_LEN,
            count=AES_GCM_ITERATIONS,
            hmac_hash_module=SHA256,
        )

        iv = decoded[:AES_GCM_IV_LEN]
        ciphertext = decoded[AES_GCM_IV_LEN:-AES_GCM_TAG_LEN]
        tag = decoded[-AES_GCM_TAG_LEN:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise ValueError("Failed to decrypt workflow configuration value") from exc


class WorkflowConfig:
    """
    Configuration for Confluence sync workflow.
    
    Attributes:
        bot_id: Bot ID for tracking sync operations
        sync_mode: Sync mode (FIRST, PARTIAL, AUTO)
        page_ids: List of page IDs
        confluence_config: Confluence API configuration
        batch_size: Batch size for fetching pages
        limit: Limit number of pages to process
        kafka_topic: Kafka topic for results
    """
    
    def __init__(
        self,
        bot_id: str,
        sync_mode: str,
        page_ids: list = None,
        confluence_url: str = None,
        confluence_token: str = None,
        batch_size: int = 50,
        limit: int = 0,
    ):
        self.bot_id = bot_id
        self.sync_mode = sync_mode.upper() if isinstance(sync_mode, str) else sync_mode
        self.page_ids = normalize_page_ids(page_ids)
        self.batch_size = batch_size
        self.limit = limit
        self.kafka_topic = os.getenv("KAFKA_RESPONSE_TOPIC")
        
        # Confluence configuration
        self.confluence_config = {
            'url': confluence_url or os.getenv('CONFLUENCE_URL'),
            'token': confluence_token or os.getenv('CONFLUENCE_TOKEN'),
            'username': decrypt_env_value(os.getenv('CONFLUENCE_USERNAME')),
            'password': decrypt_env_value(os.getenv('CONFLUENCE_PASSWORD')),
            'otp_secret': decrypt_env_value(os.getenv('CONFLUENCE_OTP_SECRET')),
        }
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'bot_id': self.bot_id,
            'sync_mode': self.sync_mode,
            'page_ids': self.page_ids,
            'confluence_config': self.confluence_config,
            'batch_size': self.batch_size,
            'limit': self.limit,
            'kafka_topic': self.kafka_topic,
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like helper for existing workflow builder code."""
        return self.to_dict().get(key, default)


def load_config_from_args(args) -> WorkflowConfig:
    """
    Load configuration from command line arguments.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        WorkflowConfig instance
    """
    # Parse page_ids if it's a JSON string
    page_ids = args.page_ids
    if isinstance(page_ids, str):
        try:
            page_ids = json.loads(page_ids)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON for page_ids: {e}")
    
    return WorkflowConfig(
        bot_id=args.bot_id,
        sync_mode=args.sync_mode,
        page_ids=page_ids,
        confluence_url=args.confluence_url,
        confluence_token=args.confluence_token,
        batch_size=args.batch_size,
        limit=args.limit,
    )
