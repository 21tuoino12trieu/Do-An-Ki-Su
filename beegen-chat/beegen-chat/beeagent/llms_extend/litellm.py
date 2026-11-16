from beegenerate.configs import LiteLLMConfig
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel
from beegenerate.const import BEEGEN_ROOT

import sys
sys.stdout.reconfigure(encoding='utf-8')


# This model can be replace by openai-agents[litellm]
# Use this client with proxy for request capturing

litellm_config = LiteLLMConfig.from_yaml_file(
    BEEGEN_ROOT / "config/llms/litellm.yaml")

openai_client = AsyncOpenAI(
    base_url=litellm_config.base_url,
    api_key=litellm_config.api_key,
)
litellm_model = OpenAIChatCompletionsModel(
    model='gpt-4.1',
    openai_client=openai_client
)
