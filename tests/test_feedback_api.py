# tests/test_feedback_api.py
"""AI 피드백 API 테스트. LLM은 feedback_agent._get_llm을 monkeypatch로 대체한다."""
import pytest

from app.agents import feedback_agent


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    """invoke 호출을 기록하는 가짜 ChatOpenAI."""

    def __init__(self, answer="**분석 결과** 잘하고 있어요.", error=None):
        self.answer = answer
        self.error = error
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return _FakeResponse(self.answer)


@pytest.fixture()
def fake_llm(monkeypatch):
    llm = _FakeLLM()
    monkeypatch.setattr(feedback_agent, "_get_llm", lambda: llm)
    return llm


def _seed_goal(client, headers):
    response = client.post("/api/v1/learning/goals", json={
        "title": "React 마스터하기", "category": "programming",
        "deadline": "2026-12-31", "daily_study_time": 60,
    }, headers=headers)
    assert response.status_code == 201
    return response.json()


def _request(client, headers, feedback_type):
    return client.post("/api/v1/learning/feedback",
                       json={"feedback_type": feedback_type}, headers=headers)


def test_feedback_returns_answer_for_each_type(client, auth_headers, fake_llm):
    for feedback_type in ("content", "schedule", "progress", "motivation"):
        response = _request(client, auth_headers, feedback_type)
        assert response.status_code == 200, response.text
        assert response.json()["answer"] == fake_llm.answer


def test_feedback_invalid_type_422(client, auth_headers, fake_llm):
    response = _request(client, auth_headers, "hack")
    assert response.status_code == 422
    assert fake_llm.calls == []


def test_feedback_snapshot_contains_user_data(client, auth_headers, fake_llm):
    goal = _seed_goal(client, auth_headers)
    schedule = client.post("/api/v1/learning/schedules", json={
        "goal_id": goal["id"], "date": "2026-07-28", "time": "09:00",
        "content": "훅 복습", "duration_minutes": 60,
    }, headers=auth_headers).json()
    client.patch(f"/api/v1/learning/schedules/{schedule['id']}",
                 json={"completed": True}, headers=auth_headers)

    response = _request(client, auth_headers, "progress")
    assert response.status_code == 200

    human = fake_llm.calls[0][1].content
    assert "React 마스터하기" in human       # 목표 제목
    assert "진도 100.0%" in human            # 일정 1/1 완료율


def test_feedback_type_selects_instruction(client, auth_headers, fake_llm):
    _request(client, auth_headers, "motivation")
    human = fake_llm.calls[0][1].content
    assert feedback_agent.FEEDBACK_INSTRUCTIONS["motivation"] in human
    assert feedback_agent.FEEDBACK_INSTRUCTIONS["content"] not in human


def test_feedback_returns_502_when_llm_fails(client, auth_headers, monkeypatch):
    llm = _FakeLLM(error=RuntimeError("api key invalid sk-secret"))
    monkeypatch.setattr(feedback_agent, "_get_llm", lambda: llm)

    response = _request(client, auth_headers, "progress")
    assert response.status_code == 502
    # 내부 오류 상세(스택·키)가 클라이언트에 노출되지 않는다
    assert "sk-secret" not in response.text
    assert "피드백을 생성하지 못했습니다" in response.json()["detail"]


def test_feedback_requires_auth(client, fake_llm):
    response = client.post("/api/v1/learning/feedback",
                           json={"feedback_type": "progress"})
    assert response.status_code == 401
    assert fake_llm.calls == []
