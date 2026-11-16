from enum import Enum
from beegen.configs.memory.memory_config import MemoryConfig, MemoryType
from beegen.const import BEEGEN_ROOT
from beegen.tools.schema.param import ParamSet
from typing import List, Dict, Any, Optional


class Mem0Operation(str, Enum):
    """Enum for memory operations."""
    ADD = "add"
    GET_HISTORY = "get_history"
    SEARCH = "search"
    UPDATE = "update"
    DELETE = "delete"
    CLEAR = "clear"


MEM0_OPERATION_INPUTS = {
    Mem0Operation.ADD: (
        ParamSet.new()
        .var("messages: List", required=True, description="List of messages to add to memory.")
        .var("user_id: Optional[str] = None", description="Optional user ID to scope the memory.")
        .var("agent_id: Optional[str] = None", description="Optional agent ID to scope the memory.")
        .var("session_id: Optional[str] = None", description="Optional session ID to scope the memory.")
        .var("custom_fact_extraction_prompt: Optional[str] = None", description="Optional custom fact extraction prompt.")
        .build()
    ),
    Mem0Operation.GET_HISTORY: (
        ParamSet.new()
        .var("user_id: Optional[str] = None", description="Optional user ID to scope the memory.")
        .var("agent_id: Optional[str] = None", description="Optional agent ID to scope the memory.")
        .var("session_id: Optional[str] = None", description="Optional session ID to scope the memory.")
        .build()
    ),
    Mem0Operation.SEARCH: (
        ParamSet.new()
        .var("query: str", required=True, description="Query to search for in memory.")
        .var("user_id: Optional[str] = None", description="Optional user ID to scope the memory.")
        .var("agent_id: Optional[str] = None", description="Optional agent ID to scope the memory.")
        .var("session_id: Optional[str] = None", description="Optional session ID to scope the memory.")
        .build()
    ),
    Mem0Operation.UPDATE: (
        ParamSet.new()
        .var("memory_id: str", required=True, description="The ID of the memory to update.")
        .var("data: str", required=True, description="The new data for the memory.")
        .var("user_id: Optional[str] = None", description="Optional user ID to scope the memory.")
        .var("agent_id: Optional[str] = None", description="Optional agent ID to scope the memory.")
        .var("session_id: Optional[str] = None", description="Optional session ID to scope the memory.")
        .var("custom_update_memory_prompt: Optional[str] = None", description="Optional custom update memory prompt.")
        .build()
    ),
    Mem0Operation.DELETE: (
        ParamSet.new()
        .var("memory_id: str", required=True, description="The ID of the memory to delete.")
        .var("user_id: Optional[str] = None", description="Optional user ID to scope the memory.")
        .var("agent_id: Optional[str] = None", description="Optional agent ID to scope the memory.")
        .var("session_id: Optional[str] = None", description="Optional session ID to scope the memory.")
        .build()
    ),
    Mem0Operation.CLEAR: (
        ParamSet.new()
        .var("user_id: Optional[str] = None", description="Optional user ID to scope the memory.")
        .var("agent_id: Optional[str] = None", description="Optional agent ID to scope the memory.")
        .var("session_id: Optional[str] = None", description="Optional session ID to scope the memory.")
        .build()
    ),
}

MEM0_OPERATION_OUTPUTS = {
    Mem0Operation.ADD: (
        ParamSet.new()
        .var(
            "results: List[Dict[str, Any]]",
            required=True,
            description="Memories returned by mem0 after add.",
        )
        .var(
            "relations: Optional[List[Dict[str, Any]]] = None",
            description="Graph relations when graph store is enabled.",
        )
        .build()
    ),
    Mem0Operation.GET_HISTORY: (
        ParamSet.new()
        .var(
            "results: List[Dict[str, Any]]",
            required=True,
            description="Retrieved memories for the scoped session.",
        )
        .var(
            "relations: Optional[List[Dict[str, Any]]] = None",
            description="Graph relations when graph store is enabled.",
        )
        .build()
    ),
    Mem0Operation.SEARCH: (
        ParamSet.new()
        .var(
            "results: List[Dict[str, Any]]",
            required=True,
            description="Memories matching the search query.",
        )
        .var(
            "relations: Optional[List[Dict[str, Any]]] = None",
            description="Graph relations when graph store is enabled.",
        )
        .build()
    ),
    Mem0Operation.UPDATE: (
        ParamSet.new()
        .var(
            "message: str",
            required=True,
            description="Confirmation message from the update operation.",
        )
        .build()
    ),
    Mem0Operation.DELETE: (
        ParamSet.new()
        .var(
            "message: str",
            required=True,
            description="Confirmation message from the delete operation.",
        )
        .build()
    ),
    Mem0Operation.CLEAR: (
        ParamSet.new()
        .var(
            "message: str",
            required=True,
            description="Confirmation message from the clear operation.",
        )
        .build()
    ),
}

class Mem0MemoryConfig(MemoryConfig):
    """Configuration for Mem0Memory."""
    llm: Dict[str, Any]
    embedder: Dict[str, Any]
    vector_store: Dict[str, Any]
    reranker: Optional[Dict[str, Any]] = None
    
    @classmethod
    def default(cls) -> 'Mem0MemoryConfig':
        """Load default config from yaml file."""
        config_data = cls.read_yaml(BEEGEN_ROOT / "config/mem0.yaml")
        return cls(**config_data) 
    
