import asyncio

from typing import List, Dict, Any, Callable
from beegenerate.configs.models.chunker_config import ChunkerConfig
from beegenerate.loggings.loggers import lf
from beegenerate.utils.token_count import num_tokens_from_string
from beegenerate.configs import LiteLLMConfig
from beegenerate.const import BEEGEN_ROOT

from langfuse.decorators import observe, langfuse_context
from beechat.services.llm_service import LLMService
from auth.keycloak import generate_internal_jwt

from urllib.parse import urlencode
from openai import AsyncOpenAI

import sys
sys.stdout.reconfigure(encoding='utf-8')


class SummaryService:
    def __init__(self, capacity_tokens: int):
        """
        Initializes the SummaryService with a bot ID and token capacity.

        Args:
            bot_id (str): The ID of the bot associated with this service.
            capacity_tokens (int): The maximum number of tokens to consider for
                                   grouping document chunks.
        """
        self.capacity_tokens = capacity_tokens
        self.chunker_config = ChunkerConfig().default()

    @observe()
    async def chunk_document(self, s3_path: str):
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

        internal_jwt = generate_internal_jwt()
        if s3_path.endswith(".pdf"):
            params = {"type": "pdf_gpt", "s3_file_path": s3_path}
        else:
            params = {"type": "multimodal", "s3_file_path": s3_path}
        url_params = urlencode(params, doseq=True)
        if internal_jwt is None:
            raise PermissionError("JWT token failed")
        url = f"{self.chunker_config.chunker_base_url}/chunk?{url_params}"

        payload = 'payload={"metadata": {}}'
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Bearer {str(internal_jwt)}'
        }

        response = requests.request("POST", url, headers=headers, data=payload)
        if response.status_code != 200:
            print(response.json())
            raise ConnectionError(f"Error chunker. Got status {response.status_code}")
        return response.json().get('response', None)

    @observe()
    def group_llm_texts_by_token_capacity(
        self,
        chunks: List[Dict[str, Any]],
        capacity_tokens: int,
        num_tokens_from_string: Callable[[str], int],
        *,
        text_field: str = "llm_text",
        sep: str = "\n\n",
    ) -> List[str]:
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
            List[str]: A list of strings, where each string is the concatenated
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
        langfuse_context.client_instance.span(
            name="summary_ground_truth",
            output=full_text,
            parent_observation_id=langfuse_context.get_current_observation_id(),
            trace_id=langfuse_context.get_current_trace_id()
        ).end()
        return out

    @observe()
    async def summary_single_chunk(self, chunk_content: str):
        """
        Summarizes a single chunk of content using an LLM stream.

        Args:
            chunk_content (str): The content of the chunk to be summarized.

        Returns:
            str: The summarized content of the chunk.
        """
        final_response = ""
        litellm_config = LiteLLMConfig.from_yaml_file(
            BEEGEN_ROOT / "config/llms/litellm.yaml")

        client = AsyncOpenAI(
            base_url=litellm_config.base_url,
            api_key=litellm_config.api_key,
        )

        chat_completion = await client.chat.completions.create(
            model="gpt-4.1",
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": lf.get_prompt("BEEKTNB_SUMMARY_DOCUMENT").compile(**{"document": chunk_content})
                }
            ]
        )
        if chat_completion.choices is not None and len(chat_completion.choices) > 0:
            final_response = chat_completion.choices[0].message.content
        else:
            langfuse_context.update_current_observation(level='ERROR', output="Summary return None")
        return final_response

    @observe()
    async def summary_document(self, capacity_tokens: int = 8000, text_document: str = None, s3_path: str = None):
        """
        Summarizes a document from either a text string or an S3 path.

        This function takes a document, chunks it if necessary, groups the chunks
        by a specified token capacity, and then summarizes each group using an LLM.
        Finally, it combines the summaries into a single string.

        Args:
            capacity_tokens (int, optional): The maximum number of tokens for each
                                             group of document chunks. Defaults to 8000.
            text_document (str, optional): The document content as a string.
                                           Required if s3_path is None.
            s3_path (str, optional): The S3 path to the document.
                                     Required if text_document is None.

        Raises:
            ValueError: If both text_document and s3_path are None.

        Returns:
            str: The combined summary of the document.
        """
        if text_document is None and s3_path is None:
            raise ValueError("text_document or s3_path is required.")
        document_chunks = []
        if s3_path is not None:
            document_chunks = await self.chunk_document(s3_path=s3_path)
        else:
            if num_tokens_from_string(text_document) > 20000:
                raise ValueError("Document too long, current limit is 20000 token (40000 character)")
            document_chunks = [
                {
                    "llm_text": text_document,
                    "embedding_text": text_document
                }
            ]
        group_chunks = self.group_llm_texts_by_token_capacity(
            chunks=document_chunks,
            capacity_tokens=capacity_tokens,
            num_tokens_from_string=num_tokens_from_string
        )
        summary_chunk = await asyncio.gather(*[
            self.summary_single_chunk(doc_chunk) for doc_chunk in group_chunks
        ])
        return "\n".join(doc for doc in summary_chunk)


@observe(name="RunTestSummary")
async def run_eval(s3_path):
    summarizer = SummaryService(
        bot_id="a0639e4d-dba7-4218-a2d6-1a3e360ed5ab",
        capacity_tokens=8000
    )
    await summarizer.summary_document(s3_path=s3_path)


async def main():

    import pandas as pd

    df = pd.read_csv("D:/supacache/file_list.csv")
    summary_task = []
    for i in range(0, len(df)):
        print(df.iloc[i]['Key'])
        await run_eval(df.iloc[i]['Key'])


if __name__ == "__main__":
    asyncio.run(main())
