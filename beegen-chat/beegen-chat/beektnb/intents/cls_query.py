from typing import List, Optional
import xml.etree.ElementTree as ET
from dataclasses import dataclass

@dataclass
class XMLData:
    label: str

    @classmethod
    def from_xml_string(cls, xml_string: str) -> 'XMLData':
        """Parse XML string and return an XMLData object."""
        root = ET.fromstring(f"<root>{xml_string}</root>")
        
        return cls(
            label=root.find('label').text,
        )


# Ví dụ sử dụng
def demo_parser():
    xml_data = """
        <label>SECURITY</label>
    """
    
    parsed_data = XMLData.from_xml_string(xml_data)
    print(f"cls brand: {parsed_data.label}")


if __name__ == "__main__":
    demo_parser()