from __future__ import annotations
import json

from typing import Any, Dict, List

from beegen.mcp.base_server import BaseMCPServer, MCPServer


class OpenMetadataServer(BaseMCPServer):
    """
    OpenMetadata MCP.

    Uses the base JSON-RPC methods; overrides are minimal since OpenMetadata
    already returns `name`, `description`, `inputSchema` in a conventional shape.
    """
    METHOD_LIST_TOOLS = "tools/list"
    METHOD_CALL_TOOL  = "tools/call"

    @staticmethod
    def to_openai_tools_schema(mcp_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize MCP tool descriptors to OpenAI tools schema.

        OpenAI expects items shaped like:
        {"type": "function", "function": {"name": str, "description": str, "parameters": JSONSchema}}
        """
        out: List[Dict[str, Any]] = []
        for t in mcp_tools or []:
            # Support various provider keys
            name = t.get("name") or t.get("tool") or t.get("id")
            if not name:
                continue
            desc = t.get("description") or t.get("summary") or ""
            params = t.get("inputSchema") or t.get("parameters") or {
                "type": "object",
                "properties": {},
                "required": [],
            }
            out.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": params,
                }
            })
        return out    

    
def main() -> None:
    from beegen.registry.resource_hub import ResourceHub
    server = ResourceHub.self().mcp("openmetadata")

    # 1) List tools
    try:
        tools = server.list_tools()
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] list_tools failed: {e}")
    openai_tools_schema = server.to_openai_tools_schema(tools)
    print(f"OpenAi tools schema: {json.dumps(openai_tools_schema, ensure_ascii=False, indent=2)}")

    print("=== Tools ===")
    for i, t in enumerate(tools, 1):
        name = t.get("name") or t.get("tool") or t.get("id")
        desc = t.get("description") or t.get("summary") or ""
        print(f"{i:2d}. {name} — {desc}")

    # 2) Call a tool
    payload = {"query":"customer","entity_type":"table","limit":2}
    try:
        result = server.call_tool("search_metadata", payload)
        print("=== Call Result ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] call_tool failed: {e}")


if __name__ == "__main__":
    main()