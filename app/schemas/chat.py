# app/schemas/chat.py
"""튜터 챗 요청/응답 스키마.

레슨 도메인(schemas.py)과 분리해 챗 관련 스키마만 모은다.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    """이전 대화 한 줄. Phase 2에서는 클라이언트가 보관해 함께 보낸다."""
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, description="사용자 질문")
    history: List[ChatTurn] = Field(default_factory=list, description="이전 대화")
    lesson_id: Optional[int] = Field(
        default=None, description="지정 시 해당 레슨 본문을 답변 근거에 우선 포함")


class ChatResponse(BaseModel):
    answer: str
    sources: List[str] = Field(default_factory=list, description="답변 근거 문서 제목")
