# backend/app/api/generator_api.py
from fastapi import APIRouter
from pydantic import BaseModel
from ..services import qdrant_service, openai_service

router = APIRouter()

class LessonTopic(BaseModel):
    topic: str

@router.post("/lesson/generate", tags=["Generator"])
def generate_new_lesson(request: LessonTopic):
    # 1단계: Qdrant에서 레슨 초안 생성
    draft = qdrant_service.generate_lesson_from_qdrant(request.topic)
    
    # 2단계: OpenAI로 레슨 검증 및 개선
    final_lesson = openai_service.validate_and_refine_lesson(draft)
    
    return final_lesson