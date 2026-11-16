from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from abc import abstractmethod, ABC

import requests

try:
    # Prefer central logger if available
    from beegen.loggings import LOGGER
except Exception:  # pragma: no cover
    import logging
    LOGGER = logging.getLogger(__name__)


@dataclass
class MCPServer:
    endpoint: str
    auth_token: str
    verify: bool | str = True
    timeout: int = 30
    retry: int = 1


class BaseMCPServer(ABC):
    """
    Base adapter for a JSON-RPC MCP server.

    Responsibilities:
      - POST JSON-RPC to `/mcp` (or `/mcp/` fallback)
      - Provide `list_tools()` and `call_tool(name, args)`
      - Normalize tool list to **OpenAI tool schema** via `to_openai_tools_schema()`
    """
    METHOD_LIST_TOOLS: str = "tools/list"
    METHOD_CALL_TOOL: str  = "tools/call"

    def __init__(self, opts: MCPServer):
        self.opts = opts
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {opts.auth_token}",
        })
        self._session.verify = opts.verify

    # ----------------------------- JSON-RPC core -----------------------------
    def _post_jsonrpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        endpoint = self.opts.endpoint.rstrip("/")
        last_err: Optional[Exception] = None
        for attempt in range(1, self.opts.retry + 1):
            try:
                resp = self._session.post(endpoint, data=json.dumps(payload), timeout=self.opts.timeout)
                if resp.status_code in (404, 405):
                    continue
                resp.raise_for_status()
                return resp.json()
            except Exception as e:  # noqa: BLE001
                last_err = e
                LOGGER.warning("MCP POST failed (%s %s) attempt %d: %s", method, endpoint, attempt, e)
            time.sleep(min(1.0 * attempt, 3.0))
        raise RuntimeError(f"MCP post failed (method={method}): {last_err}")

    # ----------------------------- Public API -------------------------------
    def list_tools(self) -> List[Dict[str, Any]]:
        """Return the raw MCP tools list from the server.

        Adapters may override this to massage provider-specific shapes.
        """
        try:
            data = self._post_jsonrpc(self.METHOD_LIST_TOOLS, {})
            result = data.get("result") or {}
            tools = result.get("tools") if isinstance(result, dict) else result
            if isinstance(tools, list):
                return tools
        except Exception as e:  # noqa: BLE001
            LOGGER.debug("list_tools via %s failed: %s", self.METHOD_LIST_TOOLS, e)
        raise RuntimeError("Unable to fetch tools from MCP")

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        params = {"name": name, "arguments": arguments or {}}
        try:
            data = self._post_jsonrpc(self.METHOD_CALL_TOOL, params)
            if "result" in data:
                return data["result"]
            if "error" in data:
                raise RuntimeError(f"MCP error: {data['error']}")
        except Exception as e:  # noqa: BLE001
            LOGGER.debug("call_tool via %s failed: %s", self.METHOD_CALL_TOOL, e)
        raise RuntimeError("Unable to call tool via MCP")

    @staticmethod
    @abstractmethod
    def to_openai_tools_schema(mcp_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize MCP tool descriptors to OpenAI tools schema.

        OpenAI expects items shaped like:
        {"type": "function", "function": {"name": str, "description": str, "parameters": JSONSchema}}
        """
        raise NotImplementedError