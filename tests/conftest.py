"""
Pytest fixtures.
All tests run with:
  - SQLite in-memory (no PostgreSQL needed)
  - httpx AsyncClient against the FastAPI app
  - BackgroundTasks mocked so the pipeline doesn't actually run

Run: pytest tests/ -v
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest.mock import patch, AsyncMock, MagicMock

from app.main import app
from app.db.session import get_db
from app.models.pg_models import Base
from app.core.security import hash_password
from app.models.pg_models import User, UserRole


# ---------------------------------------------------------------------------
# In-memory SQLite engine (replaces PostgreSQL for unit tests)
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create all tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _get_test_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Mock pipeline and file I/O so tests don't need Ollama/PyMuPDF/disk
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_pipeline(monkeypatch):
    """Replace run_pipeline with a no-op so tests don't need Ollama/PyMuPDF."""
    monkeypatch.setattr(
        "app.api.routes.exams.run_pipeline",
        AsyncMock(return_value=None),
    )


@pytest.fixture(autouse=True)
def mock_save_pdf(monkeypatch):
    """Replace _save_pdf with a stub returning a fake path — no disk I/O."""
    async def _fake_save(file, exam_id):
        return f"/tmp/fake_uploads/{exam_id}/original.pdf"

    monkeypatch.setattr("app.api.routes.exams._save_pdf", _fake_save)


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client():
    app.dependency_overrides[get_db] = _get_test_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Pre-created test users
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def instructor_user():
    async with TestSessionLocal() as db:
        user = User(
            email="instructor@test.com",
            full_name="Test Instructor",
            hashed_password=hash_password("password123"),
            role=UserRole.INSTRUCTOR,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest_asyncio.fixture
async def ta_user():
    async with TestSessionLocal() as db:
        user = User(
            email="ta@test.com",
            full_name="Test TA",
            hashed_password=hash_password("password123"),
            role=UserRole.TA,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest_asyncio.fixture
async def instructor_token(client, instructor_user):
    resp = await client.post("/api/v1/auth/token", data={
        "username": "instructor@test.com",
        "password": "password123",
    })
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def ta_token(client, ta_user):
    resp = await client.post("/api/v1/auth/token", data={
        "username": "ta@test.com",
        "password": "password123",
    })
    return resp.json()["access_token"]
