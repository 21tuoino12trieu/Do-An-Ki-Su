from google.genai import types
from google.adk.planners import BuiltInPlanner

MINIMAL_BUILTIN_THINKING = BuiltInPlanner(
    thinking_config=types.ThinkingConfig(
        include_thoughts=True,
        thinking_level=types.ThinkingLevel.MINIMAL
    )
)
