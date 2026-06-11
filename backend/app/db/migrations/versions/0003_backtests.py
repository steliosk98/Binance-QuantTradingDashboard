"""Backtests table.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backtests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("strategy", sa.String(40), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("interval", sa.String(4), nullable=False),
        sa.Column("start", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("end", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("params_json", sa.JSON, nullable=True),
        sa.Column("metrics_json", sa.JSON, nullable=True),
        sa.Column("equity_json", sa.JSON, nullable=True),
        sa.Column("trades_json", sa.JSON, nullable=True),
        sa.Column("walkforward_json", sa.JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("backtests")
