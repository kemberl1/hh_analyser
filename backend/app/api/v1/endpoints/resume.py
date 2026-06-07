"""Resume analysis endpoint — Phase 7.

REST API per docs/06-api-contract.md §5.2:
  POST /api/v1/resume/analyze — analyse resume (file or text)

Accepts:
  • multipart/form-data with file (PDF/DOCX) + optional target_grade field
  • application/json with { resume_text, target_grade }

Graceful degradation:
  • LLM_ENABLED=false → 200 with rule-based analysis only
  • LLM error/timeout → 200 with partial result (no crash)
  • Format/size errors → 400/413 with clear message
  • All cases return the {meta, data} envelope
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.grade import Grade
from app.schemas.resume import (
    ResumeAnalysisData,
    ResumeAnalysisMeta,
    ResumeAnalysisResponse,
    ResumeTextRequest,
    SalaryRange,
)
from app.services.aggregation import compute_skills_metrics
from app.services.llm.factory import get_llm_client
from app.services.resume.analysis import analyse_resume
from app.services.resume.parser import ResumeParseError, extract_text
from app.services.resume.sanitizer import sanitise_pii
from app.services.resume.skills import extract_skills_from_text, match_skills_with_market

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/resume", tags=["resume"])

# Max file size enforced at application level (5 MB)
MAX_UPLOAD_SIZE = 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_grade_id(
    session: AsyncSession, grade: str | None
) -> tuple[int | None, str]:
    """Resolve grade code to grade_id. Returns (grade_id, label)."""
    if not grade or grade == "all":
        return None, "all"
    result = await session.execute(
        select(Grade.id).where(Grade.code == grade)
    )
    grade_id = result.scalar_one_or_none()
    return grade_id, grade or "all"


async def _get_market_skills(session: AsyncSession, grade_id: int | None) -> list[dict]:
    """Fetch market top skills for matching."""
    skills = await compute_skills_metrics(session, grade_id=grade_id, limit=20)
    return skills.get("skills", [])


async def _run_analysis(
    session: AsyncSession,
    resume_text: str,
    target_grade: str | None,
) -> ResumeAnalysisResponse:
    """Shared analysis logic for both file and text endpoints."""

    # 1. Sanitise PII (NFR-16 — CRITICAL)
    sanitisation = sanitise_pii(resume_text)
    sanitised_text = sanitisation.sanitised_text

    # 2. Extract skills from original text (before sanitisation removes @-handles etc)
    resume_skills = extract_skills_from_text(resume_text)

    # 3. Get market skills and match
    grade_id, grade_label = await _resolve_grade_id(session, target_grade)
    market_skills = await _get_market_skills(session, grade_id)
    skill_match = match_skills_with_market(resume_skills, market_skills)

    # 4. Get LLM client (may be None if disabled)
    llm_client = get_llm_client()

    # 5. Run analysis
    result = await analyse_resume(
        session,
        llm_client,
        sanitised_text=sanitised_text,
        skill_match=skill_match,
        grade_id=grade_id,
        grade_label=grade_label,
    )

    # 6. Build response
    salary_range = None
    if result.get("salary_range") and isinstance(result["salary_range"], dict):
        salary_range = SalaryRange(
            **{"from": result["salary_range"].get("from"), "to": result["salary_range"].get("to")}
        )

    return ResumeAnalysisResponse(
        meta=ResumeAnalysisMeta(
            model=result.get("model"),
            analyzed_at=result.get("analyzed_at"),
            llm_enabled=settings.LLM_ENABLED and bool(settings.API_KEY),
            llm_enhanced=result.get("llm_enhanced", False),
            pii_entities_removed=sanitisation.entities_removed,
        ),
        data=ResumeAnalysisData(
            market_fit_score=result.get("market_fit_score", 0),
            passes_keyword_filters=result.get("passes_keyword_filters", False),
            estimated_grade=result.get("estimated_grade"),
            salary_range=salary_range,
            matched_skills=result.get("matched_skills", []),
            missing_in_demand_skills=result.get(
                "missing_in_demand_skills", []),
            resume_skills=result.get("resume_skills", []),
            skill_match_ratio=result.get("skill_match_ratio", 0.0),
            strengths=result.get("strengths", []),
            weaknesses=result.get("weaknesses", []),
            recommendations=result.get("recommendations", []),
            market_sample_size=result.get("market_sample_size", 0),
            llm_error=result.get("llm_error"),
        ),
    )


# ---------------------------------------------------------------------------
# POST /api/v1/resume/analyze — multipart/form-data (file upload)
# Also accepts form field resume_text for text-only submission
# ---------------------------------------------------------------------------

@router.post("/analyze", response_model=ResumeAnalysisResponse)
async def analyze_resume(
    session: AsyncSession = Depends(get_session),
    file: Optional[UploadFile] = File(None),
    resume_text: Optional[str] = Form(None),
    target_grade: Optional[str] = Form(None),
) -> ResumeAnalysisResponse:
    """Analyse a resume for market fit.

    Accepts either:
    - A file upload (PDF or DOCX) via multipart/form-data
    - Plain text via form field `resume_text`
    - Both (file takes priority)

    PII is sanitised before any external LLM call (NFR-16).
    Resume is NOT stored on the server (NFR-14).
    """
    # Validate target_grade if provided
    if target_grade and target_grade not in ("junior", "middle", "senior"):
        raise HTTPException(
            status_code=400,
            detail="target_grade должен быть: junior, middle или senior",
        )

    try:
        # Extract text from file or raw input
        if file is not None:
            # Read file content with size limit
            content = await file.read()
            if len(content) > MAX_UPLOAD_SIZE:
                raise ResumeParseError(
                    f"Файл слишком большой. Максимальный размер: "
                    f"{MAX_UPLOAD_SIZE // (1024 * 1024)} МБ.",
                    status_code=413,
                )
            text = extract_text(
                file_bytes=content,
                filename=file.filename,
                content_type=file.content_type,
            )
        elif resume_text:
            text = extract_text(raw_text=resume_text)
        else:
            raise ResumeParseError(
                "Необходимо загрузить файл (PDF/DOCX) или ввести текст резюме."
            )

        return await _run_analysis(session, text, target_grade)

    except ResumeParseError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        )


# ---------------------------------------------------------------------------
# POST /api/v1/resume/analyze/text — JSON body (alternative)
# ---------------------------------------------------------------------------

@router.post("/analyze/text", response_model=ResumeAnalysisResponse)
async def analyze_resume_text(
    body: ResumeTextRequest,
    session: AsyncSession = Depends(get_session),
) -> ResumeAnalysisResponse:
    """Analyse resume from JSON text body.

    Alternative to multipart — accepts plain JSON:
    { "resume_text": "...", "target_grade": "middle" }
    """
    try:
        text = extract_text(raw_text=body.resume_text)
        return await _run_analysis(session, text, body.target_grade)
    except ResumeParseError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        )
