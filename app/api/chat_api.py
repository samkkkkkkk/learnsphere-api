# app/api/chat_api.py
"""튜터 챗 API.

Phase 9부터 대화는 DB에 남는다. 이력은 요청 본문이 아니라 DB에서 읽으므로,
클라이언트가 과거 대화를 들고 다니지 않아도 맥락이 이어진다.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..agents import tutor_agent
from ..core.auth import get_current_user
from ..core.database import get_db
from ..crud import crud_chat, crud_lessons
from ..models.models import ChatSession, User
from ..schemas.chat import (
    ChatResponse, ChatTurn, MessageOut, MessageRequest, SessionCreateRequest,
    SessionOut,
)

router = APIRouter(prefix="/chat", tags=["Chat"])


def build_lesson_context(lesson: dict) -> str:
    """레슨 본문을 튜터가 읽을 컨텍스트 문자열로 조립한다."""
    parts = [f"제목: {lesson['title']} (레벨: {lesson['level']})",
             lesson["core_concepts"]]

    for example in lesson.get("code_examples") or []:
        parts.append(f"[코드 예시] {example.get('description', '')}\n{example.get('code', '')}")

    return "\n\n".join(parts)


def _require_session(db: Session, session_id: int, user: User) -> ChatSession:
    """본인 세션만 통과시킨다. 남의 세션은 403."""
    session = crud_chat.get_owned_session(db, session_id, user.id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="접근할 수 없는 대화입니다.")
    return session


# --- 세션 ---

@router.post("/sessions", response_model=SessionOut,
             status_code=status.HTTP_201_CREATED)
def create_session(request: SessionCreateRequest,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    if request.lesson_id is not None and \
            crud_lessons.get_lesson_detail(db, request.lesson_id) is None:
        raise HTTPException(
            status_code=404, detail=f"레슨을 찾을 수 없습니다: {request.lesson_id}")

    return crud_chat.create_session(db, user.id, request.lesson_id)


@router.get("/sessions", response_model=List[SessionOut])
def list_sessions(db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    return crud_chat.list_sessions(db, user.id)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    crud_chat.delete_session(db, _require_session(db, session_id, user))


@router.get("/sessions/{session_id}/messages", response_model=List[MessageOut])
def list_messages(session_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    _require_session(db, session_id, user)
    return crud_chat.list_messages(db, session_id)


# --- 메시지 전송 ---

@router.post("/sessions/{session_id}/messages", response_model=ChatResponse)
def send_message(session_id: int, request: MessageRequest,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """질문을 보내고 답변을 받는다. 질문/답변 모두 DB에 남는다."""
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="질문 내용을 입력해주세요.")

    session = _require_session(db, session_id, user)

    # 세션에 묶인 레슨이 있으면 그 본문을 우선 근거로 넣는다
    lesson_context = None
    if session.lesson_id is not None:
        lesson = crud_lessons.get_lesson_detail(db, session.lesson_id)
        if lesson is not None:
            lesson_context = build_lesson_context(lesson)

    # 이번 질문을 저장하기 전의 대화가 이력이 된다
    history = [ChatTurn(role=message.role, content=message.content)
               for message in crud_chat.list_messages(db, session.id)]

    crud_chat.add_message(db, session, "user", request.message)

    try:
        answer, sources = tutor_agent.run_tutor(
            request.message, history, lesson_context)
    except tutor_agent.TutorError as e:
        # 원인 예외 메시지는 서버 로그로만 남기고, 클라이언트에는 일반 문구를 준다.
        print(f"  > [Chat] 답변 생성 실패: {e}")
        raise HTTPException(
            status_code=502, detail="답변을 생성하지 못했습니다. 잠시 후 다시 시도해주세요."
        ) from e

    crud_chat.add_message(db, session, "assistant", answer, sources)

    return ChatResponse(answer=answer, sources=sources)
