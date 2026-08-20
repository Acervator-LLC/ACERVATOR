"""Pins the Market Inspector refresh cadence — the mechanism its docstring claimed.

BEFORE THIS, THE DOCSTRING WAS FALSE ON BOTH HALVES. `market_inspector.py` said:

    "Refresh cadence is enforced by the fetcher (15 min minimum unless
     force_network=True from the button)."

Measured 2026-08-20: `DEFAULT_MIN_REFRESH_S = 15 * 60` was declared and NEVER
READ, so no cadence existed; and `fetch_htf_universe` had no `force_network`
parameter, so the Refresh button passed `force=True` into a function that
ignored it. `meta["source"]` was hardcoded "exchange" and `meta["age_seconds"]`
hardcoded 0.0 -- fields carried for a cache path that was never written.

OCIR. Every assertion below is paired with its opposite, because a cadence that
always serves cache and a cadence that never does are both indistinguishable
from a working one if only one direction is driven:

  serves cache inside the window        vs  goes to network outside it
  `force_network=True` bypasses         vs  the default does not
  a result WITH data is cached          vs  an empty result is not

`age_seconds` is asserted as a MEASUREMENT, not merely present: a hardcoded 0.0
passes an existence check and fails this.
"""

from __future__ import annotations

import asyncio

import pytest

from src.gui import market_inspector_fetcher as f


class _Conn:
    """One connector stub, driving the REAL loop in `fetch_htf_universe`.

    The fetcher iterates connectors, asks each for tickers, picks a
    universe, then calls `_fetch_one_symbol` per symbol. Stubbing at the
    connector means the shipping loop runs; only the venue is replaced.
    """

    def __init__(self, symbols=("BTC/USD",)):
        self._symbols = list(symbols)

    async def get_all_tickers(self):
        return {s: {"quoteVolume": 1_000_000.0, "last": 100.0}
                for s in self._symbols}

    async def get_ohlcv(self, symbol, timeframe, limit):
        """[ts, o, h, l, c, v] — the shape `_ohlcv_to_candles` reads.

        200 daily bars, not a token few: `_fetch_one_symbol` returns None
        below 20 daily, and the weekly resample needs roughly 140 daily to
        reach its own 20-week floor. A shorter stub is silently discarded
        and every cadence assertion downstream then measures nothing.
        """
        bars = 200 if timeframe == "1d" else 40
        return [[i * 86_400_000, 100.0, 101.0, 99.0, 100.5 + i, 10.0]
                for i in range(min(limit, bars))]


def _reset():
    f._LAST_RESULT = None
    f._LAST_FETCH_MONO = 0.0


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clean_cache():
    _reset()
    yield
    _reset()


def _count_network(monkeypatch, calls: list):
    """Count real per-symbol fetches without changing what they return.

    Wraps `_fetch_one_symbol` rather than replacing it, so the loop, the
    universe pick and the candle construction all still run. A test that
    replaced them would stop measuring the code that ships.
    """
    real = f._fetch_one_symbol

    async def _counting(connector, symbol, weekly_native):
        calls.append(symbol)
        return await real(connector, symbol, weekly_native)

    monkeypatch.setattr(f, "_fetch_one_symbol", _counting)
    return calls


def test_a_result_with_data_is_cached_and_served_inside_the_window(monkeypatch):
    calls = []
    _count_network(monkeypatch, calls)
    first = _run(f.fetch_htf_universe({"cb": _Conn()}))
    assert first.candles_by_symbol_by_tf, (
        "the connector stub produced no candles, so nothing below is "
        "measuring the cadence")
    second = _run(f.fetch_htf_universe({"cb": _Conn()}))
    assert second.meta["source"] == "cache"
    assert len(calls) == 1, "the second call went to the network"


def test_the_cached_age_is_measured_not_hardcoded(monkeypatch):
    """A hardcoded 0.0 passes an existence check and fails this."""
    calls = []
    _count_network(monkeypatch, calls)
    first = _run(f.fetch_htf_universe({"cb": _Conn()}))
    assert first.candles_by_symbol_by_tf, (
        "the connector stub produced no candles, so nothing below is "
        "measuring the cadence")
    f._LAST_FETCH_MONO -= 12.0          # pretend 12 s elapsed
    cached = _run(f.fetch_htf_universe({"cb": _Conn()}))
    assert cached.meta["source"] == "cache"
    assert cached.meta["age_seconds"] >= 12.0, cached.meta["age_seconds"]


def test_force_network_bypasses_the_cache(monkeypatch):
    """The Refresh button's whole purpose, which previously did nothing."""
    calls = []
    _count_network(monkeypatch, calls)
    first = _run(f.fetch_htf_universe({"cb": _Conn()}))
    assert first.candles_by_symbol_by_tf, (
        "the connector stub produced no candles, so nothing below is "
        "measuring the cadence")
    forced = _run(f.fetch_htf_universe({"cb": _Conn()}, force_network=True))
    assert forced.meta["source"] == "exchange"
    assert len(calls) == 2, "force_network did not reach the network"


def test_the_window_expiring_goes_back_to_the_network(monkeypatch):
    """The other half of the cache test: it must not serve cache forever."""
    calls = []
    _count_network(monkeypatch, calls)
    first = _run(f.fetch_htf_universe({"cb": _Conn()}))
    assert first.candles_by_symbol_by_tf, (
        "the connector stub produced no candles, so nothing below is "
        "measuring the cadence")
    fresh = _run(f.fetch_htf_universe({"cb": _Conn()}, min_refresh_s=0.0))
    assert fresh.meta["source"] == "exchange"
    assert len(calls) == 2


def test_an_empty_result_is_not_cached(monkeypatch):
    """Caching an empty scan would serve nothing for 15 minutes and look healthy."""
    calls = []
    _count_network(monkeypatch, calls)
    _run(f.fetch_htf_universe({"cb": _Conn(symbols=())}))
    assert f._LAST_RESULT is None, "an empty scan was cached"


def test_no_connectors_still_reports_why():
    """The refusal path names its reason rather than returning a bare empty."""
    res = _run(f.fetch_htf_universe({}))
    assert res.meta["source"] == "no-exchange"
    assert res.meta["error"]
