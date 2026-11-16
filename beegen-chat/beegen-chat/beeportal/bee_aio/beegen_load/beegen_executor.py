from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
import asyncio

from beegen.tools.schema.param import ParamSet
from beeflow.nodes.base_node import BaseNode
from beeflow.states import WorkflowState
from beeflow.utils.streaming import STREAM_SERVICE
from beegen.loggings import LOGGER
from beegen.utils.common import fake_chunk_from

from beegenerate.loggings import LOGGER
from beegenerate.storage import (
    BotStore,
    DocumentStore
)
from beegenerate.vectordb import MilvusStorage
from beegenerate.configs import (
    MongoConfig,
    MilvusConfig
)

# Global service variables
bot_store = BotStore(MongoConfig.default())
vec_store = MilvusStorage(MilvusConfig.default())
doc_store = DocumentStore(MongoConfig.default())
bot_manager = {}

# Access to global bot manager
# We need to import these from server.py but import them when accessed to avoid circular imports
def get_bot_manager():
    from entrypoints.api.server import bot_manager
    return bot_manager


class BeegenExecutorNode(BaseNode):
    """
    Node executor cho agent type 'beegen' (Bot-based).

    Khác với AgentExecutorNode (dùng WorkflowEngine), node này nhận
    một dict `available_bots` ánh xạ bot_id → Bot instance (beeportal.beegen_bot_v2.Bot).
    Mỗi Bot expose interface `bot.run(messages, role_ids, topic, ...)` là async generator
    trả về các chunk streaming.

    Flow:
        1. Đọc `bot_id` và `bot_inputs` từ state.
        2. Lookup Bot instance từ `available_bots`.
        3. Stream từng chunk qua STREAM_SERVICE.push().
        4. Kết thúc bằng STREAM_SERVICE.end().

    Input schema:
        bot_id        : str               – ID của beegen bot cần thực thi
        bot_inputs    : Dict[str, Any]    – Payload gồm messages, role_ids, topic, ...

    Output schema:
        result        : Any               – Nội dung tổng hợp (full text) sau khi stream xong
        success       : bool
        error         : Optional[str]
        matched_bot   : str               – bot_id đã thực thi
    """

    type: str = "beegen-executor"

    input_schema: ParamSet = (
        ParamSet.new()
            .var("bot_id: str", required=True)
            .var("bot_inputs: Dict[str, Any]", required=True)
            .build()
    )

    output_schema: ParamSet = (
        ParamSet.new()
            .var("result: Any", required=True)
            .var("success: bool", required=True)
            .var("error: Optional[str] = None")
            .var("matched_bot: str", required=True)
            .build()
    )

    def __init__(
        self,
        available_bots: Optional[Dict[str, Any]] = None,  # bot_id -> Bot instance
        stream: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)

        if available_bots is None:
            available_bots = get_bot_manager()

        if not available_bots:
            raise ValueError(f"Node {self.full_name}: available_bots must not be empty!")

        self.available_bots = available_bots
        self.stream = stream

        for bot_id in available_bots:
            LOGGER.info(
                f"[BeegenExecutorNode] Registered bot '{bot_id}' "
                f"with executor '{self.full_name}'"
            )

    async def run(
        self,
        state: WorkflowState,
        context_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:

        request_id  = state.request_id if state else str(uuid.uuid4())
        start_time  = datetime.now()
        _outputs    = {}
        _bot_id     = None

        try:
            _inputs    = self.get_inputs(state, context_id=context_id)
            _bot_id    = _inputs.get("bot_id")
            bot_inputs = _inputs.get("bot_inputs", {})

            # ── Validate ────────────────────────────────────────────────────
            if not _bot_id:
                raise ValueError("bot_id is required")
            if _bot_id not in self.available_bots:
                raise ValueError(
                    f"[BeegenExecutorNode] Unknown bot_id: '{_bot_id}'. "
                    f"Available: {list(self.available_bots.keys())}"
                )

            bot_entry = self.available_bots[_bot_id]
            # Server lưu {config, bot} hoặc Bot instance trực tiếp
            bot = bot_entry.get('bot', bot_entry) if isinstance(bot_entry, dict) else bot_entry

            # ── Record execution ────────────────────────────────────────────
            state.record_execution(
                self.full_name,
                self.father.full_name if self.father else None,
                context_id,
            )

            LOGGER.info(
                "request[%s]: BeegenExecutorNode '%s' → bot_id='%s', inputs=%s",
                request_id, self.name, _bot_id, str(bot_inputs)[:200],
            )

            # ── Extract standard bot.run() params from bot_inputs ───────────
            messages  : List[Dict] = bot_inputs.get("messages", [])
            role_ids  : List[str]  = bot_inputs.get("role_ids", [])
            topic     : str        = bot_inputs.get("topic", "default")
            # Forward any extra kwargs transparently
            extra     : Dict       = {
                k: v for k, v in bot_inputs.items()
                if k not in ("messages", "role_ids", "topic")
            }

            # ── Stream chunks ───────────────────────────────────────────────
            full_text_parts: List[str] = []

            async for chunk in bot.run(
                messages=messages,
                role_ids=role_ids,
                topic=topic,
                **extra,
            ):
                # Collect text for final result
                if (
                    chunk.choices
                    and chunk.choices[0].delta.content is not None
                ):
                    full_text_parts.append(chunk.choices[0].delta.content)

                # Push chunk to STREAM_SERVICE so outer consumer can yield it
                if self.stream:
                    await STREAM_SERVICE.push(
                        request_id=request_id,
                        channel_name=self.identity(context_id),
                        data=chunk,
                    )

            full_text = "".join(full_text_parts)
            _outputs  = {"result": full_text, "success": True}

            LOGGER.info(
                "request[%s]: BeegenExecutorNode '%s' completed, "
                "output_len=%d chars",
                request_id, self.name, len(full_text),
            )

        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            LOGGER.error(
                f"[BeegenExecutorNode] '{self.name}' failed: {e}\n{error_msg}"
            )
            _outputs = {"error": error_msg, "success": False}

            if self.stream:
                asyncio.create_task(
                    STREAM_SERVICE.push(
                        request_id=request_id,
                        channel_name=self.identity(context_id),
                        data=fake_chunk_from(
                            content="Agent beegen gặp lỗi, vui lòng thử lại.",
                            model="error",
                        ),
                    )
                )

        finally:
            end_time = datetime.now()
            if state:
                state.set_by_index(
                    self.metrics.get("start_time", None), start_time, context_id
                )
                state.set_by_index(
                    self.metrics.get("end_time", None), end_time, context_id
                )

            self.store_result(
                state=state,
                result={
                    "result":      _outputs.get("result"),
                    "success":     _outputs.get("success", False),
                    "error":       _outputs.get("error"),
                    "matched_bot": _bot_id,
                },
                context_id=context_id,
            )

            if self.stream:
                asyncio.create_task(
                    STREAM_SERVICE.end(request_id, self.identity(context_id))
                )

        return _outputs


# ---------------------------------------------------------------------------
# Local test
# ---------------------------------------------------------------------------

async def main():
    from beeportal.beerm_v1 import BotRM
    from beegenerate.storage import BotStore
    from beegenerate.configs import MongoConfig, MilvusConfig
    from beegenerate.vectordb import MilvusStorage
    from beegenerate.storage import (
        DocumentStore,
        BotStore
)    
    from beeflow.states.workflow_indexer import WorkflowIndexer
    from beeflow.states.workflow_state import WorkflowState
    from beeflow.nodes.base_node import INPUT, OUTPUT, START, END
    from beeflow.workflow import WorkflowEngine


    bot_id = "269c75a7-b3dc-4a34-ae6f-a337ad7e8d34"

    bot_store  = BotStore(config=MongoConfig.default())
    bot_config = bot_store.fetch_bot_details(bot_id=bot_id)

    bot = BotRM(
        bot_config=bot_config,
        vec_store=MilvusStorage(config=MilvusConfig.default()),
        doc_store=DocumentStore(config=MongoConfig.default()),
        bot_store=BotStore(config=MongoConfig.default()),
    )
 
    available_bots = {bot_id: bot}
 
    with WorkflowEngine(
        name="test-beegen-executor",
        description="Test BeegenExecutorNode"
    ) as wf:
        executor = BeegenExecutorNode(
            name="beegen_executor",
            available_bots=available_bots,
            inputs=INPUT,
            outputs=OUTPUT,
        )
        START >> executor >> END
 
    wf.compile()
 
    outputs = await wf.run(
        inputs={
            "bot_id": bot_id,
            "bot_inputs": {
    "messages": [
        {
            "role": "user",
            "content": "Đất thuộc diện/có nguy cơ bị thu hồi theo quy định pháp luật bao gồm những gì?"
        }
    ],
    "role_ids": [
        "QM",
        "MY VIP",
        "SPK",
        "CRU",
        "APP",
        "Team 2",
        "Team 3",
        "L2",
        "L3"
    ],
    "topic": "default"
}
        }
    )
 
    print("\n--- result ---")
    print(outputs.get("result", ""))
 
 
if __name__ == "__main__":
    asyncio.run(main())