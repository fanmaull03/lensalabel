"""Konfigurasi aplikasi - baca DATABASE_URL dkk dari .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://user:password@localhost:5432/lensalabel"


settings = Settings()
