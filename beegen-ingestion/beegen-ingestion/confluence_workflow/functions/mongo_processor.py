"""
MongoDB helper functions for BeeFlow nodes.

This module provides helper functions for MongoNode operations.
"""

import os
from typing import Dict, Any, List, Optional
from confluence_workflow.utils.logger import get_logger
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from datetime import datetime, timezone

logger = get_logger('mongo')

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")


class MongoDBConnection:
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None

    def _active_confluence_filter(
        self,
        bot_id: str,
        extra_filter: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {
            "bot_id": bot_id,
            "deleted": {"$ne": True},
            "$or": [
                {"source": "confluence"},
                {"source_type": "confluence"},
            ],
        }
        if extra_filter:
            query.update(extra_filter)
        return query

    async def connect(self):
        try:
            self.client = AsyncIOMotorClient(MONGO_URI)
            self.db = self.client[MONGO_DB_NAME]
        except Exception as e:
            raise ConnectionError(f"Failed to connect to MongoDB: {str(e)}")
        
    async def disconnect(self): 
        try:
            if self.client:
                self.client.close()
        except Exception as e:
            raise ConnectionError(f"Failed to connect to MongoDB: {str(e)}")

    async def resolve_parent_ids(self, bot_id: str) -> int:
        """
        Post-process step: Resolve external_parent_id to parent_id UUIDs.

        For all documents with external_parent_id set:
        1. Find parent document by external_id (filtered by bot_id)
        2. Update child's parent_id with parent's _id
        3. Reconcile stale parent_id values after repeated moves
        4. Use multi-pass approach to handle dependencies

        Args:
            bot_id: The bot ID to filter documents

        Returns:
            Number of documents updated
        """
        try:
            collection = self.db["documents"]

            # Multi-pass resolution to handle dependencies and stale parent links.
            max_iterations = 10
            total_resolved = 0

            for iteration in range(max_iterations):
                # Reconcile all active documents with external_parent_id, not only
                # those whose parent_id is null. This fixes stale parent_id values
                # after repeated move in/out operations.
                cursor = collection.find(
                    self._active_confluence_filter(
                        bot_id,
                        {"external_parent_id": {"$ne": None}},
                    ),
                    {"_id": 1, "external_id": 1, "external_parent_id": 1, "parent_id": 1},
                )
                documents_to_resolve = await cursor.to_list(length=None)

                if not documents_to_resolve:
                    break  # All resolved

                iteration_resolved = 0

                for doc in documents_to_resolve:
                    parent_external_id = doc.get("external_parent_id")
                    child_external_id = doc.get("external_id")
                    current_parent_id = doc.get("parent_id")

                    # Find parent document by its external_id (filtered by bot_id)
                    parent_doc = await collection.find_one(
                        self._active_confluence_filter(
                            bot_id,
                            {"external_id": parent_external_id},
                        ),
                        {"_id": 1},
                    )

                    if parent_doc:
                        expected_parent_id = parent_doc["_id"]
                        if current_parent_id != expected_parent_id:
                            await collection.update_one(
                                {"_id": doc["_id"]},
                                {"$set": {"parent_id": expected_parent_id}},
                            )
                            iteration_resolved += 1
                            total_resolved += 1
                            logger.debug(
                                f"Resolved parent for child {child_external_id} -> parent {parent_external_id}"
                            )
                    elif current_parent_id is not None:
                        await collection.update_one(
                            {"_id": doc["_id"]},
                            {"$set": {"parent_id": None}},
                        )
                        iteration_resolved += 1
                        total_resolved += 1
                        logger.debug(
                            f"Cleared stale parent for child {child_external_id}; parent {parent_external_id} not found"
                        )

                if iteration_resolved == 0:
                    # No progress in this iteration
                    # Some parents might not exist - log them
                    cursor = collection.find(
                        self._active_confluence_filter(
                            bot_id,
                            {"external_parent_id": {"$ne": None}},
                        ),
                        {"external_id": 1, "external_parent_id": 1, "parent_id": 1},
                    )
                    documents_to_resolve = await cursor.to_list(length=None)

                    for doc in documents_to_resolve:
                        parent_doc = await collection.find_one(
                            self._active_confluence_filter(
                                bot_id,
                                {"external_id": doc["external_parent_id"]},
                            ),
                            {"_id": 1},
                        )
                        expected_parent_id = parent_doc["_id"] if parent_doc else None
                        if doc.get("parent_id") != expected_parent_id:
                            logger.warning(
                                f"Parent mismatch unresolved: child external_id={doc['external_id']}, "
                                f"external_parent_id={doc['external_parent_id']}, "
                                f"parent_id={doc.get('parent_id')}, expected_parent_id={expected_parent_id}"
                            )
                    break

            logger.info(f"Resolved {total_resolved} parent-child relationships")
            return total_resolved

        except Exception as e:
            logger.error(f"Error resolving parent IDs: {str(e)}")
            raise

    async def calculate_document_levels(self, bot_id: str) -> int:
        """
        Calculate and update the level attribute for all documents.

        Level 0: Documents without parent (root pages)
        Level N: Documents whose parent is at level N-1

        Args:
            bot_id: The bot ID to filter documents

        Returns:
            Number of documents with level updated
        """
        try:
            collection = self.db["documents"]

            # Step 1: Set level = 0 for root documents (no external_parent_id)
            result = await collection.update_many(
                self._active_confluence_filter(bot_id, {"external_parent_id": None}),
                {"$set": {"level": 0, "parent_id": None}},
            )
            updated_count = result.modified_count

            # Step 2: Calculate levels for documents with parents
            # Use multiple passes to handle deep hierarchies
            max_iterations = 100
            iteration = 0

            while iteration < max_iterations:
                # Find ALL documents with parents (not just those with level: None or level: 0)
                # This ensures we recalculate levels for documents that might have incorrect levels
                cursor = collection.find(
                    self._active_confluence_filter(
                        bot_id,
                        {"external_parent_id": {"$ne": None}},
                    ),
                    {
                        "_id": 1,
                        "external_id": 1,
                        "external_parent_id": 1,
                        "parent_id": 1,
                        "level": 1,
                    },
                )
                documents_to_update = await cursor.to_list(length=None)

                if not documents_to_update:
                    break  # No documents with parents

                iteration_count = 0

                for doc in documents_to_update:
                    parent_external_id = doc.get("external_parent_id")
                    child_external_id = doc.get("external_id")
                    current_level = doc.get("level")

                    # Find parent document
                    parent_doc = await collection.find_one(
                        self._active_confluence_filter(
                            bot_id,
                            {"external_id": parent_external_id},
                        ),
                        {"level": 1},
                    )

                    if parent_doc and parent_doc.get("level") is not None:
                        # Calculate expected level
                        expected_level = parent_doc["level"] + 1

                        # Only update if level needs to change
                        if current_level != expected_level:
                            await collection.update_one(
                                {"_id": doc["_id"]}, {"$set": {"level": expected_level}}
                            )
                            iteration_count += 1
                            updated_count += 1
                            logger.debug(
                                f"Updated level for {child_external_id}: {current_level} -> {expected_level}"
                            )
                    else:
                        if current_level != 0 or doc.get("parent_id") is not None:
                            await collection.update_one(
                                {"_id": doc["_id"]},
                                {"$set": {"level": 0, "parent_id": None}},
                            )
                            iteration_count += 1
                            updated_count += 1
                        logger.warning(
                            f"Parent not found or parent has no level for child {child_external_id}, "
                            f"external_parent_id={parent_external_id}"
                        )

                iteration += 1

                if iteration_count == 0:
                    # No progress in this iteration - all levels are correct
                    break

            # Step 3: Verify and fix inconsistent hierarchies
            await self._verify_and_fix_hierarchies(bot_id)

            logger.info(f"Calculated levels for {updated_count} documents")
            return updated_count

        except Exception as e:
            logger.error(f"Error calculating document levels: {str(e)}")
            raise
    
    async def update_sync_time_partial_mode(self, bot_id: str, page_ids: List[str]) -> int:
        """
        Update the sync timestamp for specific documents by page IDs.

        Args:
            bot_id: The bot ID to filter documents
            page_ids: List of external page IDs to update

        Returns:
            Number of documents with sync_at updated
        """
        if page_ids and not isinstance(page_ids[0], str):
            page_ids = [str(p) for p in page_ids]

        try:
            collection = self.db["documents"]

            result = await collection.update_many(
                {"bot_id": bot_id, "source": "confluence", "sync_mode": True, "external_id": {'$in': page_ids}},
                {"$set": {"sync_at": datetime.now(timezone.utc)}},
            )
            updated_count = result.modified_count

            return updated_count
        except Exception as e:
            logger.error(f"Error update sync time in partial mode: {str(e)}")
            raise

    async def _verify_and_fix_hierarchies(self, bot_id: str):
        """
        Verify and fix inconsistent parent-child hierarchies.

        Checks that:
        - All level0 documents have no parent_id
        - Parent level is child level - 1

        Args:
            bot_id: The bot ID to filter documents
        """
        try:
            collection = self.db["documents"]

            # Check level 0 documents with parent_id (should be None)
            cursor = collection.find(
                self._active_confluence_filter(
                    bot_id,
                    {"level": 0, "parent_id": {"$ne": None}},
                ),
                {"_id": 1, "external_id": 1, "parent_id": 1},
            )
            level0_with_parent = await cursor.to_list(length=None)

            for doc in level0_with_parent:
                logger.warning(
                    f"Level 0 document has parent_id: external_id={doc['external_id']}, "
                    f"parent_id={doc['parent_id']}. Removing parent_id."
                )
                await collection.update_one(
                    {"_id": doc["_id"]}, {"$set": {"parent_id": None}}
                )

            # Check for inconsistent hierarchies (parent level != child level - 1)
            pipeline = [
                {
                    "$match": {
                        **self._active_confluence_filter(bot_id),
                        "parent_id": {"$ne": None},
                        "level": {"$gt": 0},
                    }
                },
                {
                    "$lookup": {
                        "from": "documents",
                        "localField": "parent_id",
                        "foreignField": "_id",
                        "as": "parent",
                    }
                },
                {"$unwind": "$parent"},
                {
                    "$match": {
                        "parent.deleted": {"$ne": True},
                        "$or": [
                            {"parent.source": "confluence"},
                            {"parent.source_type": "confluence"},
                        ],
                    }
                },
                {
                    "$match": {
                        "$expr": {"$ne": ["$level", {"$add": ["$parent.level", 1]}]}
                    }
                },
                {
                    "$project": {
                        "external_id": 1,
                        "level": 1,
                        "external_parent_id": "$parent.external_id",
                        "parent_level": "$parent.level",
                    }
                },
            ]
            cursor = collection.aggregate(pipeline)

            inconsistent_count = 0
            async for doc in cursor:
                inconsistent_count += 1
                expected_level = doc["parent_level"] + 1
                logger.warning(
                    f"Inconsistent hierarchy: child {doc['external_id']} at level {doc['level']}, "
                    f"parent {doc['external_parent_id']} at level {doc['parent_level']}. "
                    f"Expected child level: {expected_level}"
                )
                await collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"level": expected_level}},
                )

            if inconsistent_count > 0:
                logger.warning(f"Fixed {inconsistent_count} inconsistent hierarchies")

        except Exception as e:
            logger.error(f"Error verifying hierarchies: {str(e)}")
            raise
