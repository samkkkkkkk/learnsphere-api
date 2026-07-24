import json
import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..crud import crud_lessons
from ..schemas.schemas import LessonDetail

router = APIRouter()

# JSON 파일이 저장된 디렉토리 경로
CONTENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'generated_content'))


def resolve_lesson_path(filename: str) -> str:
    """
    파일명을 검증하고 CONTENT_DIR 내부의 절대 경로로 변환합니다.
    경로 구분자가 포함되거나 CONTENT_DIR 밖을 가리키는 요청은 거부합니다.
    """
    if os.path.basename(filename) != filename or not filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="유효하지 않은 파일명입니다.")
    file_path = os.path.abspath(os.path.join(CONTENT_DIR, filename))
    if os.path.commonpath([file_path, CONTENT_DIR]) != CONTENT_DIR:
        raise HTTPException(status_code=400, detail="유효하지 않은 파일 경로입니다.")
    return file_path

# 응답 모델 정의 (어떤 형태의 JSON이든 받을 수 있도록)
class LessonContent(BaseModel):
    title: str
    level: str
    core_concepts: str
    code_examples: list
    quizzes: list

# --- DB 기반 레슨 조회 (신규 — 구 파일 기반 /lesson/* 은 프론트 전환 후 제거 예정) ---

@router.get("/lessons", tags=["Lesson"])
def get_lessons_index(db: Session = Depends(get_db)):
    """활성(is_current) 레슨 목록을 레벨별로 그룹화해 반환합니다.

    형태: { "초급": [{id, title, number}], "중급": [...], "고급": [...] }
    """
    return crud_lessons.get_lesson_index(db)


@router.get("/lessons/{lesson_id}", response_model=LessonDetail,
            response_model_exclude_none=True, tags=["Lesson"])
def get_lesson(lesson_id: int, db: Session = Depends(get_db)):
    """레슨의 활성 버전 본문을 반환합니다."""
    detail = crud_lessons.get_lesson_detail(db, lesson_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"레슨을 찾을 수 없습니다: {lesson_id}")
    return detail


# --- 파일 기반 레슨 조회 (구 API — 유지 중) ---

@router.get("/lesson/index", tags=["Lesson"])
def get_lesson_index():
    """
    생성된 학습 콘텐츠의 인덱스 파일을 읽어서 반환합니다.
    """
    index_file_path = os.path.join(CONTENT_DIR, "index.json")
    
    if not os.path.exists(index_file_path):
        raise HTTPException(status_code=404, detail="인덱스 파일을 찾을 수 없습니다. 먼저 콘텐츠를 생성해주세요.")
    
    try:
        with open(index_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"인덱스 파일 읽기 중 오류가 발생했습니다: {str(e)}")

@router.get("/lesson/{filename}", response_model=LessonContent, tags=["Lesson"])
def get_lesson_content(filename: str):
    """
    생성된 학습 콘텐츠 JSON 파일을 읽어서 반환합니다.
    """
    file_path = resolve_lesson_path(filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"해당 파일을 찾을 수 없습니다: {filename}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 읽기 중 오류가 발생했습니다: {str(e)}")