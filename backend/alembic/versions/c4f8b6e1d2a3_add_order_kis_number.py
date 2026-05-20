"""add order_log kis_order_number

Revision ID: c4f8b6e1d2a3
Revises: b3d5e7a9c2f1
Create Date: 2026-05-20 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4f8b6e1d2a3"
down_revision: Union[str, Sequence[str], None] = "b3d5e7a9c2f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add kis_order_number column + index to order_log."""
    op.add_column(
        "order_log",
        sa.Column("kis_order_number", sa.String(length=32), nullable=True),
    )
    op.create_index(
        op.f("ix_order_log_kis_order_number"),
        "order_log",
        ["kis_order_number"],
        unique=False,
    )


def downgrade() -> None:
    """Drop kis_order_number index + column."""
    op.drop_index(op.f("ix_order_log_kis_order_number"), table_name="order_log")
    op.drop_column("order_log", "kis_order_number")
