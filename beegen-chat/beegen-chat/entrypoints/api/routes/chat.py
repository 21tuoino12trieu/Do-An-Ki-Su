"""
Chat completion endpoint routes.
"""
import json
import sys
import traceback
from typing import Dict, Any
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse

from beegenerate.loggings import LOGGER
from beegenerate.storage import (
    BotStore,
    DocumentStore
)
from beegenerate.vectordb import MilvusStorage
from beegenerate.configs import (
    MongoConfig,
    MilvusConfig
)
from beemcp.services.manager import MCPManagerServiceDep, MCPManagerService

from auth.middleware import verify_token
from langfuse.decorators import langfuse_context, observe

# Global service variables
bot_store = BotStore(MongoConfig.default())
vec_store = MilvusStorage(MilvusConfig.default())
doc_store = DocumentStore(MongoConfig.default())
bot_manager = {}

# Access to global bot manager
# We need to import these from server.py but import them when accessed to avoid circular imports
def get_bot_manager():
    from entrypoints.api.server import bot_manager
    return bot_manager


# Create router
router = APIRouter(prefix="/api/v1", tags=["chat"])

def _chunk_has_docs(chunk) -> bool:
    docs = getattr(chunk, "docs", None)
    if docs:
        return True

    model_extra = getattr(chunk, "model_extra", None)
    if isinstance(model_extra, dict) and model_extra.get("docs"):
        return True

    try:
        dumped = chunk.model_dump()
        return bool(dumped.get("docs"))
    except Exception:
        return False

def _chunk_finish_reason(chunk) -> str | None:
    if len(chunk.choices) == 0:
        return None
    return getattr(chunk.choices[0], "finish_reason", None)

def _chunk_content(chunk) -> str | None:
    if len(chunk.choices) == 0:
        return None
    delta = getattr(chunk.choices[0], "delta", None)
    return getattr(delta, "content", None) if delta else None

def _chunk_has_usage(chunk) -> bool:
    return getattr(chunk, "usage", None) is not None

def _chunk_to_sse_data(chunk) -> str:
    """Serialize a stream chunk without leaking null text deltas to the UI."""
    try:
        payload = chunk.model_dump(mode="json")
    except TypeError:
        payload = chunk.model_dump()
    except Exception:
        try:
            payload = json.loads(chunk.json())
        except Exception:
            return chunk.json()

    choices = payload.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if isinstance(delta, dict) and delta.get("content") is None:
                delta["content"] = ""

    return json.dumps(payload, ensure_ascii=False)

def _should_yield_chunk(chunk) -> bool:
    content = _chunk_content(chunk)
    if content is not None and str(content) != "":
        return True

    if _chunk_has_docs(chunk):
        return True

    if _chunk_has_usage(chunk):
        return True

    if _chunk_finish_reason(chunk) is not None:
        return True

    return False

@observe(name="Beegen Chat Completions")
async def stream_response(data: Dict[str, Any], mcp_manager: MCPManagerService, keycloak_token: str, token: dict, client_message_id: str):
    """
    Stream bot responses as SSE events.

    Args:
        data: Request data including messages, bot_id, role, and topic

    Yields:
        SSE formatted chunks of the response
    """
    messages = data.get("messages", [])
    bot_id = data.get("bot_id", None)
    dialogue_id = data.get("dialogueId", None)
    print(f"dialogue_id: {dialogue_id}")
    if not client_message_id:
        client_message_id = data.get("clientMessageId", None)
    
    role = data.get("role", None)
    topic = data.get("topic", None)
    username = data.get("username", None)
    metadata = data.get("metadata", None)
    print("----------------------------------")
    print(f"data: {data}")
    print(f"metadata: {metadata}")
    print("----------------------------------")
    langfuse_context.update_current_observation(
        input=messages,
        user_id=username,
        tags=[bot_id, username],
        metadata={
            "username": username,
            "bot_id": bot_id,
            "role": role,
            "topic": topic
        }
    )

    # Get bot manager lazily to avoid circular imports
    bot_manager = get_bot_manager()

    if not bot_id or bot_id not in bot_manager:
        error_msg = f"Invalid bot_id: {bot_id}"
        LOGGER.error(error_msg)
        error_json = {"error": {"message": error_msg,
                                "type": "invalid_request_error"}}
        yield f"data: {json.dumps(error_json)}\n\n"
        yield "data: [DONE]\n\n"
        return

    bot = bot_manager[bot_id]
    response_text = ""
    
    try:    
        async for chunk in bot['bot'].run(
                messages=messages,
                role_ids=role,
                topic=topic,
                metadata=metadata,
                session_id=dialogue_id,
                client_message_id=client_message_id,
                username=username,
                bot_id=bot_id
        ):
            content = _chunk_content(chunk)

            if content is not None and str(content) != "":
                response_text += str(content)

            if _should_yield_chunk(chunk):
                yield f"data: {_chunk_to_sse_data(chunk)}\n\n"

        LOGGER.info(f"Response completed for bot {bot_id}")
        LOGGER.debug(f"Final response: {response_text}")      

    except Exception as e:
        # Capture full stack trace
        exc_type, exc_value, exc_traceback = sys.exc_info()
        stack_trace = traceback.format_exception(
            exc_type,
            exc_value,
            exc_traceback
        )

        error_msg = f"Error generating response: {str(e)}"
        LOGGER.error(error_msg)
        LOGGER.error(f"Stack trace: {''.join(stack_trace)}")
        langfuse_context.client_instance.span(level="ERROR", output=str(error_msg), metadata={"stack_trace":str(stack_trace)}).end()

        # Return detailed error information including stack trace
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": error_msg,
                "error_type": exc_type.__name__ if exc_type else type(e).__name__,
                "stack_trace": stack_trace,
                "line": exc_traceback.tb_lineno if exc_traceback else None
            }
        )

    finally:
        langfuse_context.update_current_observation(output=str(response_text))
        yield "data: [DONE]\n\n"


@router.post("/chat/completions")
async def stream_model_response(
        request: Request,
        mcp_manager: MCPManagerServiceDep,
        token: dict = Depends(verify_token),
):
    """
    OpenAI-compatible chat completions endpoint.

    Args:
        request: The incoming HTTP request
        token: The verified authentication token

    Returns:
        StreamingResponse: Server-sent events stream of response chunks
    """
    try:
        data = await request.json()
        # # SIMPLE REQUEST LOGGING
        # print("🔍 REQUEST BODY:")
        # print(json.dumps(data, indent=2, ensure_ascii=False))
        # print("=" * 50)
        keycloak_token = request.headers.get("authorization")
        client_message_id = request.headers.get("clientmessageid")
        print(f"request.headers: {request.headers}")
        return StreamingResponse(
            stream_response(data, mcp_manager, keycloak_token, token, client_message_id),
            media_type="text/event-stream"
        )
    except Exception as e:
        LOGGER.error(f"Error processing request: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": str(e)}
        )


@router.post("/chat/completions_")
async def stream_model_response(
    request: Request
):
    """
    OpenAI-compatible chat completions endpoint.

    Args:
        request: The incoming HTTP request
        token: The verified authentication token

    Returns:
        StreamingResponse: Server-sent events stream of response chunks
    """
    try:
        data = await request.json()
        return StreamingResponse(
            stream_response(data),
            media_type="text/event-stream"
        )
    except Exception as e:
        LOGGER.error(f"Error processing request: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": str(e)}
        )
