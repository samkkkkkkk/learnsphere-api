# app/crud/crud_learning.py
"""학습 매니저(목표/일정) CRUD.

진도율은 저장하지 않는다 — get_goal_stats가 조회 시점에 완료 비율을 집계한다.
"""
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from ..models.models import LearningGoal


# --- 목표 ---

def create_goal(db: Session, user_id: int, *, title: str, category: str,
                deadline, daily_study_time: int,
                description: Optional[str] = None,
                linked_level: Optional[str] = None) -> LearningGoal:
    goal = LearningGoal(
        user_id=user_id, title=title, category=category, deadline=deadline,
        daily_study_time=daily_study_time, description=description,
        linked_level=linked_level)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def list_goals(db: Session, user_id: int) -> List[LearningGoal]:
    """본인 목표만 최근 생성 순으로 반환한다."""
    return (db.query(LearningGoal)
            .filter(LearningGoal.user_id == user_id)
            .order_by(LearningGoal.id.desc())
            .all())


def get_owned_goal(db: Session, goal_id: int,
                   user_id: int) -> Optional[LearningGoal]:
    """소유자가 일치하는 목표만 돌려준다. 남의 목표는 None."""
    return (db.query(LearningGoal)
            .filter(LearningGoal.id == goal_id, LearningGoal.user_id == user_id)
            .first())


def update_goal(db: Session, goal: LearningGoal,
                fields: Dict) -> LearningGoal:
    """보낸 필드만 반영한다 (PATCH)."""
    for key, value in fields.items():
        setattr(goal, key, value)
    db.commit()
    db.refresh(goal)
    return goal


def delete_goal(db: Session, goal: LearningGoal) -> None:
    db.delete(goal)  # 일정은 cascade로 함께 삭제
    db.commit()


# --- 진도율 집계 ---

def get_goal_stats(db: Session, user_id: int) -> Dict[int, Dict[str, int]]:
    """goal_id별 진도 근거 수치를 한 번에 집계한다 (N+1 방지).

    반환: {goal_id: {schedule_done, schedule_total, lesson_done, lesson_total}}
    이 시점(P1)에는 일정 테이블이 비어 있으므로 전부 0이다. P2에서 일정 집계,
    P8에서 연결 레벨 레슨 집계가 붙는다.
    """
    stats: Dict[int, Dict[str, int]] = {}
    for goal in list_goals(db, user_id):
        stats[goal.id] = {
            "schedule_done": 0, "schedule_total": 0,
            "lesson_done": 0, "lesson_total": 0,
        }
    return stats


def calc_progress(detail: Dict[str, int]) -> float:
    """완료 비율 기반 진도율. 분모 0이면 0.0."""
    total = detail["schedule_total"] + detail["lesson_total"]
    if total == 0:
        return 0.0
    done = detail["schedule_done"] + detail["lesson_done"]
    return round(done / total * 100, 1)
