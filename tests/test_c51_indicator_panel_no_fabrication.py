"""C51: the Indicator Voting Panel must not invent TA for a real bot.

WHAT IT WAS DOING
`_generate_demo_ta` builds 60 synthetic candles from a random walk
starting at 100.0, runs the REAL VotingEngine over them, and renders the
result under the REAL bot's symbol pulled from the selector. The output
therefore has genuine indicator names, genuine directions and genuine
confidence percentages -- computed over prices that never existed.

The seed is `md5(bot_id)`, so it is deterministic PER BOT. The same bot
shows the same fabricated reading on every refresh. It does not flicker
the way random data would, which is precisely what makes it read as a
stable, trustworthy panel rather than as noise.

THREE ENTRY PATHS, ALL LIVE
  * `_auto_init_demo`   -- QTimer.singleShot(3000) from __init__
  * `_on_bot_selected`  -- the operator picking a real bot from the
                           dropdown, when _data happens to be empty
  * `force_refresh`     -- called it UNCONDITIONALLY, and its own
                           docstring says it runs after bot creation

The panel's docstring justified this as "panel is never empty". An empty
panel is a true statement. A populated one that invented its contents
is not.

ON THE DOC'S EXIT GATE
The methodology asks for "no demo callback queued when a real bot is
present", asserted by monkeypatching QTimer.singleShot. That measures
the wrong moment: the timer is scheduled in __init__, before any bot
can exist, so at schedule time there is never a real bot to detect. The
check has to happen when the callback FIRES, three seconds later, which
is where the gate below sits. These tests assert the fire-time
behaviour instead.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

@pytest.fixture(autouse=True)
def _destroy_widgets():
    """Delete every top-level widget after each test.

    v3.24.97 — these tests build whole SimulatorTab trees, and Qt keeps
    a parentless widget alive for the life of the process. Without this
    they accumulate until the suite dies with SIGSEGV (exit 139) around
    90% and prints NO failure summary, so the release gate reports
    "pytest failed" with nothing under it. The crash point moves
    between runs, which is what identifies it as accumulation rather
    than one bad test.
    """
    yield
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:                                   # pragma: no cover
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in list(app.topLevelWidgets()):
        w.hide()
        w.setParent(None)
        w.deleteLater()
    app.processEvents()



os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.gui.indicator_panel import IndicatorVotingPanel  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp):
    p = IndicatorVotingPanel()
    yield p
    p.deleteLater()


def _add_real_bot(p, bot_id="bot-real-0001", label="BTC/USD [bot-rea]"):
    """Put a real bot in the selector the way update_bot_list does:
    visible text plus the bot_id in the userData slot."""
    p._bot_selector.addItem(label, bot_id)
    p._bot_selector.setCurrentIndex(p._bot_selector.count() - 1)
    return bot_id


class TestTheInstrumentWorks:
    def test_the_generator_still_produces_data_in_demo_context(self, panel):
        """POSITIVE CONTROL. Every refusal test below would pass
        trivially against a generator that simply never works. This
        proves the fabrication path is live and reachable, so the
        refusals are refusals and not breakage."""
        panel._generate_demo_ta()
        assert panel._data, (
            "demo generation produced nothing even in a demo context; "
            "the refusal tests below would then prove nothing")

    def test_the_fabricated_values_look_real(self, panel):
        """Documents WHY this mattered: the output is not obviously
        fake. Real indicator names, real confidence numbers."""
        panel._generate_demo_ta()
        tf_data = next(iter(panel._data.values()))
        assert tf_data["signals"], "no signals produced"
        assert 0.0 <= tf_data["confidence"] <= 1.0
        assert tf_data["direction"] in ("BULLISH", "BEARISH", "NEUTRAL")

    def test_it_is_deterministic_per_bot(self, panel):
        """The seed is md5(bot_id), which is what makes it read as
        stable rather than as noise."""
        panel._selected_bot_id = "demo"
        panel._generate_demo_ta()
        first = dict(panel._data)
        panel._data = {}
        panel._generate_demo_ta()
        assert panel._data.keys() == first.keys()
        tf = next(iter(first))
        assert panel._data[tf]["net_score"] == first[tf]["net_score"]


class TestRealBotIsNeverFabricated:
    def test_selecting_a_real_bot_does_not_invent_data(self, panel):
        """Entry path 2 -- the operator picks a real bot."""
        bot_id = _add_real_bot(panel)
        panel._data = {}
        panel._on_bot_selected()
        assert panel._selected_bot_id == bot_id
        assert panel._data == {}, (
            "the panel fabricated TA for a real bot on selection")

    def test_the_3s_timer_callback_does_not_invent_data(self, panel):
        """Entry path 1 -- fired 3 s after construction, by which time
        real bots have loaded. The check must happen HERE, at fire
        time, not at schedule time."""
        _add_real_bot(panel)
        panel._data = {}
        panel._auto_init_demo()
        assert panel._data == {}

    def test_force_refresh_does_not_invent_data(self, panel):
        """Entry path 3 -- the worst one. It called the generator
        unconditionally, right after bot creation."""
        bot_id = _add_real_bot(panel)
        panel.force_refresh(bot_id=bot_id, symbol="BTC/USD",
                            ta_timeframe="1h")
        assert panel._data == {}

    def test_the_direct_call_is_gated_too(self, panel):
        """Gating only the callers would leave the generator reachable
        from any future caller."""
        _add_real_bot(panel)
        panel._generate_demo_ta()
        assert panel._data == {}

    def test_a_real_bot_in_the_roster_blocks_it_even_unselected(self, panel):
        """The 3 s timer sets _selected_bot_id to 'demo' when nothing is
        selected, which would otherwise re-open the path."""
        panel._bot_selector.addItem("BTC/USD [bot-rea]", "bot-real-0001")
        panel._selected_bot_id = ""
        panel._data = {}
        panel._auto_init_demo()
        assert panel._data == {}


class TestTheEmptyStateIsExplicit:
    def test_it_says_there_is_no_data(self, panel):
        """Silence would be indistinguishable from a panel that simply
        had not updated yet."""
        _add_real_bot(panel)
        panel._generate_demo_ta()
        assert "No TA data" in panel._summary_label.text()

    def test_the_tables_are_emptied(self, panel):
        """A refusal must not leave the PREVIOUS bot's rows on screen
        under the new bot's symbol."""
        panel._generate_demo_ta()          # demo context: populates
        assert panel._table_a.rowCount() > 0
        _add_real_bot(panel)
        panel._generate_demo_ta()          # now refuses
        assert panel._table_a.rowCount() == 0
        assert panel._data == {}


class TestSimModeStillWorks:
    def test_sim_mode_may_fabricate(self, qapp):
        """Negative control: the fix must not disable the demo panel in
        the context it legitimately exists for. A gate that blocks
        everything would pass every test above."""
        p = IndicatorVotingPanel(sim_mode=True)
        _add_real_bot(p)
        p._data = {}
        p._generate_demo_ta()
        assert p._data, "sim mode lost its demo data"
        p.deleteLater()


class TestFailureIsNotSilent:
    def test_a_failed_generation_records_and_clears(self, panel,
                                                   monkeypatch):
        """The blanket except wrapped the whole body -- including the
        RNG construction -- and returned normally, so a failure left
        stale values on screen with nothing to show for it."""
        panel._generate_demo_ta()
        assert panel._data                      # populated first

        import random

        def _boom(*a, **kw):
            raise RuntimeError("rng exploded")

        monkeypatch.setattr(random, "Random", _boom)
        panel._generate_demo_ta()
        assert panel._last_demo_error, (
            "a failed generation left no record at all")
        assert "rng exploded" in panel._last_demo_error
        assert panel._data == {}, (
            "a failed generation left the previous values on screen")
