from enum import Enum


class ChunkingType(str, Enum):
    HIERARCHICAL = "hierarchical"

class DocumentType(str, Enum):
    DOCUMENT = "document"
    QA = "QA"