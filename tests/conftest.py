# tests/conftest.py
"""DB 테스트 인프라.

주의: app.core.database가 import 시점에 create_engine(DATABASE_URL)을 실행하므로,
app 모듈을 import하기 **전에** DATABASE_URL을 SQLite로 고정해야 한다.
(database.py의 load_dotenv()는 이미 설정된 환경 변수를 덮어쓰지 않는다.)
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")
# HS256은 32바이트 이상을 권장한다 (미만이면 PyJWT가 경고)
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-pytest-0123456789")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.models import models  # noqa: F401 — Base.metadata에 테이블 등록


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture()
def client(db_session):
    """get_db를 테스트 세션으로 오버라이드한 TestClient.

    app.main import가 무겁기(임베딩 모델 등) 때문에 fixture 내부에서 지연 import한다.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def auth_user(db_session):
    """테스트용 학습자 계정 하나."""
    from app.crud import crud_users

    return crud_users.create_user(
        db_session, email="learner@example.com", password="password123",
        nickname="학습자")


@pytest.fixture()
def auth_headers(auth_user):
    """auth_user로 로그인한 Authorization 헤더."""
    from app.core.auth import create_access_token

    return {"Authorization": f"Bearer {create_access_token(auth_user.id)}"}
