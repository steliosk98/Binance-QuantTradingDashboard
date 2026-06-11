"""Local order book maintained from Binance depth snapshot + diff stream.

Implements the documented spot sync algorithm:
1. Buffer depth diff events.
2. Fetch REST snapshot (lastUpdateId).
3. Drop events with final id u <= lastUpdateId.
4. First applied event must satisfy U <= lastUpdateId + 1 <= u.
5. Every later event must have U == previous u + 1, else the book has a
   sequence gap and must be resynced from a fresh snapshot (never patched).
"""

from dataclasses import dataclass, field
from typing import Any


class SequenceGap(Exception):
    """Raised when a depth diff does not chain onto the local book."""


@dataclass
class DepthDiff:
    first_update_id: int  # U
    final_update_id: int  # u
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]

    @classmethod
    def from_ws(cls, msg: dict[str, Any]) -> "DepthDiff":
        return cls(
            first_update_id=int(msg["U"]),
            final_update_id=int(msg["u"]),
            bids=[(float(p), float(q)) for p, q in msg.get("b", [])],
            asks=[(float(p), float(q)) for p, q in msg.get("a", [])],
        )


@dataclass
class OrderBook:
    symbol: str
    last_update_id: int = 0
    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)
    synced: bool = False

    def apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.last_update_id = int(snapshot["lastUpdateId"])
        self.bids = {float(p): float(q) for p, q in snapshot["bids"]}
        self.asks = {float(p): float(q) for p, q in snapshot["asks"]}
        self.synced = True

    def apply_diff(self, diff: DepthDiff) -> bool:
        """Apply a diff event. Returns False if the event is stale (skip).

        Raises SequenceGap when the event does not chain correctly.
        """
        if not self.synced:
            raise SequenceGap(f"{self.symbol}: book not synced")
        if diff.final_update_id <= self.last_update_id:
            return False  # stale event from before the snapshot
        if diff.first_update_id > self.last_update_id + 1:
            self.synced = False
            raise SequenceGap(
                f"{self.symbol}: gap — expected U <= {self.last_update_id + 1}, "
                f"got U={diff.first_update_id}"
            )
        for price, qty in diff.bids:
            if qty == 0:
                self.bids.pop(price, None)
            else:
                self.bids[price] = qty
        for price, qty in diff.asks:
            if qty == 0:
                self.asks.pop(price, None)
            else:
                self.asks[price] = qty
        self.last_update_id = diff.final_update_id
        return True

    def top_levels(self, n: int = 20) -> dict[str, Any]:
        bids = sorted(self.bids.items(), key=lambda x: -x[0])[:n]
        asks = sorted(self.asks.items(), key=lambda x: x[0])[:n]
        return {
            "symbol": self.symbol,
            "lastUpdateId": self.last_update_id,
            "bids": [[p, q] for p, q in bids],
            "asks": [[p, q] for p, q in asks],
        }

    def best_bid(self) -> float | None:
        return max(self.bids) if self.bids else None

    def best_ask(self) -> float | None:
        return min(self.asks) if self.asks else None
