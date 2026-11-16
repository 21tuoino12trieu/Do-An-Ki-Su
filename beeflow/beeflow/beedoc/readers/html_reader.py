import aiofiles
from pathlib import Path

from beedoc.core.interfaces import DocumentReader
from beedoc.core.entities import DocumentMetadata, DocumentType
from beedoc.core.exceptions import DocumentReadError, DocumentValidationError

class HtmlReader(DocumentReader):
    """Reader for HTML documents."""
    
    async def validate_input(self, metadata: DocumentMetadata) -> bool:
        """Validate if the HTML can be processed."""
        if metadata.document_type != DocumentType.HTML:
            return False
        
        if metadata.path:
            path = Path(metadata.path)
            if not path.exists():
                raise DocumentValidationError(f"File not found: {metadata.path}")
            
            if path.suffix.lower() not in ['.html', '.htm']:
                raise DocumentValidationError(f"Expected HTML file, got: {path.suffix}")
        
        return True
    
    async def read_metadata(self, metadata: DocumentMetadata) -> DocumentMetadata:
        """Read and enrich HTML metadata."""
        if metadata.content:
            metadata.size_bytes = len(metadata.content)
            return metadata
        
        return metadata
    
    async def read_content(self, metadata: DocumentMetadata) -> bytes:
        """Load HTML content as bytes."""
        if metadata.content:
            return metadata.content
        
        if not metadata.path:
            raise DocumentReadError("No path or content provided")
        
        try:
            async with aiofiles.open(metadata.path, 'rb') as f:
                content = await f.read()
            return content
                
        except Exception as e:
            raise DocumentReadError(f"Failed to read HTML file: {e}")