import base64
import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

def converter(document_path: str, document_bytes: bytes) -> Dict[str, Any]:
    """
    Format and wrap document information into a standardized dictionary structure.

    Args:
        document_path (str): Full path to the document (e.g., an S3 URI).
        document_bytes (bytes): The raw content of the document.

    Returns:
        path (str): The document's path as a string.
        data (bytes): The raw document content as bytes.
    """
    return {
            "path": document_path,
            "data": document_bytes
    }