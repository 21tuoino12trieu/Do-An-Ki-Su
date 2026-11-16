from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Type
from beegen.configs.mcp.mcp_config import MCPConfig

from beegen.mcp.base_server import BaseMCPServer, MCPServer
from beegen.mcp.servers.openmetadata import OpenMetadataServer
from beegen.mcp.servers.jira import JiraServer
from beegen.mcp.servers.confluence import ConfluenceServer


class MCPFactory:
    """
    Build the right MCP server from config/registry.
    """

    _SERVERS: Dict[str, Type[BaseMCPServer]] = {
        "openmetadata": OpenMetadataServer,
        "jira": JiraServer,
        "confluence": ConfluenceServer,
    }

    @classmethod
    def create(cls, cfg: MCPConfig) -> BaseMCPServer:
        key = (cfg.server or "").lower()
        if key not in cls._SERVERS:
            raise ValueError(f"Unknown MCP server: {cfg.server}")
        opts = MCPServer(
            endpoint=cfg.endpoint.rstrip("/"),
            auth_token=cfg.auth_token,
            verify=cfg.verify,
            timeout=cfg.timeout,
            retry=cfg.retry,
        )
        return cls._SERVERS[key](opts)

    # # --- Optional helpers ---------------------------------------------------
    # @classmethod
    # def from_registry(cls, server: str, name: Optional[str] = None) -> BaseMCPServer:
    #     """Build adapter from ModelRegistry-held config.

    #     Expected registry layout (example, adjust to your environment):

    #     ```python
    #     ModelRegistry.self().get("mcp", server) -> {
    #       "base_url": "https://…",
    #       "bearer_token": "…",
    #       "verify": True,  # or "/path/to/ca.pem"
    #       "timeout_seconds": 30,
    #       "retry": 2,
    #     }
    #     ```
    #     """
    #     if ModelRegistry is None:
    #         raise RuntimeError("ModelRegistry unavailable; cannot load MCP config")
    #     reg = ModelRegistry.self()
    #     # Flexible keying: try explicit namespace then fallback
    #     cfg_dict = None
    #     for key in (
    #         ("mcp", server),
    #         ("mcp", name or server),
    #         (f"mcp.{server}", None),
    #     ):
    #         try:
    #             if isinstance(key, tuple):
    #                 cfg_dict = reg.get(key[0], key[1])  # type: ignore[attr-defined]
    #             else:
    #                 cfg_dict = reg.get(key)  # type: ignore[attr-defined]
    #         except Exception:
    #             cfg_dict = None
    #         if cfg_dict:
    #             break
    #     if not cfg_dict:
    #         raise RuntimeError(f"Missing MCP config for server={server}")
    #     cfg = MCPConfig(
    #         server=server,
    #         base_url=cfg_dict["base_url"],
    #         bearer_token=cfg_dict["bearer_token"],
    #         verify=cfg_dict.get("verify", True),
    #         timeout_seconds=cfg_dict.get("timeout_seconds", 30),
    #         retry=cfg_dict.get("retry", 1),
    #     )
    #     return cls.create(cfg)