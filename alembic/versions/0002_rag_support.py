"""add RAG support: answer_key_path, region embeddings, answer_key_chunks

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # answer_key_path on exams
    op.add_column("exams", sa.Column("answer_key_path", sa.String(500), nullable=True))

    # BGE-M3 embedding on answer_regions
    op.add_column("answer_regions", sa.Column("embedding", sa.JSON(), nullable=True))

    # answer_key_chunks table
    op.create_table(
        "answer_key_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("exam_id", sa.Uuid(), sa.ForeignKey("exams.id"), nullable=False),
        sa.Column("question_id", sa.String(50), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_answer_key_chunks_exam_id", "answer_key_chunks", ["exam_id"])


def downgrade() -> None:
    op.drop_index("ix_answer_key_chunks_exam_id", "answer_key_chunks")
    op.drop_table("answer_key_chunks")
    op.drop_column("answer_regions", "embedding")
    op.drop_column("exams", "answer_key_path")
