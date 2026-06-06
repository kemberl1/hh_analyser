"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import v1_router
from app.core.config import settings
from app.core.logging import setup_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN001
    """Application lifespan: startup / shutdown hooks."""
    setup_logging(settings.LOG_LEVEL)
    logger.info("app_starting", env=settings.APP_ENV)
    yield
    logger.info("app_shutting_down")


app = FastAPI(
    title="HH Analyser API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(v1_router)


# Root-level convenience health endpoint
@app.get("/health")
async def root_health() -> dict:
    return {"status": "ok"}
