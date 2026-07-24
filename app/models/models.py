# backend/app/models/models.py
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.orm import relationship
from ..core.database import Base # database.py에서 Base를 가져옴
from datetime import datetime

class User(Base):
    """학습자 계정.

    관리자는 여전히 X-Admin-API-Key 체계를 쓰므로 role 컬럼을 두지 않는다.
    (학습자 인증과 관리자 인증은 별개 경로다.)
    """
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    nickname = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.now)


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
    """[DEPRECATED] 파일 기반 백업 시절의 이력 로그.

    레슨 저장소가 DB(lesson_versions)로 이관되면서 신규 기록은 중단됐다.
    과거 파일 아카이브(generated_content/backup/)와 짝을 이루는 읽기 전용 유산으로,
    테이블 drop은 추후 별도 결정한다.
    """
    __tablename__ = 'lesson_backups'
    id = Column(Integer, primary_key=True, index=True)
    lesson_filename = Column(String(255), nullable=False)
    backup_filename = Column(String(255), nullable=False)
    # 파이프라인/백업 폴더명이 로컬 시간을 사용하므로 기본값도 로컬 시간으로 통일
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(String(100))
    prompt = Column(Text)
    params = Column(JSON)
    action = Column(String(50))  # 'create', 'restore', 'delete' 등


class LessonGeneration(Base):
    """레슨 생성 배치(세대). 파이프라인 1회 실행 또는 일회성 import가 한 세대다."""
    __tablename__ = 'lesson_generations'
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(20), nullable=False)   # 'pipeline' | 'import'
    status = Column(String(20), nullable=False, default='running')  # 'running' | 'completed' | 'failed'
    created_by = Column(String(100))
    prompt = Column(Text)
    params = Column(JSON)
    started_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime)
    total_topics = Column(Integer)
    succeeded = Column(Integer)
    failed_topics = Column(JSON)  # [{"level":..., "topic":..., "error":...}]
    versions = relationship("LessonVersion", back_populates="generation")


class Lesson(Base):
    """레슨의 안정적 정체성. 본문은 lesson_versions에만 있다.

    표시 순번(position)은 세대마다 바뀔 수 있어 키가 아니며,
    (level, slug)가 재생성 간에 같은 레슨을 잇는 유일 키다.
    """
    __tablename__ = 'lessons'
    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(20), nullable=False)    # 초급/중급/고급
    slug = Column(String(255), nullable=False)
    topic = Column(String(255))                   # Qdrant 원본 토픽명
    archived_at = Column(DateTime, nullable=True) # 새 세대에 없는 토픽 → 숨김(삭제 아님)
    created_at = Column(DateTime, default=datetime.now)
    versions = relationship("LessonVersion", back_populates="lesson")
    __table_args__ = (
        UniqueConstraint('level', 'slug', name='uq_lessons_level_slug'),
    )


class LessonVersion(Base):
    """불변 레슨 본문. 복원은 덮어쓰기가 아니라 is_current 이동이다."""
    __tablename__ = 'lesson_versions'
    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey('lessons.id'), nullable=False, index=True)
    generation_id = Column(Integer, ForeignKey('lesson_generations.id'), nullable=False)
    title = Column(String, nullable=False)
    position = Column(Integer)                    # 세대 내 레벨별 순번 (프론트 number)
    core_concepts = Column(Text, nullable=False)
    code_examples = Column(JSON, nullable=False)
    quizzes = Column(JSON, nullable=False)
    is_current = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.now)
    lesson = relationship("Lesson", back_populates="versions")
    generation = relationship("LessonGeneration", back_populates="versions")
    __table_args__ = (
        UniqueConstraint('lesson_id', 'generation_id', name='uq_lesson_versions_lesson_generation'),
        # 레슨당 활성 버전은 DB 레벨에서 최대 1개 (PostgreSQL/SQLite 공용 partial unique index)
        Index('uq_lesson_versions_current', 'lesson_id', unique=True,
              postgresql_where=text('is_current'), sqlite_where=text('is_current')),
    )