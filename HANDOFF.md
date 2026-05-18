# GradeOps — Complete Session Handoff

**Date of handoff:** 2026-05-18  
**Repo:** `/Users/karanaditya/Desktop/gradeops`  
**Status:** Core pipeline working end-to-end. Two spec features remain unbuilt.

---

## What GradeOps Is

A HITL (Human-in-the-Loop) exam grading platform for university courses.

**User roles:** Instructor, TA  
**Flow:**
1. Instructor uploads bulk exam PDF (all students in one file) + JSON rubric + optional answer key PDF
2. Pipeline splits PDF by cover page → stacks each student's pages into one tall image
3. TA reviews the stacked images in a split UI, drawing cut lines to separate question answers
4. TA clicks "Start grading" → OCR runs on each region → AI grades against rubric
5. TA reviews AI grades in a review queue, approving or overriding each
6. Results page shows scores per student per question with class statistics

**Tech stack:**
- Backend: FastAPI + SQLAlchemy async + PostgreSQL
- Frontend: React + TypeScript + TanStack Query + Tailwind CSS + Vite
- OCR: Gemini 2.5 Flash (math exams) with Groq vision fallback
- Grading: Groq `llama-3.3-70b-versatile` (text model)
- Embeddings: `BAAI/bge-small-en-v1.5` via fastembed (ONNX, CPU)
- Infrastructure: Docker Compose (postgres + api containers)

---

## How to Run

```bash
# Start everything
docker compose up -d

# Watch logs
docker compose logs api -f

# Frontend (runs outside Docker)
cd frontend && npm run dev
# → http://localhost:5173

# API
# → http://localhost:8000
# → http://localhost:8000/docs
```

The docker-compose uses `Dockerfile.dev` for the API container (not `Dockerfile`).  
`Dockerfile.dev` installs all requirements, hot-reloads via uvicorn `--reload`.  
`Dockerfile` (used for `docker compose build`) also installs requirements and pre-downloads the fastembed model — use this when rebuilding from scratch.

**`.env` file** (at repo root, not committed):
```
DATABASE_URL=postgresql+asyncpg://gradeops:gradeops@postgres:5432/gradeops
GROQ_API_KEY=<your key — console.groq.com>
GEMINI_API_KEY=<your key — aistudio.google.com>
UPLOAD_DIR=./uploads
SECRET_KEY=dev-secret-key-change-in-production
```

**API key limits (free tier):**
- Groq vision model (`llama-4-scout-17b-16e-instruct`): 500k tokens/day — burns fast with repeated testing. Resets midnight UTC.
- Gemini (`gemini-2.5-flash`): 1500 req/day per Google Cloud project. Resets midnight Pacific.
- Groq text model (`llama-3.3-70b-versatile`, used for grading): separate quota, not hit yet.
- **Important:** Gemini quota is per Google Cloud PROJECT, not per API key. Creating a new key in the same project doesn't help. Need a new project or a different Google account.

---

## File Map

```
gradeops/
├── app/
│   ├── main.py                     FastAPI app, CORS, route registration, file serving
│   ├── core/
│   │   ├── config.py               Settings (pydantic-settings, reads .env)
│   │   └── security.py             JWT encode/decode, password hashing
│   ├── api/
│   │   ├── deps.py                 get_current_user, require_instructor, require_ta_or_above
│   │   └── routes/
│   │       ├── auth.py             POST /register, POST /token
│   │       ├── courses.py          CRUD courses + GET /courses/{id}/exams
│   │       ├── exams.py            POST /exams, GET /exams/{id}, GET /exams/{id}/results,
│   │       │                       GET /exams/{id}/regions, POST /exams/{id}/start-grading,
│   │       │                       POST /exams/{id}/regions/{region_id}/split
│   │       └── review.py           GET /review/queue?exam_id=, POST /review/{region_id}
│   ├── models/
│   │   └── pg_models.py            SQLAlchemy ORM: User, Course, Exam, AnswerRegion,
│   │                               GradeRecord, AnswerKeyChunk, AuditLog
│   ├── schemas/
│   │   └── schemas.py              Pydantic request/response models
│   ├── db/
│   │   └── session.py              AsyncSession factory, engine setup
│   └── services/
│       ├── pipeline.py             The grading pipeline (see Pipeline section)
│       └── embeddings.py           BGE-small embed() and cosine_similarity() helpers
├── alembic/
│   └── versions/
│       ├── 0001_initial_schema.py
│       ├── 0002_rag_support.py     Added AnswerKeyChunk table
│       └── 0003_math_subject_flag.py  Added Exam.is_math_subject
├── frontend/src/
│   ├── App.tsx                     Routes
│   ├── api/
│   │   ├── client.ts               Axios instance (baseURL /api/v1, JWT interceptor)
│   │   └── types.ts                TypeScript interfaces
│   ├── hooks/useAuth.ts            JWT decode, currentRole(), logout()
│   ├── components/
│   │   ├── Layout.tsx              Nav sidebar
│   │   ├── ProtectedRoute.tsx      Auth guard + InstructorRoute guard
│   │   └── SplitModal.tsx          Modal for splitting a region (used in ReviewQueue)
│   └── pages/
│       ├── Login.tsx / Register.tsx
│       ├── Dashboard.tsx           Lists courses + exams
│       ├── NewCourse.tsx / NewExam.tsx
│       ├── CourseExams.tsx         Exam list for a course
│       ├── ExamStatus.tsx          Pipeline status with 6-step visual progress bar,
│       │                           auto-polls, "Mark regions →" / "Open review queue →"
│       │                           / "Retry grading →" buttons
│       ├── SplitReview.tsx         TA split UI — scroll+click to place cut lines,
│       │                           one student at a time, then start grading
│       ├── ReviewQueue.tsx         TA review — approve / override per region
│       └── ExamResults.tsx         Grades grid + statistics (mean, median, distribution)
├── Dockerfile                      Production image (installs requirements, pre-downloads fastembed)
├── Dockerfile.dev                  Dev image (hot-reload, same requirements install)
├── docker-compose.yml
├── requirements.txt
└── .env                            Not committed — see above
```

---

## Database Schema

### Key enums

**ExamStatus:** `uploaded → splitting → split_done → ocr_running → ocr_done → grading → graded → review → completed | failed`

**RegionStatus:** `pending → graded | flagged → approved | overridden`

**ContentType:** `prose | math | mixed | unknown`

**UserRole:** `instructor | ta | admin`

### Tables

**`users`** — id, email, hashed_password, full_name, role, is_active, created_at

**`courses`** — id, code, name, instructor_id, created_at

**`exams`** — id, course_id, instructor_id, title, status, file_path, answer_key_path, is_math_subject (bool), page_count, student_count (nullable — never set, see Gaps), rubric (JSON), created_at, completed_at

**`answer_regions`** — id, exam_id, student_identifier, question_id, crop_path, region_confidence, content_type, status, transcript_text, transcript_confidence, embedding (JSON array of floats), created_at

**`grade_records`** — id, answer_region_id (unique FK), ai_score, max_score, final_score (set after TA review), step_results (JSON), overall_justification, reviewed_by, reviewed_at, override_reason, plagiarism_flagged (bool, default false), plagiarism_similarity_score (float, nullable), created_at

**`answer_key_chunks`** — id, exam_id, question_id, chunk_text, embedding (JSON), created_at

**`audit_logs`** — id, actor_id, entity_type, entity_id, action, detail, created_at

---

## The Pipeline (`app/services/pipeline.py`)

### Stage 1 — `run_pipeline()` → `_split_pages()`

Called on upload via FastAPI `BackgroundTasks`.

1. Opens PDF with PyMuPDF
2. For each page: renders to PNG at 200dpi, calls `_classify_page()` (Groq vision) to detect cover pages
3. **Cover page detected:** extracts roll number/name as `student_identifier`, starts collecting pages for that student
4. **Non-cover page:** appended to current student's page list
5. If Groq is rate-limited, `_classify_page()` returns `{"is_cover": False}` as fallback — all pages go into one student (TA splits manually)
6. All pages between covers are vertically stacked with `np.vstack()` into one tall PNG per student
7. One `AnswerRegion` row created per student with `question_id="unsplit"`, `status=pending`
8. If answer key PDF uploaded: `_process_answer_key()` runs — OCR each page with Groq vision → chunk and embed → store in `answer_key_chunks`
9. Exam status set to `split_done`

### Stage 2+3 — `run_ocr_and_grade()` → `_run_ocr_and_grade_for_exam()`

Triggered by TA clicking "Start grading" after completing the split review. **Sequential — one region at a time.**

For each region (status `pending` or `flagged`):
1. `_classify_content()` — Groq vision classifies as prose/math/mixed (skipped for math exams: always "math")
2. `_run_ocr()` — Gemini 2.5 Flash for math exams, Groq vision for prose. **Auto-fallback:** if primary returns empty string, tries the other API.
3. `embed()` — BGE-small embedding of transcript stored on `answer_region.embedding`
4. RAG retrieval — cosine similarity against `answer_key_chunks` for this question, top-3 chunks
5. `_run_grading()` — Groq text model grades transcript against rubric steps + answer key context, returns JSON with per-step verdict + score
6. `GradeRecord` created, region status set to `graded` (or `flagged` if OCR confidence < 0.65)
7. DB commit after every region (partial progress saved)

Exam status → `graded` → then `run_ocr_and_grade()` wrapper sets it to `review`.

### Retry grading

`POST /exams/{id}/start-grading` also accepts exams in `failed` status (not just `split_done`).  
The pipeline resets `flagged` regions back to `pending` before re-running, so retries work correctly.

### OCR model routing

- `is_math_subject=True` → Gemini 2.5 Flash primary, Groq vision fallback
- `is_math_subject=False` → Groq vision primary, Gemini fallback

Current model IDs in `config.py`:
```python
GROQ_VISION_MODEL   = "meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_GRADING_MODEL  = "llama-3.3-70b-versatile"
GEMINI_VISION_MODEL = "gemini-2.5-flash"
```

---

## Frontend Routes

| Path | Page | Access |
|------|------|--------|
| `/login` | Login | public |
| `/register` | Register | public |
| `/dashboard` | Course + exam list | any auth |
| `/courses/new` | Create course | instructor only |
| `/courses/:id` | Exams in course | any auth |
| `/exams/new` | Upload exam | instructor only |
| `/exams/:id` | Pipeline status | any auth |
| `/exams/:id/splits` | TA split review | any auth |
| `/review/:examId` | TA review queue | any auth |
| `/exams/:id/results` | Results + stats | any auth |

---

## API Endpoints

```
POST   /api/v1/auth/register
POST   /api/v1/auth/token

POST   /api/v1/courses/
GET    /api/v1/courses/
GET    /api/v1/courses/{id}
GET    /api/v1/courses/{id}/exams

POST   /api/v1/exams/                              Upload exam PDF + rubric
GET    /api/v1/exams/{id}                          Get exam (TAs don't get file_path)
GET    /api/v1/exams/{id}/results                  Scores per student per question
GET    /api/v1/exams/{id}/regions                  All answer regions for an exam
POST   /api/v1/exams/{id}/start-grading            Trigger OCR+grade (status: split_done or failed)
POST   /api/v1/exams/{id}/regions/{rid}/split      Split one region into labelled bands

GET    /api/v1/review/queue?exam_id=&page=&page_size=
POST   /api/v1/review/{region_id}                  Approve or override a grade

GET    /uploads/{file_path}                        Serve uploaded files (crops, PDFs)
GET    /health
```

---

## Where We Diverged from Original Spec and Why

### 1. Dropped Ollama / local LLMs → cloud APIs (Groq + Gemini)
**Original spec:** Run Ollama locally (moondream for vision, qwen2.5 for text).  
**What we built:** Groq free-tier cloud inference (vision + text) + Gemini free-tier (math OCR).  
**Why:** Ollama moondream was too inaccurate for cover page detection and OCR. Groq's llama-4-scout gives much better vision results. Gemini Flash gives superior math LaTeX transcription.

### 2. Dropped page-level region detection → TA-driven split UI
**Original spec:** Pipeline auto-detects question boundaries per page using HoughLinesP (OpenCV line detection).  
**What we built:** Pipeline only detects cover pages and stacks all answer pages into one tall image per student. TAs manually draw cut lines in `SplitReview.tsx`.  
**Why:** HoughLinesP was unreliable on real handwritten exam scans. The TA split UI is more accurate and gives TAs control. One-time cost per exam upload, not per-student.

### 3. Dropped LangGraph parallel processing → sequential loop
**Original spec / early implementation:** LangGraph with `Send` fan-out to run all regions concurrently.  
**What we built:** Simple sequential `for` loop — OCR one region → grade → write to DB → next.  
**Why:** Parallel processing blew through free-tier API rate limits instantly (6 regions × concurrent calls). Sequential processing respects rate limits naturally and makes partial-progress DB writes trivial. Can be re-added later with proper rate limiting if needed.

### 4. Rubric format is JSON with `logic_steps`, not a simple marking scheme
The rubric schema (`RubricCreate`) requires per-question `logic_steps` with points and descriptions. The AI grader evaluates each step individually and returns a per-step verdict + score. This is richer than the original spec's simpler rubric format.

---

## What Is Left to Build

### 1. Plagiarism Detection (spec feature, not started)
**DB columns already exist:** `grade_records.plagiarism_flagged` (bool) and `plagiarism_similarity_score` (float).  
**What to build:**
- In `pipeline.py`, after all regions for an exam are graded, run pairwise cosine similarity on `answer_region.embedding` for each question across all students
- Flag pairs where similarity > ~0.92
- Set `plagiarism_flagged=True` and `plagiarism_similarity_score` on the relevant `GradeRecord` rows
- Surface it in `ReviewQueue.tsx` — show a warning badge on flagged regions
- Surface it in `ExamResults.tsx` — add a "Plagiarism" column or indicator

**Where to add the backend logic:** End of `_run_ocr_and_grade_for_exam()` in `app/services/pipeline.py`, after the main grading loop. Load all regions for the exam, group by `question_id`, run pairwise similarity within each group.

**Embeddings are already stored** on `answer_region.embedding` (BGE-small 384-dim float array as JSON). The `cosine_similarity()` function is already in `app/services/embeddings.py`.

### 2. Keyboard Shortcuts in Review Queue (spec feature, not started)
**What to build:** In `frontend/src/pages/ReviewQueue.tsx`, add a `useEffect` with a `keydown` listener.  
Spec calls for:
- `A` — approve currently focused region
- `O` — open override panel for current region
- `J` / `K` — navigate down/up through the queue
- `Escape` — close override panel

This requires lifting the "current focused index" state up from `RegionCard` to `ReviewQueue`, and forwarding action refs down.

### 3. CSV Export on Results Page (not in original spec, but an obvious gap)
The results page (`ExamResults.tsx`) shows grades but has no way to download them.  
**What to build:** A "Download CSV" button that constructs a CSV client-side from the existing `ExamResults` data and triggers a browser download. No backend changes needed — all data is already on the page.

Format: one row per student, columns: `student_id, q1_score, q2_score, ..., total, max_total`

### 4. `exam.student_count` Never Gets Set (minor)
`Exam.student_count` column exists but `_split_pages()` never writes it. After the split loop in `pipeline.py`, add:
```python
exam.student_count = len(students)  # students is the list of (student_id, pages) tuples
```

---

## Known Quirks and Watch-outs

1. **`get_settings()` is `@lru_cache`** — changing `.env` requires a container restart to take effect, not just a file save. Uvicorn hot-reload does NOT re-read `.env`.

2. **`_gemini_client` and `_groq_client` are module-level globals** — they're initialised lazily on first use and cached for the process lifetime. Changing API keys in `.env` requires a full container restart (`docker compose restart api`), not just a file change.

3. **Gemini quota is per Google Cloud PROJECT, not per API key.** Generating a new key in the same project shares the same daily limit. To get fresh quota you need a key from a different Google account / project.

4. **FastAPI `BackgroundTasks` shares the same `AsyncSession` as the request.** The session is passed into the background task directly. This is why grading must be fully sequential — `AsyncSession` is not safe for concurrent access.

5. **The `split_done` status is the pause point.** After upload, the pipeline stops at `split_done` and waits for TA action. The TA uses `SplitReview.tsx` to cut up the stacked images, then clicks "Start grading" which calls `POST /exams/{id}/start-grading`.

6. **Regions with `question_id="unsplit"` are the TA's work queue.** `SplitReview.tsx` filters for these. After splitting, new regions with real question IDs (`q1`, `q2`, etc.) replace them. The original `unsplit` region is deleted.

7. **The split endpoint (`POST /exams/{id}/regions/{rid}/split`) deletes the original region and its grade record** before creating new bands. If a region was accidentally split with wrong labels, there's no undo — you'd need to re-upload.

8. **`SplitReview.tsx` captures the work queue once on first load** (`workQueue` state, initialised from regions with `question_id === "unsplit"`). If a 404 occurs (region already split by another session), it refetches and reinitialises.

9. **Groq vision model `llama-4-scout-17b-16e-instruct` and Gemini `gemini-2.5-flash` have separate daily quotas.** Running the full pipeline on a 1-student exam (6 questions) uses approximately: 13 pages × ~2500 tokens/page for cover detection + 1 answer-key PDF OCR + 6 student region OCRs + 6 grading calls. Budget roughly 60-80k Groq vision tokens and 6 Gemini calls per exam.

10. **The `Dockerfile` (production) and `Dockerfile.dev` are different.** `docker-compose.yml` uses `Dockerfile.dev` via the `build.dockerfile` key. `Dockerfile` is what gets built with `docker compose build` and pre-downloads the fastembed model. Don't confuse them.

---

## Rubric JSON Format

The rubric is submitted as a JSON string in the `rubric_json` form field on exam upload. Structure:

```json
{
  "questions": [
    {
      "question_id": "q1",
      "question_text": "Derive the escape velocity formula",
      "max_marks": 8,
      "logic_steps": [
        { "id": "step_1", "description": "Define gravitational PE: U = -GMm/r", "points": 2 },
        { "id": "step_2", "description": "State condition: total energy >= 0", "points": 1 },
        { "id": "step_3", "description": "Set (1/2)mv² - GMm/R = 0 and solve for v", "points": 3 },
        { "id": "step_4", "description": "Arrive at v = sqrt(2GM/R) = sqrt(2gR)", "points": 2 }
      ]
    }
  ]
}
```

`question_id` must match what the TA enters when labelling split bands (e.g. `q1`, `q2`). The grader uses `question_id` to look up which rubric question applies to a region.

---

## Git Status

Nothing is committed yet — all files are untracked. The entire codebase exists only on disk. There is no remote. Commit before making changes.

```bash
git add .
git commit -m "feat: complete working pipeline with sequential OCR+grading"
```
