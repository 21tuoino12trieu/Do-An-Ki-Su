from beeportal.bot_enterprise_KHCN.enterprise_KHCN.intent_disclaimer import INTENT_CONFIG


def format_retrieved_docs(docs):
    """Check if log file exists and create it if not
    Args:
        docs: Document text,
    Returns:
        doc_contents: Document contents ready for reranking.
        documents_text: All document contents joined with [SEP].
        doc_ids: Identifiers associated with each document.
        ids: List of identifiers associated with each document.
        lengths: Lengths of list of retrieved docs.
    """
    return {
        "doc_contents": [doc['content'] for doc in docs],
        "documents_text": "\n\n".join([f"<Chunk {i+1} - Chunk ID: {doc['id']}>\nContent: {doc['content']}\n</Chunk {i+1}>" for i, doc in enumerate(docs)]),
        "doc_ids": [doc['id'] for doc in docs],
        "ids": [{"id": doc["id"], "score": f"{doc.get('document_matching_score') * 100:.1f}%" if doc.get("document_matching_score") is not None else None} for doc in docs],
        "lengths": len(docs)
    }


def prepare_session_id_key(session_id: str, role_ids: str = None):
    """
    Wraps session_id into a dict for Redis/cache key lookup.
    Args:
        session_id: Session identifier used for cache retrieval.
        Returns:
        Dict with 'key' field containing the session_id.
    """
    return {
        "key": session_id
    }
