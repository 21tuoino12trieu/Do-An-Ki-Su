"""
Functions module for Confluence workflow.

This module provides code functions for BeeFlow nodes.
"""

# Confluence functions
from confluence_workflow.functions.confluence_processor import (
    fetch_descendants_flat,
)

__all__ = [
    # Confluence functions
    "fetch_descendants_flat",
]
