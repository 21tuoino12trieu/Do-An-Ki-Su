from abc import ABC, abstractmethod
from typing import List, Dict, Any, Callable
from beegenerate.configs import RetrievalConfig


class BaseRetriever(ABC):
    r"Abstract base class for implementing various types of information retrievers."
    
    @abstractmethod
    async def run(
        self,
        query: str,
        bot_id: str,
        collection: str,
        top_k: int = 3,
        threshold: float = 0.0,
        **kwargs
    ) -> List[Dict[str, Any]]:
        r"Abstract base class for implementing various types of information retrievers."