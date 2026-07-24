# app/api/chat_api.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..agents import tutor_agent
from ..core.database import get_db
from ..crud import crud_lessons
from ..schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["Chat"])


def build_lesson_context(lesson: dict) -> str:
    """레슨 본문을 튜터가 읽을 컨텍스트 문자열로 조립한다."""
    parts = [f"제목: {lesson['title']} (레벨: {lesson['level']})",
             lesson["core_concepts"]]

    for example in lesson.get("code_examples") or []:
        parts.append(f"[코드 예시] {example.get('description', '')}\n{example.get('code', '')}")

    return "\n\n".join(parts)


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest, db: Session = Depends(get_db)):
    """학습자 질문에 대한 튜터 답변을 근거 문서 목록과 함께 반환합니다."""
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="질문 내용을 입력해주세요.")

    lesson_context = None
    if request.lesson_id is not None:
        lesson = crud_lessons.get_lesson_detail(db, request.lesson_id)
        if lesson is None:
            raise HTTPException(
                status_code=404, detail=f"레슨을 찾을 수 없습니다: {request.lesson_id}")
        lesson_context = build_lesson_context(lesson)

    try:
        answer, sources = tutor_agent.run_tutor(
            request.message, request.history, lesson_context)
    except tutor_agent.TutorError as e:
        # 원인 예외 메시지는 서버 로그로만 남기고, 클라이언트에는 일반 문구를 준다.
        print(f"  > [Chat] 답변 생성 실패: {e}")
        raise HTTPException(
            status_code=502, detail="답변을 생성하지 못했습니다. 잠시 후 다시 시도해주세요."
        ) from e

    return ChatResponse(answer=answer, sources=sources)
