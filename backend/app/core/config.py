"""Application configuration via pydantic-settings."""

from __future__ import annotations

import json
from typing import Any, Dict, List

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
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173", "http://localhost:3000"]

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
    LLM_ENABLED: bool = True
    # Optional custom CA bundle (PEM) for the LLM endpoint TLS chain.
    # X5 CoPilot is fronted by an internal X5 corporate CA (sre-vault.x5.ru)
    # that is NOT part of the public certifi bundle; point this at a PEM
    # containing that chain to keep TLS verification ON. Empty → default certifi.
    LLM_CA_BUNDLE: str = ""
    LLM_TIMEOUT: int = 60  # seconds
    LLM_MAX_RETRIES: int = 3
    LLM_CACHE_TTL: int = 3600  # seconds (1 hour)
    LLM_MAX_TOKENS: int = 2048
    LLM_TEMPERATURE: float = 0.4

    # --- Scheduler ---
    SCHEDULER_CRON_HOUR: int = 3
    SCHEDULER_CRON_MINUTE: int = 0
    SCHEDULER_TIMEZONE: str = "Europe/Moscow"
    SCHEDULER_MAX_PAGES: int | None = None  # None → use HH_MAX_PAGES
    SCHEDULER_MISFIRE_GRACE_TIME: int = 3600  # seconds; skip if missed by > 1h

    # ======== Phase 2: Crawler / Parser ========

    # Source selection: "html" (primary) or "api" (fallback)
    HH_SOURCE: str = "html"
    # Enable API fallback (off by default, FR-3)
    HH_API_FALLBACK_ENABLED: bool = False

    # Crawler behaviour
    HH_USER_AGENT: str = "HHAnalyserBot/1.0 (contact: hh-analyser@example.com)"
    HH_REQUEST_DELAY_MIN: float = 1.5  # seconds between requests
    HH_REQUEST_DELAY_MAX: float = 3.5
    HH_RATE_LIMIT_RPS: float = 1.0  # max requests per second (aiolimiter)
    HH_MAX_PAGES: int = 20  # pagination limit for search results
    HH_ITEMS_PER_PAGE: int = 20  # hh.ru default items per search page
    HH_BASE_URL: str = "https://hh.ru"
    HH_SEARCH_PATH: str = "/search/vacancy"
    HH_SEARCH_PARAMS: Dict[str, Any] = {
        "text": "frontend developer",
        "area": "113",  # Russia
        "per_page": "20",
    }

    # API fallback settings
    HH_API_BASE_URL: str = "https://api.hh.ru"

    # ======== Phase 2: HTML CSS Selectors (FR-37 — configurable) ========
    HTML_SELECTORS: Dict[str, str] = {
        # Search page selectors
        "vacancy_card": "div.vacancy-serp-item",
        "vacancy_link": "a.serp-item__title",
        "vacancy_link_alt": "a[data-qa='serp-item__title']",
        "next_page": "a[data-qa='pager-next']",
        # Vacancy detail page selectors
        "title": "h1[data-qa='vacancy-title']",
        "salary": "[data-qa='vacancy-salary']",
        "salary_alt": "span[data-qa='vacancy-salary-compensation-type-net'], span[data-qa='vacancy-salary-compensation-type-gross']",
        "employer_name": "a[data-qa='vacancy-company-name']",
        "employer_link": "a[data-qa='vacancy-company-name']",
        "experience": "[data-qa='vacancy-experience']",
        "employment_mode": "[data-qa='work-formats-text']",
        "description": "div[data-qa='vacancy-description']",
        "skills": "li[data-qa='skills-element']",
        "skill_tag": "div[class*='magritte-tag__label']",
        "published_date": "p.vacancy-creation-time-redesigned",
        "published_date_alt": "span[data-qa='vacancy-creation-time']",
        # Captcha detection
        "captcha_form": "form.HHCaptchaForm",
        "captcha_img": "img.hhcaptcha-picture",
    }

    @field_validator("HTML_SELECTORS", mode="before")
    @classmethod
    def parse_html_selectors(cls, v: str | dict) -> dict:
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("HH_SEARCH_PARAMS", mode="before")
    @classmethod
    def parse_search_params(cls, v: str | dict) -> dict:
        if isinstance(v, str):
            return json.loads(v)
        return v

    # ======== Phase 2: Relevance Filter (§2.3a) ========
    RELEVANCE_THRESHOLD: float = 0.0  # score >= threshold → relevant
    # hard stop-signal in title → reject regardless of score
    RELEVANCE_HARD_STOP_ON_TITLE: bool = True
    RELEVANCE_TITLE_WEIGHT_MULTIPLIER: float = 3.0  # title signals weigh N× more
    RELEVANCE_AUDIT_ENABLED: bool = True  # write rejected to filtered_vacancies

    # ======== Phase 2: Salary Normalization ========
    NDFL_RATE: float = 0.13  # default tax rate for gross→net conversion


settings = Settings()
