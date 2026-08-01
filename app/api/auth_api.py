# app/api/auth_api.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.auth import create_access_token, get_current_user, verify_password
from ..core.database import get_db
from ..crud import crud_users
from ..models.models import User
from ..schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/signup", response_model=TokenResponse,
             status_code=status.HTTP_201_CREATED)
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    """회원가입 후 바로 쓸 수 있도록 토큰까지 발급합니다."""
    if crud_users.get_by_email(db, request.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 가입된 이메일입니다.")

    user = crud_users.create_user(
        db, email=request.email, password=request.password, nickname=request.nickname)

    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = crud_users.get_by_email(db, request.email)

    # 이메일 존재 여부가 드러나지 않도록 두 경우 모두 같은 메시지를 준다
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
