from typing import List, Dict, Any
import json
from zoneinfo import ZoneInfo
from datetime import datetime
from beeportal.bot_text2sql.text2sql.constant import abbr_dict
from beeportal.bot_text2sql.text2sql.post_processing_sql import inspect_sql

CHART_KEYWORDS = {
    "vẽ biểu đồ", "biểu đồ", "chart", "plot", "đồ thị",
    "visualize", "trực quan", "biểu đồ cột", "biểu đồ tròn",
    "biểu đồ đường", "bar chart", "pie chart", "line chart",
    "histogram", "heatmap", "vẽ đồ thị", "vẽ chart"
}

def init_query(
    messages: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Formats a list of message dictionaries into a structure with query and history.
    
    Takes the most recent message as the query and formats up to 9 previous messages
    as history with "USER:" or "BOT:" prefixes.
    
    Args:
        messages: List of message dictionaries with 'content' and 'role' keys
    
    Returns:
        origin_query (str): The content of the most recent message
        conversation (List[str]): Formatted list of previous messages
    """
    query = messages[-1]['content']        
    history = [
        f"USER: {m['content']}" 
        if m['role']=='user' 
        else f"BOT: {m['content']}" 
        for m in messages[-10:-1]
    ]
    
    return {
        "origin_query": query,
        "conversation": history
    }
    

def annotate_query(origin_query: str) -> Dict[str, Any]:
    """Adds explanations after abbreviations found in text.
    
    Args:
        origin_query(str): input query to annotate
        
    Returns:
        query (str): query after annotating abbreviation
    """
    
    # Early return for empty/whitespace-only queries
    if not origin_query.strip():
        return origin_query
    
    # Use list comprehension with conditional expression for maximum speed
    words = origin_query.split()
    result = [
        f"{word} ({abbr_dict[word.lower()]}) " 
        if word.lower() in abbr_dict 
        else f"{word} " for word in words
    ]
    
    # Join and strip trailing space in one operation
    anns_query = "".join(result).rstrip()
    
    return {
        "query": anns_query
    }

def extract_latest_bot_response(messages: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Extracts the content of the most recent response from the bot/assistant.
    
    Args:
        messages: List of message dictionaries.
    
    Returns:
        previous_response (str): Content of the last bot message or empty string.
    """
    previous_response = ""
    
    # Duyệt ngược từ tin nhắn áp chót (bỏ qua tin nhắn cuối cùng là của User hiện tại)
    if len(messages) > 1:
        for msg in reversed(messages[:-1]):
            # Chấp nhận cả role 'assistant' (chuẩn OpenAI) hoặc 'bot' (nếu có custom)
            if msg.get('role') in ['assistant', 'bot']:
                previous_response = msg.get('content', "")
                break
    return {
        "previous_response": previous_response
    }


def _int_flag(value: Any) -> int:
    """Chuẩn hóa flag từ YAML BaseLoader; chỉ chấp nhận giá trị 1 rõ ràng."""
    return 1 if value is True or value == 1 or str(value).strip() == "1" else 0


def _allowed_table_pairs(allowed_tables: Any) -> List[tuple[str, str]]:
    result = []
    for item in allowed_tables or []:
        if not isinstance(item, dict):
            continue
        schema = str(item.get("schema_name") or "").strip()
        table = str(item.get("table_name") or "").strip()
        if schema and table:
            result.append((schema, table))
    return list(dict.fromkeys(result))


def _identifier_matches(reference: str, actual: str) -> bool:
    if len(reference) >= 2 and reference[0] == reference[-1] == '"':
        return reference[1:-1].replace('""', '"') == actual
    return reference.casefold() == actual.casefold()


def _resolve_table_reference(
    reference: Any,
    allowed_tables: List[tuple[str, str]],
) -> List[tuple[str, str]]:
    parts = str(reference or "").split(".")
    if len(parts) == 1:
        return [
            pair for pair in allowed_tables
            if _identifier_matches(parts[0], pair[1])
        ]
    if len(parts) == 2:
        return [
            pair for pair in allowed_tables
            if _identifier_matches(parts[0], pair[0])
            and _identifier_matches(parts[1], pair[1])
        ]
    return []


def resolve_direct_metadata_tables(
    physical_tables: Any,
    metadata_references_valid: Any,
    allowed_tables: Any,
) -> Dict[str, Any]:
    """Chỉ cho metadata repair khi toàn bộ AST table refs thuộc quyền."""
    if not _int_flag(metadata_references_valid):
        return {"tables": [], "use_metadata": 0}

    allowed = _allowed_table_pairs(allowed_tables)
    resolved = []
    for table in physical_tables or []:
        matches = _resolve_table_reference(table, allowed)
        if len(matches) != 1:
            return {"tables": [], "use_metadata": 0}
        pair = matches[0]
        resolved.append(".".join(pair))
    return {"tables": list(dict.fromkeys(resolved)), "use_metadata": int(bool(resolved))}


def format_context_examples(retriever_results: List[Dict]) -> Dict[str, str]:
    """
    Format kết quả từ retriever thành context examples
    Loại bỏ 'File tài liệu:' và giữ nguyên câu hỏi + SQL

    Args:
        retriever_results: List of docs từ RetrieverNode

    Returns:
        Dict với key 'context_examples'
    """
    docs = retriever_results if retriever_results else []

    if not docs:
        return {"context_examples": "Không có ví dụ tham khảo."}

    examples = []
    for doc in docs:
        content = doc.get('content', '')
        # Loại bỏ phần "File tài liệu: ..."
        if content.startswith("File tài liệu:"):
            content = content.split('\n', 1)[1] if '\n' in content else content
        examples.append(content.strip())

    formatted = "\n\n---\n\n".join(examples) if examples else "Không có ví dụ tham khảo."
    return {"context_examples": formatted}

def get_current_timestamp() -> Dict[str, Any]:
    """
    Get current timestamp in Asia/Bangkok timezone.

    This function is called at runtime to ensure accurate current time
    when generating SQL queries.

    Returns:
        current_timestamp (datetime): Current datetime in Asia/Bangkok timezone
    """
    return {"current_timestamp": datetime.now(ZoneInfo("Asia/Bangkok"))}


def prepare_mem0_data_merge(
    rewrite: str,
    analyze_content: str | None = None,
    sql_content: str | None = None,
):
    response_content = (analyze_content or sql_content)
    final_response = response_content if response_content else "Không có kết quả trả về"
    dialogue = [
        {"role": "user", "content": rewrite},
        {"role": "assistant","content": final_response}
    ]

    return {"dialogue": dialogue}

def persist_latest_sql(
    sql: str,
    status: str,
    count: int,
    session_id: str,
    data: list = None,
    error: str = "",
) -> dict:
    """Prepare the latest attempted SQL payload for a downstream RedisNode."""
    final_sql = str(sql or "").strip()
    if not final_sql:
        return {"should_persist": 0, "redis_key": "", "redis_value": ""}

    try:
        normalized_count = int(count or 0)
    except (TypeError, ValueError):
        normalized_count = 0

    normalized_status = str(status or "error").strip().lower()
    if normalized_status not in {"success", "error", "rejected"}:
        normalized_status = "error"
    payload = {
        "sql": final_sql,
        "status": normalized_status,
        "error": str(error or ""),
        "count": normalized_count,
        "data": data if isinstance(data, list) else [],
    }
    return {
        "should_persist": 1,
        "redis_key": f"exportable_sql:{session_id}",
        "redis_value": json.dumps(payload),
    }

def build_export_sql_key(session_id: str) -> dict:
    """Tạo Redis key để GET SQL xuất file."""
    return {"redis_key": f"exportable_sql:{session_id}"}

def _empty_cached_sql() -> dict:
    return {
        "resolved_sql": "",
        "status": "",
        "error": "",
        "count": 0,
        "data": [],
    }


def _load_cached_sql(redis_result: str) -> dict:
    if not redis_result:
        return {}
    try:
        cached = json.loads(redis_result)
    except (json.JSONDecodeError, TypeError):
        return {}
    return cached if isinstance(cached, dict) else {}


def parse_export_sql(redis_result: str) -> dict:
    """
    Xử lý kết quả trả về từ RedisNode GET.

    Args:
        redis_result: None nếu key không tồn tại, JSON string nếu có

    Returns:
        resolved_sql: câu SQL sẵn sàng execute, hoặc "" nếu không có
    """
    cached = _load_cached_sql(redis_result)
    if not cached:
        return _empty_cached_sql()

    status = str(cached.get("status") or "").strip().lower()
    # Legacy payloads were written only for successful, non-empty results.
    if not status:
        legacy_sql = str(cached.get("sql") or "").strip()
        legacy_data = cached.get("data")
        try:
            legacy_count = int(cached.get("count"))
        except (TypeError, ValueError):
            legacy_count = 0
        if legacy_sql and legacy_count > 0 and isinstance(legacy_data, list):
            status = "success"
    if status not in {"success", "error", "rejected"}:
        return _empty_cached_sql()
    try:
        raw_count = cached.get("count")
        count = int(raw_count)
        count_valid = raw_count is not None
    except (TypeError, ValueError):
        count = 0
        count_valid = False
    data = cached.get("data") if isinstance(cached.get("data"), list) else []
    sql = str(cached.get("sql") or "").strip()
    usable = status == "success" and count_valid and count > 0 and bool(sql)
    return {
        "resolved_sql": sql if usable else "",
        "status": status,
        "error": str(cached.get("error") or ""),
        "count": count,
        "data": data if usable else [],
    }
    
def parse_chart_data(redis_result: str) -> dict:
    cached = _load_cached_sql(redis_result)
    if not cached:
        return {"resolved_sql": "", "cached_data": [], "cached_count": 0,
                "status": "", "error": "", "count": 0, "data": []}

    parsed = parse_export_sql(redis_result)
    data = parsed["data"] if parsed["resolved_sql"] else []
    return {
        "resolved_sql": parsed["resolved_sql"],
        "cached_data": data,
        "cached_count": len(data),
        "status": parsed["status"],
        "error": parsed["error"],
        "count": parsed["count"],
        "data": data,
    }
    

def check_chart_intent(query: str, table_data: list) -> dict:
    """
    Check xem user có yêu cầu vẽ biểu đồ trong câu query không
    và data có đủ điều kiện để vẽ không (2-10 dòng).
    """
    query_lower = query.lower().strip()
    has_chart_keyword = any(kw in query_lower for kw in CHART_KEYWORDS)
    data_len = len(table_data) if table_data else 0
    data_suitable = 2 <= data_len <= 10

    return {
        "should_visualize": 1 if (has_chart_keyword and data_suitable) else 0
    }
