from collections import defaultdict
from typing import Optional, Dict, List, Any, Set
import os
import asyncio
from dataclasses import dataclass


@dataclass
class TraceItem:
    """Represents a single trace item (trace, span, generation, or event)."""
    data: Dict[str, Any]
    parent: Optional[str] = None
    

class TraceBuffer:
    
    def __init__(self):
        self._buffer: Dict[str, List[TraceItem]] = defaultdict(list)
        self._mapper: Dict[str, Dict[str, TraceItem]] = defaultdict(dict)
        
    def add(
        self,
        request_id: str,
        data: Dict[str, Any],
        parent: Optional[str]=None
    ) -> None:
        """Internal add item method"""
        if "name" not in data:
            raise ValueError("'name' must be included in trace data!!")
        
        name = data["name"]
        
        item = TraceItem(
            data=data,
            parent=parent
        )
        
        self._buffer[request_id].append(item)        
        self._mapper[request_id][name] = item
        
    def update(
        self,
        request_id: str,
        name: str,
        data: Dict[str, Any]
    ) -> None:
        if request_id in self._mapper:
            if name in self._mapper[request_id]:
                self._mapper[request_id][name].data.update(data)
        
    def __iter__(self):
        for request_id in self._buffer:
            yield request_id
        
    def __getitem__(self, key: str) -> List[TraceItem]:
        """Get variable: value = state[node, var]"""
        return self._buffer[key]
        

TRACE_BUFFER = TraceBuffer()

# TRACE_BUFFER.add("123", {"name": "hihi"})
# TRACE_BUFFER.update("123", "hihi", {"id": "1"})

# print(TRACE_BUFFER["123"])