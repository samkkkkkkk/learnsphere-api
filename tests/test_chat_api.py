# tests/test_chat_api.py
"""챗 API 테스트.

LLM 호출은 chat_service.ask를 monkeypatch해 대체한다.
(app.main import 자체가 무거우므로 client fixture의 지연 import 패턴을 그대로 따른다.)
"""
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.schemas.chat import ChatTurn
from app.services import chat_service


@pytest.fixture()
def fake_llm(monkeypatch):
    """ask()를 가로채 호출 인자를 기록하는 fixture."""
    calls = []

    def _fake_ask(message: str, history=()) -> str:
        calls.append({"message": message, "history": list(history)})
        return "useState는 React의 상태 관리 훅입니다."

    monkeypatch.setattr(chat_service, "ask", _fake_ask)
    return calls


# --- Phase 1: 단일 질문 ---

def test_chat_returns_answer(client, fake_llm):
    response = client.post("/api/v1/chat", json={"message": "useState가 뭐야?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "useState는 React의 상태 관리 훅입니다."


def test_chat_passes_message_to_llm(client, fake_llm):
    client.post("/api/v1/chat", json={"message": "useEffect 설명해줘"})

    assert fake_llm[0]["message"] == "useEffect 설명해줘"


@pytest.mark.parametrize("message", ["", "   "])
def test_chat_rejects_empty_message(client, fake_llm, message):
    response = client.post("/api/v1/chat", json={"message": message})

    assert response.status_code == 422
    assert fake_llm == []  # LLM을 호출하지 않고 차단


def test_chat_returns_502_when_llm_fails(client, monkeypatch):
    def _boom(message: str, history=()) -> str:
        raise chat_service.ChatServiceError("openai 연결 실패: 상세 내부 정보")

    monkeypatch.setattr(chat_service, "ask", _boom)

    response = client.post("/api/v1/chat", json={"message": "안녕"})

    assert response.status_code == 502
    # 내부 오류 상세가 클라이언트로 새지 않아야 한다
    assert "openai" not in response.json()["detail"]


# --- Phase 2: 멀티턴 ---

def test_chat_accepts_history(client, fake_llm):
    response = client.post("/api/v1/chat", json={
        "message": "그럼 그건 언제 써?",
        "history": [
            {"role": "user", "content": "useState가 뭐야?"},
            {"role": "assistant", "content": "상태 관리 훅입니다."},
        ],
    })

    assert response.status_code == 200
    assert [turn.content for turn in fake_llm[0]["history"]] == [
        "useState가 뭐야?",
        "상태 관리 훅입니다.",
    ]


def test_chat_without_history_still_works(client, fake_llm):
    """history를 안 보내는 Phase 1 방식 요청도 그대로 동작해야 한다."""
    response = client.post("/api/v1/chat", json={"message": "안녕"})

    assert response.status_code == 200
    assert fake_llm[0]["history"] == []


def test_history_truncated_to_last_10():
    history = [
        ChatTurn(role="user" if i % 2 == 0 else "assistant", content=f"turn-{i}")
        for i in range(15)
    ]

    messages = chat_service.build_messages("마지막 질문", history)

    # 시스템 메시지 1 + 최근 10턴 + 이번 질문 1
    assert len(messages) == 12
    assert isinstance(messages[0], SystemMessage)
    assert messages[1].content == "turn-5"  # 앞의 5턴은 잘려나감
    assert messages[-1].content == "마지막 질문"


def test_history_role_mapping():
    history = [
        ChatTurn(role="user", content="질문"),
        ChatTurn(role="assistant", content="답변"),
    ]

    messages = chat_service.build_messages("다음 질문", history)

    assert isinstance(messages[1], HumanMessage)
    assert isinstance(messages[2], AIMessage)
    assert isinstance(messages[3], HumanMessage)
