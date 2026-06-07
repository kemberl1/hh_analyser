"""Resume analysis service — Phase 7.

Orchestrates the full resume analysis pipeline:
  1. Text extraction (parser)
  2. PII sanitisation (sanitizer, NFR-16)
  3. Skill extraction and market matching (skills)
  4. Market context collection (aggregation)
  5. LLM prompt generation and call (LLMClient.chat)
  6. Structured result assembly

Follows the pattern established by market_insights.py (Phase 6):
  - Anonymised context only (NFR-16)
  - Graceful degradation when LLM is disabled/failing
  - No raw PII persisted (NFR-14)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.aggregation import (
    compute_salary_metrics,
    compute_skills_metrics,
)
from app.services.llm.base import LLMClient, LLMError, LLMMessage
from app.services.resume.sanitizer import sanitise_pii
from app.services.resume.skills import (
    SkillMatchResult,
    extract_skills_from_text,
    match_skills_with_market,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Market context builder (reuses aggregation.py)
# ---------------------------------------------------------------------------

async def build_resume_market_context(
    session: AsyncSession,
    *,
    grade_id: int | None = None,
    grade_label: str = "all",
) -> dict[str, Any]:
    """Collect anonymised market data for resume comparison.

    Returns salary stats and top skills — NO PII, NO raw data.
    """
    salary = await compute_salary_metrics(session)
    skills_all = await compute_skills_metrics(session, limit=30)

    # Also get grade-specific if a target grade is specified
    salary_grade = None
    skills_grade = None
    if grade_id is not None:
        salary_grade = await compute_salary_metrics(session, grade_id=grade_id)
        skills_grade = await compute_skills_metrics(session, grade_id=grade_id, limit=20)

    return {
        "grade_filter": grade_label,
        "salary_all": {
            "median": salary.get("median"),
            "p25": salary.get("percentiles", {}).get("p25"),
            "p75": salary.get("percentiles", {}).get("p75"),
            "min": salary.get("min"),
            "max": salary.get("max"),
            "sample_size": salary.get("count", 0),
            "total_vacancies": salary.get("total_count", 0),
        },
        "salary_grade": {
            "median": salary_grade.get("median") if salary_grade else None,
            "p25": salary_grade.get("percentiles", {}).get("p25") if salary_grade else None,
            "p75": salary_grade.get("percentiles", {}).get("p75") if salary_grade else None,
            "sample_size": salary_grade.get("count", 0) if salary_grade else 0,
        } if salary_grade else None,
        "top_skills_all": [
            {"name": s["skill"], "share": s["share"], "count": s["count"]}
            for s in skills_all.get("skills", [])
        ],
        "top_skills_grade": [
            {"name": s["skill"], "share": s["share"], "count": s["count"]}
            for s in (skills_grade or {}).get("skills", [])
        ] if skills_grade else None,
    }


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
Ты — эксперт-карьерный консультант по Frontend-разработке в России.
Тебе предоставлен ОБЕЗЛИЧЕННЫЙ текст резюме (без имён, контактов, адресов) \
и текущие АГРЕГИРОВАННЫЕ рыночные данные по Frontend-вакансиям.

На основе этих данных ты должен оценить «профпригодность» кандидата:

1. **Общая оценка** (0–100): насколько резюме соответствует текущему рынку Frontend.
2. **Предполагаемый грейд**: Junior / Middle / Senior — на основе опыта и навыков.
3. **Зарплатная вилка**: ориентировочная вилка в рублях для данного профиля на рынке.
4. **Прохождение фильтров**: пройдёт ли это резюме типичные фильтры рекрутеров по ключевым словам.
5. **Сильные стороны**: что хорошо в резюме относительно рыночного спроса.
6. **Слабые стороны / пробелы**: чего не хватает относительно востребованных навыков.
7. **Конкретные рекомендации** (3–5): что добавить/улучшить для повышения шансов.

Отвечай на русском языке. Будь конкретным, опирайся на рыночные данные.
НЕ выдумывай данных, которых нет. Если чего-то не хватает — скажи об этом.

ВАЖНО: Верни ответ в формате JSON (без markdown-обёрток) со следующей структурой:
{
  "market_fit_score": <число 0-100>,
  "estimated_grade": "<junior|middle|senior>",
  "salary_range": {"from": <число>, "to": <число>},
  "passes_keyword_filters": <true|false>,
  "strengths": ["<сильная сторона 1>", ...],
  "weaknesses": ["<слабая сторона 1>", ...],
  "recommendations": ["<рекомендация 1>", ...]
}\
"""


def build_resume_prompt(
    sanitised_text: str,
    skill_match: SkillMatchResult,
    market_context: dict[str, Any],
) -> list[LLMMessage]:
    """Build chat messages for resume analysis LLM call.

    All data is already sanitised — no PII in the prompt.
    """
    ctx_json = json.dumps(
        market_context, ensure_ascii=False, indent=2, default=str)

    user_message = (
        "## Обезличенный текст резюме\n\n"
        f"{sanitised_text}\n\n"
        "## Извлечённые навыки из резюме\n"
        f"Найдены: {', '.join(skill_match.resume_skills) if skill_match.resume_skills else 'не найдены'}\n\n"
        "## Сопоставление с рынком\n"
        f"Совпадают с топ-востребованными: {', '.join(skill_match.matched_skills) if skill_match.matched_skills else 'нет совпадений'}\n"
        f"Отсутствуют из топ-востребованных: {', '.join(skill_match.missing_skills) if skill_match.missing_skills else 'все покрыты'}\n"
        f"Коэффициент покрытия рынка: {skill_match.match_ratio:.0%}\n\n"
        "## Текущие рыночные данные (Frontend, Россия)\n\n"
        f"```json\n{ctx_json}\n```\n\n"
        "Проанализируй это резюме и верни структурированную оценку в формате JSON."
    )

    return [
        LLMMessage(role="system", content=_SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_message),
    ]


# ---------------------------------------------------------------------------
# LLM response parser
# ---------------------------------------------------------------------------

def _parse_llm_response(content: str) -> dict[str, Any]:
    """Best-effort parse of LLM JSON response.

    Handles cases where LLM wraps JSON in markdown code blocks.
    """
    text = content.strip()

    # Strip markdown code block if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

    logger.warning("llm_response_not_json", content_preview=text[:200])
    return {}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def analyse_resume(
    session: AsyncSession,
    llm_client: LLMClient | None,
    *,
    sanitised_text: str,
    skill_match: SkillMatchResult,
    grade_id: int | None = None,
    grade_label: str = "all",
) -> dict[str, Any]:
    """Run full resume analysis.

    Parameters
    ----------
    session : DB session for market data queries.
    llm_client : LLM client (None if disabled).
    sanitised_text : PII-free resume text.
    skill_match : pre-computed skill matching result.
    grade_id : optional target grade DB id.
    grade_label : target grade label for context.

    Returns
    -------
    Structured analysis result dict suitable for API response.
    Includes graceful degradation when LLM is unavailable.
    """
    # 1. Build market context (anonymised aggregates)
    market_context = await build_resume_market_context(
        session, grade_id=grade_id, grade_label=grade_label,
    )

    # Base result from rule-based analysis (always available)
    salary_data = market_context.get(
        "salary_grade") or market_context.get("salary_all", {})
    result: dict[str, Any] = {
        "market_fit_score": _compute_rule_based_score(skill_match, salary_data),
        "passes_keyword_filters": skill_match.match_ratio >= 0.3,
        "matched_skills": skill_match.matched_skills,
        "missing_in_demand_skills": skill_match.missing_skills,
        "resume_skills": skill_match.resume_skills,
        "skill_match_ratio": skill_match.match_ratio,
        "recommendations": _rule_based_recommendations(skill_match),
        "estimated_grade": None,
        "salary_range": None,
        "strengths": [],
        "weaknesses": [],
        "model": None,
        "llm_enhanced": False,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "market_sample_size": market_context.get("salary_all", {}).get("total_vacancies", 0),
    }

    # 2. If LLM is available, enhance with AI analysis
    if llm_client is not None:
        try:
            messages = build_resume_prompt(
                sanitised_text, skill_match, market_context)

            logger.info(
                "resume_analysis_llm_request",
                skills_found=len(skill_match.resume_skills),
                match_ratio=skill_match.match_ratio,
            )

            response = await llm_client.chat(messages)

            # Parse structured response
            llm_data = _parse_llm_response(response.content)

            if llm_data:
                # Merge LLM insights into result
                if "market_fit_score" in llm_data:
                    score = llm_data["market_fit_score"]
                    if isinstance(score, (int, float)) and 0 <= score <= 100:
                        result["market_fit_score"] = round(score)
                if "estimated_grade" in llm_data:
                    result["estimated_grade"] = llm_data["estimated_grade"]
                if "salary_range" in llm_data and isinstance(llm_data["salary_range"], dict):
                    result["salary_range"] = llm_data["salary_range"]
                if "passes_keyword_filters" in llm_data:
                    result["passes_keyword_filters"] = bool(
                        llm_data["passes_keyword_filters"])
                if "strengths" in llm_data and isinstance(llm_data["strengths"], list):
                    result["strengths"] = llm_data["strengths"]
                if "weaknesses" in llm_data and isinstance(llm_data["weaknesses"], list):
                    result["weaknesses"] = llm_data["weaknesses"]
                if "recommendations" in llm_data and isinstance(llm_data["recommendations"], list):
                    result["recommendations"] = llm_data["recommendations"]

            result["model"] = response.model
            result["llm_enhanced"] = True

            logger.info(
                "resume_analysis_llm_done",
                model=response.model,
                tokens=response.usage.get("total_tokens"),
                score=result["market_fit_score"],
            )

        except LLMError as exc:
            logger.warning(
                "resume_analysis_llm_error",
                error=str(exc),
                status_code=exc.status_code,
            )
            # Graceful degradation: return rule-based result
            result["llm_error"] = "LLM-анализ временно недоступен. Показаны результаты на основе правил."

        except Exception as exc:
            logger.error("resume_analysis_unexpected_error", error=str(exc))
            result["llm_error"] = "Произошла ошибка при LLM-анализе. Показаны результаты на основе правил."

    else:
        result["llm_error"] = (
            "LLM-анализ отключён. Показаны результаты на основе "
            "автоматического сопоставления навыков с рынком."
        )

    return result


# ---------------------------------------------------------------------------
# Rule-based fallback scoring
# ---------------------------------------------------------------------------

def _compute_rule_based_score(skill_match: SkillMatchResult, salary_data: dict) -> int:
    """Compute a basic market fit score from skill matching.

    Score 0–100 based on:
    - Skill match ratio (70% weight)
    - Number of skills found (30% weight, capped)
    """
    ratio_score = skill_match.match_ratio * 70

    # Having many skills is a signal of experience
    skills_count = len(skill_match.resume_skills)
    skills_score = min(skills_count / 10, 1.0) * \
        30  # cap at 10 skills → 30 pts

    return round(ratio_score + skills_score)


def _rule_based_recommendations(skill_match: SkillMatchResult) -> list[str]:
    """Generate basic recommendations from skill gap analysis."""
    recs: list[str] = []

    if skill_match.missing_skills:
        top_missing = skill_match.missing_skills[:5]
        recs.append(
            f"Добавьте в резюме опыт работы с: {', '.join(top_missing)}. "
            "Эти навыки наиболее востребованы на рынке."
        )

    if skill_match.match_ratio < 0.3:
        recs.append(
            "Ваше покрытие ключевых рыночных навыков ниже 30%. "
            "Рекомендуется расширить стек технологий или более подробно описать имеющийся опыт."
        )
    elif skill_match.match_ratio < 0.5:
        recs.append(
            "Покрытие рыночных навыков умеренное. "
            "Для повышения шансов стоит добавить недостающие ключевые технологии."
        )

    if not skill_match.resume_skills:
        recs.append(
            "В резюме не найдены технические навыки. "
            "Укажите конкретные технологии, фреймворки и инструменты."
        )

    if len(skill_match.resume_skills) < 5:
        recs.append(
            "В резюме указано мало навыков. Перечислите все технологии, "
            "с которыми работали (React, TypeScript, Git и т.д.)."
        )

    if not recs:
        recs.append(
            "Профиль навыков хорошо соответствует рынку. "
            "Для дальнейшего роста обратите внимание на углубление специализации."
        )

    return recs[:5]
