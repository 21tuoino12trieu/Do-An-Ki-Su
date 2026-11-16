import ast
from datetime import datetime
import json
import re
from typing import List, Dict, Any, Optional, Union
import uuid
import pandas as pd

from beeportal.utils import PROMPTS


LOCATION_MAPPING = {
    "chi nhánh": ("cn_pgd", "BEE247:DOCUMENT_TEXT_PROMPT"),
    "phòng giao dịch": ("cn_pgd", "BEE247:DOCUMENT_TEXT_PROMPT"),
    "atm": ("atm", "BEE247:ATM_TEXT_PROMPT"),
    "cdm": ("cdm_crm", "BEE247:DOCUMENT_TEXT_PROMPT"),
    "crm": ("cdm_crm", "BEE247:DOCUMENT_TEXT_PROMPT"),
    "smart bank": ("smart_bank", "BEE247:DOCUMENT_TEXT_PROMPT")
}


def post_process_card_keywords_data(data: List[Dict]) -> Dict[str, Any]:
    CARD_KEYWORD_DATA = data[0]['mapping']

    if isinstance(CARD_KEYWORD_DATA, str):
        CARD_KEYWORD_DATA = json.loads(CARD_KEYWORD_DATA)

    unique_keywords = set()
    for keywords in CARD_KEYWORD_DATA.values():
        unique_keywords.update(keywords)

    result = list(unique_keywords)

    return {
        "card_keywords_data_unique": result,
        "card_keywords_data": CARD_KEYWORD_DATA
    }


def post_process_card_filename_data(data: List[Dict]) -> Dict[str, Dict[str, str]]:
    CARD_FILENAME_DATA = data[0]['mapping']

    if isinstance(CARD_FILENAME_DATA, str):
        CARD_FILENAME_DATA = json.loads(CARD_FILENAME_DATA)

    return {
        "card_filename_data": CARD_FILENAME_DATA
    }


def post_process_card_keywords_query(query: str) -> Dict[str, List[str]]:
    return_content = []
    if isinstance(query, str):
        processed_content = query.strip()
        # Check for and extract content from a markdown code block (e.g., ```json ... ``` or ```python ... ```)
        if processed_content.startswith('```') and processed_content.endswith('```'):
            # Regex to capture content inside a markdown code block, ignoring the optional language identifier
            code_block_match = re.search(
                r'```(?:\w+)?\s*([\s\S]*?)\s*```', processed_content)
            if code_block_match:
                # Extract the content and strip any leading/trailing whitespace
                processed_content = code_block_match.group(1).strip()

        try:
            # First, try parsing as standard JSON
            data = json.loads(processed_content)
            if isinstance(data, List):
                return_content = data
            else:
                return_content = [data]
        except json.JSONDecodeError:
            try:
                # If JSON fails, try evaluating as a Python literal (handles single quotes)
                data = ast.literal_eval(processed_content)
                if isinstance(data, List):
                    return_content = data
                else:
                    return_content = [data]
            except (ValueError, SyntaxError):
                # If all parsing fails, treat the original string as the content
                return_content = [query]
    elif isinstance(query, List):
        return_content = query
    elif query == '[]' or query is None:
        return_content = []
    return {
        "query_keywords": return_content
    }


def extract_matching_card_ids(
    all_keywords: Dict,
    extracted_keywords: List,
    unique_keywords: List
) -> Dict[str, List[str]]:
    # Special case for "priority visa" combination
    if set(extracted_keywords) == {"priority", "visa"}:
        return [
            key for key, kw in all_keywords.items()
            if "priority" in kw and "visa" in kw
        ]

    matches = []

    # Handle priority cards separately
    if "priority" in extracted_keywords:
        matches.extend(
            [key for key, kw in all_keywords.items() if "priority" in kw])
        extracted_keywords = [k for k in extracted_keywords if k != "priority"]

    # Filter valid keywords and find matches
    valid_keywords = [
        k for k in extracted_keywords if k.lower() in [u.lower() for u in unique_keywords]]
    if valid_keywords:
        matches.extend([key for key, kw in all_keywords.items()
                        if all(k in kw for k in valid_keywords)])

    return {
        "card_ids": matches
    }


def extract_matching_card_topics(
    card_ids: List[str],
    card_filename: Dict[str, str]
) -> Dict[str, List[str]]:
    return {
        "card_topics": [card_filename[id] for id in card_ids]
    }

def create_card_ids_batch_inputs(enhanced_query: str, card_ids: List, role_ids: List)-> Dict[str, Any]:
    if not card_ids:
        return {
            "batch_data": []
        }
    return {
        "batch_data": [
            {
                "enhanced_query": enhanced_query,
                "partition_names": [str(id)],
                "role_ids": role_ids
            }
            for id in card_ids
        ]
    }

def create_stream_local_card_batch_inputs(
    enhanced_query: str, 
    memory_context: str, 
    card_ids: List, 
    card_filenames: Dict[str, str], 
    batch_retrieved_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    card_contents: List[str] = [doc["document_contents"] for doc in batch_retrieved_results]
    chunk_ids: List[Dict[str, Any]] = [id for doc in batch_retrieved_results for id in doc["ids"]]
    if not card_ids:
        return {
            "batch_data": [],
            "ids": chunk_ids
        }
    return {
        "batch_data": [
            {
                "enhanced_query": enhanced_query,
                "memory_context": memory_context,
                "topic": card_filenames[str(id)],
                "topics": card_filenames,
                "contents": card_contents,
                "ids": chunk_ids
            }
            for id in card_ids
        ],
        "ids": chunk_ids
    }


def format_retrieved_card_documents(docs: List[Dict[str, Any]]) -> Dict[str, any]:
    document_contents = [doc['content'] for doc in docs]
    return {
        "document_contents": "\n-------------------\n".join(document_contents),
        "ids": [{"id": doc['id']} for doc in docs]
    }


def format_retrieved_docs(
    master_docs: List[Dict],
    master_qa: List[Dict],
    gw_docs: List[Dict],
    fee_docs: List[Dict],
    promotion_docs: List[Dict],
) -> Dict[str, Any]:
    all_docs = master_docs + master_qa + gw_docs + fee_docs + promotion_docs
    return {
        "doc_contents": [doc['content'] for doc in all_docs],
        "doc_ids": [doc['id'] for doc in all_docs],
        "ids": [{"id": doc["id"], "score": f"{doc.get('document_matching_score') * 100:.1f}%" if doc.get("document_matching_score") is not None else None} for doc in all_docs],
        "lengths": len(all_docs)
    }


def get_location_doc_id(topic_category: str) -> Dict[str, Any]:
    for location_type, (document_id, prompt_key) in LOCATION_MAPPING.items():
        if location_type in topic_category.lower():
            return {"location_doc_id": document_id, "prompt_key": prompt_key}
    return {"location_doc_id": None, "prompt_key": None}


def create_location_mongo_query(location_doc_id: str) -> Dict[str, Any]:
    return {
        "query": {
            "document_id": location_doc_id
        }
    }


def post_process_location_data(document_texts: Dict[str, Any], keywords: List[str]) -> Dict[str, Any]:
    if len(keywords) > 1 or 'false' not in keywords:
        filterer_data = [
            item for item in document_texts if any(term.lower() in item.lower() for term in keywords)
        ]

        document_content = "[\n" + ',\n'.join(filterer_data) + "\n]"

        return {
            "doc_data": document_content
        }

    return {
        "doc_data": ""
    }


def check_location_cache(document_text_caching: Dict, doc_data: List[Dict]) -> Dict[str, Any]:
    document_id = doc_data[0].get('document_id')
    db_updated_time = doc_data[0].get('updated_time')
    cache_entry = document_text_caching.get(document_id, {})

    if not cache_entry or cache_entry.get('updated_time') != db_updated_time:
        document_data = doc_data[0].get('text')
        document_data = json.loads(document_data)

        for item in document_data:
            for key, value in item.items():
                if isinstance(value, str):
                    item[key] = value.lower()

        document_texts = [json.dumps(
            item, indent=0, ensure_ascii=False) for item in document_data]

        document_text_caching[document_id] = {
            'updated_time': db_updated_time,
            'text': document_texts
        }

    return {
        "overwrite_document_text_caching": document_text_caching[document_id]['text']
    }


def post_process_extracted_location_terms(keywords_text: str) -> Dict[str, Any]:
    return {
        "keywords": [k.lower().strip() for k in keywords_text.split(',')]
    }


def load_STK_mapping():
    df_stk = pd.read_excel(
        "examples/bee247/cep_stk_mapping.xlsx",
        index_col=None
    )

    # Convert DataFrame to list of dictionaries
    stk_data = df_stk.to_dict('records')
    return stk_data


def load_cep_mapping():
    df_cep = pd.read_excel(
        "examples/bee247/cep_step_mapping.xlsx",
        index_col=None
    )

    # Convert DataFrame to list of dictionaries
    cep_data = df_cep.to_dict('records')
    return cep_data


def cep_mapping_of(query: str, cep_account_mapping: List[Dict], cep_mapping: List[Dict]) -> Dict[str, Any]:
    cep_result = {
        "success": False,
        "message": "No matching found"
    }

    for account_data in cep_account_mapping:
        account_number = account_data["stk"]

        # Skip if account number is missing or not found in query
        if not account_number or str(account_number).strip() not in query:
            continue

        # Get the group for this account
        account_group = account_data["nhóm"]

        # Look up the CEP information for this group
        cep_info = next(
            (item for item in cep_mapping if item["nhóm"] == account_group), None)

        if cep_info:
            # Format the response using the template
            cep_result["message"] = PROMPTS["BEE247:CEP_MAPPING_PROMPT"].format(
                cep_account=account_data['stk'],
                cep_name=account_data['tên'],
                cep_group=cep_info["tên"]
            )
            cep_result["success"] = True
            return {"cep_result": cep_result}

    # No matching account found
    return {"cep_result": cep_result}


def format_final_docs(cep_mapping_result: Dict[str, Any], retrieved_docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    formatted_docs = []

    print(f"cep_mapping_result: {cep_mapping_result}")
    if cep_mapping_result and 'success' in cep_mapping_result and cep_mapping_result['success']:
        formatted_docs.append(
            f'TÀI LIỆU 0:\n{cep_mapping_result["message"]}')
        for i, doc in enumerate(retrieved_docs):
            formatted_docs.append(f'TÀI LIỆU {i + 1}:\n{doc["content"]}')
    else:
        for i, doc in enumerate(retrieved_docs):
            formatted_docs.append(f'TÀI LIỆU {i}:\n{doc["content"]}')

    doc_topics = {}
    for i, doc in enumerate(retrieved_docs):
        title = formatted_docs[i].split("\n")[1]
        score = doc['score']

        doc_topics[title] = max(doc_topics.get(title, 0), score)

    top_doc_title = formatted_docs[0].split("\n")[1] if formatted_docs else ""

    docs_to_include = formatted_docs  # Include all docs
    template = "NORMAL_RAG_ANSWER_PROMPT"

    if "Các gói dịch vụ và hạn mức giao dịch của eMB (Internet Banking)" in doc_topics:
        template = "EMB_RAG_ANSWER_PROMPT"
        docs_to_include = formatted_docs[:3]  # Only include top 3 docs
    elif "Cẩm nang hỗ trợ định danh Khách hàng" in doc_topics:
        if (top_doc_title == "Cẩm nang hỗ trợ định danh Khách hàng" or
                doc_topics["Cẩm nang hỗ trợ định danh Khách hàng"] > 0.85):
            template = "EKYC_RAG_ANSWER_PROMPT"

    documents_text = '\n------------------\n'.join(
        docs_to_include) if docs_to_include else "không tìm thấy tài liệu phù hợp"

    return {
        "template": template,
        "documents_text": documents_text
    }


def post_process_stream_cached_qa_answer(query: str, content: str) -> Dict[str, List[Dict[str, str]]]:
    return {
        "dialogue": [
            {"role": "user", "content": query},
            {"role": "assistant", "content": content},
        ],
        "output_response": content
    }


def post_process_standard_response(query: str, content: str) -> Dict[str, List[Dict[str, str]]]:
    return {
        "dialogue": [
            {"role": "user", "content": query},
            {"role": "assistant", "content": content},
        ],
        "output_standard_response": content
    }


def post_process_card_response(
    query: str,
    synthesize_content: str,
    local_content: Optional[List[Dict[str, Any]]] = []
) -> Dict[str, List[Dict[str, str]]]:
    local_texts = ""
    if local_content:
        local_texts = [card.get("content", "")
                    for card in local_content if card.get("content")]

    if synthesize_content:
        assistant_reply = synthesize_content
        if local_texts:
            assistant_reply += "\n" + "\n".join(local_texts)

    return {
        "dialogue": [
            {"role": "user", "content": query},
            {"role": "assistant", "content": assistant_reply},
        ],
        "output_card_response": assistant_reply
    }


def post_process_location_response(query: str, content: str) -> Dict[str, Any]:
    return {
        "dialogue": [
            {"role": "user", "content": query},
            {"role": "assistant", "content": content},
        ],
        "output_location_response": content
    }

# region ============== issue report =====================
def create_topic_query(topic: str) -> Dict[str, str]:
    """
    Args:
        topic: thông tin topic.

    Returns:
        dict: Dictionary chứa 1 keys:
            - "query": Vấn đề được phân loại (mặc định: "none")
    """

    query = f"topic ==  '{topic}'"

    try:
        return {
            "query": query,
        }
    except Exception:
        return {
            "query": "none",
        }
    
def extract_single_chunk_id(milvus_chunks: List[List[Dict[str, Any]]]) -> Dict[str, str]:
    """
    Extract single chunk_id and question from top 1 search result.
    
    Args:
        milvus_chunks: List containing sublists of dictionaries with chunk_id and question keys
        
    Returns:
        Dict containing chunk_id and question from top result, or None if not found
    """
    try:
        # Lấy item đầu tiên từ kết quả search
        first_item = None
        for sublist in milvus_chunks:
            for item in sublist:
                first_item = item
                break
            if first_item:
                break
        
        if first_item:
            return {
                "chunk_id": first_item.get('chunk_id'),
                "question": first_item.get('question')
            }
        else:
            return {
                "chunk_id": None,
                "question": None
            }
            
    except Exception as e:
        print(f"Error extracting chunk_id and question: {str(e)}")
        return {
            "chunk_id": None,
            "question": None
        }
        
    except Exception as e:
        print(f"Error extracting chunk_id: {str(e)}")
        return {"chunk_id": None}
    
def build_expr( query: str, topic: str = None, issue: str = None) -> str:
    """
    Build Milvus filter expression from topic and issue.
    (Không dùng query để filter vì query là vector search)
    
    Args:
        topic (str): Topic category to filter
        issue (str): Issue category to filter
    
    Returns:
        str: Milvus filter expression
    """
    def escape(value: str) -> str:
        # Escape dấu nháy đơn để tránh lỗi parse expression
        return value.replace("'", "\\'")
    
    conditions = []
    
    if topic:
        conditions.append(f"topic == '{escape(topic)}'")
    
    if issue:
        conditions.append(f"issue == '{escape(issue)}'")
        
    expr = " and ".join(conditions) if conditions else ""
    
    return {
        "expr_conditions": expr
    }

def prepare_insert_milvus(embeddings: str, topic: str, issue: str, question: str) -> Dict[str, Any]:
    """
    Prepare insert data for Milvus with topic field.
    
    Args:
        embeddings: Embedding vectors
        topic: Topic category (e.g., 'login_issue', 'payment_issue')
    
    Returns:
        Dictionary with formatted data for Milvus insert
    """
    chunk_id = str(uuid.uuid4())
    
    if not embeddings or not chunk_id or not topic:
        raise ValueError("Embeddings, chunk_id and topic are required")
    
    # Get first embedding
    embedding = embeddings[0] if isinstance(embeddings[0], list) else embeddings
    
    # Format: [[chunk_ids], [topics], [question], [embeddings]]
    return {
        "data_milvus": [[chunk_id], [topic], [issue], [question], [embedding]],
        "chunk_id": chunk_id,
    }

def prepare_query_postgre(chunk_id: str) -> Dict[str, Any]:
    """
    Prepares SQL query configuration to fetch the most recent issue log entry by chunk_id.
    
    This function constructs a query that retrieves the latest record from the 
    bee247_issues_log table for a given chunk_id, ordered by datetime descending.
    
    Args:
        chunk_id (str): The unique identifier of the chunk to query for.
                       Must be a valid UUID string or chunk identifier.
    
    Returns:
        Dict[str, Any]: A dictionary containing:
            - query (str): The SQL SELECT statement with asyncpg placeholder ($1)
            - params (tuple): A tuple containing the chunk_id parameter
    """
    query_sql = """
        SELECT
            _id,
            question,
            answer,
            topic,
            issue,
            chunk_id,
            number_of_relevant_question,
            datetime
        FROM agent_ai.bee247_issues_log
        WHERE chunk_id = %s
        ORDER BY datetime DESC
        LIMIT 1
    """.strip()

    return {
        "query": query_sql,
        "params": (chunk_id,)
    }

def prepare_insert_postgre(
    issue: Any,
    question: str,
    topic: str,
    output_response: str,
    chunk_id: str,
) -> Dict[str, Any]:
    """
    Ensures safe handling of output_response types and builds final answer text.
    """
    question_id = str(uuid.uuid4())
    timestamp = datetime.now().date()

    insert_sql = """
        INSERT INTO agent_ai.bee247_issues_log (
            _id,
            question,
            answer,
            topic,
            issue,
            chunk_id,
            number_of_relevant_question,
            datetime
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
    """

    return {
        "query": insert_sql,
        "params": (
            question_id,
            question,
            output_response,
            topic,
            issue,
            chunk_id,
            1,
            timestamp,
        )
    }

def prepare_update_or_insert_relevant(
    data: Optional[List[Dict[str, Any]]]
) -> Dict[str, Any]:
    """
    Prepares SQL query configuration for updating or inserting an issue log record.
    
    Logic:
    1. If no existing record → return None (no action needed)
    2. If existing record's datetime == today → UPDATE number_of_relevant_question + 1
    3. If existing record's datetime != today → INSERT new row with counter = 1
    
    Args:
        data (Optional[Dict[str, Any]]): The most recent record fetched from database.
                                                     Should contain keys: _id, question, answer, 
                                                     topic, issue, chunk_id, number_of_relevant_question, 
                                                     datetime. None if no record exists.
    
    Returns:
        Dict[str, Any]: A dictionary containing:
            - query (str): SQL statement with asyncpg placeholders ($1, $2, ...)
            - params (tuple): Parameter values for the query
            
            Special case when action="none":
            - query and params will be None
    
    """
    today_date = datetime.now().date()
    
    if data is None:
        return {"query": None, "params": None}
    
    data = data[0]
    
    # Chuyển data["datetime"] về date object
    db_date = data["datetime"]
    if isinstance(db_date, str):
        db_date = datetime.strptime(db_date, "%Y-%m-%d").date()
    elif isinstance(db_date, datetime):
        db_date = db_date.date()
    
    # === Case 2: Same date → UPDATE +1 ===
    if data["datetime"] == today_date:
        updated_value = data["number_of_relevant_question"] + 1
        
        sql_update = """
            UPDATE agent_ai.bee247_issues_log
            SET number_of_relevant_question = %s
            WHERE _id = %s
        """.strip()
        
        return {
            "query": sql_update,
            "params": (updated_value, data["_id"])
        }
    
    # === Case 3: Different date → INSERT new row ===
    new_id = str(uuid.uuid4())
    
    sql_insert = """
        INSERT INTO agent_ai.bee247_issues_log (
            _id,
            question,
            answer,
            topic,
            issue,
            chunk_id,
            number_of_relevant_question,
            datetime
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """.strip()
    
    return {
        "query": sql_insert,
        "params": (
            new_id,
            data["question"],
            data["answer"],
            data["topic"],
            data["issue"],
            data["chunk_id"],
            1,
            today_date,
        )
    }

def merge_node( output_card_response: Optional[str],
                output_location_response: Optional[str], 
                output_standard_response: Optional[str]) -> Optional[Dict[str, Optional[str]]]:
    """
    Lxác định output response.
    
    Args:
        output_card_response: Response từ card system
        output_location_response: Response từ location system
        output_standard_response: Response từ standard system
        
    Returns:
        Dictionary chứa output_response
    """
    
    
    # Lấy biến đầu tiên khác None
    output = next(
        (resp for resp in [output_card_response, output_location_response, output_standard_response] 
         if resp is not None), 
        None
    )
    
    return {
        "output_response": output
    }

def create_get_qa_mongo_query(ids: List) -> Dict[str, Any]:
    return {
        "query": {
            "_id": ids[0]["id"],
        }
    }

def create_get_document_mongo_query(data: List) -> Dict[str, Any]:
    # Lấy tags từ document đầu tiên (nếu có)
    tags = data[0].get("tags") if data and len(data) > 0 else None
    
    return {
        "query": {"_id": tags},
    }

def create_get_topic_mongo_query(data: List) -> Dict[str, Any]:
    # Lấy tags từ document đầu tiên (nếu có)
    category_id = data[0].get("category_id") if data and len(data) > 0 else None
    
    return {
        "query": {"_id": category_id},
    }


def postprocess_topic(data: List) -> Dict[str, Any]:
    # Lấy tags từ document đầu tiên (nếu có)
    topic = data[0].get("name") if data and len(data) > 0 else None
    
    return {
        "topic": topic
    }

def process_multiple_classifications(classifications: List[dict], question: str, output_response: str) -> dict:
    """
    Xử lý danh sách classifications và tạo query cho mỗi topic-issue
    
    Args:
        classifications: List of {topic: str, issue: str}
        question: Câu hỏi gốc
    
    Returns:
        {"processed_items": List[dict]} - Mỗi dict chứa {topic, issue, query, question}
    """
    processed_items = []

    # Kiểm tra classifications có hợp lệ không
    if not classifications:
        print("Warning: classifications is empty or None")
        return {"processed_items": []}
    
    for classification in classifications:
        topic = classification.get("topic", "")
        issue = classification.get("issue", "")
        
        # Tạo query filter cho Milvus
        query = f"topic ==  '{topic}' and issue == '{issue}'"
        
        processed_items.append({
            "topic": topic,
            "issue": issue,
            "query": query,
            "question": question,
            "output_response": output_response
        })
    
    return {"processed_items": processed_items}

# endregion ============== issue report =====================

if __name__ == "__main__":
    query = """```python
['priority pass', 'visa', 'infinite', 'mastercard', 'world', 'elite']
```
"""
    result = post_process_card_keywords_query(query)
    print(result)
