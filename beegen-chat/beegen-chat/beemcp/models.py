from pydantic import BaseModel
from pydantic.dataclasses import dataclass
from mcp.types import Tool

DEFAULT_MCP_SERVER_CONFIG = "./config/default_mcp.json"


@dataclass
class MCPConnection:
    name: str
    param: str


@dataclass
class BaseMCP:
    name: str
    list_tools: list[Tool]

# Request


class AddSSEMCPRequest(BaseModel):
    username: str
    name: str
    url: str
    headers: dict[str, str]

# Response


@dataclass
class AddMCPResponse:
    username: str
    name: str
    list_tools: list[Tool]


@dataclass
class GetMCPResponse:
    mcps: list[BaseMCP]
