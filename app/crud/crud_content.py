# backend/app/crud/crud_content.py
from sqlalchemy.orm import Session
from ..models import models

def get_contents_by_subject(db: Session, subject_name: str):
    # 'subjects' 테이블과 'learning_content' 테이블을 조인하여
    # subject_name이 일치하는 모든 콘텐츠를 조회합니다.
    return db.query(models.LearningContent).join(models.Subject).filter(models.Subject.subject_name.ilike(subject_name)).all()
