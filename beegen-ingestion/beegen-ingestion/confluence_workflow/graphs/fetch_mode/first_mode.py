"""FIRST mode graph for reconciling selected Confluence root trees."""

from beeflow.nodes import END, INPUT, OUTPUT, START, CodeNode, GraphNode, MongoNode, SQLNode
from beeflow.nodes.flow.for_loop_node import ForLoopNode

from beegen.configs.storage.mongo_config import MongoOperation
from beegen.configs.storage.sql_config import SQLOperation

from confluence_workflow.functions.first_mode_processor import (
    _build_updated_pages_first_mode,
    _classify_first_mode_roots,
    _fetch_confluence_pages_first_mode,
    _process_inserts_first_mode,
)
from confluence_workflow.functions.workflow_helpers import (
    build_bot_selector,
    build_first_mode_stats,
    forward_mode_output,
)
from confluence_workflow.graphs.cleanup_old_data import build_cleanup_old_confluence_data_graph


def build_first_mode_graph(config):
    """Build FIRST mode without rebuilding root trees that remain active."""
    with GraphNode(
        name="graph_first_mode",
        description="FIRST mode: reconcile selected Confluence root trees",
        inputs={
            "bot_id": INPUT,
            "page_ids": INPUT,
            "confluence_config": INPUT,
            "batch_size": INPUT,
        },
    ) as graph_first_mode:
        code_build_existing_documents_selector = CodeNode(
            name="code_build_existing_documents_selector",
            code_fn=build_bot_selector,
            inputs={"bot_id": {INPUT: "bot_id"}},
            return_keys=["query: dict"],
        )

        mongo_get_existing_documents = MongoNode(
            name="mongo_get_existing_documents",
            resource_key="aicenter-chatbot",
            operation=MongoOperation.FIND,
            inputs={
                "collection_name": "documents",
                "query": {code_build_existing_documents_selector: "query"},
                "projection": {
                    "_id": 1,
                    "external_id": 1,
                    "external_parent_id": 1,
                    "level": 1,
                    "deleted": 1,
                },
                "limit": 0,
            },
        )

        code_classify_first_mode_roots = CodeNode(
            name="code_classify_first_mode_roots",
            code_fn=_classify_first_mode_roots,
            inputs={
                "active_root_ids": {INPUT: "page_ids"},
                "existing_documents": {mongo_get_existing_documents: "data"},
                "bot_id": {INPUT: "bot_id"},
            },
            return_keys=[
                "new_root_ids: list",
                "kept_root_ids: list",
                "deleted_page_ids: list",
                "deleted_document_query: dict",
                "postgres_delete_params: Any",
            ],
        )

        code_fetch_confluence_pages = CodeNode(
            name="code_fetch_confluence_pages",
            code_fn=_fetch_confluence_pages_first_mode,
            inputs={
                "parent_ids": {code_classify_first_mode_roots: "new_root_ids"},
                "confluence_config": {INPUT: "confluence_config"},
                "batch_size": {INPUT: "batch_size"},
            },
            return_keys=["confluence_pages: list", "total_count: int"],
        )

        code_process_inserts = CodeNode(
            name="code_process_inserts",
            code_fn=_process_inserts_first_mode,
            inputs={
                "pages": {code_fetch_confluence_pages: "confluence_pages"},
                "bot_id": {INPUT: "bot_id"},
                "parent_page_ids": {
                    code_classify_first_mode_roots: "new_root_ids"
                },
            },
            return_keys=["batch_data: List[Dict[str, Any]]"],
        )

        with ForLoopNode(
            name="loop_insert_pages",
            max_concurrency=10,
            inputs={"batch_data": {code_process_inserts: "batch_data"}},
        ) as loop_insert_pages:
            sql_insert_page = SQLNode(
                name="sql_insert_page",
                resource_key="anapp",
                operation=SQLOperation.EXECUTE,
                inputs={
                    "query": {INPUT: "sql_query"},
                    "params": {INPUT: "sql_params"},
                },
            )

            mongo_upsert_page = MongoNode(
                name="mongo_upsert_page",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {INPUT: "mongo_query"},
                    "update": {INPUT: "mongo_update"},
                    "upsert": {INPUT: "mongo_upsert"},
                },
            )

            START >> sql_insert_page >> mongo_upsert_page >> END

        graph_cleanup_inactive_confluence_data = build_cleanup_old_confluence_data_graph(
            name="graph_cleanup_inactive_confluence_data",
            inputs={
                "bot_id": {INPUT: "bot_id"},
                "document_query": {
                    code_classify_first_mode_roots: "deleted_document_query"
                },
                "protected_multimedia_ids": [],
            },
        )

        mongo_delete_inactive_documents = MongoNode(
            name="mongo_delete_inactive_documents",
            resource_key="aicenter-chatbot",
            operation=MongoOperation.DELETE_MANY,
            inputs={
                "collection_name": "documents",
                "filter": {
                    code_classify_first_mode_roots: "deleted_document_query"
                },
            },
        )

        sql_delete_inactive_documents = SQLNode(
            name="sql_delete_inactive_documents",
            resource_key="anapp",
            operation=SQLOperation.EXECUTE,
            inputs={
                "query": """
                    DELETE FROM knowledge_base.documents
                    WHERE page_id = ANY(%s)
                      AND bot_id = %s
                      AND source_type = 'CONFLUENCE'
                """,
                "params": {
                    code_classify_first_mode_roots: "postgres_delete_params"
                },
            },
        )

        code_build_updated_list = CodeNode(
            name="code_build_updated_list",
            code_fn=_build_updated_pages_first_mode,
            inputs={
                "confluence_pages": {code_fetch_confluence_pages: "confluence_pages"}
            },
            return_keys=["updated_pages: list"],
        )

        code_build_first_mode_stats = CodeNode(
            name="code_build_first_mode_stats",
            code_fn=build_first_mode_stats,
            inputs={
                "total_count": {code_fetch_confluence_pages: "total_count"},
                "deleted_page_ids": {code_classify_first_mode_roots: "deleted_page_ids"},
            },
            return_keys=[
                "total_processed: int",
                "total_updated: int",
                "total_deleted: int",
            ],
        )

        code_package_mode_output = CodeNode(
            name="code_package_mode_output",
            code_fn=forward_mode_output,
            return_keys=[
                "updated_pages: list",
                "pages_no_change: list",
                "total_processed: int",
                "total_updated: int",
                "total_deleted: int",
            ],
            inputs={
                "current_updated_pages": {code_build_updated_list: "updated_pages"},
                "current_total_processed": {code_build_first_mode_stats: "total_processed"},
                "current_total_updated": {code_build_first_mode_stats: "total_updated"},
                "current_total_deleted": {code_build_first_mode_stats: "total_deleted"},
            },
            outputs={
                "updated_pages": OUTPUT,
                "pages_no_change": OUTPUT,
                "total_processed": OUTPUT,
                "total_updated": OUTPUT,
                "total_deleted": OUTPUT,
            },
        )

        START >> code_build_existing_documents_selector >> mongo_get_existing_documents >> code_classify_first_mode_roots >> code_fetch_confluence_pages
        code_fetch_confluence_pages >> code_process_inserts >> loop_insert_pages >> code_build_updated_list

        code_fetch_confluence_pages >> graph_cleanup_inactive_confluence_data
        graph_cleanup_inactive_confluence_data >> mongo_delete_inactive_documents
        mongo_delete_inactive_documents >> sql_delete_inactive_documents

        [code_fetch_confluence_pages, sql_delete_inactive_documents] >> code_build_first_mode_stats
        [code_build_updated_list, code_build_first_mode_stats] >> code_package_mode_output
        code_package_mode_output >> END

    graph_first_mode.build()
    return graph_first_mode
