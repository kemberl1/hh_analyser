"""Aggregation service — compute metrics M1–M5 from database.

Phase 4: All metrics per 04-metrics.md, computed over vacancies filtered
by published_at (Europe/Moscow timezone) and optional grade.

Public functions return plain dicts suitable for snapshot payload storage.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from itertools import combinations
from typing import Any, Sequence

import numpy as np
from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employer import Employer
from app.models.grade import Grade
from app.models.salary import Salary
from app.models.skill import Skill
from app.models.vacancy import Vacancy
from app.models.vacancy_skill import VacancySkill

# ---------------------------------------------------------------------------
# Config defaults (from 04-metrics.md §5)
# ---------------------------------------------------------------------------
LOW_CONFIDENCE_THRESHOLD = 30
TOP_N_SKILLS = 20
TOP_N_EMPLOYERS = 20
PERCENTILES = [10, 25, 50, 75, 90]

MSK_TZ = timezone(timedelta(hours=3))


# ---------------------------------------------------------------------------
# Period bucketing helpers
# ---------------------------------------------------------------------------

def period_start_for(dt: date, period_type: str) -> date:
    """Return the bucket start date for the given date and period type."""
    if period_type == "day":
        return dt
    elif period_type == "week":
        # ISO week: Monday
        return dt - timedelta(days=dt.weekday())
    elif period_type == "month":
        return dt.replace(day=1)
    elif period_type == "year":
        return dt.replace(month=1, day=1)
    raise ValueError(f"Unknown period_type: {period_type}")


def period_end_for(start: date, period_type: str) -> date:
    """Return the exclusive end date for a bucket starting at `start`."""
    if period_type == "day":
        return start + timedelta(days=1)
    elif period_type == "week":
        return start + timedelta(days=7)
    elif period_type == "month":
        m = start.month % 12 + 1
        y = start.year + (1 if start.month == 12 else 0)
        return date(y, m, 1)
    elif period_type == "year":
        return date(start.year + 1, 1, 1)
    raise ValueError(f"Unknown period_type: {period_type}")


def enumerate_periods(date_from: date, date_to: date, period_type: str) -> list[date]:
    """Return all period_start values that cover [date_from, date_to]."""
    periods: list[date] = []
    current = period_start_for(date_from, period_type)
    while current <= date_to:
        periods.append(current)
        current = period_end_for(current, period_type)
    return periods


# ---------------------------------------------------------------------------
# Base query helpers
# ---------------------------------------------------------------------------

def _vacancy_base_filter(
    stmt,
    date_from: date | None,
    date_to: date | None,
    grade_id: int | None,
):
    """Apply common filters to a vacancy query."""
    if date_from is not None:
        # published_at >= date_from (start of day MSK)
        dt_from = datetime(date_from.year, date_from.month,
                           date_from.day, tzinfo=MSK_TZ)
        stmt = stmt.where(Vacancy.published_at >= dt_from)
    if date_to is not None:
        # published_at < date_to + 1 day (exclusive end, to include the full last day)
        dt_to = datetime(date_to.year, date_to.month,
                         date_to.day, tzinfo=MSK_TZ) + timedelta(days=1)
        stmt = stmt.where(Vacancy.published_at < dt_to)
    if grade_id is not None:
        stmt = stmt.where(Vacancy.grade_id == grade_id)
    return stmt


# ---------------------------------------------------------------------------
# M1 — Salary metrics
# ---------------------------------------------------------------------------

async def compute_salary_metrics(
    session: AsyncSession,
    date_from: date | None = None,
    date_to: date | None = None,
    grade_id: int | None = None,
) -> dict[str, Any]:
    """Compute M1 salary metrics: median, min, max, mean, percentiles, range_avg, disclosure_rate.

    Returns dict suitable for snapshot payload.
    """
    # Total vacancy count (for disclosure rate)
    total_stmt = select(func.count(Vacancy.id))
    total_stmt = _vacancy_base_filter(total_stmt, date_from, date_to, grade_id)
    total_result = await session.execute(total_stmt)
    total_count = total_result.scalar() or 0

    # Salary values: point_estimate_rub_net for vacancies with salary
    salary_stmt = (
        select(
            Salary.point_estimate_rub_net,
            Salary.amount_from_rub_net,
            Salary.amount_to_rub_net,
        )
        .join(Vacancy, Vacancy.id == Salary.vacancy_id)
        .where(Salary.point_estimate_rub_net.is_not(None))
    )
    salary_stmt = _vacancy_base_filter(
        salary_stmt, date_from, date_to, grade_id)
    result = await session.execute(salary_stmt)
    rows = result.all()

    if not rows:
        return {
            "count": 0,
            "total_count": total_count,
            "median": None,
            "min": None,
            "max": None,
            "mean": None,
            "percentiles": {f"p{p}": None for p in PERCENTILES},
            "range_avg": {"from": None, "to": None},
            "salary_disclosure_rate": 0.0 if total_count > 0 else None,
            "low_confidence": True,
        }

    estimates = np.array([float(r[0]) for r in rows])
    froms = [float(r[1]) for r in rows if r[1] is not None]
    tos = [float(r[2]) for r in rows if r[2] is not None]

    sample_size = len(estimates)
    low_confidence = sample_size < LOW_CONFIDENCE_THRESHOLD

    percentile_values = np.percentile(estimates, PERCENTILES).tolist()
    percentiles_dict = {f"p{p}": round(v, 2) for p, v in zip(
        PERCENTILES, percentile_values)}

    return {
        "count": sample_size,
        "total_count": total_count,
        "median": round(float(np.median(estimates)), 2),
        "min": round(float(np.min(estimates)), 2),
        "max": round(float(np.max(estimates)), 2),
        "mean": round(float(np.mean(estimates)), 2),
        "percentiles": percentiles_dict,
        "range_avg": {
            "from": round(float(np.mean(froms)), 2) if froms else None,
            "to": round(float(np.mean(tos)), 2) if tos else None,
        },
        "salary_disclosure_rate": round(sample_size / total_count, 4) if total_count > 0 else None,
        "low_confidence": low_confidence,
    }


# ---------------------------------------------------------------------------
# M2 — Skills metrics
# ---------------------------------------------------------------------------

async def compute_skills_metrics(
    session: AsyncSession,
    date_from: date | None = None,
    date_to: date | None = None,
    grade_id: int | None = None,
    limit: int = TOP_N_SKILLS,
) -> dict[str, Any]:
    """Compute M2 skills metrics: top-N skills with count and share."""
    # Total vacancies in slice (denominator for share)
    total_stmt = select(func.count(Vacancy.id))
    total_stmt = _vacancy_base_filter(total_stmt, date_from, date_to, grade_id)
    total_result = await session.execute(total_stmt)
    total_count = total_result.scalar() or 0

    if total_count == 0:
        return {"skills": [], "sample_size": 0, "low_confidence": True}

    # Count vacancies per skill
    skill_stmt = (
        select(
            Skill.display_name,
            Skill.canonical_name,
            func.count(VacancySkill.vacancy_id).label("cnt"),
        )
        .join(VacancySkill, VacancySkill.skill_id == Skill.id)
        .join(Vacancy, Vacancy.id == VacancySkill.vacancy_id)
    )
    skill_stmt = _vacancy_base_filter(skill_stmt, date_from, date_to, grade_id)
    skill_stmt = (
        skill_stmt
        .group_by(Skill.id, Skill.display_name, Skill.canonical_name)
        .order_by(func.count(VacancySkill.vacancy_id).desc())
        .limit(limit)
    )
    result = await session.execute(skill_stmt)
    rows = result.all()

    skills = [
        {
            "skill": r[0],
            "canonical": r[1],
            "count": r[2],
            "share": round(r[2] / total_count, 4) if total_count > 0 else 0,
        }
        for r in rows
    ]

    return {
        "skills": skills,
        "sample_size": total_count,
        "low_confidence": total_count < LOW_CONFIDENCE_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# M3 — Employers metrics
# ---------------------------------------------------------------------------

async def compute_employers_metrics(
    session: AsyncSession,
    date_from: date | None = None,
    date_to: date | None = None,
    grade_id: int | None = None,
    limit: int = TOP_N_EMPLOYERS,
) -> dict[str, Any]:
    """Compute M3 employer metrics: top employers with count, share, concentration."""
    total_stmt = select(func.count(Vacancy.id))
    total_stmt = _vacancy_base_filter(total_stmt, date_from, date_to, grade_id)
    total_result = await session.execute(total_stmt)
    total_count = total_result.scalar() or 0

    if total_count == 0:
        return {
            "employers": [],
            "top10_concentration": 0.0,
            "sample_size": 0,
            "low_confidence": True,
        }

    emp_stmt = (
        select(
            Employer.id,
            Employer.hh_employer_id,
            Employer.name,
            func.count(Vacancy.id).label("cnt"),
        )
        .join(Vacancy, Vacancy.employer_id == Employer.id)
    )
    emp_stmt = _vacancy_base_filter(emp_stmt, date_from, date_to, grade_id)
    emp_stmt = (
        emp_stmt
        .group_by(Employer.id, Employer.hh_employer_id, Employer.name)
        .order_by(func.count(Vacancy.id).desc())
        .limit(limit)
    )
    result = await session.execute(emp_stmt)
    rows = result.all()

    employers = [
        {
            "employer_id": r[1],  # hh_employer_id
            "name": r[2],
            "count": r[3],
            "share": round(r[3] / total_count, 4) if total_count > 0 else 0,
        }
        for r in rows
    ]

    # Top-10 concentration (M3.3)
    top10_count = sum(e["count"] for e in employers[:10])
    top10_concentration = round(
        top10_count / total_count, 4) if total_count > 0 else 0.0

    return {
        "employers": employers,
        "top10_concentration": top10_concentration,
        "sample_size": total_count,
        "low_confidence": total_count < LOW_CONFIDENCE_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# M4 — Demand trend (timeseries)
# ---------------------------------------------------------------------------

async def compute_demand_metrics(
    session: AsyncSession,
    period_type: str = "month",
    date_from: date | None = None,
    date_to: date | None = None,
    grade_id: int | None = None,
) -> dict[str, Any]:
    """Compute M4.1/M4.3: vacancy count per bucket with growth rate."""
    # Get all vacancies' published_at in range
    stmt = select(Vacancy.published_at)
    stmt = _vacancy_base_filter(stmt, date_from, date_to, grade_id)
    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return {"points": [], "low_confidence": True}

    # Bucket counts
    bucket_counts: dict[date, int] = {}
    for (pub_at,) in rows:
        if pub_at is None:
            continue
        # Convert to MSK date
        if pub_at.tzinfo is None:
            pub_at = pub_at.replace(tzinfo=timezone.utc)
        msk_date = pub_at.astimezone(MSK_TZ).date()
        bucket = period_start_for(msk_date, period_type)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

    # Sort by period_start
    sorted_buckets = sorted(bucket_counts.items())

    points = []
    for i, (ps, count) in enumerate(sorted_buckets):
        growth = None
        if i > 0:
            prev_count = sorted_buckets[i - 1][1]
            if prev_count > 0:
                growth = round((count - prev_count) / prev_count, 4)
        points.append({
            "period_start": ps.isoformat(),
            "count": count,
            "growth": growth,
        })

    return {
        "points": points,
        "low_confidence": sum(bucket_counts.values()) < LOW_CONFIDENCE_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# M4.2 — Salary timeseries
# ---------------------------------------------------------------------------

async def compute_salary_timeseries(
    session: AsyncSession,
    period_type: str = "month",
    date_from: date | None = None,
    date_to: date | None = None,
    grade_id: int | None = None,
) -> dict[str, Any]:
    """Compute M4.2: median salary per bucket with percentiles."""
    stmt = (
        select(Vacancy.published_at, Salary.point_estimate_rub_net)
        .join(Salary, Salary.vacancy_id == Vacancy.id)
        .where(Salary.point_estimate_rub_net.is_not(None))
    )
    stmt = _vacancy_base_filter(stmt, date_from, date_to, grade_id)
    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return {"points": [], "low_confidence": True}

    # Bucket values
    buckets: dict[date, list[float]] = {}
    for pub_at, estimate in rows:
        if pub_at is None or estimate is None:
            continue
        if pub_at.tzinfo is None:
            pub_at = pub_at.replace(tzinfo=timezone.utc)
        msk_date = pub_at.astimezone(MSK_TZ).date()
        bucket = period_start_for(msk_date, period_type)
        buckets.setdefault(bucket, []).append(float(estimate))

    sorted_buckets = sorted(buckets.items())
    points = []
    for ps, values in sorted_buckets:
        arr = np.array(values)
        points.append({
            "period_start": ps.isoformat(),
            "median": round(float(np.median(arr)), 2),
            "p25": round(float(np.percentile(arr, 25)), 2),
            "p75": round(float(np.percentile(arr, 75)), 2),
            "count": len(values),
        })

    return {
        "points": points,
        "low_confidence": sum(len(v) for v in buckets.values()) < LOW_CONFIDENCE_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# M5.1–M5.3 — Distribution metrics
# ---------------------------------------------------------------------------

async def compute_distribution(
    session: AsyncSession,
    by: str = "grade",
    date_from: date | None = None,
    date_to: date | None = None,
    grade_id: int | None = None,
) -> dict[str, Any]:
    """Compute M5.1–M5.3: distribution by grade / format / experience."""
    if by == "grade":
        col_key = Grade.code
        col_label = Grade.title
        stmt = (
            select(col_key, col_label, func.count(Vacancy.id))
            .outerjoin(Grade, Grade.id == Vacancy.grade_id)
        )
        # grade filter not applied when viewing grade distribution
        stmt = _vacancy_base_filter(stmt, date_from, date_to, None)
        stmt = stmt.group_by(col_key, col_label).order_by(
            func.count(Vacancy.id).desc())
    elif by == "format":
        stmt = (
            select(
                Vacancy.employment_format,
                Vacancy.employment_format,  # label = same
                func.count(Vacancy.id),
            )
        )
        stmt = _vacancy_base_filter(stmt, date_from, date_to, grade_id)
        stmt = stmt.group_by(Vacancy.employment_format).order_by(
            func.count(Vacancy.id).desc())
    elif by == "experience":
        stmt = (
            select(
                Vacancy.experience_raw,
                Vacancy.experience_raw,
                func.count(Vacancy.id),
            )
        )
        stmt = _vacancy_base_filter(stmt, date_from, date_to, grade_id)
        stmt = stmt.group_by(Vacancy.experience_raw).order_by(
            func.count(Vacancy.id).desc())
    else:
        raise ValueError(f"Unknown distribution dimension: {by}")

    result = await session.execute(stmt)
    rows = result.all()

    total = sum(r[2] for r in rows) if rows else 0
    distribution = []
    for key, label, count in rows:
        distribution.append({
            "key": key or "unknown",
            "label": label or "Unknown",
            "count": count,
            "share": round(count / total, 4) if total > 0 else 0,
        })

    return {
        "distribution": distribution,
        "sample_size": total,
        "low_confidence": total < LOW_CONFIDENCE_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# M5.4 — Skill co-occurrence
# ---------------------------------------------------------------------------

async def compute_skill_cooccurrence(
    session: AsyncSession,
    date_from: date | None = None,
    date_to: date | None = None,
    grade_id: int | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Compute M5.4: top co-occurring skill pairs."""
    # Total vacancies for share computation
    total_stmt = select(func.count(Vacancy.id))
    total_stmt = _vacancy_base_filter(total_stmt, date_from, date_to, grade_id)
    total_result = await session.execute(total_stmt)
    total_count = total_result.scalar() or 0

    if total_count == 0:
        return {"pairs": [], "sample_size": 0, "low_confidence": True}

    # Fetch vacancy_id → list of skill display_names (Python-side pair counting)
    vs_stmt = (
        select(VacancySkill.vacancy_id, Skill.display_name)
        .join(Skill, Skill.id == VacancySkill.skill_id)
        .join(Vacancy, Vacancy.id == VacancySkill.vacancy_id)
    )
    vs_stmt = _vacancy_base_filter(vs_stmt, date_from, date_to, grade_id)
    result = await session.execute(vs_stmt)
    rows = result.all()

    # Group skills by vacancy
    vacancy_skills: dict[int, list[str]] = {}
    for vid, skill_name in rows:
        vacancy_skills.setdefault(vid, []).append(skill_name)

    # Count pairs
    pair_counts: dict[tuple[str, str], int] = {}
    for skills_list in vacancy_skills.values():
        if len(skills_list) < 2:
            continue
        unique_skills = sorted(set(skills_list))
        for a, b in combinations(unique_skills, 2):
            pair_counts[(a, b)] = pair_counts.get((a, b), 0) + 1

    # Sort and take top N
    sorted_pairs = sorted(pair_counts.items(),
                          key=lambda x: x[1], reverse=True)[:limit]

    pairs = [
        {
            "a": a,
            "b": b,
            "count": cnt,
            "share": round(cnt / total_count, 4) if total_count > 0 else 0,
        }
        for (a, b), cnt in sorted_pairs
    ]

    return {
        "pairs": pairs,
        "sample_size": total_count,
        "low_confidence": total_count < LOW_CONFIDENCE_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# Overview — aggregated dashboard summary
# ---------------------------------------------------------------------------

async def compute_overview(
    session: AsyncSession,
    date_from: date | None = None,
    date_to: date | None = None,
    grade_id: int | None = None,
) -> dict[str, Any]:
    """Compute combined overview metrics for the dashboard."""
    salary = await compute_salary_metrics(session, date_from, date_to, grade_id)
    skills = await compute_skills_metrics(session, date_from, date_to, grade_id, limit=5)
    employers = await compute_employers_metrics(session, date_from, date_to, grade_id, limit=5)
    grade_dist = await compute_distribution(session, "grade", date_from, date_to, grade_id)
    demand = await compute_demand_metrics(session, "month", date_from, date_to, grade_id)

    # Demand growth MoM: growth of last point
    demand_growth_mom = None
    if demand["points"] and len(demand["points"]) >= 1:
        last_point = demand["points"][-1]
        demand_growth_mom = last_point.get("growth")

    return {
        "salary": {
            "median": salary.get("median"),
            "p25": salary.get("percentiles", {}).get("p25"),
            "p75": salary.get("percentiles", {}).get("p75"),
        },
        "total_vacancies": salary.get("total_count", 0),
        "salary_disclosure_rate": salary.get("salary_disclosure_rate"),
        "top_skills": [
            {"skill": s["skill"], "share": s["share"]}
            for s in skills.get("skills", [])
        ],
        "top_employers": [
            {"name": e["name"], "count": e["count"]}
            for e in employers.get("employers", [])
        ],
        "grade_distribution": grade_dist.get("distribution", []),
        "demand_growth_mom": demand_growth_mom,
        "low_confidence": salary.get("low_confidence", True),
    }
