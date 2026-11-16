import fitz
from typing import Optional, Callable, List
import time

from beedoc.core.interfaces import DocumentRenderer
from beedoc.core.entities import (
    DocumentMetadata, ProcessingResult, 
    ProcessingConfig, 
    ProcessedPage, DocumentType
)
from beedoc.core.exceptions import DocumentRenderError, ConfigurationError
from beegen.loggings.loggers import LOGGER


class TextRenderer(DocumentRenderer):
    """Renderer that extracts text from PDF documents."""
    
    def __init__(self):
        self.config: Optional[ProcessingConfig] = None
        
    async def configure(self, config: ProcessingConfig) -> None:
        """Configure the renderer with processing parameters."""
        config.validate()
        self.config = config
        
    async def render_document(
        self, 
        metadata: DocumentMetadata, 
        content: bytes,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> ProcessingResult:
        """Extract text from entire PDF document."""
        if not self.config:
            raise ConfigurationError("Renderer not configured")
        
        if metadata.document_type != DocumentType.PDF:
            raise DocumentRenderError(
                f"Text extraction only supports PDF documents, got: {metadata.document_type.value}"
            )
        
        start_time = time.time()
        
        try:
            pages = await self._extract_text_from_pdf(content, metadata, progress_callback)
            total_pages = len(pages)
            
            processing_time = (time.time() - start_time) * 1000  # Convert to ms
            
            return ProcessingResult(
                document_name=metadata.name,
                document_type=metadata.document_type,
                total_pages=total_pages,
                pages=pages,
                processing_time_ms=processing_time,
                config_used=self.config
            )
            
        except Exception as e:
            raise DocumentRenderError(f"Failed to extract text from PDF: {e}")
    
    async def render_page(
        self, 
        content: bytes, 
        page_number: int,
        metadata: DocumentMetadata
    ) -> ProcessedPage:
        """Extract text from a single PDF page."""
        if metadata.document_type != DocumentType.PDF:
            raise DocumentRenderError(
                f"Text extraction only supports PDF documents, got: {metadata.document_type.value}"
            )
        
        return await self._extract_text_from_pdf_page(content, page_number, metadata)
        
    async def _extract_text_from_pdf(
        self,
        content: bytes,
        metadata: DocumentMetadata,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[ProcessedPage]:
        """Extract text from all PDF pages."""
        try:
            doc = fitz.open(stream=content, filetype="pdf")
            pages = []
            total_pages = len(doc)
            
            for page_num in range(total_pages):
                page = doc.load_page(page_num)
                
                # Extract text from the page
                text_content = page.get_text()
                
                # Clean up the text (remove excessive whitespace, etc.)
                text_content = self._clean_text(text_content)
                
                pages.append(ProcessedPage(
                    page_number=page_num + 1,
                    text_data=text_content
                ))
                
                if progress_callback:
                    progress_callback(page_num + 1, total_pages)
            
            doc.close()
            return pages
            
        except Exception as e:
            import traceback
            LOGGER.error(traceback.format_exc())
            raise DocumentRenderError(f"Failed to extract text from PDF: {e}")
        
    async def _extract_text_from_pdf_page(
        self, 
        content: bytes, 
        page_number: int, 
        metadata: DocumentMetadata
    ) -> ProcessedPage:
        """Extract text from a single PDF page."""
        try:
            doc = fitz.open(stream=content, filetype="pdf")
            
            if page_number < 1 or page_number > len(doc):
                raise DocumentRenderError(f"Page {page_number} out of range")
            
            page = doc.load_page(page_number - 1)  # 0-based index
            
            # Extract text
            text_content = page.get_text()
            text_content = self._clean_text(text_content)
            
            doc.close()
            
            return ProcessedPage(
                page_number=page_number, 
                text_data=text_content
            )
            
        except Exception as e:
            raise DocumentRenderError(f"Failed to extract text from PDF page {page_number}: {e}")
    
    def _clean_text(self, text: str) -> str:
        """Clean extracted text by removing excessive whitespace and formatting."""
        if not text:
            return ""
        
        # Replace multiple whitespace characters with single spaces
        import re
        text = re.sub(r'\s+', ' ', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        return text