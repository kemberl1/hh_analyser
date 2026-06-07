"""Phase 2 — all tables for parser, relevance, normalization, ingestion.

Revision ID: 0002_phase2
Revises: 0001_baseline
Create Date: 2026-06-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_phase2"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- grades ---
    op.create_table(
        "grades",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=True),
        sa.UniqueConstraint("code", name="uq_grades_code"),
    )

    # --- employers ---
    op.create_table(
        "employers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("hh_employer_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("trusted", sa.Boolean(),
                  server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "hh_employer_id", name="uq_employers_hh_employer_id"),
    )
    op.create_index("ix_employers_name", "employers", ["name"])

    # --- ingestion_runs ---
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("found_total", sa.Integer(),
                  server_default="0", nullable=False),
        sa.Column("created_count", sa.Integer(),
                  server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(),
                  server_default="0", nullable=False),
        sa.Column("error_count", sa.Integer(),
                  server_default="0", nullable=False),
        sa.Column("filtered_count", sa.Integer(),
                  server_default="0", nullable=False),
        sa.Column("api_fallback_count", sa.Integer(),
                  server_default="0", nullable=False),
        sa.Column("captcha_block_count", sa.Integer(),
                  server_default="0", nullable=False),
        sa.Column("meta", postgresql.JSONB(), nullable=True),
    )

    # --- vacancies ---
    op.create_table(
        "vacancies",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("hh_vacancy_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("employer_id", sa.BigInteger(), sa.ForeignKey(
            "employers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("grade_id", sa.SmallInteger(),
                  sa.ForeignKey("grades.id"), nullable=True),
        sa.Column("experience_raw", sa.Text(), nullable=True),
        sa.Column("employment_format", sa.Text(), nullable=True),
        sa.Column("area_name", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hh_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("archived", sa.Boolean(),
                  server_default="false", nullable=False),
        sa.Column("source_type", sa.Text(),
                  server_default="'html'", nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("raw_html", sa.Text(), nullable=True),
        sa.Column("ingestion_run_id", sa.BigInteger(),
                  sa.ForeignKey("ingestion_runs.id"), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "hh_vacancy_id", name="uq_vacancies_hh_vacancy_id"),
    )
    op.create_index("ix_vacancies_published_at", "vacancies", ["published_at"])
    op.create_index("ix_vacancies_grade_published",
                    "vacancies", ["grade_id", "published_at"])
    op.create_index("ix_vacancies_employer", "vacancies", ["employer_id"])

    # --- salaries ---
    op.create_table(
        "salaries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("vacancy_id", sa.BigInteger(), sa.ForeignKey(
            "vacancies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_from", sa.Numeric(14, 2), nullable=True),
        sa.Column("amount_to", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("gross", sa.Boolean(), nullable=True),
        sa.Column("amount_from_rub_net", sa.Numeric(14, 2), nullable=True),
        sa.Column("amount_to_rub_net", sa.Numeric(14, 2), nullable=True),
        sa.Column("point_estimate_rub_net", sa.Numeric(14, 2), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("vacancy_id", name="uq_salaries_vacancy_id"),
    )
    op.create_index("ix_salaries_point_estimate",
                    "salaries", ["point_estimate_rub_net"])

    # --- skills ---
    op.create_table(
        "skills",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("canonical_name", name="uq_skills_canonical_name"),
    )

    # --- skill_aliases ---
    op.create_table(
        "skill_aliases",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("skill_id", sa.BigInteger(), sa.ForeignKey(
            "skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.UniqueConstraint("alias", name="uq_skill_aliases_alias"),
    )

    # --- vacancy_skills ---
    op.create_table(
        "vacancy_skills",
        sa.Column("vacancy_id", sa.BigInteger(), sa.ForeignKey(
            "vacancies.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("skill_id", sa.BigInteger(), sa.ForeignKey(
            "skills.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("source", sa.Text(),
                  server_default="'key_skills'", nullable=False),
    )
    op.create_index("ix_vacancy_skills_skill_id",
                    "vacancy_skills", ["skill_id"])

    # --- currency_rates ---
    op.create_table(
        "currency_rates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("rate_to_rub", sa.Numeric(14, 6), nullable=False),
        sa.UniqueConstraint("currency", "rate_date",
                            name="uq_currency_rates_currency_date"),
    )

    # --- relevance_terms ---
    op.create_table(
        "relevance_terms",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("field_scope", sa.Text(),
                  server_default="'any'", nullable=False),
        sa.Column("weight", sa.Numeric(6, 2),
                  server_default="1.0", nullable=False),
        sa.Column("active", sa.Boolean(),
                  server_default="true", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("term", "kind", "field_scope",
                            name="uq_relevance_terms_term_kind_scope"),
    )
    op.create_index("ix_relevance_terms_kind_active",
                    "relevance_terms", ["kind", "active"])

    # --- filtered_vacancies ---
    op.create_table(
        "filtered_vacancies",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("hh_vacancy_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("matched_stopword", sa.Text(), nullable=True),
        sa.Column("ingestion_run_id", sa.BigInteger(),
                  sa.ForeignKey("ingestion_runs.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_filtered_vacancies_run",
                    "filtered_vacancies", ["ingestion_run_id"])
    op.create_index("ix_filtered_vacancies_hh_id",
                    "filtered_vacancies", ["hh_vacancy_id"])

    # --- seed grades ---
    op.execute("""
        INSERT INTO grades (id, code, title, sort_order) VALUES
            (1, 'junior',  'Junior',  1),
            (2, 'middle',  'Middle',  2),
            (3, 'senior',  'Senior',  3),
            (4, 'unknown', 'Unknown', 4)
        ON CONFLICT (code) DO NOTHING;
    """)


def downgrade() -> None:
    op.drop_table("filtered_vacancies")
    op.drop_table("relevance_terms")
    op.drop_table("currency_rates")
    op.drop_table("vacancy_skills")
    op.drop_table("skill_aliases")
    op.drop_table("skills")
    op.drop_table("salaries")
    op.drop_table("vacancies")
    op.drop_table("ingestion_runs")
    op.drop_table("employers")
    op.drop_table("grades")
