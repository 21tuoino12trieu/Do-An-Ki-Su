"""
Confluence Workflow Package

BeeFlow-based implementation for Confluence to PostgreSQL sync.
This package provides workflow-based data ingestion from Confluence.

Architecture:
- Main workflow: Orchestrates complete sync process
- Sub-workflows: Handle page processing
- Functions: Reusable code functions for nodes
- Config: Configuration management

Modules:
    - main: Main entry point
    - workflow: Main sync workflow
    - workflows: Sub-workflows (page processing)
    - functions: Code functions for nodes
    - config: Configuration management
"""

def run_confluence_sync(*args, **kwargs):
    from confluence_workflow.main import main

    return main(*args, **kwargs)

__all__ = [
    "run_confluence_sync",
]
