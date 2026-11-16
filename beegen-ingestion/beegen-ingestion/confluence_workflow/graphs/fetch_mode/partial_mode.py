"""
PARTIAL Mode Graph

This graph fetches only specified page IDs, compares with existing data,
and processes changes (insert/update/move/delete).
"""

from beeflow.nodes import START, END, INPUT, OUTPUT, GraphNode, CodeNode, SQLNode, MongoNode
from beeflow.nodes.flow.for_loop_node import ForLoopNode

from beegen.configs.storage.sql_config import SQLOperation
from beegen.configs.storage.mongo_config import MongoOperation

from confluence_workflow.utils.logger import get_logger

from confluence_workflow.functions.partial_mode_processor import (
    _build_metadata_completed_status_batches,
    _build_move_completed_status_batches,
    _build_unchanged_status_batches,
    _process_inserts,
    _process_updates,
    _build_move_batches,
    _build_updated_pages,
    _filter_deleted_page_ids,
    _fetch_specific_pages,
    _build_existing_pages_sql_params,
    _compare_pages,
    build_partial_error_retry_query,
)
from confluence_workflow.functions.workflow_helpers import (
    build_bot_selector,
    build_deleted_page_cleanup_inputs,
    build_metadata_update_batches,
    build_partial_mode_stats,
    forward_mode_output,
)
from confluence_workflow.graphs.cleanup_old_data import build_cleanup_old_confluence_data_graph

logger = get_logger('partial_mode')


def build_partial_mode_graph(config):
    """
    Build PARTIAL mode graph using BeeFlow.
    
    This graph:
    1. Fetches specific pages by IDs from Confluence
    2. Marks pages not found as deleted
    3. Gets existing pages from PostgreSQL for comparison
    4. Compares pages and classifies changes
    5. Processes inserts, updates, moves, deletes
    6. Builds the updated_pages list for downstream chunk processing
    
    Args:
        config: Workflow configuration
        
    Returns:
        Compiled graph instance
    """
    with GraphNode(
        name="graph_partial_mode",
        description="PARTIAL mode: Fetch specific pages and process changes",
        inputs={
            "bot_id": INPUT,
            "page_ids": INPUT,
            "limit": INPUT,
            "confluence_config": INPUT,
            "active_pages": INPUT,
        }
    ) as graph_partial_mode:
        # Step 1: Fetch specific pages
        code_fetch_specific_pages = CodeNode(
            name="code_fetch_specific_pages",
            code_fn=_fetch_specific_pages,
            inputs={
                "page_ids": {INPUT: "page_ids"},
                "confluence_config": {INPUT: "confluence_config"},
                "limit": {INPUT: "limit"},
            },
            return_keys=["fetched_pages: list", "not_found: list", "fetch_errors: list"],
        )

        code_build_bot_documents_selector = CodeNode(
            name="code_build_bot_documents_selector",
            code_fn=build_bot_selector,
            inputs={"bot_id": {INPUT: "bot_id"}},
            return_keys=["query: dict"],
        )

        mongo_get_bot_documents = MongoNode(
            name="mongo_get_bot_documents",
            resource_key='aicenter-chatbot',
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
        
        # Step 2: Filter deleted pages (not_found intersect active_pages)
        code_filter_deleted_pages = CodeNode(
            name="code_filter_deleted_pages",
            code_fn=_filter_deleted_page_ids,
            inputs={
                "not_found": {code_fetch_specific_pages: "not_found"},
                "active_pages": {INPUT: "active_pages"},
            },
            return_keys=["deleted_page_ids: list", "deleted_count: int"],
        )

        code_build_deleted_page_cleanup_inputs = CodeNode(
            name="code_build_deleted_page_cleanup_inputs",
            code_fn=build_deleted_page_cleanup_inputs,
            inputs={
                "primary_page_ids": {code_filter_deleted_pages: "deleted_page_ids"},
                "bot_id": {INPUT: "bot_id"},
            },
            return_keys=["page_ids: list", "params: Any", "selector: dict"],
        )

        # Step 3: Mark deleted pages in PostgreSQL (active pages only)
        sql_mark_deleted_pages = SQLNode(
            name="sql_mark_deleted_pages",
            resource_key='anapp',
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

        # Step 4: Mark deleted in MongoDB documents
        mongo_mark_deleted_documents = MongoNode(
            name="mongo_mark_deleted_documents",
            resource_key='aicenter-chatbot',
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
        code_build_existing_pages_params = CodeNode(
            name="code_build_existing_pages_params",
            code_fn=_build_existing_pages_sql_params,
            return_keys=["params: Any"],
            inputs={
                "bot_id": {INPUT: "bot_id"},
                "page_ids": {INPUT: "page_ids"},
            },
        )
        
        # Step 7: Get existing pages
        sql_get_existing_pages = SQLNode(
            name="sql_get_existing_pages",
            resource_key='anapp',
            operation=SQLOperation.QUERY,
            inputs={
                "query": """
                    SELECT page_id, title, content_hash, version_number, parent_id, is_deleted
                    FROM knowledge_base.documents
                    WHERE source_type = 'CONFLUENCE'
                        AND bot_id = %s
                        AND page_id = ANY(%s)
                """,
                "params": {code_build_existing_pages_params: "params"},
                "limit": 100000,
            },
        )

        code_build_partial_error_retry_query = CodeNode(
            name="code_build_partial_error_retry_query",
            code_fn=build_partial_error_retry_query,
            inputs={
                "bot_id": {INPUT: "bot_id"},
                "page_ids": {INPUT: "page_ids"},
            },
            return_keys=["query: dict"],
        )

        mongo_find_partial_error_retry_documents = MongoNode(
            name="mongo_find_partial_error_retry_documents",
            resource_key="aicenter-chatbot",
            operation=MongoOperation.FIND,
            inputs={
                "collection_name": "documents",
                "query": {code_build_partial_error_retry_query: "query"},
                "projection": {"external_id": 1, "_id": 0},
                "limit": 0,
            },
        )
        
        # Step 8: Compare pages
        code_compare_pages = CodeNode(
            name="code_compare_pages",
            code_fn=_compare_pages,
            inputs={
                "fetched_pages": {code_fetch_specific_pages: "fetched_pages"},
                "existing_pages": {sql_get_existing_pages: "data"},
                "error_retry_documents": {
                    mongo_find_partial_error_retry_documents: "data"
                },
            },
            return_keys=[
                "to_insert: list",
                "to_update: list",
                "to_metadata_update: list",
                "to_move: list",
                "move_only_page_ids: list",
                "pages_no_change: list",
            ],
        )
        
        # Step 9: Process inserts
        code_process_inserts = CodeNode(
            name="code_process_inserts",
            code_fn=_process_inserts,
            inputs={
                "pages": {code_compare_pages: "to_insert"},
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
                resource_key='anapp',
                operation=SQLOperation.EXECUTE,
                inputs={
                    "query": {INPUT: "sql_query"},
                    "params": {INPUT: "sql_params"},
                },
            )

            mongo_upsert_page = MongoNode(
                name="mongo_upsert_page",
                resource_key='aicenter-chatbot',
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {INPUT: "mongo_query"},
                    "update": {INPUT: "mongo_update"},
                    "upsert": {INPUT: "mongo_upsert"},
                },
            )

            START >> sql_insert_page >> mongo_upsert_page >> END
        
        # Step 10: Process updates
        code_process_updates = CodeNode(
            name="code_process_updates",
            code_fn=_process_updates,
            inputs={
                "pages": {code_compare_pages: "to_update"},
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
                resource_key='anapp',
                operation=SQLOperation.EXECUTE,
                inputs={
                    "query": {INPUT: "sql_query"},
                    "params": {INPUT: "sql_params"},
                },
            )

            mongo_update_page = MongoNode(
                name="mongo_update_page",
                resource_key='aicenter-chatbot',
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
                "pages": {code_compare_pages: "to_metadata_update"},
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

        # Step 11: Process moves (active: update/delete, inactive: keep sync_mode and update parent)
        code_build_move_batches = CodeNode(
            name="code_build_move_batches",
            code_fn=_build_move_batches,
            inputs={
                "to_move": {code_compare_pages: "to_move"},
                "fetched_pages": {code_fetch_specific_pages: "fetched_pages"},
                "active_pages": {INPUT: "active_pages"},
                "bot_documents": {mongo_get_bot_documents: "data"},
                "bot_id": {INPUT: "bot_id"},
            },
            return_keys=[
                "active_move_batch: list",
                "inactive_move_batch: list",
                "sql_move_batch: list",
                "moved_count: int",
                "move_deleted_page_ids: list",
                "successful_move_page_ids: list",
            ],
        )

        code_build_deleted_page_cleanup_inputs.inputs = {
            "primary_page_ids": {code_filter_deleted_pages: "deleted_page_ids"},
            "additional_page_ids": {code_build_move_batches: "move_deleted_page_ids"},
            "bot_id": {INPUT: "bot_id"},
        }

        with ForLoopNode(
            name="loop_move_active_pages",
            max_concurrency=10,
            inputs={"batch_data": {code_build_move_batches: "active_move_batch"}},
        ) as loop_move_active_pages:
            mongo_move_active_page = MongoNode(
                name="mongo_move_active_page",
                resource_key='aicenter-chatbot',
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
                resource_key='aicenter-chatbot',
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
                resource_key='anapp',
                operation=SQLOperation.EXECUTE,
                inputs={
                    "query": {INPUT: "sql_query"},
                    "params": {INPUT: "sql_params"},
                },
            )
            START >> sql_move_page >> END
        
        # Step 12: Build updated pages list
        code_build_updated_list = CodeNode(
            name="code_build_updated_list",
            code_fn=_build_updated_pages,
            return_keys=["updated_pages: list"],
            inputs={
                "insert_pages": {code_compare_pages: "to_insert"},
                "update_pages": {code_compare_pages: "to_update"},
                "metadata_update_pages": {code_compare_pages: "to_metadata_update"},
                "move_items": {code_compare_pages: "to_move"},
                "fetched_pages": {code_fetch_specific_pages: "fetched_pages"},
            },
        )

        code_build_partial_mode_stats = CodeNode(
            name="code_build_partial_mode_stats",
            code_fn=build_partial_mode_stats,
            return_keys=["total_processed: int", "total_updated: int", "total_deleted: int"],
            inputs={
                "fetched_pages": {code_fetch_specific_pages: "fetched_pages"},
                "inserted_count": {code_process_inserts: "inserted_count"},
                "updated_count": {code_process_updates: "updated_count"},
                "metadata_updated_count": {code_process_metadata_updates: "metadata_updated_count"},
                "deleted_count": {code_filter_deleted_pages: "deleted_count"},
            },
        )

        code_build_unchanged_status_batches = CodeNode(
            name="code_build_unchanged_status_batches",
            code_fn=_build_unchanged_status_batches,
            inputs={
                "page_ids": {code_compare_pages: "pages_no_change"},
                "bot_id": {INPUT: "bot_id"},
            },
            return_keys=["batch_data: list"],
        )

        with ForLoopNode(
            name="loop_update_unchanged_status",
            max_concurrency=10,
            inputs={
                "batch_data": {
                    code_build_unchanged_status_batches: "batch_data"
                }
            },
        ) as loop_update_unchanged_status:
            mongo_update_unchanged_status = MongoNode(
                name="mongo_update_unchanged_status",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {INPUT: "mongo_filter"},
                    "update": {INPUT: "mongo_update"},
                    "upsert": False,
                },
            )

            START >> mongo_update_unchanged_status >> END

        code_build_metadata_completed_status_batches = CodeNode(
            name="code_build_metadata_completed_status_batches",
            code_fn=_build_metadata_completed_status_batches,
            inputs={
                "pages": {code_compare_pages: "to_metadata_update"},
                "bot_id": {INPUT: "bot_id"},
            },
            return_keys=["batch_data: list"],
        )

        with ForLoopNode(
            name="loop_update_metadata_completed_status",
            max_concurrency=10,
            inputs={
                "batch_data": {
                    code_build_metadata_completed_status_batches: "batch_data"
                }
            },
        ) as loop_update_metadata_completed_status:
            mongo_update_metadata_completed_status = MongoNode(
                name="mongo_update_metadata_completed_status",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {INPUT: "mongo_filter"},
                    "update": {INPUT: "mongo_update"},
                    "upsert": False,
                },
            )

            START >> mongo_update_metadata_completed_status >> END

        code_build_move_completed_status_batches = CodeNode(
            name="code_build_move_completed_status_batches",
            code_fn=_build_move_completed_status_batches,
            inputs={
                "successful_page_ids": {code_build_move_batches: "successful_move_page_ids"},
                "move_only_page_ids": {code_compare_pages: "move_only_page_ids"},
                "bot_id": {INPUT: "bot_id"},
            },
            return_keys=["batch_data: list"],
        )

        with ForLoopNode(
            name="loop_update_move_completed_status",
            max_concurrency=10,
            inputs={
                "batch_data": {code_build_move_completed_status_batches: "batch_data"}
            },
        ) as loop_update_move_completed_status:
            mongo_update_move_completed_status = MongoNode(
                name="mongo_update_move_completed_status",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {INPUT: "mongo_filter"},
                    "update": {INPUT: "mongo_update"},
                    "upsert": False,
                },
            )

            START >> mongo_update_move_completed_status >> END

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
                "current_pages_no_change": {code_compare_pages: "pages_no_change"},
                "current_total_processed": {code_build_partial_mode_stats: "total_processed"},
                "current_total_updated": {code_build_partial_mode_stats: "total_updated"},
                "current_total_deleted": {code_build_partial_mode_stats: "total_deleted"},
            },
            outputs={
                "updated_pages": OUTPUT,
                "pages_no_change": OUTPUT,
                "total_processed": OUTPUT,
                "total_updated": OUTPUT,
                "total_deleted": OUTPUT,
            },
        )
        
        # Build workflow graph
        START >> code_fetch_specific_pages
        code_fetch_specific_pages >> code_filter_deleted_pages
        code_build_deleted_page_cleanup_inputs >> [sql_mark_deleted_pages, mongo_mark_deleted_documents]
        sql_mark_deleted_pages >> mongo_mark_deleted_documents >> graph_cleanup_deleted_confluence_data
        code_fetch_specific_pages >> code_build_existing_pages_params
        code_build_existing_pages_params >> sql_get_existing_pages
        START >> code_build_partial_error_retry_query >> mongo_find_partial_error_retry_documents
        [sql_get_existing_pages, mongo_find_partial_error_retry_documents] >> code_compare_pages
        code_compare_pages >> code_build_unchanged_status_batches >> loop_update_unchanged_status
        code_compare_pages >> [code_process_inserts, code_process_updates, code_process_metadata_updates, code_build_move_batches]
        [loop_insert_pages, loop_update_pages, code_compare_pages] >> code_build_bot_documents_selector
        code_build_bot_documents_selector >> mongo_get_bot_documents
        mongo_get_bot_documents >> code_build_move_batches
        code_build_move_batches >> [loop_move_active_pages, loop_move_inactive_pages]
        [loop_move_active_pages, loop_move_inactive_pages] >> loop_move_sql_updates
        loop_move_sql_updates >> code_build_move_completed_status_batches >> loop_update_move_completed_status
        [code_filter_deleted_pages, code_build_move_batches] >> code_build_deleted_page_cleanup_inputs
        code_process_inserts >> loop_insert_pages >> code_build_updated_list
        code_process_updates >> loop_update_pages >> code_build_updated_list
        code_process_metadata_updates >> loop_metadata_updates >> code_build_updated_list
        [loop_metadata_updates, loop_move_sql_updates] >> code_build_metadata_completed_status_batches
        code_build_metadata_completed_status_batches >> loop_update_metadata_completed_status
        loop_move_active_pages >> code_build_updated_list
        loop_move_inactive_pages >> code_build_updated_list
        loop_move_sql_updates >> code_build_updated_list
        code_compare_pages >> code_build_updated_list
        code_compare_pages >> code_build_partial_mode_stats
        code_process_inserts >> code_build_partial_mode_stats
        code_process_updates >> code_build_partial_mode_stats
        code_process_metadata_updates >> code_build_partial_mode_stats
        code_filter_deleted_pages >> code_build_partial_mode_stats
        graph_cleanup_deleted_confluence_data >> code_build_partial_mode_stats
        [
            code_build_updated_list,
            code_build_partial_mode_stats,
            loop_update_unchanged_status,
            loop_update_metadata_completed_status,
            loop_update_move_completed_status,
        ] >> code_package_mode_output >> END
    
    graph_partial_mode.build()
    return graph_partial_mode
