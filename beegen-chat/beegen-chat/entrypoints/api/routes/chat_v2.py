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
from beegenerate.llms.llm_executor import LLMExecutor

from auth.middleware import verify_token
from langfuse.decorators import langfuse_context, observe

# Bot ID đặc biệt – không inject bot_id vào metadata response
AIO_BOT_ID = "85e36d75-1c66-4409-aef1-ebecac1d674a"


def inject_bot_id_to_chunk(chunk_json_str: str, bot_id: str) -> str:
    """Inject bot_id vào field metadata của chunk trước khi stream về client."""
    chunk_dict = json.loads(chunk_json_str)
    chunk_dict.setdefault("metadata", {})["bot_id"] = bot_id
    return json.dumps(chunk_dict)


def extract_and_inject_bot_id(chunk_json_str: str, fallback_bot_id: str, clientMessageId: str, first_chunk: bool = False) -> str:
    """
    Extract bot_id từ metadata của chunk (do bot trả về).
    Chỉ inject bot_id khi có extracted_bot_id hoặc là chunk đầu tiên.
    """
    chunk_dict = json.loads(chunk_json_str)
    inner_metadata = chunk_dict.get("metadata", {})
    extracted_bot_id = inner_metadata.get("bot_id")
    chunk_dict.setdefault("metadata", {})["clientMessageId"] = clientMessageId

    # Ưu tiên bot_id từ bot trả về, fallback về bot_id từ request
    # Chỉ set bot_id khi có extracted_bot_id hoặc là chunk đầu tiên (first_chunk=True)
    if extracted_bot_id:
        chunk_dict.setdefault("metadata", {})["bot_id"] = extracted_bot_id
    elif first_chunk:
        chunk_dict.setdefault("metadata", {})["bot_id"] = fallback_bot_id

    return json.dumps(chunk_dict)


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
router = APIRouter(prefix="/api/v2", tags=["chat"])

@observe(name="Beegen Chat Completions V2")
async def stream_response(data: Dict[str, Any], token: dict, client_message_id: str):
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

    print(f"clientMessageId: {client_message_id}")
    
    role = data.get("role", None)
    topic = data.get("topic", None)
    username = data.get("username", None)
    metadata = data.get("metadata", None)

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
        if metadata and metadata.get('model'):
            model = metadata['model'].lower()
            if "gpt" in model:
                model = model.replace("_", "-")
                llm = LLMExecutor(
                    primary_config=doc_store.find_llm_configurations(model=model)
                )
                async for chunk in llm.run(
                    messages=messages
                ):
                    if len(chunk.choices) > 0:
                            if chunk.choices[0].delta.content is not None and str(chunk.choices[0].delta.content) != "":
                                response_text += str(chunk.choices[0].delta.content)
                                raw = chunk.json()
                                if bot_id != AIO_BOT_ID:
                                    raw = inject_bot_id_to_chunk(raw, bot_id)
                                else:
                                    raw = extract_and_inject_bot_id(raw, bot_id, first_chunk=True)
                                yield f"data: {raw}\n\n"
        else:
            # Bot không dùng mcp_manager
            is_first_chunk = True
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
                if len(chunk.choices) > 0:
                    if chunk.choices[0].delta.content is not None and str(chunk.choices[0].delta.content) != "":
                        response_text += str(chunk.choices[0].delta.content)
                        raw = chunk.json()
                        if bot_id != AIO_BOT_ID:
                            raw = inject_bot_id_to_chunk(raw, bot_id)
                        else:
                            raw = extract_and_inject_bot_id(raw, bot_id, client_message_id, first_chunk=is_first_chunk)
                            is_first_chunk = False
                        yield f"data: {raw}\n\n"

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
        yield "data: [DONE]\n\n"


@router.post("/chat/completions")
async def stream_model_response(
        request: Request,
        token: dict = Depends(verify_token),
):
    """
    OpenAI-compatible chat completions endpoint (không dùng mcp_manager).

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
        client_message_id = request.headers.get("clientmessageid")
        return StreamingResponse(
            stream_response(data, token, client_message_id),
            media_type="text/event-stream"
        )
    except Exception as e:
        LOGGER.error(f"Error processing request: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": str(e)}
        )


@router.post("/chat/completions_")
async def stream_model_response_(
    request: Request,
    token: dict = Depends(verify_token),
):
    """
    OpenAI-compatible chat completions endpoint (không dùng mcp_manager).

    Args:
        request: The incoming HTTP request
        token: The verified authentication token

    Returns:
        StreamingResponse: Server-sent events stream of response chunks
    """
    try:
        data = await request.json()
        client_message_id = request.headers.get("clientmessageid")
        return StreamingResponse(
            stream_response(data, token, client_message_id),
            media_type="text/event-stream"
        )
    except Exception as e:
        LOGGER.error(f"Error processing request: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": str(e)}
        )