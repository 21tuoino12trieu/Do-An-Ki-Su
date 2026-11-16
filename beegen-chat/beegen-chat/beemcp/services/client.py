from openai.types.chat.chat_completion import ChatCompletion
from agents import enable_verbose_stdout_logging
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from agents import FunctionTool, Handoff, UserError
from typing import Any
import json
from dotenv import load_dotenv
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client

from contextlib import AsyncExitStack
from typing import Optional
import asyncio

import sys
sys.stdout.reconfigure(encoding='utf-8')

enable_verbose_stdout_logging()

load_dotenv()  # load environment variables from .env


class ToolConverter:
    @classmethod
    def to_openai(cls, tool) -> ChatCompletionToolParam:
        if isinstance(tool, FunctionTool):
            return {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.params_json_schema,
                },
            }
        else:
            schema, is_strict = tool.inputSchema, False
            return {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": schema,
                },
            }

        raise UserError(
            f"Hosted tools are not supported with the ChatCompletions API. Got tool type: "
            f"{type(tool)}, tool: {tool}"
        )

    @classmethod
    def convert_handoff_tool(cls, handoff: Handoff[Any]) -> ChatCompletionToolParam:
        return {
            "type": "function",
            "function": {
                "name": handoff.tool_name,
                "description": handoff.tool_description,
                "parameters": handoff.input_json_schema,
            },
        }


class MCPClient:
    """MCP client for basic LLM.
    [WARNING] If you are using openai agents sdk, please use from `agents.mcp import *`
    """

    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.session: Optional[ClientSession] = None

    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server

        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:",
              [tool.name for tool in tools])

    async def connect_to_sse_server(self,
                                    url: str,
                                    headers: dict[str, str] | None = None):
        """Connect to an MCP server over HTTP+SSE."""

        # 1. Establish the SSE transport by name, not by passing a dict
        reader, writer = await self.exit_stack.enter_async_context(
            # pass as kwargs, not a dict :contentReference[oaicite:2]{index=2}
            sse_client(
                url=url
            )
        )

        # 2. Open the MCP session over those streams
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(reader, writer)
        )
        # handshake, tool discovery :contentReference[oaicite:3]{index=3}
        await self.session.initialize()

        # 3. List and print the tools
        resp = await self.session.list_tools()
        print("Connected via SSE to", url, "– available tools:",
              [t.name for t in resp.tools])
        return True

    async def tool_invoke(self, tool_name, tool_args):
        result = await self.session.call_tool(tool_name, tool_args)

        if len(result.content) == 1:
            tool_output = result.content[0].model_dump_json()
        elif len(result.content) > 1:
            tool_output = json.dumps([item.model_dump()
                                     for item in result.content])
        else:
            print(f">>> Errored MCP tool result: {result}")
            tool_output = "Error running tool."
        return tool_output

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)

    client = MCPClient()
    try:
        if sys.argv[1].startswith('python'):
            await client.connect_to_server(sys.argv[1])
        elif sys.argv[1].startswith('http'):
            await client.connect_to_sse_server(sys.argv[1])
        else:
            print("Usage: server path or uri")
            sys.exit(1)
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    asyncio.run(main())
