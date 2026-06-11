"""Liquidations table (futures !forceOrder stream).

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "liquidations",
        sa.Column("symbol", sa.String(20), primary_key=True),
        sa.Column("ts", sa.TIMESTAMP(timezone=True), primary_key=True),
        sa.Column("side", sa.String(4), primary_key=True),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("qty", sa.Float, nullable=False),
        sa.Column("value_usdt", sa.Float, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("liquidations")
