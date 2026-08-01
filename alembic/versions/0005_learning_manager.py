"""학습 매니저 테이블 (learning_goals, learning_schedules)

목표·일정을 localStorage에서 서버로 이관한다. users(0003)가 선행되어야 한다.
learning_schedules는 P2에서 모델이 붙지만, 마이그레이션 파일을 쪼개지 않기
위해 테이블은 여기서 함께 만든다.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_goals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column("daily_study_time", sa.Integer(), nullable=False),
        sa.Column("linked_level", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learning_goals_id", "learning_goals", ["id"])
    op.create_index("ix_learning_goals_user_id", "learning_goals", ["user_id"])

    op.create_table(
        "learning_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("time", sa.String(length=5), nullable=False),
        sa.Column("content", sa.String(length=255), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["goal_id"], ["learning_goals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learning_schedules_id", "learning_schedules", ["id"])
    op.create_index("ix_learning_schedules_user_id", "learning_schedules", ["user_id"])
    op.create_index("ix_learning_schedules_goal_id", "learning_schedules", ["goal_id"])
    # 주간/월간 범위 조회용 복합 인덱스
    op.create_index("ix_learning_schedules_user_date", "learning_schedules",
                    ["user_id", "date"])


def downgrade() -> None:
    op.drop_index("ix_learning_schedules_user_date", table_name="learning_schedules")
    op.drop_index("ix_learning_schedules_goal_id", table_name="learning_schedules")
    op.drop_index("ix_learning_schedules_user_id", table_name="learning_schedules")
    op.drop_index("ix_learning_schedules_id", table_name="learning_schedules")
    op.drop_table("learning_schedules")
    op.drop_index("ix_learning_goals_user_id", table_name="learning_goals")
    op.drop_index("ix_learning_goals_id", table_name="learning_goals")
    op.drop_table("learning_goals")
