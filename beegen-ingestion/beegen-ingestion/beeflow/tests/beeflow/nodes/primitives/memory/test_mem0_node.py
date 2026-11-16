import os
import asyncio
from beeflow.nodes.primitives.memory.mem0_node import Mem0Node
from beegen.configs.memory.mem0_config import (
    Mem0Operation,
    MEM0_OPERATION_INPUTS,
    MEM0_OPERATION_OUTPUTS,
)

from beeflow.states.workflow_indexer import WorkflowIndexer
from beeflow.states.workflow_state import WorkflowState
from beeflow.nodes.base_node import INPUT, OUTPUT
from beegen.prompts.prompt_manager import PromptManager
PROMPTS = PromptManager("beegen")

import uuid
TEST_USER_ID = "cuongkn"
import uuid
TEST_SESSION_ID = str(uuid.uuid4())
MESSAGES_TO_ADD = [
{"role": "user", "content": "Tôi muốn Tất toán trước hạn trả góp qua thẻ tín dụng"},
{"role": "assistant", "content": (
    "Chào bạn! Tôi rất vui được hỗ trợ bạn hôm nay.\n"
    "Để tất toán trước hạn khoản trả góp qua thẻ tín dụng, bạn cần đáp ứng các điều kiện sau:\n"
    " 1. Thanh toán toàn bộ dư nợ thẻ tín dụng tính đến thời điểm yêu cầu tất toán, ngoại trừ dư nợ trả góp chưa lên sao kê.\n"
    " 2. Thanh toán phí tất toán trước hạn trả góp, trừ trường hợp bạn đã đăng ký hình thức thanh toán phí một lần.\n"
    " 3. Cách tính phí tất toán trước hạn trả góp: Phí tất toán trước hạn = 2% * số tiền đăng ký trả góp (tối thiểu 100,000 VND).\n"
    "Lưu ý: Phí này sẽ được trừ vào hạn mức thẻ tín dụng của bạn.\n"
    "Ngoài ra, phí quản lý trả góp của các kỳ còn lại chưa lên sao kê sẽ được miễn, trừ trường hợp bạn đã đăng ký hình thức thanh toán phí một lần.\n"
    "Nếu bạn cần thêm thông tin hoặc hỗ trợ, vui lòng cho tôi biết nhé!"
)},
]
SEARCH_QUERY = "thẻ tín dụng"

# os.environ["OPENAI_API_KEY"] = "sk-_FcF3ua4t3rRfFtmTJQgHQ"

# 1. Test ADD operation with predefined messages

async def main():

    add_node = Mem0Node(
        name="mem0_add",
        resource_key="mem0-test",
        operation=Mem0Operation.ADD,
        inputs={
            # "custom_fact_extraction_prompt": "",
            "messages": INPUT,
            # "user_id": INPUT,
            "session_id": INPUT,
            "custom_fact_extraction_prompt": PROMPTS["BEE247:CUSTOM_FACT_EXTRACTION_PROMPT"]
        },
        outputs=OUTPUT,
    )

    add_indexer = WorkflowIndexer(name="workflow_mem0_add").add_node(add_node).build()

    add_state = WorkflowState(
        indexer=add_indexer,
        inputs={
            "messages": MESSAGES_TO_ADD,
            # "user_id": TEST_USER_ID,
            "session_id": TEST_SESSION_ID,
        },
    )

    print("--- Running ADD operation ---")
    await add_node.run(state=add_state)
    print("ADD output:", add_node.get_outputs(add_state, None))

    print(add_node.trace_data(add_state, None))

    # 2. Test GET_HISTORY operation scoped to the same identifiers
    history_node = Mem0Node(
        name="mem0_get_history",
        resource_key="mem0-test",
        operation=Mem0Operation.GET_HISTORY,
        inputs={
            # "user_id": INPUT,
            "session_id": INPUT,
        },
        outputs=OUTPUT,
    )

    history_indexer = WorkflowIndexer(name="workflow_mem0_history").add_node(history_node).build()

    history_state = WorkflowState(
        indexer=history_indexer,
        inputs={
            # "user_id": TEST_USER_ID,
            "session_id": TEST_SESSION_ID,
        },
    )

    print("\n--- Running GET_HISTORY operation ---")
    await history_node.run(state=history_state)
    print("GET_HISTORY output:", history_node.get_outputs(history_state, None))

    # 3. Test SEARCH operation with a query related to the added messages
    search_node = Mem0Node(
        name="mem0_search",
        resource_key="mem0-test",
        operation=Mem0Operation.SEARCH,
        inputs={
            "query": INPUT,
            # "user_id": INPUT,
            "session_id": INPUT,
        },
        outputs=OUTPUT,
    )

    search_indexer = WorkflowIndexer(name="workflow_mem0_search").add_node(search_node).build()

    search_state = WorkflowState(
        indexer=search_indexer,
        inputs={
            "query": SEARCH_QUERY,
            # "user_id": TEST_USER_ID,
            "session_id": TEST_SESSION_ID,
        },
    )

    print("\n--- Running SEARCH operation ---")
    await search_node.run(state=search_state)
    print("SEARCH input query:", SEARCH_QUERY)
    print("SEARCH output:", search_node.get_outputs(search_state, None))


if __name__ == "__main__":
    asyncio.run(main())