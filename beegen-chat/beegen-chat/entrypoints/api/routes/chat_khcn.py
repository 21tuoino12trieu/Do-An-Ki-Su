# """
# Chat completion endpoint routes.
# """
# from datetime import datetime
# import json
# from fastapi import APIRouter, Request, HTTPException, Depends
# from fastapi.responses import StreamingResponse

# from beegenerate.loggings import LOGGER
# from beemcp.services.manager import MCPManagerServiceDep

# from auth.middleware import verify_token
# from langfuse.decorators import observe
# from starlette.responses import StreamingResponse
# from starlette.middleware.base import BaseHTTPMiddleware
# from streaming.bridge import GeneratorEventBridge
# from streaming.context import get_current_run, get_current_thread, streaming_context
# from streaming.emitters import emitter
# from streaming.manager import stream_manager
# import uuid
# import asyncio
# from ag_ui.core import (
#     EventType, RunFinishedEvent
# )

# # Create router
# router = APIRouter(prefix="/api/v1/khcn", tags=["chat"])

# # Import BeeBankingApp for KHCN endpoint
# from beechat_khcn.app_khcn_stream import BeeBankingApp

# # Initialize BeeBankingApp instance
# app_khcn_stream = BeeBankingApp(bot_id="0dc3beb3-beae-44f4-9b98-2aa39f4373f8")


# @router.post("/chat/completion")
# @observe(name="Beegen Chat Completions KHCN")
# async def stream_khcn_response(
#         request: Request,
#         mcp_manager: MCPManagerServiceDep,
#         token: dict = Depends(verify_token)
# ):
#     """
#     KHCN-specific chat completions endpoint with AG-UI streaming.
    
#     Args:
#         request: The incoming HTTP request
#         token: The verified authentication token
        
#     Returns:
#         StreamingResponse: Server-sent events stream of response chunks
#     """
#     try:
#         data = await request.json()
#         messages = data.get("messages", [])

#         # Generate IDs
#         session_id = data.get("session_id", str(uuid.uuid4()))
#         thread_id = data.get("thread_id", str(uuid.uuid4()))
#         run_id = str(uuid.uuid4())
#         messages = data.get("messages", [])
#         role = data.get("role", None)
#         topic = data.get("topic", None)
#         metadata = data.get("metadata", None)
#         # Create streaming session
#         stream_manager.create_session(session_id, {
#             "thread_id": thread_id,
#             "run_id": run_id,
#             "metadata": {}
#         })

#         async def combined_stream_generator(request):

#             # Start processing + streaming
#             async with streaming_context(session_id, thread_id, run_id):
#                 # Background processing
#                 await emitter.emit_run_started()

#                 def get_chunk(chunk):
#                     if len(chunk.choices) > 0:
#                         if chunk.choices[0].delta.content is not None and str(chunk.choices[0].delta.content) != "":
#                             return chunk.choices[0].delta.content

#                 bridge = GeneratorEventBridge(
#                     message_id_factory=lambda: str(uuid.uuid4()),
#                     chunk_to_text=get_chunk
#                 )

#                 agen = app_khcn_stream.run(
#                     messages=messages,
#                     role_ids=role,
#                     topic=topic,
#                     metadata=metadata,
#                     aguiprotocol=True
#                 )

#                 processing_task = asyncio.create_task(bridge.run(agen))

#                 # Stream events và detect completion
#                 run_finished_received = False
#                 async for event_data in stream_manager.stream_events(session_id):

#                     if await request.is_disconnected():
#                         processing_task.cancel()
#                         break

#                     LOGGER.info(f"receive event from stream_events {event_data}")
#                     yield event_data

#                     # Parse event để detect run_finished
#                     if event_data.startswith("data: "):
#                         try:
#                             event_dict = json.loads(event_data[6:])
#                             if event_dict.get("type") == EventType.RUN_FINISHED:
#                                 run_finished_received = True
#                                 break
#                         except json.JSONDecodeError:
#                             pass

#                     # Fallback: check processing task done
#                     # if processing_task.done() and not run_finished_received:
#                     #     break

#                     if run_finished_received:
#                         break

#                 # 3. Completion signal (nếu chưa có run_finished)
#                 # if not run_finished_received:
#                 #     yield f"data: {RunFinishedEvent(
#                 #         thread_id=get_current_thread(),
#                 #         run_id=get_current_run(),
#                 #         result={"reason": "completed"},
#                 #         timestamp= int(datetime.now().timestamp())
#                 #     ).model_dump_json()}\n\n"

#                 # Wait for last event emitted
#                 stream_manager.close_session(session_id)

#         return StreamingResponse(
#             combined_stream_generator(request),
#             media_type="text/event-stream",
#             headers={
#                 "X-Session-ID": session_id,
#                 "X-Thread-ID": thread_id,
#                 "X-Run-ID": run_id,
#                 "X-AG-UI-Protocol": "1.0",
#                 "Cache-Control": "no-cache",
#                 "Connection": "keep-alive",
#                 "X-Accel-Buffering": "no"
#             }
#         )
#     except Exception as e:
#         LOGGER.error(f"Error processing KHCN request: {str(e)}")
#         raise HTTPException(
#             status_code=500,
#             detail={"error": str(e)}
#         )
