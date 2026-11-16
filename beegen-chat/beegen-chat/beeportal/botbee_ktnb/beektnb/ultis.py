from typing import List, Dict, Any, Optional
from beeportal.botbee_ktnb.beektnb.constant import REFUSAL_MESSAGES
from beeportal.utils import PROMPTS


character_ask_human = "[?]"

def get_message_by_role(messages: List[Dict[str, Any]]):
    m_assitance = [a['content'] for a in messages[-21:-1] if a['role'] != 'user']
    m_user = [a['content'] for a in messages[-21:-1] if a['role'] == 'user']

    return {"user_messages": m_user, "assistant_messages": m_assitance}


def get_user_history_messages(messages: List[Dict[str, Any]]):
    user_messages = [
        f"User: {m['content']}"
        # else f"BOT: {m['content']}"
        for m in messages[-41:-1] if m['role'] == 'user'
    ]

    return {"user_messages": user_messages}


def get_history_chat(hist_messages: List[Dict[str, Any]]):

    query = hist_messages[-1]['content']
    _history = [
        f"User: {m['content']}"
        if m['role'] == 'user'
        else f"BOT: {m['content']}"
        for m in hist_messages[-11:-1]
    ]  

    return {"query": query, "history_messages": _history}


def get_special_task_data(query_task: str):
    if query_task in REFUSAL_MESSAGES:
        task = REFUSAL_MESSAGES[query_task]
    else:
        task = REFUSAL_MESSAGES["5"]

    return {"task": task}


def get_rewrite_query(chat_type: str, follow_up_rewrite_query: str, simple_query: str):
    if chat_type == "follow-up":
        rewritten_query = follow_up_rewrite_query
    else:
        rewritten_query = simple_query

    return {"rewritten_query": rewritten_query}


def get_flag_advise_detect_value(rewritten_query: str):
    flag_advise_detect = False

    if 'tư vấn' in rewritten_query.lower() or 'phát hiện' in rewritten_query.lower() or 'kiến nghị' in rewritten_query.lower():
        flag_advise_detect = True

    return {"flag_advise_detect": flag_advise_detect}


def  get_topic_use_condition(
    query: str,
    topic: str,
    flag_advise_detect: bool
) -> dict:
    """
        Topic phát hiện/kiến nghị khác với topic của hướng dẫn -> Cần có bước asign lại topic để match với 
    """
    if flag_advise_detect:
        if 'BCTC' in topic:
            if "thẩm định" in query.lower():
                topic_ktnb = "Thẩm định BCTC (Báo cáo tài chính)"
            else:
                topic_ktnb = "Kiểm toán BCTC (Báo cáo tài chính)"
        elif 'KHCN' in topic:
            topic_ktnb = "Kiểm toán Hoạt động cấp tín dụng KHCN"
        elif 'PCRT' in topic:
            topic_ktnb = "Kiểm toán hoạt động PCRT"
        else:
            topic_ktnb = topic
    else:
        topic_ktnb = topic
    
    return {"topic_ktnb": topic_ktnb}


def check_state_ask_human(
    messages: List[Dict]
) -> bool:
    """
        Kiểm tra xem cần hỏi lại người dùng không khi chưa rõ topic.

        Args: Lịch sử trò chuyện

        return:
            - True: Nếu trong 20 turn chat chưa có câu hỏi lại nào
            - False: Nếu trong 20 turn chat có câu hỏi lại
    """

    result_check = [character_ask_human in a['content'] for a in messages[-21:-1] if a['role'] != 'user']

    if True not in list(result_check):
        return {"state": True}
    else:
        return {"state": False}


def prepare_system_prompt(query: str, date_time: str, definition: str, documents: str):
    if documents:
        system_prompt = PROMPTS["BEEKTNB:NON_CHIT_CHAT_PROMPT"].format(
            date=date_time,
            definition=definition,
            query=query,
            documents=documents,
        )
    else:
        system_prompt = PROMPTS["BEEKTNB:REFUSE_PROMPT"].format(
            definition=definition
        )

    return {"prompt": system_prompt}

def format_summary_data(batch_summarized_data):
    format_doc = "\n".join(doc for doc in batch_summarized_data)

    return {"format_doc": format_doc}

def format_documents(
    documents: List[Dict],
    truncate: bool = True
) -> str:
    """Format a list of documents into a single string with separators.

    Args:
        documents: List of document dictionaries, each containing a 'content' field

    Returns:
        String containing all document contents separated by [SEP] tokens
    """
    documents_text = ""
    for i, d in enumerate(documents):
        documents_text += f"\nDocument {i + 1}: {d}\n"

    if truncate:
        documents_text = documents_text[:50000]

    return {"format_data": documents_text}

def get_lastest_user_message(user_messages: List) -> str:

    return {"lastest_user_message": user_messages[-1]}

def get_history_messages(messages: List) -> List:

    return {"hist_messages": messages[-3:]}

def format_final_documents(retrieval_documents: list, rerank_documents: list, final_top_k: int) -> list:
    top_5_retrieval_chunk_ids = [doc["id"] for doc in retrieval_documents[:final_top_k // 2]]

    keep_rerank_chunk_based_on_ids = [doc for doc in rerank_documents if doc["id"] in top_5_retrieval_chunk_ids]

    for doc in rerank_documents:
        if doc["id"] not in top_5_retrieval_chunk_ids:
            keep_rerank_chunk_based_on_ids.append(doc)

        if len(keep_rerank_chunk_based_on_ids) > final_top_k:
            break

    sorted_documents = sorted(keep_rerank_chunk_based_on_ids, key=lambda x: x['score'], reverse=True)

    return {"final_documents": sorted_documents}

def format_rerank_documents(docs: Optional[List[Dict[str, Any]]] = None, qas: Optional[List[Dict[str, Any]]] = None) -> Dict:
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

    retrieval_keep_index = [0, 1, 2, 3, 4]
    
    if qas:
        format["cache_qa"] = "\n" + "=" * 60 + "\n".join([f"ID: {i}\nNội dung: {qa["content"]}" for i, qa in enumerate(qas)])
        format["qa_ids"] = [{"id": qa["id"]} for qa in qas]
        format["ids"].extend(format["qa_ids"])
    
    if docs:
        rerank_retrieval = [doc for doc in docs if doc["id"] in retrieval_keep_index]

        top_k = 10

        rerank_top_k = docs[:top_k]

        for r in rerank_top_k:
            if r['index'] not in retrieval_keep_index:
                rerank_retrieval.append(r)

            if len(rerank_retrieval) == top_k:
                break

        sorted_rerank_retrieval = sorted(rerank_retrieval, key=lambda x: x['score'], reverse=True)

        format["doc"] = "\n" + "=" * 60 + "\n".join([f"ID: {i}\nNội dung: {doc["content"]}" for i, doc in enumerate(sorted_rerank_retrieval)])
        format["doc_ids"] = [{"id": doc["id"]} for doc in sorted_rerank_retrieval]
        format["ids"].extend(format["doc_ids"])
    
    return format