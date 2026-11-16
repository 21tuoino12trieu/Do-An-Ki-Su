import asyncio
import traceback
import httpx
from typing import List, Dict, Any

from beechat.config import load_settings
from beechat.utils.pyinstrument_profiler import profile_async_func
from beegenerate.loggings import LOGGER
from langfuse.decorators import observe, langfuse_context


@observe()
@profile_async_func("Vertex AI KB Search - search_kb_engine")
async def search_kb_engine(
        query: str,
        page_size: int = 5,
        max_extractive_segment_count: int = 3,
        threshold: float = 0.5,
        **kwargs
) -> Dict[str, Any]:
    """
    Tìm kiếm tài liệu duy nhất từ Knowledge Base Engine thông qua endpoint hợp nhất trên Vertex AI.
    Cấu hình tối ưu qua Grid Search: relevanceThreshold="LOW", Python threshold=0.5.
    """
    logger = LOGGER
    logger.info(f"Thực hiện tìm kiếm Knowledge Base qua LiteLLM gateway... | Query: '{query}'")
    langfuse_context.update_current_observation(input={"query": query, "page_size": page_size, "threshold": threshold})

    settings = load_settings()
    PROJECT_NUMBER = settings.kb_vector_prj_number
    ENGINE_ID = getattr(settings, "kb_engine_id", settings.kb_vector_engine_id)
    API_VERSION = settings.kb_api_version
    base_url = settings.openai_base_url.rstrip('/')

    headers = {
        "x-litellm-api-key": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
        "X-Vertex-AI-LLM-Request-Type": "shared",
        "X-Vertex-AI-LLM-Shared-Request-Type": "priority"
    }

    kb_url = (
        f"{base_url}/vertex_ai/discovery/{API_VERSION}/projects/{PROJECT_NUMBER}"
        f"/locations/global/collections/default_collection"
        f"/engines/{ENGINE_ID}/servingConfigs/default_search:search"
    )

    kb_payload = {
        "query": query,
        "pageSize": page_size,
        "relevanceThreshold": "LOW",
        "spellCorrectionSpec": {"mode": "AUTO"},
        "languageCode": "vi",
        "contentSearchSpec": {
            "extractiveContentSpec": {
                "maxExtractiveSegmentCount": max_extractive_segment_count,
                "returnExtractiveSegmentScore": True,
                "numPreviousSegments": 1,
                "numNextSegments": 1,
            },
            "snippetSpec": {"returnSnippet": False}
        }
    }


    try:
        async with httpx.AsyncClient(verify=False, timeout=10.0, trust_env=False) as client:
            resp = await client.post(kb_url, headers=headers, json=kb_payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"[KB Search Error]: {e}")
        return {"results": [], "summary": {}}


@observe()
@profile_async_func("Vertex AI Search - core_search_banking_knowledge")
async def core_search_banking_knowledge(
        query: str,
        page_size: int = 5,
        max_extractive_segment_count: int = 3,
        threshold: float = 0.5,
        qna_docs: list = None,
        **kwargs
) -> str:
    """
    Hàm tìm kiếm Knowledge Base và định dạng lại tài liệu (kết hợp các QnA reference nếu có).
    """
    kb_data = await search_kb_engine(
        query=query,
        page_size=page_size,
        max_extractive_segment_count=max_extractive_segment_count,
        threshold=threshold
    )
    kb_result_text = await _format_response_vertex(kb_data, threshold=threshold, qna_docs=qna_docs)
    return f"[Knowledge Base]:\n{kb_result_text}"


async def _format_response_vertex(response: Dict[str, Any], threshold: float = 0.5, qna_docs: list = None) -> str:

    """
    Định dạng lại phản hồi từ Vertex AI Search (Knowledge Base), kết hợp các tài liệu QnA đạt điểm [0.4, 0.8).
    """
    logger = LOGGER
    output = []

    summary = response.get("summary", {})
    if summary_text := summary.get("summaryText"):
        output.append(f"[Thông tin tóm tắt từ dữ liệu]:\n{summary_text}\n")

    results = response.get("results", [])
    parsed_docs = []

    # 1. Parse các tài liệu từ Knowledge Base RAG (lọc bỏ các bản ghi thuần QnA)
    for doc_idx, item in enumerate(results):
        doc = item.get("document", {})
        struct = doc.get("structData", {})
        doc_id = doc.get("id", "")
        
        # Bỏ qua tài liệu dạng QnA vì QnA đã được xử lý bởi QAService
        is_qna = bool(struct.get("Question") or struct.get("question") or
                      struct.get("Answer") or struct.get("answer") or
                      doc_id.startswith("qa-"))
        if is_qna:
            continue

        derived = doc.get("derivedStructData", {})
        title = derived.get("title") or struct.get("title") or struct.get("doc_name") or "No Title"
        link = derived.get("link", "No Link")
        segments = derived.get("extractive_segments", [])

        doc_segments = []
        for seg in segments:
            score = seg.get("relevanceScore", 1.0)
            if score >= threshold:
                content = seg.get("content", "").replace("\n", " ").strip()
                if content:
                    doc_segments.append((score, content))

        # Fallback về snippets nếu không có extractive_segments
        if not doc_segments:
            snippets = derived.get("snippets", [])
            model_scores = item.get("modelScores", {})
            model_rel_score = model_scores.get("relevance_score", {}).get("values", [1.0])[0]
            if model_rel_score >= threshold:
                for snip in snippets:
                    snip_text = snip.get("snippet", "").replace("<b>", "").replace("</b>", "").replace("\n", " ").strip()
                    if snip_text:
                        doc_segments.append((model_rel_score, snip_text))

        if doc_segments:
            doc_segments.sort(key=lambda x: x[0], reverse=True)
            doc_segments = doc_segments[:3]  # Giới hạn Top 3 segments per document
            parsed_docs.append({
                "title": title,
                "link": link,
                "segments": doc_segments,
                "max_score": doc_segments[0][0]
            })

    # 2. Bổ sung các tài liệu QnA đạt điểm từ 0.4 đến 0.8 (nếu có)
    if qna_docs:
        for qdoc in qna_docs:
            parsed_docs.append({
                "title": qdoc.get("title", "QnA Reference"),
                "link": qdoc.get("link", "QnA Database"),
                "segments": [(qdoc.get("score", 0.6), qdoc.get("content", ""))],
                "max_score": qdoc.get("score", 0.6)
            })

    if not parsed_docs:
        logger.info(f"Tất cả kết quả đều dưới ngưỡng {threshold}.")
        output.append("Tất cả kết quả tìm kiếm đều dưới ngưỡng liên quan. Không có tài liệu phù hợp.")
        return "\n".join(output)

    # 3. Sắp xếp toàn bộ tài liệu theo max_score giảm dần và lấy Top 3 tài liệu max
    parsed_docs.sort(key=lambda x: x["max_score"], reverse=True)
    parsed_docs = parsed_docs[:3]
    logger.info(f"Retrieved {len(parsed_docs)} KB document(s) matching threshold >={threshold}: {[p['title'] for p in parsed_docs]}")

    output.append("[TÀI LIỆU THAM KHẢO]:")
    for doc_count, pdoc in enumerate(parsed_docs, 1):
        output.append(f"\nDocument {doc_count}. {pdoc['title']} ( {pdoc['link']})")
        for score, content in pdoc['segments']:
            logger.debug(f"    Segment score={score:.3f}: '{content[:80]}...'")
            output.append(f"   - \"{content}\"")

    return "\n".join(output)


class DocumentService:
    """Optimized service for Knowledge Base document retrieval using Vertex AI Search."""

    def __init__(self, bot_id: str, llm_service):
        self.bot_id = bot_id
        self.llm_service = llm_service
        LOGGER.info(f"Initialized DocumentService (KB Search Only) for bot: {bot_id}")

    @observe()
    async def search_documents(self, state: Dict) -> Dict:
        """Document search from Knowledge Base, combining QnA reference docs in [0.4, 0.8) from state."""
        query = (
            state.get('expanded_query')
            or state.get('enhanced_query')
            or state['query']
        )


        qna_docs = state.get('qna_docs', [])
        LOGGER.info(f"[DocumentService] Searching KB Engine for query: '{query}' | QnA Docs count: {len(qna_docs)}")

        try:
            result_text = await core_search_banking_knowledge(query=query, qna_docs=qna_docs)
            
            is_no_data = "Không có tài liệu phù hợp" in result_text or "chưa thể trả lời" in result_text.lower() or "đều dưới ngưỡng" in result_text.lower()
            
            if not is_no_data:
                final_docs = [{'content': result_text, 'score': 1.0, 'id': 'vertex_kb_result'}]
                relevance_score = 1.0
            else:
                final_docs = []
                relevance_score = 0.0

            new_state = state.copy()
            new_state['document_results'] = {
                'final_docs': final_docs,
                'relevance_score': relevance_score
            }
            langfuse_context.update_current_observation(output=new_state['document_results'])
            return new_state

        except Exception as e:
            LOGGER.error(f"Error searching KB documents via Vertex AI: {str(e)}")
            new_state = state.copy()
            new_state['document_results'] = {'final_docs': [], 'relevance_score': 0.0}
            return new_state

    async def filter_documents_batch(self, docs: List[Dict], query: str, cache_manager=None) -> Dict:
        """Pass-through document filtering without LLM call."""
        LOGGER.info(f"[DocumentService] Bypassing LLM document filter for {len(docs)} documents.")
        return {
            'filtered_docs': docs,
            'is_relevant': len(docs) > 0,
            'filter_stats': {
                'original_count': len(docs),
                'filtered_count': len(docs),
                'filter_ratio': 1.0 if docs else 0.0
            }
        }


async def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    from beechat.services.llm_service import LLMService

    print("==================================================")
    print(" DOCUMENT SERVICE TEST (KB SEARCH ONLY)")
    print("==================================================")

    llm_service = LLMService(bot_id="test_bot")
    doc_service = DocumentService(bot_id="test_bot", llm_service=llm_service)

    test_queries = [
        "Cách đổi mật khẩu app MB Bank",
        "Biểu phí chuyển tiền quốc tế MB"
    ]

    for q in test_queries:
        print(f"\n Query: '{q}'")
        res = await doc_service.search_documents({'query': q})
        docs = res.get('document_results', {}).get('final_docs', [])
        print(f"  Found {len(docs)} document result(s). Preview:\n")
        if docs:
            print(docs[0]['content'][:300] + "...")
        print("-" * 50)


if __name__ == "__main__":
    asyncio.run(main())