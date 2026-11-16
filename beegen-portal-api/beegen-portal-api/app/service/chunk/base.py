from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseChunker(ABC):
    @abstractmethod
    async def chunk(
        self, 
        reconstructed: str,
        zones: List[Dict[str, Any]],
        file_name: str,
        extract_keywords: bool = False, 
        **kwargs
    ) -> Dict[str, Any]:
        pass