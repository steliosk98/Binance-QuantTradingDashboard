"""Gap detection over a candle time grid.

Pure functions so they are unit-testable without a database. Times are epoch
milliseconds aligned to the interval grid (as Binance returns them).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GapRange:
    """Inclusive [start_ms, end_ms] range of missing grid points."""

    start_ms: int
    end_ms: int

    def expected_count(self, interval_ms: int) -> int:
        return (self.end_ms - self.start_ms) // interval_ms + 1


def align_to_grid(ts_ms: int, interval_ms: int) -> int:
    return ts_ms - (ts_ms % interval_ms)


def find_gaps(
    existing_times_ms: list[int],
    interval_ms: int,
    range_start_ms: int,
    range_end_ms: int,
) -> list[GapRange]:
    """Return missing grid ranges within [range_start_ms, range_end_ms].

    ``existing_times_ms`` must be sorted ascending (or will be sorted here);
    times outside the requested range are ignored.
    """
    start = align_to_grid(range_start_ms, interval_ms)
    end = align_to_grid(range_end_ms, interval_ms)
    if end < start:
        return []

    have = sorted(t for t in existing_times_ms if start <= t <= end)
    gaps: list[GapRange] = []
    cursor = start
    for t in have:
        if t > cursor:
            gaps.append(GapRange(cursor, t - interval_ms))
        cursor = t + interval_ms
    if cursor <= end:
        gaps.append(GapRange(cursor, end))
    return gaps
