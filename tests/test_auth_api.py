# tests/test_auth_api.py
"""학습자 인증 API 테스트."""
from datetime import datetime, timedelta, timezone

import jwt

from app.core import auth
from app.crud import crud_users

SIGNUP = {
    "email": "new@example.com",
    "password": "password123",
    "nickname": "새학습자",
}


# --- 가입 ---

def test_signup_creates_user(client, db_session):
    response = client.post("/api/v1/auth/signup", json=SIGNUP)

    assert response.status_code == 201
    assert response.json()["access_token"]
    assert crud_users.get_by_email(db_session, "new@example.com") is not None


def test_signup_duplicate_email_returns_409(client, auth_user):
    response = client.post("/api/v1/auth/signup", json={
        **SIGNUP, "email": auth_user.email})

    assert response.status_code == 409


def test_signup_invalid_email_returns_422(client):
    response = client.post("/api/v1/auth/signup", json={
        **SIGNUP, "email": "not-an-email"})

    assert response.status_code == 422


def test_signup_short_password_returns_422(client):
    response = client.post("/api/v1/auth/signup", json={**SIGNUP, "password": "short"})

    assert response.status_code == 422


def test_password_stored_as_hash(client, db_session):
    client.post("/api/v1/auth/signup", json=SIGNUP)

    user = crud_users.get_by_email(db_session, "new@example.com")
    assert user.password_hash != SIGNUP["password"]
    assert auth.verify_password(SIGNUP["password"], user.password_hash)


# --- 로그인 ---

def test_login_returns_token(client, auth_user):
    response = client.post("/api/v1/auth/login", json={
        "email": auth_user.email, "password": "password123"})

    assert response.status_code == 200
    assert auth.decode_token(response.json()["access_token"]) == auth_user.id


def test_login_wrong_password_returns_401(client, auth_user):
    response = client.post("/api/v1/auth/login", json={
        "email": auth_user.email, "password": "wrong-password"})

    assert response.status_code == 401


def test_login_unknown_email_returns_401(client):
    """가입 여부가 드러나지 않도록 오답 비밀번호와 같은 응답을 준다."""
    response = client.post("/api/v1/auth/login", json={
        "email": "nobody@example.com", "password": "password123"})

    assert response.status_code == 401


# --- 현재 사용자 ---

def test_me_with_valid_token_returns_user(client, auth_user, auth_headers):
    response = client.get("/api/v1/auth/me", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == auth_user.email
    assert body["nickname"] == "학습자"
    assert "password_hash" not in body  # 해시가 새어나가지 않아야 한다


def test_me_without_token_returns_401(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_with_malformed_token_returns_401(client):
    response = client.get("/api/v1/auth/me",
                          headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401


def test_me_with_expired_token_returns_401(client, auth_user):
    expired = jwt.encode(
        {
            "sub": str(auth_user.id),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        auth._get_secret_key(),
        algorithm=auth.JWT_ALGORITHM,
    )

    response = client.get("/api/v1/auth/me",
                          headers={"Authorization": f"Bearer {expired}"})

    assert response.status_code == 401


def test_me_with_token_signed_by_other_secret_returns_401(client, auth_user):
    forged = jwt.encode({"sub": str(auth_user.id)}, "other-secret", algorithm="HS256")

    response = client.get("/api/v1/auth/me",
                          headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401


def test_me_with_deleted_user_returns_401(client, db_session, auth_user, auth_headers):
    db_session.delete(auth_user)
    db_session.commit()

    assert client.get("/api/v1/auth/me", headers=auth_headers).status_code == 401
