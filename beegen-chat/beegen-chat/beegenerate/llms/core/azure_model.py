from openai.types.chat import ChatCompletionMessageParam
from typing import Dict, List, Tuple
from .base import BaseLLM
from beegenerate.configs import LLMConfig, LLMType
import asyncio
import warnings

from beegenerate.utils.common import raise_error

warnings.filterwarnings("ignore", category=RuntimeWarning)  


class AzureOpenAIModel(BaseLLM):
    
    r"""Azure OpenAI API in a unified ModelBackend interface."""
    
    def __init__(
        self,
        config: LLMConfig
    ) -> None:
        super().__init__(config)
        if config.api_type != LLMType.AZURE:
            raise_error(ValueError(f"Api type must be azure, not {config.api_type}"))
                
    def prepare_request(
        self, 
        messages: List[ChatCompletionMessageParam]
    ) -> Tuple[str, Dict, Dict]:
        url = (
            f"{self.config.base_url}/openai/deployments/"
            f"{self.config.model}/chat/completions"
            f"?api-version={self.config.api_version}"
            f"&api-key={self.config.api_key}"
        )
        headers = {
            'Content-Type': 'application/json',
        }
        
        params = self.config.completion.model_dump(
            exclude_none=True
        )
        params['messages'] = messages
        return url, headers, params
