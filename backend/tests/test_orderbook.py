import pytest

from app.ingestion.orderbook import DepthDiff, OrderBook, SequenceGap

SNAPSHOT = {
    "lastUpdateId": 100,
    "bids": [["100.0", "1.0"], ["99.5", "2.0"], ["99.0", "3.0"]],
    "asks": [["100.5", "1.5"], ["101.0", "2.5"], ["101.5", "3.5"]],
}


def synced_book() -> OrderBook:
    book = OrderBook("BTCUSDT")
    book.apply_snapshot(SNAPSHOT)
    return book


def diff(
    first: int,
    final: int,
    bids: list[tuple[float, float]] | None = None,
    asks: list[tuple[float, float]] | None = None,
) -> DepthDiff:
    return DepthDiff(first_update_id=first, final_update_id=final, bids=bids or [], asks=asks or [])


def test_snapshot_applied() -> None:
    book = synced_book()
    assert book.synced
    assert book.best_bid() == 100.0
    assert book.best_ask() == 100.5


def test_stale_diff_skipped() -> None:
    book = synced_book()
    assert book.apply_diff(diff(90, 100, bids=[(100.0, 9.9)])) is False
    assert book.bids[100.0] == 1.0  # unchanged


def test_diff_updates_and_removes_levels() -> None:
    book = synced_book()
    applied = book.apply_diff(
        diff(101, 105, bids=[(100.0, 5.0), (99.0, 0.0)], asks=[(100.5, 0.0), (102.0, 7.0)])
    )
    assert applied is True
    assert book.bids[100.0] == 5.0
    assert 99.0 not in book.bids
    assert book.best_ask() == 101.0
    assert book.asks[102.0] == 7.0
    assert book.last_update_id == 105


def test_chained_diffs() -> None:
    book = synced_book()
    book.apply_diff(diff(101, 105))
    book.apply_diff(diff(106, 110, bids=[(100.5, 1.0)]))
    assert book.best_bid() == 100.5
    assert book.last_update_id == 110


def test_overlapping_first_diff_ok() -> None:
    # First event after snapshot may straddle lastUpdateId: U <= id+1 <= u
    book = synced_book()
    assert book.apply_diff(diff(95, 103, bids=[(98.0, 4.0)])) is True
    assert book.last_update_id == 103


def test_gap_raises_and_marks_unsynced() -> None:
    book = synced_book()
    with pytest.raises(SequenceGap):
        book.apply_diff(diff(105, 110))  # gap: expected U <= 101
    assert not book.synced
    # Further applies refuse until resync
    with pytest.raises(SequenceGap):
        book.apply_diff(diff(111, 112))


def test_resync_after_gap() -> None:
    book = synced_book()
    with pytest.raises(SequenceGap):
        book.apply_diff(diff(200, 210))
    book.apply_snapshot({"lastUpdateId": 300, "bids": [["50.0", "1.0"]], "asks": [["51.0", "1.0"]]})
    assert book.synced
    assert book.apply_diff(diff(301, 305, asks=[(51.5, 2.0)])) is True


def test_top_levels_sorted_and_capped() -> None:
    book = synced_book()
    levels = book.top_levels(2)
    assert levels["bids"] == [[100.0, 1.0], [99.5, 2.0]]
    assert levels["asks"] == [[100.5, 1.5], [101.0, 2.5]]
