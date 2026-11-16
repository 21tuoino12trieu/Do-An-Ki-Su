from typing import Optional, List
from beegenerate.configs.yaml_model import YamlModel
from beegenerate.const import BEEGEN_ROOT
from enum import Enum


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
    
    
class RedisConfig(YamlModel):
    """Configuration for Redis connection settings.

    This class defines the parameters needed to establish and maintain
    a connection with a Redis server or cluster.

    Attributes:
        host (str): The hostname or IP address of the Redis server.
        port (int): The port number the Redis server is listening on. Default is 6379.
        password (Optional[str]): The password for authenticating with the Redis server.
            Default is None (no authentication).
        db (int): The Redis database index to use. Default is 0.
        ssl (bool): Whether to use SSL/TLS for the connection. Default is False.
        timeout (float): Connection timeout in seconds. Default is 5.0.
        socket_keepalive (bool): Whether to use socket keepalive. Default is False.
        socket_timeout (float): Socket timeout in seconds. Default is 5.0.
        connection_pool_size (int): Maximum number of connections in the pool. Default is 10.
        decode_responses (bool): Whether to decode responses from Redis. Default is True.
    """
    host: str
    port: int = 6379
    username: Optional[str] = None
    password: Optional[str] = None
    db: int = 0
    ssl: bool = False
    timeout: float = 5.0
    socket_keepalive: bool = False
    socket_timeout: float = 5.0
    connection_pool_size: int = 10
    decode_responses: bool = True
    
    @classmethod
    def default(cls) -> 'RedisConfig':
        """Load default config"""
        dict = RedisConfig.read_yaml(BEEGEN_ROOT / "config/redis.yaml")
        return RedisConfig(**dict)


if __name__ == "__main__":
    # log_config.to_yaml_file(Path('log_config.yaml'))
    log_config = RedisConfig.default()
    print(log_config)