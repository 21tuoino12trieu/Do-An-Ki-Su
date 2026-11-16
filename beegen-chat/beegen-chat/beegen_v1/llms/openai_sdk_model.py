from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion import ChatCompletion
from typing import List, AsyncGenerator, Optional, Sequence, Union
from .base_llm import BaseLLM
from beegen_v1.configs import OpenAIConfig
import httpx
import asyncio
import os


# Set proxy bypass for internal services
# os.environ['NO_PROXY'] = 'llm-gateway-dev.mbbank.com.vn,10.1.87.71,10.1.13.168'
os.environ['NO_PROXY'] = 'llm-gateway-dev.mbbank.com.vn'


class OpenAISDKModel(BaseLLM):
    """OpenAI model (SDK) with tool calls and multimodal support."""
    
    def __init__(self, config: OpenAIConfig):
        super().__init__(config)
        
        # Configure HTTP client with timeout and no SSL verification
        self.http_client = httpx.AsyncClient(
            verify=False,
            timeout=httpx.Timeout(
                connect=10.0,
                read=120.0,
                write=10.0,
                pool=5.0
            ),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=10
            )
        )
        
        # Initialize OpenAI client
        if hasattr(config, 'base_url'):
            self.client = AsyncOpenAI(
                base_url=config.base_url,
                api_key=config.api_key,
                http_client=self.http_client
            )
        
    async def stream(
        self,
        messages: List[ChatCompletionMessageParam],
        temperature: float = 0.0,
        top_p: float = 0.1,
        n: Optional[int] = None,
        stop: Optional[Union[str, Sequence[str]]] = None,
        max_tokens: Optional[int] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        response_format: Optional[dict] = None,
        tools: Optional[dict] = None,
        **kwargs
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Stream chat completion responses with Chinese character filtering.
        
        Processes messages to handle local image paths, then streams responses
        from the OpenAI-compatible API. Automatically raises an exception if
        any response chunk contains Chinese characters.
        
        Args:
            messages: List of chat messages to process in the conversation
            temperature: Controls randomness in response generation (0.0-2.0). 
                        Lower values make output more focused and deterministic.
            top_p: Controls diversity via nucleus sampling (0.0-1.0). 
                Only tokens with top_p probability mass are considered.
            n: Number of chat completion choices to generate for each input message.
                Only the first choice is typically used in streaming.
            stop: Up to 4 sequences where the API will stop generating further tokens.
                Can be a string or list of strings.
            max_tokens: Maximum number of tokens to generate in the chat completion.
                    Total length is limited by model's context length.
            frequency_penalty: Penalizes new tokens based on their existing frequency 
                            in the text so far (-2.0 to 2.0).
            presence_penalty: Penalizes new tokens based on whether they appear 
                            in the text so far (-2.0 to 2.0).
            response_format: Object specifying the format that the model must output.
                            Compatible with GPT-4 Turbo and gpt-3.5-turbo-1106.
            **kwargs: Additional streaming options specific to the implementation
            
        Returns:
            AsyncGenerator yielding ChatCompletionChunk objects containing partial 
                response data as it becomes available
            
        Raises:
            ValueError: If any response chunk contains Chinese characters
            
        Note:
            - Local image file paths are automatically converted to base64 data URLs
            - Chinese character detection covers CJK Unified Ideographs (U+4E00-U+9FFF)
        """
        # Prepare parameters
        params = self._prepare_params(
            model=self.config.model,
            messages=messages,
            stream=True,
            temperature=temperature,
            top_p=top_p,
            n=n,
            stop=stop,
            max_tokens=max_tokens,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            response_format=response_format,
            tools=tools
        )
            
        sleep = kwargs.pop("sleep", 0.0)
        stream_response = await self.client.chat.completions.create(**params)
        async for chunk in stream_response:
            if not self.check_chinese_characters(chunk, raise_on_found=True):
                # Update kwargs onto chunk
                for key, value in kwargs.items():
                    setattr(chunk, key, value)
                await asyncio.sleep(sleep)
                
                yield chunk
            
    async def generate(
        self,
        messages: List[ChatCompletionMessageParam],
        temperature: float = 0.0,
        top_p: float = 0.1,
        n: Optional[int] = None,
        stop: Optional[Union[str, Sequence[str]]] = None,
        max_tokens: Optional[int] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        response_format: Optional[dict] = None,
        tools: Optional[dict] = None,
        **kwargs
    ) -> ChatCompletion:
        """
        Generate a complete chat completion response with Chinese character filtering.
        
        Processes messages to handle local image paths, then generates a complete
        response from the OpenAI-compatible API. Automatically raises an exception
        if the response contains Chinese characters.
        
        Args:
            messages: List of chat messages to process in the conversation
            temperature: Controls randomness in response generation (0.0-2.0). 
                        Lower values make output more focused and deterministic.
            top_p: Controls diversity via nucleus sampling (0.0-1.0). 
                Only tokens with top_p probability mass are considered.
            n: Number of chat completion choices to generate for each input message.
                Only the first choice is typically used in streaming.
            stop: Up to 4 sequences where the API will stop generating further tokens.
                Can be a string or list of strings.
            max_tokens: Maximum number of tokens to generate in the chat completion.
                    Total length is limited by model's context length.
            frequency_penalty: Penalizes new tokens based on their existing frequency 
                            in the text so far (-2.0 to 2.0).
            presence_penalty: Penalizes new tokens based on whether they appear 
                            in the text so far (-2.0 to 2.0).
            response_format: Object specifying the format that the model must output.
                            Compatible with GPT-4 Turbo and gpt-3.5-turbo-1106.
            **kwargs: Additional streaming options specific to the implementation
            
        Returns:
            ChatCompletion: The complete response from the API
            
        Raises:
            ValueError: If the response contains Chinese characters
            
        Note:
            - Local image file paths are automatically converted to base64 data URLs
            - Chinese character detection covers CJK Unified Ideographs (U+4E00-U+9FFF)
        """
        # Prepare parameters
        params = self._prepare_params(
            model=self.config.model,
            messages=messages,
            stream=False,
            temperature=temperature,
            top_p=top_p,
            n=n,
            stop=stop,
            max_tokens=max_tokens,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            response_format=response_format,
            tools=tools
        )
        
        completion = await self.client.chat.completions.create(**params)
        self.check_chinese_characters(completion, raise_on_found=True)
        
        # Update kwargs onto chunk
        for key, value in kwargs.items():
            setattr(completion, key, value)
        
        return completion
        
    async def close(self):
        """Clean up resources"""
        await self.client.close()
        await self.http_client.aclose()
        

async def main():
    from beegen_v1.const import BEEGEN_ROOT
    from beegen_v1.configs import LLMConfig
    model = OpenAISDKModel(LLMConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/beegen_v1.yaml"))
    
    # response = await model.generate(messages=[{"role": "user", "content": "xin chào"}])
    # print(response)
    
    async for chunk in model.stream(
        messages=[{"role": "user", "content": "say hi"}],
        status_code=200
    ):
        print(chunk)
        

async def test_tool_callings():
    import json
    from beegen_v1.const import BEEGEN_ROOT
    from beegen_v1.configs import LLMConfig
    
    model = OpenAISDKModel(LLMConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/beegen_v1.yaml"))
    # Define some example tools
    weather_tool = {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA"
                    }
                },
                "required": ["location"]
            }
        }
    }
    
    calculator_tool = {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Perform a calculation",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to evaluate"
                    }
                },
                "required": ["expression"]
            }
        }
    }
    
    tools = [weather_tool, calculator_tool]
    
    # Text-only example with tools
    print("Text-only example with tools:")
    completion = await model.generate(
        messages=[{"role": "user", "content": "What's the weather like in San Francisco?"}],
        tools=tools
    )
    print(json.dumps(completion.model_dump(), indent=2))
    
    # Text-only example with tools
    print("Text-only example with tools (streaming):")
    async for chunk in model.stream(
        messages=[{"role": "user", "content": "What's the weather like in San Francisco?"}],
        tools=tools
    ):
        if chunk.choices:
            content = chunk.choices[0].delta.content
            if content:
                pass
            
            tool_calls = chunk.choices[0].delta.tool_calls
            if tool_calls:
                print(tool_calls)
    

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_tool_callings())