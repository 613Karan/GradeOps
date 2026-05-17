from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_instructor
from app.db.session import get_db
from app.models.pg_models import Course, User
from app.schemas.schemas import CourseCreate, CourseRead

router = APIRouter(prefix="/courses", tags=["courses"])


@router.post("/", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
async def create_course(
    payload: CourseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor),
):
    course = Course(
        code=payload.code,
        name=payload.name,
        instructor_id=current_user.id,
    )
    db.add(course)
    await db.flush()
    await db.refresh(course)
    await db.commit()
    return course


@router.get("/", response_model=list[CourseRead])
async def list_courses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Course).order_by(Course.created_at.desc()))
    return result.scalars().all()


@router.get("/{course_id}", response_model=CourseRead)
async def get_course(
    course_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Course).where(Course.id == UUID(course_id)))
    course = result.scalar_one_or_none()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course
