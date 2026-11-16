from typing import List, Optional
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass
class CustomerEntry:
    name: str
    code: str


@dataclass
class XMLData:
    cls_brand: int
    cls_intent: int
    detect: str
    brand: str
    cls_range: int

    @classmethod
    def from_xml_string(cls, xml_string: str) -> 'XMLData':
        """Parse XML string and return an XMLData object."""
        root = ET.fromstring(f"<root>{xml_string}</root>")
        
        return cls(
            cls_brand=int(root.find('cls_brand').text),
            cls_intent=int(root.find('cls_intent').text),
            brand=root.find('brand').text,
            detect=root.find('detect').text,
            cls_range=int(root.find('cls_range').text)
        )


# Ví dụ sử dụng
def demo_parser():
    xml_data = """
        <cls_brand>0</cls_brand>
        <brand>null</brand>
        <cls_intent>0</cls_intent>
        <detect>null</detect>
    """
    
    parsed_data = XMLData.from_xml_string(xml_data)
    print(f"cls brand: {parsed_data.cls_brand}")
    print(f"Brand: {parsed_data.brand}")
    print(f"cls_intent: {parsed_data.cls_intent}")
    print(f"cls_detect: {parsed_data.cls_detect}")


if __name__ == "__main__":
    demo_parser()