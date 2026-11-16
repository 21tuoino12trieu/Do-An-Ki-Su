"""
Initialize Job Graph

This graph creates a new sync job record in PostgreSQL.
Mode-specific graphs handle all document reconciliation and cleanup.
"""

from beeflow.nodes import START, END, OUTPUT, GraphNode, CodeNode, SQLNode

from beegen.configs.storage.sql_config import SQLOperation

from confluence_workflow.utils.logger import get_logger
from confluence_workflow.functions.workflow_helpers import extract_job_id

logger = get_logger('initialize_job')


def build_initialize_job_graph(config):
    """
    Build initialize job graph using BeeFlow.
    
    This graph:
    1. Creates sync job record with RUNNING status
    
    Args:
        config: Workflow configuration
        
    Returns:
        Compiled graph instance
    """
    with GraphNode(
        name="graph_initialize_job",
        description="Initialize the Confluence sync job",
    ) as graph_initialize_job:
        # Step 1: Create job record
        sql_create_job = SQLNode(
            name="sql_create_job",
            resource_key='anapp',
            operation=SQLOperation.EXECUTE,
            inputs={
                "query": """
                    INSERT INTO knowledge_base.sync_jobs (status, started_at)
                    VALUES (%s, NOW())
                    RETURNING id
                """,
                "params": ("RUNNING",),
                "returning": True,
            },
        )

        code_extract_job_id = CodeNode(
            name="code_extract_job_id",
            code_fn=extract_job_id,
            return_keys=["job_id: Any"],
            inputs={"create_job_result": {sql_create_job: "data"}},
            outputs={"job_id": OUTPUT},
        )

        START >> sql_create_job >> code_extract_job_id >> END
    
    graph_initialize_job.build()
    return graph_initialize_job
