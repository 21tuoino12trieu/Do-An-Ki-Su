from ..base_parser import BaseOutputParser
from ..exceptions import OutputParserError
from typing import Dict, Any
import re


class StructuredOutputParser(BaseOutputParser):
    """Parse output that follows a specific structure/template"""
    
    def __init__(self, template: str):
        self.template = template
        # Convert template into regex pattern
        pattern = template
        # Replace placeholder markers with named capture groups
        pattern = re.sub(r'{(\w+)}', lambda m: f'(?P<{m.group(1)}>.+?)', pattern)
        self.regex = re.compile(pattern, re.DOTALL)
    
    async def parse(self, text: str) -> Dict[str, Any]:
        try:
            text = self.clean_text(text)
            match = self.regex.match(text)
            if match:
                return match.groupdict()
            raise OutputParserError("Text does not match template structure")
        except Exception as e:
            raise OutputParserError(f"Failed to parse structured string: {str(e)}")
        
        
async def main():
    _valid = """<output>co_lien_quan</output>"""
    
    template = "<output>{label}</output>"
    
    _parser = StructuredOutputParser(template=template)
    output = await _parser.parse(_valid)
    if output:
        print(f"test 1 successful!, output = {output}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())