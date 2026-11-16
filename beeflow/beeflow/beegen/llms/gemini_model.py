from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion import ChatCompletion
from typing import Dict, List, Tuple, AsyncGenerator, Union, Any, AsyncIterator, Optional
from .base_llm import BaseLLM
from beegen.configs import LLMConfig
from beegen.llms.response import LLMGenerator
from beegen.loggings import LOGGER
import vertexai
from vertexai.preview.generative_models import GenerativeModel, Part
from google.oauth2 import service_account
import asyncio
import json
import time
import uuid
import base64
import mimetypes


class GeminiCompatibleModel(BaseLLM):
    """Gemini compatible model backend."""
    
    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._initialize_vertex_ai()
        
    def _initialize_vertex_ai(self):
        """Initialize the Vertex AI client with proper credentials"""
        credentials = service_account.Credentials.from_service_account_info(
            self.config.model_dump()
        )
        
        vertexai.init(
            project=self.config.project_id,
            location=self.config.location,
            credentials=credentials
        )
        LOGGER.info("Initialized Vertex AI with project %s", self.config.project_id)
        
    @staticmethod
    def _get_image_from_url_or_path(image_url: Union[str, Dict]) -> Part:
        """
        Convert an image URL, path, or base64 data to Gemini Part.
        
        Args:
            image_url: Image URL, file path, or base64 data
            
        Returns:
            Gemini Part object representing the image
        """
        # Extract the URL from dict format if needed
        if isinstance(image_url, dict) and "url" in image_url:
            image_url = image_url["url"]
            
        # Handle different image source types
        if image_url.startswith("data:"):
            # It's a base64 encoded image
            mime_type = image_url.split(";")[0].split(":")[1]
            base64_data = image_url.split(",")[1]
            image_bytes = base64.b64decode(base64_data)
            return Part.from_data(mime_type=mime_type, data=image_bytes)
            
        elif image_url.startswith(("http://", "https://")):
            # It's a URL - Gemini can directly use it
            return Part.from_uri(uri=image_url)
            
        else:
            # Assume it's a file path
            mime_type = mimetypes.guess_type(image_url)[0] or "image/jpeg"
            with open(image_url, "rb") as f:
                image_bytes = f.read()
            return Part.from_data(mime_type=mime_type, data=image_bytes)
    
    @staticmethod
    def _convert_to_gemini_parts(message: Dict) -> List[Union[str, Part]]:
        """
        Convert OpenAI-compatible message to Gemini parts.
        
        Args:
            message: Message in OpenAI format
            
        Returns:
            List of parts for Gemini API
        """
        content = message.get("content", "")
        
        # Simple string content
        if isinstance(content, str):
            return [content]
            
        # Multimodal content
        if isinstance(content, list):
            parts = []
            for item in content:
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                    
                elif item.get("type") == "image_url":
                    image_url = item.get("image_url")
                    parts.append(GeminiCompatibleModel._get_image_from_url_or_path(image_url))
                    
            return parts
            
        # Fallback for unexpected formats
        return [str(content)]
    
    @staticmethod
    def _process_messages(messages: List[ChatCompletionMessageParam]) -> Tuple[str, List[Union[str, Part]]]:
        """
        Process messages for Gemini API.
        
        Args:
            messages: List of messages in OpenAI format
            
        Returns:
            Tuple of (system_prompt, conversation_parts)
        """
        system_prompt = None
        conversation_parts = []
        
        for msg in messages:
            role = msg.get("role", "user")
            
            if role == "system":
                system_prompt = msg.get("content", "")
            else:
                parts = GeminiCompatibleModel._convert_to_gemini_parts(msg)
                conversation_parts.extend(parts)
                
        return system_prompt, conversation_parts
        
    async def stream(
        self,
        messages: List[ChatCompletionMessageParam],
        **kwargs
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Stream responses from LLM with performance tracking.
        
        Args:
            messages: Chat messages to process
            **kwargs: Additional streaming options
            
        Returns:
            Stream of response chunks
        """
        # metrics = PerformanceMetrics()
        # first_chunk_received = False
        async for chunk in LLMGenerator.process(
            streamline=self._request(
                messages=messages, 
                stream=True
            ),
            model=self.config.model,
            **kwargs
        ):
            # if not first_chunk_received:
            #     first_chunk_received = True
            #     metrics.record_first_token()
            
            # if chunk.choices[0].delta.content:
            #     metrics.record_token(chunk.choices[0].delta.content)
            
            # if hasattr(chunk, "token_count"):
            #     metrics.completion_tokens = chunk.token_count
            
            yield chunk
        
        # metrics.log_stats()    
    
    async def generate(
        self,
        messages: List[ChatCompletionMessageParam],
        **kwargs
    ) -> ChatCompletion:
        """Generate chat completion for a given conversation.
        
        Args:
            messages: input conversation to generate from
        """
        # metrics = PerformanceMetrics()
        # metrics.record_first_token()
        
        result = await self._request(
            messages=messages, 
            stream=False
        ).__anext__()
        
        result.update(**kwargs)
        completion = ChatCompletion(**result)
        
        # # Record the tokens into metrics stats
        # completion_tokens = completion.usage.completion_tokens
        # for _ in range(completion_tokens):
        #     metrics.record_token("_")
            
        # metrics.response_text = completion.choices[0].message.content
        
        # metrics.log_stats()
        
        return completion
        
    async def _request(
        self,
        messages: Union[
            List[Dict[str, Any]],
            List[List[Dict[str, Any]]]
        ],
        stream:bool,
        request_id: Optional[str] = None,
    ) -> AsyncIterator:
        """
        Make requests to Gemini API, supporting both single and batch requests.
        
        Args:
            messages: Either a list of messages for a single request,
                     or a list of message lists for batch requests
            **kwargs: Additional parameters for the request
                      
        Yields:
            For stream=True: Chunks of generated content
            For stream=False: Complete response
            For batch requests: List of complete responses (stream=False)
        """
        if not request_id:
            request_id = uuid.uuid4()
            
        # Check if this is a batch request by examining the first element of messages
        is_batch = isinstance(messages, list) and messages and isinstance(messages[0], list)
        
        if is_batch:
            batch_results = []
            tasks = []
            
            for msg_set in messages:
                
                async def await_single(request_id, messages):
                    return await self._request_single(
                        request_id=request_id,
                        messages=messages,
                        stream=False
                    ).__anext__()
                
                # Create a task for each message set
                task = await_single(request_id=request_id, messages=msg_set)
                tasks.append(task)
            
            # Process all requests concurrently
            batch_results = await asyncio.gather(*tasks)
            yield batch_results
            
        else:
            # Process single request
            async for result in self._request_single(
                request_id=request_id,
                messages=messages,
                stream=stream
            ):
                yield result
                           
    async def _request_single(
        self,
        request_id: str,
        messages: List[Dict[str, Any]],
        stream: bool=False
    ) -> AsyncIterator:
        """
        Process a single request to the Gemini API.
        
        Args:
            messages: List of message dictionaries
        """
        selected_keys = ["temperature", "top_p"]  # Example keys you want
        generation_config = {k: v for k, v in self.config.completion.model_dump(exclude_none=True).items() 
                    if k in selected_keys}
        
        # Process messages for Gemini API
        system_prompt, gemini_prompt = self._process_messages(messages)
        
        
        # Initialize model with system instructions if present
        model = GenerativeModel(
            model_name=self.config.model,
            system_instruction=system_prompt
        )
        
        if stream:
            # Streaming response
            response = await model.generate_content_async(
                gemini_prompt,
                generation_config=generation_config,
                stream=True
            )
            
            async for chunk in response:
                # Yield each chunk
                if chunk.usage_metadata:
                    yield self._gemini_to_openai_chunk(
                        request_id=request_id, 
                        gemini_chunk=chunk,
                        token_count=chunk.usage_metadata.candidates_token_count
                    )
                else:
                    yield self._gemini_to_openai_chunk(
                        request_id=request_id, 
                        gemini_chunk=chunk
                    )
        else:
            # Non-streaming response            
            response = await model.generate_content_async(
                gemini_prompt,
                generation_config=generation_config,
                stream=False
            )
            
            # Yield the complete response
            yield self._gemini_to_openai_response(
                request_id=request_id, 
                gemini_response=response
            )
            
    def _gemini_to_openai_chunk(self, gemini_chunk: Any, request_id: str, **kwargs) -> Dict[str, Any]:
        """
        Convert a Gemini response chunk to OpenAI API format.
        
        Args:
            gemini_chunk: the chunk of Gemini API.
            request_id: Optional request ID to include in response
        
        Return:
            OpenAI-compatible chunk format
        """
        # Create a unique ID for this chunk
        chunk_id = f"chatcmpl-{request_id}"
        
        # Create the OpenAI compatible format
        openai_chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": self.config.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": gemini_chunk.text
                    },
                    "finish_reason": None
                }
            ]
        }
        
        openai_chunk.update(**kwargs)
        
        candidate = gemini_chunk.candidates[0]
        # If this is the final chunk, set finish_reason
        if hasattr(candidate, 'finish_reason') and candidate.finish_reason:
            openai_chunk["choices"][0]["finish_reason"] = "stop"
        
        return openai_chunk
    
    def _gemini_to_openai_response(self, gemini_response: Any, request_id: str) -> Dict[str, Any]:
        """
        Convert a complete Gemini response to OpenAI API format.
        
        Args:
            gemini_response: The complete response from Gemini API
            request_id: Optional request ID to include in response
            
        Returns:
            OpenAI-compatible response format
        """
        # Create a unique ID for this response
        response_id = f"chatcmpl-{request_id}"
        
        # Get finish reason if available
        finish_reason = "stop"
        if hasattr(gemini_response, 'finish_reason') and gemini_response.finish_reason:
            finish_reason = gemini_response.finish_reason
        
        usage = gemini_response.usage_metadata
        # Create the OpenAI compatible format
        openai_response = {
            "id": response_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.config.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": gemini_response.text
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": usage.prompt_token_count,  # Gemini doesn't provide token counts
                "completion_tokens": usage.candidates_token_count,
                "total_tokens": usage.total_token_count
            }
        }
        
        return openai_response
            

async def main():
    from beegen.const import BEEGEN_ROOT
    model = GeminiCompatibleModel(config=LLMConfig.from_yaml_file(
        BEEGEN_ROOT / "config/llms/gemini.yaml"
    ))
    
    async for chunk in  model.stream(
        messages=[{"role": "user", "content": "cuộc sống có giống cuộc đời không em ?"}],
        docs = [1, 2]
    ):
        print(chunk)
    
    # response = await model.generate(
    #     messages=[{"role": "user", "content": "xin chào"}],
    #     docs = [1, 2]
    # )
    
    # print(response)
    
    # batch_completion = await model.generate_batch(
    #     batch_messages=[
    #         [{"role": "user", "content": "xin chào"}],
    #         [{"role": "user", "content": "hi"}],
    #         [{"role": "user", "content": "nói gì ngắn gọn đi"}],
    #         [{"role": "user", "content": "xin chào"}],
    #         [{"role": "user", "content": "hi"}],
    #         [{"role": "user", "content": "nói gì ngắn gọn đi"}],
    #         [{"role": "user", "content": "xin chào"}],
    #         [{"role": "user", "content": "hi"}],
    #         [{"role": "user", "content": "nói gì ngắn gọn đi"}]
    #     ],
    #     docs = [1, 2]
    # )
    
    # print(batch_completion)
    # # Multimodal example (image + text)
    print("\nMultimodal example:")
    async for chunk in model.stream(
        messages=[{
            "role": "user", 
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {"type": "image_url", "image_url": {"url": r"C:\Users\thanglq2\Downloads\deepseek.png"}}
            ]
        }],
        docs=[1, 2]
    ):
        print(chunk)
        

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())