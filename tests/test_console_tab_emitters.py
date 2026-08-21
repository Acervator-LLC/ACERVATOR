"""Pins the five Console emitters -- queue item #10.7, subsystem `console`.

    console.14.001.invariant.records_rendered
    console.14.002.invariant.view_holds_rendered
    console.14.003.invariant.drain_alive
    console.14.004.postcondition.pause_quiets_both_panes
    console.14.005.postcondition.pause_buffer_delivered

THE TAB IS A CONSUMER OF THE SINK EVERY PIN WRITES TO, AND THAT IS
SETTLED HERE BEFORE ANY PIN IS READ. `MainWindow._drain_signals` runs on
a 500 ms `QTimer`, calls `sink.since(self._signal_seq)` and renders into
`_signal_view`. An `emit` anywhere on that path writes a record into the
collection the method is draining; the next tick reads it and emits
again, so the pin's own RATE becomes a function of the quantity it
measures.

`every=` does not fix that. It slows the loop and leaves the coupling
in place, and `signal_contract.emit` never folds a FAILING check -- so
the one state worth reporting is the one state that would run straight
back into its own input.

THE COUPLING IS BROKEN BY MAKING THE EMISSION RATE INDEPENDENT OF THE
SINK. `_drain_signals` writes five integers and emits nothing.
`_emit_console_health`, on its own 5000 ms timer, is the only reader,
and it writes at most three records per interval whatever the sink
holds. Four tests drive that rather than asserting it:

  test_the_drain_emits_nothing_on_any_path        the source, via the
                                                  harness's own pin
                                                  definition
  test_two_hundred_drains_do_not_grow_the_sink    the fixed point
  test_the_write_rate_does_not_depend_on_the_drain  0 drains and 200
                                                  drains, same count
  test_a_pin_on_the_drain_path_really_does_run_away   the POSITIVE
                                                  CONTROL: the refused
                                                  design, driven, so
                                                  the three greens
                                                  above are a fact
                                                  about this code and
                                                  not about arithmetic

THE PINS' OWN RECORDS MOVE BOTH SIDES OF EVERY COMPARISON BY THE SAME
AMOUNT. A console record is read once and rendered once, so
`read - rendered` is unchanged by it; it adds one pane block and one
rendered line, so both sides of `14-002` move together; it changes no
tick count at all. `evicted` is the one quantity that grows with the
pins' own traffic, which is why it rides in `context` as a number and is
part of no expectation.

THIS TAB HAS A CADENCE, like Asset Charts and unlike History and
Trading. `14-001`, `14-002` and `14-003` fire on the health timer and
carry `every=30.0`, so item #14 may read silence from any of them as a
stopped emitter. `14-004` and `14-005` are toggle pins driven by the
operator's finger, and `14-005` fires on the RESUME half only.
`test_the_cadence_declaration_is_what_the_source_does` holds that split
against the syntax tree.

ONE PIN CARRIES A DURATION AND IT IS THE ONLY ONE THAT MAY (E8).
`14-005` is a postcondition behind a real bounded operation: the resume
drain paints up to `_buffer_max` lines into a widget on the GUI thread.

WHAT THE TAB HIDES.
  `14-001` -- the watermark moves to `new[-1].seq` and the render then
  takes `new[-200:]`. Anything above 200 in one window is discarded
  after the watermark has already passed it and can never be read again
  by this consumer.
  `test_records_the_slice_threw_away_after_the_watermark_moved_are_reported`
  drives 250 records through one pass and then asks the sink for them
  back, which returns nothing.
  `14-004` -- the drain gates on `self._console_paused` and the pause
  button's own docstring says one control quiets both panes. That
  attribute is assigned NOWHERE in `src/` or `main.py`, so the signals
  pane is not quieted at all.
  `test_the_flag_the_drain_reads_is_assigned_nowhere_in_the_tree` reads
  the tree, and the pin reports `ok` False on every pause.

WHAT IS REAL HERE AND WHAT IS A STAND-IN. The `QPlainTextEdit`s and
their real 2000-block caps, the `QPushButton`, the `QLabel`, the
`QTimer`s, the four `MainWindow` methods themselves and the `SignalSink`
are all real. `_QtLogHandler` is declared INSIDE
`MainWindow._setup_ui`, so reaching it means constructing a
`MainWindow`, which builds every tab and reads the operator's own state
off disk. `14-005` therefore uses a stand-in for the handler alone, the
way `tests/test_asset_charts_emitters.py` stands in for
`ChartDataFetcher`. The failure that pin exists to catch -- a delivery
the pane's own block cap eats -- is a property of the REAL widget and is
driven through it.

NOTHING HERE TOUCHES `~/.acervator` OR `~/.acervator_logs`. No
`MainWindow` is constructed, no settings manager and no bot manager
exist, and the sink is in memory and is never given a path.
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

RENDERED = "console.14.001.invariant.records_rendered"
HOLDS = "console.14.002.invariant.view_holds_rendered"
ALIVE = "console.14.003.invariant.drain_alive"
QUIETS = "console.14.004.postcondition.pause_quiets_both_panes"
DELIVERED = "console.14.005.postcondition.pause_buffer_delivered"

CONSOLE_PINS = (RENDERED, HOLDS, ALIVE, QUIETS, DELIVERED)

# The two toggle pins. The operator's finger is their cadence.
UNTHROTTLED = (QUIETS, DELIVERED)

MAIN_WINDOW = REPO / "src" / "gui" / "main_window.py"

# The production values, restated so the tests drive the real geometry.
PANE_BLOCKS = 2000
SLICE_CAP = 200

# Substrings that must never appear in a record this tab writes. A
# context is written to disk, and a bot id is operator-chosen text the
# privacy registry masks in the bot table.
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


class _Handler:
    """A stand-in for `_QtLogHandler`, which is a local of `_setup_ui`.

    It carries the four members `_toggle_console_pause` reads --
    `buffered_count()`, `_buffer_dropped`, `_buffer_max`, `_paused` --
    and its `set_paused` drains into the REAL widget through the same
    cursor-and-insertText shape the production `_append_to_widget` uses,
    so the widget's own block cap applies to the delivery exactly as it
    does live.

    `delay` is slept inside `set_paused`, which is the span `14-005`'s
    duration bracket claims to measure.
    """

    def __init__(self, widget: Any, *, cap: int = 5000,
                 delay: float = 0.0) -> None:
        self._te = widget
        self._paused = False
        self._buffer: list[str] = []
        self._buffer_max = cap
        self._buffer_dropped = 0
        self._delay = delay
        self.set_paused_calls = 0

    # -- the production surface ----------------------------------------

    def buffered_count(self) -> int:
        return len(self._buffer)

    def set_paused(self, paused: bool) -> None:
        self.set_paused_calls += 1
        self._paused = bool(paused)
        if self._delay:
            import time as _t

            _t.sleep(self._delay)
        if not self._paused and self._buffer:
            for msg in self._buffer:
                self._paint(msg)
            self._buffer.clear()
            if self._buffer_dropped > 0:
                self._paint(
                    f"[CONSOLE PAUSE] {self._buffer_dropped} messages "
                    f"dropped (buffer cap={self._buffer_max})")
                self._buffer_dropped = 0

    # -- what a logger call does ---------------------------------------

    def log(self, msg: str) -> None:
        """One record arriving. Buffers while paused, paints otherwise."""
        if self._paused:
            if len(self._buffer) >= self._buffer_max:
                self._buffer_dropped += 1
                return
            self._buffer.append(msg)
            return
        self._paint(msg)

    def _paint(self, msg: str) -> None:
        from PySide6.QtGui import QColor, QTextCharFormat

        cursor = self._te.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(170, 170, 170))
        if self._te.document().isEmpty():
            cursor.insertText(msg, fmt)
        else:
            cursor.insertText("\n" + msg, fmt)


@contextlib.contextmanager
def _console(qapp: QApplication, *, handler_cap: int = 5000,
             handler_delay: float = 0.0) -> Iterator[Any]:
    """The four REAL `MainWindow` methods over REAL Console widgets.

    No `MainWindow` is constructed. The methods are taken off the class
    and bound to an object that owns exactly the attributes they read --
    the pattern `tests/test_signal_timing.py` already drives
    `_drain_signals` with.

    `_console_paused` is DELIBERATELY NOT SET, because production never
    sets it either. Giving it a value here would hide the defect
    `14-004` exists to report.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QLabel, QPlainTextEdit, QPushButton

    from src.gui.main_window import MainWindow

    driven = type("DrivenConsole", (), {
        "_drain_signals": MainWindow._drain_signals,
        "_emit_console_health": MainWindow._emit_console_health,
        "_toggle_console_pause": MainWindow._toggle_console_pause,
        "_refresh_console_pause_indicator":
            MainWindow._refresh_console_pause_indicator,
    })()

    driven._signal_view = QPlainTextEdit()
    driven._signal_view.setReadOnly(True)
    driven._signal_view.setMaximumBlockCount(PANE_BLOCKS)
    driven._console = QPlainTextEdit()
    driven._console.setReadOnly(True)
    driven._console.setMaximumBlockCount(PANE_BLOCKS)

    driven._signal_seq = 0
    driven._signal_drain_ticks = 0
    driven._signal_read = 0
    driven._signal_rendered = 0
    driven._signal_slice_dropped = 0
    driven._signal_health_ticks_seen = 0

    driven._signal_timer = QTimer()
    driven._signal_timer.setInterval(500)
    driven._signal_timer.start()
    driven._console_health_timer = QTimer()
    driven._console_health_timer.setInterval(5000)
    driven._console_health_timer.start()
    driven._console_pause_refresh = QTimer()
    driven._console_pause_refresh.setInterval(500)

    driven._console_pause_btn = QPushButton("Pause")
    driven._console_pause_btn.setCheckable(True)
    driven._console_pause_indicator = QLabel("")
    driven._console_log_handler = _Handler(
        driven._console, cap=handler_cap, delay=handler_delay)

    try:
        yield driven
    finally:
        driven._signal_timer.stop()
        driven._console_health_timer.stop()
        driven._console_pause_refresh.stop()
        driven._signal_view.deleteLater()
        driven._console.deleteLater()
        driven._console_pause_btn.deleteLater()
        driven._console_pause_indicator.deleteLater()
        qapp.processEvents()


# ── sink helpers ───────────────────────────────────────────────────────


@contextlib.contextmanager
def _collect() -> Iterator[SignalSink]:
    """Install a fresh sink and restore the PREVIOUS one, never None.

    `set_sink` is process-global; restoring None would switch the
    instrument off for whatever ran before this test. The rate-limit
    windows are cleared too, because three of these five pins carry
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


def _seed(sink: SignalSink, count: int, name: str = "probe.seed") -> None:
    """Put `count` ordinary records in the sink for the drain to find."""
    for index in range(count):
        sink.emit(name, actual=index)


def _look(stub: Any) -> None:
    """One health pass with the 30 s fold window cleared first.

    The throttle is real and is asserted elsewhere. Where a test wants
    every pass admitted it says so here, in one place, rather than by
    sleeping.
    """
    sc.reset_throttle()
    stub._emit_console_health()


# ── the syntax tree ────────────────────────────────────────────────────


def _console_emit_calls() -> list[ast.Call]:
    """Every `_co_emit(...)` call node in `main_window.py`.

    Read from the syntax tree, the way `tools/emitter_registry_check.py`
    reads them. A regex over the source would answer a different
    question.
    """
    tree = ast.parse(MAIN_WINDOW.read_text(encoding="utf-8"))
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_co_emit"]


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
    """The first and last line of one method of `MainWindow`."""
    tree = ast.parse(MAIN_WINDOW.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.FunctionDef) and node.name == function
                and node.end_lineno is not None):
            return (node.lineno, node.end_lineno)
    missing = f"{function} not found in {MAIN_WINDOW}"
    raise AssertionError(missing)


# ── THE RECURSION. Settled first, because nothing else is safe. ────────


def test_the_drain_emits_nothing_on_any_path() -> None:
    """No pin sits inside `_drain_signals`, by the harness's own rule.

    Asked of `tools/emitter_registry_check.collect_pins`, which resolves
    a pin through the syntax tree rather than by matching text, so an
    aliased import or a renamed local cannot slip one past this. A
    keyword search for `emit` would answer a different, weaker question.
    """
    from tools.emitter_registry_check import collect_pins

    low, high = _span("_drain_signals")
    inside = [pin for pin in collect_pins(MAIN_WINDOW, REPO)
              if low <= pin.line <= high]
    assert inside == [], (
        "a pin inside the drain writes into the sink it is draining: "
        f"{[(p.name, p.line) for p in inside]}")

    # The sentinel. If the span ever silently resolved to the wrong
    # function this test would pass over nothing at all.
    all_pins = collect_pins(MAIN_WINDOW, REPO)
    assert len([p for p in all_pins if p.name.startswith("console.")]) == 5
    assert high > low


def test_two_hundred_drains_do_not_grow_the_sink(
        qapp: QApplication) -> None:
    """THE FIXED POINT, driven on the real drain and a real sink.

    With no other producer the sink must not gain one record however
    many times the drain runs. A pin on that path would make every tick
    add at least one, and the pane would fill with itself.
    """
    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 3)
        assert sink.count() == 3
        for _ in range(200):
            stub._drain_signals()
            assert sink.count() == 3, "the drain wrote into its own input"
        assert stub._signal_drain_ticks == 200
        assert stub._signal_read == 3
        assert stub._signal_rendered == 3
        # The pane stopped growing with the first pass, too.
        assert stub._signal_view.blockCount() == 3


def test_the_write_rate_does_not_depend_on_the_drain(
        qapp: QApplication) -> None:
    """The emission rate is a function of the clock and of nothing else.

    Five health passes with the drain never called, and five with it
    called two hundred times, must leave the SAME number of records.
    That is what "independent of the sink" means, and it is the property
    `every=` cannot supply.
    """
    def _run(drains_per_look: int) -> int:
        with _collect() as sink, _console(qapp) as stub:
            _seed(sink, 5)
            for _ in range(5):
                for _ in range(drains_per_look):
                    stub._drain_signals()
                _look(stub)
            return sink.count() - 5          # discard the seed

    quiet = _run(0)
    busy = _run(40)
    assert quiet == busy == 15, (quiet, busy)


def test_a_pin_on_the_drain_path_really_does_run_away(
        qapp: QApplication) -> None:
    """THE POSITIVE CONTROL for the two tests above.

    A green from an instrument that cannot go red is evidence of
    nothing, so the REFUSED design is driven here beside the shipped
    one, over the same sink and the same number of ticks. The refused
    drain emits one record per record it renders plus one summary --
    which is what a naive `13-004`-shaped pin on this path would do --
    and its own output is its next input.

    Thirty ticks. The shipped drain leaves the seed untouched. The
    refused one leaves hundreds.
    """
    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 1)
        for _ in range(30):
            stub._drain_signals()
        shipped = sink.count()

    with _collect() as sink:
        _seed(sink, 1)
        watermark = 0
        for _ in range(30):
            arrived = sink.since(watermark)
            if not arrived:
                continue
            watermark = arrived[-1].seq
            for _ in arrived:
                sink.emit("control.runaway.per_record", actual=1)
            sink.emit("control.runaway.summary", actual=len(arrived))
        runaway = sink.count()

    assert shipped == 1
    assert runaway > 200, runaway
    assert runaway > shipped * 100


# ── 14-001  every record the watermark consumed reached the pane ───────


def test_records_rendered_is_reported(qapp: QApplication) -> None:
    """A quiet window: everything read was rendered."""
    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 5)
        stub._drain_signals()
        stub._emit_console_health()
        rec = _only(sink, RENDERED)
    assert rec.ok is True, rec.context
    assert rec.actual == 5
    assert rec.expected == 5
    assert rec.context["lost_to_slice"] == 0
    assert rec.context["slice_cap"] == SLICE_CAP
    assert rec.context["watermark"] == 5
    assert rec.context["drain_ticks"] == 1
    assert rec.duration is None


def test_records_the_slice_threw_away_after_the_watermark_moved_are_reported(
        qapp: QApplication) -> None:
    """THE FALSIFIER for `14-001`, and it is a live defect.

    `_drain_signals` assigns the watermark from `new[-1].seq` and THEN
    renders `new[-200:]`. 250 records inside one 500 ms window means 50
    of them are stepped over by the watermark and never drawn. The sink
    is asked for them afterwards and has nothing to give: they are gone
    from this consumer for good, and until this pin nothing said so.
    """
    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 250)
        stub._drain_signals()
        # The 50 are unreachable. Not slow to fetch -- gone.
        assert sink.since(stub._signal_seq) == ()
        assert stub._signal_view.blockCount() == SLICE_CAP
        stub._emit_console_health()
        rec = _only(sink, RENDERED)
    assert rec.ok is False
    assert rec.actual == 200
    assert rec.expected == 250
    assert rec.context["lost_to_slice"] == 50
    assert rec.context["watermark"] == 250


# ── 14-002  the pane holds the window the drain wrote ──────────────────


def test_the_pane_holds_what_the_drain_wrote(qapp: QApplication) -> None:
    """Under the cap, block count and ledger agree exactly."""
    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 4)
        stub._drain_signals()
        stub._emit_console_health()
        rec = _only(sink, HOLDS)
    assert rec.ok is True, rec.context
    assert rec.actual == 4
    assert rec.expected == 4
    assert rec.context["evicted"] == 0
    assert rec.context["max_blocks"] == PANE_BLOCKS
    assert rec.context["rendered"] == 4
    assert rec.duration is None


def test_a_pane_emptied_behind_the_drain_is_reported(
        qapp: QApplication) -> None:
    """THE FALSIFIER for `14-002`.

    The Clear button is wired straight to `self._console.clear` -- the
    LOG pane. Point it at the signals pane as well, which is one
    plausible line of a future edit, and the drain goes on believing it
    wrote four lines while the pane holds none. Counting what the loop
    appended could not see that. Asking the widget can.
    """
    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 4)
        stub._drain_signals()
        stub._signal_view.clear()
        stub._emit_console_health()
        rec = _only(sink, HOLDS)
    assert rec.ok is False
    assert rec.actual == 1                  # an empty pane holds one block
    assert rec.expected == 4
    assert rec.context["evicted"] == 3


def test_the_block_cap_is_reported_as_a_number_and_not_as_a_red(
        qapp: QApplication) -> None:
    """A saturated pane is by design, so it must not paint the pin red.

    2600 records drained 200 at a time -- the slice's own limit, so
    nothing is lost on the way in. The pane keeps its last 2000 and
    reports the 600 that scrolled out as a count beside a GREEN verdict.
    Expecting zero evictions here would paint the instrument red on
    ordinary use, which is the `06-014` defect in a new place.
    """
    with _collect() as sink, _console(qapp) as stub:
        for _ in range(13):
            _seed(sink, SLICE_CAP)
            stub._drain_signals()
        assert stub._signal_rendered == 2600
        assert stub._signal_slice_dropped == 0
        stub._emit_console_health()
        rec = _only(sink, HOLDS)
    assert rec.ok is True, rec.context
    assert rec.actual == PANE_BLOCKS
    assert rec.expected == PANE_BLOCKS
    assert rec.context["evicted"] == 600
    assert rec.context["rendered"] == 2600


# ── 14-003  the drain is alive, asked from outside the drain ───────────


def test_a_live_drain_is_reported(qapp: QApplication) -> None:
    """The tick counter moved between two looks."""
    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 2)
        stub._drain_signals()
        stub._drain_signals()
        stub._emit_console_health()
        rec = _only(sink, ALIVE)
    assert rec.ok is True, rec.context
    assert rec.actual is True
    assert rec.expected is True
    assert rec.context["ticks_since_last_look"] == 2
    assert rec.context["drain_timer_active"] is True
    assert rec.context["drain_interval_ms"] == 500
    assert rec.context["look_interval_ms"] == 5000
    assert rec.duration is None


def test_a_drain_that_stopped_is_reported(qapp: QApplication) -> None:
    """THE FALSIFIER for `14-003`, and the fault the drain cannot report.

    A drain that has stopped emits nothing, and nothing is exactly what
    a healthy quiet tab emits. Only a counter read from OUTSIDE the
    drain separates them.

    THE THROTTLE IS LEFT STANDING ON PURPOSE. Both looks happen inside
    one 30 s fold window, so the second record can only appear because
    the synchroniser never folds a failing check. That is asserted here
    rather than taken from the module docstring.
    """
    with _collect() as sink, _console(qapp) as stub:
        stub._drain_signals()
        stub._emit_console_health()             # green, and admitted
        stub._signal_timer.stop()               # the timer dies
        stub._emit_console_health()             # no tick since the last
        got = _records(sink, ALIVE)
    assert len(got) == 2, [r.ok for r in got]
    assert got[0].ok is True
    assert got[1].ok is False
    assert got[1].actual is False
    assert got[1].expected is True
    assert got[1].context["ticks_since_last_look"] == 0
    assert got[1].context["drain_timer_active"] is False


# ── 14-004  the Pause button's claim to quiet both panes ───────────────


def test_a_pause_that_quiets_only_one_pane_is_reported(
        qapp: QApplication) -> None:
    """THE FALSIFIER for `14-004`, and it is a live defect.

    `_drain_signals` gates on `self._console_paused` and its docstring
    says the button "honours the same Pause the log pane uses, so one
    control quiets both". Nothing in the tree ever assigns that
    attribute, so the log pane stops and the signals pane does not.
    """
    with _collect() as sink, _console(qapp) as stub:
        stub._console_pause_btn.setChecked(True)
        stub._toggle_console_pause()
        rec = _only(sink, QUIETS)
        # The defect itself, read off the object the drain consults.
        assert getattr(stub, "_console_paused", None) is None
        assert stub._console_log_handler._paused is True
    assert rec.ok is False
    assert rec.actual is False
    assert rec.expected is True
    assert rec.context["log_pane_paused"] is True
    assert rec.context["button_checked"] is True
    assert rec.duration is None


def test_a_resume_leaves_both_panes_agreeing(qapp: QApplication) -> None:
    """The other side. Resumed, both panes are running and the pin is
    green -- so the red above is a verdict about the pause and not a pin
    that is red whatever happens."""
    with _collect() as sink, _console(qapp) as stub:
        stub._console_pause_btn.setChecked(True)
        stub._toggle_console_pause()
        stub._console_pause_btn.setChecked(False)
        stub._toggle_console_pause()
        rec = _records(sink, QUIETS)[-1]
    assert rec.ok is True, rec.context
    assert rec.actual is False
    assert rec.expected is False
    assert rec.context["log_pane_paused"] is False


def test_the_flag_the_drain_reads_is_assigned_nowhere_in_the_tree() -> None:
    """The measurement behind `14-004`, read off the syntax tree.

    A comment claiming the defect would age. This walks every module
    under `src/` plus `main.py` for an assignment to `_console_paused`
    and finds none, against a control that the same walk DOES find the
    neighbouring `_signal_seq`. Without the control a zero here would be
    a claim about the walk rather than about the tree.
    """
    targets = [*sorted((REPO / "src").rglob("*.py")), REPO / "main.py"]

    def _assigned(attribute: str) -> list[str]:
        hits: list[str] = []
        for path in targets:
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8",
                                                errors="replace"))
            except SyntaxError:                     # pragma: no cover
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Assign, ast.AugAssign,
                                         ast.AnnAssign)):
                    continue
                written = (node.targets if isinstance(node, ast.Assign)
                           else [node.target])
                for target in written:
                    if (isinstance(target, ast.Attribute)
                            and target.attr == attribute):
                        hits.append(f"{path.name}:{node.lineno}")
        return hits

    assert _assigned("_signal_seq"), "the control found nothing; the walk is broken"
    assert _assigned("_console_paused") == []


# ── 14-005  the resume put the buffer on the pane ──────────────────────


def test_a_resume_delivers_every_buffered_line(
        qapp: QApplication) -> None:
    """The operator pauses, thirty lines arrive, the resume paints them."""
    with _collect() as sink, _console(qapp) as stub:
        stub._console_pause_btn.setChecked(True)
        stub._toggle_console_pause()
        for index in range(30):
            stub._console_log_handler.log(f"line {index}")
        assert stub._console.document().isEmpty()
        stub._console_pause_btn.setChecked(False)
        stub._toggle_console_pause()
        rec = _only(sink, DELIVERED)
        assert stub._console.blockCount() == 30
    assert rec.ok is True, rec.context
    assert rec.actual == 30
    assert rec.expected == 30
    assert rec.context["held"] == 30
    assert rec.context["dropped_at_cap"] == 0
    assert rec.context["blocks_before"] == 0
    assert rec.context["buffer_cap"] == 5000
    assert rec.context["max_blocks"] == PANE_BLOCKS
    assert rec.duration is not None and rec.duration >= 0.0


def test_a_resume_the_pane_cap_eats_is_reported(
        qapp: QApplication) -> None:
    """THE FALSIFIER for `14-005`, and the loss the operator feels.

    The buffer held every line, which is what it is for. The pane's own
    2000-block cap then threw 200 of them away a moment after the buffer
    handed them over -- and the operator paused precisely to keep them.
    Reading the widget back out is the only way to see it; the buffer
    reports a clean delivery.
    """
    with _collect() as sink, _console(qapp) as stub:
        for index in range(1500):
            stub._console_log_handler.log(f"early {index}")
        assert stub._console.blockCount() == 1500
        stub._console_pause_btn.setChecked(True)
        stub._toggle_console_pause()
        for index in range(700):
            stub._console_log_handler.log(f"held {index}")
        assert stub._console_log_handler.buffered_count() == 700
        stub._console_pause_btn.setChecked(False)
        stub._toggle_console_pause()
        rec = _only(sink, DELIVERED)
        assert stub._console_log_handler.buffered_count() == 0
    assert rec.ok is False
    assert rec.actual == PANE_BLOCKS
    assert rec.expected == 2200
    assert rec.context["held"] == 700
    assert rec.context["blocks_before"] == 1500
    assert rec.context["dropped_at_cap"] == 0


def test_the_buffer_cap_adds_the_notice_line_to_what_the_resume_owes(
        qapp: QApplication) -> None:
    """The second loss, and the pin counts the notice `set_paused` adds.

    Driven on a small buffer cap so the drop path runs in a test rather
    than being argued about: five held, three dropped, and the resume
    owes six lines because it writes a warning naming the drops.
    """
    with _collect() as sink, _console(qapp, handler_cap=5) as stub:
        stub._console_pause_btn.setChecked(True)
        stub._toggle_console_pause()
        for index in range(8):
            stub._console_log_handler.log(f"line {index}")
        assert stub._console_log_handler.buffered_count() == 5
        assert stub._console_log_handler._buffer_dropped == 3
        stub._console_pause_btn.setChecked(False)
        stub._toggle_console_pause()
        rec = _only(sink, DELIVERED)
    assert rec.ok is True, rec.context
    assert rec.actual == 6
    assert rec.expected == 6
    assert rec.context["held"] == 5
    assert rec.context["dropped_at_cap"] == 3
    assert rec.context["buffer_cap"] == 5


def test_the_pause_press_itself_writes_no_delivery_record(
        qapp: QApplication) -> None:
    """`14-005` is the RESUME half only.

    The pause press delivers nothing, so there is nothing to judge and a
    record there would be a vacuous zero. `14-004` still fires on both
    halves, which is what keeps this from being silence.
    """
    with _collect() as sink, _console(qapp) as stub:
        stub._console_pause_btn.setChecked(True)
        stub._toggle_console_pause()
    assert _records(sink, DELIVERED) == []
    assert len(_records(sink, QUIETS)) == 1


def test_the_duration_tracks_two_different_resume_workloads(
        qapp: QApplication) -> None:
    """THE CONTROL for the duration on `14-005`.

    A number that is the same for a quick resume and a slow one is not a
    measurement. Two runs of the same method over the same widget, with
    the only difference inside `set_paused`, must differ by at least the
    delay -- which also proves the bracket spans that call rather than
    reporting a constant beside it.
    """
    def _resume(delay: float) -> float:
        with _collect() as sink, _console(qapp, handler_delay=delay) as stub:
            stub._console_pause_btn.setChecked(True)
            stub._toggle_console_pause()
            stub._console_log_handler.log("one held line")
            stub._console_pause_btn.setChecked(False)
            stub._toggle_console_pause()
            rec = _only(sink, DELIVERED)
        assert rec.duration is not None
        return float(rec.duration)

    quick = _resume(0.0)
    slow = _resume(0.30)
    assert slow >= quick + 0.20, (quick, slow)
    assert quick < 0.20


# ── the shape, read off the syntax tree ────────────────────────────────


def test_only_the_resume_pin_carries_a_duration() -> None:
    """E8 in this tab: one postcondition behind a real bounded
    operation, and nothing else. The other four read counters and a
    flag."""
    carriers = {_pin_name(call) for call in _console_emit_calls()
                if _keyword(call, "duration") is not None}
    assert carriers == {DELIVERED}


def test_the_cadence_declaration_is_what_the_source_does() -> None:
    """Item #14 reads this split, so it is asserted and not narrated.

    Three pins fire on the 5000 ms health timer and fold to one record
    per 30 s window. The two toggle pins carry no throttle: the
    operator's finger is their rate limit.
    """
    every: dict[str, Any] = {}
    for call in _console_emit_calls():
        node = _keyword(call, "every")
        every[_pin_name(call)] = (node.value
                                  if isinstance(node, ast.Constant)
                                  else None)
    assert set(every) == set(CONSOLE_PINS)
    assert {name for name, value in every.items() if value is None} == set(
        UNTHROTTLED)
    assert {value for name, value in every.items()
            if name not in UNTHROTTLED} == {30.0}


def test_the_cadence_pins_all_live_in_the_health_pass() -> None:
    """The cadence is a property of WHERE the three pins sit.

    All three are inside `_emit_console_health`, which the health timer
    drives; neither toggle pin is. A pin that drifted into the drain
    would fail `test_the_drain_emits_nothing_on_any_path`, and one that
    drifted out of the health pass onto some other caller would keep its
    `every=30.0` while losing the cadence the register promises. This
    holds the second half.
    """
    low, high = _span("_emit_console_health")
    placed = {_pin_name(call): low <= call.lineno <= high
              for call in _console_emit_calls()}
    assert {name for name, inside in placed.items() if inside} == {
        RENDERED, HOLDS, ALIVE}

    toggle_low, toggle_high = _span("_toggle_console_pause")
    assert {name for name, inside in placed.items() if not inside} == set(
        UNTHROTTLED)
    for call in _console_emit_calls():
        if _pin_name(call) in UNTHROTTLED:
            assert toggle_low <= call.lineno <= toggle_high


def test_no_two_pins_share_a_line() -> None:
    """One pin per line.

    `signal_contract` keys both the fold window and the timing identity
    on (name, site), and `site` is `file:line`. Two pins on one line
    would be one identity to the wire and two to a reader.
    """
    lines = [call.lineno for call in _console_emit_calls()]
    assert len(lines) == len(set(lines)) == 5


def test_no_context_carries_credential_material_or_a_bot_id() -> None:
    """A context is written to disk. These contexts hold counts,
    intervals and booleans -- no operator text at all, and no bot id,
    which the privacy registry masks in the bot table."""
    for call in _console_emit_calls():
        node = _keyword(call, "context")
        assert isinstance(node, ast.Dict), _pin_name(call)
        rendered = ast.dump(node).lower()
        for banned in FORBIDDEN:
            assert banned not in rendered, (_pin_name(call), banned)
