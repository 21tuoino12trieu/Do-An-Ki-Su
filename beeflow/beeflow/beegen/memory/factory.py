import asyncio
from beegen.memory.base import BaseMemory
from beegen.memory.mem0_memory import Mem0Memory
from beegen.configs.memory.memory_config import MemoryConfig, MemoryType


class MemoryFactory:
    """
    Factory to create beegen memory module instances.
    """

    @staticmethod
    def create(config: MemoryConfig) -> BaseMemory:
        """
        Asynchronously creates a memory module instance based on the provided configuration.

        Args:
            config (MemoryConfig): The memory configuration.

        Returns:
            BaseMemory: An instance of a memory module.
        """
        if config.api_type == MemoryType.MEM0:
            memory: Mem0Memory = Mem0Memory.create(config=config)
            return memory
        else:
            raise ValueError(f"Unsupported memory api_type: {config.api_type}")