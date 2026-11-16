"""
Redis Sentinel Service

Kết nối Redis qua Sentinel để đảm bảo high availability:
  - Sentinel tự động phát hiện master node
  - Tự động failover khi master down
  - Decode responses thành string

Cấu hình qua env:
  REDIS_SENTINEL_HOSTS       = host1:26379,host2:26379,host3:26379
  REDIS_SENTINEL_MASTER_NAME = mymaster
  REDIS_SENTINEL_USER        = redis_user
  REDIS_SENTINEL_PASSWORD    = redis_password
  REDIS_DB                   = 0
  REDIS_SOCKET_TIMEOUT       = 5
"""

import structlog
from redis.sentinel import Sentinel
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError

from config.settings import settings

logger = structlog.get_logger(__name__)


class RedisService:
    def __init__(self):
        self.sentinel_obj: Sentinel | None = None
        self.client = None

    def connect(self) -> None:
        """
        Khởi tạo Sentinel client và lấy kết nối tới master.

        Raises:
            RedisConnectionError: Nếu không kết nối được Sentinel.
        """
        sentinel_hosts = settings.redis_sentinel_host_list
        master_name    = settings.redis_sentinel_master_name
        sentinel_user  = settings.redis_sentinel_user or None
        sentinel_pass  = settings.redis_sentinel_password or None
        db             = settings.redis_db
        timeout        = settings.redis_socket_timeout

        logger.info(
            "redis_sentinel_connecting",
            sentinel_hosts=sentinel_hosts,
            master_name=master_name,
            db=db,
        )

        try:
            self.sentinel_obj = Sentinel(
                sentinel_hosts,
                socket_timeout=timeout,
                password=sentinel_pass,
                sentinel_kwargs={
                    "username": sentinel_user,
                    "password": sentinel_pass,
                },
            )

            self.client = self.sentinel_obj.master_for(
                service_name=master_name,
                db=db,
                username=sentinel_user,
                password=sentinel_pass,
                decode_responses=True,
            )

            # Ping kiểm tra kết nối thực sự
            self.client.ping()

            logger.info(
                "redis_sentinel_connected",
                master_name=master_name,
                db=db,
            )

        except RedisConnectionError as e:
            logger.error(
                "redis_sentinel_connection_failed",
                error=str(e),
                sentinel_hosts=sentinel_hosts,
            )
            raise
        except Exception as e:
            logger.error("redis_sentinel_unexpected_error", error=str(e))
            raise

    def disconnect(self) -> None:
        """Đóng kết nối Redis."""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        logger.info("redis_disconnected")

    # ─── Cache operations ──────────────────────────────────────────────────────

    def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        """
        Lưu giá trị vào Redis.

        Args:
            key:   Cache key.
            value: Giá trị string (JSON dump nếu cần).
            ttl:   Thời gian sống (giây). None = không hết hạn.

        Returns:
            True nếu thành công, False nếu thất bại.
        """
        try:
            if ttl:
                self.client.setex(key, ttl, value)
            else:
                self.client.set(key, value)
            logger.debug("redis_set_ok", key=key, ttl=ttl)
            return True
        except RedisError as e:
            logger.error("redis_set_failed", key=key, error=str(e))
            return False

    def get(self, key: str) -> str | None:
        """
        Lấy giá trị từ Redis.

        Returns:
            Giá trị string hoặc None nếu key không tồn tại / lỗi.
        """
        try:
            value = self.client.get(key)
            logger.debug("redis_get_ok", key=key, found=(value is not None))
            return value
        except RedisError as e:
            logger.error("redis_get_failed", key=key, error=str(e))
            return None

    def delete(self, key: str) -> bool:
        """Xóa key khỏi Redis."""
        try:
            self.client.delete(key)
            return True
        except RedisError as e:
            logger.error("redis_delete_failed", key=key, error=str(e))
            return False

    def exists(self, key: str) -> bool:
        """Kiểm tra key có tồn tại không."""
        try:
            return bool(self.client.exists(key))
        except RedisError as e:
            logger.error("redis_exists_failed", key=key, error=str(e))
            return False

    def ping(self) -> bool:
        """Kiểm tra kết nối còn sống không."""
        try:
            return self.client.ping()
        except RedisError:
            return False


# Singleton
redis_service = RedisService()