# tests/test_learning_api.py
"""학습 매니저 API 테스트 (목표/일정/진도율)."""
import pytest


GOAL_PAYLOAD = {
    "title": "React 마스터하기",
    "category": "programming",
    "deadline": "2026-12-31",
    "description": "훅과 상태 관리까지",
    "daily_study_time": 60,
}


def _create_goal(client, headers, **overrides):
    payload = {**GOAL_PAYLOAD, **overrides}
    response = client.post("/api/v1/learning/goals", json=payload,
                           headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def other_headers(db_session):
    """다른 학습자 계정의 Authorization 헤더 (소유권 테스트용)."""
    from app.core.auth import create_access_token
    from app.crud import crud_users

    other = crud_users.create_user(
        db_session, email="other@example.com", password="password123",
        nickname="타인")
    return {"Authorization": f"Bearer {create_access_token(other.id)}"}


# --- P1: 목표 CRUD ---

def test_create_goal_returns_progress_zero(client, auth_headers):
    goal = _create_goal(client, auth_headers)

    assert goal["title"] == GOAL_PAYLOAD["title"]
    assert goal["progress"] == 0.0
    assert goal["progress_detail"] == {
        "schedule_done": 0, "schedule_total": 0,
        "lesson_done": 0, "lesson_total": 0,
    }


def test_goal_requires_auth(client):
    response = client.post("/api/v1/learning/goals", json=GOAL_PAYLOAD)
    assert response.status_code == 401

    response = client.get("/api/v1/learning/goals")
    assert response.status_code == 401


def test_goals_scoped_to_owner(client, auth_headers, other_headers):
    _create_goal(client, auth_headers)
    _create_goal(client, other_headers, title="타인의 목표")

    response = client.get("/api/v1/learning/goals", headers=auth_headers)
    assert response.status_code == 200
    titles = [g["title"] for g in response.json()]
    assert titles == [GOAL_PAYLOAD["title"]]


def test_patch_other_users_goal_returns_403(client, auth_headers, other_headers):
    goal = _create_goal(client, auth_headers)

    response = client.patch(f"/api/v1/learning/goals/{goal['id']}",
                            json={"title": "탈취 시도"}, headers=other_headers)
    assert response.status_code == 403

    response = client.delete(f"/api/v1/learning/goals/{goal['id']}",
                             headers=other_headers)
    assert response.status_code == 403


def test_delete_goal_returns_204_and_removes_row(client, auth_headers):
    goal = _create_goal(client, auth_headers)

    response = client.delete(f"/api/v1/learning/goals/{goal['id']}",
                             headers=auth_headers)
    assert response.status_code == 204

    response = client.get("/api/v1/learning/goals", headers=auth_headers)
    assert response.json() == []


def test_patch_goal_updates_partial_fields(client, auth_headers):
    goal = _create_goal(client, auth_headers)

    response = client.patch(f"/api/v1/learning/goals/{goal['id']}",
                            json={"title": "수정된 목표"},
                            headers=auth_headers)
    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "수정된 목표"
    # 안 보낸 필드는 유지
    assert updated["category"] == GOAL_PAYLOAD["category"]
    assert updated["daily_study_time"] == GOAL_PAYLOAD["daily_study_time"]


# --- P2: 일정 CRUD + 진도율 ---

def _create_schedule(client, headers, goal_id, **overrides):
    payload = {
        "goal_id": goal_id,
        "date": "2026-08-01",
        "time": "09:00",
        "content": "React Hooks 학습",
        "duration_minutes": 60,
        **overrides,
    }
    response = client.post("/api/v1/learning/schedules", json=payload,
                           headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_schedule_rejects_foreign_goal(client, auth_headers, other_headers):
    goal = _create_goal(client, auth_headers)

    response = client.post("/api/v1/learning/schedules", json={
        "goal_id": goal["id"], "date": "2026-08-01", "time": "09:00",
        "content": "남의 목표에 일정 달기", "duration_minutes": 60,
    }, headers=other_headers)
    assert response.status_code == 403


def test_schedule_range_query(client, auth_headers):
    goal = _create_goal(client, auth_headers)
    _create_schedule(client, auth_headers, goal["id"], date="2026-08-01")
    _create_schedule(client, auth_headers, goal["id"], date="2026-08-05")
    _create_schedule(client, auth_headers, goal["id"], date="2026-08-20")

    response = client.get(
        "/api/v1/learning/schedules?start=2026-08-01&end=2026-08-07",
        headers=auth_headers)
    assert response.status_code == 200
    dates = [s["date"] for s in response.json()]
    assert dates == ["2026-08-01", "2026-08-05"]


def test_schedule_complete_toggle_sets_completed_at(client, auth_headers,
                                                    db_session):
    from app.models.models import LearningSchedule

    goal = _create_goal(client, auth_headers)
    schedule = _create_schedule(client, auth_headers, goal["id"])

    response = client.patch(f"/api/v1/learning/schedules/{schedule['id']}",
                            json={"completed": True}, headers=auth_headers)
    assert response.status_code == 200
    stored = db_session.get(LearningSchedule, schedule["id"])
    assert stored.completed is True
    assert stored.completed_at is not None

    response = client.patch(f"/api/v1/learning/schedules/{schedule['id']}",
                            json={"completed": False}, headers=auth_headers)
    assert response.status_code == 200
    db_session.refresh(stored)
    assert stored.completed is False
    assert stored.completed_at is None


def test_goal_delete_cascades_schedules(client, auth_headers, db_session):
    from app.models.models import LearningSchedule

    goal = _create_goal(client, auth_headers)
    _create_schedule(client, auth_headers, goal["id"])

    response = client.delete(f"/api/v1/learning/goals/{goal['id']}",
                             headers=auth_headers)
    assert response.status_code == 204
    assert db_session.query(LearningSchedule).count() == 0


# --- P8: 목표-레벨 연결 진도율 ---

def _seed_level_lessons(db, level, count, completed_user_id=None,
                        completed_count=0):
    """해당 레벨의 현행 레슨 count개를 만들고, 앞에서 completed_count개를
    completed_user_id의 완료로 기록한다."""
    from app.crud import crud_lessons, crud_learning

    generation = crud_lessons.create_generation(db, source="import")
    lessons = []
    for i in range(count):
        lesson = crud_lessons.upsert_lesson(db, level, f"lesson-{level}-{i}",
                                            f"레슨 {i}")
        crud_lessons.insert_version(db, lesson, generation.id, {
            "title": f"레슨 {i}", "level": level,
            "core_concepts": "내용", "code_examples": [], "quizzes": [],
        }, position=i + 1)
        lessons.append(lesson)
    db.commit()
    crud_lessons.finalize_generation(db, generation.id)

    for lesson in lessons[:completed_count]:
        crud_learning.upsert_lesson_progress(
            db, completed_user_id, lesson.id,
            done=1, correct=1, total=1, completed=True)
    return lessons


def test_goal_progress_includes_linked_level_lessons(client, auth_headers,
                                                     db_session, auth_user):
    _seed_level_lessons(db_session, "중급", 4,
                        completed_user_id=auth_user.id, completed_count=1)
    goal = _create_goal(client, auth_headers, linked_level="중급")
    schedule = _create_schedule(client, auth_headers, goal["id"])
    client.patch(f"/api/v1/learning/schedules/{schedule['id']}",
                 json={"completed": True}, headers=auth_headers)

    stored = client.get("/api/v1/learning/goals", headers=auth_headers).json()[0]
    # (일정 1 + 레슨 1) / (일정 1 + 레슨 4) = 40.0
    assert stored["progress"] == 40.0
    assert stored["progress_detail"] == {
        "schedule_done": 1, "schedule_total": 1,
        "lesson_done": 1, "lesson_total": 4,
    }


def test_goal_progress_without_linked_level_unchanged(client, auth_headers,
                                                      db_session, auth_user):
    # 레슨과 완료 기록이 있어도, 레벨을 연결하지 않은 목표에는 합산되지 않는다
    _seed_level_lessons(db_session, "초급", 3,
                        completed_user_id=auth_user.id, completed_count=2)
    goal = _create_goal(client, auth_headers)
    schedule = _create_schedule(client, auth_headers, goal["id"])
    client.patch(f"/api/v1/learning/schedules/{schedule['id']}",
                 json={"completed": True}, headers=auth_headers)

    stored = client.get("/api/v1/learning/goals", headers=auth_headers).json()[0]
    assert stored["progress"] == 100.0
    assert stored["progress_detail"]["lesson_total"] == 0


def test_linked_level_counts_only_current_lessons(client, auth_headers,
                                                  db_session, auth_user):
    from datetime import datetime

    lessons = _seed_level_lessons(db_session, "고급", 3,
                                  completed_user_id=auth_user.id,
                                  completed_count=0)
    # 한 개는 보관 처리 — 분모에서 빠져야 한다
    lessons[0].archived_at = datetime.now()
    db_session.commit()

    _create_goal(client, auth_headers, linked_level="고급")
    stored = client.get("/api/v1/learning/goals", headers=auth_headers).json()[0]
    assert stored["progress_detail"]["lesson_total"] == 2


# --- P6: 로컬 데이터 이관 ---

def test_import_maps_local_goal_ids(client, auth_headers):
    response = client.post("/api/v1/learning/import", json={
        "goals": [
            {"local_id": 111, "title": "로컬 목표 A", "category": "programming",
             "deadline": "2026-12-31", "daily_study_time": 60},
            {"local_id": 222, "title": "로컬 목표 B", "category": "design",
             "deadline": "2026-12-31", "daily_study_time": 30},
        ],
        "schedules": [
            {"local_goal_id": 222, "date": "2026-08-01", "time": "09:00",
             "content": "B의 일정", "duration_minutes": 60},
        ],
    }, headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "goals_created": 2, "schedules_created": 1, "schedules_skipped": 0}

    # 일정이 올바른 목표(B)에 붙었는지 — B만 schedule_total 1
    goals = client.get("/api/v1/learning/goals", headers=auth_headers).json()
    by_title = {g["title"]: g for g in goals}
    assert by_title["로컬 목표 B"]["progress_detail"]["schedule_total"] == 1
    assert by_title["로컬 목표 A"]["progress_detail"]["schedule_total"] == 0


def test_import_skips_orphan_schedules(client, auth_headers):
    response = client.post("/api/v1/learning/import", json={
        "goals": [
            {"local_id": 1, "title": "목표", "category": "other",
             "deadline": "2026-12-31", "daily_study_time": 60},
        ],
        "schedules": [
            {"local_goal_id": 1, "date": "2026-08-01", "time": "09:00",
             "content": "연결됨", "duration_minutes": 60},
            {"local_goal_id": 999, "date": "2026-08-01", "time": "10:00",
             "content": "고아 일정", "duration_minutes": 60},
        ],
    }, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["schedules_created"] == 1
    assert response.json()["schedules_skipped"] == 1


def test_import_rejects_oversized_payload(client, auth_headers):
    goals = [
        {"local_id": i, "title": f"목표 {i}", "category": "other",
         "deadline": "2026-12-31", "daily_study_time": 60}
        for i in range(501)
    ]
    response = client.post("/api/v1/learning/import",
                           json={"goals": goals, "schedules": []},
                           headers=auth_headers)
    assert response.status_code == 422


def test_import_preserves_completed_flag(client, auth_headers, db_session):
    from app.models.models import LearningSchedule

    response = client.post("/api/v1/learning/import", json={
        "goals": [
            {"local_id": 1, "title": "목표", "category": "other",
             "deadline": "2026-12-31", "daily_study_time": 60},
        ],
        "schedules": [
            {"local_goal_id": 1, "date": "2026-08-01", "time": "09:00",
             "content": "완료된 일정", "duration_minutes": 60,
             "completed": True},
        ],
    }, headers=auth_headers)
    assert response.status_code == 200

    stored = db_session.query(LearningSchedule).one()
    assert stored.completed is True
    assert stored.completed_at is not None


def test_goal_progress_counts_completed_schedules(client, auth_headers):
    goal = _create_goal(client, auth_headers)
    schedules = [_create_schedule(client, auth_headers, goal["id"],
                                  date=f"2026-08-0{i}") for i in range(1, 5)]
    for schedule in schedules[:2]:
        client.patch(f"/api/v1/learning/schedules/{schedule['id']}",
                     json={"completed": True}, headers=auth_headers)

    response = client.get("/api/v1/learning/goals", headers=auth_headers)
    assert response.status_code == 200
    stored = response.json()[0]
    assert stored["progress"] == 50.0
    assert stored["progress_detail"]["schedule_done"] == 2
    assert stored["progress_detail"]["schedule_total"] == 4
