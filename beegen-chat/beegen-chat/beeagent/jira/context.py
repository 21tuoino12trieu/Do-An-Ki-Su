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
    """
    username: str
    email: str
    full_name: str


def jira_tool_filter(context: ToolFilterContext, tool) -> bool:
    """Example of a custom tool filter."""
    # Filter logic based on tool name patterns
    return tool.name.startswith("jira")


# Message shown when the user is not logged in to Jira
LOGIN_MESSAGE = """Bạn chưa đăng nhập Jira, vui lòng nhập tài khoản mật khẩu theo chính xác cú pháp sau:
> `tài_khoản:mật_khẩu`
"""

# Message shown when the login credentials are incorrect
INCORRECT_LOGIN_MESSAGE = """Tài khoản hoặc mật khẩu không đúng, vui lòng nhập tài khoản mật khẩu theo chính xác cú pháp sau:
> `tài_khoản:mật_khẩu`
"""

# Message shown when login is successful; {username} will be replaced with the user's name
SUCCESS_LOGIN_MESSAGE = """Đăng nhập thành công, xin chào {username}!"""

# Message shown when the login session has expired
TOKEN_EXPIRE_MESSAGE = """Phiên đăng nhập hết hạn, vui lòng đăng nhập lại."""
