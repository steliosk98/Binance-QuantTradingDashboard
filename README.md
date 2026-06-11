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
- ✅ Stage 3 — WebSocket live layer
- ✅ Stage 4 — Analytics engine (indicators + statistics)
- ✅ Stage 5 — Microstructure + derivatives + regime widget
- ✅ Stage 6 — Backtesting engine + UI
- ✅ Stage 7 — Paper trading on Binance Testnet
- ✅ Stage 8 — Portfolio (read-only) + settings + auth
- ✅ Stage 9 — Hardening, E2E, deployment config

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│   FRONTEND  React 19 + Vite + TS · Lightweight Charts ·      │
│   Plotly · Tailwind · Zustand · TanStack Query               │
│   REST (JWT)  +  WebSocket /ws (per-topic subscriptions)     │
└──────────────▲──────────────────────────▲────────────────────┘
               │ HTTPS/REST               │ WSS
┌──────────────┴──────────────────────────┴────────────────────┐
│   API — FastAPI  (/api/v1/*, /ws relay hub, auth, JSON logs) │
└────▲──────────────▲───────────────▲──────────────▲───────────┘
     │              │               │              │
┌────┴─────┐ ┌──────┴─────┐ ┌───────┴────┐ ┌──────┴──────────┐
│INGESTION │ │ ANALYTICS  │ │ BACKTEST   │ │ PAPER TRADING   │
│worker:   │ │ indicators │ │ vectorized │ │ runner: signal→ │
│Binance WS│ │ stats,     │ │ engine, 6  │ │ order, Binance  │
│+ backfill│ │ regimes,   │ │ strategies,│ │ TESTNET only    │
│+ books   │ │ micro      │ │ walk-fwd   │ │ (or sim fills)  │
└────┬─────┘ └──────┬─────┘ └───────┬────┘ └──────┬──────────┘
     └──────────────┴───────┬───────┴─────────────┘
        ┌───────────────────▼───────────────────────┐
        │ PostgreSQL + TimescaleDB (hypertable,      │
        │ compression) · Redis (hot state, pub/sub)  │
        └────────────────────────────────────────────┘
```

## Stack

FastAPI + Python 3.12 (uv/ruff/mypy/pytest) · React 19 + TypeScript + Vite + Tailwind ·
PostgreSQL 16 + TimescaleDB · Redis 7 · Docker Compose · GitHub Actions · Playwright E2E.

## Quick start (self-host in ~10 minutes)

```bash
git clone https://github.com/steliosk98/Binance-QuantTradingDashboard.git
cd Binance-QuantTradingDashboard
docker compose up --build          # db, redis, api, ws worker, paper runner, frontend
# in another shell — load 2 years of history for the watchlist:
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.ingestion.backfill
```

- Frontend: http://localhost:5173 (dev password: `cryptoquant-dev`)
- API docs: http://localhost:8000/docs

Screenshots live in [docs/screenshots/](docs/screenshots/). Deployment (Railway / Fly.io):
[docs/DEPLOY.md](docs/DEPLOY.md).

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

## Paper trading (Stage 7)

Create strategy instances on the Paper Trading page (or via `POST /api/v1/paper/instances`).
A separate runner process (`python -m app.paper.runner`, compose service `paper`) evaluates
every running instance on each closed candle. Orders go to **Binance Spot Testnet** when
`BINANCE_TESTNET_API_KEY/SECRET` are set; otherwise fills are simulated internally so the
feature still works without credentials. Guards: max position, max daily loss (halts for the
day), and a kill switch that takes effect within one evaluation cycle. There is no live
trading mode anywhere in this codebase.

## Auth & portfolio (Stage 8)

Set `SECRET_KEY` and `APP_PASSWORD_HASH` (argon2 — generate with
`uv run python -c "from app.core.security import hash_password; print(hash_password('yourpw'))"`)
to enable single-user login; every API route and the WebSocket then require a JWT. The dev
compose stack ships with password `cryptoquant-dev`. Read-only Binance keys entered on the
Settings page are Fernet-encrypted at rest and never returned to the client; the Portfolio tab
appears only when keys are configured.

## Configuration

Copy `.env.example` to `.env`. Public Binance market data requires **no API key**.
Testnet keys (Stage 7) and read-only account keys (Stage 8) are optional; features
degrade gracefully when absent. `TRADING_MODE=testnet` is the only allowed value.

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | yes | `postgresql+asyncpg://...` (TimescaleDB) |
| `REDIS_URL` | yes | hot cache + pub/sub |
| `SECRET_KEY` | for auth | JWT signing + Fernet key derivation |
| `APP_PASSWORD_HASH` | for auth | argon2 hash of the single-user password |
| `CORS_ORIGINS` | prod | allowed frontend origin(s), comma-separated |
| `WATCHLIST` | no | default ten majors |
| `BINANCE_TESTNET_API_KEY/SECRET` | no | real testnet fills (else simulated) |
| `BINANCE_API_KEY/SECRET` | no | (enter via Settings page instead — stored encrypted) |
| `TRADING_MODE` | yes | must be `testnet` (no other mode exists) |
| `WHALE_THRESHOLD_USD` | no | whale feed threshold (default 250k) |
| `JSON_LOGS` | prod | structured JSON logs with request IDs |
| `SENTRY_DSN` | no | error reporting |
