"""
Pydantic schemas for API request / response bodies.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: str
    role: str


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(min_length=8)
    role: str = "ta"


class UserRead(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

class CourseCreate(BaseModel):
    code: str = Field(max_length=50)
    name: str = Field(max_length=255)


class CourseRead(BaseModel):
    id: UUID
    code: str
    name: str
    instructor_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Rubric (validated before insertion; stored as JSON in Exam.rubric)
# ---------------------------------------------------------------------------

class LogicStepIn(BaseModel):
    id: str
    description: str
    points: float = Field(gt=0)
    required_keywords: list[str] = []
    numeric_tolerance_pct: Optional[float] = None


class QuestionRubricIn(BaseModel):
    question_id: str
    question_text: str
    max_marks: float = Field(gt=0)
    logic_steps: list[LogicStepIn] = Field(min_length=1)
    answer_key_text: Optional[str] = None


class RubricCreate(BaseModel):
    questions: list[QuestionRubricIn] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Exams
# ---------------------------------------------------------------------------

class ExamCreate(BaseModel):
    title: str
    course_id: UUID
    rubric: RubricCreate


class ExamRead(BaseModel):
    id: UUID
    title: str
    course_id: UUID
    status: str
    file_path: Optional[str]
    is_math_subject: bool
    page_count: Optional[int]
    student_count: Optional[int]
    rubric: Optional[dict]
    created_at: datetime
    completed_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class ExamStatusUpdate(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# Answer regions
# ---------------------------------------------------------------------------

class AnswerRegionRead(BaseModel):
    id: UUID
    exam_id: UUID
    student_identifier: str
    question_id: str
    crop_path: Optional[str]
    region_confidence: Optional[float]
    content_type: str
    status: str
    transcript_text: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RegionSplitRequest(BaseModel):
    split_points: list[int] = Field(min_length=1, description="Y-pixel offsets within the crop image")
    question_ids: list[str] = Field(
        description="Label for each resulting band (len must equal len(split_points)+1). Empty string = discard that band."
    )

    @model_validator(mode="after")
    def _check_lengths(self):
        expected = len(self.split_points) + 1
        if len(self.question_ids) != expected:
            raise ValueError(
                f"question_ids must have exactly {expected} entries "
                f"(one per band), got {len(self.question_ids)}"
            )
        return self


# ---------------------------------------------------------------------------
# Grading / TA review
# ---------------------------------------------------------------------------

class GradeRead(BaseModel):
    id: UUID
    answer_region_id: UUID
    ai_score: float
    max_score: float
    final_score: Optional[float]
    step_results: Optional[list[dict]]
    overall_justification: Optional[str]
    reviewed_by: Optional[UUID]
    reviewed_at: Optional[datetime]
    override_reason: Optional[str]
    plagiarism_flagged: bool
    plagiarism_similarity_score: Optional[float]

    model_config = ConfigDict(from_attributes=True)


class TAReviewSubmit(BaseModel):
    """TA approves or overrides an AI grade."""
    final_score: float
    override_reason: Optional[str] = None


class ReviewDashboardItem(BaseModel):
    """One item in the TA review queue — all data from PostgreSQL."""
    answer_region: AnswerRegionRead
    grade: GradeRead
    crop_path: Optional[str]
    transcript_text: Optional[str] = None
    overall_justification: Optional[str] = None
    step_results: list[dict] = []


class QuestionScore(BaseModel):
    question_id: str
    final_score: Optional[float]
    ai_score: float
    max_score: float
    status: str


class StudentResult(BaseModel):
    student_identifier: str
    questions: list[QuestionScore]
    total_score: float
    max_total: float
    pending_count: int


class ExamResults(BaseModel):
    exam_id: str
    exam_title: str
    student_results: list[StudentResult]
    total_regions: int
    reviewed_regions: int
