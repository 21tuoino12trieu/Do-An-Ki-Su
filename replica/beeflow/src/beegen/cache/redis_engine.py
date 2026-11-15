import redis
from redis import exceptions as redis_exc
from typing import Any, Dict, Union, List, Optional, Tuple
from pathlib import Path
from redis.sentinel import Sentinel

from beegen.configs.cache.redis_config import RedisConfig, RedisOperation
from beegen.loggings import LOGGER


class RedisEngine:
    """Redis connection manager for the beegen framework.

    This class provides a Redis client connection and common Redis operations
    for caching, storing and retrieving data, and pub/sub operations.
    """

    def __init__(self, config: RedisConfig):
        self.config = config
        self.client = self._create_connection()

        # Operation map: function signatures mirror REDIS_OPERATION_INPUTS
        self.operation_map = {
            # Strings / keys
            RedisOperation.GET: self._op_get,
            RedisOperation.SET: self._op_set,
            RedisOperation.DELETE: self._op_delete,
            RedisOperation.EXISTS: self._op_exists,
            RedisOperation.EXPIRE: self._op_expire,
            RedisOperation.TTL: self._op_ttl,
            RedisOperation.INCR: self._op_incr,
            RedisOperation.DECR: self._op_decr,

            # Hashes
            RedisOperation.HGET: self._op_hget,
            RedisOperation.HGETALL: self._op_hgetall,
            RedisOperation.HSET: self._op_hset,
            RedisOperation.HMSET: self._op_hmset,
            RedisOperation.HDEL: self._op_hdel,

            # Lists
            RedisOperation.LPUSH: self._op_lpush,
            RedisOperation.RPUSH: self._op_rpush,
            RedisOperation.LPOP: self._op_lpop,
            RedisOperation.RPOP: self._op_rpop,
            RedisOperation.LRANGE: self._op_lrange,

            # Sets
            RedisOperation.SADD: self._op_sadd,
            RedisOperation.SMEMBERS: self._op_smembers,
            RedisOperation.SREM: self._op_srem,

            # Sorted sets
            RedisOperation.ZADD: self._op_zadd,
            RedisOperation.ZRANGE: self._op_zrange,
            RedisOperation.ZRANK: self._op_zrank,

            # Pub/Sub
            RedisOperation.PUBLISH: self._op_publish,

            # Scan
            RedisOperation.SCAN: self._op_scan,

            # Setex
            RedisOperation.SETEX: self._op_setex,
        }

    # ---------------------------------------------------------------------
    # Connection
    # ---------------------------------------------------------------------
    def _create_connection(self) -> redis.Redis:
        is_sentinel, client_kwargs, sentinel_ctor = self.config.to_redis_kwargs()
        try:
            if is_sentinel:
                # Build Sentinel and get a master-aware client
                sentinel = Sentinel(**sentinel_ctor)
                client = sentinel.master_for(self.config.master_name, **client_kwargs)
                # Quick health check
                client.ping()
                LOGGER.info(
                    "Connected via Sentinel to Redis master '%s' (db=%s) at '%s'",
                    self.config.master_name,
                    self.config.db,
                    self.config.sentinels
                )
                return client

            # Direct mode with explicit ConnectionPool
            pool = redis.ConnectionPool(
                **{k: v for k, v in client_kwargs.items() if k in {
                    "host", "port", "db", "username", "password",
                    "socket_timeout", "socket_connect_timeout",
                    "socket_keepalive", "retry_on_timeout",
                    "decode_responses", "client_name", "ssl",
                    "max_connections",
                }}
            )
            client = redis.Redis(connection_pool=pool)
            client.ping()
            LOGGER.info(
                "Connected to Redis at %s:%s (db=%s)",
                client_kwargs.get("host"),
                client_kwargs.get("port"),
                self.config.db,
            )
            return client

        except redis_exc.ConnectionError as e:
            LOGGER.error("Failed to connect to Redis: %s", str(e))
            raise

    @classmethod
    def from_path(cls, config_path: str) -> "RedisEngine":
        """Create a RedisEngine from a YAML configuration file.

        Args:
            config_path (str): Path to the Redis configuration YAML file.

        Returns:
            RedisEngine: Initialized Redis connector.
        """
        config = RedisConfig.from_yaml_file(Path(config_path))
        return cls(config=config)

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def run(self, operation_type: Union[RedisOperation, str], params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a Redis operation, returning a normalized dict.
        Accepts params and unpacks into the target op function.

        Args:
            operation_type: RedisOperation or string name (case-insensitive)
            params: input parameters for the operation

        Returns:
            Dict[str, Any]: normalized output per REDIS_OPERATION_OUTPUTS
        """
        if isinstance(operation_type, str):
            try:
                operation_type = RedisOperation(operation_type.lower())
            except ValueError:
                return {
                    "status": "error",
                    "message": f"Invalid Redis operation: {operation_type}"
                }

        fn = self.operation_map.get(operation_type)
        if not fn:
            return {
                "status": "error",
                "message": f"Unsupported Redis operation: {operation_type}"
            }

        try:
            result = fn(**(params or {}))

            # Add operation success message if not present
            if 'message' not in result:
                op_name = operation_type.value.replace('_', ' ')
                result['message'] = f"Operation {op_name} completed successfully"

            return result

        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            op_name = getattr(operation_type, "value", str(operation_type))
            LOGGER.error("Redis operation '%s' failed: %s", op_name, error_traceback)
            return {
                "status": "error",
                "message": str(error_traceback)
            }

    def close(self) -> None:
        try:
            self.client.close()
            LOGGER.info("Closed Redis connection")
        except Exception as e:
            LOGGER.error("Error closing Redis connection: %s", str(e))

    # ---------------------------------------------------------------------
    # Operations (typed, direct params; exceptions bubble up)
    # ---------------------------------------------------------------------
    # Strings / keys
    def _op_get(self, *, key: str) -> Dict[str, Any]:
        value = self.client.get(key)
        return {"status": "success", "value": value}

    def _op_set(self, *, key: str, value: Any) -> Dict[str, Any]:
        ok = bool(self.client.set(key, value))
        return {"status": "success", "ok": ok}

    def _op_delete(self, *, keys: List[str]) -> Dict[str, Any]:
        deleted = int(self.client.delete(*keys))
        return {"status": "success", "deleted_count": deleted}

    def _op_exists(self, *, key: str) -> Dict[str, Any]:
        exists = bool(self.client.exists(key))
        return {"status": "success", "exists": exists}

    def _op_expire(self, *, key: str, seconds: int) -> Dict[str, Any]:
        success = bool(self.client.expire(key, int(seconds)))
        return {"status": "success", "success": success}

    def _op_ttl(self, *, key: str) -> Dict[str, Any]:
        ttl = int(self.client.ttl(key))
        return {"status": "success", "ttl": ttl}

    def _op_incr(self, *, key: str) -> Dict[str, Any]:
        val = int(self.client.incr(key))
        return {"status": "success", "value": val}

    def _op_decr(self, *, key: str) -> Dict[str, Any]:
        val = int(self.client.decr(key))
        return {"status": "success", "value": val}

    # Hashes
    def _op_hget(self, *, key: str, field: str) -> Dict[str, Any]:
        value = self.client.hget(key, field)
        return {"status": "success", "value": value}

    def _op_hgetall(self, *, key: str) -> Dict[str, Any]:
        value = self.client.hgetall(key)
        return {"status": "success", "value": value}

    def _op_hset(self, *, key: str, field: str, value: Any) -> Dict[str, Any]:
        updated = int(self.client.hset(key, field, value))
        return {"status": "success", "updated_count": updated}

    def _op_hmset(self, *, key: str, mapping: Dict[str, Any]) -> Dict[str, Any]:
        updated = int(self.client.hset(key, mapping=mapping))
        return {"status": "success", "updated_count": updated}

    def _op_hdel(self, *, key: str, fields: List[str]) -> Dict[str, Any]:
        deleted = int(self.client.hdel(key, *fields))
        return {"status": "success", "deleted_count": deleted}

    # Lists
    def _op_lpush(self, *, key: str, values: List[Any]) -> Dict[str, Any]:
        length = int(self.client.lpush(key, *values))
        return {"status": "success", "length": length}

    def _op_rpush(self, *, key: str, values: List[Any]) -> Dict[str, Any]:
        length = int(self.client.rpush(key, *values))
        return {"status": "success", "length": length}

    def _op_lpop(self, *, key: str) -> Dict[str, Any]:
        value = self.client.lpop(key)
        return {"status": "success", "value": value}

    def _op_rpop(self, *, key: str) -> Dict[str, Any]:
        value = self.client.rpop(key)
        return {"status": "success", "value": value}

    def _op_lrange(self, *, key: str, start: int, stop: int) -> Dict[str, Any]:
        values = self.client.lrange(key, int(start), int(stop))
        return {"status": "success", "values": values}

    # Sets
    def _op_sadd(self, *, key: str, members: List[Any]) -> Dict[str, Any]:
        added = int(self.client.sadd(key, *members))
        return {"status": "success", "added_count": added}

    def _op_smembers(self, *, key: str) -> Dict[str, Any]:
        members = list(self.client.smembers(key))
        return {"status": "success", "members": members}

    def _op_srem(self, *, key: str, members: List[Any]) -> Dict[str, Any]:
        removed = int(self.client.srem(key, *members))
        return {"status": "success", "removed_count": removed}

    # Sorted sets
    def _op_zadd(self, *, key: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        # items = [{"member": Any, "score": float}, ...]
        mapping = {i["member"]: float(i["score"]) for i in items}
        added = int(self.client.zadd(key, mapping))
        return {"status": "success", "added_count": added}

    def _op_zrange(self, *, key: str, start: int, stop: int, with_scores: bool = False) -> Dict[str, Any]:
        members = self.client.zrange(key, int(start), int(stop), withscores=bool(with_scores))
        return {"status": "success", "members": members}

    def _op_zrank(self, *, key: str, member: Any) -> Dict[str, Any]:
        rank = self.client.zrank(key, member)
        return {"status": "success", "rank": rank if rank is not None else None}

    # Pub/Sub
    def _op_publish(self, *, channel: str, input_message: Any) -> Dict[str, Any]:
        receivers = int(self.client.publish(channel, input_message))
        return {"status": "success", "receivers": receivers}

    # Scan
    def _op_scan(self, *, cursor: int, match: Optional[str] = None, count: Optional[int] = None) -> Dict[str, Any]:
        next_cursor, keys = self.client.scan(cursor=int(cursor), match=match, count=count)
        return {"status": "success", "next_cursor": int(next_cursor), "keys": keys}

    # Setex
    def _op_setex(self, *, key: str, value: Any, seconds: int) -> Dict[str, Any]:
        ok = bool(self.client.setex(key, int(seconds), value))
        return {"status": "success", "ok": ok}


# ---------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------
def _print(title: str, data: Dict[str, Any]) -> None:
    print(f"\n=== {title} ===")
    for k, v in data.items():
        print(f"{k}: {v}")


def example() -> None:
    import json
    # Using a YAML file
    engine = RedisEngine.from_path("config/redis.yaml")

    # Or use RESOURCE_HUB
    # from beegen.registry.resource_hub import RESOURCE_HUB
    # engine = RESOURCE_HUB.redis("aicenter-chatbot")

    try:
        # SET + GET
        _print("SET", engine.run(RedisOperation.SET, {"key": "hello", "value": "world"}))
        _print("GET", engine.run(RedisOperation.GET, {"key": "hello"}))

        # HASH
        _print("HMSET", engine.run(RedisOperation.HMSET, {
            "key": "user:1001",
            "mapping": {"name": "John", "email": "john@example.com", "age": "30"}
        }))
        _print("HGETALL", engine.run(RedisOperation.HGETALL, {"key": "user:1001"}))

        # LIST
        _print("RPUSH", engine.run(RedisOperation.RPUSH, {"key": "logs", "values": ["a", "b", "c"]}))
        _print("LRANGE", engine.run(RedisOperation.LRANGE, {"key": "logs", "start": 0, "stop": -1}))
        _print("RPOP", engine.run(RedisOperation.RPOP, {"key": "logs"}))

        # SET (collection)
        _print("SADD", engine.run(RedisOperation.SADD, {"key": "features", "members": ["x", "y", "z"]}))
        _print("SMEMBERS", engine.run(RedisOperation.SMEMBERS, {"key": "features"}))

        # ZSET
        _print("ZADD", engine.run(RedisOperation.ZADD, {
            "key": "scores",
            "items": [{"member": "alice", "score": 10.0}, {"member": "bob", "score": 7.5}]
        }))
        _print("ZRANGE", engine.run(RedisOperation.ZRANGE, {"key": "scores", "start": 0, "stop": -1, "with_scores": True}))
        _print("ZRANK(alice)", engine.run(RedisOperation.ZRANK, {"key": "scores", "member": "alice"}))

        # TTL / EXPIRE / EXISTS
        _print("EXISTS(hello)", engine.run(RedisOperation.EXISTS, {"key": "hello"}))
        _print("TTL(hello)", engine.run(RedisOperation.TTL, {"key": "hello"}))
        _print("EXPIRE(hello->120s)", engine.run(RedisOperation.EXPIRE, {"key": "hello", "seconds": 120}))
        _print("TTL(hello)", engine.run(RedisOperation.TTL, {"key": "hello"}))

        # PUBLISH
        # _print("PUBLISH", engine.run(RedisOperation.PUBLISH, {"channel": "events", "message": json.dumps({"type": "ping"})}))

        # SCAN
        _print("SCAN", engine.run(RedisOperation.SCAN, {"cursor": 0, "match": "u*", "count": 5}))

        # DELETE
        _print("DELETE keys", engine.run(RedisOperation.DELETE, {"keys": ["hello", "user:1001", "scores", "logs", "features"]}))

        # SETEX
        _print("SETEX", engine.run(RedisOperation.SETEX, {
            "key": "session:abc",
            "value": "user_data",
            "seconds": 3600
        }))
        _print("TTL(session:abc)", engine.run(RedisOperation.TTL, {"key": "session:abc"}))

    finally:
        engine.close()


if __name__ == "__main__":
    example()