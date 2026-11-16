import json
import asyncio
from typing import List, Annotated, cast
from fastapi import Depends, Request, HTTPException, status
from agents.mcp import MCPServer, MCPServerSse, MCPServerStdio
from mcp import McpError
from beegenerate.loggings import LOGGER

from ..models import DEFAULT_MCP_SERVER_CONFIG, AddMCPResponse, GetMCPResponse, BaseMCP


class MCPManagerService:
    """
    MCP server manager.

    Manages MCP servers, allowing addition, removal, and listing of MCP servers for users.
    Handles batch connection and cleanup of servers, and provides methods for user-specific
    server management and tool listing.
    """

    def __init__(self):
        """
        Initialize the MCPManagerService.

        Sets up internal lists for servers and users, and loads the default configuration.
        """
        self.mcp_server_list: List[MCPServer] = []
        self.mcp_server_list_name: List[str] = []
        self.mcp_server_list_users: dict[str, dict[str, MCPServer]] = {}
        self.lock = asyncio.Lock()
        self.load_default_config_agent_compatible()

    def load_default_config_agent_compatible(self):
        """
        Load default MCP server configuration from the default config file.

        Loads server definitions from the JSON config and initializes server objects.
        """
        # Load config
        with open(DEFAULT_MCP_SERVER_CONFIG) as f:
            configs = json.loads(f.read())
            LOGGER.info(f"Default MCP servers: {configs}")

            keys = configs['mcpServers'].keys()
            for key in keys:
                LOGGER.info(f"Loading {key} server...")
                if "url" in configs['mcpServers'][key].keys():
                    server = MCPServerSse(
                        params=configs['mcpServers'][key], name=key, client_session_timeout_seconds=50)
                    self.mcp_server_list.append(server)
                else:
                    server = MCPServerStdio(
                        params=configs['mcpServers'][key], name=key, client_session_timeout_seconds=50)
                    self.mcp_server_list.append(server)
            LOGGER.info(f"Loaded {len(keys)} MCP servers")

    async def batch_connect(self):
        """
        Initialize connections to all MCP servers in the manager.
        """
        for server in self.mcp_server_list:
            await server.connect()

    async def batch_cleanup(self):
        """
        Cleanup connections to all MCP servers in the manager.
        """
        for server in self.mcp_server_list:
            await server.cleanup()

    # async def add_stdio_server_user(self, user_id: str, name: str, param: str) -> AddMCPResponse:
    #     """Add MCP stdio server by params.
    #     Please follow MCP configuration: https://modelcontextprotocol.io/examples#configuring-with-claude

    #     Args:
    #         param: MCP server run command. Example: `npx -y @modelcontextprotocol/server-memory`
    #     """
    #     try:
    #         if self.mcp_server_list_users.get(user_id) is None:
    #             self.mcp_server_list_users[user_id] = {}

    #         param = param.split(' ')
    #         mcp_param = {
    #             "command": param[0],
    #             "args": [param for param in param]
    #         }
    #         server = MCPServerStdio(
    #             params=mcp_param, client_session_timeout_seconds=30)
    #         await server.connect()
    #         self.mcp_server_list.append(server)
    #         list_tools = await server.list_tools()
    #         return AddMCPResponse(
    #             name=name,
    #             list_tools=list_tools
    #         )
    #     except Exception as e:
    #         raise f"Error adding stdio server: {e}"

    async def add_sse_server_user(self, username: str, name: str, url: str, headers: dict[str, str], tool_filter=None) -> AddMCPResponse:
        """
        Add an SSE-based MCP server for a specific user.
        Please follow MCP configuration: https://modelcontextprotocol.io/examples#configuring-with-claude

        Args:
            username (str): The user's username.
            name (str): The name to assign to the MCP server.
            url (str): The URL of the SSE server.
            headers (dict[str, str]): HTTP headers for the server connection.

        Returns:
            AddMCPResponse: Information about the added server and its tools.

        Raises:
            HTTPException: If the server already exists or times out.
            McpError: If there is an MCP-specific error.
            RuntimeError: For unexpected errors.
        """
        try:
            if self.mcp_server_list_users.get(username) is None:
                self.mcp_server_list_users[username] = {}
            if name in self.mcp_server_list_users[username].keys():
                if self.mcp_server_list_users[username][name] != {}:
                    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                        detail="MCP server existed, please choose other name")
            server = MCPServerSse(
                params={
                    "url": url,
                    "headers": headers or {}
                },
                cache_tools_list=True,
                name=name, client_session_timeout_seconds=20,
                tool_filter=tool_filter)
            await asyncio.wait_for(server.connect(), timeout=10)
            async with self.lock:
                self.mcp_server_list_users[username][name] = server
                list_tools = await server.list_tools(None, None)
                return AddMCPResponse(
                    username=username,
                    name=name,
                    list_tools=list_tools
                )
        except TimeoutError as e:
            LOGGER.error(
                f"[MCPManager] timeout adding SSE server '{name}':\n{e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_408_REQUEST_TIMEOUT,
                                detail="MCP server timeout")
        except McpError as e:
            LOGGER.error(
                f"[MCPManager] failed to add SSE server '{name}':\n{e}", exc_info=True)
            # re-raise so FastAPI can turn it into a 500 (or you could wrap in HTTPException)
            raise e
        except Exception as e:
            LOGGER.error(
                f"[MCPManager] unexpected error adding SSE server '{name}':\n{e}", exc_info=True)
            raise RuntimeError(f"Error adding SSE server '{name}': {e}") from e

    async def get_list_server(self):
        """
        Get the list of all MCP server names managed by this service.

        Returns:
            list: List of server names.

        Raises:
            RuntimeError: If an error occurs while retrieving the list.
        """
        try:
            servers = []
            for server in self.mcp_server_list:
                servers.append(server.name)
            return servers
        except Exception as e:
            raise RuntimeError(f"Error getting list MCP servers: {e}")

    async def get_mcp_of_user_for_agent(self, username, mcp_server_name):
        try:
            if self.mcp_server_list_users.get(username) is None:
                return None
            return self.mcp_server_list_users[username].get(mcp_server_name, None)
        except Exception as e:
            raise RuntimeError(
                f"Error getting {mcp_server_name} MCP serves of user {username}: {e}")

    async def get_list_server_of_user_for_agent(self, username):
        """
        Get the list of MCP server objects for a specific user.

        Args:
            username (str): The user's username.

        Returns:
            list: List of MCPServer objects for the user.

        Raises:
            RuntimeError: If an error occurs while retrieving the list.
        """
        try:
            mcps = []
            if self.mcp_server_list_users.get(username) is None:
                return []
            for server in self.mcp_server_list_users[username].keys():
                mcps.append(self.mcp_server_list_users[username][server])
            return mcps
        except Exception as e:
            raise RuntimeError(
                f"Error getting list MCP servers of user {username}: {e}")

    async def get_list_server_of_user(self, username) -> GetMCPResponse:
        """
        Get the list of MCP servers and their tools for a specific user.

        Args:
            username (str): The user's username.

        Returns:
            GetMCPResponse: Response containing the user's MCP servers and their tools.

        Raises:
            RuntimeError: If an error occurs while retrieving the list.
        """
        try:
            if self.mcp_server_list_users.get(username) is None:
                return GetMCPResponse(mcps=[])
            servers = []
            for server in self.mcp_server_list_users[username].keys():
                tools = await self.mcp_server_list_users[username][server].list_tools(None, None)
                servers.append(BaseMCP(
                    name=server,
                    list_tools=tools
                ))
            result = GetMCPResponse(mcps=servers)
            return result
        except Exception as e:
            raise RuntimeError(
                f"Error getting list MCP servers of user {username}: {e}")

    async def list_all_tool(self):
        """
        List all tools available from all MCP servers.

        Returns:
            list: List of all tools from all servers.
        """
        tools = []
        for server in self.mcp_server_list:
            tools += server.list_tools(None, None)

        print(tools)

    async def remove_mcp_of_user(self, username, mcp_name):
        """
        Remove an MCP server for a specific user.

        Args:
            username (str): The user's username.
            mcp_name (str): The name of the MCP server to remove.

        Raises:
            RuntimeError: If an error occurs during removal.
        """
        try:
            async with self.lock:
                if self.mcp_server_list_users.get(username) is None:
                    return True
                server = self.mcp_server_list_users[username].get(
                    mcp_name, None)
                if server is None:
                    return True
                await server.cleanup()
                self.mcp_server_list_users[username].pop(mcp_name, None)
                return True
        except Exception as e:
            raise RuntimeError(
                f"Error removing MCP of user {username}: {e}")


def get_mcp_manager(request: Request) -> MCPManagerService:
    """
    FastAPI dependency provider for MCPManagerService.

    Args:
        request (Request): The FastAPI request object.

    Returns:
        MCPManagerService: The MCP manager instance from the request state.
    """
    mcp_manager = cast(MCPManagerService, request.state.mcp_manager)
    return mcp_manager


MCPManagerServiceDep = Annotated[MCPManagerService, Depends(get_mcp_manager)]


async def main():
    """
    Main function for testing MCPManagerService.

    Connects to all servers, adds a test SSE server, and performs cleanup.
    """
    import os
    os.environ["NO_PROXY"] = "NO_PROXY"
    manager = MCPManagerService()
    await manager.batch_connect()
    # await manager.batch_cleanup()
    await manager.add_sse_server(param="http://localhost:8010/sse")
    await manager.batch_cleanup()

if __name__ == "__main__":
    asyncio.run(main())
