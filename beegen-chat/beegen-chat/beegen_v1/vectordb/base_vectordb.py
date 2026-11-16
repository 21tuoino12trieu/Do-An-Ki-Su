from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypeVar
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator


class VDBRecord(BaseModel):
    r"""Encapsulates information about a vector's unique identifier and its
    payload, which is primarily used as a data transfer object when saving
    to vector storage.

    Attributes:
        id (str, optional): A unique identifier for the vector. If not
            provided, an random uuid will be assigned.
        vector (List[float]): The numerical representation of the vector.        
        payload (Optional[Dict[str, Any]], optional): Any additional metadata
            or information related to the vector. (default: :obj:`None`)
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    vector: Optional[List[float]] = None
    payload: Optional[Dict[str, Any]] = None
    

class VDBQuery(BaseModel):
    r"""Represents a query to a vector database.

    Attributes:
        query_vector (List[float]): The numerical representation of the query
            vector.
        top_k (int, optional): The number of top similar vectors to retrieve
            from the database. (default: :obj:`1`)
    """
    query_vector: List[float]
    collection: str
    top_k: int = Field(default=1, gt=0)
    threshold: float = Field(default=0.0, ge=0)
    output_fields: List[str] = []

    @field_validator('top_k')
    def validate_top_k(cls, v: int) -> int:
        if v <= 0:
            raise ValueError('top_k must be greater than 0')
        return v
    
    
class VDBResult(BaseModel):
    r"""Encapsulates the result of a query against a vector database.

    Attributes:
        record (VectorRecord): The target vector record.
        similarity (float): The similarity score between the query vector and
            the record.
    """
    record: VDBRecord
    similarity: float
    
    @field_validator('similarity')
    def validate_similarity(cls, v: float) -> float:
        if not -1 <= v <= 1:
            raise ValueError('similarity score must be between -1 and 1')
        return v

    @classmethod
    def construct(
        cls,
        similarity: float,
        id: str,
        vector: List[float] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> "VDBResult":
        return cls(
            record=VDBRecord(id=id, vector=vector, payload=payload),
            similarity=similarity,
        )
        

class VDBStatus(BaseModel):
    r"""Vector database status.

    Attributes:
        vector_dim (int): The dimention of stored vectors.
        vector_count (int): The number of stored vectors.
    """
    vector_dim: int
    vector_count: int
    
    @field_validator('vector_dim')
    def validate_vector_dim(cls, v: int) -> int:
        if v <= 0:
            raise ValueError('vector_dim must be greater than 0')
        return v

    @field_validator('vector_count')
    def validate_vector_count(cls, v: int) -> int:
        if v < 0:
            raise ValueError('vector_count must be non-negative')
        return v
    

T = TypeVar('T', bound=str)


class BaseVectorStore(ABC):
    r"""Abstract base class for vector storage system."""
    
    
    def get_payloads_by_vector(
        self,
        vector: List[float],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        r"""Returns payloads of top k vector records that closest to the given
        vector.

        This function is a wrapper of `BaseVectorStorage.query`.

        Args:
            vector (List[float]): The search vector.
            top_k (int): The number of top similer vectors.

        Returns:
            List[List[Dict[str, Any]]]: A list of vector payloads retrieved
                from the storage based on similarity to the query vector.
        """
        
        results = self.run(VDBQuery(vector, top_k))
        return [
            result.record.payload
            for result in results
            if result.record.payload is not None
        ]
    
    @abstractmethod    
    async def run(
        self,
        operation: str,
        params: Dict = None,
        **kwargs
    ) -> Dict[str, Any]:
         """
        Run a VectorDB operation asynchronously.
        
        Args:
            operation (MilvusOperation): The operation to perform
            params (Dict, optional): Parameters for the operation
            **kwargs: Additional keyword arguments
            
        Returns:
            Dict[str, Any]: A dictionary containing operation results
        """