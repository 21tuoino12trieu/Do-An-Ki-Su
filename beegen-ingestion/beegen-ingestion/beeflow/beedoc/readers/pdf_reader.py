import aiofiles
from pathlib import Path
import fitz

from beedoc.core.interfaces import DocumentReader
from beedoc.core.entities import DocumentMetadata, DocumentType
from beedoc.core.exceptions import DocumentReadError, DocumentValidationError


class PdfReader(DocumentReader):
    """Reader for PDF documents."""
    
    async def validate_input(self, metadata: DocumentMetadata) -> bool:
        """Validate if the PDF can be processed."""
        if metadata.document_type != DocumentType.PDF:
            return False
            
        if metadata.path:
            path = Path(metadata.path)
            if not path.exists():
                raise DocumentValidationError(f"File not found: {metadata.path}")
            
            if path.suffix.lower() != '.pdf':
                raise DocumentValidationError(f"Expected PDF file, got: {path.suffix}")
        
        return True
    
    async def read_metadata(self, metadata: DocumentMetadata) -> DocumentMetadata:
        """Read and enrich PDF metadata."""
        content = metadata.content
        if not content:
            if not metadata.path:
                raise DocumentValidationError("No path or content provided")
            
            try:
                async with aiofiles.open(metadata.path, 'rb') as f:
                    content = await f.read()
            except Exception as e:
                raise DocumentReadError(f"Failed to read PDF file: {e}")
        
        # Validate PDF and get page count
        try:
            doc = fitz.open(stream=content, filetype="pdf")
            page_count = len(doc)
            doc.close()
            
            # Store additional metadata
            metadata.size_bytes = len(content)
            return metadata
            
        except Exception as e:
            raise DocumentValidationError(f"Invalid PDF file: {e}")
    
    async def read_content(self, metadata: DocumentMetadata) -> bytes:
        """Load PDF content as bytes."""
        if metadata.content:
            return metadata.content
        
        if not metadata.path:
            raise DocumentReadError("No path or content provided")
        
        try:
            async with aiofiles.open(metadata.path, 'rb') as f:
                content = await f.read()
            
            # Validate the PDF can be opened
            try:
                doc = fitz.open(stream=content, filetype="pdf")
                doc.close()
                return content
            except Exception as e:
                raise DocumentReadError(f"Invalid PDF file: {e}")
                
        except Exception as e:
            raise DocumentReadError(f"Failed to read PDF file: {e}")