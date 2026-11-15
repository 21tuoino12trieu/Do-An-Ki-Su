from ..base_parser import BaseOutputParser
from ..exceptions import OutputParserError
from typing import Dict, Any


class KeyValueOutputParser(BaseOutputParser):
    """Parse key-value pair formatted output"""
    
    def __init__(self, separator: str = ":"):
        self.separator = separator
    
    async def parse(self, text: str) -> Dict[str, Any]:
        try:
            text = self.clean_text(text)
            result = {}
            for line in text.split('\n'):
                if self.separator in line:
                    key, value = line.split(self.separator, 1)
                    result[key.strip()] = value.strip()
            return result
        except Exception as e:
            raise OutputParserError(f"Failed to parse key-value pairs: {str(e)}")
        

async def main():
    _valid = """name   :   John Doe  
age:30
city :New York"""

    _invalid = """name: John Doe
age  30  # Missing separator
city: New York"""

    _parser = KeyValueOutputParser()
    output = await _parser.parse(_valid)
    if output:
        print(f"test 1 successful!, output = {output}")
    try:
        output_invalid = await _parser.parse(_invalid)
        print(output_invalid)
    except OutputParserError:
        print("test 2 successful!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())