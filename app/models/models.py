# backend/app/models/models.py
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from ..core.database import Base # database.py에서 Base를 가져옴

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