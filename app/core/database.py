# backend/app/core/database.py
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 데이터베이스 세션을 가져오는 함수 (의존성 주입용)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    """요청과 별개로 짧게 쓰고 닫는 세션.

    스트리밍 응답처럼 요청 의존성의 수명보다 오래 사는 작업이 쓴다.
    (get_db가 준 세션은 응답 본문이 끝나기 전에 닫힐 수 있다.)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_scope():
    """session_scope 자체를 주입한다 (테스트에서 갈아끼울 수 있도록 의존성으로 노출)."""
    return session_scope