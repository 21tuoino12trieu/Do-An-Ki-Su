# beedocV2/processors/text_processor.py
"""
Text document processor for plain text and code files.

This processor handles text-based documents including plain text files, markdown,
HTML, CSS, Python, and JavaScript files. It provides conversion between different
text formats while preserving content structure and applying appropriate formatting.

Supported document types:
- TXT: Plain text files
- MD: Markdown files  
- HTML: HTML documents
- CSS: Stylesheet files
- PY: Python source code
- JS: JavaScript source code

Supported output formats:
- PLAIN_TEXT: Raw text content with minimal formatting
- MARKDOWN: Markdown-formatted text with proper escaping
- HTML: HTML-formatted content with syntax highlighting for code

The processor intelligently handles format conversions, applying syntax highlighting
for code files, proper escaping for markdown output, and clean text extraction
for HTML input while maintaining readability and structure.
"""

from typing import Any, Set
import html
import re

from ..entities.document import Document
from ..entities.document_types import DocumentType
from ..entities.output_formats import OutputFormat, OutputStructure, ProcessedContent, create_single_content
from ..utils.file_utils import safe_decode
from .base import BaseProcessor, FormatMethodMixin


class TextProcessor(BaseProcessor, FormatMethodMixin):
    """
    Processor for text-based documents and source code files.
    
    Handles conversion between text formats with intelligent format detection,
    syntax highlighting for code files, and proper escaping/formatting for
    different output targets. Supports both plain text extraction and formatted
    output with preserved structure.
    """
    
    SUPPORTED_TYPES: Set[DocumentType] = {
        DocumentType.TXT,
        DocumentType.MD, 
        DocumentType.HTML,
        DocumentType.CSS,
        DocumentType.PY,
        DocumentType.JS
    }
    
    SUPPORTED_FORMATS: Set[OutputFormat] = {
        OutputFormat.PLAIN_TEXT,
        OutputFormat.MARKDOWN,
        OutputFormat.HTML
    }
    
    # Language mapping for syntax highlighting
    LANGUAGE_MAP = {
        DocumentType.PY: 'python',
        DocumentType.JS: 'javascript', 
        DocumentType.CSS: 'css',
        DocumentType.HTML: 'html',
        DocumentType.MD: 'markdown',
        DocumentType.TXT: 'text'
    }
    

    
    def to_plain_text(self, content: str, structure: OutputStructure) -> str:
        """
        Convert to plain text format.
        
        Args:
            content: Source text content
            structure: Output structure (ignored for text files)
            
        Returns:
            Plain text content with cleaned formatting
        """
        # Handle different input types
        if hasattr(self, '_current_doc_type'):
            doc_type = self._current_doc_type
        else:
            # Fallback: detect from content patterns
            doc_type = self._detect_content_type(content)
        
        if doc_type == DocumentType.HTML:
            # Strip HTML tags and decode entities
            text = re.sub(r'<[^>]+>', '', content)
            text = html.unescape(text)
            # Clean up whitespace
            text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
            return text.strip()
        
        elif doc_type == DocumentType.MD:
            # Remove markdown formatting but preserve structure
            text = content
            # Remove headers
            text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
            # Remove bold/italic
            text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
            text = re.sub(r'\*([^*]+)\*', r'\1', text)
            # Remove links but keep text
            text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
            # Remove code blocks
            text = re.sub(r'```[^`]*```', '', text, flags=re.DOTALL)
            text = re.sub(r'`([^`]+)`', r'\1', text)
            return text.strip()
        
        else:
            # For code files and plain text, return as-is
            return content.strip()
    
    def to_markdown(self, content: str, structure: OutputStructure) -> str:
        """
        Convert to markdown format.
        
        Args:
            content: Source text content  
            structure: Output structure (ignored for text files)
            
        Returns:
            Markdown-formatted content with proper escaping
        """
        doc_type = getattr(self, '_current_doc_type', self._detect_content_type(content))
        
        if doc_type == DocumentType.MD:
            # Already markdown, return as-is
            return content
        
        elif doc_type == DocumentType.HTML:
            # Basic HTML to markdown conversion
            text = content
            # Convert headers
            text = re.sub(r'<h([1-6])[^>]*>([^<]+)</h[1-6]>', lambda m: '#' * int(m.group(1)) + ' ' + m.group(2), text)
            # Convert bold/italic
            text = re.sub(r'<(strong|b)[^>]*>([^<]+)</\1>', r'**\2**', text)
            text = re.sub(r'<(em|i)[^>]*>([^<]+)</\1>', r'*\2*', text)
            # Convert code
            text = re.sub(r'<code[^>]*>([^<]+)</code>', r'`\1`', text)
            # Remove other tags
            text = re.sub(r'<[^>]+>', '', text)
            text = html.unescape(text)
            return text.strip()
        
        elif doc_type in [DocumentType.PY, DocumentType.JS, DocumentType.CSS]:
            # Wrap code in markdown code block
            language = self.LANGUAGE_MAP.get(doc_type, 'text')
            return f"```{language}\n{content}\n```"
        
        else:
            # Plain text - escape markdown special characters
            text = content
            # Escape markdown characters
            for char in ['*', '_', '`', '#', '[', ']', '(', ')', '!']:
                text = text.replace(char, '\\' + char)
            return text
    
    def to_html(self, content: str, structure: OutputStructure) -> str:
        """
        Convert to HTML format.
        
        Args:
            content: Source text content
            structure: Output structure (ignored for text files)
            
        Returns:
            HTML-formatted content with syntax highlighting
        """
        doc_type = getattr(self, '_current_doc_type', self._detect_content_type(content))
        
        if doc_type == DocumentType.HTML:
            # Already HTML, return as-is (could add validation/cleanup here)
            return content
        
        elif doc_type == DocumentType.MD:
            # Basic markdown to HTML conversion
            text = html.escape(content)
            # Convert headers
            text = re.sub(r'^(#{1,6})\s+(.+)$', lambda m: f'<h{len(m.group(1))}>{m.group(2)}</h{len(m.group(1))}>', text, flags=re.MULTILINE)
            # Convert bold/italic
            text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
            text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
            # Convert code
            text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
            # Convert line breaks
            text = text.replace('\n', '<br>\n')
            return f'<div class="markdown-content">{text}</div>'
        
        elif doc_type in [DocumentType.PY, DocumentType.JS, DocumentType.CSS]:
            # Wrap in HTML with syntax highlighting class
            language = self.LANGUAGE_MAP.get(doc_type, 'text')
            escaped_content = html.escape(content)
            return f'<pre><code class="language-{language}">{escaped_content}</code></pre>'
        
        else:
            # Plain text - escape and wrap in pre tag
            escaped_content = html.escape(content)
            return f'<pre class="plain-text">{escaped_content}</pre>'
    
    def _detect_content_type(self, content: str) -> DocumentType:
        """
        Detect document type from content patterns.
        
        Args:
            content: Text content to analyze
            
        Returns:
            Most likely DocumentType based on content
        """
        # Check for HTML
        if re.search(r'<html|<head|<body|<!DOCTYPE', content, re.IGNORECASE):
            return DocumentType.HTML
        
        # Check for CSS
        if re.search(r'[{][^}]*[}]|@media|@import', content):
            return DocumentType.CSS
            
        # Check for JavaScript
        if re.search(r'function\s+\w+|var\s+\w+|console\.log|document\.', content):
            return DocumentType.JS
            
        # Check for Python
        if re.search(r'def\s+\w+|import\s+\w+|from\s+\w+|print\(', content):
            return DocumentType.PY
            
        # Check for Markdown
        if re.search(r'^#{1,6}\s+|^\*\s+|\[.+\]\(.+\)', content, re.MULTILINE):
            return DocumentType.MD
            
        # Default to plain text
        return DocumentType.TXT
    
    def dispatch_format_method(self, content: str, output_format: OutputFormat, 
                              output_structure: OutputStructure) -> Any:
        """
        Override to set current document type for format methods.
        
        Args:
            content: Text content to process
            output_format: Target output format
            output_structure: Target output structure
            
        Returns:
            Processed content in requested format
        """
        # Store current document type for format methods to access
        self._current_doc_type = getattr(self, '_processing_doc_type', DocumentType.TXT)
        
        return super().dispatch_format_method(content, output_format, output_structure)
    
    def process(self, document: Document, output_format: OutputFormat, 
                output_structure: OutputStructure) -> ProcessedContent:
        """
        Override process to store document type for format methods.
        
        Args:
            document: Text document to process
            output_format: Target output format  
            output_structure: Target output structure
            
        Returns:
            ProcessedContent with converted text
        """
        # Store document type for format method access
        self._processing_doc_type = document.document_type
        
        # Validate request
        self.validate_request(document, output_format, output_structure)
        
        # Text files only support SINGLE structure
        if output_structure != OutputStructure.SINGLE:
            output_structure = OutputStructure.SINGLE
        
        # Load and decode content
        raw_content = self.load_content(document)
        text_content = safe_decode(raw_content)
        
        # Dispatch to format-specific method
        processed_content = self.dispatch_format_method(text_content, output_format, output_structure)
        
        # Create result
        metadata = {
            'original_type': document.document_type.value,
            'content_length': len(text_content),
            'language': self.LANGUAGE_MAP.get(document.document_type, 'text')
        }
        
        return create_single_content(processed_content, output_format, metadata)