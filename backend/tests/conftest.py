"""Shared fixtures. DB tests need a running TimescaleDB (docker compose up db).

TEST_DATABASE_URL defaults to the compose database server with a dedicated
``cryptoquant_test`` database, created automatically if missing.
"""

import asyncio
import os
from collections.abc import AsyncIterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://cryptoquant:cryptoquant@localhost:5432/cryptoquant_test",
)

TABLES = [
    "candles",
    "funding_rates",
    "open_interest",
    "long_short_ratio",
    "liquidations",
    "backtests",
    "paper_instances",
    "paper_orders",
    "paper_equity",
    "app_settings",
    "alert_rules",
    "alert_events",
]


async def _ensure_database() -> None:
    admin_url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    db_name = TEST_DATABASE_URL.rsplit("/", 1)[1]
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    await engine.dispose()


@pytest.fixture(scope="session")
def migrated_db() -> str:
    asyncio.run(_ensure_database())
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")
    return TEST_DATABASE_URL


@pytest.fixture
async def db_session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_db)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        for table in TABLES:
            await session.execute(text(f"TRUNCATE {table}"))
        await session.commit()
        yield session
    await engine.dispose()
