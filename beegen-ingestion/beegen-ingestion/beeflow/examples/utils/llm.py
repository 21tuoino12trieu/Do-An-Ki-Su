import base64
import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

def schema_detector(
    data: Optional[List[str]],
) -> Dict[str, Any]:
    """
    Choose document content from two possible branch outputs.

    Args:
        data (Optional[List[str]]): Content from branch 1.

    Returns:
        content (Dict[str, Any]): Dictionary containing a list of content pages, or None if no content is found.
    """
    if data and "pages" in data and isinstance(data["pages"], list):
        return {
            "content": [
                p.get("content", "")
                for p in data["pages"]
                if isinstance(p, dict) and "content" in p
            ]
        }
    return {"content": None}