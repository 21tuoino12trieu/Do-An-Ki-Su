from typing import List, Optional
from pydantic import BaseModel
from app.utils.enums import ChunkingType


class ChunkRequest(BaseModel):
    chunk_type: Optional[ChunkingType] = ChunkingType.HIERARCHICAL


class Chunk(BaseModel):
    content: str
    keywords: Optional[List[str]]
