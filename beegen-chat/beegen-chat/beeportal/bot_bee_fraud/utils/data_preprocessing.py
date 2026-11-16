# import re

# # Pre-compile regex patterns for better performance
# REGEX_PATTERNS = [
#     (re.compile(r'mbvcb[.\s]\d+[.\s]\d+[.\s]([^.]+)(?:[.]\s*ct|\s+ct tu|\s+toi|$)', re.IGNORECASE), 1),
#     # (re.compile(r'^q\S+\s+\S+\s+\d+\s+(.*)$', re.IGNORECASE), 1),
#     (re.compile(r'^qy\d{9}\s+bitcakem\d{6}\s+1\s+(.+)$', re.IGNORECASE), 1),
#     (re.compile(r"^zalopay-chuyentien-\S+-(.+)", re.IGNORECASE), 1),
#     (re.compile(r"^ibft (.+)", re.IGNORECASE), 1),
#     (re.compile(r"\.\d+\.\d+\.(.+?)(?:\.ct|\.chuyen tien|ft\d+)", re.IGNORECASE), 1),
#     (re.compile(r"(.+?)\sft\d+", re.IGNORECASE), 1),
#     (re.compile(r"mb \d+ (.+?)(?:-|$)", re.IGNORECASE), 1),
#     (re.compile(r"^\d+(.*?)(?:oqch|qua momo-chuyen tien-oqch)", re.IGNORECASE), 1),
# ]

# CLEANUP_PATTERNS = [
#     (re.compile(r'\#\s?'), ''),
#     (re.compile(r'\s{2,}'), ' '),
#     (re.compile(r'^atmcash-\d+$', re.IGNORECASE), ''),
#     (re.compile(r"\s+(ma gd|\b(\d{6}(\s\d{2}){3}\s\d+\sma giao dich)\b|trace|ma giao dich).*", re.IGNORECASE), ""),
#     (re.compile(r"mbtsw\d{9}", re.IGNORECASE), ""),
#     (re.compile(r'\bft\d+\b', re.IGNORECASE), ''),
#     (re.compile(r'mb\s+\d+\s*', re.IGNORECASE), ''),
#     (re.compile(r'[^\w\s]', re.IGNORECASE), ''),
# ]


# def clean_transaction_detail(text):
#     """
#     Optimized version: Clean up transaction details by applying pre-compiled regex patterns.
#     """
#     if text is None:
#         return ""

#     text = str(text).lower()

#     # Apply initial cleanup
#     for pattern, replacement in CLEANUP_PATTERNS[:2]:  # Only hash and whitespace cleanup first
#         text = pattern.sub(replacement, text)

#     # Try extraction patterns first (most specific to least specific)
#     for pattern, group_index in REGEX_PATTERNS:
#         match = pattern.search(text)
#         if match:
#             text = match.group(group_index)
#             text = re.sub(r'[^\w\s]', " ", text).strip()
#             break  # Exit early on first match

#     # Apply remaining cleanup patterns
#     for pattern, replacement in CLEANUP_PATTERNS[2:]:
#         text = pattern.sub(replacement, text)

#     return text.strip()
