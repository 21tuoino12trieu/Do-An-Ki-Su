"""
AUTO Mode Graph

This graph gets active pages from MongoDB, fetches from Confluence,
compares and detects changes (insert/update/move/delete).
"""

from beeflow.nodes import (
    START,
    END,
    INPUT,
    OUTPUT,
    GraphNode,
    CodeNode,
    SQLNode,
    MongoNode,
    BranchNode,
)
from beeflow.nodes.flow.for_loop_node import ForLoopNode

from beegen.configs.storage.sql_config import SQLOperation
from beegen.configs.storage.mongo_config import MongoOperation

from confluence_workflow.utils.logger import get_logger
from confluence_workflow.functions.auto_mode_processor import (
    _extract_active_page_ids,
    _fetch_confluence_pages,
    _build_postgres_pages_sql_params,
    _compare_datasets,
    _process_inserts,
    _process_updates,
    _build_move_batches,
    _build_updated_pages,
)
from confluence_workflow.functions.workflow_helpers import (
    build_empty_mode_output,
    build_metadata_update_batches,
    forward_mode_output,
)
from confluence_workflow.functions.workflow_helpers import (
    build_auto_mode_stats,
    build_bot_selector,
    build_bot_sync_mode_query,
    build_deleted_page_cleanup_inputs,
)
from confluence_workflow.graphs.cleanup_old_data import build_cleanup_old_confluence_data_graph

logger = get_logger("auto_mode")


def build_auto_mode_graph(config):
    """
    Build AUTO mode graph using BeeFlow.

    This graph:
    1. Gets active page IDs from MongoDB
    2. Fetches all pages from Confluence (parents + descendants)
    3. Gets all pages from PostgreSQL
    4. Compares datasets and classifies changes
    5. Processes inserts, updates, moves, deletes
    6. Builds the updated_pages list for downstream chunk processing

    Args:
        config: Workflow configuration

    Returns:
        Compiled graph instance
    """
    with GraphNode(
        name="graph_auto_mode",
        description="AUTO mode: Compare and process changes",
        inputs={
            "bot_id": INPUT,
            "page_ids": INPUT,
            "batch_size": INPUT,
            "confluence_config": INPUT,
        },
    ) as graph_auto_mode:
        code_build_active_pages_query = CodeNode(
            name="code_build_active_pages_query",
            code_fn=build_bot_sync_mode_query,
            inputs={"bot_id": {INPUT: "bot_id"}},
            return_keys=["query: dict"],
        )

        
        # Step 1: Get active pages from MongoDB
        mongo_get_active_pages = MongoNode(
            name="mongo_get_active_pages",
            resource_key="aicenter-chatbot",
            operation=MongoOperation.FIND,
            inputs={
                "collection_name": "documents",
                "query": {code_build_active_pages_query: "query"},
                "projection": {"external_id": 1, "_id": 0},
            },
        )

        code_extract_active_page_ids = CodeNode(
            name="code_extract_active_page_ids",
            code_fn=_extract_active_page_ids,
            inputs={"active_pages": {mongo_get_active_pages: "data"}},
            return_keys=["active_page_ids: list", "has_active_pages: bool"],
        )

        branch_has_active_pages = BranchNode(
            name="branch_has_active_pages",
            cases={"has_active_pages == True": "code_fetch_confluence_pages"},
            inputs={"has_active_pages": {code_extract_active_page_ids: "has_active_pages"}},
            default="code_build_empty_mode_output",
        )

        code_build_bot_documents_selector = CodeNode(
            name="code_build_bot_documents_selector",
            code_fn=build_bot_selector,
            inputs={"bot_id": {INPUT: "bot_id"}},
            return_keys=["query: dict"],
        )

        mongo_get_bot_documents = MongoNode(
            name="mongo_get_bot_documents",
            resource_key="aicenter-chatbot",
            operation=MongoOperation.FIND,
            inputs={
                "collection_name": "documents",
                "query": {code_build_bot_documents_selector: "query"},
                "projection": {
                    "_id": 1,
                    "external_id": 1,
                    "level": 1,
                    "external_parent_id": 1,
                    "sync_mode": 1,
                },
            },
        )

        # Step 2: Fetch all pages from Confluence
        code_fetch_confluence_pages = CodeNode(
            name="code_fetch_confluence_pages",
            code_fn=_fetch_confluence_pages,
            inputs={
                "page_ids": {INPUT: "page_ids"},
                "confluence_config": {INPUT: "confluence_config"},
                "batch_size": {INPUT: "batch_size"},
            },
            return_keys=[
                "confluence_pages: list",
                "fetch_complete: bool",
                "failed_root_ids: list",
            ],
        )

        # Step 3: Get all pages from PostgreSQL
        code_build_pg_params = CodeNode(
            name="code_build_pg_params",
            code_fn=_build_postgres_pages_sql_params,
            inputs={"bot_id": {INPUT: "bot_id"}},
            return_keys=["params: Any"],
        )

        sql_get_postgres_pages = SQLNode(
            name="sql_get_postgres_pages",
            resource_key="anapp",
            operation=SQLOperation.QUERY,
            inputs={
                "query": """
                    SELECT page_id, title, content_hash, parent_id, is_deleted, sync_status
                    FROM knowledge_base.documents
                    WHERE source_type = 'CONFLUENCE'
                      AND sync_status = 'SYNCED'
                      AND bot_id = %s
                """,
                "params": {code_build_pg_params: "params"},
                "limit": 100000,
            },
        )

        # Step 4: Compare datasets
        code_compare_datasets = CodeNode(
            name="code_compare_datasets",
            code_fn=_compare_datasets,
            inputs={
                "confluence_pages": {code_fetch_confluence_pages: "confluence_pages"},
                "postgres_pages": {sql_get_postgres_pages: "data"},
                "active_page_ids": {code_extract_active_page_ids: "active_page_ids"},
                "fetch_complete": {code_fetch_confluence_pages: "fetch_complete"},
            },
            return_keys=[
                "to_insert: list",
                "to_update: list",
                "to_metadata_update: list",
                "to_move: list",
                "to_delete: list",
                "pages_no_change: list",
            ],
        )

        # Step 5: Process inserts
        code_process_inserts = CodeNode(
            name="code_process_inserts",
            code_fn=_process_inserts,
            inputs={
                "pages": {code_compare_datasets: "to_insert"},
                "bot_id": {INPUT: "bot_id"},
            },
            return_keys=["batch_data: List[Dict[str, Any]]", "inserted_count: int"],
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
                inputs={"query": {INPUT: "sql_query"}, "params": {INPUT: "sql_params"}},
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

        # Step 6: Process updates
        code_process_updates = CodeNode(
            name="code_process_updates",
            code_fn=_process_updates,
            inputs={
                "pages": {code_compare_datasets: "to_update"},
                "bot_id": {INPUT: "bot_id"},
            },
            return_keys=["batch_data: List[Dict[str, Any]]", "updated_count: int"],
        )

        with ForLoopNode(
            name="loop_update_pages",
            max_concurrency=10,
            inputs={"batch_data": {code_process_updates: "batch_data"}},
        ) as loop_update_pages:
            sql_update_page = SQLNode(
                name="sql_update_page",
                resource_key="anapp",
                operation=SQLOperation.EXECUTE,
                inputs={"query": {INPUT: "sql_query"}, "params": {INPUT: "sql_params"}},
            )

            mongo_update_page = MongoNode(
                name="mongo_update_page",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {INPUT: "mongo_query"},
                    "update": {INPUT: "mongo_update"},
                    "upsert": {INPUT: "mongo_upsert"},
                },
            )

            START >> sql_update_page >> mongo_update_page >> END

        code_process_metadata_updates = CodeNode(
            name="code_process_metadata_updates",
            code_fn=build_metadata_update_batches,
            inputs={
                "pages": {code_compare_datasets: "to_metadata_update"},
                "bot_id": {INPUT: "bot_id"},
            },
            return_keys=["batch_data: list", "metadata_updated_count: int"],
        )

        with ForLoopNode(
            name="loop_metadata_updates",
            max_concurrency=10,
            inputs={"batch_data": {code_process_metadata_updates: "batch_data"}},
        ) as loop_metadata_updates:
            sql_update_metadata = SQLNode(
                name="sql_update_metadata",
                resource_key="anapp",
                operation=SQLOperation.EXECUTE,
                inputs={"query": {INPUT: "sql_query"}, "params": {INPUT: "sql_params"}},
            )
            mongo_update_metadata = MongoNode(
                name="mongo_update_metadata",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {INPUT: "mongo_filter"},
                    "update": {INPUT: "mongo_update"},
                    "upsert": False,
                },
            )
            START >> sql_update_metadata >> mongo_update_metadata >> END

        # Step 7: Process moves
        code_build_move_batches = CodeNode(
            name="code_build_move_batches",
            code_fn=_build_move_batches,
            inputs={
                "to_move": {code_compare_datasets: "to_move"},
                "confluence_pages": {code_fetch_confluence_pages: "confluence_pages"},
                "active_page_ids": {code_extract_active_page_ids: "active_page_ids"},
                "bot_documents": {mongo_get_bot_documents: "data"},
                "bot_id": {INPUT: "bot_id"},
            },
            return_keys=[
                "active_move_batch: list",
                "inactive_move_batch: list",
                "sql_move_batch: list",
                "moved_count: int",
                "move_deleted_page_ids: list",
            ],
        )

        with ForLoopNode(
            name="loop_move_active_pages",
            max_concurrency=10,
            inputs={"batch_data": {code_build_move_batches: "active_move_batch"}},
        ) as loop_move_active_pages:
            mongo_move_active_page = MongoNode(
                name="mongo_move_active_page",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {INPUT: "mongo_filter"},
                    "update": {INPUT: "mongo_update"},
                },
            )
            START >> mongo_move_active_page >> END

        with ForLoopNode(
            name="loop_move_inactive_pages",
            max_concurrency=10,
            inputs={"batch_data": {code_build_move_batches: "inactive_move_batch"}},
        ) as loop_move_inactive_pages:
            mongo_move_inactive_page = MongoNode(
                name="mongo_move_inactive_page",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {INPUT: "mongo_filter"},
                    "update": {INPUT: "mongo_update"},
                    "upsert": {INPUT: "mongo_upsert"},
                },
            )
            START >> mongo_move_inactive_page >> END

        with ForLoopNode(
            name="loop_move_sql_updates",
            max_concurrency=10,
            inputs={"batch_data": {code_build_move_batches: "sql_move_batch"}},
        ) as loop_move_sql_updates:
            sql_move_page = SQLNode(
                name="sql_move_page",
                resource_key="anapp",
                operation=SQLOperation.EXECUTE,
                inputs={
                    "query": {INPUT: "sql_query"},
                    "params": {INPUT: "sql_params"},
                },
            )
            START >> sql_move_page >> END

        code_build_deleted_page_cleanup_inputs = CodeNode(
            name="code_build_deleted_page_cleanup_inputs",
            code_fn=build_deleted_page_cleanup_inputs,
            inputs={
                "primary_page_ids": {code_compare_datasets: "to_delete"},
                "additional_page_ids": {code_build_move_batches: "move_deleted_page_ids"},
                "bot_id": {INPUT: "bot_id"},
            },
            return_keys=["page_ids: list", "params: Any", "selector: dict"],
        )

        # Step 8: Process deletes
        sql_mark_deleted_pages = SQLNode(
            name="sql_mark_deleted_pages",
            resource_key="anapp",
            operation=SQLOperation.EXECUTE,
            inputs={
                "query": """
                    UPDATE knowledge_base.documents
                    SET is_deleted = TRUE,
                        sync_status = 'DELETED_ON_SOURCE'
                    WHERE page_id = ANY(%s) AND bot_id = %s
                """,
                "params": {code_build_deleted_page_cleanup_inputs: "params"},
            },
        )

        mongo_mark_deleted_documents = MongoNode(
            name="mongo_mark_deleted_documents",
            resource_key="aicenter-chatbot",
            operation=MongoOperation.UPDATE_MANY,
            inputs={
                "collection_name": "documents",
                "filter": {code_build_deleted_page_cleanup_inputs: "selector"},
                "update": {
                    "$set": {"deleted": True},
                    "$currentDate": {"sync_at": True},
                },
            },
        )

        graph_cleanup_deleted_confluence_data = build_cleanup_old_confluence_data_graph(
            name="graph_cleanup_deleted_confluence_data",
            inputs={
                "bot_id": {INPUT: "bot_id"},
                "document_query": {code_build_deleted_page_cleanup_inputs: "selector"},
                "protected_multimedia_ids": [],
            },
        )

        # Step 9: Build updated pages list
        code_build_updated_list = CodeNode(
            name="code_build_updated_list",
            code_fn=_build_updated_pages,
            inputs={
                "insert_pages": {code_compare_datasets: "to_insert"},
                "update_pages": {code_compare_datasets: "to_update"},
                "metadata_update_pages": {code_compare_datasets: "to_metadata_update"},
                "move_items": {code_compare_datasets: "to_move"},
                "confluence_pages": {code_fetch_confluence_pages: "confluence_pages"},
            },
            return_keys=["updated_pages: list"],
        )

        code_build_auto_mode_stats = CodeNode(
            name="code_build_auto_mode_stats",
            code_fn=build_auto_mode_stats,
            inputs={
                "inserted_count": {code_process_inserts: "inserted_count"},
                "updated_count": {code_process_updates: "updated_count"},
                "metadata_updated_count": {code_process_metadata_updates: "metadata_updated_count"},
                "moved_count": {code_build_move_batches: "moved_count"},
                "deleted_page_ids": {code_compare_datasets: "to_delete"},
            },
            return_keys=["total_processed: int", "total_updated: int", "total_deleted: int"],
        )

        code_build_empty_mode_output = CodeNode(
            name="code_build_empty_mode_output",
            code_fn=build_empty_mode_output,
            outputs={
                "updated_pages": OUTPUT,
                "pages_no_change": OUTPUT,
                "total_processed": OUTPUT,
                "total_updated": OUTPUT,
                "total_deleted": OUTPUT,
            },
            return_keys=[
                "updated_pages: list",
                "pages_no_change: list",
                "total_processed: int",
                "total_updated: int",
                "total_deleted: int",
            ],
        )

        code_package_mode_output = CodeNode(
            name="code_package_mode_output",
            code_fn=forward_mode_output,
            inputs={
                "current_updated_pages": {code_build_updated_list: "updated_pages"},
                "current_pages_no_change": {code_compare_datasets: "pages_no_change"},
                "current_total_processed": {code_build_auto_mode_stats: "total_processed"},
                "current_total_updated": {code_build_auto_mode_stats: "total_updated"},
                "current_total_deleted": {code_build_auto_mode_stats: "total_deleted"},
            },
            return_keys=[
                "updated_pages: list",
                "pages_no_change: list",
                "total_processed: int",
                "total_updated: int",
                "total_deleted: int",
            ],
            outputs={
                "updated_pages": OUTPUT,
                "pages_no_change": OUTPUT,
                "total_processed": OUTPUT,
                "total_updated": OUTPUT,
                "total_deleted": OUTPUT,
            },
        )

        # Build workflow graph
        START >> code_build_active_pages_query >> mongo_get_active_pages >> code_extract_active_page_ids
        code_extract_active_page_ids >> [branch_has_active_pages, code_build_pg_params]
        branch_has_active_pages >> code_fetch_confluence_pages
        code_build_pg_params >> sql_get_postgres_pages
        [code_fetch_confluence_pages, sql_get_postgres_pages] >> code_compare_datasets

        code_compare_datasets >> [
            code_process_inserts,
            code_process_updates,
            code_process_metadata_updates,
            code_build_move_batches,
        ]

        code_process_inserts >> loop_insert_pages >> code_build_updated_list
        code_process_updates >> loop_update_pages >> code_build_updated_list
        code_process_metadata_updates >> loop_metadata_updates >> code_build_updated_list
        [loop_insert_pages, loop_update_pages, code_compare_datasets] >> code_build_bot_documents_selector
        code_build_bot_documents_selector >> mongo_get_bot_documents
        mongo_get_bot_documents >> code_build_move_batches
        code_build_move_batches >> [loop_move_active_pages, loop_move_inactive_pages]
        [loop_move_active_pages, loop_move_inactive_pages] >> loop_move_sql_updates
        [code_compare_datasets, code_build_move_batches] >> code_build_deleted_page_cleanup_inputs
        loop_move_active_pages >> code_build_updated_list
        loop_move_inactive_pages >> code_build_updated_list
        loop_move_sql_updates >> code_build_updated_list

        code_build_deleted_page_cleanup_inputs >> [sql_mark_deleted_pages, mongo_mark_deleted_documents]
        sql_mark_deleted_pages >> mongo_mark_deleted_documents >> graph_cleanup_deleted_confluence_data

        code_compare_datasets >> code_build_auto_mode_stats
        code_process_inserts >> code_build_auto_mode_stats
        code_process_updates >> code_build_auto_mode_stats
        code_process_metadata_updates >> code_build_auto_mode_stats
        code_build_move_batches >> code_build_auto_mode_stats
        graph_cleanup_deleted_confluence_data >> code_build_auto_mode_stats
        [code_build_updated_list, code_build_auto_mode_stats] >> code_package_mode_output >> END
        code_build_empty_mode_output >> END

    graph_auto_mode.build()
    return graph_auto_mode
