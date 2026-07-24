# tests/test_chat_api.py
"""챗 API 테스트.

에이전트 호출은 tutor_agent.run_tutor를 monkeypatch해 대체한다.
(app.main import 자체가 무거우므로 client fixture의 지연 import 패턴을 그대로 따른다.)
"""
import pytest

from app.agents import tutor_agent


@pytest.fixture()
def fake_tutor(monkeypatch):
    """run_tutor()를 가로채 호출 인자를 기록하는 fixture."""
    calls = []

    def _fake_run_tutor(question, history=(), lesson_context=None):
        calls.append({
            "question": question,
            "history": list(history),
            "lesson_context": lesson_context,
        })
        return "useState는 React의 상태 관리 훅입니다.", ["State"]

    monkeypatch.setattr(tutor_agent, "run_tutor", _fake_run_tutor)
    return calls


# --- Phase 1: 단일 질문 ---

def test_chat_returns_answer(client, fake_tutor):
    response = client.post("/api/v1/chat", json={"message": "useState가 뭐야?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "useState는 React의 상태 관리 훅입니다."


def test_chat_passes_message_to_agent(client, fake_tutor):
    client.post("/api/v1/chat", json={"message": "useEffect 설명해줘"})

    assert fake_tutor[0]["question"] == "useEffect 설명해줘"


@pytest.mark.parametrize("message", ["", "   "])
def test_chat_rejects_empty_message(client, fake_tutor, message):
    response = client.post("/api/v1/chat", json={"message": message})

    assert response.status_code == 422
    assert fake_tutor == []  # 에이전트를 호출하지 않고 차단


def test_chat_returns_502_when_agent_fails(client, monkeypatch):
    def _boom(question, history=(), lesson_context=None):
        raise tutor_agent.TutorError("openai 연결 실패: 상세 내부 정보")

    monkeypatch.setattr(tutor_agent, "run_tutor", _boom)

    response = client.post("/api/v1/chat", json={"message": "안녕"})

    assert response.status_code == 502
    # 내부 오류 상세가 클라이언트로 새지 않아야 한다
    assert "openai" not in response.json()["detail"]


# --- Phase 2: 멀티턴 ---

def test_chat_accepts_history(client, fake_tutor):
    response = client.post("/api/v1/chat", json={
        "message": "그럼 그건 언제 써?",
        "history": [
            {"role": "user", "content": "useState가 뭐야?"},
            {"role": "assistant", "content": "상태 관리 훅입니다."},
        ],
    })

    assert response.status_code == 200
    assert [turn.content for turn in fake_tutor[0]["history"]] == [
        "useState가 뭐야?",
        "상태 관리 훅입니다.",
    ]


def test_chat_without_history_still_works(client, fake_tutor):
    """history를 안 보내는 Phase 1 방식 요청도 그대로 동작해야 한다."""
    response = client.post("/api/v1/chat", json={"message": "안녕"})

    assert response.status_code == 200
    assert fake_tutor[0]["history"] == []


# --- Phase 5: 근거 문서 ---

def test_chat_response_includes_sources(client, fake_tutor):
    response = client.post("/api/v1/chat", json={"message": "useState가 뭐야?"})

    assert response.json()["sources"] == ["State"]
