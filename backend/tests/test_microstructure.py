import pytest

from app.analytics.microstructure import CvdTracker, CvdWindow, book_imbalance, spread_bps

BIDS = [(100.0, 5.0), (99.5, 3.0), (99.0, 2.0)]
ASKS = [(100.5, 1.0), (101.0, 1.0), (101.5, 8.0)]


def test_imbalance_basic() -> None:
    # top 2: bid 8 vs ask 2 → (8-2)/10 = 0.6
    assert book_imbalance(BIDS, ASKS, 2) == pytest.approx(0.6)


def test_imbalance_full_depth() -> None:
    # 10 vs 10 → 0
    assert book_imbalance(BIDS, ASKS, 3) == pytest.approx(0.0)


def test_imbalance_bounds() -> None:
    assert book_imbalance(BIDS, [], 5) == pytest.approx(1.0)
    assert book_imbalance([], ASKS, 5) == pytest.approx(-1.0)
    assert book_imbalance([], [], 5) is None


def test_spread_bps() -> None:
    # mid 100.25, spread 0.5 → ~49.88 bps
    assert spread_bps(100.0, 100.5) == pytest.approx(49.875, abs=0.01)
    assert spread_bps(None, 100.5) is None


def test_cvd_accumulates_signed_volume() -> None:
    w = CvdWindow(window_ms=60_000)
    w.add_trade(1_000, 100.0, is_buyer_maker=False)  # taker buy +100
    w.add_trade(2_000, 30.0, is_buyer_maker=True)  # taker sell −30
    w.add_trade(3_000, 50.0, is_buyer_maker=False)  # +50
    assert w.value(3_000) == pytest.approx(120.0)


def test_cvd_expires_old_trades() -> None:
    w = CvdWindow(window_ms=60_000)
    w.add_trade(0, 100.0, is_buyer_maker=False)
    w.add_trade(30_000, 50.0, is_buyer_maker=False)
    assert w.value(59_000) == pytest.approx(150.0)
    # t=70s: the t=0 trade falls out of the window
    assert w.value(70_000) == pytest.approx(50.0)
    # t=2min: everything expired
    assert w.value(120_000) == pytest.approx(0.0)


def test_cvd_tracker_windows_diverge() -> None:
    t = CvdTracker()
    t.add_trade(0, 100.0, is_buyer_maker=False)
    t.add_trade(90_000, 10.0, is_buyer_maker=True)
    snap = t.snapshot(90_000)
    assert snap["cvd_1m"] == pytest.approx(-10.0)  # only the recent sell
    assert snap["cvd_5m"] == pytest.approx(90.0)  # both trades
