# app/schemas/chat.py
"""튜터 챗 요청/응답 스키마.

레슨 도메인(schemas.py)과 분리해 챗 관련 스키마만 모은다.
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    """대화 한 줄."""
    role: Literal["user", "assistant"]
    content: str


# --- 세션 ---

class SessionCreateRequest(BaseModel):
    lesson_id: Optional[int] = Field(
        default=None, description="지정 시 해당 레슨 본문을 답변 근거에 우선 포함")


class SessionOut(BaseModel):
    id: int
    title: Optional[str] = None
    lesson_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    sources: Optional[List[str]] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- 메시지 전송 ---

class MessageRequest(BaseModel):
    message: str = Field(min_length=1, description="사용자 질문")


class ChatResponse(BaseModel):
    answer: str
    sources: List[str] = Field(default_factory=list, description="답변 근거 문서 제목")
