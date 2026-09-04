"""``CandleSeries.step_to_ts`` moves ``cursor`` forward only.

Each test builds ``rows`` through ``build_candle_series_from_rows`` and reads
``cursor``, ``get_current`` and ``get_history`` around a target timestamp that
sits behind the row the cursor already reached.
"""

from src.simulator.fleet.candle_series import build_candle_series_from_rows


def _series(timestamps):
    rows = [
        [ts, 100.0, 110.0, 90.0, 100.0 + i, 10.0] for i, ts in enumerate(timestamps)
    ]
    return build_candle_series_from_rows("X/USD", rows)


def test_step_to_ts_advances_the_cursor_and_reports_true():
    s = _series([100, 200, 300])

    moved = s.step_to_ts(300)

    assert moved is True, "a forward target must report the advance"
    assert s.cursor == 2, f"cursor should reach index 2, got {s.cursor}"


def test_step_to_ts_refuses_a_target_behind_the_cursor():
    s = _series([100, 200, 300])
    assert s.step_to_ts(300) is True, "positive control: the cursor does move"
    assert s.cursor == 2

    moved = s.step_to_ts(100)

    assert moved is False, "a target behind the cursor must not report an advance"
    assert s.cursor == 2, f"cursor must stay at index 2, got {s.cursor}"


def test_step_to_ts_leaves_the_cursor_when_the_target_precedes_the_first_row():
    s = _series([500, 600, 700])
    s.set_cursor(2)

    moved = s.step_to_ts(100)

    assert moved is False, "a target before the first row must report no advance"
    assert s.cursor == 2, f"cursor must stay at index 2, got {s.cursor}"


def test_step_to_ts_reports_false_when_the_target_lands_on_the_cursor():
    s = _series([100, 200, 300])
    assert s.step_to_ts(200) is True, "positive control: the cursor does move"

    moved = s.step_to_ts(250)

    assert moved is False, "a target on the current row must report no advance"
    assert s.cursor == 1, f"cursor must stay at index 1, got {s.cursor}"


def test_get_current_keeps_the_reached_row_after_a_target_behind_the_cursor():
    s = _series([100, 200, 300])
    s.step_to_ts(300)
    reached = s.get_current()
    assert reached is not None and reached[0] == 300

    s.step_to_ts(100)

    served = s.get_current()
    assert served is not None
    assert served[0] == 300, f"get_current served timestamp {served[0]}, want 300"


def test_get_history_keeps_its_length_after_a_target_behind_the_cursor():
    s = _series([100, 200, 300])
    s.step_to_ts(300)
    assert [r[0] for r in s.get_history(limit=100)] == [100, 200, 300]

    s.step_to_ts(100)

    stamps = [r[0] for r in s.get_history(limit=100)]
    assert stamps == [100, 200, 300], f"get_history returned {stamps}"
