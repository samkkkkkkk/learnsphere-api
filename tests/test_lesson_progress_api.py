# tests/test_lesson_progress_api.py
"""레슨 퀴즈 진도 API 테스트."""
from app.crud import crud_lessons


def seed_lesson(db, title="조건부 렌더링", level="초급",
                slug="conditional-rendering"):
    """활성 버전을 가진 레슨 하나를 만든다 (test_chat_api 패턴)."""
    generation = crud_lessons.create_generation(db, source="import")
    lesson = crud_lessons.upsert_lesson(db, level, slug, title)
    crud_lessons.insert_version(db, lesson, generation.id, {
        "title": title,
        "level": level,
        "core_concepts": "조건에 따라 다른 JSX를 반환합니다.",
        "code_examples": [],
        "quizzes": [{"question": "질문?", "answer": "답변"}],
    }, position=1)
    db.commit()
    crud_lessons.finalize_generation(db, generation.id)
    return lesson


PROGRESS = {"done": 3, "correct": 2, "total": 3, "completed": True}


def test_upsert_creates_then_updates(client, auth_headers, db_session):
    from app.models.models import LessonProgress

    lesson = seed_lesson(db_session)

    response = client.put(f"/api/v1/learning/lesson-progress/{lesson.id}",
                          json=PROGRESS, headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["completed"] is True

    # 같은 (user, lesson)에 다시 PUT — 행이 늘지 않고 값만 갱신
    response = client.put(f"/api/v1/learning/lesson-progress/{lesson.id}",
                          json={"done": 1, "correct": 1, "total": 3,
                                "completed": False},
                          headers=auth_headers)
    assert response.status_code == 200
    assert db_session.query(LessonProgress).count() == 1
    stored = db_session.query(LessonProgress).one()
    assert stored.done == 1
    assert stored.completed is False


def test_upsert_unknown_lesson_404(client, auth_headers):
    response = client.put("/api/v1/learning/lesson-progress/9999",
                          json=PROGRESS, headers=auth_headers)
    assert response.status_code == 404


def test_lesson_progress_requires_auth(client, db_session):
    lesson = seed_lesson(db_session)

    response = client.put(f"/api/v1/learning/lesson-progress/{lesson.id}",
                          json=PROGRESS)
    assert response.status_code == 401

    response = client.get("/api/v1/learning/lesson-progress")
    assert response.status_code == 401


def test_retake_clears_completed_at(client, auth_headers, db_session):
    from app.models.models import LessonProgress

    lesson = seed_lesson(db_session)
    client.put(f"/api/v1/learning/lesson-progress/{lesson.id}",
               json=PROGRESS, headers=auth_headers)
    stored = db_session.query(LessonProgress).one()
    assert stored.completed_at is not None

    # '다시 풀기' — 완료 해제 시 completed_at도 비워진다
    client.put(f"/api/v1/learning/lesson-progress/{lesson.id}",
               json={"done": 0, "correct": 0, "total": 3, "completed": False},
               headers=auth_headers)
    db_session.refresh(stored)
    assert stored.completed is False
    assert stored.completed_at is None


def test_import_skips_unknown_lessons(client, auth_headers, db_session):
    lesson = seed_lesson(db_session)

    response = client.post("/api/v1/learning/lesson-progress/import", json={
        "items": [
            {"lesson_id": lesson.id, **PROGRESS},
            {"lesson_id": 9999, **PROGRESS},
        ],
    }, headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"created": 1, "updated": 0, "skipped": 1}

    listed = client.get("/api/v1/learning/lesson-progress",
                        headers=auth_headers).json()
    assert [p["lesson_id"] for p in listed] == [lesson.id]
