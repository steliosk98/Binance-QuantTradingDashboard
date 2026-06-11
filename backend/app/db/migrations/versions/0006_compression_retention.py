"""TimescaleDB compression + retention policies (spec §3.2, Stage 9).

- candles: compress chunks older than 30 days (segment by symbol, interval)
- liquidations: 90-day retention

Policies are best-effort: skipped gracefully on plain Postgres (e.g. CI
service images without the toolkit licence features).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            BEGIN
                ALTER TABLE candles SET (
                    timescaledb.compress,
                    timescaledb.compress_segmentby = 'symbol, interval',
                    timescaledb.compress_orderby = 'open_time DESC'
                );
                PERFORM add_compression_policy('candles', INTERVAL '30 days',
                    if_not_exists => TRUE);
            EXCEPTION WHEN OTHERS THEN
                RAISE NOTICE 'candles compression policy skipped: %', SQLERRM;
            END;
            BEGIN
                PERFORM add_retention_policy('liquidations', INTERVAL '90 days',
                    if_not_exists => TRUE);
            EXCEPTION WHEN OTHERS THEN
                RAISE NOTICE 'liquidations retention skipped (not a hypertable): %', SQLERRM;
            END;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            BEGIN
                PERFORM remove_compression_policy('candles', if_exists => TRUE);
            EXCEPTION WHEN OTHERS THEN NULL;
            END;
            BEGIN
                PERFORM remove_retention_policy('liquidations', if_exists => TRUE);
            EXCEPTION WHEN OTHERS THEN NULL;
            END;
        END $$;
        """
    )
