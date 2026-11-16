import os
import tiktoken
import asyncio

from typing import List, Dict, Callable, Any
from urllib.parse import urlencode
from beegenerate.configs.models.chunker_config import ChunkerConfig


tiktoken_cache_dir = os.path.join(os.getcwd(), "beegenerate/utils")
os.environ["TIKTOKEN_CACHE_DIR"] = tiktoken_cache_dir

# validate
assert os.path.exists(os.path.join(tiktoken_cache_dir, "REPLACE_WITH_LOCAL_SECRET"))


enc = tiktoken.get_encoding("o200k_base")
chunker_config = ChunkerConfig().default()

def num_tokens_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    num_tokens = len(enc.encode(string))
    return num_tokens

async def chunk_document(s3_path: str, keycloak_token: str | None = None):
    """
    Chunks a document located at a given S3 path using an external chunker service.

    Args:
        s3_path (str): The S3 path to the document to be chunked.

    Raises:
        PermissionError: If the JWT token generation fails.
        ConnectionError: If there's an error connecting to or receiving a
                            non-200 response from the chunker service.

    Returns:
        dict: The JSON response from the chunker service, typically containing
                the chunked document. Returns None if 'response' key is missing.
    """
    import requests 
    if s3_path.endswith(".pdf"):
        params = {"type": "pdf_gpt", "s3_file_path": s3_path}
    else:
        params = {"type": "multimodal", "s3_file_path": s3_path}
    url_params = urlencode(params, doseq=True)
    if keycloak_token is None:
        raise PermissionError("JWT token failed")
    url = f"{chunker_config.chunker_base_url}/chunk?{url_params}"

    payload = 'payload={"metadata": {}}'
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Bearer {str(keycloak_token)}'
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    if response.status_code != 200:
        print(response.json())
        raise ConnectionError(f"Error chunker. Got status {response.status_code}")
    return response.json().get('response', None)


def group_llm_texts_by_token_capacity(
    chunks: List[Dict[str, Any]],
    capacity_tokens: int,
    num_tokens_from_string: Callable[[str], int],
    *,
    text_field: str = "llm_text",
    sep: str = "\n\n",
) -> dict:
    """
    Groups consecutive chunks by token count such that the total tokens in each group
    do not exceed `capacity_tokens`.

    Args:
        chunks (List[Dict[str, Any]]): A list of document chunks, where each chunk
                                        is a dictionary.
        capacity_tokens (int): The maximum token capacity for each grouped text.
        num_tokens_from_string (Callable[[str], int]): A function to calculate
                                                        the number of tokens in a string.
        text_field (str, optional): The key in the chunk dictionary that holds the
                                    text content. Defaults to "llm_text".
        sep (str, optional): The separator string used to join texts within a group.
                                Defaults to "\\n\\n".

    Raises:
        ValueError: If `capacity_tokens` is not positive, or if a single chunk's
                    token count exceeds `capacity_tokens`.
        KeyError: If a chunk does not contain the specified `text_field`.

    Returns:
        dict: A dict with 'document' key, where value is the concatenated
                    'llm_text' of a consecutive group of chunks.
    """
    if capacity_tokens <= 0:
        raise ValueError("capacity_tokens must be positive.")
    if not chunks:
        return []

    texts = []
    tokens = []
    for i, ch in enumerate(chunks):
        if text_field not in ch:
            raise KeyError(f"Chunk {i} does not have field '{text_field}'")
        s = ch[text_field]
        t = num_tokens_from_string(s)
        if t >= capacity_tokens:
            Warning(
                f"Chunk {i} has {t} tokens >= capacity {capacity_tokens}. "
                "This chunk needs to be split or capacity increased."
            )
        texts.append(s)
        tokens.append(t)

    out: List[str] = []
    start = 0
    curr_sum = 0

    for i, t in enumerate(tokens):
        if curr_sum + t >= capacity_tokens:
            out.append(sep.join(texts[start:i]))
            start = i
            curr_sum = t
        else:
            curr_sum += t

    # Last group
    out.append(sep.join(texts[start:]))

    full_text = "\n".join([x for x in out])
    return {"document": full_text}


def prepare_paths_batch_data(paths: list, capacity_tokens: int = 8000, keycloak_token: str | None = None):
    """"""
    list_group_chunks = []

    for path in paths:
        document_chunks = asyncio.run(chunk_document(s3_path=path, keycloak_token=keycloak_token))

        group_chunks = group_llm_texts_by_token_capacity(
            chunks=document_chunks,
            capacity_tokens=capacity_tokens,
            num_tokens_from_string=num_tokens_from_string
        )

        list_group_chunks.append(group_chunks)

    return {"batch_data": list_group_chunks}


