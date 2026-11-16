from abc import ABC, abstractmethod
from typing import List, AsyncGenerator
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessageParam
)
from beegenerate.configs import LLMConfig
import time
from beegenerate.loggings import LOGGER
import asyncio
import sys


def configure_event_loop():
    """Configure appropriate event loop policy based on platform."""
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    elif sys.platform.startswith(("linux", "darwin")):
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")
    
    
configure_event_loop()


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


class HTTPError(Exception):
    """Custom exception for HTTP-related errors."""
    def __init__(self, message: str, status_code: int):
        self.status_code = status_code
        super().__init__(f"{message} (Status code: {status_code})")


class BaseLLM(ABC):
    """Base class for LLM implementations (OpenAI, Azure, Gemini, etc...)"""
    
    def __init__(self, config: LLMConfig) -> None:
        """Initialize LLM with configuration."""
        self.config = config
        
    @abstractmethod
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
        pass
    
    @abstractmethod
    async def generate(
        self,
        messages: List[ChatCompletionMessageParam],
        **kwargs
    ) -> ChatCompletion:
        """Generate chat completion for a given conversation.
        
        Args:
            messages: input conversation to generate from
        """
    
    @abstractmethod
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