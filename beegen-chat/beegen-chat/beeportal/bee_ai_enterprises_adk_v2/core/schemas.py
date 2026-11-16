from typing import Literal
from pydantic import BaseModel, Field

class ChatTurn(BaseModel):
    role: Literal["user", "model"]
    text: str

class MainVerdict(BaseModel):
    needs_review: bool = Field(description="False nếu là câu chào hỏi, cảm ơn cơ bản không cần duyệt. True nếu có thông tin nghiệp vụ cần duyệt.")
    answer: str = Field(description="Câu trả lời gửi cho người dùng hoặc để ReviewerAgent duyệt.")

class MainInput(BaseModel):
    user_query: str
    conversation_history: list[ChatTurn] = Field(default_factory=list)
    previous_draft: str | None = None
    review_feedback: str | None = None
    evidence: str = ""
    instruction: str | None = None
    user_context: str = ""  # injected from mem0 long-term memory

class ReviewInput(BaseModel):
    user_query: str
    conversation_history: list[ChatTurn] = Field(default_factory=list)
    previous_draft: str | None = None
    review_feedback: str | None = None
    evidence: str
    iteration: int
    is_final_iteration: bool = False

class ReviewVerdict(BaseModel):
    status: Literal["PASS", "REVISE", "ASK_BACK"]
    supported_claims: str = ""
    unsupported_claims: str = ""
    issues: str = ""
    recommendations: str = ""
    ask_back_question: str = ""
    action_plan: str = ""
