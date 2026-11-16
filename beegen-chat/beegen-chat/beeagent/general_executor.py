from agents import Agent

from .llms_extend.litellm import litellm_model

normal_agent = Agent(
    name="Assistant",
    model=litellm_model,
    instructions="""Trợ lý giải đáp mọi thắc mắc. Luôn luôn trả lời bằng tiếng Việt."""
)
