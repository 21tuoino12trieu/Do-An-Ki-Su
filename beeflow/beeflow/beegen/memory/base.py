from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from beegen.configs.memory.memory_config import MemoryConfig


class BaseMemory(ABC):
    """
    Abstract base class for memory modules.
    """

    @classmethod
    @abstractmethod
    async def create(cls, config: MemoryConfig):
        """
        Asynchronously creates a memory module instance based on the provided configuration.
        """
        pass

    @abstractmethod
    async def add(
        self,
        messages: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ):
        """
        Adds a list of messages to the memory.
        """
        pass

    @abstractmethod
    async def get_history(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves the message history for a given session.
        """
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Searches the memory.
        """
        pass

    @abstractmethod
    async def clear(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ):
        """
        Clears the memory for a given session.
        """
        pass

    @abstractmethod
    async def update(
        self,
        memory_id: str,
        data: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ):
        """
        Updates a memory entry.
        """
        pass

    @abstractmethod
    async def delete(
        self,
        memory_id: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ):
        """
        Deletes a memory entry.
        """
        pass
