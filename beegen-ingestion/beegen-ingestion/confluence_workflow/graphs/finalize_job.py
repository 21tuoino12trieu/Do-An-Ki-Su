"""Finalize Job Graph."""

from beeflow.nodes import START, END, INPUT, OUTPUT, GraphNode, SQLNode, CodeNode

from beegen.configs.storage.sql_config import SQLOperation

from confluence_workflow.utils.logger import get_logger
from confluence_workflow.functions.workflow_helpers import build_finalize_payload

logger = get_logger('finalize_job')


def build_finalize_job_graph(config):
    """
    Build finalize job graph using the same SQL update as legacy finalize_job().
    """
    with GraphNode(
        name="graph_finalize_job",
        description="Finalize sync job with status and statistics",
        inputs={
            "job_id": INPUT,
            "status": INPUT,
            "total_processed": INPUT,
            "total_updated": INPUT,
            "total_deleted": INPUT,
            "error": INPUT,
            "updated_pages": INPUT,
        }
    ) as graph_finalize_job:

        code_build_finalize_payload = CodeNode(
            name="code_build_finalize_payload",
            code_fn=build_finalize_payload,
            return_keys=["params: Any", "result: Dict[str, Any]"],
            inputs={
                "job_id": {INPUT: "job_id"},
                "status": {INPUT: "status"},
                "total_processed": {INPUT: "total_processed"},
                "total_updated": {INPUT: "total_updated"},
                "total_deleted": {INPUT: "total_deleted"},
                "error": {INPUT: "error"},
                "updated_pages": {INPUT: "updated_pages"},
            },
            outputs={"result": OUTPUT},
        )

        sql_finalize_job = SQLNode(
            name="sql_finalize_job",
            resource_key="anapp",
            operation=SQLOperation.EXECUTE,
            inputs={
                "query": """
                    UPDATE knowledge_base.sync_jobs
                    SET status = %s,
                        total_processed = %s,
                        total_updated = %s,
                        total_deleted = %s,
                        finished_at = NOW(),
                        logs = %s
                    WHERE id = %s
                """,
                "params": {code_build_finalize_payload: "params"},
            },
        )

        START >> code_build_finalize_payload >> sql_finalize_job >> END

    graph_finalize_job.build()
    return graph_finalize_job
