from functools import lru_cache
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "GradeOps"
    DEBUG: bool = False
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8

    # PostgreSQL
    DATABASE_URL: str = "postgresql+psycopg2://gradeops:gradeops@localhost:5432/gradeops"

    # Groq (free cloud inference — sign up at console.groq.com)
    GROQ_API_KEY: str = ""
    GROQ_VISION_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    GROQ_GRADING_MODEL: str = "llama-3.3-70b-versatile"

    # Gemini Flash (free math OCR — sign up at aistudio.google.com)
    GEMINI_API_KEY: str = ""
    GEMINI_VISION_MODEL: str = "gemini-2.5-flash"

    # File storage
    UPLOAD_DIR: str = "./uploads"
    USE_CLOUDINARY: bool = False

    # Cloudinary (for production)
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # Quality thresholds
    OCR_CONFIDENCE_MIN: float = 0.65
    REGION_CONFIDENCE_MIN: float = 0.70

    model_config = ConfigDict(env_file=".env", case_sensitive=True)


@lru_cache()
def get_settings() -> Settings:
    return Settings()
