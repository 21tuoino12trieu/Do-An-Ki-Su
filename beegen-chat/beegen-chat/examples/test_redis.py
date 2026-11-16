import redis
import time

# Redis connection setup
REDIS_HOST = "10.215.107.47"
REDIS_PORT = 6379
REDIS_PASSWORD = "Speci@L1"
REDIS_USERNAME = "nlp_user"


def test_redis_basic_functions():
    # Connect to Redis
    r = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        username=REDIS_USERNAME,
        password=REDIS_PASSWORD,
        decode_responses=True  # Return strings instead of bytes
    )
    
    print("Testing Redis connection and basic operations...")
    
    try:
        # Test connection
        if r.ping():
            print("Successfully connected to Redis")
        else:
            print("Could not ping Redis server")
            return
        
        # Test string operations
        print("\n--- String Operations ---")
        r.set("test:string", "Hello Redis!")
        value = r.get("test:string")
        print(f"Set string value and got back: {value}")
        
        # Test expiration
        print("\n--- Expiration ---")
        r.setex("test:expiring", 5, "This will disappear in 5 seconds")
        print(f"Value before waiting: {r.get('test:expiring')}")
        print("Waiting 6 seconds...")
        time.sleep(6)
        print(f"Value after waiting: {r.get('test:expiring')}")
        
        # Test hash operations
        print("\n--- Hash Operations ---")
        r.hset("test:hash", mapping={
            "field1": "value1",
            "field2": "value2",
            "count": 42
        })
        hash_value = r.hgetall("test:hash")
        print(f"Hash values: {hash_value}")
        
        # Test list operations
        print("\n--- List Operations ---")
        r.lpush("test:list", "third", "second", "first")
        r.rpush("test:list", "fourth", "fifth")
        list_values = r.lrange("test:list", 0, -1)
        print(f"List values: {list_values}")
        
        # Test increment/decrement
        print("\n--- Increment/Decrement ---")
        r.set("test:counter", 10)
        r.incr("test:counter")
        r.incr("test:counter")
        r.decr("test:counter")
        counter = r.get("test:counter")
        print(f"Counter after inc/dec operations: {counter}")
        
        # Clean up
        print("\n--- Cleaning Up ---")
        keys = ["test:string", "test:hash", "test:list", "test:counter"]
        for key in keys:
            r.delete(key)
            exists = r.exists(key)
            print(f"Key {key} deleted: {'Yes' if not exists else 'No'}")
        
        print("\nAll Redis operations completed successfully")
        
    except redis.RedisError as e:
        print(f"Redis error: {e}")
    finally:
        r.close()
        print("\nConnection closed")

if __name__ == "__main__":
    test_redis_basic_functions()