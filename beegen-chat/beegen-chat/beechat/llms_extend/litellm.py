import os
import sys
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel
from beechat.config import load_settings

sys.stdout.reconfigure(encoding='utf-8')

settings = load_settings()
base_url = settings.openai_base_url.rstrip('/')
if not base_url.endswith('/v1'):
    base_url = f"{base_url}/v1"

api_key = settings.openai_api_key

openai_client = AsyncOpenAI(
    base_url=base_url,
    api_key=api_key,
)

litellm_model = OpenAIChatCompletionsModel(
    model=settings.scenario_model,
    openai_client=openai_client
)
