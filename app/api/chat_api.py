# app/api/chat_api.py
"""튜터 챗 API.

Phase 9부터 대화는 DB에 남는다. 이력은 요청 본문이 아니라 DB에서 읽으므로,
클라이언트가 과거 대화를 들고 다니지 않아도 맥락이 이어진다.
"""
import json
from typing import AsyncIterator, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..agents import tutor_agent
from ..core.auth import get_current_user
from ..core.database import get_db, get_session_scope
from ..crud import crud_chat, crud_lessons
from ..models.models import ChatSession, User
from ..schemas.chat import (
    ChatResponse, ChatTurn, MessageOut, MessageRequest, SessionCreateRequest,
    SessionOut,
)

router = APIRouter(prefix="/chat", tags=["Chat"])

# 답변 생성이 실패했을 때 클라이언트에 보여줄 문구 (내부 오류 상세는 로그로만 남긴다)
GENERATION_ERROR_MESSAGE = "답변을 생성하지 못했습니다. 잠시 후 다시 시도해주세요."


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

def _prepare_turn(db: Session, session: ChatSession, message: str
                  ) -> Tuple[List[ChatTurn], Optional[str]]:
    """질문을 저장하고, 튜터에 넘길 (이력, 레슨 컨텍스트)를 만든다.

    이력은 이번 질문을 저장하기 **전**의 대화다.
    """
    # 세션에 묶인 레슨이 있으면 그 본문을 우선 근거로 넣는다
    lesson_context = None
    if session.lesson_id is not None:
        lesson = crud_lessons.get_lesson_detail(db, session.lesson_id)
        if lesson is not None:
            lesson_context = build_lesson_context(lesson)

    history = [ChatTurn(role=stored.role, content=stored.content)
               for stored in crud_chat.list_messages(db, session.id)]

    crud_chat.add_message(db, session, "user", message)

    return history, lesson_context


@router.post("/sessions/{session_id}/messages", response_model=ChatResponse)
def send_message(session_id: int, request: MessageRequest,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    """질문을 보내고 답변을 받는다. 질문/답변 모두 DB에 남는다.

    Phase 11에서 스트리밍(`/stream`)이 생겼지만, 이 엔드포인트는 폴백으로 남긴다.
    """
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="질문 내용을 입력해주세요.")

    session = _require_session(db, session_id, user)
    history, lesson_context = _prepare_turn(db, session, request.message)

    try:
        answer, sources = tutor_agent.run_tutor(
            request.message, history, lesson_context)
    except tutor_agent.TutorError as e:
        # 원인 예외 메시지는 서버 로그로만 남기고, 클라이언트에는 일반 문구를 준다.
        print(f"  > [Chat] 답변 생성 실패: {e}")
        raise HTTPException(
            status_code=502, detail=GENERATION_ERROR_MESSAGE) from e

    crud_chat.add_message(db, session, "assistant", answer, sources)

    return ChatResponse(answer=answer, sources=sources)


# --- 스트리밍 전송 ---

def _sse(payload: dict) -> str:
    """SSE 한 덩어리로 감싼다. 한글이 그대로 보이도록 ensure_ascii=False."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def answer_stream(question: str, history: List[ChatTurn],
                        lesson_context: Optional[str], session_id: int,
                        user_id: int, session_scope) -> AsyncIterator[str]:
    """토큰을 SSE로 흘리고, 끝나면 받아 둔 답변을 DB에 남긴다.

    요청 의존성이 준 DB 세션은 응답 본문이 끝나기 전에 닫힐 수 있으므로,
    저장은 `session_scope()`로 새 세션을 짧게 열어서 한다.

    중도 이탈(제너레이터 close)도 `finally`를 타므로 부분 답변이 보존된다.
    """
    chunks: List[str] = []
    sources: List[str] = []

    try:
        async for event in tutor_agent.astream_tutor(
                question, history, lesson_context):
            if event["type"] == "token":
                chunks.append(event["content"])
                yield _sse(event)
            elif event["type"] == "sources":
                sources = event["sources"]
                yield _sse({"type": "done", "sources": sources})
    except tutor_agent.TutorError as e:
        # 내부 오류 상세는 서버 로그로만. 클라이언트는 무한 대기 대신 error를 받는다.
        print(f"  > [Chat] 스트리밍 답변 생성 실패: {e}")
        yield _sse({"type": "error", "detail": GENERATION_ERROR_MESSAGE})
    finally:
        answer = "".join(chunks)
        if answer:
            with session_scope() as fresh_db:
                stored = crud_chat.get_owned_session(fresh_db, session_id, user_id)
                if stored is not None:
                    crud_chat.add_message(
                        fresh_db, stored, "assistant", answer, sources)


@router.post("/sessions/{session_id}/stream")
async def stream_message(session_id: int, request: MessageRequest,
                         db: Session = Depends(get_db),
                         user: User = Depends(get_current_user),
                         session_scope=Depends(get_session_scope)):
    """질문에 대한 답변을 토큰 단위로 흘려보낸다 (Server-Sent Events).

    이벤트는 세 종류다.
      - `{"type":"token","content":"..."}` — 답변 조각
      - `{"type":"done","sources":[...]}` — 정상 종료
      - `{"type":"error","detail":"..."}` — 생성 실패 (연결은 정상 종료)
    """
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="질문 내용을 입력해주세요.")

    session = _require_session(db, session_id, user)
    # 스트림이 시작되면 요청 세션은 곧 닫히므로, 필요한 값은 지금 꺼내 둔다.
    user_id = user.id

    # 사용자 메시지는 스트림 시작 **전에** 저장한다 (클라이언트가 바로 끊어도 남도록)
    history, lesson_context = _prepare_turn(db, session, request.message)

    return StreamingResponse(
        answer_stream(request.message, history, lesson_context, session_id,
                      user_id, session_scope),
        media_type="text/event-stream",
        # 프록시가 SSE를 버퍼링하면 타이핑 효과가 사라진다.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
