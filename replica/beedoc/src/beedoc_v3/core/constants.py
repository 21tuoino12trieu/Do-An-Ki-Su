from enum import Enum
from typing import Dict, Set

class DocumentStatus(Enum):
    PENDING = "pending"
    READING = "reading"
    RECONSTRUCTING = "reconstructing"
    COMPLETED = "completed"
    FAILED = "failed"

class DocumentCategory(Enum):
    VISUAL = "visual"        # Cần VLM: PDF, DOCX, XLSX, Images
    TEXTUAL = "textual"      # Cần LLM: TXT, MD
    STRUCTURED = "structured" # Cần Table Logic: CSV, JSON

EXTENSION_CATEGORY_MAP: Dict[str, DocumentCategory] = {
    "html": DocumentCategory.TEXTUAL,
}
