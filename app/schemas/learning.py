# app/schemas/learning.py
"""학습 매니저 요청/응답 스키마.

레슨(schemas.py)·챗(chat.py)과 분리해 학습 목표/일정 스키마만 모은다.
GoalOut의 progress는 DB 값이 아니라 조회 시 계산해 채운다.
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

# 목표 카테고리 (프론트 CATEGORY_MAP과 일치)
GOAL_CATEGORIES = ("programming", "design", "language", "business", "other")
# 목표에 연결할 수 있는 레슨 레벨
LESSON_LEVELS = ("초급", "중급", "고급")


# --- 목표 ---

class GoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=20)
    deadline: date
    description: Optional[str] = None
    daily_study_time: int = Field(ge=15, le=480, description="일일 학습 시간(분)")
    linked_level: Optional[str] = Field(
        default=None, description="지정 시 해당 레벨 레슨 완료가 진도에 합산")


class GoalUpdate(BaseModel):
    """PATCH 부분 수정 — 보낸 필드만 반영한다."""
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    category: Optional[str] = Field(default=None, min_length=1, max_length=20)
    deadline: Optional[date] = None
    description: Optional[str] = None
    daily_study_time: Optional[int] = Field(default=None, ge=15, le=480)
    linked_level: Optional[str] = None


class GoalProgressDetail(BaseModel):
    """진도율의 근거 수치. 프론트가 '일정 n/m + 레슨 n/m'로 표시한다."""
    schedule_done: int = 0
    schedule_total: int = 0
    lesson_done: int = 0
    lesson_total: int = 0


# --- 일정 ---

class ScheduleCreate(BaseModel):
    goal_id: int
    date: date
    time: str = Field(pattern=r"^\d{2}:\d{2}$", description='"HH:MM"')
    content: str = Field(min_length=1, max_length=255)
    duration_minutes: int = Field(ge=15, le=300)


class ScheduleUpdate(BaseModel):
    """PATCH 부분 수정 — completed 전환 시 completed_at을 서버가 관리한다."""
    date: Optional[date] = None
    time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    content: Optional[str] = Field(default=None, min_length=1, max_length=255)
    duration_minutes: Optional[int] = Field(default=None, ge=15, le=300)
    completed: Optional[bool] = None


class ScheduleOut(BaseModel):
    id: int
    goal_id: int
    date: date
    time: str
    content: str
    duration_minutes: int
    completed: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class GoalOut(BaseModel):
    id: int
    title: str
    category: str
    description: Optional[str] = None
    deadline: date
    daily_study_time: int
    linked_level: Optional[str] = None
    progress: float = 0.0
    progress_detail: GoalProgressDetail = Field(default_factory=GoalProgressDetail)
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
