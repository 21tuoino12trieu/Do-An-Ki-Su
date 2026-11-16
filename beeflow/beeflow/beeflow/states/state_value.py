from typing import Any, Optional, Dict, List, Union
from collections import defaultdict
import uuid

DEFAULT = "DEFAULT"


class VariableCell:
    """Storage cho một biến có thể có nhiều giá trị trong các context/loop khác nhau"""
    
    def __init__(self, default_value: Any = None):
        self.contexts: Dict[str, Any] = {} # contextid -> value
        self.versions: List[str] = [] # Stack để track order của contexts
        self.DEFAULT_VALUE = default_value
        self.DEFAULT_CONTEXT = "main"
        
    def __setitem__(self, context_id: Optional[str], value: Any) -> None:
        """Set giá trị cho context cụ thể"""
        # If context_id is None, update the most recent context or create default
        if context_id is None:
            if not self.versions:
                # No existing contexts, create default
                context_id = self.DEFAULT_CONTEXT
            else:
                # Update the most recent context
                context_id = self.versions[-1]
        
        self.contexts[context_id] = value
        
        # Track ordering - only add if it's a new context
        if context_id not in self.versions:
            self.versions.append(context_id)
            
    def __getitem__(self, context_id: Optional[str] = None) -> Any:
        """Get giá trị từ context cụ thể"""
        if context_id is None:
            if not self.versions:
                context_id = self.DEFAULT_CONTEXT
            else:
                context_id = self.versions[-1]
        
        return self.contexts.get(context_id, self.DEFAULT_VALUE)
    
    def get(self) -> Any:
        """Get giá trị từ context gần nhất hoặc default"""
        if self.versions:
            latest_context = self.versions[-1]
            return self.contexts[latest_context]
        return self.DEFAULT_VALUE
    

if __name__ == "__main__":
    # Basic usage
    cell = VariableCell(default_value=0)
    
    # Set với context
    cell["loop1"] = 10
    cell["loop2"] = 20
    
    # When setting with None, it updates the most recent context (loop2)
    cell[None] = 30  # This updates loop2 from 20 to 30
    
    print(f"loop1: {cell['loop1']}")  # 10
    print(f"loop2: {cell['loop2']}")  # 30 (updated)
    print(f"current: {cell.get()}")  # 30
    
    # Test with empty cell - creates default context
    empty_cell = VariableCell(default_value=0)
    empty_cell[None] = 100  # Creates "global" context
    print(f"empty cell current: {empty_cell.get()}")  # 100
    
    empty_cell["loop1"] = 200
    print(f"empty cell current: {empty_cell.get()}")  # 100
    
    empty_cell[None] = 150
    print(f"empty cell current: {empty_cell.get()}")  # 100
