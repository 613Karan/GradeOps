"""
Exam ingestion endpoint.

Flow:
  1. Instructor uploads bulk PDF scan + JSON rubric
  2. PDF saved to local uploads/ directory (or Cloudinary in prod)
  3. Rubric stored as JSON directly in Exam.rubric column
  4. Exam record created in PostgreSQL
  5. BackgroundTasks runs the full pipeline asynchronously
"""
import json
import os
import uuid
from uuid import UUID

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_instructor
from app.core.config import get_settings
from app.db.session import get_db
from app.models.pg_models import Exam, ExamStatus, User
from app.schemas.schemas import ExamRead, RubricCreate
from app.services.pipeline import run_pipeline

router = APIRouter(prefix="/exams", tags=["exams"])
settings = get_settings()


async def _save_pdf(file: UploadFile, exam_id: str) -> str:
    """Save uploaded PDF locally (or upload to Cloudinary). Returns file path/URL."""
    if settings.USE_CLOUDINARY:
        import cloudinary.uploader
        import cloudinary
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
        )
        content = await file.read()
        result = cloudinary.uploader.upload(
            content,
            public_id=f"gradeops/{exam_id}/original",
            resource_type="raw",
        )
        return result["secure_url"]

    exam_dir = os.path.join(settings.UPLOAD_DIR, exam_id)
    os.makedirs(exam_dir, exist_ok=True)
    file_path = os.path.join(exam_dir, "original.pdf")

    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    return file_path


@router.post("/", response_model=ExamRead, status_code=status.HTTP_201_CREATED)
async def create_exam(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    course_id: str = Form(...),
    rubric_json: str = Form(..., description="JSON string of RubricCreate schema"),
    pdf_file: UploadFile = File(..., description="Bulk exam scan PDF"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor),
):
    # Validate rubric JSON
    try:
        rubric_data = RubricCreate.model_validate(json.loads(rubric_json))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid rubric JSON: {e}")

    # Validate file type
    if pdf_file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    exam_id = uuid.uuid4()

    # Save PDF
    file_path = await _save_pdf(pdf_file, str(exam_id))

    # Create Exam row with rubric stored as JSON
    exam = Exam(
        id=exam_id,
        title=title,
        course_id=UUID(course_id),
        instructor_id=current_user.id,
        file_path=file_path,
        rubric=rubric_data.model_dump(),
        status=ExamStatus.UPLOADED,
    )
    db.add(exam)
    await db.flush()
    await db.refresh(exam)
    await db.commit()

    # Run pipeline in background
    background_tasks.add_task(run_pipeline, str(exam_id), db)

    return exam


@router.get("/{exam_id}", response_model=ExamRead)
async def get_exam(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import select
    result = await db.execute(select(Exam).where(Exam.id == UUID(exam_id)))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    return exam
