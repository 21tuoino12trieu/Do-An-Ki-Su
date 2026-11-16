from typing import Any, Dict, List, Optional
import re
import ast
from beeportal.constant import (
    abbr_dict, 
    COMPLAINT_DESCRIPTIONS, 
    COMPLAINT_MAPPING, 
    COMPLAINT_PATTERNS, 
    SCENARIO_LOOKUP,
    REFUSAL_MESSAGES,
    LOCATION_MAPPING,
)

from beegen.prompts.prompt_manager import PromptManager
PROMPTS = PromptManager("beegen")

def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        return " ".join(text_parts).strip()
    return str(content)

def init_query(
    messages: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Formats a list of message dictionaries into a structure with query and history.

    Takes the most recent message as the query and formats up to 20 previous messages
    as history with "USER:" or "BOT:" prefixes.

    Args:
        messages: List of message dictionaries with 'content' and 'role' keys.

    Returns:
        origin_query: The content of the most recent message.
        conversation: Formatted list of previous messages.
    """
    query = _extract_text_content(messages[-1]['content'])        
    history = [
        f"USER: {_extract_text_content(m['content'])}" 
        if m['role']=='user' 
        else f"BOT: {_extract_text_content(m['content'])}" 
        for m in messages[-21:-1]
    ]
    
    return {
        "origin_query": query,
        "conversation": history
    }
    

def annotate_query(origin_query: str) -> Dict[str, Any]:
    """Adds explanations after abbreviations found in text.

    Args:
        origin_query: Input query to annotate.

    Returns:
        query: Query after annotating abbreviation.
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


def get_intent_retriever(docs: Optional[List[Dict]] = None, qas: Optional[List[Dict]] = None, valid_score: float = 0.5) -> Dict[str, str]:
    """Determines the intent ('chitchat' or 'non_chitchat') based on document scores.

    Args:
        docs: List of documents with their scores.
        valid_score: The score threshold to be considered valid.

    Returns:
        intent: The determined intent.
    """
    valid_count = 0
    
    if docs:
        for doc in docs:
            if doc["score"] > valid_score:
                valid_count += 1
    
    if qas:
        for qa in qas:
            if qa["score"] > valid_score:
                valid_count += 1
    
    return {
        'intent': 'chitchat' if valid_count == 0 else 'non_chitchat'
    }
    

def get_cache_qa(docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Returns the first and only doc (candidate QA) if it exists.

    Args:
        docs: The docs returned from the rerank phase.

    Returns:
        cache_qa: The QA cached from the database; None if non-existent.
        ids: The ID of the matched cached QA; an empty list if non-existent.
    """
    if not docs:
        return {
            "cache_qa": None,
            "ids": []
        }
    
    return {
        "cache_qa": docs[0]["content"],
        "ids": [{"id": docs[0]["id"], "score": f"{docs[0].get("document_matching_score") * 100:.1f}%" if docs[0].get("document_matching_score") is not None else None,}]
    }

def post_process_response(query: str, content: str) -> Dict[str, List[Dict[str, str]]]:
    """Wrap the response into the dialogue format expected by the client.
    Args:
        query: User query.
        content: Content to be responsed.

    Returns:
        dialogue: Conversation payload containing the user message and response.
    """
    return {
        "dialogue": [
            {"role": "user", "content": query},
            {"role": "assistant", "content": content},
        ]
    }
    

def identify_complaint_type(query: str) -> Dict[str, Any]:
    """Identifies the type of complaint from the user query.

    Args:
        query: The user's query.

    Returns:
        type: The identified complaint type.
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
    """Gets scenarios by their IDs using an O(1) lookup per ID.

    Args:
        scenario_ids: A list of scenario IDs to retrieve.

    Returns:
        A list of scenario objects corresponding to the given IDs.
    """
    return [SCENARIO_LOOKUP[sid] for sid in scenario_ids if sid in SCENARIO_LOOKUP]


def _find_best_matching_scenario(scenarios: List[Dict], query: str) -> Optional[Dict]:
    """Finds the scenario with the most keyword matches from the query.

    Args:
        scenarios: A list of scenarios to search through.
        query: The user query to match against scenario keywords.

    Returns:
        The best-matching scenario dictionary, or None if no scenarios are provided.
    """
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
    """Creates a default response for a given complaint type.

    Args:
        complaint_type: The type of complaint.

    Returns:
        A dictionary containing a default response scenario.
    """
    description = COMPLAINT_DESCRIPTIONS.get(complaint_type, "khiếu nại giao dịch")
    return {
        "id": "default",
        "keywords": [],
        "title": description,
        "response": f"Bee xin lỗi vì sự bất tiện bạn đang gặp phải. Để hỗ trợ về {description} của bạn, vui lòng chọn **\"Liên hệ tư vấn viên\"** để được hỗ trợ nhanh chóng. 🙏"
    }


def find_scenario_for_complaint(type: str, query: str = None) -> Dict:
    """Finds an appropriate scenario for a given complaint type.

    If multiple scenarios match, it selects the best one based on keyword matching
    against the query.

    Args:
        type: The detected complaint type.
        query: The original user query (optional).

    Returns:
        A scenario dictionary containing id, keywords, title, and response.
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
    """Gets the appropriate refusal message for the filtered content type.

    Args:
        filter_type: The filter type ('1', '2', '3', '4', or 'none').

    Returns:
        message: The appropriate refusal message.
    """
    # Sử dụng danh sách thông báo từ file beechat_prompt.py
    message = REFUSAL_MESSAGES.get(filter_type, "Xin lỗi, Bee chưa nắm được mong muốn của bạn. Bạn vui lòng mô tả cụ thể hơn được không, Bee rất sẵn lòng hỗ trợ!")
    return {
        'message': message
    }
    
    
def get_topic_category(topic: str) -> Dict[str, Any]:
    """Maps a topic keyword to its corresponding topic category.

    Args:
        topic: The topic keyword.

    Returns:
        topic_category: The mapped topic category.
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
    """Gets the location document ID from a topic category.

    Args:
        topic_category: The category of the topic.

    Returns:
        location_doc_id: The document ID for the location, or None if not found.
    """
    for location_type, doc_id in LOCATION_MAPPING.items():
        if location_type in topic_category.lower():
            return {'location_doc_id': doc_id}
    return {'location_doc_id': None}


def create_location_mongo_query(location_doc_id: str) -> Dict[str, Any]:
    """Creates a MongoDB query to fetch a location document.

    Args:
        location_doc_id: The ID of the location document.

    Returns:
        query: A dictionary representing the MongoDB query.
    """
    return {
        "query": {
            "document_id": location_doc_id
        }
    }
    
import json

def post_process_location_data(data: List, keywords: str) -> Dict[str, Any]:
    """Filters location data based on keywords and formats it as a JSON string.

    Args:
        data: A list containing the location data document.
        keywords: A comma-separated string of keywords to filter by.

    Returns:
        doc_data: A string containing a JSON array of filtered location items.
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
    """Finds a node in the card hierarchy tree and determines if it's a leaf node.

    A leaf node contains actual card data (IDs), while branch nodes contain
    subcategories or children.

    Args:
        target_key: The key name to search for in the hierarchy.
        hierarchy: The card hierarchy dictionary.

    Returns:
        found: Whether the target key was found.
        valid: True if the node contains card data, False if it has children.
        value: Card IDs or children names.

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
    """Creates batch inputs for card data retrieval.

    Args:
        query: The user query.
        value: A list of values (e.g., card IDs) to create batches for.

    Returns:
        batch_data: A list of dictionaries, each formatted as a batch input.
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
    """Collects and combines standard and card documents based on topic category.

    Args:
        standard_docs: A list of standard documents.
        card_docs: A list of card-specific documents.
        topic_category: The category of the topic.

    Returns:
        docs: A combined list of documents.
    """
    if topic_category == "specific_card":
        return {"docs": card_docs + standard_docs}
    if topic_category == "generic_card":
        return {"docs": standard_docs + card_docs}
    return {"docs": standard_docs}


def format_retrieved_documents(docs: Optional[List[Dict[str, Any]]] = None, qas: Optional[List[Dict[str, Any]]] = None) -> Dict:
    """Formats retrieved documents and Q&A pairs.

    This function takes optional lists of documents and Q&A pairs, formats their
    content into separate strings, and collects their IDs.

    Args:
        docs: An optional list of document dictionaries, each with 'content' and 'id'.
        qas: An optional list of Q&A dictionaries, each with 'content' and 'id'.

    Returns:
        A dictionary containing:
        - 'cache_qa' (str | None): A formatted string of Q&A pairs, or None.
        - 'doc' (str | None): A formatted string of documents, or None.
        - 'ids' (List[Dict[str, Any]]): A list of dictionaries, each containing an 'id'.
        - 'qa_ids' (List[Dict[str, Any]]): A list of dictionaries, each containing an 'id'.
        - 'doc_ids' (List[Dict[str, Any]]): A list of dictionaries, each containing an 'id'.
    """
    format = {
        "cache_qa": None,
        "doc": None,
        "ids": [],
        "qa_ids": [],
        "doc_ids": []
    }
    
    if qas:
        format["cache_qa"] = "\n" + "=" * 60 + "\n".join([f"ID: {i}\nNội dung: {qa["content"]}" for i, qa in enumerate(qas)])
        format["qa_ids"] = [{"id": qa["id"]} for qa in qas]
        format["ids"].extend(format["qa_ids"])
    
    if docs:
        format["doc"] = "\n" + "=" * 60 + "\n".join([f"ID: {i}\nNội dung: {doc["content"]}" for i, doc in enumerate(docs)])
        format["doc_ids"] = [{"id": doc["id"]} for doc in docs]
        format["ids"].extend(format["doc_ids"])
    
    return format

def prepare_docs_ref(docs: List) -> Dict:
    """Extracts document references from a list of documents.

    Args:
        docs: A list of document dictionaries.

    Returns:
        ref: A list of document references (e.g., source filenames).
    """
    return {"ref": [doc['doc'] for doc in docs]}


def collect_relevant_docs(docs: List, relevant_ids: List) -> Dict:
    """Collects documents from a list based on a list of relevant indices.

    Args:
        docs: The list of all documents.
        relevant_ids: A list of integer indices for the relevant documents.

    Returns:
        relevant_docs: A list containing only the relevant documents.
    """
    try:
        return {"relevant_docs": [docs[i] for i in range(len(docs)) if i in ast.literal_eval(relevant_ids)]}
    except SyntaxError:
        return {"relevant_docs": []}


def format_final_documents(docs: List) -> Dict:
    """Formats the final list of documents into a single string for the LLM prompt.

    Args:
        docs: A list of final, relevant document dictionaries.

    Returns:
        documents_text: A formatted string containing the documents' content and sources.
    """
    if not docs:
        return {"documents_text": "không tìm thấy tài liệu phù hợp"}
    
    return {
        "documents_text": "\n-----------------------------\n".join([f"--- TÀI LIỆU {i} [Nguồn: {doc['doc']}] ---\n{doc['content']}" for i, doc in enumerate(docs)])
    }

def get_query(
    messages: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Gets the most recent user query from a list of messages.

    Args:
        messages: A list of message dictionaries with 'content' and 'role' keys.

    Returns:
        query: The content of the most recent message.
    """
    query = messages[-1]['content']

    return {
        "query": query
    }


def extract_all_questions(docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extracts unique questions and their corresponding answers from a list of documents.

    If a question appears in both L1 and L2 documents, the L2 version is preferred.

    Args:
        docs: A list of documents to extract questions from.

    Returns:
        qadocs: A list of dictionaries, each containing a unique question, answer, and document metadata.
    """
    question_map = {}

    for doc in docs:
        content = doc['content']
        question_match = re.search(
            r'Câu hỏi:(.*?)(?=\nCâu trả lời:|$)', content, re.DOTALL)

        if question_match:
            question = question_match.group(1).strip()
            doc_role = doc.get("role", "L1")

            # Extract answer if it exists
            answer_match = re.search(
                r'Câu trả lời:(.*?)(?=\nCâu hỏi:|$)', content, re.DOTALL)
            answer = answer_match.group(1).strip() if answer_match else ""

            # Nếu câu hỏi đã tồn tại, chỉ thay thế nếu doc hiện tại là L2 và doc cũ là L1
            if question in question_map:
                if doc_role == 'L2' and question_map[question]['role'] == 'L1':
                    question_map[question] = {
                        'role': doc_role,
                        'answer': answer,
                        **doc
                    }
            else:
                question_map[question] = {
                    'role': doc_role,
                    'answer': answer,
                    **doc
                }

    questions_with_docs = [
        {
            'question': q,
            'role': info['role'],
            'answer': info['answer'],
            'id': info['id'],
            'doc': info['doc']
        }
        for q, info in question_map.items()
    ]

    return {"qadocs": questions_with_docs}


def format_questions(docs: List[Dict]) -> Dict[str, Any]:
    """Formats a list of question documents into a numbered string.

    Args:
        docs: A list of question-and-answer document dictionaries.

    Returns:
        txt: A formatted string listing all questions with their level.
    """
    all_questions = "\n".join([
        f"Câu hỏi {i+1} (Level {q['role']}): {q['question']}"
        for i, q in enumerate(docs)
    ])

    return {"txt": all_questions}


def get_matched_answer(docs: List[Dict], index: int) -> Dict[str, Any]:
    """Retrieves the answer and source document for a selected question index.

    Args:
        docs: A list of question-and-answer documents.
        index: The index of the selected question in the list.

    Returns:
        response: The answer content for the matched question.
        docs: A list containing the source document of the answer.
    """
    return {
        "response": docs[index]['answer'],
        "docs": [docs[index]['doc']]
    }


# memory utils

def post_process_mem0_search_results(mem0_response: List[Dict[str, Any]]) -> Dict[str, str]:
    """Aggregate Mem0 retrieval results into a cleaned memory context string.
    Args:
        mem0_response: List of Mem0 records, each optionally containing a `memory` field.

    Returns:
        memory_context: Dictionary with a single `memory_context` key ready for downstream nodes.
    """
    memory_context = {
        "memory_context": ""
    }

    if not mem0_response:
        return memory_context

    memories = [r.get("memory", "").strip()
                for r in mem0_response if r.get("memory")]

    if not memories:
        return memory_context

    cleaned = []
    for m in memories:
        if not m.endswith((".", "!", "?")):
            m += "."
        cleaned.append(m)

    combined_text = " ".join(cleaned)

    return {
        "memory_context": combined_text
    }

async def update_turn_chat_trace_id(session_id: str, client_message_id: str, trace_id: str):
    """
    Tìm assistant message turn trong collection 'turn_chat'
    và cập nhật 'client_message_id' thành trace_id mới.
    """
    import asyncio
    from beegenerate.loggings import LOGGER
    from beegenerate.storage.mongo.mongodb import MongoStorage
    from beegenerate.configs.db.mongo_config import MongoConfig
    from beegenerate.const import BEEGEN_ROOT

    try:
        config_path = BEEGEN_ROOT / "config/mongo_memory.yaml"
        if not config_path.exists():
            config_path = BEEGEN_ROOT / "config/mongo.yaml"
        config = MongoConfig.from_yaml_file(config_path)
        db = MongoStorage(config=config)
    except Exception as e:
        LOGGER.error(f"[update_turn_chat_trace_id] Failed to initialize MongoStorage: {e}")
        return None

    # Vì Java backend ghi nhận bất đồng bộ hoặc ghi nhận sau khi stream xong,
    # thực hiện retry tìm và cập nhật trong vòng 10 giây.
    max_retries = 10
    delay = 3.0

    query = {
        "dialogue_id": session_id,
        "is_from_user": False,
        "actor_id": client_message_id
    }

    LOGGER.info(f"[update_turn_chat_trace_id] Starting trace ID update for dialogue_id={session_id}, actor_id={client_message_id} -> trace_id={trace_id}")

    for attempt in range(1, max_retries + 1):
        await asyncio.sleep(delay)
        try:
            table = db._client[db.db_name]["chat_turn"]
            doc = table.find_one(query)
            if doc:
                doc_id = doc["_id"]
                LOGGER.info(f"[update_turn_chat_trace_id] Found assistant turn document _id={doc_id} on attempt {attempt}")
                
                # Cập nhật client_message_id thành trace_id
                result = table.update_one(
                    {"_id": doc_id},
                    {"$set": {"client_message_id": trace_id}}
                )
                LOGGER.info(f"[update_turn_chat_trace_id] Successfully updated client_message_id to {trace_id}. Modified count: {result.modified_count}")
                return doc_id
        except Exception as e:
            LOGGER.warning(f"[update_turn_chat_trace_id] Error on attempt {attempt}: {e}")

    LOGGER.error(f"[update_turn_chat_trace_id] Failed to find or update TurnDocument after {max_retries} attempts.")
    return None

