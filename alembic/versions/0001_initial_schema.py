"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("instructor", "ta", "admin", name="userrole"),
            nullable=False,
            server_default="ta",
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "courses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("instructor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "exams",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("course_id", sa.Uuid(), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("instructor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "uploaded", "splitting", "split_done", "ocr_running", "ocr_done",
                "grading", "graded", "review", "completed", "failed",
                name="examstatus",
            ),
            nullable=False,
            server_default="uploaded",
        ),
        sa.Column("file_path", sa.String(500)),
        sa.Column("page_count", sa.Integer()),
        sa.Column("student_count", sa.Integer()),
        sa.Column("rubric", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_exams_status", "exams", ["status"])

    op.create_table(
        "answer_regions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("exam_id", sa.Uuid(), sa.ForeignKey("exams.id"), nullable=False),
        sa.Column("student_identifier", sa.String(100), nullable=False),
        sa.Column("question_id", sa.String(50), nullable=False),
        sa.Column("crop_path", sa.String(500)),
        sa.Column("region_confidence", sa.Float()),
        sa.Column(
            "content_type",
            sa.Enum("prose", "math", "mixed", "unknown", name="contenttype"),
            server_default="unknown",
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "ocr_done", "graded", "flagged", "approved", "overridden", name="regionstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("transcript_text", sa.Text()),
        sa.Column("transcript_confidence", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_answer_regions_exam_id", "answer_regions", ["exam_id"])
    op.create_index("ix_answer_regions_status", "answer_regions", ["status"])

    op.create_table(
        "grade_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("answer_region_id", sa.Uuid(), sa.ForeignKey("answer_regions.id"), nullable=False, unique=True),
        sa.Column("ai_score", sa.Float(), nullable=False),
        sa.Column("max_score", sa.Float(), nullable=False),
        sa.Column("final_score", sa.Float()),
        sa.Column("step_results", sa.JSON()),
        sa.Column("overall_justification", sa.Text()),
        sa.Column("reviewed_by", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("override_reason", sa.Text()),
        sa.Column("plagiarism_flagged", sa.Boolean(), server_default="false"),
        sa.Column("plagiarism_similarity_score", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), index=True),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("grade_records")
    op.drop_table("answer_regions")
    op.drop_table("exams")
    op.drop_table("courses")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS regionstatus")
    op.execute("DROP TYPE IF EXISTS contenttype")
    op.execute("DROP TYPE IF EXISTS examstatus")
    op.execute("DROP TYPE IF EXISTS userrole")
