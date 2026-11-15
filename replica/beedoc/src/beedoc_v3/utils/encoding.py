import codecs
import re
from bs4 import UnicodeDammit


def detect_html_encoding(raw_bytes: bytes) -> str:
    sample = raw_bytes[:4096]
    if raw_bytes.startswith(b"\x00\x00\xfe\xff"):
        return "utf-32-be"
    if raw_bytes.startswith(b"\xff\xfe\x00\x00"):
        return "utf-32-le"
    if raw_bytes.startswith(b"\xfe\xff"):
        return "utf-16-be"
    if raw_bytes.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"

    charset_match = re.search(
        rb"charset\s*=\s*[\"']?\s*([a-z0-9._-]+)", sample, flags=re.IGNORECASE,
    )
    if charset_match:
        try:
            encoding = charset_match.group(1).decode("ascii")
            codecs.lookup(encoding)
            return encoding
        except (LookupError, UnicodeDecodeError):
            pass
    try:
        raw_bytes.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        detected = UnicodeDammit(raw_bytes, is_html=True).original_encoding
        if detected:
            try:
                codecs.lookup(detected)
                return detected
            except LookupError:
                pass
        return "cp1252"
