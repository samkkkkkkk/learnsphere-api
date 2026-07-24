# tests/test_lessons_api.py
"""ID 기반 레슨 조회 API 테스트 (TestClient + in-memory SQLite)."""
from app.crud import crud_lessons as crud


def make_content(title="Test Lesson", level="초급"):
    return {
        "title": title,
        "level": level,
        "core_concepts": "핵심 개념 설명",
        "code_examples": [{"description": "예시", "code": "console.log(1)"}],
        "quizzes": [{"question": "질문?", "answer": "답변"}],
    }


def seed_lessons(db):
    generation = crud.create_generation(db, source="import")
    lessons = []
    for i, (level, title) in enumerate(
            [("초급", "기초 하나"), ("초급", "기초 둘"), ("고급", "심화 하나")], 1):
        lesson = crud.upsert_lesson(db, level, f"slug-{i}", title)
        crud.insert_version(db, lesson, generation.id, make_content(title, level), position=i)
        lessons.append(lesson)
    db.commit()
    crud.finalize_generation(db, generation.id)
    return lessons


def test_lessons_index_empty(client):
    response = client.get("/api/v1/lessons")
    assert response.status_code == 200
    assert response.json() == {}


def test_lessons_index_grouped(client, db_session):
    seed_lessons(db_session)
    response = client.get("/api/v1/lessons")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"초급", "고급"}
    assert [l["title"] for l in body["초급"]] == ["기초 하나", "기초 둘"]
    assert all({"id", "title", "number"} <= set(l.keys()) for l in body["초급"])


def test_lesson_detail_fields(client, db_session):
    lessons = seed_lessons(db_session)
    response = client.get(f"/api/v1/lessons/{lessons[0].id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == lessons[0].id
    assert body["level"] == "초급"
    assert body["title"] == "기초 하나"
    assert body["core_concepts"] == "핵심 개념 설명"
    assert body["code_examples"] == [{"description": "예시", "code": "console.log(1)"}]
    assert body["quizzes"] == [{"question": "질문?", "answer": "답변"}]
    assert body["version_id"] > 0


def test_lesson_detail_not_found(client):
    response = client.get("/api/v1/lessons/9999")
    assert response.status_code == 404


def test_archived_lesson_hidden(client, db_session):
    lessons = seed_lessons(db_session)
    # 새 세대에 slug-1만 포함 → slug-2, slug-3은 archived
    generation = crud.create_generation(db_session, source="pipeline")
    lesson = crud.upsert_lesson(db_session, "초급", "slug-1", "기초 하나")
    crud.insert_version(db_session, lesson, generation.id, make_content("기초 하나 v2"), position=1)
    db_session.commit()
    crud.finalize_generation(db_session, generation.id)

    body = client.get("/api/v1/lessons").json()
    assert [l["title"] for l in body.get("초급", [])] == ["기초 하나 v2"]
    assert "고급" not in body
    assert client.get(f"/api/v1/lessons/{lessons[2].id}").status_code == 404
