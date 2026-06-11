"""Seed deterministic synthetic candles for hermetic E2E runs.

Binance geo-blocks some CI runners (HTTP 451), so E2E never touches the
network: python -m scripts.seed_e2e
"""

import asyncio
import time

import numpy as np

from app.db.session import session_scope
from app.ingestion.binance_client import INTERVAL_MS, Kline
from app.ingestion.upserts import upsert_candles

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
BASE_PRICE = {"BTCUSDT": 60_000.0, "ETHUSDT": 1_600.0}
COUNT = 800


def synth(symbol: str, interval: str, count: int = COUNT) -> list[Kline]:
    step = INTERVAL_MS[interval]
    now = int(time.time() * 1000)
    start = (now - count * step) // step * step
    rng = np.random.default_rng(abs(hash((symbol, interval))) % 2**32)
    closes = BASE_PRICE[symbol] * np.exp(np.cumsum(rng.normal(0.0001, 0.005, count)))
    klines = []
    for i in range(count):
        c = float(closes[i])
        o = float(closes[i - 1]) if i else c
        klines.append(
            Kline(
                open_time=start + i * step,
                open=o,
                high=max(o, c) * 1.002,
                low=min(o, c) * 0.998,
                close=c,
                volume=10.0 + float(rng.uniform(0, 5)),
                close_time=start + (i + 1) * step - 1,
                quote_volume=c * 12,
                trades=100,
                taker_buy_volume=6.0,
            )
        )
    return klines


async def main() -> None:
    async with session_scope() as session:
        for symbol in SYMBOLS:
            for interval in ("1m", "1h", "1d"):
                n = await upsert_candles(session, symbol, interval, synth(symbol, interval))
                print(f"seeded {symbol} {interval}: {n}")


if __name__ == "__main__":
    asyncio.run(main())
