from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

class QueryInfo(BaseModel):
    """Information about a query."""
    query: str
    purpose: str

class DocumentResult(BaseModel):
    """Results of document retrieval."""
    docs: List[Dict]
    relevance_score: float

class ConversationIntent(BaseModel):
    """Analysis of conversation intent."""
    intent: str
    category: str
    topic: str
    needs_clarification: bool

class CardInformation(BaseModel):
    """Information about a card."""
    keywords: List[str] = Field(default_factory=list)
    matched_nodes: List[Dict] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_message: str = ""
    children: List[Dict] = Field(default_factory=list)
    matched_ids: List[str] = Field(default_factory=list)
    current_node: Optional[str] = None

class LocationInformation(BaseModel):
    """Information about a location query."""
    document_id: str
    keywords: List[str] = Field(default_factory=list)
    document_texts: List[str] = Field(default_factory=list)
    filtered_data: List[str] = Field(default_factory=list)


class CardNode(BaseModel):
    """Model for a node in the card graph."""
    id: str
    name: str
    category: str
    keywords: List[str] = Field(default_factory=list)
    features: List[str] = Field(default_factory=list)

class CardState(BaseModel):
    """Model for card conversation state."""
    current_node: Optional[str] = None
    needs_clarification: bool = False
    clarification_message: str = ""
    clarification_options: List[Dict] = Field(default_factory=list)
    matched_nodes: List[Dict] = Field(default_factory=list)
    confidence: float = 0.0