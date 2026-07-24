# tests/test_chat_api.py
"""챗 API 테스트.

에이전트 호출은 tutor_agent.run_tutor를 monkeypatch해 대체한다.
(app.main import 자체가 무거우므로 client fixture의 지연 import 패턴을 그대로 따른다.)
"""
import pytest

from app.agents import tutor_agent
from app.crud import crud_lessons


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


# --- Phase 6: 레슨 컨텍스트 ---

def test_chat_with_lesson_id_injects_lesson_content(client, db_session, fake_tutor):
    lesson = seed_lesson(db_session)

    response = client.post("/api/v1/chat", json={
        "message": "이 예제 설명해줘",
        "lesson_id": lesson.id,
    })

    assert response.status_code == 200
    context = fake_tutor[0]["lesson_context"]
    assert "조건에 따라 다른 JSX를 반환합니다." in context
    assert "cond ? <A /> : <B />" in context  # 코드 예시까지 포함


def test_chat_with_unknown_lesson_id_returns_404(client, fake_tutor):
    response = client.post("/api/v1/chat", json={
        "message": "설명해줘",
        "lesson_id": 9999,
    })

    assert response.status_code == 404
    assert fake_tutor == []  # 에이전트를 호출하지 않는다


def test_chat_with_archived_lesson_returns_404(client, db_session, fake_tutor):
    """레슨 조회 API와 동일하게 아카이브된 레슨은 없는 것으로 취급한다."""
    from datetime import datetime, timezone

    lesson = seed_lesson(db_session)
    lesson.archived_at = datetime.now(timezone.utc)
    db_session.commit()

    response = client.post("/api/v1/chat", json={
        "message": "설명해줘",
        "lesson_id": lesson.id,
    })

    assert response.status_code == 404


def test_chat_without_lesson_id_passes_none(client, fake_tutor):
    """레슨을 지정하지 않는 기존 요청은 그대로 동작한다."""
    response = client.post("/api/v1/chat", json={"message": "안녕"})

    assert response.status_code == 200
    assert fake_tutor[0]["lesson_context"] is None
