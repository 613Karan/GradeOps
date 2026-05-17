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

    # Ollama (all models served locally)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_ROUTER_MODEL: str = "qwen2.5:0.5b"
    OLLAMA_OCR_MODEL: str = "moondream"
    OLLAMA_GRADING_MODEL: str = "qwen2.5:0.5b"

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
