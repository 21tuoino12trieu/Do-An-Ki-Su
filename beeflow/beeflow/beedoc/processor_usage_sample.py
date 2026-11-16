"""
Usage examples for the Document Processing System.
"""

import asyncio
from pathlib import Path
from typing import List

from beedoc.core.entities import DocumentMetadata, ProcessingConfig, OutputFormat, DocumentType
from beedoc.core.exceptions import DocumentProcessingError
from beedoc.processor import DocumentProcessingPipeline, DefaultDocumentProcessor


async def example_basic_usage():
    """Basic usage example."""
    
    # Create a processing pipeline
    pipeline = DocumentProcessingPipeline()
    
    # Process a single image
    try:
        result = await pipeline.process_from_path(r"D:\work\beeflow\data\sample1.jpg")
        print(f"Processed {result.document_name}: {result.total_pages} pages")
        print(f"Processing time: {result.processing_time_ms:.2f}ms")
        
        # Access the processed image data
        for page in result.pages:
            print(f"Page {page.page_number}: {page.image_data.shape}")  # numpy array shape
            
    except DocumentProcessingError as e:
        print(f"Processing failed: {e}")


async def example_custom_config():
    """Example with custom configuration."""
    
    pipeline = DocumentProcessingPipeline(
        config=ProcessingConfig(
            max_dimension=800,
            output_format=OutputFormat.BASE64,
            quality=85
        )
    )
    
    # Process PDF with custom config
    result = await pipeline.process_from_path(r"D:\work\beeflow\data\sample2.pdf")
    
    print(f"Processed {result.total_pages} pages from PDF")
    for page in result.pages:
        print(f"Page {page.page_number}: {len(page.image_data)} characters (base64)")


async def example_batch_processing():
    """Example of batch processing multiple documents."""
    
    pipeline = DocumentProcessingPipeline(config = ProcessingConfig(
        max_dimension=1000,
        output_format=OutputFormat.NUMPY_ARRAY
    ))
    
    # Process multiple files
    file_paths = [
        r"D:\work\beeflow\data\sample1.jpg",
        r"C:\Users\thanglq2\Downloads\image (3).png", 
        r"C:\Users\thanglq2\Downloads\Đánh giá hết kỳ HĐLĐ_Lê Quang Thắng.pdf",
        r"C:\Users\thanglq2\Downloads\FPT AI Open Hackathon Proposal.pdf"
    ]
    
    def progress_callback(current: int, total: int):
        print(f"Progress: {current}/{total} documents processed")
    
    try:
        results = await pipeline.process_batch_from_paths(
            file_paths, 
            progress_callback=progress_callback
        )
        
        total_pages = sum(result.total_pages for result in results)
        print(f"Batch processing complete: {total_pages} total pages processed")
        
    except DocumentProcessingError as e:
        print(f"Batch processing failed: {e}")


async def example_processing_from_bytes():
    """Example of processing document from bytes."""
    
    pipeline = DocumentProcessingPipeline()
    
    # Load file content
    with open(r"D:\work\beeflow\data\sample2.pdf", "rb") as f:
        content = f.read()
    
    # Process from bytes
    result = await pipeline.process_from_bytes(
        name=r"D:\work\beeflow\data\sample2.pdf",
        content=content,
        document_type=DocumentType.PDF,
        config=ProcessingConfig(output_format=OutputFormat.BASE64)
    )
    
    print(f"Processed {result.document_name} from bytes")


async def example_single_page_processing():
    """Example of processing a single page from a document."""
    
    processor = DefaultDocumentProcessor()
    
    # Create metadata for PDF
    metadata = DocumentMetadata.from_path(r"C:\Users\thanglq2\Downloads\Đánh giá hết kỳ HĐLĐ_Lê Quang Thắng.pdf")
    
    # Process only page 5
    page = await processor.process_document_page(
        metadata=metadata,
        page_number=1,
        config=ProcessingConfig(max_dimension=2000)
    )
    
    print(f"Processed page {page.page_number}")
    print(f"Image dimensions: {page.width}x{page.height}")


async def example_error_handling():
    """Example of comprehensive error handling."""
    
    pipeline = DocumentProcessingPipeline()
    
    try:
        # This will fail if file doesn't exist
        result = await pipeline.process_from_path("nonexistent.pdf")
        
    except DocumentProcessingError as e:
        print(f"Processing error: {e}")
        if e.details:
            print(f"Error details: {e.details}")
    
    except Exception as e:
        print(f"Unexpected error: {e}")


async def example_text_extraction():
    """Example of extracting text from PDF."""
    
    pipeline = DocumentProcessingPipeline()
    
    # Configure for text extraction
    config = ProcessingConfig(
        output_format=OutputFormat.TEXT
    )
    
    # Process PDF to extract text
    result = await pipeline.process_from_path(r"C:\Users\thanglq2\Downloads\Đánh giá hết kỳ HĐLĐ_Lê Quang Thắng.pdf", config)
    
    print(f"Extracted text from {result.total_pages} pages")
    for page in result.pages:
        print(f"Page {page.page_number}:")
        print(f"Text: {page.text_data[:100]}...")  # First 100 characters
        print("---")


async def example_pdf_visual_vs_text():
    """Example showing different PDF processing modes."""
    
    pipeline = DocumentProcessingPipeline()
    
    # Process same PDF in different ways
    pdf_path = r"C:\Users\thanglq2\Downloads\Đánh giá hết kỳ HĐLĐ_Lê Quang Thắng.pdf"
    
    # 1. Visual rendering to images
    visual_config = ProcessingConfig(
        output_format=OutputFormat.BASE64,
        max_dimension=800
    )
    visual_result = await pipeline.process_from_path(pdf_path, visual_config)
    
    # 2. Text extraction
    text_config = ProcessingConfig(
        output_format=OutputFormat.TEXT
    )
    text_result = await pipeline.process_from_path(pdf_path, text_config)
    
    print("Visual processing:")
    for page in visual_result.pages:
        print(f"  Page {page.page_number}: {len(page.image_data)} chars (base64)")
    
    print("\nText extraction:")
    for page in text_result.pages:
        print(f"  Page {page.page_number}: {len(page.text_data)} chars (text)")


async def example_format_validation():
    """Example showing format validation."""
    
    pipeline = DocumentProcessingPipeline()
    
    try:
        # This will fail - can't extract text from images
        config = ProcessingConfig(output_format=OutputFormat.TEXT)
        result = await pipeline.process_from_path(r"D:\work\beeflow\data\sample1.jpg", config)
        
    except DocumentProcessingError as e:
        print(f"Expected error: {e}")
    
    # This works - images can be converted to base64
    config = ProcessingConfig(output_format=OutputFormat.BASE64)
    result = await pipeline.process_from_path(r"D:\work\beeflow\data\sample1.jpg", config)
    print(f"Successfully processed image to base64")


# Main example runner
async def main():
    """Run all examples."""
    print("🚀 Document Processing System Examples\n")
    
    examples = [
        ("Basic Usage", example_basic_usage),
        ("Custom Configuration", example_custom_config),
        ("Text Extraction", example_text_extraction),
        ("PDF Visual vs Text", example_pdf_visual_vs_text),
        ("Format Validation", example_format_validation),
        ("Batch Processing", example_batch_processing),
        ("Processing from Bytes", example_processing_from_bytes),
        ("Single Page Processing", example_single_page_processing),
        ("Error Handling", example_error_handling),
    ]
    
    for name, example_func in examples:
        print(f"--- {name} ---")
        try:
            await example_func()
        except Exception as e:
            print(f"Example failed: {e}")
        print()


if __name__ == "__main__":
    asyncio.run(main())