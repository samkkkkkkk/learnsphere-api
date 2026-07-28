# app/crud/crud_learning.py
"""학습 매니저(목표/일정) CRUD.

진도율은 저장하지 않는다 — get_goal_stats가 조회 시점에 완료 비율을 집계한다.
"""
from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..models.models import LearningGoal, LearningSchedule, LessonProgress


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


# --- 레슨 퀴즈 진도 ---

def _apply_progress(row: LessonProgress, *, done: int, correct: int,
                    total: int, completed: bool) -> None:
    """진도 값을 반영한다. 완료가 풀리면 completed_at도 비운다."""
    row.done = done
    row.correct = correct
    row.total = total
    if completed and not row.completed:
        row.completed_at = datetime.now()
    elif not completed:
        row.completed_at = None
    row.completed = completed


def upsert_lesson_progress(db: Session, user_id: int, lesson_id: int, *,
                           done: int, correct: int, total: int,
                           completed: bool) -> LessonProgress:
    """(user, lesson)당 1행 유지 — 있으면 갱신, 없으면 생성."""
    row = (db.query(LessonProgress)
           .filter(LessonProgress.user_id == user_id,
                   LessonProgress.lesson_id == lesson_id)
           .first())
    if row is None:
        row = LessonProgress(user_id=user_id, lesson_id=lesson_id)
        db.add(row)
    _apply_progress(row, done=done, correct=correct, total=total,
                    completed=completed)
    db.commit()
    db.refresh(row)
    return row


def list_lesson_progress(db: Session, user_id: int) -> List[LessonProgress]:
    return (db.query(LessonProgress)
            .filter(LessonProgress.user_id == user_id)
            .order_by(LessonProgress.lesson_id)
            .all())


def import_lesson_progress(db: Session, user_id: int, items,
                           valid_lesson_ids) -> Dict[str, int]:
    """로컬 퀴즈 기록을 한 트랜잭션으로 이관한다.

    없는(보관 포함) 레슨은 건너뛴다. 이미 서버 기록이 있으면 갱신한다.
    """
    existing = {row.lesson_id: row for row in list_lesson_progress(db, user_id)}
    created = updated = skipped = 0

    for item in items:
        if item.lesson_id not in valid_lesson_ids:
            skipped += 1
            continue
        row = existing.get(item.lesson_id)
        if row is None:
            row = LessonProgress(user_id=user_id, lesson_id=item.lesson_id)
            db.add(row)
            existing[item.lesson_id] = row
            created += 1
        else:
            updated += 1
        _apply_progress(row, done=item.done, correct=item.correct,
                        total=item.total, completed=item.completed)

    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


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

def _level_lesson_stats(db: Session, user_id: int,
                        levels) -> Dict[str, Dict[str, int]]:
    """레벨별 (현행 레슨 수, 완료 레슨 수)를 사용자당 1회 집계한다.

    분모는 항상 현행(is_current, 미보관) 레슨 기준 — 세대 교체 후에도
    get_lesson_index와 자동으로 일관된다.
    """
    from . import crud_lessons

    index = crud_lessons.get_lesson_index(db)
    completed_ids = {
        row.lesson_id
        for row in (db.query(LessonProgress.lesson_id)
                    .filter(LessonProgress.user_id == user_id,
                            LessonProgress.completed.is_(True))
                    .all())
    }

    stats: Dict[str, Dict[str, int]] = {}
    for level in levels:
        lessons = index.get(level, [])
        stats[level] = {
            "total": len(lessons),
            "done": sum(1 for lesson in lessons
                        if lesson["id"] in completed_ids),
        }
    return stats


def get_goal_stats(db: Session, user_id: int) -> Dict[int, Dict[str, int]]:
    """goal_id별 진도 근거 수치를 한 번에 집계한다 (N+1 방지).

    반환: {goal_id: {schedule_done, schedule_total, lesson_done, lesson_total}}
    일정은 group by 1쿼리, 연결 레벨 레슨은 레벨별 1회 집계 후 분배한다.
    """
    rows = (db.query(
                LearningSchedule.goal_id,
                func.count(LearningSchedule.id),
                func.sum(case((LearningSchedule.completed, 1), else_=0)))
            .filter(LearningSchedule.user_id == user_id)
            .group_by(LearningSchedule.goal_id)
            .all())
    by_goal = {goal_id: (total, int(done or 0)) for goal_id, total, done in rows}

    goals = list_goals(db, user_id)
    linked_levels = {goal.linked_level for goal in goals if goal.linked_level}
    by_level = (_level_lesson_stats(db, user_id, linked_levels)
                if linked_levels else {})

    stats: Dict[int, Dict[str, int]] = {}
    for goal in goals:
        total, done = by_goal.get(goal.id, (0, 0))
        level_stat = by_level.get(goal.linked_level, {"total": 0, "done": 0})
        stats[goal.id] = {
            "schedule_done": done, "schedule_total": total,
            "lesson_done": level_stat["done"],
            "lesson_total": level_stat["total"],
        }
    return stats


def calc_progress(detail: Dict[str, int]) -> float:
    """완료 비율 기반 진도율. 분모 0이면 0.0."""
    total = detail["schedule_total"] + detail["lesson_total"]
    if total == 0:
        return 0.0
    done = detail["schedule_done"] + detail["lesson_done"]
    return round(done / total * 100, 1)
