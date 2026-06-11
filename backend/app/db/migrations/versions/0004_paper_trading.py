"""Paper trading tables: instances, orders, equity curve.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_instances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("strategy", sa.String(40), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("interval", sa.String(4), nullable=False),
        sa.Column("qty_usd", sa.Float, nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="running"),
        sa.Column("params_json", sa.JSON, nullable=True),
        sa.Column("guards_json", sa.JSON, nullable=True),
        sa.Column("state_json", sa.JSON, nullable=True),
    )
    op.create_table(
        "paper_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("instance_id", sa.String(36), nullable=False, index=True),
        sa.Column("ts", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("type", sa.String(10), nullable=False, server_default="MARKET"),
        sa.Column("qty", sa.Float, nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="filled"),
        sa.Column("signal", sa.String(200), nullable=True),
        sa.Column("testnet_order_id", sa.String(40), nullable=True),
    )
    op.create_table(
        "paper_equity",
        sa.Column("instance_id", sa.String(36), primary_key=True),
        sa.Column("ts", sa.TIMESTAMP(timezone=True), primary_key=True),
        sa.Column("equity_usd", sa.Float, nullable=False),
        sa.Column("position_qty", sa.Float, nullable=False),
        sa.Column("price", sa.Float, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("paper_equity")
    op.drop_table("paper_orders")
    op.drop_table("paper_instances")
