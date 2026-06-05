"""
Tests for app/services/pipeline.py
All external API calls (Groq, Gemini) are mocked — no running services needed.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


MOCK_RUBRIC = {
    "questions": [
        {
            "question_id": "Q1",
            "max_marks": 5.0,
            "logic_steps": [
                {"id": "step_1", "description": "Correct balance", "points": 2.0,
                 "required_keywords": [], "numeric_tolerance_pct": None},
                {"id": "step_2", "description": "Arrhenius application", "points": 2.0,
                 "required_keywords": [], "numeric_tolerance_pct": 5.0},
                {"id": "step_3", "description": "Final answer", "points": 1.0,
                 "required_keywords": [], "numeric_tolerance_pct": None},
            ],
            "answer_key_text": "k = Ae^(-Ea/RT)",
        }
    ]
}

MOCK_GRADING_RESULT = {
    "step_results": [
        {"step_id": "step_1", "description": "Correct balance", "max_points": 2.0,
         "awarded_points": 2.0, "verdict": "correct", "justification": "Equation is balanced."},
        {"step_id": "step_2", "description": "Arrhenius application", "max_points": 2.0,
         "awarded_points": 1.5, "verdict": "partial", "justification": "Missing negative sign."},
        {"step_id": "step_3", "description": "Final answer", "max_points": 1.0,
         "awarded_points": 0.0, "verdict": "incorrect", "justification": "Wrong units."},
    ],
    "total_awarded": 3.5,
    "total_max": 5.0,
    "overall_justification": "Good understanding but errors in final computation.",
}


def _groq_response(content: str):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    return resp


def _mock_groq(content: str):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_groq_response(content))
    return client


# ---------------------------------------------------------------------------
# _classify_content
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_classify_math(tmp_path):
    from app.services.pipeline import _classify_content

    img_file = tmp_path / "img.png"
    img_file.write_bytes(b"fakepng")

    with patch("app.services.pipeline._get_groq", return_value=_mock_groq("math")):
        result = await _classify_content(str(img_file))

    assert result == "math"


@pytest.mark.asyncio
async def test_classify_defaults_to_mixed_on_error(tmp_path):
    from app.services.pipeline import _classify_content

    img_file = tmp_path / "img.png"
    img_file.write_bytes(b"fakepng")

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("connection refused"))

    with patch("app.services.pipeline._get_groq", return_value=mock_client):
        result = await _classify_content(str(img_file))

    assert result == "mixed"


# ---------------------------------------------------------------------------
# _run_ocr
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_ocr_prose(tmp_path):
    from app.services.pipeline import _run_ocr

    img_file = tmp_path / "img.png"
    img_file.write_bytes(b"fakepng")

    transcript_text = "Entropy is a measure of disorder in a thermodynamic system."

    with patch("app.services.pipeline._get_groq", return_value=_mock_groq(transcript_text)):
        transcript, confidence = await _run_ocr(str(img_file), "prose")

    assert transcript == transcript_text
    assert 0.0 <= confidence <= 1.0


@pytest.mark.asyncio
async def test_run_ocr_returns_empty_on_failure(tmp_path):
    from app.services.pipeline import _run_ocr

    img_file = tmp_path / "img.png"
    img_file.write_bytes(b"fakepng")

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("service down"))

    mock_gemini = MagicMock()
    mock_gemini.models.generate_content = MagicMock(side_effect=Exception("service down"))

    with patch("app.services.pipeline._get_groq", return_value=mock_client), \
         patch("app.services.pipeline._get_gemini", return_value=mock_gemini):
        transcript, confidence = await _run_ocr(str(img_file), "math")

    assert transcript == ""
    assert confidence == 0.0


# ---------------------------------------------------------------------------
# _run_grading
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_grading_parses_json():
    from app.services.pipeline import _run_grading

    with patch("app.services.pipeline._get_groq", return_value=_mock_groq(json.dumps(MOCK_GRADING_RESULT))):
        result = await _run_grading(
            transcript="The rate constant k = Ae^(-Ea/RT)",
            rubric=MOCK_RUBRIC,
            question_id="Q1",
            answer_key_context=[],
        )

    assert result["total_awarded"] == 3.5
    assert result["total_max"] == 5.0
    assert len(result["step_results"]) == 3
    assert result["step_results"][0]["verdict"] == "correct"


@pytest.mark.asyncio
async def test_grading_strips_think_tags():
    from app.services.pipeline import _run_grading

    content_with_think = "<think>Let me analyse each step carefully...</think>" + json.dumps(MOCK_GRADING_RESULT)

    with patch("app.services.pipeline._get_groq", return_value=_mock_groq(content_with_think)):
        result = await _run_grading("transcript", MOCK_RUBRIC, "Q1", answer_key_context=[])

    assert result["total_awarded"] == 3.5


@pytest.mark.asyncio
async def test_grading_zero_fallback_on_failure():
    from app.services.pipeline import _run_grading

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM service down"))

    with patch("app.services.pipeline._get_groq", return_value=mock_client):
        result = await _run_grading("transcript", MOCK_RUBRIC, "Q1", answer_key_context=[])

    assert result["total_awarded"] == 0.0
    assert len(result["step_results"]) == 3
    assert all(r["verdict"] == "missing" for r in result["step_results"])
