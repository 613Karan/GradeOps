# GradeOps

A Human-in-the-Loop (HITL) exam grading platform for universities. Instructors upload bulk handwritten exam scans; an AI pipeline performs OCR, grades each answer against a granular rubric, and flags potential plagiarism. Teaching Assistants review, approve, or override every AI decision through a purpose-built dashboard before results are finalised.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [The Grading Pipeline](#the-grading-pipeline)
- [API Reference](#api-reference)
- [Frontend Routes](#frontend-routes)
- [Rubric Format](#rubric-format)
- [Database Schema](#database-schema)
- [Divergences from Original Spec](#divergences-from-original-spec)
- [Known Limitations](#known-limitations)
- [Free-Tier API Limits](#free-tier-api-limits)

---

## How It Works

1. **Instructor uploads** a bulk PDF (all student scripts in one file) + a grading rubric built in the UI + an optional answer key PDF
2. **Pipeline splits** the PDF by cover page — extracting each student's name and roll number automatically using a vision model
3. **TA reviews** the stacked per-student images and draws cut lines to separate individual question answers
4. **TA clicks "Start grading"** — the pipeline OCRs each answer region, embeds it, retrieves relevant answer key context (RAG), and grades it against the rubric using an LLM
5. **AI proposes** a score for each question with a per-step breakdown and justification
6. **TA approves or overrides** each grade via a keyboard-shortcut-driven review queue
7. **Results page** shows final scores per student per question, class statistics, plagiarism flags, and a CSV export

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.11, FastAPI, SQLAlchemy (async), Alembic |
| **Database** | PostgreSQL 16 |
| **OCR — general** | Groq `llama-4-scout-17b-16e-instruct` (vision) |
| **OCR — math** | Google Gemini `gemini-2.5-flash` (vision) |
| **Grading LLM** | Groq `llama-3.3-70b-versatile` (text) |
| **Embeddings** | `BAAI/bge-small-en-v1.5` via fastembed (ONNX, CPU-only) |
| **PDF processing** | PyMuPDF (fitz) |
| **Image processing** | OpenCV, NumPy |
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS |
| **State management** | TanStack Query (React Query) |
| **Auth** | JWT (python-jose), bcrypt |
| **Infrastructure** | Docker, Docker Compose |

Both Groq and Gemini are used on their **free tiers** — no billing required.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Browser (Vite dev)                  │
│   React + TypeScript + Tailwind + TanStack Query        │
│   localhost:5173                                        │
└───────────────────────┬─────────────────────────────────┘
                        │ HTTP / REST
┌───────────────────────▼─────────────────────────────────┐
│              FastAPI  (localhost:8000)                   │
│                                                         │
│  /api/v1/auth      JWT register + login                 │
│  /api/v1/courses   Course CRUD                          │
│  /api/v1/exams     Upload, status, results, split       │
│  /api/v1/review    TA approve / override queue          │
│  /uploads/*        Static file serving (crops, PDFs)    │
│                                                         │
│  BackgroundTasks ──► Grading pipeline (sequential)      │
└──────────┬─────────────────────────┬────────────────────┘
           │                         │
┌──────────▼──────────┐   ┌──────────▼──────────┐
│   PostgreSQL 16      │   │  ./uploads/          │
│   (Docker)           │   │  PDF scans           │
│                      │   │  Per-student PNGs    │
│   users              │   │  Cropped regions     │
│   courses            │   └─────────────────────┘
│   exams              │
│   answer_regions     │   External APIs (free tier)
│   grade_records      │   ├─ Groq (vision + text)
│   answer_key_chunks  │   └─ Google Gemini (math OCR)
│   audit_logs         │
└─────────────────────┘
```

---

## Prerequisites

- **Docker Desktop** — includes Docker Compose; runs the backend API and PostgreSQL database
  - Mac/Windows: [docs.docker.com/get-docker](https://docs.docker.com/get-docker/)
  - After installing, open Docker Desktop and wait for the engine to start (whale icon in menubar)
- **Node.js 18+** — for the frontend dev server
  - Check: `node --version` (must be ≥ 18)
  - Install: [nodejs.org](https://nodejs.org) or `brew install node`
- **Groq API key** — free, no credit card
- **Gemini API key** — free, no credit card

---

## Getting API Keys

Both keys are free and take about two minutes each.

### Groq (used for OCR and grading)

1. Go to [console.groq.com](https://console.groq.com) and sign up / log in
2. Click **API Keys** in the left sidebar
3. Click **Create API Key**, give it any name, copy the key
4. It starts with `gsk_...`

### Google Gemini (used for math OCR)

1. Go to [aistudio.google.com](https://aistudio.google.com) and sign in with a Google account
2. Click **Get API key** (top left) → **Create API key in new project**
3. Copy the key — it starts with `AIza...`

> Both free tiers have daily limits that are enough for a full demo run. No billing setup or credit card is ever required.

---

## Quick Start

### 1. Clone the repo

```bash
git clone <repo-url>
cd gradeops
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` in any text editor and fill in the two API keys you just created:

```env
GROQ_API_KEY=gsk_...        ← paste your Groq key here
GEMINI_API_KEY=AIza...      ← paste your Gemini key here
```

Everything else in `.env` works as-is for local development — do not change `DATABASE_URL`.

### 3. Start the backend

```bash
docker compose up -d
```

This pulls the images (first time only) and starts:
- `postgres` — PostgreSQL 16 on port 5432
- `api` — FastAPI on port 8000 (with hot-reload)

**First run note:** On startup, the API container downloads the fastembed embedding model (~130 MB) to a named Docker volume. This happens once and is cached permanently. It takes roughly 60 seconds — the API will return 503 until it finishes. Watch progress with:

```bash
docker compose logs api -f
```

Wait until you see `Application startup complete` before proceeding.

Health check (should return `{"status":"ok"}`):
```bash
curl http://localhost:8000/health
```

### 4. Run database migrations

```bash
docker exec gradeops-api-1 alembic upgrade head
```

If the container name differs on your machine, find it with `docker ps` and substitute accordingly.

### 5. Start the frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

The app is now running at **http://localhost:5173**

### 6. Create accounts

Open [http://localhost:5173/register](http://localhost:5173/register) in your browser and create two accounts:

| Role | What they do |
|---|---|
| **instructor** | Creates courses, uploads exams, views results |
| **ta** | Reviews AI splits, approves or overrides grades |

You need both roles to complete a full end-to-end run. Use different email addresses (e.g. `prof@demo.com` and `ta@demo.com`). Passwords can be anything.

Alternatively, create them via the API directly (no browser needed):

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"prof@demo.com","full_name":"Professor","password":"pass1234","role":"instructor"}'

curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"ta@demo.com","full_name":"Teaching Assistant","password":"pass1234","role":"ta"}'
```

### 7. Run a demo

1. Log in as the **instructor** → create a course → upload an exam PDF with a rubric
2. Wait for status to reach **Split done** (pipeline auto-runs after upload)
3. Log in as the **TA** → open the exam → click **Review splits** → draw cut lines, label each band (`q1`, `q2`, …) → save
4. Back on the exam page, click **Start grading** — pipeline runs OCR + AI grading
5. When status reaches **Review**, open the **Review queue** — approve or override each grade
6. Open **Results** to see final scores, class statistics, plagiarism flags, and export CSV

Interactive API docs (Swagger UI) are available at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the two API keys. All other values work as-is for local development.

| Variable | Description | Required |
|---|---|---|
| `SECRET_KEY` | JWT signing key — any random string | yes |
| `DATABASE_URL` | PostgreSQL connection string — matches `docker-compose.yml` | yes (do not change) |
| `GROQ_API_KEY` | Groq API key (`gsk_...`) | yes |
| `GEMINI_API_KEY` | Google Gemini API key (`AIza...`) | yes |
| `UPLOAD_DIR` | Where PDFs and crops are stored inside the container | yes (leave as `./uploads`) |

> **Note:** `get_settings()` uses `@lru_cache`. After editing `.env`, run `docker compose up -d --force-recreate api` to reload — a plain `docker compose restart` will not re-read the env file.

---

## Project Structure

```
gradeops/
├── app/
│   ├── main.py                     FastAPI app, CORS, routes, static file mount
│   ├── core/
│   │   ├── config.py               Pydantic-settings (reads .env)
│   │   └── security.py             JWT + bcrypt
│   ├── api/
│   │   ├── deps.py                 get_current_user, require_instructor, require_ta_or_above
│   │   └── routes/
│   │       ├── auth.py             POST /register, POST /token
│   │       ├── courses.py          CRUD + exam list
│   │       ├── exams.py            Upload, status, results, region split, start-grading
│   │       └── review.py           Review queue + approve/override
│   ├── models/
│   │   └── pg_models.py            SQLAlchemy ORM + enums
│   ├── schemas/
│   │   └── schemas.py              Pydantic request/response models
│   ├── db/
│   │   └── session.py              Async session factory
│   └── services/
│       ├── pipeline.py             Full grading pipeline (split → OCR → grade → plagiarism)
│       └── embeddings.py           BGE-small embed(), cosine_similarity(), top_k()
├── alembic/
│   └── versions/
│       ├── 0001_initial_schema.py
│       ├── 0002_rag_support.py
│       └── 0003_math_subject_flag.py
├── frontend/
│   └── src/
│       ├── App.tsx
│       ├── api/
│       │   ├── client.ts           Axios + JWT interceptor
│       │   └── types.ts            TypeScript interfaces
│       ├── hooks/useAuth.ts
│       ├── components/
│       │   ├── Layout.tsx
│       │   ├── ProtectedRoute.tsx
│       │   └── SplitModal.tsx
│       └── pages/
│           ├── Login.tsx / Register.tsx
│           ├── Dashboard.tsx
│           ├── NewCourse.tsx / NewExam.tsx   (visual rubric builder)
│           ├── CourseExams.tsx
│           ├── ExamStatus.tsx               (6-step progress bar, auto-polls)
│           ├── SplitReview.tsx              (click-to-cut TA split UI)
│           ├── ReviewQueue.tsx              (keyboard shortcuts, override panel)
│           └── ExamResults.tsx             (grades grid, statistics, CSV export)
├── tests/                          Unit tests (SQLite in-memory, mocked APIs)
├── Dockerfile                      Production image (pre-downloads fastembed model)
├── Dockerfile.dev                  Dev image (hot-reload)
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## The Grading Pipeline

All pipeline logic lives in `app/services/pipeline.py`. It runs as a FastAPI `BackgroundTask` — fully sequential, one region at a time — to respect free-tier API rate limits and enable per-region DB commits.

### Stage 1 — PDF Split (`run_pipeline`)

Triggered immediately on exam upload.

1. Opens the PDF with PyMuPDF, renders each page to PNG at 200 dpi
2. Sends each page to Groq vision to detect cover pages — extracts student name + roll number as `student_identifier`
3. All pages between cover pages are vertically stacked (`np.vstack`) into one tall PNG per student
4. One `AnswerRegion` row created per student with `question_id="unsplit"`
5. If an answer key PDF was uploaded: each page is OCR'd, embedded with BGE-small, and stored as `AnswerKeyChunk` rows for RAG retrieval
6. `exam.student_count` set, exam status → `split_done`

**Fallback:** Groq timeout on a page → page treated as non-cover (appended to current student). Daily quota exhausted → `RuntimeError` raised, exam marked `failed`.

### Stage 2 — TA Split Review

The TA opens each student's stacked image in `SplitReview.tsx`, clicks to place horizontal cut lines, and labels each band with a question ID. The split endpoint slices the image at those pixel coordinates, creates new `AnswerRegion` rows, and deletes the original `unsplit` region and its grade record.

### Stage 3 — OCR + Grading (`run_ocr_and_grade`)

Triggered by TA clicking "Start grading". For each `pending` or `flagged` region:

1. **Content classification** — Groq vision classifies as `prose` / `math` / `mixed` (skipped for `is_math_subject=True` exams)
2. **OCR** — Gemini 2.5 Flash for math; Groq vision for prose. Auto-fallback: if primary returns empty string, the other API is tried
3. **Embedding** — BGE-small embeds the transcript; stored on `answer_region.embedding` (384-dimensional float array as JSON)
4. **RAG retrieval** — cosine similarity against `AnswerKeyChunk` rows for this question; top-3 chunks injected into the grading prompt
5. **Grading** — Groq text model evaluates each rubric `logic_step` individually, returning `verdict` + `awarded_points` + `justification` per step

> **RAG is optional.** If no answer key PDF was uploaded, step 4 is skipped and the LLM grades solely against the rubric logic steps. Uploading an answer key gives the grading model reference material for each question, which improves scoring accuracy on open-ended and derivation-style answers.
6. `GradeRecord` created; region status → `graded` (or `flagged` if OCR confidence < 0.65)
7. DB committed after every region

Exam status → `graded` → `review`.

### Stage 4 — Plagiarism Detection

After all regions are graded:

1. Groups `AnswerRegion` rows by `question_id` across all students
2. Pairwise cosine similarity on embedding vectors within each group
3. Pairs exceeding **0.92 similarity** → both `GradeRecord` rows get `plagiarism_flagged=True` and `plagiarism_similarity_score` set
4. Flagged regions show a red badge in the review queue and results page; clean exams show a green "No plagiarism detected" banner

### OCR Routing

| `is_math_subject` | Primary | Fallback |
|---|---|---|
| `False` (default) | Groq vision | Gemini 2.5 Flash |
| `True` | Gemini 2.5 Flash | Groq vision |

---

## API Reference

### Auth
```
POST   /api/v1/auth/register
POST   /api/v1/auth/token
```

### Courses
```
POST   /api/v1/courses/
GET    /api/v1/courses/
GET    /api/v1/courses/{id}
GET    /api/v1/courses/{id}/exams
```

### Exams
```
POST   /api/v1/exams/                              Upload exam (instructor only)
GET    /api/v1/exams/{id}                          Exam status + metadata
GET    /api/v1/exams/{id}/results                  Scores per student per question
GET    /api/v1/exams/{id}/regions                  All answer regions
POST   /api/v1/exams/{id}/start-grading            Start OCR + grading pipeline
POST   /api/v1/exams/{id}/regions/{rid}/split      Split a region into labelled bands
```

### Review
```
GET    /api/v1/review/queue?exam_id=               TA review queue (paginated)
POST   /api/v1/review/{region_id}                  Approve or override a grade
```

### Static
```
GET    /uploads/{file_path}    Serve crops and PDFs
GET    /health
```

Full interactive docs available at `http://localhost:8000/docs` (Swagger UI).

---

## Frontend Routes

| Path | Page | Access |
|---|---|---|
| `/login` | Login | public |
| `/register` | Register | public |
| `/dashboard` | Course list | any auth |
| `/courses/new` | Create course | instructor |
| `/courses/:id` | Exam list | any auth |
| `/exams/new` | Upload exam + rubric builder | instructor |
| `/exams/:id` | Pipeline status (auto-polls) | any auth |
| `/exams/:id/splits` | TA split review | any auth |
| `/review/:examId` | TA review queue | any auth |
| `/exams/:id/results` | Grades + statistics | any auth |

### Review Queue Keyboard Shortcuts

| Key | Action |
|---|---|
| `J` | Focus next region |
| `K` | Focus previous region |
| `A` | Approve focused region |
| `E` | Open / close override panel |
| `Esc` | Close override panel |

Shortcuts are suppressed when an input field is focused. A "⌨ Shortcuts" button in the header shows the full reference panel.

---

## Rubric Format

Rubrics are defined visually in the upload form — no JSON knowledge required. Internally serialised as:

```json
{
  "questions": [
    {
      "question_id": "q1",
      "question_text": "Derive the escape velocity formula",
      "max_marks": 8,
      "logic_steps": [
        { "id": "step_1", "description": "Define gravitational PE: U = -GMm/r", "points": 2 },
        { "id": "step_2", "description": "State total energy condition: KE + PE >= 0", "points": 1 },
        { "id": "step_3", "description": "Set (1/2)mv² - GMm/R = 0 and solve for v", "points": 3 },
        { "id": "step_4", "description": "Arrive at v = sqrt(2GM/R) = sqrt(2gR)", "points": 2 }
      ]
    }
  ]
}
```

`question_id` must match what the TA enters when labelling split bands (e.g. `q1`, `q2`). `max_marks` is the sum of all step `points` values — the builder computes it automatically.

---

## Database Schema

### Enums

**ExamStatus:** `uploaded → splitting → split_done → ocr_running → ocr_done → grading → graded → review → completed | failed`

**RegionStatus:** `pending → graded | flagged → approved | overridden`

**ContentType:** `prose | math | mixed | unknown`

**UserRole:** `instructor | ta | admin`

### Tables

**`users`** — id, email, hashed_password, full_name, role, is_active, created_at

**`courses`** — id, code, name, instructor_id, created_at

**`exams`** — id, course_id, instructor_id, title, status, file_path, answer_key_path, is_math_subject, page_count, student_count, rubric (JSON), created_at, completed_at

**`answer_regions`** — id, exam_id, student_identifier, question_id, crop_path, region_confidence, content_type, status, transcript_text, transcript_confidence, embedding (JSON float array), created_at

**`grade_records`** — id, answer_region_id (unique FK), ai_score, max_score, final_score, step_results (JSON), overall_justification, reviewed_by, reviewed_at, override_reason, plagiarism_flagged (bool), plagiarism_similarity_score (float), created_at

**`answer_key_chunks`** — id, exam_id, question_id, chunk_text, embedding (JSON), created_at

**`audit_logs`** — id, actor_id, entity_type, entity_id, action, detail, created_at

---

## Divergences from Original Spec

The original spec proposed: Python + PyTorch + Hugging Face (Nougat/Qwen-VL for OCR) + LangChain + LangGraph, with HTML/CSS + React + FastAPI + PostgreSQL or MongoDB.

| Spec | What was built | Why |
|---|---|---|
| Nougat / Qwen-VL locally via Hugging Face | Groq `llama-4-scout-17b-16e-instruct` + Gemini `gemini-2.5-flash` | Local vision models were too inaccurate on real handwritten exam scripts; cloud APIs gave substantially better OCR quality |
| PyTorch | fastembed ONNX (CPU) | No GPU required; BGE-small-en-v1.5 via ONNX runs on any CPU and is sufficient for RAG retrieval and plagiarism detection |
| LangGraph parallel fan-out | Simple sequential `for` loop | Parallel processing immediately exhausted free-tier rate limits; sequential processing respects limits naturally and saves partial progress after every region |
| OpenCV HoughLinesP auto question boundary detection | TA-driven split UI | Line detection was unreliable on real handwritten scans; the manual cut-line UI is more accurate and gives TAs direct control |
| MongoDB | PostgreSQL | The relational structure between users, courses, exams, regions, and grades made foreign keys and joins the natural fit |
| Raw JSON rubric input | Visual rubric builder | Professors define questions and grading steps directly — no JSON knowledge needed |
| Cloud storage for crops/PDFs | Local `./uploads/` directory | Sufficient for local deployment; Cloudinary config keys exist in `config.py` for a future production path |

---

## Known Limitations

1. **`@lru_cache` on settings** — changing `.env` requires `docker compose up -d --force-recreate api`. A plain `docker compose restart` will not re-read the env file.

2. **Groq daily quota** — the vision model has a 500k token/day limit on the free tier. A full exam run uses roughly 60–80k tokens. Quota resets at midnight UTC. If exhausted mid-pipeline, the exam is marked `failed` and can be retried after midnight via "Retry grading".

3. **Gemini quota is per Google Cloud project** — a new API key in the same project shares the same 1,500 requests/day limit. A different Google account is needed for fresh quota.

4. **No cloud file storage** — file uploads are saved to `./uploads/` on local disk. Cloud deployments require migrating `_save_pdf()` and crop-writing to Cloudinary or equivalent object storage.

5. **Sequential pipeline performance** — grading is one region at a time. For large exams (30 students × 6 questions = 180 regions) this is slow. Re-introducing parallelism with proper rate-limit back-off is the primary performance improvement path.

6. **No split undo** — the split endpoint deletes the original region before creating new bands. Incorrect splits require re-uploading the exam.

---

## Free-Tier API Limits

| Service | Model | Daily Limit | Resets |
|---|---|---|---|
| Groq | `llama-4-scout-17b-16e-instruct` (OCR) | 500k tokens | Midnight UTC |
| Groq | `llama-3.3-70b-versatile` (grading) | Separate quota | Midnight UTC |
| Gemini | `gemini-2.5-flash` (math OCR) | 1,500 requests | Midnight Pacific |
| fastembed | `BAAI/bge-small-en-v1.5` | Unlimited (local) | — |

Both Groq and Gemini free tiers require no credit card. On free accounts the daily cap is the only constraint — there is no financial risk from  exposed key.
