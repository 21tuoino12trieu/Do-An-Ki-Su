# beedocV2/processors/structured_processor.py
"""
Structured data processor for JSON, XML, and YAML files.

This processor handles structured data formats including JSON, XML, and YAML documents.
It provides parsing, validation, and conversion between structured formats and plain text
representations while preserving data structure and hierarchy.

Supported document types:
- JSON: JavaScript Object Notation files
- XML: Extensible Markup Language documents  
- YAML: YAML Ain't Markup Language files

Supported output formats:
- JSON_STRUCTURED: Parsed and validated JSON objects with proper formatting
- PLAIN_TEXT: Pretty-printed text representation of structured data

The processor intelligently parses structured data, validates syntax, handles nested
structures, and provides clean text representations with proper indentation and
formatting for human readability.
"""

import json
import xml.etree.ElementTree as ET
from typing import Any, Dict, Set, Union
import yaml

from ..entities.document import Document
from ..entities.document_types import DocumentType
from ..entities.output_formats import OutputFormat, OutputStructure, ProcessedContent, create_single_content
from ..utils.file_utils import safe_decode
from .base import BaseProcessor, FormatMethodMixin, ProcessorError


class StructuredDataError(ProcessorError):
    """Raised when structured data parsing fails."""
    pass


class StructuredProcessor(BaseProcessor, FormatMethodMixin):
    """
    Processor for structured data documents (JSON, XML, YAML).
    
    Handles parsing and conversion of structured data formats with validation,
    error handling, and clean formatting for both structured output and human-
    readable text representations. Preserves data hierarchy and provides
    consistent formatting across different input formats.
    """
    
    SUPPORTED_TYPES: Set[DocumentType] = {
        DocumentType.JSON,
        DocumentType.XML,
        DocumentType.YAML
    }
    
    SUPPORTED_FORMATS: Set[OutputFormat] = {
        OutputFormat.JSON_STRUCTURED,
        OutputFormat.PLAIN_TEXT
    }
    
    def process(self, document: Document, output_format: OutputFormat, 
                output_structure: OutputStructure) -> ProcessedContent:
        """
        Process structured document to requested format.
        
        Args:
            document: Structured document to process
            output_format: Target output format
            output_structure: Target output structure (only SINGLE supported)
            
        Returns:
            ProcessedContent with parsed structured data or formatted text
        """
        # Validate request
        self.validate_request(document, output_format, output_structure)
        
        # Structured data only supports SINGLE structure
        if output_structure != OutputStructure.SINGLE:
            output_structure = OutputStructure.SINGLE
        
        # Load and decode content
        raw_content = self.load_content(document)
        text_content = safe_decode(raw_content)
        
        # Parse structured data first
        try:
            parsed_data = self._parse_structured_data(text_content, document.document_type)
        except Exception as e:
            raise StructuredDataError(f"Failed to parse {document.document_type.value}: {str(e)}")
        
        # Store parsed data for format methods
        self._parsed_data = parsed_data
        self._original_type = document.document_type
        
        # Dispatch to format-specific method
        processed_content = self.dispatch_format_method(parsed_data, output_format, output_structure)
        
        # Create result
        metadata = {
            'original_type': document.document_type.value,
            'content_length': len(text_content),
            'data_type': type(parsed_data).__name__,
            'has_nested_structure': self._has_nested_structure(parsed_data)
        }
        
        return create_single_content(processed_content, output_format, metadata)
    
    def _parse_structured_data(self, content: str, doc_type: DocumentType) -> Any:
        """
        Parse structured data based on document type.
        
        Args:
            content: Raw text content
            doc_type: Document type for format selection
            
        Returns:
            Parsed data structure (dict, list, or primitive)
            
        Raises:
            StructuredDataError: If parsing fails
        """
        try:
            if doc_type == DocumentType.JSON:
                return json.loads(content)
            
            elif doc_type == DocumentType.YAML:
                return yaml.safe_load(content)
            
            elif doc_type == DocumentType.XML:
                # Parse XML and convert to dict-like structure
                root = ET.fromstring(content)
                return self._xml_to_dict(root)
            
            else:
                raise StructuredDataError(f"Unsupported structured type: {doc_type.value}")
                
        except json.JSONDecodeError as e:
            raise StructuredDataError(f"Invalid JSON syntax: {str(e)}")
        except yaml.YAMLError as e:
            raise StructuredDataError(f"Invalid YAML syntax: {str(e)}")
        except ET.ParseError as e:
            raise StructuredDataError(f"Invalid XML syntax: {str(e)}")
    
    def _xml_to_dict(self, element: ET.Element) -> Dict[str, Any]:
        """
        Convert XML element to dictionary structure.
        
        Args:
            element: XML element to convert
            
        Returns:
            Dictionary representation of XML structure
        """
        result = {}
        
        # Add attributes
        if element.attrib:
            result['@attributes'] = element.attrib
        
        # Add text content
        if element.text and element.text.strip():
            if len(element) == 0:  # No children, just text
                return element.text.strip()
            result['@text'] = element.text.strip()
        
        # Add children
        children = {}
        for child in element:
            child_data = self._xml_to_dict(child)
            
            if child.tag in children:
                # Multiple children with same tag - convert to list
                if not isinstance(children[child.tag], list):
                    children[child.tag] = [children[child.tag]]
                children[child.tag].append(child_data)
            else:
                children[child.tag] = child_data
        
        # Merge children into result
        if children:
            result.update(children)
        
        # If result only has one key and it's text, return just the text
        if len(result) == 1 and '@text' in result:
            return result['@text']
        
        # If result is empty but element has text, return text
        if not result and element.text:
            return element.text.strip()
        
        # Add root element name if this is the root
        if not hasattr(self, '_xml_root_processed'):
            self._xml_root_processed = True
            return {element.tag: result} if result else {element.tag: element.text or ""}
        
        return result
    
    def _has_nested_structure(self, data: Any) -> bool:
        """
        Check if data has nested structure (dicts/lists within dicts/lists).
        
        Args:
            data: Parsed data to check
            
        Returns:
            True if data contains nested structures
        """
        if isinstance(data, dict):
            return any(isinstance(v, (dict, list)) for v in data.values())
        elif isinstance(data, list):
            return any(isinstance(item, (dict, list)) for item in data)
        return False
    
    def to_json_structured(self, data: Any, structure: OutputStructure) -> Dict[str, Any]:
        """
        Convert to structured JSON format.
        
        Args:
            data: Parsed structured data
            structure: Output structure (ignored)
            
        Returns:
            Dictionary with structured data and metadata
        """
        return {
            'data': data,
            'format': 'json_structured',
            'original_type': getattr(self, '_original_type', DocumentType.JSON).value,
            'schema_info': self._analyze_schema(data)
        }
    
    def to_plain_text(self, data: Any, structure: OutputStructure) -> str:
        """
        Convert to pretty-printed plain text format.
        
        Args:
            data: Parsed structured data
            structure: Output structure (ignored)
            
        Returns:
            Human-readable text representation
        """
        original_type = getattr(self, '_original_type', DocumentType.JSON)
        
        if original_type == DocumentType.JSON:
            # Pretty print JSON
            return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
        
        elif original_type == DocumentType.YAML:
            # Convert to YAML format
            return yaml.dump(data, default_flow_style=False, indent=2, sort_keys=True)
        
        elif original_type == DocumentType.XML:
            # Convert back to formatted text representation
            return self._dict_to_formatted_text(data, indent=0)
        
        else:
            # Fallback to JSON format
            return json.dumps(data, indent=2, ensure_ascii=False)
    
    def _dict_to_formatted_text(self, obj: Any, indent: int = 0) -> str:
        """
        Convert dictionary/list structure to formatted text.
        
        Args:
            obj: Object to format
            indent: Current indentation level
            
        Returns:
            Formatted text representation
        """
        indent_str = "  " * indent
        
        if isinstance(obj, dict):
            if not obj:
                return "{}"
            
            lines = []
            for key, value in obj.items():
                if key.startswith('@'):
                    # Special XML attributes/text
                    continue
                
                formatted_value = self._dict_to_formatted_text(value, indent + 1)
                if '\n' in formatted_value:
                    lines.append(f"{indent_str}{key}:")
                    lines.append(formatted_value)
                else:
                    lines.append(f"{indent_str}{key}: {formatted_value}")
            
            return '\n'.join(lines)
        
        elif isinstance(obj, list):
            if not obj:
                return "[]"
            
            lines = []
            for item in obj:
                formatted_item = self._dict_to_formatted_text(item, indent + 1)
                if '\n' in formatted_item:
                    lines.append(f"{indent_str}-")
                    lines.append(formatted_item)
                else:
                    lines.append(f"{indent_str}- {formatted_item}")
            
            return '\n'.join(lines)
        
        elif isinstance(obj, str):
            # Handle multiline strings
            if '\n' in obj:
                return f'|\n{indent_str}  ' + f'\n{indent_str}  '.join(obj.split('\n'))
            return f'"{obj}"' if ' ' in obj or not obj else obj
        
        else:
            return str(obj)
    
    def _analyze_schema(self, data: Any) -> Dict[str, Any]:
        """
        Analyze data structure to provide schema information.
        
        Args:
            data: Parsed data to analyze
            
        Returns:
            Dictionary with schema analysis
        """
        def get_type_info(obj):
            if isinstance(obj, dict):
                return {
                    'type': 'object',
                    'keys': list(obj.keys()),
                    'key_count': len(obj)
                }
            elif isinstance(obj, list):
                return {
                    'type': 'array',
                    'length': len(obj),
                    'item_types': list(set(type(item).__name__ for item in obj[:5]))  # Sample first 5
                }
            else:
                return {
                    'type': type(obj).__name__,
                    'value': str(obj)[:100] + '...' if len(str(obj)) > 100 else str(obj)
                }
        
        return get_type_info(data)