"""Pins the five Exchange emitters -- queue item #10.8, subsystem `exchange`.

    exchange.15.001.postcondition.command_routed_to_chosen_table
    exchange.15.002.invariant.every_bot_reaches_a_table
    exchange.15.003.invariant.selection_survives_refresh
    exchange.15.004.postcondition.privacy_applied_to_every_field
    exchange.15.005.postcondition.privacy_button_matches_registry

TWO OF THESE FIVE ARE ABOUT A COMMAND REACHING THE WRONG BOT, WHICH IS A
REAL-MONEY ACTION ON THE WRONG ASSET. It has already happened in
`ExchangeTab._cmd` once: the function's own comment records MEM-408, an
operator report that Extractor commands silently hijacked the
last-selected Scrumming bot. The wrong bot returns exactly as cleanly as
the right one, so nothing raises and nothing logs -- the Bot Swarm
misroute shape, with money attached.

`15-001` IS THE FALLBACK THAT THE v3.20.62 FIX LEFT BEHIND. That fix
reversed the preference and kept the fallback, so when the preferred
table holds no selection both branches still take the OTHER table's.
`test_a_command_that_lands_on_the_other_tables_bot_is_reported` drives
the reachable path with real widgets: select a Scrumming row, click an
Extractor row's Detail BUTTON (a click on a cell widget changes no row
selection, so the flag flips and the Scrumming selection stands), then
press a command. The command lands on the Scrumming bot, and the test
asserts that it does before it asserts the pin saw it.

`15-003` IS THE SAME LOSS WITH NOBODY'S FINGER ON IT. A Qt selection is
anchored to a ROW INDEX. `update_bots` runs on the 2000 ms dashboard
timer and rewrites rows in place without re-anchoring, so a fleet list
that arrives in a different order leaves the highlight where it was
while a different bot sits under it.
`test_a_reordered_refresh_that_moves_the_selection_is_reported` swaps
two scrumming statuses and reads the other bot back out of the table.

NOTHING HERE READS AN ARGUMENT BACK AS THOUGH IT WERE A RESULT.
`15-001` never touches `command`; it matches the id about to be
dispatched against each table's CURRENT selection. `15-002` counts rows
that really carry a column-0 item, not the length of the list it was
handed. `15-003` compares a selection read before the re-render against
one read after. `15-004` asks the registry again from a fresh accessor
call rather than trusting `set_all`'s argument. `15-005` reads the
button's own text off the widget.

ONE INSTANCE EXISTS PER CONFIGURED EXCHANGE, and that decides the
throttle. `signal_contract._throttle_admit` keys its fold window on
`(name, site)` and `site` is `file:line`, so every ExchangeTab shares
ONE window on the two cadence pins. A green therefore names one exchange
and stands for `count` passes across all of them; a red is never folded.
`test_two_exchanges_fold_into_one_green_record` and
`test_a_red_from_every_exchange_survives_the_shared_window` drive both
halves with two real tabs.

NO PIN CARRIES A DURATION (E8). Three follow an operator press and read
widget state; two walk table rows already in memory. `15-001` writes its
record BEFORE the dispatch, so there is no completed operation to time
and a number would be fabricated.
`test_no_pin_in_this_tab_carries_a_duration` holds that against the
syntax tree.

WHAT IS REAL AND WHAT IS A STAND-IN. The `ExchangeTab`, both
`QTableWidget` subclasses, the `QPushButton`s, the `QLabel`s and the
`SignalSink` are real; no `MainWindow` is constructed and no bot manager
exists. Two things are stood in for and neither is under test.
`CryptoNewsTicker` becomes an inert `QWidget`, because the production
class spawns a `QThread` that fetches ten RSS feeds and a test must
never reach the network. `get_privacy_mask_registry` becomes a
`PrivacyMaskRegistry` bound to a `tmp_path` file, because the real
singleton auto-persists to the operator's own
`~/.acervator/settings.json` on every `set_all`.

NOTHING HERE TOUCHES `~/.acervator` OR `~/.acervator_logs`, REACHES AN
EXCHANGE, OR SENDS A COMMAND TO A REAL BOT. `on_bot_cmd` is a list
append. The sink is in memory and is never given a path.
"""

from __future__ import annotations

import ast
import contextlib
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

import pytest

# `tests/conftest.py` puts the repository root on `sys.path` before any
# test module is imported, so these import normally rather than after a
# path insert. THAT IS WHY THERE IS NO `# noqa: E402` HERE: they are at
# the top because they belong there, not because a suppression was
# written over a real finding.
from src.core import signal_contract as sc
from src.core.privacy_mask_registry import PrivacyMaskRegistry
from src.core.signal_contract import SignalSink

# Set before any fixture imports PySide6, which is this module's only
# route to Qt. Nothing above touches it.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent

if TYPE_CHECKING:                       # pragma: no cover
    # Annotation only. PySide6 must not be imported at module scope: the
    # source-reading tests below are pure Python and have to run on a box
    # without Qt. A skipped test is not evidence, so the skip is scoped
    # to the fixture and not to the module.
    from PySide6.QtWidgets import QApplication

ROUTED = "exchange.15.001.postcondition.command_routed_to_chosen_table"
REACHED = "exchange.15.002.invariant.every_bot_reaches_a_table"
SELECTION = "exchange.15.003.invariant.selection_survives_refresh"
APPLIED = "exchange.15.004.postcondition.privacy_applied_to_every_field"
BUTTON = "exchange.15.005.postcondition.privacy_button_matches_registry"

EXCHANGE_PINS = (ROUTED, REACHED, SELECTION, APPLIED, BUTTON)

# The two cadence pins. `_refresh_dashboard` is their clock.
THROTTLED = (REACHED, SELECTION)

MAIN_WINDOW = REPO / "src" / "gui" / "main_window.py"

# The production values, restated so the tests drive the real geometry.
FOLD_WINDOW = 30.0
DASHBOARD_INTERVAL_MS = 2000
PRIVACY_FIELDS = 19

# Substrings that must never appear in a record this tab writes. A
# context is written to disk. `bot_id` leads the list here for a reason
# the other tabs did not have: this tab's whole subject is WHICH BOT a
# command reached, and the privacy registry masks that very string in
# the table two lines away.
FORBIDDEN = ("api_key", "apikey", "secret", "passphrase", "password",
             "credential", "token", "bot_id")


# ── Qt fixtures ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """The QApplication the widget tests run against."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication as _QApplication

    running = _QApplication.instance()
    if isinstance(running, _QApplication):
        return running
    return _QApplication(sys.argv)


def _scrum(bot_id: str, symbol: str = "BTC/USD") -> dict:
    """One Scrumming status, in the shape `BotContainer.get_status` emits."""
    return {"bot_id": bot_id, "mode": "scrumming", "symbol": symbol,
            "state": "running", "stats": {"total_trades": 2},
            "target_balance": 50.0}


def _extractor(bot_id: str, base: str = "ETH") -> dict:
    """One Extractor status, in the shape `ExtractorBot.get_status` emits."""
    return {"bot_id": bot_id, "mode": "extractor", "symbol": f"{base}/USD",
            "state": "running", "base_currency": base,
            "stats": {"total_trades": 1}, "chunk_size_usd": 100.0,
            "chunk_size_base": 1.0, "chunk_free_base": 0.5,
            "n_positions_open": 1, "n_positions_drawdown": 0,
            "pool_color": "green"}


@contextlib.contextmanager
def _tab(qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
         registry_dir: Path, *,
         exchange_id: str = "coinbase") -> Iterator[Any]:
    """A REAL `ExchangeTab`, with the network and the operator's disk cut.

    `CryptoNewsTicker.start()` spawns a `QThread` over ten RSS feeds;
    it is replaced by an inert `QWidget`. `get_privacy_mask_registry`
    returns the process-wide singleton, which auto-persists to
    `~/.acervator/settings.json` on every `set_all`; it is replaced by a
    registry bound to `registry_dir`. Both substitutions are made on the
    names `main_window` really resolves, and both are undone by
    `monkeypatch` on the way out.

    `_pull_rate_timer` is stopped immediately. It is a 1000 ms timer
    that reads `MarketDataPool` and paints a label -- the site this unit
    REFUSED -- and letting it fire during a test would be noise from a
    subsystem nothing here is measuring.
    """
    from PySide6.QtWidgets import QWidget

    from src.gui import crypto_news_ticker as ticker_module
    from src.gui import main_window as mw

    class _InertTicker(QWidget):
        """No thread, no feed, no timer. Holds the header slot only."""

        def start(self) -> None:
            return

    monkeypatch.setattr(
        ticker_module, "CryptoNewsTicker", _InertTicker, raising=True)

    registry = PrivacyMaskRegistry(
        settings_path=registry_dir / "settings.json", autosave=True)
    monkeypatch.setattr(
        mw, "get_privacy_mask_registry", lambda: registry, raising=True)

    sent: list[tuple[str, str]] = []
    warnings: list[str] = []

    class _StatusLog:
        def log(self, message: str, level: str = "info") -> None:
            warnings.append(f"{level}:{message}")

    tab = mw.ExchangeTab(
        exchange_id, exchange_id.capitalize(),
        on_bot_cmd=lambda bot_id, command: sent.append((bot_id, command)),
        status_log=_StatusLog())
    tab._pull_rate_timer.stop()
    tab.dispatched = sent
    tab.warnings = warnings
    tab.registry = registry
    try:
        yield tab
    finally:
        tab._pull_rate_timer.stop()
        tab.setParent(None)
        tab.deleteLater()
        qapp.processEvents()


# ── sink helpers ───────────────────────────────────────────────────────


@contextlib.contextmanager
def _collect() -> Iterator[SignalSink]:
    """Install a fresh sink and restore the PREVIOUS one, never None.

    `set_sink` is process-global; restoring None would switch the
    instrument off for whatever ran before this test. The rate-limit
    windows are cleared too, because two of these five pins carry
    `every=30.0` and a window left standing by an earlier test would
    suppress the record this one is reading.
    """
    sink = SignalSink()
    previous = sc.get_sink()
    sc.reset_throttle()
    sc.set_sink(sink)
    try:
        yield sink
    finally:
        sc.set_sink(previous)
        sc.reset_throttle()


def _records(sink: SignalSink, name: str) -> list:
    return [r for r in sink.records() if r.name == name]


def _only(sink: SignalSink, name: str):
    """The single record under this name, or a failure that says so."""
    got = _records(sink, name)
    assert len(got) == 1, f"{name}: expected 1 record, got {len(got)}"
    return got[0]


def _last(sink: SignalSink, name: str):
    got = _records(sink, name)
    assert got, f"{name}: no record"
    return got[-1]


def _tick(tab: Any, statuses: list[dict]) -> None:
    """One dashboard pass with the 30 s fold window cleared first.

    The throttle is REAL and is asserted in the two multiplicity tests
    below. Where a test needs THIS pass admitted rather than folded into
    the previous one it says so here, in one place, rather than by
    sleeping for thirty seconds.
    """
    sc.reset_throttle()
    tab.update_bots(statuses)


# ── the syntax tree ────────────────────────────────────────────────────


def _exchange_emit_calls() -> list[ast.Call]:
    """Every `_ex_emit(...)` call node in `main_window.py`.

    Read from the syntax tree, the way `tools/emitter_registry_check.py`
    reads them. A regex over the source would answer a different
    question.
    """
    tree = ast.parse(MAIN_WINDOW.read_text(encoding="utf-8"))
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_ex_emit"]


def _pin_name(call: ast.Call) -> str:
    first = call.args[0]
    assert isinstance(first, ast.Constant)
    return str(first.value)


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _span(function: str) -> tuple[int, int]:
    """The first and last line of one method of `ExchangeTab`.

    Scoped to the class, because `update_bots` is defined on three
    classes in this file and a tree-wide search would return whichever
    one `ast.walk` reached first.
    """
    tree = ast.parse(MAIN_WINDOW.read_text(encoding="utf-8"))
    for klass in ast.walk(tree):
        if not (isinstance(klass, ast.ClassDef)
                and klass.name == "ExchangeTab"):
            continue
        for node in klass.body:
            if (isinstance(node, ast.FunctionDef) and node.name == function
                    and node.end_lineno is not None):
                return (node.lineno, node.end_lineno)
    missing = f"ExchangeTab.{function} not found in {MAIN_WINDOW}"
    raise AssertionError(missing)


# ── 15-001  the command reached the table the operator chose ───────────


def test_a_command_reaches_the_table_the_operator_chose(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """The ordinary case, so the red below is a verdict and not a mood.

    The operator selects an Extractor row -- a real row selection, which
    is what flips the flag AND clears the sibling -- and presses Stop.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("scrum-1"), _extractor("ext-1")])
        tab._extractor_table.selectRow(0)
        assert tab._last_clicked_table == "extractor"
        assert tab._bot_table.get_selected_bot_id() == ""
        tab._cmd("stop")
        rec = _only(sink, ROUTED)
        assert tab.dispatched == [("ext-1", "stop")]
    assert rec.ok is True, rec.context
    assert rec.actual == "extractor"
    assert rec.expected == "extractor"
    assert rec.context["exchange"] == "coinbase"
    assert rec.context["command"] == "stop"
    assert rec.context["scrumming_selected"] is False
    assert rec.context["extractor_selected"] is True
    assert rec.context["fell_back"] is False
    assert rec.duration is None


def test_a_command_that_lands_on_the_other_tables_bot_is_reported(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """THE FALSIFIER for `15-001`, AND IT IS THE MISROUTE ITSELF.

    MEM-408 in the direction the v3.20.62 fix opened. Driven, not
    argued:

      1. The operator selects a Scrumming row. `_last_clicked_table`
         becomes "scrumming" and the Extractor table is cleared.
      2. The operator clicks the Extractor row's Detail BUTTON. A click
         on a cell widget changes no row selection, so
         `_extractor_clicked` flips the flag to "extractor" while the
         Scrumming selection stands untouched.
      3. The operator presses Stop.

    `_cmd` resolves through the extractor branch, finds nothing there,
    falls back, and sends `stop` to the SCRUMMING bot. The dispatch is
    asserted first, because the pin is only worth anything if the
    misroute is real.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("scrum-1"), _extractor("ext-1")])
        tab._bot_table.selectRow(0)
        assert tab._last_clicked_table == "scrumming"

        detail = tab._extractor_table.cellWidget(0, 7)
        assert detail is not None, "the Extractor Detail button is gone"
        detail.click()

        # The state the fallback needs, read off the widgets.
        assert tab._last_clicked_table == "extractor"
        assert tab._extractor_table.get_selected_bot_id() == ""
        assert tab._bot_table.get_selected_bot_id() == "scrum-1"

        tab._cmd("stop")
        rec = _only(sink, ROUTED)

        # THE MISROUTE, asserted on the dispatch itself. A `stop` on the
        # wrong bot is a real-money action on the wrong asset.
        assert tab.dispatched == [("scrum-1", "stop")]

    assert rec.ok is False
    assert rec.actual == "scrumming"
    assert rec.expected == "extractor"
    assert rec.context["fell_back"] is True
    assert rec.context["scrumming_selected"] is True
    assert rec.context["extractor_selected"] is False
    assert rec.context["command"] == "stop"


def test_the_fallback_hijacks_in_the_other_direction_too(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """The mirror image, so the pin is not one-sided.

    The preference is on the Scrumming table and only the Extractor
    table holds a selection. `delete` -- the command with the least
    recoverable consequence -- goes to the Extractor bot.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("scrum-1"), _extractor("ext-1")])
        tab._extractor_table.selectRow(0)
        # Put the preference back on Scrumming without selecting a row,
        # exactly as the Scrumming Detail button does.
        detail = tab._bot_table.cellWidget(0, 9)
        assert detail is not None, "the Scrumming Detail button is gone"
        detail.click()
        assert tab._last_clicked_table == "scrumming"
        assert tab._bot_table.get_selected_bot_id() == ""

        tab._cmd("delete")
        rec = _only(sink, ROUTED)
        assert tab.dispatched == [("ext-1", "delete")]

    assert rec.ok is False
    assert rec.actual == "extractor"
    assert rec.expected == "scrumming"
    assert rec.context["command"] == "delete"
    assert rec.context["fell_back"] is True


def test_a_command_with_nothing_selected_writes_no_routing_record(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """No dispatch, no route to judge, no vacuous record.

    `_cmd` returns after warning the operator. A record here would
    assert something about a command that never left, which is the
    `14-005`-on-the-pause-press shape.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("scrum-1"), _extractor("ext-1")])
        tab._cmd("start")
        assert tab.dispatched == []
        assert tab.warnings == ["warning:Select a bot first."]
        assert _records(sink, ROUTED) == []


def test_the_routing_pin_is_written_before_the_dispatch(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """A command that raises still leaves its routing on the record.

    That is the whole reason the pin sits above `self._on_bot_cmd` and
    carries no duration: there is no completed operation below it to
    time, and a handler that throws must not take the evidence with it.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("scrum-1")])
        tab._bot_table.selectRow(0)

        def _explode(bot_id: str, command: str) -> None:
            raise RuntimeError("the bot manager is down")

        tab._on_bot_cmd = _explode
        with pytest.raises(RuntimeError):
            tab._cmd("pause")
        rec = _only(sink, ROUTED)
    assert rec.ok is True, rec.context
    assert rec.actual == "scrumming"
    assert rec.duration is None


# ── 15-002  every bot reached a table the operator can read ────────────


def test_every_bot_reaches_a_table(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """Both modes routed, both rendered, counted off the widgets."""
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots(
            [_scrum("s1"), _scrum("s2"), _extractor("e1")])
        rec = _only(sink, REACHED)
        assert tab._bot_table.item(0, 0).text() == "s1"
        assert tab._extractor_table.item(0, 0).text() == "e1"
    assert rec.ok is True, rec.context
    assert rec.actual == 3
    assert rec.expected == 3
    assert rec.context["scrumming_rows"] == 2
    assert rec.context["extractor_rows"] == 1
    assert rec.context["routed_scrumming"] == 2
    assert rec.context["routed_extractor"] == 1
    assert rec.context["exchange"] == "coinbase"
    assert rec.duration is None


def test_a_bot_both_mode_filters_drop_is_reported(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """THE FALSIFIER for `15-002`, and it is a silent loss.

    `update_bots` keeps `mode == "scrumming"` in one comprehension and
    `mode == "extractor"` in the other. Anything else falls between
    them: no row, no warning, no exception. The operator's fleet count
    says three and the tab shows two, and until this pin nothing said
    which.

    A third mode is one enum member away -- `BotMode` lost `GRID` in
    v3.20.4 and the unknown-mode branch in `restore_bots_from_state`
    exists precisely because a persisted bot can carry one.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        stranded = _scrum("ghost-1")
        stranded["mode"] = "paper"
        tab.update_bots([_scrum("s1"), stranded, _extractor("e1")])
        rec = _only(sink, REACHED)
        # The loss itself, read off the widgets rather than argued.
        assert tab._bot_table.rowCount() == 1
        assert tab._extractor_table.rowCount() == 1
    assert rec.ok is False
    assert rec.actual == 2
    assert rec.expected == 3
    assert rec.context["routed_scrumming"] == 1
    assert rec.context["routed_extractor"] == 1


def test_the_row_measure_sees_a_blank_row_a_skipped_render_leaves(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """THE POSITIVE CONTROL for the second loss `15-002` claims to see.

    `BotStatusTable.update_bots` calls `setRowCount(len(...))` FIRST and
    then `continue`s past any non-scrumming status, so the row exists
    and is empty. `rowCount()` counts it; the operator cannot read it.

    That path is UNREACHABLE through `ExchangeTab` today, because the
    comprehensions are themselves the filter -- so it is driven here
    against the table directly. Without this the claim that the measure
    discriminates would rest on reading the source, and the count would
    be a claim about the argument rather than about the widget.
    """
    with _tab(qapp, monkeypatch, tmp_path) as tab:
        table = tab._bot_table
        misrouted = _extractor("wrong-home")
        table.update_bots([_scrum("s1"), misrouted])

        assert table.rowCount() == 2                 # what the list said
        drawn = sum(1 for row in range(table.rowCount())
                    if table.item(row, 0) is not None)
        assert drawn == 1                            # what is readable
        assert table.item(1, 0) is None


def test_the_row_count_is_read_from_the_widget_and_not_from_the_list(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """THE CONTROL that makes `15-002`'s widget read mean anything.

    MEASURED WHILE BUILDING THIS UNIT, and it is why this test exists.
    Replacing `actual` with `len(scrum_statuses) + len(extractor_statuses)`
    -- counting the ARGUMENT instead of the widgets -- passed every other
    test in this file. Both of `update_bots`'s comprehensions use the
    same predicate `BotStatusTable.update_bots` uses, so through the tab
    the list length and the rendered count agree on every input the tab
    can be given, and the stronger read was unverified. A read-back
    nothing can tell apart from an echo is an echo.

    Only the CHILD TABLE'S RENDER is perturbed here, in the way
    `BotStatusTable`'s own `continue` perturbs it: the row exists,
    `setRowCount` made it, and column 0 is empty. The real
    `ExchangeTab.update_bots` runs over the real widgets and the real
    sink. The pin must count what is READABLE, not what was asked for.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        table = tab._bot_table
        rendered = table.update_bots

        def _skip_the_last_row(statuses: list[dict]) -> None:
            rendered(statuses)
            if table.rowCount():
                table.takeItem(table.rowCount() - 1, 0)

        table.update_bots = _skip_the_last_row
        tab.update_bots([_scrum("s1"), _scrum("s2")])
        rec = _only(sink, REACHED)

        # The blank row, read off the widget: counted by `rowCount()`,
        # unreadable by the operator.
        assert table.rowCount() == 2
        assert table.item(1, 0) is None
    assert rec.ok is False
    assert rec.actual == 1
    assert rec.expected == 2
    assert rec.context["scrumming_rows"] == 1
    assert rec.context["routed_scrumming"] == 2


def test_an_empty_fleet_is_green_and_not_an_error(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """Zero bots is an ordinary state, so the pin must not paint it red.

    Both sections are hidden and both counts are zero. An instrument
    that goes red on a fresh install is the `06-014` defect in a new
    place.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([])
        rec = _only(sink, REACHED)
        assert tab._bot_table.isHidden() is True
        assert tab._extractor_table.isHidden() is True
    assert rec.ok is True, rec.context
    assert rec.actual == 0
    assert rec.expected == 0


# ── 15-003  the highlight still points at the same bot ─────────────────


def test_a_quiet_refresh_leaves_the_selection_where_it_was(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """The steady state: same list, same order, same bot under the row."""
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        fleet = [_scrum("s1"), _scrum("s2"), _extractor("e1")]
        tab.update_bots(fleet)
        tab._bot_table.selectRow(0)
        assert tab._bot_table.get_selected_bot_id() == "s1"
        _tick(tab, fleet)
        rec = _last(sink, SELECTION)
        assert tab._bot_table.get_selected_bot_id() == "s1"
    assert rec.ok is True, rec.context
    assert rec.actual == 0
    assert rec.expected == 0
    assert rec.context["scrumming_selection_moved"] is False
    assert rec.context["extractor_selection_moved"] is False
    assert rec.context["selections_before"] == 1
    assert rec.context["selections_after"] == 1
    assert rec.context["preferred_table"] == "scrumming"
    assert rec.duration is None


def test_a_reordered_refresh_that_moves_the_selection_is_reported(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """THE FALSIFIER for `15-003`, and it is the second misroute.

    A Qt selection is anchored to a ROW INDEX. `update_bots` rewrites
    the rows in place and never re-anchors it, so a fleet list arriving
    in a different order -- which is what a deletion does to every row
    below it -- slides a different bot under the operator's highlight.

    Nothing on screen changes. The highlight does not move. The next
    command goes somewhere else, on a 2000 ms timer, with the operator's
    hands still. This is asserted on the table's own answer BEFORE the
    record is read, and then followed through `_cmd` so the consequence
    is on the record too.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("s1"), _scrum("s2")])
        tab._bot_table.selectRow(0)
        assert tab._bot_table.get_selected_bot_id() == "s1"

        _tick(tab, [_scrum("s2"), _scrum("s1")])           # one tick
        rec = _last(sink, SELECTION)

        # THE SUBSTITUTION, read off the widget.
        assert tab._bot_table.get_selected_bot_id() == "s2"
        tab._cmd("stop")
        assert tab.dispatched == [("s2", "stop")]

    assert rec.ok is False
    assert rec.actual == 1
    assert rec.expected == 0
    assert rec.context["scrumming_selection_moved"] is True
    assert rec.context["extractor_selection_moved"] is False
    assert rec.context["selections_before"] == 1
    assert rec.context["selections_after"] == 1


def test_a_selection_whose_bot_left_the_fleet_is_not_a_red(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """THE CONTROL that keeps `15-003` from being red on ordinary use.

    Deleting the selected bot removes its row, and the table is visibly
    empty afterwards. Nothing was silently substituted, so nothing is
    counted. A pin that reported this would go red every time the
    operator deleted a bot, and an instrument red on ordinary use is
    read as broken and then ignored -- the `06-014` lesson.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("s1")])
        tab._bot_table.selectRow(0)
        assert tab._bot_table.get_selected_bot_id() == "s1"

        _tick(tab, [])                                    # s1 deleted
        rec = _last(sink, SELECTION)
        assert tab._bot_table.get_selected_bot_id() == ""
    assert rec.ok is True, rec.context
    assert rec.actual == 0
    assert rec.context["selections_before"] == 1
    assert rec.context["selections_after"] == 0
    assert rec.context["scrumming_selection_moved"] is False


def test_a_moved_extractor_selection_is_reported_on_its_own_side(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """The other table, so the pin is not scrumming-only.

    The context names which side moved, because the two tables carry
    different accounting and a reader has to know which one to look at.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_extractor("e1"), _extractor("e2", base="SOL")])
        tab._extractor_table.selectRow(0)
        assert tab._extractor_table.get_selected_bot_id() == "e1"
        _tick(tab, [_extractor("e2", base="SOL"), _extractor("e1")])
        rec = _last(sink, SELECTION)
        assert tab._extractor_table.get_selected_bot_id() == "e2"
    assert rec.ok is False
    assert rec.actual == 1
    assert rec.context["extractor_selection_moved"] is True
    assert rec.context["scrumming_selection_moved"] is False
    assert rec.context["preferred_table"] == "extractor"


# ── 15-004  every registered mask really took ──────────────────────────


def test_the_privacy_toggle_reaches_every_registered_field(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """One press masks all of them, read back out of the registry."""
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab._on_global_privacy_clicked()
        rec = _only(sink, APPLIED)
        assert all(tab.registry.is_masked(fid)
                   for fid in tab.registry.known_field_ids())
    assert rec.ok is True, rec.context
    assert rec.actual == PRIVACY_FIELDS
    assert rec.expected == PRIVACY_FIELDS
    assert rec.context["masking"] is True
    assert rec.context["fields_declared"] == PRIVACY_FIELDS
    assert rec.context["fields_left_behind"] == 0
    assert rec.context["exchange"] == "coinbase"
    assert rec.duration is None


def test_a_second_press_reveals_every_field_and_is_still_green(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """The unmask half. `expected` is the field COUNT either way, so the
    pin is not green only for one direction of the toggle."""
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab._on_global_privacy_clicked()
        tab._on_global_privacy_clicked()
        rec = _records(sink, APPLIED)[-1]
        assert not any(tab.registry.is_masked(fid)
                       for fid in tab.registry.known_field_ids())
    assert rec.ok is True, rec.context
    assert rec.actual == PRIVACY_FIELDS
    assert rec.context["masking"] is False
    assert rec.context["fields_left_behind"] == 0


def test_a_partial_apply_that_leaves_fields_exposed_is_reported(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """THE FALSIFIER for `15-004`.

    `set_all` persists inside its own try, and `_persist_unlocked`
    swallows every exception by design so a Qt repaint can never raise.
    A `set_all` that reached only part of the catalogue therefore
    returns cleanly, the button relabels itself, and three columns of
    the bot table are still legible on a shared screen.

    Driven with a registry whose `set_all` stops short, which is one
    plausible line of a future edit -- a new field group registered in
    one place and not the other.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        real_set_all = tab.registry.set_all

        def _half(value: bool) -> None:
            real_set_all(value)
            for fid in tab.registry.known_field_ids()[-4:]:
                tab.registry.set_masked(fid, not value)

        tab.registry.set_all = _half
        tab._on_global_privacy_clicked()
        rec = _only(sink, APPLIED)
        # The exposure itself, read off the registry.
        leaked = [fid for fid in tab.registry.known_field_ids()
                  if not tab.registry.is_masked(fid)]
        assert len(leaked) == 4
    assert rec.ok is False
    assert rec.actual == PRIVACY_FIELDS - 4
    assert rec.expected == PRIVACY_FIELDS
    assert rec.context["fields_left_behind"] == 4
    assert rec.context["masking"] is True


# ── 15-005  the button told the truth about it ─────────────────────────


def test_the_button_agrees_with_the_registry(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """Masked everything, and the label says ON."""
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab._on_global_privacy_clicked()
        rec = _only(sink, BUTTON)
        assert tab._privacy_mode_btn.text() == "Privacy Mode: ON"
    assert rec.ok is True, rec.context
    assert rec.actual is True
    assert rec.expected is True
    assert rec.context["masking"] is True
    assert rec.context["fields_declared"] == PRIVACY_FIELDS
    assert rec.duration is None


def test_a_button_that_says_off_over_a_masked_screen_is_reported(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """THE FALSIFIER for `15-005`, and it is the dangerous direction.

    `_refresh_privacy_mode_btn_style` computes `all_masked` inside a
    bare `except` that falls back to False. A registry that answers
    `is_masked` badly therefore relabels the button OFF while every
    field is masked. The operator reads "OFF", believes the values are
    already revealed, and shares the screen.

    `is_masked` is broken AFTER `set_all` has run, so the flip really
    reached every field -- which is why `15-004` stays green here and
    only `15-005` goes red. Two pins, two questions, two verdicts.

    THIS TEST WAS RED AGAINST THE FIRST VERSION OF THE PIN, and the pin
    was wrong. It read the expectation through `all(reg.is_masked(...))`
    -- the very accessor the restyle reads -- so the broken accessor
    raised inside the pin's own `contextlib.suppress` and NO RECORD WAS
    WRITTEN. The instrument went silent on the one fault it exists to
    report. The pin now reads `to_dict()`, an independent accessor over
    the same locked state. That silence is what this assertion buys.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        real_set_all = tab.registry.set_all

        def _then_break(value: bool) -> None:
            real_set_all(value)

            def _broken(*_field_id: object) -> bool:
                # Star-args, not a named parameter: an unused named one
                # is dead code and the Coding Archetype reports it as
                # such (vulture, high). The call shape `is_masked(fid)`
                # still binds, which is all the restyle needs.
                failure = "registry read failed"
                raise RuntimeError(failure)

            tab.registry.is_masked = _broken

        tab.registry.set_all = _then_break
        tab._on_global_privacy_clicked()

        applied = _only(sink, APPLIED)
        rec = _only(sink, BUTTON)
        assert tab._privacy_mode_btn.text() == "Privacy Mode: OFF"

    assert applied.ok is True, "the flip itself reached every field"
    assert rec.ok is False
    assert rec.actual is False
    assert rec.expected is True
    assert rec.context["masking"] is True


# ── the cadence, and what one instance per exchange does to it ─────────


def test_two_exchanges_fold_into_one_green_record(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """THE MULTIPLICITY, driven.

    `_throttle_admit` keys its window on `(name, site)` and `site` is
    `file:line`. Two ExchangeTabs run the SAME two lines, so they share
    one 30 s window: the first pass is admitted and every later pass
    inside the window folds into its `count`, whichever tab made it.

    A reader must therefore treat a green as a record ABOUT the exchange
    its context names, standing for `count` passes across all of them --
    never as a claim that the others are healthy. That is exactly why
    the exchange id is in the context, and it is asserted here rather
    than explained in a comment.
    """
    with _collect() as sink:
        with _tab(qapp, monkeypatch, tmp_path,
                  exchange_id="coinbase") as first, \
                _tab(qapp, monkeypatch, tmp_path / "second",
                     exchange_id="kraken") as second:
            first.update_bots([_scrum("s1")])
            second.update_bots([_scrum("s2")])
            first.update_bots([_scrum("s1")])
            second.update_bots([_scrum("s2")])
        got = _records(sink, REACHED)

    assert len(got) == 1, [r.context["exchange"] for r in got]
    assert got[0].ok is True
    assert got[0].context["exchange"] == "coinbase"
    assert got[0].count == 1
    # The three folded passes are carried, not dropped: the NEXT
    # admitted record would stand for them. Inside one window there is
    # no next, which is the property being shown.
    assert len(_records(sink, SELECTION)) == 1


def test_a_red_from_every_exchange_survives_the_shared_window(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """THE HALF THAT MAKES THE SHARED WINDOW SAFE.

    A failing check is never folded. Two exchanges, both losing a bot to
    the mode filter, inside one 30 s window: two records, one per
    exchange, each naming its own. If the synchroniser folded reds the
    second exchange's loss would be invisible for thirty seconds, and
    the throttle would be a blindfold rather than a spam control.
    """
    stranded = _scrum("ghost")
    stranded["mode"] = "paper"
    with _collect() as sink:
        with _tab(qapp, monkeypatch, tmp_path,
                  exchange_id="coinbase") as first, \
                _tab(qapp, monkeypatch, tmp_path / "second",
                     exchange_id="kraken") as second:
            first.update_bots([_scrum("s1"), stranded])
            second.update_bots([_scrum("s2"), stranded])
        got = _records(sink, REACHED)

    assert len(got) == 2, [r.context["exchange"] for r in got]
    assert [r.ok for r in got] == [False, False]
    assert [r.context["exchange"] for r in got] == ["coinbase", "kraken"]


def test_the_operator_driven_pins_carry_no_throttle(
        qapp: QApplication, monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path) -> None:
    """Three presses, three records, inside one fold window.

    `15-001`, `15-004` and `15-005` are driven by a finger. Throttling
    them would collapse three separate operator actions into one line,
    and on `15-001` that line would be about only one of three commands.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("s1")])
        tab._bot_table.selectRow(0)
        for command in ("start", "pause", "stop"):
            tab._cmd(command)
        assert len(_records(sink, ROUTED)) == 3
        assert [r.context["command"] for r in _records(sink, ROUTED)] == [
            "start", "pause", "stop"]

        tab._on_global_privacy_clicked()
        tab._on_global_privacy_clicked()
        assert len(_records(sink, APPLIED)) == 2
        assert len(_records(sink, BUTTON)) == 2


# ── the shape, read off the syntax tree ────────────────────────────────


def test_no_pin_in_this_tab_carries_a_duration() -> None:
    """E8 in this tab: not one of the five may carry a number.

    Three follow an operator press and read widget state; two walk table
    rows already in memory. `15-001` writes its record BEFORE the
    dispatch, so there is no completed operation to time either.
    """
    carriers = {_pin_name(call) for call in _exchange_emit_calls()
                if _keyword(call, "duration") is not None}
    assert carriers == set()


def test_the_cadence_declaration_is_what_the_source_does() -> None:
    """Item #14 reads this split, so it is asserted and not narrated.

    Two pins fire on `update_bots`, which the 2000 ms dashboard timer
    drives, and fold to one record per 30 s window. The three
    operator-driven pins carry no throttle.
    """
    every: dict[str, Any] = {}
    for call in _exchange_emit_calls():
        node = _keyword(call, "every")
        every[_pin_name(call)] = (node.value
                                  if isinstance(node, ast.Constant)
                                  else None)
    assert set(every) == set(EXCHANGE_PINS)
    assert {name for name, value in every.items() if value is None} == (
        set(EXCHANGE_PINS) - set(THROTTLED))
    assert {value for name, value in every.items()
            if name in THROTTLED} == {FOLD_WINDOW}


def test_each_pin_sits_in_the_method_the_register_claims() -> None:
    """The cadence is a property of WHERE each pin sits.

    A pin that kept its `every=30.0` while drifting onto an
    operator-driven caller would lose the cadence the register promises
    without changing one character of its own line.
    """
    placed = {_pin_name(call): call.lineno
              for call in _exchange_emit_calls()}
    assert set(placed) == set(EXCHANGE_PINS)

    for method, expected in (
            ("_cmd", {ROUTED}),
            ("update_bots", {REACHED, SELECTION}),
            ("_on_global_privacy_clicked", {APPLIED, BUTTON})):
        low, high = _span(method)
        inside = {name for name, line in placed.items()
                  if low <= line <= high}
        assert inside == expected, method


def test_the_dashboard_timer_really_is_the_cadence() -> None:
    """The clock behind `15-002` and `15-003`, read off the source.

    The register says 2000 ms. `_setup_refresh_timer` is where that
    number lives, and a comment claiming it would age.
    """
    source = MAIN_WINDOW.read_text(encoding="utf-8")
    tree = ast.parse(source)
    starts: list[int] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef)
                and node.name == "_setup_refresh_timer"):
            continue
        for call in ast.walk(node):
            if (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "start"
                    and call.args
                    and isinstance(call.args[0], ast.Constant)):
                starts.append(int(call.args[0].value))
    assert starts == [DASHBOARD_INTERVAL_MS], starts


def test_no_two_pins_share_a_line() -> None:
    """One pin per line.

    `signal_contract` keys both the fold window and the timing identity
    on (name, site), and `site` is `file:line`. Two pins on one line
    would be one identity to the wire and two to a reader.
    """
    lines = [call.lineno for call in _exchange_emit_calls()]
    assert len(lines) == len(set(lines)) == 5


def test_no_pin_compares_an_expression_with_itself() -> None:
    """E9, asked of this tab by the checker's own rule.

    A CHECK whose `actual` and `expected` are the same expression
    derives `ok` True on every call. `collect_pins` decides that by
    comparing AST dumps, which is the definition this repo uses.
    """
    from tools.emitter_registry_check import collect_pins

    pins = [pin for pin in collect_pins(MAIN_WINDOW, REPO)
            if pin.name.startswith("exchange.")]
    assert len(pins) == 5
    assert [pin.name for pin in pins if pin.vacuous_check] == []
    assert [pin.name for pin in pins if pin.carries_duration] == []


def test_no_context_carries_credential_material_or_a_bot_id() -> None:
    """A context is written to disk, and this tab is per-EXCHANGE.

    A bot id is operator-chosen text that the privacy registry masks in
    this very table, and two of these pins exist because a command
    reached the wrong bot -- so the temptation to name the bot is at its
    highest here and is refused. The contexts hold table names, the
    fixed command vocabulary, booleans and counts. The only string that
    varies is `exchange`, which is the tab's own configured id and is
    what makes one instance's records distinguishable from another's.
    """
    for call in _exchange_emit_calls():
        node = _keyword(call, "context")
        assert isinstance(node, ast.Dict), _pin_name(call)
        rendered = ast.dump(node).lower()
        for banned in FORBIDDEN:
            assert banned not in rendered, (_pin_name(call), banned)


def test_every_context_names_its_exchange() -> None:
    """The multiplicity is only readable if every record says which tab.

    One ExchangeTab exists per configured exchange and all of them share
    each pin's single source line, so without this key a reader cannot
    tell two instances' records apart -- and on the two throttled pins a
    folded green would name nothing at all.
    """
    for call in _exchange_emit_calls():
        node = _keyword(call, "context")
        assert isinstance(node, ast.Dict), _pin_name(call)
        keys = [key.value for key in node.keys
                if isinstance(key, ast.Constant)]
        assert "exchange" in keys, _pin_name(call)


def test_the_register_row_for_every_pin_points_at_its_real_line() -> None:
    """The register is the join, and a stale line makes it a guess.

    The checker reports line drift as a WARNING and does not fail on it,
    which is a stated blind spot. This closes it for this tab's five
    rows.
    """
    from tools.emitter_registry_check import (
        REGISTRY_PATH,
        collect_pins,
        parse_registry,
    )

    registry = parse_registry(
        (REPO / REGISTRY_PATH).read_text(encoding="utf-8"))
    assert registry.parse_errors == []
    rows = {row.name: row for row in registry.rows
            if row.subsystem == "exchange"}
    assert set(rows) == set(EXCHANGE_PINS)

    pins = {pin.name: pin for pin in collect_pins(MAIN_WINDOW, REPO)
            if pin.name.startswith("exchange.")}
    for name, row in rows.items():
        assert row.file == "src/gui/main_window.py", name
        assert row.line == pins[name].line, (
            f"{name}: register says {row.line}, the pin is at "
            f"{pins[name].line}")
