from pydantic import BaseModel
from typing import Optional

class ChatRequestSchema(BaseModel):
    query: str
    user_id: str
    # character_id: Optional[str] = None

class ClearUserSchema(BaseModel):
    user_id: str
    # character_id: Optional[str] = None

class NewUserSchema(BaseModel):
    user_id: str
    # character_id: Optional[str] = None

# class UserInfoSchema(BaseModel):
#     user_id: str