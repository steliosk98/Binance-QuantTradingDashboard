"""Analytics REST endpoints (spec Stage 4), Redis-cached."""

import math
from typing import Annotated, Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import indicators as ind
from app.analytics import stats as st
from app.analytics.cache import cache_key, get_cached, set_cached
from app.analytics.data import load_candles_df, load_close_matrix
from app.api.deps import get_db
from app.core.config import get_settings
from app.core.redis import get_redis
from app.ingestion.binance_client import INTERVAL_MS

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _validate_interval(interval: str) -> None:
    if interval not in INTERVAL_MS:
        raise HTTPException(status_code=422, detail=f"unsupported interval {interval!r}")


def _series_payload(s: pd.Series) -> list[Any]:
    """Series → [[iso_time, value|null], ...] with NaN → null."""
    return [
        [
            pd.Timestamp(str(idx)).isoformat(),
            None if (v is None or (isinstance(v, float) and math.isnan(v))) else v,
        ]
        for idx, v in s.items()
    ]


def _last_candle_ms(df: pd.DataFrame) -> int:
    return int(df.index[-1].timestamp() * 1000) if not df.empty else 0


async def _df_or_404(db: AsyncSession, symbol: str, interval: str, limit: int) -> pd.DataFrame:
    df = await load_candles_df(db, symbol.upper(), interval, limit)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"no candles for {symbol} {interval}")
    return df


@router.get("/indicators")
async def get_indicators(
    db: DbSession,
    symbol: Annotated[str, Query(min_length=5, max_length=20)],
    interval: str = "1h",
    limit: Annotated[int, Query(ge=50, le=2000)] = 1000,
) -> dict[str, Any]:
    _validate_interval(interval)
    df = await _df_or_404(db, symbol, interval, limit)
    redis = get_redis()
    key = cache_key("indicators", symbol.upper(), interval, _last_candle_ms(df), {"limit": limit})
    cached = await get_cached(redis, key)
    if cached is not None:
        return dict(cached)

    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    macd_df = ind.macd(close)
    bb = ind.bollinger(close)
    stoch = ind.stochastic(high, low, close)
    cloud = ind.ichimoku_cloud(high, low)
    vp = ind.volume_profile(close, volume)

    payload = {
        "symbol": symbol.upper(),
        "interval": interval,
        "sma_20": _series_payload(ind.sma(close, 20)),
        "sma_50": _series_payload(ind.sma(close, 50)),
        "ema_20": _series_payload(ind.ema(close, 20)),
        "rsi_14": _series_payload(ind.rsi(close)),
        "macd": _series_payload(macd_df["macd"]),
        "macd_signal": _series_payload(macd_df["signal"]),
        "macd_histogram": _series_payload(macd_df["histogram"]),
        "bb_upper": _series_payload(bb["upper"]),
        "bb_middle": _series_payload(bb["middle"]),
        "bb_lower": _series_payload(bb["lower"]),
        "atr_14": _series_payload(ind.atr(high, low, close)),
        "vwap_session": _series_payload(ind.vwap_session(high, low, close, volume)),
        "obv": _series_payload(ind.obv(close, volume)),
        "stoch_k": _series_payload(stoch["k"]),
        "stoch_d": _series_payload(stoch["d"]),
        "ichimoku_senkou_a": _series_payload(cloud["senkou_a"]),
        "ichimoku_senkou_b": _series_payload(cloud["senkou_b"]),
        "volume_profile": {
            "price": vp["price"].tolist(),
            "volume": vp["volume"].tolist(),
        },
    }
    await set_cached(redis, key, payload)
    return payload


@router.get("/stats/returns")
async def get_returns_stats(
    db: DbSession,
    symbol: Annotated[str, Query(min_length=5, max_length=20)],
    interval: str = "1h",
    limit: Annotated[int, Query(ge=100, le=2000)] = 2000,
) -> dict[str, Any]:
    _validate_interval(interval)
    df = await _df_or_404(db, symbol, interval, limit)
    redis = get_redis()
    key = cache_key("returns", symbol.upper(), interval, _last_candle_ms(df), {"limit": limit})
    cached = await get_cached(redis, key)
    if cached is not None:
        return dict(cached)
    rets = st.log_returns(df["close"])
    payload = {
        "symbol": symbol.upper(),
        "interval": interval,
        **st.distribution_summary(rets),
    }
    await set_cached(redis, key, payload)
    return payload


@router.get("/stats/volatility")
async def get_volatility(
    db: DbSession,
    symbol: Annotated[str, Query(min_length=5, max_length=20)],
    interval: str = "1h",
    window: Annotated[int, Query(ge=10, le=500)] = 30,
    limit: Annotated[int, Query(ge=100, le=2000)] = 2000,
) -> dict[str, Any]:
    _validate_interval(interval)
    df = await _df_or_404(db, symbol, interval, limit)
    redis = get_redis()
    key = cache_key(
        "volatility",
        symbol.upper(),
        interval,
        _last_candle_ms(df),
        {"window": window, "limit": limit},
    )
    cached = await get_cached(redis, key)
    if cached is not None:
        return dict(cached)
    payload = {
        "symbol": symbol.upper(),
        "interval": interval,
        "window": window,
        "close_to_close": _series_payload(st.realized_vol_c2c(df["close"], window, interval)),
        "parkinson": _series_payload(
            st.realized_vol_parkinson(df["high"], df["low"], window, interval)
        ),
        "garman_klass": _series_payload(
            st.realized_vol_garman_klass(
                df["open"], df["high"], df["low"], df["close"], window, interval
            )
        ),
    }
    await set_cached(redis, key, payload)
    return payload


@router.get("/stats/hurst")
async def get_hurst(
    db: DbSession,
    symbol: Annotated[str, Query(min_length=5, max_length=20)],
    interval: str = "1h",
    window: Annotated[int, Query(ge=64, le=1024)] = 256,
    limit: Annotated[int, Query(ge=200, le=2000)] = 2000,
) -> dict[str, Any]:
    _validate_interval(interval)
    df = await _df_or_404(db, symbol, interval, limit)
    redis = get_redis()
    key = cache_key(
        "hurst", symbol.upper(), interval, _last_candle_ms(df), {"window": window, "limit": limit}
    )
    cached = await get_cached(redis, key)
    if cached is not None:
        return dict(cached)
    rets = st.log_returns(df["close"])
    series = st.rolling_hurst(rets, window=window)
    overall = st.hurst_rs(rets)
    payload = {
        "symbol": symbol.upper(),
        "interval": interval,
        "window": window,
        "hurst": None if math.isnan(overall) else overall,
        "rolling": _series_payload(series),
        "zscore": _series_payload(st.zscore(df["close"])),
    }
    await set_cached(redis, key, payload)
    return payload


@router.get("/stats/correlation")
async def get_correlation(
    db: DbSession,
    window: Annotated[int, Query(ge=10, le=365)] = 90,
) -> dict[str, Any]:
    symbols = get_settings().watchlist_symbols
    closes = await load_close_matrix(db, symbols, "1d", limit=window + 30)
    if closes.empty:
        raise HTTPException(status_code=404, detail="no daily candles available")
    redis = get_redis()
    last_ms = int(closes.index[-1].timestamp() * 1000)
    key = cache_key("correlation", "WATCHLIST", "1d", last_ms, {"window": window})
    cached = await get_cached(redis, key)
    if cached is not None:
        return dict(cached)
    rets = closes.apply(lambda col: st.log_returns(col))
    corr = st.correlation_matrix(rets, window)
    btc_beta: dict[str, float | None] = {}
    if "BTCUSDT" in rets.columns:
        for sym in rets.columns:
            beta_series = st.rolling_beta(rets[sym], rets["BTCUSDT"], window)
            last_beta = beta_series.dropna()
            btc_beta[sym] = float(last_beta.iloc[-1]) if not last_beta.empty else None
    payload = {
        "window_days": window,
        "symbols": corr.columns.tolist(),
        "matrix": [[None if math.isnan(v) else round(v, 4) for v in row] for row in corr.values],
        "btc_beta": btc_beta,
    }
    await set_cached(redis, key, payload)
    return payload


@router.get("/regime")
async def get_regime(
    db: DbSession,
    symbol: Annotated[str | None, Query(min_length=5, max_length=20)] = None,
    interval: str = "1h",
) -> dict[str, Any]:
    """Regime labels for one symbol or the whole watchlist."""
    from sqlalchemy import select

    from app.analytics.regime import classify_regime
    from app.models import FundingRate

    _validate_interval(interval)
    symbols = [symbol.upper()] if symbol else get_settings().watchlist_symbols
    redis = get_redis()
    out: dict[str, Any] = {}
    for sym in symbols:
        df = await load_candles_df(db, sym, interval, 1500)
        if df.empty:
            out[sym] = None
            continue
        key = cache_key("regime", sym, interval, _last_candle_ms(df), {})
        cached = await get_cached(redis, key)
        if cached is not None:
            out[sym] = cached
            continue
        result = await db.execute(
            select(FundingRate.funding_time, FundingRate.rate)
            .where(FundingRate.symbol == sym)
            .order_by(FundingRate.funding_time.desc())
            .limit(360)  # ~120 days of 8h funding
        )
        rows = result.all()
        funding = pd.Series([r[1] for r in reversed(rows)], dtype=float) if rows else None
        regime = classify_regime(df, funding, interval).to_dict()
        await set_cached(redis, key, regime)
        out[sym] = regime
    return {"interval": interval, "regimes": out}


@router.get("/funding-extremes")
async def get_funding_extremes(db: DbSession) -> dict[str, Any]:
    """Watchlist ranked by absolute annualized funding (most extreme first)."""
    from sqlalchemy import select

    from app.models import FundingRate

    entries: list[dict[str, Any]] = []
    for sym in get_settings().watchlist_symbols:
        result = await db.execute(
            select(FundingRate.rate, FundingRate.funding_time)
            .where(FundingRate.symbol == sym)
            .order_by(FundingRate.funding_time.desc())
            .limit(1)
        )
        row = result.first()
        if row is None:
            continue
        rate = float(row[0])
        entries.append(
            {
                "symbol": sym,
                "funding_rate": rate,
                "annualized_pct": rate * 3 * 365 * 100,  # 8h funding → 3/day
            }
        )
    entries.sort(key=lambda e: abs(e["funding_rate"]), reverse=True)
    return {"extremes": entries}


@router.get("/stats/pairs")
async def get_pairs(
    db: DbSession,
    symbol_a: Annotated[str, Query(min_length=5, max_length=20)],
    symbol_b: Annotated[str, Query(min_length=5, max_length=20)],
    interval: str = "1h",
    limit: Annotated[int, Query(ge=200, le=2000)] = 1000,
) -> dict[str, Any]:
    _validate_interval(interval)
    if symbol_a.upper() == symbol_b.upper():
        raise HTTPException(status_code=422, detail="pick two different symbols")
    df_a = await _df_or_404(db, symbol_a, interval, limit)
    df_b = await _df_or_404(db, symbol_b, interval, limit)
    redis = get_redis()
    last_ms = max(_last_candle_ms(df_a), _last_candle_ms(df_b))
    key = cache_key(
        "pairs", f"{symbol_a.upper()}-{symbol_b.upper()}", interval, last_ms, {"limit": limit}
    )
    cached = await get_cached(redis, key)
    if cached is not None:
        return dict(cached)
    result = st.engle_granger(df_a["close"], df_b["close"])
    spread_z = result.pop("spread_z")
    payload = {
        "symbol_a": symbol_a.upper(),
        "symbol_b": symbol_b.upper(),
        "interval": interval,
        **result,
        "cointegrated_5pct": result["pvalue"] < 0.05,
        "spread_z": _series_payload(spread_z),
    }
    await set_cached(redis, key, payload)
    return payload
