import numpy as np
import fitz
import time
import io
import base64
from typing import Optional, Callable
from PIL import Image
from beedoc.core.interfaces import DocumentRenderer
from beedoc.core.entities import (
    DocumentMetadata, ProcessingResult, ProcessingConfig, 
    ProcessedPage, DocumentType
)
from beedoc.core.exceptions import DocumentRenderError, ConfigurationError


class Base64Renderer(DocumentRenderer):
    """Renderer that outputs base64-encoded PNG images."""
    
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
        """Render entire document to base64 strings."""
        if not self.config:
            raise ConfigurationError("Renderer not configured")
        
        start_time = time.time()
        
        try:
            if metadata.document_type == DocumentType.IMAGE:
                pages = await self._render_image(content, metadata)
                total_pages = 1
            elif metadata.document_type == DocumentType.PDF:
                pages = await self._render_pdf(content, metadata, progress_callback)
                total_pages = len(pages)
            else:
                raise DocumentRenderError(
                    f"Base64 rendering only supports image and PDF documents, got: {metadata.document_type.value}"
                )
            
            processing_time = (time.time() - start_time) * 1000
            
            return ProcessingResult(
                document_name=metadata.name,
                document_type=metadata.document_type,
                total_pages=total_pages,
                pages=pages,
                processing_time_ms=processing_time,
                config_used=self.config
            )
            
        except Exception as e:
            raise DocumentRenderError(f"Failed to render document: {e}")
    
    async def render_page(
        self, 
        content: bytes, 
        page_number: int,
        metadata: DocumentMetadata
    ) -> ProcessedPage:
        """Render a single page."""
        if metadata.document_type == DocumentType.IMAGE:
            if page_number != 1:
                raise DocumentRenderError("Images only have page 1")
            pages = await self._render_image(content, metadata)
            return pages[0]
        elif metadata.document_type == DocumentType.PDF:
            return await self._render_pdf_page(content, page_number, metadata)
        else:
            raise DocumentRenderError(
                f"Base64 rendering only supports image and PDF documents, got: {metadata.document_type.value}"
            )
    
    async def _render_image(self, content: bytes, metadata: DocumentMetadata) -> list[ProcessedPage]:
        """Render image to base64 string."""
        try:
            image = Image.open(io.BytesIO(content))
            
            # Apply resizing if needed
            if self.config.max_dimension:
                image = self._resize_image(image, self.config.max_dimension)
            
            # Convert to PNG base64
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", quality=self.config.quality)
            buffer.seek(0)
            
            img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            
            return [ProcessedPage(page_number=1, image_data=img_base64)]
            
        except Exception as e:
            raise DocumentRenderError(f"Failed to render image: {e}")
    
    async def _render_pdf(
        self, 
        content: bytes, 
        metadata: DocumentMetadata,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> list[ProcessedPage]:
        """Render PDF pages to base64 strings."""
        try:
            doc = fitz.open(stream=content, filetype="pdf")
            pages = []
            total_pages = len(doc)
            
            for page_num in range(total_pages):
                page = doc.load_page(page_num)
                
                zoom_factor = self.config.max_dimension / max(page.rect.height, page.rect.width)
                matrix = fitz.Matrix(zoom_factor, zoom_factor)
                pixmap = page.get_pixmap(matrix=matrix)
                
                # Convert to PNG bytes then base64
                img_bytes = pixmap.tobytes("png")
                img_base64 = base64.b64encode(img_bytes).decode("utf-8")
                
                pages.append(ProcessedPage(
                    page_number=page_num + 1,
                    image_data=img_base64
                ))
                
                if progress_callback:
                    progress_callback(page_num + 1, total_pages)
            
            doc.close()
            return pages
            
        except Exception as e:
            raise DocumentRenderError(f"Failed to render PDF: {e}")
    
    async def _render_pdf_page(
        self, 
        content: bytes, 
        page_number: int, 
        metadata: DocumentMetadata
    ) -> ProcessedPage:
        """Render a single PDF page."""
        try:
            doc = fitz.open(stream=content, filetype="pdf")
            
            if page_number < 1 or page_number > len(doc):
                raise DocumentRenderError(f"Page {page_number} out of range")
            
            page = doc.load_page(page_number - 1)
            
            zoom_factor = self.config.max_dimension / max(page.rect.height, page.rect.width)
            matrix = fitz.Matrix(zoom_factor, zoom_factor)
            pixmap = page.get_pixmap(matrix=matrix)
            
            img_bytes = pixmap.tobytes("png")
            img_base64 = base64.b64encode(img_bytes).decode("utf-8")
            
            doc.close()
            
            return ProcessedPage(page_number=page_number, image_data=img_base64)
            
        except Exception as e:
            raise DocumentRenderError(f"Failed to render PDF page {page_number}: {e}")
    
    def _resize_image(self, image: Image.Image, max_dim: int) -> Image.Image:
        """Resize image maintaining aspect ratio."""
        width, height = image.size
        
        if max(width, height) <= max_dim:
            return image
        
        if height > width:
            new_height = max_dim
            new_width = int(width * (max_dim / height))
        else:
            new_width = max_dim
            new_height = int(height * (max_dim / width))
        
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)