"""
Database session factory and file storage helpers.
"""
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# PostgreSQL (asyncpg driver)
# ---------------------------------------------------------------------------

_pg_url = settings.DATABASE_URL.replace(
    "postgresql+psycopg2://", "postgresql+asyncpg://"
).replace(
    "postgresql://", "postgresql+asyncpg://"
)

engine = create_async_engine(
    _pg_url,
    pool_size=10,
    max_overflow=20,
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a committed-or-rolled-back async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# File storage helpers
# ---------------------------------------------------------------------------

def get_upload_path(filename: str) -> str:
    """Return local file path (dev) or Cloudinary URL (prod)."""
    if settings.USE_CLOUDINARY:
        import cloudinary
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
        )
        return f"https://res.cloudinary.com/{settings.CLOUDINARY_CLOUD_NAME}/raw/upload/{filename}"
    return os.path.join(settings.UPLOAD_DIR, filename)
