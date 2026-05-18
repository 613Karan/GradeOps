"""
TA Review Dashboard routes.

All data served from PostgreSQL — no MongoDB, no S3 presigned URLs.
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_ta_or_above
from app.db.session import get_db
from app.models.pg_models import AnswerRegion, AuditLog, GradeRecord, RegionStatus, User
from app.schemas.schemas import GradeRead, ReviewDashboardItem, TAReviewSubmit

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/queue", response_model=list[ReviewDashboardItem])
async def get_review_queue(
    exam_id: str,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ta_or_above),
):
    offset = (page - 1) * page_size
    result = await db.execute(
        select(AnswerRegion, GradeRecord)
        .join(GradeRecord, GradeRecord.answer_region_id == AnswerRegion.id)
        .where(
            AnswerRegion.exam_id == UUID(exam_id),
            AnswerRegion.status.in_([
                RegionStatus.GRADED, RegionStatus.FLAGGED,
                RegionStatus.APPROVED, RegionStatus.OVERRIDDEN,
            ]),
        )
        .offset(offset)
        .limit(page_size)
    )
    rows = result.all()

    return [
        ReviewDashboardItem(
            answer_region=region,
            grade=grade,
            crop_path=region.crop_path,
            transcript_text=region.transcript_text,
            overall_justification=grade.overall_justification,
            step_results=grade.step_results or [],
        )
        for region, grade in rows
    ]


@router.post("/{region_id}", response_model=GradeRead)
async def submit_review(
    region_id: UUID,
    payload: TAReviewSubmit,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ta_or_above),
):
    result = await db.execute(
        select(AnswerRegion, GradeRecord)
        .join(GradeRecord, GradeRecord.answer_region_id == AnswerRegion.id)
        .where(AnswerRegion.id == region_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Answer region not found")

    region, grade = row

    if payload.final_score != grade.ai_score and not payload.override_reason:
        raise HTTPException(
            status_code=422,
            detail="override_reason is required when changing the AI score",
        )

    if payload.final_score > grade.max_score:
        raise HTTPException(
            status_code=422,
            detail=f"final_score cannot exceed max_score ({grade.max_score})",
        )

    grade.final_score = payload.final_score
    grade.reviewed_by = current_user.id
    grade.reviewed_at = datetime.now(timezone.utc)
    grade.override_reason = payload.override_reason

    region.status = (
        RegionStatus.OVERRIDDEN
        if payload.final_score != grade.ai_score
        else RegionStatus.APPROVED
    )

    db.add(AuditLog(
        actor_id=current_user.id,
        entity_type="grade_record",
        entity_id=str(grade.id),
        action="grade_override" if payload.final_score != grade.ai_score else "grade_approved",
        detail=payload.override_reason,
    ))

    await db.flush()
    await db.refresh(grade)
    return grade
