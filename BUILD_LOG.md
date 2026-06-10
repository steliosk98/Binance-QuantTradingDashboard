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

### Known issues / blockers
- **HARD BLOCKER: no GitHub remote or credentials.** The run instructions contained a literal
  `<REPO_URL>` placeholder; `gh` was not installed (now installed but not authenticated); no SSH
  keys, no keychain credential, no `GITHUB_TOKEN`. Push / PR / GitHub CI verification cannot be
  completed. All other Stage 0 criteria verified locally. Work is committed on branch
  `stage-0-scaffolding` locally. Once the human provides `gh auth login` (or a token) and the repo
  URL, resume protocol: add remote, push, open PR, verify CI, merge, continue to Stage 1.
