from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://dail:dail_secret@db:5432/dail_forge"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://dail:dail_secret@db:5432/dail_forge"
    CURATION_API_KEY: str = "dail-forge-secret-key-change-me"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
