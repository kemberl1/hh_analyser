"""Baseline empty migration.

Revision ID: 0001_baseline
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Baseline — empty migration to verify Alembic setup."""
    pass


def downgrade() -> None:
    """Nothing to downgrade."""
    pass
