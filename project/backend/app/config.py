from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV: str = "development"
    APP_NAME: str = "StudyMate AI"
    LOG_LEVEL: str = "INFO"
    ENABLE_METRICS: bool = True

    JWT_SECRET: str = "dev-secret"
    JWT_ACCESS_MIN: int = 30
    JWT_REFRESH_DAYS: int = 14
    CORS_ORIGINS: str = "http://localhost:3000"

    DATABASE_URL: str = "postgresql+asyncpg://studymate:studymate@postgres:5432/studymate"
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://studymate:studymate@postgres:5432/studymate"
    REDIS_URL: str = "redis://redis:6379/0"
    CHROMA_HOST: str = "chroma"
    CHROMA_PORT: int = 8000

    LLM_PROVIDER: str = "ollama"
    OLLAMA_HOST: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "llama3.2:3b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    ADMIN_EMAIL: str = "admin@studymate.local"
    ADMIN_PASSWORD: str = "admin1234"

    RATE_LIMIT_PER_MINUTE: int = 120

    @property
    def cors_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
