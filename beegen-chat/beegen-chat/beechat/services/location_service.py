import asyncio
import json
import logging
import traceback
import math
import unicodedata
import time
import hashlib
from typing import Dict, Any, List, AsyncGenerator

import httpx
try:
    from langfuse.decorators import observe
except ImportError:
    def observe(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from beechat.config import load_settings
from beechat.utils.error_message import stream_error_message
from beechat.services.llm_service import LLMService

# Cấu hình Logger
logger = logging.getLogger('google_adk.utils.function_search_location')
logger.setLevel(logging.DEBUG)

# Cấu hình Cache
_LOCATION_CACHE = {}
_CACHE_TTL = 900  # 15 minutes


def _get_type(struct_data: Dict[str, Any]) -> str:
    return struct_data.get("Type") or struct_data.get("branch_type") or ""


def _get_address(struct_data: Dict[str, Any]) -> str:
    return struct_data.get("Address") or struct_data.get("address") or ""


def _get_province(struct_data: Dict[str, Any]) -> str:
    return struct_data.get("Province") or struct_data.get("province_city") or struct_data.get(
        "province_centrally_governed_city") or ""


def _get_phone(struct_data: Dict[str, Any]) -> str:
    return struct_data.get("phone_number") or struct_data.get("Phone") or ""


def _clean_time_str(t: str) -> str:
    """Loại bỏ giây (:00) rườm rà trong chuỗi thời gian nếu có."""
    if not t:
        return ""
    t = t.strip()
    parts = t.split(":")
    if len(parts) >= 3:
        sec_ampm = parts[2]
        ampm = ""
        if " " in sec_ampm:
            ampm = " " + sec_ampm.split(" ")[1]
        elif sec_ampm.lower().endswith("pm"):
            ampm = " PM"
        elif sec_ampm.lower().endswith("am"):
            ampm = " AM"
        return f"{parts[0]}:{parts[1]}{ampm}"
    return t


def _get_branch_work_time(struct_data: Dict[str, Any]) -> str:
    """Tự động xây dựng câu hiển thị giờ làm việc chi tiết cho Chi nhánh/PGD."""
    morning_start = _clean_time_str(struct_data.get("weekday_morning_transaction_start_time"))
    morning_end = _clean_time_str(struct_data.get("weekday_morning_transaction_end_time"))
    afternoon_start = _clean_time_str(struct_data.get("weekday_afternoon_transaction_start_time"))
    afternoon_end = _clean_time_str(struct_data.get("weekday_afternoon_transaction_end_time"))

    weekday_str = ""
    if morning_start and morning_end and afternoon_start and afternoon_end:
        weekday_str = f"Thứ 2 - Thứ 6: Sáng {morning_start} - {morning_end}, Chiều {afternoon_start} - {afternoon_end}"
    elif morning_start and morning_end:
        weekday_str = f"Thứ 2 - Thứ 6: {morning_start} - {morning_end}"

    # Giờ chốt giao dịch tiền mặt nếu kết thúc sớm hơn giờ giao dịch chung
    morning_cash_end = _clean_time_str(struct_data.get("weekday_morning_cash_transaction_end_time"))
    afternoon_cash_end = _clean_time_str(struct_data.get("weekday_afternoon_cash_transaction_end_time"))
    cash_limits = []
    if morning_cash_end and morning_cash_end != morning_end:
        cash_limits.append(f"sáng đến {morning_cash_end}")
    if afternoon_cash_end and afternoon_cash_end != afternoon_end:
        cash_limits.append(f"chiều đến {afternoon_cash_end}")
    if cash_limits:
        weekday_str += f" (GD tiền mặt: {', '.join(cash_limits)})"

    # Thứ 7
    sat_available = struct_data.get("saturday_available")
    sat_str = ""
    if sat_available == "Y":
        sat_start = _clean_time_str(struct_data.get("saturday_transaction_start_time"))
        sat_end = _clean_time_str(struct_data.get("saturday_transaction_end_time"))
        sat_cash_end = _clean_time_str(struct_data.get("saturday_cash_transaction_end_time"))
        if sat_start and sat_end:
            sat_str = f"Thứ 7: Sáng {sat_start} - {sat_end}"
            if sat_cash_end and sat_cash_end != sat_end:
                sat_str += f" (GD tiền mặt đến {sat_cash_end})"
        else:
            sat_str = "Thứ 7: Có hoạt động sáng"
    else:
        sat_str = "Thứ 7, Chủ Nhật: Nghỉ"

    parts = [p for p in [weekday_str, sat_str] if p]
    return ". ".join(parts)


def _get_work_time(struct_data: Dict[str, Any]) -> str:
    """Lấy hoặc xây dựng thời gian hoạt động."""
    place_type = _get_type(struct_data)
    # Nếu là chi nhánh hoặc có trường giờ mở cửa trong dữ liệu
    if place_type in ("CN", "PGD", "TTKD") or "weekday_morning_transaction_start_time" in struct_data:
        return _get_branch_work_time(struct_data)

    # Đối với ATM/SmartBank/Recycle
    raw_time = struct_data.get("work_time") or struct_data.get("Work_time") or struct_data.get(
        "working_time") or struct_data.get("Working_time") or struct_data.get("Time") or ""
    if not raw_time and place_type in ("ATM", "Recycle", "SMB"):
        return "Hoạt động 24/7"
    return raw_time


@observe()
async def _filter_locations_with_llm(query: str, items: list, user_location: str, settings: Any) -> dict:
    """
    Sử dụng LLM nội bộ để lọc danh sách các địa điểm dựa trên yêu cầu khắt khe (địa lý, thời gian).
    Trả về dict chứa các index hợp lệ: {"matched": [...], "suggested": [...]}
    """
    if not items:
        return {"matched": [], "suggested": []}

    simplified_items = []
    for i, item in enumerate(items):
        simplified_items.append({
            "id": i,
            "name": item.get("name"),
            "address": item.get("address"),
            "province": item.get("province"),
            "work_time": item.get("work_time")
        })

    items_json = json.dumps(simplified_items, ensure_ascii=False)

    prompt = f"""Bạn là một chuyên gia địa lý và hệ thống lọc địa điểm ngân hàng tự động.
Yêu cầu của khách hàng: "{query}" (Khu vực trọng tâm: "{user_location}")

NHIỆM VỤ CỦA BẠN:
Đánh giá mức độ khớp của từng địa điểm trong danh sách (dựa vào 'name', 'address' và 'province') so với yêu cầu của khách hàng.

HƯỚNG DẪN SUY LUẬN ĐỊA LÝ (BẮT BUỘC):
1. Quy tắc Ưu tiên Tìm kiếm Tên Riêng Cụ thể (QUAN TRỌNG NHẤT):
   - Nếu trong câu hỏi của khách hàng có chứa tên gọi đầy đủ hoặc tên gọi cụ thể của một máy ATM, CRM, SMB, Chi nhánh hoặc Phòng giao dịch (ví dụ: "ATM CN KINH BAC", "CRM OKI CN KINH BAC", "PGD Vạn Phúc", "Chi nhánh Ba Đình"...).
   - Bạn PHẢI đối chiếu xem có địa điểm nào trong danh sách có tên trùng khớp chính xác hoàn toàn hoặc gần như hoàn toàn với tên cụ thể được hỏi đó (bất kể viết hoa, viết thường hay có dấu/không dấu).
   - Nếu có, bạn CHỈ ĐƯỢC PHÉP đưa địa điểm/máy trùng khớp đó vào danh sách "matched", và BẮT BUỘC PHẢI LOẠI BỎ hoàn toàn tất cả các địa điểm khác ra khỏi cả danh sách "matched" và "suggested" (không gợi ý/đề xuất bất kỳ địa điểm lân cận hay máy nào khác).
2. Phân tích từ khóa địa danh: Nhận diện các cụm từ chỉ địa danh trong yêu cầu (Ví dụ: "Minh Khai Hà Nội" -> "Minh Khai" và "Hà Nội").
3. Nguyên tắc "Có chứa là Hợp lệ" (Chỉ áp dụng khi không khớp tên riêng cụ thể ở Quy tắc 1):
   - CHỈ CẦN từ khóa địa danh xuất hiện ở BẤT KỲ ĐÂU trong 'name', 'address' hoặc 'province' của địa điểm, thì địa điểm đó ĐƯỢC CHẤP NHẬN.
   - Ví dụ 1: Yêu cầu "Minh Khai" -> Địa chỉ "424 Minh Khai, Phường Vĩnh Tuy" (HỢP LỆ), Địa chỉ "Số 1 Nguyễn Trãi, Phường Minh Khai" (HỢP LỆ).
   - Ví dụ 2: Yêu cầu "Vạn Phúc" -> Tên "PGD Vạn Phúc" (HỢP LỆ), Địa chỉ "Đường Vạn Phúc" (HỢP LỆ).
4. Ràng buộc Tỉnh/Thành phố: Nếu khách hàng chỉ định rõ một Tỉnh/Thành phố, loại bỏ những địa điểm có 'province' khác hoàn toàn.
5. Chống nhầm lẫn: So khớp chính xác chuỗi ký tự, KHÔNG chấp nhận các từ na ná nhau (Ví dụ: Yêu cầu "Vạn Phúc" thì "Vĩnh Phúc" là KHÔNG hợp lệ).
6. Phân loại kết quả:
   - "matched": Đáp ứng Quy tắc 1 (Ưu tiên hàng đầu) hoặc Quy tắc 3.
   - "suggested": Chỉ khớp tỉnh/thành phố nhưng thiếu từ khóa chi tiết, dùng làm gợi ý lân cận.

ĐỊNH DẠNG TRẢ VỀ:
Bạn BẮT BUỘC phải viết suy luận ngắn gọn trước, sau đó trả về kết quả JSON nằm trong block ```json ... ```.

Ví dụ:
Phân tích:
- Yêu cầu: "Minh Khai Hà Nội" -> Từ khóa: "Minh Khai", "Hà Nội".
- Item 0: province "Hà Nội", address "123 Minh Khai" -> Chứa đủ cả hai -> Hợp lệ (matched).
- Item 1: province "Hà Nội", address "456 Vĩnh Tuy" -> Thiếu chữ "Minh Khai" -> Gợi ý (suggested).
```json
{{
  "matched": [0],
  "suggested": []
}}
```

Danh sách địa điểm:
{items_json}
"""

    try:
        base_url = settings.openai_base_url.rstrip('/')
        if not base_url.endswith('/v1'):
            url = f"{base_url}/v1/chat/completions"
        else:
            url = f"{base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
            "X-Vertex-AI-LLM-Request-Type": "shared",
            "X-Vertex-AI-LLM-Shared-Request-Type": "priority"
        }

        # Sử dụng model gemini-3.5-flash-lite thay cho qwen-instruct
        model_name = getattr(settings, "base_fast_onpremise_model", "gemini-3.5-flash-lite")
        if not model_name or "qwen" in model_name.lower():
            model_name = "gemini-3.5-flash-lite"
        if model_name.startswith("litellm_proxy/"):
            model_name = model_name.replace("litellm_proxy/", "")

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system",
                 "content": "You are a helpful banking assistant. Follow the instructions and always output a JSON block wrapped in ```json ... ``` at the end."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0
        }

        logger.info(f"[Location Search] Bắt đầu gọi LLM nội bộ ({model_name}) để lọc {len(items)} kết quả raw...")
        async with httpx.AsyncClient(verify=False, timeout=15.0, trust_env=False) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()

            import re
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Fallback nếu model không trả về markdown block
                json_str = content
                if json_str.startswith("```json"): json_str = json_str[7:]
                if json_str.startswith("```"): json_str = json_str[3:]
                if json_str.endswith("```"): json_str = json_str[:-3]

            result_dict = json.loads(json_str.strip())

            if isinstance(result_dict, dict):
                matched = result_dict.get("matched", [])
                suggested = result_dict.get("suggested", [])

                matched = [int(i) for i in matched] if isinstance(matched, list) else []
                suggested = [int(i) for i in suggested] if isinstance(suggested, list) else []

                logger.info(f"[Location Search] LLM đã lọc xong. Matched: {len(matched)}, Suggested: {len(suggested)}")
                return {"matched": matched, "suggested": suggested}
            elif isinstance(result_dict, list):
                result_indices = [int(i) for i in result_dict]
                return {"matched": result_indices, "suggested": []}
    except Exception as e:
        logger.error(f"[LLM Filter] Lỗi khi gọi LLM lọc: {e}. Áp dụng Python keyword fallback filter...")
        try:
            import re
            q_lower = query.lower()
            stopwords = {
                "tôi", "muốn", "hỏi", "mã", "máy", "địa", "chỉ", "cụ", "thể", "và", "trạng", "thái", 
                "hoạt", "động", "của", "là", "gì", "cho", "mình", "biết", "ở", "đâu", "tại", "gần", "nào",
                "atm", "crm", "smb", "smartbank", "chi", "nhánh", "phòng", "giao", "dịch", "pgd", "mb", "mbbank"
            }
            words = re.findall(r'\w+', q_lower)
            sig_words = [w for w in words if w not in stopwords and len(w) > 1]
            if not sig_words:
                return {"matched": list(range(len(items))), "suggested": []}
                
            matched_indices = []
            for idx, item in enumerate(items):
                name_addr = (item.get("name", "") + " " + item.get("address", "")).lower()
                if sum(1 for w in sig_words if w in name_addr) == len(sig_words):
                    matched_indices.append(idx)
                    
            if not matched_indices:
                for idx, item in enumerate(items):
                    name_addr = (item.get("name", "") + " " + item.get("address", "")).lower()
                    if any(w in name_addr for w in sig_words):
                        matched_indices.append(idx)
                        
            if matched_indices:
                logger.info(f"[Location Search] Python fallback matched: {matched_indices}")
                return {"matched": matched_indices, "suggested": []}
        except Exception as filter_err:
            logger.error(f"[Location Search] Lỗi trong Python fallback filter: {filter_err}")
        return {"matched": list(range(len(items))), "suggested": []}
    return {"matched": [], "suggested": []}


@observe()
async def core_search_location(
        query: str,
        page_size: int = 35,
        type_filter: str = "",
        return_raw: bool = False,
        user_location: str = "",
        offset: int = 0,
        **kwargs
) -> str:
    """
    Hàm search lõi để tìm kiếm thông tin ATM, Chi nhánh, PGD, SmartBank (SMB).

    Args:
        query: Từ khóa tìm kiếm (địa điểm, tên đường...).
        type_filter: Loại địa điểm cần lọc ("ATM", "CN", "PGD", "SMB").
        return_raw: Trả về raw JSON nếu True (dùng cho debug).
        user_location: Vị trí người dùng để tính toán độ liên quan.
    """
    # Đảm bảo page_size được lấy chính xác bất kể key là page_size hay pagesize được truyền từ ngoài qua kwargs
    if "pagesize" in kwargs:
        page_size = kwargs.pop("pagesize")
    elif "page_size" in kwargs:
        page_size = kwargs.pop("page_size")

    # Đảm bảo type_filter được suy luận chính xác từ query nếu type_filter vẫn trống
    if not type_filter:
        query_lower = query.lower()
        if "atm" in query_lower or "rút tiền" in query_lower or "cây atm" in query_lower:
            type_filter = "ATM"
        elif "crm" in query_lower or "nộp tiền" in query_lower or "recycle" in query_lower:
            type_filter = "CRM"
        elif "smartbank" in query_lower or "smb" in query_lower:
            type_filter = "ATM"
        elif "chi nhánh" in query_lower or "cn" in query_lower:
            type_filter = "CN"
        elif "phòng giao dịch" in query_lower or "pgd" in query_lower:
            type_filter = "PGD"
        elif "trung tâm kinh doanh" in query_lower or "ttkd" in query_lower:
            type_filter = "TTKD"
        elif "hội sở" in query_lower:
            type_filter = "HO"

    if type_filter and type_filter.strip().upper() == "SMB":
        type_filter = "ATM"

    logger.info(f"Thực hiện tìm kiếm Location/Branch/SMB cho query: {query}")

    settings = load_settings()
    PROJECT_NUMBER = getattr(settings, "kb_atm_prj_number", "901045532135")
    ENGINE_ID = getattr(settings, "kb_atm_engine_id", "dc-atm-pgd_1778856348641")
    API_VERSION = getattr(settings, "kb_atm_api_version", getattr(settings, "kb_api_version", "v1alpha"))
    
    base_url = settings.openai_base_url.rstrip('/')
    if base_url.endswith('/v1'):
        clean_base_url = base_url[:-3].rstrip('/')
    else:
        clean_base_url = base_url

    headers = {
        "x-litellm-api-key": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
        "X-Vertex-AI-LLM-Request-Type": "shared",
        "X-Vertex-AI-LLM-Shared-Request-Type": "priority"
    }

    # URL gọi qua LiteLLM Proxy tới Vertex AI Discovery
    search_url = (
        f"{clean_base_url}/vertex_ai/discovery/{API_VERSION}/projects/{PROJECT_NUMBER}"
        f"/locations/global/collections/default_collection"
        f"/engines/{ENGINE_ID}/servingConfigs/default_search:search"
    )

    if type_filter.strip().upper() == "HO":
        return """💡 **Thông tin hỗ trợ nhận xét địa điểm (dành cho Bee):**
Khách hàng đang tìm kiếm thông tin về Hội sở chính.
Nhiệm vụ của Bee:
1. Trả lời trực tiếp địa chỉ của Hội sở chính được cung cấp bên dưới.

📍 **Danh sách các điểm giao dịch tìm thấy:**

1. 🏦 **Hội Sở Chính MBBank** ✅ [KHỚP CHÍNH XÁC]
   🏠 18 Lê Văn Lương, Phường Yên Hòa, Thành phố Hà Nội
   🗺️ Hà Nội
   🏷️ Hội sở
"""

    # --- Map type_filter → Vertex AI filter expression ---
    _TYPE_FILTER_MAP = {
        "ATM": 'Type: ANY("ATM", "Recycle")',
        "CRM": 'Type: ANY("Recycle")',
        "CN": 'branch_type: ANY("CN")',
        "PGD": 'branch_type: ANY("PGD")',
        "SMB": 'Type: ANY("Recycle")',
        "TTKD": 'branch_type: ANY("TTKD")',
    }
    filter_expr = _TYPE_FILTER_MAP.get(type_filter.strip().upper(), "") if type_filter else ""

    payload = {
        "query": query,
        "pageSize": page_size,  # Lấy candidate pool rộng 50 kết quả từ API để lọc cục bộ chính xác hơn
        "spellCorrectionSpec": {"mode": "AUTO"},
        "languageCode": "vi-VN",
        "userInfo": {"timeZone": "Asia/Bangkok"},
        "contentSearchSpec": {
            "snippetSpec": {"returnSnippet": True}
        }
    }

    if filter_expr:
        payload["filter"] = filter_expr
        logger.info(f"[Location Search] Áp dụng filter: '{filter_expr}'")

    async def _fetch_api(url, payload):
        async with httpx.AsyncClient(verify=False, timeout=15.0, trust_env=False) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    try:
        cache_key = hashlib.md5(f"{query}_{type_filter}_{user_location}".encode()).hexdigest()
        current_time = time.time()

        if cache_key in _LOCATION_CACHE:
            cached_data = _LOCATION_CACHE[cache_key]
            items, timestamp = cached_data[0], cached_data[1]
            if current_time - timestamp < _CACHE_TTL:
                logger.info(f"[Location Search] Phục hồi từ Cache cho query: {query}")
                return await _format_cached_response(items, query=query, type_filter=type_filter,
                                                     user_location=user_location, offset=offset)

        if offset > 0:
            for ck, cached_data in _LOCATION_CACHE.items():
                if len(cached_data) == 5:
                    items, timestamp, c_query, c_type, c_loc = cached_data
                    if c_query == query and (current_time - timestamp < _CACHE_TTL):
                        logger.info(f"[Location Search] Phục hồi từ Cache (Fallback) cho query: {query}")
                        return await _format_cached_response(items, query=query, type_filter=c_type,
                                                             user_location=c_loc, offset=offset)

        data = await _fetch_api(search_url, payload)

        if return_raw:
            return json.dumps(data, indent=2, ensure_ascii=False)

        valid_items = _parse_raw_results(data, type_filter)
        final_items = []
        if valid_items:
            # Giới hạn số lượng đưa vào LLM nội bộ
            valid_items = valid_items[:page_size]

            # Sử dụng LLM nội bộ để lọc chính xác
            filter_result = await _filter_locations_with_llm(query, valid_items, user_location, settings)

            matched_indices = filter_result.get("matched", [])
            suggested_indices = filter_result.get("suggested", [])

            if matched_indices:
                unique_indices = list(dict.fromkeys(matched_indices))
                final_items = [valid_items[i] for i in unique_indices if i < len(valid_items)]
            elif suggested_indices:
                # Không có điểm matched -> dùng điểm suggested (cùng xã/phường) làm fallback
                unique_indices = list(dict.fromkeys(suggested_indices))
                final_items = [valid_items[i] for i in unique_indices if i < len(valid_items)]
                for v in final_items:
                    v["is_fallback"] = True
            else:
                final_items = []

        _LOCATION_CACHE[cache_key] = (final_items, current_time, query, type_filter, user_location)

        return await _format_cached_response(final_items, query=query, type_filter=type_filter,
                                             user_location=user_location, offset=offset)

    except Exception as e:
        logger.error(f"❌ [Location Search] Lỗi: {e}")
        logger.error(traceback.format_exc())
        return f"❌ Xin lỗi, đã có lỗi xảy ra khi tìm kiếm thông tin địa điểm: {str(e)}"


# ==============================================================================
# SECTION: Relevance & Formatting Helpers
# ==============================================================================


def _resolve_name(struct_data: Dict[str, Any]) -> str:
    """Lấy tên hiển thị chính xác theo schema ATM hoặc PGD/CN."""
    place_type = _get_type(struct_data)

    if place_type in ("ATM", "Recycle", "SMB"):
        return struct_data.get("ATM_Name") or struct_data.get("Cabin_Booth") or ""

    if place_type in ("CN", "PGD", "TTKD"):
        return struct_data.get("branch_transaction_office_name") or struct_data.get("branch_name") or struct_data.get(
            "branch_code") or ""

    return (
            struct_data.get("branch_transaction_office_name")
            or struct_data.get("ATM_Name")
            or struct_data.get("branch_name")
            or struct_data.get("Cabin_Booth")
            or ""
    )


def _resolve_type_label(place_type: str) -> str:
    """Chuẩn hóa nhãn loại hình địa điểm."""
    mapping = {
        "ATM": "ATM",
        "CN": "Chi nhánh",
        "PGD": "Phòng Giao Dịch",
        "CHI_NHANH": "Chi nhánh",
        "BRANCH": "Chi nhánh",
        "Recycle": "CRM/Recycle",
        "SMB": "ATM",
        "TTKD": "Trung tâm kinh doanh",
    }
    return mapping.get(place_type, place_type or "N/A")


def _parse_single_result(struct_data: Dict[str, Any]) -> Dict[str, Any]:
    """Trích xuất thông tin cần thiết từ structData của một kết quả."""
    name = _resolve_name(struct_data)
    address = _get_address(struct_data)
    place_type_raw = _get_type(struct_data)
    if place_type_raw == "SMB":
        place_type_raw = "ATM"
    province = _get_province(struct_data)
    phone = _get_phone(struct_data)
    work_time = _get_work_time(struct_data)

    # Mở rộng trích xuất các trường thông tin khác
    extra_info = []

    branch_code = struct_data.get("branch_code")
    if branch_code: extra_info.append(f"Mã chi nhánh: {branch_code}")

    atm_id = struct_data.get("ATM_ID")
    if atm_id: extra_info.append(f"Mã máy: {atm_id}")

    cabin = struct_data.get("Cabin_Booth")
    if cabin: extra_info.append(f"Vị trí đặt máy: {cabin}")

    dev_branch = struct_data.get("Dev__Branch") or struct_data.get("Branch") or struct_data.get(
        "internal_management_branch")
    if dev_branch: extra_info.append(f"Đơn vị quản lý: {dev_branch}")

    fax = struct_data.get("fax_number")
    if fax: extra_info.append(f"Fax: {fax}")

    note = struct_data.get("note")
    if note: extra_info.append(f"Ghi chú: {note}")

    return {
        "name": name,
        "address": address,
        "place_type_raw": place_type_raw,
        "place_type_label": _resolve_type_label(place_type_raw),
        "province": province,
        "phone": phone,
        "work_time": work_time,
        "extra_info": extra_info,
        "status": struct_data.get("Status", ""),
        "biz_type": struct_data.get("Business_Type") or struct_data.get("business_type") or "",
        "struct_data": struct_data
    }


def _build_proximity_context(query: str, user_location: str, type_filter: str, current_offset: int,
                             has_more: bool) -> str:
    """Tạo thông tin context để LLM xử lý danh sách."""
    type_label = _resolve_type_label(type_filter) if type_filter else "điểm giao dịch"
    loc_str = f" tại {user_location}" if user_location else ""

    fallback_prompt = f"""💡 **Thông tin hệ thống (Dành cho LLM):**
Bên dưới là danh sách kết quả tìm kiếm đã được hệ thống phân trang và lọc chuẩn xác.
Khách hàng đang tìm kiếm {type_label}{loc_str}.
YÊU CẦU BẮT BUỘC ĐỐI VỚI BẠN:
1. **HIỂN THỊ NGUYÊN VẸN**: Trình bày danh sách CHÍNH XÁC như kết quả bên dưới, TUYỆT ĐỐI KHÔNG tự ý lọc bớt.
2. **GIỮ NGUYÊN SỐ THỨ TỰ**: Bắt buộc in nguyên số thứ tự đã được đánh sẵn ở mỗi dòng (ví dụ "9.", "10."). KHÔNG tự đánh số lại từ 1, KHÔNG tự đếm theo lịch sử chat.
3. **Hiển thị trực tiếp**: Trình bày danh sách một cách rõ ràng, mạch lạc, KHÔNG THÊM BÌNH LUẬN từ lóng hay lời trêu đùa.
"""

    prompt = fallback_prompt
    try:
        from app.utils.langfuse_utils import get_compiled_prompt_with_fallback
        compiled = get_compiled_prompt_with_fallback(
            prompt_name="BEECHAT_LOCATION_SEARCH_CACHED_CONTEXT",
            variables={"user_location": user_location, "type_label": type_label, "loc_str": loc_str},
            fallback_value=fallback_prompt
        )
        if compiled:
            prompt = compiled
    except Exception:
        pass

    # Ghi đè hoàn toàn luật hiển thị cũ để phù hợp với kiến trúc phân trang mới bằng Python
    override_instruction = (
        f"\n\n🚨 **GHI ĐÈ QUY TẮC HIỂN THỊ VÀ PHÂN TRANG (TUÂN THỦ TUYỆT ĐỐI):**\n"
        f"- BỎ QUA mọi quy tắc cũ liên quan đến việc tự thêm `raw_index: X` hoặc tự lọc lại địa lý.\n"
        f"- Danh sách bên dưới ĐÃ ĐƯỢC HỆ THỐNG PYTHON LỌC KHẮT KHE VÀ PHÂN TRANG CHUẨN XÁC.\n"
        f"- BẠN TUYỆT ĐỐI KHÔNG ĐƯỢC TỰ Ý LỌC BỎ BẤT KỲ ĐỊA ĐIỂM NÀO TRONG DANH SÁCH BÊN DƯỚI.\n"
        f"- BẠN PHẢI GIỮ NGUYÊN SỐ THỨ TỰ CÓ SẴN (ví dụ nếu danh sách bắt đầu bằng {current_offset + 1}., bạn phải in đúng {current_offset + 1}.). KHÔNG đếm lại từ 1, KHÔNG nối tiếp sai từ lịch sử chat.\n"
    )

    PAGE_SIZE = 8
    if has_more:
        next_page = (current_offset // PAGE_SIZE) + 2
        clean_query = query.strip()
        override_instruction += f"- VẪN CÒN kết quả ở trang sau. Bạn BẮT BUỘC PHẢI THÊM chính xác nút `<button value=\"Xem thêm {clean_query} (Trang {next_page})\">Xem thêm</button>` vào cuối câu trả lời.\n"
    else:
        override_instruction += f"- ĐÃ HẾT kết quả (hoặc đây là danh sách tham khảo). BẠN TUYỆT ĐỐI KHÔNG ĐƯỢC PHÉP thêm nút 'Xem thêm'.\n"

    prompt += override_instruction
    return prompt


def _parse_raw_results(data: Dict[str, Any], type_filter: str) -> list:
    """Trích xuất và parse danh sách từ dữ liệu Datastore."""
    results = data.get("results", [])
    valid_items = []
    seen = set()

    for item in results:
        doc = item.get("document", {})
        struct_data = doc.get("structData", {})
        derived = doc.get("derivedStructData", {})
        if not struct_data: continue

        parsed = _parse_single_result(struct_data)
        if not parsed["name"] and not parsed["address"]: continue

        # Filter SMB nếu yêu cầu
        if type_filter.strip().upper() == "SMB":
            cabin = struct_data.get("Cabin_Booth", "")
            if "SMB" not in parsed["name"].upper() and "SMB" not in cabin.upper():
                continue

        # Deduplication based on name and address
        key = (parsed["name"].strip().lower(), parsed["address"].strip().lower())
        if key in seen:
            continue
        seen.add(key)

        is_exact = int(derived.get("is_exact_match_query", 0))

        parsed.update({
            "is_exact": is_exact
        })
        valid_items.append(parsed)

    return valid_items


async def _format_cached_response(valid_items: list, query: str = "", type_filter: str = "", user_location: str = "",
                                  offset: int = 0) -> str:
    """Định dạng kết quả từ Cache thành văn bản Markdown."""
    if not valid_items and offset == 0:
        return "📭 Không tìm thấy thông tin ATM, Chi nhánh hoặc SmartBank nào phù hợp với yêu cầu của bạn.\n🚨 LỆNH TỪ HỆ THỐNG: TUYỆT ĐỐI KHÔNG ĐƯỢC GỌI LẠI TOOL TÌM KIẾM. HÃY DỪNG LẠI VÀ TRẢ LỜI KHÁCH HÀNG NGAY LẬP TỨC RẰNG KHÔNG TÌM THẤY."

    query_lower = query.lower()
    detail_keywords = ["chi tiết", "detail", "xem thêm", "tất cả", "nhiều hơn", "đầy đủ", "trang 2", "10"]
    is_detail_request = offset > 0 or any(kw in query_lower for kw in detail_keywords)

    # Trả lời Top 3 địa điểm mặc định. Nếu người dùng yêu cầu chi tiết -> trả lời 10 địa điểm
    PAGE_SIZE = 10 if is_detail_request else 3
    is_fallback = any(item.get("is_fallback") for item in valid_items)

    remaining_items = valid_items[offset:offset + PAGE_SIZE]
    if not remaining_items:
        return "📭 Không tìm thấy hoặc không còn thông tin địa điểm nào khác trong danh sách kết quả."

    has_more = (offset + PAGE_SIZE) < len(valid_items) and not is_fallback

    output = [_build_proximity_context(query, user_location, type_filter, offset, has_more)]

    if is_fallback and offset == 0:
        output.append(f"\n📍 **Danh sách kết quả tìm kiếm:**\n")
        output.append(
            f"📭 **Rất tiếc, tôi không tìm thấy địa điểm nào khớp chính xác với tiêu chí của bạn.**\n💡 *Dưới đây là một số địa điểm lân cận để bạn tham khảo:*\n")
    else:
        output.append(f"\n📍 **Danh sách kết quả tìm kiếm (Trang {offset // PAGE_SIZE + 1}):**\n")

    for i, item in enumerate(remaining_items, offset + 1):
        label = ""
        if item.get("is_exact") and not is_fallback:
            label = " ✅ [KHỚP CHÍNH XÁC]"

        icon = "✨" if ("SMB" in (item['name'] or "").upper() or item['place_type_raw'] == "SMB") else \
            ("🏧" if item['place_type_raw'] == "ATM" else "🏦")

        # Bắt buộc đánh số thứ tự tuyệt đối từ Python để đếm chuẩn 100%
        output.append(f"{i}. {icon} **{item['name']}**{label}")
        output.append(f"   🏠 {item['address']}")
        if item['province']: output.append(f"   🗺️ {item['province']}")
        if item['phone']: output.append(f"   📞 {item['phone']}")
        if item['work_time']: output.append(f"   ⏰ {item['work_time']}")
        if item['biz_type']: output.append(f"   🏷️ {item['biz_type']}")
        for info in item.get('extra_info', []):
            output.append(f"   ℹ️ {info}")

        status_norm = (item['status'] or "").lower()
        if status_norm and status_norm not in ["active", "in operation", "đang hoạt động", "hoạt động"]:
            output.append(f"   ⚠️ Trạng thái: {item['status']}")
        output.append("")

    if len(valid_items) > 3 and not is_detail_request:
        output.append("\n💡 *Hệ thống tìm thấy nhiều địa điểm phù hợp hơn. Nếu bạn muốn xem danh sách chi tiết hơn (tối đa 10 địa điểm), vui lòng yêu cầu 'Cho tôi xem chi tiết hơn' hoặc 'Xem thêm địa điểm chi tiết'.*")

    return "\n".join(output)


class LocationService:
    """
    Service for handling location-related queries.
    Integrated with Vertex AI Search & internal LLM filtering.
    """

    def __init__(self, bot_id: str = "default", llm_service: LLMService = None):
        self.bot_id = bot_id
        self.llm_service = llm_service

    async def generate_location_response(self, state: Dict, doc_id: str = "", **kwargs) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Answer queries about MB Bank branch and ATM locations.

        Args:
            state: Dictionary containing conversation state
            doc_id: Document ID for location data

        Yields:
            ChatCompletionChunk: Response chunks
        """
        try:
            logger.info(f"Processing location query for document: {doc_id}")

            query = state.get('query', '')
            user_location = state.get('user_location', '')
            offset = state.get('offset', 0)
            page_size = state.get('page_size', state.get('pagesize', 35))

            type_filter = kwargs.get('type_filter', '')
            if not type_filter:
                if doc_id == "atm":
                    type_filter = "ATM"
                elif doc_id == "cn_pgd":
                    q_lower = query.lower()
                    if "chi nhánh" in q_lower or "cn" in q_lower:
                        type_filter = "CN"
                    elif "phòng giao dịch" in q_lower or "pgd" in q_lower:
                        type_filter = "PGD"
                elif doc_id == "cdm_crm":
                    type_filter = "CRM"
                elif doc_id == "smart_bank":
                    type_filter = "SMB"

            formatted_prompt = await core_search_location(
                query=query,
                page_size=page_size,
                type_filter=type_filter,
                user_location=user_location,
                offset=offset,
                **kwargs
            )

            if self.llm_service:
                async for chunk in self.llm_service.llm_stream(prompt_template=formatted_prompt):
                    yield chunk
            else:
                logger.error("No LLMService instance provided in LocationService")
                async for chunk in stream_error_message(None, formatted_prompt):
                    yield chunk

        except Exception as e:
            logger.error(f"Error generating location response: {str(e)}")
            logger.error(traceback.format_exc())
            if self.llm_service:
                async for chunk in stream_error_message(self.llm_service, "Xin lỗi, tôi gặp sự cố khi xử lý thông tin địa điểm."):
                    yield chunk


async def main():
    import sys
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')

    print("==================================================")
    print(" 🧪 TESTING LOCATION SERVICE & CORE SEARCH")
    print("==================================================")

    test_cases = [
        {"name": "1. SEARCH ATM", "query": "ATM Lê Văn Lương", "type": "ATM", "doc_id": "atm", "user_location": "Lê Văn Lương"},
        {"name": "2. SEARCH CHI NHÁNH", "query": "Chi nhánh Ba Đình", "type": "CN", "doc_id": "cn_pgd", "user_location": "Ba Đình"},
        {"name": "3. SEARCH PHÒNG GIAO DỊCH", "query": "Phòng giao dịch Láng Hạ", "type": "PGD", "doc_id": "cn_pgd", "user_location": "Láng Hạ"},
        {"name": "4. SEARCH SMARTBANK (SMB)", "query": "SmartBank Hà Nội", "type": "SMB", "doc_id": "smart_bank", "user_location": "Hà Nội"},
    ]

    llm_service = LLMService(bot_id="test_location_bot")
    service = LocationService(bot_id="test_location_bot", llm_service=llm_service)

    for tc in test_cases:
        print(f"\n{'█' * 80}")
        print(f" 🧪 TEST CASE: {tc['name']}")
        print(f"   - Query: '{tc['query']}'")
        print(f"   - Type: '{tc['type']}'")
        print(f"   - User Location: '{tc.get('user_location', '')}'")
        print(f"{'█' * 80}")

        # Step 1: Gọi trực tiếp core_search_location lấy formatted search prompt
        print("\n--- [STEP 1: Core Search Location Output] ---")
        formatted = await core_search_location(
            query=tc['query'],
            type_filter=tc['type'],
            user_location=tc.get('user_location', '')
        )
        print(formatted)

        # Step 2: Stream kết quả qua LocationService.generate_location_response
        print("\n--- [STEP 2: LocationService Streaming Output] ---")
        state = {
            "query": tc['query'],
            "user_location": tc.get('user_location', ''),
            "offset": 0
        }
        print("Bot Output: ", end="", flush=True)
        async for chunk in service.generate_location_response(state, doc_id=tc['doc_id']):
            if hasattr(chunk, 'choices') and chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
        print(f"\n\n{'=' * 80}\n")


if __name__ == "__main__":
    asyncio.run(main())
