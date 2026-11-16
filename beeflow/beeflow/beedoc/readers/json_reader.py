import aiofiles
import json
from pathlib import Path

from beedoc.core.interfaces import DocumentReader
from beedoc.core.entities import DocumentMetadata, DocumentType
from beedoc.core.exceptions import DocumentReadError, DocumentValidationError


class JsonReader(DocumentReader):
    """Reader for JSON documents."""
    
    async def validate_input(self, metadata: DocumentMetadata) -> bool:
        """Validate if the JSON can be processed."""
        if metadata.document_type != DocumentType.JSON:
            return False
        
        if metadata.path:
            path = Path(metadata.path)
            if not path.exists():
                raise DocumentValidationError(f"File not found: {metadata.path}")
            
            if path.suffix.lower() != '.json':
                raise DocumentValidationError(f"Expected JSON file, got: {path.suffix}")
        
        return True
    
    async def read_metadata(self, metadata: DocumentMetadata) -> DocumentMetadata:
        """Read and enrich JSON metadata."""
        content = metadata.content
        if not content:
            if not metadata.path:
                raise DocumentValidationError("No path or content provided")
            
            try:
                async with aiofiles.open(metadata.path, 'rb') as f:
                    content = await f.read()
            except Exception as e:
                raise DocumentReadError(f"Failed to read JSON file: {e}")
        
        # Validate JSON structure
        try:
            json.loads(content.decode('utf-8'))
            metadata.size_bytes = len(content)
            return metadata
        except json.JSONDecodeError as e:
            raise DocumentValidationError(f"Invalid JSON format: {e}")
    
    async def read_content(self, metadata: DocumentMetadata) -> bytes:
        """Load JSON content as bytes."""
        if metadata.content:
            return metadata.content
        
        if not metadata.path:
            raise DocumentReadError("No path or content provided")
        
        try:
            async with aiofiles.open(metadata.path, 'rb') as f:
                content = await f.read()
            
            # Validate JSON
            try:
                json.loads(content.decode('utf-8'))
                return content
            except json.JSONDecodeError as e:
                raise DocumentReadError(f"Invalid JSON format: {e}")
                
        except Exception as e:
            raise DocumentReadError(f"Failed to read JSON file: {e}")