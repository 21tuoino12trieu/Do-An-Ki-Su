# BeeDoc

A flexible, async document processing library for Python that converts documents (images, PDFs) into multiple output formats.

## Features

- **Multiple Input Types**: Images (JPG, PNG, GIF, BMP, TIFF), PDFs, and text-based documents (TXT, CSV, JSON, HTML, Markdown, DOCX)
- **Flexible Output Formats**: NumPy arrays, Base64 strings, or extracted text
- **Async/Await**: Built with asyncio for efficient concurrent processing
- **Batch Processing**: Process multiple documents in parallel
- **Configurable**: Customize dimensions, quality, and output format

## Installation

```bash
pip install opencv-python numpy pillow pymupdf aiofiles
```

## Quick Start

### Basic Usage

```python
import asyncio
from beedoc.processor import DocumentProcessingPipeline

async def main():
    pipeline = DocumentProcessingPipeline()
    
    # Process an image or PDF
    result = await pipeline.process_from_path("document.pdf")
    
    print(f"Processed {result.total_pages} pages")
    for page in result.pages:
        print(f"Page {page.page_number}: {page.image_data.shape}")

asyncio.run(main())
```

### Custom Configuration

```python
from beedoc.core.entities import ProcessingConfig, OutputFormat

config = ProcessingConfig(
    max_dimension=1200,
    output_format=OutputFormat.BASE64,
    quality=95
)

pipeline = DocumentProcessingPipeline(config=config)
result = await pipeline.process_from_path("image.jpg")
```

### Text Extraction from PDFs

```python
config = ProcessingConfig(output_format=OutputFormat.TEXT)
result = await pipeline.process_from_path("document.pdf", config)

for page in result.pages:
    print(f"Page {page.page_number}: {page.text_data}")
```

### Batch Processing

```python
file_paths = ["doc1.pdf", "doc2.jpg", "doc3.png"]

def progress(current, total):
    print(f"Processing {current}/{total}")

results = await pipeline.process_batch_from_paths(
    file_paths,
    progress_callback=progress
)
```

### Process from Bytes

```python
from beedoc.core.entities import DocumentType

with open("document.pdf", "rb") as f:
    content = f.read()

result = await pipeline.process_from_bytes(
    name="document.pdf",
    content=content,
    document_type=DocumentType.PDF
)
```

## Output Formats

| Format | Description | Use Case |
|--------|-------------|----------|
| `NUMPY_ARRAY` | NumPy arrays (default) | Computer vision, ML preprocessing |
| `BASE64` | Base64-encoded PNG strings | Web applications, API responses |
| `TEXT` | Extracted text content | Text analysis, NLP (PDF only) |

## Configuration Options

```python
ProcessingConfig(
    max_dimension=1200,          # Max width/height in pixels
    output_format=OutputFormat.NUMPY_ARRAY,  # Output format
    preserve_aspect_ratio=True,  # Maintain aspect ratio
    quality=95                   # Image quality (1-100)
)
```

## Architecture

The library follows a clean architecture pattern:

- **Readers**: Handle document loading and validation (`ImageReader`, `PdfReader`, etc.)
- **Renderers**: Convert documents to target formats (`NumpyRenderer`, `Base64Renderer`, `TextRenderer`)
- **Factories**: Create appropriate readers and renderers based on document/output type
- **Processor**: Orchestrates the reading and rendering pipeline

## Error Handling

```python
from beedoc.core.exceptions import DocumentProcessingError

try:
    result = await pipeline.process_from_path("document.pdf")
except DocumentProcessingError as e:
    print(f"Processing failed: {e}")
    if e.details:
        print(f"Details: {e.details}")
```

## Supported Document Types

- **Images**: JPG, JPEG, PNG, GIF, BMP, TIFF
- **PDFs**: Full support for rendering and text extraction
- **Text**: TXT, CSV, JSON, HTML, Markdown, DOCX (readers implemented)

## API Reference

### DocumentProcessingPipeline

Main interface for document processing.

**Methods:**
- `process_from_path(file_path, config, progress_callback)` - Process from file path
- `process_from_bytes(name, content, document_type, config)` - Process from bytes
- `process_batch_from_paths(file_paths, config, progress_callback)` - Batch process files

### ProcessingResult

Contains processing results.

**Attributes:**
- `document_name` - Name of the processed document
- `document_type` - Type of document
- `total_pages` - Total number of pages
- `pages` - List of `ProcessedPage` objects
- `processing_time_ms` - Processing time in milliseconds

### ProcessedPage

Represents a single processed page.

**Attributes:**
- `page_number` - Page number (1-based)
- `image_data` - NumPy array or Base64 string
- `text_data` - Extracted text content
- `width`, `height` - Dimensions in pixels

## License

[Your License Here]