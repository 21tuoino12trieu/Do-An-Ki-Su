from .base_parser import BaseOutputParser
from beegen.configs import ParserType
from .exceptions import OutputParserError
from .implementations.json import JSONOutputParser
from .implementations.key_value import KeyValueOutputParser
from .implementations.regex import RegexOutputParser
from .implementations.structured import StructuredOutputParser
from .implementations.xml import XMLOutputParser
from .implementations.yaml import YAMLOutputParser
from typing import Optional, Callable, Union


class OutputParserFactory:
    """Factory for creating output parsers"""
    
    @staticmethod
    def create(
        format: ParserType,
        separator: Optional[str] = None,  # For KEY_VALUE
        template: Optional[str] = None,  # For STRUCTURED
        pattern: Optional[str] = None,    # For REGEX
        parser_fn: Optional[Union[Callable, str]] = None
    ) -> BaseOutputParser:
        if format == ParserType.JSON:
            return JSONOutputParser()
        elif format == ParserType.YAML:
            return YAMLOutputParser()
        elif format == ParserType.XML:
            return XMLOutputParser()
        elif format == ParserType.KEY_VALUE:
            return KeyValueOutputParser(separator=separator or ":")
        elif format == ParserType.REGEX:
            if not pattern:
                raise OutputParserError("Regex pattern is required")
            return RegexOutputParser(pattern=pattern)
        elif format == ParserType.STRUCTURED:
            if not template:
                raise OutputParserError("Structure template is required")
            return StructuredOutputParser(template=template)
        else:
            raise OutputParserError(f"Unknown parser type: {format}")
        

async def main():
    
    test_input = """<output>co_lien_quan</output>"""
    
    template = "<output>{label}</output>"
    
    parser = OutputParserFactory.create(
        format=ParserType.XML,
    )
    result = await parser.parse(text=test_input)
    print(result)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())