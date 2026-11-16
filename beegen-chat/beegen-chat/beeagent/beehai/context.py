from pydantic.dataclasses import dataclass
from agents.mcp import ToolFilterContext


@dataclass
class UserInfo:
    """
    Data class representing Jira user information.

    Attributes:
        username (str): The user's Jira username.
        email (str): The user's email address.
        full_name (str): The user's full name.
        current_time (str): Current time.
    """
    username: str
    email: str
    full_name: str
    current_time: str


def botgresql_tool_filter(context: ToolFilterContext, tool) -> bool:
    """Example of a custom tool filter."""
    # Filter logic based on tool name patterns
    return tool.name.startswith("botgresql")
