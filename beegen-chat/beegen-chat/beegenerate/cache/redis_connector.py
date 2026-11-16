import redis
from typing import Any, Dict, Union, List
from pathlib import Path

from beegenerate.configs.cache.redis_config import RedisConfig, RedisOperation
from beegenerate.loggings import LOGGER


class RedisConnector:
    """Redis connection manager for the beegen framework.

    This class provides a Redis client connection and common Redis operations
    for caching, storing and retrieving data, and pub/sub operations.

    Attributes:
        config (RedisConfig): The Redis connection configuration.
        client (redis.Redis): The Redis client instance.
    """

    def __init__(self, config: RedisConfig):
        """Initialize a Redis connector with the provided configuration.

        Args:
            config (RedisConfig): Redis connection configuration.
        """
        self.config = config
        self.client = self._create_connection()

    def _create_connection(self) -> redis.Redis:
        """Create a Redis client based on configuration.

        Returns:
            redis.Redis: Configured Redis client instance.
        """
        try:
            client = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
                db=self.config.db,
                ssl=self.config.ssl,
                socket_timeout=self.config.socket_timeout,
                socket_keepalive=self.config.socket_keepalive,
                connection_pool=redis.ConnectionPool(
                    host=self.config.host,
                    port=self.config.port,
                    username=self.config.username,
                    password=self.config.password,
                    db=self.config.db,
                    max_connections=self.config.connection_pool_size,
                    decode_responses=self.config.decode_responses
                )
            )
            # Test connection
            client.ping()
            LOGGER.info("Successfully connected to Redis at %s:%s", self.config.host, self.config.port)
            return client
        except redis.ConnectionError as e:
            LOGGER.error("Failed to connect to Redis: %s", str(e))
            raise
        
    @classmethod
    def from_path(cls, config_path: Union[str, Path]) -> 'RedisConnector':
        """Create a RedisConnector from a YAML configuration file.

        Args:
            config_path (Union[str, Path]): Path to the Redis configuration YAML file.

        Returns:
            RedisConnector: Initialized Redis connector.
        """
        config = RedisConfig.from_yaml_file(config_path)
        return cls(config=config)
    
    def run(
        self, 
        operation_type: Union[RedisOperation, str], 
        params: Dict[str, Any]
    ) -> Any:
        """Execute a Redis operation based on the specified operation type and parameters.

        Args:
            operation_type (Union[RedisOperation, str]): The type of Redis operation to perform.
            params (Dict[str, Any]): Parameters for the operation.

        Returns:
            Any: The result of the operation, varies based on the operation type.

        Raises:
            ValueError: If required parameters are missing or invalid operation type is provided.
            Exception: If the operation fails.
        """
        if isinstance(operation_type, str):
            try:
                operation_type = RedisOperation(operation_type.lower())
            except ValueError:
                raise ValueError(f"Invalid Redis operation: {operation_type}")

        try:
            # Validate and extract required parameters
            if operation_type == RedisOperation.GET:
                self._validate_params(params, ["key"])
                return self.client.get(params["key"])
                
            elif operation_type == RedisOperation.SET:
                self._validate_params(params, ["key", "value"])
                ex = params.get("seconds")
                return self.client.set(params["key"], params["value"], ex=ex)
                
            elif operation_type == RedisOperation.DELETE:
                self._validate_params(params, ["key"])
                return bool(self.client.delete(params["key"]))
                
            elif operation_type == RedisOperation.EXISTS:
                self._validate_params(params, ["key"])
                return bool(self.client.exists(params["key"]))
                
            elif operation_type == RedisOperation.EXPIRE:
                self._validate_params(params, ["key", "seconds"])
                return bool(self.client.expire(params["key"], params["seconds"]))
                
            elif operation_type == RedisOperation.TTL:
                self._validate_params(params, ["key"])
                return self.client.ttl(params["key"])
                
            elif operation_type == RedisOperation.INCR:
                self._validate_params(params, ["key"])
                return self.client.incr(params["key"])
                
            elif operation_type == RedisOperation.DECR:
                self._validate_params(params, ["key"])
                return self.client.decr(params["key"])
                
            # Hash operations
            elif operation_type == RedisOperation.HGET:
                self._validate_params(params, ["key", "field"])
                return self.client.hget(params["key"], params["field"])
                
            elif operation_type == RedisOperation.HGETALL:
                self._validate_params(params, ["key"])
                return self.client.hgetall(params["key"])
                
            elif operation_type == RedisOperation.HSET:
                self._validate_params(params, ["key", "field", "value"])
                return bool(self.client.hset(params["key"], params["field"], params["value"]))
                
            elif operation_type == RedisOperation.HMSET:
                self._validate_params(params, ["key", "fields"])
                return bool(self.client.hset(params["key"], mapping=params["fields"]))
                
            elif operation_type == RedisOperation.HDEL:
                self._validate_params(params, ["key", "field"])
                return bool(self.client.hdel(params["key"], params["field"]))
                
            # List operations
            elif operation_type == RedisOperation.LPUSH:
                self._validate_params(params, ["key", "value"])
                return self.client.lpush(params["key"], params["value"])
                
            elif operation_type == RedisOperation.RPUSH:
                self._validate_params(params, ["key", "value"])
                return self.client.rpush(params["key"], params["value"])
                
            elif operation_type == RedisOperation.LPOP:
                self._validate_params(params, ["key"])
                return self.client.lpop(params["key"])
                
            elif operation_type == RedisOperation.RPOP:
                self._validate_params(params, ["key"])
                return self.client.rpop(params["key"])
                
            elif operation_type == RedisOperation.LRANGE:
                self._validate_params(params, ["key", "start", "end"])
                return self.client.lrange(params["key"], params["start"], params["end"])
                
            # Set operations
            elif operation_type == RedisOperation.SADD:
                self._validate_params(params, ["key", "value"])
                return bool(self.client.sadd(params["key"], params["value"]))
                
            elif operation_type == RedisOperation.SMEMBERS:
                self._validate_params(params, ["key"])
                return self.client.smembers(params["key"])
                
            elif operation_type == RedisOperation.SREM:
                self._validate_params(params, ["key", "value"])
                return bool(self.client.srem(params["key"], params["value"]))
                
            # Sorted set operations
            elif operation_type == RedisOperation.ZADD:
                self._validate_params(params, ["key", "score", "value"])
                return self.client.zadd(params["key"], {params["value"]: params["score"]})
                
            elif operation_type == RedisOperation.ZRANGE:
                self._validate_params(params, ["key", "start", "end"])
                withscores = params.get("withscores", False)
                return self.client.zrange(params["key"], params["start"], params["end"], withscores=withscores)
                
            elif operation_type == RedisOperation.ZRANK:
                self._validate_params(params, ["key", "value"])
                return self.client.zrank(params["key"], params["value"])
                
            # Pub/Sub operations
            elif operation_type == RedisOperation.PUBLISH:
                self._validate_params(params, ["channel", "message"])
                return self.client.publish(params["channel"], params["message"])
                
            # Scanning operations
            elif operation_type == RedisOperation.SCAN:
                cursor = params.get("cursor", 0)
                match = params.get("pattern", "*")
                count = params.get("count", 10)
                return self.client.scan(cursor=cursor, match=match, count=count)
                
            else:
                raise ValueError(f"Unsupported Redis operation: {operation_type}")
                
        except Exception as e:
            operation_name = operation_type.value if hasattr(operation_type, 'value') else str(operation_type)
            LOGGER.error(f"Error executing Redis {operation_name} operation: {str(e)}")
            raise
        
    def _validate_params(self, params: Dict[str, Any], required_keys: List[str]) -> None:
        """Validate that all required parameters are present.

        Args:
            params (Dict[str, Any]): The parameters dictionary to validate.
            required_keys (List[str]): List of required parameter keys.

        Raises:
            ValueError: If any required parameters are missing.
        """
        missing_keys = [key for key in required_keys if key not in params]
        if missing_keys:
            raise ValueError(f"Missing required parameters: {', '.join(missing_keys)}")

    def close(self) -> None:
        """Close the Redis connection."""
        try:
            self.client.close()
            LOGGER.info("Closed Redis connection")
        except Exception as e:
            LOGGER.error(f"Error closing Redis connection: {str(e)}")
            

async def main():
    from beegenerate.registry.model_registry import ModelRegistry   
    
    # Initialize connector
    redis_conn = ModelRegistry.self().redis("nlp_user")
    
    # Use run method for SET operation
    redis_conn.run(
        operation_type=RedisOperation.SET,
        params={"key": "test_key", "value": "Hello Redis!", "seconds": 3600}
    )
    
    # Use run method for GET operation
    value = redis_conn.run(
        operation_type=RedisOperation.GET,
        params={"key": "test_key"}
    )
    print(f"Retrieved value: {value}")
    
    # Use run method for hash operations
    redis_conn.run(
        operation_type=RedisOperation.HMSET,
        params={
            "key": "user:1001",
            "fields": {
                "name": "John Doe",
                "email": "john@example.com",
                "age": "30"
            }
        }
    )
    
    user_data = redis_conn.run(
        operation_type=RedisOperation.HGETALL,
        params={"key": "user:1001"}
    )
    print(f"User data: {user_data}")
    
    # Clean up
    redis_conn.run(
        operation_type=RedisOperation.DELETE,
        params={"key": "test_key"}
    )
    redis_conn.run(
        operation_type=RedisOperation.DELETE,
        params={"key": "user:1001"}
    )
    
    redis_conn.close()
    

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())