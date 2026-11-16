"""
Main workflow for Confluence sync using BeeFlow.

This module provides complete sync workflow using BeeFlow's service nodes.
"""

from uuid import UUID
from typing import Any

from beeflow.workflow import WorkflowEngine
from beeflow.nodes import START, END, INPUT, OUTPUT, BranchNode, MongoNode, KafkaNode, CodeNode, S3Node
from beeflow.nodes.flow.for_loop_node import ForLoopNode
from beeflow.nodes.base_node import BaseNode
from beegen.configs.storage.mongo_config import MongoOperation
from beegen.configs.event_streaming.kafka_config import KafkaOperation
from beegen.configs.storage.s3_config import S3Operation

from confluence_workflow.utils.logger import get_logger
from confluence_workflow.functions.auto_mode_processor import _extract_active_page_ids
from confluence_workflow.functions.workflow_helpers import (
    build_bot_selector,
    build_page_document_query,
    select_mode_output,
    validate_stage_context,
    select_finalize_context,
    select_pages_for_chunk_processing,
    download_page_from_confluence,
    build_chunk_dispatch_payload,
    build_chunk_dispatch_document_update,
    finalize_chunk_job_ready_item,
    build_chunk_job_error_item,
    build_chunk_job_message,
    validate_chunk_job_produced,
    build_sync_error_document_update,
    cleanup_page_batch_temp_files,
    forward_sync_context,
)
from confluence_workflow.graphs import (
    build_initialize_job_graph,
    build_finalize_job_graph,
    build_resolve_parent_child_graph,
    build_calculate_level_graph,
    build_update_sync_at_graph,
    build_first_mode_graph,
    build_partial_mode_graph,
    build_auto_mode_graph,
)

logger = get_logger('workflow')


_ORIGINAL_TRACE_DATA = BaseNode.trace_data


def _normalize_trace_value(value: Any) -> Any:
    """Convert trace payload values to verify_data-compatible primitives."""
    if isinstance(value, UUID):
        return str(value)

    value_type = type(value)
    if value_type.__name__ == "ObjectId":
        return str(value)

    if isinstance(value, dict):
        return {
            _normalize_trace_value(key): _normalize_trace_value(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_normalize_trace_value(item) for item in value]

    if isinstance(value, tuple):
        return tuple(_normalize_trace_value(item) for item in value)

    if isinstance(value, set):
        return {_normalize_trace_value(item) for item in value}

    if isinstance(value, frozenset):
        return frozenset(_normalize_trace_value(item) for item in value)

    return value


def _patched_trace_data(self, state, context_id, size_threshold_bytes: int = 100000):
    return _normalize_trace_value(
        _ORIGINAL_TRACE_DATA(self, state, context_id, size_threshold_bytes)
    )


BaseNode.trace_data = _patched_trace_data


def build_confluence_sync_workflow(config):
    """
    Build complete Confluence sync workflow using BeeFlow.
    
    This workflow orchestrates entire sync process by calling sub-graphs:
    1. Initialize sync job
    2. Route based on sync mode
    3. Fetch and process pages using mode-specific graphs
    4. Resolve parent-child relationships
    5. Calculate document levels
    6. Update sync timestamps
    7. Send page-fetch requests to Kafka
    8. Finalize job
    
    Args:
        config: Workflow configuration
        
    Returns:
        Compiled workflow instance
    """
    with WorkflowEngine(
        name="wf_confluence_sync",
        description="Confluence to PostgreSQL sync workflow",
    ) as wf_confluence_sync:
        
        # Build sub-graphs
        graph_initialize_job = build_initialize_job_graph(config)
        graph_finalize_job = build_finalize_job_graph(config)
        graph_resolve_parent_child = build_resolve_parent_child_graph(config)
        graph_calculate_level = build_calculate_level_graph(config)
        graph_update_sync_at = build_update_sync_at_graph(config)
        graph_first_mode = build_first_mode_graph(config)
        graph_partial_mode = build_partial_mode_graph(config)
        graph_auto_mode = build_auto_mode_graph(config)

        code_build_partial_active_query = CodeNode(
            name="code_build_partial_active_query",
            code_fn=build_bot_selector,
            return_keys=["query: dict"],
            inputs={"bot_id": {INPUT: "bot_id"}},
        )

        mongo_get_partial_active_pages = MongoNode(
            name="mongo_get_partial_active_pages",
            resource_key='aicenter-chatbot',
            operation=MongoOperation.FIND,
            inputs={
                "collection_name": "documents",
                "query": {code_build_partial_active_query: "query"},
                "projection": {"external_id": 1, "_id": 0},
            },
        )

        code_extract_partial_active_page_ids = CodeNode(
            name="code_extract_partial_active_page_ids",
            code_fn=_extract_active_page_ids,
            return_keys=["active_page_ids: list", "has_active_pages: bool"],
            inputs={"active_pages": {mongo_get_partial_active_pages: "data"}},
        )

        graph_first_mode.inputs = {
            "bot_id": {INPUT: "bot_id"},
            "page_ids": {INPUT: "page_ids"},
            "confluence_config": {INPUT: "confluence_config"},
            "batch_size": {INPUT: "batch_size"},
        }

        graph_partial_mode.inputs = {
            "bot_id": {INPUT: "bot_id"},
            "page_ids": {INPUT: "page_ids"},
            "limit": {INPUT: "limit"},
            "confluence_config": {INPUT: "confluence_config"},
            "active_pages": {code_extract_partial_active_page_ids: "active_page_ids"},
        }

        graph_auto_mode.inputs = {
            "bot_id": {INPUT: "bot_id"},
            "page_ids": {INPUT: "page_ids"},
            "batch_size": {INPUT: "batch_size"},
            "confluence_config": {INPUT: "confluence_config"},
        }

        code_select_mode_output = CodeNode(
            name="code_select_mode_output",
            code_fn=select_mode_output,
            return_keys=[
                "job_id: Any",
                "bot_id: Any",
                "sync_mode: str",
                "page_ids: list",
                "confluence_config: dict",
                "updated_pages: list",
                "pages_no_change: list",
                "total_processed: int",
                "total_updated: int",
                "total_deleted: int",
                "status: str",
                "error: str",
                "should_continue: bool",
            ],
            inputs={
                "current_sync_mode": {INPUT: "sync_mode"},
                "current_job_id": {graph_initialize_job: "job_id"},
                "current_bot_id": {INPUT: "bot_id"},
                "current_page_ids": {INPUT: "page_ids"},
                "current_confluence_config": {INPUT: "confluence_config"},
                "first_updated_pages": {graph_first_mode: "updated_pages"},
                "first_pages_no_change": {graph_first_mode: "pages_no_change"},
                "first_total_processed": {graph_first_mode: "total_processed"},
                "first_total_updated": {graph_first_mode: "total_updated"},
                "first_total_deleted": {graph_first_mode: "total_deleted"},
                "partial_updated_pages": {graph_partial_mode: "updated_pages"},
                "partial_pages_no_change": {graph_partial_mode: "pages_no_change"},
                "partial_total_processed": {graph_partial_mode: "total_processed"},
                "partial_total_updated": {graph_partial_mode: "total_updated"},
                "partial_total_deleted": {graph_partial_mode: "total_deleted"},
                "auto_updated_pages": {graph_auto_mode: "updated_pages"},
                "auto_pages_no_change": {graph_auto_mode: "pages_no_change"},
                "auto_total_processed": {graph_auto_mode: "total_processed"},
                "auto_total_updated": {graph_auto_mode: "total_updated"},
                "auto_total_deleted": {graph_auto_mode: "total_deleted"},
            },
        )

        branch_after_mode = BranchNode(
            name="branch_after_mode",
            cases={"should_continue == True": "graph_resolve_parent_child"},
            inputs={"should_continue": {code_select_mode_output: "should_continue"}},
            default="code_select_finalize_context",
        )

        graph_resolve_parent_child.inputs = {
            "current_job_id": {code_select_mode_output: "job_id"},
            "current_bot_id": {code_select_mode_output: "bot_id"},
            "current_sync_mode": {code_select_mode_output: "sync_mode"},
            "current_page_ids": {code_select_mode_output: "page_ids"},
            "current_updated_pages": {code_select_mode_output: "updated_pages"},
            "current_total_processed": {code_select_mode_output: "total_processed"},
            "current_total_updated": {code_select_mode_output: "total_updated"},
            "current_total_deleted": {code_select_mode_output: "total_deleted"},
            "current_status": {code_select_mode_output: "status"},
            "current_error": {code_select_mode_output: "error"},
        }

        code_validate_resolve_context = CodeNode(
            name="code_validate_resolve_context",
            code_fn=validate_stage_context,
            return_keys=[
                "job_id: Any",
                "bot_id: Any",
                "sync_mode: str",
                "page_ids: list",
                "updated_pages: list",
                "total_processed: int",
                "total_updated: int",
                "total_deleted: int",
                "status: str",
                "error: str",
                "should_continue: bool",
            ],
            inputs={
                "stage_name": "graph_resolve_parent_child",
                "current_job_id": {graph_resolve_parent_child: "job_id"},
                "current_bot_id": {graph_resolve_parent_child: "bot_id"},
                "current_sync_mode": {graph_resolve_parent_child: "sync_mode"},
                "current_page_ids": {graph_resolve_parent_child: "page_ids"},
                "current_updated_pages": {graph_resolve_parent_child: "updated_pages"},
                "current_total_processed": {graph_resolve_parent_child: "total_processed"},
                "current_total_updated": {graph_resolve_parent_child: "total_updated"},
                "current_total_deleted": {graph_resolve_parent_child: "total_deleted"},
                "current_status": {graph_resolve_parent_child: "status"},
                "current_error": {graph_resolve_parent_child: "error"},
                "fallback_job_id": {code_select_mode_output: "job_id"},
                "fallback_bot_id": {code_select_mode_output: "bot_id"},
                "fallback_sync_mode": {code_select_mode_output: "sync_mode"},
                "fallback_page_ids": {code_select_mode_output: "page_ids"},
                "fallback_updated_pages": {code_select_mode_output: "updated_pages"},
                "fallback_total_processed": {code_select_mode_output: "total_processed"},
                "fallback_total_updated": {code_select_mode_output: "total_updated"},
                "fallback_total_deleted": {code_select_mode_output: "total_deleted"},
                "fallback_status": {code_select_mode_output: "status"},
                "fallback_error": {code_select_mode_output: "error"},
            },
        )

        branch_after_resolve = BranchNode(
            name="branch_after_resolve",
            cases={"should_continue == True": "graph_calculate_level"},
            inputs={"should_continue": {code_validate_resolve_context: "should_continue"}},
            default="code_select_finalize_context",
        )

        graph_calculate_level.inputs = {
            "current_job_id": {code_validate_resolve_context: "job_id"},
            "current_bot_id": {code_validate_resolve_context: "bot_id"},
            "current_sync_mode": {code_validate_resolve_context: "sync_mode"},
            "current_page_ids": {code_validate_resolve_context: "page_ids"},
            "current_updated_pages": {code_validate_resolve_context: "updated_pages"},
            "current_total_processed": {code_validate_resolve_context: "total_processed"},
            "current_total_updated": {code_validate_resolve_context: "total_updated"},
            "current_total_deleted": {code_validate_resolve_context: "total_deleted"},
            "current_status": {code_validate_resolve_context: "status"},
            "current_error": {code_validate_resolve_context: "error"},
        }

        code_validate_calculate_context = CodeNode(
            name="code_validate_calculate_context",
            code_fn=validate_stage_context,
            return_keys=[
                "job_id: Any",
                "bot_id: Any",
                "sync_mode: str",
                "page_ids: list",
                "updated_pages: list",
                "total_processed: int",
                "total_updated: int",
                "total_deleted: int",
                "status: str",
                "error: str",
                "should_continue: bool",
            ],
            inputs={
                "stage_name": "graph_calculate_level",
                "current_job_id": {graph_calculate_level: "job_id"},
                "current_bot_id": {graph_calculate_level: "bot_id"},
                "current_sync_mode": {graph_calculate_level: "sync_mode"},
                "current_page_ids": {graph_calculate_level: "page_ids"},
                "current_updated_pages": {graph_calculate_level: "updated_pages"},
                "current_total_processed": {graph_calculate_level: "total_processed"},
                "current_total_updated": {graph_calculate_level: "total_updated"},
                "current_total_deleted": {graph_calculate_level: "total_deleted"},
                "current_status": {graph_calculate_level: "status"},
                "current_error": {graph_calculate_level: "error"},
                "fallback_job_id": {code_validate_resolve_context: "job_id"},
                "fallback_bot_id": {code_validate_resolve_context: "bot_id"},
                "fallback_sync_mode": {code_validate_resolve_context: "sync_mode"},
                "fallback_page_ids": {code_validate_resolve_context: "page_ids"},
                "fallback_updated_pages": {code_validate_resolve_context: "updated_pages"},
                "fallback_total_processed": {code_validate_resolve_context: "total_processed"},
                "fallback_total_updated": {code_validate_resolve_context: "total_updated"},
                "fallback_total_deleted": {code_validate_resolve_context: "total_deleted"},
                "fallback_status": {code_validate_resolve_context: "status"},
                "fallback_error": {code_validate_resolve_context: "error"},
            },
        )

        branch_after_calculate = BranchNode(
            name="branch_after_calculate",
            cases={"should_continue == True": "graph_update_sync_at"},
            inputs={"should_continue": {code_validate_calculate_context: "should_continue"}},
            default="code_select_finalize_context",
        )

        graph_update_sync_at.inputs = {
            "current_job_id": {code_validate_calculate_context: "job_id"},
            "current_bot_id": {code_validate_calculate_context: "bot_id"},
            "current_sync_mode": {code_validate_calculate_context: "sync_mode"},
            "current_page_ids": {code_validate_calculate_context: "page_ids"},
            "current_updated_pages": {code_validate_calculate_context: "updated_pages"},
            "current_total_processed": {code_validate_calculate_context: "total_processed"},
            "current_total_updated": {code_validate_calculate_context: "total_updated"},
            "current_total_deleted": {code_validate_calculate_context: "total_deleted"},
            "current_status": {code_validate_calculate_context: "status"},
            "current_error": {code_validate_calculate_context: "error"},
        }

        code_validate_sync_at_context = CodeNode(
            name="code_validate_sync_at_context",
            code_fn=validate_stage_context,
            return_keys=[
                "job_id: Any",
                "bot_id: Any",
                "sync_mode: str",
                "page_ids: list",
                "updated_pages: list",
                "total_processed: int",
                "total_updated: int",
                "total_deleted: int",
                "status: str",
                "error: str",
                "should_continue: bool",
            ],
            inputs={
                "stage_name": "graph_update_sync_at",
                "current_job_id": {graph_update_sync_at: "job_id"},
                "current_bot_id": {graph_update_sync_at: "bot_id"},
                "current_sync_mode": {graph_update_sync_at: "sync_mode"},
                "current_page_ids": {graph_update_sync_at: "page_ids"},
                "current_updated_pages": {graph_update_sync_at: "updated_pages"},
                "current_total_processed": {graph_update_sync_at: "total_processed"},
                "current_total_updated": {graph_update_sync_at: "total_updated"},
                "current_total_deleted": {graph_update_sync_at: "total_deleted"},
                "current_status": {graph_update_sync_at: "status"},
                "current_error": {graph_update_sync_at: "error"},
                "fallback_job_id": {code_validate_calculate_context: "job_id"},
                "fallback_bot_id": {code_validate_calculate_context: "bot_id"},
                "fallback_sync_mode": {code_validate_calculate_context: "sync_mode"},
                "fallback_page_ids": {code_validate_calculate_context: "page_ids"},
                "fallback_updated_pages": {code_validate_calculate_context: "updated_pages"},
                "fallback_total_processed": {code_validate_calculate_context: "total_processed"},
                "fallback_total_updated": {code_validate_calculate_context: "total_updated"},
                "fallback_total_deleted": {code_validate_calculate_context: "total_deleted"},
                "fallback_status": {code_validate_calculate_context: "status"},
                "fallback_error": {code_validate_calculate_context: "error"},
            },
        )

        branch_after_sync_at = BranchNode(
            name="branch_after_sync_at",
            cases={"should_continue == True": "code_select_pages_for_chunk_processing"},
            inputs={"should_continue": {code_validate_sync_at_context: "should_continue"}},
            default="code_select_finalize_context",
        )

        code_select_pages_for_chunk_processing = CodeNode(
            name="code_select_pages_for_chunk_processing",
            code_fn=select_pages_for_chunk_processing,
            inputs={
                "confluence_config": {code_select_mode_output: "confluence_config"},
                "bot_id": {code_validate_sync_at_context: "bot_id"},
                "updated_pages": {code_validate_sync_at_context: "updated_pages"},
            },
            return_keys=[
                "pages_for_chunk_processing: list",
                "has_pages_for_chunk_processing: bool",
            ],
        )

        branch_after_select_pages_for_chunk_processing = BranchNode(
            name="branch_after_select_pages_for_chunk_processing",
            cases={"has_pages_for_chunk_processing == True": "page_loop"},
            inputs={
                "has_pages_for_chunk_processing": {
                    code_select_pages_for_chunk_processing: "has_pages_for_chunk_processing",
                }
            },
            default="code_validate_chunk_processing_context",
        )

        with ForLoopNode(
            name="page_loop",
            description="Iterate through pages need to chunk",
            inputs={"batch_data": {code_select_pages_for_chunk_processing: "pages_for_chunk_processing"}},
            max_concurrency=8,
        ) as page_loop:
            code_download_page_from_confluence = CodeNode(
                name="code_download_page_from_confluence",
                code_fn=download_page_from_confluence,
                inputs={
                    "confluence_config": {INPUT: "confluence_config"},
                    "input_page_id": {INPUT: "page_id"},
                    "input_bot_id": {INPUT: "bot_id"},
                    "input_title": {INPUT: "title"},
                    "input_version": {INPUT: "version"},
                    "input_content": {INPUT: "page_content"},
                    "input_source_link": {INPUT: "source_link"},
                    "input_updated_by": {INPUT: "updated_by"},
                    "input_sync_status": {INPUT: "sync_status"},
                },
                return_keys=[
                    "page_id: str",
                    "bot_id: Any",
                    "title: Any",
                    "version: Any",
                    "content: Any",
                    "source_link: Any",
                    "updated_by: Any",
                    "sync_status: Any",
                    "file_path: Any",
                    "has_downloaded_page: bool",
                    "has_download_error: bool",
                    "download_error_message: str",
                ],
            )

            branch_after_download_page = BranchNode(
                name="branch_after_download_page",
                cases={
                    "has_downloaded_page == True": "code_build_chunk_dispatch_document_query",
                    "has_download_error == True": "code_build_download_error_page_document_query",
                },
                inputs={
                    "has_downloaded_page": {code_download_page_from_confluence: "has_downloaded_page"},
                    "has_download_error": {code_download_page_from_confluence: "has_download_error"},
                },
                default=END,
            )

            code_build_chunk_dispatch_document_query = CodeNode(
                name="code_build_chunk_dispatch_document_query",
                code_fn=build_page_document_query,
                return_keys=["query: dict"],
                inputs={
                    "bot_id": {code_download_page_from_confluence: "bot_id"},
                    "page_id": {code_download_page_from_confluence: "page_id"},
                },
            )

            mongo_find_chunk_dispatch_document = MongoNode(
                name="mongo_find_chunk_dispatch_document",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.FIND_ONE,
                inputs={
                    "collection_name": "documents",
                    "query": {code_build_chunk_dispatch_document_query: "query"},
                    "projection": {
                        "_id": 1,
                        "bot_id": 1,
                        "doc_name": 1,
                        "source_link": 1,
                    },
                },
            )

            code_build_chunk_dispatch_payload = CodeNode(
                name="code_build_chunk_dispatch_payload",
                code_fn=build_chunk_dispatch_payload,
                inputs={
                    "document": {mongo_find_chunk_dispatch_document: "data"},
                    "bot_id": {code_download_page_from_confluence: "bot_id"},
                    "version": {code_download_page_from_confluence: "version"},
                    "file_path": {code_download_page_from_confluence: "file_path"},
                },
                return_keys=[
                    "upload_file_path: str",
                    "upload_bucket: str",
                    "upload_object_key: str",
                    "upload_content_type: str",
                    "chunk_job_item: dict",
                ],
            )

            s3_upload_confluence_html = S3Node(
                name="s3_upload_confluence_html",
                resource_key="ai-nlp-text",
                operation=S3Operation.UPLOAD_FILE,
                inputs={
                    "bucket": {code_build_chunk_dispatch_payload: "upload_bucket"},
                    "local_file_path": {code_build_chunk_dispatch_payload: "upload_file_path"},
                    "key": {code_build_chunk_dispatch_payload: "upload_object_key"},
                    "content_type": {code_build_chunk_dispatch_payload: "upload_content_type"},
                },
            )

            branch_after_confluence_html_upload = BranchNode(
                name="branch_after_confluence_html_upload",
                cases={"upload_status == 'success'": "code_build_chunk_dispatch_document_update"},
                inputs={"upload_status": {s3_upload_confluence_html: "status"}},
                default="code_build_chunk_dispatch_upload_error_update",
            )

            code_build_chunk_dispatch_document_update = CodeNode(
                name="code_build_chunk_dispatch_document_update",
                code_fn=build_chunk_dispatch_document_update,
                return_keys=["update: dict"],
            )

            mongo_update_chunk_dispatch_document = MongoNode(
                name="mongo_update_chunk_dispatch_document",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {code_build_chunk_dispatch_document_query: "query"},
                    "update": {code_build_chunk_dispatch_document_update: "update"},
                },
            )

            code_finalize_chunk_job_ready_item = CodeNode(
                name="code_finalize_chunk_job_ready_item",
                code_fn=finalize_chunk_job_ready_item,
                inputs={
                    "prepared_item": {code_build_chunk_dispatch_payload: "chunk_job_item"},
                    "document_update_status": {mongo_update_chunk_dispatch_document: "status"},
                },
                return_keys=["chunk_job_item: dict"],
                outputs={"chunk_job_item": OUTPUT["chunk_job_item"]},
            )

            code_build_chunk_dispatch_upload_error_update = CodeNode(
                name="code_build_chunk_dispatch_upload_error_update",
                code_fn=build_sync_error_document_update,
                return_keys=["update: dict"],
                inputs={"error_message": "Could not upload Confluence HTML to S3"},
            )

            mongo_update_chunk_dispatch_upload_error = MongoNode(
                name="mongo_update_chunk_dispatch_upload_error",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {code_build_chunk_dispatch_document_query: "query"},
                    "update": {code_build_chunk_dispatch_upload_error_update: "update"},
                },
            )

            code_build_chunk_dispatch_upload_error_item = CodeNode(
                name="code_build_chunk_dispatch_upload_error_item",
                code_fn=build_chunk_job_error_item,
                inputs={
                    "document": {mongo_find_chunk_dispatch_document: "data"},
                    "version": {code_download_page_from_confluence: "version"},
                    "error_message": "Could not upload Confluence HTML to S3",
                    "document_update_status": {
                        mongo_update_chunk_dispatch_upload_error: "status"
                    },
                },
                return_keys=["chunk_job_item: dict"],
                outputs={"chunk_job_item": OUTPUT["chunk_job_item"]},
            )

            code_build_download_error_page_document_query = CodeNode(
                name="code_build_download_error_page_document_query",
                code_fn=build_page_document_query,
                return_keys=["query: dict"],
                inputs={
                    "bot_id": {code_download_page_from_confluence: "bot_id"},
                    "page_id": {code_download_page_from_confluence: "page_id"},
                },
            )

            code_build_download_error_document_update = CodeNode(
                name="code_build_download_error_document_update",
                code_fn=build_sync_error_document_update,
                return_keys=["update: dict"],
                inputs={
                    "error_message": {code_download_page_from_confluence: "download_error_message"},
                },
            )

            mongo_find_download_error_page_document = MongoNode(
                name="mongo_find_download_error_page_document",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.FIND_ONE,
                inputs={
                    "collection_name": "documents",
                    "query": {code_build_download_error_page_document_query: "query"},
                    "projection": {
                        "_id": 1,
                        "bot_id": 1,
                        "doc_name": 1,
                        "source_link": 1,
                    },
                },
            )

            mongo_update_document_download_error = MongoNode(
                name="mongo_update_document_download_error",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {code_build_download_error_page_document_query: "query"},
                    "update": {code_build_download_error_document_update: "update"},
                },
            )

            branch_after_update_document_download_error = BranchNode(
                name="branch_after_update_document_download_error",
                cases={"update_status == 'success'": "code_build_download_error_chunk_job_item"},
                inputs={"update_status": {mongo_update_document_download_error: "status"}},
                default=END,
            )

            code_build_download_error_chunk_job_item = CodeNode(
                name="code_build_download_error_chunk_job_item",
                code_fn=build_chunk_job_error_item,
                return_keys=["chunk_job_item: dict"],
                inputs={
                    "document": {mongo_find_download_error_page_document: "data"},
                    "version": {code_download_page_from_confluence: "version"},
                    "error_message": {
                        code_download_page_from_confluence: "download_error_message"
                    },
                    "document_update_status": {mongo_update_document_download_error: "status"},
                },
                outputs={"chunk_job_item": OUTPUT["chunk_job_item"]},
            )

            START >> code_download_page_from_confluence >> branch_after_download_page
            branch_after_download_page >> [
                code_build_chunk_dispatch_document_query,
                code_build_download_error_page_document_query,
                END,
            ]
            code_build_chunk_dispatch_document_query >> mongo_find_chunk_dispatch_document
            mongo_find_chunk_dispatch_document >> code_build_chunk_dispatch_payload
            code_build_chunk_dispatch_payload >> s3_upload_confluence_html
            s3_upload_confluence_html >> branch_after_confluence_html_upload
            branch_after_confluence_html_upload >> [
                code_build_chunk_dispatch_document_update,
                code_build_chunk_dispatch_upload_error_update,
            ]
            code_build_chunk_dispatch_document_update >> mongo_update_chunk_dispatch_document
            mongo_update_chunk_dispatch_document >> code_finalize_chunk_job_ready_item >> END
            code_build_chunk_dispatch_upload_error_update >> mongo_update_chunk_dispatch_upload_error
            mongo_update_chunk_dispatch_upload_error >> code_build_chunk_dispatch_upload_error_item >> END
            code_build_download_error_page_document_query >> [
                mongo_find_download_error_page_document,
                code_build_download_error_document_update,
            ]
            code_build_download_error_document_update >> mongo_update_document_download_error
            mongo_find_download_error_page_document >> branch_after_update_document_download_error
            mongo_update_document_download_error >> branch_after_update_document_download_error
            branch_after_update_document_download_error >> [code_build_download_error_chunk_job_item, END]
            code_build_download_error_chunk_job_item >> END

        code_build_chunk_job_message = CodeNode(
            name="code_build_chunk_job_message",
            code_fn=build_chunk_job_message,
            inputs={
                "current_job_id": {code_validate_sync_at_context: "job_id"},
                "current_bot_id": {code_validate_sync_at_context: "bot_id"},
                "page_results": {page_loop: "batch_result"},
            },
            return_keys=["chunk_job_key: str", "chunk_job_value: dict"],
        )

        kafka_send_chunk_job = KafkaNode(
            name="kafka_send_chunk_job",
            resource_key="aicenter-cua",
            operation=KafkaOperation.PRODUCE,
            inputs={
                "topic": config.kafka_topic,
                "key": {code_build_chunk_job_message: "chunk_job_key"},
                "value": {code_build_chunk_job_message: "chunk_job_value"},
            },
        )

        code_validate_chunk_job_produced = CodeNode(
            name="code_validate_chunk_job_produced",
            code_fn=validate_chunk_job_produced,
            inputs={"produce_status": {kafka_send_chunk_job: "status"}},
            return_keys=["chunk_job_produced: bool"],
        )

        code_cleanup_page_batch_temp_files = CodeNode(
            name="code_cleanup_page_batch_temp_files",
            code_fn=cleanup_page_batch_temp_files,
            return_keys=["deleted_temp_paths: int"],
            inputs={
                "pages_for_chunk_processing": {
                    code_select_pages_for_chunk_processing: "pages_for_chunk_processing",
                },
                "chunk_job_produced": {
                    code_validate_chunk_job_produced: "chunk_job_produced",
                },
            },
        )

        code_validate_chunk_processing_context = CodeNode(
            name="code_validate_chunk_processing_context",
            code_fn=forward_sync_context,
            return_keys=[
                "job_id: Any",
                "bot_id: Any",
                "sync_mode: str",
                "page_ids: list",
                "updated_pages: list",
                "total_processed: int",
                "total_updated: int",
                "total_deleted: int",
                "status: str",
                "error: str",
            ],
            inputs={
                "current_job_id": {code_validate_sync_at_context: "job_id"},
                "current_bot_id": {code_validate_sync_at_context: "bot_id"},
                "current_sync_mode": {code_validate_sync_at_context: "sync_mode"},
                "current_page_ids": {code_validate_sync_at_context: "page_ids"},
                "current_updated_pages": {code_validate_sync_at_context: "updated_pages"},
                "current_total_processed": {code_validate_sync_at_context: "total_processed"},
                "current_total_updated": {code_validate_sync_at_context: "total_updated"},
                "current_total_deleted": {code_validate_sync_at_context: "total_deleted"},
                "current_status": {code_validate_sync_at_context: "status"},
                "current_error": {code_validate_sync_at_context: "error"},
            },
        )

        code_select_finalize_context = CodeNode(
            name="code_select_finalize_context",
            code_fn=select_finalize_context,
            return_keys=[
                "job_id: Any",
                "status: str",
                "total_processed: int",
                "total_updated: int",
                "total_deleted: int",
                "error: str",
                "updated_pages: list",
            ],
            inputs={
                "mode_job_id": {code_select_mode_output: "job_id"},
                "mode_status": {code_select_mode_output: "status"},
                "mode_total_processed": {code_select_mode_output: "total_processed"},
                "mode_total_updated": {code_select_mode_output: "total_updated"},
                "mode_total_deleted": {code_select_mode_output: "total_deleted"},
                "mode_error": {code_select_mode_output: "error"},
                "mode_updated_pages": {code_select_mode_output: "updated_pages"},
                "resolve_job_id": {code_validate_resolve_context: "job_id"},
                "resolve_status": {code_validate_resolve_context: "status"},
                "resolve_total_processed": {code_validate_resolve_context: "total_processed"},
                "resolve_total_updated": {code_validate_resolve_context: "total_updated"},
                "resolve_total_deleted": {code_validate_resolve_context: "total_deleted"},
                "resolve_error": {code_validate_resolve_context: "error"},
                "resolve_updated_pages": {code_validate_resolve_context: "updated_pages"},
                "calculate_job_id": {code_validate_calculate_context: "job_id"},
                "calculate_status": {code_validate_calculate_context: "status"},
                "calculate_total_processed": {code_validate_calculate_context: "total_processed"},
                "calculate_total_updated": {code_validate_calculate_context: "total_updated"},
                "calculate_total_deleted": {code_validate_calculate_context: "total_deleted"},
                "calculate_error": {code_validate_calculate_context: "error"},
                "calculate_updated_pages": {code_validate_calculate_context: "updated_pages"},
                "sync_job_id": {code_validate_sync_at_context: "job_id"},
                "sync_status": {code_validate_sync_at_context: "status"},
                "sync_total_processed": {code_validate_sync_at_context: "total_processed"},
                "sync_total_updated": {code_validate_sync_at_context: "total_updated"},
                "sync_total_deleted": {code_validate_sync_at_context: "total_deleted"},
                "sync_error": {code_validate_sync_at_context: "error"},
                "sync_updated_pages": {code_validate_sync_at_context: "updated_pages"},
                "fetch_job_id": {code_validate_chunk_processing_context: "job_id"},
                "fetch_status": {code_validate_chunk_processing_context: "status"},
                "fetch_total_processed": {code_validate_chunk_processing_context: "total_processed"},
                "fetch_total_updated": {code_validate_chunk_processing_context: "total_updated"},
                "fetch_total_deleted": {code_validate_chunk_processing_context: "total_deleted"},
                "fetch_error": {code_validate_chunk_processing_context: "error"},
                "fetch_updated_pages": {code_validate_chunk_processing_context: "updated_pages"},
            },
        )

        graph_finalize_job.inputs = {
            "job_id": {code_select_finalize_context: "job_id"},
            "status": {code_select_finalize_context: "status"},
            "total_processed": {code_select_finalize_context: "total_processed"},
            "total_updated": {code_select_finalize_context: "total_updated"},
            "total_deleted": {code_select_finalize_context: "total_deleted"},
            "error": {code_select_finalize_context: "error"},
            "updated_pages": {code_select_finalize_context: "updated_pages"},
        }
        
        # Step 2: Route based on sync mode
        branch_route_sync_mode = BranchNode(
            name="branch_route_sync_mode",
            cases={
                "sync_mode == 'FIRST'": "graph_first_mode",
                "sync_mode == 'PARTIAL'": "code_build_partial_active_query",
                "sync_mode == 'AUTO'": "graph_auto_mode"
            },
            inputs={"sync_mode": INPUT},
            default="code_build_partial_active_query"
        )

        # Build workflow graph
        START >> graph_initialize_job >> branch_route_sync_mode
        branch_route_sync_mode >> [graph_first_mode, code_build_partial_active_query, graph_auto_mode]
        code_build_partial_active_query >> mongo_get_partial_active_pages
        mongo_get_partial_active_pages >> code_extract_partial_active_page_ids >> graph_partial_mode
        graph_first_mode >> code_select_mode_output
        graph_partial_mode >> code_select_mode_output
        graph_auto_mode >> code_select_mode_output
        code_select_mode_output >> branch_after_mode
        branch_after_mode >> [graph_resolve_parent_child, code_select_finalize_context]
        graph_resolve_parent_child >> code_validate_resolve_context >> branch_after_resolve
        branch_after_resolve >> [graph_calculate_level, code_select_finalize_context]
        graph_calculate_level >> code_validate_calculate_context >> branch_after_calculate
        branch_after_calculate >> [graph_update_sync_at, code_select_finalize_context]
        graph_update_sync_at >> code_validate_sync_at_context >> branch_after_sync_at
        branch_after_sync_at >> [code_select_pages_for_chunk_processing, code_select_finalize_context]
        code_select_pages_for_chunk_processing >> branch_after_select_pages_for_chunk_processing
        branch_after_select_pages_for_chunk_processing >> [page_loop, code_validate_chunk_processing_context]
        page_loop >> code_build_chunk_job_message >> kafka_send_chunk_job
        kafka_send_chunk_job >> code_validate_chunk_job_produced
        code_validate_chunk_job_produced >> code_cleanup_page_batch_temp_files
        code_cleanup_page_batch_temp_files >> code_validate_chunk_processing_context
        code_validate_chunk_processing_context >> code_select_finalize_context
        code_select_finalize_context >> graph_finalize_job >> END

    wf_confluence_sync.compile()
    return wf_confluence_sync
