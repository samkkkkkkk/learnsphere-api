# tests/test_chat_api.py
"""챗 API 테스트.

에이전트 호출은 tutor_agent.run_tutor / astream_tutor를 monkeypatch해 대체한다.
(app.main import 자체가 무거우므로 client fixture의 지연 import 패턴을 그대로 따른다.)
"""
import asyncio
import json
from contextlib import contextmanager

import pytest

from app.agents import tutor_agent
from app.core.auth import create_access_token
from app.crud import crud_lessons, crud_users


def seed_lesson(db, title="조건부 렌더링", level="초급"):
    """활성 버전을 가진 레슨 하나를 만든다."""
    generation = crud_lessons.create_generation(db, source="import")
    lesson = crud_lessons.upsert_lesson(db, level, "conditional-rendering", title)
    crud_lessons.insert_version(db, lesson, generation.id, {
        "title": title,
        "level": level,
        "core_concepts": "조건에 따라 다른 JSX를 반환합니다.",
        "code_examples": [{"description": "삼항 연산자", "code": "cond ? <A /> : <B />"}],
        "quizzes": [{"question": "질문?", "answer": "답변"}],
    }, position=1)
    db.commit()
    crud_lessons.finalize_generation(db, generation.id)
    return lesson


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


@pytest.fixture()
def session_id(client, auth_headers):
    """빈 대화 세션 하나."""
    response = client.post("/api/v1/chat/sessions", json={}, headers=auth_headers)
    return response.json()["id"]


def send(client, headers, session_id, message):
    return client.post(f"/api/v1/chat/sessions/{session_id}/messages",
                       json={"message": message}, headers=headers)


# --- 인증 ---

def test_chat_requires_authentication(client):
    assert client.get("/api/v1/chat/sessions").status_code == 401
    assert client.post("/api/v1/chat/sessions", json={}).status_code == 401


# --- 세션 ---

def test_create_session_returns_id(client, auth_headers):
    response = client.post("/api/v1/chat/sessions", json={}, headers=auth_headers)

    assert response.status_code == 201
    assert isinstance(response.json()["id"], int)


def test_create_session_with_unknown_lesson_returns_404(client, auth_headers):
    response = client.post("/api/v1/chat/sessions", json={"lesson_id": 9999},
                           headers=auth_headers)

    assert response.status_code == 404


def test_list_sessions_returns_only_own(client, db_session, auth_headers, session_id):
    other = crud_users.create_user(
        db_session, email="other@example.com", password="password123",
        nickname="다른사람")
    other_headers = {"Authorization": f"Bearer {create_access_token(other.id)}"}
    client.post("/api/v1/chat/sessions", json={}, headers=other_headers)

    mine = client.get("/api/v1/chat/sessions", headers=auth_headers).json()

    assert [item["id"] for item in mine] == [session_id]


def test_access_other_users_session_returns_403(client, db_session, session_id):
    other = crud_users.create_user(
        db_session, email="other@example.com", password="password123",
        nickname="다른사람")
    other_headers = {"Authorization": f"Bearer {create_access_token(other.id)}"}

    response = client.get(f"/api/v1/chat/sessions/{session_id}/messages",
                          headers=other_headers)

    assert response.status_code == 403


def test_delete_session_removes_messages(client, auth_headers, session_id, fake_tutor):
    send(client, auth_headers, session_id, "질문")

    assert client.delete(f"/api/v1/chat/sessions/{session_id}",
                         headers=auth_headers).status_code == 204
    assert client.get("/api/v1/chat/sessions", headers=auth_headers).json() == []
    # 지워진 세션의 메시지는 조회 자체가 막힌다
    assert client.get(f"/api/v1/chat/sessions/{session_id}/messages",
                      headers=auth_headers).status_code == 403


# --- 메시지 ---

def test_send_message_returns_answer_and_sources(client, auth_headers, session_id,
                                                 fake_tutor):
    response = send(client, auth_headers, session_id, "useState가 뭐야?")

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "useState는 React의 상태 관리 훅입니다."
    assert body["sources"] == ["State"]


def test_send_message_persists_user_and_assistant(client, auth_headers, session_id,
                                                  fake_tutor):
    send(client, auth_headers, session_id, "useState가 뭐야?")

    messages = client.get(f"/api/v1/chat/sessions/{session_id}/messages",
                          headers=auth_headers).json()

    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "useState가 뭐야?"
    assert messages[1]["sources"] == ["State"]


def test_history_loaded_from_db(client, auth_headers, session_id, fake_tutor):
    """2번째 질문에는 1번째 대화가 이력으로 붙는다 (요청 본문에는 없음)."""
    send(client, auth_headers, session_id, "useState가 뭐야?")
    send(client, auth_headers, session_id, "그럼 그건 언제 써?")

    second_call = fake_tutor[1]
    assert [turn.content for turn in second_call["history"]] == [
        "useState가 뭐야?",
        "useState는 React의 상태 관리 훅입니다.",
    ]


def test_first_message_sets_session_title(client, auth_headers, session_id, fake_tutor):
    send(client, auth_headers, session_id, "useState가 뭐야?")
    send(client, auth_headers, session_id, "두 번째 질문")

    sessions = client.get("/api/v1/chat/sessions", headers=auth_headers).json()

    # 제목은 첫 질문으로 고정되고 이후 질문에 덮이지 않는다
    assert sessions[0]["title"] == "useState가 뭐야?"


@pytest.mark.parametrize("message", ["", "   "])
def test_send_message_rejects_empty(client, auth_headers, session_id, fake_tutor,
                                    message):
    response = send(client, auth_headers, session_id, message)

    assert response.status_code == 422
    assert fake_tutor == []  # 에이전트를 호출하지 않고 차단


def test_send_message_returns_502_when_agent_fails(client, monkeypatch, auth_headers,
                                                   session_id):
    def _boom(question, history=(), lesson_context=None):
        raise tutor_agent.TutorError("openai 연결 실패: 상세 내부 정보")

    monkeypatch.setattr(tutor_agent, "run_tutor", _boom)

    response = send(client, auth_headers, session_id, "안녕")

    assert response.status_code == 502
    # 내부 오류 상세가 클라이언트로 새지 않아야 한다
    assert "openai" not in response.json()["detail"]


# --- 레슨 컨텍스트 ---

def test_lesson_session_injects_lesson_content(client, db_session, auth_headers,
                                               fake_tutor):
    lesson = seed_lesson(db_session)
    created = client.post("/api/v1/chat/sessions", json={"lesson_id": lesson.id},
                          headers=auth_headers).json()

    send(client, auth_headers, created["id"], "이 예제 설명해줘")

    context = fake_tutor[0]["lesson_context"]
    assert "조건에 따라 다른 JSX를 반환합니다." in context
    assert "cond ? <A /> : <B />" in context  # 코드 예시까지 포함


def test_plain_session_has_no_lesson_context(client, auth_headers, session_id,
                                             fake_tutor):
    send(client, auth_headers, session_id, "안녕")

    assert fake_tutor[0]["lesson_context"] is None


# --- 스트리밍 (Phase 11) ---

TOKENS = ["use", "State", "는 상태 훅입니다."]


@pytest.fixture()
def fake_stream(monkeypatch):
    """astream_tutor()를 가짜 async generator로 대체하고 호출 인자를 기록한다."""
    calls = []

    async def _fake_astream(question, history=(), lesson_context=None):
        calls.append({
            "question": question,
            "history": list(history),
            "lesson_context": lesson_context,
        })
        for token in TOKENS:
            yield {"type": "token", "content": token}
        yield {"type": "sources", "sources": ["State"]}

    monkeypatch.setattr(tutor_agent, "astream_tutor", _fake_astream)
    return calls


def stream(client, headers, session_id, message="useState가 뭐야?"):
    return client.stream("POST", f"/api/v1/chat/sessions/{session_id}/stream",
                         json={"message": message}, headers=headers)


def read_events(response):
    """SSE 본문에서 data 페이로드만 순서대로 뽑는다."""
    return [json.loads(line[len("data: "):])
            for line in response.iter_lines() if line.startswith("data: ")]


def stored_messages(client, headers, session_id):
    return client.get(f"/api/v1/chat/sessions/{session_id}/messages",
                      headers=headers).json()


def test_stream_yields_multiple_token_events(client, auth_headers, session_id,
                                             fake_stream):
    with stream(client, auth_headers, session_id) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        tokens = [e for e in read_events(response) if e["type"] == "token"]

    assert [e["content"] for e in tokens] == TOKENS


def test_stream_ends_with_done_event(client, auth_headers, session_id, fake_stream):
    with stream(client, auth_headers, session_id) as response:
        events = read_events(response)

    assert events[-1] == {"type": "done", "sources": ["State"]}


def test_stream_saves_user_message_before_streaming(client, auth_headers, session_id,
                                                   fake_stream):
    """본문을 한 줄도 읽지 않고 끊어도 질문은 남아 있다."""
    with stream(client, auth_headers, session_id, "질문만 남기고 이탈"):
        pass

    messages = stored_messages(client, auth_headers, session_id)
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "질문만 남기고 이탈"


def test_stream_saves_assistant_message_on_completion(client, auth_headers, session_id,
                                                      fake_stream):
    with stream(client, auth_headers, session_id) as response:
        read_events(response)

    messages = stored_messages(client, auth_headers, session_id)
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "".join(TOKENS)
    assert messages[1]["sources"] == ["State"]


def test_stream_saves_partial_on_early_close(client, db_session, auth_user,
                                             auth_headers, session_id, fake_stream):
    """중간에 끊어도 그때까지 받은 답변은 저장된다.

    TestClient는 스트리밍 응답을 끝까지 소비해버려 '중도 이탈'을 흉내 낼 수 없다.
    그래서 응답 제너레이터(`answer_stream`)를 직접 만들어 첫 토큰만 받고 닫는다.
    """
    from app.api import chat_api

    @contextmanager
    def _scope():
        yield db_session

    async def consume_first_token_then_close():
        stream_gen = chat_api.answer_stream(
            "useState가 뭐야?", [], None, session_id, auth_user.id, _scope)
        first = await stream_gen.__anext__()
        await stream_gen.aclose()  # 클라이언트가 창을 닫은 상황
        return first

    first = asyncio.run(consume_first_token_then_close())

    assert json.loads(first[len("data: "):])["content"] == TOKENS[0]

    assistant = [m for m in stored_messages(client, auth_headers, session_id)
                 if m["role"] == "assistant"]
    assert len(assistant) == 1
    assert assistant[0]["content"] == TOKENS[0]  # 첫 토큰까지만
    assert assistant[0]["sources"] is None  # 출처는 아직 못 받았다


def test_stream_loads_history_and_lesson_context(client, db_session, auth_headers,
                                                 fake_stream):
    """비스트리밍 경로와 같은 재료(이력·레슨 본문)를 받는다."""
    lesson = seed_lesson(db_session)
    created = client.post("/api/v1/chat/sessions", json={"lesson_id": lesson.id},
                          headers=auth_headers).json()

    with stream(client, auth_headers, created["id"], "첫 질문") as response:
        read_events(response)
    with stream(client, auth_headers, created["id"], "두 번째 질문") as response:
        read_events(response)

    second = fake_stream[1]
    assert [turn.content for turn in second["history"]] == ["첫 질문", "".join(TOKENS)]
    assert "조건에 따라 다른 JSX를 반환합니다." in second["lesson_context"]


def test_stream_sends_error_event_when_agent_fails(client, monkeypatch, auth_headers,
                                                   session_id):
    """실패해도 연결은 정상 종료되고, 내부 오류 상세는 새지 않는다."""
    async def _boom(question, history=(), lesson_context=None):
        raise tutor_agent.TutorError("openai 연결 실패: 상세 내부 정보")
        yield  # pragma: no cover — async generator로 만들기 위한 장식

    monkeypatch.setattr(tutor_agent, "astream_tutor", _boom)

    with stream(client, auth_headers, session_id) as response:
        events = read_events(response)

    assert events[-1]["type"] == "error"
    assert "openai" not in events[-1]["detail"]


@pytest.mark.parametrize("message", ["", "   "])
def test_stream_rejects_empty_message(client, auth_headers, session_id, fake_stream,
                                      message):
    with stream(client, auth_headers, session_id, message) as response:
        assert response.status_code == 422
    assert fake_stream == []


def test_stream_requires_authentication(client, session_id):
    with client.stream("POST", f"/api/v1/chat/sessions/{session_id}/stream",
                       json={"message": "안녕"}) as response:
        assert response.status_code == 401


def test_stream_other_users_session_returns_403(client, db_session, session_id,
                                                fake_stream):
    other = crud_users.create_user(
        db_session, email="other@example.com", password="password123",
        nickname="다른사람")
    other_headers = {"Authorization": f"Bearer {create_access_token(other.id)}"}

    with stream(client, other_headers, session_id) as response:
        assert response.status_code == 403
