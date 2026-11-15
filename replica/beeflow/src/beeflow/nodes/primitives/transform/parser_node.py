from dataclasses import dataclass
from beeflow.nodes.base_node import BaseNode
from beeflow.configs import NodeConfig, NodeType
from beegen.tools.schema.param import ParamSet
from beegen.parser.parser_factory import OutputParserFactory
from beegen.configs import ParserType
from typing import Dict, Any, Optional, List
from pydantic import model_validator


class ParserNodeConfig(NodeConfig):
    """Configuration for parser node to convert text -> dict in the workflow."""
    type: NodeType = "parser"
        
    format: ParserType = ParserType.XML
    
    # Optional attributes for specific parser types
    separator: Optional[str] = None  # For KEY_VALUE
    template: Optional[str] = None   # For STRUCTURED
    pattern: Optional[str] = None    # For REGEX
    
    
@dataclass
class ExtractField:
    """Represents a field to extract with its path and type information."""
    output_key: str      # The final key name (e.g., "address")
    chain_path: List[str]  # Full path (e.g., ["company", "user", "address"])
    type_hint: str       # Type information (e.g., "dict", "str", "list")
    
    @classmethod
    def from_string(cls, schema_str: str) -> 'ExtractField':
        """Parse schema string like 'company.user.address: dict' into ExtractField."""
        if ":" not in schema_str:
            schema_str += ": Any"
        
        chain_text, type_hint = schema_str.split(":", 1)
        chain_path = chain_text.strip().split(".")
        output_key = chain_path[-1]
        
        return cls(
            output_key=output_key,
            chain_path=chain_path,
            type_hint=type_hint.strip()
        )
    

class ParserNode(BaseNode):
    """Node for parsing text into structured data using various parsers.
    
    This node takes text as input and uses the configured parser to convert
    it into a structured dictionary format.
    """
    
    type: NodeType = "parser"
    
    __slots__ = [
        'backend',  # The parser implementation
        'format',
        'separator',
        'template',
        'pattern',
        'extract_schema',
        'extract_fields'
    ]
    
    input_schema: ParamSet = (
        ParamSet.new()
            .var("text: str", required=True)
            .build()
    )
    
    def __init__(
        self,
        format: Optional[ParserType] = None,
        extract_schema: List[str] = None,
        separator: Optional[str] = None,
        template: Optional[str] = None,
        pattern: Optional[str] = None,
        **kwargs
    ):
        """Initialize ParserNode from either config or kwargs.
        
        Args:
            format: Parser format type
            extract_schema: List of output variable definitions
            separator: Separator for KEY_VALUE parser
            template: Template for STRUCTURED parser
            pattern: Pattern for REGEX parser
            **kwargs: Additional keyword arguments for NodeConfig
        """
        
        super().__init__(**kwargs)
        
        self.format = format or ParserType.XML
        self.separator = separator
        self.template = template
        self.pattern = pattern
        self.extract_schema = extract_schema
        
        if self.extract_schema:
            # Parse schema into structured format
            self.extract_fields = [
                ExtractField.from_string(schema_str) 
                for schema_str in self.extract_schema
            ]
            
            # Build output schema from extract_fields
            output_schema = ParamSet.new()
            for field in self.extract_fields:
                output_schema = output_schema.var(f"{field.output_key}: {field.type_hint}")
            self.output_schema = output_schema.build()
        else:
            raise TypeError(f"{self.name}'s extract_schema has not been provided, required list of var names")
        
        self.backend = OutputParserFactory.create(
            format=self.format,
            separator=self.separator,
            template=self.template,
            pattern=self.pattern
        )
        
        self.core = self._process

    def _extract_value_by_path(self, data: Dict[str, Any], chain_path: List[str]) -> Any:
        """Extract value from nested dictionary using chain path."""
        current = data
        for key in chain_path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current
        
    async def _process(self, text: str) -> Dict[str, Any]:
        """Parse text and return structured data according to extract_fields."""
        
        if not text:
            return {}
        
        # Parse the text using the backend parser
        parsed_data = await self.backend.parse(text)
        
        # Extract values according to extract_fields
        result = {}
        for field in self.extract_fields:
            extracted_value = self._extract_value_by_path(parsed_data, field.chain_path)
            result[field.output_key] = extracted_value
        
        return result

    def specific_metadata(self) -> Dict[str, Any]:
        """Return subclass-specific metadata dictionary."""
        return {
            "format": self.format,
            "separator": self.separator,
            "template": self.template,
            "pattern": self.pattern
        }
        

    

