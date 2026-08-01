# tests/test_pipeline_db.py
"""생성 파이프라인 DB 전환 테스트 (qdrant/openai 모킹 e2e)."""
import pytest

from app.crud import crud_lessons as crud
from app.models.models import LessonVersion
from app.services import content_pipeline_service as pipeline
from app.services.openai_service import LessonGenerationError


def make_content(title, level="초급"):
    return {
        "title": title,
        "level": level,
        "core_concepts": "핵심 개념",
        "code_examples": [{"description": "예시", "code": "code"}],
        "quizzes": [{"question": "q", "answer": "a"}],
    }


@pytest.fixture()
def pipeline_db(db_session, monkeypatch):
    """파이프라인이 BackgroundTask에서 여는 세션을 테스트 세션으로 고정."""
    monkeypatch.setattr(pipeline, "SessionLocal", lambda: db_session)
    return db_session


def mock_qdrant(monkeypatch, topics_by_level):
    monkeypatch.setattr(pipeline.qdrant_service, "get_contexts_by_level",
                        lambda level: topics_by_level.get(level, {}))


def seed_previous_generation(db, topics):
    generation = crud.create_generation(db, source="import")
    for i, (level, topic, title) in enumerate(topics, 1):
        lesson = crud.upsert_lesson(db, level, crud.slugify(topic), topic)
        crud.insert_version(db, lesson, generation.id, make_content(title, level), position=i)
    db.commit()
    crud.finalize_generation(db, generation.id)


def test_pipeline_success_switches_generation(pipeline_db, monkeypatch):
    seed_previous_generation(pipeline_db, [("초급", "Topic A", "A v1")])
    mock_qdrant(monkeypatch, {"초급": {"Topic A": "ctx"}})
    monkeypatch.setattr(pipeline.openai_service, "generate_lesson_with_llm",
                        lambda level, topic, ctx: make_content(f"{topic} v2", level))

    generation = crud.create_generation(pipeline_db, source="pipeline")
    pipeline.run_full_content_generation(generation.id)

    assert crud.get_generation(pipeline_db, generation.id).status == "completed"
    index = crud.get_lesson_index(pipeline_db)
    assert [l["title"] for l in index["초급"]] == ["Topic A v2"]


def test_pipeline_partial_failure_keeps_old_version(pipeline_db, monkeypatch):
    seed_previous_generation(pipeline_db, [
        ("초급", "Good Topic", "Good v1"),
        ("초급", "Bad Topic", "Bad v1"),
    ])
    mock_qdrant(monkeypatch, {"초급": {"Good Topic": "ctx", "Bad Topic": "ctx"}})

    def fake_llm(level, topic, ctx):
        if topic == "Bad Topic":
            raise LessonGenerationError("스키마 불일치")
        return make_content(f"{topic} v2", level)

    monkeypatch.setattr(pipeline.openai_service, "generate_lesson_with_llm", fake_llm)

    generation = crud.create_generation(pipeline_db, source="pipeline")
    pipeline.run_full_content_generation(generation.id)

    result = crud.get_generation(pipeline_db, generation.id)
    assert result.status == "completed"
    assert result.succeeded == 1
    assert result.failed_topics == [
        {"level": "초급", "topic": "Bad Topic", "error": "스키마 불일치"}]
    # 실패 토픽은 구버전 유지, 성공 토픽은 신버전
    titles = {l["title"] for l in crud.get_lesson_index(pipeline_db)["초급"]}
    assert titles == {"Good Topic v2", "Bad v1"}
    # 실패 토픽의 버전이 저장되지 않았는지 (에러 삼킴 회귀 방지)
    assert pipeline_db.query(LessonVersion).filter(
        LessonVersion.generation_id == generation.id).count() == 1


def test_pipeline_total_failure_marks_failed_and_keeps_current(pipeline_db, monkeypatch):
    seed_previous_generation(pipeline_db, [("초급", "Stable", "V1")])

    def broken_qdrant(level):
        raise RuntimeError("Qdrant 연결 실패")

    monkeypatch.setattr(pipeline.qdrant_service, "get_contexts_by_level", broken_qdrant)

    generation_id = crud.create_generation(pipeline_db, source="pipeline").id
    pipeline.run_full_content_generation(generation_id)

    assert crud.get_generation(pipeline_db, generation_id).status == "failed"
    assert [l["title"] for l in crud.get_lesson_index(pipeline_db)["초급"]] == ["V1"]


# --- API 트리거 ---

ADMIN_HEADERS = {"X-Admin-API-Key": "test-admin-key"}


def test_generate_endpoint_returns_generation_id(client, db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "run_full_content_generation",
                        lambda generation_id: calls.append(generation_id))

    response = client.post("/api/v1/admin/generate-all-content", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    generation_id = response.json()["generation_id"]
    assert calls == [generation_id]


def test_generate_endpoint_conflict_while_running(client, db_session, monkeypatch):
    monkeypatch.setattr(pipeline, "run_full_content_generation", lambda generation_id: None)
    first = client.post("/api/v1/admin/generate-all-content", headers=ADMIN_HEADERS)
    assert first.status_code == 200
    # no-op 태스크라 세대가 running으로 남음 → 중복 트리거는 409
    second = client.post("/api/v1/admin/generate-all-content", headers=ADMIN_HEADERS)
    assert second.status_code == 409


def test_generate_endpoint_requires_admin_key(client):
    assert client.post("/api/v1/admin/generate-all-content").status_code == 401
