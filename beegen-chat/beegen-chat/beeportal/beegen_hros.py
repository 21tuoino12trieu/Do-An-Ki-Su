import re
from typing import (
    List,
    Dict
)

from openai import AsyncStream
from openai.types.chat import ChatCompletionChunk
from pydantic import BaseModel

from beegenerate.prompts.beegen_common import CHIT_CHAT_PROMPT
from beegenerate.prompts.beehros import \
    NON_CHIT_CHAT_PROMPT, \
    REFUSE_PROMPT, \
    VERIFY_DOCUMENT_PROMPT, \
    CATEGORY_CLASSIFICATION_PROMPT, \
    REWRITE_AND_CLASSIFY_PROMPT
from beegenerate.utils.common import transform_bot_id
from beeportal.beegen_bot_v2 import Bot, parse_model, VerifyResult
from langfuse.decorators import observe
from datetime import date, datetime
from beegenerate.loggings.loggers import lf


def get_prompt(prompt_name: str):
    try:
        formatted_prompt_name = f"BEEHROS:{prompt_name}"
        return lf.get_prompt(name=formatted_prompt_name).prompt
    except Exception as e:
        return globals()[prompt_name]


class InputQuery(BaseModel):
    query: str
    intent: str


class BotHROS(Bot):
    @observe()
    async def _verify_document(
            self,
            query: str,
            documents: List[Dict]
    ) -> VerifyResult:
        _prompt = get_prompt("VERIFY_DOCUMENT_PROMPT").format(
            query=query,
            documents=self._format_documents(
                documents=documents
            )
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt}
            ]
        )

        return parse_model(
            input_text=response_text,
            model_class=VerifyResult
        )

    @observe()
    async def _category_classify(
            self,
            query: str
    ) -> str:
        _prompt = get_prompt("CATEGORY_CLASSIFICATION_PROMPT").format(
            query=query
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt}
            ]
        )

        response_text = re.sub(r'[^0-9a-zA-ZÀ-ỹ\s]', '', response_text)

        return response_text

    @observe()
    async def _retrieval_and_rerank(
            self,
            input_query: InputQuery,
            role_ids: List[str] = ["L1"],
            topic: str = "default",
            valid_score: float = 0.5
    ) -> Dict:
        # 2. retrieve the relevan records by vector search
        retrieval_records = await self._retriever.run(
            query=input_query.query,
            bot_id=self.bot_config['id'],
            collection=f"bot_{transform_bot_id(self.bot_config['id'])}",
            allowed_roles=role_ids,
            top_k=self.bot_config['retrieval'].top_k,
            threshold=self.bot_config['retrieval'].threshold
        )

        # 3. rerank the retrieval results
        reranked_results = await self._reranker.run(
            query=input_query.query,
            texts=[r['content'] for r in retrieval_records],
            top_k=self.bot_config['reranking'].top_k,
            threshold=self.bot_config['reranking'].threshold,
        )

        # 4. construct the final documents
        final_docs = []
        valid_count = 0
        for r in reranked_results:
            record = retrieval_records[r['index']]
            record['score'] = r['score']
            if record['score'] > valid_score:
                valid_count += 1
            final_docs.append(record)

        # 5. return dict
        return {
            'docs': final_docs,
            'intent': 'chitchat' if valid_count == 0 else 'non_chitchat'
        }

    @observe()
    def _format_documents(
            self,
            documents: List[Dict]
    ) -> str:
        """Format a list of documents into a single string with separators.

        Args:
            documents: List of document dictionaries, each containing a 'content' field

        Returns:
            String containing all document contents separated by [SEP] tokens
        """
        today = date.today()
        formatted_docs = []
        for doc in documents:
            file_name = doc["content"].split("\n")[0]
            content = doc["content"]
            notice = ""
            if doc['valid_from'] is not None and doc['valid_to'] is None:
                if today < doc['valid_from'].date():
                    notice = f"**Lưu ý: Tài liệu này chỉ có hiệu lực từ ngày {doc['valid_from'].strftime('%d/%m/%Y')}**"
            elif doc['valid_from'] is None and doc['valid_to'] is not None:
                if today > doc['valid_to'].date():
                    notice = f"**Lưu ý: Tài liệu đã hết hiệu lực từ ngày {doc['valid_to'].strftime('%d/%m/%Y')}**"
            elif doc['valid_from'] is not None and doc['valid_to'] is not None:
                if today < doc['valid_from'].date() or today > doc['valid_to'].date():
                    notice = f"**Lưu ý: Tài liệu này chỉ có hiệu lực từ ngày {doc['valid_from'].strftime('%d/%m/%Y')} đến ngày {doc['valid_to'].strftime('%d/%m/%Y')}**"
            formatted_doc = {
                "Tên tài liệu": file_name,
                "Nội dung": content,
                "Chú thích": notice
            }

            if doc['valid_from'] is not None or doc['valid_to'] is not None:
                if doc['valid_from'] is not None and today < doc['valid_from'].date():
                    continue
                if doc['valid_to'] is not None and today > doc['valid_to'].date():
                    continue

            formatted_docs.append(str(formatted_doc))

        documents_text = "\n".join(formatted_docs)
        return documents_text

    @observe()
    async def _flow_non_chit_chat(
            self,
            query: str,
            docs: List[Dict]
    ) -> AsyncStream[ChatCompletionChunk]:  # type: ignore
        """Handle information-seeking conversation flow.

        Args:
            query: User's input query
            docs: List of relevant documents

        Returns:
            Stream of response chunks from LLM

        """

        verify = await self._verify_document(
            query=query,
            documents=docs
        )

        category = await self._category_classify(query)

        if verify.output == 'matched':
            current_date = datetime.now().strftime('%d/%m/%Y')

            system_prompt = get_prompt("NON_CHIT_CHAT_PROMPT").format(
                date=current_date,
                definition=self.bot_config['definition'],
                query=query,
                documents=self._format_documents(
                    documents=docs
                )
            )
        else:
            system_prompt = get_prompt("REFUSE_PROMPT").format(
                definition=self.bot_config['definition']
            )

        attached_docs = self._create_attached_docs(
            documents=docs
        )

        chunk: ChatCompletionChunk

        async for chunk in self._llm.run(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                docs=attached_docs
        ):
            chunk.category = category
            yield chunk

    @observe()
    async def _flow_chit_chat(
            self,
            query: str,
            docs: List[Dict]
    ) -> AsyncStream[ChatCompletionChunk]:  # type: ignore
        """Handle casual conversation flow.

        Args:
            query: User's input message
            docs: List of relevant documents for context

        Returns:
            Stream of response chunks from LLM

        Note:
            Uses casual conversation prompt template
        """
        # 1. create chitchat prompt
        system_prompt = get_prompt("CHIT_CHAT_PROMPT").format(
            definition=self.bot_config['definition']
        )

        # 2. create attached docs for output return (FE)
        attached_docs = self._create_attached_docs(
            documents=docs
        )

        # 3. create streaming response
        async for chunk in self._llm.run(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                docs=attached_docs
        ):
            chunk.category = 'default'
            yield chunk

    @observe()
    async def _generate_intent(
            self,
            messages: List[Dict],
    ) -> InputQuery:
        """Determine the intent of the user's latest message.

        Uses conversation history and LLM to:
        1. Rewrite the query for better understanding
        2. Classify the intent as chitchat or non-chitchat

        Args:
            messages: List of conversation messages, each with 'role' and 'content'

        Returns:
            InputQuery object containing rewritten query and classified intent

        Raises:
            ValueError: If query parsing fails
        """

        # 1. get the user latest message and chat history
        query = messages[-1]['content']
        _history = [
            f"Người dùng: {m['content']}"
            if m['role'] == 'user'
            else f"BOT: {m['content']}"
            for m in messages[-21:-1]
        ]
        # 2. Rewrite the conversation and classify the intent of user
        _prompt = get_prompt("REWRITE_AND_CLASSIFY_PROMPT").format(
            definition=self.bot_config['definition'],
            conversation=_history,
            query=query
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt}
            ]
        )

        return parse_model(
            input_text=response_text,
            model_class=InputQuery
        )


async def main():
    from beegenerate.storage import BotStore
    from beegenerate.configs import MongoConfig, MilvusConfig
    from beegenerate.storage import DocumentStore
    from beegenerate.vectordb import MilvusStorage

    bot_id = "1a0f5c26-3070-42dc-b251-f3f5da551d51"
    bot_store = BotStore(config=MongoConfig.default())
    bot_config = bot_store.fetch_bot_details(
        bot_id=bot_id
    )

    bot = BotHROS(
        bot_config=bot_config,
        vec_store=MilvusStorage(config=MilvusConfig.default()),
        doc_store=DocumentStore(config=MongoConfig.default()),
        bot_store=BotStore(config=MongoConfig.default())
    )

    async for chunk in bot.run(
            messages=[
                {"role": "user", "content": "cách thêm phiếu xuất kho cho quản lý đối tác"}
            ],
            role_ids=["Quản lý tài sản"],
            topic="default"
    ):
        if len(chunk.choices) > 0:
            if chunk.choices[0].delta.content is not None:
                # print(chunk.category)
                response_text = chunk.choices[0].delta.content
                print(response_text, end="")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
