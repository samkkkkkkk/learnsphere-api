"""레슨 퀴즈 진도 테이블 (lesson_progress)

퀴즈 완료 기록을 localStorage에서 서버로 이관한다. (user, lesson)당 1행.
learning_manager(0005)가 선행되어야 한다.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lesson_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "lesson_id",
                            name="uq_lesson_progress_user_lesson"),
    )
    op.create_index("ix_lesson_progress_id", "lesson_progress", ["id"])
    op.create_index("ix_lesson_progress_user_id", "lesson_progress", ["user_id"])
    op.create_index("ix_lesson_progress_lesson_id", "lesson_progress", ["lesson_id"])


def downgrade() -> None:
    op.drop_index("ix_lesson_progress_lesson_id", table_name="lesson_progress")
    op.drop_index("ix_lesson_progress_user_id", table_name="lesson_progress")
    op.drop_index("ix_lesson_progress_id", table_name="lesson_progress")
    op.drop_table("lesson_progress")
