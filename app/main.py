import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.routes import auth, courses, exams, review
from app.core.config import get_settings
from app.db.session import engine
from app.models.pg_models import Base

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure uploads directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    # Create all PostgreSQL tables on startup (use Alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="HITL exam grading pipeline — fully open-source model stack",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(courses.router, prefix="/api/v1")
app.include_router(exams.router, prefix="/api/v1")
app.include_router(review.router, prefix="/api/v1")


@app.get("/uploads/{file_path:path}")
async def serve_upload(file_path: str):
    full_path = os.path.join(settings.UPLOAD_DIR, file_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(full_path)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}
