# GradeOps — Setup & Testing Guide

## Prerequisites
- Python 3.11+
- Docker + Docker Compose
- 8 GB RAM minimum (for mock stack)
- A GPU with 6+ GB VRAM *only* when swapping in real models (not needed for dev/tests)

---

## 1. Clone and install Python deps

```bash
git clone <your-repo>
cd gradeops

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

---

## 2. Run unit tests (zero infrastructure needed)

These tests use SQLite in-memory + mongomock. No Docker, no GPU, no running services.

```bash
pytest tests/ -v
```

Expected output:
```
tests/test_auth.py::test_register_instructor          PASSED
tests/test_auth.py::test_register_duplicate_email     PASSED
tests/test_auth.py::test_login_success                PASSED
tests/test_auth.py::test_login_wrong_password         PASSED
tests/test_auth.py::test_register_invalid_role        PASSED
tests/test_exams.py::test_create_exam_as_instructor   PASSED
tests/test_exams.py::test_create_exam_rejected_for_ta PASSED
...
tests/test_workers.py::test_classify_math             PASSED
tests/test_workers.py::test_grading_llm_parses_json   PASSED
...
```

Run with coverage:
```bash
pytest tests/ --cov=app --cov-report=term-missing
```

---

## 3. Run the full dev stack (Docker, mock AI services, no GPU)

This spins up Postgres, MongoDB, Redis, LocalStack S3, all mock AI services,
the FastAPI app, and a Celery worker — all in Docker.

```bash
docker-compose -f docker-compose.dev.yml up --build
```

Wait for all services to be healthy (~60s on first run, mainly Ollama pulling qwen2.5:0.5b).

The API will be available at: http://localhost:8000
Swagger docs:               http://localhost:8000/docs

---

## 4. Test the API manually (HTTPie or curl)

### Register users
```bash
# Register an instructor
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"prof@uni.edu","full_name":"Prof Smith","password":"pass1234","role":"instructor"}'

# Register a TA
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"ta@uni.edu","full_name":"Teaching Assistant","password":"pass1234","role":"ta"}'
```

### Get tokens
```bash
export INSTRUCTOR_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=prof@uni.edu&password=pass1234" | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

export TA_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=ta@uni.edu&password=pass1234" | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### Upload an exam + rubric
```bash
# Create a sample rubric file
cat > /tmp/rubric.json << 'RUBRIC'
{
  "questions": [{
    "question_id": "Q1",
    "question_text": "Apply the Arrhenius equation to find k.",
    "max_marks": 5.0,
    "logic_steps": [
      {"id": "step_1", "description": "Correct equation setup", "points": 2.0},
      {"id": "step_2", "description": "Correct substitution", "points": 2.0},
      {"id": "step_3", "description": "Final answer within 5% tolerance", "points": 1.0, "numeric_tolerance_pct": 5.0}
    ],
    "answer_key_text": "k = A * e^(-Ea/RT)"
  }]
}
RUBRIC

# Use any PDF as a test exam scan
curl -X POST http://localhost:8000/api/v1/exams/ \
  -H "Authorization: Bearer $INSTRUCTOR_TOKEN" \
  -F "title=CH301 Midterm" \
  -F "course_id=00000000-0000-0000-0000-000000000001" \
  -F "rubric_json=$(cat /tmp/rubric.json)" \
  -F "pdf_file=@/path/to/exam.pdf"
```

The response gives you an `exam_id`. The system immediately enqueues the
splitter → OCR → grading pipeline (running against mock services in dev).

### Check exam status
```bash
curl http://localhost:8000/api/v1/exams/<exam_id> \
  -H "Authorization: Bearer $INSTRUCTOR_TOKEN"
```

### Check Celery worker logs
```bash
docker-compose -f docker-compose.dev.yml logs -f worker
```

### View TA review queue (after grading completes)
```bash
curl "http://localhost:8000/api/v1/review/queue?exam_id=<exam_id>" \
  -H "Authorization: Bearer $TA_TOKEN"
```

### Approve or override a grade
```bash
# Approve AI grade
curl -X POST http://localhost:8000/api/v1/review/<region_id> \
  -H "Authorization: Bearer $TA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"final_score": 3.5}'

# Override with reason
curl -X POST http://localhost:8000/api/v1/review/<region_id> \
  -H "Authorization: Bearer $TA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"final_score": 4.5, "override_reason": "Student showed correct approach, minor arithmetic error"}'
```

---

## 5. Swap in real models (when GPU available)

Edit `.env.dev` and change the relevant service URLs:

| Service | Dev (mock) | Real (GPU) |
|---------|------------|------------|
| OCR | `mock-ocr:8001` | vLLM serving `Qwen/Qwen2.5-VL-3B-Instruct` |
| Grading | `mock-grading:8003` | vLLM serving `Qwen/Qwen2.5-7B-Instruct` |
| Embed | `mock-embed:8004` | FlagEmbedding serving `BAAI/bge-m3` |
| Layout | `mock-layout:8005` | PaddleOCR 3.0 service |
| Router | Ollama `qwen2.5:0.5b` | Same (CPU is fine) |

### Serve real models with vLLM (one-time GPU setup)

```bash
# OCR model — ~6 GB VRAM
pip install vllm
vllm serve Qwen/Qwen2.5-VL-3B-Instruct --port 8001 --dtype bfloat16

# Grading model — ~8 GB VRAM
vllm serve Qwen/Qwen2.5-7B-Instruct --port 8003 --dtype bfloat16

# Router — CPU, via Ollama
ollama pull qwen2.5:0.5b
ollama serve   # runs on :11434
```

### BGE-M3 embedding service (CPU)
```bash
pip install FlagEmbedding fastapi uvicorn
# See services/embed_service/ (to be added in next iteration)
```

---

## 6. Model summary

| Component | Model | Size | License | Hardware |
|-----------|-------|------|---------|----------|
| LLM Router | Qwen2.5-0.5B-Instruct | 0.5B | Apache 2.0 | CPU |
| OCR (primary) | Qwen2.5-VL-3B-Instruct | 3B | Apache 2.0 | ~6 GB GPU |
| Grading Judge | Qwen2.5-7B-Instruct | 7B | Apache 2.0 | ~8 GB GPU |
| Embeddings | BGE-M3 | 568M | Apache 2.0 | CPU |
| Layout Detection | PaddleOCR 3.0 | — | Apache 2.0 | CPU |

Total GPU memory needed for real stack: ~14 GB (a single RTX 3090/4090 handles both).
Both models can also run quantised (Q4) on CPU (~16 GB RAM) if no GPU is available,
just with higher latency (~10–30s per answer instead of ~1–3s).
