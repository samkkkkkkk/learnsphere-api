import json
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# JSON 파일이 저장된 디렉토리 경로
CONTENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'generated_content'))

# 응답 모델 정의 (어떤 형태의 JSON이든 받을 수 있도록)
class LessonContent(BaseModel):
    topic: str
    concepts: str
    examples: list
    quiz: dict

@router.get("/lesson/{topic_name}", response_model=LessonContent, tags=["Lesson"])
def get_lesson_content(topic_name: str):
    """
    생성된 학습 콘텐츠 JSON 파일을 읽어서 반환합니다.
    """
    file_path = os.path.join(CONTENT_DIR, f"{topic_name.lower().replace(' ', '_')}_lesson.json")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="해당 주제의 학습 콘텐츠를 찾을 수 없습니다.")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data