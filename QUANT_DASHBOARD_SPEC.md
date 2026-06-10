# CryptoQuant Dashboard — Autonomous Build Specification

> **Audience:** This document is a complete handoff specification for an autonomous coding agent (Claude Code).
> **Mission:** Build, test, document, and deploy a production-grade crypto quant analytics & trading-research platform powered by the Binance API, in discrete stages. Each stage must be built, tested, committed, and pushed to GitHub before the next stage begins.

---

## 0. Ground Rules for the Agent (read first, re-read between stages)

1. **One stage at a time.** Do not start stage N+1 until stage N's acceptance criteria all pass and the work is pushed to GitHub on `main` (or merged via a stage branch — see Git workflow below).
2. **Test-first discipline.** Every stage ships with automated tests. CI must be green before a stage is considered done.
3. **No real-money trading. Ever.** This platform is read-only against Binance production market data. Any order-execution code targets **Binance Spot Testnet only** (`testnet.binance.vision`) and must be gated behind an explicit `TRADING_MODE=testnet` env var. There is no production trading mode in this spec — do not add one.
4. **Secrets hygiene.** No API keys in code, commits, logs, or error messages. `.env` for local dev, platform secrets for deployment. Add `.env` to `.gitignore` in Stage 0 and verify with a pre-commit hook (`detect-secrets` or `gitleaks`).
5. **Public market data needs no API key.** All of Stages 0–7 work without Binance credentials. Account-related features (Stage 8) require keys; degrade gracefully when absent (hide the portfolio tab, don't crash).
6. **Rate limits are law.** Binance REST: respect the `X-MBX-USED-WEIGHT-1M` response header; back off at 80% of the limit; honor HTTP 429/418 with exponential backoff. Centralize all REST calls in one client with a token-bucket limiter. Prefer WebSockets for anything live.
7. **Idempotent & resumable.** Every script (especially data backfills) must be safe to re-run. Use upserts, not inserts.
8. **Keep a build journal.** Maintain `BUILD_LOG.md` at repo root. After each stage append: date, what was built, key decisions, deviations from this spec and why, known issues. This is the agent's memory across sessions.
9. **If something in this spec is impossible or has changed** (e.g., a Binance endpoint was deprecated, a library is broken), document the deviation in `BUILD_LOG.md`, choose the closest working alternative, and continue. Do not stall.
10. **Definition of done (global):** code formatted + linted, type checks pass, tests pass locally and in CI, README updated, BUILD_LOG updated, pushed to GitHub, deployable.

---

## 1. Product Overview

**Name:** CryptoQuant (working title — feel free to rename, update everywhere consistently)

**What it is:** A self-hosted web platform that ingests Binance market data (spot + USD-M futures), stores it as queryable time series, computes technical / statistical / microstructure analytics, lets the user research and backtest strategies, paper-trades them on Binance Testnet, and presents everything in a real-time dashboard.

**What it is not:** A live-money execution engine, a custodial service, or financial advice. Display a disclaimer in the UI footer.

**Primary user:** A single technical user (the owner) running it for personal research. Single-tenant; simple auth is enough.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          FRONTEND (React + Vite + TS)           │
│  TradingView Lightweight Charts · Plotly · Tailwind · Zustand   │
│  REST (TanStack Query)  +  WebSocket (live updates)             │
└───────────────▲─────────────────────────────▲───────────────────┘
                │ HTTPS/REST                  │ WSS
┌───────────────┴─────────────────────────────┴───────────────────┐
│                     API GATEWAY — FastAPI                       │
│  /api/v1/* REST endpoints · /ws relay hub · auth middleware     │
└───────▲──────────────▲──────────────▲──────────────▲────────────┘
        │              │              │              │
┌───────┴──────┐ ┌─────┴──────┐ ┌─────┴──────┐ ┌─────┴──────────┐
│ INGESTION    │ │ ANALYTICS  │ │ BACKTEST   │ │ PAPER TRADING  │
│ WORKER       │ │ ENGINE     │ │ ENGINE     │ │ ENGINE         │
│ Binance WS + │ │ indicators │ │ vectorbt-  │ │ signal→order   │
│ REST backfill│ │ stats,     │ │ style,     │ │ on Binance     │
│              │ │ micro-     │ │ walk-fwd   │ │ TESTNET only   │
│              │ │ structure  │ │            │ │                │
└──────┬───────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────────┘
       │               │              │              │
┌──────▼───────────────▼──────────────▼──────────────▼───────────┐
│  STORAGE                                                        │
│  PostgreSQL + TimescaleDB (candles, trades, funding, OI,        │
│  liquidations, backtest results, paper orders)                  │
│  Redis (hot cache: latest ticks, order book state, pub/sub)     │
└─────────────────────────────────────────────────────────────────┘
```

### 2.1 Technology choices (binding unless broken)

| Layer | Choice | Rationale |
|---|---|---|
| Backend language | Python 3.12 | Quant ecosystem (pandas, numpy, vectorbt) |
| API framework | FastAPI + Uvicorn | Async, WebSocket support, OpenAPI for free |
| Binance client | `python-binance` (or raw `httpx`/`websockets` if it misbehaves) | Mature, covers spot + futures + testnet |
| Time-series DB | PostgreSQL 16 + TimescaleDB extension | Hypertables, continuous aggregates, compression |
| Cache / pub-sub | Redis 7 | Order book state, WS fan-out |
| Task scheduling | APScheduler inside the ingestion worker (avoid Celery complexity) | Single-tenant scale |
| Data wrangling | pandas + numpy; `pandas-ta` for indicators | Standard |
| Backtesting | `vectorbt` (fallback: hand-rolled vectorized engine if install issues) | Fast, pandas-native |
| Frontend | React 18 + TypeScript + Vite | Standard |
| Charts | TradingView Lightweight Charts (candles), Plotly.js (statistical plots), no D3 hand-rolling | Speed + polish |
| State | Zustand + TanStack Query | Simple |
| Styling | Tailwind CSS, dark theme default | Quant dashboards are dark |
| Containerization | Docker + docker-compose (db, redis, api, worker, frontend) | One-command local run |
| CI | GitHub Actions | Lint, typecheck, test on every push |
| Deployment | Railway (primary target) or Fly.io; docker-compose for self-host | Matches owner's prior research |
| Python tooling | `uv` for deps, `ruff` for lint+format, `mypy` for types, `pytest` | Modern, fast |
| JS tooling | `pnpm`, `eslint`, `prettier`, `vitest`, `playwright` (E2E, Stage 9) | Standard |

### 2.2 Repository layout (monorepo)

```
cryptoquant/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers (market, analytics, backtest, portfolio, ws)
│   │   ├── core/           # config, logging, rate limiter, security
│   │   ├── ingestion/      # binance REST backfill + WS consumers
│   │   ├── analytics/      # indicators, stats, microstructure, regimes
│   │   ├── backtest/       # engine, strategies, metrics
│   │   ├── paper/          # testnet execution engine
│   │   ├── models/         # SQLAlchemy models + Pydantic schemas
│   │   └── db/             # session, migrations (alembic)
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/     # charts, widgets, layout
│   │   ├── pages/          # Dashboard, Chart, Research, Backtest, Portfolio
│   │   ├── stores/         # zustand
│   │   ├── api/            # typed client (generate from OpenAPI)
│   │   └── ws/             # websocket manager
│   └── package.json
├── docker-compose.yml
├── .github/workflows/ci.yml
├── BUILD_LOG.md
├── README.md
└── docs/                   # per-stage notes, API docs, screenshots
```

---

## 3. Data Specification

### 3.1 Sources (Binance)

| Data | Endpoint / Stream | Cadence |
|---|---|---|
| Klines (OHLCV) | REST `GET /api/v3/klines` (backfill); WS `<symbol>@kline_<interval>` (live) | 1m, 5m, 15m, 1h, 4h, 1d |
| Trades | WS `<symbol>@aggTrade` | real-time |
| Order book | REST depth snapshot + WS `<symbol>@depth@100ms` diffs (maintain local book per Binance's documented sync algorithm) | real-time |
| 24h tickers | WS `!ticker@arr` | 1s |
| Funding rate | Futures REST `GET /fapi/v1/fundingRate` + premium index stream | 8h + live |
| Open interest | Futures REST `GET /futures/data/openInterestHist` | 5m |
| Long/short ratio | Futures REST `GET /futures/data/globalLongShortAccountRatio` | 5m |
| Liquidations | Futures WS `!forceOrder@arr` | real-time |
| Account (optional) | Signed REST: balances, orders, trades | on demand |

**Default symbol universe:** BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, ADAUSDT, DOGEUSDT, AVAXUSDT, LINKUSDT, DOTUSDT — configurable via `WATCHLIST` env var / settings table.

**Historical depth:** backfill 2 years of 1h+1d candles, 90 days of 5m/15m, 30 days of 1m, for the watchlist. Funding/OI: max available.

### 3.2 Core schema (TimescaleDB hypertables)

- `candles(symbol, interval, open_time PK, open, high, low, close, volume, quote_volume, trades, taker_buy_volume)` — hypertable on `open_time`, compressed after 30 days.
- `agg_trades(symbol, trade_time, price, qty, is_buyer_maker)` — hypertable, 14-day retention policy.
- `funding_rates(symbol, funding_time, rate)`
- `open_interest(symbol, ts, oi, oi_value)`
- `long_short_ratio(symbol, ts, ratio, long_pct, short_pct)`
- `liquidations(symbol, ts, side, price, qty, value_usdt)`
- `backtests(id, created_at, strategy, params_json, symbol, interval, start, end, metrics_json, equity_curve_ref)`
- `paper_orders(id, ts, symbol, side, type, qty, price, status, strategy, testnet_order_id)`
- `app_settings(key, value_json)`

Use continuous aggregates to derive higher-timeframe candles from 1m where convenient.

---

## 4. Analytics Specification

### 4.1 Technical indicators (per symbol/interval, computed on demand, cached in Redis)
SMA/EMA (configurable periods), RSI(14), MACD(12,26,9), Bollinger(20,2), ATR(14), VWAP (session + rolling), OBV, Stochastic, Ichimoku (cloud only), volume profile (price-bucketed volume histogram over visible range).

### 4.2 Statistical / quant metrics
- Returns: log returns per interval; rolling annualized realized volatility (close-to-close, Parkinson, Garman-Klass).
- Distribution: histogram, skew, kurtosis, Jarque-Bera p-value, QQ data vs normal.
- Correlation matrix across watchlist (rolling 30/90-day, on daily log returns) + rolling BTC beta per coin.
- Hurst exponent (R/S method, rolling) → regime hint (trending >0.55, mean-reverting <0.45).
- Z-score of price vs rolling mean (mean-reversion signal input).
- Stationarity: ADF test on spreads (for pairs analysis).
- Pairs analysis: Engle-Granger cointegration test on user-selected pair, spread z-score chart.

### 4.3 Microstructure (live, from WS)
- Order book imbalance: (bid_vol − ask_vol)/(bid_vol + ask_vol) at top N levels (N=5,10,20), rolling sparkline.
- Spread (bps) tracking.
- Trade flow: taker buy vs sell volume ratio per rolling 1m/5m window (CVD — cumulative volume delta).
- Whale feed: aggTrades above configurable USD threshold (default $250k BTC/ETH, $100k others).
- Liquidation feed + rolling liquidation totals per side.

### 4.4 Derivatives analytics
- Funding rate: current + history chart + annualized equivalent; basis (perp vs spot) chart.
- Open interest chart overlaid with price; OI delta alerts.
- Long/short ratio chart.

### 4.5 Regime widget
Composite dashboard widget per symbol: trend state (ADX + Hurst), volatility percentile (current realized vol vs 1y distribution), funding extremity percentile. Output: simple labels (e.g., "Trending / High Vol / Crowded Longs").

---

## 5. Backtesting & Paper Trading Specification

### 5.1 Backtest engine
- Vectorized, candle-based, long/short, single-asset (multi-asset portfolio = stretch goal Stage 7).
- Costs: taker fee (default 10 bps, configurable), slippage model (fixed bps, default 5).
- Outputs: equity curve, drawdown series, trade list, metrics: total/annualized return, Sharpe, Sortino, Calmar, max DD, win rate, profit factor, exposure, turnover, avg trade PnL.
- Walk-forward mode: split data into N rolling train/test windows; optimize params on train (grid search over declared param ranges), report out-of-sample stitched equity curve. Make overfitting visible: always show in-sample vs out-of-sample metrics side by side.

### 5.2 Built-in strategies (each a class with declared param schema so the UI can auto-render forms)
1. **SMA/EMA crossover** (fast, slow)
2. **RSI mean reversion** (entry/exit thresholds, holding limit)
3. **Bollinger mean reversion** (band entry, mid-band exit)
4. **Donchian breakout / momentum** (lookback, ATR stop)
5. **Z-score mean reversion** (lookback, entry z, exit z)
6. **Funding-rate contrarian** (enter against extreme funding percentiles) — daily, futures data
7. **Pairs trading** (cointegrated pair, spread z entry/exit) — stretch goal

### 5.3 Paper trading (Binance Spot Testnet ONLY)
- A runner that subscribes to live candles, evaluates one or more strategy instances, and places market/limit orders on `testnet.binance.vision` using testnet keys.
- Persist every signal and order; show live paper PnL, positions, and an equity curve in the UI.
- Kill switch in UI + max-position and max-daily-loss guards in code.
- If testnet keys are absent: simulate fills internally (paper-paper mode) so the feature still demos.

---

## 6. Frontend Specification

**Global:** dark theme, responsive (desktop-first), top nav: Dashboard · Chart · Research · Backtest · Paper Trading · Portfolio · Settings. WebSocket connection status indicator. Footer disclaimer: "Research tool. Not financial advice. No live trading."

### Pages
1. **Dashboard (home):** watchlist table (price, 24h %, vol, funding, OI Δ, regime label, sparkline); market-wide widgets: BTC dominance proxy (BTC vs watchlist returns), correlation heatmap (Plotly), liquidation feed, whale feed, top funding extremes.
2. **Chart:** full-screen TradingView Lightweight Charts candlestick + volume; symbol/interval switchers; indicator toggles (overlays + sub-panes for RSI/MACD); order book depth chart side panel; live order book imbalance + CVD sparklines; funding/OI sub-chart for futures symbols.
3. **Research:** per-symbol statistical workbench — returns distribution histogram + QQ plot, rolling volatility chart (3 estimators), Hurst chart, z-score chart; pairs tab: pick two symbols → cointegration test result + spread z-score chart.
4. **Backtest:** strategy picker → auto-generated param form → run → results: equity curve with drawdown shading, metrics cards, trade list table, monthly returns heatmap; walk-forward toggle; saved backtests list (compare up to 3 equity curves).
5. **Paper Trading:** strategy instances (create/start/stop), live positions, order log, paper equity curve, kill switch.
6. **Portfolio (only if real read-only API keys provided):** balances, allocation pie, PnL history. Read-only; never request trade permissions on real keys.
7. **Settings:** watchlist editor, fee/slippage defaults, whale thresholds, API key entry (stored encrypted at rest with a server-side key; never returned to the client after save).

---

## 7. Staged Build Plan

> For every stage: create branch `stage-N-<slug>` → build → test → update README + BUILD_LOG → open PR → merge to `main` → push → verify CI green → proceed.

### Stage 0 — Repo, scaffolding, CI, Docker skeleton
**Build:** Monorepo per layout above; FastAPI "hello" app with `/health`; React+Vite+Tailwind shell with nav and dark theme; docker-compose with postgres(+timescale image), redis, backend, frontend; GitHub Actions CI (ruff, mypy, pytest, eslint, tsc, vitest); pre-commit with gitleaks; `.env.example`.
**Tests:** health endpoint test; frontend renders nav (vitest); CI passes.
**Accept:** `docker compose up` serves frontend at :5173 and API docs at :8000/docs; CI green on GitHub.

### Stage 1 — Binance REST client + historical backfill
**Build:** Rate-limited async Binance REST client (weight-header aware, retries/backoff); Alembic migrations for `candles`, `funding_rates`, `open_interest`, `long_short_ratio`; idempotent backfill CLI (`python -m app.ingestion.backfill --symbols ... --intervals ...`) with progress logging and gap detection/repair; APScheduler job for periodic top-ups of funding/OI/LSR.
**Tests:** client unit tests with mocked HTTP (incl. 429 handling); backfill upsert idempotency test against a dockerized test DB; gap-repair test.
**Accept:** Backfill of BTCUSDT+ETHUSDT 1h for 2 years completes; row counts match expected candle counts ±exchange downtime; re-running changes nothing.

### Stage 2 — Market data REST API + basic charting UI
**Build:** Endpoints: `GET /api/v1/candles`, `/symbols`, `/funding`, `/open-interest`, `/ticker-summary`; OpenAPI-generated TS client; Chart page with Lightweight Charts candles+volume, symbol & interval switchers pulling from API; Dashboard watchlist table (REST polling for now, 5s).
**Tests:** API contract tests (pagination, validation, empty ranges); component test for chart page data wiring.
**Accept:** Browser shows real BTC candles from local DB; switching symbol/interval works; lighthouse-fast initial load.

### Stage 3 — WebSocket live layer
**Build:** Ingestion worker consuming Binance WS (klines for watchlist, aggTrades, !ticker@arr, futures !forceOrder, premium index); writes live candles to DB (closed candles) and Redis (forming candle, latest tick); local order book maintainer for the selected symbol (snapshot+diff sync per Binance docs) kept in Redis; FastAPI `/ws` hub fanning out via Redis pub/sub with per-topic subscriptions (`candles:BTCUSDT:1m`, `book:BTCUSDT`, `liqs`, `tickers`); frontend WS manager with auto-reconnect; Chart page goes live (forming candle updates); Dashboard table goes live; depth chart panel; liquidation + whale feeds.
**Tests:** order book sync unit tests (apply diffs to snapshot fixture, detect sequence gaps → resync); WS hub integration test (publish fake tick → client receives); reconnect logic test.
**Accept:** Candle on Chart page updates sub-second; killing the worker's network (simulated) recovers automatically; depth chart mirrors Binance UI within visual tolerance.

### Stage 4 — Analytics engine (indicators + statistics)
**Build:** Analytics module per §4.1–4.2 with Redis caching keyed by (symbol, interval, last_candle_time); endpoints `GET /api/v1/analytics/indicators`, `/stats/returns`, `/stats/volatility`, `/stats/hurst`, `/stats/correlation`, `/stats/pairs`; Chart page indicator toggles (overlays + RSI/MACD panes); Research page (distribution, QQ, vol estimators, Hurst, z-score, pairs cointegration); Dashboard correlation heatmap.
**Tests:** golden-value tests for each indicator vs known fixtures (compare to pandas-ta reference); statistical functions tested against scipy/statsmodels on synthetic series (e.g., Hurst ≈0.5 on white noise, >0.6 on trending random walk with drift); cache invalidation test.
**Accept:** RSI/MACD visually match TradingView for same data window; Research page fully functional for any watchlist symbol.

### Stage 5 — Microstructure + derivatives analytics + regime widget
**Build:** CVD and order book imbalance computed in the worker, streamed over WS; whale threshold settings; funding/OI/LSR charts on Chart page sub-pane; regime classifier per §4.5 with `GET /api/v1/analytics/regime` and dashboard labels; basis chart (perp mark vs spot).
**Tests:** imbalance math unit tests; CVD accumulation test from synthetic trade stream; regime classifier tests on synthetic regimes.
**Accept:** Dashboard shows live regime labels; CVD and imbalance sparklines move with the market; funding extremes widget ranks correctly.

### Stage 6 — Backtesting engine + UI
**Build:** Engine per §5.1, strategies 1–6 per §5.2 with param schemas; endpoints: `POST /api/v1/backtests` (async run, poll status), `GET /api/v1/backtests/{id}`; persistence of results; Backtest page per §6.4 incl. monthly returns heatmap and comparison view; walk-forward mode.
**Tests:** engine correctness on synthetic data (e.g., perfect-foresight strategy on a sine wave yields expected trades; buy-and-hold equity matches price ratio net of fees); metric formulas vs hand-computed fixtures; walk-forward window splitting tests; determinism test (same seed/params → identical results).
**Accept:** SMA crossover on BTCUSDT 1h, 2 years, runs in <10 s and renders full results; walk-forward shows IS vs OOS comparison; saved backtests reload correctly.

### Stage 7 — Paper trading on Binance Testnet
**Build:** Paper engine per §5.3 (testnet order placement + internal-sim fallback); strategy instance lifecycle API + UI; guards (max position, daily loss, kill switch); paper equity curve from fills.
**Tests:** signal→order pipeline with mocked testnet API; guard trigger tests; sim-fill engine tests; restart recovery test (instances resume state from DB).
**Accept:** A z-score strategy instance runs live against 1m candles for ≥1 hour, logging signals/orders visible in UI; kill switch halts within one evaluation cycle.

### Stage 8 — Account portfolio (read-only) + settings + auth
**Build:** Encrypted API-key storage (Fernet with `SECRET_KEY` from env); read-only portfolio endpoints + Portfolio page; Settings page complete; simple auth: single-user password login (argon2 hash from env) issuing JWT; all API routes protected; CORS locked to frontend origin.
**Tests:** crypto round-trip test; auth flow tests (401s, token expiry); portfolio endpoints with mocked signed client; verify keys never appear in any response or log (grep-based test).
**Accept:** With read-only keys set, Portfolio renders balances; without keys, tab hidden; unauthenticated requests rejected.

### Stage 9 — Hardening, E2E, deployment
**Build:** Playwright E2E suite (login → dashboard live data → chart with indicator → run backtest → view results); structured JSON logging + request IDs; Sentry hooks (optional via env); DB compression + retention policies applied; production Dockerfiles (multi-stage, non-root); Railway deployment config (`railway.json` / Procfile equivalents) **and** documented Fly.io alternative; deploy; smoke-test the deployed URL; finalize README (architecture diagram, screenshots into `docs/`, setup, deployment, env var table); tag `v1.0.0` release on GitHub.
**Tests:** full E2E green in CI (against compose stack); deployed `/health` and one data endpoint verified.
**Accept:** Public (or password-protected) deployed URL serving live data; `v1.0.0` tagged; README sufficient for a stranger to self-host with docker-compose in <15 minutes.

### Stage 10 (stretch — only if all above is done)
Alerting (Telegram bot for whale/liquidation/funding/regime-change alerts), pairs-trading strategy + multi-asset portfolio backtests, strategy param optimization dashboard (heatmap of Sharpe over param grid), CSV/Parquet export endpoints.

---

## 8. Environment Variables (maintain in `.env.example`)

```
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
SECRET_KEY=                # JWT signing + Fernet derivation
APP_PASSWORD_HASH=         # argon2 hash for single-user login
WATCHLIST=BTCUSDT,ETHUSDT,...
BINANCE_API_KEY=           # optional, read-only, Stage 8
BINANCE_API_SECRET=        # optional
BINANCE_TESTNET_API_KEY=   # optional, Stage 7
BINANCE_TESTNET_API_SECRET=# optional
TRADING_MODE=testnet       # the only allowed value
WHALE_THRESHOLD_USD=250000
SENTRY_DSN=                # optional
```

## 9. Quality Bars

- Backend: ruff clean, mypy strict on `app/` (allow targeted ignores), pytest coverage ≥80% on `analytics/` and `backtest/` modules specifically.
- Frontend: tsc strict, eslint clean.
- p95 REST latency < 200 ms for cached analytics; WS fan-out latency < 250 ms tick-to-browser locally.
- No endpoint returns unbounded result sets — paginate or cap everything.
- Every chart has loading + empty + error states.

## 10. Known Risks & Prescribed Mitigations

- **Binance geo-restrictions on deployment hosts:** some cloud regions are blocked by Binance. If the deployed API gets 451 responses, switch Railway/Fly region (EU regions generally work) and document in BUILD_LOG.
- **`vectorbt` install friction:** if it fails on the target Python, pin a compatible version or fall back to the hand-rolled vectorized engine (the engine interface in §5.1 must not leak the library choice).
- **WS disconnects / 24h connection limit:** Binance drops WS connections every 24h — implement proactive reconnect before the limit and treat reconnect as a normal event, not an error.
- **Order book drift:** any sequence gap → full resync from snapshot. Never patch over gaps.
- **Clock skew on signed requests:** sync with Binance server time endpoint before signing.

---

*End of specification. Begin with Stage 0.*
