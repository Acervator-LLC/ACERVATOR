"""C03: real exchange ids, and privacy mode that actually covers everything.

SWARM-4.4 — _bot_exchange_id imported get_bot_container from
..trading.bot_container. That symbol DOES NOT EXIST: zero definitions,
zero references anywhere in src/. So the first branch raised ImportError
on EVERY call, a bare `except Exception: pass` swallowed it, and every
lookup fell through to a full StateManager().load_state() parse of the
whole state file to retrieve one string. _refresh_visible_bots calls it
once per bot, so changing the exchange filter on a 35-bot swarm was 35
complete re-reads. The value was already in memory the whole time:
get_status() emits "exchange" and the widget keeps that dict.

SWARM-4.7 — the locust tooltip leaked what the labels were masking. The
painted symbol (:697) and painted bot_id (:716) both route through
_mask_or; the tooltip interpolated the RAW symbol and a RAW 12-character
bot_id, four characters MORE than the label ever showed. Privacy mode on
meant the locust read **** and a hover handed the real values back.

SWARM-4.11 — bot_swarm_list.py contains ZERO mask_or references, so
whatever _refresh_bot_list_rows hands to set_bots renders verbatim. The
list view showed real symbols while the grid beside it showed ****.

WHY THESE TESTS TOGGLE THE REGISTRY
mask_or short-circuits to str(value) for any field_id not in
ALL_FIELD_IDS -- an unregistered id NEVER masks. A test that only
asserted "_mask_or is called" would pass against a typo'd field id that
silently does nothing. These drive the real registry and assert the
rendered output changes.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.core.privacy_mask_registry import (  # noqa: E402
    ALL_FIELD_IDS, get_privacy_mask_registry,
)
from src.gui.bot_visualizer import BotVisualizationTab  # noqa: E402

FIELD = "bot_swarm.identifiers"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def masked():
    """Turn privacy ON for the swarm identifiers, and restore after."""
    reg = get_privacy_mask_registry()
    before = reg.is_masked(FIELD)
    reg.set_masked(FIELD, True)
    yield reg
    reg.set_masked(FIELD, before)


def _painted_tooltip(w, app) -> str:
    """Force a real paintEvent and return the tooltip it set.

    repaint() does NOT fire paintEvent under the offscreen platform --
    measured. render() into a pixmap does, and the tooltip is rebuilt
    inside paintEvent from the latest data.
    """
    from PySide6.QtGui import QPixmap

    w.resize(80, 80)
    w.render(QPixmap(w.size()))
    app.processEvents()
    return w.toolTip()


def _status(bid, symbol="BTC/USD", exchange="coinbase", **extra):
    d = {"bot_id": bid, "symbol": symbol, "exchange": exchange,
         "mode": "live", "current_holdings": 0.0,
         "stats": {"ytd_folded_usd": 0.0, "ytd_scrummed_usd": 0.0}}
    d["stats"].update(extra.pop("stats", {}))
    d.update(extra)
    return d


class TestTheMaskingInstrumentWorks:
    def test_the_field_id_is_registered(self):
        """POSITIVE CONTROL. mask_or short-circuits on an unknown
        field_id and never masks, so every privacy assertion below
        would pass vacuously against a typo."""
        assert FIELD in ALL_FIELD_IDS

    def test_the_registry_toggles(self, masked):
        assert masked.is_masked(FIELD) is True


class TestExchangeIdComesFromStatus:
    def test_it_reads_the_status_exchange(self, qapp):
        tab = BotVisualizationTab()
        tab.update_bots([_status("a", exchange="coinbase"),
                         _status("b", exchange="kraken")])
        assert tab._bot_exchange_id("a") == "coinbase"
        assert tab._bot_exchange_id("b") == "kraken"
        tab.deleteLater()

    def test_an_unknown_bot_is_empty_not_a_guess(self, qapp):
        tab = BotVisualizationTab()
        tab.update_bots([_status("a")])
        assert tab._bot_exchange_id("nope") == ""
        tab.deleteLater()

    def test_the_nonexistent_import_is_gone(self):
        """get_bot_container does not exist anywhere in src/, so
        importing it guaranteed an ImportError on every call.

        Asserted over the AST, not the text: the rationale comment in
        the fixed function names the symbol it removed."""
        import src.gui.bot_visualizer as bv

        tree = ast.parse(Path(bv.__file__).read_text(encoding="utf-8"))
        imported = [
            a.name for n in ast.walk(tree)
            if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in n.names]
        assert "get_bot_container" not in imported

    def test_no_state_file_read_per_lookup(self):
        """The fallback re-parsed the whole bot_state.json once per
        bot, on every filter change. AST again -- the comment says
        StateManager."""
        import src.gui.bot_visualizer as bv

        tree = ast.parse(Path(bv.__file__).read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "_bot_exchange_id")
        calls = [getattr(c.func, "id", "") or getattr(c.func, "attr", "")
                 for c in ast.walk(fn) if isinstance(c, ast.Call)]
        assert "StateManager" not in calls
        assert "load_state" not in calls

    def test_the_filter_selects_on_it(self, qapp):
        """Negative control on the fix: reading the id correctly is
        only useful if the filter still uses it."""
        tab = BotVisualizationTab()
        tab.update_bots([_status("a", exchange="coinbase"),
                         _status("b", exchange="kraken")])
        ids = {b for b in tab._bot_widgets
               if tab._bot_exchange_id(b) == "kraken"}
        assert ids == {"b"}
        tab.deleteLater()


class TestPrivacyCoversTheTooltip:
    def test_the_tooltip_hides_the_symbol(self, qapp, masked):
        tab = BotVisualizationTab()
        tab.update_bots([_status("botrealid001", symbol="BTC/USD")])
        tip = _painted_tooltip(tab._bot_widgets["botrealid001"], qapp)
        assert "BTC/USD" not in tip, (
            f"privacy is ON and the tooltip still leaks the symbol: {tip!r}")
        tab.deleteLater()

    def test_the_tooltip_hides_the_bot_id(self, qapp, masked):
        tab = BotVisualizationTab()
        tab.update_bots([_status("botrealid001")])
        tip = _painted_tooltip(tab._bot_widgets["botrealid001"], qapp)
        assert "botrealid" not in tip, (
            f"privacy is ON and the tooltip still leaks the bot_id "
            f"(it showed 12 chars, more than the label's 8): {tip!r}")
        tab.deleteLater()

    def test_the_tooltip_still_shows_non_identifying_data(self, qapp,
                                                         masked):
        """NEGATIVE CONTROL. Masking must hide identifiers, not blank
        the tooltip -- a fix that returned an empty string would pass
        both tests above."""
        tab = BotVisualizationTab()
        tab.update_bots([_status("botrealid001")])
        tip = _painted_tooltip(tab._bot_widgets["botrealid001"], qapp)
        assert "State:" in tip and "Trades:" in tip and "P/L:" in tip
        tab.deleteLater()

    def test_privacy_off_shows_the_real_symbol(self, qapp):
        """NEGATIVE CONTROL. The mask must be conditional; always-on
        masking would pass every test above."""
        reg = get_privacy_mask_registry()
        before = reg.is_masked(FIELD)
        reg.set_masked(FIELD, False)
        try:
            tab = BotVisualizationTab()
            tab.update_bots([_status("botrealid001", symbol="BTC/USD")])
            tip = _painted_tooltip(tab._bot_widgets["botrealid001"], qapp)
            assert "BTC/USD" in tip
            tab.deleteLater()
        finally:
            reg.set_masked(FIELD, before)


class TestPrivacyCoversTheListView:
    def test_rows_carry_a_masked_symbol(self, qapp, masked):
        """bot_swarm_list.py has zero mask_or references, so the
        producer is the only place this can be done."""
        tab = BotVisualizationTab()
        tab.update_bots([_status("a", symbol="BTC/USD")])
        tab._refresh_bot_list_rows()
        from src.gui.bot_swarm_list import COL_TICKER
        texts = [tab._bot_list.item(r, COL_TICKER).text()
                 for r in range(tab._bot_list.rowCount())]
        assert texts and "BTC/USD" not in texts, (
            f"privacy is ON and the list view still renders the real "
            f"symbol: {texts!r}")
        tab.deleteLater()

    def test_the_consumer_still_does_no_masking_of_its_own(self):
        """Records WHY the producer must mask. If this ever becomes
        false, the masking belongs in one place, not two."""
        import src.gui.bot_swarm_list as bsl

        src = Path(bsl.__file__).read_text(encoding="utf-8")
        assert "mask_or" not in src


class TestInflowOutflowReachTheRows:
    def test_per_bot_values_are_distinct(self, qapp):
        """The C54 keys now exist; this is the consumer half. Two bots
        with different values must render differently -- the clause
        that fails if C54 ever regresses to a fleet aggregate."""
        tab = BotVisualizationTab()
        tab.update_bots([
            _status("a", stats={"ytd_folded_usd": 10.0,
                                "ytd_scrummed_usd": 1.0}),
            _status("b", stats={"ytd_folded_usd": 25.0,
                                "ytd_scrummed_usd": 2.0}),
        ])
        tab._refresh_bot_list_rows()
        from src.gui.bot_swarm_list import COL_INFLOW
        lst = tab._bot_list
        cells = {lst._bot_ids[r]: lst.item(r, COL_INFLOW).text()
                 for r in range(lst.rowCount())}
        assert cells["a"] == "$10.00", cells
        assert cells["b"] == "$25.00", cells
        assert cells["a"] != cells["b"]
        tab.deleteLater()
