"""업로드 문서 테이블 (uploaded_documents)

관리자가 업로드한 RAG 문서의 이력·처리 상태를 저장한다.
벡터 본체는 Qdrant 전용 컬렉션(uploaded-docs)에 있다.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "uploaded_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=10), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default="pending"),
        sa.Column("chunk_count", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filename", name="uq_uploaded_documents_filename"),
    )
    op.create_index("ix_uploaded_documents_id", "uploaded_documents", ["id"])


def downgrade() -> None:
    op.drop_index("ix_uploaded_documents_id", table_name="uploaded_documents")
    op.drop_table("uploaded_documents")
