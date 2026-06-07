"""Phase 4 — snapshots table for precomputed aggregations.

Revision ID: 0003_phase4
Revises: 0002_phase2
Create Date: 2026-06-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_phase4"
down_revision: Union[str, None] = "0002_phase2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("metric_type", sa.Text(), nullable=False),
        sa.Column("period_type", sa.Text(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("grade_id", sa.SmallInteger(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("gross_basis", sa.Boolean(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "metric_type", "period_type", "period_start",
            "grade_id", "currency", "gross_basis",
            name="uq_snapshots_slice",
        ),
    )
    op.create_index(
        "ix_snapshots_lookup",
        "snapshots",
        ["metric_type", "period_type", "period_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_snapshots_lookup", table_name="snapshots")
    op.drop_table("snapshots")
