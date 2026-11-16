import datetime
from typing import Any, Dict, List
import uuid

from app.utils.enums import DocumentType
from app.service.portal.utils.prepare_document import build_topic_tree


def prepare_delete_dialogues_query(bot_id: str, ids: List[str]) -> Dict[str, Any]:
    """Query to find specific deleted dialogues for a bot (used in clean workflow)"""
    return {
        "query_deleted_dialogues": {
            "_id": {"$in": ids},
            "bot_id": bot_id,
            "deleted": True
        }
    }


def extract_dialogue_ids(deleted_dialogues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract _id list from deleted dialogues. These IDs map to doc_id in chunk_data."""
    ids = [d.get("_id") for d in deleted_dialogues if d.get("_id")]
    chunk_ids_from_chunks = []  # will be populated after fetching chunk_data
    return {
        "dialogue_ids": ids
    }


def prepare_delete_chunks_by_dialogue_ids(dialogue_ids: List[str]) -> Dict[str, Any]:
    """Build Mongo filter for deleting QnA chunk_data by doc_id (= dialogue _id)."""
    return {
        "mongo_filter": {
            "doc_id": {"$in": dialogue_ids}
        }
    }


def prepare_delete_dialogues_filter(dialogue_ids: List[str]) -> Dict[str, Any]:
    """Build mongo filter for hard-deleting the dialogue records themselves"""
    return {
        "mongo_filter": {
            "_id": {"$in": dialogue_ids}
        }
    }


def collect_chunk_ids_by_dialogue(chunk_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Collect chunk_id list from chunk_data records for Milvus delete expr"""
    chunk_ids = [c.get("chunk_id") for c in (chunk_data or []) if c.get("chunk_id")]
    ids_str = ", ".join(f'"{i}"' for i in chunk_ids)
    return {
        "chunk_ids": chunk_ids,
        "milvus_expr": f"chunk_id in [{ids_str}]" if chunk_ids else "chunk_id in [\"__none__\"]"
    }


def prepare_mongo_query_qna(bot_id: str, ids: List[str]) -> Dict[str, Any]:
    query_dialogue_info = {
        "_id": {"$in": ids},
        "bot_id": bot_id,
        "deleted": {"$ne": True}
    }
    
    return {
        "query_dialogue_info": query_dialogue_info,
    }

def prepare_query_old_chunks(ids: List[str]) -> Dict[str, Any]:
    return {
        "query_old_chunks": {
            "doc_id": {"$in": ids}
        },
        "projection": {"chunk_id": 1, "_id": 0}
    }

def prepare_delete_old_chunks(chunk_ids: List[str]) -> Dict[str, Any]:
    # Filter out None values
    valid_ids = [i for i in chunk_ids if i is not None]
    ids_str = ", ".join(f'"{i}"' for i in valid_ids)
    return {
        "mongo": {
            "chunk_id": {"$in": valid_ids}
        },
        "milvus": f"chunk_id in [{ids_str}]" if valid_ids else "chunk_id in [\"__none__\"]"
    }

def collect_old_chunks(old_chunks_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "old_chunks": [chunk.get("chunk_id") for chunk in (old_chunks_data or []) if chunk.get("chunk_id")]
    }

def create_batch_get_doc_info(qna_data: List[Dict]) -> Dict[str, Any]:
    batch = []

    for d in qna_data:
        tags = d.get("tags")
        doc_id = tags[0] if isinstance(tags, list) and len(tags) > 0 else tags
        batch.append({
            "pipeline": [
                {"$match": {"_id": doc_id, "deleted": {"$ne": True}}},
                {"$addFields": {
                    "_id": {"$toString": "$_id"},
                    "category_id": {"$toString": "$category_id"}
                }}
            ]
        })

    return {
        "batch_data": batch
    }

def get_category_query(doc_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "query": {"_id": doc_data[0].get("category_id")}
    }

def prepare_qna_chunk(dialogue_data: List[Dict[str, Any]], doc_name_data: List[Dict[str, Any]], all_topics: List[Dict[str, Any]]) -> Dict[str, Any]:
    milvus_chunks = []
    mongo_chunks = []
    aligned_dialogue_ids = []
    aligned_topic_paths = []

    for i, dialogue in enumerate(dialogue_data):
        dialogue_id = dialogue.get('_id')
        answer = dialogue['answers'][0].get('text') if dialogue.get('answers') else ""
        
        questions_set = dialogue.get('questions', [])
        questions = [q.get('text') for q in questions_set]
        
        doc_info = doc_name_data[i]["doc_info"][0] if doc_name_data[i].get("doc_info") else {}
        name = doc_info.get('doc_name', "")
        topic_id = doc_info.get('category_id')
        
        # Build topic path
        topic_path_dict = build_topic_tree(topic_id, all_topics)
        topic_path = topic_path_dict.get("topic_path", "")
        
        for question in questions:
            milvus_chunks.append(question)
            mongo_chunks.append(
                f"File tài liệu: {name}\nCâu hỏi: {question}\nCâu trả lời: {answer}"
            )
            aligned_dialogue_ids.append(str(dialogue_id))
            aligned_topic_paths.append(topic_path)

    return {
        "milvus_chunks": milvus_chunks,
        "mongo_chunks": mongo_chunks,
        "aligned_dialogue_ids": aligned_dialogue_ids,
        "aligned_topic_paths": aligned_topic_paths
    }
    
def prepare_ingestion_data(
    milvus_chunks: List[str],
    mongo_chunks: List[str],
    embeddings: List[List[float]],
    aligned_dialogue_ids: List[str],
    aligned_topic_paths: List[str], 
) -> Dict[str, Any]:
    chunk_ids = [str(dialogue_id) for dialogue_id in aligned_dialogue_ids]
    # chunk_ids = [str(uuid.uuid4()) for _ in range(len(embeddings))]
    
    milvus_data = [
        {
            "chunk_id": chunk_id,
            "vector": embedding,
            "content": milvus_chunk,
            "topic": topic_path,
            "type": DocumentType.QA,
        }
        for chunk_id, embedding, milvus_chunk, topic_path in zip(chunk_ids, embeddings, milvus_chunks, aligned_topic_paths)
    ]
    
    from collections import defaultdict
    index_map = defaultdict(int)
    
    mongo_chunk_data = []
    for chunk_id, chunk, dialogue_id in zip(chunk_ids, mongo_chunks, aligned_dialogue_ids):
        idx = index_map[dialogue_id]
        index_map[dialogue_id] += 1
        mongo_chunk_data.append({
            "_id": chunk_id,
            "chunk_id": chunk_id,
            "doc_id": dialogue_id,
            "chunk_index": idx,
            "llm_text": chunk
        })
    
    return {
        "milvus_data": milvus_data,
        "mongo_chunk_data": mongo_chunk_data
    }
