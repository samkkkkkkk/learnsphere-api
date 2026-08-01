from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..crud import crud_lessons
from ..schemas.schemas import LessonDetail

router = APIRouter()


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
