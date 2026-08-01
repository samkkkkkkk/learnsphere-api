# backend/app/schemas/schemas.py
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional

class LearningContentBase(BaseModel):
    title: str
    main_category: str
    sub_category: str
    topic_group: Optional[str] = None

    class Config:
        from_attributes = True # SQLAlchemy 모델과 호환되도록 설정

class SubjectBase(BaseModel):
    subject_name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


# --- 레슨 본문 (DB 이관) ---

class CodeExample(BaseModel):
    description: str
    code: str

class Quiz(BaseModel):
    question: str
    answer: str
    explanation: Optional[str] = None  # LLM이 생성하는 선택 필드 (기존 파일 33/141건에 존재)

class LessonContentSchema(BaseModel):
    """레슨 본문의 정본 스키마.

    LLM 생성 결과와 파일 import 본문을 저장 전에 검증하는 공용 게이트.
    core_concepts가 비면 에러 레슨일 가능성이 높으므로 거부한다.
    """
    title: str = Field(min_length=1)
    level: str = Field(min_length=1)
    core_concepts: str = Field(min_length=1)
    code_examples: List[CodeExample]
    quizzes: List[Quiz]

class LessonSummary(BaseModel):
    id: int
    title: str
    number: int

class LessonDetail(BaseModel):
    id: int
    level: str
    title: str
    core_concepts: str
    code_examples: List[CodeExample]
    quizzes: List[Quiz]
    version_id: int
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True