from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uvicorn

# Import MessageQueue service
from beememory.message_queue.MessageQueue import MessageQueueService, Message

app = FastAPI(title="Message Queue API")
queue_service = MessageQueueService()

class MessageCreate(BaseModel):
    user_id: str
    content: str
    role: str
    flag: str

class MessageResponse(BaseModel):
    user_id: str
    content: str
    timestamp: datetime
    role: str
    flag: str

class QueueStatus(BaseModel):
    pending_count: int
    is_processing: bool
    last_error: Optional[str]

class ErrorResponse(BaseModel):
    error_type: str

@app.post("/add-message/", response_model=MessageResponse)
async def add_message(message: MessageCreate):
    new_message = Message(
        user_id=message.user_id,
        content=message.content,
        timestamp=datetime.now(),
        role=message.role,
        flag=message.flag
    )
    
    await queue_service.add_message(new_message)
    return new_message

@app.get("/queue-status/{user_id}/{flag}", response_model=QueueStatus)
async def get_queue_status(user_id: str, flag: str):
    """Get status of a specific queue"""
    status = await queue_service.get_queue_status(user_id, flag)
    return status

@app.get("/message-queue/{user_id}/{flag}", response_model=List[MessageResponse])
async def get_batch_for_processing(user_id: str, flag: str, min_size: int = 1):
    """Get all available messages if queue size >= min_size"""
    if min_size < 0:
        raise HTTPException(status_code=400, detail="min_size must be positive")
        
    batch = await queue_service.get_batch_for_processing(user_id, flag, min_size)

    return batch

@app.post("/message-queue/mark-processed/{user_id}/{flag}")
async def mark_batch_processed(user_id: str, flag: str):
    """Mark a batch as successfully processed"""
    await queue_service.mark_batch_processed(user_id, flag)
    return {"status": "success"}

@app.post("/message-queue/mark-failed/{user_id}/{flag}")
async def mark_batch_failed(user_id: str, flag: str):
    """Mark a batch as failed with error details"""
    await queue_service.handle_processing_failure(user_id, flag, "")
    return {"status": "error_handled"}

@app.get("/all_queue_stats")
async def get_all_queues_stats():
    result = await queue_service.get_all_queues_stats()
    transformed_result = {
        f"{user}_{queue_type}": stats 
        for (user, queue_type), stats in result.items()
    }
    
    return {"status": transformed_result}