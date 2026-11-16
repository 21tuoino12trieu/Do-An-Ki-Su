from beememory.entrypoint.schema.request_schema import (
    ChatRequestSchema, 
    ClearUserSchema,
    NewUserSchema,
    # UserInfoSchema
)
from beememory.prompt import MAIN_CHAT_SYSTEM_PROMPT
from beememory.conversation_manager.ConversationManager import ResponseGenerator
from beememory.memory_manager import MemoryManager

from beememory.constant import db, model, milvus_client

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from collections import deque
import uuid
import asyncio
import traceback
from typing import Optional
import json

app = FastAPI(
    title="Chatbot API",
    description="API endpoints for managing chat conversations and users",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8001"],  # Replace "*" with specific domains for better security
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],
    allow_credentials=True,
    )

def get_chat_history(user_id, top_n=-1):
    chat_history = db.query_message_by_user_id(user_id, top_n)
    chat_history = [{'role' : chat[0], 'content': chat[1]} for chat in chat_history]
    return chat_history

def is_user_id_exsist(user_id):
    user_info = db.query_user_by_id(user_id)
    if user_info:
        return True
    return False

response_generator = ResponseGenerator(model, db, get_chat_history)

@app.get("/healthcheck")
def read_root():
    return "ok"
    
@app.post("/chat2")
async def handle_request_2(request: ChatRequestSchema):
    
    # user_id = db.get_dialogue_id(user_id=request.user_id, character_id=request.character_id)
    user_id = request.user_id
    
    complete_response = []
    
    print("new request:", request)
    
    async def error_stream(message: str):
        yield f"data: {{'message': '{message}'}}\n\n"
        
    async def generate_stream():
        
        sys_prompt = MAIN_CHAT_SYSTEM_PROMPT
        async for chunk in response_generator.generate_response(user_id=user_id, query=request.query, sys_prompt=sys_prompt):
            yield f"data: {chunk}\n\n"
            complete_response.append(chunk)
                    
        full_response = '\n'.join(complete_response)
        db.add_message(
            user_id=user_id, 
            role="assistant", 
            content=full_response
        )
        MemoryManager.add_message(
            content=full_response,
            user_id=user_id,
            flag=MemoryManager.ALL_FLAGS,
            role="assistant"
        )
        await MemoryManager.summary_messages(
            user_id=user_id,
            top_n=4
        )
        await MemoryManager.extract_core_message(
            user_id=user_id,
            top_n_history=4,
        )            
        
    try:
        if not is_user_id_exsist(user_id):
            return StreamingResponse(
                error_stream(f"Please create user_id: {user_id}"), 
                media_type="text/event-stream"
            )
        
        db.add_message(user_id=user_id, role="user", content=request.query)
        MemoryManager.add_message(
            content=request.query, 
            user_id=user_id,
            flag=MemoryManager.ALL_FLAGS,
            role="user"
        )
        
        return StreamingResponse(generate_stream(), media_type="text/event-stream")
    
    except Exception as e:
        error_trace = traceback.format_exc()
        return StreamingResponse(
            error_stream("An error occurred processing your request"),
            media_type="text/event-stream"
        )
    
        

@app.get("/memory")
async def typing(user_id: str):
    # user_id = db.get_dialogue_id(user_id=user_id, character_id=character_id)
    
    summary_memory = db.get_summary_memory(user_id=user_id)
    core_memory = db.get_core_memory(user_id=user_id)
    
    #TODO: milvus
    archived_memory = milvus_client.get_all_user_content(user_id=user_id)
    # archived_memory = ""
    
    final_response = {
        "summary_memory": summary_memory,
        "core_memory": core_memory,
        "archived_memory": archived_memory
    }
    
    return json.dumps(final_response, indent=4)

@app.get("/chatHistory")
async def typing(user_id: str):
    # user_id = db.get_dialogue_id(user_id=user_id, character_id=character_id)
    history = get_chat_history(user_id=user_id)
    return history
    

#TODO: User feature
@app.post("/new_user")
def post(request: NewUserSchema):
    user_id = db.get_user_id(user_id=request.user_id, force_create=False)
    
    if is_user_id_exsist(user_id):
        return {"message" : f"User id {user_id} existed"}
    else:
        db.add_user(user_id)
        return {"message": "Add new user success"}

@app.get("/list_all_users")
def list_all_users() -> list[str]:
    all_users = db.query_user_by_id()
    all_user_id = [user['id'] for user in all_users]
    return all_user_id

@app.get("/clear")
def clear():
    return {"message" : "ok"}

@app.post("/clear_user")
def clear_user(request: ClearUserSchema):
    user_id = db.get_user_id(user_id=request.user_id, character_id=request.character_id, force_create=False)
    if is_user_id_exsist(user_id):   
        decoded_user_id = str(uuid.uuid4())
        db.delete_user_by_id(user_id)
        db.decode_user_id_in_chat_table(user_id,
                                        {"user_id" : decoded_user_id})
        db.decode_user_id_in_memory_summary_table(user_id,
                                        {"user_id" : decoded_user_id})
        
        MemoryManager.remove_all_messages(user_id=user_id)
        

        return "Cleared user_id successful"
    else:
        return "User id not exsisted"
    
# @app.post("/user_info")
# def user_info(request: UserInfoSchema):
#     user_i4 = db.query_user_by_id(user_id)
#     return user_i4
