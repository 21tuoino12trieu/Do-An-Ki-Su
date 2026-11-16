"""Update Sync At Graph."""

from beeflow.nodes import START, END, INPUT, OUTPUT, GraphNode, CodeNode

from confluence_workflow.utils.logger import get_logger
from confluence_workflow.functions.workflow_helpers import update_sync_time, forward_sync_context

logger = get_logger('update_sync_at')


def build_update_sync_at_graph(config):
    """
    Build update sync_at graph using the legacy Mongo sync_time logic.
    """
    with GraphNode(
        name="graph_update_sync_at",
        description="Update sync timestamp for documents",
        inputs={
            "current_job_id": INPUT,
            "current_bot_id": INPUT,
            "current_sync_mode": INPUT,
            "current_page_ids": INPUT,
            "current_updated_pages": INPUT,
            "current_total_processed": INPUT,
            "current_total_updated": INPUT,
            "current_total_deleted": INPUT,
            "current_status": INPUT,
            "current_error": INPUT,
        }
    ) as graph_update_sync_at:

        code_update_sync_time = CodeNode(
            name="code_update_sync_time",
            code_fn=update_sync_time,
            return_keys=["updated_count: int", "skipped: bool"],
            inputs={
                "bot_id": {INPUT: "current_bot_id"},
                "sync_mode": {INPUT: "current_sync_mode"},
                "page_ids": {INPUT: "current_page_ids"},
            },
        )

        code_package_context = CodeNode(
            name="code_package_context",
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
                "current_job_id": {INPUT: "current_job_id"},
                "current_bot_id": {INPUT: "current_bot_id"},
                "current_sync_mode": {INPUT: "current_sync_mode"},
                "current_page_ids": {INPUT: "current_page_ids"},
                "current_updated_pages": {INPUT: "current_updated_pages"},
                "current_total_processed": {INPUT: "current_total_processed"},
                "current_total_updated": {INPUT: "current_total_updated"},
                "current_total_deleted": {INPUT: "current_total_deleted"},
                "current_status": {INPUT: "current_status"},
                "current_error": {INPUT: "current_error"},
            },
            outputs={
                "job_id": OUTPUT,
                "bot_id": OUTPUT,
                "sync_mode": OUTPUT,
                "page_ids": OUTPUT,
                "updated_pages": OUTPUT,
                "total_processed": OUTPUT,
                "total_updated": OUTPUT,
                "total_deleted": OUTPUT,
                "status": OUTPUT,
                "error": OUTPUT,
            },
        )

        START >> code_update_sync_time >> code_package_context >> END
    
    graph_update_sync_at.build()
    return graph_update_sync_at
