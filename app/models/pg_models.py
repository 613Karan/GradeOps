"""
PostgreSQL models via SQLAlchemy.

All data lives here — rubrics, transcripts, and grading results stored as
JSON columns directly on the relevant tables (no MongoDB needed).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, JSON, String, Text, Uuid
)
from sqlalchemy import Enum as _SAEnum


def _enum(py_enum, name):
    return _SAEnum(
        py_enum,
        name=name,
        values_callable=lambda obj: [e.value for e in obj],
    )
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


def _utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    INSTRUCTOR = "instructor"
    TA = "ta"
    ADMIN = "admin"


class ExamStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    SPLITTING = "splitting"
    SPLIT_DONE = "split_done"
    OCR_RUNNING = "ocr_running"
    OCR_DONE = "ocr_done"
    GRADING = "grading"
    GRADED = "graded"
    REVIEW = "review"
    COMPLETED = "completed"
    FAILED = "failed"


class RegionStatus(str, enum.Enum):
    PENDING = "pending"
    OCR_DONE = "ocr_done"
    GRADED = "graded"
    FLAGGED = "flagged"
    APPROVED = "approved"
    OVERRIDDEN = "overridden"


class ContentType(str, enum.Enum):
    PROSE = "prose"
    MATH = "math"
    MIXED = "mixed"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(_enum(UserRole, "userrole"), nullable=False, default=UserRole.TA)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    created_exams = relationship("Exam", back_populates="instructor", foreign_keys="[Exam.instructor_id]")
    grade_overrides = relationship("GradeRecord", back_populates="reviewed_by_user")


class Course(Base):
    __tablename__ = "courses"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    instructor_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    exams = relationship("Exam", back_populates="course")


class Exam(Base):
    __tablename__ = "exams"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(Uuid(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    instructor_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    status = Column(_enum(ExamStatus, "examstatus"), default=ExamStatus.UPLOADED, nullable=False, index=True)

    # Local path or Cloudinary URL to original PDF
    file_path = Column(String(500))
    # Local path to instructor-uploaded answer key PDF
    answer_key_path = Column(String(500))
    # True → math-heavy subject; pipeline routes OCR to Gemini Flash instead of Groq
    is_math_subject = Column(Boolean, default=False, nullable=False)
    page_count = Column(Integer)
    student_count = Column(Integer)

    # Full rubric document stored as JSON
    rubric = Column(JSON)

    created_at = Column(DateTime(timezone=True), default=_utcnow)
    completed_at = Column(DateTime(timezone=True))

    course = relationship("Course", back_populates="exams")
    instructor = relationship("User", back_populates="created_exams", foreign_keys=[instructor_id])
    answer_regions = relationship("AnswerRegion", back_populates="exam")


class AnswerRegion(Base):
    """One cropped answer image extracted from a scanned page."""
    __tablename__ = "answer_regions"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(Uuid(as_uuid=True), ForeignKey("exams.id"), nullable=False, index=True)

    student_identifier = Column(String(100), nullable=False)
    question_id = Column(String(50), nullable=False)

    # Local path or Cloudinary URL to cropped image
    crop_path = Column(String(500))

    region_confidence = Column(Float)
    content_type = Column(_enum(ContentType, "contenttype"), default=ContentType.UNKNOWN)
    status = Column(_enum(RegionStatus, "regionstatus"), default=RegionStatus.PENDING, nullable=False, index=True)

    # OCR output stored directly
    transcript_text = Column(Text)
    transcript_confidence = Column(Float)

    # BGE-M3 embedding of transcript (populated after OCR)
    embedding = Column(JSON)

    created_at = Column(DateTime(timezone=True), default=_utcnow)

    exam = relationship("Exam", back_populates="answer_regions")
    grade_record = relationship("GradeRecord", back_populates="answer_region", uselist=False)


class GradeRecord(Base):
    __tablename__ = "grade_records"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    answer_region_id = Column(Uuid(as_uuid=True), ForeignKey("answer_regions.id"), unique=True, nullable=False)

    ai_score = Column(Float, nullable=False)
    max_score = Column(Float, nullable=False)
    final_score = Column(Float)

    # Per-step breakdown and justification stored as JSON
    step_results = Column(JSON)
    overall_justification = Column(Text)

    # TA review
    reviewed_by = Column(Uuid(as_uuid=True), ForeignKey("users.id"))
    reviewed_at = Column(DateTime(timezone=True))
    override_reason = Column(Text)

    plagiarism_flagged = Column(Boolean, default=False)
    plagiarism_similarity_score = Column(Float)

    created_at = Column(DateTime(timezone=True), default=_utcnow)

    answer_region = relationship("AnswerRegion", back_populates="grade_record")
    reviewed_by_user = relationship("User", back_populates="grade_overrides")


class AnswerKeyChunk(Base):
    """One embedded chunk from the instructor-uploaded answer key PDF."""
    __tablename__ = "answer_key_chunks"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(Uuid(as_uuid=True), ForeignKey("exams.id"), nullable=False, index=True)
    question_id = Column(String(50), nullable=False)  # "q1", "q2", or "general"
    chunk_text = Column(Text, nullable=False)
    embedding = Column(JSON)  # list[float] from BGE-M3
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class AuditLog(Base):
    """Immutable append-only log for compliance."""
    __tablename__ = "audit_logs"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id = Column(Uuid(as_uuid=True), ForeignKey("users.id"))
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(36), nullable=False)
    action = Column(String(100), nullable=False)
    detail = Column(Text)
    created_at = Column(DateTime(timezone=True), default=_utcnow, index=True)
