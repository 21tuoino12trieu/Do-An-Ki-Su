import base64
from typing import List, Dict, Any, Optional
from examples.utils.constant import (
    abbr_dict, 
    COMPLAINT_DESCRIPTIONS, 
    COMPLAINT_MAPPING, 
    COMPLAINT_PATTERNS, 
    SCENARIO_LOOKUP,
    REFUSAL_MESSAGES,
    LOCATION_MAPPING,
)
import re
import ast


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
        for m in messages[-21:-1]
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

def clean_json_string(s: str) -> str:
    """
    Remove markdown/literal markers from JSON string.
    Supports ```json ... ```, ''' ... ''', etc.
    """
    # Remove leading/trailing whitespace
    s = s.strip()

    # Remove triple backticks or triple quotes
    s = re.sub(r"^(```\w*|''')", '', s)
    s = re.sub(r"(```|''')$", '', s)

    return s.strip()

def encode_to_base64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def get_intent_retriever(docs: List[Dict], valid_score: float = 0.5) -> Dict[str, str]:
    """
    Args:
        docs (List[Dict])
        valid_score (float)
    
    Returns:
        intent (str)
    """
    valid_count = 0
    
    for doc in docs:
        if doc["score"] > valid_score:
            valid_count += 1
    
    return {
        'intent': 'chitchat' if valid_count == 0 else 'non_chitchat'
    }
    

def get_cache_qa(docs: List) -> Dict[str, Any]:
    """Return the first and the only doc (candidate qa) if exists
    
    Args:
        docs(List) : the docs return from rerank phase
    
    Returns:
        cache_qa(str): the qa cached from db, return None if non-exist
    """
    if not docs:
        return {
            "cache_qa": None
        }
    
    return {
        "cache_qa": docs[0]["content"]
    }
    

def identify_complaint_type(query: str) -> Dict[str, Any]:
    """Xác định loại kiểu khiếu nại
    
    Returns:
        type (str): loại khiếu nại trả về
    """
    query_lower = query.lower()

    for pattern, complaint_type in COMPLAINT_PATTERNS:
        if re.search(pattern, query_lower):
            return {"type": complaint_type}

    # Fallback keyword groups
    if any(k in query_lower for k in ["chuyển tiền", "chuyển khoản"]):
        return {"type": "transfer_failure"}
    if any(k in query_lower for k in ["atm", "rút tiền"]):
        return {"type": "atm_withdrawal_issue"}
    if "thẻ" in query_lower or "card" in query_lower:
        if "phát hành" in query_lower or "không nhận được" in query_lower:
            return {"type": "card_delivery_issue"}
        else:
            return {"type": "card_transaction_issue"}
    if "nạp" in query_lower and any(k in query_lower for k in ["điện thoại", "đt"]):
        return {"type": "topup_issue"}
    if any(k in query_lower for k in ["thái độ", "nhân viên"]):
        return {"type": "staff_complaint"}
    if any(k in query_lower for k in ["app", "ứng dụng"]):
        return {"type": "app_transaction_issue"}

    return {"type": "other_transaction"}


def _get_scenarios_by_ids(scenario_ids: List[str]) -> List[Dict]:
    """Get scenarios by their IDs (O(1) lookup per ID)"""
    return [SCENARIO_LOOKUP[sid] for sid in scenario_ids if sid in SCENARIO_LOOKUP]


def _find_best_matching_scenario(scenarios: List[Dict], query: str) -> Optional[Dict]:
    """Find scenario with most keyword matches"""
    if not query or len(scenarios) <= 1:
        return scenarios[0] if scenarios else None
    
    query_lower = query.lower()
    best_scenario = None
    max_matches = 0
    
    for scenario in scenarios:
        # Count keyword matches in one pass
        matches = sum(1 for keyword in scenario.get("keywords", []) 
                     if keyword.lower() in query_lower)
        
        if matches > max_matches:
            max_matches = matches
            best_scenario = scenario
    
    return best_scenario or scenarios[0]


def _create_default_response(complaint_type: str) -> Dict:
    """Create default response for unknown complaint types"""
    description = COMPLAINT_DESCRIPTIONS.get(complaint_type, "khiếu nại giao dịch")
    return {
        "id": "default",
        "keywords": [],
        "title": description,
        "response": f"Bee xin lỗi vì sự bất tiện bạn đang gặp phải. Để hỗ trợ về {description} của bạn, vui lòng chọn **\"Liên hệ tư vấn viên\"** để được hỗ trợ nhanh chóng. 🙏"
    }


def find_scenario_for_complaint(type: str, query: str = None) -> Dict:
    """
    Find appropriate scenario for complaint type.
    
    Args:
        type: Detected complaint type
        query: Original user query (optional)
        
    Returns:
        id (str)
        keywords (List[str])
        title (str)
        response (str)
    """
    # Get scenario IDs for this complaint type
    scenario_ids = COMPLAINT_MAPPING.get(type, [])
    if not scenario_ids:
        return _create_default_response(type)
    
    # Get actual scenarios
    scenarios = _get_scenarios_by_ids(scenario_ids)
    if not scenarios:
        return _create_default_response(type)
    
    # Find best matching scenario
    best_scenario = _find_best_matching_scenario(scenarios, query)
    return best_scenario or _create_default_response(type)


def get_refusal_message(filter_type: str) -> Dict[str, Any]:
    """
    Lấy thông báo từ chối phù hợp với loại nội dung đã lọc.

    Args:
        filter_type: Loại lọc (1, 2, 3, 4 hoặc "none")

    Returns:
        message(str): Thông báo từ chối phù hợp
    """
    # Sử dụng danh sách thông báo từ file beechat_prompt.py
    message = REFUSAL_MESSAGES.get(filter_type, "Xin lỗi, Bee chưa nắm được mong muốn của bạn. Bạn vui lòng mô tả cụ thể hơn được không, Bee rất sẵn lòng hỗ trợ!")
    return {
        'message': message
    }
    
    
def get_topic_category(topic: str) -> Dict[str, Any]:
    """
    Mapping từ keyword topic về topic category
    
    Args:
        topic: giá trị topic keyword
    
    Returns:
        topic_category(str)
    """
    
    topic_mapping = {
        "card": "generic_card",
        "generic_card": "generic_card",
        "specific_card": "specific_card",
        "payment": "payment",
        "chi_nhanh": "chi nhánh",
        "atm": "atm",
        "cdm_crm": "cdm_crm",
        "smart_bank": "smart bank",
        "app": "app",
        "staff": "staff"
    }
    
    return {
        'topic_category': topic_mapping.get(topic, 'standard')
    }


def get_location_doc_id(topic_category: str) -> Dict[str, Any]:
    """
    Get location document ID from topic
    
    Returns:
        location_doc_id(str)
    """
    for location_type, doc_id in LOCATION_MAPPING.items():
        if location_type in topic_category.lower():
            return {'location_doc_id': doc_id}
    return {'location_doc_id': None}


def create_location_mongo_query(location_doc_id: str) -> Dict[str, Any]:
    """
    Returns:
        query(Dict)
    """
    return {
        "query": {
            "document_id": location_doc_id
        }
    }
    
import json

def post_process_location_data(data: List, keywords: str) -> Dict[str, Any]:
    """
    Returns:
        doc_data (str)
    """
    if not data:
        return {"doc_data": ""}
        
    text_data = data[0].get("text", None)
    text_data = json.loads(text_data)
    
    text_data = [json.dumps(item, indent=0, ensure_ascii=False) for item in text_data]

    
    if not text_data:
        return {"doc_data": ""}
    
    if not keywords:
        keywords = []
    else:
        keywords = keywords.split(",")
            
    if len(keywords) > 0:
        filterer_data = [
            item for item in text_data
            if any(term.lower() in item.lower() for term in keywords)
        ]
        
        document_content = "[\n" + ',\n'.join(filterer_data) + "\n]"
        
        return {
            "doc_data": document_content
        }
    
    return {
        "doc_data": ""
    }


def find_node_in_hierarchy(target_key: str, hierarchy: dict) -> dict:
    """
    Find a node in the card hierarchy tree and determine if it's a leaf node.
    
    A leaf node contains actual card data (IDs), while branch nodes contain 
    subcategories or children.
    
    Args:
        target_key (str): The key name to search for in the hierarchy
        hierarchy (dict, optional): Card hierarchy dict. Defaults to CARD_HIERARCHY_NEW
        
    Returns:
        - found (bool): Whether the target key was found
        - valid (bool): True if node contains card data, False if it has children
        - value (Union[List, str]): Card IDs or children names
            
    Examples:
        >>> find_node_in_hierarchy('visa_infinite')
        {'found': True, 'valid': True, 'value': '72'}
        
        >>> find_node_in_hierarchy('visa_credit') 
        {'found': True, 'valid': False, 'value': ['Visa Infinite', 'Visa Priority', ...]}
    """
    
    def _recursive_search(data: dict, search_key: str) -> dict:
        """Recursively search for a key in nested dictionary structure."""
        
        # Check if key exists at current level
        if search_key in data:
            return data[search_key]
        
        # Search in all nested dictionary values
        for value in data.values():
            if isinstance(value, dict):
                result = _recursive_search(value, search_key)
                if result is not None:
                    return result
                    
        return None
    
    # Search for the target node
    node = _recursive_search(hierarchy, target_key)
    
    # Handle not found case
    if node is None:
        return {
            'found': False, 
            'valid': False, 
            'value': None
        }
    
    # Determine node type and extract relevant data
    # Priority: id > special_ids > card_ids > children > empty
    
    if 'id' in node:
        # Single card node
        return {
            'found': True,
            'valid': True, 
            'value': [node['id']]
        }
        
    elif 'special_ids' in node:
        # Special card variants node  
        return {
            'found': True,
            'valid': True,
            'value': node['special_ids']
        }
        
    elif 'card_ids' in node:
        # Multiple cards node
        return {
            'found': True,
            'valid': True,
            'value': node['card_ids']
        }
        
    elif 'children' in node:
        # Branch node with subcategories
        children_names = [
            child_node.get('name', '') 
            for child_node in node['children'].values()
        ]
        return {
            'found': True,
            'valid': False,
            'value': children_names
        }
        
    else:
        # Empty branch node
        return {
            'found': True,
            'valid': False,
            'value': []
        }


def create_card_batch_inputs(query: str, value: List) -> Dict[str, Any]:
    """
    Returns:    
        batch_data (List[Dict])
    """
    if not value:
        return {
            "batch_data": []
        }
        
    return {
        "batch_data": [
            {
                "query": query, 
                "partition_names": [str(v)]
            } 
            for v in value
        ]
    }

    
def collect_documents(standard_docs: List, card_docs: List, topic_category: str) -> Dict:
    """
    Returns:
        docs(List)
    """
    if topic_category == "specific_card":
        return {"docs": card_docs + standard_docs}
    if topic_category == "generic_card":
        return {"docs": standard_docs + card_docs}
    return {"docs": standard_docs}


def format_filter_documents(docs: List) -> Dict:
    """
    Returns:
        documents_list(List)
    """
    # Prepare documents for batch processing
    documents_list = []
    for i, doc in enumerate(docs):
        content = doc['content']
        content_preview = content[:400] if len(content) > 400 else content
        documents_list.append(f"ID: {i}\nNội dung: {content_preview}")

    documents_text = "\n" + "=" * 60 + "\n".join(documents_list)
    
    return {"documents_list": documents_text}


def prepare_docs_ref(docs: List) -> Dict:
    """
    Returns:
        ref(List)
    """
    return {"ref": [doc['doc'] for doc in docs]}


def collect_relevant_docs(docs: List, relevant_ids: List) -> Dict:
    """
    Returns:
        relevant_docs(List)
    """
    try:
        return {"relevant_docs": [docs[i] for i in range(len(docs)) if i in ast.literal_eval(relevant_ids)]}
    except SyntaxError:
        return {"relevant_docs": []}


def format_final_documents(docs: List) -> Dict:
    """
    Returns:
        documents_text(str)
    """
    if not docs:
        return {"documents_text": "không tìm thấy tài liệu phù hợp"}
    
    return {
        "documents_text": "\n-----------------------------\n".join([f"--- TÀI LIỆU {i} [Nguồn: {doc['doc']}] ---\n{doc['content']}" for i, doc in enumerate(docs)])
    }