import json
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# JSON 파일이 저장된 디렉토리 경로
CONTENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'generated_content'))

# 응답 모델 정의 (어떤 형태의 JSON이든 받을 수 있도록)
class LessonContent(BaseModel):
    title: str
    level: str
    core_concepts: str
    code_examples: list
    quizzes: list

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
    file_path = os.path.join(CONTENT_DIR, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"해당 파일을 찾을 수 없습니다: {filename}")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 읽기 중 오류가 발생했습니다: {str(e)}")