"""
Graphs module for Confluence workflow.

This module provides sub-workflows for different sync operations.
All graphs are implemented using BeeFlow's WorkflowEngine.
"""

from confluence_workflow.graphs.initialize_job import build_initialize_job_graph
from confluence_workflow.graphs.finalize_job import build_finalize_job_graph
from confluence_workflow.graphs.resolve_parent_child import build_resolve_parent_child_graph
from confluence_workflow.graphs.calculate_level import build_calculate_level_graph
from confluence_workflow.graphs.sync_time import build_update_sync_at_graph

from confluence_workflow.graphs.fetch_mode.first_mode import build_first_mode_graph
from confluence_workflow.graphs.fetch_mode.partial_mode import build_partial_mode_graph
from confluence_workflow.graphs.fetch_mode.auto_mode import build_auto_mode_graph
from confluence_workflow.graphs.cleanup_old_data import build_cleanup_old_confluence_data_graph

__all__ = [
    # Core graphs
    "build_initialize_job_graph",
    "build_finalize_job_graph",
    "build_resolve_parent_child_graph",
    "build_calculate_level_graph",
    "build_update_sync_at_graph",
    # Mode-specific graphs
    "build_first_mode_graph",
    "build_partial_mode_graph",
    "build_auto_mode_graph",
    "build_cleanup_old_confluence_data_graph",
]
