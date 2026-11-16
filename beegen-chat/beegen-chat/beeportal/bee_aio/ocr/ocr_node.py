from typing import Any, Dict, List, Optional

from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.templates.basic_chain_node import BasicChainNode
from beeflow.nodes.flow.for_loop_node import ForLoopNode
from beeflow.configs.node_config import NodeType
from beeflow.nodes.primitives.data.mongo_node import MongoNode


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def is_image(metadata: Dict[str, Any]) -> Dict[str, Any]:
    images: List[Dict] = metadata.get("images", [])
    return {"is_image": bool(images)}


def extract_image(
    metadata: Dict[str, Any],
    messages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Phân tách images thành 2 nhóm:
      - image_last_message  : ảnh ở lượt cuối cùng → cần OCR
      - image_conversation  : ảnh ở các lượt trước → lấy nội dung từ Mongo
    """
    images: List[Dict] = metadata.get("images", [])
    last_turn_index = len(messages) - 1

    last_message_images: List[Dict] = []
    conversation_images: List[Dict] = []

    for img in images:
        if "turn_index" not in img:
            continue
        if img["turn_index"] == last_turn_index:
            last_message_images.append(img)
        else:
            conversation_images.append(img)

    return {
        "is_image_last_message": bool(last_message_images),
        "image_last_message":    last_message_images,
        "image_conversation":    conversation_images,
        "is_image_conversation": bool(conversation_images),
    }


def passthrough_messages(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Không có ảnh → trả nguyên messages gốc."""
    return {"reconstructed_messages": messages}


def build_mongo_query(images: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Tạo query Mongo để lấy content cho các ảnh trong conversation.
    _id dạng uuid4 string.
    """
    ids = [img["id"] for img in images]
    return {
        "mongo_query": {"_id": {"$in": ids}}
    }

# def build_batch_ocr(data: List[Dict[str, Any]]) -> Dict[str, Any]:
#     """
#     Tạo query Mongo để lấy content cho các ảnh trong conversation.
#     _id dạng uuid4 string.
#     """
#     ids = [img["id"] for img in images]
#     return {
#         "mongo_query": {"_id": {"$in": ids}}
#     }


def merge_ocr_and_mongo(
    messages: List[Dict[str, Any]],
    image_last_message: List[Dict[str, Any]],
    image_conversation: List[Dict[str, Any]],
    ocr_results: Optional[List[str]],
    mongo_docs: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """
    Gộp kết quả OCR (last message) và Mongo (conversation images)
    vào đúng turn_index trong messages.

    - last_message_images  : gắn inline dạng image_url + text OCR
    - conversation_images  : gắn inline dạng image_url + text từ Mongo tags
    """
    # ── Build lookup: turn_index → list of {url, text} ───────────────────
    images_by_turn: Dict[int, List[Dict]] = {}

    # Nhóm 1: last message → dùng ocr_results
    ocr_results = ocr_results or []
    for img, ocr_text in zip(image_last_message, ocr_results):
        idx = img["turn_index"]
        images_by_turn.setdefault(idx, []).append({
            "id":      img["id"],
            "ocr_text": ocr_text,
        })

    # Nhóm 2: conversation → dùng content lấy từ Mongo
    mongo_docs = mongo_docs or []
    doc_by_id: Dict[str, Dict] = {str(d["_id"]): d for d in mongo_docs}
    for img in image_conversation:
        idx  = img["turn_index"]
        doc  = doc_by_id.get(str(img["id"]), {})
        text = doc.get("content") or " ".join(doc.get("_id", [])) or ""
        images_by_turn.setdefault(idx, []).append({
            "id":      img["id"],
            "ocr_text": text,
        })

    # ── Reconstruct messages ──────────────────────────────────────────────
    reconstructed: List[Dict] = []
    for i, msg in enumerate(messages):
        items = images_by_turn.get(i)
        if not items:
            reconstructed.append(msg)
            continue

        content_blocks: List[Dict] = []
        for item in items:
            content_blocks.append({
                "type":      "image_url",
                "image_url": {"url": f"id:{item['id']}"},  # caller resolve thành URL thật
            })
        content_blocks.append({
            "type": "text",
            "text": msg.get("content", ""),
        })
        reconstructed.append({**msg, "content": content_blocks})

    return {"reconstructed_messages": reconstructed}


# ---------------------------------------------------------------------------
# OcrNode
# ---------------------------------------------------------------------------

class OcrNode(GraphNode):
    """
    GraphNode xử lý ảnh từ metadata.images:

    Luồng:
        1. check_images           — có ảnh không?
           └─ Không               → passthrough_messages → END
           └─ Có                  → extract_image

        2. extract_image          — tách last_message_images vs conversation_images
           Hai nhánh chạy độc lập:
           ├─ is_image_last_message → _batch_ocr (ForLoopNode + llm_ocr_image)
           └─ is_image_conversation → build_mongo_query → mongo_get_image

        3. merge_ocr_and_mongo    — gộp kết quả, gắn inline theo turn_index → END

    Input schema:
        messages : List[Dict]   — conversation history
        metadata : Dict         — {"images": [{"id": uuid4_str, "turn_index": int}, ...]}

    Output schema:
        reconstructed_messages : List[Dict]   — messages đã gắn ảnh inline đúng turn
    """

    type: NodeType = "graph"

    def __init__(
        self,
        ocr_resource_key: str = "qwen-vl-chat",
        mongo_resource_key: str = "aicenter-chatbot",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.ocr_resource_key   = ocr_resource_key
        self.mongo_resource_key = mongo_resource_key
        self._build_graph()

    def _build_graph(self):
        with self:

            # ── Bước 1: kiểm tra có ảnh không ───────────────────────────────
            _check = CodeNode(
                name="check_images",
                code_fn=is_image,
                inputs={"metadata": INPUT["metadata"]},
                return_keys=["is_image: bool"],
            )

            # ── Branch chính: có ảnh → extract, không → passthrough ──────────
            _branch_main = BranchNode(
                name="branch_has_images",
                inputs={"is_image": _check},
                cases={"is_image == True": "extract_image"},
                default="passthrough_messages",
            )

            # ── Path A (default): không có ảnh ──────────────────────────────
            _passthrough = CodeNode(
                name="passthrough_messages",
                code_fn=passthrough_messages,
                inputs={"messages": INPUT["messages"]},
                return_keys=["reconstructed_messages: List[Dict]"],
                outputs=OUTPUT,
            )

            # ── Bước 2: tách ảnh theo turn ──────────────────────────────────
            _extract = CodeNode(
                name="extract_image",
                code_fn=extract_image,
                inputs={
                    "metadata": INPUT["metadata"],
                    "messages": INPUT["messages"],
                },
                return_keys=[
                    "is_image_last_message: bool",
                    "image_last_message: List[Dict]",
                    "image_conversation: List[Dict]",
                    "is_image_conversation: bool",
                ],
            )

            # ── Branch con 1: last message images → batch OCR ───────────────
            _branch_last = BranchNode(
                name="branch_last_message",
                inputs={"is_image_last_message": _extract},
                cases={"is_image_last_message == True": "_get_base_content_query"},
                default="skip_ocr",
            )

            # Skip OCR — trả list rỗng để merge không bị thiếu key
            _skip_ocr = CodeNode(
                name="skip_ocr",
                code_fn=lambda: {"ocr_results": []},
                inputs={},
                return_keys=["ocr_results: List[str]"],
            )

            # # Prepare for loop node
            _get_base_content_query= CodeNode(
                name= "_get_base_content_query",
                code_fn= build_mongo_query,
                inputs= {
                    "images": _extract["image_last_message"]
                },
                return_keys=["mongo_query: Dict"]
            )

            # Lấy base64 từ Mongo
            _mongo_get_base = MongoNode(
                name="mongo_get_image",
                resource_key=self.mongo_resource_key,
                operation="find",
                inputs={
                    "collection_name": "multimedia",
                    "query":           _get_base_content_query["mongo_query"],
                    "projection":      {"base_content": 1, "_id":0},
                },
            )

            # ForLoopNode: OCR từng ảnh ở last message
            with ForLoopNode(
                name="_batch_ocr",
                inputs={"batch_data": _mongo_get_base["data"]},
                outputs={"batch_result": {OUTPUT: "ocr_results"}},
            ) as _batch_ocr:

                _llm_ocr = BasicChainNode(
                    name="llm_ocr_image",
                    resource_key=self.ocr_resource_key,
                    messages_template=[
                        {
                            "role":    "system",
                            "content": "Bạn là chuyên gia bóc tách thông tin trong ảnh.",
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Trích xuất toàn bộ thông tin có trong ảnh, "
                                        "chỉ trả thông tin đã bóc tách. "
                                        "Không giải thích hay yêu cầu gì thêm."
                                    ),
                                },
                                {
                                    "type":      "image_url",
                                    "image_url": {"url": "data:image/png;base64,{image_data}"},
                                },
                            ],
                        },
                    ],
                    inputs={"image_data": {INPUT: "base_content"}},
                    outputs=OUTPUT,
                    stream=False,
                )

                START >> _llm_ocr >> END

            # ── Branch con 2: conversation images → Mongo ───────────────────
            _branch_conv = BranchNode(
                name="branch_conversation",
                inputs={"is_image_conversation": _extract},
                cases={"is_image_conversation == True": "_build_query"},
                default="skip_mongo",
            )

            # Skip Mongo — trả list rỗng
            _skip_mongo = CodeNode(
                name="skip_mongo",
                code_fn=lambda: {"mongo_docs": []},
                inputs={},
                return_keys=["mongo_docs: List[Dict]"],
            )

            # Tạo query _id $in [uuid4, ...]
            _build_query = CodeNode(
                name="_build_query",
                code_fn=build_mongo_query,
                inputs={"images": _extract["image_conversation"]},
                return_keys=["mongo_query: Dict"],
            )

            # Lấy content/tags từ Mongo
            _mongo_get = MongoNode(
                name="mongo_get_image",
                resource_key=self.mongo_resource_key,
                operation="find",
                inputs={
                    "collection_name": "multimedia",
                    "query":           _build_query["mongo_query"],
                    "projection":      {"content": 1, "_id": 1},
                },
                # return_keys=["mongo_docs: List[Dict]"],
            )

            # ── Bước 3: merge cả hai nhánh → reconstruct ────────────────────
            _merge = CodeNode(
                name="merge_ocr_and_mongo",
                code_fn=merge_ocr_and_mongo,
                inputs={
                    "messages":            INPUT["messages"],
                    "image_last_message":  _extract["image_last_message"],
                    "image_conversation":  _extract["image_conversation"],
                    # Lấy từ nhánh nào có giá trị (batch_ocr hoặc skip_ocr)
                    "ocr_results":         [_batch_ocr, _skip_ocr],
                    # Lấy từ nhánh nào có giá trị (mongo_get hoặc skip_mongo)
                    "mongo_docs":          [_mongo_get, _skip_mongo],
                },
                return_keys=["reconstructed_messages: List[Dict]"],
                outputs=OUTPUT,
            )

            # ── Graph edges ──────────────────────────────────────────────────
            START >> _check >> _branch_main

            # Path A: không có ảnh
            _branch_main >> [_passthrough,
                             _extract] 

            # Path B: có ảnh
            _passthrough >> END

            # Nhánh 1 (song song): last message OCR
            _extract >> [_branch_last,
                         _branch_conv] 
            
            _branch_last >> [_get_base_content_query,
                             _skip_ocr]
            _skip_ocr >> END
            _get_base_content_query >> _mongo_get_base >> _batch_ocr >> END

            # Nhánh 2 (song song): conversation Mongo
            _branch_conv >> [_build_query,
                             _skip_mongo]
            _build_query >> _mongo_get >> END
            _skip_mongo >> END

            # Merge sau khi cả 2 nhánh xong
            # [_batch_ocr, _skip_ocr, _mongo_get, _skip_mongo] >> _merge >> END

        self.build()


# ---------------------------------------------------------------------------
# Local tests
# ---------------------------------------------------------------------------

async def test_with_images():
    """Có cả last_message_images lẫn conversation_images."""
    from beeflow.nodes.base_node import INPUT, OUTPUT
    from beeflow.states.workflow_indexer import WorkflowIndexer
    from beeflow.states.workflow_state import WorkflowState

    ocr_node = OcrNode(
        name="ocr_node",
        ocr_resource_key="qwen-vl-chat",
        inputs=INPUT,
        outputs=OUTPUT,
    )
    indexer = WorkflowIndexer(name="wf_ocr_01").add_node(ocr_node).build()
    state = WorkflowState(
        indexer=indexer,
        inputs={
            "messages": [
                {"role": "user",      "content": "Đây là hợp đồng vay của tôi"},
                {"role": "assistant", "content": "Tôi thấy hợp đồng của bạn..."},
                {"role": "user",      "content": "Điều khoản số 3 có vấn đề gì không?"},
            ],
            "metadata": {
                "images": [
                    # Ảnh ở turn 0 (conversation) → lấy từ Mongo
                    {"id": "a6ce94f1-0766-4848-8921-39a334903459", "turn_index": 0},
                    # Ảnh ở turn 2 (last message) → OCR
                    {"id": "a6ce94f1-0766-4848-8921-39a334114921", "turn_index": 2},
                    {"id": "a6ce94f1-0766-4848-8921-39a334903459", "turn_index": 2},
                ],
            },
        },
    )
    await ocr_node.run(state=state)
    print("=== test_with_images ===")
    print(ocr_node.get_result(state))


async def test_no_images():
    """Không có ảnh → passthrough."""
    from beeflow.nodes.base_node import INPUT, OUTPUT
    from beeflow.states.workflow_indexer import WorkflowIndexer
    from beeflow.states.workflow_state import WorkflowState

    ocr_node = OcrNode(
        name="ocr_no_img",
        ocr_resource_key="qwen-vl-chat",
        inputs=INPUT,
        outputs=OUTPUT,
    )
    indexer = WorkflowIndexer(name="wf_ocr_02").add_node(ocr_node).build()
    state = WorkflowState(
        indexer=indexer,
        inputs={
            "messages": [
                {"role": "user", "content": "Tôi muốn hỏi về lãi suất"},
            ],
            "metadata": {},
        },
    )
    await ocr_node.run(state=state)
    print("=== test_no_images ===")
    print(ocr_node.get_result(state))


async def test_only_last_message():
    """Chỉ có ảnh ở last message → chỉ chạy OCR, không Mongo."""
    from beeflow.nodes.base_node import INPUT, OUTPUT
    from beeflow.states.workflow_indexer import WorkflowIndexer
    from beeflow.states.workflow_state import WorkflowState

    ocr_node = OcrNode(
        name="ocr_last_only",
        ocr_resource_key="qwen-vl-chat",
        inputs=INPUT,
        outputs=OUTPUT,
    )
    indexer = WorkflowIndexer(name="wf_ocr_03").add_node(ocr_node).build()
    state = WorkflowState(
        indexer=indexer,
        inputs={
            "messages": [
                {"role": "user", "content": "Ảnh này là gì?"},
            ],
            "metadata": {
                "images": [
                    {"id": "a6ce94f1-0766-4848-8921-39a334903459", "turn_index": 0},
                ],
            },
        },
    )
    await ocr_node.run(state=state)
    print("=== test_only_last_message ===")
    print(ocr_node.get_result(state))


async def test_only_conversation():
    """Chỉ có ảnh trong conversation → chỉ chạy Mongo, không OCR."""
    from beeflow.nodes.base_node import INPUT, OUTPUT
    from beeflow.states.workflow_indexer import WorkflowIndexer
    from beeflow.states.workflow_state import WorkflowState

    ocr_node = OcrNode(
        name="ocr_conv_only",
        ocr_resource_key="qwen-vl-chat",
        inputs=INPUT,
        outputs=OUTPUT,
    )
    indexer = WorkflowIndexer(name="wf_ocr_04").add_node(ocr_node).build()
    state = WorkflowState(
        indexer=indexer,
        inputs={
            "messages": [
                {"role": "user",      "content": "Đây là hợp đồng"},
                {"role": "assistant", "content": "Tôi thấy rồi"},
                {"role": "user",      "content": "Còn vấn đề gì không?"},
            ],
            "metadata": {
                "images": [
                    # Chỉ có ảnh ở turn 0 (không phải last)
                    {"id": "a6ce94f1-0766-4848-8921-39a334903459", "turn_index": 0},
                ],
            },
        },
    )
    await ocr_node.run(state=state)
    print("=== test_only_conversation ===")
    print(ocr_node.get_result(state))


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_with_images())