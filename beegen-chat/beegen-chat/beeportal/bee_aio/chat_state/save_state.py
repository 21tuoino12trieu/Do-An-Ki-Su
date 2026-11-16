import json
import uuid
from typing import Dict, Any

from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.configs.node_config import NodeType
from beeflow.configs.graph_config import GraphNodeConfig
from beegen.loggings import LOGGER


# =====================================================================
# 1. PURE FUNCTIONS (dùng trong CodeNode)
# =====================================================================

def prepare_save_state(
    merged_messages: list | None,
    bot_response: str,
    session_id: str,
    redis_key: str
) -> Dict[str, Any]:
    """Chuẩn bị Payload để lưu xuống cả Redis và Mongo."""
    from datetime import datetime
    import datetime as dt

    merged_messages = merged_messages or []

    final_messages = merged_messages + [
        {"role": "assistant", "content": bot_response}
    ]

    mongo_doc = {
        "session_id": session_id,
        "messages": final_messages,
        "latest_bot_response": bot_response,
        "updated_at": datetime.now(dt.timezone.utc)
    }

    return {
        "redis_key_out": redis_key,
        "redis_value_out": json.dumps(final_messages, ensure_ascii=False),
        "mongo_doc": mongo_doc,
        "collection_name": "chat_sessions",
    }


def prepare_upsert(session_id: str, mongo_doc: dict, collection_name: str) -> Dict[str, Any]:
    """Chuẩn bị payload cho upsert (insert or update)."""
    mongo_doc_clean = {k: v for k, v in mongo_doc.items() if k != "_id"}

    return {
        "filter": {"_id": session_id},
        "update": {"$set": mongo_doc_clean},
        "upsert": True,
    }


# =====================================================================
# 2. CONFIG
# =====================================================================

class SaveStateNodeConfig(GraphNodeConfig):
    """Config cho SaveStateNode."""
    type: NodeType = "save_state"
    ttl_seconds: int = 86400  # 24 hours default TTL


# =====================================================================
# 3. NODE
# =====================================================================

class SaveStateNode(GraphNode):
    """
    GraphNode save State xuống Redis và MongoDB.

    Luồng:
        INPUT → prepare → upsert_prepare → [redis_set, mongo_upsert] → END

    Input schema:
        merged_messages: List[Dict] — lịch sử đã merge
        bot_response: str           — response của bot
        session_id: str             — session ID
        redis_key: str              — Redis key

    Output schema:
        saved: bool  — trạng thái lưu thành công
    """

    type: NodeType = "graph"

    def __init__(
        self,
        ttl_seconds: int = 86400,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.ttl_seconds = ttl_seconds
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
            # --- Bước 1: Prepare save state ---
            n_prepare = CodeNode(
                name=sub("prepare_save_state"),
                code_fn=prepare_save_state,
                inputs={
                    "merged_messages": INPUT["merged_messages"],
                    "bot_response": INPUT["bot_response"],
                    "session_id": INPUT["session_id"],
                    "redis_key": INPUT["redis_key"]
                },
                return_keys={
                    "redis_key_out: str",
                    "redis_value_out: str",
                    "mongo_doc: dict",
                    "collection_name: str",
                }
            )

            # --- Bước 2: Prepare upsert payload ---
            n_upsert_prepare = CodeNode(
                name=sub("prepare_upsert"),
                code_fn=prepare_upsert,
                inputs={
                    "session_id": INPUT["session_id"],
                    "mongo_doc": {n_prepare: "mongo_doc"},
                    "collection_name": {n_prepare: "collection_name"}
                },
                return_keys={
                    "filter: dict",
                    "update: dict",
                    "upsert: bool",
                }
            )

            # --- Bước 3: Save vào Redis ---
            n_redis_set = RedisNode(
                name=sub("redis_set"),
                resource_key="aicenter-chatbot",
                operation=RedisOperation.SETEX,
                inputs={
                    "key": {n_prepare: "redis_key_out"},
                    "value": {n_prepare: "redis_value_out"},
                    "seconds": self.ttl_seconds
                }
            )

            # --- Bước 4: Upsert vào Mongo ---
            n_mongo_upsert = MongoNode(
                name=sub("mongo_upsert"),
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": {n_prepare: "collection_name"},
                    "filter": {n_upsert_prepare: "filter"},
                    "update": {n_upsert_prepare: "update"},
                    "upsert": {n_upsert_prepare: "upsert"}
                }
            )

            # --- Graph edges ---
            START >> n_prepare >> n_upsert_prepare
            n_upsert_prepare >> [n_redis_set, n_mongo_upsert] >> END

        self.build()


async def main():
    from beeflow.workflow import WorkflowEngine
    from beeflow.nodes.base_node import INPUT, START, END

    with WorkflowEngine(
        name="test-save-state",
        description="Test SaveStateNode"
    ) as test_save:

        save_state = SaveStateNode(
            name="save_state",
            inputs=INPUT,
        )

        START >> save_state >> END

    test_save.compile()

    merged_messages = [
        {"role": "user", "content": "Xin chào"},
        {"role": "assistant", "content": "Chào bạn"}
    ]

    result = await test_save.run(
        inputs={
            "merged_messages": merged_messages,
            "bot_response": "Rất vui được gặp bạn!",
            "session_id": "test_session_001",
            "redis_key": "chat_history:test_session_001"
        }
    )

    print("=" * 60)
    print(f"Save result: {result}")
    print("=" * 60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
