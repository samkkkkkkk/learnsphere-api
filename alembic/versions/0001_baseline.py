"""baseline: 기존 3 테이블 (subjects, learning_content, lesson_backups)

기존 create_all() 기반 스키마를 그대로 옮긴 기준점.
이미 테이블이 존재하는 DB는 `alembic stamp 0001`로 처리한다.

Revision ID: 0001
Revises:
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subjects",
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("subject_name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("subject_id"),
        sa.UniqueConstraint("subject_name"),
    )
    op.create_index("ix_subjects_subject_id", "subjects", ["subject_id"])

    op.create_table(
        "learning_content",
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("main_category", sa.String(), nullable=True),
        sa.Column("sub_category", sa.String(), nullable=True),
        sa.Column("topic_group", sa.String(), nullable=True),
        sa.Column("source_path", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("content_id"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.subject_id"]),
        sa.UniqueConstraint("source_path"),
    )
    op.create_index("ix_learning_content_content_id", "learning_content", ["content_id"])

    op.create_table(
        "lesson_backups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lesson_filename", sa.String(length=255), nullable=False),
        sa.Column("backup_filename", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lesson_backups_id", "lesson_backups", ["id"])


def downgrade() -> None:
    op.drop_index("ix_lesson_backups_id", table_name="lesson_backups")
    op.drop_table("lesson_backups")
    op.drop_index("ix_learning_content_content_id", table_name="learning_content")
    op.drop_table("learning_content")
    op.drop_index("ix_subjects_subject_id", table_name="subjects")
    op.drop_table("subjects")
