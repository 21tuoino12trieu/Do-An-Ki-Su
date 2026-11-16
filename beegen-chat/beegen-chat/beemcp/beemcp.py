from fastapi import APIRouter, HTTPException, Depends, status

from beegenerate.loggings import LOGGER
from beemcp.services.manager import MCPManagerServiceDep
from beemcp.models import AddSSEMCPRequest, AddMCPResponse, GetMCPResponse

from auth.middleware import verify_token

router = APIRouter(prefix="/mcp", tags=["mcp"])

# TODO: Activate this after done MCP Manager Super service
# @router.post("/add_sse")
async def add_sse_mcp_to_user(
    request: AddSSEMCPRequest,
    mcp_manager: MCPManagerServiceDep,
    token: dict = Depends(verify_token)
) -> AddMCPResponse:
    """
    Add an SSE-based MCP server to a user.

    Args:
        request (AddSSEMCPRequest): The request body containing username, server name, URL, and headers.
        mcp_manager (MCPManagerServiceDep): Dependency-injected MCP manager service.
        token (dict): Authorization token (injected by FastAPI dependency).

    Returns:
        AddMCPResponse: Information about the added MCP server and its tools.

    Raises:
        HTTPException: If the server already exists or an error occurs.
    """
    try:
        result = await mcp_manager.add_sse_server_user(
            username=request.username,
            name=request.name,
            url=request.url,
            headers=request.headers
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Error adding MCP to user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error adding MCP to user.")


@router.get("/{username}")
async def get_mcp_of_user(
    username: str,
    mcp_manager: MCPManagerServiceDep,
    token: dict = Depends(verify_token)
) -> GetMCPResponse:
    """
    Retrieve the list of MCP servers for a user.

    Args:
        username (str): The username whose MCP servers are to be retrieved.
        mcp_manager (MCPManagerServiceDep): Dependency-injected MCP manager service.
        token (dict): Authorization token (injected by FastAPI dependency).

    Returns:
        GetMCPResponse: The user's MCP servers and their tools.

    Raises:
        HTTPException: If an error occurs during retrieval.
    """
    try:
        result = await mcp_manager.get_list_server_of_user(username)
        return result
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Error getting MCP of user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error getting MCP of user.")
