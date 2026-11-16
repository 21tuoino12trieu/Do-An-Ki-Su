from openai.types.chat import ChatCompletionMessageParam
from typing import Dict, List, Tuple
from .base import BaseLLM
from beegenerate.configs import LLMConfig, LLMType
from beegenerate.utils.common import raise_error

from beegenerate.loggings import LOGGER


class VllmOpenAIModel(BaseLLM):
    
    r"""VLLM OpenAI API in a unified ModelBackend interface."""
    
    def __init__(
        self, 
        config: LLMConfig,
    ) -> None:
        super().__init__(config)
        if config.api_type != LLMType.VLLM:
            raise_error(ValueError(f"Api type must be vllm, not {config.api_type}"))
                
    def prepare_request(
        self, 
        messages: List[ChatCompletionMessageParam]
    ) -> Tuple[str, Dict, Dict]:
        url = self.config.base_url + "/chat/completions"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.config.api_key}'
        }
        
        params = self.config.completion.model_dump(
            exclude_none=True
        )
        params['model'] = self.config.model
        params['messages'] = messages
        return url, headers, params