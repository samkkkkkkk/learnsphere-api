# tests/test_lessons_crud.py
"""레슨 세대/버전 CRUD 단위 테스트 (in-memory SQLite)."""
import pytest
from sqlalchemy.exc import IntegrityError

from app.crud import crud_lessons as crud
from app.models.models import Lesson, LessonVersion


def make_content(title="Test Lesson", level="초급"):
    return {
        "title": title,
        "level": level,
        "core_concepts": "핵심 개념 설명",
        "code_examples": [{"description": "예시", "code": "console.log(1)"}],
        "quizzes": [{"question": "질문?", "answer": "답변"}],
    }


def seed_generation(db, topics, source="pipeline", failed_topics=None):
    """topics: [(level, topic, title)] → 세대 생성 + 버전 적재 + finalize."""
    generation = crud.create_generation(db, source=source)
    for i, (level, topic, title) in enumerate(topics, 1):
        lesson = crud.upsert_lesson(db, level, crud.slugify(topic), topic)
        crud.insert_version(db, lesson, generation.id, make_content(title, level), position=i)
    db.commit()
    return crud.finalize_generation(db, generation.id, failed_topics=failed_topics)


# --- slugify ---

def test_slugify_matches_file_naming_rule():
    assert crud.slugify("Your First Component") == "your-first-component"
    # 특수문자 제거 + 공백/하이픈 정규화 (기존 safe_title과 동일 규칙)
    assert crud.slugify("State: A Component's Memory") == "state-a-components-memory"


# --- upsert ---

def test_upsert_lesson_idempotent(db_session):
    first = crud.upsert_lesson(db_session, "초급", "abc", "Abc")
    db_session.commit()
    second = crud.upsert_lesson(db_session, "초급", "abc", "Abc")
    db_session.commit()
    assert first.id == second.id
    assert db_session.query(Lesson).count() == 1


def test_upsert_lesson_same_slug_different_level(db_session):
    beginner = crud.upsert_lesson(db_session, "초급", "abc", "Abc")
    advanced = crud.upsert_lesson(db_session, "고급", "abc", "Abc")
    db_session.commit()
    assert beginner.id != advanced.id


# --- 세대 전환 (원자성) ---

def test_running_generation_does_not_affect_index(db_session):
    seed_generation(db_session, [("초급", "Topic One", "V1")])
    # 새 세대를 적재만 하고 finalize 하지 않음 → 조회는 구버전 유지
    gen2 = crud.create_generation(db_session, source="pipeline")
    lesson = crud.upsert_lesson(db_session, "초급", crud.slugify("Topic One"), "Topic One")
    crud.insert_version(db_session, lesson, gen2.id, make_content("V2"), position=1)
    db_session.commit()

    index = crud.get_lesson_index(db_session)
    assert [l["title"] for l in index["초급"]] == ["V1"]

    crud.finalize_generation(db_session, gen2.id)
    index = crud.get_lesson_index(db_session)
    assert [l["title"] for l in index["초급"]] == ["V2"]


def test_finalize_archives_missing_and_keeps_failed(db_session):
    seed_generation(db_session, [
        ("초급", "Keep Me", "Keep V1"),
        ("초급", "Drop Me", "Drop V1"),
        ("중급", "Fail Me", "Fail V1"),
    ])
    gen2 = crud.create_generation(db_session, "pipeline")
    lesson = crud.upsert_lesson(db_session, "초급", crud.slugify("Keep Me"), "Keep Me")
    crud.insert_version(db_session, lesson, gen2.id, make_content("Keep V2"), position=1)
    db_session.commit()
    generation = crud.finalize_generation(
        db_session, gen2.id,
        failed_topics=[{"level": "중급", "topic": "Fail Me", "error": "LLM 오류"}],
    )

    index = crud.get_lesson_index(db_session)
    # Drop Me는 새 세대에 없고 실패 목록에도 없음 → archived로 목록에서 제외
    assert [l["title"] for l in index["초급"]] == ["Keep V2"]
    # 실패 토픽은 구버전 유지
    assert [l["title"] for l in index["중급"]] == ["Fail V1"]
    assert generation.status == "completed"
    assert generation.succeeded == 1
    assert generation.total_topics == 2


def test_failed_generation_leaves_current_untouched(db_session):
    seed_generation(db_session, [("초급", "Stable", "V1")])
    gen2 = crud.create_generation(db_session, "pipeline")
    crud.fail_generation(db_session, gen2.id, error="전체 실패")

    index = crud.get_lesson_index(db_session)
    assert [l["title"] for l in index["초급"]] == ["V1"]
    assert crud.get_generation(db_session, gen2.id).status == "failed"


# --- is_current 유일성 ---

def test_is_current_unique_constraint(db_session):
    gen1 = crud.create_generation(db_session, "pipeline")
    lesson = crud.upsert_lesson(db_session, "초급", "dup", "Dup")
    v1 = crud.insert_version(db_session, lesson, gen1.id, make_content("V1"), 1)
    v1.is_current = True
    db_session.commit()

    gen2 = crud.create_generation(db_session, "pipeline")
    v2 = crud.insert_version(db_session, lesson, gen2.id, make_content("V2"), 1)
    v2.is_current = True
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --- 복원 ---

def test_restore_version_roundtrip(db_session):
    seed_generation(db_session, [("초급", "Roundtrip", "V1")])
    lesson = db_session.query(Lesson).first()
    gen2 = crud.create_generation(db_session, "pipeline")
    crud.insert_version(db_session, lesson, gen2.id, make_content("V2"), 1)
    db_session.commit()
    crud.finalize_generation(db_session, gen2.id)

    versions = crud.get_versions(db_session, lesson.id)
    v1 = next(v for v in versions if v.title == "V1")
    v2 = next(v for v in versions if v.title == "V2")

    restored = crud.restore_version(db_session, lesson.id, v1.id)
    assert restored.is_current
    assert crud.get_lesson_detail(db_session, lesson.id)["title"] == "V1"

    # 버전은 불변이므로 다시 최신으로 왕복 가능
    crud.restore_version(db_session, lesson.id, v2.id)
    assert crud.get_lesson_detail(db_session, lesson.id)["title"] == "V2"


def test_restore_version_wrong_lesson_returns_none(db_session):
    seed_generation(db_session, [("초급", "A", "A1"), ("중급", "B", "B1")])
    lesson_a, lesson_b = db_session.query(Lesson).order_by(Lesson.id).all()
    version_b = crud.get_versions(db_session, lesson_b.id)[0]
    assert crud.restore_version(db_session, lesson_a.id, version_b.id) is None


# --- 세대 activate ---

def test_activate_generation_switches_and_unarchives(db_session):
    gen1 = seed_generation(db_session, [("초급", "A", "A1"), ("초급", "B", "B1")])
    # 두 번째 세대는 A만 포함 → B는 archived
    gen2 = crud.create_generation(db_session, "pipeline")
    lesson_a = crud.upsert_lesson(db_session, "초급", crud.slugify("A"), "A")
    crud.insert_version(db_session, lesson_a, gen2.id, make_content("A2"), 1)
    db_session.commit()
    crud.finalize_generation(db_session, gen2.id)
    assert [l["title"] for l in crud.get_lesson_index(db_session)["초급"]] == ["A2"]

    # gen1으로 전환 → B 복귀 + A는 A1로 롤백
    crud.activate_generation(db_session, gen1.id)
    titles = [l["title"] for l in crud.get_lesson_index(db_session)["초급"]]
    assert titles == ["A1", "B1"]


def test_activate_generation_without_versions_raises(db_session):
    generation = crud.create_generation(db_session, "pipeline")
    with pytest.raises(ValueError):
        crud.activate_generation(db_session, generation.id)


# --- 조회 ---

def test_lesson_index_grouping_and_order(db_session):
    seed_generation(db_session, [
        ("초급", "One", "일"),
        ("초급", "Two", "이"),
        ("고급", "Three", "삼"),
    ])
    index = crud.get_lesson_index(db_session)
    assert set(index.keys()) == {"초급", "고급"}
    assert [l["number"] for l in index["초급"]] == [1, 2]


def test_lesson_detail_not_found(db_session):
    assert crud.get_lesson_detail(db_session, 9999) is None
