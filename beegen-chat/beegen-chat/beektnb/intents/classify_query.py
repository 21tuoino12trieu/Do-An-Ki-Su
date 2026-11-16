from typing import List, Optional
import xml.etree.ElementTree as ET
from dataclasses import dataclass
import re

# Loại control chars trái luật (XML 1.0)
_ILLEGAL = re.compile(
    r"[\x00-\x08\x0B\x0C\x0E-\x1F\uD800-\uDFFF\uFFFE\uFFFF]"
)

def normalize_xml_text(
    text: str
) -> str:
    
    s = _ILLEGAL.sub("", text)
    # Escape & không phải entity hợp lệ
    s = re.sub(r'&(?!#\d+;|#x[0-9a-fA-F]+;|\w+;)', '&amp;', s)

    print(s)

    return s


@dataclass
class IntentClassify:
    task1: str
    task2: str
    task3: str

    @classmethod
    def from_xml_string(cls, xml_string: str) -> 'IntentClassify':
        """Parse XML string and return an XMLData object."""
        xml_string = normalize_xml_text(xml_string)

        root = ET.fromstring(f"<root>{xml_string}</root>")
        
        return cls(
            task1=root.find('task1').text,
            task2=root.find('task2').text,
            task3=root.find('task3').text
        )
    
@dataclass
class RewriteQuery:
    rewrite: str

    @classmethod
    def from_xml_string(cls, xml_string: str) -> 'RewriteQuery':
        """Parse XML string and return an XMLData object."""
        xml_string = normalize_xml_text(xml_string)

        root = ET.fromstring(f"<root>{xml_string}</root>")
        
        return cls(
            rewrite=root.find('rewrite').text,
        )

@dataclass
class ClassifyTopic:
    topic: str

    @classmethod
    def from_xml_string(cls, xml_string: str) -> 'ClassifyTopic':
        """Parse XML string and return an XMLData object."""
        xml_string = normalize_xml_text(xml_string)

        root = ET.fromstring(f"<root>{xml_string}</root>")
        
        return cls(
            topic=root.find('topic').text,
        )

@dataclass
class VerifyTopic:
    status: str
    topic: str

    @classmethod
    def from_xml_string(cls, xml_string: str) -> 'ClassifyTopic':
        """Parse XML string and return an XMLData object."""
        xml_string = normalize_xml_text(xml_string)

        root = ET.fromstring(f"<root>{xml_string}</root>")
        
        return cls(
            status=root.find('verify_topic').text,
            topic=root.find('topic').text
        )

@dataclass
class VerifyDocument:
    status: str

    @classmethod
    def from_xml_string(cls, xml_string: str) -> 'VerifyDocument':
        """Parse XML string and return an XMLData object."""
        xml_string = normalize_xml_text(xml_string)

        root = ET.fromstring(f"<root>{xml_string}</root>")
        
        return cls(
            status=root.find('verify_document').text,
        )

@dataclass
class CreateSubtask:
    subtask: List[str]

    @classmethod
    def from_xml_string(cls, xml_string: str) -> 'CreateSubtask':
        """Parse XML string and return an XMLData object."""
        xml_string = normalize_xml_text(xml_string)
        
        root = ET.fromstring(f"<root>{xml_string}</root>")
        
        return cls(
            status=root.find('sub_taskss').text,
        )

@dataclass
class ChoiceDocument:
    result: str

    @classmethod
    def from_xml_string(cls, xml_string: str) -> 'CreateSubtask':
        """Parse XML string and return an XMLData object."""
        xml_string = normalize_xml_text(xml_string)
        
        root = ET.fromstring(f"<root>{xml_string}</root>")
        
        return cls(
            result=root.find('result').text,
        )


# Ví dụ sử dụng
def demo_parser():
    xml_data = """
        <rewrite>Thủ tục ... kho quỹ & Sàn giao dịch?></rewrite>
    """
    
    parsed_data = RewriteQuery.from_xml_string(xml_data)
    print(f"cls brand: {parsed_data.rewrite}")

if __name__ == "__main__":
    demo_parser()