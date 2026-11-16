from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime

from streaming.manager import stream_manager

router = APIRouter(prefix="/api/v1", tags=["sessions"])

class SessionInfoDTO(BaseModel):
    session_id: str
    active: bool
    queue_size: int
    created_at: datetime
    metadata: dict
    event_count: int

class SessionListDTO(BaseModel):
    sessions: List[SessionInfoDTO]

@router.get("/sessions", response_model=SessionListDTO)
async def get_all_sessions_api():
    """
    Lấy thông tin của tất cả các phiên đang được quản lý.
    """
    sessions_data = stream_manager.get_all_sessions()
    # Convert created_at string to datetime objects for Pydantic validation
    for session in sessions_data:
        if "created_at" in session and isinstance(session["created_at"], str):
            session["created_at"] = datetime.fromisoformat(session["created_at"])
    return {"sessions": sessions_data}

@router.get("/sessions/{session_id}", response_model=SessionInfoDTO)
async def get_session_info_api(session_id: str):
    """
    Lấy thông tin chi tiết về một phiên cụ thể.
    """
    session_info = stream_manager.get_session_info(session_id)
    if not session_info:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Convert created_at string to datetime object for Pydantic validation
    if "created_at" in session_info and isinstance(session_info["created_at"], str):
        session_info["created_at"] = datetime.fromisoformat(session_info["created_at"])
        
    return session_info
