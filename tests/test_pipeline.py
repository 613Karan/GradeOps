"""
Tests for app/services/pipeline.py (replaces test_workers.py).
All Ollama HTTP calls are mocked with httpx — no running services needed.
"""
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
import httpx


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


# ---------------------------------------------------------------------------
# _classify_content
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_classify_math(tmp_path):
    from app.services.pipeline import _classify_content

    img_file = tmp_path / "img.png"
    img_file.write_bytes(b"fakepng")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"message": {"content": "math"}})

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await _classify_content(str(img_file))

    assert result == "math"


@pytest.mark.asyncio
async def test_classify_defaults_to_mixed_on_error(tmp_path):
    from app.services.pipeline import _classify_content

    img_file = tmp_path / "img.png"
    img_file.write_bytes(b"fakepng")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mock_client_cls.return_value = mock_client

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
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={
        "message": {"content": transcript_text},
        "done": True,
    })

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        transcript, confidence = await _run_ocr(str(img_file), "prose")

    assert transcript == transcript_text
    assert 0.0 <= confidence <= 1.0


@pytest.mark.asyncio
async def test_run_ocr_returns_empty_on_failure(tmp_path):
    from app.services.pipeline import _run_ocr

    img_file = tmp_path / "img.png"
    img_file.write_bytes(b"fakepng")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("service down"))
        mock_client_cls.return_value = mock_client

        transcript, confidence = await _run_ocr(str(img_file), "math")

    assert transcript == ""
    assert confidence == 0.0


# ---------------------------------------------------------------------------
# _run_grading
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_grading_parses_json():
    from app.services.pipeline import _run_grading

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={
        "message": {"content": json.dumps(MOCK_GRADING_RESULT)},
        "done": True,
    })

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await _run_grading(
            transcript="The rate constant k = Ae^(-Ea/RT)",
            rubric=MOCK_RUBRIC,
            question_id="Q1",
        )

    assert result["total_awarded"] == 3.5
    assert result["total_max"] == 5.0
    assert len(result["step_results"]) == 3
    assert result["step_results"][0]["verdict"] == "correct"


@pytest.mark.asyncio
async def test_grading_strips_think_tags():
    """<think>...</think> blocks must be stripped before JSON parsing."""
    from app.services.pipeline import _run_grading

    content_with_think = (
        "<think>Let me analyse each step carefully...</think>"
        + json.dumps(MOCK_GRADING_RESULT)
    )

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={
        "message": {"content": content_with_think},
        "done": True,
    })

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await _run_grading("transcript", MOCK_RUBRIC, "Q1")

    assert result["total_awarded"] == 3.5


@pytest.mark.asyncio
async def test_grading_zero_fallback_on_failure():
    """On total failure, must return zero scores so the pipeline doesn't crash."""
    from app.services.pipeline import _run_grading

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("LLM service down"))
        mock_client_cls.return_value = mock_client

        result = await _run_grading("transcript", MOCK_RUBRIC, "Q1")

    assert result["total_awarded"] == 0.0
    assert len(result["step_results"]) == 3
    assert all(r["verdict"] == "missing" for r in result["step_results"])
