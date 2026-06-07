"""Pydantic v2 schemas for resume analysis API — Phase 7.

Matches the JSON contract in docs/06-api-contract.md §5.2.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# §5.2 — Resume Analysis
# ---------------------------------------------------------------------------

class ResumeAnalysisMeta(BaseModel):
    """Metadata envelope for resume analysis response."""
    model: str | None = None
    embedding_model: str | None = None
    analyzed_at: str | None = None
    llm_enabled: bool = True
    llm_enhanced: bool = False
    pii_entities_removed: int = 0


class SalaryRange(BaseModel):
    """Estimated salary range."""
    from_: int | None = Field(None, alias="from")
    to: int | None = None

    model_config = {"populate_by_name": True}


class ResumeAnalysisData(BaseModel):
    """Resume analysis result payload."""
    market_fit_score: int = 0
    passes_keyword_filters: bool = False
    estimated_grade: str | None = None
    salary_range: SalaryRange | None = None
    matched_skills: list[str] = Field(default_factory=list)
    missing_in_demand_skills: list[str] = Field(default_factory=list)
    resume_skills: list[str] = Field(default_factory=list)
    skill_match_ratio: float = 0.0
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    market_sample_size: int = 0
    llm_error: str | None = None


class ResumeAnalysisResponse(BaseModel):
    """Full response for POST /api/v1/resume/analyze."""
    meta: ResumeAnalysisMeta
    data: ResumeAnalysisData


class ResumeTextRequest(BaseModel):
    """JSON body for text-based resume submission."""
    resume_text: str = Field(..., min_length=1, max_length=50000)
    target_grade: str | None = Field(
        None, pattern="^(junior|middle|senior)$"
    )
