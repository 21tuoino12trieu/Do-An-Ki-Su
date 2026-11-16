import asyncio
import datetime
from beeflow.workflow import WorkflowEngine
from beeflow.nodes.primitives.data.mongo_node import MongoNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.flow.for_loop_node import ForLoopNode
from beeflow.nodes import EmbeddingNode
from beeflow.nodes.graph.graph_node import GraphNode
from beeflow.nodes.primitives.data.milvus_node import MilvusNode
from beeflow.nodes.flow.branch_node import BranchNode
from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
from beegen.configs import MilvusOperation, MongoOperation

from app.model.document import UploadRequest, TrainRequest, CleanDataRequest
from app.service.chunk import chunk
from app.service.portal.utils.common import convert_bot_id
from app.service.portal.utils.prepare_qna import (
    collect_old_chunks,
    create_batch_get_doc_info,
    get_category_query,
    prepare_delete_old_chunks,
    prepare_ingestion_data,
    prepare_mongo_query_qna,
    prepare_qna_chunk,
    prepare_query_old_chunks,
    # clean helpers
    prepare_delete_dialogues_query,
    extract_dialogue_ids,
    prepare_delete_chunks_by_dialogue_ids,
    prepare_delete_dialogues_filter,
    collect_chunk_ids_by_dialogue,
)
from app.utils.enums import ChunkingType, DocumentType
from app.utils.db_validation import (
    validate_active_dialogues,
    validate_bot,
    validate_dialogues_for_clean,
)
from fastapi import HTTPException, status


def _build_all_topics_pipeline(bot_id: str):
    return {
        "pipeline": [
            {"$match": {"bot_id": bot_id}},
            {"$addFields": {
                "_id": {"$toString": "$_id"},
                "parent_id": {"$toString": "$parent_id"}
            }}
        ]
    }


def _check_qna_embedding(embeddings: list, milvus_chunks: list) -> dict:
    """Check if embedding count matches number of QnA chunks."""
    success = (
        isinstance(embeddings, list)
        and isinstance(milvus_chunks, list)
        and len(embeddings) == len(milvus_chunks)
    )
    return {"embed_success": success}


def _build_qna_training_status_update(ids: list, is_trained: bool, training_status: str) -> dict:
    """Build Mongo UPDATE_MANY payload to update training status on dialogue records."""
    update_fields = {
        "is_trained": is_trained,
        "training_status": training_status,
    }
    if is_trained and training_status == "DONE":
        update_fields["trained_at"] = datetime.datetime.now(datetime.UTC)
    return {
        "filter": {"_id": {"$in": ids}},
        "update": {"$set": update_fields},
    }


class ProcessQnAService:
    def __init__(self):
        self._build_train_qna_workflow()
        self._build_clean_qna_workflow()
    
    def _build_train_qna_workflow(self):
        with WorkflowEngine(
            name="wf_train_qna",
            description="train qna",
            langfuse="beegen-portal"
        ) as wf_train_qna:
            code_prepare_mongo_query = CodeNode(
                name="code_prepare_mongo_query",
                code_fn=prepare_mongo_query_qna,
                inputs={
                    "bot_id": INPUT,
                    "ids": INPUT
                },
                return_keys=[
                    "query_dialogue_info: Dict[str, Any]"
                ]
            )
            
            get_dialogue_info = MongoNode(
                name="get_dialogue_info",
                resource_key="aicenter-chatbot",
                operation="find",
                inputs={
                    "collection_name": "dialogue",
                    "query": {code_prepare_mongo_query: "query_dialogue_info"},
                }
            )
            
            code_build_topic_pipeline = CodeNode(
                name="code_build_topic_pipeline",
                code_fn=_build_all_topics_pipeline,
                inputs={"bot_id": INPUT},
                return_keys=["pipeline: list"]
            )

            get_all_topics = MongoNode(
                name="get_all_topics",
                resource_key="aicenter-chatbot",
                operation="aggregate",
                inputs={
                    "collection_name": "category",
                    "pipeline": {code_build_topic_pipeline: "pipeline"}
                }
            )
            
            code_create_batch_get_doc_info = CodeNode(
                name="code_create_batch_get_doc_info",
                code_fn=create_batch_get_doc_info,
                inputs={
                    "qna_data": {get_dialogue_info: "data"}
                },
                return_keys=[
                    "batch_data: List[Dict[str, Any]]",
                ]
            )
            
            with ForLoopNode(
                name="loop_get_doc_info",
                inputs={
                    "batch_data": code_create_batch_get_doc_info
                }
            ) as loop_get_doc_info:                
                get_document_info = MongoNode(
                    name="get_document_info",
                    resource_key="aicenter-chatbot",
                    operation="aggregate",
                    inputs={
                        "collection_name": "documents",
                        "pipeline": INPUT,
                    },
                    outputs={"data": {OUTPUT: "doc_info"}}
                )
                
                START >> get_document_info >> END
                
            code_prepare_qna_chunk = CodeNode(
                name="code_prepare_qna_chunk",
                code_fn=prepare_qna_chunk,
                inputs={
                    "dialogue_data": {get_dialogue_info: "data"},
                    "doc_name_data": {loop_get_doc_info: "batch_result"},
                    "all_topics": {get_all_topics: "data"}
                },
                return_keys=[
                    "milvus_chunks: List[str]",
                    "mongo_chunks: List[str]",
                    "aligned_dialogue_ids: List[str]",
                    "aligned_topic_paths: List[str]"
                ]
            )
            
            embedding_chunk = EmbeddingNode(
                name="embedding_chunk",
                resource_key="qwen-embedding-chat",
                inputs={"texts": {code_prepare_qna_chunk: "milvus_chunks"}}
            )
            
            code_prepare_ingestion_data = CodeNode(
                name="code_prepare_ingestion_data",
                code_fn=prepare_ingestion_data,
                inputs={
                    "milvus_chunks": {code_prepare_qna_chunk: "milvus_chunks"},
                    "mongo_chunks": {code_prepare_qna_chunk: "mongo_chunks"},
                    "embeddings": {embedding_chunk: "embeddings"},
                    "aligned_dialogue_ids": {code_prepare_qna_chunk: "aligned_dialogue_ids"},
                    "aligned_topic_paths": {code_prepare_qna_chunk: "aligned_topic_paths"},
                },
                return_keys=[
                    "milvus_data: List[str]",
                    "mongo_chunk_data: List[str]"
                ]
            )
            
            with GraphNode(
                name="graph_data_ingestion",
                description="insert chunk to vectordb and storage",
                inputs={
                    "ids": INPUT,
                    "bot_id": INPUT,
                    "milvus_data": {code_prepare_ingestion_data: "milvus_data"},
                    "mongo_chunk_data": {code_prepare_ingestion_data: "mongo_chunk_data"}
                }
            ) as graph_data_ingestion:
                code_get_collection_name = CodeNode(
                    name="code_get_collection_name",
                    code_fn=convert_bot_id,
                    inputs={
                        "bot_id": INPUT,
                    },
                    return_keys=[
                        "collection_name: str"
                    ]
                )
                
                code_prepare_query_old_chunks = CodeNode(
                    name="code_prepare_query_old_chunks",
                    code_fn=prepare_query_old_chunks,
                    inputs={
                        "ids": INPUT
                    },
                    return_keys=[
                        "query_old_chunks: Dict[str, Any]",
                        "projection: Dict[str, Any]"
                    ]
                )
                    
                mongo_get_old_chunks = MongoNode(
                    name="get_old_chunks",
                    resource_key="aicenter-chatbot",
                    operation=MongoOperation.FIND,
                    inputs={
                        "collection_name": "chunk_data",
                        "query": {code_prepare_query_old_chunks: "query_old_chunks"},
                        "projection": {code_prepare_query_old_chunks: "projection"},
                    }
                )
                
                code_collect_old_chunks = CodeNode(
                    name="code_collect_old_chunks",
                    code_fn=collect_old_chunks,
                    inputs={
                        "old_chunks_data": {mongo_get_old_chunks: "data"}
                    },
                    return_keys=[
                        "old_chunks: List[str]"
                    ]
                )
                
                code_prepare_delete_old_chunks = CodeNode(
                    name="code_prepare_delete_old_chunks",
                    code_fn=prepare_delete_old_chunks,
                    inputs={
                        "chunk_ids": {code_collect_old_chunks: "old_chunks"}
                    },
                    return_keys=[
                        "mongo: Dict[str, Any]",
                        "milvus: str"
                    ]
                )
                
                mongo_delete_old_chunks = MongoNode(
                    name="mongo_delete_old_chunks",
                    resource_key="aicenter-chatbot",
                    operation=MongoOperation.DELETE_MANY,
                    inputs={
                        "collection_name": "chunk_data",
                        "filter": {code_prepare_delete_old_chunks: "mongo"},
                    }
                )
                
                milvus_delete_old_chunks = MilvusNode(
                    name="milvus_delete_old_chunks",
                    resource_key="chatbot-libra",
                    operation=MilvusOperation.DELETE,
                    inputs={
                        "collection_name": {code_get_collection_name: "collection_name"},
                        "expr": {code_prepare_delete_old_chunks: "milvus"}
                    }
                )
                
                mongo_insert_chunk_data = MongoNode(
                    name="mongo_insert_chunk_data",
                    resource_key="aicenter-chatbot",
                    operation=MongoOperation.INSERT_MANY,
                    inputs={
                        "collection_name": "chunk_data",
                        "documents": {INPUT: "mongo_chunk_data"}
                    }
                )
                
                milvus_insert_data = MilvusNode(
                    name="milvus_insert_data",
                    resource_key="chatbot-libra",
                    operation=MilvusOperation.INSERT,
                    inputs={
                        "data": {INPUT: "milvus_data"},
                        "collection_name": {code_get_collection_name: "collection_name"}
                    }
                )
                
                START >> [code_prepare_query_old_chunks, code_get_collection_name]
                code_prepare_query_old_chunks >> mongo_get_old_chunks >> code_collect_old_chunks >> code_prepare_delete_old_chunks

                # Delete old data (both wait for read to complete via code_prepare_delete_old_chunks)
                code_prepare_delete_old_chunks >> mongo_delete_old_chunks
                [code_prepare_delete_old_chunks, code_get_collection_name] >> milvus_delete_old_chunks

                # Insert new data only after respective deletes complete
                mongo_delete_old_chunks >> mongo_insert_chunk_data >> END
                milvus_delete_old_chunks >> milvus_insert_data >> END
            
            # ── Training status update nodes ───────────────────────────────
            code_check_qna_embedding = CodeNode(
                name="code_check_qna_embedding",
                code_fn=_check_qna_embedding,
                inputs={
                    "embeddings": {embedding_chunk: "embeddings"},
                    "milvus_chunks": {code_prepare_qna_chunk: "milvus_chunks"}
                },
                return_keys=["embed_success: bool"]
            )

            code_build_done_status = CodeNode(
                name="code_build_done_status",
                code_fn=_build_qna_training_status_update,
                inputs={
                    "ids": INPUT,
                    "is_trained": True,
                    "training_status": "DONE",
                },
                return_keys=["filter: dict", "update: dict"]
            )

            code_build_error_status = CodeNode(
                name="code_build_error_status",
                code_fn=_build_qna_training_status_update,
                inputs={
                    "ids": INPUT,
                    "is_trained": False,
                    "training_status": "ERROR",
                },
                return_keys=["filter: dict", "update: dict"]
            )

            branch_update_qna_status = BranchNode(
                name="branch_update_qna_status",
                cases={"embed_success == True": code_build_done_status},
                default=code_build_error_status,
                inputs={"embed_success": {code_check_qna_embedding: "embed_success"}}
            )

            mongo_update_done_status = MongoNode(
                name="mongo_update_done_status",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_MANY,
                inputs={
                    "collection_name": "dialogue",
                    "filter": {code_build_done_status: "filter"},
                    "update": {code_build_done_status: "update"},
                }
            )

            mongo_update_error_status = MongoNode(
                name="mongo_update_error_status",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_MANY,
                inputs={
                    "collection_name": "dialogue",
                    "filter": {code_build_error_status: "filter"},
                    "update": {code_build_error_status: "update"},
                }
            )

            # ── Workflow graph ─────────────────────────────────────────────
            START >> code_prepare_mongo_query >> [
                get_dialogue_info, code_build_topic_pipeline
            ]
            code_build_topic_pipeline >> get_all_topics
            get_dialogue_info >> code_create_batch_get_doc_info >> loop_get_doc_info
            [loop_get_doc_info, get_all_topics] >> code_prepare_qna_chunk >> embedding_chunk

            # Embedding check → branch status (for DONE/ERROR update)
            [embedding_chunk, code_prepare_qna_chunk] >> code_check_qna_embedding
            code_check_qna_embedding >> branch_update_qna_status >> [code_build_done_status, code_build_error_status]
            code_build_error_status >> mongo_update_error_status >> END

            # Insert proceeds only if embedding was successful (DONE branch)
            code_build_done_status >> code_prepare_ingestion_data >> graph_data_ingestion

            # DONE status fires only after all inserts (graph) AND done-status-build complete
            [graph_data_ingestion, code_build_done_status] >> mongo_update_done_status >> END

        wf_train_qna.compile()
        self.train_qna_workflow = wf_train_qna
    
    def _build_clean_qna_workflow(self):
        with WorkflowEngine(
            name="wf_clean_qna",
            description="clean deleted QnA records from Mongo and Milvus",
            langfuse="beegen-portal"
        ) as wf_clean_qna:

            # Step 1: Query deleted dialogues for this bot
            code_prepare_deleted_query = CodeNode(
                name="code_prepare_deleted_query",
                code_fn=prepare_delete_dialogues_query,
                inputs={"bot_id": INPUT, "ids": INPUT},
                return_keys=["query_deleted_dialogues: Dict[str, Any]"]
            )

            get_deleted_dialogues = MongoNode(
                name="get_deleted_dialogues",
                resource_key="aicenter-chatbot",
                operation="find",
                inputs={
                    "collection_name": "dialogue",
                    "query": {code_prepare_deleted_query: "query_deleted_dialogues"},
                }
            )

            # Step 2: Extract dialogue _ids
            code_extract_dialogue_ids = CodeNode(
                name="code_extract_dialogue_ids",
                code_fn=extract_dialogue_ids,
                inputs={"deleted_dialogues": {get_deleted_dialogues: "data"}},
                return_keys=["dialogue_ids: List[str]"]
            )

            # Step 3: Fetch chunk_data records that belong to these dialogues (doc_id = dialogue _id)
            code_prepare_chunk_query = CodeNode(
                name="code_prepare_chunk_query",
                code_fn=prepare_query_old_chunks,
                inputs={"ids": {code_extract_dialogue_ids: "dialogue_ids"}},
                return_keys=[
                    "query_old_chunks: Dict[str, Any]",
                    "projection: Dict[str, Any]",
                ]
            )

            get_chunk_data = MongoNode(
                name="get_chunk_data",
                resource_key="aicenter-chatbot",
                operation="find",
                inputs={
                    "collection_name": "chunk_data",
                    "query": {code_prepare_chunk_query: "query_old_chunks"},
                    "projection": {code_prepare_chunk_query: "projection"}
                }
            )

            # Step 4: Collect chunk_ids -> build Milvus expr
            code_collect_chunk_ids = CodeNode(
                name="code_collect_chunk_ids",
                code_fn=collect_chunk_ids_by_dialogue,
                inputs={"chunk_data": {get_chunk_data: "data"}},
                return_keys=["chunk_ids: List[str]", "milvus_expr: str"]
            )

            # Step 5a: Get Milvus collection name (shared bot collection)
            code_get_collection_name = CodeNode(
                name="code_get_collection_name",
                code_fn=convert_bot_id,
                inputs={"bot_id": INPUT},
                return_keys=["collection_name: str"]
            )

            # Step 5b: Delete from Milvus
            milvus_delete_chunks = MilvusNode(
                name="milvus_delete_chunks",
                resource_key="chatbot-libra",
                operation=MilvusOperation.DELETE,
                inputs={
                    "collection_name": {code_get_collection_name: "collection_name"},
                    "expr": {code_collect_chunk_ids: "milvus_expr"}
                }
            )

            # Step 6: Delete chunk_data from Mongo
            code_prepare_mongo_chunk_filter = CodeNode(
                name="code_prepare_mongo_chunk_filter",
                code_fn=prepare_delete_chunks_by_dialogue_ids,
                inputs={"dialogue_ids": {code_extract_dialogue_ids: "dialogue_ids"}},
                return_keys=["mongo_filter: Dict[str, Any]"]
            )

            mongo_delete_chunk_data = MongoNode(
                name="mongo_delete_chunk_data",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.DELETE_MANY,
                inputs={
                    "collection_name": "chunk_data",
                    "filter": {code_prepare_mongo_chunk_filter: "mongo_filter"},
                }
            )

            # Step 7: Hard delete dialogue records from Mongo
            code_prepare_dialogue_filter = CodeNode(
                name="code_prepare_dialogue_filter",
                code_fn=prepare_delete_dialogues_filter,
                inputs={"dialogue_ids": {code_extract_dialogue_ids: "dialogue_ids"}},
                return_keys=["mongo_filter: Dict[str, Any]"]
            )

            mongo_delete_dialogues = MongoNode(
                name="mongo_delete_dialogues",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.DELETE_MANY,
                inputs={
                    "collection_name": "dialogue",
                    "filter": {code_prepare_dialogue_filter: "mongo_filter"},
                }
            )

            # Workflow graph
            START >> code_prepare_deleted_query >> get_deleted_dialogues >> code_extract_dialogue_ids
            code_extract_dialogue_ids >> [code_prepare_chunk_query, code_prepare_mongo_chunk_filter, code_prepare_dialogue_filter]

            # Step 1: READ chunk IDs from Mongo first
            code_prepare_chunk_query >> get_chunk_data >> code_collect_chunk_ids

            # Step 2: Delete from Milvus (needs IDs + collection name)
            [code_collect_chunk_ids, code_get_collection_name] >> milvus_delete_chunks

            # Step 3: Delete chunk_data from Mongo AFTER IDs collected (read-before-delete)
            [code_prepare_mongo_chunk_filter, code_collect_chunk_ids] >> mongo_delete_chunk_data

            # Step 4: Delete parent dialogue records ONLY after all child deletes complete
            [
                mongo_delete_chunk_data,
                milvus_delete_chunks,
                code_prepare_dialogue_filter,
            ] >> mongo_delete_dialogues >> END

            START >> code_get_collection_name

        wf_clean_qna.compile()
        self.clean_qna_workflow = wf_clean_qna

    async def clean(
        self, request: CleanDataRequest, **kwargs
    ):
        """Hard delete specific QnA (dialogue) records from Mongo and Milvus."""
        validate_bot(request.bot_id)
        validate_dialogues_for_clean(request.bot_id, request.ids)
        try:
            import uuid
            request_id = str(uuid.uuid4())
            result = await self.clean_qna_workflow.run(
                request_id=request_id,
                inputs={
                    "bot_id": request.bot_id,
                    "ids": request.ids,
                }
            )
            return result
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Clean QnA failed: {str(e)}"
            )

    async def train(
        self, qna: TrainRequest, **kwargs
    ):
        validate_bot(qna.bot_id)
        validate_active_dialogues(qna.bot_id, qna.ids)
        try:
            import uuid
            request_id = str(uuid.uuid4())
            result = await self.train_qna_workflow.run(
                request_id=request_id,
                inputs={
                    "bot_id": qna.bot_id,
                    "ids": qna.ids
                }
            )
            return result
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Train QnA failed: {str(e)}"
            )

    async def upload(
        self, qna: UploadRequest, **kwargs
    ):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="QnA upload is not implemented"
        )

async def main():
    service = ProcessQnAService()
    
    qna = TrainRequest(bot_id="41130a38-8091-4e0f-ab69-dcb4d6b2014d",type="QA",ids=["c109b18a-d989-49de-8994-905677bfb8ad"])
    
    result = await service.train(qna)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
