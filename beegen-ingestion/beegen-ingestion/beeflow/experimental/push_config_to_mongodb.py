

from beegen.configs.cache.redis_config import RedisConfig
from beegen.registry.resource_hub import ResourceHub


redis_config = RedisConfig(
    host="10.215.107.47",
    port=6379,
    username="nlp_user",
    password="Speci@L1",
)

# print(isinstance(redis_config, RedisConfig))

ResourceHub.self().register(redis_config, "redis:nlp-user")