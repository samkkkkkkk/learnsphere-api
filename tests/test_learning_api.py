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
