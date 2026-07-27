"""레슨 본문 저장용 테이블 3종 (lesson_generations, lessons, lesson_versions)

레슨 저장소를 generated_content/ 파일에서 PostgreSQL로 이관하기 위한 스키마.
설계 근거는 DB_MIGRATION_PLAN.md §3 참고.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lesson_generations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("total_topics", sa.Integer(), nullable=True),
        sa.Column("succeeded", sa.Integer(), nullable=True),
        sa.Column("failed_topics", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lesson_generations_id", "lesson_generations", ["id"])

    op.create_table(
        "lessons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("level", "slug", name="uq_lessons_level_slug"),
    )
    op.create_index("ix_lessons_id", "lessons", ["id"])

    op.create_table(
        "lesson_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("generation_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("core_concepts", sa.Text(), nullable=False),
        sa.Column("code_examples", sa.JSON(), nullable=False),
        sa.Column("quizzes", sa.JSON(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"]),
        sa.ForeignKeyConstraint(["generation_id"], ["lesson_generations.id"]),
        sa.UniqueConstraint("lesson_id", "generation_id", name="uq_lesson_versions_lesson_generation"),
    )
    op.create_index("ix_lesson_versions_id", "lesson_versions", ["id"])
    op.create_index("ix_lesson_versions_lesson_id", "lesson_versions", ["lesson_id"])
    # 레슨당 활성 버전 최대 1개 보장 (partial unique index)
    op.create_index(
        "uq_lesson_versions_current",
        "lesson_versions",
        ["lesson_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
        sqlite_where=sa.text("is_current"),
    )


def downgrade() -> None:
    op.drop_index("uq_lesson_versions_current", table_name="lesson_versions")
    op.drop_index("ix_lesson_versions_lesson_id", table_name="lesson_versions")
    op.drop_index("ix_lesson_versions_id", table_name="lesson_versions")
    op.drop_table("lesson_versions")
    op.drop_index("ix_lessons_id", table_name="lessons")
    op.drop_table("lessons")
    op.drop_index("ix_lesson_generations_id", table_name="lesson_generations")
    op.drop_table("lesson_generations")
