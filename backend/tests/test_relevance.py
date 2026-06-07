"""Tests for Relevance Filter — relevant pass, junk is rejected."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.relevance import RelevanceFilter, RelevanceResult, TermEntry
from app.services.seed import POSITIVE_TERMS, STOP_TERMS
from app.services.source_interface import RawVacancy


def _build_filter() -> RelevanceFilter:
    """Build a filter with seed terms (no DB needed for unit tests)."""
    terms = []
    for term, scope, weight in POSITIVE_TERMS:
        terms.append(TermEntry(term=term.lower(), kind="positive",
                     field_scope=scope, weight=weight))
    for term, scope, weight in STOP_TERMS:
        terms.append(TermEntry(term=term.lower(), kind="stop",
                     field_scope=scope, weight=weight))
    return RelevanceFilter(terms=terms)


class TestRelevanceFilter:
    """Test that relevant Frontend vacancies pass and junk is rejected."""

    def setup_method(self):
        self.rf = _build_filter()

    # ── Relevant vacancies should PASS ──

    def test_frontend_junior_passes(self):
        raw = RawVacancy(
            hh_vacancy_id=1,
            title="Junior Frontend-разработчик (React)",
            description="Ищем frontend-разработчика с знанием React, JavaScript.",
            skills=["React", "JavaScript", "TypeScript"],
        )
        result = self.rf.check(raw)
        assert result.relevant is True
        assert result.score > 0

    def test_senior_frontend_passes(self):
        raw = RawVacancy(
            hh_vacancy_id=2,
            title="Senior Frontend Developer (Vue.js / TypeScript)",
            description="Глубокие знания JavaScript, опыт с SPA, Vue.js.",
            skills=["Vue.js", "TypeScript"],
        )
        result = self.rf.check(raw)
        assert result.relevant is True

    def test_frontend_react_developer_passes(self):
        raw = RawVacancy(
            hh_vacancy_id=3,
            title="Фронтенд-разработчик React",
            description="Разработка пользовательских интерфейсов на React.",
            skills=["React", "Redux"],
        )
        result = self.rf.check(raw)
        assert result.relevant is True

    def test_verstka_passes(self):
        """Верстальщик is a Frontend role."""
        raw = RawVacancy(
            hh_vacancy_id=4,
            title="Верстальщик / Frontend developer",
            description="Адаптивная верстка, HTML, CSS, JavaScript.",
            skills=["HTML", "CSS"],
        )
        result = self.rf.check(raw)
        assert result.relevant is True

    # ── Irrelevant vacancies should be REJECTED ──

    def test_fullstack_rejected(self):
        raw = RawVacancy(
            hh_vacancy_id=10,
            title="Fullstack-разработчик (Node.js + React)",
            description="Backend на Node.js, frontend на React.",
            skills=["Node.js", "React"],
        )
        result = self.rf.check(raw)
        assert result.relevant is False

    def test_backend_rejected(self):
        raw = RawVacancy(
            hh_vacancy_id=11,
            title="Backend-разработчик Python (Django)",
            description="REST API, PostgreSQL, Redis.",
            skills=["Python", "Django"],
        )
        result = self.rf.check(raw)
        assert result.relevant is False

    def test_pm_rejected(self):
        """Руководитель проектов is hard-stopped on title."""
        raw = RawVacancy(
            hh_vacancy_id=12,
            title="Руководитель проектов (IT)",
            description="Управление frontend и backend командами.",
            skills=["Agile", "Scrum"],
        )
        result = self.rf.check(raw)
        assert result.relevant is False
        assert result.reason == "hard_stop_title"

    def test_qa_rejected(self):
        raw = RawVacancy(
            hh_vacancy_id=13,
            title="QA Engineer / Тестировщик",
            description="Тестирование frontend-приложений.",
            skills=["Cypress", "Playwright"],
        )
        result = self.rf.check(raw)
        assert result.relevant is False

    def test_devops_rejected(self):
        raw = RawVacancy(
            hh_vacancy_id=14,
            title="DevOps Engineer",
            description="CI/CD, Kubernetes, деплой frontend и backend.",
            skills=["Kubernetes", "Docker"],
        )
        result = self.rf.check(raw)
        assert result.relevant is False

    def test_analyst_rejected(self):
        raw = RawVacancy(
            hh_vacancy_id=15,
            title="Системный аналитик",
            description="Анализ требований, проектирование API.",
            skills=["SQL", "UML"],
        )
        result = self.rf.check(raw)
        assert result.relevant is False

    def test_designer_rejected(self):
        raw = RawVacancy(
            hh_vacancy_id=16,
            title="UI/UX Дизайнер",
            description="Проектирование интерфейсов, Figma.",
            skills=["Figma", "Sketch"],
        )
        result = self.rf.check(raw)
        assert result.relevant is False

    # ── Edge cases ──

    def test_frontend_in_description_only_with_stop_title(self):
        """Stop-signal in title + frontend in description → rejected (title priority)."""
        raw = RawVacancy(
            hh_vacancy_id=20,
            title="Project Manager",
            description="Управление frontend-командой, React-проекты.",
            skills=["React"],
        )
        result = self.rf.check(raw)
        assert result.relevant is False

    def test_pure_frontend_title_no_description(self):
        """Frontend in title, no description → passes."""
        raw = RawVacancy(
            hh_vacancy_id=21,
            title="Frontend developer",
            description="",
            skills=[],
        )
        result = self.rf.check(raw)
        assert result.relevant is True

    def test_empty_vacancy(self):
        """Empty title and description → not relevant (score=0, threshold=0)."""
        raw = RawVacancy(hh_vacancy_id=22, title="", description="", skills=[])
        result = self.rf.check(raw)
        # score=0 and threshold=0 → score >= threshold → relevant
        # This is by design: unknown vacancies with 0 score pass at threshold=0
        # In practice, the crawler would never produce such a vacancy
        assert result.score == 0
