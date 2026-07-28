# app/api/learning_api.py
"""학습 매니저 API (목표/일정).

전 엔드포인트가 학습자 JWT 인증을 요구한다. 진도율은 DB 값이 아니라
crud_learning.get_goal_stats로 조회 시점에 계산해 응답에 채운다.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.auth import get_current_user
from ..core.database import get_db
from ..crud import crud_learning
from ..models.models import LearningGoal, User
from ..schemas.learning import (
    GoalCreate, GoalOut, GoalProgressDetail, GoalUpdate,
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
