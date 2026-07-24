# app/crud/crud_chat.py
from typing import List, Optional, Sequence

from sqlalchemy.orm import Session

from ..models.models import ChatMessage, ChatSession

# 세션 제목은 첫 질문 앞부분에서 딴다.
TITLE_MAX_LENGTH = 40


def create_session(db: Session, user_id: int,
                   lesson_id: Optional[int] = None) -> ChatSession:
    session = ChatSession(user_id=user_id, lesson_id=lesson_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_sessions(db: Session, user_id: int) -> List[ChatSession]:
    """본인 세션만 최근 갱신 순으로 반환한다."""
    return (db.query(ChatSession)
            .filter(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
            .all())


def get_owned_session(db: Session, session_id: int,
                      user_id: int) -> Optional[ChatSession]:
    """소유자가 일치하는 세션만 돌려준다. 남의 세션은 None."""
    return (db.query(ChatSession)
            .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
            .first())


def delete_session(db: Session, session: ChatSession) -> None:
    db.delete(session)  # 메시지는 cascade로 함께 삭제
    db.commit()


def list_messages(db: Session, session_id: int) -> List[ChatMessage]:
    return (db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id)
            .all())


def add_message(db: Session, session: ChatSession, role: str, content: str,
                sources: Optional[Sequence[str]] = None) -> ChatMessage:
    message = ChatMessage(
        session_id=session.id,
        role=role,
        content=content,
        sources=list(sources) if sources else None,
    )
    db.add(message)

    # 첫 질문으로 제목을 채운다 (목록에서 대화를 구분할 수 있도록)
    if role == "user" and not session.title:
        session.title = content[:TITLE_MAX_LENGTH]

    db.commit()
    db.refresh(message)
    return message
