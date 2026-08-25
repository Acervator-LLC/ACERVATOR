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
timer and rewrites rows in place, so a fleet list that arrives in a
different order left the highlight where it was while a different bot
sat under it. Driven on the unrepaired tree: select `bot-AAA`, refresh
with the two statuses swapped, and `_cmd("stop")` dispatched
`('bot-BBB', 'stop')`.

ISSUE #51 REPAIRED THAT, AND THE PIN KEPT ITS FALSIFIER. The two bot
tables now re-anchor the highlight by BOT ID across the rewrite
(`main_window._reanchor_bot_selection`), so the ordinary reordered
refresh is green and
`test_a_reordered_refresh_keeps_the_highlight_on_the_chosen_bot` reads
the same bot back out of the widget.
`test_a_reordered_refresh_that_moves_the_selection_is_reported` remains
the falsifier and drives the pin's failing condition by the one route
that still produces it: it takes the re-anchor away and swaps the two
statuses again. A check nobody has ever seen fail is not a check, and
that test is also the positive control for the repair -- it fails if
`_reanchor_bot_selection` is renamed or removed.

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
`file:line`, and every ExchangeTab runs the same two lines, so until
issue #57 all of them shared ONE window on the two cadence pins: a green
named one exchange and stood for `count` passes across all of them, and
an exchange whose emitter had stopped was invisible behind another
exchange's green. Both cadence pins now pass
`instance=self.exchange_id`, so each tab holds its own window and each
green counts only its own exchange's passes.

FOUR TESTS DRIVE THAT WITH TWO REAL TABS, and between them they are the
two-sided control:
`test_each_exchange_folds_into_its_own_green_record` (two healthy tabs
are two greens and NOT a fault),
`test_a_dead_exchange_is_visible_behind_a_healthy_one` (the falsifier --
one tab's emitter stops and the record set says so, where before the
repair it read exactly like two healthy tabs),
`test_a_red_is_never_folded_inside_one_exchange_window` (the throttle
bypass, driven where the per-exchange key cannot fake it) and
`test_a_red_from_every_exchange_arrives_on_its_own_record`.

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

if TYPE_CHECKING:  # pragma: no cover
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
FORBIDDEN = (
    "api_key",
    "apikey",
    "secret",
    "passphrase",
    "password",
    "credential",
    "token",
    "bot_id",
)


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
    return {
        "bot_id": bot_id,
        "mode": "scrumming",
        "symbol": symbol,
        "state": "running",
        "stats": {"total_trades": 2},
        "target_balance": 50.0,
    }


def _extractor(bot_id: str, base: str = "ETH") -> dict:
    """One Extractor status, in the shape `ExtractorBot.get_status` emits."""
    return {
        "bot_id": bot_id,
        "mode": "extractor",
        "symbol": f"{base}/USD",
        "state": "running",
        "base_currency": base,
        "stats": {"total_trades": 1},
        "chunk_size_usd": 100.0,
        "chunk_size_base": 1.0,
        "chunk_free_base": 0.5,
        "n_positions_open": 1,
        "n_positions_drawdown": 0,
        "pool_color": "green",
    }


@contextlib.contextmanager
def _tab(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    registry_dir: Path,
    *,
    exchange_id: str = "coinbase",
) -> Iterator[Any]:
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

    monkeypatch.setattr(ticker_module, "CryptoNewsTicker", _InertTicker, raising=True)

    registry = PrivacyMaskRegistry(
        settings_path=registry_dir / "settings.json", autosave=True
    )
    monkeypatch.setattr(mw, "get_privacy_mask_registry", lambda: registry, raising=True)

    sent: list[tuple[str, str]] = []
    warnings: list[str] = []

    class _StatusLog:
        def log(self, message: str, level: str = "info") -> None:
            warnings.append(f"{level}:{message}")

    tab = mw.ExchangeTab(
        exchange_id,
        exchange_id.capitalize(),
        on_bot_cmd=lambda bot_id, command: sent.append((bot_id, command)),
        status_log=_StatusLog(),
    )
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


def _without_the_reanchor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put the tree back the way it was before the issue #51 repair.

    `BotStatusTable.update_bots` and `ExtractorBotTable.update_bots`
    both end by calling the module-level `_reanchor_bot_selection`,
    resolved through globals on every call. Replacing it with a no-op
    restores the exact pre-repair behaviour -- rows rewritten in place,
    the selection left on its old ROW INDEX -- which is the condition
    `15-003` exists to report.

    The name is asserted to exist and to be callable FIRST. A
    `monkeypatch.setattr` on a name that has been renamed away would
    raise, but a hand-rolled `setattr` would not, and a falsifier that
    quietly patches nothing is a test that proves nothing. This is
    therefore also the positive control for the repair: delete the
    re-anchor and the tests below fail.
    """
    from src.gui import main_window as mw

    assert callable(mw._reanchor_bot_selection)
    monkeypatch.setattr(
        mw,
        "_reanchor_bot_selection",
        lambda _table, _previous_bot_id, _bot_ids: None,
        raising=True,
    )


def _without_the_detail_row_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put the tree back the way it was before the issue #52 repair.

    `BotStatusTable._on_detail` and `ExtractorBotTable._on_detail` both
    now begin by calling the module-level `_select_row_for_bot`,
    resolved through globals on every call, so the Detail button selects
    its own row and the `itemSelectionChanged` handler ALREADY wired in
    `ExchangeTab.__init__` clears the sibling. Replacing that function
    with a no-op restores the exact pre-repair behaviour: the button
    flips `_last_clicked_table` through `_scrum_clicked` /
    `_extractor_clicked` and moves no selection at all.

    THAT IS WHY THE TWO FALSIFIERS BELOW STILL REACH `15-001`'s FAILING
    CONDITION. The pin matches the id about to be dispatched against
    each table's CURRENT selection, so it reports any genuine
    disagreement between the preference and the live selection -- but
    after the repair no operator gesture produces one, because every
    gesture that moves the flag now moves the selection with it. The
    fallback itself is UNCHANGED and still stands for the first-time
    operator who has one populated table and no click history; taking
    it out would refuse that operator's command instead.

    The name is asserted to exist and to be callable FIRST, for the
    reason `_without_the_reanchor` gives: `monkeypatch.setattr` on a
    renamed-away name raises, a hand-rolled `setattr` would not, and a
    falsifier that quietly patches nothing proves nothing. This is
    therefore also the positive control for the repair -- rename or
    delete `_select_row_for_bot` and the tests that call this fail.
    """
    from src.gui import main_window as mw

    assert callable(mw._select_row_for_bot)
    monkeypatch.setattr(
        mw, "_select_row_for_bot", lambda _table, _bot_id, _bot_ids: None, raising=True
    )


def _stop_the_emitter(tab: Any) -> None:
    """Kill ONE tab's two cadence pins and leave the widget working.

    Both pins read `self.exchange_id` while building their own context,
    inside `ExchangeTab.update_bots`'s own `contextlib.suppress`. Making
    that read raise stops the records at the production call site --
    which is what a stopped emitter is -- without patching `emit`, the
    sink or the throttle, and without moving the `site` string that the
    fold window is keyed on. The tab still renders both tables: nothing
    else in `update_bots` reads the attribute.

    The attribute is asserted to be there before it is taken away, and
    asserted to raise afterwards. A falsifier that quietly breaks
    nothing proves nothing.
    """
    assert getattr(tab, "exchange_id", None)
    del tab.exchange_id
    if getattr(tab, "exchange_id", None) is not None:
        message = "the emitter did not stop"
        raise AssertionError(message)


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
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_ex_emit"
    ]


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
        if not (isinstance(klass, ast.ClassDef) and klass.name == "ExchangeTab"):
            continue
        for node in klass.body:
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == function
                and node.end_lineno is not None
            ):
                return (node.lineno, node.end_lineno)
    missing = f"ExchangeTab.{function} not found in {MAIN_WINDOW}"
    raise AssertionError(missing)


# ── 15-001  the command reached the table the operator chose ───────────


def test_a_command_reaches_the_table_the_operator_chose(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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


def test_the_extractor_detail_button_carries_the_selection_with_it(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ISSUE #52: the Detail button is a row click, so `15-001` is green.

    The gesture the falsifier below drives, with the repair in place and
    nothing patched out: select a Scrumming row, click the EXTRACTOR
    row's Detail button, press Stop. The command reaches `ext-1`.

    The three widget reads between the click and the command are the
    mechanism, not decoration. The preference moved AND the selection
    moved with it AND the sibling is empty -- and the sibling is empty
    because `_select_row_for_bot` does NOT block the signal, so the
    `itemSelectionChanged` handler `ExchangeTab.__init__` already wires
    does the clearing. There is no second copy of that rule.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("scrum-1"), _extractor("ext-1")])
        tab._bot_table.selectRow(0)
        assert tab._bot_table.get_selected_bot_id() == "scrum-1"

        detail = tab._extractor_table.cellWidget(0, 7)
        assert detail is not None, "the Extractor Detail button is gone"
        detail.click()

        assert tab._last_clicked_table == "extractor"
        assert tab._extractor_table.get_selected_bot_id() == "ext-1"
        assert tab._bot_table.get_selected_bot_id() == ""
        assert tab._bot_table.selectedItems() == []

        tab._cmd("stop")
        rec = _only(sink, ROUTED)
        assert tab.dispatched == [("ext-1", "stop")]
    assert rec.ok is True, rec.context
    assert rec.actual == "extractor"
    assert rec.expected == "extractor"
    assert rec.context["fell_back"] is False
    assert rec.context["scrumming_selected"] is False
    assert rec.context["extractor_selected"] is True


def test_the_scrumming_detail_button_carries_the_selection_with_it(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ISSUE #52 in the other direction, because BOTH tables have one.

    `delete` again -- the command with the least recoverable
    consequence, and the one the mirror falsifier sends to the wrong
    bot once the repair is taken away.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("scrum-1"), _extractor("ext-1")])
        tab._extractor_table.selectRow(0)
        assert tab._extractor_table.get_selected_bot_id() == "ext-1"

        detail = tab._bot_table.cellWidget(0, 9)
        assert detail is not None, "the Scrumming Detail button is gone"
        detail.click()

        assert tab._last_clicked_table == "scrumming"
        assert tab._bot_table.get_selected_bot_id() == "scrum-1"
        assert tab._extractor_table.get_selected_bot_id() == ""
        assert tab._extractor_table.selectedItems() == []

        tab._cmd("delete")
        rec = _only(sink, ROUTED)
        assert tab.dispatched == [("scrum-1", "delete")]
    assert rec.ok is True, rec.context
    assert rec.actual == "scrumming"
    assert rec.expected == "scrumming"
    assert rec.context["fell_back"] is False
    assert rec.context["command"] == "delete"


def test_a_detail_button_inside_the_selected_table_moves_the_highlight(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The same-table case, and it is a SECOND misroute issue #52 closes.

    `15-001` could never see this one. The operator has `s1` selected
    and presses the Detail button on `s2`'s row: before the repair the
    preference and the selection agreed -- both said "scrumming" -- so
    the pin was green while `pause` went to `s1`, the bot whose Detail
    dialog the operator was NOT looking at. Nothing fell back, so
    nothing was reported. Measured on the unrepaired tree, with real
    widgets, before the repair was written.

    The row-selecting repair closes it for the same reason it closes the
    cross-table hijack: the button now does what a row click does. The
    dispatch is the assertion; the pin is read only to show it did not
    turn red on a route that is correct.

    THE SECOND CLICK IS THE IDEMPOTENCE CHECK, AND IT IS COUNTED.
    Selecting a row from inside `_on_detail` fires
    `itemSelectionChanged`, which runs the handler that clears the
    sibling -- so the emissions are the thing to measure, not the thing
    to argue about. Two counters ride the same two signals the
    production handlers ride, so they see exactly what those handlers
    see, `blockSignals` included. One click that moves the highlight is
    ONE emission on that table and NONE on the sibling (the sibling's
    clear runs blocked), and a repeat click on the row already selected
    is none on either. No storm, no churn under an operator who
    double-clicks.

    THE IDEMPOTENCE IS QT'S, NOT A BRANCH IN THE REPAIR, and that is
    why it is asserted here. `_select_row_for_bot` carried an
    already-on-this-bot early return until it was measured: a 40-row
    table scrolled to the bottom, this emission counter, and a
    ctrl-click two-row selection all read the same values with the
    guard and without it, so the guard was removed and the behaviour it
    claimed is pinned here instead.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("s1"), _scrum("s2"), _extractor("e1")])
        tab._bot_table.selectRow(0)
        assert tab._bot_table.get_selected_bot_id() == "s1"

        seen = {"scrumming": 0, "extractor": 0}
        tab._bot_table.itemSelectionChanged.connect(
            lambda: seen.__setitem__("scrumming", seen["scrumming"] + 1)
        )
        tab._extractor_table.itemSelectionChanged.connect(
            lambda: seen.__setitem__("extractor", seen["extractor"] + 1)
        )

        tab._bot_table.cellWidget(1, 9).click()
        assert tab._last_clicked_table == "scrumming"
        assert tab._bot_table.get_selected_bot_id() == "s2"
        assert tab._bot_table.currentRow() == 1
        assert seen == {"scrumming": 1, "extractor": 0}, seen

        tab._bot_table.cellWidget(1, 9).click()
        assert tab._bot_table.get_selected_bot_id() == "s2"
        assert tab._bot_table.currentRow() == 1
        assert seen == {"scrumming": 1, "extractor": 0}, seen

        tab._cmd("pause")
        rec = _only(sink, ROUTED)
        assert tab.dispatched == [("s2", "pause")]
    assert rec.ok is True, rec.context
    assert rec.context["fell_back"] is False


def test_the_detail_button_leaves_a_row_it_cannot_read_alone(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A row the render SKIPPED must not be selected by the repair.

    `BotStatusTable.update_bots` calls `setRowCount` first and then
    `continue`s past a status neither mode filter claims, so the row
    exists with no column-0 item. `selectedItems()` stays empty on such
    a row and `get_selected_bot_id` answers "" for it -- which is the
    empty-preferred-table state `_cmd` falls back out of, so selecting
    one would be MEM-408 in a new place. `_reanchor_bot_selection`
    refuses the same row for the same reason.

    Driven against the table directly, the way `15-002`'s blank-row
    control is: the path is unreachable through `ExchangeTab`, whose
    comprehensions are themselves the filter, and a skipped row carries
    no Detail button to press either -- both are asserted here.
    `_on_detail` is called with the skipped row's bot id to reach the
    branch at all.
    """
    with _tab(qapp, monkeypatch, tmp_path) as tab:
        table = tab._bot_table
        misrouted = _extractor("wrong-home")
        table.update_bots([_scrum("s1"), misrouted])
        assert table.item(1, 0) is None
        assert table.cellWidget(1, 9) is None

        table.selectRow(0)
        assert table.get_selected_bot_id() == "s1"

        table._on_detail("wrong-home")

        # The highlight did not move onto the unreadable row.
        assert table.get_selected_bot_id() == "s1"
        assert table.currentRow() == 0


def test_a_command_that_lands_on_the_other_tables_bot_is_reported(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """THE FALSIFIER for `15-001`, AND IT IS THE MISROUTE ITSELF.

    MEM-408 in the direction the v3.20.62 fix opened. Driven, not
    argued:

      1. The operator selects a Scrumming row. `_last_clicked_table`
         becomes "scrumming" and the Extractor table is cleared.
      2. The operator clicks the Extractor row's Detail BUTTON, which
         flips the flag to "extractor" through `_extractor_clicked`.
      3. The operator presses Stop.

    `_cmd` resolves through the extractor branch, finds nothing there,
    falls back, and sends `stop` to the SCRUMMING bot. The dispatch is
    asserted first, because the pin is only worth anything if the
    misroute is real.

    ISSUE #52 REPAIRED STEP 2, AND THIS FALSIFIER KEPT ITS RED. The
    Detail button sits inside a cell, and a click on a cell widget
    changes no row selection -- that was the whole gap, and the ONE
    entry point that moved the flag without moving the selection. The
    button now selects its own row first (`_select_row_for_bot`), so
    the sibling is cleared by the handler already wired on
    `itemSelectionChanged`, and the same three gestures are green in
    `test_the_extractor_detail_button_carries_the_selection_with_it`,
    which reads `ext-1` back off the dispatch.

    SO THE DRIVE IS UNCHANGED AND THE PRE-REPAIR BUTTON IS RESTORED
    UNDER IT, the way `15-003`'s falsifier takes the re-anchor away.
    `_without_the_detail_row_selection` is the only route left to a
    genuine disagreement between the preference and the live selection,
    and it doubles as the positive control: the repair is a named
    module function, and renaming it makes this test fail rather than
    pass quietly. The fallback the pin watches is untouched.
    """
    _without_the_detail_row_selection(monkeypatch)
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
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The mirror image, so the pin is not one-sided.

    The preference is on the Scrumming table and only the Extractor
    table holds a selection. `delete` -- the command with the least
    recoverable consequence -- goes to the Extractor bot.

    ISSUE #52 REPAIRED THIS DIRECTION TOO, and that is why it is driven
    here: BOTH tables carry a Detail button and BOTH flip the flag
    through their `on_bot_clicked` callback, so a repair applied to one
    of them would have left the hijack standing in this direction.
    `_without_the_detail_row_selection` restores the pre-repair button
    on both, which is the one route left to the genuine disagreement
    the pin reports. The repaired gesture is green in
    `test_the_scrumming_detail_button_carries_the_selection_with_it`.
    """
    _without_the_detail_row_selection(monkeypatch)
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("scrum-1"), _extractor("ext-1")])
        tab._extractor_table.selectRow(0)
        # Put the preference back on Scrumming without selecting a row,
        # exactly as the Scrumming Detail button did before issue #52.
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
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Both modes routed, both rendered, counted off the widgets."""
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("s1"), _scrum("s2"), _extractor("e1")])
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
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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

        assert table.rowCount() == 2  # what the list said
        drawn = sum(
            1 for row in range(table.rowCount()) if table.item(row, 0) is not None
        )
        assert drawn == 1  # what is readable
        assert table.item(1, 0) is None


def test_the_row_count_is_read_from_the_widget_and_not_from_the_list(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """THE FALSIFIER for `15-003`, and it is the second misroute.

    A Qt selection is anchored to a ROW INDEX. `update_bots` rewrites
    the rows in place, so a fleet list arriving in a different order --
    which is what a deletion does to every row below it -- slid a
    different bot under the operator's highlight. Nothing on screen
    changed. The highlight did not move. The next command went
    somewhere else, on a 2000 ms timer, with the operator's hands
    still.

    Issue #51 repaired that in the two table classes, so swapping two
    statuses no longer produces the drift and this test can no longer
    drive it that way. It is NOT deleted, because a pin with no
    falsifier is a check nobody has ever seen fail. The failing
    condition is driven by the one route that still reaches it: the
    re-anchor is taken away and the same swap is made. The pin is read
    off the WIDGETS on either side of the rewrite, so it reports the
    drift whatever the cause -- including a re-anchor that stopped
    working, which is the regression this test now also guards.

    The consequence is still followed through `_cmd`, because a
    substitution the operator cannot see is only a defect once a
    command lands on it.
    """
    _without_the_reanchor(monkeypatch)
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("s1"), _scrum("s2")])
        tab._bot_table.selectRow(0)
        assert tab._bot_table.get_selected_bot_id() == "s1"

        _tick(tab, [_scrum("s2"), _scrum("s1")])  # one tick
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


def test_a_reordered_refresh_keeps_the_highlight_on_the_chosen_bot(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """THE REPAIR, on the same drive that produced the defect.

    Same statuses, same swap, no monkeypatch: the highlight follows the
    BOT and `15-003` goes green. The command is dispatched afterwards
    because the pin's verdict is not the point -- where the operator's
    money goes is.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("s1"), _scrum("s2")])
        tab._bot_table.selectRow(0)
        assert tab._bot_table.get_selected_bot_id() == "s1"

        _tick(tab, [_scrum("s2"), _scrum("s1")])
        rec = _last(sink, SELECTION)

        assert tab._bot_table.get_selected_bot_id() == "s1"
        tab._cmd("stop")
        assert tab.dispatched == [("s1", "stop")]

    assert rec.ok is True, rec.context
    assert rec.actual == 0
    assert rec.context["scrumming_selection_moved"] is False
    assert rec.context["selections_before"] == 1
    assert rec.context["selections_after"] == 1


def test_the_visible_highlight_lands_on_the_chosen_bots_new_row(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The HIGHLIGHT, not merely the answer `get_selected_bot_id` gives.

    The operator reads the screen, so the repair is only a repair if
    the painted row is the chosen bot's row. Three bots, the first one
    deleted, every row below it shifted up: the selected row index must
    MOVE, and the column-0 text on the row that is really selected must
    be the bot the operator chose. Read off the widget's own selection
    model and its own items.

    THE SECOND DRIVE IS NOT A REPEAT. A deletion also SHRINKS the
    table, and Qt clamps a current row that falls off the end -- so a
    restore that re-selected the OLD ROW INDEX can land on the right
    bot there by accident. Measured: a row-anchored restore planted in
    place of this one passed the deletion drive. The reorder below
    keeps the row count at two and moves `s3` from row 1 to row 0, so
    only a restore that found the bot by ID can put the highlight
    there.
    """
    with _collect(), _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("s1"), _scrum("s2"), _scrum("s3")])
        tab._bot_table.selectRow(2)
        assert tab._bot_table.get_selected_bot_id() == "s3"
        assert tab._bot_table.currentRow() == 2

        _tick(tab, [_scrum("s2"), _scrum("s3")])  # s1 deleted

        painted = sorted({item.row() for item in tab._bot_table.selectedItems()})
        assert painted == [1], painted
        assert tab._bot_table.item(1, 0).text() == "s3"
        assert tab._bot_table.currentRow() == 1
        assert tab._bot_table.get_selected_bot_id() == "s3"

        # Same row count, different order: no clamping to hide behind.
        _tick(tab, [_scrum("s3"), _scrum("s2")])

        painted = sorted({item.row() for item in tab._bot_table.selectedItems()})
        assert painted == [0], painted
        assert tab._bot_table.item(0, 0).text() == "s3"
        assert tab._bot_table.currentRow() == 0
        assert tab._bot_table.get_selected_bot_id() == "s3"
        tab._cmd("pause")
        assert tab.dispatched == [("s3", "pause")]


def test_the_refresh_does_not_move_the_operators_preferred_table(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The re-anchor must not impersonate an operator click.

    Re-selecting a row emits `itemSelectionChanged`, and `ExchangeTab`
    connects that to a handler which sets `_last_clicked_table`. That
    flag records WHICH TABLE THE OPERATOR CHOSE and `_cmd` reads it
    first, so a 2000 ms timer moving it would be a second misroute of
    the same family as the one being repaired. The restore therefore
    blocks signals across itself.

    THE DRIVE IS THE STATE THAT SEPARATES THE TWO. The flag and the
    selection have to disagree, or a restore that flips the flag flips
    it to the value it already held and nothing is measured. The
    `15-001` path produced exactly that disagreement: select a
    Scrumming row, then click an Extractor row's Detail BUTTON -- a
    click on a cell widget changes no row selection, so the flag went
    to "extractor" while the Scrumming selection stood. Now reorder the
    scrumming rows, which is the one case where the restore really
    runs.

    ISSUE #52 CLOSED THAT GENERATOR, SO IT IS RESTORED HERE. The Detail
    button now selects its own row, which is the repair. This test is
    not about the button: it is about a 2000 ms timer that must not
    impersonate one, and it needs the flag and the selection to
    disagree to measure anything at all.
    `_without_the_detail_row_selection` puts the pre-repair button back
    for the length of this drive -- the same move `_without_the_reanchor`
    makes one section down -- and nothing else in the drive changes.

    THE CONSEQUENCE IS ON `15-001`'s OWN RECORD. `expected` IS the
    flag. If the timer moved it, the fallback hijack this tab already
    reports would be written down as a clean route -- the instrument
    laundering the very defect it exists to catch. So the record is
    read, not just the attribute.
    """
    _without_the_detail_row_selection(monkeypatch)
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("s1"), _scrum("s2"), _extractor("e1")])
        tab._bot_table.selectRow(0)
        assert tab._last_clicked_table == "scrumming"

        detail = tab._extractor_table.cellWidget(0, 7)
        assert detail is not None, "the Extractor Detail button is gone"
        detail.click()
        assert tab._last_clicked_table == "extractor"
        assert tab._bot_table.get_selected_bot_id() == "s1"

        # The scrumming rows reorder. The restore RUNS here.
        _tick(tab, [_scrum("s2"), _scrum("s1"), _extractor("e1")])

        # The highlight followed the bot, and the flag did not move.
        assert tab._bot_table.get_selected_bot_id() == "s1"
        assert tab._last_clicked_table == "extractor"

        tab._cmd("stop")
        rec = _only(sink, ROUTED)
        assert tab.dispatched == [("s1", "stop")]

    # Still the `15-001` fallback hijack, still reported as one.
    assert rec.ok is False
    assert rec.expected == "extractor"
    assert rec.actual == "scrumming"
    assert rec.context["fell_back"] is True


def test_a_selection_whose_bot_left_the_fleet_is_not_a_red(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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

        _tick(tab, [])  # s1 deleted
        rec = _last(sink, SELECTION)
        assert tab._bot_table.get_selected_bot_id() == ""
    assert rec.ok is True, rec.context
    assert rec.actual == 0
    assert rec.context["selections_before"] == 1
    assert rec.context["selections_after"] == 0
    assert rec.context["scrumming_selection_moved"] is False


def test_a_selection_whose_bot_left_the_fleet_is_dropped_not_left_behind(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The chosen answer for a bot that is gone: CLEAR the selection.

    Two other answers were available and both are worse. Leaving the
    old ROW selected is the defect itself -- a different bot is under
    it. Moving the highlight to a neighbour would have the timer choose
    a bot for the operator. Clearing is honest and the path already
    exists: `_cmd` logs "Select a bot first." and dispatches nothing.

    The row BELOW the deleted one shifts up into the vacated index, so
    this is the exact shape that produced the misroute. The current
    cell is asserted too: `clearSelection` alone leaves `currentRow()`
    pointing at the old row, which is the MEM-411 half of the same
    family.
    """
    with _collect(), _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_scrum("s1"), _scrum("s2")])
        tab._bot_table.selectRow(0)
        assert tab._bot_table.get_selected_bot_id() == "s1"

        _tick(tab, [_scrum("s2")])  # s1 deleted

        assert tab._bot_table.selectedItems() == []
        assert tab._bot_table.currentRow() == -1
        assert tab._bot_table.get_selected_bot_id() == ""
        tab._cmd("stop")
        assert tab.dispatched == []
        assert tab.warnings[-1] == "warning:Select a bot first."


def test_a_moved_extractor_selection_is_reported_on_its_own_side(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The other table, so the pin is not scrumming-only.

    The context names which side moved, because the two tables carry
    different accounting and a reader has to know which one to look at.
    Driven with the re-anchor taken away, for the reason given on the
    scrumming falsifier above: after issue #51 a reordered refresh no
    longer moves the selection, and the pin still has to be shown
    capable of reporting it when something does.
    """
    _without_the_reanchor(monkeypatch)
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


def test_a_reordered_extractor_refresh_keeps_its_own_selection(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The repair on the Extractor side, on the same drive.

    `ExtractorBotTable` is a separate class with its own `update_bots`,
    so the scrumming proof says nothing about it. Same swap, no
    monkeypatch, and the command follows.
    """
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab.update_bots([_extractor("e1"), _extractor("e2", base="SOL")])
        tab._extractor_table.selectRow(0)
        assert tab._extractor_table.get_selected_bot_id() == "e1"

        _tick(tab, [_extractor("e2", base="SOL"), _extractor("e1")])
        rec = _last(sink, SELECTION)

        assert tab._extractor_table.get_selected_bot_id() == "e1"
        assert tab._extractor_table.item(1, 0).text() == "e1"
        tab._cmd("stop")
        assert tab.dispatched == [("e1", "stop")]

    assert rec.ok is True, rec.context
    assert rec.actual == 0
    assert rec.context["extractor_selection_moved"] is False
    assert rec.context["preferred_table"] == "extractor"


# ── 15-004  every registered mask really took ──────────────────────────


def test_the_privacy_toggle_reaches_every_registered_field(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One press masks all of them, read back out of the registry."""
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab._on_global_privacy_clicked()
        rec = _only(sink, APPLIED)
        assert all(
            tab.registry.is_masked(fid) for fid in tab.registry.known_field_ids()
        )
    assert rec.ok is True, rec.context
    assert rec.actual == PRIVACY_FIELDS
    assert rec.expected == PRIVACY_FIELDS
    assert rec.context["masking"] is True
    assert rec.context["fields_declared"] == PRIVACY_FIELDS
    assert rec.context["fields_left_behind"] == 0
    assert rec.context["exchange"] == "coinbase"
    assert rec.duration is None


def test_a_second_press_reveals_every_field_and_is_still_green(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The unmask half. `expected` is the field COUNT either way, so the
    pin is not green only for one direction of the toggle."""
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        tab._on_global_privacy_clicked()
        tab._on_global_privacy_clicked()
        rec = _records(sink, APPLIED)[-1]
        assert not any(
            tab.registry.is_masked(fid) for fid in tab.registry.known_field_ids()
        )
    assert rec.ok is True, rec.context
    assert rec.actual == PRIVACY_FIELDS
    assert rec.context["masking"] is False
    assert rec.context["fields_left_behind"] == 0


def test_a_partial_apply_that_leaves_fields_exposed_is_reported(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
        leaked = [
            fid
            for fid in tab.registry.known_field_ids()
            if not tab.registry.is_masked(fid)
        ]
        assert len(leaked) == 4
    assert rec.ok is False
    assert rec.actual == PRIVACY_FIELDS - 4
    assert rec.expected == PRIVACY_FIELDS
    assert rec.context["fields_left_behind"] == 4
    assert rec.context["masking"] is True


# ── 15-005  the button told the truth about it ─────────────────────────


def test_the_button_agrees_with_the_registry(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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


def test_each_exchange_folds_into_its_own_green_record(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """THE MULTIPLICITY, driven -- and TWO HEALTHY TABS ARE NOT A FAULT.

    `_throttle_admit` keys its window on `(name, site, instance)`, and
    both cadence pins declare `instance=self.exchange_id`. Two
    ExchangeTabs run the SAME two lines, so before issue #57 they shared
    one 30 s window and the second tab's passes folded into the first
    tab's record. They hold one window EACH now: two exchanges, two
    greens, and the second pass inside each window folds into its own
    exchange's tally rather than into somebody else's.

    A green is a record ABOUT the exchange its context names and its
    `count` is that exchange's own passes. Nothing here is a fault: both
    records are `ok` True, which is the half of the control that stops
    the repair from turning ordinary multiplicity into an alarm.
    """
    with _collect() as sink:
        with (
            _tab(qapp, monkeypatch, tmp_path, exchange_id="coinbase") as first,
            _tab(
                qapp, monkeypatch, tmp_path / "second", exchange_id="kraken"
            ) as second,
        ):
            first.update_bots([_scrum("s1")])
            second.update_bots([_scrum("s2")])
            first.update_bots([_scrum("s1")])
            second.update_bots([_scrum("s2")])
        got = _records(sink, REACHED)

    assert len(got) == 2, [r.context["exchange"] for r in got]
    assert [r.ok for r in got] == [True, True]
    assert [r.context["exchange"] for r in got] == ["coinbase", "kraken"]
    # One admitted pass each. The SECOND pass of each tab folded into
    # its OWN exchange's window; inside one window there is no next
    # record to carry it, which is the property being shown.
    assert [r.count for r in got] == [1, 1]
    assert len(_records(sink, SELECTION)) == 2


def test_a_dead_exchange_is_visible_behind_a_healthy_one(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """THE FALSIFIER FOR ISSUE #57.

    The second tab's emitter is stopped: `exchange_id` raises, so both
    pins die while building their own context, inside the tab's own
    `contextlib.suppress`, at the production call site. The widget keeps
    rendering and only its records stop.

    On the unrepaired tree this produced EXACTLY what two healthy tabs
    produced -- one record, naming `coinbase`, `count` 1 -- so the dead
    tab was invisible. With the exchange in the key the record set names
    the exchanges that are still speaking and no others, which is the
    fact item #14 reads.
    """
    with _collect() as sink:
        with (
            _tab(qapp, monkeypatch, tmp_path, exchange_id="coinbase") as first,
            _tab(
                qapp, monkeypatch, tmp_path / "second", exchange_id="kraken"
            ) as second,
        ):
            _stop_the_emitter(second)
            for _ in range(3):
                first.update_bots([_scrum("s1")])
                second.update_bots([_scrum("s2")])
        got = _records(sink, REACHED)

    assert [r.context["exchange"] for r in got] == ["coinbase"]
    assert [r.context["exchange"] for r in _records(sink, SELECTION)] == ["coinbase"]
    # The healthy tab is unharmed by its neighbour's silence.
    assert got[0].ok is True


def test_the_two_drives_do_not_read_the_same(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """THE WHOLE OF ISSUE #57 IN ONE ASSERTION.

    The two tests above are one control between them, and a reader
    should not have to hold both in their head to see it. This runs BOTH
    drives -- two healthy tabs, then the same two with the second one's
    emitter stopped -- and asserts the record sets DIFFER.

    On the unrepaired tree they did not. Both read `records=1`,
    `exchanges named=['coinbase']`, `counts=[1]`, for both pins. That
    is the defect: a green over-claimed, so the healthy neighbour's
    record covered for the dead tab and nothing on disk said which of
    the two runs had happened.
    """

    def _drive(*, dead: bool) -> dict[str, list[tuple[str, int]]]:
        with _collect() as sink:
            with (
                _tab(qapp, monkeypatch, tmp_path, exchange_id="coinbase") as first,
                _tab(
                    qapp, monkeypatch, tmp_path / "second", exchange_id="kraken"
                ) as second,
            ):
                if dead:
                    _stop_the_emitter(second)
                for _ in range(3):
                    first.update_bots([_scrum("s1")])
                    second.update_bots([_scrum("s2")])
            return {
                pin: [(r.context["exchange"], r.count) for r in _records(sink, pin)]
                for pin in THROTTLED
            }

    healthy = _drive(dead=False)
    stopped = _drive(dead=True)

    # BOTH cadence pins, because a repair that reached only one of them
    # would leave the other over-claiming and this test would not care.
    for pin in THROTTLED:
        assert healthy[pin] == [("coinbase", 1), ("kraken", 1)], pin
        assert stopped[pin] == [("coinbase", 1)], pin
        assert healthy[pin] != stopped[pin], pin


def test_a_red_is_never_folded_inside_one_exchange_window(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """THE THROTTLE BYPASS, DRIVEN WHERE THE KEY CANNOT FAKE IT.

    `emit` guards the throttle with `if _judged is not False`, so a
    failing check never enters a fold window at all. Two exchanges each
    failing would now produce two records whether or not that guard
    existed -- the per-exchange key alone would explain it -- so the
    bypass is driven on ONE tab instead: three failing passes, one
    exchange, one 30 s window, three records.
    """
    stranded = _scrum("ghost")
    stranded["mode"] = "paper"
    with _collect() as sink, _tab(qapp, monkeypatch, tmp_path) as tab:
        for _ in range(3):
            tab.update_bots([_scrum("s1"), stranded])
        got = _records(sink, REACHED)

    assert len(got) == 3
    assert [r.ok for r in got] == [False, False, False]
    assert [r.context["exchange"] for r in got] == ["coinbase"] * 3


def test_a_red_from_every_exchange_arrives_on_its_own_record(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """THE HALF THAT MADE THE SHARED WINDOW SAFE, AND STILL HOLDS.

    A failing check is never folded. Two exchanges, both losing a bot to
    the mode filter, inside one 30 s window: two records, one per
    exchange, each naming its own. This was the only thing standing
    between the shared window and a blindfold before issue #57, and the
    per-exchange key does not retire it -- a red must still bypass, as
    the one-tab test above drives.
    """
    stranded = _scrum("ghost")
    stranded["mode"] = "paper"
    with _collect() as sink:
        with (
            _tab(qapp, monkeypatch, tmp_path, exchange_id="coinbase") as first,
            _tab(
                qapp, monkeypatch, tmp_path / "second", exchange_id="kraken"
            ) as second,
        ):
            first.update_bots([_scrum("s1"), stranded])
            second.update_bots([_scrum("s2"), stranded])
        got = _records(sink, REACHED)

    assert len(got) == 2, [r.context["exchange"] for r in got]
    assert [r.ok for r in got] == [False, False]
    assert [r.context["exchange"] for r in got] == ["coinbase", "kraken"]


def test_the_operator_driven_pins_carry_no_throttle(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
            "start",
            "pause",
            "stop",
        ]

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
    carriers = {
        _pin_name(call)
        for call in _exchange_emit_calls()
        if _keyword(call, "duration") is not None
    }
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
        every[_pin_name(call)] = node.value if isinstance(node, ast.Constant) else None
    assert set(every) == set(EXCHANGE_PINS)
    assert {name for name, value in every.items() if value is None} == (
        set(EXCHANGE_PINS) - set(THROTTLED)
    )
    assert {value for name, value in every.items() if name in THROTTLED} == {
        FOLD_WINDOW
    }


def test_each_pin_sits_in_the_method_the_register_claims() -> None:
    """The cadence is a property of WHERE each pin sits.

    A pin that kept its `every=30.0` while drifting onto an
    operator-driven caller would lose the cadence the register promises
    without changing one character of its own line.
    """
    placed = {_pin_name(call): call.lineno for call in _exchange_emit_calls()}
    assert set(placed) == set(EXCHANGE_PINS)

    for method, expected in (
        ("_cmd", {ROUTED}),
        ("update_bots", {REACHED, SELECTION}),
        ("_on_global_privacy_clicked", {APPLIED, BUTTON}),
    ):
        low, high = _span(method)
        inside = {name for name, line in placed.items() if low <= line <= high}
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
        if not (
            isinstance(node, ast.FunctionDef) and node.name == "_setup_refresh_timer"
        ):
            continue
        for call in ast.walk(node):
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "start"
                and call.args
                and isinstance(call.args[0], ast.Constant)
            ):
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

    pins = [
        pin
        for pin in collect_pins(MAIN_WINDOW, REPO)
        if pin.name.startswith("exchange.")
    ]
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
        keys = [key.value for key in node.keys if isinstance(key, ast.Constant)]
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

    registry = parse_registry((REPO / REGISTRY_PATH).read_text(encoding="utf-8"))
    assert registry.parse_errors == []
    rows = {row.name: row for row in registry.rows if row.subsystem == "exchange"}
    assert set(rows) == set(EXCHANGE_PINS)

    pins = {
        pin.name: pin
        for pin in collect_pins(MAIN_WINDOW, REPO)
        if pin.name.startswith("exchange.")
    }
    for name, row in rows.items():
        assert row.file == "src/gui/main_window.py", name
        assert row.line == pins[name].line, (
            f"{name}: register says {row.line}, the pin is at " f"{pins[name].line}"
        )
