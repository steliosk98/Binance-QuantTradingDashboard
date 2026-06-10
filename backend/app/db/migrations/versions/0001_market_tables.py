"""Market data tables: candles, funding_rates, open_interest, long_short_ratio.

Candles becomes a TimescaleDB hypertable partitioned on open_time.

Revision ID: 0001
Revises:
Create Date: 2026-06-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.create_table(
        "candles",
        sa.Column("symbol", sa.String(20), primary_key=True),
        sa.Column("interval", sa.String(4), primary_key=True),
        sa.Column("open_time", sa.TIMESTAMP(timezone=True), primary_key=True),
        sa.Column("open", sa.Float, nullable=False),
        sa.Column("high", sa.Float, nullable=False),
        sa.Column("low", sa.Float, nullable=False),
        sa.Column("close", sa.Float, nullable=False),
        sa.Column("volume", sa.Float, nullable=False),
        sa.Column("quote_volume", sa.Float, nullable=False),
        sa.Column("trades", sa.BigInteger, nullable=False),
        sa.Column("taker_buy_volume", sa.Float, nullable=False),
    )
    op.execute(
        "SELECT create_hypertable('candles', 'open_time', "
        "chunk_time_interval => INTERVAL '7 days', migrate_data => TRUE)"
    )

    op.create_table(
        "funding_rates",
        sa.Column("symbol", sa.String(20), primary_key=True),
        sa.Column("funding_time", sa.TIMESTAMP(timezone=True), primary_key=True),
        sa.Column("rate", sa.Float, nullable=False),
    )

    op.create_table(
        "open_interest",
        sa.Column("symbol", sa.String(20), primary_key=True),
        sa.Column("ts", sa.TIMESTAMP(timezone=True), primary_key=True),
        sa.Column("oi", sa.Float, nullable=False),
        sa.Column("oi_value", sa.Float, nullable=False),
    )

    op.create_table(
        "long_short_ratio",
        sa.Column("symbol", sa.String(20), primary_key=True),
        sa.Column("ts", sa.TIMESTAMP(timezone=True), primary_key=True),
        sa.Column("ratio", sa.Float, nullable=False),
        sa.Column("long_pct", sa.Float, nullable=False),
        sa.Column("short_pct", sa.Float, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("long_short_ratio")
    op.drop_table("open_interest")
    op.drop_table("funding_rates")
    op.drop_table("candles")
