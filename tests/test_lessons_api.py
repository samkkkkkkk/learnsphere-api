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


ADMIN_HEADERS = {"X-Admin-API-Key": "test-admin-key"}


def test_admin_generations_list_and_detail(client, db_session):
    seed_lessons(db_session)
    response = client.get("/api/v1/admin/generations", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["source"] == "import"
    assert body[0]["status"] == "completed"
    assert body[0]["succeeded"] == 3

    detail = client.get(f"/api/v1/admin/generations/{body[0]['id']}", headers=ADMIN_HEADERS)
    assert detail.status_code == 200
    assert detail.json()["failed_topics"] == []
    assert client.get("/api/v1/admin/generations/9999", headers=ADMIN_HEADERS).status_code == 404


def test_admin_activate_generation_switch(client, db_session):
    seed_lessons(db_session)  # gen1: 초급 2개 + 고급 1개
    gen1_id = client.get("/api/v1/admin/generations", headers=ADMIN_HEADERS).json()[0]["id"]

    # gen2: slug-1만 포함 → finalize 후 나머지 archived
    generation = crud.create_generation(db_session, source="pipeline")
    lesson = crud.upsert_lesson(db_session, "초급", "slug-1", "기초 하나")
    crud.insert_version(db_session, lesson, generation.id, make_content("기초 하나 v2"), position=1)
    db_session.commit()
    crud.finalize_generation(db_session, generation.id)
    assert [l["title"] for l in client.get("/api/v1/lessons").json()["초급"]] == ["기초 하나 v2"]

    # gen1으로 전환 → 전체 복귀
    response = client.post(f"/api/v1/admin/generations/{gen1_id}/activate", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    body = client.get("/api/v1/lessons").json()
    assert [l["title"] for l in body["초급"]] == ["기초 하나", "기초 둘"]
    assert [l["title"] for l in body["고급"]] == ["심화 하나"]

    # 빈 세대 activate → 400, 없는 세대 → 404
    empty = crud.create_generation(db_session, source="pipeline")
    assert client.post(f"/api/v1/admin/generations/{empty.id}/activate",
                       headers=ADMIN_HEADERS).status_code == 400
    assert client.post("/api/v1/admin/generations/9999/activate",
                       headers=ADMIN_HEADERS).status_code == 404


def test_admin_versions_and_restore(client, db_session):
    lessons = seed_lessons(db_session)
    lesson_id = lessons[0].id
    # 두 번째 버전 생성
    generation = crud.create_generation(db_session, source="pipeline")
    lesson = crud.upsert_lesson(db_session, "초급", "slug-1", "기초 하나")
    crud.insert_version(db_session, lesson, generation.id, make_content("기초 하나 v2"), position=1)
    db_session.commit()
    crud.finalize_generation(db_session, generation.id)

    versions = client.get(f"/api/v1/admin/lessons/{lesson_id}/versions", headers=ADMIN_HEADERS)
    assert versions.status_code == 200
    body = versions.json()
    assert len(body) == 2
    assert body[0]["is_current"] is True and body[0]["title"] == "기초 하나 v2"

    old_version_id = body[1]["version_id"]
    restore = client.post(f"/api/v1/admin/lessons/{lesson_id}/restore",
                          headers=ADMIN_HEADERS, json={"version_id": old_version_id})
    assert restore.status_code == 200
    assert client.get(f"/api/v1/lessons/{lesson_id}").json()["title"] == "기초 하나"

    # 다른 레슨의 버전 id로 복원 시도 → 404
    other_versions = client.get(f"/api/v1/admin/lessons/{lessons[1].id}/versions",
                                headers=ADMIN_HEADERS).json()
    assert client.post(f"/api/v1/admin/lessons/{lesson_id}/restore", headers=ADMIN_HEADERS,
                       json={"version_id": other_versions[0]["version_id"]}).status_code == 404
    # 버전 없는 레슨 → 404
    assert client.get("/api/v1/admin/lessons/9999/versions", headers=ADMIN_HEADERS).status_code == 404


def test_admin_endpoints_require_key(client, db_session):
    assert client.get("/api/v1/admin/generations").status_code == 401
    assert client.post("/api/v1/admin/generations/1/activate").status_code == 401
    assert client.get("/api/v1/admin/lessons/1/versions").status_code == 401
    assert client.post("/api/v1/admin/lessons/1/restore", json={"version_id": 1}).status_code == 401


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
