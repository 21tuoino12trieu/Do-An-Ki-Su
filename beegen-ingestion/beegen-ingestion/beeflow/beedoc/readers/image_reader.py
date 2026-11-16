import aiofiles
from pathlib import Path
from PIL import Image
import io

from beedoc.core.interfaces import DocumentReader
from beedoc.core.entities import DocumentMetadata, DocumentType
from beedoc.core.exceptions import DocumentReadError, DocumentValidationError


class ImageReader(DocumentReader):
    """Reader for image documents."""
    
    SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}
    
    async def validate_input(self, metadata: DocumentMetadata) -> bool:
        """validate if the image can be processed."""
        if metadata.document_type != DocumentType.IMAGE:
            return False
        
        if metadata.path:
            path = Path(metadata.path)
            if not path.exists():
                raise DocumentValidationError(f"File not found: {metadata.path}")

            if path.suffix.lower() not in self.SUPPORTED_FORMATS:
                raise DocumentValidationError(f"Unsupported image format: {path.suffix}")
        
        return True
    
    async def read_metadata(self, metadata: DocumentMetadata) -> DocumentMetadata:
        """Read and enrich image metadata."""
        if metadata.content:
            # Try to get image info from bytes
            try:
                with Image.open(io.BytesIO(metadata.content)) as img:
                    metadata.size_bytes = len(metadata.content)
                return metadata
            except Exception as e:
                raise DocumentValidationError(f"Invalid image content: {e}")
        
        return metadata
    
    async def read_content(self, metadata: DocumentMetadata) -> bytes:
        """Load image content as bytes."""
        if metadata.content:
            return metadata.content
        
        if not metadata.path:
            raise DocumentReadError("No path or content provided")
        
        try:
            async with aiofiles.open(metadata.path, 'rb') as f:
                content = await f.read()
            
            # Validate the image can be opened
            try:
                with Image.open(io.BytesIO(content)) as img:
                    img.verify()
                return content
            except Exception as e:
                raise DocumentReadError(f"Invalid image file: {e}")
                
        except Exception as e:
            raise DocumentReadError(f"Failed to read image file: {e}")