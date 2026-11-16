import asyncio
import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from beeflow.nodes import GraphNode, BasicChainNode, BranchNode, RedisNode
from beeflow.nodes.base_node import INPUT, OUTPUT, START, END
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.primitives.data.mongo_node import MongoNode
from beeflow.nodes.primitives.ai.llm_node import LLMNode
from beeflow.nodes.gcp.gcp_retriever_node import GCPRetrieverNode
from beeflow.utils.streaming import STREAM_SERVICE
from beeflow.workflow import WorkflowEngine
from beegen.registry.resource_hub import ResourceHub
from beegen.utils.common import transform_bot_id
from beegen.configs.storage.mongo_config import MongoOperation
from beegen.configs.cache.redis_config import RedisOperation


from beegenerate.llms.llm_response import fake_chunk_from
from beeportal.utils import PROMPTS, init_query
from beegen.tools.schema.param import ParamSet
from beeportal.bee_ai_enterprises.react_agent import ReActAgentNode

def create_mongo_query(document_id: str, page: int = 1) -> Dict[str, Any]:
    """Create a MongoDB query to fetch documents by IDs.

    Args:
        document_id: List of document IDs to retrieve

    Returns:
        query (Dict[str, Any]): MongoDB query dictionary
        skip (int): skip page 
    """
    # print('Skip: ', page * 10)
    return {
        "query": {"document_id": document_id},
        "skip": (page - 1) * 10
    }

def create_search_query(bot_id: str, keyword: str ) -> Dict[str, Any]:
    """Create a MongoDB query to search documents by keyword.

    Args:
        keyword: Search keyword

    Returns:
        query (Dict[str, Any]): MongoDB query dictionary
    """
    # Case-insensitive search in title and content fields
    return {
        "query": {
            "bot_id": bot_id,
            "$or": [
                {"title": {"$regex": keyword, "$options": "i"}},
                {"content": {"$regex": keyword, "$options": "i"}},
                {"tags": {"$regex": keyword, "$options": "i"}},
            ]
        }
    }

def get_session_key(session_id: str = None, role_ids: str = None) -> Dict[str, str]:
    """Extract session_id from INPUT and use as Redis key.

    The INPUT dict may contain a session_id field. If present, return it;
    otherwise return None to indicate no prior state exists.

    Args:
        session_id (str): Session ID from INPUT.

    Returns:
        Dict with 'key' ready for RedisNode input.
    """
    return {"key": "beeDeposit:" + session_id or None}

def prepare_list_documents_query(bot_id: str, category_id: str = "all") -> Dict[str, Any]:
    """Create MongoDB query for list documents.

    Args:
        bot_id: Bot ID to filter documents
        category_id: Category ID to filter (default "all" means get all)

    Returns:
        query (Dict[str, Any]): MongoDB query dictionary
    """
    query = {"bot_id": bot_id}
    if category_id and category_id != "all":
        query["category_id"] = category_id
    return {"query": query}

def preprocess_message_attachments(message: Dict[str, Any]) -> Dict[str, Any]:
    """Convert user message with attachments to standard multimodal content list format."""
    if not isinstance(message, dict):
        return message
        
    # Always pop attachments key to avoid confusing downstream processors (even if None)
    msg_copy = dict(message)
    attachments = msg_copy.pop("attachments", None)
    
    if not attachments:
        return msg_copy
        
    content_text = msg_copy.get("content", "")
    
    # If content is already a list, do nothing
    if isinstance(content_text, list):
        return msg_copy
        
    # Build standard OpenAI-compatible content list
    new_content = [{"type": "text", "text": str(content_text)}]
    
    for att in attachments:
        if not isinstance(att, dict):
            continue
        att_type = att.get("type", "")
        url_or_base64 = att.get("url_or_base64", "")
        
        # Check if it is an image or if the data URI is an image
        is_image = False
        if att_type in ("image", "image_base64"):
            is_image = True
        elif isinstance(url_or_base64, str) and url_or_base64.startswith("data:image/"):
            is_image = True
        elif isinstance(url_or_base64, str) and url_or_base64.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            is_image = True
            
        if is_image and url_or_base64:
            new_content.append({
                "type": "image_url",
                "image_url": {
                    "url": url_or_base64
                }
            })
            
    msg_copy["content"] = new_content
    return msg_copy

def limit_history_images(messages: List[Dict[str, Any]], max_images: int = 5) -> List[Dict[str, Any]]:
    """Scan messages in reverse order to keep only the most recent max_images across the entire history."""
    if not messages:
        return messages

    pruned_messages = []
    total_images_in = 0
    total_images_out = 0

    for msg in reversed(messages):
        if not isinstance(msg, dict):
            pruned_messages.append(msg)
            continue

        msg_copy = dict(msg)
        content = msg_copy.get("content")

        if isinstance(content, list):
            new_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    total_images_in += 1
                    if total_images_out < max_images:
                        new_parts.append(part)
                        total_images_out += 1
                    else:
                        # Skip this image as it exceeds the limit
                        pass
                else:
                    new_parts.append(part)
            msg_copy["content"] = new_parts
        pruned_messages.append(msg_copy)

    pruned_list = list(reversed(pruned_messages))
    print(f"[IMAGE_LIMITER] Total images in history: {total_images_in} -> Kept: {total_images_out} (Max allowed: {max_images})")
    return pruned_list

def prepare_input_agent(messages_new, state):
    """Prepare input messages for the agent by appending the latest user message.

    Concatenates the existing conversation history (loaded from Redis as JSON
    string) with the newest user message to form the full message list.
    If no prior state exists, return the entire messages_new list.

    Args:
        messages_new (List[Dict[str, Any]]): List of new messages from the current
            turn, where the last item is the latest user message.
        state (str): JSON string of existing conversation messages loaded from
            Redis, or an empty string/None if no prior history.

    Returns:
        Dict[str, List[Dict[str, Any]]]: Dictionary containing the combined
            'messages' list ready for agent input.
    """
    processed_messages_new = [
        preprocess_message_attachments(msg) if msg.get("role") == "user" else msg
        for msg in messages_new
    ]
    if not state:
        merged = processed_messages_new
    else:
        parsed_state = json.loads(state)
        merged = parsed_state + [processed_messages_new[-1]]
        
    # Prune history to limit images to the most recent 5
    pruned = limit_history_images(merged, max_images=5)
    return {
        'messages': pruned
    }

def merge_retrieval_results(qna_docs: List[Dict] = None, raw_docs: List[Dict] = None) -> Dict[str, Any]:
    """Merge QnA source-of-truth docs with raw document chunks.

    QnA docs are placed first (higher priority as Source of Truth).
    Each doc is tagged with source_type ('qna' or 'raw') so the LLM
    can distinguish and prioritize accordingly.

    Args:
        qna_docs: Documents from the QnA engine (retriever-qna).
        raw_docs: Documents from the raw doc engine (retriever).

    Returns:
        Dict with 'docs' key containing the merged, tagged document list.
    """
    merged = []
    for doc in (qna_docs or []):
        doc["source_type"] = "qna"
        merged.append(doc)
    for doc in (raw_docs or []):
        doc["source_type"] = "raw"
        merged.append(doc)
    return {"docs": merged}

class BeeAiEnterprises:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        self.mongo_engine = ResourceHub.self().sync_mongo("aicenter-chatbot")
        bot_info = self.mongo_engine._find_one(
            collection_name="botinfo", query={"_id": self.bot_id})
        self.name = bot_info.get('data', {'name': {}}).get('name', None)
        self.config = bot_info.get(
            'data', {'metadata': {}}).get('metadata', {})
        self.definition = self.config.get('system_prompt', "không có mô tả nào được cung cấp")
        self.checkpoint_collection = "checkpoint"

        self._build_flow()

    def _build_flow(self):

        with WorkflowEngine(
            name="beeAiEnterprises",
            description="Chatbot beeAiEnterprises sử dụng ReAct Agent với Retrieval tool"
        ) as bee_ai_enterprises:

            get_session_key_fn = CodeNode(
                name="get_session_key",
                code_fn=get_session_key,
                inputs={
                    "session_id": INPUT,
                    "role_ids": INPUT
                }, # Fix input aio
                return_keys=["key"]
            )

            get_redis = RedisNode(
                name="redis_get_value",
                resource_key="aicenter-chatbot",
                operation=RedisOperation.GET,
                inputs={
                    "key": {get_session_key_fn: "key"}
                }
            )

            with GraphNode(
                name="process_query",
                description="luồng xử lý query đầu vào",
                inputs={"messages": INPUT}
            ) as process_query:
                init_query_fn = CodeNode(
                    name="init_query_fn",
                    code_fn=init_query,
                    inputs={"messages": INPUT},
                    return_keys=["origin_query: str", "conversation: List[str]"],
                    outputs={"origin_query": OUTPUT, "conversation": OUTPUT}
                )
                START >> init_query_fn >> END

            with GraphNode(
                name="retrieval_graph",
                description="Tool truy vấn tài liệu từ knowledge base. Kết quả bao gồm 2 loại nguồn:\n"
                    "(1) QnA source-of-truth (source_type='qna'): các cặp hỏi-đáp đã được chuẩn hoá từ tài liệu gốc, đóng vai trò nguồn sự thật chính.\n"
                    "(2) Raw document chunks (source_type='raw'): nội dung thô từ tài liệu gốc, dùng bổ sung ngữ cảnh.\n"
                    "Mỗi doc có: id, content, title (tên tài liệu), source_type ('qna' hoặc 'raw').\n"
                    "Chú ý chọn đúng 'category' khi gọi tool:\n"
                    "- 'bieu_mau': khi người dùng cần tìm kiếm/tải biểu mẫu, mẫu biểu, template, bảng biểu, phụ lục mẫu.\n"
                    "- 'khac': các trường hợp tra cứu thông tin quy trình, quy định, hướng dẫn hoặc câu hỏi thông thường khác.",
                input_schema=(
                    ParamSet.new()
                        .var("query: str", "Câu query truy vấn vào knowledge base", required=True)
                        .var("category: str = 'khac'", "Phân loại tài liệu cần truy vấn: 'bieu_mau' (cho biểu mẫu/template/mẫu đơn) hoặc 'khac' (cho các tài liệu hướng dẫn, quy trình khác).", required=False)
                        .build()
                        )
                ) as retrieval_graph:
                    


                    # Branch 1: Datastore BM for forms/templates
                    bm_retrieval = GCPRetrieverNode(
                        name="bm_retrieval",
                        description="Truy vấn tài liệu biểu mẫu từ retriever-datastore-bm",
                        resource_key='retriever-datastore-bm',
                        use_rerank=True,
                        rerank_key="bge-m3",
                        rerank_threshold=0.0,
                        inputs={
                            "query": INPUT,
                            "page_size": 10,
                            "relevance_threshold": "HIGH",
                            "payload_overrides": {
                                "spellCorrectionSpec": {
                                    "mode": "AUTO"
                                },
                                "languageCode": "vi-VN",
                                "userInfo": {
                                    "timeZone": "Asia/Saigon"
                                },
                                "relevanceScoreSpec": {
                                    "returnRelevanceScore": True
                                },
                                "contentSearchSpec": {
                                    "extractiveContentSpec": {
                                        "maxExtractiveSegmentCount": 3,
                                        "returnExtractiveSegmentScore": True,
                                        "numPreviousSegments": 1,
                                        "numNextSegments": 1
                                    },
                                    "snippetSpec": {
                                        "returnSnippet": False
                                    }
                                }
                            }
                        },
                        outputs={"docs": OUTPUT}
                    )

                    # Dummy pass-through node to start standard flow
                    standard_flow_start = CodeNode(
                        name="standard_flow_start",
                        code_fn=lambda: {},
                        inputs={},
                        return_keys=[]
                    )

                    branch_query = BranchNode(
                        name="branch_query",
                        inputs={
                            "query": INPUT,
                            "category": INPUT
                        },
                        cases={
                            "category == 'bieu_mau' or 'biểu mẫu' in query.lower() or 'mẫu biểu' in query.lower()": "bm_retrieval"
                        },
                        default="standard_flow_start"
                    )

                    # Engine 1: QnA Source of Truth
                    qna_retrieval = GCPRetrieverNode(
                        name="qna_retrieval",
                        description="Truy vấn kho QnA source-of-truth",
                        resource_key='retriever-qna',
                        use_rerank=True,
                        rerank_key="bge-m3",
                        rerank_threshold=0.6,
                        inputs={
                            "query": INPUT,
                            "page_size": 10,
                            "relevance_threshold": "HIGH",
                            "payload_overrides": {
                                "languageCode": "vi-VN",
                                "params": {
                                    "returnRankSignals": True
                                },
                                "relevanceScoreSpec": {
                                    "returnRelevanceScore": True
                                },
                                "spellCorrectionSpec": {
                                    "mode": "AUTO"
                                },
                                "userInfo": {
                                    "timeZone": "Asia/Saigon"
                                }
                            }
                        }
                    )

                    # Engine 2: Raw document chunks
                    raw_retrieval = GCPRetrieverNode(
                        name="raw_retrieval",
                        description="Truy vấn raw document chunks từ tài liệu gốc",
                        resource_key='retriever',
                        use_rerank=True,
                        rerank_key="bge-m3",
                        rerank_threshold=0.0,
                        inputs={
                            "query": INPUT,
                            "page_size": 7,
                            "relevance_threshold": "HIGH",
                            "payload_overrides": {
                                "spellCorrectionSpec": {
                                    "mode": "AUTO"
                                },
                                "languageCode": "vi-VN",
                                "userInfo": {
                                    "timeZone": "Asia/Saigon"
                                },
                                "relevanceScoreSpec": {
                                    "returnRelevanceScore": True
                                },
                                "contentSearchSpec": {
                                    "extractiveContentSpec": {
                                        "maxExtractiveSegmentCount": 3,
                                        "returnExtractiveSegmentScore": True,
                                        "numPreviousSegments": 1,
                                        "numNextSegments": 1
                                    },
                                    "snippetSpec": {
                                        "returnSnippet": False
                                    }
                                }
                            }
                        }
                    )

                    # Merge 2 engine results: QnA first, Raw second
                    merge_fn = CodeNode(
                        name="merge_results",
                        code_fn=merge_retrieval_results,
                        inputs={
                            "qna_docs": {qna_retrieval: "docs"},
                            "raw_docs": {raw_retrieval: "docs"}
                        },
                        return_keys=["docs"],
                        outputs={"docs": OUTPUT}
                    )

                    START >> branch_query >> [bm_retrieval, standard_flow_start]
                    bm_retrieval >> END
                    standard_flow_start >> [qna_retrieval, raw_retrieval] >> merge_fn >> END

                    retrieval_graph.build()

            prepare_input_fn = CodeNode(
                name="prepare_input_agent",
                code_fn=prepare_input_agent,
                inputs={
                    "messages_new": {INPUT: "messages"},
                    "state": {get_redis: "value"}
                },
                return_keys=["messages"]
            )

            # ReActAgentNode - dùng bản đã fix trong react_agent_node.py
            react_agent = ReActAgentNode(
                name="react_agent",
                # resource_key="gpt-4.1",
                resource_key="gemini-3-flash-chat",
                # resource_key="qwen-instruct-chat",
                tools=[
                    retrieval_graph
                ],
                max_iterations=5,
                context_prompt = PROMPTS['BEE_AI_ENTERPRISES:REACT_AGENT'].format(definition=self.definition),
                reviewer_prompt = PROMPTS['BEE_AI_ENTERPRISES:REVIEWER_AGENT'],
                inputs=prepare_input_fn,
                outputs={"final_answer": OUTPUT}
            )

            get_state_fn = CodeNode(
                name="format_result_fn",
                code_fn=self._final_state,
                inputs={
                    "state_output": react_agent["final_state_messages"],
                    "final_answer": {react_agent: "final_answer"},
                    "query": {process_query: "origin_query"}
                },
                return_keys=["state"]
            )

            save_redis = RedisNode(
                name="redis_save_state",
                resource_key="aicenter-chatbot",
                operation=RedisOperation.SETEX,
                inputs={
                    "key": {get_session_key_fn: "key"},
                    "value": {get_state_fn: 'state'},
                    "seconds": 600
                }
            )

            START >> get_session_key_fn >> get_redis >> process_query >> prepare_input_fn >> react_agent >> get_state_fn >> save_redis >> END

        bee_ai_enterprises.compile()
        self.workflow = bee_ai_enterprises

    def _final_state(self, state_output: Any, final_answer: Any, process_query: Any) -> Dict[str, str]:

        return {'state': json.dumps(state_output, ensure_ascii=False)}

    async def run(self, messages: List[Dict], client_message_id: str, session_id: str, username: str, role_ids: List[str] = [], **kwargs):
        try:
            asyncio.create_task(self.workflow.run(
                request_id=client_message_id,
                inputs={
                    "messages": messages,
                    "session_id": session_id,
                    "role_ids": role_ids
                },
                session_id=session_id,
                user_id=username
            ))

            async for channel_name in STREAM_SERVICE.get_channels(client_message_id):
                async for chunk in STREAM_SERVICE.get(client_message_id, channel_name, json_mode=False):
                    yield chunk
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield fake_chunk_from(content='Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại sau.', model="error")


async def main():
    bot_id = "4c0821bf-6a87-4231-93ac-52abe4c6e06b"

    bot = BeeAiEnterprises(bot_id)
    import uuid
    dialogue_id = str(uuid.uuid4())
    client_message_id = str(uuid.uuid4())
    username = 'dev-beebot'

    print('dialogue_id:', dialogue_id)
    print('client_message_id:', client_message_id)

    async for chunk in bot.run(
            messages=[{"role": "user", "content": "Quy định độ tuổi đối với bên bảo đảm là KHCN"}],
            session_id=dialogue_id,
            client_message_id=client_message_id,
            role_ids=["L1"],
            topic="default",
            username=username,
    ):
        print(f"{chunk.choices[0].delta.content or ''}", end="")
        # print(chunk)

    await asyncio.sleep(4)


if __name__ == '__main__':
    asyncio.run(main())
