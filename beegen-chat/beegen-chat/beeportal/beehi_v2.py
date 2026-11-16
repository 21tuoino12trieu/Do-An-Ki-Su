from beegenerate.prompts import (
    SYSTEM_PROMPT_INTENT,
    SYSTEM_PROMPT_CHIT_CHAT,
    SYSTEM_PROMPT_VERIFY_DOCUMENT_ENHANCED,
    SYSTEM_PROMPT_NON_CHIT_CHAT,
    SYSTEM_PROMPT_REFUSE,
    SYSTEM_PROMPT_RELEVANCE_TOPIC,
    SYSTEM_PROMPT_QUERY_CLARITY
)

from beegenerate.embeddings import EmbeddingFactory
from beegenerate.prompts.happy_hub import SYSTEM_PROMPT_PARTIAL_ANSWER
from beegenerate.retrievers.vector_retriever import VectorRetriever
from beegenerate.vectordb import MilvusStorage
from beegenerate.reranks import RerankingFactory
from beegenerate.storage import (
    DocumentStore,
    BotStore
)

from beegenerate.llms.llm_executor import LLMExecutor
from functools import lru_cache
from cachetools import TTLCache
from openai import AsyncStream
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from typing import (List, Dict, TypeVar, Optional, AsyncGenerator, Any)

import time
import re
import asyncio
from pydantic import BaseModel
from datetime import datetime
from beegenerate.utils.common import transform_bot_id

from beegenerate.loggings import LOGGER
from prometheus_client import Counter, Histogram
from langfuse.decorators import observe, langfuse_context
from beegenerate.loggings.loggers import lf

# Định nghĩa kiểu dữ liệu
T = TypeVar('T', bound=BaseModel)

# Metrics
LATENCY = Histogram('bot_latency_seconds', 'Time spent processing request')
ERRORS = Counter('bot_errors_total', 'Total errors by type')
REQUESTS = Counter('bot_requests_total', 'Total requests processed')
INTENT_METRICS = Counter('bot_intent_total', 'Total intents by type', ['intent'])


class DocumentResult(BaseModel):
    docs: List[Dict]
    relevance_score: float


class BeehiBot:
    def __init__(
            self,
            bot_config: Dict,
            vec_store: MilvusStorage,
            doc_store: DocumentStore,
            bot_store: BotStore
    ):
        """Khởi tạo BeehiBot với các thành phần cần thiết"""
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
        self._reranker = RerankingFactory.create(config=bot_config['reranking'])

        # Semaphore cho rate limiting
        self._retrieval_semaphore = asyncio.Semaphore(30)
        self._llm_semaphore = asyncio.Semaphore(15)

        # Bộ nhớ đệm cho kết quả và phân tích
        self._doc_cache = TTLCache(maxsize=1000, ttl=3600)
        self._intent_cache = TTLCache(maxsize=1000, ttl=3600)

        # Log
        self.log_messages = []

    @observe(name="BeehiBot")
    async def run(self, messages: List[Dict], role_ids: List[str] = [], topic: str = "default", **kwargs) -> AsyncGenerator:
        """Luồng xử lý tối ưu hóa với xử lý một phần câu hỏi"""
        langfuse_context.update_current_trace(name="BeehiBot")
        REQUESTS.inc()
        start_time = time.time()
        query = messages[-1]['content']

        try:
            # 1. Song song hóa phân tích ý định và truy xuất tài liệu
            analysis_result = await self._analyze_query_intent_clarity(messages, query)

            # Sử dụng câu tóm tắt ý định để truy xuất tài liệu
            intent_query = analysis_result.get('query', query)
            cache_key = f"{query}_{intent_query}_{role_ids[-1]}_{topic}"

            # Truy xuất tài liệu với đánh giá chi tiết
            doc_result = await self._get_documents_enhanced(
                query=query,
                intent_query=intent_query,
                role_ids=role_ids,
                topic=topic,
                cache_key=cache_key
            )

            # 2. Xử lý logic phản hồi
            if analysis_result['intent'] == "is_simple_chit_chat":
                # Xử lý trò chuyện đơn giản
                prompt_system = SYSTEM_PROMPT_CHIT_CHAT.format(
                    documents="",
                    greeting=analysis_result['greeting']
                )
            else:
                # Xử lý câu hỏi cần tài liệu
                if doc_result['docs'] and doc_result['relevance_score'] > self.bot_config.get('threshold', {}).get(
                        'doc_relevance', 0.01):
                    # Kiểm tra mức độ trả lời được
                    if doc_result['fully_answered'] and analysis_result['clarity_level'] == "complete":
                        # Kiểm tra thông tin thời gian nếu cần
                        has_time_info = True
                        if re.findall(r'\b(202\d|203\d)\b', query):
                            has_time_info = await self._check_temporal_relevance(query, doc_result['docs'])
                            LOGGER.info(f"Kết quả kiểm tra thông tin thời gian: {has_time_info}")

                        if has_time_info:
                            # Câu hỏi rõ ràng, có tài liệu liên quan với thông tin thời gian đầy đủ
                            prompt_system = SYSTEM_PROMPT_NON_CHIT_CHAT.format(
                                date=datetime.now().strftime('%Y-%m-%d'),
                                documents=self._format_documents(doc_result['docs']),
                                greeting=analysis_result['greeting']
                            )
                        else:
                            # Tài liệu không chứa thông tin thời gian cần thiết
                            prompt_system = SYSTEM_PROMPT_REFUSE

                    elif doc_result['partially_answered']:
                        # Trường hợp trả lời một phần
                        prompt_system = SYSTEM_PROMPT_PARTIAL_ANSWER.format(
                            date=datetime.now().strftime('%Y-%m-%d'),
                            documents=self._format_documents(doc_result['docs']),
                            greeting=analysis_result['greeting'],
                            answered_info=doc_result['answered_info'],
                            missing_info=doc_result['missing_info']
                        )

                    elif analysis_result['clarity_level'] != "complete":
                        # Câu hỏi không rõ ràng nhưng có tài liệu liên quan
                        clarification = await self._generate_clarification_prompt(
                            query,
                            DocumentResult(docs=doc_result['docs'], relevance_score=doc_result['relevance_score'])
                        )
                        prompt_system = f"""
                            Vai trò: Bạn là Bee Hi - trợ lý ảo thông minh của ngân hàng MB
                            Đưa ra nguyên văn câu trả lời sau:
                            {clarification}
                        """
                    else:
                        # Không đủ thông tin để trả lời
                        prompt_system = SYSTEM_PROMPT_REFUSE
                else:
                    # Không có tài liệu liên quan
                    prompt_system = SYSTEM_PROMPT_REFUSE

            # 3. Tạo và trả về câu trả lời
            response_messages = [
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": query}
            ]

            # 4. Stream câu trả lời
            async with self._llm_semaphore:
                buffer = []
                async for chunk in self._llm.run(
                        messages=response_messages,
                        docs=self._create_attached_docs(doc_result['docs']),
                        sleep=0.0001
                ):
                    buffer.append(chunk)
                    if len(buffer) >= 50:
                        for buffered_chunk in buffer:
                            yield buffered_chunk
                        buffer.clear()

                # Trả về các chunk còn lại
                for chunk in buffer:
                    yield chunk

            # Ghi nhận metrics
            LATENCY.observe(time.time() - start_time)

        except Exception as e:
            ERRORS.inc()
            LOGGER.error(f"Lỗi trong quá trình xử lý: {str(e)}")
            langfuse_context.update_current_observation(level="ERROR", output=str(e))

            # Tạo một phản hồi lỗi
            error_message = {"role": "system", "content": "Đã xảy ra lỗi khi xử lý yêu cầu. Vui lòng thử lại sau."}
            async with self._llm_semaphore:
                async for chunk in self._llm.run(
                        messages=[error_message, {"role": "user", "content": "lỗi"}],
                        sleep=0.0001
                ):
                    yield chunk

    @observe()
    async def _get_documents_enhanced(
            self, query: str,
            intent_query: str,
            role_ids: List[str],
            topic: str,
            cache_key: Optional[str] = None) -> Dict:
        """Truy xuất và xác minh tài liệu liên quan với đánh giá chi tiết"""
        # Kiểm tra cache
        if cache_key and cache_key in self._doc_cache:
            return self._doc_cache[cache_key]

        async with self._retrieval_semaphore:
            # Truy xuất tài liệu dựa trên câu tóm tắt intent
            retrieval_records = await self._retriever.run(
                query=intent_query or query,  # Ưu tiên câu tóm tắt intent nếu có
                bot_id=self.bot_config['id'],
                collection=f"bot_{transform_bot_id(self.bot_config['id'])}",
                allowed_roles=role_ids,
                top_k=self.bot_config['retrieval'].top_k,
                threshold=self.bot_config['retrieval'].threshold,
            )

            # Nếu không có kết quả, trả về trống
            if not retrieval_records:
                result = {
                    "docs": [],
                    "relevance_score": 0.0,
                    "fully_answered": False,
                    "partially_answered": False,
                    "answered_info": "",
                    "missing_info": ""
                }
                if cache_key:
                    self._doc_cache[cache_key] = result
                return result

            # Reranking
            reranked_results = await self._reranker.run(
                query=query,
                texts=[r['content'] for r in retrieval_records],
                top_k=self.bot_config['reranking'].top_k,
                threshold=self.bot_config['reranking'].threshold,
            )

            # Chuẩn bị tài liệu cho xác minh
            documents_to_verify = []
            for r in reranked_results:
                record = retrieval_records[r['index']]
                record['score'] = r['score']
                documents_to_verify.append(record)

            # Nếu không có tài liệu để xác minh, trả về trống
            if not documents_to_verify:
                result = {
                    "docs": [],
                    "relevance_score": 0.0,
                    "fully_answered": False,
                    "partially_answered": False,
                    "answered_info": "",
                    "missing_info": ""
                }
                if cache_key:
                    self._doc_cache[cache_key] = result
                return result

            # Xác minh tất cả tài liệu cùng lúc với đánh giá chi tiết
            verification_results = await self._verify_documents_batch_enhanced(
                query=query,
                intent_query=intent_query or query,
                documents=documents_to_verify
            )

            # Xử lý kết quả xác minh
            final_docs = []
            max_score = 0
            fully_answered = False
            partially_answered = False
            answered_info = ""
            missing_info = ""

            for idx, result in enumerate(verification_results):
                if result["relevant"]:
                    record = documents_to_verify[idx]
                    record.update({
                        "fully_answered": result["fully_answered"],
                        "partially_answered": result["partially_answered"],
                        "answered_info": result["answered_info"],
                        "missing_info": result["missing_info"]
                    })
                    final_docs.append(record)
                    max_score = max(max_score, record['score'])

                    # Cập nhật trạng thái trả lời
                    if result["fully_answered"]:
                        fully_answered = True
                        answered_info = result["answered_info"]
                    elif result["partially_answered"] and not fully_answered:
                        partially_answered = True
                        answered_info = result["answered_info"]
                        missing_info = result["missing_info"]

            result = {
                "docs": final_docs,
                "relevance_score": max_score,
                "fully_answered": fully_answered,
                "partially_answered": partially_answered,
                "answered_info": answered_info,
                "missing_info": missing_info
            }

            # Lưu cache
            if cache_key:
                self._doc_cache[cache_key] = result

            return result

    @observe()
    async def _verify_documents_batch_enhanced(
            self,
            query: str,
            intent_query: str,
            documents: List[Dict]) -> List[Dict]:
        """Xác minh nhiều tài liệu trong một lần gọi LLM với đánh giá chi tiết hơn"""
        if not documents:
            return []

        # Format tất cả tài liệu thành một tin nhắn
        verification_prompt = SYSTEM_PROMPT_VERIFY_DOCUMENT_ENHANCED
        formatted_docs = []
        for idx, doc in enumerate(documents, 1):
            formatted_docs.append(f"Document {idx}:\n{doc['content']}")

        all_docs = "\n\n".join(formatted_docs)

        # Tạo một tin nhắn xác minh với cả câu hỏi gốc và câu tóm tắt ý định
        messages = [
            {"role": "system", "content": verification_prompt},
            {"role": "user",
             "content": f"Câu hỏi gốc: {query}\nCâu tóm tắt ý định: {intent_query}\n\nTài liệu để đánh giá:\n{all_docs}\n\n" +
                        "Yêu cầu: Đánh giá từng tài liệu và trả về kết quả theo định dạng "
                        "<output>doc1:tra_loi_day_du/tra_loi_mot_phan/khong_lien_quan|doc2:tra_loi_day_du"
                        "/tra_loi_mot_phan/khong_lien_quan|...</output>"}
        ]

        response_text = await self._stream_llm_response(messages)

        # Trích xuất kết quả xác minh cơ bản
        match_output = re.search(r'<output>(.*?)</output>', response_text)
        match_answered = re.search(r'<answered_info>(.*?)</answered_info>', response_text)
        match_missing = re.search(r'<missing_info>(.*?)</missing_info>', response_text)

        if not match_output:
            return [{"relevant": False, "answered_info": "", "missing_info": ""} for _ in documents]

        results = match_output.group(1).strip().split('|')

        # Tạo danh sách kết quả chi tiết
        detailed_results = []
        for idx, result in enumerate(results):
            doc_result = {
                "relevant": False,
                "fully_answered": False,
                "partially_answered": False,
                "answered_info": match_answered.group(1).strip() if match_answered else "",
                "missing_info": match_missing.group(1).strip() if match_missing else ""
            }

            status = result.split(':')[1].strip()
            if status == "tra_loi_day_du":
                doc_result["relevant"] = True
                doc_result["fully_answered"] = True
            elif status == "tra_loi_mot_phan":
                doc_result["relevant"] = True
                doc_result["partially_answered"] = True

            detailed_results.append(doc_result)

        return detailed_results

    @observe()
    async def _analyze_query_intent_clarity(self, messages: List[Dict], query: str) -> Dict:
        """Phân tích ý định và độ rõ ràng của câu hỏi trong một lần gọi LLM"""
        # Tạo key cache
        cache_key = f"analysis_{query}"
        if cache_key in self._intent_cache:
            return self._intent_cache[cache_key]

        # Format lịch sử hội thoại
        history = []
        message_pairs = []
        current_pair = []

        for msg in messages[:-1][::-1]:
            current_pair.append(msg)
            if len(current_pair) == 2:
                message_pairs.append(current_pair)
                current_pair = []
            if len(message_pairs) == 4:
                break

        # Đảo ngược cặp và làm phẳng
        for pair in reversed(message_pairs):
            history.extend(pair)

        # Thêm bất kỳ tin nhắn đơn nào còn lại
        if current_pair:
            history.extend(reversed(current_pair))

        # Format lịch sử hội thoại
        formatted_history = [
            f"{'Người dùng' if m['role'] == 'user' else 'BOT'}: {m['content']}"
            for m in history
        ]

        # Tạo prompt kết hợp để phân tích
        system_prompt = f"""
        # Phần 1: Phân tích ý định
        {SYSTEM_PROMPT_INTENT.format(conversation=formatted_history, documents="", relevance_score=0)}

        # Phần 2: Phân tích độ rõ ràng
        {SYSTEM_PROMPT_QUERY_CLARITY}

        # Định dạng kết quả
        <query>câu tóm tắt ý định của tin nhắn mới</query>
        <intent>nhóm được phân loại</intent>
        <greeting>chatbot đã chào hỏi người dùng chưa</greeting>
        <clarity>nhãn độ rõ ràng</clarity>
        """

        response_text = await self._stream_llm_response(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Tin nhắn mới: '{query}'"}
            ]
        )

        # Phân tích kết quả với xử lý lỗi
        try:
            new_query = re.findall(r'<query>(.*?)</query>', response_text)[0]
            intent = re.findall(r'<intent>(.*?)</intent>', response_text)[0]
            greeting = re.findall(r'<greeting>(.*?)</greeting>', response_text)[0].lower() == 'true'
            clarity = re.findall(r'<clarity>(.*?)</clarity>', response_text)[0]

            result = {
                "query": new_query,
                "intent": intent,
                "greeting": greeting,
                "clarity_level": clarity,
            }
        except (IndexError, Exception) as e:
            LOGGER.error(f"Lỗi khi phân tích kết quả LLM: {str(e)}")
            # Giá trị mặc định an toàn
            result = {
                "query": query,
                "intent": "require_document",
                "greeting": False,
                "clarity_level": "unclear",
            }

        # Lưu cache
        self._intent_cache[cache_key] = result

        return result

    @observe()
    async def _check_temporal_relevance(self, query: str, documents: List[Dict]) -> bool:
        """Kiểm tra thông tin thời gian trong tài liệu"""
        if not documents:
            return False

        # Tìm năm trong câu hỏi
        year_match = re.findall(r'\b(202\d|203\d)\b', query)
        if not year_match:
            return True  # Không cần kiểm tra thời gian

        year_in_query = year_match[0]
        docs_text = self._format_documents(documents)

        prompt = f"""
        Vai trò: Chuyên gia phân tích thông tin thời gian

        Nhiệm vụ: Kiểm tra xem tài liệu có chứa thông tin về năm {year_in_query} không.

        Tài liệu:
        {docs_text}

        Yêu cầu: Chỉ trả lời "co_thong_tin" hoặc "khong_co_thong_tin"
        """

        response = await self._stream_llm_response([
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Câu hỏi: {query}"}
        ])

        return "co_thong_tin" in response.lower()

    @observe()
    async def _generate_clarification_prompt(self, query: str, doc_result: DocumentResult) -> str:
        """Tạo gợi ý làm rõ bằng cách phân tích tài liệu và đề xuất chủ đề"""
        try:
            # Phân tích tài liệu để trích xuất chủ đề chính
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT_RELEVANCE_TOPIC},
                {"role": "user",
                 "content": f"Câu hỏi: {query}\nTài liệu cung cấp: {self._format_documents(doc_result.docs)}"}
            ]

            # Lấy chủ đề từ LLM
            response = await self._stream_llm_response(messages)
            match = re.search(r'<topics>(.*?)</topics>', response)
            topics = match.group(1).split('|') if match else []

            # Format chủ đề thành câu hỏi
            if topics:
                topics_text = ", ".join(topics[:-1])
                if len(topics) > 1:
                    topics_text += f" hoặc {topics[-1]}"
                else:
                    topics_text = topics[0]

                return f"Bạn có thể chia sẻ rõ hơn về nhu cầu của mình được không? 🤔\nBạn muốn tìm hiểu thông tin về một trong những chủ đề sau: {topics_text} đúng không?"

            # Fallback nếu không có chủ đề
            return "Bạn có thể chia sẻ rõ hơn về nhu cầu của mình được không? 🤔"
        except Exception as e:
            LOGGER.error(f"Lỗi khi tạo gợi ý làm rõ: {str(e)}")
            return "Bạn có thể chia sẻ rõ hơn về nhu cầu của mình được không? 🤔"

    @observe()
    async def _stream_llm_response(self, messages: List[Dict]) -> str:
        """Stream phản hồi từ LLM và nối các chunk thành một chuỗi duy nhất"""
        try:
            response_text = ""
            async for chunk in self._llm.run(messages=messages):
                if chunk.choices and chunk.choices[0].delta.content:
                    response_text += chunk.choices[0].delta.content
            return response_text
        except Exception as e:
            LOGGER.error(f"Lỗi khi stream LLM response: {e}")
            langfuse_context.update_current_observation(level="ERROR", output=str(e))
            raise RuntimeError(f"Không thể lấy phản hồi LLM: {str(e)}")

    @observe()
    def _format_documents(self, documents: List[Dict]) -> str:
        """Format danh sách tài liệu thành một chuỗi với dấu phân cách"""
        return "\n-----------------------------\n".join(
            [d['content'] for d in documents]
        )

    @observe()
    def _create_attached_docs(self, documents: List[Dict]) -> List[Dict]:
        """Tạo metadata cho tài liệu để đính kèm vào yêu cầu LLM"""
        attached_docs = []
        for doc in documents:
            chunk_info = {"id": doc['id']}
            if 'doc' in doc:
                chunk_info['source'] = doc['doc']
            attached_docs.append(chunk_info)
        return attached_docs

    async def shutdown(self):
        """Dọn dẹp tài nguyên khi tắt"""
        try:
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            [task.cancel() for task in tasks]
            await asyncio.gather(*tasks, return_exceptions=True)
            self._doc_cache.clear()
            self._intent_cache.clear()
        except Exception as e:
            LOGGER.error(f"Lỗi khi shutdown: {str(e)}")


async def main():
    from beegenerate.configs import MongoConfig, MilvusConfig

    """Ví dụ sử dụng BeehiBot"""
    bot_id = "b10f0d26-4d91-47f5-8cac-034b87e42c7f"
    bot_store = BotStore(config=MongoConfig.default())
    bot_config = bot_store.fetch_bot_details(bot_id=bot_id)

    bot = BeehiBot(
        bot_config=bot_config,
        vec_store=MilvusStorage(config=MilvusConfig.default()),
        doc_store=DocumentStore(config=MongoConfig.default()),
        bot_store=bot_store
    )

    try:
        response_text = ""
        async for chunk in bot.run(
                messages=[
                    {"role": "user", "content": "chấm dứt hợp đồng lao động như thế nào"}
                ],
                role_ids=["L1"]
        ):

            if chunk.choices and chunk.choices[0].delta.content:
                response_text += chunk.choices[0].delta.content

        LOGGER.info(f"{response_text}")

    finally:
        await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
