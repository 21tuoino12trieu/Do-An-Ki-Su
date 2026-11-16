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

# Mapping extension to Category
EXTENSION_CATEGORY_MAP: Dict[str, DocumentCategory] = {
    # Visual Group
    "pdf": DocumentCategory.VISUAL,
    "docx": DocumentCategory.VISUAL,
    "doc": DocumentCategory.VISUAL,
    "xlsx": DocumentCategory.VISUAL,
    "xls": DocumentCategory.VISUAL,
    "png": DocumentCategory.VISUAL,
    "jpg": DocumentCategory.VISUAL,
    "jpeg": DocumentCategory.VISUAL,
    "webp": DocumentCategory.VISUAL,

    # Textual Group
    "txt": DocumentCategory.TEXTUAL,
    "md": DocumentCategory.TEXTUAL,
    "html": DocumentCategory.TEXTUAL,

    # Structured Group
    "csv": DocumentCategory.STRUCTURED,
    "json": DocumentCategory.STRUCTURED,
}
