import json
import uuid
from typing import Dict, Any, List

from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.configs.node_config import NodeType
from beeflow.configs.graph_config import GraphNodeConfig
from beegen.loggings import LOGGER


# =====================================================================
# 1. PURE FUNCTIONS (dùng trong CodeNode)
# =====================================================================

def extract_session_key(session_id: str) -> Dict[str, Any]:
    """Tạo Redis Key và lấy session_id từ đầu vào."""
    return {
        "redis_key": f"chat_history:{session_id}",
        "mongo_query": f"session_id:{session_id}"
    }


def merge_state(current_messages: list, redis_result: Any, mongo_result: Any = None, number_of_messages: int = 6) -> Dict[str, Any]:
    """
    Kết hợp lịch sử chat cũ (từ Redis hoặc Mongo) và tin nhắn mới của User.
    Ưu tiên: Redis > Mongo > Empty
    number_of_messages: số lượng message gần nhất để tạo conversation (mặc định 6 messages ~ 3 turns)
    """
    history = []

    # Ưu tiên lấy từ Redis trước
    if redis_result:
        try:
            history = json.loads(redis_result) if isinstance(redis_result, str) else redis_result
            LOGGER.info(f"Loaded {len(history)} messages from Redis")
        except Exception as e:
            LOGGER.warning(f"Không thể parse lịch sử từ Redis: {e}")
            history = []

    # Nếu Redis không có, thử MongoDB
    elif mongo_result:
        try:
            if isinstance(mongo_result, dict) and "messages" in mongo_result:
                history = mongo_result["messages"]
            LOGGER.info(f"Loaded {len(history)} messages from MongoDB")
        except Exception as e:
            LOGGER.warning(f"Không thể parse lịch sử từ MongoDB: {e}")
            history = []

    merged_messages = history + current_messages

    # Tạo conversation từ number_of_messages message gần nhất
    recent = merged_messages[-number_of_messages:] if len(merged_messages) >= number_of_messages else merged_messages
    conversation = [
        f"USER: {m['content']}"
        if m['role'] == 'user'
        else f"BOT: {m['content']}"
        for m in recent
    ]

    return {
        "merged_messages": merged_messages,
        "origin_query": current_messages[-1]["content"] if current_messages else "",
        "conversation": conversation
    }


def select_history_source(redis_value: Any, mongo_doc: Any) -> Dict[str, Any]:
    """Chọn nguồn history: ưu tiên Redis, nếu không có thì dùng MongoDB."""
    # Kiểm tra redis_value hợp lệ: không None, không rỗng, và không phải là null trong response
    use_redis = False
    if redis_value is not None and redis_value != "":
        # Nếu là dict với format {"status": "success", "value": null, ...}, coi là không có dữ liệu
        if isinstance(redis_value, dict):
            if redis_value.get("status") == "success" and redis_value.get("value") is None:
                use_redis = False
            else:
                use_redis = True
        else:
            use_redis = True

    return {
        "selected_redis_value": redis_value if use_redis else None,
        "selected_mongo_value": mongo_doc if not use_redis else None,
        "source": "redis" if use_redis else "mongodb"
    }


# =====================================================================
# 2. CONFIG
# =====================================================================

class LoadStateNodeConfig(GraphNodeConfig):
    """Config cho LoadStateNode."""
    type: NodeType = "load_state"
    ttl_seconds: int = 86400  # 24 hours default TTL
    number_of_messages: int = 6


# =====================================================================
# 3. NODE
# =====================================================================

class LoadStateNode(GraphNode):
    """
    GraphNode load State từ Redis và MongoDB.

    Luồng:
        INPUT → extract_key → [redis_get, mongo_find]
              → select_source → merge_state → OUTPUT

    Input schema:
        session_id: str   — chứa session_id
        messages: List[Dict] — tin nhắn hiện tại của user

    Output schema:
        merged_messages: List[Dict]  — lịch sử + tin nhắn mới
        latest_query: str            — query của user
        source: str                  — nguồn load ("redis" | "mongodb")
    """

    type: NodeType = "graph"

    def __init__(
        self,
        ttl_seconds: int = 300,
        number_of_messages: int = 6,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.ttl_seconds = ttl_seconds
        self.number_of_messages = number_of_messages
        self._build_graph()

    def _build_graph(self):
        from beeflow.nodes import (
            CodeNode, RedisNode, MongoNode,
            START, END, INPUT, OUTPUT,
        )
        from beeflow.nodes.primitives.data.redis_node import RedisNode
        from beeflow.nodes.primitives.data.mongo_node import MongoNode
        from beegen.configs.cache.redis_config import RedisOperation
        from beegen.configs import MongoOperation

        def sub(suffix: str) -> str:
            return suffix

        with self:
            # --- Bước 1: Extract session key ---
            n_extract = CodeNode(
                name=sub("extract_session_key"),
                code_fn=extract_session_key,
                inputs={"session_id": INPUT["session_id"]},
                return_keys={"redis_key: str", "mongo_query: str"}
            )

            # --- Bước 2: Load từ Redis ---
            n_redis_get = RedisNode(
                name=sub("redis_get"),
                resource_key="aicenter-chatbot",
                operation=RedisOperation.GET,
                inputs={"key": {n_extract: "redis_key"}},
            )

            # --- Bước 3: Load từ Mongo ---
            n_mongo_find = MongoNode(
                name=sub("mongo_find"),
                resource_key="aicenter-chatbot",
                operation=MongoOperation.FIND_ONE,
                inputs={
                    "collection_name": "chat_sessions",
                    "query": {n_extract: "mongo_query"},
                }
            )

            # --- Bước 4: Select source (Redis ưu tiên) ---
            n_select_source = CodeNode(
                name=sub("select_source"),
                code_fn=select_history_source,
                inputs={
                    "redis_value": {n_redis_get: "value"},
                    "mongo_doc": {n_mongo_find: "document"}
                },
                return_keys={
                    "selected_redis_value: Any",
                    "selected_mongo_value: Any",
                    "source: str"
                }
            )

            # --- Bước 5: Merge với tin nhắn hiện tại ---
            n_merge = CodeNode(
                name=sub("merge_state"),
                code_fn=merge_state,
                inputs={
                    "current_messages": INPUT["messages"],
                    "redis_result": {n_select_source: "selected_redis_value"},
                    "mongo_result": {n_select_source: "selected_mongo_value"},
                    "number_of_messages": self.number_of_messages,
                },
                return_keys={"merged_messages: list", "origin_query: str", "conversation: list"},
                outputs=OUTPUT
            )

            # --- Graph edges ---
            START >> [n_extract, n_mongo_find] >> n_redis_get >> n_select_source >> n_merge >> END
            
        self.build()

async def main():
    from beeflow.workflow import WorkflowEngine
    from beeflow.nodes.base_node import INPUT, OUTPUT, START, END

    with WorkflowEngine(
        name="test-load-state",
        description="Test LoadStateNode"
    ) as test_load:

        load_state = LoadStateNode(
            name="load_state",
            inputs=INPUT,
            outputs=OUTPUT,
        )

        START >> load_state >> END

    test_load.compile()

    result = await test_load.run(
        inputs={
            "session_id": "test1",
            "messages": [{"role": "user", "content": "Xin chào"}]
        }
    )

    # print("=" * 60)
    print(f"Source: {result['origin_query']}")
    print(f"Messages count: {len(result['merged_messages'])}")
    print(f"Merged messages: {result['merged_messages']}")
    # print("=" * 60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
