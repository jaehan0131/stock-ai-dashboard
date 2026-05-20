"""add signal target_stocks

Revision ID: 9a2c4f8e1b6d
Revises: 67a73e05a325
Create Date: 2026-05-19 21:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9a2c4f8e1b6d"
down_revision: Union[str, Sequence[str], None] = "67a73e05a325"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add target_stocks column to signal table (JSON array text, nullable)."""
    op.add_column(
        "signal",
        sa.Column("target_stocks", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop target_stocks column."""
    op.drop_column("signal", "target_stocks")
