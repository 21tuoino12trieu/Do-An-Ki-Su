"""
Milvus Connection Manager - DEPRECATED
This module is deprecated as vector search has been migrated to Vertex AI Search.
"""
from beegenerate.loggings import LOGGER

class MilvusConnectionManager:
    """Deprecated stub manager for Milvus operations."""
    def __init__(self):
        LOGGER.info("MilvusConnectionManager is deprecated. All search operations now use Vertex AI Search.")

    async def execute_optimized(self, *args, **kwargs):
        LOGGER.warning("Milvus execute_optimized called on deprecated manager.")
        return []

milvus_manager = MilvusConnectionManager()