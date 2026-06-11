"""Microstructure analytics (spec §4.3): order book imbalance + CVD.

Pure logic, driven by the WS worker which streams results over Redis.
"""

from collections import deque
from dataclasses import dataclass, field


def book_imbalance(
    bids: list[tuple[float, float]] | list[list[float]],
    asks: list[tuple[float, float]] | list[list[float]],
    levels: int,
) -> float | None:
    """(bid_vol − ask_vol) / (bid_vol + ask_vol) over the top `levels` levels.

    Bids must be sorted descending by price, asks ascending (as published).
    Returns None when the book side is empty.
    """
    bid_vol = sum(q for _, q in bids[:levels])
    ask_vol = sum(q for _, q in asks[:levels])
    total = bid_vol + ask_vol
    if total <= 0:
        return None
    return (bid_vol - ask_vol) / total


def spread_bps(best_bid: float | None, best_ask: float | None) -> float | None:
    if not best_bid or not best_ask or best_bid <= 0:
        return None
    mid = (best_bid + best_ask) / 2
    return (best_ask - best_bid) / mid * 10_000


@dataclass
class CvdWindow:
    """Cumulative volume delta over a rolling time window.

    Taker buys add quote volume, taker sells subtract (is_buyer_maker=True
    means the taker sold into the bid).
    """

    window_ms: int
    trades: deque[tuple[int, float]] = field(default_factory=deque)
    cvd: float = 0.0

    def add_trade(self, ts_ms: int, value: float, is_buyer_maker: bool) -> None:
        delta = -value if is_buyer_maker else value
        self.trades.append((ts_ms, delta))
        self.cvd += delta
        self._expire(ts_ms)

    def _expire(self, now_ms: int) -> None:
        cutoff = now_ms - self.window_ms
        while self.trades and self.trades[0][0] < cutoff:
            _, delta = self.trades.popleft()
            self.cvd -= delta

    def value(self, now_ms: int | None = None) -> float:
        if now_ms is not None:
            self._expire(now_ms)
        return self.cvd


@dataclass
class CvdTracker:
    """Per-symbol CVD over 1m and 5m rolling windows."""

    one_min: CvdWindow = field(default_factory=lambda: CvdWindow(60_000))
    five_min: CvdWindow = field(default_factory=lambda: CvdWindow(300_000))

    def add_trade(self, ts_ms: int, value: float, is_buyer_maker: bool) -> None:
        self.one_min.add_trade(ts_ms, value, is_buyer_maker)
        self.five_min.add_trade(ts_ms, value, is_buyer_maker)

    def snapshot(self, now_ms: int) -> dict[str, float]:
        return {"cvd_1m": self.one_min.value(now_ms), "cvd_5m": self.five_min.value(now_ms)}
