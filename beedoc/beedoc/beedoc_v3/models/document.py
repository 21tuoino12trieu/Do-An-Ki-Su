import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from beedoc_v3.core.constants import DocumentStatus, DocumentCategory

@dataclass
class Zone:
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Page:
    """Represents a single page of a document.

    content: list of zones for the page.
    """
    page_number: int
    image_list: Optional[List[str]] = None  # List of temporary images saved path
    image_data: Optional[Union[bytes, str]] = None      # Raw image data (base64 or bytes)
    content: List[Zone] = field(default_factory=list)      # Per-zone markdown content
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_markdown(self) -> str:
        """Returns the markdown content of the page."""
        return "\n\n".join([zone.content for zone in self.content if zone and zone.content])
@dataclass
class Document:
    """The central data object that travels through the pipeline."""
    # Input info
    file_path: Optional[str] = None
    file_name: str = ""
    extension: str = ""
    category: Optional[DocumentCategory] = None
    max_pages: Optional[int] = None

    # Storage & Identity
    document_id: Optional[str] = None
    file_hash: Optional[str] = None
    file_size_bytes: int = 0

    # Content structure
    pages: List[Page] = field(default_factory=list)

    # Reconstructed results
    reconstructed_content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    ai_metadata: Dict[str, Any] = field(default_factory=dict)

    # Status & Logging  
    status: DocumentStatus = DocumentStatus.PENDING
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    processing_time_ms: int = 0

    def add_page(self, page: Page) -> None:
        self.pages.append(page)

    def update_status(self, status: DocumentStatus, error: Optional[str] = None) -> None:
        self.status = status
        if error:
            self.error_message = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "file_name": self.file_name,
            "status": self.status.value,
            "category": self.category.value if self.category else None,
            "total_pages": len(self.pages),
            "reconstructed_content": self.reconstructed_content,
            "metadata": self.metadata,
            "ai_metadata": self.ai_metadata,
            "error": self.error_message,
            "processing_time_ms": self.processing_time_ms
        }
