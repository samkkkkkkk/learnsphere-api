# app/schemas/learning.py
"""학습 매니저 요청/응답 스키마.

레슨(schemas.py)·챗(chat.py)과 분리해 학습 목표/일정 스키마만 모은다.
GoalOut의 progress는 DB 값이 아니라 조회 시 계산해 채운다.
"""
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# 'date: Optional[date] = None' 꼴은 함정이다 — 클래스 본문에서 date=None 할당이
# 어노테이션 평가보다 먼저 일어나 Optional[None]이 되어 버린다. 필드명이 date인
# 곳에서는 이 별칭을 쓴다.
DateType = date

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
    date: Optional[DateType] = None
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


# --- 대시보드 ---

class DashboardOut(BaseModel):
    overall_progress: float
    completed_goals: int
    total_goals: int
    weekly_hours: float
    # 일~토 7칸, 완료 일정의 학습 시간(시간 단위)
    weekly_pattern: List[float]
    current_streak: int
    best_streak: int


# --- AI 피드백 ---

class FeedbackRequest(BaseModel):
    feedback_type: Literal["content", "schedule", "progress", "motivation"]


class FeedbackResponse(BaseModel):
    # 마크다운 형식의 피드백 본문
    answer: str


# --- 레슨 퀴즈 진도 ---

class LessonProgressUpsert(BaseModel):
    done: int = Field(ge=0)
    correct: int = Field(ge=0)
    total: int = Field(ge=0)
    completed: bool = False


class LessonProgressOut(BaseModel):
    lesson_id: int
    done: int
    correct: int
    total: int
    completed: bool
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LessonProgressImportItem(LessonProgressUpsert):
    lesson_id: int


class LessonProgressImportRequest(BaseModel):
    items: List[LessonProgressImportItem] = Field(
        default_factory=list, max_length=500)


class LessonProgressImportResult(BaseModel):
    created: int
    updated: int
    # 존재하지 않는(또는 보관된) 레슨이라 건너뛴 수
    skipped: int


# --- 로컬 데이터 이관 ---

# 한 번에 받는 항목 수 상한 (goals/schedules 각각)
IMPORT_MAX_ITEMS = 500


class ImportGoal(BaseModel):
    """localStorage에 있던 목표 하나. local_id는 일정 연결용 임시 키다."""
    local_id: int
    title: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=20)
    deadline: date
    description: Optional[str] = None
    daily_study_time: int = Field(ge=15, le=480)


class ImportSchedule(BaseModel):
    local_goal_id: int
    date: date
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    content: str = Field(min_length=1, max_length=255)
    duration_minutes: int = Field(ge=15, le=300)
    completed: bool = False


class ImportRequest(BaseModel):
    goals: List[ImportGoal] = Field(
        default_factory=list, max_length=IMPORT_MAX_ITEMS)
    schedules: List[ImportSchedule] = Field(
        default_factory=list, max_length=IMPORT_MAX_ITEMS)


class ImportResult(BaseModel):
    goals_created: int
    schedules_created: int
    # local_goal_id가 goals에 없어 연결하지 못한 일정 수
    schedules_skipped: int


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
