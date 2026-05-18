"""
Async grading pipeline — called via FastAPI BackgroundTasks.

Three stages:
  1. _split_pages               — PDF → cropped region PNGs (PyMuPDF + OpenCV)
                                  + _process_answer_key (if answer key PDF uploaded)
  2+3. _run_ocr_and_grade_for_exam — LangGraph parallel chains
                                  Each region runs its own chain: OCR → RAG → grade
                                  All chains execute concurrently; semaphores cap
                                  in-flight API calls within free-tier rate limits.

LangGraph graph structure:
  START → fan_out_regions (Send × N) → process_region_node → END
                                           ↑ one node per region, all parallel

Semaphore limits (free tier):
  - Groq vision  (OCR prose): 5 concurrent  → ~30 RPM
  - Gemini Flash (OCR math):  3 concurrent  → ~15 RPM
  - Groq text    (grading):  10 concurrent  → ~30 RPM

DB writes always happen sequentially after the graph completes,
since AsyncSession is not safe for concurrent access.
"""
import asyncio
import base64
import json
import logging
import os
import re
import uuid
from uuid import UUID

from groq import AsyncGroq
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.pg_models import (
    AnswerKeyChunk, AnswerRegion, ContentType, Exam, ExamStatus, GradeRecord, RegionStatus
)

settings = get_settings()
logger = logging.getLogger(__name__)

_groq_client: AsyncGroq | None = None
_gemini_client = None



def _get_groq() -> AsyncGroq:
    global _groq_client
    if _groq_client is None:
        if not settings.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set in .env")
        _groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    return _groq_client


def _get_gemini():
    global _gemini_client
    if _gemini_client is None:
        import google.genai as genai
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set in .env")
        _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _gemini_client


def _vision_message(prompt: str, image_b64: str) -> list[dict]:
    return [{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
        ],
    }]


def _extract_json(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    return m.group() if m else text


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

async def run_pipeline(exam_id: str, db: AsyncSession) -> None:
    """Stage 1: split student PDF + process answer key. Stops at SPLIT_DONE."""
    try:
        await _split_pages(exam_id, db)
    except Exception:
        logger.exception("Split stage failed for exam %s", exam_id)
        result = await db.execute(select(Exam).where(Exam.id == UUID(exam_id)))
        exam = result.scalar_one_or_none()
        if exam:
            exam.status = ExamStatus.FAILED
            await db.commit()


async def run_ocr_and_grade(exam_id: str, db: AsyncSession) -> None:
    """Stages 2 + 3: sequential OCR+grade, then sets exam to REVIEW."""
    try:
        await _run_ocr_and_grade_for_exam(exam_id, db)
        result = await db.execute(select(Exam).where(Exam.id == UUID(exam_id)))
        exam = result.scalar_one_or_none()
        if exam:
            exam.status = ExamStatus.REVIEW
            await db.commit()
    except Exception:
        logger.exception("OCR+grading pipeline failed for exam %s", exam_id)
        result = await db.execute(select(Exam).where(Exam.id == UUID(exam_id)))
        exam = result.scalar_one_or_none()
        if exam:
            exam.status = ExamStatus.FAILED
            await db.commit()


# ---------------------------------------------------------------------------
# Stage 1a: PDF splitting
# ---------------------------------------------------------------------------

async def _classify_page(image_b64: str) -> dict:
    prompt = (
        "Look at this scanned exam page. Is this an exam cover/title page? "
        "Cover pages typically have printed fields for NAME, ROLL NO., COURSE NO., DATE "
        "and an instructions section.\n\n"
        "If this IS a cover page, respond with JSON:\n"
        "{\"is_cover\": true, \"roll_no\": \"<roll number>\", \"name\": \"<student name>\", \"course\": \"<course code>\"}\n\n"
        "If this is NOT a cover page:\n"
        "{\"is_cover\": false, \"roll_no\": \"\", \"name\": \"\", \"course\": \"\"}\n\n"
        "Reply ONLY with the JSON object, no other text."
    )
    try:
        resp = await _get_groq().chat.completions.create(
            model=settings.GROQ_VISION_MODEL,
            messages=_vision_message(prompt, image_b64),
            max_tokens=256,
        )
        return json.loads(_extract_json(resp.choices[0].message.content))
    except Exception as e:
        logger.warning("Cover page classification failed: %s", e)
        return {"is_cover": False, "roll_no": "", "name": "", "course": ""}


async def _split_pages(exam_id: str, db: AsyncSession) -> None:
    """
    Stage 1a — cover-only split.

    Detects cover pages via vision model, stacks all pages between consecutive
    covers into one tall PNG per student (question_id="unsplit").  The TA then
    places cut lines in the UI to divide each script into per-question regions.
    """
    import fitz
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

    # Accumulate: list of (student_id, [img, img, ...])
    students: list[tuple[str, list]] = []
    current_student_id: str | None = None
    current_pages: list = []
    student_counter = 0

    for page in doc:
        mat = fitz.Matrix(200 / 72, 200 / 72)
        pix = page.get_pixmap(matrix=mat)
        page_png = pix.tobytes("png")
        image_b64 = base64.b64encode(page_png).decode()

        page_info = await _classify_page(image_b64)
        if page_info.get("is_cover"):
            # Flush previous student's pages
            if current_student_id is not None and current_pages:
                students.append((current_student_id, current_pages))

            student_counter += 1
            roll_no = page_info.get("roll_no", "").strip().replace(" ", "")
            name = page_info.get("name", "").strip()
            if roll_no and name:
                current_student_id = f"{roll_no} — {name}"
            elif roll_no:
                current_student_id = roll_no
            elif name:
                current_student_id = name
            else:
                current_student_id = f"student_{student_counter}"
            current_pages = []
        else:
            img_array = np.frombuffer(page_png, dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if img is not None:
                current_pages.append(img)

    # Flush last student
    if current_student_id is not None and current_pages:
        students.append((current_student_id, current_pages))
    elif not students and current_pages:
        # No cover page found at all — treat whole PDF as a single student
        students.append(("student_1", current_pages))

    # Create one tall-stacked AnswerRegion per student
    for student_id, pages in students:
        merged = np.vstack(pages) if len(pages) > 1 else pages[0]
        region_id = uuid.uuid4()
        crop_path = os.path.join(regions_dir, f"{region_id}.png")
        success, encoded = cv2.imencode(".png", merged)
        if not success:
            continue
        with open(crop_path, "wb") as f:
            f.write(encoded.tobytes())
        db.add(AnswerRegion(
            id=region_id,
            exam_id=UUID(exam_id),
            student_identifier=student_id,
            question_id="unsplit",
            crop_path=crop_path,
            region_confidence=1.0,
            content_type=ContentType.UNKNOWN,
            status=RegionStatus.PENDING,
        ))

    if exam.answer_key_path and os.path.exists(exam.answer_key_path):
        await _process_answer_key(exam_id, exam.answer_key_path, db)

    exam.student_count = len(students)
    exam.status = ExamStatus.SPLIT_DONE
    await db.commit()


# ---------------------------------------------------------------------------
# Stage 1b: Answer key OCR + embedding
# ---------------------------------------------------------------------------

async def _ocr_page(image_b64: str) -> str:
    """OCR a single page image, returning plain text."""
    prompt = (
        "Transcribe all text from this page verbatim. "
        "Include all content — headings, answers, equations, everything. "
        "Output plain text only, no formatting commentary."
    )
    try:
        resp = await _get_groq().chat.completions.create(
            model=settings.GROQ_VISION_MODEL,
            messages=_vision_message(prompt, image_b64),
            max_tokens=2048,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("Answer key page OCR failed: %s", e)
        return ""


async def _identify_question(image_b64: str) -> str | None:
    """Return the question ID visible at the top of an answer key page, or None."""
    prompt = (
        "Look at this exam answer page. "
        "Does this page START a new question? Look for a question number "
        "(e.g. 'Q1', '2.', 'Q.3').\n\n"
        "If a question number IS visible: {\"question_number\": \"Q1\"}\n"
        "If not: {\"question_number\": null}\n\n"
        "Reply ONLY with the JSON object."
    )
    try:
        resp = await _get_groq().chat.completions.create(
            model=settings.GROQ_VISION_MODEL,
            messages=_vision_message(prompt, image_b64),
            max_tokens=64,
        )
        data = json.loads(_extract_json(resp.choices[0].message.content))
        q_raw = data.get("question_number")
        if not q_raw:
            return None
        m = re.search(r"\d+", str(q_raw))
        return f"q{m.group()}" if m else None
    except Exception as e:
        logger.warning("Question identification failed: %s", e)
        return None


async def _process_answer_key(exam_id: str, answer_key_path: str, db: AsyncSession) -> None:
    """
    OCR each page of the answer key, identify its question, embed with BGE-M3,
    and store as AnswerKeyChunk rows.
    """
    import fitz
    from app.services.embeddings import embed

    try:
        doc = fitz.open(answer_key_path)
    except Exception as e:
        logger.error("Could not open answer key PDF: %s", e)
        return

    for page_num, page in enumerate(doc):
        mat = fitz.Matrix(200 / 72, 200 / 72)
        pix = page.get_pixmap(matrix=mat)
        page_png = pix.tobytes("png")
        image_b64 = base64.b64encode(page_png).decode()

        text = await _ocr_page(image_b64)
        if not text:
            continue

        # Try to identify which question this page belongs to
        q_id = await _identify_question(image_b64)
        question_id = q_id if q_id else f"general_p{page_num + 1}"

        try:
            embedding = embed(text)
        except Exception as e:
            logger.warning("Embedding failed for answer key page %d: %s", page_num, e)
            embedding = None

        db.add(AnswerKeyChunk(
            exam_id=UUID(exam_id),
            question_id=question_id,
            chunk_text=text,
            embedding=embedding,
        ))

    await db.flush()
    logger.info("Answer key processed for exam %s (%d pages)", exam_id, len(doc))


# ---------------------------------------------------------------------------
# Stage 2: OCR + embedding
# ---------------------------------------------------------------------------

async def _classify_content(image_path: str) -> str:
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
        resp = await _get_groq().chat.completions.create(
            model=settings.GROQ_VISION_MODEL,
            messages=_vision_message(prompt, image_b64),
            max_tokens=8,
        )
        word = resp.choices[0].message.content.strip().lower().split()[0]
        if word in ("math", "prose", "mixed"):
            return word
    except Exception as e:
        logger.warning("Content classification failed: %s", e)
    return "mixed"


async def _run_ocr_groq(image_b64: str, content_type: str) -> tuple[str, float]:
    """OCR via Groq vision — used for prose-heavy subjects."""
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
            "Transcribe this handwritten exam answer verbatim. "
            "Render any mathematical expressions as LaTeX ($...$ inline, $$...$$ display). "
            "Output clean Markdown only."
        )
    try:
        resp = await _get_groq().chat.completions.create(
            model=settings.GROQ_VISION_MODEL,
            messages=_vision_message(prompt, image_b64),
            max_tokens=2048,
        )
        return resp.choices[0].message.content, 0.8
    except Exception as e:
        logger.error("Groq OCR failed: %s", e)
        return "", 0.0


async def _run_ocr_gemini(image_bytes: bytes, content_type: str) -> tuple[str, float]:
    """OCR via Gemini Flash — used for math-heavy subjects."""
    import asyncio
    import google.genai as genai
    from google.genai import types as genai_types

    if content_type == "math":
        prompt = (
            "You are a mathematical OCR engine. Transcribe this handwritten mathematics answer exactly.\n"
            "Rules:\n"
            "- Render ALL expressions as LaTeX: $...$ for inline, $$...$$ for display equations\n"
            "- Preserve the full derivation step by step, in order\n"
            "- For fractions use \\frac{}{}, for integrals use \\int, for summations \\sum\n"
            "- If a diagram or graph is present that cannot be transcribed, write [DIAGRAM: brief description]\n"
            "- Output clean Markdown only, no commentary"
        )
    else:
        prompt = (
            "Transcribe this handwritten exam answer exactly.\n"
            "- Transcribe all text verbatim\n"
            "- Render any mathematical expressions as LaTeX ($...$ inline, $$...$$ display)\n"
            "- If a diagram is present that cannot be transcribed, write [DIAGRAM: brief description]\n"
            "- Output clean Markdown only, no commentary"
        )

    try:
        client = _get_gemini()
        image_part = genai_types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=settings.GEMINI_VISION_MODEL,
                contents=[image_part, prompt],
            ),
        )
        return response.text.strip(), 0.9
    except Exception as e:
        logger.error("Gemini OCR failed: %s", e)
        return "", 0.0


async def _run_ocr(image_path: str, content_type: str, use_gemini: bool = False) -> tuple[str, float]:
    """
    Route OCR to Gemini Flash (math) or Groq (prose), with cross-fallback.
    If the primary API returns empty (quota exhausted / error), tries the other.
    """
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
    except Exception as e:
        logger.error("Failed to read image %s: %s", image_path, e)
        return "", 0.0

    image_b64 = base64.b64encode(image_bytes).decode()

    if use_gemini:
        text, conf = await _run_ocr_gemini(image_bytes, content_type)
        if not text:
            logger.warning("Gemini OCR returned empty — falling back to Groq vision")
            text, conf = await _run_ocr_groq(image_b64, content_type)
        return text, conf
    else:
        text, conf = await _run_ocr_groq(image_b64, content_type)
        if not text:
            logger.warning("Groq OCR returned empty — falling back to Gemini")
            text, conf = await _run_ocr_gemini(image_bytes, content_type)
        return text, conf


async def _process_one_region(
    region,
    rubric: dict,
    use_gemini: bool,
    key_chunks: list[dict],
    has_answer_key: bool,
) -> dict:
    """OCR → embed → RAG → grade for a single region. Fully sequential."""
    from app.services.embeddings import embed as _embed, top_k

    out: dict = {
        "region_id":      str(region.id),
        "content_type":   None,
        "transcript":     "",
        "confidence":     0.0,
        "embedding":      None,
        "grading_output": None,
    }

    crop_path   = region.crop_path
    question_id = region.question_id

    if not crop_path or not os.path.exists(crop_path):
        logger.warning("Crop image missing for region %s", region.id)
        return out

    content_type = "math" if use_gemini else await _classify_content(crop_path)
    transcript, confidence = await _run_ocr(crop_path, content_type, use_gemini=use_gemini)

    out["content_type"] = content_type
    out["transcript"]   = transcript
    out["confidence"]   = confidence

    if transcript:
        try:
            out["embedding"] = _embed(transcript)
        except Exception as e:
            logger.warning("Embedding failed for region %s: %s", region.id, e)

        answer_key_context: list[str] = []
        if has_answer_key and out["embedding"]:
            q_chunks = [
                c for c in key_chunks
                if c.get("embedding") and (
                    c["question_id"] == question_id
                    or c["question_id"].startswith("general")
                )
            ]
            if q_chunks:
                answer_key_context = top_k(out["embedding"], q_chunks, k=3)

        grading_output = await _run_grading(
            transcript=transcript,
            rubric=rubric,
            question_id=question_id,
            answer_key_context=answer_key_context,
        )
        out["grading_output"] = grading_output
        logger.info(
            "Region %s (%s): conf=%.2f score=%.1f/%.1f",
            region.id, question_id, confidence,
            grading_output["total_awarded"], grading_output["total_max"],
        )

    return out


# ---------------------------------------------------------------------------
# Stage 2+3 combined: sequential OCR + grading
# ---------------------------------------------------------------------------

async def _run_ocr_and_grade_for_exam(exam_id: str, db: AsyncSession) -> None:
    """Process each region one at a time: OCR → embed → grade → write to DB."""
    result = await db.execute(select(Exam).where(Exam.id == UUID(exam_id)))
    exam = result.scalar_one_or_none()
    if not exam or not exam.rubric:
        logger.error("Exam %s not found or missing rubric", exam_id)
        return

    use_gemini = bool(exam.is_math_subject)
    exam.status = ExamStatus.OCR_RUNNING
    await db.commit()

    regions_result = await db.execute(
        select(AnswerRegion).where(
            AnswerRegion.exam_id == UUID(exam_id),
            AnswerRegion.status.in_([RegionStatus.PENDING, RegionStatus.FLAGGED]),
        )
    )
    regions = regions_result.scalars().all()
    for region in regions:
        if region.status == RegionStatus.FLAGGED:
            region.status = RegionStatus.PENDING
    await db.commit()

    chunks_result = await db.execute(
        select(AnswerKeyChunk).where(AnswerKeyChunk.exam_id == UUID(exam_id))
    )
    key_chunks = [
        {"question_id": c.question_id, "chunk_text": c.chunk_text, "embedding": c.embedding}
        for c in chunks_result.scalars().all()
    ]
    has_answer_key = len(key_chunks) > 0

    logger.info(
        "Exam %s: sequential pipeline — %d regions, model=%s",
        exam_id, len(regions), "Gemini Flash Lite" if use_gemini else "Groq vision",
    )

    for i, region in enumerate(regions):
        logger.info("Processing region %d/%d: %s (%s)", i + 1, len(regions), region.id, region.question_id)
        r = await _process_one_region(region, exam.rubric, use_gemini, key_chunks, has_answer_key)

        if r["content_type"]:
            region.content_type = ContentType(r["content_type"])
        region.transcript_text       = r["transcript"]
        region.transcript_confidence = r["confidence"]
        region.embedding             = r["embedding"]

        if r["grading_output"]:
            region.status = RegionStatus.GRADED
            out = r["grading_output"]
            db.add(GradeRecord(
                answer_region_id=region.id,
                ai_score=out["total_awarded"],
                max_score=out["total_max"],
                step_results=out["step_results"],
                overall_justification=out["overall_justification"],
            ))
        else:
            region.status = (
                RegionStatus.FLAGGED
                if r["confidence"] < settings.OCR_CONFIDENCE_MIN
                else RegionStatus.OCR_DONE
            )
        await db.commit()

    result = await db.execute(select(Exam).where(Exam.id == UUID(exam_id)))
    exam = result.scalar_one_or_none()
    if exam:
        exam.status = ExamStatus.GRADED
    await db.commit()


# ---------------------------------------------------------------------------
# Stage 3: RAG grading
# ---------------------------------------------------------------------------

async def _run_grading(
    transcript: str,
    rubric: dict,
    question_id: str,
    answer_key_context: list[str],
) -> dict:
    """
    Grade a student transcript against the rubric, informed by retrieved
    answer key chunks. answer_key_context is a list of reference text chunks
    retrieved via RAG — empty list means no answer key was uploaded.
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

    if answer_key_context:
        reference_section = "ANSWER KEY REFERENCE (retrieved via RAG):\n" + "\n---\n".join(answer_key_context)
    else:
        reference_section = f"ANSWER KEY:\n{question.get('answer_key_text') or 'Not provided.'}"

    system_prompt = (
        "You are a strict academic grader. Evaluate the student's answer "
        "against the rubric steps. Use the answer key reference to judge correctness. "
        "Award partial credit only where the rubric permits. "
        "Respond ONLY with valid JSON — no preamble, no markdown fences."
    )

    user_prompt = f"""QUESTION ID: {question_id}
MAX MARKS: {question.get('max_marks', 0)}

RUBRIC STEPS:
{steps_text}

{reference_section}

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
        resp = await _get_groq().chat.completions.create(
            model=settings.GROQ_GRADING_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=2048,
            response_format={"type": "json_object"},
        )
        raw = re.sub(r"<think>.*?</think>", "", resp.choices[0].message.content, flags=re.DOTALL).strip()
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


