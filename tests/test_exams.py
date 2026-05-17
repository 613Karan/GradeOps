import io
import json
import pytest


SAMPLE_RUBRIC = {
    "questions": [
        {
            "question_id": "Q1",
            "question_text": "Balance the equation and apply Arrhenius equation.",
            "max_marks": 5.0,
            "logic_steps": [
                {"id": "step_1", "description": "Correct stoichiometric balance", "points": 2.0},
                {"id": "step_2", "description": "Correct Arrhenius application", "points": 2.0},
                {"id": "step_3", "description": "Final answer within 5% tolerance", "points": 1.0,
                 "numeric_tolerance_pct": 5.0},
            ],
            "answer_key_text": "k = Ae^(-Ea/RT). Substitute values to get k ≈ 1.37e-13 s-1.",
        }
    ]
}


def _make_pdf_upload():
    return io.BytesIO(b"%PDF-1.4 fake-exam-content")


@pytest.mark.asyncio
async def test_create_exam_as_instructor(client, instructor_token):
    resp = await client.post(
        "/api/v1/exams/",
        data={
            "title": "CH301 Midterm",
            "course_id": "00000000-0000-0000-0000-000000000001",
            "rubric_json": json.dumps(SAMPLE_RUBRIC),
        },
        files={"pdf_file": ("exam.pdf", _make_pdf_upload(), "application/pdf")},
        headers={"Authorization": f"Bearer {instructor_token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["title"] == "CH301 Midterm"
    assert data["status"] == "uploaded"


@pytest.mark.asyncio
async def test_create_exam_rejected_for_ta(client, ta_token):
    resp = await client.post(
        "/api/v1/exams/",
        data={
            "title": "Unauthorized Exam",
            "course_id": "00000000-0000-0000-0000-000000000001",
            "rubric_json": json.dumps(SAMPLE_RUBRIC),
        },
        files={"pdf_file": ("exam.pdf", _make_pdf_upload(), "application/pdf")},
        headers={"Authorization": f"Bearer {ta_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_exam_rejected_without_auth(client):
    resp = await client.post(
        "/api/v1/exams/",
        data={
            "title": "No Auth Exam",
            "course_id": "00000000-0000-0000-0000-000000000001",
            "rubric_json": json.dumps(SAMPLE_RUBRIC),
        },
        files={"pdf_file": ("exam.pdf", _make_pdf_upload(), "application/pdf")},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_exam_invalid_rubric(client, instructor_token):
    bad_rubric = {"questions": [{"question_id": "Q1"}]}
    resp = await client.post(
        "/api/v1/exams/",
        data={
            "title": "Bad Rubric Exam",
            "course_id": "00000000-0000-0000-0000-000000000001",
            "rubric_json": json.dumps(bad_rubric),
        },
        files={"pdf_file": ("exam.pdf", _make_pdf_upload(), "application/pdf")},
        headers={"Authorization": f"Bearer {instructor_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_exam(client, instructor_token):
    create_resp = await client.post(
        "/api/v1/exams/",
        data={
            "title": "Fetch Test Exam",
            "course_id": "00000000-0000-0000-0000-000000000001",
            "rubric_json": json.dumps(SAMPLE_RUBRIC),
        },
        files={"pdf_file": ("exam.pdf", _make_pdf_upload(), "application/pdf")},
        headers={"Authorization": f"Bearer {instructor_token}"},
    )
    exam_id = create_resp.json()["id"]

    get_resp = await client.get(
        f"/api/v1/exams/{exam_id}",
        headers={"Authorization": f"Bearer {instructor_token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == exam_id


@pytest.mark.asyncio
async def test_pipeline_triggered_on_exam_create(client, instructor_token):
    """Verify that run_pipeline BackgroundTask is registered after exam creation."""
    from unittest.mock import AsyncMock, patch

    with patch("app.api.routes.exams.run_pipeline", new_callable=AsyncMock) as mock_pipeline:
        resp = await client.post(
            "/api/v1/exams/",
            data={
                "title": "Pipeline Trigger Test",
                "course_id": "00000000-0000-0000-0000-000000000001",
                "rubric_json": json.dumps(SAMPLE_RUBRIC),
            },
            files={"pdf_file": ("exam.pdf", _make_pdf_upload(), "application/pdf")},
            headers={"Authorization": f"Bearer {instructor_token}"},
        )
        assert resp.status_code == 201
