from beegenerate.prompts.beegen_common import (
    CHIT_CHAT_PROMPT,
    REFUSE_PROMPT
)

from pydantic import BaseModel
import yaml

from beegenerate.retrievers.vector_retriever import VectorRetriever
from beegenerate.vectordb import MilvusStorage
from beegenerate.storage.mongo.mongodb_v2 import MongoExecutor
from beegenerate.reranks import RerankingFactory
from beegenerate.storage import (
    DocumentStore,
    BotStore
)

from beegenerate.llms.llm_executor import LLMExecutor

from openai import AsyncStream
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from typing import (
    List,
    Dict,
    TypeVar,
    Type
)

from datetime import datetime
from beegenerate.utils.common import transform_bot_id

from beegenerate.loggings import LOGGER
import asyncio
from beegenerate.configs import MongoConfig
from beegenerate.prompts.beektnb import REWRITE_AND_CLASSIFY_PROMPT
from beektnb.prompts.content_filter import REFUSAL_MESSAGES
from beektnb.constant import list_category
import time
from beektnb.intents.cls_query import XMLData
from langfuse.decorators import observe, langfuse_context
from beektnb.intents.classify_query import IntentClassify, RewriteQuery, ClassifyTopic, VerifyTopic, VerifyDocument, ChoiceDocument
from beektnb.prompts.classify import CLS_INTENT, REWRITE_BASE, CLS_TOPIC, VERIFY_TOPIC_QUERY, \
    VERIFY_DOCUMENT_PROMPT, NON_CHIT_CHAT_ILLEGAL, ASK_HUMAN_QUESTION_TOPIC, ASK_HUMAN_VERIFY_TOPIC
from beektnb.services.summary_service import SummaryService
from beegenerate.loggings.loggers import lf

import json
from types import SimpleNamespace


# Create a generic type that must be a subclass of BaseModel
T = TypeVar('T', bound=BaseModel)

# Khai báo semaphore dùng chung
semaphore = asyncio.Semaphore(5)


class InputQuery(BaseModel):
    query: str
    intent: str


class QueryTopic(BaseModel):
    topic: int


class VerifyResult(BaseModel):
    output: str


def parse_model(
        input_text: str,
        model_class: Type[T]
) -> T:
    """
    Parse input text into a specified Pydantic model.

    Args:
        input_text: Input string in a format similar to YAML
        model_class: The Pydantic model class to parse into

    Returns:
        An instance of the specified model class

    Raises:
        ValueError: If parsing or validation fails
    """
    # Remove ```yaml``` markers if present
    cleaned_text = input_text
    if "```yaml" in input_text:
        # Split by ```yaml and ``` and take the content in between
        parts = input_text.split("```yaml")
        if len(parts) > 1:
            cleaned_text = parts[1].split("```")[0].strip()

    # Parse YAML
    try:
        data = yaml.safe_load(cleaned_text)
        if not data:
            raise ValueError("Empty or invalid YAML content")

        # Parse Type
        if "query" in data:
            data['query'] = str(data['query'])

        # Validate and create specified Pydantic model
        return model_class(**data)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML format: {e}")
    except Exception as e:
        raise ValueError(f"Validation error: {e}")


class BotKTNB:
    """A chatbot class that handles conversations using LLM, document retrieval, and reranking.

    This class implements a complete conversation flow including:
    - Intent classification
    - Document retrieval and reranking
    - Handling both casual (chitchat) and information-seeking conversations
    - Role-based access control for documents

    Attributes:
        bot_id (str): Unique identifier for the bot instance
        bot_store (MongoStorage): Storage for bot configurations and metadata
        bot_config (Dict[str, Any]): Bot-specific configuration settings
        _llm (LLMExecutor): Language model execution handler
        _retriever (VectorRetriever): Document retrieval component
        _reranker (RerankingFactory): Document reranking component
    """

    def __init__(
            self,
            bot_config: Dict,
            vec_store: MilvusStorage,
            doc_store: DocumentStore,
            bot_store: BotStore
    ):
        """Initialize the Bot instance with necessary components.

        Args:
            bot_config (Dict): Configuration dictionary containing LLM, embedding, and reranking settings for the bot
            vec_store (MilvusStorage): Vector storage instance for managing embeddings and similarity search
            doc_store (DocumentStore): Document storage instance for retrieving and managing content
            bot_store (BotStore): Bot configuration storage used for fallback LLM configs when primary configuration is inactive
        """
        self.bot_config = bot_config

        self._llm = LLMExecutor(
            primary_config=self.bot_config['llm'],
            config_store=bot_store
        )

        self._retriever = VectorRetriever(
            config=bot_config['retrieval'],
            vec_store=vec_store,
            doc_store=doc_store
        )

        self._mongo = MongoExecutor(
            config=MongoConfig.default()
        )

        self._reranker = RerankingFactory.create(config=self.bot_config['reranking'])

        self.character_ask_human = "[?]"

        self.summarizer = SummaryService(
            capacity_tokens=8000
        )


    @observe()
    def _format_documents(
            self,
            documents: List[Dict],
            truncate: bool = True
    ) -> str:
        """Format a list of documents into a single string with separators.

        Args:
            documents: List of document dictionaries, each containing a 'content' field

        Returns:
            String containing all document contents separated by [SEP] tokens
        """

        # if truncate:
        #     documents_text = "\n[SEP]\n".join([d['content'] for d in documents])[:50000]
        # else:
        #     documents_text = "\n[SEP]\n".join([d['content'] for d in documents])

        documents_text = ""
        for i, d in enumerate(documents):
            documents_text += f"\nDocument {i + 1}: {d}\n"

        if truncate:
            documents_text = documents_text[:80000]

        return documents_text

    @observe()
    def _create_attached_docs(
            self,
            documents: List[Dict]
    ) -> List[Dict]:
        """Create metadata for documents to be attached to LLM requests.

        Args:
            documents: List of document dictionaries containing 'id' and optional 'doc' fields

        Returns:
            List of dictionaries containing document metadata (id and source)
        """
        attached_docs = []
        for r in documents:
            chunk_info = {
                "id": r['id'],
            }
            if 'doc' in r:
                chunk_info['source'] = r['doc']

            attached_docs.append(chunk_info)
        return attached_docs

    @observe()
    async def _stream_llm_response(
            self,
            messages: List[Dict]
    ) -> str:
        """Stream response from LLM and concatenate chunks into a single string.

        Args:
            messages: List of message dictionaries with 'role' and 'content' fields

        Returns:
            Concatenated response string from the LLM

        Raises:
            RuntimeError: If LLM streaming fails
        """
        try:
            response_text = ""
            async for chunk in self._llm.run(messages=messages):
                if len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                    response_text += str(chunk.choices[0].delta.content)
            return response_text
        except Exception as e:
            LOGGER.error(f"Error streaming LLM response: {e}")
            raise RuntimeError(f"Failed to get LLM response: {str(e)}")
        
    @observe
    async def _check_matcher(
        self,
        query: str,
        list_chunk: List[str],
        document_complie: List[Dict]
    ) -> List[Dict]:
        
        # list_prompt = [CHOICE_DOCUMENT.format(query=query, chunk=chunk) for chunk in list_chunk]
        
        list_prompt = [lf.get_prompt("BEEKTNB_CHOICE_DOCUMENT").compile(**{"query": query, "chunk": chunk}) for chunk in list_chunk]

        # with open("beektnb/list_chunk.txt", 'w', encoding='utf-8') as f:
        #     for ch in list_chunk:
        #         f.write("-------Document---------")
        #         f.write(ch)
        #         f.write("\n")

        async def run_with_semaphore(_prompt: str):
            async with semaphore:
                return await self._stream_llm_response(
                    messages=[{"role": "user", "content": _prompt}]
                )

        output = await asyncio.gather(*[
            run_with_semaphore(
                _prompt = _prompt
            ) for _prompt in list_prompt]
        )

        output_list_chunk = []
        for out, chunk in zip(output, document_complie):
            try:
                parser_data = ChoiceDocument.from_xml_string(out)

            except Exception as e:
                LOGGER.error(f"Classify query error: {e}")

                parser_data = ChoiceDocument.from_xml_string(
                    """
                        <result>matched</result>
                    """
                )

            if parser_data.result == 'matched':
                output_list_chunk.append(chunk)

        return output_list_chunk

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
            for m in messages[-11:-1]
        ]
        # _history = []
        # 2. Rewrite the conversation and classify the intent of user
        _prompt = REWRITE_AND_CLASSIFY_PROMPT.format(
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

    @observe()
    async def _retrieval(
            self,
            query: str,
            role_ids: List[str] = [],
            topic: str | None = None,
            partition_names: List[str] = []
    ) -> List[Dict]:
        if topic:
            retrieval_records = await self._retriever.run(
                query=query,
                bot_id=self.bot_config['id'],
                collection=f"bot_{transform_bot_id(self.bot_config['id'])}",
                allowed_roles=role_ids,
                top_k=3 if "QA" in partition_names else 30,
                # top_k=16,
                threshold=0.9 if "QA" in partition_names else 0.4,
                partition_names=partition_names,
                expr = f"topic == '{topic}'"
            )

        else:
            # 2. retrieve the relevan records by vector search
            retrieval_records = await self._retriever.run(
                query=query,
                bot_id=self.bot_config['id'],
                collection=f"bot_{transform_bot_id(self.bot_config['id'])}",
                allowed_roles=role_ids,
                top_k=3 if "QA" in partition_names else 30,
                # top_k=16,
                threshold=0.9 if "QA" in partition_names else 0.5,
                partition_names=partition_names
                # expr = " || ".join([f'role == "{r}"' for r in roles])
            )

        return retrieval_records

    @observe()
    async def _rerank(
            self,
            query: str,
            retrieval_records: List[Dict],
            top_k: int = 4
    ) -> Dict:

        # Check retrieval records
        if len(retrieval_records) == 0:
            return []

        reranked_results = await self._reranker.run(
            query=query,
            texts=[r['content'] for r in retrieval_records],
            top_k=top_k,
            threshold=self \
                .bot_config['reranking'] \
                .threshold,
        )

        return reranked_results

    @observe()
    def _construct_final_document(
            self,
            rerank_results: List[Dict],
            valid_score: float = 0.5,
    ) -> Dict:
        # 1. construct the final documents
        final_docs = []
        valid_count = 0
        for r in rerank_results:
            record = r['docs']
            record['score'] = r['score']
            if record['score'] > valid_score:
                valid_count += 1
            final_docs.append(record)

        # 2. return dict
        return {
            'docs': final_docs,
            'intent': 'chit_chat' if valid_count == 0 else 'non_chit_chat'
        }
    
    @observe()
    async def _fetch_bot_category(
        self,
        bot_id: str
    ):
        mongo_config = self.bot_config["mongo"]
        categories = await self._mongo._find(
            params={
                "collection_name": mongo_config["category_collection_name"],
                "query": {"bot_id": bot_id}
            }
        )

        return categories
    
    @observe()
    def _process_category_data(
        self,
        category_data: list
    ) -> tuple[str, dict]:
        processed_data = ""
        category_mapping = {}

        fallback_case = "**Không xác định**: Use this topic when the query doesn't clearly fit into one of these topic above or you're uncertain whether to classify it under one of them."

        for i, data in enumerate(category_data):
            item_data = f"Index {i + 1}: **{data["name"]}** - {data["description"]}\n\n"
            processed_data += item_data
            category_mapping[i+1] = data["name"]

        processed_data += f"Index {len(category_data) + 1}: {fallback_case}"

        return processed_data, category_mapping
    
    @observe()
    async def _extract_query_topic(
        self,
        rewritten_query: str,
        category_data: dict
    ) -> str:
        
        _prompt = lf.get_prompt("BEEKTNB:EXTRACT_QUERY_TOPIC_PROMPT").compile(
            **{
                "query": rewritten_query, 
                "category_data": category_data
            }
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt}
            ]
        )

        return parse_model(
            input_text=response_text,
            model_class=QueryTopic
        )

    @observe()
    async def _retrieval_rerank_cross(
            self,
            query: str,
            role_ids: List[str] = [],
            topic: str | None = None,
            valid_score: float = 0.5
    ) -> Dict:
        # Retrieval documents & QA:
        retrieval_results = await asyncio.gather(*[
            self._retrieval(
                query=query,
                role_ids=role_ids,
                topic=topic,
                partition_names=['document']
            ),
            self._retrieval(
                query=query,
                role_ids=role_ids,
                partition_names=['QA']
            )
        ])
        retrieval_document, retrieval_qa = retrieval_results[0], retrieval_results[1]

        # with open("beektnb/retrieval_doc.txt", 'w', encoding='utf-8') as f:
        #     for i, doc in enumerate(retrieval_document):
        #         if i == 0:
        #             print(doc)
        #         f.write(f"Document {i}: \n")
        #         f.write(doc['content'])
        #         f.write(str(doc["score"]))
        #         f.write("\n\n\n")

        #     for i, doc in enumerate(retrieval_qa):
        #         if i == 0:
        #             print(doc)
        #         f.write(f"Document {i}: \n")
        #         f.write(doc['content'])
        #         f.write(str(doc["score"]))
        #         f.write("\n\n\n")

        print("Len retrieval document: ", len(retrieval_document))
        print("Len retrieval qa: ", len(retrieval_qa))

        # Rerank document + qa
        rerank_results = await asyncio.gather(*[
            self._rerank(
                query=query,
                retrieval_records=retrieval_document,
                top_k=len(retrieval_document)
            ),
            self._rerank(
                query=query,
                retrieval_records=retrieval_qa,
                top_k=2
            )
        ])
        rerank_content, rerank_qa = rerank_results[0], rerank_results[1]

        # # print("Rerank content: ", rerank_content)

        # top_k = self.bot_config['reranking'].top_k

        # # Get top_k / 2 document from retrieval
        # index_retrieval = [i for i in range(top_k//2)]
        # rerank_retrieval = []
        # for r in rerank_content:
        #     if r['index'] in index_retrieval:
        #         rerank_retrieval.append(r)

        # # Get top_k document from rerank
        # rerank_top_k = rerank_content[:top_k]

        # # Combine rerank
        # rerank_combine = rerank_retrieval
        # index_combine = [r['index'] for r in rerank_retrieval]

        # for r in rerank_top_k:
        #     if r['index'] not in index_combine:
        #         rerank_combine.append(r)
        #         index_combine.append(r['index'])

        #     if len(index_combine) == top_k:
        #         break

        rerank_combine = rerank_content

        # Get document use index
        rerank_document_final = [{"docs": retrieval_document[r["index"]], "score": r["score"]} for r in rerank_combine]
        rerank_qa_final = [{"docs": retrieval_qa[r["index"]], "score": r["score"]} for r in rerank_qa]

        # Combine document and qa
        rerank_document_qa_combine = rerank_document_final + rerank_qa_final

        # Sort decrease result rerank by score and concat with top 1:
        rerank_all_sort = sorted(rerank_document_qa_combine, key=lambda x: x['score'], reverse=True)

        rerank_all_final = self._construct_final_document(
            rerank_results=rerank_all_sort,
            valid_score=valid_score
        )

        print("Rerank content: ", rerank_content)
        print("Rerank combine: ", rerank_combine)

        # print("Rerank final: \n")
        # for data in rerank_all_final['docs']:
        #     print("id: ", data['id'])
        #     print("Content: ", data['content'][:3000])

        #     print("*" * 30)

        # print("Len rerank final: ", len(rerank_all_final['docs']))

        # with open("test_rerank_doc.txt", 'w', encoding='utf-8')  as f:
        #     for data in rerank_all_final['docs']:
        #         f.write("------------\n")
        #         f.write(data['content'])
        #         f.write("\n\n")
        return rerank_all_final

    @observe()
    async def _retrieval_rerank_llm(
            self,
            query: str,
            role_ids: List[str] = [],
            topic: str = "default",
            valid_score: float = 0.3
    ) -> Dict:
        # Retrieval documents & QA:
        retrieval_results = await asyncio.gather(*[
            self._retrieval(
                query=query,
                role_ids=role_ids,
                topic=topic,
                partition_names=['document']
            ),
            self._retrieval(
                query=query,
                role_ids=role_ids,
                topic=topic,
                partition_names=['QA']
            )
        ])
        retrieval_document, retrieval_qa = retrieval_results[0], retrieval_results[1]

        with open("beektnb/retrieval_text.txt", 'w', encoding='utf-8') as f: 
            for r in retrieval_document:
                f.write(f"Document: {r['content']}")
                f.write("\n\n")

        # Rerank document + qa
        rerank_results = await asyncio.gather(*[
            self._rerank(
                query=query,
                retrieval_records=retrieval_document,
                top_k=len(retrieval_document)
            ),
            self._rerank(
                query=query,
                retrieval_records=retrieval_qa,
                top_k=2
            )
        ])
        rerank_content, rerank_qa = rerank_results[0], rerank_results[1]

        rerank_content_tmp = [{"docs": retrieval_document[r["index"]], "score": r["score"]} for r in rerank_content]
        rerank_qa_tmp = [{"docs": retrieval_qa[r["index"]], "score": r["score"]} for r in rerank_qa]

        # Complie documents
        document_compile = rerank_content_tmp + rerank_qa_tmp

        document_compile_content = [document_compile[i]['docs']['content'] for i in range(len(document_compile))]

        output_chunk = await self._check_matcher(query=query, list_chunk=document_compile_content, document_complie=document_compile)

        # rerank_all_final = [{"docs": r, "score": r["score"]} for r in output_chunk]

        rerank_all_final = self._construct_final_document(
            rerank_results=output_chunk,
            valid_score=valid_score
        )

        # print("Rerank content: ", rerank_content)
        # print("Rerank combine: ", rerank_combine)


        print("Rerank final: \n")
        for data in rerank_all_final['docs']:
            print("id: ", data['id'])
            print("Content: ", data['content'][:2000])

            print("*" * 30)

        return rerank_all_final

    @observe()
    async def _retrieval_rerank_document(
            self,
            query: str,
            role_ids: List[str] = [],
            topic: str = "default",
            valid_score: float = 0.5
    ) -> Dict:
        # Retrieval documents & QA:
        retrieval_document = await self._retrieval(
            query=query,
            role_ids=role_ids,
            topic=topic,
            partition_names=['document', 'QA']
        )

        # retrieval_document, retrieval_qa = retrieval_results[0], retrieval_results[1]

        # with open("beektnb/test/retrieval_doc.txt", 'w', encoding='utf-8') as f:
        #     for i, doc in enumerate(retrieval_document):
        #         f.write(f"Document {i}: \n")
        #         f.write(doc['content'])
        #         f.write("\n\n\n")

        print("Len retrieval document: ", len(retrieval_document))
        # print("Len retrieval qa: ", len(retrieval_qa))

        # Rerank document + qa
        rerank_content = await self._rerank(
                query=query,
                retrieval_records=retrieval_document,
                top_k=self.bot_config['reranking'].top_k
            )
        
        # rerank_content, rerank_qa = rerank_results[0], rerank_results[1]

        print("Rerank content: ", rerank_content)

        top_k = self.bot_config['reranking'].top_k

        # Get top_k / 2 document from retrieval
        index_retrieval = [i for i in range(top_k//2)]
        rerank_retrieval = []
        for r in rerank_content:
            if r['index'] in index_retrieval:
                rerank_retrieval.append(r)

        # Get top_k document from rerank
        rerank_top_k = rerank_content[:top_k]

        # Combine rerank
        rerank_combine = rerank_retrieval
        index_combine = [r['index'] for r in rerank_retrieval]

        for r in rerank_top_k:
            if r['index'] not in index_combine:
                rerank_combine.append(r)
                index_combine.append(r['index'])

            if len(index_combine) == top_k:
                break

        # rerank_combine = rerank_top_k

        # Get document use index
        rerank_document_final = [{"docs": retrieval_document[r["index"]], "score": r["score"]} for r in rerank_combine]
        # rerank_qa_final = [{"docs": retrieval_qa[r["index"]], "score": r["score"]} for r in rerank_qa]

        # Combine document and qa
        # rerank_document_qa_combine = rerank_document_final + rerank_qa_final
        rerank_document_qa_combine = rerank_document_final

        # Sort decrease result rerank by score and concat with top 1:
        rerank_all_sort = sorted(rerank_document_qa_combine, key=lambda x: x['score'], reverse=True)

        rerank_all_final = self._construct_final_document(
            rerank_results=rerank_all_sort,
            valid_score=valid_score
        )

        print("Rerank content: ", rerank_content)
        print("Rerank combine: ", rerank_combine)

        print("Rerank final: \n")
        for data in rerank_all_final['docs']:
            print("id: ", data['id'])
            print("Content: ", data['content'][:3000])

            print("*" * 30)

        print("Len rerank final: ", len(rerank_all_final['docs']))

        # with open("test_rerank_doc.txt", 'w', encoding='utf-8')  as f:
        #     for data in rerank_all_final['docs']:
        #         f.write("------------\n")
        #         f.write(data['content'])
        #         f.write("\n\n")
        return rerank_all_final

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
        system_prompt = CHIT_CHAT_PROMPT.format(
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
            yield chunk

        return

    @observe()
    async def _verify_document(
            self,
            query: str,
            documents: List[Dict]
    ) -> VerifyResult:
        """Verify if retrieved documents match the user's query.

        Args:
            query: User's input query
            documents: List of retrieved documents to verify

        Returns:
            VerifyResult object indicating if documents match query
        """
        _prompt = VERIFY_DOCUMENT_PROMPT.format(
            query=query,
            documents=self._format_documents(
                documents=documents,
            ),
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt}
            ]
        )

        try:
            parser_data = VerifyDocument.from_xml_string(response_text)

            return parser_data

        except Exception as e:
            LOGGER.error(f"Classify query error: {e}")

            return VerifyDocument.from_xml_string(
                """
                    <verify_document>matched</verify_document>
                """
            )

    @observe()
    async def _cls_type_query(
            self,
            messages: List[Dict],
    ) -> str:
        """Classify kind user's question
        """
        query = messages[-1]['content']

        _prompt = CLS_INTENT.format(
            query=query
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt}
            ]
        )

        try:
            parser_data = XMLData.from_xml_string(response_text)

            return parser_data.label

        except Exception as e:
            LOGGER.error(f"Classify query error: {e}")

            return "none"

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

        Note:
            Verifies document relevance before generating response
        """
        # 1. verify the relevant of documents
        # verify = await self._verify_document(
        #     query=query,
        #     documents=docs
        # )

        # 2. decide the flow matched/unmatched
        if docs:
            current_date = datetime.now().strftime('%Y-%m-%d')

            system_prompt = lf.get_prompt("BEEKTNB_NON_CHIT_CHAT_PROMPT").compile(**{"date": current_date, 
                                                                             "definition": self.bot_config['definition'], 
                                                                             "query": query, 
                                                                             "documents": self._format_documents(
                                                                                documents=docs,
                                                                            ),})
        else:
            system_prompt = REFUSE_PROMPT.format(
                definition=self.bot_config['definition']
            )

        # 3. create attached docs to return in bot results (for FE)
        attached_docs = self._create_attached_docs(
            documents=docs
        )

        # 4. create streaming response
        async for chunk in self._llm.run(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                docs=attached_docs
        ):
            yield chunk

        return

    @observe()
    async def _flow_special_case(
            self,
            task: str,
            query: str
    ) -> AsyncStream[ChatCompletionChunk]:  # type: ignore
        """ Handle special case
        """

        system_prompt = NON_CHIT_CHAT_ILLEGAL.format(
            definition=self.bot_config['definition'],
            task=task
        )

        # 4. create streaming response
        async for chunk in self._llm.run(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                docs=[]
        ):
            yield chunk

        return

    @observe
    async def _flow_ask_human(
            self,
            query: str,
            topic_ktnb: str = None
    ) -> AsyncStream[ChatCompletionChunk]: # type: ignore
        """
            Handle case ask human repeate
        """
        if topic_ktnb is not None:
            system_prompt = ASK_HUMAN_VERIFY_TOPIC.format(topic=topic_ktnb)
        else:
            system_prompt = ASK_HUMAN_QUESTION_TOPIC

        flag = True
        async for chunk in self._llm.run(
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': query}
                ],
                docs=[]
        ):
            if flag:
                flag=False
                if chunk.choices[0].delta.content:
                    chunk.choices[0].delta.content = f"{self.character_ask_human} {chunk.choices[0].delta.content}"
                else:
                    chunk.choices[0].delta.content = f"{self.character_ask_human} "
            
                yield chunk
                
            else:
                yield chunk

        return

    @observe()
    async def _flow_classify_intent(
            self,
            messages: List[Dict]
    ) -> 'IntentClassify':
        """Handle case classify
        """
        query = messages[-1]['content']

        _prompt = CLS_INTENT.format(
            query=query
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt}
            ]
        )
        print("Response text: ", response_text)
        try:
            parser_data = IntentClassify.from_xml_string(response_text)

            return parser_data

        except Exception as e:
            LOGGER.error(f"Classify query error: {e}")

            return IntentClassify.from_xml_string(
                """
                    <task1>non_chit_chat</task1>
                    <task2>none</task2>
                    <task3>simple</task3>
                """
            )

    @observe()
    async def _flow_rewrite_simple(
            self,
            messages: List[Dict],
    ) -> 'RewriteQuery':
        """Rewrite query simple
        """
        query = messages[-1]['content']

        _prompt_simple = REWRITE_BASE.format(
            # conversation=_history,
            query=query,
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt_simple}
            ]
        )

        try:
            parser_data = RewriteQuery.from_xml_string(response_text)

            return parser_data

        except Exception as e:
            LOGGER.error(f"Flow rewrite simple error: {e}")

            return RewriteQuery.from_xml_string(
                f"<rewrite>{query}</rewrite>"
            )
        
    @observe()
    async def _flow_rewrite_base(
        self,
        messages: List[Dict],
    ) -> 'RewriteQuery':
        """Rewrite query base
        """
        query = messages[-1]['content']

        _history = [
            f"User: {m['content']}"
            if m['role'] == 'user'
            else f"BOT: {m['content']}"
            for m in messages[-11:-1]
        ]

        _prompt_simple = lf.get_prompt("BEEKTNB_REWRITE").compile(**{"conversation": _history, "query": query})

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt_simple}
            ]
        )

        try:
            parser_data = RewriteQuery.from_xml_string(response_text)

            return parser_data

        except Exception as e:
            LOGGER.error(f"Flow rewrite simple error: {e}")

            return RewriteQuery.from_xml_string(
                f"<rewrite>{query}</rewrite>"
            )

    @observe()
    async def _flow_rewrite_follow_up(
            self,
            messages: List[Dict],
    ) -> 'RewriteQuery':

        query = messages[-1]['content']
        _history = [
            f"User: {m['content']}"
            if m['role'] == 'user'
            else f"BOT: {m['content']}"
            for m in messages[-11:-1]
        ]

        # _prompt_simple = REWRITE_FOLLOW_UP.format(
        #     conversation=_history,
        #     query=query,
        # )

        _prompt_follow_up = lf.get_prompt("BEEKTNB_REWRITE_FOLLOW_UP").compile(**{"conversation": _history, "query": query})

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt_follow_up}
            ]
        )

        try:
            parser_data = RewriteQuery.from_xml_string(response_text)

            return parser_data

        except Exception as e:
            LOGGER.error(f"Flow rewrite simple error: {e}")

            return RewriteQuery.from_xml_string(
                f"<rewrite>{query}</rewrite>"
            )

    async def _flow_classify_topic(
            self,
            messages: List[Dict],
    ) -> 'ClassifyTopic':

        _history = [
            f"User: {m['content']}"
            # else f"BOT: {m['content']}"
            for m in messages[-41:-1] if m['role'] == 'user'
        ]

        _prompt_topic = CLS_TOPIC.format(
            category=list_category,
            conversation=_history
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt_topic}
            ]
        )

        try:
            parser_data = ClassifyTopic.from_xml_string(response_text)

            return parser_data

        except Exception as e:
            LOGGER.error(f"Flow classify topic error: {e}")

            return ClassifyTopic.from_xml_string(
                f"<topic>none</topic>"
            )

    @observe()
    async def _flow_verify_topic(
            self,
            query: str
    ) -> 'VerifyTopic':
        """Kiểm tra xem câu hỏi của người dùng đã có hoạt động kiểm toán nội bộ chưa

        """
        _prompt_verify = VERIFY_TOPIC_QUERY.format(
            category=list_category,
            query=query
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt_verify}
            ]
        )

        try:
            parser_data = VerifyTopic.from_xml_string(response_text)

            return parser_data

        except Exception as e:
            LOGGER.error(f"Flow classify topic error: {e}")

            return RewriteQuery.from_xml_string(
                f"<verify_topic>no</verify_topic>"
            )
    
    
    @observe
    async def check_state_ask_human(
        self,
        messages: List[Dict]
    ) -> bool:
        """
            Kiểm tra xem cần hỏi lại người dùng không khi chưa rõ topic.

            Args: Lịch sử trò chuyện

            return:
                - True: Nếu trong 20 turn chat chưa có câu hỏi lại nào
                - False: Nếu trong 20 turn chat có câu hỏi lại
        """

        result_check = [self.character_ask_human in a['content'] for a in messages[-21:-1] if a['role'] != 'user']

        if True not in list(result_check):
            return True
        else:
            return False
    
    def create_chunk(
            self,
            text,
    ) -> Dict:
        chunk = {
            "choices": [{
                "delta": {
                    "content": text,
                }
            }],
            "docs": [],
        }

        obj_chunk = json.loads(json.dumps(chunk), object_hook=lambda x: SimpleNamespace(**x))
        obj_chunk.json = lambda: json.dumps(chunk)

        return obj_chunk

    def get_topic_use_condition(
            self,
            query: str,
            topic_verify: str,
            flag_advise_detect: bool
    ) -> str:
        """
            Topic phát hiện/kiến nghị khác với topic của hướng dẫn -> Cần có bước asign lại topic để match với 
        """
        if flag_advise_detect:
            if 'BCTC' in topic_verify:
                if "thẩm định" in query.lower():
                    topic_ktnb = "Thẩm định BCTC (Báo cáo tài chính)"
                else:
                    topic_ktnb = "Kiểm toán BCTC (Báo cáo tài chính)"
            elif 'KHCN' in topic_verify:
                topic_ktnb = "Kiểm toán Hoạt động cấp tín dụng KHCN"
            elif 'PCRT' in topic_verify:
                topic_ktnb = "Kiểm toán hoạt động PCRT"
            else:
                topic_ktnb = topic_verify
        else:
            topic_ktnb = topic_verify
        
        return topic_ktnb

    @observe(name="BotKTNB")
    async def run(
            self,
            messages: List[Dict],
            role_ids: List[str] = [],
            **kwargs
    ) -> AsyncStream[ChatCompletionChunk]:  # type: ignore
        langfuse_context.update_current_trace(name="BotKTNB")
        query_origin = messages[-1]['content']

        _history = [
            f"User: {m['content']}"
            if m['role'] == 'user'
            else f"BOT: {m['content']}"
            for m in messages[-5:-1]
        ]
        
        topic = None

        try:
            bot_id = kwargs.get("bot_id", None)
            if not bot_id:
                raise ValueError("Bot ID is not provided")
        except Exception as e:
            raise ValueError("Bot ID is not provided")
        
        try:
            metadata = kwargs.get("metadata", {})
            print("Metadata: ", metadata)
        except Exception as e:
            print("Error get metadata")
            metadata = {}
            print("Metadata: ", metadata)

        if metadata is not None:
            paths = metadata.get("paths", [])
            type_chat = metadata.get("type", "DEFAULT")
        else:
            paths = []
            type_chat = "DEFAULT"

        if type_chat == "SUMMARY":
            if paths and len(paths) > 0:

                yield self.create_chunk(text="BotKTNB đang chuẩn bị bản tóm tắt, bạn vui lòng đợi trong giây lát.\n")

                text_summary = await asyncio.gather(*[
                    self.summarizer.summary_document(s3_path=p) for p in paths
                ])

                for t_summary in text_summary:
                    yield self.create_chunk(text=t_summary + "\n\n")

                return

            else:
                
                yield self.create_chunk(text="BotKTNB đang chuẩn bị bản tóm tắt, bạn vui lòng đợi trong giây lát.\n")

                text_summary = await self.summarizer.summary_document(text_document=query_origin)

                yield self.create_chunk(text=text_summary)

                return
            
        else:
            t_s = time.time()
            result_analysis_query = await asyncio.gather(*[
                self._flow_classify_intent(messages=messages),
                self._flow_rewrite_follow_up(messages=messages),
                # self._flow_rewrite_base(messages=messages),
                # self._flow_rewrite_simple(messages=messages),
                # self._flow_classify_topic(messages=messages),
                # self._flow_verify_topic(query=query_origin)
            ])
            print("Time process analysis: ", time.time() - t_s)
            # classify_query, rewrite_simple, rewrite_follow_up, cls_topic, verify_topic = \
                # result_analysis_query[0], result_analysis_query[1], result_analysis_query[2], result_analysis_query[3], \
                # result_analysis_query[4]
            classify_query, rewrite_follow_up = \
                result_analysis_query[0], result_analysis_query[1]

            print("task 1: ", classify_query.task1)
            print("task 2: ", classify_query.task2)
            print("task 3: ", classify_query.task3)

            if classify_query.task1 == "chit_chat":
                async for chunk in self._flow_chit_chat(
                    query=query_origin,
                    docs=[]
                ):
                    yield chunk

                return

            elif classify_query.task2 != "none":
                cls_query = classify_query.task2
                if cls_query in REFUSAL_MESSAGES:
                    task = REFUSAL_MESSAGES[cls_query]
                else:
                    task = REFUSAL_MESSAGES["5"]

                async for chunk in self._flow_special_case(
                        query=query_origin,
                        task=task
                ):
                    yield chunk

                return

            else:
                # if classify_query.task3 == 'follow-up':
                
                # query_rewrite_base = rewrite_base.rewrite
                # else:
                #     query_rewrite = rewrite_simple.rewrite

                query_rewrite = rewrite_follow_up.rewrite

                try:
                    categories = await self._fetch_bot_category(
                        bot_id=bot_id
                    )

                    status = categories["status"]

                    if status != "success":
                        topic == None
                    else:

                        processed_category_data, category_mapping = self._process_category_data(categories["data"])

                        query_topic = await self._extract_query_topic(
                            rewritten_query=query_rewrite,
                            category_data=processed_category_data
                        )

                        topic_index = int(query_topic.topic)

                        if topic_index not in category_mapping:
                            topic = None
                        else:
                            topic = category_mapping[topic_index]
                except Exception as e:
                    LOGGER.error(f"Error in get query topic: {e}")
                    topic = None

                print("Topic: ", topic)

                retrieval_result = await self._retrieval_rerank_cross(
                    query=query_rewrite,
                    role_ids=role_ids,
                    topic=topic,
                    valid_score=0.5
                )

                async for chunk in self._flow_non_chit_chat(
                        query=query_rewrite,
                        docs=retrieval_result['docs']
                ):
                    yield chunk

                return


async def main():

    # from beeportal.beegen_bot_v2 import Bot
    from beegenerate.storage import BotStore
    from beegenerate.configs import MongoConfig, MilvusConfig
    import time

    # bot_id = "b10f0d26-4d91-47f5-8cac-034b87e42c7f"
    bot_id = "f359b089-6b2d-4c0a-8dfe-e85eca992a61"
    bot_store = BotStore(config=MongoConfig.default())
    bot_config = bot_store.fetch_bot_details(
        bot_id=bot_id
    )

    bot = BotKTNB(
        bot_config=bot_config,
        vec_store=MilvusStorage(config=MilvusConfig.default()),
        doc_store=DocumentStore(config=MongoConfig.default()),
        bot_store=BotStore(config=MongoConfig.default())
    )

    # messages = [{"role": "user", "content": "Tóm tắt hoạt động kiểm toán tín dụng"}]

    # await bot.test_async(messages=messages)
    # await bot.test_sync(messages=messages)

    # with open("beektnb/list_no_docs.txt", "r", encoding='utf-8') as f:
    #     questions = f.read().strip().split("\n")

    # print("Question: ", questions[0])
    # print("len question: ", len(questions))

    # for i, ques in enumerate(questions):
    #     try:
    #         output_text = ""
    #         async for chunk in bot.run(
    #             messages = [
    #                 {"role": "user", "content": ques},
    #             ],
    #             role_ids = ["L1"],
    #             topic = "default"
    #         ):
    #             if len(chunk.choices) > 0:
    #                 if chunk.choices[0].delta.content is not None:
    #                     response_text = chunk.choices[0].delta.content
    #                     # print(response_text, end="")
    #                     output_text += response_text

    #         with open("beektnb/answer_test_no_docs_2.txt", "a", encoding='utf-8') as f:
    #             f.write(f"Question {i+1}: {ques}")
    #             f.write("\n")
    #             f.write(output_text)
    #             f.write("\n\n\n")

    #         time.sleep(2)

    #     except Exception as e:
    #         time.sleep(2)

    history = []
    while True:
        user_input = input("You: ")
        t_s = time.time()
        output_text = ""
        async for chunk in bot.run(
                messages=history + [
                    {"role": "user", "content": user_input},
                ],
                role_ids=["L1"],
                metadata={
                    "type": "DEFAULT",
                    "path": []
                },
                bot_id=bot_id
        ):
            if len(chunk.choices) > 0:
                if chunk.choices[0].delta.content is not None:
                    response_text = chunk.choices[0].delta.content
                    print(response_text, end="")
                    output_text += response_text
        
        history += [{"role": "user", "content": user_input}, {"role": "assitance", "content": output_text}]

        with open("beektnb/response_text.txt", "w", encoding='utf-8') as f:
            f.write(output_text)

        print("Total time: ", time.time() - t_s)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
