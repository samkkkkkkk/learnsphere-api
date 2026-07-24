# app/schemas/chat.py
"""튜터 챗 요청/응답 스키마.

레슨 도메인(schemas.py)과 분리해 챗 관련 스키마만 모은다.
"""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, description="사용자 질문")


class ChatResponse(BaseModel):
    answer: str
