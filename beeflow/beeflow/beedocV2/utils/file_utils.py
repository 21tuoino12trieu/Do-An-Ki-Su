# beedocV2/utils/file_utils.py
"""
File utilities for reading and validating document content.
Handles file paths, raw content, and URL fetching.
"""

import os
import requests
from pathlib import Path
from typing import Union, Optional, Tuple
from urllib.parse import urlparse
import mimetypes


class FileReadError(Exception):
    """Raised when file reading fails."""
    pass


class URLFetchError(Exception):
    """Raised when URL fetching fails."""
    pass


def read_file_content(file_path: Union[str, Path]) -> bytes:
    """
    Read file content as bytes.
    
    Args:
        file_path: Path to the file
        
    Returns:
        File content as bytes
        
    Raises:
        FileReadError: If file cannot be read
    """
    try:
        path = Path(file_path)
        if not path.exists():
            raise FileReadError(f"File does not exist: {file_path}")
        
        if not path.is_file():
            raise FileReadError(f"Path is not a file: {file_path}")
        
        with open(path, 'rb') as f:
            return f.read()
    
    except (OSError, IOError, PermissionError) as e:
        raise FileReadError(f"Failed to read file {file_path}: {str(e)}")


def fetch_url_content(url: str, timeout: int = 30) -> Tuple[bytes, str]:
    """
    Fetch content from URL.
    
    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        
    Returns:
        Tuple of (content_bytes, content_type)
        
    Raises:
        URLFetchError: If URL cannot be fetched
    """
    try:
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise URLFetchError(f"Invalid URL: {url}")
        
        # Fetch content
        headers = {
            'User-Agent': 'BeedocV2/1.0 (Document Processing Pipeline)'
        }
        
        response = requests.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()
        
        # Get content type
        content_type = response.headers.get('content-type', 'application/octet-stream')
        
        return response.content, content_type
    
    except requests.RequestException as e:
        raise URLFetchError(f"Failed to fetch URL {url}: {str(e)}")


def validate_file_path(file_path: Union[str, Path]) -> bool:
    """
    Validate if file path exists and is readable.
    
    Args:
        file_path: Path to validate
        
    Returns:
        True if file is valid and readable
    """
    try:
        path = Path(file_path)
        return path.exists() and path.is_file() and os.access(path, os.R_OK)
    except (OSError, TypeError):
        return False


def get_file_info(file_path: Union[str, Path]) -> dict:
    """
    Get file information including size, modification time, and MIME type.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Dictionary with file information
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return {}
        
        stat_info = path.stat()
        mime_type, _ = mimetypes.guess_type(str(path))
        
        return {
            'size_bytes': stat_info.st_size,
            'modified_timestamp': stat_info.st_mtime,
            'mime_type': mime_type,
            'extension': path.suffix.lower(),
            'filename': path.name,
            'stem': path.stem
        }
    
    except (OSError, IOError):
        return {}


def ensure_bytes(content: Union[str, bytes], encoding: str = 'utf-8') -> bytes:
    """
    Ensure content is in bytes format.
    
    Args:
        content: Content to convert
        encoding: Encoding to use if content is string
        
    Returns:
        Content as bytes
    """
    if isinstance(content, str):
        return content.encode(encoding)
    return content


def detect_encoding(content: bytes) -> str:
    """
    Detect text encoding of content.
    
    Args:
        content: Content bytes to analyze
        
    Returns:
        Detected encoding (defaults to 'utf-8')
    """
    try:
        # Try UTF-8 first
        content.decode('utf-8')
        return 'utf-8'
    except UnicodeDecodeError:
        pass
    
    # Try common encodings
    encodings = ['latin1', 'cp1252', 'iso-8859-1']
    for encoding in encodings:
        try:
            content.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    
    # Fallback to utf-8 with error handling
    return 'utf-8'


def safe_decode(content: bytes, encoding: Optional[str] = None) -> str:
    """
    Safely decode bytes to string with fallback handling.
    
    Args:
        content: Content bytes to decode
        encoding: Specific encoding to use (auto-detect if None)
        
    Returns:
        Decoded string content
    """
    if encoding is None:
        encoding = detect_encoding(content)
    
    try:
        return content.decode(encoding)
    except UnicodeDecodeError:
        # Fallback with error replacement
        return content.decode(encoding, errors='replace')


def is_text_file(file_path: Union[str, Path]) -> bool:
    """
    Check if file appears to be a text file based on content sampling.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if file appears to be text
    """
    try:
        with open(file_path, 'rb') as f:
            # Read first 1KB
            sample = f.read(1024)
            
        if not sample:
            return True  # Empty file
        
        # Check for null bytes (common in binary files)
        if b'\x00' in sample:
            return False
        
        # Try to decode as text
        try:
            sample.decode('utf-8')
            return True
        except UnicodeDecodeError:
            # Try with error replacement
            try:
                sample.decode('utf-8', errors='replace')
                # If most characters are printable, consider it text
                printable_chars = sum(1 for c in sample if 32 <= c <= 126 or c in (9, 10, 13))
                return printable_chars / len(sample) > 0.7
            except:
                return False
                
    except (OSError, IOError):
        return False