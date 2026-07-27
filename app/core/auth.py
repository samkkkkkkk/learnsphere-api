# app/core/auth.py
"""학습자 인증 (비밀번호 해시 + JWT).

관리자 인증(core/security.py의 X-Admin-API-Key)과는 별개 경로다.
passlib은 bcrypt 4.x와 호환 문제가 있어 bcrypt 패키지를 직접 쓴다.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..models.models import User
from .database import get_db

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))  # 기본 7일

_bearer = HTTPBearer(auto_error=False)


def _get_secret_key() -> str:
    """JWT 서명 키. 미설정이면 503으로 막는다 (빈 키로 서명하지 않도록)."""
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="서버에 JWT_SECRET_KEY가 설정되지 않았습니다.",
        )
    return secret


# --- 비밀번호 ---

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # 해시 형식이 깨진 경우 (예: 평문이 저장됨) 인증 실패로 처리
        return False


# --- 토큰 ---

def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _get_secret_key(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[int]:
    """토큰에서 user_id를 꺼낸다. 만료·위조·형식 오류면 None."""
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        return None


# --- 의존성 ---

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="로그인이 필요합니다.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Authorization: Bearer 토큰으로 현재 사용자를 찾는다."""
    if credentials is None:
        raise _UNAUTHORIZED

    user_id = decode_token(credentials.credentials)
    if user_id is None:
        raise _UNAUTHORIZED

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise _UNAUTHORIZED

    return user
