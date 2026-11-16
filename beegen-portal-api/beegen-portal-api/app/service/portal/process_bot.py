import asyncio
from typing import Any, Dict, List

from beeflow.workflow import WorkflowEngine
from beeflow.nodes.primitives.data.mongo_node import MongoNode
from beeflow.nodes.primitives.transform.code_node import CodeNode
from beeflow.nodes.primitives.data.milvus_node import MilvusNode
from beeflow.nodes.base_node import END, INPUT, OUTPUT, START
from beegen.configs import MilvusOperation, MongoOperation
from fastapi import HTTPException, status

from app.service.portal.utils.prepare_document import (
    get_milvus_collection_names_for_delete,
)
from app.utils.db_validation import validate_bot
from app.utils.milvus_schema import create_bot_collections

# ─────────────────────────────────────────────────────────────
# Pure helper functions (used in CodeNodes)
# ─────────────────────────────────────────────────────────────

def build_bot_id_query(bot_id: str) -> Dict[str, Any]:
    """Build a Mongo query for every document or dialogue owned by a bot."""
    return {"query": {"bot_id": bot_id}}


def extract_doc_ids(documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract _id list from documents Mongo result."""
    doc_ids = [d.get("_id") for d in documents if d.get("_id")]
    return {"doc_ids": doc_ids}


def extract_dialogue_ids(dialogues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract _id list from dialogues Mongo result."""
    dialogue_ids = [d.get("_id") for d in dialogues if d.get("_id")]
    return {"dialogue_ids": dialogue_ids}


def build_doc_ids_filter(doc_ids: List[str]) -> Dict[str, Any]:
    """Build {document_id: {$in: doc_ids}} Mongo filter for node."""
    return {"mongo_filter": {"document_id": {"$in": doc_ids}}}


def build_document_ids_filter(doc_ids: List[str]) -> Dict[str, Any]:
    """Build {_id: {$in: doc_ids}} Mongo filter for document records."""
    return {"mongo_filter": {"_id": {"$in": doc_ids}}}


def build_chunk_doc_ids_filter(doc_ids: List[str]) -> Dict[str, Any]:
    """Build {doc_id: {$in: doc_ids}} Mongo filter for chunk_data."""
    return {"mongo_filter": {"doc_id": {"$in": doc_ids}}}


def build_dialogue_ids_filter(dialogue_ids: List[str]) -> Dict[str, Any]:
    """Build {doc_id: {$in: dialogue_ids}} Mongo filter for QnA chunk_data."""
    return {"mongo_filter": {"doc_id": {"$in": dialogue_ids}}}


def build_bot_id_filter(bot_id: str) -> Dict[str, Any]:
    """Build {bot_id: <bot_id>} Mongo filter for dialogue deletion."""
    return {"mongo_filter": {"bot_id": bot_id}}





class ProcessBotService:
    def __init__(self):
        self._build_create_bot_workflow()
        self._build_delete_bot_workflow()

    # ──────────────────────────────────────────────────────────
    # create_bot workflow
    # ──────────────────────────────────────────────────────────

    def _build_create_bot_workflow(self):
        with WorkflowEngine(
            name="wf_create_bot",
            description="create Milvus chunk and node collections for a new bot",
            langfuse="beegen-portal"
        ) as wf_create_bot:

            code_create_bot_collections = CodeNode(
                name="code_create_bot_collections",
                code_fn=create_bot_collections,
                inputs={"bot_id": INPUT},
                return_keys=[
                    "chunk_collection_name: str",
                    "node_collection_name: str",
                ],
                outputs=OUTPUT,
            )

            START >> code_create_bot_collections >> END

        wf_create_bot.compile()
        self.create_bot_workflow = wf_create_bot

    # ──────────────────────────────────────────────────────────
    # delete_bot workflow
    # ──────────────────────────────────────────────────────────

    def _build_delete_bot_workflow(self):
        with WorkflowEngine(
            name="wf_delete_bot",
            description=(
                "delete all data for a bot from Mongo and Milvus. "
                "Step 1: query all documents and dialogues by bot_id. "
                "Step 2: delete document_data/chunk_data/node/documents (document flow) "
                "and chunk_data/dialogue (QnA flow). "
                "Step 3: clear Milvus bot collections (chunk + node). "
            ),
            langfuse="beegen-portal"
        ) as wf_delete_bot:

            # ── Branch A: Document flow ──────────────────────
            # A1. Query all documents for this bot
            code_build_docs_query = CodeNode(
                name="code_build_docs_query",
                code_fn=build_bot_id_query,
                inputs={"bot_id": INPUT},
                return_keys=["query: Dict[str, Any]"]
            )

            get_documents = MongoNode(
                name="get_documents",
                resource_key="aicenter-chatbot",
                operation="find",
                inputs={
                    "collection_name": "documents",
                    "query": {code_build_docs_query: "query"},
                    "limit": 100000,
                }
            )

            # A2. Extract document _ids
            code_extract_doc_ids = CodeNode(
                name="code_extract_doc_ids",
                code_fn=extract_doc_ids,
                inputs={"documents": {get_documents: "data"}},
                return_keys=["doc_ids: List[str]"]
            )

            # A3. Build filters for chunk_data by doc_id and node by document_id
            code_build_chunk_doc_ids_filter = CodeNode(
                name="code_build_chunk_doc_ids_filter",
                code_fn=build_chunk_doc_ids_filter,
                inputs={"doc_ids": {code_extract_doc_ids: "doc_ids"}},
                return_keys=["mongo_filter: Dict[str, Any]"]
            )

            code_build_doc_ids_filter = CodeNode(
                name="code_build_doc_ids_filter",
                code_fn=build_doc_ids_filter,
                inputs={"doc_ids": {code_extract_doc_ids: "doc_ids"}},
                return_keys=["mongo_filter: Dict[str, Any]"]
            )

            code_build_document_ids_filter = CodeNode(
                name="code_build_document_ids_filter",
                code_fn=build_document_ids_filter,
                inputs={"doc_ids": {code_extract_doc_ids: "doc_ids"}},
                return_keys=["mongo_filter: Dict[str, Any]"]
            )

            mongo_delete_chunks_by_doc = MongoNode(
                name="mongo_delete_chunks_by_doc",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.DELETE_MANY,
                inputs={
                    "collection_name": "chunk_data",
                    "filter": {code_build_chunk_doc_ids_filter: "mongo_filter"},
                }
            )

            mongo_delete_nodes_by_doc = MongoNode(
                name="mongo_delete_nodes_by_doc",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.DELETE_MANY,
                inputs={
                    "collection_name": "node",
                    "filter": {code_build_doc_ids_filter: "mongo_filter"},
                }
            )

            mongo_delete_document_data = MongoNode(
                name="mongo_delete_document_data",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.DELETE_MANY,
                inputs={
                    "collection_name": "document_data",
                    "filter": {code_build_doc_ids_filter: "mongo_filter"},
                }
            )

            mongo_delete_documents = MongoNode(
                name="mongo_delete_documents",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.DELETE_MANY,
                inputs={
                    "collection_name": "documents",
                    "filter": {code_build_document_ids_filter: "mongo_filter"},
                }
            )

            # B1. Query all dialogues for this bot
            code_build_dialogues_query = CodeNode(
                name="code_build_dialogues_query",
                code_fn=build_bot_id_query,
                inputs={"bot_id": INPUT},
                return_keys=["query: Dict[str, Any]"]
            )

            get_dialogues = MongoNode(
                name="get_dialogues",
                resource_key="aicenter-chatbot",
                operation="find",
                inputs={
                    "collection_name": "dialogue",
                    "query": {code_build_dialogues_query: "query"},
                    "limit": 100000,
                }
            )

            # B2. Extract dialogue _ids
            code_extract_dialogue_ids = CodeNode(
                name="code_extract_dialogue_ids",
                code_fn=extract_dialogue_ids,
                inputs={"dialogues": {get_dialogues: "data"}},
                return_keys=["dialogue_ids: List[str]"]
            )

            # B3. Delete QnA chunk_data by dialogue._id (stored as doc_id in chunk_data)
            code_build_dialogue_ids_filter = CodeNode(
                name="code_build_dialogue_ids_filter",
                code_fn=build_dialogue_ids_filter,
                inputs={"dialogue_ids": {code_extract_dialogue_ids: "dialogue_ids"}},
                return_keys=["mongo_filter: Dict[str, Any]"]
            )

            mongo_delete_qna_chunk_data = MongoNode(
                name="mongo_delete_qna_chunk_data",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.DELETE_MANY,
                inputs={
                    "collection_name": "chunk_data",
                    "filter": {code_build_dialogue_ids_filter: "mongo_filter"},
                }
            )

            # B4. Delete all dialogues for bot
            code_build_bot_id_filter = CodeNode(
                name="code_build_bot_id_filter",
                code_fn=build_bot_id_filter,
                inputs={"bot_id": INPUT},
                return_keys=["mongo_filter: Dict[str, Any]"]
            )

            mongo_delete_dialogues = MongoNode(
                name="mongo_delete_dialogues",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.DELETE_MANY,
                inputs={
                    "collection_name": "dialogue",
                    "filter": {code_build_bot_id_filter: "mongo_filter"},
                }
            )

            # ── Branch C: Milvus cleanup ─────────────────────
            # Drops the Milvus collections (chunk + node) directly.
            code_get_milvus_names = CodeNode(
                name="code_get_milvus_names",
                code_fn=get_milvus_collection_names_for_delete,
                inputs={"bot_id": INPUT},
                return_keys=["chunk_collection_name: str", "node_collection_name: str"]
            )

            milvus_drop_chunk_collection = MilvusNode(
                name="milvus_drop_chunk_collection",
                resource_key="chatbot-libra",
                operation=MilvusOperation.DROP_COLLECTION,
                inputs={
                    "collection_name": {code_get_milvus_names: "chunk_collection_name"}
                }
            )

            milvus_drop_node_collection = MilvusNode(
                name="milvus_drop_node_collection",
                resource_key="chatbot-libra",
                operation=MilvusOperation.DROP_COLLECTION,
                inputs={
                    "collection_name": {code_get_milvus_names: "node_collection_name"},
                }
            )

            # ── Workflow graph ──────────────────────────────
            START >> [
                code_build_docs_query,
                code_build_dialogues_query,
                code_get_milvus_names,
            ]

            # Document branch
            code_build_docs_query >> get_documents >> code_extract_doc_ids >> [
                code_build_chunk_doc_ids_filter,
                code_build_doc_ids_filter,
                code_build_document_ids_filter,
            ]
            code_build_chunk_doc_ids_filter >> mongo_delete_chunks_by_doc
            code_build_doc_ids_filter >> [
                mongo_delete_nodes_by_doc,
                mongo_delete_document_data,
            ]
            [
                mongo_delete_chunks_by_doc,
                mongo_delete_nodes_by_doc,
                mongo_delete_document_data,
                code_build_document_ids_filter,
            ] >> mongo_delete_documents >> END

            # QnA branch: collect dialogue IDs before deleting dependent data.
            code_build_dialogues_query >> get_dialogues >> code_extract_dialogue_ids >> code_build_dialogue_ids_filter
            code_build_dialogue_ids_filter >> mongo_delete_qna_chunk_data
            mongo_delete_qna_chunk_data >> code_build_bot_id_filter >> mongo_delete_dialogues >> END

            # Milvus branch
            code_get_milvus_names >> [milvus_drop_chunk_collection, milvus_drop_node_collection]
            milvus_drop_chunk_collection >> END
            milvus_drop_node_collection >> END

        wf_delete_bot.compile()
        self.delete_bot_workflow = wf_delete_bot

    # ──────────────────────────────────────────────────────────
    # Public methods
    # ──────────────────────────────────────────────────────────

    async def create_bot(self, bot_id: str, **kwargs):
        """Create chunk and node Milvus collections for a new bot."""
        validate_bot(bot_id)
        try:
            import uuid
            result = await self.create_bot_workflow.run(
                request_id=str(uuid.uuid4()),
                inputs={"bot_id": bot_id}
            )
            if not result.get("chunk_collection_name") or not result.get(
                "node_collection_name"
            ):
                raise RuntimeError("Milvus collections were not created")
            return result
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Create bot failed: {str(e)}"
            )

    async def delete_bot(self, bot_id: str, **kwargs):
        """Delete trained Mongo and Milvus data for a bot.

        Queries documents and dialogues from Mongo by bot_id first,
        then deletes dependent trained data and clears the Milvus chunk/node
        collections, then deletes document_data and documents.

        Args:
            bot_id: The bot identifier.
        """
        validate_bot(bot_id)
        try:
            import uuid
            result = await self.delete_bot_workflow.run(
                request_id=str(uuid.uuid4()),
                inputs={"bot_id": bot_id}
            )
            return result
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Delete bot failed: {str(e)}"
            )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test ProcessBotService")
    parser.add_argument("--action", choices=["create", "delete"], required=True)
    parser.add_argument("--bot_id", type=str, required=True)
    args = parser.parse_args()

    async def _run():
        svc = ProcessBotService()
        if args.action == "create":
            result = await svc.create_bot(args.bot_id)
        else:
            result = await svc.delete_bot(args.bot_id)
        print(result)

    asyncio.run(_run())
