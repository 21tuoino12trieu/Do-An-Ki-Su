from typing import List, Optional
import xml.etree.ElementTree as ET
from dataclasses import dataclass

@dataclass
class L1Classify:
    L1: str

    @classmethod
    def from_xml_string(cls, xml_string: str) -> 'L1Classify':
        """Parse XML string and return an XMLData object."""
        root = ET.fromstring(f"<root>{xml_string}</root>")
        
        return cls(
            L1=root.find('L1').text
        )

@dataclass
class ExtractQuery:
    L1: str
    L2: str
    relation: str

    @classmethod
    def from_xml_string(cls, xml_string: str) -> 'ExtractQuery':
        """Parse XML string and return an XMLData object."""
        root = ET.fromstring(f"<root>{xml_string}</root>")
        
        return cls(
            L1=root.find('L1').text,
            L2=root.find('L2').text,
            relation=root.find('relation').text
        )

@dataclass
class CLSQuestion:
    intent: str

    @classmethod
    def from_xml_string(cls, xml_string: str) -> 'CLSQuestion':
        """Parse XML string and return an XMLData object."""
        root = ET.fromstring(f"<root>{xml_string}</root>")
        
        return cls(
            intent=root.find('intent').text
        )

@dataclass
class RewriteQuestion:
    rewrite: str

    @classmethod
    def from_xml_string(cls, xml_string: str) -> 'RewriteQuestion':
        """Parse XML string and return an XMLData object."""
        root = ET.fromstring(f"<root>{xml_string}</root>")
        
        return cls(
            rewrite=root.find('rewrite').text
        )

@dataclass
class CLSSxkd:
    sxkd: str
    major: str
    code: str

    @classmethod
    def from_xml_string(cls, xml_string: str) -> 'RewriteQuestion':
        """Parse XML string and return an XMLData object."""
        root = ET.fromstring(f"<root>{xml_string}</root>")
        
        return cls(
            sxkd=root.find('sxkd').text,
            major=root.find('major').text,
            code=root.find('code').text
        )

@dataclass
class ChoiceDocument:
    id: int
    # score: float

    @classmethod
    def from_xml_string(cls, xml_string: str) -> 'RewriteQuestion':
        """Parse XML string and return an XMLData object."""
        root = ET.fromstring(f"<root>{xml_string}</root>")
        list_id = []
        if root.find('id').text:
            for a in root.find('id').text.split(','):
                try:
                    list_id.append(int(a.strip()))
                except Exception as e:
                    continue
        
        print(list_id)
        
        return cls(
            id=list_id,
            # score=float(root.find('score').text)
        )

if __name__=='__main__':
    cls = ChoiceDocument.from_xml_string(
        f"""<id>  </id>"""
    )

