import aiofiles
from pathlib import Path

from beedoc.core.interfaces import DocumentReader
from beedoc.core.entities import DocumentMetadata, DocumentType
from beedoc.core.exceptions import DocumentReadError, DocumentValidationError


class TxtReader(DocumentReader):
    """Reader for text documents."""
    
    async def validate_input(self, metadata: DocumentMetadata) -> bool:
        """Validate if the text file can be processed."""
        if metadata.document_type != DocumentType.TXT:
            return False
        
        if metadata.path:
            path = Path(metadata.path)
            if not path.exists():
                raise DocumentValidationError(f"File not found: {metadata.path}")
            
            if path.suffix.lower() != '.txt':
                raise DocumentValidationError(f"Expected TXT file, got: {path.suffix}")
        
        return True
    
    async def read_metadata(self, metadata: DocumentMetadata) -> DocumentMetadata:
        """Read and enrich text metadata."""
        if metadata.content:
            try:
                # Try to decode as UTF-8 to validate
                metadata.content.decode('utf-8')
                metadata.size_bytes = len(metadata.content)
                return metadata
            except UnicodeDecodeError as e:
                raise DocumentValidationError(f"Invalid text encoding: {e}")
        
        return metadata
    
    async def read_content(self, metadata: DocumentMetadata) -> bytes:
        """Load text content as bytes."""
        if metadata.content:
            return metadata.content
        
        if not metadata.path:
            raise DocumentReadError("No path or content provided")
        
        try:
            async with aiofiles.open(metadata.path, 'rb') as f:
                content = await f.read()
            
            # Validate UTF-8 encoding
            try:
                content.decode('utf-8')
                return content
            except UnicodeDecodeError as e:
                raise DocumentReadError(f"Invalid text encoding: {e}")
                
        except Exception as e:
            raise DocumentReadError(f"Failed to read text file: {e}")