"""app_settings key/value table.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(60), primary_key=True),
        sa.Column("value_json", sa.JSON, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
