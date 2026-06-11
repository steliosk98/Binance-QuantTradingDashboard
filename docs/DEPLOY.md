# Deployment

Services to run: **backend API** (`backend/Dockerfile.prod`), **worker**
(same image, command `python -m app.ingestion.worker`), **paper runner**
(command `python -m app.paper.runner`), **frontend** (`frontend/Dockerfile.prod`),
plus managed **PostgreSQL with TimescaleDB** and **Redis**.

> Binance geo-blocks some cloud regions (HTTP 451). Use **EU regions**
> (Railway `europe-west4`, Fly `ams`/`fra`). If the API returns 451 after
> deploy, move regions.

## Required environment variables

| Variable | Service | Notes |
|---|---|---|
| `DATABASE_URL` | backend, worker, paper | `postgresql+asyncpg://...` |
| `REDIS_URL` | backend, worker, paper | `redis://...` |
| `SECRET_KEY` | backend | long random string; JWT + Fernet |
| `APP_PASSWORD_HASH` | backend | argon2 hash (see README) |
| `CORS_ORIGINS` | backend | frontend public origin |
| `JSON_LOGS` | all backend services | `true` in production |
| `BACKEND_URL` | frontend | internal URL of the backend service |
| `TRADING_MODE` | paper | must stay `testnet` |
| `BINANCE_TESTNET_API_KEY/SECRET` | paper | optional (sim fills without) |
| `SENTRY_DSN` | backend services | optional |

## Railway

1. `railway login` (or set `RAILWAY_TOKEN`), `railway init` in the repo.
2. Add plugins: PostgreSQL (enable the TimescaleDB image or use
   [Timescale Cloud](https://www.timescale.com/cloud)) and Redis.
3. Create four services from this repo:
   - **api** — Dockerfile `backend/Dockerfile.prod` (runs migrations on boot,
     `railway.json` already points here; healthcheck `/health`).
   - **worker** — same Dockerfile, start command `python -m app.ingestion.worker`.
   - **paper** — same Dockerfile, start command `python -m app.paper.runner`.
   - **web** — Dockerfile `frontend/Dockerfile.prod`, `BACKEND_URL` set to the
     api service's private URL.
4. Set the env vars above; region `europe-west4`.
5. Smoke-test: `curl https://<api-domain>/health` and
   `curl "https://<api-domain>/api/v1/candles?symbol=BTCUSDT" -H "Authorization: Bearer <token>"`.
6. Seed history: `railway run python -m app.ingestion.backfill`.

## Fly.io alternative

```bash
fly launch --no-deploy --dockerfile backend/Dockerfile.prod --name cryptoquant-api --region ams
fly postgres create --name cryptoquant-db --region ams   # attach, then install timescaledb
fly redis create --name cryptoquant-redis --region ams
fly secrets set SECRET_KEY=... APP_PASSWORD_HASH=... DATABASE_URL=... REDIS_URL=...
fly deploy
# worker + paper as separate apps with the same image:
#   fly launch ... --dockerfile backend/Dockerfile.prod; override process cmd in fly.toml
# frontend:
fly launch --dockerfile frontend/Dockerfile.prod --name cryptoquant-web --region ams
```

## Self-host (docker compose)

`docker compose up --build` runs the full stack (dev images). For production
self-hosting, swap the Dockerfiles for the `.prod` variants and set the env
vars above.
