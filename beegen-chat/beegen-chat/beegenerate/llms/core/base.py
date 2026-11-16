from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Dict, Tuple
from openai import AsyncStream
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessageParam
)
import json
import time
import aiohttp
import asyncio
import sys
from beegenerate.llms.llm_response import stream_chunks
from beegenerate.configs import LLMConfig
from beegenerate.loggings import LOGGER


def configure_event_loop():
    """Configure appropriate event loop policy based on platform."""
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    elif sys.platform.startswith(("linux", "darwin")):
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")
    
    
configure_event_loop()


class HTTPError(Exception):
    """Custom exception for HTTP-related errors."""
    def __init__(self, message: str, status_code: int):
        self.status_code = status_code
        super().__init__(f"{message} (Status code: {status_code})")


class ContentPolicyViolation(Exception):
    """Exception raised when content violates safety policies."""
    def __init__(self, message: str = "Content policy violation"):
        super().__init__(message)
        

class PerformanceMetrics:
    """Track and log LLM performance metrics."""
    
    def __init__(self):
        self.start_time = time.time()
        self.first_token_time = None
        self.completion_tokens = 0
        self.response_text = ""

    @property
    def latency(self) -> float:
        """Time to first token in seconds."""
        if self.first_token_time is None:
            return 0
        return self.first_token_time - self.start_time

    @property
    def total_time(self) -> float:
        """Total processing time in seconds."""
        return max(time.time() - self.start_time, 0.1)  # Avoid division by zero

    @property
    def tokens_per_second(self) -> float:
        """Token processing speed."""
        return self.completion_tokens / self.total_time

    def record_first_token(self):
        """Record timestamp of first token received."""
        if self.first_token_time is None:
            self.first_token_time = time.time()

    def record_token(self, content: str):
        """Record a new token."""
        if content:
            self.response_text += content
            self.completion_tokens += 1

    def log_stats(self):
        """Log performance statistics."""
        LOGGER.info(f"Response: {self.response_text}")
        LOGGER.info("Performance Statistics:")
        LOGGER.info(f"\tCompletion tokens: {self.completion_tokens}")
        LOGGER.info(f"\tTotal time: {self.total_time:.2f}s")
        LOGGER.info(f"\tSpeed: {self.tokens_per_second:.2f} tokens/s")
        LOGGER.info(f"\tFirst token latency: {self.latency:.3f}s")
        LOGGER.info("_" * 70)


class BaseLLM(ABC):
    """Base class for LLM implementations (OpenAI, Azure, VLLM, etc..)"""
    
    def __init__(self, config: LLMConfig) -> None:
        """Initialize LLM with configuration.
        
        Args:
            config: given LLM configurations
        """
        self.config = config
        
    @abstractmethod
    def prepare_request(
        self, 
        messages: List[ChatCompletionMessageParam]
    ) -> Tuple[str, Dict, Dict]:
        """Prepare API request parameters.
        
        Args:
            messages: List of chat completion messages
            
        Returns:
            Tuple of (url, headers, request_params)
        """
        pass
    
    def _check_filter_results(self, filter_results: Dict) -> None:
        """Check content filter results against safety policies.
        
        Args:
            filter_results: Content filter results dictionary
            
        Raises:
            ContentPolicyViolation: If content violates policies
        """
        for category in ['hate', 'self_harm', 'violence', 'sexual']:
            if category in filter_results:
                if filter_results[category]['filtered']:
                    violation_type = category.replace('_', ' ').title()
                    raise ContentPolicyViolation(f"Content violated {violation_type} policy")
                
    def validate_chunk(self, chunk: ChatCompletionChunk) -> None:
        """Validate streaming response chunk against safety policies.
        
        Args:
            chunk: Response chunk to validate
            
        Raises:
            ContentPolicyViolation: If content violates policies
        """
        if not hasattr(chunk.choices[0], "content_filter_results"):
            return

        self._check_filter_results(chunk.choices[0].content_filter_results)

    def validate_completion(self, completion: ChatCompletion) -> None:
        """Validate complete response against safety policies.
        
        Args:
            completion: Complete response to validate
            
        Raises:
            ContentPolicyViolation: If content violates policies
        """
        # Check content filter results if available
        if hasattr(completion.choices[0], "content_filter_results"):
            self._check_filter_results(completion.choices[0].content_filter_results)
            
    async def stream(
        self,
        messages: List[ChatCompletionMessageParam],
        **kwargs
    ) -> AsyncGenerator[ChatCompletionChunk, None]: # type: ignore
        """Stream responses from LLM with performance tracking.
        
        Args:
            messages: Chat messages to process
            **kwargs: Additional streaming options
            
        Returns:
            AsyncGenerator[ChatCompletionChunk]: Stream of response chunks
            
        Raises:
            ConnectionError: If connection to LLM fails
            HTTPError: If server returns error status
            ContentPolicyViolation: If content violates safety policies
            TimeoutError: If request or streaming timeout occurs
        """
        if not messages:
            messages = [{'role': 'user', 'content': 'xin chào'}]
        
        LOGGER.info(f"mesages = {messages}")
            
        url, headers, params = self.prepare_request(messages)
        params['stream'] = True
        
        LOGGER.info(f"Streaming request to: {url}")
        metrics = PerformanceMetrics()
        
        # Configure timeouts
        timeout = aiohttp.ClientTimeout(
            total=None,  # No total timeout
            connect=5.0,  # Connection timeout
            sock_connect=5.0,  # Socket connect timeout
            sock_read=30.0  # Socket read timeout
        )
        
        try:
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False),
                timeout=timeout
            ) as session:
                async with session.post(
                    url=url,
                    headers=headers,
                    json=params
                ) as response:
                    if response.status != 200:
                        raise HTTPError("Request failed", response.status)
                    
                    first_chunk_received = False
                    async for chunk in stream_chunks(response, self.config.model, **kwargs):
                        if not first_chunk_received:
                            # Extend read timeout after first chunk
                            session._timeout = aiohttp.ClientTimeout(
                                total=None,
                                connect=2.0,
                                sock_connect=1.0,
                                sock_read=None  # No read timeout after first chunk
                            )
                            first_chunk_received = True
                            
                        metrics.record_first_token()
                        if chunk.choices[0].delta.content:
                            metrics.record_token(chunk.choices[0].delta.content)
                        
                        self.validate_chunk(chunk)
                        yield chunk
                        
                    metrics.log_stats()
                    
        except asyncio.TimeoutError as e:
            raise TimeoutError(f"Request timed out: {str(e)}")
        except Exception as e:
            raise ConnectionError(f"Connection failed: {str(e)}")
        
    async def generate(
        self,
        messages: List[ChatCompletionMessageParam],
        **kwargs
    ) -> ChatCompletion:
        """Generate chat completion for a given conversation.
        
        Args:
            messages: input conversation to generate from
        """
        try:
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False)
            ) as session:
                return await self._process_single(
                    messages=messages, 
                    session=session, 
                    request_id=0,
                    **kwargs
                )
        except Exception as e:
            raise ConnectionError(f"Single request failed: {str(e)}")
            
    async def generate_batch(
        self,
        batch_messages: List[List[ChatCompletionMessageParam]],
        **kwargs
    ) -> List[ChatCompletion]:
        """Generate chat completions for multiple requests in parallel batches.
        
        Args:
            batch_messages: List of request to batch process
            
        Returns:
            List[ChatCompletion]: List of complete model responses
        
        Raises:
            ConnectionError: If connection fails
            HTTPError: If server returns error status
        """
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False)
            ) as session:
                tasks = [
                    self._process_single(messages, session, i, **kwargs)
                    for i, messages in enumerate(batch_messages)
                ]
                responses = await asyncio.gather(*tasks)

                process_time = time.time() - start_time
                LOGGER.info(f"Batch processing time: {process_time:.2f}s")
                
                return responses
        except Exception as e:
            raise ConnectionError(f"Batch processing failed: {str(e)}")
        
    async def _process_single(
        self,
        messages: List[ChatCompletionMessageParam],
        session: aiohttp.ClientSession,
        request_id: int,
        **kwargs
    ) -> ChatCompletion:
        """Process a single non-streaming request.
        
        Args:
            messages: Messages to process
            session: Active HTTP session
            request_id: Request identifier for logging
        
        Returns:
            ChatCompletion: Complete response from the model
        
        Raises:
            HTTPError: If server returns error status
        """
        
        url, headers, params = self.prepare_request(messages)
        params['stream'] = False
        
        LOGGER.info(f"Processing request {request_id}")
        async with session.post(
            url=url, 
            headers=headers, 
            json=params
        ) as response:
            if response.status != 200:
                raise HTTPError("Request failed", response.status)
                
            result = await response.json()
            result.update(**kwargs)
            completion = ChatCompletion(**result)
            self.validate_completion(completion)
            return completion