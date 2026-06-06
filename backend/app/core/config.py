"""Application configuration via pydantic-settings."""

from __future__ import annotations

import json
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings, populated from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # --- Database ---
    DATABASE_URL: str = "postgresql+psycopg://hh_analyser:changeme@db:5432/hh_analyser"

    # --- CORS ---
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list) -> list:
        if isinstance(v, str):
            return json.loads(v)
        return v

    # --- LLM (Phase 6+) ---
    API_KEY: str = ""
    LLM_BASE_URL: str = "https://api-copilot.x5.ru/aigw/v1/"
    LLM_MODEL: str = "x5-airun-medium"

    # --- Scheduler ---
    SCHEDULER_CRON_HOUR: int = 3
    SCHEDULER_CRON_MINUTE: int = 0


settings = Settings()
