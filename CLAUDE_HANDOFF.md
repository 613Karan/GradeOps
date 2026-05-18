# GradeOps — Claude Session Handoff

## Project Overview

**GradeOps** is a FastAPI + PostgreSQL + Ollama HITL (Human-in-the-Loop) exam grading pipeline.

- **Backend**: FastAPI + SQLAlchemy async + PostgreSQL + Ollama (local LLM)
- **Frontend**: React + TypeScript + TanStack Query + Tailwind CSS + Vite
- **Pipeline**: PDF upload → PDF splitting (PyMuPDF + OpenCV) → OCR (vision LLM) → grading (text LLM) → TA review queue → results

**Repo root**: `/Users/karanaditya/Desktop/gradeops`

---

## Work Completed in Previous Sessions

### 1. ExamStatus pipeline display fix (`frontend/src/pages/ExamStatus.tsx`)
- Added `toVisualStep()` mapping function that converts 10 backend statuses → 5 visual pipeline steps
- Fixed `refetchInterval` stopping condition and "Open review queue" button visibility
- Expanded `ExamStatus` type in `frontend/src/api/types.ts`

### 2. Results page (`frontend/src/pages/ExamResults.tsx`)
- Full two-tab page: **Grades** (student × question grid) + **Statistics** (class metrics, distribution chart, per-question averages)
- Statistics are all computed client-side from real API data (not hardcoded)
- Route added in `App.tsx`: `/exams/:id/results`
- "View results →" button added to `ReviewQueue.tsx`

### 3. Results API endpoint (`app/api/routes/exams.py`)
- `GET /exams/{exam_id}/results` returns `ExamResults` schema
- Groups AnswerRegion + GradeRecord by student, sums scores, counts pending regions

### 4. Schemas added (`app/schemas/schemas.py`)
- `QuestionScore`, `StudentResult`, `ExamResults`

---

## Active Bug: 14 Students from 1 PDF Upload

### Root Cause
In `app/services/pipeline.py`, `_split_pages()` at **line 158**:
```python
student_identifier=f"page_{page_num}",   # ← WRONG: 14 pages = 14 "students"
question_id=f"q_{region_num + 1}",       # ← WRONG: underscore, should be q1, q2...
```

The pipeline has no concept of exam cover pages. Each PDF page becomes a separate "student".

### Correct Behavior (IIT exam format)
- PDFs start with a **cover page** containing: `NAME`, `ROLL NO.`, `COURSE NO.`, `DATE` fields
- The cover page's roll number is the `student_identifier`
- Subsequent pages until the next cover page are that student's answer pages
- A single student's exam is typically 14 pages (1 cover + 13 answer pages)

---

## PENDING TASK: Implement Cover Page Detection

### What to change: `app/services/pipeline.py`

#### Step A — Add `_classify_page()` function (new, insert before `_classify_content`)

```python
async def _classify_page(image_b64: str) -> dict:
    """
    Calls vision model to detect if page is an exam cover page.
    Returns {"is_cover": bool, "roll_no": str, "name": str, "course": str}
    """
    prompt = (
        "Look at this scanned exam page. Is this an exam cover/title page? "
        "Cover pages typically have printed fields for NAME, ROLL NO., COURSE NO., DATE "
        "and an instructions section.\n\n"
        "If this IS a cover page, respond with JSON:\n"
        "{\"is_cover\": true, \"roll_no\": \"<roll number>\", \"name\": \"<student name>\", \"course\": \"<course code>\"}\n\n"
        "If this is NOT a cover page:\n"
        "{\"is_cover\": false, \"roll_no\": \"\", \"name\": \"\", \"course\": \"\"}\n\n"
        "Reply ONLY with the JSON object."
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
                    "format": "json",
                },
            )
            resp.raise_for_status()
            raw = resp.json()["message"]["content"]
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            return json.loads(raw)
    except Exception as e:
        logger.warning("Cover page classification failed: %s", e)
        return {"is_cover": False, "roll_no": "", "name": "", "course": ""}
```

#### Step B — Rewrite `_split_pages()` (replace lines 62–169 entirely)

Replace the entire `_split_pages` function with this logic:

```python
async def _split_pages(exam_id: str, db: AsyncSession) -> None:
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

    current_student_id = "student_1"
    student_counter = 0
    question_counter: dict[str, int] = {}

    for page_num, page in enumerate(doc):
        mat = fitz.Matrix(200 / 72, 200 / 72)
        pix = page.get_pixmap(matrix=mat)
        page_png = pix.tobytes("png")

        # Classify: is this a cover page?
        image_b64 = base64.b64encode(page_png).decode()
        page_info = await _classify_page(image_b64)

        if page_info.get("is_cover"):
            student_counter += 1
            roll_no = page_info.get("roll_no", "").strip().replace(" ", "")
            name = page_info.get("name", "").strip()
            current_student_id = roll_no or name or f"student_{student_counter}"
            question_counter[current_student_id] = 0
            continue  # cover pages are not answer regions

        # Answer page — detect regions with HoughLinesP
        if current_student_id not in question_counter:
            question_counter[current_student_id] = 0

        img_array = np.frombuffer(page_png, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100,
                                minLineLength=img.shape[1] * 0.6, maxLineGap=10)

        y_cuts = [0]
        if lines is not None:
            for line in lines:
                x1, y1, x2, y2 = line[0]
                if abs(y2 - y1) < 10:
                    y_cuts.append(int((y1 + y2) / 2))
        y_cuts.append(img.shape[0])
        y_cuts = sorted(set(y_cuts))

        merged = [y_cuts[0]]
        for y in y_cuts[1:]:
            if y - merged[-1] > 50:
                merged.append(y)
        y_cuts = merged

        for i in range(len(y_cuts) - 1):
            y_start, y_end = y_cuts[i], y_cuts[i + 1]
            if y_end - y_start < 30:
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

            question_counter[current_student_id] += 1
            q_num = question_counter[current_student_id]

            region = AnswerRegion(
                id=region_id,
                exam_id=UUID(exam_id),
                student_identifier=current_student_id,
                question_id=f"q{q_num}",          # q1, q2... (NO underscore)
                crop_path=crop_path,
                region_confidence=0.8,
                content_type=ContentType.UNKNOWN,
                status=RegionStatus.PENDING,
            )
            db.add(region)

    exam.status = ExamStatus.SPLIT_DONE
    await db.commit()
```

Key changes vs current code:
- `student_identifier=f"page_{page_num}"` → uses roll number from cover page
- `question_id=f"q_{region_num + 1}"` → `f"q{q_num}"` (no underscore, per-student counter)
- Single global `region_num` counter → per-student `question_counter` dict
- New `_classify_page()` call per page before region detection

---

### What to change: `mock_ollama.py`

The mock Ollama can't see images, so for cover page classification it must return `is_cover: false` (meaning all pages are treated as answer pages — fine for local dev, single-student flow).

In the `chat()` endpoint handler at **line 103**, change the vision model branch:

```python
# Current code (lines 103–108):
if "vl" in req.model or has_images:
    # Vision model — OCR or classify
    if "reply with exactly one word" in prompt.lower():
        content = _mock_classify(prompt)
    else:
        content = _mock_ocr(prompt)

# Replace with:
if "vl" in req.model or has_images:
    # Vision model — cover detection, content classification, or OCR
    if "cover" in prompt.lower() or "roll no" in prompt.lower():
        # Cover page detection — mock can't see images, so always say not a cover
        content = json.dumps({"is_cover": False, "roll_no": "", "name": "", "course": ""})
    elif "reply with exactly one word" in prompt.lower():
        content = _mock_classify(prompt)
    else:
        content = _mock_ocr(prompt)
```

---

## File Map — What's Where

| File | Purpose | Status |
|------|---------|--------|
| `app/services/pipeline.py` | 3-stage PDF → OCR → grade pipeline | **NEEDS REWRITE** (cover page detection) |
| `mock_ollama.py` | Local dev Ollama mock on port 11434 | **NEEDS SMALL CHANGE** (cover page branch) |
| `app/api/routes/exams.py` | Exam CRUD + `/results` endpoint | Done |
| `app/schemas/schemas.py` | Pydantic schemas | Done |
| `app/models/pg_models.py` | SQLAlchemy ORM models | Unchanged |
| `app/core/config.py` | Settings (models, paths, flags) | Unchanged |
| `frontend/src/pages/ExamStatus.tsx` | Pipeline status page | Done |
| `frontend/src/pages/ExamResults.tsx` | Results + statistics page | Done |
| `frontend/src/pages/ReviewQueue.tsx` | TA review queue | Done |
| `frontend/src/App.tsx` | Routes | Done |
| `frontend/src/api/types.ts` | TypeScript API types | Done |

---

## Key Config Values (`app/core/config.py`)

```python
OLLAMA_OCR_MODEL = "moondream"          # vision model, used for cover detection + OCR
OLLAMA_GRADING_MODEL = "qwen2.5:0.5b"  # text model, used for grading
OLLAMA_BASE_URL = "http://localhost:11434"
UPLOAD_DIR = "./uploads"
OCR_CONFIDENCE_MIN = 0.5
USE_CLOUDINARY = False                  # local dev uses disk
```

---

## How to Run Locally

```bash
# Terminal 1: mock Ollama
cd /Users/karanaditya/Desktop/gradeops
python mock_ollama.py

# Terminal 2: backend
uvicorn main:app --reload

# Terminal 3: frontend
cd frontend && npm run dev
```

---

## Behavior After Fix (Local Dev with Mock)

Because `mock_ollama.py` returns `is_cover: false` for every page (can't see images), all pages will be treated as answer pages for a single `student_1`. This is correct for local dev — you get one student with many question regions instead of 14 fake "students".

With **real Ollama** (moondream or qwen2.5vl:3b) on a real exam PDF:
- Cover page is detected → roll number extracted → `student_identifier = "240107043"` (Karan's roll)
- Subsequent 13 answer pages → regions for that student with ids `q1`, `q2`, etc.

---

## IIT Exam PDF Format (reference)

The uploaded test PDF (`240107043-endsem paper.pdf`) is:
- Student: Karan Aditya, Roll No. 240107043
- Course: CL-207
- 14 pages total: page 1 is the cover, pages 2–14 are answer pages
- Cover page has printed fields: NAME, ROLL NO., COURSE NO., DATE

---

## After Implementing the Fix

Once the pipeline fix is working, the remaining cleanup tasks are:
1. Commit all changes to git (nothing is committed yet — all files are untracked)
2. Test end-to-end: upload the IIT exam PDF, verify one student `240107043` appears in results
3. Optional: add `student_count` update in `_split_pages` after all pages processed (`exam.student_count = len(question_counter)`)
