# backend/app/models/models.py
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from ..core.database import Base # database.py에서 Base를 가져옴
from datetime import datetime

class Subject(Base):
    __tablename__ = 'subjects'
    subject_id = Column(Integer, primary_key=True, index=True)
    subject_name = Column(String, unique=True, nullable=False)
    description = Column(Text)
    contents = relationship("LearningContent", back_populates="subject")

class LearningContent(Base):
    __tablename__ = 'learning_content'
    content_id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey('subjects.subject_id'), nullable=False)
    title = Column(String, nullable=False)
    main_category = Column(String)
    sub_category = Column(String)
    topic_group = Column(String, nullable=True)
    source_path = Column(String, unique=True)
    subject = relationship("Subject", back_populates="contents")

class LessonBackup(Base):
    __tablename__ = 'lesson_backups'
    id = Column(Integer, primary_key=True, index=True)
    lesson_filename = Column(String(255), nullable=False)
    backup_filename = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100))
    prompt = Column(Text)
    params = Column(JSON)
    action = Column(String(50))  # 'create', 'restore', 'delete' 등