# backend/app/core/security.py
import os
import secrets
from typing import Optional
from fastapi import Header, HTTPException


def verify_admin_key(x_admin_api_key: Optional[str] = Header(None, alias="X-Admin-API-Key")):
    """
    관리자 전용 엔드포인트 보호용 의존성.
    요청 헤더 'X-Admin-API-Key'가 환경 변수 ADMIN_API_KEY와 일치해야 통과합니다.
    """
    expected = os.getenv("ADMIN_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="서버에 ADMIN_API_KEY가 설정되지 않았습니다. .env 파일에 ADMIN_API_KEY를 설정해주세요.",
        )
    if not x_admin_api_key or not secrets.compare_digest(x_admin_api_key, expected):
        raise HTTPException(status_code=401, detail="유효하지 않은 관리자 API 키입니다.")
