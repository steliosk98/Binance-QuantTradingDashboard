from app.ingestion.gaps import GapRange, align_to_grid, find_gaps

H = 3_600_000  # 1h in ms


def grid(start: int, count: int) -> list[int]:
    return [start + i * H for i in range(count)]


def test_align_to_grid() -> None:
    assert align_to_grid(H + 1234, H) == H
    assert align_to_grid(5 * H, H) == 5 * H


def test_no_gaps_when_complete() -> None:
    times = grid(0, 10)
    assert find_gaps(times, H, 0, 9 * H) == []


def test_everything_missing() -> None:
    assert find_gaps([], H, 0, 4 * H) == [GapRange(0, 4 * H)]


def test_hole_in_middle() -> None:
    times = grid(0, 3) + grid(6 * H, 4)  # missing 3h,4h,5h
    gaps = find_gaps(times, H, 0, 9 * H)
    assert gaps == [GapRange(3 * H, 5 * H)]


def test_missing_head_and_tail() -> None:
    times = grid(2 * H, 3)  # have 2h,3h,4h within range 0..7h
    gaps = find_gaps(times, H, 0, 7 * H)
    assert gaps == [GapRange(0, H), GapRange(5 * H, 7 * H)]


def test_times_outside_range_ignored() -> None:
    times = [100 * H, 200 * H]
    assert find_gaps(times, H, 0, 2 * H) == [GapRange(0, 2 * H)]


def test_unaligned_range_is_aligned() -> None:
    gaps = find_gaps([], H, H + 5, 3 * H + 5)
    assert gaps == [GapRange(H, 3 * H)]


def test_expected_count() -> None:
    assert GapRange(0, 4 * H).expected_count(H) == 5
