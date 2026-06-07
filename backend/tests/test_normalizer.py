"""Tests for Normalizer — salary parsing, grade resolution, skill canonicalization."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from selectolax.parser import HTMLParser

from app.services.html_source import HtmlVacancySource
from app.services.normalizer import Normalizer, _match_grade_keywords
from app.services.source_interface import RawVacancy

FIXTURES = Path(__file__).parent / "fixtures"


# ── Salary normalization ─────────────────────────────────────────────────


class TestSalaryNormalization:
    """Test salary parsing and normalization (currency, gross→net, point_estimate)."""

    def setup_method(self):
        self.normalizer = Normalizer(ndfl_rate=0.13)

    def test_salary_from_to_rub_net(self):
        """80 000 – 120 000 RUR net → point_estimate = 100 000."""
        raw = RawVacancy(
            hh_vacancy_id=1, title="Test",
            salary_from=80000, salary_to=120000,
            salary_currency="RUR", salary_gross=False,
        )
        nv = self.normalizer.normalize(raw)
        assert nv.salary is not None
        assert nv.salary.amount_from_rub_net == 80000.0
        assert nv.salary.amount_to_rub_net == 120000.0
        assert nv.salary.point_estimate_rub_net == 100000.0

    def test_salary_gross_to_net(self):
        """300 000 RUR gross → net = 300000 * 0.87 = 261000."""
        raw = RawVacancy(
            hh_vacancy_id=2, title="Test",
            salary_from=300000, salary_to=None,
            salary_currency="RUR", salary_gross=True,
        )
        nv = self.normalizer.normalize(raw)
        assert nv.salary is not None
        assert nv.salary.amount_from_rub_net == 261000.0
        assert nv.salary.amount_to_rub_net is None
        assert nv.salary.point_estimate_rub_net == 261000.0

    def test_salary_usd(self):
        """3000 USD net → 3000 * 90 = 270000 RUB net."""
        raw = RawVacancy(
            hh_vacancy_id=3, title="Test",
            salary_from=3000, salary_to=5000,
            salary_currency="USD", salary_gross=False,
        )
        nv = self.normalizer.normalize(raw)
        assert nv.salary is not None
        assert nv.salary.amount_from_rub_net == 270000.0
        assert nv.salary.amount_to_rub_net == 450000.0
        assert nv.salary.point_estimate_rub_net == 360000.0

    def test_salary_gross_none_treated_as_gross(self):
        """If gross=None, treat as gross (conservative)."""
        raw = RawVacancy(
            hh_vacancy_id=4, title="Test",
            salary_from=100000, salary_to=None,
            salary_currency="RUR", salary_gross=None,
        )
        nv = self.normalizer.normalize(raw)
        assert nv.salary is not None
        assert nv.salary.amount_from_rub_net == 87000.0

    def test_no_salary(self):
        """No salary info → salary is None."""
        raw = RawVacancy(hh_vacancy_id=5, title="Test")
        nv = self.normalizer.normalize(raw)
        assert nv.salary is None

    def test_salary_only_to(self):
        """Only salary_to → point_estimate = to."""
        raw = RawVacancy(
            hh_vacancy_id=6, title="Test",
            salary_from=None, salary_to=200000,
            salary_currency="RUR", salary_gross=False,
        )
        nv = self.normalizer.normalize(raw)
        assert nv.salary is not None
        assert nv.salary.point_estimate_rub_net == 200000.0


# ── Salary text parsing (from HTML) ─────────────────────────────────────


class TestSalaryTextParsing:
    """Test HtmlVacancySource._parse_salary_text static method."""

    def test_from_to_rub_net(self):
        f, t, c, g = HtmlVacancySource._parse_salary_text(
            "от 80 000 до 120 000 руб. на руки"
        )
        assert f == 80000.0
        assert t == 120000.0
        assert c == "RUR"
        assert g is False

    def test_from_to_rub_gross(self):
        f, t, c, g = HtmlVacancySource._parse_salary_text(
            "от 300 000 до 450 000 руб. до вычета налогов"
        )
        assert f == 300000.0
        assert t == 450000.0
        assert c == "RUR"
        assert g is True

    def test_from_only(self):
        f, t, c, g = HtmlVacancySource._parse_salary_text(
            "от 250 000 руб. на руки"
        )
        assert f == 250000.0
        assert t is None
        assert c == "RUR"
        assert g is False

    def test_usd(self):
        f, t, c, g = HtmlVacancySource._parse_salary_text(
            "от 3 000 до 5 000 USD на руки"
        )
        assert f == 3000.0
        assert t == 5000.0
        assert c == "USD"

    def test_empty(self):
        f, t, c, g = HtmlVacancySource._parse_salary_text("")
        assert f is None
        assert t is None
        assert c is None
        assert g is None


# ── Grade resolution ─────────────────────────────────────────────────────


class TestGradeResolution:
    """Test grade detection from title/experience."""

    def setup_method(self):
        self.normalizer = Normalizer()

    def test_junior_from_title(self):
        raw = RawVacancy(hh_vacancy_id=10, title="Junior Frontend-разработчик")
        nv = self.normalizer.normalize(raw)
        assert nv.grade_code == "junior"

    def test_senior_from_title(self):
        raw = RawVacancy(hh_vacancy_id=11, title="Senior Frontend Developer")
        nv = self.normalizer.normalize(raw)
        assert nv.grade_code == "senior"

    def test_middle_from_title(self):
        raw = RawVacancy(hh_vacancy_id=12,
                         title="Middle Frontend developer React")
        nv = self.normalizer.normalize(raw)
        assert nv.grade_code == "middle"

    def test_junior_from_experience(self):
        raw = RawVacancy(
            hh_vacancy_id=13, title="Frontend developer", experience_raw="noExperience")
        nv = self.normalizer.normalize(raw)
        assert nv.grade_code == "junior"

    def test_senior_from_experience(self):
        raw = RawVacancy(
            hh_vacancy_id=14, title="Frontend developer", experience_raw="between3And6")
        nv = self.normalizer.normalize(raw)
        assert nv.grade_code == "senior"

    def test_unknown_grade(self):
        raw = RawVacancy(hh_vacancy_id=15, title="Frontend developer")
        nv = self.normalizer.normalize(raw)
        assert nv.grade_code == "unknown"

    def test_title_priority_over_experience(self):
        """Title 'Senior' should override experience 'noExperience'."""
        raw = RawVacancy(
            hh_vacancy_id=16, title="Senior Frontend Developer",
            experience_raw="noExperience"
        )
        nv = self.normalizer.normalize(raw)
        assert nv.grade_code == "senior"

    def test_lead_is_senior(self):
        raw = RawVacancy(hh_vacancy_id=17,
                         title="Ведущий Frontend-разработчик")
        nv = self.normalizer.normalize(raw)
        assert nv.grade_code == "senior"

    def test_russian_experience(self):
        raw = RawVacancy(
            hh_vacancy_id=18, title="Frontend разработчик",
            experience_raw="Нет опыта"
        )
        nv = self.normalizer.normalize(raw)
        assert nv.grade_code == "junior"


# ── Skill canonicalization ───────────────────────────────────────────────


class TestSkillCanonicalization:
    def test_dedup_and_lowercase(self):
        normalizer = Normalizer()
        raw = RawVacancy(
            hh_vacancy_id=20, title="Test",
            skills=["React", "react", "  React ", "JavaScript", "javascript"]
        )
        nv = normalizer.normalize(raw)
        assert nv.skills == ["react", "javascript"]

    def test_empty_skills(self):
        normalizer = Normalizer()
        raw = RawVacancy(hh_vacancy_id=21, title="Test", skills=[])
        nv = normalizer.normalize(raw)
        assert nv.skills == []


# ── HTML fixture parsing ─────────────────────────────────────────────────


class TestHtmlFixtureParsing:
    """Test parsing vacancies from HTML fixtures (no network).

    Fixtures reflect real hh.ru magritte redesign markup (validated June 2026).
    Selectors match those configured in app.core.config.HTML_SELECTORS.
    """

    def test_parse_junior_vacancy(self):
        html = (FIXTURES / "vacancy_frontend_junior.html").read_text()
        tree = HTMLParser(html)

        title_node = tree.css_first("h1[data-qa='vacancy-title']")
        assert title_node is not None
        assert "Junior Frontend" in title_node.text(strip=True)

        salary_node = tree.css_first("[data-qa='vacancy-salary']")
        assert salary_node is not None
        f, t, c, g = HtmlVacancySource._parse_salary_text(
            salary_node.text(strip=True))
        assert f == 80000.0
        assert t == 120000.0
        assert c == "RUR"
        assert g is False

    def test_parse_senior_vacancy_gross(self):
        html = (FIXTURES / "vacancy_senior_frontend.html").read_text()
        tree = HTMLParser(html)
        salary_node = tree.css_first("[data-qa='vacancy-salary']")
        f, t, c, g = HtmlVacancySource._parse_salary_text(
            salary_node.text(strip=True))
        assert f == 300000.0
        assert t == 450000.0
        assert g is True

    def test_parse_skills_from_html(self):
        """Skills are inside <li data-qa='skills-element'> with text in
        <div class='magritte-tag__label'> or direct text (real magritte markup)."""
        html = (FIXTURES / "vacancy_frontend_junior.html").read_text()
        tree = HTMLParser(html)
        skill_nodes = tree.css("li[data-qa='skills-element']")
        skills = []
        for sn in skill_nodes:
            tag = sn.css_first("div[class*='magritte-tag__label']")
            if tag:
                skills.append(tag.text(strip=True))
            else:
                text = sn.text(strip=True)
                if text:
                    skills.append(text)
        assert "React" in skills
        assert "JavaScript" in skills
        assert len(skills) == 5

    def test_parse_published_date(self):
        """Published date lives in a <div> containing 'Вакансия опубликована <span>DATE</span>'."""
        html = (FIXTURES / "vacancy_frontend_junior.html").read_text()
        source = HtmlVacancySource()
        tree = HTMLParser(html)
        dt = source._parse_published_date(tree)
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 6
        assert dt.day == 5

    def test_parse_employment_format(self):
        """Employment format uses data-qa='work-formats-text' with 'Формат работы:...' prefix."""
        html = (FIXTURES / "vacancy_frontend_junior.html").read_text()
        tree = HTMLParser(html)
        fmt_node = tree.css_first("[data-qa='work-formats-text']")
        assert fmt_node is not None
        result = HtmlVacancySource._parse_employment_format(
            fmt_node.text(strip=True))
        assert result == "remote"

    def test_parse_employment_hybrid(self):
        html = (FIXTURES / "vacancy_senior_frontend.html").read_text()
        tree = HTMLParser(html)
        fmt_node = tree.css_first("[data-qa='work-formats-text']")
        assert fmt_node is not None
        result = HtmlVacancySource._parse_employment_format(
            fmt_node.text(strip=True))
        assert result == "hybrid"
