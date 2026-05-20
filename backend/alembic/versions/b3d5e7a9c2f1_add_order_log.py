"""add order_log table

Revision ID: b3d5e7a9c2f1
Revises: 9a2c4f8e1b6d
Create Date: 2026-05-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.storage.types  # UtcDateTime 커스텀 타입 참조용


# revision identifiers, used by Alembic.
revision: str = "b3d5e7a9c2f1"
down_revision: Union[str, Sequence[str], None] = "9a2c4f8e1b6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create order_log table — 주문 시도 영구 로그 (dry_run 포함)."""
    op.create_table(
        "order_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("signal_id", sa.Integer(), sa.ForeignKey("signal.id"), nullable=True),
        sa.Column("stock_code", sa.String(length=6), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("order_type", sa.String(length=8), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("request_payload", sa.Text(), nullable=False),
        sa.Column("response_payload", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("created_at", app.storage.types.UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_order_log_signal_id"), "order_log", ["signal_id"], unique=False
    )


def downgrade() -> None:
    """Drop order_log table."""
    op.drop_index(op.f("ix_order_log_signal_id"), table_name="order_log")
    op.drop_table("order_log")
