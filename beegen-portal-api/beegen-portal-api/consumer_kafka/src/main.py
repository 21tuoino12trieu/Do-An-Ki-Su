"""
CUA Consumer / Router Service
Entry point - chạy asyncio event loop.
"""

import asyncio
from src.utils.logging import setup_logging
from src.services.kafka_consumer import CUAConsumer
import os
os.environ['NO_PROXY'] = '*.mbbank.com.vn'

async def main():
    setup_logging()
    consumer = CUAConsumer()
    await consumer.start()


if __name__ == "__main__":
    asyncio.run(main())
