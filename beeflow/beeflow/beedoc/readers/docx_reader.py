import aiofiles
import io
from pathlib import Path

from beedoc.core.interfaces import DocumentReader
from beedoc.core.entities import DocumentMetadata, DocumentType
from beedoc.core.exceptions import DocumentReadError, DocumentValidationError


class DocxReader(DocumentReader):
    """Reader for DOCX documents."""
    
    async def validate_input(self, metadata: DocumentMetadata) -> bool:
        """Validate if the DOCX can be processed."""
        if metadata.document_type != DocumentType.DOCX:
            return False
        
        if metadata.path:
            path = Path(metadata.path)
            if not path.exists():
                raise DocumentValidationError(f"File not found: {metadata.path}")
            
            if path.suffix.lower() != '.docx':
                raise DocumentValidationError(f"Expected DOCX file, got: {path.suffix}")
        
        return True
    
    async def read_metadata(self, metadata: DocumentMetadata) -> DocumentMetadata:
        """Read and enrich DOCX metadata."""
        if metadata.content:
            # Validate DOCX content
            try:
                # Simple validation by checking if it's a zip file (DOCX is essentially a zip)
                import zipfile
                zipfile.ZipFile(io.BytesIO(metadata.content))
                metadata.size_bytes = len(metadata.content)
                return metadata
            except Exception as e:
                raise DocumentValidationError(f"Invalid DOCX content: {e}")
        
        return metadata
    
    async def read_content(self, metadata: DocumentMetadata) -> bytes:
        """Load DOCX content as bytes."""
        if metadata.content:
            return metadata.content
        
        if not metadata.path:
            raise DocumentReadError("No path or content provided")
        
        try:
            async with aiofiles.open(metadata.path, 'rb') as f:
                content = await f.read()
            
            # Validate the DOCX can be opened
            try:
                import zipfile
                zipfile.ZipFile(io.BytesIO(content))
                return content
            except Exception as e:
                raise DocumentReadError(f"Invalid DOCX file: {e}")
                
        except Exception as e:
            raise DocumentReadError(f"Failed to read DOCX file: {e}")