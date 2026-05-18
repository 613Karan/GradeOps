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

from app.api.deps import get_current_user, require_instructor, require_ta_or_above
from app.core.config import get_settings
from app.db.session import get_db
from app.models.pg_models import AnswerRegion, ContentType, Exam, ExamStatus, GradeRecord, RegionStatus, User, UserRole
from app.schemas.schemas import AnswerRegionRead, ExamRead, ExamResults, QuestionScore, RegionSplitRequest, RubricCreate, StudentResult
from app.services.pipeline import run_ocr_and_grade, run_pipeline
from typing import Optional

router = APIRouter(prefix="/exams", tags=["exams"])
settings = get_settings()


async def _save_pdf(file: UploadFile, exam_id: str, filename: str = "original.pdf") -> str:
    """Save uploaded PDF locally. Returns file path."""
    exam_dir = os.path.join(settings.UPLOAD_DIR, exam_id)
    os.makedirs(exam_dir, exist_ok=True)
    file_path = os.path.join(exam_dir, filename)
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
    is_math_subject: bool = Form(False, description="True routes OCR to Gemini Flash for better math transcription"),
    pdf_file: UploadFile = File(..., description="Bulk exam scan PDF"),
    answer_key_pdf: Optional[UploadFile] = File(None, description="Answer key PDF (enables RAG grading)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor),
):
    # Validate rubric JSON
    try:
        rubric_data = RubricCreate.model_validate(json.loads(rubric_json))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid rubric JSON: {e}")

    for f in [pdf_file, answer_key_pdf]:
        if f and f.content_type not in ("application/pdf", "application/octet-stream"):
            raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    exam_id = uuid.uuid4()

    file_path = await _save_pdf(pdf_file, str(exam_id), "original.pdf")

    answer_key_path = None
    if answer_key_pdf and answer_key_pdf.filename:
        answer_key_path = await _save_pdf(answer_key_pdf, str(exam_id), "answer_key.pdf")

    exam = Exam(
        id=exam_id,
        title=title,
        course_id=UUID(course_id),
        instructor_id=current_user.id,
        file_path=file_path,
        answer_key_path=answer_key_path,
        is_math_subject=is_math_subject,
        rubric=rubric_data.model_dump(),
        status=ExamStatus.UPLOADED,
    )
    db.add(exam)
    await db.flush()
    await db.refresh(exam)
    await db.commit()

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
    if current_user.role == UserRole.TA:
        return ExamRead.model_validate(exam).model_copy(update={"file_path": None})
    return exam


@router.get("/{exam_id}/results", response_model=ExamResults)
async def get_exam_results(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import select
    result = await db.execute(select(Exam).where(Exam.id == UUID(exam_id)))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    rows_result = await db.execute(
        select(AnswerRegion, GradeRecord)
        .join(GradeRecord, GradeRecord.answer_region_id == AnswerRegion.id)
        .where(AnswerRegion.exam_id == UUID(exam_id))
        .order_by(AnswerRegion.student_identifier, AnswerRegion.question_id)
    )
    rows = rows_result.all()

    # Group by student
    from collections import defaultdict
    students: dict[str, list[tuple]] = defaultdict(list)
    for region, grade in rows:
        students[region.student_identifier].append((region, grade))

    reviewed_statuses = {RegionStatus.APPROVED, RegionStatus.OVERRIDDEN}

    student_results = []
    for student_id, region_grades in sorted(students.items()):
        questions = []
        total_score = 0.0
        max_total = 0.0
        pending_count = 0

        for region, grade in region_grades:
            is_reviewed = region.status in reviewed_statuses
            effective_score = grade.final_score if is_reviewed else None
            if not is_reviewed:
                pending_count += 1
            questions.append(QuestionScore(
                question_id=region.question_id,
                final_score=effective_score,
                ai_score=grade.ai_score,
                max_score=grade.max_score,
                status=region.status.value,
                plagiarism_flagged=grade.plagiarism_flagged or False,
                plagiarism_similarity_score=grade.plagiarism_similarity_score,
            ))
            total_score += effective_score if effective_score is not None else grade.ai_score
            max_total += grade.max_score

        student_results.append(StudentResult(
            student_identifier=student_id,
            questions=questions,
            total_score=round(total_score, 2),
            max_total=round(max_total, 2),
            pending_count=pending_count,
        ))

    reviewed_count = sum(
        1 for region, _ in rows
        if region.status in reviewed_statuses
    )

    return ExamResults(
        exam_id=exam_id,
        exam_title=exam.title,
        student_results=student_results,
        total_regions=len(rows),
        reviewed_regions=reviewed_count,
    )


@router.get("/{exam_id}/regions", response_model=list[AnswerRegionRead])
async def list_regions(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ta_or_above),
):
    from sqlalchemy import select
    result = await db.execute(
        select(AnswerRegion)
        .where(AnswerRegion.exam_id == UUID(exam_id))
        .order_by(AnswerRegion.student_identifier, AnswerRegion.question_id)
    )
    return result.scalars().all()


@router.post("/{exam_id}/start-grading", status_code=status.HTTP_202_ACCEPTED)
async def start_grading(
    exam_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ta_or_above),
):
    from sqlalchemy import select
    result = await db.execute(select(Exam).where(Exam.id == UUID(exam_id)))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.status not in (ExamStatus.SPLIT_DONE, ExamStatus.FAILED):
        raise HTTPException(
            status_code=400,
            detail=f"Exam must be in split_done or failed state to start grading (current: {exam.status})",
        )
    background_tasks.add_task(run_ocr_and_grade, exam_id, db)
    return {"detail": "Grading pipeline started"}


def _normalize_q_id(raw: str) -> str | None:
    """'Q1', '2.', 'Q.3', '' → 'q1', 'q2', 'q3', None."""
    import re
    s = raw.strip()
    if not s:
        return None
    m = re.search(r"\d+", s)
    return f"q{m.group()}" if m else s.lower().replace(" ", "_")


@router.post("/{exam_id}/regions/{region_id}/split", response_model=list[AnswerRegionRead])
async def split_region(
    exam_id: str,
    region_id: str,
    body: RegionSplitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ta_or_above),
):
    """
    Split one answer region into labelled bands.
    Each band in question_ids that has a non-empty label becomes a new AnswerRegion;
    blank labels discard that band.  The original region is always deleted.
    """
    import cv2
    from sqlalchemy import select, delete as sa_delete

    result = await db.execute(select(AnswerRegion).where(AnswerRegion.id == UUID(region_id)))
    region = result.scalar_one_or_none()
    if not region:
        raise HTTPException(status_code=404, detail="Region not found")
    if str(region.exam_id) != exam_id:
        raise HTTPException(status_code=400, detail="Region does not belong to this exam")
    if not region.crop_path or not os.path.exists(region.crop_path):
        raise HTTPException(status_code=400, detail="Region image not found on disk")

    img = cv2.imread(region.crop_path)
    if img is None:
        raise HTTPException(status_code=500, detail="Could not decode region image")

    h = img.shape[0]
    split_points = sorted(set(p for p in body.split_points if 0 < p < h))
    if not split_points:
        raise HTTPException(status_code=422, detail="No valid split points within image bounds")

    q_ids = [_normalize_q_id(lbl) for lbl in body.question_ids]
    if not any(q_ids):
        raise HTTPException(status_code=422, detail="At least one band must have a non-empty question label")

    regions_dir = os.path.dirname(region.crop_path)
    student_id = region.student_identifier
    exam_uuid = region.exam_id

    # Delete grade record first (FK), then the region
    await db.execute(sa_delete(GradeRecord).where(GradeRecord.answer_region_id == region.id))
    await db.delete(region)

    y_boundaries = [0] + split_points + [h]
    new_regions = []
    for i, (y_start, y_end) in enumerate(zip(y_boundaries[:-1], y_boundaries[1:])):
        q_id = q_ids[i]
        if q_id is None:
            continue  # unlabelled band — discard

        crop = img[y_start:y_end, :]
        new_id = uuid.uuid4()
        crop_path = os.path.join(regions_dir, f"{new_id}.png")

        success, encoded = cv2.imencode(".png", crop)
        if not success:
            continue
        with open(crop_path, "wb") as f:
            f.write(encoded.tobytes())

        new_region = AnswerRegion(
            id=new_id,
            exam_id=exam_uuid,
            student_identifier=student_id,
            question_id=q_id,
            crop_path=crop_path,
            region_confidence=0.9,
            content_type=ContentType.UNKNOWN,
            status=RegionStatus.PENDING,
        )
        db.add(new_region)
        new_regions.append(new_region)

    await db.commit()
    for r in new_regions:
        await db.refresh(r)

    return new_regions
