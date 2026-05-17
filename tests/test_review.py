"""
Tests for the TA review dashboard endpoints.
All data seeded directly into PostgreSQL (no MongoDB).
"""
import uuid
import pytest

from app.models.pg_models import (
    AnswerRegion, ContentType, Exam, ExamStatus,
    GradeRecord, RegionStatus
)
from tests.conftest import TestSessionLocal


async def _seed_exam(exam_id, instructor_id):
    async with TestSessionLocal() as db:
        exam = Exam(
            id=exam_id,
            title="Test Exam",
            course_id=uuid.uuid4(),
            instructor_id=instructor_id,
            file_path=f"uploads/{exam_id}/original.pdf",
            status=ExamStatus.GRADED,
        )
        db.add(exam)
        await db.commit()


async def _seed_region_with_grade(exam_id, region_id, ai_score=3.5, max_score=5.0):
    """Seed an AnswerRegion + GradeRecord directly into the test DB."""
    async with TestSessionLocal() as db:
        region = AnswerRegion(
            id=region_id,
            exam_id=exam_id,
            student_identifier="student_001",
            question_id="Q1",
            crop_path=f"uploads/{exam_id}/regions/{region_id}.png",
            transcript_text="The rate constant k = Ae^(-Ea/RT)",
            transcript_confidence=0.85,
            region_confidence=0.95,
            content_type=ContentType.MIXED,
            status=RegionStatus.GRADED,
        )
        db.add(region)
        await db.flush()

        grade = GradeRecord(
            answer_region_id=region_id,
            ai_score=ai_score,
            max_score=max_score,
            step_results=[],
            overall_justification="Good attempt.",
            plagiarism_flagged=False,
        )
        db.add(grade)
        await db.commit()


@pytest.mark.asyncio
async def test_ta_can_approve_grade(client, ta_token, ta_user, instructor_user):
    exam_id = uuid.uuid4()
    region_id = uuid.uuid4()
    await _seed_exam(exam_id, instructor_user.id)
    await _seed_region_with_grade(exam_id, region_id, ai_score=3.5)

    resp = await client.post(
        f"/api/v1/review/{region_id}",
        json={"final_score": 3.5},
        headers={"Authorization": f"Bearer {ta_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["final_score"] == 3.5
    assert data["override_reason"] is None


@pytest.mark.asyncio
async def test_ta_can_override_with_reason(client, ta_token, ta_user, instructor_user):
    exam_id = uuid.uuid4()
    region_id = uuid.uuid4()
    await _seed_exam(exam_id, instructor_user.id)
    await _seed_region_with_grade(exam_id, region_id, ai_score=3.5)

    resp = await client.post(
        f"/api/v1/review/{region_id}",
        json={"final_score": 4.5, "override_reason": "Student showed correct approach"},
        headers={"Authorization": f"Bearer {ta_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["final_score"] == 4.5
    assert resp.json()["override_reason"] == "Student showed correct approach"


@pytest.mark.asyncio
async def test_override_requires_reason(client, ta_token, instructor_user):
    exam_id = uuid.uuid4()
    region_id = uuid.uuid4()
    await _seed_exam(exam_id, instructor_user.id)
    await _seed_region_with_grade(exam_id, region_id, ai_score=3.5)

    resp = await client.post(
        f"/api/v1/review/{region_id}",
        json={"final_score": 5.0},
        headers={"Authorization": f"Bearer {ta_token}"},
    )
    assert resp.status_code == 422
    assert "override_reason" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_score_cannot_exceed_max(client, ta_token, instructor_user):
    exam_id = uuid.uuid4()
    region_id = uuid.uuid4()
    await _seed_exam(exam_id, instructor_user.id)
    await _seed_region_with_grade(exam_id, region_id, ai_score=3.5, max_score=5.0)

    resp = await client.post(
        f"/api/v1/review/{region_id}",
        json={"final_score": 6.0, "override_reason": "Extra credit"},
        headers={"Authorization": f"Bearer {ta_token}"},
    )
    assert resp.status_code == 422
    assert "max_score" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_review_region_not_found(client, ta_token):
    fake_id = uuid.uuid4()
    resp = await client.post(
        f"/api/v1/review/{fake_id}",
        json={"final_score": 3.0},
        headers={"Authorization": f"Bearer {ta_token}"},
    )
    assert resp.status_code == 404
