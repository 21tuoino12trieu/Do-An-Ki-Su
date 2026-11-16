from beegenerate.prompts.botPC import (
    CREATE_QS_INTENT,
    QA_FILTER_PROMPT
)

from beegenerate.retrievers.vector_retriever import VectorRetriever
from beegenerate.vectordb import MilvusStorage
from beegenerate.reranks import RerankingFactory
from beegenerate.storage import (
    DocumentStore,
    BotStore
)
from beegenerate.storage.mongo.document_store_PC import StorePC
from beegenerate.configs import MongoConfig

from beegenerate.llms.llm_executor import LLMExecutor

from typing import List, Dict, Optional, AsyncGenerator

import time
import asyncio
from pydantic import BaseModel
from datetime import datetime
from beegenerate.utils.common import transform_bot_id

from beegenerate.loggings import LOGGER
from prometheus_client import Counter, Histogram

from beegenerate.loggings.loggers import lf
from langfuse.decorators import langfuse_context, observe

# Metrics
LATENCY = Histogram('bot_latency_seconds_v2', 'Time spent processing request_v2')
REQUESTS = Counter('bot_requests_total_v2', 'Total requests processed v2')
import uuid
import re
from beegenerate.llms.llm_response import fake_chunk_from


def create_response_chunk(answer: str, **kwargs):
    return fake_chunk_from(
        content=answer,
        model="cached",
        chat_id=f"chat-{uuid.uuid4()}",
        current_time=0,
        last=False,
        **kwargs
    )


class DocumentResult(BaseModel):
    docs: List[Dict]
    relevance_score: float


class BeePC:
    def __init__(
            self,
            bot_config: Dict,
            vec_store: MilvusStorage,
            doc_store: DocumentStore,
            bot_store: BotStore
    ):
        """Initialize BeePC with required components and configurations."""
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

        # Semaphores for rate limiting
        self._retrieval_semaphore = asyncio.Semaphore(20)
        self._llm_semaphore = asyncio.Semaphore(10)

        # Set relevance threshold
        self.relevance_threshold = self.bot_config.get('threshold', {}).get('doc_relevance', 0.9)

    @observe()
    def _format_documents(self, documents: List[Dict]) -> str:
        """Format a list of documents into a single string with separators."""
        return "\n-----------------------------\n".join(
            [d['content'] for d in documents]
        )

    @observe()
    def _create_attached_docs(self, documents: List[Dict]) -> List[Dict]:
        """Create metadata for documents to be attached to LLM requests."""
        attached_docs = []
        for doc in documents:
            chunk_info = {"id": doc['id']}
            if 'doc' in doc:
                chunk_info['source'] = doc['doc']
            attached_docs.append(chunk_info)
        return attached_docs

    @observe()
    def extract_questions_from_docs(self, doc_result_docs, user_query):
        """Trích xuất câu hỏi từ các tài liệu và tạo response button"""
        questions = []

        for doc in doc_result_docs[:4]:  # Chỉ lấy 4 tài liệu đầu
            content = doc['content']
            # Sử dụng regex để trích xuất câu hỏi
            question_match = re.search(r'Câu hỏi:\s*(.*?)(?=\nCâu trả lời:|$)', content, re.DOTALL)
            if question_match:
                question = question_match.group(1).strip()
                questions.append(question)

        # Tạo response với format button
        if questions:
            response = f'''Xin chào! Hiện tại, câu hỏi "{user_query}" của bạn đang chưa có sẵn trong hệ thống Q&A. Tôi đang tìm thấy các câu hỏi tương tự như sau trong Q&A. Bạn quan tâm đến câu hỏi nào?\n\n'''

            for i, question in enumerate(questions, 1):
                response += f"<button: {question}>\n"

            response += "\nVui lòng chọn một câu hỏi để tôi có thể hỗ trợ bạn tốt nhất."
            return response

        return None

    @observe()
    async def _get_relevant_documents(
            self,
            query: str,
            role_ids: List[str],
            topic: str
    ) -> DocumentResult:
        """Retrieve and rank relevant documents."""
        async with self._retrieval_semaphore:
            # Initial retrieval
            retrieval_records = await self._retriever.run(
                query=query,
                bot_id=self.bot_config['id'],
                collection=f"bot_{transform_bot_id(self.bot_config['id'])}",
                allowed_roles=role_ids,
                top_k=self.bot_config['retrieval'].top_k,
                threshold=self.bot_config['retrieval'].threshold,
                partition_names=["QA"]  # Chỉ lấy từ partition QA
            )

            # Reranking
            reranked_results = await self._reranker.run(
                query=query,
                texts=[r['content'] for r in retrieval_records],
                top_k=self.bot_config['reranking'].top_k,
                threshold=self.bot_config['reranking'].threshold,
            )

            # Process reranked results
            final_docs = []
            max_score = 0

            for r in reranked_results:
                record = retrieval_records[r['index']]
                record['score'] = r['score']
                final_docs.append(record)
                max_score = max(max_score, r['score'])

            return DocumentResult(
                docs=final_docs,
                relevance_score=max_score
            )

    @observe()
    def _create_questions_prompt(self, docs: List[Dict], query: str) -> List[Dict]:
        """Create prompt to extract questions from top documents."""
        top_docs = docs[:4]  # Ensure we only use top 4 docs
        docs_content = "\n\n".join([f"Tài liệu {i + 1}:\n{doc['content']}" for i, doc in enumerate(top_docs)])

        user_prompt = f"""Câu hỏi của người dùng: {query}

            Các tài liệu:
            {docs_content}

            Hãy phân tích các tài liệu trên và trích xuất câu hỏi chính mà mỗi tài liệu có thể trả lời."""

        return [
            {"role": "system", "content": CREATE_QS_INTENT.format(question=query)},
            {"role": "user", "content": user_prompt}
        ]

    @observe()
    async def _stream_direct_response(self, content: str, sleep_time: float = 0.0001):
        """Stream direct response content without using LLM."""
        # Chia nội dung thành các phần nhỏ để stream
        for i in range(0, len(content), 5):
            chunk_text = content[i:i + 5]
            # Giả lập cấu trúc response như LLM.run
            response = {"choices": [{"delta": {"content": chunk_text}}]}
            yield response
            await asyncio.sleep(sleep_time)

    @observe(name="BeePC")
    async def run(
            self,
            messages: List[Dict],
            role_ids: List[str] = [],
            topic: str = "default",
            **kwargs
    ) -> AsyncGenerator:
        """Main pipeline with simplified logic flow."""
        langfuse_context.update_current_trace(name="BeePC")
        REQUESTS.inc()
        start_time = time.time()

        # 1. Get query from last message
        query = messages[-1]['content']

        # 2. Get relevant documents
        doc_result = await self._get_relevant_documents(
            query=query,
            role_ids=role_ids,
            topic=topic
        )
        # 3. Check document relevance against threshold
        async with self._llm_semaphore:

            # 1. Chuẩn bị tài liệu từ kết quả truy xuất
            doc_result_docs = doc_result.docs  # Các tài liệu đã được sắp xếp theo điểm tương đồng

            # 2. Trích xuất câu hỏi từ tất cả các tài liệu
            questions_map = {}  # Sử dụng map để tránh trùng lặp

            for doc in doc_result_docs:
                # Trích xuất câu hỏi từ nội dung tài liệu
                content = doc['content']
                question_match = re.search(r'Câu hỏi:(.*?)(\nCâu trả lời:|$)', content)
                if question_match:
                    question = question_match.group(1).strip()
                    questions_map[question] = {
                        'doc': doc
                    }

            # 3. Chuyển map thành danh sách để sử dụng trong prompt
            questions_with_docs = [
                {'question': q, 'doc': info['doc']}
                for q, info in questions_map.items()
            ]
            # 4. Tạo prompt để so sánh tất cả các câu hỏi cùng một lúc
            all_questions = "\n".join([
                f"Câu hỏi {i + 1}: {q['question']}"
                for i, q in enumerate(questions_with_docs)
            ])
            # 6. Sử dụng LLM để tìm câu hỏi khớp nhất
            user_query = query  # Câu hỏi ban đầu của người dùng

            messages_input = [
                {'role': 'user',
                 'content': QA_FILTER_PROMPT.format(
                     document=all_questions,
                     question=user_query
                 )}
            ]

            # 7. Gửi prompt và lấy phản hồi
            response = ""
            matched_doc = None

            try:
                async for chunk in self._llm.run(
                        messages=messages_input,
                        sleep=0.0001
                ):
                    if chunk.choices and chunk.choices[0].delta.content:
                        response += chunk.choices[0].delta.content

                # 8. Trích xuất kết quả từ phản hồi
                match = re.search(r'<result>(.*?)</result>', response)

                if match and match.group(1).strip() and match.group(1).strip().isdigit():
                    index = int(match.group(1).strip()) - 1
                    if 0 <= index < len(questions_with_docs):
                        matched_doc = questions_with_docs[index]['doc']
            except Exception as e:
                LOGGER.error(f"Lỗi khi chạy LLM để so khớp câu hỏi: {e}")

            # 9. Trả về câu trả lời dựa trên kết quả so khớp
            if matched_doc:

                doc_store = StorePC(config=MongoConfig.default())
                doc_content = doc_store.find_document_chunks(
                    chunk_ids=[matched_doc['doc']]
                )

                if doc_content and 'answer' in doc_content[0]:
                    answer = doc_content[0]['answer']

                    doc_id = [
                        {'id': matched_doc['doc'],
                         'source': matched_doc['doc']}
                    ]
                    yield create_response_chunk(answer, docs=doc_id)

            else:
                # Nếu không tìm thấy câu hỏi khớp, quay lại luồng tạo câu hỏi (luồng if trước đó)
                LOGGER.info("Không tìm thấy câu hỏi khớp, chuyển sang luồng đề xuất câu hỏi")

                # Trích xuất câu hỏi trực tiếp từ text
                questions = []
                for doc in doc_result_docs[:4]:  # Chỉ lấy 4 tài liệu đầu
                    content = doc['content']
                    question_match = re.search(r'Câu hỏi:\s*(.*?)(?=\nCâu trả lời:|$)', content, re.DOTALL)
                    if question_match:
                        question = question_match.group(1).strip()
                        questions.append(question)

                # Tạo response với format button
                if questions:
                    response_text = f'''Xin chào! Hiện tại, câu hỏi "{query}" của bạn đang chưa có sẵn trong hệ thống Q&A. Tôi đang tìm thấy các câu hỏi tương tự như sau trong Q&A. Bạn quan tâm đến câu hỏi nào?\n\n'''

                    for i, question in enumerate(questions, 1):
                        response_text += f"<button: {question}>\n"

                    response_text += "\nVui lòng chọn một câu hỏi để tôi có thể hỗ trợ bạn tốt nhất."

                    # Lấy tất cả doc_id từ các tài liệu
                    doc_id = [
                        {'id': doc['id'],
                         'source': doc.get('doc', doc['id'])}
                        for doc in doc_result_docs
                    ]
                    print(doc_id)
                    print("=" * 50)
                    # Trả về response với docs
                    yield create_response_chunk(response_text, docs=doc_id)

                else:
                    # Fallback nếu không trích xuất được câu hỏi
                    fallback_text = "Xin lỗi, tôi không tìm thấy câu hỏi phù hợp trong hệ thống."
                    doc_id = [
                        {'id': doc['id'],
                         'source': doc.get('doc', doc['id'])}
                        for doc in doc_result_docs
                    ]
                    yield create_response_chunk(fallback_text, docs=doc_id)

        # Record metrics
        LATENCY.observe(time.time() - start_time)

    async def shutdown(self):
        """Cleanup resources during shutdown."""
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        [task.cancel() for task in tasks]
        await asyncio.gather(*tasks, return_exceptions=True)


async def main():
    from beegenerate.configs import MongoConfig, MilvusConfig

    """Example usage of BeePC."""
    bot_id = "31b323e9-9946-4e9f-bc4c-84762bae2303"
    bot_store = BotStore(config=MongoConfig.default())
    bot_config = bot_store.fetch_bot_details(bot_id=bot_id)

    bot = BeePC(
        bot_config=bot_config,
        vec_store=MilvusStorage(config=MilvusConfig.default()),
        doc_store=DocumentStore(config=MongoConfig.default()),
        bot_store=bot_store
    )

    response_text = ""
    async for chunk in bot.run(
            messages=[
                {"role": "user",
                 "content": "làm nào để biết là khách hàng cá nhân"}
            ],
            role_ids=["L1"],
            topic="QA"
    ):
        if chunk.choices and chunk.choices[0].delta.content:
            response_text += chunk.choices[0].delta.content

    LOGGER.info(f"{response_text}")
    await bot.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
