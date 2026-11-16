from typing import Any, Dict, List
from app.service.chunk.base import BaseChunker
from app.service.chunk.hierarchical import HierarchicalChunker
from app.utils.enums import ChunkingType


def get_chunking_service(chunk_type) -> BaseChunker:
    chunk_type_str = chunk_type.value if isinstance(chunk_type, ChunkingType) else str(chunk_type)
    if chunk_type_str == ChunkingType.HIERARCHICAL.value:
        return HierarchicalChunker()
    raise ValueError(f"Unsupported chunk_type: {chunk_type}")

async def chunk(
    reconstructed: str,
    zones: List[Dict[str, Any]],
    file_name: str,
    chunk_type: ChunkingType,
    extract_keywords: bool = False,
) -> Dict[str, Any]:
    chunking_service: BaseChunker = get_chunking_service(chunk_type)
    return await chunking_service.chunk(
        reconstructed=reconstructed,
        zones=zones,
        file_name=file_name,
        extract_keywords=extract_keywords,
    )