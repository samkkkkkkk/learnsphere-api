# app/agents/feedback_agent.py
"""학습 매니저 AI 피드백 에이전트.

검색이 필요 없어 LangGraph 없이 단건 LLM 호출로 충분하다.
학습 스냅샷(목표·일정·진도)은 crud_learning.build_feedback_snapshot이 만들고,
이 모듈은 그것을 근거로 타입별 피드백을 생성하는 일만 한다.
"""
import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = (
    "당신은 학습자를 돕는 한국어 학습 코치입니다.\n"
    "아래 '학습 현황'에 제공된 데이터만 근거로 답하세요. "
    "데이터에 없는 내용은 지어내지 마세요.\n"
    "구체적인 수치를 인용해 신뢰를 주고, 실행 가능한 조언 3~4개를 제시하세요.\n"
    "답변은 **마크다운**으로 작성하세요. HTML 태그는 사용하지 마세요.\n"
    "분량은 200~400자 내외로 간결하게 유지하세요."
)

# 4가지 피드백 버튼에 대응하는 지시문
FEEDBACK_INSTRUCTIONS = {
    "content": (
        "학습 현황(진도율·연결된 레슨 레벨·완료한 레슨)을 바탕으로 "
        "다음에 학습하면 좋을 콘텐츠를 추천해주세요."
    ),
    "schedule": (
        "최근 일정 완료율과 학습 시간을 근거로 학습 분량이 적절한지 진단하고, "
        "줄이거나 늘리는 구체적인 조절 방안을 제안해주세요."
    ),
    "progress": (
        "목표별 진도율과 완료 일정·레슨 수치를 분석한 진도 리포트를 작성해주세요. "
        "잘하고 있는 점과 보완할 점을 나눠 짚어주세요."
    ),
    "motivation": (
        "학습 기록(연속 학습일·완료 수치)을 근거로 학습자를 격려하는 "
        "동기부여 메시지를 작성해주세요. 막연한 칭찬 대신 실제 성과를 짚어주세요."
    ),
}


class FeedbackError(Exception):
    """피드백 생성 실패. API 레이어가 502로 변환한다."""


_llm: ChatOpenAI | None = None


def _get_llm() -> ChatOpenAI:
    """LLM 클라이언트를 지연 생성한다 (import 시점에 키를 요구하지 않도록)."""
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(model=CHAT_MODEL)
    return _llm


def run_feedback(feedback_type: str, snapshot: str) -> str:
    """학습 스냅샷을 근거로 타입별 피드백을 생성한다 (마크다운)."""
    instruction = FEEDBACK_INSTRUCTIONS.get(feedback_type)
    if instruction is None:
        raise FeedbackError(f"지원하지 않는 피드백 타입: {feedback_type}")

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=(
            f"=== 학습 현황 ===\n{snapshot}\n\n=== 요청 ===\n{instruction}")),
    ]

    try:
        response = _get_llm().invoke(messages)
    except Exception as e:
        raise FeedbackError(f"피드백 생성 실패: {e}") from e

    content = response.content
    if not isinstance(content, str) or not content.strip():
        raise FeedbackError("LLM이 빈 응답을 반환했습니다.")
    return content
