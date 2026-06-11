# CryptoQuant Build Log

Agent memory across sessions. Append-only; one section per stage.

---

## Stage 0 — Repo, scaffolding, CI, Docker skeleton (2026-06-10)

### Built
- Monorepo layout per spec §2.2: `backend/` (FastAPI, uv, ruff, mypy strict, pytest) and
  `frontend/` (React 19 + TS + Vite + Tailwind v4, eslint, prettier, vitest).
- FastAPI app with `GET /health`, CORS middleware, pydantic-settings config (`app/core/config.py`).
- Frontend shell: dark theme, top nav (Dashboard · Chart · Research · Backtest · Paper Trading ·
  Portfolio · Settings) via react-router, footer disclaimer.
- `docker-compose.yml`: timescaledb (pg16), redis 7, backend, frontend, with healthchecks.
- GitHub Actions CI (`.github/workflows/ci.yml`): backend (ruff, ruff format, mypy, pytest),
  frontend (eslint, prettier check, tsc, vitest), gitleaks job.
- Pre-commit config with gitleaks + ruff. `.env.example`, `.gitignore` (`.env` ignored).

### Key decisions / deviations
- Spec says React 18; Vite scaffold ships React 19 — kept 19 (no downside for this app). Tailwind v4
  (CSS-first config via `@tailwindcss/vite`) instead of v3, same rationale.
- Environment tooling installed during this run: gh, uv, pnpm, gitleaks via Homebrew.

### Verification (acceptance criteria)
- `uv run ruff check .` → "All checks passed!"
- `uv run mypy` → "Success: no issues found in 6 source files"
- `uv run pytest -q` → 1 passed (health endpoint)
- `pnpm run lint && pnpm exec tsc -b && pnpm run test` → eslint clean, tsc clean, 1 test passed (nav renders)
- `docker compose up --build -d` → all 4 services healthy; `curl :8000/health` →
  `{"status":"ok","service":"cryptoquant-api"}`; `:8000/docs` → 200; `:5173` → 200 with
  `<title>CryptoQuant</title>`
- `gitleaks detect` → "no leaks found"
- CI green on GitHub → **BLOCKED**, see below.

### Unblocked (2026-06-10, later same day)
- Human ran `gh auth login` (account steliosk98). Created private repo
  `steliosk98/Binance-QuantTradingDashboard` via `gh repo create --source .`, pushed main +
  stage branch, opened PR #1. First CI run: gitleaks job failed with 403 (default GITHUB_TOKEN
  lacked PR read) → fixed by adding `permissions: contents: read, pull-requests: read` to the job.
  All checks green, merged PR #1, CI green on main (run 27299819653). **Stage 0 fully complete.**
- Note for later: GitHub warns actions/checkout@v4 + gitleaks-action@v2 run on deprecated Node 20
  (forced to Node 24 from 2026-06-16). Revisit action versions during Stage 9 hardening.

## Stage 1 — Binance REST client + historical backfill (2026-06-10)

### Built
- `app/core/ratelimit.py`: WeightLimiter — tracks `X-MBX-USED-WEIGHT-1M`, throttles at 80% of the
  per-minute weight limit, injectable clock/sleeper for tests.
- `app/ingestion/binance_client.py`: async httpx client for spot klines + futures
  funding/OI/long-short ratio; 429/418 honor Retry-After, 5xx + transport errors retried with
  exponential backoff; all REST centralized here per ground rule 6.
- SQLAlchemy models + Alembic migration `0001`: `candles` (TimescaleDB hypertable, 7-day chunks),
  `funding_rates`, `open_interest`, `long_short_ratio`.
- `app/ingestion/backfill.py` CLI: gap-detection-driven (diff expected grid vs DB, fetch only
  missing ranges) → idempotent + resumable + gap repair in one mechanism. Upserts via
  `ON CONFLICT DO UPDATE`.
- `app/ingestion/scheduler.py`: APScheduler top-ups (futures data 5m, candles 15m).
- CI: backend job now runs against a timescaledb service container.

### Key decisions / deviations
- **Bug found & fixed during acceptance:** Binance `fundingRate` and `/futures/data/*` endpoints
  return the LATEST `limit` rows when only `startTime` is sent. First implementation paginated
  forward by cursor and silently fetched only recent data. Rewrote to always send explicit
  [startTime, endTime] windows (`_fetch_windows`).
- `session_scope` initially wrapped `session.begin()`, which broke on mid-batch commits → now
  commits on success / rolls back on error.
- Used raw httpx instead of python-binance (spec allows): less magic, easier weight control.
- DB tests run against real TimescaleDB (compose locally, service container in CI); no skips.

### Verification (acceptance criteria)
- `uv run ruff check .` → pass; `uv run mypy` → "no issues in 21 source files";
  `uv run pytest -q` → **21 passed** (rate limiter, client incl. 429 retry, gap logic,
  DB idempotency + gap-repair + upsert-update).
- Backfill BTCUSDT+ETHUSDT 1h 2 years: `python -m app.ingestion.backfill --symbols BTCUSDT,ETHUSDT
  --intervals 1h --no-futures` → **17,520 rows each** (= 2×365×24 exactly, zero downtime gaps).
- Re-run → "complete, no gaps", 0 upserts, total count unchanged (35,040).
- Futures data BTCUSDT: funding 7,397 rows (2019-09→now), OI 8,640, LSR 8,640 (full 30-day
  retention at 5m = 288×30).
- Full watchlist backfill (all 10 symbols, all intervals) kicked off to populate dev DB.

## Stage 2 — Market data REST API + basic charting UI (2026-06-10)

### Built
- REST endpoints under `/api/v1`: `candles` (asc order, start/end windows, limit ≤1000),
  `symbols`, `funding`, `open-interest`, `ticker-summary` (last price, 24h %, vol, funding,
  OI Δ — computed from DB candles). All endpoints capped; FastAPI DI session per request.
- OpenAPI → TypeScript types via `openapi-typescript` (`src/api/schema.d.ts`) + thin typed
  fetch client; TanStack Query + zustand stores.
- Chart page: TradingView Lightweight Charts v5 (candles + volume histogram), symbol/interval
  switchers, 5s polling, loading/empty/error states.
- Dashboard: watchlist table polling ticker-summary every 5s; nulls render as "—".

### Key decisions / deviations
- lightweight-charts v5 API (`addSeries(CandlestickSeries, …)`) — spec assumed v4 style.
- Fixed `ORDER BY DISTINCT` SQLAlchemy bug found by contract test.
- Claude Preview/Chrome MCP unavailable in this environment → verified browser rendering with a
  one-off Playwright script (screenshots in `docs/screenshots/`). Playwright stays as a dev dep
  (needed for Stage 9 E2E anyway).

### Verification (acceptance criteria)
- Backend: ruff + mypy clean, **28 tests passed** (contract tests: pagination, validation 422s,
  empty ranges, ticker shape).
- Frontend: eslint + tsc clean, **6 tests passed** (chart data wiring, interval switch refetch,
  empty/error states, dashboard table).
- Browser (Playwright vs compose stack): chart page renders 7 canvases of real BTC 1h data from
  local DB; switching to ETHUSDT/1d re-renders; dashboard shows 10 watchlist rows with live-ish
  prices (BTC 61,882). Screenshots: `docs/screenshots/stage2-*.png`.
- Full watchlist backfill completed in background: 1m 302k, 5m 165k, 15m 51.8k, 1h 105k, 4h 26k,
  1d 4.4k candle rows + funding/OI/LSR for all 10 symbols.

## Stage 3 — WebSocket live layer (2026-06-11)

### Built
- `app/ingestion/worker.py`: WS ingestion process — spot combined stream (klines 6 intervals ×
  watchlist + aggTrades + per-symbol tickers), futures stream (!forceOrder + !markPrice), REST
  premium-index poller (5s), order book maintainers for BTCUSDT/ETHUSDT. New compose `worker`
  service.
- `app/ingestion/orderbook.py`: pure OrderBook implementing Binance's documented snapshot+diff
  sync; any sequence gap → full resync (never patched). `book_maintainer.py` wires it to WS +
  REST snapshot + Redis.
- `app/ingestion/ws_streams.py`: reconnecting consumer — exponential backoff (cap 60s), proactive
  23h reconnect, injectable for tests.
- `app/api/ws.py`: `/ws` hub — per-topic subscribe/unsubscribe over Redis pub/sub
  (`candles:SYM:IV`, `trades:SYM`, `book:SYM`, `tickers`, `marks`, `liqs`, `whales`), topic
  validation, 50-topic cap.
- Migration 0002: `liquidations` table; worker persists force orders.
- Frontend: `WsManager` (auto-reconnect + resubscribe), `useTopic`/`useWsStatus` hooks, nav WS
  status indicator, live chart (forming candle + sub-second trade ticks), depth panel with spread,
  live dashboard tickers, liquidation + whale feeds. Vite `/ws` proxy.

### Key decisions / deviations
- **Binance array streams (`!ticker@arr`, `!markPrice@arr`) deliver nothing inside combined-stream
  URLs** (verified by probe). Switched to per-symbol `@ticker` streams.
- **Futures WS (fstream.binance.com) is blocked on this network**: connects but never delivers
  (verified host + container; futures REST works fine). Mitigation per spec Known Risks: REST
  premium-index poller (5s) feeds the `marks` topic; futures WS consumer kept for deploy hosts
  where it works; liquidation feed degrades to empty with a waiting state. Re-verify after Stage 9
  deploy (EU region expected to work).
- Whale trades published to dedicated `whales` topic + recent list in Redis (threshold from
  `WHALE_THRESHOLD_USD`).
- Sub-second chart updates achieved by moving the forming candle's close/high/low on every
  aggTrade tick client-side (kline stream itself only pushes ~2s).

### Verification (acceptance criteria)
- ruff + mypy strict clean; backend **43 tests** (order book sync: stale/chained/overlap/gap/
  resync; reconnect with fake WS — exactly one reconnect; hub integration vs real Redis:
  subscribe/receive/unsubscribe/validation); frontend **11 tests** (WsManager reconnect +
  resubscribe + backoff + explicit close; chart/dashboard wiring).
- Live pipeline measured via `/ws`: book 121 msg/12s (10/s), tickers 101/12s, trades median gap
  1ms (sub-second ✓), candles ~2s + trade ticks, marks via REST poller.
- Network kill: 50s `docker network disconnect` → "Temporary failure in name resolution" →
  backoff → all 4 streams reconnected, both books resynced automatically ✓.
- Depth accuracy: local best bid/ask == Binance REST snapshot exactly (0.00 bps diff) ✓.
- Browser (Playwright): ws-status "live", depth panel populated (81 cells), feeds rendered,
  tickers flowing into the page (frame inspection). Screenshots: `docs/screenshots/stage3-*.png`.

## Stage 4 — Analytics engine: indicators + statistics (2026-06-11)

### Built
- `app/analytics/indicators.py` (§4.1): SMA/EMA, RSI + ATR on true Wilder RMA (SMA-seeded —
  matches TradingView), MACD, Bollinger, session+rolling VWAP, OBV, Stochastic, Ichimoku cloud,
  volume profile.
- `app/analytics/stats.py` (§4.2): log returns; annualized realized vol (close-to-close,
  Parkinson, Garman-Klass); distribution summary (hist, skew, kurtosis, Jarque-Bera, QQ);
  correlation matrix + rolling BTC beta; Hurst (R/S, rolling); z-score; ADF; Engle-Granger
  cointegration with hedge ratio + spread z.
- Redis caching keyed `(name, symbol, interval, last_candle_time, params-hash)` — new closed
  candle invalidates naturally. Endpoints: `/api/v1/analytics/indicators`, `/stats/returns`,
  `/stats/volatility`, `/stats/hurst` (incl. z-score), `/stats/correlation`, `/stats/pairs`.
- Frontend: indicator toggles on Chart (SMA/EMA/BB/VWAP overlays; RSI + MACD in separate
  lightweight-charts v5 panes); Research page (Distribution+QQ, 3-estimator vol, Hurst+z-score,
  Pairs cointegration) with Plotly; dashboard 90-day correlation heatmap.

### Key decisions / deviations
- **pandas-ta not used** (abandoned upstream, numpy-2 incompatible). Indicators implemented
  directly with pandas/numpy; golden tests reference Wilder's canonical RSI example and
  hand-computed fixtures instead of pandas-ta output. Spec allows closest working alternative.
- Initial ewm-based RSI failed the Wilder golden test (seeding differs) → implemented exact
  SMA-seeded Wilder recursion.
- `get_redis` now hands out one client per event loop (async Redis connections are loop-bound;
  pytest creates a loop per test).

### Verification (acceptance criteria)
- ruff + mypy strict clean. Backend **72 tests** green: indicator goldens (RSI Wilder example
  70.46/58.18 ✓), vol estimators agree on simulated GBM, Hurst ≈0.5 on white noise / >0.6 with
  drift, ADF stationary-vs-walk, Engle-Granger detects (and rejects) cointegration, hedge ratio
  ≈2.0 on synthetic pair, cache hit + invalidation-on-new-candle. Frontend **14 tests** green.
- RSI/MACD vs TradingView: formula-level equivalence (Wilder RMA = TV's ta.rsi; MACD = EMA12−EMA26
  with EMA9 signal) + golden tests; live values sane (RSI last 49.6–54.5 in range).
- Cached analytics latency: ~18 ms (p95 bar: <200 ms) ✓.
- Browser (Playwright): chart with SMA+BB overlays and RSI/MACD panes (15 canvases); Research all
  4 tabs functional incl. for SOLUSDT; pairs verdict rendered; heatmap renders.
  Screenshots: `docs/screenshots/stage4-*.png`.

### Known issues / blockers (resolved)
- **HARD BLOCKER: no GitHub remote or credentials.** The run instructions contained a literal
  `<REPO_URL>` placeholder; `gh` was not installed (now installed but not authenticated); no SSH
  keys, no keychain credential, no `GITHUB_TOKEN`. Push / PR / GitHub CI verification cannot be
  completed. All other Stage 0 criteria verified locally. Work is committed on branch
  `stage-0-scaffolding` locally. Once the human provides `gh auth login` (or a token) and the repo
  URL, resume protocol: add remote, push, open PR, verify CI, merge, continue to Stage 1.
