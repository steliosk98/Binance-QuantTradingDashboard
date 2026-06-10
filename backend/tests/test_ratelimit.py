import pytest

from app.core.ratelimit import WeightLimiter


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


@pytest.mark.asyncio
async def test_acquire_under_threshold_does_not_sleep() -> None:
    clock = FakeClock()
    sleeps: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)

    limiter = WeightLimiter(100, backoff_ratio=0.8, clock=clock, sleeper=fake_sleep)
    await limiter.acquire(50)
    assert sleeps == []
    assert limiter.used_weight == 50


@pytest.mark.asyncio
async def test_acquire_over_threshold_sleeps_to_next_minute() -> None:
    clock = FakeClock(start=10.0)
    sleeps: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)
        clock.now += s  # advancing into the next window resets the counter

    limiter = WeightLimiter(100, backoff_ratio=0.8, clock=clock, sleeper=fake_sleep)
    await limiter.acquire(70)
    await limiter.acquire(20)  # 70+20 > 80 → wait 50s until next minute
    assert sleeps == [50.0]
    assert limiter.used_weight == 20


@pytest.mark.asyncio
async def test_server_header_overrides_local_count() -> None:
    limiter = WeightLimiter(6000)
    limiter.update_from_headers({"x-mbx-used-weight-1m": "1234"})
    assert limiter.used_weight == 1234
    # Server count never lowers local accounting
    limiter.update_from_headers({"X-MBX-USED-WEIGHT-1M": "5"})
    assert limiter.used_weight == 1234


@pytest.mark.asyncio
async def test_window_rollover_resets() -> None:
    clock = FakeClock(start=59.0)
    limiter = WeightLimiter(100, clock=clock)
    await limiter.acquire(60)
    clock.now = 61.0
    await limiter.acquire(60)  # would exceed in same window, but window rolled
    assert limiter.used_weight == 60
