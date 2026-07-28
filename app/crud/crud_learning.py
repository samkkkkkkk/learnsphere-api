# app/crud/crud_learning.py
"""학습 매니저(목표/일정) CRUD.

진도율은 저장하지 않는다 — get_goal_stats가 조회 시점에 완료 비율을 집계한다.
"""
from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..models.models import LearningGoal, LearningSchedule


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


# --- 일정 ---

def create_schedule(db: Session, user_id: int, *, goal_id: int,
                    schedule_date: date, time: str, content: str,
                    duration_minutes: int,
                    completed: bool = False) -> LearningSchedule:
    schedule = LearningSchedule(
        user_id=user_id, goal_id=goal_id, date=schedule_date, time=time,
        content=content, duration_minutes=duration_minutes,
        completed=completed,
        completed_at=datetime.now() if completed else None)
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def list_schedules(db: Session, user_id: int, start: Optional[date] = None,
                   end: Optional[date] = None) -> List[LearningSchedule]:
    """본인 일정을 날짜 범위로 조회한다 (주간/월간 공용)."""
    query = (db.query(LearningSchedule)
             .filter(LearningSchedule.user_id == user_id))
    if start is not None:
        query = query.filter(LearningSchedule.date >= start)
    if end is not None:
        query = query.filter(LearningSchedule.date <= end)
    return query.order_by(LearningSchedule.date,
                          LearningSchedule.time,
                          LearningSchedule.id).all()


def get_owned_schedule(db: Session, schedule_id: int,
                       user_id: int) -> Optional[LearningSchedule]:
    """소유자가 일치하는 일정만 돌려준다. 남의 일정은 None."""
    return (db.query(LearningSchedule)
            .filter(LearningSchedule.id == schedule_id,
                    LearningSchedule.user_id == user_id)
            .first())


def update_schedule(db: Session, schedule: LearningSchedule,
                    fields: Dict) -> LearningSchedule:
    """보낸 필드만 반영한다. completed 전환 시 completed_at을 함께 관리한다."""
    completed = fields.pop("completed", None)
    if completed is not None and completed != schedule.completed:
        schedule.completed = completed
        schedule.completed_at = datetime.now() if completed else None

    for key, value in fields.items():
        setattr(schedule, key, value)
    db.commit()
    db.refresh(schedule)
    return schedule


def delete_schedule(db: Session, schedule: LearningSchedule) -> None:
    db.delete(schedule)
    db.commit()


# --- 로컬 데이터 이관 ---

def import_local_data(db: Session, user_id: int, goals, schedules
                      ) -> Dict[str, int]:
    """localStorage 데이터를 한 트랜잭션으로 이관한다.

    goals의 local_id → 신규 id 매핑으로 일정을 연결하고, 매핑이 없는
    일정은 건너뛴 수만 보고한다. 커밋은 마지막에 1회 — 중간 실패 시
    아무것도 남지 않아 재시도가 안전하다.
    """
    id_map: Dict[int, int] = {}
    for item in goals:
        goal = LearningGoal(
            user_id=user_id, title=item.title, category=item.category,
            deadline=item.deadline, daily_study_time=item.daily_study_time,
            description=item.description)
        db.add(goal)
        db.flush()  # 신규 id 확보 (커밋 아님)
        id_map[item.local_id] = goal.id

    schedules_created = 0
    schedules_skipped = 0
    for item in schedules:
        goal_id = id_map.get(item.local_goal_id)
        if goal_id is None:
            schedules_skipped += 1
            continue
        db.add(LearningSchedule(
            user_id=user_id, goal_id=goal_id, date=item.date, time=item.time,
            content=item.content, duration_minutes=item.duration_minutes,
            completed=item.completed,
            completed_at=datetime.now() if item.completed else None))
        schedules_created += 1

    db.commit()
    return {
        "goals_created": len(goals),
        "schedules_created": schedules_created,
        "schedules_skipped": schedules_skipped,
    }


# --- 진도율 집계 ---

def get_goal_stats(db: Session, user_id: int) -> Dict[int, Dict[str, int]]:
    """goal_id별 진도 근거 수치를 한 번에 집계한다 (N+1 방지).

    반환: {goal_id: {schedule_done, schedule_total, lesson_done, lesson_total}}
    일정은 group by 1쿼리로 집계한다. lesson_*은 P8(목표-레벨 연결)에서 붙는다.
    """
    rows = (db.query(
                LearningSchedule.goal_id,
                func.count(LearningSchedule.id),
                func.sum(case((LearningSchedule.completed, 1), else_=0)))
            .filter(LearningSchedule.user_id == user_id)
            .group_by(LearningSchedule.goal_id)
            .all())
    by_goal = {goal_id: (total, int(done or 0)) for goal_id, total, done in rows}

    stats: Dict[int, Dict[str, int]] = {}
    for goal in list_goals(db, user_id):
        total, done = by_goal.get(goal.id, (0, 0))
        stats[goal.id] = {
            "schedule_done": done, "schedule_total": total,
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
