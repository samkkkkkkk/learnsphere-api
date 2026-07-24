# app/api/chat_api.py
from fastapi import APIRouter, HTTPException

from ..agents import tutor_agent
from ..schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest):
    """학습자 질문에 대한 튜터 답변을 근거 문서 목록과 함께 반환합니다."""
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="질문 내용을 입력해주세요.")

    try:
        answer, sources = tutor_agent.run_tutor(request.message, request.history)
    except tutor_agent.TutorError as e:
        # 원인 예외 메시지는 서버 로그로만 남기고, 클라이언트에는 일반 문구를 준다.
        print(f"  > [Chat] 답변 생성 실패: {e}")
        raise HTTPException(
            status_code=502, detail="답변을 생성하지 못했습니다. 잠시 후 다시 시도해주세요."
        ) from e

    return ChatResponse(answer=answer, sources=sources)
