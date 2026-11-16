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
from beeflow.nodes.templates.retriever_node_v2 import RetrieverNode
from beeflow.utils.streaming import STREAM_SERVICE
from beeflow.workflow import WorkflowEngine
from beegen.registry.resource_hub import ResourceHub
from beegen.utils.common import transform_bot_id
from beegen.configs.storage.mongo_config import MongoOperation
from beegen.configs.cache.redis_config import RedisOperation


from beegenerate.llms.llm_response import fake_chunk_from
from beeportal.utils import PROMPTS, init_query
from beegen.tools.schema.param import ParamSet
from beeportal.bot_deposit.pev_fc_agent_node import PlanExecuteVerifyAgentNode

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
    if not state:
        return {'messages': messages_new}
    parsed_state = json.loads(state)
    return {
        'messages': parsed_state + [messages_new[-1]]
    }

class BeeDeposit:
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
            name="beeDeposit",
            description="Chat bot Deposit sử dụng ReAct Agent với Retrieval tool"
        ) as beeDeposit:

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
                description="Tool truy vấn tài liệu từ knowledge base",
                input_schema=(
                    ParamSet.new()
                        .var("query: str", "Câu query truy vấn vào knowledge base", required=True)
                        .build()
                        )
                ) as retrieval_graph:
                    retrieval_node = RetrieverNode(
                    name="retrieval_tool",
                    description="Tool truy vấn tài liệu từ knowledge base",
                    inputs={
                        "query": INPUT,
                        "collection": transform_bot_id(self.bot_id),
                        "top_k": 16,
                        "rerank_top_k": 8,
                        "allowed_roles": ['L1'],
                        "bot_id": self.bot_id,
                        "partition_names": ['document'],
                        "output_fields": ["chunk_id"],
                        "rerank_threshold": 0.0,
                        "threshold": self.config.get('retrieval', {}).get('retrieval_threshold', 0.0)
                    },
                    outputs={"docs": OUTPUT})

                    START >> retrieval_node >> END

                    retrieval_graph.build()
            
            with GraphNode(
                name="get_list_documents",
                description="Tool lấy danh sách sản phẩm, chương trình huy động vốn ở trong knowledge. Đầu ra trả về bao gồm id (id của chunk), doc/document_id (id của tài liệu, dùng để lấy toàn bộ tài liệu), content (nội dung của chunk)",
                input_schema=(
                    ParamSet.new()
                        .var("category_id: str", "id của category để lọc tập hợp tài liệu theo chủ đề lấy từ get_categories, mặc định là 'all' để lấy tất cả", required=False)
                        .build()
                        )
                ) as get_list_documents:

                    create_list_query_fn = CodeNode(
                        name="create_list_query_fn",
                        code_fn=prepare_list_documents_query,
                        inputs={
                            'bot_id': self.bot_id,
                            'category_id': INPUT
                        },
                        return_keys=["query"]
                    )

                    mongo_node = MongoNode(
                        name="get_list_documents_tool",
                        resource_key="aicenter-chatbot",
                        description="Tool lấy danh sách sản phẩm, chương trình huy động vốn ở trong knowledge",
                        operation=MongoOperation.FIND,
                        inputs={
                            "query": {create_list_query_fn: "query"},
                            "collection_name": "documents",
                            "projection": {
                                "doc_name": 1,
                                "_id": 1,
                                "category_id": 1
                            },
                            "limit": 100
                        },
                        outputs=OUTPUT
                    )

                    START >> create_list_query_fn >> mongo_node >> END
                    get_list_documents.build()
            
            with GraphNode(
                name="get_document_content",
                description="Lấy nội dung của tài liệu trong knowlegde bằng id, kết quả trả về sẽ 10 trang (chunk)",
                input_schema=(
                    ParamSet.new()
                        .var("document_id: str", "id của tài liệu", required=True)
                        .var("page: int", "trang của tài liệu, mặc định là 10", required=False)
                        .build()
                    )
                ) as get_document_content:

                    create_mongo_query_fn = CodeNode(
                        name="create_mongo_query_fn",
                        code_fn=create_mongo_query,
                        inputs={
                            'document_id': INPUT,
                            'page': INPUT
                        },
                        return_keys=['query: Dict[str, Any]', 'skip: int']
                    )

                    mongo_node = MongoNode(
                        name="get_content",
                        resource_key="aicenter-chatbot",
                        description="Lấy toàn bộ nội dung của tài liệu trong knowlegde bằng id",
                        operation=MongoOperation.FIND,
                        inputs={
                            "query": {create_mongo_query_fn: "query"},
                            "collection_name": "document_data",
                            "projection": {
                                "content": 1,
                            },
                            "skip": {create_mongo_query_fn: "skip"}
                        },
                        outputs=OUTPUT
                    )

                    START >> create_mongo_query_fn >> mongo_node >> END
                    get_document_content.build()

            with GraphNode(
                name="search_documents",
                description="Tìm kiếm tài liệu trong knowledge bằng từ khóa",
                input_schema=(
                    ParamSet.new()
                        .var("keyword: str", "từ khóa tìm kiếm", required=True)
                        .build()
                    )
                ) as search_documents:

                    create_search_query_fn = CodeNode(
                        name="create_search_query_fn",
                        code_fn=create_search_query,
                        inputs={
                            'keyword': INPUT,
                            'bot_id': self.bot_id
                        }
                    )

                    mongo_node = MongoNode(
                        name="search_content",
                        resource_key="aicenter-chatbot",
                        description="Tìm kiếm tài liệu theo từ khóa",
                        operation=MongoOperation.FIND,
                        inputs={
                            "query": create_search_query_fn,
                            "collection_name": "document_data",
                            "limit": 20,
                            "projection": {
                                "_id": 1,
                                "title": 1,
                                "content": 1,
                                "doc_name": 1,
                                "document_id": 1
                            }
                        },
                        outputs=OUTPUT
                    )

                    START >> create_search_query_fn >> mongo_node >> END
                    search_documents.build()

            with GraphNode(
                name="get_categories",
                description="Lấy danh sách các topic/danh mục từ bảng category. Trả về name và _id của mỗi category, mỗi topic/danh mục sẽ tương ứng với một tập hợp tài liệu sản phẩm, chương trình tương ứng",
                input_schema=(
                    ParamSet.new().build()
                )
            ) as get_categories:

                mongo_node = MongoNode(
                    name="get_categories_tool",
                    resource_key="aicenter-chatbot",
                    description="Lấy danh sách các topic/danh mục",
                    operation=MongoOperation.FIND,
                    inputs={
                        "query": {'bot_id': self.bot_id},
                        "collection_name": "category",
                        "projection": {
                            "name": 1,
                            "_id": 1
                        }
                    },
                    outputs=OUTPUT
                )

                START >> mongo_node >> END
                get_categories.build()

            prepare_input_fn = CodeNode(
                name="prepare_input_agent",
                code_fn=prepare_input_agent,
                inputs={
                    "messages_new": {INPUT: "messages"},
                    "state": {get_redis: "value"}
                },
                return_keys=["messages"]
            )

            # PlanExecuteVerifyAgentNode - dùng bản đã fix trong pev_fc_agent_node.py
            react_agent = PlanExecuteVerifyAgentNode(
                name="react_agent",
                resource_key="gpt-4.1",
                # resource_key="gemini-2.5-flash-chat",
                tools=[
                    retrieval_graph,
                    get_list_documents,
                    get_document_content,
                    search_documents,
                    get_categories
                ],
                max_iterations=15,
                context_prompt=f"""Bạn là một agent hỗ trợ khách hàng về các sản phẩm gửi tiền (deposit) của MB Bank.
Thông tin về bot: {self.definition}
Nhiệm vụ của bạn:
1. Suy nghĩ từng bước để trả lời câu hỏi của khách hàng
2. Trả lời bằng tiếng Việt, lịch sự và chính xác

DANH SÁCH CÁC TOOL VÀ KHI NÀO SỬ DỤNG:

1. **retrieval_tool**: Tìm kiếm tài liệu bằng semantic search (vector similarity).
   - Dùng khi: hỏi về thông tin sản phẩm, chương trình, giải thưởng, lãi suất, điều kiện gửi tiền, thông tin chi nhánh.
   - Input: câu hỏi tự nhiên

2. **search_documents**: Tìm kiếm tài liệu bằng từ khóa (keyword search).
   - Dùng khi: muốn tìm tài liệu cụ thể theo từ khóa trong tiêu đề, nội dung, tags.
   - Input: keyword (từ khóa tìm kiếm)

3. **get_categories**: Lấy danh sách các topic/danh mục sản phẩm.
   - Dùng khi: khách hàng muốn xem có những danh mục nào, hoặc muốn duyệt sản phẩm theo chủ đề.
   - Input: không cần tham số

4. **get_list_documents**: Lấy danh sách sản phẩm/chương trình theo danh mục.
   - Dùng khi: muốn hiển thị danh sách sản phẩm trong một danh mục cụ thể.
   - Input: category_id (lấy từ get_categories, mặc định 'all' để lấy tất cả)

5. **get_document_content**: Lấy nội dung chi tiết của một tài liệu.
   - Dùng khi: khách hàng muốn xem chi tiết một sản phẩm/tài liệu cụ thể.
   - Input: document_id, page (mặc định page 1)

THỨ TỰ GỢI Ý:
- Hỏi thông tin chung/chung chung → get_categories → get_list_documents
- Hỏi chi tiết về sản phẩm → retrieval_tool hoặc search_documents
- Xem nội dung chi tiết → get_document_content
- Luôn ưu tiên retrieval_tool cho các câu hỏi về lãi suất, điều kiện, quyền lợi.""",
                # inputs={prepare_input_fn: "messages"},
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

        beeDeposit.compile()
        self.workflow = beeDeposit

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
    bot_id = "347f7a6e-83d2-4cfa-9e85-6bc080c234c4"

    bot = BeeDeposit(bot_id)
    import uuid
    dialogue_id = str(uuid.uuid4())
    client_message_id = str(uuid.uuid4())
    username = 'dev-deposit'

    print('dialogue_id:', dialogue_id)
    print('client_message_id:', client_message_id)

    async for chunk in bot.run(
            messages=[{"role": "user", "content": "cho tôi biết bạn có những đầu mục tài liệu nào"}],
            session_id=dialogue_id,
            client_message_id=client_message_id,
            role_ids=["L1"],
            topic="default",
            username=username,
    ):
        # print(f"{chunk.choices[0].delta.content or ''}", end="")
        print(chunk)

    await asyncio.sleep(4)


if __name__ == '__main__':
    asyncio.run(main())
