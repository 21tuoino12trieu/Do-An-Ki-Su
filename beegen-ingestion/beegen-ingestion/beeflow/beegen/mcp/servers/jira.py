from __future__ import annotations

from typing import Any, Dict, List

from ..base_server import BaseMCPServer, MCPServer


class JiraServer(BaseMCPServer):
    """
    Example adapter for a Jira-backed MCP server.

    If your Jira MCP returns slightly different keys, massage them here.
    """

    def list_tools(self) -> List[Dict[str, Any]]:
        tools = super().list_tools()
        # Example: ensure consistent keys
        norm: List[Dict[str, Any]] = []
        for t in tools:
            if "inputSchema" not in t and "parameters" in t:
                t = {**t, "inputSchema": t["parameters"]}
            norm.append(t)
        return norm