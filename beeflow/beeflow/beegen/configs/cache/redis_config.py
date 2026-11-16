from typing import Dict, Optional, List, Any, Tuple
from beegen.configs.yaml_model import YamlModel
from beegen.const import BEEGEN_ROOT
from enum import Enum
from pydantic import Field
from beegen.tools.schema.param import ParamSet


class RedisOperation(str, Enum):
    GET = "get"
    SET = "set"
    DELETE = "delete"
    EXISTS = "exists"
    EXPIRE = "expire"
    TTL = "ttl"
    INCR = "incr"
    DECR = "decr"
    HGET = "hget"
    HGETALL = "hgetall"
    HSET = "hset"
    HMSET = "hmset"
    HDEL = "hdel"
    LPUSH = "lpush"
    RPUSH = "rpush"
    LPOP = "lpop"
    RPOP = "rpop"
    LRANGE = "lrange"
    SADD = "sadd"
    SMEMBERS = "smembers"
    SREM = "srem"
    ZADD = "zadd"
    ZRANGE = "zrange"
    ZRANK = "zrank"
    PUBLISH = "publish"
    SCAN = "scan"
    SETEX = "setex"
    
# Helper
def PS(*vars_):
    """
    Build a ParamSet with concise English descriptions.
    Each item: {"name": "key: str", "required": True/False, "description": "text"}
    """
    b = ParamSet.new()
    for v in vars_:
        b = b.var(
            v["name"],
            required=v.get("required", False),
            description=v.get("description")
        )
    return b.build()

# ========= INPUT SCHEMAS =========
REDIS_OPERATION_INPUTS = {
    # Strings / keys
    RedisOperation.GET: PS(
        {"name": "key: str", "required": True, "description": "Key to read"}
    ),
    RedisOperation.SET: PS(
        {"name": "key: str", "required": True, "description": "Key to write"},
        {"name": "value: Any", "required": True, "description": "Value to store"},
    ),
    RedisOperation.DELETE: PS(
        {"name": "keys: List[str]", "required": True, "description": "Keys to remove"}
    ),
    RedisOperation.EXISTS: PS(
        {"name": "key: str", "required": True, "description": "Key to check"}
    ),
    RedisOperation.EXPIRE: PS(
        {"name": "key: str", "required": True, "description": "Key to set TTL"},
        {"name": "seconds: int", "required": True, "description": "Expiration in seconds"},
    ),
    RedisOperation.TTL: PS(
        {"name": "key: str", "required": True, "description": "Key to inspect TTL"}
    ),
    RedisOperation.INCR: PS(
        {"name": "key: str", "required": True, "description": "Counter key to increment"}
    ),
    RedisOperation.DECR: PS(
        {"name": "key: str", "required": True, "description": "Counter key to decrement"}
    ),

    # Hashes
    RedisOperation.HGET: PS(
        {"name": "key: str", "required": True, "description": "Hash key"},
        {"name": "field: str", "required": True, "description": "Field to fetch"},
    ),
    RedisOperation.HGETALL: PS(
        {"name": "key: str", "required": True, "description": "Hash key"}
    ),
    RedisOperation.HSET: PS(
        {"name": "key: str", "required": True, "description": "Hash key"},
        {"name": "field: str", "required": True, "description": "Field to set"},
        {"name": "value: Any", "required": True, "description": "Value to set"},
    ),
    RedisOperation.HMSET: PS(
        {"name": "key: str", "required": True, "description": "Hash key"},
        {"name": "mapping: Dict[str, Any]", "required": True, "description": "Field-value map"},
    ),
    RedisOperation.HDEL: PS(
        {"name": "key: str", "required": True, "description": "Hash key"},
        {"name": "fields: List[str]", "required": True, "description": "Fields to remove"},
    ),

    # Lists
    RedisOperation.LPUSH: PS(
        {"name": "key: str", "required": True, "description": "List key"},
        {"name": "values: List[Any]", "required": True, "description": "Values to push left"},
    ),
    RedisOperation.RPUSH: PS(
        {"name": "key: str", "required": True, "description": "List key"},
        {"name": "values: List[Any]", "required": True, "description": "Values to push right"},
    ),
    RedisOperation.LPOP: PS(
        {"name": "key: str", "required": True, "description": "List key to pop from left"}
    ),
    RedisOperation.RPOP: PS(
        {"name": "key: str", "required": True, "description": "List key to pop from right"}
    ),
    RedisOperation.LRANGE: PS(
        {"name": "key: str", "required": True, "description": "List key"},
        {"name": "start: int", "required": True, "description": "Start index (inclusive)"},
        {"name": "stop: int", "required": True, "description": "Stop index (inclusive)"},
    ),

    # Sets
    RedisOperation.SADD: PS(
        {"name": "key: str", "required": True, "description": "Set key"},
        {"name": "members: List[Any]", "required": True, "description": "Members to add"},
    ),
    RedisOperation.SMEMBERS: PS(
        {"name": "key: str", "required": True, "description": "Set key"}
    ),
    RedisOperation.SREM: PS(
        {"name": "key: str", "required": True, "description": "Set key"},
        {"name": "members: List[Any]", "required": True, "description": "Members to remove"},
    ),

    # Sorted sets
    RedisOperation.ZADD: PS(
        {"name": "key: str", "required": True, "description": "Sorted set key"},
        {"name": "items: List[Dict]", "required": True, "description": "List of {'score': float, 'member': Any}"},
    ),
    RedisOperation.ZRANGE: PS(
        {"name": "key: str", "required": True, "description": "Sorted set key"},
        {"name": "start: int", "required": True, "description": "Start rank (inclusive)"},
        {"name": "stop: int", "required": True, "description": "Stop rank (inclusive)"},
        {"name": "with_scores: bool", "required": False, "description": "Include scores if True"},
    ),
    RedisOperation.ZRANK: PS(
        {"name": "key: str", "required": True, "description": "Sorted set key"},
        {"name": "member: Any", "required": True, "description": "Member to get rank for"},
    ),

    # Pub/Sub
    RedisOperation.PUBLISH: PS(
        {"name": "channel: str", "required": True, "description": "Channel name"},
        {"name": "input_message: Any", "required": True, "description": "Message to publish"},
    ),

    # Scan
    RedisOperation.SCAN: PS(
        {"name": "cursor: int", "required": True, "description": "Current cursor (use 0 to start)"},
        {"name": "match: str", "required": False, "description": "Glob pattern to filter keys"},
        {"name": "count: int", "required": False, "description": "Hint for batch size"},
    ),

    RedisOperation.SETEX: PS(
        {"name": "key: str", "required": True, "description": "Key to write"},
        {"name": "value: Any", "required": True, "description": "Value to store"},
        {"name": "seconds: int", "required": True, "description": "Expiration in seconds"},
    ),
}

# ========= OUTPUT SCHEMAS =========
REDIS_OPERATION_OUTPUTS = {
    RedisOperation.GET: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "value: Any", "required": False, "description": "Stored value or None"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.SET: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "ok: bool", "required": True, "description": "True if write succeeded"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.DELETE: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "deleted_count: int", "required": True, "description": "Number of keys removed"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.EXISTS: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "exists: bool", "required": True, "description": "True if key exists"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.EXPIRE: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "success: bool", "required": True, "description": "True if TTL set"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.TTL: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "ttl: int", "required": True, "description": "Seconds to expire (-1 no TTL, -2 missing)"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.INCR: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "value: int", "required": True, "description": "New counter value"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.DECR: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "value: int", "required": True, "description": "New counter value"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),

    RedisOperation.HGET: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "value: Any", "required": False, "description": "Field value or None"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.HGETALL: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "value: Dict[str, Any]", "required": True, "description": "Field-value map"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.HSET: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "updated_count: int", "required": True, "description": "Fields added/updated (0/1 per field)"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.HMSET: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "updated_count: int", "required": True, "description": "Fields added/updated"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.HDEL: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "deleted_count: int", "required": True, "description": "Fields removed"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),

    RedisOperation.LPUSH: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "length: int", "required": True, "description": "List length after push"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.RPUSH: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "length: int", "required": True, "description": "List length after push"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.LPOP: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "value: Any", "required": False, "description": "Popped value or None"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.RPOP: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "value: Any", "required": False, "description": "Popped value or None"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.LRANGE: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "values: List[Any]", "required": True, "description": "Slice of list values"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),

    RedisOperation.SADD: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "added_count: int", "required": True, "description": "New members added"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.SMEMBERS: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "members: List[Any]", "required": True, "description": "All members of the set"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.SREM: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "removed_count: int", "required": True, "description": "Members removed"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),

    RedisOperation.ZADD: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "added_count: int", "required": True, "description": "New members added"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.ZRANGE: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "members: List[Any]", "required": True, "description": "Members by rank (optionally with scores)"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
    RedisOperation.ZRANK: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "rank: int", "required": False, "description": "0-based rank or None if missing"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),

    RedisOperation.PUBLISH: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "receivers: int", "required": True, "description": "Subscribers that received the message"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),

    RedisOperation.SCAN: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "next_cursor: int", "required": True, "description": "Cursor for next scan (0 means done)"},
        {"name": "keys: List[str]", "required": True, "description": "Keys returned in this batch"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),

    RedisOperation.SETEX: PS(
        {"name": "status: str", "required": True, "description": "Operation status ('success' or 'error')"},
        {"name": "ok: bool", "required": True, "description": "True if write succeeded"},
        {"name": "message: str", "required": False, "description": "Message if status is not 'success'"}
    ),
}

class SentinelEndpoint(YamlModel):
    """Single Sentinel endpoint."""
    host: str
    port: int = Field(default=26379, ge=1, le=65535)


class SentinelAuth(YamlModel):
    """Optional auth for Sentinel itself (not the Redis DATA master)."""
    username: Optional[str] = None
    password: Optional[str] = None

class RedisConfig(YamlModel):
    """
    Redis configuration for direct connections or Sentinel.

    Expected YAML:
      master_name: "mymaster"
      sentinels:
        - { host: "10.0.0.11", port: 26379 }
        - { host: "10.0.0.12", port: 26379 }
      sentinel_auth:
        username: "sentinel-user"      # optional
        password: "sentinel-pass"      # optional
      username: "data-user"            # optional (DATA ACL)
      password: "data-pass"            # optional (DATA ACL)
      db: 0
      decode_responses: true
      connect_timeout: 5.0
      socket_timeout: 5.0
      socket_keepalive: false
      connection_pool_size: 10
      client_name: "beeflow-client"
      retry_on_timeout: true
    """
    # Direct connection (used when Sentinel is not configured).
    host: str = "127.0.0.1"
    port: int = Field(default=6379, ge=1, le=65535)

    # DATA (master) auth (not Sentinel)
    username: Optional[str] = None
    password: Optional[str] = None

    # DB & connection behaviors
    db: int = Field(default=0, ge=0)
    decode_responses: bool = True
    connect_timeout: float = Field(default=5.0, gt=0)
    socket_timeout: float = Field(default=5.0, gt=0)
    socket_keepalive: bool = False
    connection_pool_size: int = Field(default=10, gt=0)

    # Nice-to-have options mapping to redis-py
    client_name: Optional[str] = Field(default="beeflow-client")
    retry_on_timeout: bool = Field(default=True)

    # Optional Sentinel mode.
    master_name: Optional[str] = None
    sentinels: List[SentinelEndpoint] = Field(default_factory=list)
    sentinel_auth: Optional[SentinelAuth] = None

    ssl: bool = False

    # -------- Loaders --------
    @classmethod
    def default(cls) -> "RedisConfig":
        data = cls.read_yaml(BEEGEN_ROOT / "config/redis.yaml")
        return RedisConfig(**data)
    
    def to_redis_kwargs(self) -> Tuple[bool, Dict[str, Any], Dict[str, Any]]:
        """
        Build kwargs for redis clients.

        Returns:
            (is_sentinel, client_kwargs, sentinel_ctor_kwargs)

        - is_sentinel: True if Sentinel config is present
        - client_kwargs: kwargs for redis.Redis(...) or Sentinel.master_for(..., **client_kwargs)
        - sentinel_ctor_kwargs: kwargs for Sentinel(...). Empty if not sentinel
        """
        # Common client kwargs (used by both direct & sentinel master_for)
        client_kwargs: Dict[str, Any] = {
            "db": self.db,
            "username": self.username,
            "password": self.password,
            "socket_timeout": self.socket_timeout,
            "socket_connect_timeout": self.connect_timeout,  # redis-py uses socket_connect_timeout
            "socket_keepalive": self.socket_keepalive,
            "retry_on_timeout": self.retry_on_timeout,
            "decode_responses": self.decode_responses,
            "client_name": self.client_name,
            "ssl": self.ssl,
            # Pool size is applied via ConnectionPool; master_for will manage its own pool.
        }
        client_kwargs  = {k: v for k, v in client_kwargs.items() if v is not None}

        # Determine if we are in Sentinel mode
        has_sentinel = bool(self.master_name and self.sentinels)

        if not has_sentinel:
            # Direct mode: we must have host/port
            if not self.host:
                raise ValueError("Direct Redis mode requires 'host' (or configure Sentinel).")
            client_kwargs.update(
                {
                    "host": self.host,
                    "port": self.port or 6379,
                    "max_connections": self.connection_pool_size,
                }
            )
            return False, client_kwargs, {}

        # Sentinel mode ctor kwargs
        endpoints = [(e.host, e.port) for e in (self.sentinels or [])]
        if not endpoints:
            raise ValueError("Sentinel mode requires at least one sentinel endpoint.")

        # Auth to connect to Sentinel processes (NOT the Redis data auth)
        sentinel_auth_kwargs: Dict[str, Any] = {}
        if self.sentinel_auth:
            if self.sentinel_auth.username:
                sentinel_auth_kwargs["username"] = self.sentinel_auth.username
            if self.sentinel_auth.password:
                sentinel_auth_kwargs["password"] = self.sentinel_auth.password

        sentinel_ctor_kwargs: Dict[str, Any] = {
            "sentinels": endpoints,
            "socket_timeout": self.socket_timeout,
            "sentinel_kwargs": sentinel_auth_kwargs or None,
        }

        # client_kwargs already has DATA ACL (username/password), timeouts, etc.
        # master_for will use these to create the pooled client towards the master.
        return True, client_kwargs, sentinel_ctor_kwargs
    
if __name__ == "__main__":
    # log_config.to_yaml_file(Path('log_config.yaml'))
    from beegen.registry.resource_hub import ResourceHub
    from beegen.registry.resource_factory import ResourceFactory
    
    # ResourceFactory.create(redis_config)
