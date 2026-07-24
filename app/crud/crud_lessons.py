# app/crud/crud_lessons.py
"""레슨 세대/버전 CRUD.

저장 모델: lessons(정체성) × lesson_generations(세대) → lesson_versions(불변 본문).
활성 본문은 lesson_versions.is_current=True 하나뿐이며(partial unique index),
전환(finalize/restore/activate)은 항상 "기존 current 해제 → 새 current 지정" 순서의
단일 트랜잭션으로 수행한다.
"""
import re
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from ..models.models import Lesson, LessonGeneration, LessonVersion


def slugify(topic: str) -> str:
    """기존 파일명 규칙(content_pipeline_service의 safe_title)과 동일한 정규화 + lowercase."""
    safe = re.sub(r'[^\w\s-]', '', topic).strip()
    safe = re.sub(r'[-\s]+', '-', safe)
    return safe.lower()


# --- 세대(generation) ---

def get_running_generation(db: Session) -> Optional[LessonGeneration]:
    return db.query(LessonGeneration).filter(LessonGeneration.status == 'running').first()


def create_generation(db: Session, source: str, created_by: str = None,
                      prompt: str = None, params: dict = None) -> LessonGeneration:
    generation = LessonGeneration(
        source=source, status='running',
        created_by=created_by, prompt=prompt, params=params,
        started_at=datetime.now(),
    )
    db.add(generation)
    db.commit()
    db.refresh(generation)
    return generation


def get_generations(db: Session) -> List[LessonGeneration]:
    return db.query(LessonGeneration).order_by(LessonGeneration.id.desc()).all()


def get_generation(db: Session, generation_id: int) -> Optional[LessonGeneration]:
    return db.get(LessonGeneration, generation_id)


def fail_generation(db: Session, generation_id: int, error: str = None) -> None:
    generation = db.get(LessonGeneration, generation_id)
    if generation is None:
        return
    generation.status = 'failed'
    generation.completed_at = datetime.now()
    if error:
        generation.failed_topics = (generation.failed_topics or []) + [{"error": error}]
    db.commit()


# --- 레슨/버전 적재 (세대 진행 중, is_current 미변경) ---

def upsert_lesson(db: Session, level: str, slug: str, topic: str = None) -> Lesson:
    """(level, slug)로 레슨을 찾고 없으면 생성. commit은 호출자 몫."""
    lesson = db.query(Lesson).filter(Lesson.level == level, Lesson.slug == slug).first()
    if lesson is None:
        lesson = Lesson(level=level, slug=slug, topic=topic, created_at=datetime.now())
        db.add(lesson)
        db.flush()  # id 확보
    elif topic and lesson.topic != topic:
        lesson.topic = topic
    return lesson


def insert_version(db: Session, lesson: Lesson, generation_id: int,
                   content: dict, position: int = None) -> LessonVersion:
    """검증된 본문(dict: LessonContentSchema 형태)을 비활성 버전으로 적재. commit은 호출자 몫."""
    version = LessonVersion(
        lesson_id=lesson.id,
        generation_id=generation_id,
        title=content['title'],
        position=position,
        core_concepts=content['core_concepts'],
        code_examples=content['code_examples'],
        quizzes=content['quizzes'],
        is_current=False,
        created_at=datetime.now(),
    )
    db.add(version)
    db.flush()
    return version


# --- 세대 전환 ---

def finalize_generation(db: Session, generation_id: int, failed_topics: list = None) -> LessonGeneration:
    """세대 완료: 새 버전들을 활성으로 전환하고 세대에 없는 레슨을 숨긴다 (단일 트랜잭션).

    - 새 버전이 있는 레슨: 기존 current 해제 → 새 버전 current + 숨김 해제
    - 실패 토픽(failed_topics)의 레슨: 기존 current 유지 (부분 성공 허용)
    - 둘 다 아닌 활성 레슨: archived_at 설정 (토픽이 사라진 경우)
    """
    failed_topics = failed_topics or []
    generation = db.get(LessonGeneration, generation_id)
    if generation is None:
        raise ValueError(f"generation {generation_id}이(가) 존재하지 않습니다.")

    new_versions = db.query(LessonVersion).filter(
        LessonVersion.generation_id == generation_id).all()
    lesson_ids = [v.lesson_id for v in new_versions]
    now = datetime.now()

    if lesson_ids:
        db.query(LessonVersion).filter(
            LessonVersion.lesson_id.in_(lesson_ids),
            LessonVersion.is_current.is_(True),
        ).update({LessonVersion.is_current: False}, synchronize_session=False)
        db.flush()
        db.query(LessonVersion).filter(
            LessonVersion.generation_id == generation_id,
        ).update({LessonVersion.is_current: True}, synchronize_session=False)
        db.query(Lesson).filter(
            Lesson.id.in_(lesson_ids),
            Lesson.archived_at.isnot(None),
        ).update({Lesson.archived_at: None}, synchronize_session=False)

    failed_keys = {(f.get('level'), slugify(f.get('topic', ''))) for f in failed_topics}
    lesson_id_set = set(lesson_ids)
    for lesson in db.query(Lesson).filter(Lesson.archived_at.is_(None)).all():
        if lesson.id in lesson_id_set:
            continue
        if (lesson.level, lesson.slug) in failed_keys:
            continue
        lesson.archived_at = now

    generation.status = 'completed'
    generation.completed_at = now
    generation.succeeded = len(new_versions)
    generation.total_topics = len(new_versions) + len(failed_topics)
    generation.failed_topics = failed_topics or None
    db.commit()
    db.refresh(generation)
    return generation


def activate_generation(db: Session, generation_id: int) -> Optional[LessonGeneration]:
    """특정 세대의 버전 전체를 활성으로 일괄 전환 (단일 트랜잭션).

    대상 세대에 버전이 없는 활성 레슨은 숨기고, 버전이 있는 레슨은 숨김 해제한다.
    세대가 없으면 None, 세대에 버전이 하나도 없으면 ValueError.
    """
    generation = db.get(LessonGeneration, generation_id)
    if generation is None:
        return None
    versions = db.query(LessonVersion).filter(
        LessonVersion.generation_id == generation_id).all()
    if not versions:
        raise ValueError(f"generation {generation_id}에 전환할 버전이 없습니다.")

    lesson_ids = [v.lesson_id for v in versions]
    now = datetime.now()

    db.query(Lesson).filter(
        Lesson.archived_at.is_(None),
        ~Lesson.id.in_(lesson_ids),
    ).update({Lesson.archived_at: now}, synchronize_session=False)
    db.query(Lesson).filter(
        Lesson.id.in_(lesson_ids),
        Lesson.archived_at.isnot(None),
    ).update({Lesson.archived_at: None}, synchronize_session=False)
    db.query(LessonVersion).filter(
        LessonVersion.lesson_id.in_(lesson_ids),
        LessonVersion.is_current.is_(True),
    ).update({LessonVersion.is_current: False}, synchronize_session=False)
    db.flush()
    db.query(LessonVersion).filter(
        LessonVersion.generation_id == generation_id,
    ).update({LessonVersion.is_current: True}, synchronize_session=False)
    db.commit()
    db.refresh(generation)
    return generation


# --- 버전 조회/복원 ---

def get_versions(db: Session, lesson_id: int) -> List[LessonVersion]:
    return (db.query(LessonVersion)
            .filter(LessonVersion.lesson_id == lesson_id)
            .order_by(LessonVersion.id.desc())
            .all())


def restore_version(db: Session, lesson_id: int, version_id: int) -> Optional[LessonVersion]:
    """지정 버전을 활성으로 전환. 버전이 없거나 다른 레슨 소속이면 None."""
    version = db.get(LessonVersion, version_id)
    if version is None or version.lesson_id != lesson_id:
        return None
    db.query(LessonVersion).filter(
        LessonVersion.lesson_id == lesson_id,
        LessonVersion.is_current.is_(True),
    ).update({LessonVersion.is_current: False}, synchronize_session=False)
    db.flush()
    version.is_current = True
    lesson = db.get(Lesson, lesson_id)
    lesson.archived_at = None
    db.commit()
    db.refresh(version)
    return version


# --- 공개 조회 ---

def get_lesson_index(db: Session) -> dict:
    """{레벨: [{id, title, number}]} — 기존 index.json과 동일한 형태."""
    rows = (db.query(Lesson, LessonVersion)
            .join(LessonVersion, (LessonVersion.lesson_id == Lesson.id)
                  & LessonVersion.is_current.is_(True))
            .filter(Lesson.archived_at.is_(None))
            .order_by(Lesson.level, LessonVersion.position)
            .all())
    index = {}
    for lesson, version in rows:
        index.setdefault(lesson.level, []).append({
            'id': lesson.id,
            'title': version.title,
            'number': version.position,
        })
    return index


def get_lesson_detail(db: Session, lesson_id: int) -> Optional[dict]:
    row = (db.query(Lesson, LessonVersion)
           .join(LessonVersion, (LessonVersion.lesson_id == Lesson.id)
                 & LessonVersion.is_current.is_(True))
           .filter(Lesson.id == lesson_id, Lesson.archived_at.is_(None))
           .first())
    if row is None:
        return None
    lesson, version = row
    return {
        'id': lesson.id,
        'level': lesson.level,
        'title': version.title,
        'core_concepts': version.core_concepts,
        'code_examples': version.code_examples,
        'quizzes': version.quizzes,
        'version_id': version.id,
        'updated_at': version.created_at,
    }
