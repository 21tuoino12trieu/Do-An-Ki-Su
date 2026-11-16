from datetime import datetime
from agents import function_tool


@function_tool
def current_datetime():
    """
    Get the current date and time of the current session.

    Returns:
        str: A string representing the current date and time.
    """
    now = datetime.now()
    return f"Current date and time: {now}"
