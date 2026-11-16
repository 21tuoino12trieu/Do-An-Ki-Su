import cv2
import numpy as np
import fitz
from typing import Optional, Callable
import time

from beedoc.core.interfaces import DocumentRenderer
from beedoc.core.entities import (
    DocumentMetadata, ProcessingResult, ProcessingConfig, 
    ProcessedPage, DocumentType
)
from beedoc.core.exceptions import DocumentRenderError, ConfigurationError


class NumpyRenderer(DocumentRenderer):
    """Renderer that outputs numpy arrays."""
    
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
        """Render entire document to numpy arrays."""
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
                    f"Numpy rendering only supports image and PDF documents, got: {metadata.document_type.value}"
                )
            
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
                f"Numpy rendering only supports image and PDF documents, got: {metadata.document_type.value}"
            )
    
    async def _render_image(self, content: bytes, metadata: DocumentMetadata) -> list[ProcessedPage]:
        """Render image to numpy array."""
        try:
            img_arr = np.frombuffer(content, np.uint8)
            img = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
            
            if img is None:
                raise DocumentRenderError("Failed to decode image")
            
            # Apply resizing if needed
            if self.config.max_dimension:
                img = self._resize_image(img, self.config.max_dimension)
            
            return [ProcessedPage(page_number=1, image_data=img)]
            
        except Exception as e:
            raise DocumentRenderError(f"Failed to render image: {e}")
    
    async def _render_pdf(
        self, 
        content: bytes, 
        metadata: DocumentMetadata,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> list[ProcessedPage]:
        """Render PDF pages to numpy arrays."""
        try:
            doc = fitz.open(stream=content, filetype="pdf")
            pages = []
            total_pages = len(doc)
            
            for page_num in range(total_pages):
                page = doc.load_page(page_num)
                
                # Calculate zoom factor
                zoom_factor = self.config.max_dimension / max(page.rect.height, page.rect.width)
                matrix = fitz.Matrix(zoom_factor, zoom_factor)
                pixmap = page.get_pixmap(matrix=matrix)
                
                # Convert to numpy array
                img_arr = np.frombuffer(
                    pixmap.samples, 
                    dtype=np.uint8
                ).reshape(pixmap.height, pixmap.width, pixmap.n)
                
                # Convert color space to BGR for OpenCV compatibility
                if pixmap.n == 4:  # RGBA
                    img_arr = cv2.cvtColor(img_arr, cv2.COLOR_RGBA2BGRA)
                elif pixmap.n == 3:  # RGB
                    img_arr = cv2.cvtColor(img_arr, cv2.COLOR_RGB2BGR)
                elif pixmap.n == 1:  # Grayscale
                    img_arr = cv2.cvtColor(img_arr, cv2.COLOR_GRAY2BGR)
                else:
                    raise DocumentRenderError(f"Unsupported color channels: {pixmap.n}")
                
                pages.append(ProcessedPage(
                    page_number=page_num + 1,
                    image_data=img_arr
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
            
            page = doc.load_page(page_number - 1)  # 0-based index
            
            zoom_factor = self.config.max_dimension / max(page.rect.height, page.rect.width)
            matrix = fitz.Matrix(zoom_factor, zoom_factor)
            pixmap = page.get_pixmap(matrix=matrix)
            
            img_arr = np.frombuffer(
                pixmap.samples, 
                dtype=np.uint8
            ).reshape(pixmap.height, pixmap.width, pixmap.n)
            
            # Color space conversion
            if pixmap.n == 4:
                img_arr = cv2.cvtColor(img_arr, cv2.COLOR_RGBA2BGRA)
            elif pixmap.n == 3:
                img_arr = cv2.cvtColor(img_arr, cv2.COLOR_RGB2BGR)
            elif pixmap.n == 1:
                img_arr = cv2.cvtColor(img_arr, cv2.COLOR_GRAY2BGR)
            
            doc.close()
            
            return ProcessedPage(page_number=page_number, image_data=img_arr)
            
        except Exception as e:
            raise DocumentRenderError(f"Failed to render PDF page {page_number}: {e}")
    
    def _resize_image(self, img: np.ndarray, max_dim: int) -> np.ndarray:
        """Resize image maintaining aspect ratio."""
        height, width = img.shape[:2]
        
        if max(height, width) <= max_dim:
            return img
        
        if height > width:
            new_height = max_dim
            new_width = int(width * (max_dim / height))
        else:
            new_width = max_dim
            new_height = int(height * (max_dim / width))
        
        return cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)