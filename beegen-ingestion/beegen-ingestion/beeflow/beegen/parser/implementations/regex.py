from ..base_parser import BaseOutputParser
from ..exceptions import OutputParserError
from typing import Dict, Any
import re


class RegexOutputParser(BaseOutputParser):
    """Parse output using regex pattern"""
    
    def __init__(self, pattern: str):
        self.pattern = pattern
        try:
            self.regex = re.compile(pattern)
        except re.error as e:
            raise OutputParserError(f"Invalid regex pattern: {str(e)}")
    
    async def parse(self, text: str) -> Dict[str, Any]:
        try:
            text = self.clean_text(text)
            match = self.regex.match(text)
            if match:
                return match.groupdict()
            return {}
        except Exception as e:
            raise OutputParserError(f"Failed to parse with regex: {str(e)}")
        

async def main():
    _valid = """Email: john.doe@example.com
Phone: 123-456-7890
ID: ABC123"""

    pattern = r"Email: (?P<email>[^\n]+)\nPhone: (?P<phone>[^\n]+)\nID: (?P<id>[^\n]+)"
    
    _parser = RegexOutputParser(pattern=pattern)
    output = await _parser.parse(_valid)
    if output:
        print(f"test 1 successful!, output = {output}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())