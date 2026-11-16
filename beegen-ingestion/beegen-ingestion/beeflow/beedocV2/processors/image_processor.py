# beedocV2/processors/image_processor.py
"""
Image document processor for all image formats.

This processor handles image files including raster and vector formats, providing
conversion to various output representations including numpy arrays for processing,
base64 encoding for web applications, and raw bytes for storage or transmission.

Supported document types:
- JPG, JPEG: JPEG compressed images
- PNG: Portable Network Graphics with transparency support
- GIF: Graphics Interchange Format with animation support
- BMP: Windows Bitmap format
- TIFF: Tagged Image File Format for high-quality images
- SVG: Scalable Vector Graphics (handled as text/bytes)

Supported output formats:
- NUMPY_ARRAY: NumPy array representation for image processing
- BASE64: Base64 encoded string for web embedding
- BYTES: Raw binary data for storage or transmission

The processor intelligently handles different image formats, preserves image
properties and metadata, handles transparency and color modes, and provides
optimized representations for different use cases.
"""

import base64
import io
from typing import Any, Dict, Set, Tuple, Optional
import numpy as np
from PIL import Image, ImageFile

from ..entities.document import Document
from ..entities.document_types import DocumentType
from ..entities.output_formats import OutputFormat, OutputStructure, ProcessedContent, create_single_content
from .base import BaseProcessor, FormatMethodMixin, ProcessorError


# Enable loading of truncated images
ImageFile.LOAD_TRUNCATED_IMAGES = True


class ImageProcessingError(ProcessorError):
    """Raised when image processing fails."""
    pass


class ImageProcessor(BaseProcessor, FormatMethodMixin):
    """
    Processor for image documents in various formats.
    
    Handles loading, processing, and conversion of image files to different
    output representations. Supports both raster images (with PIL/Pillow)
    and vector graphics (SVG as text/bytes). Provides format-specific
    optimizations and maintains image quality and metadata.
    """
    
    SUPPORTED_TYPES: Set[DocumentType] = {
        DocumentType.JPG,
        DocumentType.JPEG,
        DocumentType.PNG,
        DocumentType.GIF,
        DocumentType.BMP,
        DocumentType.TIFF,
        DocumentType.SVG
    }
    
    SUPPORTED_FORMATS: Set[OutputFormat] = {
        OutputFormat.NUMPY_ARRAY,
        OutputFormat.BASE64,
        OutputFormat.BYTES
    }
    
    # PIL format mapping
    PIL_FORMATS = {
        DocumentType.JPG: 'JPEG',
        DocumentType.JPEG: 'JPEG',
        DocumentType.PNG: 'PNG',
        DocumentType.GIF: 'GIF',
        DocumentType.BMP: 'BMP',
        DocumentType.TIFF: 'TIFF'
    }
    
    def process(self, document: Document, output_format: OutputFormat, 
                output_structure: OutputStructure) -> ProcessedContent:
        """
        Process image document to requested format.
        
        Args:
            document: Image document to process
            output_format: Target output format
            output_structure: Target output structure (only SINGLE supported)
            
        Returns:
            ProcessedContent with image data in requested format
        """
        # Validate request
        self.validate_request(document, output_format, output_structure)
        
        # Images only support SINGLE structure
        if output_structure != OutputStructure.SINGLE:
            output_structure = OutputStructure.SINGLE
        
        # Load content
        raw_content = self.load_content(document)
        
        # Handle SVG separately (text-based)
        if document.document_type == DocumentType.SVG:
            return self._process_svg(raw_content, output_format, document)
        
        # Process raster image
        return self._process_raster_image(raw_content, output_format, document)
    
    def _process_svg(self, content: bytes, output_format: OutputFormat, 
                    document: Document) -> ProcessedContent:
        """
        Process SVG image (vector format).
        
        Args:
            content: SVG content as bytes
            output_format: Target output format
            document: Document metadata
            
        Returns:
            ProcessedContent with SVG data
        """
        metadata = {
            'image_type': 'svg',
            'is_vector': True,
            'size_bytes': len(content),
            'format': 'svg'
        }
        
        if output_format == OutputFormat.BYTES:
            result = content
        elif output_format == OutputFormat.BASE64:
            result = base64.b64encode(content).decode('ascii')
        elif output_format == OutputFormat.NUMPY_ARRAY:
            # SVG can't be directly converted to numpy array
            raise ImageProcessingError("SVG images cannot be converted to numpy arrays. Convert to raster format first.")
        else:
            raise ImageProcessingError(f"Unsupported format {output_format.value} for SVG")
        
        return create_single_content(result, output_format, metadata)
    
    def _process_raster_image(self, content: bytes, output_format: OutputFormat,
                             document: Document) -> ProcessedContent:
        """
        Process raster image using PIL.
        
        Args:
            content: Image content as bytes
            output_format: Target output format
            document: Document metadata
            
        Returns:
            ProcessedContent with processed image data
        """
        try:
            # Load image with PIL
            with Image.open(io.BytesIO(content)) as image:
                # Get image metadata
                metadata = self._extract_image_metadata(image, document.document_type)
                
                # Store image data for format methods
                self._image = image.copy()  # Copy to avoid issues with context manager
                self._original_content = content
                self._metadata = metadata
                
                # Dispatch to format method
                result = self.dispatch_format_method(self._image, output_format, OutputStructure.SINGLE)
                
                return create_single_content(result, output_format, metadata)
                
        except Exception as e:
            raise ImageProcessingError(f"Failed to process image: {str(e)}")
    
    def _extract_image_metadata(self, image: Image.Image, doc_type: DocumentType) -> Dict[str, Any]:
        """
        Extract metadata from PIL image.
        
        Args:
            image: PIL Image object
            doc_type: Document type
            
        Returns:
            Dictionary with image metadata
        """
        metadata = {
            'width': image.width,
            'height': image.height,
            'mode': image.mode,
            'format': image.format or doc_type.value.upper(),
            'has_transparency': self._has_transparency(image),
            'color_mode': self._get_color_mode_info(image.mode),
            'is_animated': getattr(image, 'is_animated', False),
            'n_frames': getattr(image, 'n_frames', 1)
        }
        
        # Add EXIF data if available
        if hasattr(image, '_getexif') and image._getexif():
            try:
                exif = image._getexif()
                metadata['has_exif'] = True
                metadata['exif_keys'] = len(exif) if exif else 0
            except:
                metadata['has_exif'] = False
        
        return metadata
    
    def _has_transparency(self, image: Image.Image) -> bool:
        """Check if image has transparency."""
        return (
            image.mode in ('RGBA', 'LA') or
            (image.mode == 'P' and 'transparency' in image.info)
        )
    
    def _get_color_mode_info(self, mode: str) -> Dict[str, Any]:
        """Get information about image color mode."""
        mode_info = {
            'L': {'name': 'grayscale', 'channels': 1, 'has_alpha': False},
            'LA': {'name': 'grayscale_alpha', 'channels': 2, 'has_alpha': True},
            'RGB': {'name': 'rgb', 'channels': 3, 'has_alpha': False},
            'RGBA': {'name': 'rgba', 'channels': 4, 'has_alpha': True},
            'CMYK': {'name': 'cmyk', 'channels': 4, 'has_alpha': False},
            'P': {'name': 'palette', 'channels': 1, 'has_alpha': False},
            '1': {'name': 'bilevel', 'channels': 1, 'has_alpha': False}
        }
        
        return mode_info.get(mode, {'name': mode, 'channels': 0, 'has_alpha': False})
    
    def to_numpy_array(self, image: Image.Image, structure: OutputStructure) -> np.ndarray:
        """
        Convert image to numpy array.
        
        Args:
            image: PIL Image object
            structure: Output structure (ignored)
            
        Returns:
            NumPy array representation of image
        """
        # Convert to RGB if necessary (for consistent output)
        if image.mode == 'P':
            # Convert palette to RGB
            image = image.convert('RGB')
        elif image.mode == 'CMYK':
            # Convert CMYK to RGB
            image = image.convert('RGB')
        
        # Convert to numpy array
        array = np.array(image)
        
        # Ensure consistent shape (H, W, C) even for grayscale
        if len(array.shape) == 2:
            array = np.expand_dims(array, axis=2)
        
        return array
    
    def to_base64(self, image: Image.Image, structure: OutputStructure) -> str:
        """
        Convert image to base64 string.
        
        Args:
            image: PIL Image object  
            structure: Output structure (ignored)
            
        Returns:
            Base64 encoded image string with data URL prefix
        """
        # Use original content if available for better quality
        if hasattr(self, '_original_content'):
            content = self._original_content
            
            # Determine MIME type
            format_name = image.format or 'JPEG'
            mime_type = f"image/{format_name.lower()}"
            if mime_type == 'image/jpeg':
                mime_type = 'image/jpeg'
            
        else:
            # Re-encode image
            output = io.BytesIO()
            format_name = image.format or 'PNG'
            
            # Save with optimal settings
            if format_name == 'JPEG':
                image.save(output, format='JPEG', quality=85, optimize=True)
                mime_type = 'image/jpeg'
            else:
                image.save(output, format='PNG', optimize=True)
                mime_type = 'image/png'
            
            content = output.getvalue()
        
        # Encode to base64
        base64_data = base64.b64encode(content).decode('ascii')
        
        # Return with data URL prefix for web use
        return f"data:{mime_type};base64,{base64_data}"
    
    def to_bytes(self, image: Image.Image, structure: OutputStructure) -> bytes:
        """
        Convert image to bytes.
        
        Args:
            image: PIL Image object
            structure: Output structure (ignored)
            
        Returns:
            Raw image bytes
        """
        # Use original content if available
        if hasattr(self, '_original_content'):
            return self._original_content
        
        # Re-encode image
        output = io.BytesIO()
        format_name = image.format or 'PNG'
        
        # Save with optimal settings
        if format_name == 'JPEG':
            image.save(output, format='JPEG', quality=90, optimize=True)
        elif format_name == 'PNG':
            image.save(output, format='PNG', optimize=True)
        else:
            # Default to PNG for unknown formats
            image.save(output, format='PNG')
        
        return output.getvalue()