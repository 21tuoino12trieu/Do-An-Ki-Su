from confluence_workflow.utils.logger import get_logger

logger = get_logger("milvus_processor")

def _build_milvus_delete_payload(chunk_docs: list[dict] | None, bot_id: str) -> dict:
    """Build Milvus delete payload from Mongo chunk_data rows."""
    chunk_ids = []
    seen_chunk_ids = set()

    for doc in (chunk_docs or []):
        chunk_id = doc.get("chunk_id")
        if chunk_id is None:
            continue

        normalized = str(chunk_id)
        if normalized in seen_chunk_ids:
            continue

        seen_chunk_ids.add(normalized)
        chunk_ids.append(normalized)

    collection_name = f"bot_{bot_id.replace('-', '_')}_chunk"
    
    if not collection_name or not chunk_ids:
        return {
            "collection_name": collection_name,
            "expr": "",
            "has_chunk_ids": False,
        }
    
    # Ví dụ chunk_ids = ["c1", "c2", "c3"] khi đi qua
    # chunk_ids_expr sẽ thành '"c1", "c2", "c3"'
    # đi qua expr sẽ thành 'chunk_id in ["c1", "c2", "c3"]'
    chunk_ids_expr = ", ".join([f'"{chunk_id}"' for chunk_id in chunk_ids])
    expr = f"chunk_id in [{chunk_ids_expr}]"

    logger.info("Built Milvus delete payload with %s chunk_ids", len(chunk_ids))
    return {
        "collection_name": collection_name,
        "expr": expr,
        "has_chunk_ids": True,
    }


def _build_milvus_node_delete_payload(node_docs: list[dict] | None, bot_id: str) -> dict:
    """Build Milvus delete payload from Mongo node rows."""
    node_ids = list(dict.fromkeys(
        str(doc["node_id"])
        for doc in (node_docs or [])
        if doc.get("node_id") is not None
    ))
    collection_name = f"bot_{bot_id.replace('-', '_')}_node"

    if not node_ids:
        return {
            "collection_name": collection_name,
            "expr": "",
            "has_node_ids": False,
        }

    node_ids_expr = ", ".join(f'"{node_id}"' for node_id in node_ids)
    return {
        "collection_name": collection_name,
        "expr": f"node_id in [{node_ids_expr}]",
        "has_node_ids": True,
    }
