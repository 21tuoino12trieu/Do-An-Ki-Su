"""
MongoDB Service - Lưu trữ WorkflowLog.
"""

import structlog
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from src.config.settings import settings
from src.models.message import WorkflowLog
from src.models.exceptions import MongoWriteFailedError
from src.utils.aes import aes_decode

logger = structlog.get_logger(__name__)

class MongoService:
    def __init__(self):
        self._client: MongoClient | None = None
        self._collection = None
        self.uri = self._get_uri()

    def _get_uri(self) -> str:
        if settings.ai_mongodb_cua_username and settings.ai_mongodb_cua_password:
            return (
                f"mongodb://{settings.ai_mongodb_cua_username}:{aes_decode(settings.ai_mongodb_cua_password)}"
                f"@{settings.ai_mongodb_cua_url_suffix}"
            )
        else:
            return f"mongodb://{settings.ai_mongodb_cua_url_suffix}"

    def connect(self):
        self._client = MongoClient(self.uri)
        db = self._client[settings.mongo_db]
        self._collection = db[settings.mongo_collection_logs]
        logger.info("mongodb_connected", db=settings.mongo_db, collection=settings.mongo_collection_logs)

    def disconnect(self):
        if self._client:
            self._client.close()
            logger.info("mongodb_disconnected")

    def save_log(self, log: WorkflowLog) -> None:
        """
        Lưu WorkflowLog vào MongoDB.

        Raises:
            MongoWriteFailedError: Khi không ghi được.
        """
        try:
            doc = log.model_dump()
            doc["created_at"] = doc["created_at"].isoformat()
            doc["updated_at"] = doc["updated_at"].isoformat()
            self._collection.insert_one(doc)
            logger.info("log_saved", request_id=log.request_id, status=log.status)
        except PyMongoError as e:
            logger.error("mongo_save_failed", request_id=log.request_id, error=str(e))
            raise MongoWriteFailedError(
                f"Không thể lưu log cho request_id={log.request_id}", cause=e
            )
        
    def update_status(self, request_id: str, status: str, dag_run_id: str | None = None, retry_count: int = 0):
        """Cập nhật trạng thái của một log entry."""
        try:
            fields: dict = {"status": status, "retry_count": retry_count}
            if dag_run_id:
                fields["dag_run_id"] = dag_run_id
            self._collection.update_one(
                {"request_id": request_id},
                {"$set": fields},
                upsert=False,
            )
        except PyMongoError as e:
            logger.error("mongo_update_failed", request_id=request_id, error=str(e))


# Singleton
mongo_service = MongoService()