import itertools
from datetime import date, timedelta

import pytest

from pulse import derived
from pulse.sync.planner import LOOKBACK_DAYS, chunks, sync_window

D = date(2026, 11, 21)


def test_sync_window_rolls_back_three_days():
    assert sync_window(D, D) == (D - timedelta(days=LOOKBACK_DAYS), D + timedelta(days=1))
    assert sync_window(None, D) == (D - timedelta(days=3), D + timedelta(days=1))


def test_sync_window_catches_up_after_downtime():
    start, end = sync_window(D - timedelta(days=10), D)
    assert start == D - timedelta(days=13) and end == D + timedelta(days=1)


def test_sync_window_ignores_future_high_water_mark():
    assert sync_window(D + timedelta(days=5), D)[0] == D - timedelta(days=3)


@pytest.mark.parametrize("newest_first", [False, True])
def test_chunks_cover_exactly(newest_first):
    start, end = date(2026, 1, 1), date(2026, 4, 15)
    parts = chunks(start, end, 14, newest_first=newest_first)
    assert all((hi - lo).days <= 14 for lo, hi in parts)
    ordered = sorted(parts)
    assert ordered[0][0] == start and ordered[-1][1] == end
    assert all(a[1] == b[0] for a, b in itertools.pairwise(ordered))
    if newest_first:
        assert parts[0][1] == end


def test_chunks_edge_cases():
    assert chunks(D, D, 5) == []
    assert chunks(D, D + timedelta(days=1), 90) == [(D, D + timedelta(days=1))]
    with pytest.raises(ValueError):
        chunks(D, D + timedelta(days=2), 0)


def test_baseline_quartiles_and_min_points():
    b = derived.baseline([1, 2, 3, 4, 5, 6, 7, 8, None])
    assert b is not None
    assert (b.median, b.q1, b.q3, b.n) == (4.5, 2.75, 6.25, 8)
    assert derived.baseline([1, 2, 3]) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (5, "in_range"),
        (2.75, "in_range"),
        (8, "mild"),
        (1, "mild"),
        (11, "notable"),
        (None, "none"),
    ],
)
def test_status(value, expected):
    b = derived.baseline([1, 2, 3, 4, 5, 6, 7, 8])
    # median 4.5, IQR 3.5 → notable beyond 4.5 ± 5.25
    assert derived.status(value, b) == expected


def test_status_without_baseline():
    assert derived.status(5, None) == "none"
    assert derived.delta(5, None) is None


def test_delta_and_curves():
    b = derived.baseline([10] * 7)
    assert derived.delta(12, b) == 2
    assert derived.status(10, b) == "in_range"
    assert derived.status(11, b) == "notable"  # zero IQR: any deviation is notable
    assert derived.cumulative([1, 2, 3]) == [1, 3, 6]
    assert derived.median_curve([[1, 2], [3, 4], [5, 100]]) == [3, 4]
    assert derived.median_curve([]) == []
    assert derived.stdev([60, 0, None]) == 30
    assert derived.stdev([5]) is None


def test_physical_rollup_chunks_stay_under_api_limits_across_dst():
    from zoneinfo import ZoneInfo

    from pulse.datatypes import CivilWindow
    from pulse.sync.streams import STREAMS_BY_NAME

    tz = ZoneInfo("America/Toronto")
    limits = {"hr_minute": 14, "steps_15m": 90}  # days, per the API (physical time)
    for name, limit in limits.items():
        stream = STREAMS_BY_NAME[name]
        # A chunk that ends just after the fall-back change gains an hour.
        for lo, hi in chunks(date(2026, 8, 1), date(2026, 11, 30), stream.chunk_days):
            s, e = CivilWindow(lo, hi, tz).utc_bounds()
            assert (e - s) < timedelta(days=limit), (name, lo, hi)
