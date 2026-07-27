# app/crud/crud_users.py
from typing import Optional

from sqlalchemy.orm import Session

from ..core.auth import hash_password
from ..models.models import User


def get_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def create_user(db: Session, email: str, password: str, nickname: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password),
        nickname=nickname,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
