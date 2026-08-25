"""Stone Tablet candle playback, one bot at a time.

Operator task 2026-08-08 (screenshot area 4): "This display is mostly
working for the VWAP play back but need to add stone tablet candle play
back as well. Need to display one bot's vwap, stone tablet (ytd data
overlays once it starts playing from the first documented historical
trade)."

And, added mid-task: "This needs to be changed to show one chart and
have the others be displayed when their respective bot is selected from
the... drop down menu."

WHY ONE BOT. The chart stacked a band per symbol at 36px each. On the
operator's 37-bot fleet that is a 1,332px column in which a candle body
is a smudge -- the close polyline was legible only because a line needs
one pixel of height and a bar needs several. Candles require the height,
so the picker chooses which symbol gets it.

THE YTD OVERLAY STARTS AT THE FIRST DOCUMENTED TRADE, not at the start
of the replay. The tape opens with warm-up candles that precede any gate
decision; shading those as validated would assert coverage that does not
exist -- the same error as counting warm-up ticks toward TA coverage.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _destroy_widgets():
    """Delete every top-level widget after each test.

    These tests build whole SimulatorTab / FleetReplayPanel trees. Qt
    keeps a parentless widget alive for the life of the process, so
    without this they accumulate across the suite until the run dies
    with a segfault (exit 139, and once 127) partway through -- no
    failure summary, just truncated output. The crash point moved
    between runs, which is what identified it as accumulation rather
    than one bad test.
    """
    yield
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:  # pragma: no cover
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in list(app.topLevelWidgets()):
        w.hide()
        w.setParent(None)
        w.deleteLater()
    app.processEvents()


SYMS = ["CHIP/USD", "SPK/USD"]
T0 = 1_776_778_500_000
STEP = 300_000


def _qapp():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:  # pragma: no cover
        pytest.skip("PySide6 unavailable")
    return QApplication.instance() or QApplication([])


def _chart(symbols=None):
    _qapp()
    from src.gui.simulator_tab.fleet.sim_visuals import SimPriceVwapChart

    c = SimPriceVwapChart()
    c.set_symbols(list(symbols or SYMS))
    return c


def _feed(chart, sym, n=60, px0=1.0):
    px = px0
    for i in range(n):
        px *= 1.0 + ((i % 5) - 2) * 0.004
        chart.append_tick(
            sym,
            close_price=px,
            volume=50.0,
            ts=T0 + i * STEP,
            open_price=px * 0.999,
            high=px * 1.005,
            low=px * 0.995,
        )


class TestCandlesAreStored:
    def test_the_whole_bar_is_kept(self):
        c = _chart()
        _feed(c, SYMS[0], 10)
        bars = c._candles[SYMS[0]]
        assert len(bars) == 10
        ts, o, h, low, close = bars[-1]
        assert isinstance(ts, int)
        assert h >= max(o, close)
        assert low <= min(o, close)

    def test_a_close_only_caller_still_works(self):
        """The signature stayed backwards compatible; OHLC is optional
        and a close-only tick degenerates to a doji."""
        c = _chart()
        c.append_tick(SYMS[0], close_price=2.0, volume=1.0)
        ts, o, h, low, close = c._candles[SYMS[0]][-1]
        assert o == close == 2.0
        assert h == low == 2.0

    def test_storage_is_bounded(self):
        c = _chart()
        _feed(c, SYMS[0], c._MAX_CANDLES + 75)
        assert len(c._candles[SYMS[0]]) == c._MAX_CANDLES

    def test_the_bound_discards_the_oldest(self):
        """The operator watches the live end; dropping recent bars
        would remove exactly what is being looked at."""
        c = _chart()
        _feed(c, SYMS[0], c._MAX_CANDLES + 10)
        first_ts = c._candles[SYMS[0]][0][0]
        assert first_ts == T0 + 10 * STEP

    def test_reloading_the_fleet_clears_candles(self):
        c = _chart()
        _feed(c, SYMS[0], 20)
        c.set_symbols(SYMS)
        assert c._candles[SYMS[0]] == []


class TestFocusMode:
    def test_default_is_all_bands(self):
        assert _chart().focus_symbol() == ""

    def test_focusing_selects_one_symbol(self):
        c = _chart()
        c.set_focus_symbol(SYMS[1])
        assert c.focus_symbol() == SYMS[1]

    def test_an_unknown_symbol_is_refused(self):
        """Silently focusing nothing would blank the chart with no
        indication why."""
        c = _chart()
        c.set_focus_symbol("NOPE/USD")
        assert c.focus_symbol() == ""

    def test_focus_grows_the_widget(self):
        """A band is 36px; a candle needs real height."""
        c = _chart()
        banded = c.minimumHeight()
        c.set_focus_symbol(SYMS[0])
        assert c.minimumHeight() >= c._FOCUS_MIN_H > banded / len(SYMS)

    def test_focus_survives_a_reload_that_keeps_the_symbol(self):
        c = _chart()
        c.set_focus_symbol(SYMS[0])
        c.set_symbols(SYMS)
        assert c.focus_symbol() == SYMS[0]

    def test_focus_clears_when_the_symbol_leaves_the_fleet(self):
        c = _chart()
        c.set_focus_symbol(SYMS[0])
        c.set_symbols(["BTC/USD"])
        assert c.focus_symbol() == ""


class TestTheYtdOverlay:
    def test_the_start_is_recorded(self):
        c = _chart()
        c.set_ytd_start(SYMS[0], T0 + 30 * STEP)
        assert c._ytd_from[SYMS[0]] == T0 + 30 * STEP

    def test_no_overlay_before_it_is_set(self):
        """Absence must mean "not yet known", not "starts at zero" --
        an overlay from zero would shade the entire warm-up."""
        c = _chart()
        assert SYMS[0] not in c._ytd_from

    def test_a_bad_value_is_ignored(self):
        c = _chart()
        c.set_ytd_start(SYMS[0], None)
        assert SYMS[0] not in c._ytd_from


class TestItPaints:
    """A painter that throws takes the whole tab down, so both modes
    are actually rendered rather than merely configured."""

    @staticmethod
    def _render(c):
        from PySide6.QtGui import QPixmap

        c.resize(700, 300)
        pm = QPixmap(700, 300)
        c.render(pm)
        return pm

    def test_focused_mode_renders(self):
        c = _chart()
        _feed(c, SYMS[0], 80)
        c.set_ytd_start(SYMS[0], T0 + 40 * STEP)
        c.set_focus_symbol(SYMS[0])
        assert not self._render(c).isNull()

    def test_focused_mode_renders_before_any_candle(self):
        c = _chart()
        c.set_focus_symbol(SYMS[0])
        assert not self._render(c).isNull()

    def test_band_mode_still_renders(self):
        c = _chart()
        _feed(c, SYMS[0], 40)
        _feed(c, SYMS[1], 40)
        assert not self._render(c).isNull()

    def test_a_flat_series_does_not_divide_by_zero(self):
        """high == low across the window is a real market condition."""
        c = _chart()
        for i in range(30):
            c.append_tick(
                SYMS[0],
                close_price=5.0,
                volume=1.0,
                ts=T0 + i * STEP,
                open_price=5.0,
                high=5.0,
                low=5.0,
            )
        c.set_focus_symbol(SYMS[0])
        assert not self._render(c).isNull()


class TestThePicker:
    def _tab(self):
        _qapp()
        from src.gui.simulator_tab.simulator_tab import SimulatorTab

        t = SimulatorTab()
        t.resize(1600, 900)
        return t

    def test_the_picker_exists_and_defaults_to_bands(self):
        t = self._tab()
        assert t._chart_bot_picker.currentData() == ""
        assert t._sim_price_chart.focus_symbol() == ""

    def test_the_roster_populates_from_the_fleet(self):
        t = self._tab()
        t._sim_price_chart.set_symbols(SYMS)
        t.refresh_chart_bot_roster(SYMS)
        items = [
            t._chart_bot_picker.itemData(i) for i in range(t._chart_bot_picker.count())
        ]
        assert items == [""] + sorted(SYMS)

    def test_choosing_a_bot_focuses_the_chart(self):
        t = self._tab()
        t._sim_price_chart.set_symbols(SYMS)
        t.refresh_chart_bot_roster(SYMS)
        i = t._chart_bot_picker.findData(SYMS[0])
        t._chart_bot_picker.setCurrentIndex(i)
        assert t._sim_price_chart.focus_symbol() == SYMS[0]

    def test_a_reload_keeps_the_operators_selection(self):
        """Jumping the chart to a different bot on reload would read as
        the chart having lost its data."""
        t = self._tab()
        t._sim_price_chart.set_symbols(SYMS)
        t.refresh_chart_bot_roster(SYMS)
        i = t._chart_bot_picker.findData(SYMS[1])
        t._chart_bot_picker.setCurrentIndex(i)
        t.refresh_chart_bot_roster(SYMS)
        assert t._chart_bot_picker.currentData() == SYMS[1]
        assert t._sim_price_chart.focus_symbol() == SYMS[1]

    def test_a_reload_without_the_symbol_falls_back_to_bands(self):
        t = self._tab()
        t._sim_price_chart.set_symbols(SYMS)
        t.refresh_chart_bot_roster(SYMS)
        t._chart_bot_picker.setCurrentIndex(t._chart_bot_picker.findData(SYMS[0]))
        t._sim_price_chart.set_symbols(["BTC/USD"])
        t.refresh_chart_bot_roster(["BTC/USD"])
        assert t._chart_bot_picker.currentData() == ""
        assert t._sim_price_chart.focus_symbol() == ""
