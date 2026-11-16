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
from beegenerate.loggings.loggers import lf
from beegenerate.llms.core_v2.factory import LLMFactory
from enum import Enum
import time
import uuid
from langfuse.decorators import observe, langfuse_context


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
        self._primary = LLMFactory.create(config=primary_config)

        self._config_store = config_store or MongoStorage.default()
        self._max_retries = max_retries

    def _get_fallback_config(self) -> LLMConfig:
        """Fetch latest fallback config from store."""
        for config_dict in self._config_store.find(
            collection_name="beegen_configurations",
            query={"type": "LLM"}
        ):
            config = LLMConfig.create_config(config_dict['config'])
            if self._primary.config.api_type != config.api_type:
                return config

        raise NoFallbackError("No fallback configuration available")

    @observe(name="LLMExecutor", as_type='generation')
    async def run(
        self,
        messages: List[ChatCompletionMessageParam],
        **kwargs
    ) -> AsyncStream[ChatCompletionChunk]:  # type: ignore
        """Execute LLM operation with fallback handling."""
        # LOGGER.info(f"Messages = {messages}")
        # LOGGER.info(f"Config = {self._primary.config}")

        # Config model context
        config = self._primary.config.completion.model_dump()
        model_name = self._primary.config.model or ""

        langfuse_context.update_current_observation(
            model_parameters=config,
            model=str(model_name),
            input=messages
        )
        final_response = ""
        stop_stream = False
        try:
            async for chunk in self._process_stream(
                self._primary.stream(messages, **kwargs)
            ):
                if not (hasattr(chunk, 'choices') and chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta and chunk.choices[0].delta.content):
                    continue
                if not stop_stream:
                    final_response += str(chunk.choices[0].delta.content)
                    if chunk.choices[0].finish_reason == "stop":
                        stop_stream = True
                else:
                    langfuse_context.update_current_observation(
                        usage_details=chunk.usage,
                    )
                yield chunk

                if stop_stream:
                    if final_response.endswith('None'):
                        langfuse_context.update_current_observation(
                            output=final_response[:-4]
                        )
        except Exception as primary_error:
            import traceback
            LOGGER.error(f"Primary LLM failed: {traceback.format_exc()}")
            langfuse_context.client_instance.span(trace_id=langfuse_context.get_current_trace_id(),
                                                  parent_observation_id=langfuse_context.get_current_observation_id(),
                                                  level="ERROR", output=traceback.format_exc()).end()
            try:
                # create fallback llm
                fallback = LLMFactory.create(config=self._get_fallback_config())
                # yield an error chunk to remind FE of error
                async for chunk in self._process_stream(
                    fallback.stream(messages, **kwargs),
                    error_occurred=True
                ):
                    if not stop_stream:
                        final_response += str(chunk.choices[0].delta.content)
                        if chunk.choices[0].finish_reason == "stop":
                            stop_stream = True
                    else:
                        langfuse_context.update_current_observation(
                            usage_details=chunk.usage,
                        )
                    yield chunk

                    if stop_stream:
                        if final_response.endswith('None'):
                            langfuse_context.update_current_observation(
                                output=final_response[:-4],
                                metadata={
                                    "fallback": {
                                        "reason": primary_error,
                                        "traceback": traceback.format_exc()
                                    }
                                }
                            )
            except Exception as fallback_error:
                # totally error, return the error default message
                LOGGER.error(f"Fallback LLM failed: {str(fallback_error)}")
                langfuse_context.client_instance.span(trace_id=langfuse_context.get_current_trace_id(),
                                                      parent_observation_id=langfuse_context.get_current_observation_id(),
                                                      level="ERROR", output=traceback.format_exc()).end()
                async for chunk in self._process_stream(
                    simulate_error_streaming(),
                    error_occurred=True
                ):
                    if not stop_stream:
                        final_response += str(chunk.choices[0].delta.content)
                        if chunk.choices[0].finish_reason == "stop":
                            stop_stream = True
                    else:
                        langfuse_context.update_current_observation(
                            usage_details=chunk.usage,
                        )
                    yield chunk

                    if stop_stream:
                        if final_response.endswith('None'):
                            langfuse_context.update_current_observation(
                                output=final_response[:-4],
                                metadata={
                                    "fallback": {
                                        "reason": fallback_error,
                                        "traceback": traceback.format_exc()
                                    }
                                }
                            )

    async def _process_stream(
        self,
        stream: AsyncStream[ChatCompletionChunk],
        error_occurred: bool = False
    ) -> AsyncStream[ChatCompletionChunk]:  # type: ignore
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

    async def health_check(self) -> Dict[str, Union[bool, str]]:
        """Check if LLM services are healthy.

        Returns:
            Dict containing health status and any error messages
        """
        status = {
            "primary_healthy": False,
            "fallback_healthy": None,
            "error": None
        }

        try:
            # Check primary LLM with non-streaming mode for quick check
            async for _ in self._primary.stream(
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1
            ):
                pass
            status["primary_healthy"] = True

        except Exception as e:
            LOGGER.info(f"got error: {str(e)}")
            # Test fallback if primary failed
            if not status["primary_healthy"]:
                try:
                    fallback_config = self._get_fallback_config()
                    fallback = LLMFactory.create(config=fallback_config)
                    async for _ in fallback.stream(
                        messages=[{"role": "user", "content": "test"}],
                        max_tokens=1
                    ):
                        pass
                    status["fallback_healthy"] = True
                except Exception as e:
                    status["fallback_healthy"] = False
                    status["error"] = str(e)

        return status


async def main():

    from beegenerate.const import BEEGEN_ROOT

    """Example usage of LLMExecutor."""
    try:
        primary_config = LLMConfig.from_yaml_file(BEEGEN_ROOT / "config/llms/beegen_v1.yaml")
        print(primary_config.model_dump_json(indent=2))
        llm = LLMExecutor(
            primary_config=primary_config
        )

        # Example: Streaming mode
        async for chunk in llm.run(
            messages=[{'role': 'user', 'content': 'xin chào'}],
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
