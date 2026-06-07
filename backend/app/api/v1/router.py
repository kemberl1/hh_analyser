"""V1 API router — aggregates all v1 endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.ingestion import router as ingestion_router
from app.api.v1.endpoints.insights import router as insights_router
from app.api.v1.endpoints.metrics import router as metrics_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(health_router, tags=["health"])
v1_router.include_router(ingestion_router)
v1_router.include_router(metrics_router)
v1_router.include_router(insights_router)
