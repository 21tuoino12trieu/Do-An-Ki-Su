from abc import ABC, abstractmethod
from typing import Dict, Any
import re


class BaseOutputParser(ABC):
    """Base class for all output parsers"""
    
    @abstractmethod
    async def parse(self, text: str) -> Dict[str, Any]:
        """Parse text into structured output"""
        pass

    def clean_text(self, text: str) -> str:
        """Clean and normalize text before parsing"""
        # Remove any markdown code block markers
        text = re.sub(r'```(?:\w+)?\n', '', text)
        text = text.replace('```', '')
        return text.strip()
    

