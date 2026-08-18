"""A trade marker must sit on the candle the trade happened on.

C29, cascade 26. Findings SN-15, SN-16, SN-30, SN-37, NF-51.

THE DEFECTS

SN-15 — ORDER. The panel's drain calls `mark_trade` (:1340) BEFORE
`append_tick` (:1368). `mark_trade` pins `len(prices) - 1`, so every
marker landed on the PREVIOUS drain's candle. Off by one, always.

SN-16 — DECIMATION. `append_tick` halves the series past `_MAX_POINTS`
with `prices[::2]`, which keeps indices 0, 2, 4... and remaps markers
`i // 2`. That is exact for even indices and wrong for odd ones, and the
error compounds on every subsequent halving. Anchoring on a position in
a list that gets rewritten underneath it cannot be made correct by
arithmetic — the anchor has to be an identity the decimation preserves.

  NOTE ON THE PLAN. C29 step 1 says "anchor markers by timestamp". The
  series carries no timestamps — `_series[symbol]` is `(prices, vwaps)`
  and `append_tick(symbol, close_price, volume)` never receives one. A
  monotonic per-symbol ORDINAL is the same idea without changing the
  caller's signature: a stable identity, sliced by the same decimation
  as the data, resolved back to a position only at paint time.

SN-30 — `clear_data` cleared the series and left `_markers` populated,
so markers from the previous run were drawn against the new one.

SN-37 — `_markers` was an unbounded list.

NF-51 — `clear_gates` reset five fields and not `_ls_scrum`, so the
landing-strip override LED stayed lit through a clear.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SYM = "BTC/USD"


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _chart():
    from src.gui.simulator_tab.fleet.sim_visuals import SimPriceVwapChart

    _app()
    c = SimPriceVwapChart()
    c.set_symbols([SYM])
    return c


def _resolved_indices(chart):
    """Where the markers currently point, in CURRENT series positions.

    Goes through the chart's own resolver so the test measures what the
    paint would draw, not a reimplementation of it.
    """
    return [i for i, _ok in chart.resolved_markers(SYM)]


def _feed(chart, n, spike_at, spike_price=9999.0, base=100.0):
    """Append n ticks; the spike candle is uniquely identifiable by
    price, and `mark_trade` is called in the FIXED order (append first)."""
    for i in range(n):
        px = spike_price if i == spike_at else base + i
        chart.append_tick(SYM, px, 1.0)
        if i == spike_at:
            chart.mark_trade(SYM, True)


class TestTheInstrumentWorks:
    def test_a_marker_is_recorded_at_all(self):
        """POSITIVE CONTROL."""
        c = _chart()
        _feed(c, 10, spike_at=4)
        assert len(_resolved_indices(c)) == 1

    def test_the_spike_is_uniquely_identifiable(self):
        """The fixture's premise: exactly one candle carries the spike
        price, so 'the marker is on the spike' is unambiguous."""
        c = _chart()
        _feed(c, 10, spike_at=4)
        prices, _ = c._series[SYM]
        assert prices.count(9999.0) == 1


class TestMarkerSitsOnTheTradeCandle:
    def test_below_the_decimation_threshold(self):
        """Exit gate, run 1: series shorter than _MAX_POINTS."""
        c = _chart()
        n = c._MAX_POINTS // 2
        spike = n // 3
        _feed(c, n, spike_at=spike)
        prices, _ = c._series[SYM]
        idx = _resolved_indices(c)[0]
        assert prices[idx] == 9999.0, (
            f"marker at index {idx} is on price {prices[idx]}, not the "
            f"spike candle")

    def test_above_the_decimation_threshold(self):
        """Exit gate, run 2: long enough to force at least one halving,
        which is where index anchoring goes wrong."""
        c = _chart()
        n = c._MAX_POINTS * 3
        spike = c._MAX_POINTS // 3
        _feed(c, n, spike_at=spike)
        prices, _ = c._series[SYM]
        assert len(prices) <= c._MAX_POINTS, "no decimation occurred"
        idx = _resolved_indices(c)[0]
        assert prices[idx] == 9999.0, (
            f"after decimation the marker slid to price {prices[idx]}")

    def test_an_odd_index_survives_decimation(self):
        """The specific case `i // 2` gets wrong. An odd-indexed marker
        maps onto the preceding kept candle under the old remap."""
        c = _chart()
        n = c._MAX_POINTS * 2
        spike = 7                      # odd
        _feed(c, n, spike_at=spike)
        prices, _ = c._series[SYM]
        idx = _resolved_indices(c)[0]
        assert prices[idx] == 9999.0

    def test_a_marked_candle_is_never_decimated_away(self):
        """Ordinal anchoring alone is not enough.

        It fixes the arithmetic, but an odd-ordinal candle is simply
        deleted by `[::2]` and its marker then resolves to nothing — so
        a long replay quietly loses the operator's trades. That is a
        different way of being wrong, not a fix.

        Marked candles are pinned through the decimation, so the marker
        stays EXACT rather than being dropped or slid onto a neighbour.
        """
        c = _chart()
        n = c._MAX_POINTS * 4        # several halvings
        _feed(c, n, spike_at=1)      # odd, the case [::2] discards
        prices, _ = c._series[SYM]
        resolved = c.resolved_markers(SYM)
        assert len(resolved) == 1, "the marker was decimated away"
        idx = resolved[0][0]
        assert prices[idx] == 9999.0

    def test_pinning_does_not_defeat_the_point_cap(self):
        """NEGATIVE CONTROL: keeping marked candles must not let the
        series grow without bound. Bounded by _MAX_MARKERS."""
        c = _chart()
        for i in range(c._MAX_POINTS * 6):
            c.append_tick(SYM, 100.0 + i, 1.0)
            if i % 3 == 0:
                c.mark_trade(SYM, True)
        prices, _ = c._series[SYM]
        assert len(prices) <= c._MAX_POINTS + c._MAX_MARKERS


class TestOrderingIsFixedAtTheCallSite:
    def test_the_panel_appends_before_it_marks(self):
        """SN-15, asserted structurally on the panel: `mark_trade` fired
        before `append_tick`, so every marker pinned the PREVIOUS
        drain's candle."""
        import ast

        panel = (REPO_ROOT / "src" / "gui" / "simulator_tab" / "fleet"
                 / "fleet_replay_panel.py")
        tree = ast.parse(panel.read_text(encoding="utf-8"))
        marks = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and getattr(n.func, "attr", "") == "mark_trade"]
        appends = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call)
                   and getattr(n.func, "attr", "") == "append_tick"]
        assert marks and appends
        assert min(appends) < min(marks), (
            f"mark_trade at {min(marks)} runs before append_tick at "
            f"{min(appends)}; markers pin the previous candle")


class TestMarkerLifecycle:
    def test_clear_data_clears_markers(self):
        """SN-30: markers from the previous run were drawn against the
        new one."""
        c = _chart()
        _feed(c, 20, spike_at=5)
        c.clear_data()
        assert _resolved_indices(c) == []

    def test_clear_markers_still_works_per_symbol(self):
        c = _chart()
        _feed(c, 20, spike_at=5)
        c.clear_markers(SYM)
        assert _resolved_indices(c) == []

    def test_markers_are_bounded(self):
        """SN-37: unbounded growth over a long replay."""
        c = _chart()
        cap = c._MAX_MARKERS
        for i in range(cap * 10):
            c.append_tick(SYM, 100.0 + i, 1.0)
            c.mark_trade(SYM, True)
        assert len(c._markers[SYM]) == cap

    def test_the_newest_markers_are_the_ones_kept(self):
        """A bound that discards the RECENT markers would be worse than
        no bound: the operator is watching the live end."""
        c = _chart()
        cap = c._MAX_MARKERS
        for i in range(cap + 5):
            c.append_tick(SYM, 100.0 + i, 1.0)
            c.mark_trade(SYM, i >= cap)       # last 5 validated=True
        oks = [ok for _i, ok in c._markers[SYM]]
        assert oks[-1] is True


class TestClearGatesClearsTheOverrideLed:
    def test_ls_led_is_cleared(self):
        """NF-51. LS is an OVERRIDE, not a blocker, and it was left lit
        through clear_gates — so a cleared panel still claimed an active
        landing-strip override."""
        from src.gui.simulator_tab.fleet.sim_visuals import GateLightsCell

        _app()
        row = GateLightsCell() if callable(GateLightsCell) else None
        if row is None:
            pytest.skip("gate LED row unavailable")
        row._ls_scrum = True
        row.clear_gates()
        assert row._ls_scrum is False

    def test_clear_gates_still_clears_the_blockers(self):
        """NEGATIVE CONTROL: the existing behaviour must survive."""
        from src.gui.simulator_tab.fleet.sim_visuals import GateLightsCell

        _app()
        row = GateLightsCell()
        row._evaluated = True
        row._scrum_armed = True
        row._scrum_blocked = {"X"}
        row.clear_gates()
        assert row._evaluated is False
        assert row._scrum_armed is False
        assert row._scrum_blocked == set()
