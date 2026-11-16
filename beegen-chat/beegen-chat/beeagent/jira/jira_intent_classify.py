from agents import Agent
from pydantic.dataclasses import dataclass

from ..llms_extend.litellm import litellm_model


@dataclass
class UserIntent():
    is_normal: bool
    is_jira_relate: bool


jira_intent_classify = Agent(
    name="Jira intent detection",
    model=litellm_model,
    instructions="Check if user query is related to Jira",
    output_type=UserIntent
)
