# app/api/learning_api.py
"""학습 매니저 API (목표/일정).

전 엔드포인트가 학습자 JWT 인증을 요구한다. 진도율은 DB 값이 아니라
crud_learning.get_goal_stats로 조회 시점에 계산해 응답에 채운다.
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.auth import get_current_user
from ..core.database import get_db
from ..crud import crud_learning, crud_lessons
from ..models.models import LearningGoal, LearningSchedule, User
from ..schemas.learning import (
    DashboardOut, GoalCreate, GoalOut, GoalProgressDetail, GoalUpdate,
    ImportRequest, ImportResult, LessonProgressImportRequest,
    LessonProgressImportResult, LessonProgressOut, LessonProgressUpsert,
    ScheduleCreate, ScheduleOut, ScheduleUpdate,
)

router = APIRouter(prefix="/learning", tags=["Learning"])


def _require_goal(db: Session, goal_id: int, user: User) -> LearningGoal:
    """본인 목표만 통과시킨다. 남의 목표는 403."""
    goal = crud_learning.get_owned_goal(db, goal_id, user.id)
    if goal is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="접근할 수 없는 목표입니다.")
    return goal


def _to_goal_out(goal: LearningGoal, detail: dict) -> GoalOut:
    """ORM 목표 + 집계 수치를 응답 모델로 조립한다."""
    out = GoalOut.model_validate(goal)
    out.progress_detail = GoalProgressDetail(**detail)
    out.progress = crud_learning.calc_progress(detail)
    return out


_EMPTY_DETAIL = {"schedule_done": 0, "schedule_total": 0,
                 "lesson_done": 0, "lesson_total": 0}


# --- 목표 ---

@router.post("/goals", response_model=GoalOut,
             status_code=status.HTTP_201_CREATED)
def create_goal(request: GoalCreate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    goal = crud_learning.create_goal(
        db, user.id, title=request.title, category=request.category,
        deadline=request.deadline, daily_study_time=request.daily_study_time,
        description=request.description, linked_level=request.linked_level)
    return _to_goal_out(goal, dict(_EMPTY_DETAIL))


@router.get("/goals", response_model=List[GoalOut])
def list_goals(db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    stats = crud_learning.get_goal_stats(db, user.id)
    return [_to_goal_out(goal, stats.get(goal.id, dict(_EMPTY_DETAIL)))
            for goal in crud_learning.list_goals(db, user.id)]


@router.patch("/goals/{goal_id}", response_model=GoalOut)
def update_goal(goal_id: int, request: GoalUpdate,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    goal = _require_goal(db, goal_id, user)
    goal = crud_learning.update_goal(
        db, goal, request.model_dump(exclude_unset=True))
    detail = crud_learning.get_goal_stats(db, user.id).get(
        goal.id, dict(_EMPTY_DETAIL))
    return _to_goal_out(goal, detail)


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    crud_learning.delete_goal(db, _require_goal(db, goal_id, user))


# --- 일정 ---

def _require_schedule(db: Session, schedule_id: int,
                      user: User) -> LearningSchedule:
    """본인 일정만 통과시킨다. 남의 일정은 403."""
    schedule = crud_learning.get_owned_schedule(db, schedule_id, user.id)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="접근할 수 없는 일정입니다.")
    return schedule


@router.post("/schedules", response_model=ScheduleOut,
             status_code=status.HTTP_201_CREATED)
def create_schedule(request: ScheduleCreate, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    # 남의 목표에 일정을 달 수 없다
    _require_goal(db, request.goal_id, user)
    return crud_learning.create_schedule(
        db, user.id, goal_id=request.goal_id, schedule_date=request.date,
        time=request.time, content=request.content,
        duration_minutes=request.duration_minutes)


@router.get("/schedules", response_model=List[ScheduleOut])
def list_schedules(start: Optional[date] = None, end: Optional[date] = None,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    return crud_learning.list_schedules(db, user.id, start, end)


@router.patch("/schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(schedule_id: int, request: ScheduleUpdate,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    schedule = _require_schedule(db, schedule_id, user)
    return crud_learning.update_schedule(
        db, schedule, request.model_dump(exclude_unset=True))


@router.delete("/schedules/{schedule_id}",
               status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    crud_learning.delete_schedule(db, _require_schedule(db, schedule_id, user))


# --- 대시보드 ---

@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    """진도현황 탭 통계 일괄 (진도율·주간 학습·연속 학습일)."""
    return crud_learning.get_dashboard_stats(db, user.id, date.today())


# --- 레슨 퀴즈 진도 ---

@router.put("/lesson-progress/{lesson_id}", response_model=LessonProgressOut)
def upsert_lesson_progress(lesson_id: int, request: LessonProgressUpsert,
                           db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)):
    """퀴즈 진도를 저장한다 — (user, lesson)당 1행 upsert."""
    if crud_lessons.get_lesson_detail(db, lesson_id) is None:
        raise HTTPException(
            status_code=404, detail=f"레슨을 찾을 수 없습니다: {lesson_id}")
    return crud_learning.upsert_lesson_progress(
        db, user.id, lesson_id, done=request.done, correct=request.correct,
        total=request.total, completed=request.completed)


@router.get("/lesson-progress", response_model=List[LessonProgressOut])
def list_lesson_progress(db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)):
    return crud_learning.list_lesson_progress(db, user.id)


@router.post("/lesson-progress/import",
             response_model=LessonProgressImportResult)
def import_lesson_progress(request: LessonProgressImportRequest,
                           db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)):
    """localStorage의 퀴즈 기록을 한 번에 이관한다. 없는 레슨은 건너뛴다."""
    index = crud_lessons.get_lesson_index(db)
    valid_ids = {lesson["id"] for lessons in index.values()
                 for lesson in lessons}
    return crud_learning.import_lesson_progress(
        db, user.id, request.items, valid_ids)


# --- 로컬 데이터 이관 ---

@router.post("/import", response_model=ImportResult)
def import_local_data(request: ImportRequest, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """localStorage에 있던 목표/일정을 한 번에 서버로 옮긴다 (단일 트랜잭션)."""
    return crud_learning.import_local_data(
        db, user.id, request.goals, request.schedules)
