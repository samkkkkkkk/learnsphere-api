# app/services/chat_service.py
"""튜터 챗 LLM 호출.

Phase 2에서는 검색(RAG) 없이 이전 대화 + 질문을 LLM에 전달한다.
Qdrant 검색과 LangGraph 그래프는 이후 Phase에서 app/agents/로 옮겨간다.
"""
import os
from typing import List, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..schemas.chat import ChatTurn

CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")

# LLM에 실어 보낼 이전 대화 최대 개수. 토큰 비용과 응답 지연을 억제한다.
MAX_HISTORY_TURNS = 10

SYSTEM_PROMPT = (
    "당신은 React를 가르치는 한국어 튜터입니다. "
    "학습자의 질문에 정확하고 이해하기 쉽게 답하세요. "
    "코드를 보여줄 때는 마크다운 코드 블록을 사용하세요."
)


class ChatServiceError(Exception):
    """LLM 호출 실패. API 레이어가 502로 변환한다."""


_llm: ChatOpenAI | None = None


def _get_llm() -> ChatOpenAI:
    """LLM 클라이언트를 지연 생성한다.

    import 시점에 생성하면 OPENAI_API_KEY가 없는 환경(테스트 수집 등)에서 터진다.
    """
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(model=CHAT_MODEL)
    return _llm


def build_messages(message: str, history: Sequence[ChatTurn] = ()) -> List[BaseMessage]:
    """시스템 프롬프트 + 최근 대화 + 이번 질문을 LangChain 메시지로 조립한다."""
    messages: List[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]

    for turn in list(history)[-MAX_HISTORY_TURNS:]:
        if turn.role == "user":
            messages.append(HumanMessage(content=turn.content))
        else:
            messages.append(AIMessage(content=turn.content))

    messages.append(HumanMessage(content=message))
    return messages


def ask(message: str, history: Sequence[ChatTurn] = ()) -> str:
    """이전 대화를 반영해 LLM에 질문하고 답변 텍스트를 반환한다."""
    try:
        response = _get_llm().invoke(build_messages(message, history))
    except Exception as e:
        raise ChatServiceError(f"LLM 호출 중 오류: {e}") from e

    content = response.content
    if not content:
        raise ChatServiceError("LLM 응답이 비어있습니다.")
    return content
