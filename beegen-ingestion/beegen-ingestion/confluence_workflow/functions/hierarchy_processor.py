"""Hierarchy operations used by the Confluence workflow graphs."""

from typing import Any, Dict

from confluence_workflow.functions.mongo_processor import MongoDBConnection
from confluence_workflow.utils.logger import get_logger

logger = get_logger("hierarchy_processor")


async def resolve_parent_child_relationships(bot_id: str) -> Dict[str, Any]:
    """Resolve external parent IDs to Mongo document IDs for one bot."""
    mongo_conn = MongoDBConnection()
    await mongo_conn.connect()
    try:
        resolved_count = await mongo_conn.resolve_parent_ids(bot_id)
        logger.info("Resolved %s parent-child relationships", resolved_count)
        return {"resolved_count": resolved_count}
    finally:
        await mongo_conn.disconnect()


async def calculate_document_levels_for_bot(bot_id: str) -> Dict[str, Any]:
    """Calculate Mongo document hierarchy levels for one bot."""
    mongo_conn = MongoDBConnection()
    await mongo_conn.connect()
    try:
        updated_count = await mongo_conn.calculate_document_levels(bot_id)
        logger.info("Calculated levels for %s documents", updated_count)
        return {"updated_count": updated_count}
    finally:
        await mongo_conn.disconnect()
