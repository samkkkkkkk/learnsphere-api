# tests/test_tutor_agent.py
"""튜터 에이전트(LangGraph) 테스트.

Qdrant 검색과 LLM 호출을 모두 monkeypatch해 그래프 자체의 동작만 검증한다.
"""
import asyncio

import pytest

from app.agents import tutor_agent
from app.schemas.chat import ChatTurn
from app.services import qdrant_service

SAMPLE_DOCS = [
    {"text": "key는 목록 항목을 식별합니다.", "title": "리스트와 key",
     "source": "/learn/rendering-lists", "score": 0.9},
    {"text": "key가 없으면 React가 항목을 잘못 재사용합니다.", "title": "리스트와 key",
     "source": "/learn/rendering-lists", "score": 0.8},
    {"text": "상태는 useState로 관리합니다.", "title": "State",
     "source": "/learn/state", "score": 0.5},
]


class _FakeResponse:
    def __init__(self, content):
        self.content = content


@pytest.fixture()
def spy(monkeypatch):
    """검색/LLM 호출 순서와 인자를 기록한다."""
    record = {"order": [], "messages": None, "search_args": None}

    def _fake_search(query, top_k=5, level=None):
        record["order"].append("retrieve")
        record["search_args"] = {"query": query, "top_k": top_k, "level": level}
        return SAMPLE_DOCS

    class _FakeLLM:
        def invoke(self, messages):
            record["order"].append("generate")
            record["messages"] = messages
            return _FakeResponse("key는 React가 항목을 구분하는 데 씁니다.")

    monkeypatch.setattr(qdrant_service, "search_similar", _fake_search)
    monkeypatch.setattr(tutor_agent, "_get_llm", lambda: _FakeLLM())
    # 그래프를 매번 새로 만들어 다른 테스트의 캐시에 영향받지 않게 한다
    monkeypatch.setattr(tutor_agent, "_graph", None)
    return record


def test_tutor_calls_retrieve_before_generate(spy):
    tutor_agent.run_tutor("key prop은 왜 필요해?")

    assert spy["order"] == ["retrieve", "generate"]


def test_tutor_injects_retrieved_docs_into_prompt(spy):
    tutor_agent.run_tutor("key prop은 왜 필요해?")

    system_prompt = spy["messages"][0].content
    assert "key는 목록 항목을 식별합니다." in system_prompt
    assert "리스트와 key" in system_prompt


def test_tutor_returns_deduplicated_sources(spy):
    _, sources = tutor_agent.run_tutor("key prop은 왜 필요해?")

    # 같은 문서에서 두 조각이 나와도 제목은 한 번만
    assert sources == ["리스트와 key", "State"]


def test_tutor_answers_when_no_search_hit(monkeypatch):
    monkeypatch.setattr(
        qdrant_service, "search_similar", lambda *a, **kw: [])

    class _FakeLLM:
        def __init__(self):
            self.messages = None

        def invoke(self, messages):
            self.messages = messages
            return _FakeResponse("문서를 찾지 못했지만 일반적으로는…")

    fake_llm = _FakeLLM()
    monkeypatch.setattr(tutor_agent, "_get_llm", lambda: fake_llm)
    monkeypatch.setattr(tutor_agent, "_graph", None)

    answer, sources = tutor_agent.run_tutor("아무거나")

    assert answer.startswith("문서를 찾지 못했지만")
    assert sources == []
    assert "참고 문서를 찾지 못했습니다" in fake_llm.messages[0].content


def test_tutor_includes_history(spy):
    history = [
        ChatTurn(role="user", content="useState가 뭐야?"),
        ChatTurn(role="assistant", content="상태 관리 훅입니다."),
    ]

    tutor_agent.run_tutor("그럼 그건 언제 써?", history)

    contents = [message.content for message in spy["messages"]]
    assert "useState가 뭐야?" in contents
    assert "상태 관리 훅입니다." in contents
    assert contents[-1] == "그럼 그건 언제 써?"


def test_tutor_puts_lesson_context_before_retrieved_docs(spy):
    tutor_agent.run_tutor(
        "이 예제 설명해줘", lesson_context="이 레슨은 조건부 렌더링을 다룹니다.")

    system_prompt = spy["messages"][0].content
    assert system_prompt.index("조건부 렌더링") < system_prompt.index("리스트와 key")


def test_history_truncated_to_last_10():
    """토큰 비용 억제를 위해 오래된 대화는 잘라낸다."""
    history = [
        ChatTurn(role="user" if i % 2 == 0 else "assistant", content=f"turn-{i}")
        for i in range(15)
    ]

    messages = tutor_agent.build_messages({
        "question": "마지막 질문", "history": history, "retrieved": [],
    })

    # 시스템 메시지 1 + 최근 10턴 + 이번 질문 1
    assert len(messages) == 12
    assert messages[1].content == "turn-5"  # 앞의 5턴은 잘려나감
    assert messages[-1].content == "마지막 질문"


def test_history_role_mapping():
    from langchain_core.messages import AIMessage, HumanMessage

    messages = tutor_agent.build_messages({
        "question": "다음 질문",
        "history": [
            ChatTurn(role="user", content="질문"),
            ChatTurn(role="assistant", content="답변"),
        ],
        "retrieved": [],
    })

    assert isinstance(messages[1], HumanMessage)
    assert isinstance(messages[2], AIMessage)
    assert isinstance(messages[3], HumanMessage)


# --- 스트리밍 (Phase 11) ---

class _FakeChunk:
    def __init__(self, content):
        self.content = content


def fake_graph_events(events):
    """astream_events가 주어진 이벤트를 순서대로 내는 가짜 그래프."""
    class _FakeGraph:
        async def astream_events(self, _input, version=None):
            for event in events:
                yield event

    return _FakeGraph()


async def collect(agen):
    return [item async for item in agen]


def test_astream_yields_tokens_then_sources(monkeypatch):
    """토큰만 골라 흘리고, 마지막에 검색 문서 제목을 낸다."""
    monkeypatch.setattr(tutor_agent, "_get_graph", lambda: fake_graph_events([
        {"event": "on_chain_start", "data": {}},
        {"event": "on_chain_end", "name": "retrieve",
         "data": {"output": {"retrieved": SAMPLE_DOCS}}},
        {"event": "on_chat_model_stream", "data": {"chunk": _FakeChunk("key는 ")}},
        {"event": "on_chat_model_stream", "data": {"chunk": _FakeChunk("")}},  # 빈 조각
        {"event": "on_chat_model_stream", "data": {"chunk": _FakeChunk("식별자입니다.")}},
        {"event": "on_chain_end", "name": "LangGraph", "data": {"output": {}}},
    ]))

    events = asyncio.run(collect(tutor_agent.astream_tutor("key가 뭐야?")))

    assert events == [
        {"type": "token", "content": "key는 "},
        {"type": "token", "content": "식별자입니다."},
        # 같은 문서의 두 조각은 제목 하나로 합쳐진다
        {"type": "sources", "sources": ["리스트와 key", "State"]},
    ]


def test_astream_yields_empty_sources_without_search_hit(monkeypatch):
    monkeypatch.setattr(tutor_agent, "_get_graph", lambda: fake_graph_events([
        {"event": "on_chat_model_stream", "data": {"chunk": _FakeChunk("음…")}},
    ]))

    events = asyncio.run(collect(tutor_agent.astream_tutor("아무거나")))

    assert events[-1] == {"type": "sources", "sources": []}


def test_astream_wraps_llm_error(monkeypatch):
    class _BoomGraph:
        async def astream_events(self, _input, version=None):
            yield {"event": "on_chat_model_stream", "data": {"chunk": _FakeChunk("시")}}
            raise RuntimeError("rate limit")

    monkeypatch.setattr(tutor_agent, "_get_graph", lambda: _BoomGraph())

    async def _run():
        return await collect(tutor_agent.astream_tutor("질문"))

    with pytest.raises(tutor_agent.TutorError):
        asyncio.run(_run())


def test_tutor_wraps_llm_error(monkeypatch):
    monkeypatch.setattr(
        qdrant_service, "search_similar", lambda *a, **kw: [])

    class _BoomLLM:
        def invoke(self, messages):
            raise RuntimeError("rate limit")

    monkeypatch.setattr(tutor_agent, "_get_llm", lambda: _BoomLLM())
    monkeypatch.setattr(tutor_agent, "_graph", None)

    with pytest.raises(tutor_agent.TutorError):
        tutor_agent.run_tutor("질문")
