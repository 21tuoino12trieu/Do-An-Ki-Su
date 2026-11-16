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
from beeflow.nodes.primitives.data.sql_node import SQLNode
from beeflow.nodes.primitives.ai.llm_node import LLMNode
from beeflow.nodes.templates.retriever_node_v3 import RetrieverNodeV3
from beeflow.utils.streaming import STREAM_SERVICE
from beeflow.workflow import WorkflowEngine
from beegen.registry.resource_hub import ResourceHub
from beegen.utils.common import transform_bot_id
from beegen.configs.storage.mongo_config import MongoOperation
from beegen.configs.cache.redis_config import RedisOperation
from beegen.configs.storage.sql_config import SQLOperation

from beegenerate.llms.llm_response import fake_chunk_from
from beeportal.utils import PROMPTS, init_query
from beegen.tools.schema.param import ParamSet
from beeportal.bot_hr.pev_fc_agent_node import PlanExecuteVerifyAgentNode

# =========================================================
# SYSTEM PROMPT CHO BOT HR (HCM + RAG)
# =========================================================
HR_BOT_SYSTEM_PROMPT = """
Bạn là trợ lý AI của hệ thống HR tại MB Bank. Nhiệm vụ của bạn là cung cấp thông tin từ tài liệu nội bộ của MB.

Bạn có 2 loại công cụ (tools) chính:

## 1. HCM TOOLS (Công cụ thông tin nhân sự cá nhân)
Các tool này truy vấn dữ liệu nhân sự từ hệ thống HCM của MB Bank dựa trên username của người dùng hiện tại.

- **get_employee_basic_info**: Lấy thông tin nhân sự cơ bản (hồ sơ, quá trình công tác, hợp đồng, vị trí kiêm nhiệm, thâm niên)
- **get_employee_benefits**: Lấy thông tin phúc lợi (nghỉ phép, phép năm, bằng cấp/chứng chỉ, khen thưởng)
- **get_employee_review**: Lấy thông tin đánh giá (kết quả đánh giá kỳ, thông tin Đảng/quân nhân, quá trình trước MB)

## 2. RAG TOOLS (Công cụ tra cứu tài liệu)
Các tool này tìm kiếm thông tin trong knowledge base của MB Bank.

- **get_kb_structure**: [DÙNG ĐẦU TIÊN] Lấy cấu trúc toàn bộ knowledge base dạng cây: danh mục (category) -> danh sách tài liệu kèm ID. Gọi tool này khi bắt đầu hội thoại để biết KB có những tài liệu gì, từ đó định hướng tra cứu chính xác.
- **retrieval_graph**: Tìm kiếm tài liệu bằng vector search trong knowledge base
- **get_document_content**: Lấy nội dung chi tiết của một tài liệu theo ID
- **search_documents**: Tìm kiếm tài liệu theo từ khóa

## 3. QA TOOLS (Công cụ tra cứu câu hỏi mẫu)
Tool này tìm kiếm trong bộ câu hỏi & trả lời có sẵn (Q&A dialogue).

- **search_dialogue**: Tìm kiếm câu hỏi mẫu (Q&A) bằng từ khóa, trả về câu hỏi và câu trả lời tương ứng
Ví dụ: "Đường dẫn HCM là gì?" → search_dialogue

## 4. HR CONSULTATION TOOL (Tạo yêu cầu tư vấn trực tiếp)
Tool này cho phép người dùng tạo yêu cầu tư vấn trực tiếp từ Khối tổ chức nhân sự.

- **request_hr_consultation**: Tạo yêu cầu tư vấn trực tiếp từ phòng Nhân sự khi:
  - Thông tin bot cung cấp chưa đầy đủ hoặc chưa rõ ràng
  - Tình huống thực tế phức tạp, cần chuyên gia tư vấn trực tiếp
  - Thông tin bot trả lời có thể sai sót gây tổn thất cho người dùng
  - Các trường hợp đặc thù không nằm trong tài liệu có sẵn

## HƯỚNG DẪN SỬ DỤNG TOOLS:

### Khi người dùng hỏi về THÔNG TIN CÁ NHÂN của họ:
→ Sử dụng HCM TOOLS phù hợp:
   - **get_employee_basic_info**: profile, chức danh, hợp đồng, thâm niên, quá trình công tác
   - **get_employee_benefits**: phép, bằng cấp, khen thưởng
   - **get_employee_review**: đánh giá, Đảng, quá trình trước MB
Ví dụ: "Chức danh của tôi là gì?" → get_employee_basic_info


### Khi người dùng hỏi CẢ HAI:
→ Có thể kết hợp cả HCM TOOLS và RAG TOOLS
Ví dụ: "Tôi còn bao nhiêu ngày phép và quy định nghỉ phép như thế nào?"

## LƯU Ý:
- **search_dialogue** (QA TOOL): Dùng để tra cứu câu hỏi & trả lời có sẵn — kết quả có thể dùng để trả lời nhanh mà không cần tra thêm nguồn khác


## PHẠM VI TRẢ LỜI HỎI ĐÁP & KẾT LUẬN
- Bạn chỉ được sử dụng những thông tin tìm kiếm được để phản hồi cho người dùng, không được đưa ra các kết luận. Chỉ phân tích dựa trên các tài liệu hiện có.
- Để biết rõ hơn phạm vi trả lời nội bộ, nên khám phá những đầu tài liệu hiện có ngay từ bước đầu tiên trước khi tìm kiếm.

## LƯU Ý QUAN TRỌNG:
- Linh hoạt sử dụng các tool để tìm được câu trả lời
- Luôn trả lời bằng tiếng Việt
- Nếu không tìm thấy thông tin, thông báo cho người dùng một cách lịch sự
- **Nếu thông tin tìm được không đầy đủ hoặc câu hỏi thuộc tình huống phức tạp, hãy đề xuất người dùng sử dụng công cụ nội bộ để được tư vấn trực tiếp từ Khối tổ chức nhân sự**
- Thông tin nhân sự là BÍ MẬT - chỉ cung cấp khi được yêu cầu bởi chính người đó
- Không cho phép người dùng hỏi thông tin của user khác
- Hạn chế đưa thông tin gây khó hiểu của hệ thống vào trong câu trả lời
- Chỉ dùng thông tin tìm kiếm được để trả lời.
"""


# =========================================================
# HÀM HỖ TRỢ
# =========================================================
def create_mongo_query(document_id: str, page: int = 1) -> Dict[str, Any]:
    """Create a MongoDB query to fetch documents by IDs."""
    return {
        "query": {"document_id": document_id},
        "skip": (page - 1) * 10
    }

def create_search_query(bot_id: str, keyword: str, allowed_ids: list = None) -> Dict[str, Any]:
    """Create a MongoDB query to search documents by keyword, filtered by allowed doc IDs."""
    query = {
        "bot_id": bot_id,
        "$or": [
            {"title": {"$regex": keyword, "$options": "i"}},
            {"content": {"$regex": keyword, "$options": "i"}},
            {"tags": {"$regex": keyword, "$options": "i"}},
        ]
    }
    if allowed_ids:
        query["document_id"] = {"$in": allowed_ids}
    return {"query": query}

def build_doc_access_query(document_id: str, role_uuids: list = None) -> Dict[str, Any]:
    """Build query to check if a document is accessible by given role UUIDs."""
    role_filter = {"$or": [{"role_ids": {"$exists": False}}]}
    if role_uuids:
        role_filter["$or"].append({"role_ids": {"$in": role_uuids}})
    return {"query": {"$and": [{"_id": document_id}, role_filter]}}

def extract_accessible_doc_id(docs_data: list) -> Dict[str, Any]:
    """Pass through document_id if doc is accessible, else None."""
    if docs_data:
        return {"doc_id": docs_data[0]["_id"]}
    return {"doc_id": None}

def check_doc_access_and_build_query(doc_id: Any, original_query_fn_result: dict) -> Dict[str, Any]:
    """Only build document_data query if doc access check passed."""
    if not doc_id:
        return {"query": {"_id": "NONEXISTENT"}, "skip": 0}
    return original_query_fn_result

def build_allowed_docs_query(bot_id: str, role_uuids: list = None) -> Dict[str, Any]:
    """Build query to get all document IDs accessible by given roles."""
    role_filter = {"$or": [{"role_ids": {"$exists": False}}]}
    if role_uuids:
        role_filter["$or"].append({"role_ids": {"$in": role_uuids}})
    return {"query": {"$and": [{"bot_id": bot_id}, role_filter]}}

def extract_allowed_doc_ids(docs_data: list) -> Dict[str, list]:
    """Extract list of allowed document _id values."""
    if not docs_data:
        return {"allowed_ids": []}
    return {"allowed_ids": [d["_id"] for d in docs_data if d.get("_id")]}

def build_kb_documents_query(bot_id: str, role_uuids: list = None) -> Dict[str, Any]:
    """Build MongoDB query for all documents accessible by given roles."""
    base_query = {"bot_id": bot_id}
    role_filter = {"$or": [{"role_ids": {"$exists": False}}]}
    if role_uuids:
        role_filter["$or"].append({"role_ids": {"$in": role_uuids}})
    return {"query": {"$and": [base_query, role_filter]}}

def assemble_kb_tree(categories_data: list, documents_data: list) -> Dict[str, Any]:
    """Assemble category -> documents tree structure from KB collections."""
    cat_map = {}
    for cat in (categories_data or []):
        cat_id = str(cat.get("_id", ""))
        if cat_id:
            cat_map[cat_id] = cat.get("name", "Unnamed")

    doc_by_cat = {}
    for doc in (documents_data or []):
        cat_id = doc.get("category_id", "") or ""
        doc_info = {
            "id": str(doc.get("_id", "")),
            "name": doc.get("doc_name", "Unnamed")
        }
        doc_by_cat.setdefault(cat_id, []).append(doc_info)

    categories = []
    seen_cat_ids = set()
    for cat_id, cat_name in cat_map.items():
        categories.append({
            "category_id": cat_id,
            "category_name": cat_name,
            "documents": doc_by_cat.get(cat_id, []),
            "document_count": len(doc_by_cat.get(cat_id, []))
        })
        seen_cat_ids.add(cat_id)

    uncategorized = []
    for cat_id, docs in doc_by_cat.items():
        if cat_id and cat_id not in seen_cat_ids:
            uncategorized.extend(docs)
    uncategorized.extend(doc_by_cat.get("", []))

    result = {
        "kb_structure": {
            "categories": categories,
            "total_categories": len(categories),
            "total_documents": len(documents_data or []),
        }
    }
    if uncategorized:
        result["kb_structure"]["uncategorized_documents"] = uncategorized

    return {"result": result}

def search_dialogue_query(bot_id: str, keyword: str, role_uuids: list = None) -> Dict[str, Any]:
    """Create a MongoDB query to search Q&A dialogues by keyword, filtered by roles."""
    # Base keyword filter
    keyword_filter = {
        "$or": [
            {"name": {"$regex": keyword, "$options": "i"}},
            {"questions.text": {"$regex": keyword, "$options": "i"}},
            {"answers.text": {"$regex": keyword, "$options": "i"}},
            {"tags": {"$regex": keyword, "$options": "i"}},
        ]
    }
    # Role filter: public + matching roles
    role_filter = {"$or": [{"role_ids": {"$exists": False}}]}
    if role_uuids:
        role_filter["$or"].append({"role_ids": {"$in": role_uuids}})
    return {"query": {"$and": [{"bot_id": bot_id, "deleted": {"$ne": True}}, keyword_filter, role_filter]}}

def prepare_hr_request(subject: str, description: str, sensitive_keys: dict) -> Dict[str, Any]:
    """Mock: Prepare a fake HR consultation request confirmation."""
    import uuid
    from datetime import datetime
    ticket_id = f"HR-{uuid.uuid4().hex[:8].upper()}"
    return {
        "result": {
            "ticket_id": ticket_id,
            "subject": subject,
            "description": description,
            "username": sensitive_keys.get("username", "unknown"),
            "status": "pending",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": f"Yêu cầu tư vấn đã được ghi nhận. Mã yêu cầu: {ticket_id}. Khối tổ chức nhân sự sẽ liên hệ với bạn trong thời gian sớm nhất. (Chú ý rằng tính năng đang trong quá trình phát triển)"
        }
    }

def get_session_key(session_id: str = None, role_ids: str = None) -> Dict[str, str]:
    """Extract session_id from INPUT and use as Redis key."""
    return {"key": "beeHR:" + session_id or None}

def prepare_list_documents_query(bot_id: str, category_id: str = "all", role_uuids: list = None) -> Dict[str, Any]:
    """Create MongoDB query for list documents, filtered by role UUIDs."""
    query = {"bot_id": bot_id}
    if category_id and category_id != "all":
        query["category_id"] = category_id

    # Filter by roles: public docs (no role_ids field) + docs matching user's roles
    role_filter = {
        "$or": [
            {"role_ids": {"$exists": False}},
        ]
    }
    if role_uuids:
        role_filter["$or"].append({"role_ids": {"$in": role_uuids}})

    return {"query": {"$and": [query, role_filter]}}

def prepare_role_lookup_query(role_names: list, bot_id: str) -> Dict[str, Any]:
    """Build query to find role UUIDs by role names."""
    return {
        "query": {
            "bot_id": bot_id,
            "role_name": {"$in": role_names}
        }
    }

def extract_role_uuids(roles_data: list) -> Dict[str, list]:
    """Extract list of role _id UUIDs from roles collection result."""
    if not roles_data:
        return {"role_uuids": []}
    return {"role_uuids": [r["_id"] for r in roles_data if r.get("_id")]}

def prepare_input_agent(messages_new, sensitive_keys_in, state):
    """Prepare input messages for the agent by appending the latest user message."""
    if not state:
        return {
            'messages': messages_new,
            'sensitive_keys': sensitive_keys_in
        }
    parsed_state = json.loads(state)
    return {
        'messages': parsed_state + [messages_new[-1]],
        'sensitive_keys': sensitive_keys_in
    }

def prepare_input_tool(sensitive_keys_in):
    return {
        'sensitive_keys': sensitive_keys_in
    }

def extract_role_ids_from_keys(sensitive_keys: dict) -> list:
    """Extract role_ids from sensitive_keys dict."""
 
    return {
        'role_ids': sensitive_keys['role_ids']
    }


# =========================================================
# HCM TOOLS - Gộp query helpers theo nhóm
# =========================================================
# ---- Prepared query specs (dùng trong SQLNode) ----
QUERY_PROFILE = """
    SELECT username, employeeid, employeecode, fullname, dateofbirth, flagstatus
    FROM chatbot_beehi_hcm.beehi_base_emp_info
    WHERE username = %(username)s
"""
QUERY_WORK_HISTORY = """
    SELECT e.username, w.jobname, w.orgnamemanage, w.orgnamelevel1, w.orgnamelevel2, w.orgnamelevel3,
           w.joincompanydate, w.fromdate, w.todate, w.status, w.level, w.documenttype
    FROM chatbot_beehi_hcm.beehi_emp_mb_process_info w
    INNER JOIN chatbot_beehi_hcm.beehi_base_emp_info e ON w.employeeid = e.employeeid
    WHERE e.username = %(username)s
    ORDER BY w.fromdate DESC
"""
QUERY_CONTRACT = """
    SELECT e.username, c.contracttype, c.contractnumber, c.fromdate, c.todate, c.status
    FROM chatbot_beehi_hcm.beehi_emp_contract_process_info c
    INNER JOIN chatbot_beehi_hcm.beehi_base_emp_info e ON c.employeeid = e.employeeid
    WHERE e.username = %(username)s
    ORDER BY c.fromdate DESC
"""
QUERY_CONCURRENT = """
    SELECT e.username, c.jobname, c.orgnamemanage, c.fromdate, c.todate, c.status
    FROM chatbot_beehi_hcm.beehi_emp_concurrent_process_info c
    INNER JOIN chatbot_beehi_hcm.beehi_base_emp_info e ON c.employeeid = e.employeeid
    WHERE e.username = %(username)s
    ORDER BY c.fromdate DESC
"""
QUERY_SENIORITY = """
    SELECT e.username, s.senioritymb, s.posseniority
    FROM chatbot_beehi_hcm.beehi_emp_seniority_info s
    INNER JOIN chatbot_beehi_hcm.beehi_base_emp_info e ON s.employeeid = e.employeeid
    WHERE e.username = %(username)s
"""
QUERY_EDUCATION = """
    SELECT e.username, d.degreetype, d.majorlevel, d.school, d.faculities, d.certificatename, d.certificateplace, d.certificateresult, d.todate
    FROM chatbot_beehi_hcm.beehi_emp_degree_info d
    INNER JOIN chatbot_beehi_hcm.beehi_base_emp_info e ON d.employeeid = e.employeeid
    WHERE e.username = %(username)s
"""
QUERY_LEAVE = """
    SELECT e.username, l.leavetype, l.fromtime, l.totime, l.useddays, l.status
    FROM chatbot_beehi_hcm.beehi_emp_leave_info l
    INNER JOIN chatbot_beehi_hcm.beehi_base_emp_info e ON l.employeeid = e.employeeid
    WHERE e.username = %(username)s AND l.status = 'Đã phê duyệt'
    ORDER BY l.fromtime DESC
"""
QUERY_ANNUAL_LEAVE = """
    SELECT e.username, a.year, a.totaldays, a.remaindays, a.useddays, a.posbonusdays, a.annualdays, a.annualdays, a.useswitcheddays, a.fromdate, a.seniorbonusdays
    FROM chatbot_beehi_hcm.beehi_emp_annual_leave_info a
    INNER JOIN chatbot_beehi_hcm.beehi_base_emp_info e ON a.employeeid = e.employeeid
    WHERE e.username = %(username)s
    ORDER BY a.year DESC
    LIMIT 1
"""
QUERY_AWARDS = """
    SELECT e.username, a.rewardtype, a.rewardrecord, a.documentnumber, a.fromdate, a.reason
    FROM chatbot_beehi_hcm.beehi_emp_reward_process_info a
    INNER JOIN chatbot_beehi_hcm.beehi_base_emp_info e ON a.employeeid = e.employeeid
    WHERE e.username = %(username)s
    ORDER BY a.fromdate DESC
"""
QUERY_RATING = """
    SELECT e.username, r.periodname, r.resultfinal, r.ratingafter, r.status
    FROM chatbot_beehi_hcm.beehi_emp_rating_process_info r
    INNER JOIN chatbot_beehi_hcm.beehi_base_emp_info e ON r.employeeid = e.employeeid
    WHERE e.username = %(username)s
    ORDER BY r.periodname DESC
"""
QUERY_PARTY = """
    SELECT e.username, p.partydate, p.partyofficialdate, p.partyplace, p.armyjoin, p.armylevel
    FROM chatbot_beehi_hcm.beehi_emp_party_army_info p
    INNER JOIN chatbot_beehi_hcm.beehi_base_emp_info e ON p.employeeid = e.employeeid
    WHERE e.username = %(username)s
"""
QUERY_PRE_MB = """
    SELECT e.username, p.organizationname, p.positionname, p.fromdate, p.todate, p.mission, p.reasonleave, p.rewardinfo
    FROM chatbot_beehi_hcm.beehi_emp_pre_mb_process_info p
    INNER JOIN chatbot_beehi_hcm.beehi_base_emp_info e ON p.employeeid = e.employeeid
    WHERE e.username = %(username)s
    ORDER BY p.fromdate DESC
"""


def prepare_sql_input_with_params(query_str: str, limit_val: int = None, params_extractor: callable = None):
    """Factory tạo function prepare SQL với params có thể mở rộng."""
    if params_extractor is None:
        params_extractor = lambda sk: {"username": sk["username"]}
    def _prepare(sensitive_keys: dict) -> dict:
        result = {
            "query": query_str,
            "params": params_extractor(sensitive_keys),
        }
        if limit_val:
            result["limit"] = limit_val
        return result
    _prepare.__name__ = "prepare_sql"
    return _prepare


# ---- Merge functions cho HCM tools ----
def merge_basic_info(profile, work, contract, concurrent, seniority):
    """Merge basic info"""
    return {"result": {"profile": profile, "work_history": work, "contract": contract, "concurrent_positions": concurrent, "seniority": seniority}}

def merge_benefits(leave_records, annual_leave, education, awards):
    """Merge benefits"""
    return {"result": {"leave_records": leave_records, "annual_leave": annual_leave, "education": education, "awards": awards}}

def merge_review(performance_reviews, party_army_info, pre_mb_history):
    """Merge review"""
    return {"result": {"performance_reviews": performance_reviews, "party_army_info": party_army_info, "pre_mb_history": pre_mb_history}}


# =========================================================
# BOT CLASS
# =========================================================
class BeeHR:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id

        # MongoDB engine cho RAG
        self.mongo_engine = ResourceHub.self().sync_mongo("aicenter-chatbot")
        bot_info = self.mongo_engine._find_one(
            collection_name="botinfo", query={"_id": self.bot_id})
        self.name = bot_info.get('data', {'name': {}}).get('name', None)
        self.config = bot_info.get(
            'data', {'metadata': {}}).get('metadata', {})
        self.definition = HR_BOT_SYSTEM_PROMPT

        self._build_flow()

    def _build_flow(self):
        with WorkflowEngine(
            name="beeHR",
            description="Chat bot HR sử dụng ReAct Agent với HCM Tools và RAG Tools"
        ) as beeBot:

            # =====================================================
            # REDIS SESSION MANAGEMENT
            # =====================================================
            get_session_key_fn = CodeNode(
                name="get_session_key",
                code_fn=get_session_key,
                inputs={
                    "session_id": INPUT,
                    "role_ids": INPUT
                },
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

            # =====================================================
            # PROCESS QUERY GRAPH
            # =====================================================
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

            # =====================================================
            # RAG TOOL: retrieval_graph (Vector Search)
            # =====================================================
            with GraphNode(
                name="retrieval_graph",
                description="Tool truy vấn tài liệu từ knowledge base truy vấn bằng vector search với tập chunk sẵn có",
                input_schema=(
                    ParamSet.new()
                        .var("query: str", "Câu query truy vấn vào knowledge base", required=True)
                        .build()
                )
            ) as retrieval_graph:
                prepare_input = CodeNode(
                    name="prepare_input",
                    code_fn=prepare_input_tool,
                    inputs={
                        "sensitive_keys_in": { INPUT : "sensitive_keys" }
                    },
                    return_keys=['sensitive_keys']
                )

                extract_role_ids = CodeNode(
                    name="extract_role_ids",
                    code_fn=extract_role_ids_from_keys,
                    inputs={
                        "sensitive_keys": {prepare_input: "sensitive_keys"}
                    },
                    return_keys=["role_ids"]
                )

                retrieval_node = RetrieverNodeV3(
                    name="retrieval_tool",
                    description="Tool truy vấn tài liệu từ knowledge base",
                    use_hierarchical_search=True,
                    use_hybrid_search=True,
                    use_node_search=True,
                    inputs={
                        "query": INPUT,
                        "allowed_roles": { extract_role_ids : 'role_ids' },
                        "bot_id": self.bot_id,
                        'top_k': 10,
                        'top_k_node': 5,
                        'top_k_topic': 3,
                        'top_k_score': 5,
                        'top_k_children': 3,
                        'threshold': 0.0,
                        'output_fields': ['chunk_id', 'type'],
                        'search_weighted_score': [0.5, 0.5],
                        'rerank_top_k': 10,
                        'rerank_threshold': 0.0,
                        'rerank_top_k_node': 3,
                        'rerank_threshold_node': 0.0
                    },
                    outputs={"docs": OUTPUT})

                START >> prepare_input >> extract_role_ids >> retrieval_node >> END
                retrieval_graph.build()

            # =====================================================
            # RAG TOOL: get_list_documents
            # =====================================================
            with GraphNode(
                name="get_list_documents",
                description="Tool lấy danh sách tài liệu ở trong knowledge",
                input_schema=(
                    ParamSet.new()
                        .var("category_id: str", "id của category để lọc tập hợp tài liệu theo chủ đề, mặc định là 'all'", required=False)
                        .build()
                )
            ) as get_list_documents:

                prepare_input = CodeNode(
                    name="prepare_input",
                    code_fn=prepare_input_tool,
                    inputs={
                        "sensitive_keys_in": { INPUT : "sensitive_keys" }
                    },
                    return_keys=['sensitive_keys']
                )

                extract_role_ids = CodeNode(
                    name="extract_role_ids",
                    code_fn=extract_role_ids_from_keys,
                    inputs={
                        "sensitive_keys": {prepare_input: "sensitive_keys"}
                    },
                    return_keys=["role_ids"]
                )

                lookup_roles_fn = CodeNode(
                    name="lookup_role_uuids",
                    code_fn=prepare_role_lookup_query,
                    inputs={
                        "role_names": {extract_role_ids: "role_ids"},
                        "bot_id": self.bot_id
                    },
                    return_keys=["query"]
                )

                roles_mongo = MongoNode(
                    name="get_role_uuids",
                    resource_key="aicenter-chatbot",
                    description="Lookup role UUIDs from role names",
                    operation=MongoOperation.FIND,
                    inputs={
                        "query": {lookup_roles_fn: "query"},
                        "collection_name": "roles",
                        "projection": {"_id": 1}
                    }
                )

                extract_uuids_fn = CodeNode(
                    name="extract_role_uuids",
                    code_fn=extract_role_uuids,
                    inputs={
                        "roles_data": {roles_mongo: "data"}
                    },
                    return_keys=["role_uuids"]
                )

                create_list_query_fn = CodeNode(
                    name="create_list_query_fn",
                    code_fn=prepare_list_documents_query,
                    inputs={
                        'bot_id': self.bot_id,
                        'category_id': INPUT,
                        'role_uuids': {extract_uuids_fn: "role_uuids"}
                    },
                    return_keys=["query"]
                )

                mongo_node = MongoNode(
                    name="get_list_documents_tool",
                    resource_key="aicenter-chatbot",
                    description="Tool lấy danh sách tài liệu có ở trong knowledge",
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

                START >> prepare_input >> extract_role_ids >> lookup_roles_fn >> roles_mongo >> extract_uuids_fn >> create_list_query_fn >> mongo_node >> END
                get_list_documents.build()

            # =====================================================
            # RAG TOOL: get_document_content
            # =====================================================
            with GraphNode(
                name="get_document_content",
                description="Lấy nội dung của tài liệu trong knowledge bằng id",
                input_schema=(
                    ParamSet.new()
                        .var("document_id: str", "id của tài liệu", required=True)
                        .var("page: int", "trang của tài liệu, mặc định là 1", required=False)
                        .build()
                )
            ) as get_document_content:

                prepare_input = CodeNode(
                    name="prepare_input",
                    code_fn=prepare_input_tool,
                    inputs={
                        "sensitive_keys_in": { INPUT : "sensitive_keys" }
                    },
                    return_keys=['sensitive_keys']
                )

                extract_role_ids = CodeNode(
                    name="extract_role_ids",
                    code_fn=extract_role_ids_from_keys,
                    inputs={
                        "sensitive_keys": {prepare_input: "sensitive_keys"}
                    },
                    return_keys=["role_ids"]
                )

                lookup_roles_fn = CodeNode(
                    name="lookup_role_uuids",
                    code_fn=prepare_role_lookup_query,
                    inputs={
                        "role_names": {extract_role_ids: "role_ids"},
                        "bot_id": self.bot_id
                    },
                    return_keys=["query"]
                )

                roles_mongo = MongoNode(
                    name="get_role_uuids",
                    resource_key="aicenter-chatbot",
                    description="Lookup role UUIDs from role names",
                    operation=MongoOperation.FIND,
                    inputs={
                        "query": {lookup_roles_fn: "query"},
                        "collection_name": "roles",
                        "projection": {"_id": 1}
                    }
                )

                extract_uuids_fn = CodeNode(
                    name="extract_role_uuids",
                    code_fn=extract_role_uuids,
                    inputs={
                        "roles_data": {roles_mongo: "data"}
                    },
                    return_keys=["role_uuids"]
                )

                build_doc_access_query_fn = CodeNode(
                    name="build_doc_access_query",
                    code_fn=build_doc_access_query,
                    inputs={
                        "document_id": INPUT,
                        "role_uuids": {extract_uuids_fn: "role_uuids"}
                    },
                    return_keys=["query"]
                )

                doc_access_mongo = MongoNode(
                    name="check_doc_access",
                    resource_key="aicenter-chatbot",
                    description="Check if document is accessible by user's roles",
                    operation=MongoOperation.FIND,
                    inputs={
                        "query": {build_doc_access_query_fn: "query"},
                        "collection_name": "documents",
                        "projection": {"_id": 1},
                        "limit": 1
                    }
                )

                extract_accessible_doc_id_fn = CodeNode(
                    name="extract_accessible_doc_id",
                    code_fn=extract_accessible_doc_id,
                    inputs={
                        "docs_data": {doc_access_mongo: "data"}
                    },
                    return_keys=["doc_id"]
                )

                create_mongo_query_fn = CodeNode(
                    name="create_mongo_query_fn",
                    code_fn=create_mongo_query,
                    inputs={
                        'document_id': INPUT,
                        'page': INPUT
                    },
                    return_keys=['query: Dict[str, Any]', 'skip: int']
                )

                prepare_doc_data_query_fn = CodeNode(
                    name="prepare_doc_data_query",
                    code_fn=lambda query, skip, doc_id: ({"data_query": {"_id": "NONEXISTENT"}, "data_skip": 0} if not doc_id else {"data_query": query, "data_skip": skip}),
                    inputs={
                        "query": {create_mongo_query_fn: "query"},
                        "skip": {create_mongo_query_fn: "skip"},
                        "doc_id": {extract_accessible_doc_id_fn: "doc_id"}
                    },
                    return_keys=["data_query: Dict[str, Any]", "data_skip: int"]
                )

                mongo_node = MongoNode(
                    name="get_content",
                    resource_key="aicenter-chatbot",
                    description="Lấy toàn bộ nội dung của tài liệu trong knowledge bằng id",
                    operation=MongoOperation.FIND,
                    inputs={
                        "query": {prepare_doc_data_query_fn: "data_query"},
                        "collection_name": "document_data",
                        "projection": {
                            "content": 1,
                        },
                        "skip": {prepare_doc_data_query_fn: "data_skip"}
                    },
                    outputs=OUTPUT
                )

                START >> prepare_input >> extract_role_ids >> lookup_roles_fn >> roles_mongo >> extract_uuids_fn >> build_doc_access_query_fn >> doc_access_mongo >> extract_accessible_doc_id_fn
                START >> create_mongo_query_fn
                [create_mongo_query_fn, extract_accessible_doc_id_fn] >> prepare_doc_data_query_fn >> mongo_node >> END
                get_document_content.build()

            # =====================================================
            # RAG TOOL: search_documents
            # =====================================================
            with GraphNode(
                name="search_documents",
                description="Tìm kiếm tài liệu, chunk trong knowledge bằng từ khóa",
                input_schema=(
                    ParamSet.new()
                        .var("keyword: str", "từ khóa tìm kiếm", required=True)
                        .build()
                )
            ) as search_documents:

                prepare_input = CodeNode(
                    name="prepare_input",
                    code_fn=prepare_input_tool,
                    inputs={
                        "sensitive_keys_in": { INPUT : "sensitive_keys" }
                    },
                    return_keys=['sensitive_keys']
                )

                extract_role_ids = CodeNode(
                    name="extract_role_ids",
                    code_fn=extract_role_ids_from_keys,
                    inputs={
                        "sensitive_keys": {prepare_input: "sensitive_keys"}
                    },
                    return_keys=["role_ids"]
                )

                lookup_roles_fn = CodeNode(
                    name="lookup_role_uuids",
                    code_fn=prepare_role_lookup_query,
                    inputs={
                        "role_names": {extract_role_ids: "role_ids"},
                        "bot_id": self.bot_id
                    },
                    return_keys=["query"]
                )

                roles_mongo = MongoNode(
                    name="get_role_uuids",
                    resource_key="aicenter-chatbot",
                    description="Lookup role UUIDs from role names",
                    operation=MongoOperation.FIND,
                    inputs={
                        "query": {lookup_roles_fn: "query"},
                        "collection_name": "roles",
                        "projection": {"_id": 1}
                    }
                )

                extract_uuids_fn = CodeNode(
                    name="extract_role_uuids",
                    code_fn=extract_role_uuids,
                    inputs={
                        "roles_data": {roles_mongo: "data"}
                    },
                    return_keys=["role_uuids"]
                )

                build_allowed_docs_query_fn = CodeNode(
                    name="build_allowed_docs_query",
                    code_fn=build_allowed_docs_query,
                    inputs={
                        "bot_id": self.bot_id,
                        "role_uuids": {extract_uuids_fn: "role_uuids"}
                    },
                    return_keys=["query"]
                )

                allowed_docs_mongo = MongoNode(
                    name="get_allowed_docs",
                    resource_key="aicenter-chatbot",
                    description="Get all document IDs accessible by user's roles",
                    operation=MongoOperation.FIND,
                    inputs={
                        "query": {build_allowed_docs_query_fn: "query"},
                        "collection_name": "documents",
                        "projection": {"_id": 1}
                    }
                )

                extract_allowed_ids_fn = CodeNode(
                    name="extract_allowed_doc_ids",
                    code_fn=extract_allowed_doc_ids,
                    inputs={
                        "docs_data": {allowed_docs_mongo: "data"}
                    },
                    return_keys=["allowed_ids"]
                )

                create_search_query_fn = CodeNode(
                    name="create_search_query_fn",
                    code_fn=create_search_query,
                    inputs={
                        'keyword': INPUT,
                        'bot_id': self.bot_id,
                        'allowed_ids': {extract_allowed_ids_fn: "allowed_ids"}
                    },
                    return_keys=['query: Dict[str, Any]']
                )

                mongo_node = MongoNode(
                    name="search_content",
                    resource_key="aicenter-chatbot",
                    description="Tìm kiếm tài liệu theo từ khóa",
                    operation=MongoOperation.FIND,
                    inputs={
                        "query": { create_search_query_fn: "query" },
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

                START >> prepare_input >> extract_role_ids >> lookup_roles_fn >> roles_mongo >> extract_uuids_fn >> build_allowed_docs_query_fn >> allowed_docs_mongo >> extract_allowed_ids_fn >> create_search_query_fn >> mongo_node >> END
                search_documents.build()

            # =====================================================
            # RAG TOOL: search_dialogue (Q&A)
            # =====================================================
            with GraphNode(
                name="search_dialogue",
                description="Tìm kiếm câu hỏi & trả lời có sẵn (Q&A) trong dialogue bằng từ khóa (Ưu tiên tìm kiếm trước)",
                input_schema=(
                    ParamSet.new()
                        .var("keyword: str", "từ khóa tìm kiếm trong bộ câu hỏi mẫu", required=True)
                        .build()
                )
            ) as search_dialogue:

                prepare_input = CodeNode(
                    name="prepare_input",
                    code_fn=prepare_input_tool,
                    inputs={
                        "sensitive_keys_in": { INPUT : "sensitive_keys" }
                    },
                    return_keys=['sensitive_keys']
                )

                extract_role_ids = CodeNode(
                    name="extract_role_ids",
                    code_fn=extract_role_ids_from_keys,
                    inputs={
                        "sensitive_keys": {prepare_input: "sensitive_keys"}
                    },
                    return_keys=["role_ids"]
                )

                lookup_roles_fn = CodeNode(
                    name="lookup_role_uuids",
                    code_fn=prepare_role_lookup_query,
                    inputs={
                        "role_names": {extract_role_ids: "role_ids"},
                        "bot_id": self.bot_id
                    },
                    return_keys=["query"]
                )

                roles_mongo = MongoNode(
                    name="get_role_uuids",
                    resource_key="aicenter-chatbot",
                    description="Lookup role UUIDs from role names",
                    operation=MongoOperation.FIND,
                    inputs={
                        "query": {lookup_roles_fn: "query"},
                        "collection_name": "roles",
                        "projection": {"_id": 1}
                    }
                )

                extract_uuids_fn = CodeNode(
                    name="extract_role_uuids",
                    code_fn=extract_role_uuids,
                    inputs={
                        "roles_data": {roles_mongo: "data"}
                    },
                    return_keys=["role_uuids"]
                )

                create_dialogue_query_fn = CodeNode(
                    name="create_dialogue_query_fn",
                    code_fn=search_dialogue_query,
                    inputs={
                        'keyword': INPUT,
                        'bot_id': self.bot_id,
                        'role_uuids': {extract_uuids_fn: "role_uuids"}
                    },
                    return_keys=['query: Dict[str, Any]']
                )

                mongo_node = MongoNode(
                    name="search_dialogue_tool",
                    resource_key="aicenter-chatbot",
                    description="Tìm kiếm trong bộ câu hỏi mẫu (dialogue)",
                    operation=MongoOperation.FIND,
                    inputs={
                        "query": { create_dialogue_query_fn: "query" },
                        "collection_name": "dialogue",
                        "limit": 10,
                        "projection": {
                            "name": 1,
                            "questions": 1,
                            "answers": 1,
                            "_id": 1
                        }
                    },
                    outputs=OUTPUT
                )

                START >> prepare_input >> extract_role_ids >> lookup_roles_fn >> roles_mongo >> extract_uuids_fn >> create_dialogue_query_fn >> mongo_node >> END
                search_dialogue.build()

            # =====================================================
            # UTILITY TOOL: get_current_time
            # =====================================================
            with GraphNode(
                name="get_current_time",
                description="Lấy thời gian hiện tại (ngày, tháng, năm, giờ, phút)",
                input_schema=(
                    ParamSet.new().build()
                )
            ) as get_current_time:

                prepare_input = CodeNode(
                    name="prepare_input",
                    code_fn=prepare_input_tool,
                    inputs={
                        "sensitive_keys_in": { INPUT : "sensitive_keys" }
                    },
                    return_keys=['sensitive_keys']
                )

                now_node = CodeNode(
                    name="get_current_time_fn",
                    code_fn=lambda: {"result": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                    inputs={},
                    return_keys=["result"],
                    outputs=OUTPUT
                )

                START >> prepare_input >> now_node >> END
                get_current_time.build()

            # =====================================================
            # RAG TOOL: get_categories
            # =====================================================
            with GraphNode(
                name="get_categories",
                description="Lấy danh sách các topic/danh mục từ bảng category",
                input_schema=(
                    ParamSet.new().build()
                )
            ) as get_categories:

                prepare_input = CodeNode(
                    name="prepare_input",
                    code_fn=prepare_input_tool,
                    inputs={
                        "sensitive_keys_in": { INPUT : "sensitive_keys" }
                    },
                    return_keys=['sensitive_keys']
                )

                extract_role_ids = CodeNode(
                    name="extract_role_ids",
                    code_fn=extract_role_ids_from_keys,
                    inputs={
                        "sensitive_keys": {prepare_input: "sensitive_keys"}
                    },
                    return_keys=["role_ids"]
                )

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

                START >> prepare_input >> extract_role_ids >> mongo_node >> END
                get_categories.build()

            # =====================================================
            # KB STRUCTURE TOOL: get_kb_structure (category -> documents tree)
            # =====================================================
            with GraphNode(
                name="get_kb_structure",
                description="Lấy cấu trúc toàn bộ knowledge base dạng cây: danh mục (category) -> danh sách tài liệu kèm ID. Nên gọi ở đầu hội thoại để biết KB có những tài liệu gì.",
                input_schema=(
                    ParamSet.new().build()
                )
            ) as get_kb_structure:

                prepare_input = CodeNode(
                    name="prepare_input",
                    code_fn=prepare_input_tool,
                    inputs={
                        "sensitive_keys_in": { INPUT : "sensitive_keys" }
                    },
                    return_keys=['sensitive_keys']
                )

                extract_role_ids = CodeNode(
                    name="extract_role_ids",
                    code_fn=extract_role_ids_from_keys,
                    inputs={
                        "sensitive_keys": {prepare_input: "sensitive_keys"}
                    },
                    return_keys=["role_ids"]
                )

                lookup_roles_fn = CodeNode(
                    name="lookup_role_uuids",
                    code_fn=prepare_role_lookup_query,
                    inputs={
                        "role_names": {extract_role_ids: "role_ids"},
                        "bot_id": self.bot_id
                    },
                    return_keys=["query"]
                )

                roles_mongo = MongoNode(
                    name="get_role_uuids",
                    resource_key="aicenter-chatbot",
                    description="Lookup role UUIDs from role names",
                    operation=MongoOperation.FIND,
                    inputs={
                        "query": {lookup_roles_fn: "query"},
                        "collection_name": "roles",
                        "projection": {"_id": 1}
                    }
                )

                extract_uuids_fn = CodeNode(
                    name="extract_role_uuids",
                    code_fn=extract_role_uuids,
                    inputs={
                        "roles_data": {roles_mongo: "data"}
                    },
                    return_keys=["role_uuids"]
                )

                get_all_categories = MongoNode(
                    name="get_all_categories",
                    resource_key="aicenter-chatbot",
                    description="Lấy tất cả categories",
                    operation=MongoOperation.FIND,
                    inputs={
                        "query": {'bot_id': self.bot_id},
                        "collection_name": "category",
                        "projection": {"name": 1, "_id": 1}
                    }
                )

                build_kb_docs_query_fn = CodeNode(
                    name="build_kb_docs_query",
                    code_fn=build_kb_documents_query,
                    inputs={
                        "bot_id": self.bot_id,
                        "role_uuids": {extract_uuids_fn: "role_uuids"}
                    },
                    return_keys=["query"]
                )

                get_all_docs = MongoNode(
                    name="get_all_docs",
                    resource_key="aicenter-chatbot",
                    description="Lấy tất cả documents user có quyền truy cập",
                    operation=MongoOperation.FIND,
                    inputs={
                        "query": {build_kb_docs_query_fn: "query"},
                        "collection_name": "documents",
                        "projection": {
                            "doc_name": 1,
                            "_id": 1,
                            "category_id": 1
                        }
                    }
                )

                assemble_fn = CodeNode(
                    name="assemble_kb_tree",
                    code_fn=assemble_kb_tree,
                    inputs={
                        "categories_data": {get_all_categories: "data"},
                        "documents_data": {get_all_docs: "data"}
                    },
                    return_keys=["result"],
                    outputs=OUTPUT
                )

                # Flow: role resolution chain || get_all_categories (parallel)
                START >> prepare_input >> extract_role_ids >> lookup_roles_fn >> roles_mongo >> extract_uuids_fn >> build_kb_docs_query_fn >> get_all_docs
                START >> get_all_categories
                [get_all_categories, get_all_docs] >> assemble_fn >> END
                get_kb_structure.build()

            # =====================================================
            # HR TOOL: request_hr_consultation (Mock)
            # =====================================================
            with GraphNode(
                name="request_hr_consultation",
                description="Create a request for direct HR consultation when the bot's information is insufficient or the situation requires human expertise — e.g., complex cases, edge cases not covered in documents, or situations where wrong information could cause losses",
                input_schema=(
                    ParamSet.new()
                        .var("subject: str", "The subject/title of the HR consultation request", required=True)
                        .var("description: str", "Detailed description of the issue requiring direct HR consultation", required=True)
                        .build()
                )
            ) as request_hr_consultation:

                prepare_input = CodeNode(
                    name="prepare_input",
                    code_fn=prepare_input_tool,
                    inputs={
                        "sensitive_keys_in": { INPUT : "sensitive_keys" }
                    },
                    return_keys=['sensitive_keys']
                )

                mock_request_fn = CodeNode(
                    name="mock_request_fn",
                    code_fn=prepare_hr_request,
                    inputs={
                        'subject': INPUT,
                        'description': INPUT,
                        'sensitive_keys': {prepare_input: "sensitive_keys"}
                    },
                    return_keys=["result"],
                    outputs=OUTPUT
                )

                START >> prepare_input >> mock_request_fn >> END
                request_hr_consultation.build()

            # =====================================================
            # NHÓM 1: get_employee_basic_info
            # Profile + Work History + Contract + Concurrent + Seniority
            # =====================================================
            with GraphNode(
                name="get_employee_basic_info",
                description="HCM TOOL - Lấy thông tin nhân sự hiện tại cơ bản: hồ sơ cá nhân, quá trình công tác, hợp đồng, vị trí kiêm nhiệm, thâm niên",
                input_schema=(
                    ParamSet.new().build()
                )
            ) as hcm_basic_info:
                p_profile = CodeNode(
                    name="prep_profile",
                    code_fn=prepare_sql_input_with_params(QUERY_PROFILE, 1),
                    inputs={"sensitive_keys": INPUT},
                    return_keys=["query", "params", "limit"]
                )
                p_work = CodeNode(
                    name="prep_work",
                    code_fn=prepare_sql_input_with_params(QUERY_WORK_HISTORY, 20),
                    inputs={"sensitive_keys": INPUT},
                    return_keys=["query", "params", "limit"]
                )
                p_contract = CodeNode(
                    name="prep_contract",
                    code_fn=prepare_sql_input_with_params(QUERY_CONTRACT, 10),
                    inputs={"sensitive_keys": INPUT},
                    return_keys=["query", "params", "limit"]
                )
                p_concurrent = CodeNode(
                    name="prep_concurrent",
                    code_fn=prepare_sql_input_with_params(QUERY_CONCURRENT, 10),
                    inputs={"sensitive_keys": INPUT},
                    return_keys=["query", "params", "limit"]
                )
                p_seniority = CodeNode(
                    name="prep_seniority",
                    code_fn=prepare_sql_input_with_params(QUERY_SENIORITY, 1),
                    inputs={"sensitive_keys": INPUT},
                    return_keys=["query", "params", "limit"]
                )

                n_profile = SQLNode(
                    name="exec_profile",
                    resource_key="hr_information",
                    operation=SQLOperation.QUERY,
                    inputs={"query": {p_profile: "query"}, "params": {p_profile: "params"}, "limit": {p_profile: "limit"}},
                    # outputs=OUTPUT
                )
                n_work = SQLNode(
                    name="exec_work",
                    resource_key="hr_information",
                    operation=SQLOperation.QUERY,
                    inputs={"query": {p_work: "query"}, "params": {p_work: "params"}, "limit": {p_work: "limit"}},
                    # outputs=OUTPUT
                )
                n_contract = SQLNode(
                    name="exec_contract",
                    resource_key="hr_information",
                    operation=SQLOperation.QUERY,
                    inputs={"query": {p_contract: "query"}, "params": {p_contract: "params"}, "limit": {p_contract: "limit"}},
                    # outputs=OUTPUT
                )
                n_concurrent = SQLNode(
                    name="exec_concurrent",
                    resource_key="hr_information",
                    operation=SQLOperation.QUERY,
                    inputs={"query": {p_concurrent: "query"}, "params": {p_concurrent: "params"}, "limit": {p_concurrent: "limit"}},
                    # outputs=OUTPUT
                )
                n_seniority = SQLNode(
                    name="exec_seniority",
                    resource_key="hr_information",
                    operation=SQLOperation.QUERY,
                    inputs={"query": {p_seniority: "query"}, "params": {p_seniority: "params"}, "limit": {p_seniority: "limit"}},
                    # outputs=OUTPUT
                )

                

                # Gộp kết quả
                merge_node = CodeNode(
                    name="merge_basic_info",
                    code_fn=merge_basic_info,
                    inputs={
                        "profile": {n_profile: "data"},
                        "work": {n_work: "data"},
                        "contract": {n_contract: "data"},
                        "concurrent": {n_concurrent: "data"},
                        "seniority": {n_seniority: "data"},
                    },
                    return_keys=["result"],
                    outputs=OUTPUT
                )
                
                # Phân luồng: START → prepare song song → SQL song song
                START >> [p_profile, p_work, p_contract, p_concurrent, p_seniority]
                p_profile >> n_profile
                p_work >> n_work
                p_contract >> n_contract
                p_concurrent >> n_concurrent
                p_seniority >> n_seniority

                [n_profile, n_work, n_contract, n_concurrent, n_seniority] >> merge_node >> END
                hcm_basic_info.build()

            # =====================================================
            # NHÓM 2: get_employee_benefits
            # Leave Records + Annual Leave + Education + Awards
            # =====================================================
            with GraphNode(
                name="get_employee_benefits",
                description="HCM TOOL - Lấy thông tin phúc lợi: nghỉ phép (đã được phê duyệt), phép năm, bằng cấp/chứng chỉ (đã được phê duyệt), khen thưởng",
                input_schema=(
                    ParamSet.new().build()
                )
            ) as hcm_benefits:
                p_leave = CodeNode(name="prep_leave", code_fn=prepare_sql_input_with_params(QUERY_LEAVE, 20), inputs={"sensitive_keys": INPUT}, return_keys=["query", "params", "limit"])
                p_annual = CodeNode(name="prep_annual", code_fn=prepare_sql_input_with_params(QUERY_ANNUAL_LEAVE, 1), inputs={"sensitive_keys": INPUT}, return_keys=["query", "params", "limit"])
                p_edu = CodeNode(name="prep_edu", code_fn=prepare_sql_input_with_params(QUERY_EDUCATION, 20), inputs={"sensitive_keys": INPUT}, return_keys=["query", "params", "limit"])
                p_awards = CodeNode(name="prep_awards", code_fn=prepare_sql_input_with_params(QUERY_AWARDS, 20), inputs={"sensitive_keys": INPUT}, return_keys=["query", "params", "limit"])

                n_leave = SQLNode(
                    name="exec_leave",
                    resource_key="hr_information",
                    operation=SQLOperation.QUERY,
                    inputs={"query": {p_leave: "query"}, "params": {p_leave: "params"}, "limit": {p_leave: "limit"}},
                    # outputs=OUTPUT
                )
                n_annual = SQLNode(
                    name="exec_annual",
                    resource_key="hr_information",
                    operation=SQLOperation.QUERY,
                    inputs={"query": {p_annual: "query"}, "params": {p_annual: "params"}, "limit": {p_annual: "limit"}},
                    # outputs=OUTPUT
                )
                n_edu = SQLNode(
                    name="exec_edu",
                    resource_key="hr_information",
                    operation=SQLOperation.QUERY,
                    inputs={"query": {p_edu: "query"}, "params": {p_edu: "params"}, "limit": {p_edu: "limit"}},
                    # outputs=OUTPUT
                )
                n_awards = SQLNode(
                    name="exec_awards",
                    resource_key="hr_information",
                    operation=SQLOperation.QUERY,
                    inputs={"query": {p_awards: "query"}, "params": {p_awards: "params"}, "limit": {p_awards: "limit"}},
                    # outputs=OUTPUT
                )

                START >> [p_leave, p_annual, p_edu, p_awards]
                p_leave >> n_leave; p_annual >> n_annual; p_edu >> n_edu; p_awards >> n_awards

                merge_node = CodeNode(
                    name="merge_benefits",
                    code_fn=merge_benefits,
                    inputs={
                        "leave_records": {n_leave: "data"},
                        "annual_leave": {n_annual: "data"},
                        "education": {n_edu: "data"},
                        "awards": {n_awards: "data"},
                    },
                    return_keys=["result"],
                    outputs=OUTPUT
                )
                [n_leave, n_annual, n_edu, n_awards] >> merge_node >> END
                hcm_benefits.build()

            # =====================================================
            # NHÓM 3: get_employee_review
            # Performance Reviews + Party/Army + Pre-MB History
            # =====================================================
            with GraphNode(
                name="get_employee_review",
                description="HCM TOOL - Lấy thông tin đánh giá: kết quả đánh giá kỳ, thông tin Đảng/quân nhân, quá trình trước MB",
                input_schema=(
                    ParamSet.new().build()
                )
            ) as hcm_review:
                p_rating = CodeNode(name="prep_rating", code_fn=prepare_sql_input_with_params(QUERY_RATING, 10), inputs={"sensitive_keys": INPUT}, return_keys=["query", "params", "limit"])
                p_party = CodeNode(name="prep_party", code_fn=prepare_sql_input_with_params(QUERY_PARTY, 5), inputs={"sensitive_keys": INPUT}, return_keys=["query", "params", "limit"])
                p_premb = CodeNode(name="prep_premb", code_fn=prepare_sql_input_with_params(QUERY_PRE_MB, 10), inputs={"sensitive_keys": INPUT}, return_keys=["query", "params", "limit"])

                n_rating = SQLNode(
                    name="exec_rating",
                    resource_key="hr_information",
                    operation=SQLOperation.QUERY,
                    inputs={"query": {p_rating: "query"}, "params": {p_rating: "params"}, "limit": {p_rating: "limit"}},
                    # outputs=OUTPUT
                )
                n_party = SQLNode(
                    name="exec_party",
                    resource_key="hr_information",
                    operation=SQLOperation.QUERY,
                    inputs={"query": {p_party: "query"}, "params": {p_party: "params"}, "limit": {p_party: "limit"}},
                    # outputs=OUTPUT
                )
                n_premb = SQLNode(
                    name="exec_premb",
                    resource_key="hr_information",
                    operation=SQLOperation.QUERY,
                    inputs={"query": {p_premb: "query"}, "params": {p_premb: "params"}, "limit": {p_premb: "limit"}},
                    # outputs=OUTPUT
                )

                START >> [p_rating, p_party, p_premb]
                p_rating >> n_rating; p_party >> n_party; p_premb >> n_premb

                merge_node = CodeNode(
                    name="merge_review",
                    code_fn=merge_review,
                    inputs={
                        "performance_reviews": {n_rating: "data"},
                        "party_army_info": {n_party: "data"},
                        "pre_mb_history": {n_premb: "data"},
                    },
                    return_keys=["result"],
                    outputs=OUTPUT
                )
                [n_rating, n_party, n_premb] >> merge_node >> END
                hcm_review.build()

            # =====================================================
            # PREPARE INPUT FOR AGENT
            # =====================================================
            prepare_input_fn = CodeNode(
                name="prepare_input_agent",
                code_fn=prepare_input_agent,
                inputs={
                    "messages_new": {INPUT: "messages"},
                    "state": {get_redis: "value"},
                    "sensitive_keys_in": {INPUT: "sensitive_keys"}
                },
                return_keys=["messages", "sensitive_keys"]
            )

            # =====================================================
            # REACT AGENT với tất cả tools
            # =====================================================
            react_agent = PlanExecuteVerifyAgentNode(
                name="react_agent",
                # resource_key="qwen-instruct-chat",
                # resource_key="gpt-4.1",
                # resource_key="gemini-3-flash-chat",
                resource_key="gemini-3-flash-chat-bk",
                # resource_key="gemini-2.5-flash-chat",
                # resource_key="Qwen3.6-27B",
                # resource_key="gemini-3.5-flash-chat",
                # resource_key="gemini-3.1-pro-chat",
                tools=[
                    # RAG Tools
                    retrieval_graph,
                    get_kb_structure,
                    # get_list_documents,  # Replaced by get_kb_structure
                    get_document_content,
                    search_documents,
                    # get_categories,     # Replaced by get_kb_structure
                    search_dialogue,
                    # HCM Tools (gộp nhóm)
                    hcm_basic_info,
                    hcm_benefits,
                    hcm_review,
                    # HR Consultation Tool
                    # request_hr_consultation,
                    # Utility Tools
                    get_current_time,
                ],
                max_iterations=15,
                context_prompt=self.definition,
                inputs=prepare_input_fn,
                outputs={"final_answer": OUTPUT}
            )

            # =====================================================
            # FORMAT RESULT & SAVE SESSION
            # =====================================================
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
                    "seconds": 1800
                }
            )

            # =====================================================
            # WORKFLOW CONNECTIONS
            # =====================================================
            START >> get_session_key_fn >> get_redis >> process_query >> prepare_input_fn >> react_agent >> get_state_fn >> save_redis >> END

        beeBot.compile()
        self.workflow = beeBot

    def _final_state(self, state_output: Any, final_answer: Any, process_query: Any) -> Dict[str, str]:
        return {'state': json.dumps(state_output, ensure_ascii=False)}

    async def run(self, messages: List[Dict], client_message_id: str, session_id: str, username: str, role_ids: List[str] = [], **kwargs):
        try:
            asyncio.create_task(self.workflow.run(
                request_id=client_message_id,
                inputs={
                    "messages": messages,
                    "session_id": session_id,
                    "role_ids": role_ids,
                    # "username": username,  # Pass username cho HCM tools
                    "sensitive_keys": {
                        "username": username,
                        "token": "abc",
                        "role_ids": role_ids
                    }
                },
                session_id=session_id,
                user_id=username
            ))

            async for channel_name in STREAM_SERVICE.get_channels(client_message_id):
                async for chunk in STREAM_SERVICE.get(client_message_id, channel_name, json_mode=False):
                    if chunk.choices[0].delta.content:
                        yield chunk
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield fake_chunk_from(content='Xin lỗi, đã xảy ra lỗi khi xử lý yêu cầu của bạn. Vui lòng thử lại sau.', model="error")


# =========================================================
# TEST MAIN
# =========================================================
async def main():
    bot_id = "5d816aa9-a21c-4f02-92bf-a28d09aa0ef9"

    bot = BeeHR(bot_id)
    import uuid
    dialogue_id = str(uuid.uuid4())
    client_message_id = str(uuid.uuid4())
    username = 'cuonglt.os'

    print('dialogue_id:', dialogue_id)
    print('client_message_id:', client_message_id)

    async for chunk in bot.run(
            messages=[{"role": "user", "content": "Bạn có những đầu tài liệu nào ?"}],
            session_id=dialogue_id,
            client_message_id=client_message_id,
            role_ids=["L1", "L2", "HRCN"],
            topic="default",
            username=username,
    ):
        print(chunk)
        # print(f"{chunk.choices[0].delta.content or ''}", end= "")

    await asyncio.sleep(4)


if __name__ == '__main__':
    asyncio.run(main())
