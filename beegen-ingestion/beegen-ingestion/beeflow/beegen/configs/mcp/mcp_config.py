from enum import Enum

"""
This is the single config model used by ModelRegistry to build & store
MCP server instances under the key pattern:  mcp:<server>

Example YAML (BEEGEN_ROOT/config/mcp.yaml):

  server: openmetadata
  endpoint: https://your-host/mcp
  auth_token: ${ENV_TOKEN}
  verify: false
  timeout: 30
  retry: 2

Usage:
  from beegen.configs.mcp.mcp_config import McpConfig
  cfg = McpConfig.default()
  ModelRegistry.self().register(cfg)  # -> 'mcp:openmetadata'
"""

from typing import Optional

from beegen.configs.yaml_model import YamlModel
from beegen.const import BEEGEN_ROOT

class MCPServer(str, Enum):
    OPENMETADATA = "openmetadata"
    CONFLUENCE = "confluence"
    JIRA = "jira"

class MCPMethod(str, Enum):
    LIST = "list"
    CALL = "call"


class MCPConfig(YamlModel):
    """Config model so ModelRegistry can build and store MCP servers."""

    # server/provider name, e.g. "openmetadata", "confluence", "jira"
    server: str

    # Endpoint + auth
    endpoint: str
    auth_token: Optional[str] = None

    # Connection behavior
    verify: bool | str = False
    timeout: int = 30
    retry: int = 1

    @classmethod
    def default(cls) -> "MCPConfig":
        data = cls.read_yaml(BEEGEN_ROOT / "config/mcp.yaml")
        return cls(**data)

if __name__ == "__main__":
    mcp_config = MCPConfig.default()
    print(MCPConfig)