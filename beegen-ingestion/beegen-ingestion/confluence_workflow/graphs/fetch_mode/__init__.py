"""
Fetch mode sub-graphs for Confluence workflow.

This module provides mode-specific fetch graphs:
- FIRST: Fetch all descendants from parent pages
- PARTIAL: Fetch specific pages
- AUTO: Fetch active pages from MongoDB and compare
"""

from confluence_workflow.graphs.fetch_mode.first_mode import build_first_mode_graph
from confluence_workflow.graphs.fetch_mode.partial_mode import build_partial_mode_graph
from confluence_workflow.graphs.fetch_mode.auto_mode import build_auto_mode_graph

__all__ = [
    "build_first_mode_graph",
    "build_partial_mode_graph",
    "build_auto_mode_graph",
]
