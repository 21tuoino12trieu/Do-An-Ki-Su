from ..base_parser import BaseOutputParser
from ..exceptions import OutputParserError
import json
from typing import Dict, Any


class JSONOutputParser(BaseOutputParser):
    """Parse JSON formatted output"""
    
    async def parse(self, text: str) -> Dict[str, Any]:
        try:
            text = self.clean_text(text)
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise OutputParserError(f"Failed to parse JSON: {str(e)}")
        

async def main():
    json_valid = """{
    "name": "John Doe",
    "age": 30,
    "skills": ["Python", "AI"],
    "address": {
        "city": "New York",
        "country": "USA"
    }
}"""

    json_invalid = """{
    "name": "John Doe",
    age: 30,  // Missing quotes
}"""

    json_parser = JSONOutputParser()
    output = await json_parser.parse(json_valid)
    print(output)
    # output_invalid = await json_parser.parse(json_invalid)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())