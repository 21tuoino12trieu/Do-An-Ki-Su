from beegenerate.prompts.beegen_common import (
    REWRITE_AND_CLASSIFY_PROMPT,
    VERIFY_DOCUMENT_PROMPT,
    NON_CHIT_CHAT_PROMPT,
    REFUSE_PROMPT
)

from pydantic import BaseModel
import yaml

from beegenerate.retrievers.vector_retriever import VectorRetriever
from beegenerate.vectordb import MilvusStorage
from beegenerate.reranks import RerankingFactory
from beegenerate.storage import (
    DocumentStore,
    BotStore
)

from beegenerate.configs import (
    LLMConfig
)

from beegenerate.llms.llm_executor import LLMExecutor

from openai import AsyncStream
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from typing import (
    List,
    Dict,
    Tuple,
    Any,
    TypeVar,
    Type
)

from datetime import datetime
from beegenerate.utils.common import transform_bot_id

from beegenerate.loggings import LOGGER

from beecrm.hierarchy import hierarchy
from beecrm.utils import run_calculate_score
import json
from types import SimpleNamespace

from beecrm.services.beecrm_sv import L1Classify, ExtractQuery, CLSQuestion, RewriteQuestion, CLSSxkd, ChoiceDocument
from beecrm.prompts.beecrm_prompt import L1_CLASSIFY, EXTRACT_QUERY, CLS_QUESTION, CHAT_PROMPT, REJECT_PROMPT, REWRITE_PROMPT, CLS_SXKD, CHOICE_DOCUMENT, CHOICE_RANK_DOCUMENTS

from beecrm.hierarchy import hierarchy
from beecrm.utils import run_calculate_score, run_calculate_score_sxkd, run_suggest_business_industries, run_query_industry
import json
from types import SimpleNamespace
import re
import asyncio
from langfuse.decorators import observe, langfuse_context
from beecrm.constant import MAJOR
from beegenerate.const import BEEGEN_ROOT

# Create a generic type that must be a subclass of BaseModel
T = TypeVar('T', bound=BaseModel)


class InputQuery(BaseModel):
    query: str
    intent: str


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

        # Validate and create specified Pydantic model
        return model_class(**data)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML format: {e}")
    except Exception as e:
        raise ValueError(f"Validation error: {e}")


class BotCRM:
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

        self._reranker = RerankingFactory.create(config=self.bot_config['reranking'])
        
        print("BEEGEN ROOT: ", BEEGEN_ROOT)
        self._llm_search = LLMExecutor(
            primary_config=LLMConfig.from_yaml_file(
                BEEGEN_ROOT / "config/llms/beegen_v3.yaml"),
            config_store=bot_store
        )

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
        documents_text = "\n[SEP]\n".join([d['content'] for d in documents])
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
    
    @observe()
    async def _stream_llm_response_search(
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
            async for chunk in self._llm_search.run(messages=messages):
                if len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                    response_text += str(chunk.choices[0].delta.content)
            return response_text
        except Exception as e:
            LOGGER.error(f"Error streaming LLM response: {e}")
            raise RuntimeError(f"Failed to get LLM response: {str(e)}")

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
            topic: str = "default",
            partition_names: List[str] = []
    ) -> List[Dict]:
        # 2. retrieve the relevan records by vector search
        retrieval_records = await self._retriever.run(
            query=query,
            bot_id=self.bot_config['id'],
            collection=f"bot_{transform_bot_id(self.bot_config['id'])}",
            allowed_roles=role_ids,
            top_k=self \
                .bot_config['retrieval'] \
                .top_k,
            # top_k=16,
            threshold=self \
                .bot_config['retrieval'] \
                .threshold,
            partition_names=partition_names
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
    async def _retrieval_and_rerank(
            self,
            query: str,
            role_ids: List[str] = [],
            topic: str = "default",
            partition_names: List[str] = [],
            top_k: int = 4,
            valid_score: float = 0.5
    ) -> Dict:
        # Retrieval
        retrieval_records = await self._retrieval(
            query=query,
            role_ids=role_ids,
            topic=topic,
            partition_names=partition_names
        )

        # Rerank
        reranked_results = await self._rerank(
            query=query,
            retrieval_records=retrieval_records,
        )

        # 1. construct the final documents
        final_docs = []
        valid_count = 0
        for r in reranked_results:
            record = retrieval_records[r['index']]
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
    async def _rewrite_query(
            self,
            messages: List[Dict]
    ) -> 'RewriteQuestion':
        # 1. get the user latest message and chat history 
        query = messages[-1]['content']
        _history = [
            f"User: {m['content']}"
            if m['role'] == 'user'
            else f"Bot: {m['content']}"
            for m in messages[-11:-1]
        ]

        # print("History: ", _history)

        system_prompt = REWRITE_PROMPT.format(
            query=query,
            conversation=_history,
            hierarchy=hierarchy
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": system_prompt}
            ]
        )

        try:
            parser_data = RewriteQuestion.from_xml_string(response_text)

            return parser_data

        except Exception as e:
            LOGGER.error(f"Flow classify topic error: {e}")

            return RewriteQuestion.from_xml_string(
                f"""<rewrite>{query}</rewrite>"""
            )

    @observe()
    async def _flow_choice_major(
            self,
            query: str,
            docs: List[str]
    ) -> 'ChoiceDocument':
        """Choice document
        """
        dict_doc = [{"id": i, 'text': text} for i, text in enumerate(docs)]
        system_prompt = CHOICE_RANK_DOCUMENTS.format(
            query=query,
            docs=dict_doc
        )

        response_text = await self._stream_llm_response_search(
            messages=[
                {"role": "user", "content": system_prompt}
            ]
        )
        # print("Respoonce text: ", response_text)
        try:
            parser_data = ChoiceDocument.from_xml_string(response_text)

            return parser_data

        except Exception as e:
            LOGGER.error(f"Flow choice document error: {e}")

            return ChoiceDocument.from_xml_string(
                f"""<id>0</id>"""
            )

    @observe()
    async def search_semantic(
            self,
            query: str,
            role_ids: List[str] = [],
            topic: str = "default",
            partition_names=['document'],
    ) -> List[Dict]:
        # Retrieval and rerank
        result_search = await self._retrieval(
            query=query,
            role_ids=role_ids,
            topic=topic,
            partition_names=partition_names,
        )

        docs = [r['content'] for r in result_search]

        result_choice = await self._flow_choice_major(query=query, docs=docs)

        list_index_doc = result_choice.id

        print("list index doc: ", list_index_doc)

        list_index_doc = [a for a in list_index_doc if a < len(docs)]
        
        # count = 0
        # while len(list_index_doc) <= 2 and count < len(docs) - 1:
        #     if count not in list_index_doc:
        #         list_index_doc.append(count)
            
        #     count += 1

        
        list_name_major = [docs[index_doc].split("\n")[0].strip() for index_doc in list_index_doc]

        crmBusinessIndustries = [
            {"businessIndustryName": name_major} for name_major in list_name_major
        ]

        return crmBusinessIndustries

    def process_scenarios(
        self,
        scenarios: List[Dict]
    ) -> Tuple[str, bool]:
        if scenarios:
            if 'random' not in scenarios[0]:
                content_response = "Dưới đây là kịch bản bán hàng được xây dựng theo yêu cầu của bạn. Hãy áp dụng ngay để nâng cao hiệu quả bán hàng nhé.\n"
                share_scenarios = False

            elif scenarios[0]['random'] == False:
                content_response = "Dưới đây là kịch bản bán hàng được xây dựng theo yêu cầu của bạn. Hãy áp dụng ngay để nâng cao hiệu quả bán hàng nhé.\n"
                share_scenarios = False

            else:
                content_response = "Bạn quả là người ham học hỏi vì đã tham khảo toàn bộ những kịch bản bán hàng hiệu quả mà tôi phải vắt óc để nghĩ ra. Hãy cho tôi thêm thời gian để suy nghĩ ra những kịch bản mới nhé. Vui lòng tham khảo lại 1 kịch bản hấp dẫn mà tôi đã từng chia sẻ cho bạn"
                share_scenarios = False

        else:
            content_response = f"Hiện tại tôi chưa có kịch bản bán theo yêu cầu của bạn, tôi sẽ cập nhật và gửi tới bạn trong thời gian gần nhất. Bạn có vui lòng chia sẻ kịch bản bán hàng hiệu quả mà bạn đã từng áp dụng trong thực tế công việc?"
            share_scenarios = True
        
        return content_response, share_scenarios

        
    @observe()
    async def _flow_chat(
            self,
            query: str,
            query_original: str,
            docs: List[Dict],
            username: str,
            cls_question: 'CLSQuestion',
            cls_sxkd: 'CLSSxkd',
            role_ids: List[str] = [],
            topic: str = "default",
            partition_names: List[str] = ['document']
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

        if cls_sxkd.sxkd == 'true':
            print("Vào case sản xuất kinh doanh......")
            if cls_sxkd.major == 'true' or cls_sxkd.code != '-1':
                result_search = await asyncio.gather(*[
                    run_query_industry(query=query_original, username=username, code=cls_sxkd.code),
                    self.search_semantic(query=query, role_ids=role_ids, topic=topic, partition_names=partition_names)
                ])
                
                r_query_industry, r_search_semantic = result_search[0], result_search[1]

                print("R query industry: ", r_query_industry)
                print("R semantic: ", r_search_semantic)

                if r_query_industry.get("type"):
                    if r_query_industry["type"] == "scenarios":
                        scenarios = r_query_industry['data']['scenarios']

                        content_response, share_scenarios = self.process_scenarios(scenarios)

                        obj_chunk = self.create_chunk(content=content_response, scenarios=scenarios, share_scenarios=share_scenarios)

                        yield obj_chunk

                        return
                    
                    else:
                        crmBusinessIndustries = r_query_industry['data']['crmBusinessIndustries']

                        if crmBusinessIndustries:
                            print("Search database")
                            r_search = crmBusinessIndustries
                        else:
                            print("Search semantic")
                            r_search = r_search_semantic

                        # Trường hợp không search được ngành nghề cả search database và search semantic
                        if len(r_search) == 0:
                            obj_chunk = self.create_chunk(
                                content="Xin lỗi, hiện tại tôi chưa tìm thấy ngành nghề theo yêu cầu của bạn. Bạn có thể mô tả chi tiết hơn ngành nghề bạn đang quan tâm được không?"
                            )

                            yield obj_chunk

                            return
                        
                        elif len(r_search) == 1:
                            print("R search: ", r_search)

                            tmp_query_industry = await run_query_industry(query=r_search[0]["businessIndustryName"], username=username, code="-1")

                            print("tmp query industry: ", tmp_query_industry)

                            if tmp_query_industry["type"] == "scenarios":
                                scenarios = tmp_query_industry['data']['scenarios']

                                content_response, share_scenarios = self.process_scenarios(scenarios)

                                obj_chunk = self.create_chunk(content=content_response, scenarios=scenarios, share_scenarios=share_scenarios)

                                yield obj_chunk

                                return
                        
                        else:

                            obj_chunk = self.create_chunk(
                                content="Dưới đây là ngành/nhóm ngành phù hợp với tìm kiếm của bạn. Hãy chọn ngành để xem kịch bản bán hàng.",
                                crmBusinessIndustries=r_search
                            )
                        
                            yield obj_chunk

                            return
                
                else:
                    print("Search semantic")
                    obj_chunk = self.create_chunk(
                        content="Dưới đây là ngành/nhóm ngành phù hợp với tìm kiếm của bạn. Hãy chọn ngành để xem kịch bản bán hàng.",
                        crmBusinessIndustries=r_search_semantic
                    )

                    yield obj_chunk

                    return

            else:
                # Gọi api để xử lý case vào SXKD nhưng không có ngành
                # Output: Trả về top 5 ngành con.
                print("username: ", username)
                industries = await run_suggest_business_industries(
                    username=username
                )

                content_response = "Dưới đây là các ngành được gợi ý xem kịch bản bán hàng. Trường hợp ngành bạn cần không nằm trong danh sách, vui lòng nhập tên ngành cụ thể để tìm kịch bản phù hợp."

                obj_chunk = self.create_chunk(
                    content=content_response,
                    crmBusinessIndustries=industries
                )

                yield obj_chunk

                return
                            
        else:
            if cls_question.intent == "true":
                # 1. create chitchat prompt
                # system_prompt = CHAT_PROMPT.format(
                #     definition=self.bot_config['definition'],
                # )
                obj_chunk = self.create_chunk(
                    content="""Bạn vui lòng lựa chọn sản phẩm để mình gợi ý các kịch bản bán hàng hiệu quả nhé!\n<Button: Tín dụng> <Button: Huy động> <Button: CDs> <Button: Bancas><Button: Thẻ><Button: SP Đầu tư><Button: Kiều hối>"""
                )

                yield obj_chunk

                return

            else:
                system_prompt = REJECT_PROMPT.format(
                    definition=self.bot_config['definition'],
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
        verify = await self._verify_document(
            query=query,
            documents=docs
        )

        # 2. decide the flow matched/unmatched
        if verify.output == 'matched':
            current_date = datetime.now().strftime('%Y-%m-%d')

            system_prompt = NON_CHIT_CHAT_PROMPT.format(
                date=current_date,
                definition=self.bot_config['definition'],
                query=query,
                documents=self._format_documents(
                    documents=docs
                )
            )
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

    @observe()
    async def _flow_classify_L1(
            self,
            messages: List[Dict]
    ) -> 'L1Classify':
        """Nhiệm vụ phân loại những topic L1 đã được đề cập trong lịch sử trò chuyện.
           
           Output: Danh sách topic L1
        """

        # Get User's message
        message_user = "\n".join(["user: " + m['content'] for m in messages[-51:-1] if m['role'] == 'user'])

        _prompt = L1_CLASSIFY.format(
            hierarchy=hierarchy,
            conversation=message_user
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt}
            ]
        )
        print("Responce text flow classify topic: ", response_text)
        try:
            parser_data = L1Classify.from_xml_string(response_text)

            return parser_data

        except Exception as e:
            LOGGER.error(f"Flow classify L1 error: {e}")

            return L1Classify.from_xml_string(
                f"""<L1>none</L1>"""
            )

    @observe()
    async def _flow_extract_query(
            self,
            query: str
    ) -> 'ExtractQuery':
        """Nhiệm vụ trích xuất L1, L2 trong câu truy vấn của người dùng.
           
           Output: L1, L2 và quan hệ giữa L1 & L2
        """

        _prompt = EXTRACT_QUERY.format(
            query=query,
            hierarchy=hierarchy
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt}
            ]
        )

        try:
            parser_data = ExtractQuery.from_xml_string(response_text)

            return parser_data

        except Exception as e:
            LOGGER.error(f"Flow extract query error: {e}")

            return ExtractQuery.from_xml_string(
                f"""<L1>none</L1>
                    <L2>none</L2>
                    <relation>no</relation>"""
            )

    @observe()
    async def _flow_cls_question(
            self,
            query: str
    ) -> 'CLSQuestion':

        _prompt = CLS_QUESTION.format(
            query=query
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt}
            ]
        )

        try:
            parser_data = CLSQuestion.from_xml_string(response_text)

            return parser_data

        except Exception as e:
            LOGGER.error(f"Flow classify question error: {e}")

            return CLSQuestion.from_xml_string(
                f"""<chat>false</chat>"""
            )
    
    async def _flow_cls_sxkd(
            self,
            query: str
    ) -> 'CLSSxkd':
        """Xác định câu hỏi người dùng có đề cập đến SXKD không.
        
        Output: true|false
        """

        _prompt = CLS_SXKD.format(
            query=query,
            major=MAJOR
        )

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "user", "content": _prompt}
            ]
        )

        # print("Reponse text: ", response_text)

        try:
            parser_data = CLSSxkd.from_xml_string(response_text)

            return parser_data

        except Exception as e:
            LOGGER.error(f"Flow classify sxkd error: {e}")

            return CLSSxkd.from_xml_string(
                f"""<sxkd>false</sxkd>
                    <major>false</major>
                    <code>-1</code>"""
            )

    def create_chunk(
            self,
            content: str,
            scenarios: List[Dict] = [],
            share_scenarios: bool = False,
            crmBusinessIndustries: List[Dict] = []
    ) -> Dict:
        chunk = {
            "choices": [{
                "delta": {
                    "content": content,
                }
            }],
            "docs": [],
            "metadata": {
                "scenarios": scenarios,
                "share_scenarios": share_scenarios,
                "crmBusinessIndustries": crmBusinessIndustries
            }
        }

        obj_chunk = json.loads(json.dumps(chunk), object_hook=lambda x: SimpleNamespace(**x))
        obj_chunk.json = lambda: json.dumps(chunk)

        return obj_chunk

    @observe()
    async def verify_l1(
            self,
            query: str,
            role_ids: List[str]
    ) -> bool:
        # Retrieval QA, xác định xem câu chat có match với QA không, nếu match và score cao thì return câu trả lời
        retrieval_record = await self._retrieval(
            query=query,
            partition_names=['QA'],
            role_ids=role_ids
        )

        if retrieval_record and retrieval_record[0]['score'] >= 0.99:
            # process content
            content = retrieval_record[0]['content']
            content = content.split("Câu trả lời:")[-1].strip()
            return True, content
        else:
            return False, ""

    @observe()
    async def run_case_l1_l2(
            self,
            category: str,
            sub_category: str,
            username: str
    ) -> Dict:

        scenarios = await run_calculate_score(
            username=username,
            category=category,
            sub_category=sub_category
        )
        print(scenarios)
        content_response, share_scenarios = self.process_scenarios(scenarios)

        obj_chunk = self.create_chunk(content=content_response, scenarios=scenarios, share_scenarios=share_scenarios)

        return obj_chunk
    
    @observe()
    async def run_case_l3(
            self,
            username: str,
            businessIndustryName: str,
            businessIndustryId: str = None,
            
    ) -> Dict:
        """Hanlde trường hợp hỏi L3 của sản xuất kinh doanh
        """

        scenarios = await run_calculate_score_sxkd(
            username=username,
            businessIndustryId=businessIndustryId,
            businessIndustryName=businessIndustryName
        )
        
        content_response, share_scenarios = self.process_scenarios(scenarios)

        obj_chunk = self.create_chunk(
            content=content_response,
            scenarios=scenarios,
            share_scenarios=share_scenarios
        )

        return obj_chunk

    @observe()
    async def run_case_l1(
            self,
            category: str,
            username: str,
            content: str
    ) -> Dict:
        has_l2 = re.findall(r"<Button:\s*(.*?)\s*>", content)

        # Trường hợp L1 có L2, trả về nội dung theo QA
        if has_l2:
            # Chunk chứa nội dung.
            obj_chunk = self.create_chunk(content=content, scenarios=[], share_scenarios=False)

            return obj_chunk

        # Trường hợp L1 không có L2, sẽ truy vấn đến kịch bản và trả về cho FE
        else:
            sub_category = ""

            print("Username: ", username)
            print("Category: ", category)
            print("Sub category: ", sub_category)

            # Call API calculate scoring
            scenarios = await run_calculate_score(
                username=username,
                category=category,
                sub_category=sub_category
            )

            content_response, share_scenarios = self.process_scenarios(scenarios)
            
            obj_chunk = self.create_chunk(content=content_response, scenarios=scenarios, share_scenarios=share_scenarios)

            return obj_chunk
    

    @observe(name="BotCRM")
    async def run(
            self,
            messages: List[Dict],
            role_ids: List[str] = [],
            topic: str = "default",
            **kwargs
    ) -> AsyncStream[ChatCompletionChunk]:  # type: ignore
        query_original = messages[-1]['content']
        username = topic

        # Kiểm tra query có trong QA không, nếu có trả về cho FE ngay
        tmp_verify = await self.verify_l1(query_original, role_ids=role_ids)

        if tmp_verify[0]:
            obj_chunk = await self.run_case_l1(
                category=query_original,
                username=username,
                content=tmp_verify[1]
            )

            yield obj_chunk

            return

        # Kiểm tra metadata
        metadata = kwargs.get("metadata", None)

        print("Metadata: ", metadata)

        if metadata is not None:
            crmBusinessIndustry = metadata.get("crmBusinessIndustry", None)

            print("crmBusinessIndustries: ", crmBusinessIndustry)
            
            if crmBusinessIndustry is not None:
                businessIndustryId = crmBusinessIndustry.get("businessIndustryId", None)
                businessIndustryName = crmBusinessIndustry.get("businessIndustryName", None)

                print("businessIndustryId: ", businessIndustryId)
                print("businessIndustryName: ", businessIndustryName)

                if businessIndustryName is not None:
                    obj_chunk = await self.run_case_l3(
                        username=username,
                        businessIndustryId=businessIndustryId,
                        businessIndustryName=businessIndustryName
                    )

                    yield obj_chunk

                    return

        if "xem thêm" in query_original.lower() and len(messages) > 1:
            messages_user = [a for a in messages[:-1] if ("xem thêm" not in a['content'].lower() and a['role'] == 'user')] + [messages[-1]]
            parser_rewrite = await self._rewrite_query(messages=messages_user)
        else:
            # Trường hợp query không có trong QA
            parser_rewrite = await self._rewrite_query(messages=messages)

        print("Câu hỏi sau rewrite: ", parser_rewrite.rewrite)

        # 1. Classify L1 topic and Extract query
        result_parsers = await asyncio.gather(
            *[self._flow_classify_L1(messages=messages),
              self._flow_extract_query(query=parser_rewrite.rewrite),
              self._flow_cls_question(query=parser_rewrite.rewrite),
              self._flow_cls_sxkd(query=parser_rewrite.rewrite)]
        )

        topic_l1 = []
        if result_parsers[0] != 'none':
            topic_l1 = [a.strip() for a in result_parsers[0].L1.split(',') if a != 'none']

        query_l1, query_l2, query_l1_l2_relation = result_parsers[1].L1, result_parsers[1].L2, result_parsers[1].relation
        cls_question, cls_sxkd = result_parsers[2], result_parsers[3]

        print("topic l1: ", topic_l1)
        print("query l1: ", query_l1)
        print("query l2: ", query_l2)
        print("query l1 l2 relation: ", query_l1_l2_relation)

        # L1 != none, L2 != none
        if query_l1 != 'none' and query_l2 != 'none':
            print("Vào case L1, L2 khác none")

            result_l1 = await self.verify_l1(query=query_l1, role_ids=role_ids)
            print("result l1: ", result_l1)

            if result_l1[0]:
                if query_l2 == 'SXKD':
                    print("Vào case sản xuất kinh doanh......")

                    # 4. decide the flow, return streaming response
                    async for chunk in self._flow_chat(
                            # messages=messages,
                            query=parser_rewrite.rewrite,
                            query_original=query_original,
                            docs=[],
                            cls_question=cls_question,
                            cls_sxkd=cls_sxkd,
                            role_ids=role_ids,
                            topic=topic,
                            username=username
                    ):
                        yield chunk

                    return

                else:
                    # Call API calculate scoring
                    obj_chunk = await self.run_case_l1_l2(
                        category=query_l1,
                        sub_category=query_l2,
                        username=username
                    )

                    yield obj_chunk

                    return
            
            else:
                # 4. decide the flow, return streaming response
                async for chunk in self._flow_chat(
                        # messages=messages,
                        query=parser_rewrite.rewrite,
                        query_original=query_original,
                        docs=[],
                        cls_question=cls_question,
                        cls_sxkd=cls_sxkd,
                        role_ids=role_ids,
                        topic=topic,
                        username=username
                ):
                    yield chunk

                return
        
        # L1 != none, L2 = none
        elif query_l1 != 'none' and query_l2 == 'none':
            result_l1 = await self.verify_l1(query=query_l1, role_ids=role_ids)

            print("result l1: ", result_l1)

            if cls_sxkd.sxkd == "true":
                print("Vào case sản xuất kinh doanh......")
                # 4. decide the flow, return streaming response
                async for chunk in self._flow_chat(
                        # messages=messages,
                        query=parser_rewrite.rewrite,
                        query_original=query_original,
                        docs=[],
                        cls_question=cls_question,
                        cls_sxkd=cls_sxkd,
                        role_ids=role_ids,
                        topic=topic,
                        username=username
                ):
                    yield chunk

                return

            elif result_l1[0]:
                print("Vào case L1")

                content = result_l1[1]

                obj_chunk = await self.run_case_l1(
                    category=query_l1,
                    username=username,
                    content=content
                )

                yield obj_chunk

                return

            else:
                # 4. decide the flow, return streaming response
                async for chunk in self._flow_chat(
                        # messages=messages,
                        query=parser_rewrite.rewrite,
                        query_original=query_original,
                        docs=[],
                        cls_question=cls_question,
                        cls_sxkd=cls_sxkd,
                        role_ids=role_ids,
                        topic=topic,
                        username=username
                ):
                    yield chunk

                return
        
        # L1 = none, L2 != none
        elif query_l1 == 'none' and query_l2 != 'none':
            if query_l2 == 'SXKD':
                print("Vào case sản xuất kinh doanh......")

                # 4. decide the flow, return streaming response
                async for chunk in self._flow_chat(
                        # messages=messages,
                        query=parser_rewrite.rewrite,
                        query_original=query_original,
                        docs=[],
                        cls_question=cls_question,
                        cls_sxkd=cls_sxkd,
                        role_ids=role_ids,
                        topic=topic,
                        username=username
                ):
                    yield chunk

                return

            else:
                print("Vào query l2 != none")
                print("Topic l1: ", topic_l1)
                result_verify_l1 = await asyncio.gather(*[
                    self.verify_l1(t, role_ids=role_ids) for t in topic_l1
                ])
                print("result_verify_l1: ", result_verify_l1)
                category, sub_category = None, None
                for i, res in enumerate(result_verify_l1):
                    if res[0]:
                        c_button = [a.strip() for a in re.findall(r"<Button:\s*(.*?)\s*>", res[1])]
                        print("c_button: ", c_button)
                        if query_l2 in c_button:
                            category = topic_l1[i]
                            sub_category = query_original

                            break

                if category is not None and sub_category is not None:
                    obj_chunk = await self.run_case_l1_l2(
                        category=category,
                        sub_category=sub_category,
                        username=username
                    )

                    yield obj_chunk

                    return
                
                else:
                    # 4. decide the flow, return streaming response
                    async for chunk in self._flow_chat(
                            # messages=messages,
                            query=parser_rewrite.rewrite,
                            query_original=query_original,
                            docs=[],
                            cls_question=cls_question,
                            cls_sxkd=cls_sxkd,
                            role_ids=role_ids,
                            topic=topic,
                            username=username
                    ):
                        yield chunk

                    return
        
        # L1 = none, L2 = none
        else:
            # 4. decide the flow, return streaming response
            async for chunk in self._flow_chat(
                    # messages=messages,
                    query=parser_rewrite.rewrite,
                    query_original=query_original,
                    docs=[],
                    cls_question=cls_question,
                    cls_sxkd=cls_sxkd,
                    role_ids=role_ids,
                    topic=topic,
                    username=username
            ):
                yield chunk

            return


async def main():
    from beeportal.beegen_bot_v2 import Bot
    from beegenerate.storage import BotStore
    from beegenerate.configs import MongoConfig, MilvusConfig
    import time

    # bot_id = "b10f0d26-4d91-47f5-8cac-034b87e42c7f"
    bot_id = "ae5e0fb7-7db6-42fa-8024-ee133a116cd0"
    bot_store = BotStore(config=MongoConfig.default())
    bot_config = bot_store.fetch_bot_details(
        bot_id=bot_id
    )

    bot = BotCRM(
        bot_config=bot_config,
        vec_store=MilvusStorage(config=MilvusConfig.default()),
        doc_store=DocumentStore(config=MongoConfig.default()),
        bot_store=BotStore(config=MongoConfig.default())
    )
    messages = []
    while True:
        print("Nhập câu chat: ")
        user_input = str(input())
        t_s = time.time()
        messages.append({"role": "user", "content": user_input})
        response_text = ""
        async for chunk in bot.run(
                messages=messages,
                role_ids=["L1"],
                topic="chaundn"
        ):
            if len(chunk.choices) > 0:
                if chunk.choices[0].delta.content is not None:
                    response_text += chunk.choices[0].delta.content
        
        print(response_text)
        messages.append({"role": "assitance", "content": response_text})

        print("Total time: ", time.time() - t_s)


if __name__ == "__main__":
    asyncio.run(main())
