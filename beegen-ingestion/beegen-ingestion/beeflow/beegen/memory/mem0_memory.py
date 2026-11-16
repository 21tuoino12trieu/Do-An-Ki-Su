from typing import Any, Dict, List, Optional
from mem0 import AsyncMemory
from mem0.configs.base import MemoryConfig
from beegen.memory.base import BaseMemory
from beegen.configs.memory.mem0_config import Mem0MemoryConfig, Mem0Operation

class Mem0Memory(BaseMemory):
    """
    A beegen memory module that uses mem0.AsyncMemory as its backend.
    """

    def __init__(self, client: AsyncMemory):
        self.client: AsyncMemory = client
        self.operation_map = {
            Mem0Operation.ADD: self.add,
            Mem0Operation.GET_HISTORY: self.get_history,
            Mem0Operation.SEARCH: self.search,
            Mem0Operation.UPDATE: self.update,
            Mem0Operation.DELETE: self.delete,
            Mem0Operation.CLEAR: self.clear,
        }

    @classmethod
    def create(cls, config: Mem0MemoryConfig) -> "Mem0Memory":
        """
        Async factory to initialize the memory.
        """
        config_dict = config.dict(exclude_unset=True)

        # Filter config_dict to only include fields valid for mem0.MemoryConfig
        valid_fields = MemoryConfig.model_fields.keys()
        mem0_config_dict = {
            k: v for k, v in config_dict.items() if k in valid_fields
        }
        # Create the mem0-native config and initialize the client
        mem0_config = MemoryConfig(**mem0_config_dict)
        client = AsyncMemory(config=mem0_config)

        return cls(client)

    async def add(
        self,
        messages: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs
    ):
        """
        Adds a list of messages to the memory.
        """
        return await self.client.add(
            messages=messages,
            user_id=user_id,
            agent_id=agent_id,
            run_id=session_id,
            **kwargs
        )

    async def get_history(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Retrieves the message history for a given session.
        """
        return await self.client.get_all(
            user_id=user_id, agent_id=agent_id, run_id=session_id, **kwargs
        )

    async def search(
        self,
        query: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Searches the memory.
        """
        return await self.client.search(
            query=query, user_id=user_id, agent_id=agent_id, run_id=session_id, **kwargs
        )

    async def clear(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs
    ):
        """
        Clears the memory for a given session.
        """
        return await self.client.delete_all(
            user_id=user_id, agent_id=agent_id, run_id=session_id, **kwargs
        )

    async def update(
        self,
        memory_id: str,
        data: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs
    ):
        """
        Updates a memory entry.
        """
        # The original mem0 `update` doesn't support scoping, so we don't pass the IDs.
        return await self.client.update(
            memory_id=memory_id,
            data=data,
            **kwargs
        )

    async def delete(
        self,
        memory_id: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs
    ):
        """
        Deletes a memory entry.
        """
        # The original mem0 `delete` doesn't support scoping, so we don't pass the IDs.
        return await self.client.delete(
            memory_id=memory_id,
            **kwargs
        )

    async def run(
        self, 
        operation: Mem0Operation,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a mem0 operation.

        Args:
            operation: The Mem0Operation enum value.
            params: Parameters needed for the operation.

        Returns:
            A standardized response dictionary with the operation result.
        """
        if params is None:
            params = {}

        try:
            if operation not in self.operation_map:
                raise ValueError(f"Unsupported operation: {operation}")

            result = await self.operation_map[operation](**params)

            response: Dict[str, Any] = {"status": "success"}
            if isinstance(result, dict):
                response.update(result)
            else:
                output_key = {
                    Mem0Operation.ADD: "results",
                    Mem0Operation.GET_HISTORY: "results",
                    Mem0Operation.SEARCH: "results",
                    Mem0Operation.UPDATE: "message",
                    Mem0Operation.DELETE: "message",
                    Mem0Operation.CLEAR: "message",
                }.get(operation, "data")
                response[output_key] = result

            list_key_map = {
                Mem0Operation.ADD: "results",
                Mem0Operation.GET_HISTORY: "results",
                Mem0Operation.SEARCH: "results",
            }
            list_key = list_key_map.get(operation)
            if list_key:
                data = response.get(list_key)
                if isinstance(data, list):
                    response["count"] = len(data)

            if "message" not in response:
                op_name = operation.name.lower().replace("_", " ")
                response["message"] = (
                    f"Operation {op_name} completed successfully"
                )

            return response

        except Exception:
            import traceback

            error_traceback = traceback.format_exc()
            return {
                "status": "error",
                "message": error_traceback,
            }
