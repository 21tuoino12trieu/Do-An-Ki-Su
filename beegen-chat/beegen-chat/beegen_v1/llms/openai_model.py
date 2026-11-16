from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion import ChatCompletion
from typing import Dict, List, Tuple, AsyncIterator, Union, Any, Optional
from .base_llm import BaseLLM
from beegen_v1.configs import LLMConfig
from beegen_v1.llms.response import LLMGenerator
from beegen_v1.loggings import LOGGER
import aiohttp
import asyncio
import json
import base64
import mimetypes


class OpenAICompatibleModel(BaseLLM):
    """OpenAI compatible model with tool calls and multimodal support."""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
                    
    @staticmethod
    def _encode_image(image_path: str) -> Dict:
        """
        Encode an image file to base64.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dictionary with image data in OpenAI-compatible format
        """
        mime_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{base64_image}"
            }
        }
    
    async def stream(
        self,
        messages: List[ChatCompletionMessageParam],
        **kwargs
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Stream responses from Azure OpenAI with support for tools and tool_choice.
        
        Args:
            messages: Chat messages to process
            tools: Optional list of tools the model can use
            **kwargs: Additional streaming options
            
        Returns:
            Stream of response chunks
        """
        # Preprocess messages to handle image paths
        processed_messages = [self.resolve_image_paths(message) for message in messages]
        
        # metrics = PerformanceMetrics()
        # first_chunk_received = False        
        
        async for chunk in LLMGenerator.process(
            streamline=self._request(
                messages=processed_messages, 
                stream=True
            ),
            model=self.config.model,
            **kwargs
        ):
            # if not first_chunk_received:
            #     first_chunk_received = True
            #     metrics.record_first_token()
            
            # Track tokens from both content and tool calls
            # if chunk.choices and chunk.choices[0].delta:
            #     delta = chunk.choices[0].delta
            #     if delta.content:
            #         metrics.record_token(delta.content)
            
            yield chunk
            
        # metrics.log_stats()
    
    async def generate(
        self,
        messages: List[ChatCompletionMessageParam],
        **kwargs
    ) -> ChatCompletion:
        """Generate chat completion with tool calls support.
        
        Args:
            messages: input conversation to generate from
            tools: Optional list of tools the model can use
            **kwargs: Additional generation options
        """
        # Preprocess messages to handle image paths
        processed_messages = [self.resolve_image_paths(message) for message in messages]
        
        # metrics = PerformanceMetrics()
        # metrics.record_first_token()
                
        result = await self._request(
            messages=processed_messages, 
            stream=False
        ).__anext__()
        
        result.update(**kwargs)
        completion = ChatCompletion(**result)
        
        # # Record the tokens into metrics stats
        # completion_tokens = completion.usage.completion_tokens
        # for _ in range(completion_tokens):
        #     metrics.record_token("_")
            
        # # Store response content in metrics
        # metrics.response_text = completion.choices[0].message.content or ""
        
        # metrics.log_stats()
        
        return completion
    
    def _prepare_url_headers(self) -> Tuple[str, Dict]:
        """Prepare Azure OpenAI API URL and headers."""
        url = self.config.base_url + "/chat/completions"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.config.api_key}'
        }
        
        return url, headers
        
    async def _request(
        self,
        messages: Union[
            List[ChatCompletionMessageParam],
            List[List[ChatCompletionMessageParam]]
        ],
        stream: bool = True
    ) -> AsyncIterator:
        """
        Make requests to Azure OpenAI API, supporting both single and batch requests.
        
        Args:
            messages: Either a list of messages for a single request,
                     or a list of message lists for batch requests
            stream: Whether to stream the response
            batch_tools: Optional list of tools for each request in a batch
            **kwargs: Additional parameters for the request
                      
        Yields:
            For stream=True: Chunks of generated content
            For stream=False: Complete response
            For batch requests: List of complete responses (stream=False)
        """
        # prepare request params
        url, headers = self._prepare_url_headers()
        
        # Single request mode - messages is a single list of messages
        params = self.config.completion.model_dump(exclude_none=True)
        params['model'] = self.config.model
        params['messages'] = messages
        params['stream'] = stream
            
        if stream:
            params["stream_options"] = {
                "include_usage": True
            }
                
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            async with session.post(url=url, headers=headers, json=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ValueError(f"Request failed: {error_text}", response.status)
                
                if stream:
                    async for line in response.content:
                        line_text = line.decode('utf-8').strip()
                        if line_text.startswith("data: "):
                            line_text = line_text[6:]  # Remove "data: " prefix
                            
                        if line_text and line_text != "[DONE]":
                            try:
                                chunk_data = json.loads(line_text)
                                yield self._process_tool_call_chunk(chunk_data)
                            except json.JSONDecodeError:
                                LOGGER.warning(f"Failed to decode JSON from chunk: {line_text}")
                else:
                    result = await response.json()
                    yield self._process_tool_call_response(result)
    
    def _process_tool_call_chunk(self, chunk_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a chunk that might contain tool calls.
        
        Args:
            chunk_data: Raw chunk data from the API
            
        Returns:
            Processed chunk data with properly structured tool calls
        """
        # If there are no tool calls or choices, return as is
        if (not chunk_data.get("choices") or 
            not chunk_data["choices"][0].get("delta") or 
            not chunk_data["choices"][0]["delta"].get("tool_calls")):
            return chunk_data
            
        # Process tool calls in the delta
        for choice in chunk_data["choices"]:
            if "delta" in choice and "tool_calls" in choice["delta"]:
                # Ensure tool_calls is properly structured
                tool_calls = choice["delta"]["tool_calls"]
                for i, tool_call in enumerate(tool_calls):
                    # If the function arguments are coming in as a string, ensure they stay as a string
                    # (Some Azure OpenAI versions may return arguments differently)
                    if "function" in tool_call and "arguments" in tool_call["function"]:
                        arguments = tool_call["function"]["arguments"]
                        if isinstance(arguments, str):
                            # Keep as is - the ChatCompletionChunk constructor will handle it
                            pass
                        elif isinstance(arguments, dict):
                            # Convert back to string for consistency
                            tool_call["function"]["arguments"] = json.dumps(arguments)
                            
        return chunk_data
    
    def _process_tool_call_response(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a complete response that might contain tool calls.
        
        Args:
            response_data: Raw response data from the API
            
        Returns:
            Processed response data with properly structured tool calls
        """
        # If there are no tool calls or choices, return as is
        if (not response_data.get("choices") or 
            not response_data["choices"][0].get("message") or 
            not response_data["choices"][0]["message"].get("tool_calls")):
            return response_data
        
        # Process tool calls in the message
        for choice in response_data["choices"]:
            if "message" in choice and "tool_calls" in choice["message"]:
                # Ensure tool_calls is properly structured
                tool_calls = choice["message"]["tool_calls"]
                for i, tool_call in enumerate(tool_calls):
                    # Ensure function arguments are strings
                    if "function" in tool_call and "arguments" in tool_call["function"]:
                        arguments = tool_call["function"]["arguments"]
                        if isinstance(arguments, dict):
                            # Convert to string for consistency with OpenAI format
                            tool_call["function"]["arguments"] = json.dumps(arguments)
        
        return response_data


async def main():
    # Example config for Azure
    from beegen_v1.registry.model_registry import ModelRegistry
    
    model = ModelRegistry.self().llm("gpt-4o")
    
    # Define some example tools
    # weather_tool = {
    #     "type": "function",
    #     "function": {
    #         "name": "get_weather",
    #         "description": "Get the current weather in a given location",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "location": {
    #                     "type": "string",
    #                     "description": "The city and state, e.g. San Francisco, CA"
    #                 }
    #             },
    #             "required": ["location"]
    #         }
    #     }
    # }
    
    # calculator_tool = {
    #     "type": "function",
    #     "function": {
    #         "name": "calculate",
    #         "description": "Perform a calculation",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "expression": {
    #                     "type": "string",
    #                     "description": "The mathematical expression to evaluate"
    #                 }
    #             },
    #             "required": ["expression"]
    #         }
    #     }
    # }
    
    # tools = [weather_tool, calculator_tool]
    
    # Text-only example with tools
    # print("Text-only example with tools:")
    # completion = await model.generate(
    #     messages=[{"role": "user", "content": "What's the weather like in San Francisco?"}],
    #     tools=tools
    # )
    # print(json.dumps(completion.model_dump(), indent=2))
    
    # # Multimodal example with tools
    # print("\nMultimodal example with tools:")
    # completion = await model.generate(
    #     messages=[{
    #         "role": "user", 
    #         "content": [
    #             {"type": "text", "text": "What can you see in this image? Also, calculate 15 * 37."},
    #             {"type": "image_url", "image_url": {"url": "path/to/your/image.jpg"}}
    #         ]
    #     }],
    #     tools=tools
    # )
    # print(json.dumps(completion.model_dump(), indent=2))
    
    # Streaming example with tools
    async for chunk in model.stream(
        messages=[{"role": "user", "content": "Calculate 123 * 456"}],
        # tools=tools
    ):
        print(chunk)
    
    # response = await model.generate(messages=[{"role": "user", "content": "Calculate 123 * 456"}])
    # print(response)
    

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())