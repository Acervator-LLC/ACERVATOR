"""v3.24.10 — pin tests for Stone Tablet candle addressing.

Operator directive 2026-08-02: assign unique numbered addresses
(``candle_no_ticker``) to candles so historical trade actions bind
to an exact candle rather than a fuzzy timestamp window.

The load-bearing behaviours:
    * a trade anywhere inside a 5m candle maps to THAT candle
    * a timestamp before the tablet starts returns None, never 0
      (otherwise every pre-listing trade collides on candle 0)
    * addresses sort lexically in chronological order
    * the same index on two tickers is NOT the same moment
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.stone_tablets.addressing import (  # noqa: E402
    CandleAddress,
    address_for_ts,
    format_address,
    index_for_ts,
    parse_address,
    ticker_from_symbol,
    ts_for_index,
    verify_addressing_stable,
)

_STEP = 300_000
_T0 = 1_774_915_200_000  # 2026-04-01T00:00:00Z


def _rows(n: int, start: int = _T0) -> list[list[float]]:
    return [[start + i * _STEP, 100.0, 101.0, 99.0, 100.5, 5.0] for i in range(n)]


# ── format / parse ───────────────────────────────────────────────


def test_format_zero_pads_to_six():
    assert format_address("BTC", 0) == "000000_BTC"
    assert format_address("BTC", 1234) == "001234_BTC"
    assert format_address("BTC", 61199) == "061199_BTC"


def test_format_uppercases_ticker():
    assert format_address("btc", 7) == "000007_BTC"


def test_format_rejects_negative_index():
    with pytest.raises(ValueError):
        format_address("BTC", -1)


def test_format_rejects_empty_ticker():
    with pytest.raises(ValueError):
        format_address("", 1)


def test_parse_roundtrip():
    a = parse_address("001234_BTC")
    assert a == CandleAddress(index=1234, ticker="BTC")
    assert str(a) == "001234_BTC"


def test_parse_rejects_garbage():
    for bad in ("", "BTC", "abc_BTC", "1234", "1234-BTC", None):
        assert parse_address(bad) is None


def test_addresses_sort_chronologically():
    addrs = [format_address("BTC", i) for i in (5, 100, 2, 61199, 0)]
    assert sorted(addrs) == [
        "000000_BTC",
        "000002_BTC",
        "000005_BTC",
        "000100_BTC",
        "061199_BTC",
    ]


# ── ticker extraction ────────────────────────────────────────────


def test_ticker_from_pair_and_bare():
    assert ticker_from_symbol("BTC/USD") == "BTC"
    assert ticker_from_symbol("ALLO/USDC") == "ALLO"
    assert ticker_from_symbol("BTC") == "BTC"
    assert ticker_from_symbol("btc/usd") == "BTC"


# ── index resolution ─────────────────────────────────────────────


def test_index_at_exact_open():
    rows = _rows(10)
    assert index_for_ts(rows, _T0) == 0
    assert index_for_ts(rows, _T0 + 5 * _STEP) == 5


def test_mid_candle_maps_to_that_candle():
    """A trade 3 minutes into a 5-minute candle belongs to it."""
    rows = _rows(10)
    assert index_for_ts(rows, _T0 + 180_000) == 0
    assert index_for_ts(rows, _T0 + _STEP + 180_000) == 1


def test_boundary_belongs_to_next_candle():
    rows = _rows(10)
    assert index_for_ts(rows, _T0 + _STEP - 1) == 0
    assert index_for_ts(rows, _T0 + _STEP) == 1


def test_before_first_candle_is_none_not_zero():
    """Critical: returning 0 would collide every pre-listing trade
    onto the first candle."""
    rows = _rows(10)
    assert index_for_ts(rows, _T0 - 1) is None
    assert address_for_ts("BTC", rows, _T0 - 1) is None


def test_after_last_candle_clamps_to_last():
    rows = _rows(10)
    assert index_for_ts(rows, _T0 + 999 * _STEP) == 9


def test_empty_rows_is_none():
    assert index_for_ts([], _T0) is None
    assert address_for_ts("BTC", [], _T0) is None


# ── address_for_ts / ts_for_index ────────────────────────────────


def test_address_for_ts_accepts_pair_symbol():
    rows = _rows(10)
    assert address_for_ts("BTC/USD", rows, _T0 + 2 * _STEP) == "000002_BTC"


def test_ts_for_index_roundtrip():
    rows = _rows(50)
    for i in (0, 7, 49):
        ts = ts_for_index(rows, i)
        assert index_for_ts(rows, ts) == i


def test_ts_for_index_out_of_range():
    rows = _rows(5)
    assert ts_for_index(rows, -1) is None
    assert ts_for_index(rows, 5) is None
    assert ts_for_index([], 0) is None


# ── cross-ticker semantics (documented caveat) ───────────────────


def test_same_index_different_tickers_is_different_time():
    """Tablets start at different listing dates, so index equality
    across tickers does NOT imply time equality."""
    btc = _rows(100, start=_T0)
    late = _rows(100, start=_T0 + 30 * 86_400_000)
    assert ts_for_index(btc, 50) != ts_for_index(late, 50)


# ── stability ────────────────────────────────────────────────────


def test_stability_holds_on_append():
    rows = _rows(10)
    first = int(rows[0][0])
    rows.extend(_rows(5, start=_T0 + 10 * _STEP))
    assert verify_addressing_stable(rows, first) is True


def test_stability_fails_on_earlier_backfill():
    """Prepending earlier candles shifts every address — must be
    detected, not silently accepted."""
    rows = _rows(10)
    first = int(rows[0][0])
    rows.insert(0, [_T0 - _STEP, 1.0, 1.0, 1.0, 1.0, 1.0])
    assert verify_addressing_stable(rows, first) is False


def test_stability_false_on_empty():
    assert verify_addressing_stable([], _T0) is False
