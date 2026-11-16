from beegenerate.prompts.beegen_common import (
    REWRITE_AND_CLASSIFY_PROMPT,
    CHIT_CHAT_PROMPT,
    VERIFY_DOCUMENT_PROMPT,
    NON_CHIT_CHAT_PROMPT,
    REFUSE_PROMPT
)

from beegenerate.prompts.bot_KT_S import (
    DECOMPOSE_QUERY_PROMPT,
    GET_RESPONSE_PROMPT
)
from pydantic import BaseModel
import yaml, json
import re
import pandas as pd

from beegenerate.retrievers.vector_retriever import VectorRetriever
from beegenerate.vectordb import MilvusStorage
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
    Tuple,
    Any,
    TypeVar,
    Type,
    Union
)

from datetime import datetime
from beegenerate.utils.common import transform_bot_id

from beegenerate.loggings import LOGGER
from beegenerate.loggings.loggers import lf
from langfuse.decorators import langfuse_context, observe

# Create a generic type that must be a subclass of BaseModel
T = TypeVar('T', bound=BaseModel)


class InputQuery(BaseModel):
    query: str
    intent: str


class VerifyResult(BaseModel):
    output: str


from beegenerate.llms.llm_response import fake_chunk_from
import uuid


def create_response_chunk(answer: str, **kwargs):
    return fake_chunk_from(
        content=answer,
        model="cached",
        chat_id=f"chat-{uuid.uuid4()}",
        current_time=0,
        last=False,
        **kwargs
    )


def sort_documents_by_date(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sắp xếp danh sách tài liệu theo 'Ngày ban hành' (mới nhất trước).

    Args:
        documents (list): Danh sách tài liệu (dict) có trường 'Ngày ban hành'.

    Returns:
        list: Danh sách đã sắp xếp theo ngày giảm dần.
    """

    def parse_date(date_str: str) -> datetime:
        try:
            return datetime.strptime(date_str, "%d/%m/%Y")
        except Exception:
            return datetime.min  # lõi set time cũ rích

    return sorted(documents, key=lambda doc: parse_date(doc.get("Ngày ban hành văn bản", "")), reverse=True)


def convert_chunks_to_prompt(docs_classified: Dict[str, List[Dict[str, Any]]]) -> str:
    """
    Trích xuất content theo thứ tự ưu tiên tier và nối lại thành chuỗi theo định dạng chunk.

    Args:
        docs_classified (dict): Dữ liệu đã phân theo tier.

    Returns:
        str: Chuỗi định dạng theo từng chunk.
    """
    result_lines = []
    chunk_index = 1

    for tier in sorted(docs_classified.keys(), key=lambda x: int(x.split("_")[1])):  # sx theo tier
        for doc in docs_classified[tier]:
            content = doc.get("content", "").strip()
            docs_name = doc.get("Tên văn bản", "").strip()
            result_lines.append(f"chunk_{chunk_index}:\n Thông tin ban hành:### {docs_name} ###\n{content}")
            chunk_index += 1

    return "\n".join(result_lines)

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


def get_docs_info(source: Union[str, bytes], sheet_name: Union[str, int] = 0) -> dict:
    """
    Đọc Excel và chuyển thành dict lồng, với key ngoài là giá trị cột đầu tiên, value là dict còn lại.

    Args:
        source (str or bytes): Đường dẫn file local hoặc URL.
        sheet_name (str or int): Tên hoặc index sheet trong Excel.

    Returns:
        dict: Dữ liệu dạng dict[key1] = {col2: val2, col3: val3, ...}
    """
    df = pd.read_excel(source, sheet_name=sheet_name)
    df = df.dropna(how='all')  # Bỏ dòng trống hoàn toàn

    # Xác định tên cột
    columns = df.columns.tolist()
    if len(columns) < 2:
        raise ValueError("Excel cần ít nhất 2 cột để xây dựng nested dict.")

    key_column = columns[0]
    value_columns = columns[1:]

    # Tạo dict lồng
    nested_dict = {
        str(row[key_column]): {
            str(col): row[col] for col in value_columns
        }
        for _, row in df.iterrows()
    }

    return nested_dict


class BeeKTData:
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
            bot_store: BotStore,
            bot_id: str
    ):
        """Initialize the Bot instance with necessary components.
        
        Args:
            bot_config (Dict): Configuration dictionary containing LLM, embedding, and reranking settings for the bot
            vec_store (MilvusStorage): Vector storage instance for managing embeddings and similarity search
            doc_store (DocumentStore): Document storage instance for retrieving and managing content
            bot_store (BotStore): Bot configuration storage used for fallback LLM configs when primary configuration is inactive
        """
        self.bot_id = bot_id
        self.bot_config = bot_config

        self._llm = LLMExecutor(
            primary_config=self.bot_config['llm'],
            config_store=bot_store
        )
        self._doc_store = doc_store
        self._retriever = VectorRetriever(
            config=bot_config['retrieval'],
            vec_store=vec_store,
            doc_store=doc_store
        )

        self._reranker = RerankingFactory.create(config=self.bot_config['reranking'])

    @staticmethod
    def _get_role_hierarchy(role: str) -> List[str]:
        """Get list of roles based on hierarchy."""
        role_hierarchy = {
            "L1": ["L1"],
            "L2": ["L2", "L1"],
            "L3": ["L3", "L2", "L1"]
        }
        return role_hierarchy.get(role, ["L1"])

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
            messages: List[Dict],
            docs : List[Dict] = [],
            check_stream :str =False
    ):
        """Stream response from LLM and concatenate chunks into a single string.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' fields
            
        Returns:
            Concatenated response string from the LLM
            
        Raises:
            RuntimeError: If LLM streaming fails
        """
        try:
            attached_docs = self._create_attached_docs(documents=docs)

            if check_stream:
                # Trả về từng chunk
                async for chunk in self._llm.run(messages=messages, docs=attached_docs):
                    yield chunk
                return
            else:
                # Gom tất cả chunk thành 1 string rồi yield 1 lần
                response_text = ""
                async for chunk in self._llm.run(messages=messages, docs=attached_docs):
                    if len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                        response_text += str(chunk.choices[0].delta.content)
                yield response_text
                return

        except Exception as e:
            LOGGER.error(f"Error streaming LLM response: {e}")
            langfuse_context.update_current_observation(level="ERROR", output=str(e))
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

        response_text = ""
        async for text in self._stream_llm_response(
            messages=[{"role": "user", "content": _prompt}],
            check_stream=False  # gom chuỗi
        ):
            response_text = text  # chỉ có 1 yield cuối cùng

        return parse_model(
            input_text=response_text,
            model_class=InputQuery
        )

    @observe()
    async def _decompose_query(
            self,
            input_query: str,
    ) -> List:
        _prompt = DECOMPOSE_QUERY_PROMPT.format(
            query=input_query
        )

        response_text = ""
        async for text in self._stream_llm_response(
            messages=[{"role": "user", "content": _prompt}],
            check_stream=False  # gom chuỗi
        ):
            response_text = text  # chỉ có 1 yield cuối cùng
        print("=" * 25 + "response_text_DECOMPOSE_QUERY" + "=" * 25)
        print(response_text)
        queries_separated = re.findall(r"<element>(.*?)</element>", response_text, re.DOTALL)
        return queries_separated

    @observe()
    async def _retrieval_and_rerank(
            self,
            input_query: str,
            role_ids: List[str] = ["L1"],
            topic: str = "default",
            valid_score: float = 0.5
    ) -> List[Dict]:
        """Retrieve and rerank documents based on query and role hierarchy.
        
        Performs two-stage search:
        1. Initial retrieval using vector similarity
        2. Reranking of retrieved documents
        
        Args:
            input_query: Query object containing search text
            role: Role level for filtering documents ("L1", "L2", "L3")
            topic: Topic category for filtering
            valid_score: Minimum score threshold for valid documents
            
        Returns:
            Dictionary containing:
                - 'docs': List of ranked documents
                - 'intent': Classified intent based on document relevance
                
        Note:
            Returns empty doc list if no documents score above valid_score
        """

        # 2. retrieve the relevan records by vector search
        retrieval_records = await self._retriever.run(
            query=input_query,
            bot_id=self.bot_config['id'],
            collection=f"bot_{transform_bot_id(self.bot_config['id'])}",
            allowed_roles=role_ids,
            top_k=self \
                .bot_config['retrieval'] \
                .top_k,
            threshold=self \
                .bot_config['retrieval'] \
                .threshold
            # expr = " || ".join([f'role == "{r}"' for r in roles])
        )

        print(retrieval_records)

        # 3. rerank the retrieval results
        reranked_results = await self._reranker.run(
            query=input_query,
            texts=[r['content'] for r in retrieval_records],
            top_k=self \
                .bot_config['reranking'] \
                .top_k,
            threshold=self \
                .bot_config['reranking'] \
                .threshold,
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

        response_text = ""
        async for text in self._stream_llm_response(
            messages=[{"role": "user", "content": _prompt}],
            check_stream=False  # gom chuỗi
        ):
            response_text = text  # chỉ có 1 yield cuối cùng

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

    @observe(name="BeeKTData")
    async def run(
            self,
            messages: List[Dict],
            role_ids: List[str] = ["L1"],
            topic: str = "default",
            **kwargs
    ) -> AsyncStream[ChatCompletionChunk]:  # type: ignore
        langfuse_context.update_current_trace(name="BeeKTData")
        # 1. process input query
        input_query = messages[-1]["content"]

        queries_separated = await self._decompose_query(input_query)
        print("=" * 25 + "queries_separated" + "=" * 25)
        print(queries_separated)
        # chỉ phản hồi nếu có 1 câu hỏi
        if len(queries_separated) == 1:
            # 2. retrieval + rerank the relevant docs from db, 
            # it is also classify the relevant of documents based on threshold valid_score
            docs_relevant = []
            for ele_query in queries_separated:
                tmp_docs_relevant = await self._retrieval_and_rerank(
                    input_query=ele_query,
                    role_ids=role_ids,
                    topic=topic,
                    valid_score=0.7
                )
                docs_relevant.extend(tmp_docs_relevant["docs"])

            # 3. If not docs, return default answer
            if not docs_relevant:
                default_answers = 'Kính gửi Anh/chị \nHiện tại yêu cầu tư vấn/hướng dẫn của anh/chị chưa được hỗ trợ. Anh/chị vui lòng truy cập https://dichvunoibo.mbbank.com.vn/ để gửi yêu cầu tới P.Chính sách chế độ TCKT xử lý \nTrân trọng'
                yield create_response_chunk(default_answers)
                return
            num_docs = len(docs_relevant)
            # 4. If docs is exist , process docs
            print(("=" * 25 + "_{}_docs_relevant" + "=" * 25).format(num_docs))
            print("=" * 25 + "docs_relevant" + "=" * 25)
            print(docs_relevant)
            try:
                docs_classified = {
                    "tier_1": [],
                    "tier_2": [],
                    "tier_3": [],
                    "tier_4": [],
                    "tier_5": []
                }

                mapping_type = {
                    "HN": "tier_1",
                    "LU": "tier_2",
                    "ND": "tier_3",
                    "TT": "tier_4",
                    "VBNB": "tier_5"
                }

                table_docs = get_docs_info(source="./data_map_KT/van_ban_tra_cuu_v1_2.xlsx", sheet_name="Sheet1")
                
                print("=" * 25 + "table_docs" + "=" * 25)
                print(table_docs)

                for doc in docs_relevant:
                    info_docs = self._doc_store._find_docs_with_botid(
                        doc["doc"],
                        self.bot_id
                    )

                    print("=" * 25 + "info_docs" + "=" * 25)
                    print(info_docs)
                
                    doc_name = info_docs[0]["doc_name"].split(".")[0].strip()
                    if doc_name in table_docs.keys():
                        tmp_table_doc = table_docs[doc_name]
                        type_doc = tmp_table_doc["Nhóm văn bản"]
                        doc.update(tmp_table_doc)
                        docs_classified[mapping_type[type_doc]].append(doc)

                print("=" * 25 + "docs_classified" + "=" * 25)
                print(docs_classified)

                sorted_classified = {}
                for tier, docs in docs_classified.items():
                    sorted_classified[tier] = sort_documents_by_date(docs)

                print("=" * 25 + "sorted_classified" + "=" * 25)
                print(sorted_classified)
            except Exception as e:
                LOGGER.error(f"Lỗi khi xử lý tài liệu đã truy vấn: {e}")

            # 5. create response by LLM
            try:
                docs_prompt = convert_chunks_to_prompt(sorted_classified)
                response_prompt = GET_RESPONSE_PROMPT.format(
                    query=input_query,
                    docs=docs_prompt
                )

                print("=" * 25 + "response_prompt" + "=" * 25)
                print(response_prompt)

                async for  final_response in self._stream_llm_response(
                        messages=[
                            {"role": "user", "content": response_prompt}
                        ],
                        docs=docs_relevant,
                        check_stream= True
                    ):
                    yield final_response
                # yield create_response_chunk(final_response)
                return
            except Exception as e:
                LOGGER.error(f"Lỗi khi tạo phản hồi từ LLM: {e}")
        else:
            condition_answers = 'Kính gửi Anh/chị \n Anh/chị vui lòng thực hiện tra cứu một nội dung duy nhất. \n Trận trọng'
            yield create_response_chunk(condition_answers)
            return

        default_answers = 'Kính gửi Anh/chị \nHiện tại yêu cầu tư vấn/hướng dẫn của anh/chị chưa được hỗ trợ. Anh/chị vui lòng truy cập https://dichvunoibo.mbbank.com.vn/ để gửi yêu cầu tới P.Chính sách chế độ TCKT xử lý \nTrân trọng'
        yield create_response_chunk(default_answers)


async def main():
    from beegenerate.storage import BotStore
    from beegenerate.configs import MongoConfig, MilvusConfig

    # bot_id = "b10f0d26-4d91-47f5-8cac-034b87e42c7f"
    bot_id = "71eff3f6-1fc4-48c4-8ca8-df836d26d4c5"
    bot_store = BotStore(config=MongoConfig.default())
    bot_config = bot_store.fetch_bot_details(
        bot_id=bot_id
    )

    bot = BeeKTData(
        bot_config=bot_config,
        vec_store=MilvusStorage(config=MilvusConfig.default()),
        doc_store=DocumentStore(config=MongoConfig.default()),
        bot_store=BotStore(config=MongoConfig.default()),
        bot_id=bot_id
    )

    async for chunk in bot.run(
            messages=[
                {"role": "user", "content": "Đối với dịch vụ cầm đồ thì giá tính thuế được xác định như thế nào?"},
            ],
            role_ids=["L1"],
            topic="default"
    ):
        if len(chunk.choices) > 0:
            if chunk.choices[0].delta.content is not None:
                response_text = chunk.choices[0].delta.content
                print(response_text, end="")

    # # test
    # file_path = "duong_dan/ten_file.xlsx"
    # data = get_docs_info(file_path)
    # print(json.dumps(data, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
