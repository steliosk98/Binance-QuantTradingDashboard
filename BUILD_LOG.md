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

## Stage 5 — Microstructure + derivatives + regime widget (2026-06-11)

### Built
- `app/analytics/microstructure.py`: order book imbalance (top 5/10/20), spread bps, rolling-window
  CVD (1m/5m, quote-volume signed by taker side). Book maintainer now publishes imbalance+spread in
  every `book:` message; worker streams throttled (1/s) `cvd:{symbol}` from aggTrades.
- `app/analytics/regime.py` (§4.5): trend via ADX(14, new Wilder implementation) + Hurst on
  returns; volatility percentile of current 30-bar realized vol vs history; funding extremity
  percentile. `GET /api/v1/analytics/regime` (single symbol or whole watchlist, cached) +
  `GET /analytics/funding-extremes` (ranked by |funding|) + `GET /api/v1/long-short`.
- Frontend: MicroPanel (imbalance 5/20 + CVD 1m/5m live sparklines + spread) on Chart; Futures
  panel (funding %, OI, L/S ratio Plotly charts + live basis from marks topic); dashboard Regime
  column (labels like "Trending · High Vol · Crowded Shorts") + Funding Extremes widget.

### Key decisions / deviations
- classify_trend is hierarchical: Hurst ≤0.45 → Mean-reverting; else ADX ≥25 **or** Hurst ≥0.55 →
  Trending (Hurst on returns is ~0.5 for steady drift trends, so requiring both was wrong —
  caught by the synthetic-regime test).
- Basis uses mark vs index from the `marks` topic (REST-poller-backed where futures WS blocked).

### Verification (acceptance criteria)
- Backend **85 tests** green (imbalance math incl. one-sided books; CVD accumulation/expiry/window
  divergence on synthetic trades; regime classifier on synthetic trending/mean-reverting/crowded-
  funding regimes). Frontend **19 tests** green (sparkline, regime labels, funding-extremes
  ordering). ruff/mypy/eslint/tsc clean.
- Live: regime endpoint returns labels for all 10 symbols (e.g. BTC "Trending/High Vol/Balanced",
  adx 23.4, hurst 0.61); funding-extremes sorted desc by |rate| ✓ (AVAX −13.4% ann. first).
- Live streams over /ws: 8 CVD updates + 100 imbalance updates in 10s, values moving ✓.
- Browser (Playwright): dashboard shows regime labels + correctly-ranked funding extremes; chart
  micro-panel draws 4 live sparklines; futures panel renders funding/OI/LSR charts.
  Screenshots: `docs/screenshots/stage5-*.png`.

## Stage 6 — Backtesting engine + UI (2026-06-11)

### Built
- `app/backtest/engine.py`: vectorized long/short engine — target positions decided on close,
  shifted one bar (no look-ahead); fee+slippage charged on |Δposition|; equity/drawdown/round-trip
  trade extraction; metrics: total/annualized return, Sharpe, Sortino, Calmar, max DD, win rate,
  profit factor, exposure, turnover, avg trade PnL.
- `app/backtest/strategies.py`: 6 strategies (§5.2) with declared param schemas + grid values:
  SMA crossover, RSI MR, Bollinger MR, Donchian breakout w/ trailing ATR stop, Z-score MR,
  Funding contrarian (joins funding series onto candles).
- `app/backtest/walkforward.py`: contiguous train/test windows, grid search on train (best
  Sharpe), stitched OOS equity, per-window IS-vs-OOS metrics (overfitting visible by design).
- API: `GET /strategies` (schemas for UI forms), `POST /api/v1/backtests` (202 + asyncio
  background task, compute in `asyncio.to_thread`), `GET /backtests[/{id}]`; migration 0003
`backtests` table (status/params/metrics/equity/trades/walkforward JSON).
- Backtest page: strategy picker → auto-generated param form → run → poll → metrics cards,
  equity curve with drawdown shading (dual axis), monthly returns heatmap, walk-forward IS/OOS
  table + stitched OOS curve, trade list, saved backtests with reload + up-to-3 comparison.

### Key decisions / deviations
- **vectorbt not used** — hand-rolled vectorized engine (spec's prescribed fallback); interface
  doesn't leak the choice.
- Equity curve stored inline as JSON (`equity_json`) rather than a separate ref — small payloads
  (≤20k bars), single-tenant.
- Async runs use in-process asyncio tasks (single-tenant; no Celery per spec §2.1).

### Verification (acceptance criteria)
- Backend **107 tests** green. Engine: buy-and-hold == price ratio net of costs; perfect
  foresight on sine wave → 4.9x equity; no-look-ahead jump test; short-side math; costs ==
  (1-c)^turnover on flat prices; trade extraction; hand-computed Sharpe/exposure/maxDD;
  determinism (identical runs byte-equal); WF window tiling + grid product + IS/OOS reporting.
  Frontend **22 tests** green (schema-driven form, run→poll→results, saved list).
- **SMA crossover BTCUSDT 1h × 2 years (17,521 bars, 390 trades): done in 0.76 s** (<10 s bar) ✓.
- Walk-forward (4 windows) renders IS vs OOS side by side (e.g. window 1: IS Sharpe 1.92 vs OOS
  0.49 — overfitting made visible) ✓.
- Browser (Playwright): full results page renders; saved backtests reload after page refresh;
  2-curve comparison chart works. Screenshot: `docs/screenshots/stage6-backtest-results.png`.

## Stage 7 — Paper trading on Binance Testnet (2026-06-11)

### Built
- `app/paper/executor.py`: SimExecutor (internal fills at ref ± slippage — "paper-paper" mode) and
  TestnetExecutor (HMAC-signed market orders on testnet.binance.vision, server-time sync against
  clock skew, long-only since spot, refuses to construct unless TRADING_MODE=testnet).
  `build_executor()` picks testnet iff keys are configured.
- `app/paper/engine.py`: per-instance evaluation on closed candles — strategy target → guarded
  order (max-position clamp, max-daily-loss halt with UTC day reset), position accounting with
  realized PnL across adds/reduces/flips, equity snapshot per evaluation. State persisted in
  `paper_instances.state_json` → restart-safe.
- `app/paper/runner.py` (compose service `paper`): psubscribes `candles:*`, evaluates all running
  instances per closed candle. Kill switch = DB status check on every cycle.
- Migration 0004: `paper_instances`, `paper_orders` (incl. `testnet_order_id`), `paper_equity`.
- Lifecycle API: list/create/get + `/stop` (kill switch) + `/start`. Paper Trading page: create
  form (schema-driven params + guards), instance table with live position/PnL/halted state, kill
  switch button, order log, paper equity curve.

### Key decisions / deviations
- **No testnet keys present** (no `.env.local`) → runs in spec-sanctioned simulated-fill mode;
  TestnetExecutor fully implemented and covered by mocked tests, activates automatically when
  `BINANCE_TESTNET_API_KEY/SECRET` appear.
- Testnet path is long-only (spot can't short); sim mode supports shorts.

### Verification (acceptance criteria)
- Backend **115 tests** green (sim fill slippage; guard clamp math; signal→order pipeline against
  real DB with spike fixture → SELL order + state + equity row; stopped instance skipped; daily
  loss halt; restart recovery — fresh session resumes identical state, no duplicate re-entry;
  testnet executor signature/header/fill-parse with respx). Frontend **26 tests** green.
- **Live acceptance: z-score instance on BTCUSDT 1m ran 04:23→05:26 UTC (63 one-minute
  evaluations, >1 hour)** with 4 real signal-driven orders (2 round trips: short 62,600→cover
  62,647; short 62,734→cover 62,724), equity tracked $997.6–$999.6, all visible in the UI ✓.
- **Kill switch: stopped via API at ~05:27; 5 subsequent 1m candles produced zero new
  evaluations** (equity frozen at 63 rows) — halts within one cycle ✓.
- Live restart recovery: `docker restart` of the paper container mid-run → resumed from DB state.
- Screenshot: `docs/screenshots/stage7-paper.png`.

## Stage 8 — Portfolio (read-only) + settings + auth (2026-06-11)

### Built
- `app/core/security.py`: Fernet (key derived from SECRET_KEY via SHA-256), argon2 password
  verify, HS256 JWT (24 h TTL).
- Auth: `POST /api/v1/auth/login` (+ `/status`); `require_auth` dependency on every router
  except health/auth; WebSocket authenticates via `?token=` inside the handler (closes 4401).
  Auth enforced iff SECRET_KEY + APP_PASSWORD_HASH are both set (explicit, never half-on).
  CORS restricted to configured origins. Compose dev password: `cryptoquant-dev`.
- Settings (migration 0005 `app_settings`): general settings (watchlist, fee/slippage, whale
  threshold) + API keys stored Fernet-encrypted, exposed only as `{configured: bool}`; DELETE
  supported. Settings page complete.
- Portfolio: signed read-only `GET /api/v3/account` (server-time sync), USD valuation via cached
  tickers, allocation pie + balances table; tab hidden unless keys configured.
- Frontend: login gate (LoginPage when auth enabled & no token), token in localStorage,
  Authorization header on all calls, 401 → token cleared → back to login; WS manager re-evaluates
  its URL per (re)connect so the token applies right after login (bug found by live Playwright
  check — status stayed "offline" after login with the constructor-captured URL).

### Key decisions / deviations
- No real read-only Binance keys available in this environment → "Portfolio renders balances"
  verified via mocked signed-client test + component test with fixture balances; the live checks
  cover the no-keys path (tab hidden) and the full auth flow.

### Verification (acceptance criteria)
- Backend **124 tests** green: Fernet round-trip; argon2 verify; JWT expiry raises; 401 on
  /symbols, /settings, /portfolio/status without token; login flow (wrong pw 401 → token works →
  garbage token 401); settings round-trip; **grep test: API key/secret never appear in any
  response body and stored ciphertext ≠ plaintext**; portfolio with mocked account (balances,
  USD valuation, zero-balance filtering); portfolio 404 without keys. Frontend **31 tests**.
- Live (compose with auth enabled): unauth /symbols → 401, /health → 200 (public), wrong pw →
  401, login → token (147 chars) → 200; portfolio status `{configured:false}`.
- Browser (Playwright): login gate shown; wrong password rejected with message; correct password
  → live dashboard; **Portfolio tab hidden without keys** ✓; Settings page renders general form +
  key status; WS reconnects authenticated → "live" after login ✓.
  Screenshots: `docs/screenshots/stage8-*.png`.

## Stage 9 — Hardening, E2E, deployment (2026-06-11)

### Built
- Structured JSON logging (`app/core/logging.py`): request-ID middleware (X-Request-ID echoed,
  contextvar-propagated into every log line), duration logging, `JSON_LOGS` env switch; optional
  Sentry init via `SENTRY_DSN`.
- Migration 0006: TimescaleDB compression on `candles` (segment by symbol+interval, compress
  after 30 days) + 90-day retention on `liquidations`; policies degrade gracefully on plain PG.
- Production Dockerfiles: backend multi-stage (uv → slim, non-root uid 10001, runs migrations on
  boot, PORT-aware) and frontend (build → nginx-unprivileged with /api + /ws proxy template).
- Playwright E2E (`frontend/e2e/app.spec.ts`): login (wrong + right password) → dashboard
  watchlist data → chart + RSI pane → run backtest → full results → saved-backtest reload.
  Hermetic: `scripts/seed_e2e.py` seeds deterministic synthetic candles (Binance 451-blocks some
  CI runners, so E2E never touches the network). New CI `e2e` job: compose up → migrate → seed →
  Playwright (chromium).
- `railway.json` + `docs/DEPLOY.md` (Railway primary, EU region per geo-block risk; Fly.io
  alternative; full env table; self-host notes). README finalized: architecture diagram, env
  table, quick start, screenshots.

### Verification (acceptance criteria)
- Backend 124 + frontend 31 unit/integration tests green; ruff/mypy/eslint/tsc clean.
- **E2E: 5/5 passed locally against the compose stack (17 s)**; same suite wired into CI.
- Prod images build cleanly (`Dockerfile.prod` × 2). JSON logging emits structured lines with
  request IDs (verified in container). Compression policy registered
  (timescaledb_information.jobs: policy_compression on candles) ✓.
- Local smoke of the "deployed" stack: /health 200, authed candles endpoint 200.

### Known issues / blockers
- **Cloud deploy not executed: no RAILWAY_TOKEN / Fly credentials in this environment**
  (no `.env.local`; run instructions allow degraded mode + documenting). Everything needed to
  deploy is in the repo (`railway.json`, prod Dockerfiles, `docs/DEPLOY.md` step-by-step). Once a
  Railway/Fly account token is provided: follow docs/DEPLOY.md §Railway (≈15 min), smoke-test
  `/health`, then record the URL here.

### Known issues / blockers (resolved)
- **HARD BLOCKER: no GitHub remote or credentials.** The run instructions contained a literal
  `<REPO_URL>` placeholder; `gh` was not installed (now installed but not authenticated); no SSH
  keys, no keychain credential, no `GITHUB_TOKEN`. Push / PR / GitHub CI verification cannot be
  completed. All other Stage 0 criteria verified locally. Work is committed on branch
  `stage-0-scaffolding` locally. Once the human provides `gh auth login` (or a token) and the repo
  URL, resume protocol: add remote, push, open PR, verify CI, merge, continue to Stage 1.
