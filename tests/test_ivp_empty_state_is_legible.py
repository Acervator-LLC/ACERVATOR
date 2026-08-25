"""The Indicator Voting Panel's empty state must name the bot and the reason.

WHAT THE INVESTIGATION ESTABLISHED
The blank panel in the operator's screenshot was NOT caused by C51. Bot
7c39c7a2 was restored IDLE, the panel rendered 35 seconds before the bot
even started, and the bot was stopped 12.8 seconds after its init tick --
roughly 45 seconds short of its first TA-capable tick. `_last_summary`
was None for the entire life of that process, and the real feed at
main_window.py is gated on exactly that field.

The decisive proof was not a log line: "Awaiting TA signals..." is the
confidence-bar placeholder, painted only when the widget has NEVER been
fed. No non-empty update_data ever ran on that panel instance, real or
fabricated.

WHAT C51 DID DO, and what these tests pin
Neither `if` on the real feed had an `else`, so a selected bot with no
`_last_summary` produced NOTHING -- no render, no log, on either the
success or the failure path. That silence is the reason diagnosing this
needed four traced lanes arguing from absence.

Three genuinely different states were collapsed into one generic string,
and only one of them is a fault:

  * the bot is idle or stopped and was never started
  * the bot is running but has not reached its first TA read (a
    SEARCH-mode bot waits ~12 ticks, roughly 60 seconds)
  * the bot is parked inside its dust band, where the tick returns BEFORE
    the TA block by design and no TA is ever computed -- permanent, not
    transient

SCOPE: crypto only. The stocks window has a second IndicatorVotingPanel
with no data feed at all, which C51 did blank outright. Per operator
directive 2026-08-06 the stocks panel and mode are not to be touched
until crypto is complete, so that repair is deliberately NOT made here.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

import src.gui.main_window as mw  # noqa: E402
from src.gui.indicator_panel import IndicatorVotingPanel  # noqa: E402

GUI_SRC = Path(mw.__file__).read_text(encoding="utf-8")


def _refresh_dashboard_src() -> str:
    """The whole _refresh_dashboard body.

    Fixed-size text windows do not work here: roughly 2,000 lines of
    phantom-composite arithmetic sit between the `_last_summary` guard
    and its else-branch, so any window small enough to be meaningful
    misses the branch entirely.
    """
    for n in ast.walk(ast.parse(GUI_SRC)):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if n.name == "_refresh_dashboard":
            return ast.get_source_segment(GUI_SRC, n) or ""
    raise AssertionError("_refresh_dashboard not found")


def _is_ivp_update(stmt) -> bool:
    """Is this statement exactly `self._indicator_panel.update_data(...)`?

    Matched on the statement itself rather than by walking into it, so
    the block returned below is the one that DIRECTLY holds the call and
    not some enclosing block several levels up.
    """
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    func = stmt.value.func
    return (
        getattr(func, "attr", "") == "update_data"
        and getattr(getattr(func, "value", None), "attr", "") == "_indicator_panel"
    )


def _block_containing_ivp_update() -> list:
    """The statement list that directly holds the real feed's update_data.

    Fixed-size character windows do not work on this method: roughly
    2,000 lines of phantom-composite arithmetic sit inside it, and any
    window small enough to be meaningful breaks the moment a comment is
    written on the path it measures.
    """
    for node in ast.walk(ast.parse(_refresh_dashboard_src())):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list) and any(_is_ivp_update(stmt) for stmt in block):
                return block
    raise AssertionError(
        "the real feed's `self._indicator_panel.update_data(...)` call "
        "is no longer a statement inside _refresh_dashboard"
    )


class _IdleOrRunningBot:
    """The fields MainWindow's empty-state decision reads off a bot.

    Only two states matter to the test below: a bot that was never
    started, and one that is running with nothing else wrong.
    """

    def __init__(self, state: str):
        self.config = SimpleNamespace(
            symbol="BTC/USD", exchange_id="coinbase", ta_timeframe="1h"
        )
        self.state = SimpleNamespace(value=state)
        self.stats = SimpleNamespace(current_price=100.0, last_error="")
        self.position_value_usd = 100.0
        self._current_holdings = 1.0
        self._quote_to_usd = 1.0
        self._target_balance = 50.0
        self._at_target_counter = 0


class _EmptyStateShell:
    """The REAL MainWindow decision methods without a real QMainWindow.

    Both are the function objects off MainWindow itself. Building an
    actual MainWindow would wire exchanges, timers and the live bot
    manager, which this suite must not touch.
    """

    _ivp_cached_candle_count = mw.MainWindow._ivp_cached_candle_count
    _ivp_empty_state_cause = mw.MainWindow._ivp_empty_state_cause


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    """A real IndicatorVotingPanel.

    `qapp` is named as a parameter because a QWidget cannot be
    constructed without a QApplication, and that is how pytest is told
    to build one first. It was previously named and never read, which
    vulture reported as dead code on the live tree before this unit
    touched the file; reading it here closes the finding and makes the
    ordering requirement explicit rather than implicit.
    """
    if qapp is None:
        raise AssertionError("no QApplication: a QWidget cannot be constructed")
    p = IndicatorVotingPanel()
    yield p
    p.deleteLater()


def _populate(p):
    """Give the panel a real-shaped payload so 'cleared' means something."""
    p.update_data(
        {
            "1h": {
                "bullish": 3,
                "bearish": 2,
                "neutral": 1,
                "net_score": 0.4,
                "confidence": 0.7,
                "direction": "BULLISH",
                "signals": [
                    {
                        "indicator": "bb",
                        "direction": "BULLISH",
                        "confidence": 0.7,
                        "details": {},
                    }
                ],
                "locks": [],
            }
        },
        "BTC/USD",
    )


class TestTheInstrumentWorks:
    def test_the_panel_can_be_populated(self, panel):
        """POSITIVE CONTROL. Every 'it clears' assertion below would pass
        against a panel that never renders anything."""
        _populate(panel)
        assert panel._table_a.rowCount() == 1
        assert panel._data


class TestShowNoDataNamesTheBot:
    def test_it_renders_the_reason(self, panel):
        panel.show_no_data("botid123", "ETH/USD", "bot is idle — not started")
        assert "not started" in panel._summary_label.text()

    def test_it_uses_the_GIVEN_symbol_not_a_stale_one(self, panel):
        """_render_no_data reused whatever symbol was last displayed, so
        an empty render could sit under the PREVIOUS bot's ticker."""
        _populate(panel)  # panel now says BTC/USD
        panel.show_no_data("botid123", "ETH/USD", "no TA read yet")
        assert panel._symbol_label_raw == "ETH/USD"

    def test_it_clears_the_tables(self, panel):
        _populate(panel)
        panel.show_no_data("botid123", "ETH/USD", "no TA read yet")
        assert panel._table_a.rowCount() == 0
        assert panel._data == {}

    def test_it_survives_an_empty_symbol(self, panel):
        """The 'no bot selected' path passes nothing."""
        panel.show_no_data(reason="no bot selected")
        assert "no bot selected" in panel._summary_label.text()


class TestTheClearIsComplete:
    def test_the_bars_are_reset_too(self, panel):
        """R4. An empty render left both bar widgets untouched, so the
        PREVIOUS bot's confidence bars could stay painted above two
        zero-row tables: a chart of one symbol under another's header."""
        _populate(panel)
        assert panel._conf_bars_a._target_bars, "positive control: bars not fed"
        panel.update_data({}, "")
        assert not panel._conf_bars_a._target_bars
        assert not panel._conf_bars_b._target_bars


class TestForceRefreshIsHonest:
    def test_it_no_longer_calls_the_generator(self):
        """R3. It did `_data = {}` then called the demo generator
        unconditionally. Pre-C51 that was clear-then-refill in a
        millisecond; post-C51 it is clear-then-REFUSE."""
        import src.gui.indicator_panel as ipm

        src = Path(ipm.__file__).read_text(encoding="utf-8")
        fn = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.FunctionDef) and n.name == "force_refresh"
        )
        calls = [
            getattr(c.func, "attr", "") for c in ast.walk(fn) if isinstance(c, ast.Call)
        ]
        assert "_generate_demo_ta" not in calls
        assert "show_no_data" in calls

    def test_it_blocks_signals_around_the_programmatic_selection(self):
        """Otherwise setCurrentIndex fires _on_bot_selected as a side
        effect and the empty state renders twice."""
        import src.gui.indicator_panel as ipm

        src = Path(ipm.__file__).read_text(encoding="utf-8")
        fn = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.FunctionDef) and n.name == "force_refresh"
        )
        calls = [
            getattr(c.func, "attr", "") for c in ast.walk(fn) if isinstance(c, ast.Call)
        ]
        assert "blockSignals" in calls

    def test_a_new_bot_gets_a_named_empty_state(self, panel):
        panel._bot_selector.addItem("SOL/USD [newbot01]", "newbot01")
        panel.force_refresh(bot_id="newbot01", symbol="SOL/USD", ta_timeframe="1h")
        assert panel._symbol_label_raw == "SOL/USD"
        assert "new bot" in panel._summary_label.text()


class TestTheRealFeedHasElseBranches:
    def test_the_no_summary_case_renders_something(self):
        """THE defect. A selected bot with no _last_summary produced no
        render and no log at all."""
        assert "show_no_data" in _refresh_dashboard_src()

    def test_the_no_selection_case_renders_something(self):
        assert _refresh_dashboard_src().count("show_no_data") >= 2

    def test_the_success_path_is_logged(self):
        """There was no log statement anywhere on the real feed's success
        path, which is why the investigation had to argue from silence.

        RESTATED 2026-08-13, Unit 1. The assertion measured the distance
        in CHARACTERS between the `update_data` call and the words "IVP
        feed" -- four hundred of them. That is a proxy for the property,
        not the property: any comment written on that path consumes the
        window while the success path stays just as well logged. Unit 1
        put a twelve-line comment and the `remember_ta` call there and
        the window ran out.

        The replacement is STRONGER. It finds the statement list that
        directly contains the `update_data` call and requires the log
        call to be a sibling inside that same block. The old window
        could be satisfied by a log line belonging to a different
        branch that merely sat nearby in the file; a sibling cannot.
        """
        block = _block_containing_ivp_update()
        logged = [
            stmt
            for stmt in block
            if isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and getattr(stmt.value.func, "attr", "") in ("debug", "info", "warning")
            and stmt.value.args
            and isinstance(stmt.value.args[0], ast.Constant)
            and "IVP feed" in str(stmt.value.args[0].value)
        ]
        assert logged, (
            "the real feed's success path has no 'IVP feed' log call "
            "as a sibling of its update_data call"
        )

    def test_the_reason_distinguishes_idle_from_waiting(self, panel):
        """Collapsing 'never started' and 'running, no read yet' into one
        string is what made the panel unreadable.

        RESTATED 2026-08-13, Unit 2. The assertion looked for two literal
        substrings in the dashboard method's SOURCE. Unit 2 moved the
        wording out of MainWindow into the panel's cause table and left
        MainWindow emitting a cause token, so both substrings left this
        function while the property itself got stronger.

        The replacement asserts the property rather than its shadow, and
        does it twice: MainWindow must return DIFFERENT cause tokens for
        an idle bot and a running one, and the panel must RENDER
        different sentences for them with neither carrying the other's
        cause. A source substring can be satisfied by a comment. A
        rendered label cannot.
        """
        idle_cause, idle_detail = _EmptyStateShell()._ivp_empty_state_cause(
            _IdleOrRunningBot(state="idle"), "bid-idle"
        )
        warm_cause, warm_detail = _EmptyStateShell()._ivp_empty_state_cause(
            _IdleOrRunningBot(state="running"), "bid-warm"
        )
        assert idle_cause != warm_cause, (idle_cause, warm_cause)

        panel.show_no_data(
            bot_id="bid-idle", symbol="BTC/USD", cause=idle_cause, detail=idle_detail
        )
        idle_text = panel._summary_label.text()
        panel.show_no_data(
            bot_id="bid-warm", symbol="BTC/USD", cause=warm_cause, detail=warm_detail
        )
        warm_text = panel._summary_label.text()

        assert idle_text != warm_text
        assert "not running" in idle_text.lower()
        assert "cold start" in warm_text.lower()
        assert "cold start" not in idle_text.lower()
        assert "not running" not in warm_text.lower()


class TestTheStocksPanelIsUntouched:
    def test_no_stocks_change_was_made(self):
        """Operator directive 2026-08-06: the stocks panel and mode are
        not to be touched until crypto is complete. C51 did blank that
        panel outright — it has no data feed at all — but the repair is
        deliberately deferred, not forgotten."""
        import src.gui.stock_main_window as smw

        src = Path(smw.__file__).read_text(encoding="utf-8")
        assert "update_data" not in src, (
            "the stocks window was modified; the operator asked for it "
            "to be left alone until crypto is complete"
        )
