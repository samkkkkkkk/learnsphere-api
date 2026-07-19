# backend/app/main.py

from fastapi import FastAPI, Depends, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List
from fastapi.middleware.cors import CORSMiddleware
import os

from .core.database import engine, get_db
from .core.security import verify_admin_key
from .models import models
from .schemas import schemas
from .crud import crud_content
from .services import content_pipeline_service

# --- API 라우터 임포트 ---
from .api import lesson_api, admin_api

# 데이터베이스 테이블 생성
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="React Learning Platform API")

# --- (추가) CORS 미들웨어 설정 ---
# 프론트엔드 주소에서의 요청을 허용합니다.
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 정적 파일 서빙 설정 ---
# 생성된 콘텐츠 파일들을 정적 파일로 제공
generated_content_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'generated_content'))
if os.path.exists(generated_content_path):
    app.mount("/static/content", StaticFiles(directory=generated_content_path), name="content")

# --- (수정) API 라우터 등록 ---
# lesson_api와 admin_api만 등록합니다.
app.include_router(lesson_api.router, prefix="/api/v1")
app.include_router(admin_api.router, prefix="/api/v1")


@app.get("/", tags=["Root"])
def read_root():
    return {"message": "Welcome to the Learning Platform API!"}

@app.get("/api/health", tags=["Health Check"])
def health_check():
    return {"status": "ok"}

# PostgreSQL DB에서 콘텐츠 목록을 가져오는 API
@app.get("/api/v1/contents/{subject_name}", response_model=List[schemas.LearningContentBase], tags=["Contents"])
def read_contents_by_subject(subject_name: str, db: Session = Depends(get_db)):
    contents = crud_content.get_contents_by_subject(db, subject_name=subject_name)
    return contents

# Qdrant DB 변경 시 호출되는 웹훅 (전체 재생성을 트리거하므로 관리자 키 인증 필요)
@app.post("/api/v1/webhooks/content-updated", tags=["Webhooks"], dependencies=[Depends(verify_admin_key)])
def handle_content_update(background_tasks: BackgroundTasks):
    """
    Qdrant DB 변경과 같은 이벤트가 발생했을 때 호출되는 웹훅.
    실제 작업은 백그라운드로 넘기고 즉시 응답합니다.
    (현재는 전체 콘텐츠를 재생성하는 관리자 작업과 동일하게 동작합니다.)
    """
    print("웹훅 수신: 콘텐츠 업데이트 파이프라인을 백그라운드에서 시작합니다.")
    
    # (수정) 호출하는 함수를 명확하게 지정
    background_tasks.add_task(content_pipeline_service.run_full_content_generation)
    
    return {"message": "Content update pipeline accepted and running in the background."}
