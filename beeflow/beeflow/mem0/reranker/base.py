from abc import ABC, abstractmethod

from typing import List, Dict, Any, Optional
 
class BaseReranker(ABC):

    """Abstract base class for all rerankers."""

    @abstractmethod

    def rerank(self, query: str, documents: List) -> List[Dict[str, Any]]:

        """

        Rerank documents based on relevance to the query.

        Args:

            query: The search query

            documents: List of documents to rerank, each with 'memory' field  

            top_k: Number of top documents to return (None = return all)

            threshold (float, optional): Minimum score for a memory to be included in the results. Defaults to None.


        Returns:

            List of reranked documents with added 'rerank_score' field

        """

        pass
 