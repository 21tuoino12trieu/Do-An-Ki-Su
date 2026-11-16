from ..base_parser import BaseOutputParser
from ..exceptions import OutputParserError

from typing import Dict, Any
import xml.etree.ElementTree as ET


class XMLOutputParser(BaseOutputParser):
    """Parse XML formatted output"""
    
    def _xml_to_dict(self, element: ET.Element) -> Dict[str, Any]:
        """Convert XML element to dictionary recursively"""
        result = {}
        
        # Handle attributes
        if element.attrib:
            result.update(element.attrib)
            
        # Handle children
        children = list(element)
        if children:
            # Group children by tag
            child_groups = {}
            for child in children:
                if child.tag not in child_groups:
                    child_groups[child.tag] = []
                child_groups[child.tag].append(child)
            
            # Process each group
            for tag, group in child_groups.items():
                if len(group) == 1:
                    # Single child
                    child = group[0]
                    if len(child) > 0:
                        # Child has children
                        result[tag] = self._xml_to_dict(child)
                    else:
                        # Child is a leaf node
                        result[tag] = child.text or ""
                else:
                    # Multiple children with same tag
                    result[tag] = [
                        self._xml_to_dict(child) if len(child) > 0 else child.text or ""
                        for child in group
                    ]
        else:
            # No children, just text content
            text = element.text
            if text is not None and text.strip():
                result["text"] = text.strip()
                
        return result
    
    async def parse(self, text: str) -> Dict[str, Any]:
        try:
            text = self.clean_text(text)
            # Add root element if not present
            if not text.startswith('<?xml') and not text.startswith('<root'):
                text = f'<root>{text}</root>'
            root = ET.fromstring(text)
            return self._xml_to_dict(root)
        except ET.ParseError as e:
            raise OutputParserError(f"Failed to parse XML: {str(e)}")
        except Exception as e:
            raise OutputParserError(f"XML parsing error: {str(e)}") 
        

async def main():
    _valid = """<intent>transaction_complaint</intent>
        <complaint_type>loại_khiếu_nại_chi_tiết</complaint_type>
        <topic>chủ_đề</topic>
        <greeting>true/false</greeting>"""

    _invalid = """<person>
    <name>John Doe</name>
    <age>30</age>
    </skills>  <!-- Unmatched tag -->
</person>"""

    _parser = XMLOutputParser()
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