from typing import Dict, Any, Optional, ClassVar, Tuple, List, Set
from .workflow_state import WorkflowState
from .workflow_indexer import WorkflowIndexer
from collections import defaultdict


class StateRegistry:
    """
    Ultra-simple dict-based state manager for maximum performance.
    Perfect for 500+ CCU with minimal overhead.
    """
    __slots__ = ('_states', '_execution_order')
    
    # Singleton instance
    _self: ClassVar[Optional['StateRegistry']] = None
    
    @classmethod
    def self(cls) -> 'StateRegistry':
        """Get the singleton instance of the registry.
        
        Returns:
            The singleton SimpleStateManager instance
        """
        if cls._self is None:
            cls._self = cls()
        return cls._self
    
    def __init__(self):
        self._states: Dict[str, WorkflowState] = {}
        
    def create(
        self, 
        indexer: WorkflowIndexer,
        inputs: Dict[str, Any] = {},
        user_id: Optional[str] = None,
        session_id: Optional[str] = None, 
        request_id: Optional[str] = None
    ) -> WorkflowState:
        """Create new state with given data."""
        _state = WorkflowState(
            indexer=indexer,
            inputs=inputs,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id
        )
            
        self._states[_state.request_id] = _state
        return _state
    
    def __getitem__(self, request_id: str) -> Optional[WorkflowState]:
        """
        Access value by storage index.
        
        Args:
            key: state key (request id) to get state
            
        Returns:
            WorkflowState at the given key
        """
        return self._states.get(request_id, None)
    
    def __iter__(self):
        """Enable iteration over states keys."""
        return iter(self._states.keys())
    

STATE_REGISTRY = StateRegistry.self()