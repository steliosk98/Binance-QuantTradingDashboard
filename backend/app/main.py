from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.alerts import router as alerts_router
from app.api.analytics import router as analytics_router
from app.api.auth import enforce_production_auth, require_auth
from app.api.auth import router as auth_router
from app.api.backtests import router as backtests_router
from app.api.health import router as health_router
from app.api.market import router as market_router
from app.api.optimize import router as optimize_router
from app.api.paper import router as paper_router
from app.api.portfolio import router as portfolio_router
from app.api.settings import router as settings_router
from app.api.ws import router as ws_router
from app.core.config import get_settings
from app.core.logging import request_id_middleware, setup_json_logging, setup_sentry

settings = get_settings()
enforce_production_auth()

if settings.json_logs:
    setup_json_logging()
setup_sentry()

app = FastAPI(title=settings.app_name, version="2.0.0")

app.middleware("http")(request_id_middleware)

# CORS locked to the configured frontend origin(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public: health + login/status. Everything else requires a valid token
# whenever auth is configured (SECRET_KEY + APP_PASSWORD_HASH).
app.include_router(health_router)
app.include_router(auth_router)

protected = [Depends(require_auth)]
app.include_router(market_router, dependencies=protected)
app.include_router(ws_router)  # WS authenticates via ?token= inside the handler
app.include_router(analytics_router, dependencies=protected)
app.include_router(backtests_router, dependencies=protected)
app.include_router(paper_router, dependencies=protected)
app.include_router(settings_router, dependencies=protected)
app.include_router(portfolio_router, dependencies=protected)
app.include_router(alerts_router, dependencies=protected)
app.include_router(optimize_router, dependencies=protected)
