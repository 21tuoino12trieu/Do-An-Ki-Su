from ..base_parser import BaseOutputParser
from ..exceptions import OutputParserError
import yaml
from typing import Dict, Any


class YAMLOutputParser(BaseOutputParser):
    """Parse YAML formatted output"""
    
    async def parse(self, text: str) -> Dict[str, Any]:
        try:
            text = self.clean_text(text)
            return yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise OutputParserError(f"Failed to parse YAML: {str(e)}")
        
        
async def main():
    _valid = """name: John Doe
age: 30
skills:
    - Python
    - AI
address:
    city: New York
    country: USA"""

    _invalid = """name: John Doe
age: 30
    skills:  # Invalid indentation
    - Python"""
    
    print(_valid)

    _parser = YAMLOutputParser()
    output = await _parser.parse(_valid)
    if output:
        print(f"test 1 successful!, output = {output}")
    try:
        output_invalid = await _parser.parse(_invalid)
    except OutputParserError:
        print("test 2 successful!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())