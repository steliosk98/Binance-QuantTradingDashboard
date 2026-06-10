# CryptoQuant

A self-hosted crypto quant analytics & trading-research platform powered by the Binance API.
Ingests spot + USD-M futures market data, stores it as queryable time series (TimescaleDB),
computes technical / statistical / microstructure analytics, backtests strategies, and
paper-trades them on **Binance Spot Testnet only** — there is no live-money trading mode.

> Research tool. Not financial advice. No live trading.

## Status

Built in stages — see [BUILD_LOG.md](BUILD_LOG.md) for progress.

- ✅ Stage 0 — Repo scaffolding, CI, Docker skeleton
- ✅ Stage 1 — Binance REST client + historical backfill
- ✅ Stage 2 — Market data REST API + basic charting UI
- ⬜ Stage 3 — WebSocket live layer
- ⬜ Stage 4 — Analytics engine (indicators + statistics)
- ⬜ Stage 5 — Microstructure + derivatives + regime widget
- ⬜ Stage 6 — Backtesting engine + UI
- ⬜ Stage 7 — Paper trading on Binance Testnet
- ⬜ Stage 8 — Portfolio (read-only) + settings + auth
- ⬜ Stage 9 — Hardening, E2E, deployment

## Stack

FastAPI + Python 3.12 (uv/ruff/mypy/pytest) · React 19 + TypeScript + Vite + Tailwind ·
PostgreSQL 16 + TimescaleDB · Redis 7 · Docker Compose · GitHub Actions.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs

## Local development

```bash
# Backend
cd backend
uv sync
uv run uvicorn app.main:app --reload   # http://localhost:8000
uv run pytest                          # tests
uv run ruff check . && uv run mypy     # lint + types

# Frontend
cd frontend
pnpm install
pnpm dev                               # http://localhost:5173
pnpm test                              # vitest
```

## Data backfill (Stage 1)

```bash
cd backend
uv run alembic upgrade head        # create tables (TimescaleDB hypertable for candles)
uv run python -m app.ingestion.backfill --symbols BTCUSDT,ETHUSDT --intervals 1h
uv run python -m app.ingestion.backfill   # full watchlist, all intervals + funding/OI/LSR
uv run python -m app.ingestion.scheduler  # periodic top-ups (candles 15m, futures data 5m)
```

Backfill is idempotent: it diffs the expected candle grid against the DB and fetches only
missing ranges (this also repairs gaps). Historical depth per spec: 2y of 1h/4h/1d, 90d of
5m/15m, 30d of 1m. Note: tests require a running Postgres (`docker compose up -d db`);
a `cryptoquant_test` database is created automatically.

## Configuration

Copy `.env.example` to `.env`. Public Binance market data requires **no API key**.
Testnet keys (Stage 7) and read-only account keys (Stage 8) are optional; features
degrade gracefully when absent. `TRADING_MODE=testnet` is the only allowed value.
