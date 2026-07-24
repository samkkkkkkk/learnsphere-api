# app/agents/tutor_agent.py
"""RAG 튜터 에이전트.

retrieve → generate 2노드 선형 그래프. 검색된 React 문서를 근거로 답한다.

대화 이력은 checkpointer 없이 호출자가 주입한다. Phase 9에서 DB가 이력의
주인이 되므로, 그래프가 별도 저장소를 갖지 않는 편이 단순하다.
"""
import os
from typing import Dict, List, Optional, Sequence, Tuple, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from ..schemas.chat import ChatTurn
from ..services import qdrant_service

CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")

# LLM에 실어 보낼 이전 대화 최대 개수. 토큰 비용과 응답 지연을 억제한다.
MAX_HISTORY_TURNS = 10

# 질문 하나당 가져올 문서 조각 수.
TOP_K = 4

SYSTEM_PROMPT = (
    "당신은 React를 가르치는 한국어 튜터입니다.\n"
    "아래 '참고 문서'를 근거로 학습자의 질문에 정확하고 이해하기 쉽게 답하세요.\n"
    "참고 문서에 없는 내용은 지어내지 말고, 모르면 모른다고 말하세요.\n"
    "코드를 보여줄 때는 마크다운 코드 블록을 사용하세요."
)


class TutorError(Exception):
    """튜터 응답 생성 실패. API 레이어가 502로 변환한다."""


class TutorState(TypedDict, total=False):
    question: str
    history: List[ChatTurn]
    lesson_context: Optional[str]
    retrieved: List[Dict]
    answer: str


_llm: ChatOpenAI | None = None


def _get_llm() -> ChatOpenAI:
    """LLM 클라이언트를 지연 생성한다 (import 시점에 키를 요구하지 않도록)."""
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(model=CHAT_MODEL)
    return _llm


def _build_context(state: TutorState) -> str:
    """레슨 본문 + 검색 문서를 하나의 참고 자료 블록으로 조립한다.

    레슨 컨텍스트를 앞에 두어, 학습자가 보고 있는 레슨이 우선 근거가 되게 한다.
    """
    blocks: List[str] = []

    lesson_context = state.get("lesson_context")
    if lesson_context:
        blocks.append(f"[현재 학습 중인 레슨]\n{lesson_context}")

    for doc in state.get("retrieved") or []:
        blocks.append(f"[{doc['title']}]\n{doc['text']}")

    if not blocks:
        return "(참고 문서를 찾지 못했습니다. 일반적인 React 지식으로 답하되, 불확실하면 그렇다고 밝히세요.)"

    return "\n\n---\n\n".join(blocks)


def build_messages(state: TutorState) -> List[BaseMessage]:
    """시스템 프롬프트 + 참고 문서 + 최근 대화 + 이번 질문을 조립한다."""
    system = f"{SYSTEM_PROMPT}\n\n=== 참고 문서 ===\n{_build_context(state)}"
    messages: List[BaseMessage] = [SystemMessage(content=system)]

    for turn in list(state.get("history") or [])[-MAX_HISTORY_TURNS:]:
        if turn.role == "user":
            messages.append(HumanMessage(content=turn.content))
        else:
            messages.append(AIMessage(content=turn.content))

    messages.append(HumanMessage(content=state["question"]))
    return messages


# --- 노드 ---

def retrieve(state: TutorState) -> TutorState:
    """질문과 가까운 문서 조각을 검색한다."""
    docs = qdrant_service.search_similar(state["question"], top_k=TOP_K)
    return {"retrieved": docs}


def generate(state: TutorState) -> TutorState:
    """참고 문서를 근거로 답변을 생성한다."""
    try:
        response = _get_llm().invoke(build_messages(state))
    except Exception as e:
        raise TutorError(f"LLM 호출 중 오류: {e}") from e

    content = response.content
    if not content:
        raise TutorError("LLM 응답이 비어있습니다.")
    return {"answer": content}


def build_tutor_graph():
    """retrieve → generate 선형 그래프를 만든다."""
    graph = StateGraph(TutorState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_tutor_graph()
    return _graph


def run_tutor(question: str, history: Sequence[ChatTurn] = (),
              lesson_context: Optional[str] = None) -> Tuple[str, List[str]]:
    """질문에 대한 답변과 근거 문서 제목 목록을 반환한다."""
    result = _get_graph().invoke({
        "question": question,
        "history": list(history),
        "lesson_context": lesson_context,
    })

    sources = []
    for doc in result.get("retrieved") or []:
        title = doc.get("title")
        if title and title not in sources:
            sources.append(title)

    return result["answer"], sources
