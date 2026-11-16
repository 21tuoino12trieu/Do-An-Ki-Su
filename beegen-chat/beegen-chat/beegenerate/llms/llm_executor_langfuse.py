from typing import (
    Dict, 
    List, 
    AsyncIterator,
    Optional,
    Any,
    Union
)
import backoff
from openai import AsyncStream
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from beegenerate.llms.llm_response import (
    create_error_chunk,
    simulate_error_streaming,
    fake_chunk_from
)
from beegenerate.configs import LLMConfig, LLMType
from beegenerate.storage import MongoStorage
from beegenerate.loggings import LOGGER
from .core import LLMFactory, BaseLLM
from enum import Enum
import time
import uuid



from langfuse import Langfuse
from langfuse.decorators import observe, langfuse_context
from dotenv import load_dotenv
import os
from beegenerate.configs.logging.langfuse_config import LangfuseConfig

# Import Langfuse Config

langfuse_config = LangfuseConfig.default()

# Setup logging
LOGGER = setup_logger(
    name=f"beegen-core.{__name__}",
    config=LogConfig.default()
)

class LLMExecutionError(Exception):
    """Base exception for LLM execution errors."""
    pass

class ConfigurationError(LLMExecutionError):
    """Raised when there's an issue with LLM configuration."""
    pass

class NoFallbackError(LLMExecutionError):
    """Raised when no fallback configuration is available."""
    pass

class LLMExecutor:
    """Fault-tolerant LLM executor with primary/fallback capability.
    
    This class provides a robust implementation for executing LLM operations with
    automatic fallback handling and retry mechanisms. Supports streaming, non-streaming,
    and batch processing modes.
    
    Attributes:
        primary_config (LLMConfig): Configuration for primary LLM
        config_store (MongoStorage): Storage for fallback configurations
        
    Examples:
        >>> executor = LLMExecutor(primary_config=my_config)
        >>> # Streaming mode
        >>> async for chunk in executor.run(messages=messages):
        >>>     process_chunk(chunk)
        >>> # Non-streaming mode
        >>> result = await executor.run(messages=messages, mode=LLMRunMode.NONSTREAM)
        >>> # Batch mode
        >>> results = await executor.run(messages=batch_messages, mode=LLMRunMode.BATCH)
    """
    
    def __init__(
        self,
        primary_config: LLMConfig,
        config_store: Optional[MongoStorage] = None,
        max_retries: int = 3
    ) -> None:
        """Initialize the LLM executor.
        
        Args:
            primary_config: Configuration for the primary LLM
            config_store: Optional MongoDB storage for configurations
            max_retries: Maximum number of retry attempts for failed calls
        
        Raises:
            ConfigurationError: If the configuration is invalid
        """
        self._validate_config(primary_config)
        self._primary = LLMFactory.create(config=primary_config)
        self._config_store = config_store or MongoStorage.default()
        self._max_retries = max_retries

        try:
            os.environ['NO_PROXY'] = '*.mbbank.com.vn'
            print(f"Set NO_PROXY={os.environ['NO_PROXY']}")
        except Exception as e:
            print(f"Error setting NO_PROXY: {str(e)}")

        try:
            os.environ['LANGFUSE_SECRET_KEY']=langfuse_config.secret_key
            os.environ['LANGFUSE_PUBLIC_KEY']=langfuse_config.public_key
            os.environ['LANGFUSE_HOST']=langfuse_config.host
            self.langfuse = Langfuse(
                # secret_key=str(langfuse_config.secret_key),              
                # public_key=str(langfuse_config.public_key),
                # host=str(langfuse_config.host)
                secret_key=os.getenv('LANGFUSE_SECRET_KEY'),
                public_key=os.getenv('LANGFUSE_PUBLIC_KEY'),
                host=os.getenv('LANGFUSE_HOST')
            )
        except Exception as e:
            LOGGER.warning(f"Failed to initialize Langfuse: {e}")
            self.langfuse = None

    def _validate_config(self, config: LLMConfig) -> None:
        """Validate LLM configuration."""
        if not config.api_key or config.api_key == "YOUR_API_KEY":
            raise ConfigurationError("Invalid API key in configuration")
        if not config.model:
            raise ConfigurationError("Model must be specified in configuration")
        if not config.base_url:
            raise ConfigurationError("Base URL must be specified in configuration")

    def _get_fallback_config(self) -> LLMConfig:
        """Fetch latest fallback config from store."""
        for config_dict in self._config_store.find(
            collection_name="beegen_configurations",
            query={"type": "LLM"}
        ):
            config = LLMConfig(**config_dict['config'])
            if self._primary.config.api_type != config.api_type:
                self._validate_config(config)
                return config
                
        raise NoFallbackError("No fallback configuration available")
    
    def flush_langfuse(self):
        """Flush any pending Langfuse events."""
        if hasattr(self, 'langfuse') and self.langfuse:
            try:
                self.langfuse.flush()
            except Exception as e:
                LOGGER.error(f"Error flushing Langfuse: {e}")
    
    @observe(as_type="generation")
    async def run(
        self,
        messages: List[ChatCompletionMessageParam],
        **kwargs
    ) -> AsyncStream[ChatCompletionChunk]: # type: ignore
        """Execute LLM operation with fallback handling and Langfuse tracking."""
        # Update Langfuse with input information
        langfuse_context.update_current_observation(
            input=messages,
            model=self._primary.config.model,
            metadata={
                # "temperature": kwargs.get("temperature", self._primary.config.temperature),
                "temperature": kwargs.get("temperature", getattr(self._primary.config.completion, "temperature", 0)),
                "api_type": self._primary.config.api_type,
                "api_base": self._primary.config.base_url,
            }
        )
        
        # Track token usage and accumulate response
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        full_response = ""
        fallback_used = False
        
        try:
            async for chunk in self._process_stream(
                self._primary.stream(messages, **kwargs)
            ):
                # Update token usage if available in the chunk
                if hasattr(chunk, 'usage') and chunk.usage:
                    token_usage = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens
                    }
                
                # Accumulate response text if content exists
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content
                    
                # Update Langfuse with current progress
                langfuse_context.update_current_observation(
                    output=full_response,
                    usage_details={
                        "input": token_usage.get("prompt_tokens", 0),
                        "output": token_usage.get("completion_tokens", 0),
                        "total": token_usage.get("total_tokens", 0)
                    }
                )
                
                yield chunk
                
            # Final update with complete token usage after stream completes
            langfuse_context.update_current_observation(
                # status="success",
                usage_details={
                    "input": token_usage.get("prompt_tokens", 0),
                    "output": token_usage.get("completion_tokens", 0),
                    "total": token_usage.get("total_tokens", 0)
                }
            )
            
        except Exception as primary_error:
            LOGGER.error(f"Primary LLM failed: {str(primary_error)}")
            
            # Track primary failure in Langfuse
            langfuse_context.update_current_observation(
                # status="error",
                error=str(primary_error),
                metadata={"error_type": "primary_llm_failure"}
            )
            
            try:
                # create fallback llm
                fallback = LLMFactory.create(config=self._get_fallback_config())
                
                # Create a new Langfuse trace for fallback
                fallback_trace = None
                if self.langfuse:
                    fallback_trace = self.langfuse.trace(name="fallback_llm")
                    fallback_generation = fallback_trace.generation(
                        name="fallback_generation",
                        model=fallback.config.model,
                        input=messages,
                        metadata={
                            "temperature": kwargs.get("temperature", fallback.config.temperature),
                            "api_type": fallback.config.api_type,
                            "api_base": fallback.config.base_url,
                        }
                    )
                
                # Reset tracking variables for fallback
                token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                full_response = ""
                fallback_used = True
                
                # yield an error chunk to remind FE of error
                async for chunk in self._process_stream(
                    fallback.stream(messages, **kwargs),
                    error_occurred=True
                ):
                    # Track token usage for fallback
                    if hasattr(chunk, 'usage') and chunk.usage:
                        token_usage = {
                            "prompt_tokens": chunk.usage.prompt_tokens,
                            "completion_tokens": chunk.usage.completion_tokens,
                            "total_tokens": chunk.usage.total_tokens
                        }
                    
                    # Accumulate fallback response
                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        full_response += chunk.choices[0].delta.content
                    
                    # Update fallback trace if available
                    if fallback_trace and 'fallback_generation' in locals():
                        fallback_generation.update(
                            output=full_response,
                            usage={
                                "input_tokens": token_usage.get("prompt_tokens", 0),
                                "output_tokens": token_usage.get("completion_tokens", 0),
                                "total_tokens": token_usage.get("total_tokens", 0)
                            }
                        )
                    
                    yield chunk
                
                # Update main Langfuse observation with fallback info
                langfuse_context.update_current_observation(
                    metadata={"fallback_used": True, "fallback_model": fallback.config.model}
                )
                
                # Complete fallback trace
                if fallback_trace and 'fallback_generation' in locals():
                    fallback_generation.end(
                        # status="success",
                        output=full_response,
                        usage={
                            "input_tokens": token_usage.get("prompt_tokens", 0),
                            "output_tokens": token_usage.get("completion_tokens", 0),
                            "total_tokens": token_usage.get("total_tokens", 0)
                        }
                    )
                    fallback_trace.update(
                        # status="success"
                        )
                
            except Exception as fallback_error:
                # totally error, return the error default message
                LOGGER.error(f"Fallback LLM failed: {str(fallback_error)}")
                
                # Update Langfuse with fallback failure
                langfuse_context.update_current_observation(
                    # status="error",
                    error=str(fallback_error),
                    metadata={
                        "error_type": "fallback_llm_failure",
                        "primary_error": str(primary_error)
                    }
                )
                
                # Update fallback trace if it exists
                if 'fallback_trace' in locals() and fallback_trace:
                    if 'fallback_generation' in locals():
                        fallback_generation.end(status="error", error=str(fallback_error))
                    fallback_trace.update(status="error", error=str(fallback_error))
                
                async for chunk in self._process_stream(
                    simulate_error_streaming(),
                    error_occurred=True
                ):
                    yield chunk
    
    async def _process_stream(
        self, 
        stream: AsyncStream[ChatCompletionChunk],
        error_occurred: bool = False
    ) -> AsyncStream[ChatCompletionChunk]: # type: ignore
        """Process token stream from LLM response.
        
        Args:
            stream: AsyncStream of chat completion chunks
            error_occurred: Flag indicating if error recovery is in progress
            
        Yields:
            ChatCompletionChunk: Individual tokens from the stream
        """
        if error_occurred:
            # If we're in error recovery, first yield an error notification
            yield create_error_chunk()
        
        async for chunk in stream:
            yield chunk

    @observe(as_type="health_check")
    async def health_check(self) -> Dict[str, Union[bool, str]]:
        """Check if LLM services are healthy with Langfuse tracking.
        
        Returns:
            Dict containing health status and any error messages
        """
        status = {
            "primary_healthy": False,
            "fallback_healthy": None,
            "error": None
        }
        
        # Update Langfuse with health check info
        langfuse_context.update_current_observation(
            input="Health check",
            metadata={
                "primary_model": self._primary.config.model,
                "primary_api": self._primary.config.base_url
            }
        )
        
        try:
            # Check primary LLM with non-streaming mode for quick check
            async for _ in self._primary.stream(
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1
            ):
                pass
            status["primary_healthy"] = True
                
        except Exception as e:               
            LOGGER.info("got error: %s", str(e))    
            # Test fallback if primary failed
            if not status["primary_healthy"]:
                try:
                    fallback_config = self._get_fallback_config()
                    fallback = LLMFactory.create(config=fallback_config)
                    
                    # Update Langfuse with fallback info
                    langfuse_context.update_current_observation(
                        metadata={
                            "fallback_model": fallback_config.model,
                            "fallback_api": fallback_config.base_url
                        }
                    )
                    
                    async for _ in fallback.stream(
                        messages=[{"role": "user", "content": "test"}],
                        max_tokens=1
                    ):
                        pass
                    status["fallback_healthy"] = True
                    
                except Exception as e:
                    status["fallback_healthy"] = False
                    status["error"] = str(e)
                    
                    # Update Langfuse with error
                    langfuse_context.update_current_observation(
                        # status="error",
                        error=str(e)
                    )
        
        # Final update to Langfuse
        langfuse_context.update_current_observation(
            # status="success" if status["primary_healthy"] or status["fallback_healthy"] else "error",
            output=status
        )
        
        return status

async def main():
    from beegenerate.storage import BotStore
    from beegenerate.configs import MongoConfig
    
    # bot_id = "b10f0d26-4d91-47f5-8cac-034b87e42c7f"
    bot_id = "a9d0ebff-62eb-403f-9244-85a835999cf3"
    bot_store = BotStore(config=MongoConfig.default())
    bot_config = bot_store.fetch_bot_details(
        bot_id=bot_id
    )
    
    print(bot_config['llm'])
    
    """Example usage of LLMExecutor."""
    try:
        llm = LLMExecutor(
            primary_config=bot_config['llm']
        )
        
        # Check health
        health_status = await llm.health_check()
        print(f"Health Status: {health_status}")
        
        # Example: Streaming mode
        async for chunk in llm.run(
            messages=[{'role': 'user', 'content': 'you dont have to be this way'}],
            temperature=1.7
        ):
            content = chunk.choices[0].delta.content
            if content:
                print(content, end="")
            else:
                print("")
                if hasattr(chunk.choices[0], "message"):
                    print('message = ', chunk.choices[0].message)
            # print(chunk)
                
    except Exception as e:
        LOGGER.error(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())