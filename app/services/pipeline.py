"""
Async grading pipeline — called via FastAPI BackgroundTasks.

Replaces Celery workers entirely. Three stages:
  1. _split_pages  — PDF → cropped region PNGs (PyMuPDF + OpenCV)
  2. _run_ocr_for_exam  — classify content type + transcribe via Ollama
  3. _run_grading_for_exam  — grade each region via Ollama

All Ollama calls use POST http://localhost:11434/api/chat (no streaming).
"""
import base64
import json
import logging
import os
import re
import uuid
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.pg_models import (
    AnswerRegion, ContentType, Exam, ExamStatus, GradeRecord, RegionStatus
)

settings = get_settings()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_pipeline(exam_id: str, db: AsyncSession) -> None:
    """Main entry point — called by BackgroundTasks in the exams route."""
    try:
        await _split_pages(exam_id, db)
        await _run_ocr_for_exam(exam_id, db)
        await _run_grading_for_exam(exam_id, db)

        result = await db.execute(select(Exam).where(Exam.id == UUID(exam_id)))
        exam = result.scalar_one_or_none()
        if exam:
            exam.status = ExamStatus.REVIEW
            await db.commit()
    except Exception:
        logger.exception("Pipeline failed for exam %s", exam_id)
        result = await db.execute(select(Exam).where(Exam.id == UUID(exam_id)))
        exam = result.scalar_one_or_none()
        if exam:
            exam.status = ExamStatus.FAILED
            await db.commit()


# ---------------------------------------------------------------------------
# Stage 1: PDF splitting
# ---------------------------------------------------------------------------

async def _split_pages(exam_id: str, db: AsyncSession) -> None:
    """
    PyMuPDF renders each PDF page to PNG.
    OpenCV detects horizontal lines to find answer region boundaries.
    Crops each region and saves to disk (or Cloudinary).
    Creates AnswerRegion rows in DB.
    """
    import fitz  # PyMuPDF
    import cv2
    import numpy as np

    result = await db.execute(select(Exam).where(Exam.id == UUID(exam_id)))
    exam = result.scalar_one_or_none()
    if not exam:
        raise ValueError(f"Exam {exam_id} not found")

    exam.status = ExamStatus.SPLITTING
    await db.commit()

    pdf_path = exam.file_path
    if not pdf_path or not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found at {pdf_path}")

    doc = fitz.open(pdf_path)
    exam.page_count = len(doc)

    regions_dir = os.path.join(settings.UPLOAD_DIR, exam_id, "regions")
    os.makedirs(regions_dir, exist_ok=True)

    region_num = 0

    for page_num, page in enumerate(doc):
        mat = fitz.Matrix(200 / 72, 200 / 72)
        pix = page.get_pixmap(matrix=mat)
        page_png = pix.tobytes("png")

        # Detect horizontal lines via OpenCV HoughLinesP
        img_array = np.frombuffer(page_png, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100,
                                minLineLength=img.shape[1] * 0.6, maxLineGap=10)

        # Collect unique y-coordinates of horizontal lines
        y_cuts = [0]
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                if abs(y2 - y1) < 10:  # roughly horizontal
                    y_cuts.append(int((y1 + y2) / 2))
        y_cuts.append(img.shape[0])
        y_cuts = sorted(set(y_cuts))

        # Merge cuts that are too close together (< 50px)
        merged = [y_cuts[0]]
        for y in y_cuts[1:]:
            if y - merged[-1] > 50:
                merged.append(y)
        y_cuts = merged

        # Crop between consecutive cut lines
        for i in range(len(y_cuts) - 1):
            y_start, y_end = y_cuts[i], y_cuts[i + 1]
            if y_end - y_start < 30:  # skip slivers
                continue

            crop = img[y_start:y_end, :]
            region_id = uuid.uuid4()
            crop_filename = f"{region_id}.png"
            crop_path = os.path.join(regions_dir, crop_filename)

            success, encoded = cv2.imencode(".png", crop)
            if not success:
                continue

            if settings.USE_CLOUDINARY:
                import cloudinary.uploader
                cloudinary.config(
                    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
                    api_key=settings.CLOUDINARY_API_KEY,
                    api_secret=settings.CLOUDINARY_API_SECRET,
                )
                upload_result = cloudinary.uploader.upload(
                    encoded.tobytes(),
                    public_id=f"gradeops/{exam_id}/regions/{region_id}",
                    resource_type="image",
                )
                crop_path = upload_result["secure_url"]
            else:
                with open(crop_path, "wb") as f:
                    f.write(encoded.tobytes())

            region = AnswerRegion(
                id=region_id,
                exam_id=UUID(exam_id),
                student_identifier=f"page_{page_num}",
                question_id=f"q_{region_num + 1}",
                crop_path=crop_path,
                region_confidence=0.8,
                content_type=ContentType.UNKNOWN,
                status=RegionStatus.PENDING,
            )
            db.add(region)
            region_num += 1

    exam.status = ExamStatus.SPLIT_DONE
    await db.commit()


# ---------------------------------------------------------------------------
# Stage 2: OCR helpers
# ---------------------------------------------------------------------------

async def _classify_content(image_path: str) -> str:
    """
    Classifies image content using the vision model (qwen2.5vl:3b).
    Returns 'math', 'prose', or 'mixed'. Defaults to 'mixed' on failure.
    qwen2.5:0.5b is text-only so we use the VL model here instead.
    """
    try:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()
    except Exception:
        return "mixed"

    prompt = (
        "Look at this handwritten exam answer image. "
        "Reply with exactly one word: 'math' if it contains mostly equations/formulas, "
        "'prose' if it is mostly written text sentences, "
        "or 'mixed' if it contains both. Reply with only the single word."
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": settings.OLLAMA_OCR_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [image_b64],
                        }
                    ],
                    "stream": False,
                },
            )
            resp.raise_for_status()
            word = resp.json()["message"]["content"].strip().lower().split()[0]
            if word in ("math", "prose", "mixed"):
                return word
    except Exception as e:
        logger.warning("Content classification failed: %s", e)

    return "mixed"


async def _run_ocr(image_path: str, content_type: str) -> tuple[str, float]:
    """
    Calls Ollama qwen2.5-vl:3b to transcribe handwritten answer.
    Returns (transcript_markdown, confidence_score).
    """
    try:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()
    except Exception as e:
        logger.error("Failed to read image %s: %s", image_path, e)
        return "", 0.0

    if content_type == "math":
        prompt = (
            "Transcribe this handwritten mathematics answer exactly. "
            "Render ALL mathematical expressions as LaTeX using $...$ for inline math "
            "and $$...$$ for display equations. Output clean Markdown only."
        )
    elif content_type == "prose":
        prompt = (
            "Transcribe this handwritten text verbatim into clean Markdown. "
            "Preserve paragraph structure. Do not add commentary."
        )
    else:
        prompt = (
            "Transcribe this handwritten exam answer. "
            "Transcribe all text verbatim. "
            "Render any mathematical expressions as LaTeX ($...$ inline, $$...$$ display). "
            "Output clean Markdown only."
        )

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": settings.OLLAMA_OCR_MODEL,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                            "images": [image_b64],
                        }
                    ],
                    "stream": False,
                },
            )
            resp.raise_for_status()
            transcript = resp.json()["message"]["content"]
            return transcript, 0.8
    except Exception as e:
        logger.error("OCR failed for %s: %s", image_path, e)
        return "", 0.0


async def _run_ocr_for_exam(exam_id: str, db: AsyncSession) -> None:
    """Fetches all PENDING regions for exam, runs classification + OCR on each."""
    result = await db.execute(select(Exam).where(Exam.id == UUID(exam_id)))
    exam = result.scalar_one_or_none()
    if exam:
        exam.status = ExamStatus.OCR_RUNNING
        await db.commit()

    result = await db.execute(
        select(AnswerRegion).where(
            AnswerRegion.exam_id == UUID(exam_id),
            AnswerRegion.status == RegionStatus.PENDING,
        )
    )
    regions = result.scalars().all()

    for region in regions:
        if not region.crop_path or not os.path.exists(region.crop_path):
            continue

        content_type = await _classify_content(region.crop_path)
        region.content_type = ContentType(content_type)

        transcript, confidence = await _run_ocr(region.crop_path, content_type)

        region.transcript_text = transcript
        region.transcript_confidence = confidence
        region.status = (
            RegionStatus.FLAGGED
            if confidence < settings.OCR_CONFIDENCE_MIN
            else RegionStatus.OCR_DONE
        )

    result = await db.execute(select(Exam).where(Exam.id == UUID(exam_id)))
    exam = result.scalar_one_or_none()
    if exam:
        exam.status = ExamStatus.OCR_DONE
    await db.commit()


# ---------------------------------------------------------------------------
# Stage 3: Grading
# ---------------------------------------------------------------------------

async def _run_grading(transcript: str, rubric: dict, question_id: str) -> dict:
    """
    Calls Ollama qwen2.5:7b to grade a transcript against a rubric question.
    Strips <think>...</think> blocks before JSON parsing.
    Returns zero scores with 'manual review required' on failure.
    """
    question = next(
        (q for q in rubric.get("questions", []) if q["question_id"] == question_id),
        None,
    )
    if not question:
        question = rubric.get("questions", [{}])[0] if rubric.get("questions") else {}

    logic_steps = question.get("logic_steps", [])
    steps_text = "\n".join(
        f"  Step {s['id']}: {s['description']}  [{s['points']} pts]"
        for s in logic_steps
    )

    system_prompt = (
        "You are a strict academic grader. Evaluate the student's handwritten answer "
        "against the rubric steps. Award partial credit only where the rubric permits. "
        "Respond ONLY with valid JSON — no preamble, no markdown fences."
    )

    user_prompt = f"""QUESTION ID: {question_id}
MAX MARKS: {question.get('max_marks', 0)}

RUBRIC STEPS:
{steps_text}

ANSWER KEY:
{question.get('answer_key_text') or 'Not provided.'}

STUDENT TRANSCRIPT:
{transcript}

Respond with JSON exactly matching this schema:
{{
  "step_results": [
    {{
      "step_id": "<id>",
      "description": "<rubric description>",
      "max_points": <float>,
      "awarded_points": <float>,
      "verdict": "correct" | "partial" | "incorrect" | "missing",
      "justification": "<one sentence>"
    }}
  ],
  "total_awarded": <float>,
  "total_max": <float>,
  "overall_justification": "<2-3 sentences>"
}}"""

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": settings.OLLAMA_GRADING_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "format": "json",
                },
            )
            resp.raise_for_status()
            raw = resp.json()["message"]["content"]

            # Strip any <think>...</think> blocks before JSON parsing
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

            return json.loads(raw)

    except Exception as e:
        logger.error("Grading LLM failed for question %s: %s", question_id, e)
        return {
            "step_results": [
                {
                    "step_id": s["id"],
                    "description": s["description"],
                    "max_points": s["points"],
                    "awarded_points": 0.0,
                    "verdict": "missing",
                    "justification": "Grading LLM error — manual review required",
                }
                for s in logic_steps
            ],
            "total_awarded": 0.0,
            "total_max": question.get("max_marks", 0),
            "overall_justification": "Automated grading failed. TA review required.",
        }


async def _run_grading_for_exam(exam_id: str, db: AsyncSession) -> None:
    """Fetches all OCR_DONE regions for exam, retrieves rubric from exam, grades each."""
    result = await db.execute(select(Exam).where(Exam.id == UUID(exam_id)))
    exam = result.scalar_one_or_none()
    if not exam or not exam.rubric:
        logger.error("No rubric found for exam %s", exam_id)
        return

    if exam:
        exam.status = ExamStatus.GRADING
        await db.commit()

    result = await db.execute(
        select(AnswerRegion).where(
            AnswerRegion.exam_id == UUID(exam_id),
            AnswerRegion.status == RegionStatus.OCR_DONE,
        )
    )
    regions = result.scalars().all()

    for region in regions:
        if not region.transcript_text:
            continue

        grading_output = await _run_grading(
            transcript=region.transcript_text,
            rubric=exam.rubric,
            question_id=region.question_id,
        )

        grade = GradeRecord(
            answer_region_id=region.id,
            ai_score=grading_output["total_awarded"],
            max_score=grading_output["total_max"],
            step_results=grading_output["step_results"],
            overall_justification=grading_output["overall_justification"],
        )
        db.add(grade)
        region.status = RegionStatus.GRADED

    result = await db.execute(select(Exam).where(Exam.id == UUID(exam_id)))
    exam = result.scalar_one_or_none()
    if exam:
        exam.status = ExamStatus.GRADED
    await db.commit()
