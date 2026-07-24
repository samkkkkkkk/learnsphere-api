# app/services/chat_service.py
"""튜터 챗 LLM 호출.

Phase 1에서는 검색(RAG) 없이 LLM에 질문을 그대로 전달한다.
Qdrant 검색과 LangGraph 그래프는 이후 Phase에서 app/agents/로 옮겨간다.
"""
import os

from langchain_openai import ChatOpenAI

CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")

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


def ask(message: str) -> str:
    """질문 하나를 LLM에 보내고 답변 텍스트를 반환한다."""
    try:
        response = _get_llm().invoke([
            ("system", SYSTEM_PROMPT),
            ("human", message),
        ])
    except Exception as e:
        raise ChatServiceError(f"LLM 호출 중 오류: {e}") from e

    content = response.content
    if not content:
        raise ChatServiceError("LLM 응답이 비어있습니다.")
    return content
