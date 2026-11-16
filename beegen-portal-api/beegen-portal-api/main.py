import asyncio

from app.consumer.confluence.kafka.consumer import run_consumer
from beegen.loggings import LOGGER


if __name__ == "__main__":
    LOGGER.info("Starting Confluence Kafka consumer")
    asyncio.run(run_consumer())
