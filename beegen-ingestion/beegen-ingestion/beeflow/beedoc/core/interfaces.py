from abc import ABC, abstractmethod
from typing import Optional, Callable
from .entities import DocumentMetadata, ProcessingResult, ProcessingConfig, ProcessedPage


class DocumentReader(ABC):
    """Abstract base class for document readers."""
    
    @abstractmethod
    async def validate_input(self, metadata: DocumentMetadata) -> bool:
        """Validate if the document can be processed."""
        pass
    
    @abstractmethod
    async def read_metadata(self, metadata: DocumentMetadata) -> DocumentMetadata:
        """Read and enrich document metadata."""
        pass
    
    @abstractmethod
    async def read_content(self, metadata: DocumentMetadata) -> bytes:
        """Load document content as bytes."""
        pass


class DocumentRenderer(ABC):
    """Abstract base class for document renderers."""
    
    @abstractmethod
    async def configure(self, config: ProcessingConfig) -> None:
        """Configure the renderer with processing parameters."""
        pass
    
    @abstractmethod
    async def render_document(
        self, 
        metadata: DocumentMetadata, 
        content: bytes,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> ProcessingResult:
        """Render entire document to target format."""
        pass
    
    @abstractmethod
    async def render_page(
        self, 
        content: bytes, 
        page_number: int,
        metadata: DocumentMetadata
    ) -> 'ProcessedPage':
        """Render a single page."""
        pass


class DocumentProcessor(ABC):
    """Main interface for document processing operations."""
    
    @abstractmethod
    async def process_document(
        self,
        metadata: DocumentMetadata,
        config: Optional[ProcessingConfig] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> ProcessingResult:
        """Process a document with the given configuration."""
        pass
    
    @abstractmethod
    async def process_batch(
        self,
        documents: list[DocumentMetadata],
        config: Optional[ProcessingConfig] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> list[ProcessingResult]:
        """Process multiple documents."""
        pass