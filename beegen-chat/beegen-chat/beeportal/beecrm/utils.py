import asyncio
import json
import re
from typing import Optional, Dict, Any, List, Tuple

from beeportal.beecrm.services.beecrm_sv import CLSQuestion, CLSSxkd, ExtractQuery, RewriteQuestion
from beeportal.beecrm.services.mapping_template import DEFAULT_TEMPLATE, TEMPLATE_MAPPING_RCM, TEMPLATE_MAPPING_ASKBACK
from beeportal.beecrm.services.scoring import run_calculate_score, run_calculate_score_sxkd, run_count_scenarios, run_get_user_info, run_query_industry, run_rcm_scenario_id, run_suggest_business_industries


def custom_transform_bot_id(bot_id: str) -> str:
    return f"bot_{bot_id.replace('-', '_')}_chunk"

def init_query(
    messages: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Formats a list of message dictionaries into a structure with query and history.
    
    Takes the most recent message as the query and formats up to 20 previous messages
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
        for m in messages[-11:-1]
    ]

    return {
        "origin_query": query,
        "conversation": history
    }

def verify_workflow_type(metadata: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Decide which workflow should run."""
    data = metadata or {}
    return {"workflow": data.get("workflow", "internal")}


def check_switch_state(
    metadata: Optional[Dict[str, Any]],
    cached: Optional[Dict[str, Any]],
    # count_scenario: Optional[int],
) -> Dict[str, Any]:
    """
    Check switch state from metadata to determine routing and update state.
    
    State transition logic:
    - askback → recommend (next state)
    - recommend → standard (next state)
    - standard → standard (stays the same)
    
    Args:
        metadata: Dictionary containing workflow metadata with 'switched' key
        
    Returns:
        Dictionary with:
        - 'switch_route': Current routing path ('askback', 'recommend', or 'standard')
        - 'updated_metadata': Metadata with updated 'switched' value for next iteration
    
    Examples:
        >>> check_switch_state({"switched": "ask_back"})
        {'switch_route': 'askback', 'updated_metadata': {'switched': 'recommend'}}
        
        >>> check_switch_state({"switched": "recommend"})
        {'switch_route': 'recommend', 'updated_metadata': {'switched': 'standard'}}
        
        >>> check_switch_state({})
        {'switch_route': 'standard', 'updated_metadata': {'switched': 'standard'}}
    """
    data = metadata or {}
    switched = data.get("switched", "").lower().strip()

    get_cache = cached or {}
    
    # Extract L1 and L2 from cached data, handle None values
    l1_raw = get_cache.get("L1")
    l2_raw = get_cache.get("L2")
    count_scenario = get_cache.get("count_scenario")
    
    # Create updated metadata copy
    updated_metadata = data.copy()
    updated_metadata["count_scenario"] = count_scenario
    
    # Normalize variations of askback
    if switched in ["ask_back", "askback", "ask-back"]:
        current_route = "askback"
        updated_metadata["switched"] = "recommend"  # Transition to recommend
    
    # Check for recommend state
    elif switched in ["recommend", "recommendation"]:
        current_route = "recommend"
        updated_metadata["switched"] = "standard" 
        updated_metadata["category"] = l1_raw
        updated_metadata["sub_category"] = l2_raw

    
    # Default to standard flow
    else:
        current_route = "standard"
        updated_metadata["switched"] = "standard"  
    
    return {
        "switch_route": current_route,
        "updated_metadata": updated_metadata
    }

def postprocess_redis_value(redis_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simple postprocess to convert Redis string value to dict.
    
    Args:
        redis_output: Dictionary with 'values' key containing JSON string
        
    Returns:
        Dictionary with parsed values
    """
    
    if isinstance(redis_output, str):
        try:
            return {"values": json.loads(redis_output)}
        except json.JSONDecodeError:
            return {"values": {}}
    
    return {"values": redis_output if isinstance(redis_output, dict) else {}}

def format_filter_input(L1: str = None, L2: str = None, L3: str = None) -> Dict[str, Any]:
    """
    Format các tham số L1, L2, L3 thành cấu trúc input chuẩn.
    
    Args:
        L1: Giá trị cho trường L1 (optional)
        L2: Giá trị cho trường L2 (optional)
        L3: Giá trị cho trường L3 (optional)
    
    Returns:
        Dict có dạng {
            "values": {
                "L1": "Thẻ",
                "L2": None,
                "L3": None
            }
        }
    """
    return { "input_data":
                {
                    "values": {
                        "L1": L1,
                        "L2": L2,
                        "L3": L3
                    }
                }
    }

def prepare_input(cached: dict, sub_category: str = None) -> Dict[str, Any]:
    """
    Format các tham số L1, L2 thành cấu trúc input chuẩn.
    
    Args:
        L1: Giá trị cho trường L1 (optional)
        L2: Giá trị cho trường L2 (optional)
    
    Returns:
        Dict có dạng {
            "values": {
                "L1": "Thẻ",
                "L2": None,
                "L3": None
            }
        }
    """
    return { 
        "L1": cached.get("L1"),
        "L2": sub_category
    }

def wrap_with_values(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wrap input data vào cấu trúc có key "values".
    
    Args:
        input_data: Dict có dạng {
            "L1": "Thẻ",
            "L2": None,
            "L3": None
        }
    
    Returns:
        Dict có dạng {
            "values": {
                "L1": "Thẻ",
                "L2": None,
                "L3": None
            }
        }
    """
    return { "formated_input": 
                {
                    "values": input_data
                }
    }

async def get_number_of_scenarios(input_data: Dict[str, Any]) -> Dict[str, int]:
    """
    Hàm nhận input có cấu trúc values và trả về số lượng scenarios.
    
    Args:
        input_data: Dict có dạng {
            "values": {
                "L1": "Thẻ",
                "L2": null,
                "L3": null
            }
        }
    
    Returns:
        Dict với key "count_scenario": {
            "count_scenario": 5
        }
    """
    # Lấy values từ input
    values = input_data.get("values", {})
    
    # Chuẩn bị filter_values, loại bỏ các giá trị null
    filter_values = {
        key: value 
        for key, value in values.items() 
        if value is not None
    }
    
    # Gọi hàm run_count_scenarios
    result = await run_count_scenarios(filter_values=filter_values)
    
    # Trả về kết quả theo format yêu cầu
    return {
        "count_scenario": result.get("count_scenario", 0)
    }

def select_template(
    cached: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    """
    Select template based on L1 and L2 from cached data.
    
    Args:
        cached: Dictionary containing L1, L2, L3 information
        
    Returns:
        Dictionary with selected template_askback and template_rcm names
        
    Example:
        cached = {"L1": "Tín dụng", "L2": "Nhà đất", "L3": None}
        -> {"template_askback": "BEECRM:GPT_TINDUNG_NHADAT_ASKBACK", 
            "template_rcm": "BEECRM:GPT_TINDUNG_NHADAT_RCM"}
    """
    data = cached or {}
    
    # Extract L1 and L2 from cached data, handle None values
    l1_raw = data.get("L1")
    l2_raw = data.get("L2")
    
    # Convert None to empty string and strip whitespace
    l1 = (l1_raw or "").strip()
    l2 = (l2_raw or "").strip()
    
    # Case 1: Both L1 and L2 are provided
    if l2:
        for (mapped_l1, mapped_l2), template_askback in TEMPLATE_MAPPING_ASKBACK.items():
            if mapped_l2 == l2:
                template_rcm = TEMPLATE_MAPPING_RCM.get((mapped_l1, mapped_l2))
                if template_rcm:
                    return {
                        "template_askback": template_askback,
                        "template_rcm": template_rcm
                    }
    
    # Case 2: Only L1 is provided or L2 not found
    if l1:
        # Try to find L1 with empty L2
        template_askback = TEMPLATE_MAPPING_ASKBACK.get((l1, ""))
        template_rcm = TEMPLATE_MAPPING_RCM.get((l1, ""))
        if template_askback and template_rcm:
            return {
                "template_askback": template_askback, 
                "template_rcm": template_rcm
            }
    
    # Case 3: No match found, use default template
    return {
        "template_askback": DEFAULT_TEMPLATE, 
        "template_rcm": DEFAULT_TEMPLATE
    }


def add_is_crmind_metadata(metadata: Dict[str, Any], cached:Dict[str, Any]) -> Dict[str, Any]:
    """
    Add an `is_scenario` flag into the given metadata and wrap it under `rcm_metadata`.
    
    This function safely updates an existing metadata dictionary by adding the field
    `"is_crmind": True`, then returns the updated metadata wrapped inside a new key
    `"rcm_metadata"`. This ensures a consistent response structure for downstream
    workflow handling in recommendation or scenario-related processes.
    
    Args:
        metadata (Dict[str, Any]): Original metadata dictionary.
                                   Example:
                                   {
                                       "workflow": "gpt",
                                       "switched": "recommend"
                                   }
        cached (Dict[str, Any]): Dictionary containing L1, L2, L3 values from cache.
        category (str): Category name.
        sub_category (str): Sub-category name.
        count_scenario (int): Number of scenarios.
    
    Returns:
        Dict[str, Any]: A dictionary containing the updated metadata under the key
                        `"rcm_metadata"`.
    """
    if not isinstance(metadata, dict):
        metadata = {}

    data = cached or {}
    
    # Extract L1 and L2 from cached data, handle None values
    l1_raw = data.get("L1")
    l2_raw = data.get("L2")
    count_scenario = data.get("count_scenario")

    updated_metadata = metadata.copy()
    updated_metadata["workflow"] = "gpt"
    updated_metadata["switched"] = "standard"
    updated_metadata["category"] = l1_raw
    updated_metadata["sub_category"] = l2_raw
    updated_metadata["count_scenario"] = count_scenario

    # Check if metadata is empty or L1 is "Xin chào"
    if (not l1_raw and not l2_raw) or (l1_raw and l1_raw.strip() == "Xin chào"):
        return {"rcm_metadata": updated_metadata,
                "is_classify": False}
    else:
        return {"rcm_metadata": updated_metadata,
                "is_classify": True}



def determine_internal_route(docs: List) -> Dict[str, Optional[str]]:
    """Decide whether to use cached QA or standard flow.
    Args:
        docs(List) : the docs return from rerank phase
    
    Returns:
        qa_route (str): route name, e.g. 'qa_cached' or 'standard_flow'
        qa_cache (Optional[str]): cached QA content if one was found
    """
    if not docs:
        return {
            "qa_route": "standard_flow",
            "qa_cache": None
        }

    return {"qa_route": "qa_cached",
            "qa_cache": docs[0]["content"]}

async def get_user_info_by_username(
    username: str
) -> Dict[str, str]:
    """
    Lấy thông tin user dựa trên username.
    
    Args:
        username: Tên đăng nhập của user
        
    Returns:
        Dict chứa thông tin user dưới dạng string
        Format: {"user_info": "RM nam 30 tuổi, đang sinh sống tại Tây Hồ, Hà Nội"}
    """
    try:
        # Gọi API để lấy thông tin user
        user_data = await run_get_user_info(username=username)
        
        # Format thông tin user thành string
        # Giả sử user_data có các trường: age, gender, location, area
        # Bạn cần điều chỉnh theo cấu trúc response thực tế từ API
        
        user_info_str = "Thông tin RM chưa có trong hệ thống"
            
        return {"user_info": user_info_str}
        
    except Exception as e:
        return {"user_info": "RM thông tin cơ bản"}

def route_qa_flow(docs: List, query: str) -> Dict[str, Any]:
    """
    Xác định xem câu trả lời QA có chứa sub-category (L2) hay không.
    - Nếu có button → L1 có L2, cần cho người dùng chọn L2
    - Nếu không có button → L1 không có L2, gọi API calculate scenario trực tiếp
    
    Args:
        docs (List): Nội dung câu trả lời từ QA cache, có thể chứa các button
                       sub-category theo format <Button: tên_sub_category>
        query (str): Câu truy vấn từ người dùng
    
    Returns:
        Dict[str, bool]: Dictionary chứa các key:
                        - is_sub_category True: Nếu tìm thấy ít nhất 1 button sub-category
                        - is_rcm_business_industry True: Nếu query == "SXKD" và không có docs
                        - is_viewmore True: Nếu query == "xem thêm"
    """
    # Chuẩn hóa query về lowercase
    query_lower = query.lower().strip()
    
    if not docs:
        # Kiểm tra query có phải "SXKD" không
        if query_lower == "sxkd":
            return {
                "is_rcm_business_industry": True,
                "is_sub_category": False,
                "is_viewmore": False,
                "is_rcm_standard": False,
                "qa_cache": None
            }
        # Kiểm tra query có phải "xem thêm" không
        elif query_lower == "xem thêm":
            return {
                "is_viewmore": True,
                "is_rcm_business_industry": False,
                "is_sub_category": False,
                "is_rcm_standard": False,
                "qa_cache": None
            }
        else:
            return {
                "is_rcm_business_industry": False,
                "is_sub_category": False,
                "is_viewmore": False,
                "is_rcm_standard": True,
                "qa_cache": None
            }

    # Nếu có docs, xử lý như cũ
    qa_cache = docs[0]["content"]

    is_sub_category = re.findall(r"<Button:\s*(.*?)\s*>", qa_cache)

    if is_sub_category:
        return {
            "is_sub_category": True,
            "is_rcm_business_industry": False,
            "is_viewmore": False,
            "is_rcm_standard": False,
            "qa_cache": qa_cache
        }
    
    return {
        "is_sub_category": False,
        "is_rcm_business_industry": False,
        "is_viewmore": False,
        "is_rcm_standard": False,
        "qa_cache": qa_cache
    }


## ========== function wapper format response ================

def create_chunk(
    content: str,
    scenarios: List[Dict[str, Any]] = [],
    share_scenarios: bool = False,
    crmBusinessIndustries: List[Dict[str, Any]] = []
) -> Dict[str, Any]:
    """
    Tạo response chunk theo định dạng chuẩn cho CRM chatbot, sử dụng key 'content' thay vì 'choices'.

    Hàm này đóng gói nội dung phản hồi cùng metadata thành cấu trúc thống nhất, 
    giúp frontend dễ dàng hiển thị nội dung trả lời, danh sách kịch bản hoặc gợi ý ngành nghề.

    Args:
        content (str): Nội dung phản hồi chính gửi cho người dùng.
                       Ví dụ: "Dưới đây là kịch bản bán hàng phù hợp nhất với khách hàng của bạn..."
        
        scenarios (List[Dict[str, Any]], optional): Danh sách kịch bản bán hàng liên quan.
                       Mỗi phần tử thường gồm:
                           - scenario_id (str): ID của kịch bản
                           - scenario_name (str): Tên kịch bản
                           - score (float): Điểm phù hợp
                           - random (bool): True nếu kịch bản được chọn ngẫu nhiên
                       Mặc định là danh sách rỗng.
        
        share_scenarios (bool, optional): Cờ cho phép hiển thị nút “Chia sẻ kịch bản mới”.
                       Giá trị True thường được bật khi không tìm thấy kịch bản phù hợp.
                       Mặc định là False.
        
        crmBusinessIndustries (List[Dict[str, Any]], optional): Danh sách ngành nghề gợi ý.
                       Mỗi phần tử gồm:
                           - businessIndustryId (str): ID ngành
                           - businessIndustryName (str): Tên ngành
                           - scenarioCount (int): Số lượng kịch bản thuộc ngành
                       Mặc định là danh sách rỗng.

    Returns:
        Dict[str, Any]: Dictionary chứa response được chuẩn hóa, gồm:
            {
                "response_qa": {
                    "content": str,  # Nội dung phản hồi
                    "docs": list,    # Danh sách tài liệu (hiện để trống)
                    "metadata": {
                        "workflow": "internal",
                        "scenarios": List[Dict],            # Danh sách kịch bản
                        "share_scenarios": bool,            # Cờ chia sẻ
                        "crmBusinessIndustries": List[Dict] # Ngành nghề gợi ý
                    }
                }
            }
    """

    chunk = {
        "content": content,
        "docs": [],
        "metadata": {
            "workflow": "internal",
            "scenarios": scenarios,
            "share_scenarios": share_scenarios,
            "crmBusinessIndustries": crmBusinessIndustries
        }
    }

    return {"response": chunk}

def extract_answer_from_qa(
    qa_content: str
) -> Dict[str, str]:
    """
    Trích xuất nội dung "Câu trả lời:" từ string Q&A.
    
    Args:
        qa_content: String chứa nội dung Q&A với format:
                   "File tài liệu: ... Câu hỏi: ... Câu trả lời: ..."
        
    Returns:
        Dict với key "answer" chứa nội dung câu trả lời
        {"answer_qa": "Chào bạn! Mình là Trợ lý..."}
        
    Example:
        Input: "File tài liệu: Q&A.docx Câu hỏi: Xin chào Câu trả lời: Chào bạn! ..."
        Output: {"answer_qa": "Chào bạn! Mình là Trợ lý bán hàng thông minh. ..."}
    """
    if not qa_content or not isinstance(qa_content, str):
        return {"answer": ""}
    
    # Method 1: Sử dụng regex để tìm nội dung sau "Câu trả lời:"
    match = re.search(r'Câu trả lời:\s*(.*)', qa_content, re.DOTALL)
    
    if match:
        answer = match.group(1).strip()
        return {"answer_qa": answer}
    
    # Fallback: nếu không tìm thấy, return empty string
    return {"answer_qa": ""}

async def create_chunk_for_suggest(
        content: str,
        username: str,
        scenarios: List[Dict] = [],
        share_scenarios: bool = False,
    ) -> Dict:
    """
    Create a response chunk with business industry suggestions for CRM chatbot.
    
    This function generates a standardized response that includes both the reply content
    and suggested business industries fetched based on the user's profile. The response
    follows OpenAI's streaming format for consistent frontend processing.
    
    Args:
        content (str): Text content to display to the user.
                      Example: "Here are the suggested industries for sales scenarios..."
        
        username (str): Username to fetch personalized business industry suggestions.
                       Used to determine user's region/area for relevant recommendations.
        
        scenarios (List[Dict], optional): List of sales scenarios. Each dict contains:
                                         - scenario_id: Scenario identifier
                                         - scenario_name: Scenario title
                                         - score: Relevance score
                                         - random: True if randomly selected
                                         Defaults to [].
        
        share_scenarios (bool, optional): Flag indicating if user should share scenarios.
                                         Set to True when no matching scenarios found,
                                         prompting user to contribute their own.
                                         Defaults to False.
    
    Returns:
        contents (str): Text sent to the fake LLM node.
        docs (List[Dict[str, Any]]): Related documents (currently empty).
        metadata (Dict[str, Any]): Extra data with scenarios, share flag, industries.
    
    Note:
        The function calls run_suggest_business_industries() to fetch top 5 industries
        based on user's region and scenario availability in their area.
    """
    
    industries = await run_suggest_business_industries(
                    username=username
                )
    
    chunk = {
        "content": content,
        "docs": [],
        "metadata": {
            "scenarios": scenarios,
            "share_scenarios": share_scenarios,
            "crmBusinessIndustries": industries
        }
    }

    return {
        "contents": chunk.get("content", ""),
        "docs": chunk.get("docs", []),
        "metadata": chunk.get("metadata", {})
    }

# region ====================== rcm scenarios with l1, l2 ==============================

def process_scenarios(
    scenarios: List[Dict]
) -> Tuple[str, bool]:
    if scenarios:
        if 'random' not in scenarios[0]:
            content_response = "Dưới đây là kịch bản bán hàng được xây dựng theo yêu cầu của bạn. Hãy áp dụng ngay để nâng cao hiệu quả bán hàng nhé.\n"
            share_scenarios = False

        elif scenarios[0]['random'] == False:
            content_response = "Dưới đây là kịch bản bán hàng được xây dựng theo yêu cầu của bạn. Hãy áp dụng ngay để nâng cao hiệu quả bán hàng nhé.\n"
            share_scenarios = False

        else:
            content_response = "Bạn quả là người ham học hỏi vì đã tham khảo toàn bộ những kịch bản bán hàng hiệu quả mà tôi phải vắt óc để nghĩ ra. Hãy cho tôi thêm thời gian để suy nghĩ ra những kịch bản mới nhé. Vui lòng tham khảo lại 1 kịch bản hấp dẫn mà tôi đã từng chia sẻ cho bạn"
            share_scenarios = False

    else:
        content_response = f"Hiện tại tôi chưa có kịch bản bán theo yêu cầu của bạn, tôi sẽ cập nhật và gửi tới bạn trong thời gian gần nhất. Bạn có vui lòng chia sẻ kịch bản bán hàng hiệu quả mà bạn đã từng áp dụng trong thực tế công việc?"
        share_scenarios = False
    
    return content_response, share_scenarios


async def recommend_scenarios_standard(username: str, category: str, sub_category: str, count_scenario: Optional[int] = 0) -> Dict:
    """
    Gợi ý kịch bản bán hàng chuẩn dựa trên category và sub_category.

    Hàm này xử lý luồng gợi ý kịch bản cho các sản phẩm tiêu chuẩn (không phải sản xuất kinh doanh - SXKD).
    Nó gọi API tính điểm phù hợp của các kịch bản dựa trên thông tin người dùng, 
    sau đó chọn nội dung phù hợp nhất và đóng gói thành response chuẩn.

    Args:
        username (str): Mã nhân viên/username của RM để xác định vùng miền, khu vực phục vụ việc tính điểm.
                        Ví dụ: "chaundn", "nguyenvana"
        category (str): Category cấp 1 (L1) của sản phẩm.
                        Ví dụ: "Tín dụng", "Huy động vốn", "Bancas", "CDs", "Thẻ"
        sub_category (str): Category cấp 2 (L2) của sản phẩm (có thể để rỗng nếu không có L2).
                            Ví dụ: "Nhà đất", "Ô tô", "SXKD", "Có kỳ hạn"

    Returns:
        contents (str): Text sent to the fake LLM node.
        docs (List[Dict[str, Any]]): Related documents (currently empty).
        metadata (Dict[str, Any]): Extra data with scenarios, share flag, industries.

    """

    # Gọi API tính điểm kịch bản
    scenarios = await run_calculate_score(
        username=username,
        category=category,
        sub_category=sub_category
    )

    # Xử lý kết quả để lấy nội dung phản hồi và flag chia sẻ
    content_response, share_scenarios = process_scenarios(scenarios)
    
    # Tạo chunk theo định dạng chuẩn với key 'content'
    chunk = create_chunk(
        content=content_response,
        scenarios=scenarios,
        share_scenarios=share_scenarios
    )["response"]

    metadata = chunk.get("metadata", {})
    metadata["count_scenario"] = count_scenario

    # Trả về dữ liệu cuối cùng
    return {
        "contents": chunk.get("content", ""),
        "docs": chunk.get("docs", []),
        "metadata": metadata
    }

async def recommend_scenarios_special(username: str, cate: str, sub_cate: str, count_scenario: Optional[int] = 0) -> Dict:
    """
    Gợi ý kịch bản bán hàng chuẩn dựa trên category và sub_category.

    Hàm này xử lý luồng gợi ý kịch bản cho các sản phẩm tiêu chuẩn (không phải sản xuất kinh doanh - SXKD).
    Nó gọi API tính điểm phù hợp của các kịch bản dựa trên thông tin người dùng, 
    sau đó chọn nội dung phù hợp nhất và đóng gói thành response chuẩn.

    Args:
        username (str): Mã nhân viên/username của RM để xác định vùng miền, khu vực phục vụ việc tính điểm.
                        Ví dụ: "chaundn", "nguyenvana"
        category (str): Category cấp 1 (L1) của sản phẩm.
                        Ví dụ: "Tín dụng", "Huy động vốn", "Bancas", "CDs", "Thẻ"
        sub_category (str): Category cấp 2 (L2) của sản phẩm (có thể để rỗng nếu không có L2).
                            Ví dụ: "Nhà đất", "Ô tô", "SXKD", "Có kỳ hạn"

    Returns:
        contents (str): Text sent to the fake LLM node.
        docs (List[Dict[str, Any]]): Related documents (currently empty).
        metadata (Dict[str, Any]): Extra data with scenarios, share flag, industries.
        category (str): .
        sub_category (str): .

    """

    # Gọi API tính điểm kịch bản
    scenarios = await run_calculate_score(
        username=username,
        category=cate,
        sub_category=sub_cate
    )

    print("scenariossssssssssss: ", scenarios)

    # Xử lý kết quả để lấy nội dung phản hồi và flag chia sẻ
    content_response, share_scenarios = process_scenarios(scenarios)
    
    # Tạo chunk theo định dạng chuẩn với key 'content'
    chunk = create_chunk(
        content=content_response,
        scenarios=scenarios,
        share_scenarios=share_scenarios
    )["response"]

    metadata = chunk.get("metadata", {})
    metadata["count_scenario"] = count_scenario

    new_category = scenarios[0]['category']
    new_sub_category = scenarios[0]['sub_category']
    print("scenariossssssssssss: ", new_sub_category)

    # Trả về dữ liệu cuối cùng
    return {
        "contents": chunk.get("content", ""),
        "docs": chunk.get("docs", []),
        "metadata": metadata,
        "category": new_category,
        "sub_category": new_sub_category
    }

def is_scenarios_empty(metadata: Dict[str, Any]) -> bool:
    """
    Kiểm tra xem trường 'scenarios' trong phần 'metadata' có rỗng hay không.

    Hàm này truy cập vào key 'metadata' trong đối tượng đầu vào,
    sau đó lấy danh sách 'scenarios' để xác định xem nó có phần tử nào không.

    Args:
        data (Dict[str, Any]): Dữ liệu đầu vào chứa 'metadata'.
                               Ví dụ:
                               {
                                   "anchor": None,
                                   "metadata": {
                                       "workflow": "internal",
                                       "scenarios": [],
                                       "share_scenarios": True,
                                       "crmBusinessIndustries": []
                                   }
                               }

    Returns:
        is_scenarios (bool)
    """
    scenarios = metadata.get("scenarios", [])
    return {"is_scenarios": not bool(scenarios)}


# endregion ====================== rcm scenarios with l1, l2 ==============================


#  region ================== run l3 flow ===================================

def business_industry_route_decision(metadata: Dict) -> Dict[str, Any]:
    """
    Quyết định có routing vào luồng xử lý business industry (SXKD) hay không.
    
    Hàm này kiểm tra metadata từ FE để xác định xem người dùng có đang chọn một
    ngành nghề cụ thể (business industry) hay không. Nếu có, sẽ route vào luồng
    xử lý SXKD để gợi ý kịch bản theo ngành nghề đã chọn, đồng thời trả về thông tin
    ngành nghề để sử dụng cho các node tiếp theo.
    
    Args:
        metadata (Dict): Dictionary chứa metadata từ request, có thể chứa:

    
    Returns:
        Dict[str, Any]: Dictionary chứa thông tin routing và business industry:
            {
                "business_industry_flow": bool,         # True nếu route vào SXKD flow
                "businessIndustryId": Optional[str],     # ID ngành nghề hoặc None
                "businessIndustryName": Optional[str]    # Tên ngành nghề hoặc None
            }
            
    """
    # Kiểm tra metadata
    if metadata is not None:
        crmBusinessIndustry = metadata.get("crmBusinessIndustry", None)
        
        if crmBusinessIndustry is not None:
            businessIndustryId = crmBusinessIndustry.get("businessIndustryId", None)
            businessIndustryName = crmBusinessIndustry.get("businessIndustryName", None)

            if businessIndustryName is not None:
                return {
                    "business_industry_flow": True,
                    "businessIndustryId": businessIndustryId,
                    "businessIndustryName": businessIndustryName
                }
            
    return {
        "business_industry_flow": False,
        "businessIndustryId": None,
        "businessIndustryName": None
    }

async def run_business_industry_flow(
    username: str,
    businessIndustryId: Optional[str],
    businessIndustryName: str,
    count_scenario: int
) -> Dict[str, Any]:
    """
    Xử lý luồng gợi ý kịch bản bán hàng cho ngành nghề cụ thể (SXKD).
    
    Args:
        username (str): Mã nhân viên/username của RM để xác định thông tin vùng miền,
                       khu vực, kinh nghiệm phục vụ việc tính điểm kịch bản.
                       Ví dụ: "chaundn", "nguyenvana"
        
        businessIndustryId (Optional[str]): ID của ngành nghề trong database.
                                           Có thể None nếu chỉ có tên ngành.
                                           Ví dụ: "BI001", "BI123", None
        
        businessIndustryName (str): Tên ngành nghề đã được chọn.
                                   Bắt buộc phải có giá trị.
                                   Ví dụ: "Nông nghiệp", "Chế biến thực phẩm",
                                          "Kinh doanh thời trang"
    
    Returns:
        contents (str): Text sent to the fake LLM node.
        docs (List[Dict[str, Any]]): Related documents (currently empty).
        metadata (Dict[str, Any]): Extra data with scenarios, share flag, industries.

    
    """
    scenarios = await run_calculate_score_sxkd(
        username=username,
        businessIndustryId=businessIndustryId,
        businessIndustryName=businessIndustryName
    )
    
    content_response, share_scenarios = process_scenarios(scenarios)

    chunk = create_chunk(
        content=content_response,
        scenarios=scenarios,
        share_scenarios=share_scenarios
    )["response"]

    metadata = chunk.get("metadata", {})
    metadata["count_scenario"] = count_scenario

    return {
        "contents": chunk.get("content", ""),  
        "docs": chunk.get("docs", []),
        "metadata": metadata
    }

#  endregion ================== run l3 flow ===================================


# region =================== standard flow ==================================

def preprocess_rewrite(origin_query: str, messages: List[Dict[str, Any]]):
    """
    Xử lý lại danh sách tin nhắn hội thoại sau bước rewrite truy vấn.

    Args:
        origin_query (str): Câu truy vấn gốc của người dùng.
                            Ví dụ: "xem thêm các kịch bản khác"
        
        messages (List[Dict[str, Any]]): Danh sách toàn bộ tin nhắn trong hội thoại,
                                         mỗi phần tử có cấu trúc:
                                         {
                                             "role": "user" | "assistant",
                                             "content": "nội dung tin nhắn"
                                         }

    Returns:
        Dict[str, Any]: Kết quả xử lý hội thoại.
            - Nếu có chứa "xem thêm" trong query và có nhiều hơn 1 tin nhắn:
                {
                    "conversation_processed": List[Dict]  # Danh sách tin nhắn đã lọc
                }

    """
    
    if "xem thêm" in origin_query.lower() and len(messages) > 1:
        messages_user = [
            a for a in messages[:-1]
            if ("xem thêm" not in a["content"].lower() and a["role"] == "user")
        ] + [messages[-1]]
        return {"conversation_processed": messages_user}
    else:
        return {"conversation_processed": messages}
    
def check_viewmore_flow(cached: dict) -> Dict[str, bool]:
    """
    Kiểm tra flow "xem thêm" và xác định có phải business industry flow không.

    Args:
        cached (dict): Dictionary chứa thông tin cache với cấu trúc:
                      {
                          "L1": str | None,
                          "L2": str | None,
                          "L3": str | None
                      }

    Returns:
        Dict[str, bool]: Kết quả kiểm tra flow với 2 trường:
            - is_business_industry (bool): True nếu có "xem thêm" VÀ L3 khác None

    """
    
    # Nếu có "xem thêm", kiểm tra L3
    l3_value = cached.get("L3")
    
    # "xem thêm" có và L3 khác None -> cả 2 True
    if l3_value is not None and l3_value != "":
        return {
            "is_business_industry": True
        }
    
    return {
        "is_business_industry": False
    }

def format_conversation(conversation_processed: List[Dict[str, Any]]):
    """
    Định dạng lại lịch sử hội thoại thành chuỗi văn bản dễ đọc.

    Args:
        conversation_processed (List[Dict[str, Any]]): 
            Danh sách tin nhắn đã qua xử lý (thường từ `postprocess_rewrite`),
            mỗi phần tử có cấu trúc:
            {
                "role": "user" | "assistant",
                "content": "nội dung tin nhắn"
            }

    Returns:
        Dict[str, List[str]]: Dictionary chứa danh sách hội thoại đã định dạng.
            Cấu trúc:
            {
                "formated_conversation": [
                    "User: Xin chào",
                    "Bot: Chào bạn, tôi có thể giúp gì?"
                ]
            }
    """
    _history = [
        f"User: {m['content']}"
        if m['role'] == 'user'
        else f"Bot: {m['content']}"
        for m in conversation_processed[-11:-1]
    ]

    return {"formated_conversation": _history}


def postprocess_rewrite(query: str, origin_query: str)-> Dict[str, str]:
    """
    Xử lý và parse kết quả rewrite query từ XML format.



    Args:
        query: Chuỗi XML chứa rewritten query.
            Ví dụ: "<rewrite>Tư vấn vay mua nhà đất</rewrite>"
        origin_query: Câu truy vấn gốc của người dùng, dùng làm fallback 
            khi parse XML thất bại.

    Returns:
        Dict: Dictionary chứa key "rewrited_query" với value là object 
            RewriteQuestion đã được parse từ XML.
    """
    try:
        parser_data = RewriteQuestion.from_xml_string(query)
        return {"rewrited_query": parser_data.rewrite}
    except Exception:
        origin_parser_data = RewriteQuestion.from_xml_string(f"<rewrite>{origin_query}</rewrite>")
        return {"rewrited_query": origin_parser_data.rewrite}

def postprocess_cls_question(query: str)-> Dict[str, str]:
    """
    Parse kết quả phân loại intent từ XML format.

    Args:
        query: Chuỗi XML chứa kết quả classification.
            Ví dụ: "<intent>true</intent>" hoặc "<intent>false</intent>"

    Returns:
        dict: Dictionary chứa key "intent" với value là string intent 
            đã được parse từ XML. Mặc định là "false" nếu parse thất bại.

    """
    try:
        parser_data = CLSQuestion.from_xml_string(query)
        return {"intent_question": parser_data.intent}
    except Exception:
        default = CLSQuestion.from_xml_string(
                f"""<intent>false</intent>"""
            )
        return {"intent_question": default.intent}
    
def postprocess_extract_query(query: str) -> Dict[str, str]:
    """
    Parse và trích xuất thông tin phân loại query từ XML format.


    Args:
        query: Chuỗi XML chứa thông tin phân loại.
            Ví dụ: 
```xml
            <L1>Sản phẩm vay</L1>
            <L2>Vay mua nhà</L2>
            <relation>yes</relation>
```

    Returns:
        dict: Dictionary chứa 3 keys:
            - "L1": Phân loại cấp 1 (mặc định: "none")
            - "L2": Phân loại cấp 2 (mặc định: "none")
            - "relation": Mối quan hệ giữa L1 và L2 (mặc định: "no")
    """
    try:
        parser_data = ExtractQuery.from_xml_string(query)
        return {
            "L1": parser_data.L1,
            "L2": parser_data.L2,
            "relation": parser_data.relation,
        }
    except Exception:
        default = ExtractQuery.from_xml_string(
            """<L1>none</L1>
               <L2>none</L2>
               <relation>no</relation>"""
        )
        return {
            "L1": default.L1,
            "L2": default.L2,
            "relation": default.relation,
        }
    
def postprocess_classify_business_industry(query: str) -> Dict[str, str]:
    """
    Parse và phân loại ngành nghề kinh doanh từ XML format.

    Hàm này parse XML string chứa thông tin phân loại ngành nghề sản xuất 
    kinh doanh (SXKD), ngành chính và mã ngành. Nếu parse thất bại, trả về 
    giá trị mặc định "false" cho sxkd/major và "-1" cho code.

    Args:
        query: Chuỗi XML chứa thông tin phân loại ngành nghề.
            Ví dụ: 
```xml
            <sxkd>true</sxkd>
            <major>Nông nghiệp</major>
            <code>01</code>
```

    Returns:
        dict: Dictionary chứa 3 keys:
            - "sxkd": Thuộc lĩnh vực sản xuất kinh doanh (true/false, mặc định: "false")
            - "major": Ngành nghề chính (mặc định: "false")
            - "code": Mã ngành nghề (mặc định: "-1")

    """
    try:
        parser_data = CLSSxkd.from_xml_string(query)

        return {
            "sxkd": parser_data.sxkd,
            "major": parser_data.major,
            "code": parser_data.code
        }

    except Exception as e:
        default = CLSSxkd.from_xml_string(
            """<sxkd>false</sxkd>
               <major>false</major>
               <code>-1</code>"""
        )
        return {
            "sxkd": default.sxkd,
            "major": default.major,
            "code": default.code
        }

# endregion =================== standard flow ==================================


# region ===================== business industry standard flow =================

def regex_query_industry(
    query: str,
    username: str,
    code: str,
) -> Dict[str, Any]:
    """
    Process an industry-related query and extract corresponding sales scenarios.
    
    This function calls `run_query_industry` to retrieve industry data based on the
    given query, username, and code. It determines the type of response and returns
    structured data suitable for further processing in CRM chatbot workflows.
    
    If the API call fails, the function returns a default response indicating no
    available industry data.
    
    Args:
        query (str): User input or search query describing the business industry.
                     Example: "vay vốn thu mua nông sản"
        
        username (str): Username of the Relationship Manager (RM) executing the query.
                        Used to identify the user's region or area for personalization.
        
        code (str): A code or identifier used to classify or route the query.
                    Example: "L3_TINDUNG_SXKD"
    
    Returns:
        Dict[str, Any]: A standardized response object containing:
            - response_type (str): Type of the returned data, e.g. `"scenarios"` or `"crmBusinessIndustries"`.
            - data (Dict): The associated data structure.
                * If success:
                    {
                        "response_type": "scenarios",
                        "data": {
                            "scenarios": [...]
                        }
                    }
                * If failed:
                    {
                        "response_type": "crmBusinessIndustries",
                        "data": {
                            "crmBusinessIndustries": []
                        }
                    }
    
    """
    try:
        rs_industry = run_query_industry(query, username, code)
        response_type = rs_industry.get("type", "")
        data = rs_industry.get("data", {})

        return {
            "response_type": response_type,
            "data": data
        }

    except Exception:
        return {
            "response_type": "crmBusinessIndustries",
            "data": {
                "crmBusinessIndustries": []
            }
        }
    
async def recommend_scenario_with_chunk(username: str, docs: List) -> Dict[str, Optional[str]]:
    """recommend_scenario_with_chunk.
    Args:
        username (str): username
        docs(List): the docs return from rerank phase
    
    Returns:
        Dict with keys:
        - contents (str): Text sent to the fake LLM node.
        - docs_chunk (List[Dict[str, Any]]): Related documents (currently empty).
        - metadata (Dict[str, Any]): Extra data with scenarios, share flag, industries.
        - crm_category_name (str): CRM category name if found, empty string otherwise.
        - crm_sub_category_name (str): CRM sub-category name if found, empty string otherwise.
        - business_industry_name (str): Business industry name if found, empty string otherwise.
    """
    
    # Khởi tạo giá trị mặc định khi không có docs
    if not docs:
        # Tạo chunk mặc định khi không có scenarios
        content_response, share_scenarios = process_scenarios([])
        chunk = create_chunk(
            content=content_response,
            scenarios=[],
            share_scenarios=share_scenarios
        )["response"]
        
        return {
            "contents": chunk.get("content", ""),
            "docs_chunk": chunk.get("docs", []),
            "metadata": chunk.get("metadata", {}),
            "crm_category_name": "",
            "crm_sub_category_name": "",
            "business_industry_name": ""
        }
    
    # Xử lý khi có docs
    try:
        scenario_data_str = docs[0].get("content", "{}")
        scenario_data = json.loads(scenario_data_str)
        
        scenario_id = scenario_data.get("_id", "")
        business_industry_name = scenario_data.get("business_industry_name", "")
        crm_category_name = scenario_data.get("crm_category_name", "")
        crm_sub_category_name = scenario_data.get("crm_sub_category_name", "")

        # Kiểm tra xem có business_industry_name không để quyết định luồng xử lý
        if business_industry_name:
            # Luồng hiện tại: sử dụng business_industry_name
            count_scenarios = await get_number_of_scenarios(
                {
                    "values": {
                        "L1": "",
                        "L2": "",
                        "L3": business_industry_name
                    }
                }
            )
        else:
            # Luồng mới: sử dụng crm_category_name và crm_sub_category_name
            count_scenarios = await get_number_of_scenarios(
                {
                    "values": {
                        "L1": crm_category_name,
                        "L2": crm_sub_category_name,
                        "L3": ""
                    }
                }
            )
        
        # Gọi API để lấy scenario theo ID
        scenario_data = await run_rcm_scenario_id(
            username=username,
            scenario_id=scenario_id   
        )
        
        # Xử lý kết quả để lấy nội dung phản hồi và flag chia sẻ
        content_response, share_scenarios = process_scenarios(scenario_data)
        
        # Tạo chunk theo định dạng chuẩn
        chunk = create_chunk(
            content=content_response,
            scenarios=scenario_data,
            share_scenarios=share_scenarios
        )["response"]

        metadata = chunk.get("metadata", {})
        metadata["count_scenario"] = count_scenarios["count_scenario"]
        
        # Trả về dữ liệu cuối cùng
        return {
            "contents": chunk.get("content", ""),
            "docs_chunk": chunk.get("docs", []),
            "metadata": metadata,
            "crm_category_name": crm_category_name,
            "crm_sub_category_name": crm_sub_category_name,
            "business_industry_name": business_industry_name
        }
        
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        # Xử lý lỗi khi parse JSON hoặc truy cập dữ liệu
        print(f"Error processing docs: {e}")
        content_response, share_scenarios = process_scenarios([])
        chunk = create_chunk(
            content=content_response,
            scenarios=[],
            share_scenarios=share_scenarios
        )["response"]
        
        return {
            "contents": chunk.get("content", ""),
            "docs_chunk": chunk.get("docs", []),
            "metadata": chunk.get("metadata", {}),
            "crm_category_name": "",
            "crm_sub_category_name": "",
            "business_industry_name": ""
        }
    
def set_hierarchy_in_cache(
    category: Optional[str] = None,
    sub_category: Optional[str] = None,
    business_industry: Optional[str] = None,
    cached: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Tạo fake_cache với hierarchy L1, L2, L3
    
    Args:
        category: Tên category để set cho L1 (ví dụ: "Tín dụng")
        sub_category: Tên sub_category để set cho L2 (ví dụ: "Nhà đất"), optional
        business_industry: Tên business industry để set cho L3, optional
        cached: Dictionary chứa giá trị L1, L2, L3 từ cache hiện tại, optional
        
    Returns:
        fake_cache (dict) Dictionary chứa cache với cấu trúc L1, L2, L3
        
    Example:
        >>> set_hierarchy_in_cache("Tín dụng", "Nhà đất")
        {"L1": "Tín dụng", "L2": "Nhà đất", "L3": None}
        
        >>> set_hierarchy_in_cache("Tín dụng")
        {"L1": "Tín dụng", "L2": None, "L3": None}
        
        >>> set_hierarchy_in_cache("", "", "", {"L1": "Cached L1", "L2": "Cached L2", "L3": "Cached L3"})
        {"L1": "Cached L1", "L2": "Cached L2", "L3": "Cached L3"}
        
        >>> set_hierarchy_in_cache("New L1", None, "", {"L1": "Cached L1", "L2": "Cached L2", "L3": "Cached L3"})
        {"L1": "New L1", "L2": "Cached L2", "L3": "Cached L3"}
    """
    # Khởi tạo cached mặc định nếu không được truyền vào
    if cached is None:
        cached = {"L1": None, "L2": None, "L3": None, "count_scenario": 0}
    
    # Sử dụng giá trị từ cached nếu input là None hoặc chuỗi rỗng
    fake_cache = {
        "L1": category if category else cached.get("L1"),
        "L2": sub_category if sub_category else cached.get("L2"),
        "L3": business_industry if business_industry else cached.get("L3"),
        "count_scenario": cached.get("count_scenario", 0) 
    }
    
    return {"fake_cache": fake_cache}

def extract_cached(
    cached: Optional[Dict[str, Any]],
) -> Dict[str, str]:
    """
    Select template based on L1 and L2 from cached data.
    
    Args:
        cached: Dictionary containing L1, L2, L3 information
        
    Returns:
        Dict with L1, L2, L3
    """
    data = cached or {}
    
    # Extract L1 and L2 from cached data, handle None values
    l1_raw = data.get("L1")
    l2_raw = data.get("L2")
    l3_raw = data.get("L3")

    return {"L1_cache": l1_raw,
            "L2_cache": l2_raw,
            "L3_cache": l3_raw,}

# region ================= New flow ==============================
def check_button_flow(
    metadata: Optional[Dict[str, Any]],
) -> Dict[str, bool]:
    """
    Check if the message is from a button flow.
    
    Args:
        metadata: Dictionary containing workflow and messageType information
        
    Returns:
        Dict with is_button_flow boolean
    """
    if metadata and isinstance(metadata, dict):
        # Check if messageType field exists in metadata
        if "messageType" in metadata:
            return {"is_button_flow": True}
    
    return {"is_button_flow": False}


def update_metadata_with_classification(
    metadata: Dict[str, Any],
    L1: str,
    L2: Optional[str] = None,
    count_scenario: Optional[int] = 0
) -> Dict[str, Any]:
    """
    Update metadata with L1, L2 classification results.
    
    Args:
        metadata: Original metadata dictionary
        L1: L1 category from classification
        L2: L2 sub-category from classification
        
    Returns:
        Dict[str, Any]: Updated metadata with classification info
    """
    if not isinstance(metadata, dict):
        metadata = {}
    
    updated_metadata = metadata.copy()

    # Convert None to empty string and strip whitespace
    l1 = L1.strip() if L1 else ""
    l2 = L2.strip() if L2 else ""

    updated_metadata["category"] = l1
    updated_metadata["sub_category"] = l2
    updated_metadata["count_scenario"] = count_scenario
    
    # Case 1: Both L1 and L2 are provided
    if l2:
        for (mapped_l1, mapped_l2), template_askback in TEMPLATE_MAPPING_ASKBACK.items():
            if mapped_l2 == l2:
                template_rcm = TEMPLATE_MAPPING_RCM.get((mapped_l1, mapped_l2))
                if template_rcm:
                    return {
                        "updated_metadata": updated_metadata,
                        "template_askback": template_askback,
                        "template_rcm": template_rcm
                    }
    
    # Case 2: Only L1 is provided or L2 not found
    if l1:
        # Try to find L1 with empty L2
        template_askback = TEMPLATE_MAPPING_ASKBACK.get((l1, ""))
        template_rcm = TEMPLATE_MAPPING_RCM.get((l1, ""))
        if template_askback and template_rcm:
            return {
                "updated_metadata": updated_metadata,
                "template_askback": template_askback, 
                "template_rcm": template_rcm
            }
    
    # Case 3: No match found, use default template
    return {
        "updated_metadata": updated_metadata,
        "template_askback": DEFAULT_TEMPLATE, 
        "template_rcm": DEFAULT_TEMPLATE
    }
    


# endregion ================= New flow ==============================

    
if __name__ == '__main__':
    # Test without needing PromptManager
    cached = {"L1": "Tín dụng", "L2": "Nhà đất", "L3": None}
    rs = select_template(cached=cached)
    print(rs)