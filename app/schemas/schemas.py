# backend/app/schemas/schemas.py
from pydantic import BaseModel
from typing import Optional

class LearningContentBase(BaseModel):
    title: str
    main_category: str
    sub_category: str
    topic_group: Optional[str] = None

    class Config:
        from_attributes = True # SQLAlchemy 모델과 호환되도록 설정

class SubjectBase(BaseModel):
    subject_name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True