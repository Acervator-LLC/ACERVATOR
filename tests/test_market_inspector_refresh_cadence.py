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
import os
import sys

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
        return {s: {"quoteVolume": 1_000_000.0, "last": 100.0} for s in self._symbols}

    async def get_ohlcv(self, symbol, timeframe, limit):
        """[ts, o, h, l, c, v] — the shape `_ohlcv_to_candles` reads.

        200 daily bars, not a token few: `_fetch_one_symbol` returns None
        below 20 daily, and the weekly resample needs roughly 140 daily to
        reach its own 20-week floor. A shorter stub is silently discarded
        and every cadence assertion downstream then measures nothing.
        """
        bars = 200 if timeframe == "1d" else 40
        return [
            [i * 86_400_000, 100.0, 101.0, 99.0, 100.5 + i, 10.0]
            for i in range(min(limit, bars))
        ]


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
        "measuring the cadence"
    )
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
        "measuring the cadence"
    )
    f._LAST_FETCH_MONO -= 12.0  # pretend 12 s elapsed
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
        "measuring the cadence"
    )
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
        "measuring the cadence"
    )
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


# =====================================================================
# THE BUTTON -> FETCHER WIRING
# =====================================================================
#
# Everything above calls `fetch_htf_universe` DIRECTLY, so all of it
# stays green while the Refresh button is disconnected from the cadence
# it is supposed to override. Three hops carry `force` from the click to
# the parameter:
#
#     clicked            -> _start_fetch(force=True)
#     _start_fetch       -> _fetch_and_analyze(connectors, force=force)
#     _fetch_and_analyze -> fetch_htf_universe(..., force_network=force)
#
# Measured 2026-08-20: each hop was broken independently and the suite
# stayed green (6 / 26 / 32 passed), because nothing in tests/ built the
# tab and pressed Refresh. A break at any hop is the ORIGINAL defect
# moved one layer up -- the button serves a scan up to 15 minutes old
# while the operator watches "Fetching..." and believes the venue was
# polled.
#
# OCIR, same as above: BOTH directions are driven. Asserting only that
# the button reaches `force_network=True` is passed by hardcoding the
# parameter to True, which deletes the cadence in the other direction
# and puts every refresh back on the venue's rate budget.

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    """Headless Qt, mirroring tests/test_topology_proposals_gui.py.

    `importorskip` sits INSIDE the fixture rather than at module scope:
    at module scope it would skip the six cadence tests above -- which
    need no Qt at all -- on any box without PySide6.
    """
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication(sys.argv)


def _capture_calls(monkeypatch) -> list:
    """Record every argument that ACTUALLY ARRIVES at the fetcher.

    Patched on the fetcher MODULE, because that is where the shipping
    code resolves the name: `_fetch_and_analyze` runs a function-local
    `from .market_inspector_fetcher import fetch_htf_universe` on every
    call, so the module attribute is read at call time and this
    substitution is what the real GUI path lands on.

    The spy mirrors the real signature rather than taking `**kwargs`, so
    a positional argument binds exactly as a keyword one does. A
    kwargs-only spy would record `None` -- and silently stop measuring
    anything -- if the call site were ever rewritten positionally.

    The whole call is recorded, not just `force_network`, so a future
    assertion about the universe cap or the active-symbol set has the
    evidence already in hand.
    """
    seen: list = []

    async def _spy(
        exchange_connectors,
        active_symbols=None,
        top_n=f.DEFAULT_TOP_N,
        progress_cb=None,
        force_network=False,
        min_refresh_s=f.DEFAULT_MIN_REFRESH_S,
    ):
        seen.append(
            {
                "connectors": exchange_connectors,
                "active_symbols": active_symbols,
                "top_n": top_n,
                "progress_cb": progress_cb,
                "force_network": force_network,
                "min_refresh_s": min_refresh_s,
            }
        )
        return f.FetchResult(
            candles_by_symbol_by_tf={},
            closes_by_symbol={},
            universe=[],
            meta={
                "source": "exchange",
                "age_seconds": 0.0,
                "error": None,
                "symbol_count": 0,
            },
        )

    monkeypatch.setattr(f, "fetch_htf_universe", _spy)
    return seen


def _forced(seen: list) -> list:
    """The `force_network` values the fetcher was actually handed."""
    return [call["force_network"] for call in seen]


def _wire_tab():
    """Build the real tab and give it the two things `_start_fetch` needs.

    Without BOTH `_connectors_getter` and `_scheduler` it returns early
    and schedules nothing, so an unwired tab would make every assertion
    below vacuous. `_drain` fails loudly on that rather than reading an
    empty list as agreement.
    """
    from src.gui.market_inspector import MarketInspectorTab

    tab = MarketInspectorTab()
    scheduled: list = []
    tab.set_exchange_source(lambda: {"cb": _Conn()}, scheduled.append)
    return tab, scheduled


def _drain(qapp, scheduled: list) -> None:
    """Flush Qt, then run what the tab handed the scheduler.

    `processEvents` runs first because the assertion below is about what
    the button's `clicked` connection produced: a queued connection would
    not have delivered yet, and an empty `scheduled` would then read as
    "the tab refused" instead of "not delivered yet". It runs again after
    the coroutine because `_fetch_and_analyze` ends in `_render_signals`,
    which repopulates both tables -- so that rendering pass is executed
    here rather than deferred past the end of the test.
    """
    qapp.processEvents()
    assert len(scheduled) == 1, (
        f"_start_fetch scheduled {len(scheduled)} coroutine(s), not 1; "
        "the tab refused before reaching the fetcher, so nothing here "
        "is measuring the wiring"
    )
    coro = scheduled.pop()
    assert asyncio.iscoroutine(
        coro
    ), f"the scheduler was handed {type(coro)!r}, not a coroutine"
    _run(coro)
    qapp.processEvents()


def test_the_refresh_button_forces_the_network_through_every_hop(qapp, monkeypatch):
    """Press the REAL button; assert what reaches the REAL parameter.

    Driven through `QPushButton.click()` rather than by calling
    `_start_fetch(force=True)`, so the button's own `clicked` connection
    is pinned too -- it is the first of the three hops, and a helper call
    would step straight over it.
    """
    seen = _capture_calls(monkeypatch)
    tab, scheduled = _wire_tab()
    try:
        tab._refresh_btn.click()
        _drain(qapp, scheduled)
    finally:
        tab.deleteLater()
    assert _forced(seen) == [True], (
        "the Refresh button did not force a network fetch: "
        f"fetch_htf_universe received force_network={_forced(seen)}. The "
        "button will serve a cached scan up to 15 minutes old while "
        "reporting a fresh one."
    )


def test_the_unforced_path_leaves_the_cadence_in_force(qapp, monkeypatch):
    """The other direction: the default entry must NOT force.

    Without this, hardcoding `force_network=True` anywhere along the
    three hops passes the test above and silently deletes the cadence --
    every refresh back onto the venue, which is the condition the
    cadence was added to end.
    """
    seen = _capture_calls(monkeypatch)
    tab, scheduled = _wire_tab()
    try:
        tab._start_fetch()
        _drain(qapp, scheduled)
    finally:
        tab.deleteLater()
    assert _forced(seen) == [False], (
        "the unforced path forced a network fetch: fetch_htf_universe "
        f"received force_network={_forced(seen)}, so the 15-minute "
        "cadence is bypassed on every refresh."
    )
