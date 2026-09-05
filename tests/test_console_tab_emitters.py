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

`14-002` IS RESTATED BY ISSUE #48 AND THE RESTATEMENT IS WRITTEN DOWN,
not left to drift. The drain now draws two kinds of line -- records, and
a gap marker over a stretch the `[-200:]` slice stepped over -- so "what
the drain wrote" is `_signal_rendered + _signal_markers` rather than
`_signal_rendered` alone, and `gap_markers` rides in `context` so the
two can be taken apart in `session.jsonl`. `14-001` IS NOT RESTATED: it
asks whether every RECORD the watermark consumed reached the pane, a
marker is not a record, and a Console that quietly keeps up must stay
distinguishable in the record stream from one that quietly skips.
`test_a_marker_does_not_count_as_a_record_rendered` holds that line.

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

  WHAT ISSUE #48 THEN DID ABOUT IT, AND WHAT IT DELIBERATELY DID NOT
  DO. The records are NOT lost from the system: `SignalSink` appends
  and flushes on every emit, so everything the pane steps over is on
  disk in `~/.acervator_logs/signals/session.jsonl`. The pane is one
  consumer falling behind, and there are two ways to be behind. Advance
  the watermark only as far as the render reached and the pane falls
  further behind under sustained load, showing older and older records
  while the sink races ahead, with nothing on the screen to say whether
  it is a live monitor or a historical one -- worse than a gap. SO THE
  PANE STAYS CURRENT AND DRAWS THE GAP. `_draw_signal_gap_marker` puts
  one amber line above the slice, naming how many records were stepped
  over, saying they are NOT LOST, and naming the file they are in. The
  200-line slice and the 2000-block cap both stay: an unbounded render
  would stall the Qt GUI thread, and that is an arc of its own.
  TWO PATHS REACH THAT SLICE and the tests below drive both -- the
  resume after a long pause, which issue #49's repair created, and a
  live burst of more than 200 records inside one 500 ms window with no
  pause at all, which is what #48 was filed for and predates the
  repair.
  `14-004` -- REPAIRED, issue #49, and this is what it hid. The drain
  gates on `self._console_paused` and the pause button's own docstring
  says one control quiets both panes. That attribute was assigned
  NOWHERE in `src/` or `main.py`, so the log pane stopped and the
  signals pane under it went on scrolling. `_set_console_paused` now
  writes it and `_toggle_console_pause` calls it, so the pin is GREEN on
  a pause. `test_the_flag_the_drain_reads_is_assigned_exactly_once_in_the_tree`
  reads the tree for that one assignment against the same control, and
  `test_a_pause_that_quiets_only_one_pane_is_reported` still drives the
  pin to red -- through `_without_the_console_pause_flag`, which puts
  the pre-repair tree back for the length of one drive.

  WHAT THE REPAIR THEN HANDS TO `14-001`, AND IT IS NOT NOTHING. A
  paused drain advances NO watermark, so the sink holds the whole pause
  and the first pass after the resume reads it in one go. Driven on the
  real widgets: a backlog of 200 or fewer arrives whole; above that the
  `[-200:]` slice keeps the NEWEST 200 and `_signal_slice_dropped`
  counts the rest -- 53 records lost out of a 250-record pause, 2303 out
  of a 2500-record one -- after the watermark has already moved past
  them. The operator paused to KEEP those lines. `14-001` goes red and
  names the mechanism rather than losing them in silence, which is the
  behaviour issue #48 owns.
  `test_a_resume_delivers_the_backlog_and_the_slice_reports_what_it_ate`
  pins those numbers so #48 has a measured baseline to move.

WHAT IS REAL HERE AND WHAT IS A STAND-IN. The `QPlainTextEdit`s and
their real 2000-block caps, the `QPushButton`, the `QLabel`, the
`QTimer`s, the four `MainWindow` methods themselves and the `SignalSink`
are all real. `_QtLogHandler` lives in
`src/gui/main_tabs/console_log_handler.py`. `14-005` still uses a
stand-in for the handler alone, the way
`tests/test_asset_charts_emitters.py` stands in for `ChartDataFetcher`:
the pin brackets a drain duration, and the real handler offers no way to
lengthen one. The failure that pin exists to catch -- a delivery
the pane's own block cap eats -- is a property of the REAL widget and is
driven through it.

NOTHING HERE TOUCHES `~/.acervator` OR `~/.acervator_logs`. No
`MainWindow` is constructed, no settings manager and no bot manager
exist, and the sink is in memory and is never given a path.
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

import pytest

# `tests/conftest.py` puts the repository root on `sys.path` before any test
# module is imported, so these need no path insert above them.
from src.core import signal_contract as sc
from src.core.signal_contract import SignalSink

# Set before any fixture imports PySide6, which is this module's only
# route to Qt. Nothing above touches it.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent

if TYPE_CHECKING:  # pragma: no cover
    # Annotation only: importing PySide6 at module scope would skip the whole
    # file on a box without Qt, and the fixture scopes the skip instead.
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

# issue #48. The two strings the gap marker must carry, restated here
# so a test can assert their ABSENCE from a pane that drew nothing.
GAP_TAG = "[SIGNALS GAP]"
SIGNALS_FILE = "~/.acervator_logs/signals/session.jsonl"

# Substrings that must never appear in a record this tab writes. A bot id is
# operator-chosen text the privacy registry masks in the bot table.
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


class _Handler:
    """A stand-in for `_QtLogHandler`, which takes no injectable delay.

    It carries the four members `_toggle_console_pause` reads --
    `buffered_count()`, `_buffer_dropped`, `_buffer_max`, `_paused` --
    and its `set_paused` drains into the REAL widget through the same
    cursor-and-insertText shape the production `_append_to_widget` uses,
    so the widget's own block cap applies to the delivery exactly as it
    does live.

    `delay` is slept inside `set_paused`, which is the span `14-005`'s
    duration bracket claims to measure.
    """

    def __init__(self, widget: Any, *, cap: int = 5000, delay: float = 0.0) -> None:
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
                    f"dropped (buffer cap={self._buffer_max})"
                )
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
def _console(
    qapp: QApplication, *, handler_cap: int = 5000, handler_delay: float = 0.0
) -> Iterator[Any]:
    """The four REAL `MainWindow` methods over REAL Console widgets.

    No `MainWindow` is constructed. The methods are taken off the class
    and bound to an object that owns exactly the attributes they read --
    the pattern `tests/test_signal_timing.py` already drives
    `_drain_signals` with.

    `_console_paused` is DELIBERATELY NOT PRE-SET. A `MainWindow` does
    not carry it before the first press either: `_set_console_paused` is
    its only writer and `_toggle_console_pause` is that function's only
    caller (issue #49). Seeding it here would start every drive from a
    state production never starts from, and would hide a repair that
    stopped calling it.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QLabel, QPlainTextEdit, QPushButton

    from src.gui.main_window import MainWindow

    driven = type(
        "DrivenConsole",
        (),
        {
            "_drain_signals": MainWindow._drain_signals,
            "_emit_console_health": MainWindow._emit_console_health,
            "_toggle_console_pause": MainWindow._toggle_console_pause,
            "_refresh_console_pause_indicator": MainWindow._refresh_console_pause_indicator,
        },
    )()

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
    driven._signal_markers = 0
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
        driven._console, cap=handler_cap, delay=handler_delay
    )

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


def _pane_lines(stub: Any) -> list[str]:
    """The signals pane's own text, one entry per block."""
    return stub._signal_view.toPlainText().splitlines()


def _marker(skipped: int) -> str:
    """The gap-marker line, asked of the production helper.

    Every drawing test compares the pane against THIS, so a change to
    the wording moves them all together and none of them can go stale
    against the pane. The wording itself is pinned as a literal, once,
    in `test_the_marker_says_the_records_are_not_lost_and_where_they_are`
    -- because a round trip through the helper would pass just as
    happily if the helper said "gone".
    """
    from src.gui import main_window as mw

    return mw._signal_gap_marker_text(skipped)


def _fragment_formats(block: Any) -> list[tuple[str | None, str]]:
    """(background colour or None, foreground colour) per text fragment.

    Read off the real `QTextDocument`, which is where the difference
    between a marker and a record actually lives. Asking the source for
    a colour string would answer a different question: whether the CSS
    the drain wrote REACHED the document is exactly what `appendHtml`
    can silently drop.
    """
    from PySide6.QtCore import Qt

    out: list[tuple[str | None, str]] = []
    it = block.begin()
    while not it.atEnd():
        fragment = it.fragment()
        if fragment.isValid():
            fmt = fragment.charFormat()
            painted = fmt.background().style() != Qt.BrushStyle.NoBrush
            out.append(
                (
                    fmt.background().color().name() if painted else None,
                    fmt.foreground().color().name(),
                )
            )
        it += 1
    return out


def _without_the_console_pause_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put the tree back the way it was before the issue #49 repair.

    `_toggle_console_pause` now calls the module-level
    `_set_console_paused`, resolved through globals on every call, and
    that function is the ONLY writer of `self._console_paused` -- the
    flag `_drain_signals` gates the signals pane on. Replacing it with a
    no-op restores the exact pre-repair behaviour: the log handler is
    still paused, the attribute is never created, `_drain_signals` reads
    its `getattr(..., False)` default and the signals pane goes on
    scrolling under a stopped log pane.

    THAT IS WHY THE FALSIFIER BELOW STILL REACHES `14-004`'s FAILING
    CONDITION. The pin compares the flag the drain really reads against
    the button the operator really pressed, so it reports any genuine
    disagreement between them -- but after the repair no press produces
    one, because the press that stops the log pane now sets the flag as
    well.

    The name is asserted to exist and to be callable FIRST, for the
    reason `_without_the_reanchor` in `tests/test_exchange_tab_emitters.py`
    gives: `monkeypatch.setattr` on a renamed-away name raises, a
    hand-rolled `setattr` would not, and a falsifier that quietly
    patches nothing proves nothing. This is therefore also the positive
    control for the repair -- rename or delete `_set_console_paused` and
    the test that calls this fails.
    """
    from src.gui import main_window as mw

    assert callable(mw._set_console_paused)

    def _pre_repair_no_op(_window: object, *, paused: bool) -> None:
        """Take the argument and write nothing, as the tree once did.

        That is exactly what issue #49 found: the log handler is paused
        and the flag the signals drain reads is never created at all.

        `paused` is spelled out rather than swallowed by `**kwargs` so
        this stand-in carries the SAME signature as the function it
        replaces. A repair that changed the call back to a positional
        argument would raise here instead of quietly patching a
        function nobody calls any more.
        """
        assert isinstance(paused, bool)

    monkeypatch.setattr(mw, "_set_console_paused", _pre_repair_no_op, raising=True)


def _without_the_gap_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put the tree back the way it was before the issue #48 repair.

    `_drain_signals` now calls the module-level
    `_draw_signal_gap_marker`, resolved through globals on every call,
    and that function is the ONLY thing that puts a gap marker on the
    signals pane. Replacing it with a stand-in that draws nothing and
    returns zero restores the exact pre-repair behaviour: the watermark
    still moves past the whole read, the `[-200:]` slice still throws
    the rest away, `_signal_slice_dropped` still counts them, and the
    pane still shows the newest 200 with nothing to say the others ever
    existed.

    RETURNING ZERO IS PART OF THE STAND-IN AND NOT AN ACCIDENT. The
    drain adds this return value to `_signal_markers`, which
    `console.14.002` counts as part of what the drain drew. A stand-in
    that drew nothing and returned one would leave the pin red about a
    block that is not there, and the falsifier would then be measuring
    its own bug instead of the pre-repair pane.

    The name is asserted to exist and to be callable FIRST, for the
    reason `_without_the_console_pause_flag` gives above and
    `_without_the_reanchor` in `tests/test_exchange_tab_emitters.py`
    gave before it: `monkeypatch.setattr` on a renamed-away name
    raises, a hand-rolled `setattr` would not, and a falsifier that
    quietly patches nothing proves nothing. This is therefore also the
    positive control for the repair -- rename or delete
    `_draw_signal_gap_marker` and the test that calls this fails.
    """
    from src.gui import main_window as mw

    assert callable(mw._draw_signal_gap_marker)

    def _pre_repair_no_op(_view: object, *, skipped: int) -> int:
        """Take the count and draw nothing, as the tree once did.

        `skipped` is spelled out rather than swallowed by `**kwargs` so
        this stand-in carries the SAME signature as the function it
        replaces. A repair that went back to a positional argument
        would raise here instead of quietly patching a function nobody
        calls any more.
        """
        assert isinstance(skipped, int)
        return 0

    monkeypatch.setattr(mw, "_draw_signal_gap_marker", _pre_repair_no_op, raising=True)


def test_two_hundred_drains_do_not_grow_the_sink(qapp: QApplication) -> None:
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


def test_the_write_rate_does_not_depend_on_the_drain(qapp: QApplication) -> None:
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
            return sink.count() - 5  # discard the seed

    quiet = _run(0)
    busy = _run(40)
    assert quiet == busy == 15, (quiet, busy)


def test_a_pin_on_the_drain_path_really_does_run_away(qapp: QApplication) -> None:
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
    qapp: QApplication,
) -> None:
    """THE FALSIFIER for `14-001`, and it is a live defect.

    `_drain_signals` assigns the watermark from `new[-1].seq` and THEN
    renders `new[-200:]`. 250 records inside one 500 ms window means 50
    of them are stepped over by the watermark and never drawn. The sink
    is asked for them afterwards and has nothing to give: THIS CONSUMER
    cannot reach them again, and until this pin nothing said so.

    RESTATED FOR ISSUE #48, TWO CLAUSES OF IT. "Gone for good" was
    wrong about the system and is now wrong about the pane as well.
    The sink appends and flushes on every emit, so the 50 are on disk
    in `~/.acervator_logs/signals/session.jsonl` -- what `sink.since`
    cannot return is a fact about the in-memory window, not about the
    records. And the pane no longer holds exactly `SLICE_CAP` blocks in
    silence: it holds one more, the gap marker, above the slice it
    describes. The pin's own numbers are UNCHANGED, which is the point
    -- the marker is drawn, not counted as a record.
    """
    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 250)
        stub._drain_signals()
        # The 50 are out of this consumer's reach. Not slow to fetch --
        # not in the window. They are still in `session.jsonl`.
        assert sink.since(stub._signal_seq) == ()
        assert stub._signal_view.blockCount() == SLICE_CAP + 1
        assert stub._signal_markers == 1
        assert _pane_lines(stub)[0] == _marker(50)
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


def test_a_pane_emptied_behind_the_drain_is_reported(qapp: QApplication) -> None:
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
    assert rec.actual == 1  # an empty pane holds one block
    assert rec.expected == 4
    assert rec.context["evicted"] == 3


def test_the_block_cap_is_reported_as_a_number_and_not_as_a_red(
    qapp: QApplication,
) -> None:
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
        stub._emit_console_health()  # green, and admitted
        stub._signal_timer.stop()  # the timer dies
        stub._emit_console_health()  # no tick since the last
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
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE FALSIFIER for `14-004`, reached rather than waited for.

    It WAS a live defect and issue #49 closed it, so the pin is green
    on a pause now and the failing condition has to be reached another
    way.

    `_drain_signals` gates on `self._console_paused` and its docstring
    says the button "honours the same Pause the log pane uses, so one
    control quiets both". Before the repair nothing in the tree ever
    assigned that attribute, so the log pane stopped and the signals
    pane did not. `_without_the_console_pause_flag` puts that tree back
    for the length of this drive -- the same move
    `tests/test_exchange_tab_emitters.py` makes for `15-001` and
    `15-003`.

    THE ASSERTIONS ARE UNCHANGED AND THE DRIVE IS UNCHANGED. Only the
    route to the red moved. `getattr(..., None) is None` is the
    pre-repair condition EXACTLY: it fails if the repair merely wrote
    the wrong value, and it fails if the falsifier patched nothing at
    all.

    The pane is then driven, because a pin's opinion is not the defect.
    Five records arrive under a pressed Pause and the signals pane
    renders six -- the five plus the pause record itself -- while the
    log pane holds nothing.
    """
    _without_the_console_pause_flag(monkeypatch)
    with _collect() as sink, _console(qapp) as stub:
        stub._console_pause_btn.setChecked(True)
        stub._toggle_console_pause()
        rec = _only(sink, QUIETS)
        # The defect itself, read off the object the drain consults.
        assert getattr(stub, "_console_paused", None) is None
        assert stub._console_log_handler._paused is True
        # And the consequence, read off the pane rather than the pin.
        assert stub._signal_view.document().isEmpty()
        _seed(sink, 5)
        stub._console_log_handler.log("one line the operator wanted kept")
        stub._drain_signals()
        assert stub._signal_view.blockCount() == 6, (
            "the paused drain rendered nothing; the falsifier patched "
            "nothing and this test proves nothing"
        )
        assert stub._console.document().isEmpty()
    assert rec.ok is False
    assert rec.actual is False
    assert rec.expected is True
    assert rec.context["log_pane_paused"] is True
    assert rec.context["button_checked"] is True
    assert rec.duration is None


def test_a_pause_quiets_the_signals_pane_as_well_as_the_log(qapp: QApplication) -> None:
    """THE REPAIR, issue #49, driven rather than asserted about.

    ONE PRESS, TWO MECHANISMS. `set_paused` buffers the log pane;
    `_set_console_paused` writes the flag `_drain_signals` reads. This
    is the drive the falsifier above inverts: forty records and four
    log lines arrive across four drain ticks under a pressed Pause, and
    both panes hold exactly what they held at the press.

    `14-004` is green here, which is the whole point of the repair: the
    emitter that found this defect now reports it repaired.
    """
    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 10)
        stub._console_log_handler.log("before the press")
        stub._drain_signals()
        assert stub._signal_view.blockCount() == 10
        assert stub._console.blockCount() == 1

        stub._console_pause_btn.setChecked(True)
        stub._toggle_console_pause()
        assert stub._console_paused is True
        at_press_signals = stub._signal_view.blockCount()
        at_press_log = stub._console.blockCount()
        watermark = stub._signal_seq
        read_at_press = stub._signal_read

        for _ in range(4):
            _seed(sink, 10)
            stub._console_log_handler.log("held")
            stub._drain_signals()

        assert stub._signal_view.blockCount() == at_press_signals
        assert stub._console.blockCount() == at_press_log
        # The watermark did not move either, so nothing was consumed
        # and thrown away while the operator was reading.
        assert stub._signal_seq == watermark
        assert stub._signal_read == read_at_press
        assert stub._console_log_handler.buffered_count() == 4
        rec = _only(sink, QUIETS)
    assert rec.ok is True, rec.context
    assert rec.actual is True
    assert rec.expected is True
    assert rec.context["log_pane_paused"] is True
    assert rec.context["button_checked"] is True
    assert rec.duration is None


def test_a_pause_does_not_make_the_drain_look_dead(qapp: QApplication) -> None:
    """The repair must not turn `14-003` red every time Pause is held.

    `_signal_drain_ticks` is incremented as the FIRST statement of
    `_drain_signals`, above the pause guard, so a paused drain still
    counts its own invocations and `drain_alive` reads a live timer.
    Were the counter below the guard, an operator reading the pane for
    ten seconds would raise a stopped-drain alarm -- the exact fault
    `14-003` exists to separate from ordinary silence.
    """
    with _collect() as sink, _console(qapp) as stub:
        stub._console_pause_btn.setChecked(True)
        stub._toggle_console_pause()
        for _ in range(20):
            stub._drain_signals()
        assert stub._signal_drain_ticks == 20
        assert stub._signal_rendered == 0
        _look(stub)
        alive = _only(sink, ALIVE)
        rendered = _only(sink, RENDERED)
    assert alive.ok is True, alive.context
    assert alive.context["ticks_since_last_look"] == 20
    assert alive.context["drain_timer_active"] is True
    # Nothing was read and nothing was rendered, so 14-001 is green too:
    # a pause loses nothing WHILE it is held.
    assert rendered.ok is True, rendered.context
    assert rendered.actual == 0
    assert rendered.expected == 0
    assert rendered.context["lost_to_slice"] == 0


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


def test_set_console_paused_is_the_only_writer_of_the_flag(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With `_set_console_paused` neutered the flag never moves.

    A second writer anywhere on the press path would keep
    `_console_paused` moving and quietly retire the `14-004` falsifier.
    """
    with _collect(), _console(qapp) as stub:
        _without_the_console_pause_flag(monkeypatch)
        for checked in (True, False, True):
            stub._console_pause_btn.setChecked(checked)
            stub._toggle_console_pause()
            assert not hasattr(stub, "_console_paused"), stub._console_paused


def test_the_pause_flag_control_moves_the_flag_when_the_writer_is_left_alone(
    qapp: QApplication,
) -> None:
    """The control: unpatched, `_toggle_console_pause` moves the flag."""
    with _collect(), _console(qapp) as stub:
        stub._console_pause_btn.setChecked(True)
        stub._toggle_console_pause()
        assert stub._console_paused is True
        stub._console_pause_btn.setChecked(False)
        stub._toggle_console_pause()
        assert stub._console_paused is False


def test_a_resume_delivers_the_backlog_and_the_slice_reports_what_it_ate(
    qapp: QApplication,
) -> None:
    """WHAT THE ISSUE #49 PAUSE HANDS TO `14-001`, AS NUMBERS.

    A paused drain advances no watermark, so the sink keeps every record
    of the pause and the first pass after the resume reads the whole
    backlog in one call. `_drain_signals` then renders `new[-200:]` --
    the NEWEST 200 -- after `self._signal_seq = new[-1].seq` has already
    moved past all of it, so anything older is unreachable by this
    consumer for the rest of the run.

    THE NUMBERS ARE PINNED HERE BECAUSE ISSUE #48 OWNS THAT BEHAVIOUR
    AND NEEDS A BASELINE TO MOVE, not a paragraph to argue with. Each
    row below is (records emitted during the pause) -> (rendered,
    dropped by the slice, blocks on the pane). Three records ride along
    with every drive: the pause's own `14-004`, and the resume's
    `14-004` and `14-005`.

        50    ->  53 rendered,    0 dropped,  53 blocks, 0 markers
        197   -> 200 rendered,    0 dropped, 200 blocks, 0 markers
        250   -> 200 rendered,   53 dropped, 201 blocks, 1 marker
        2500  -> 200 rendered, 2303 dropped, 201 blocks, 1 marker

    RESTATED FOR ISSUE #48, IN THE BLOCK COLUMN ONLY. Every rendered
    and dropped count above is the number this test measured before the
    marker existed, and #48 did not move any of them -- the pane stays
    CURRENT and draws the gap rather than falling behind to close it.
    The two rows that skip records now carry one more block each: the
    marker, above the slice it describes. A row that skipped nothing
    draws nothing.

    The operator paused precisely to keep those lines. The loss is
    REPORTED rather than silent -- `14-001` goes red, `lost_to_slice`
    names the mechanism, and since #48 the pane says so on the screen
    as well.

    The pane's own 2000-block cap is NOT what bites here: the 200-line
    slice caps the delivery first, so the cap can only evict pane
    history that was already there. `14-002` reports that separately,
    through `evicted`.
    """

    def _resume_after(backlog: int) -> tuple[int, int, int, int, Any]:
        with _collect() as sink, _console(qapp) as stub:
            stub._console_pause_btn.setChecked(True)
            stub._toggle_console_pause()
            _seed(sink, backlog)
            stub._drain_signals()
            assert stub._signal_view.document().isEmpty()
            stub._console_pause_btn.setChecked(False)
            stub._toggle_console_pause()
            stub._drain_signals()
            _look(stub)
            return (
                stub._signal_rendered,
                stub._signal_slice_dropped,
                stub._signal_view.blockCount(),
                stub._signal_markers,
                _only(sink, RENDERED),
            )

    rendered, dropped, blocks, markers, rec = _resume_after(50)
    assert (rendered, dropped, blocks, markers) == (53, 0, 53, 0)
    assert rec.ok is True, rec.context

    rendered, dropped, blocks, markers, rec = _resume_after(197)
    assert (rendered, dropped, blocks, markers) == (200, 0, 200, 0)
    assert rec.ok is True, rec.context

    rendered, dropped, blocks, markers, rec = _resume_after(250)
    assert (rendered, dropped, blocks, markers) == (200, 53, 201, 1)
    assert rec.ok is False
    assert rec.actual == 200
    assert rec.expected == 253
    assert rec.context["lost_to_slice"] == 53
    assert rec.context["slice_cap"] == SLICE_CAP

    rendered, dropped, blocks, markers, rec = _resume_after(2500)
    assert (rendered, dropped, blocks, markers) == (200, 2303, 201, 1)
    assert rec.ok is False
    assert rec.context["lost_to_slice"] == 2303
    # The pane cap never bit: 200 rendered and one marker is under 2000
    # blocks.
    assert blocks < PANE_BLOCKS


def test_the_marker_says_the_records_are_not_lost_and_where_they_are() -> None:
    """THE WORDING, PINNED AS A LITERAL AND NOT AS A ROUND TRIP.

    Every other test here asks the production helper for the string and
    compares the pane against it, which would pass just as happily if
    the helper said "gone". This one spells the line out, so a rewrite
    that dropped "NOT LOST" or dropped the path has to come through
    here first.

    No widget and no Qt: the wording is a property of the text.
    """
    from src.gui import main_window as mw

    line = mw._signal_gap_marker_text(4800)
    assert line == (
        "──── [SIGNALS GAP] 4800 earlier records skipped to stay "
        "current · NOT LOST · on disk in "
        "~/.acervator_logs/signals/session.jsonl ────"
    )
    # The three things it has to carry, asserted one at a time so a
    # failure names which one went.
    assert "4800" in line  # how many
    assert "NOT LOST" in line  # they still exist
    assert SIGNALS_FILE in line  # and where
    # The count leads, so the eye finds it without reading the sentence.
    assert line.index("4800") < line.index("NOT LOST")
    # A record line never starts this way.
    assert line.startswith("──── ")
    assert line.endswith(" ────")


def test_a_live_burst_draws_the_gap_it_stepped_over(qapp: QApplication) -> None:
    """PATH B -- issue #48's own path. No pause anywhere in this drive.

    250 records inside one 500 ms window. The watermark moves past all
    250, the slice keeps the newest 200 and the pane now says what
    happened to the other 50.
    """
    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 250)
        stub._drain_signals()
        lines = _pane_lines(stub)
        assert stub._signal_slice_dropped == 50
        assert stub._signal_rendered == 200
        assert stub._signal_markers == 1
        assert stub._signal_view.blockCount() == SLICE_CAP + 1
        assert lines[0] == _marker(50)
        assert lines.count(_marker(50)) == 1


def test_a_resume_draws_the_gap_it_stepped_over(qapp: QApplication) -> None:
    """PATH A -- the resume issue #49's repair created.

    The operator pauses, 5000 records arrive, he resumes. The drain
    reads the whole backlog in one call and steps over all but the
    newest 200. 4803 rather than 4800 because three pin records ride
    along with the drive itself: the pause's own `14-004`, and the
    resume's `14-004` and `14-005`. The number is asserted separately
    from the wording, so a change in what rides along fails on the
    number and does not quietly rewrite the marker.
    """
    with _collect() as sink, _console(qapp) as stub:
        stub._console_pause_btn.setChecked(True)
        stub._toggle_console_pause()
        _seed(sink, 5000)
        stub._drain_signals()
        assert stub._signal_view.document().isEmpty()
        stub._console_pause_btn.setChecked(False)
        stub._toggle_console_pause()
        stub._drain_signals()
        lines = _pane_lines(stub)
        assert stub._signal_slice_dropped == 4803
        assert stub._signal_markers == 1
        assert stub._signal_view.blockCount() == SLICE_CAP + 1
        assert lines[0] == _marker(4803)


def test_a_pass_that_kept_everything_draws_no_marker(qapp: QApplication) -> None:
    """A quiet window leaves no trace at all.

    A marker on every pass would be furniture the operator learns to
    read past, and the one that mattered would go by with the rest.
    """
    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 50)
        stub._drain_signals()
        text = stub._signal_view.toPlainText()
        assert stub._signal_slice_dropped == 0
        assert stub._signal_markers == 0
        assert stub._signal_view.blockCount() == 50
        assert GAP_TAG not in text


def test_the_marker_sits_above_the_records_it_describes(qapp: QApplication) -> None:
    """PLACEMENT, DRIVEN.

    The skipped records are OLDER than the 200 the pass draws, so the
    marker belongs above them. Below, on a pane that then goes quiet,
    it would sit at the bottom as the newest thing on the screen and
    read as a gap at the live edge -- a lie about a pane that is in
    fact fully current.
    """
    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 1000)
        stub._drain_signals()
        lines = _pane_lines(stub)
    assert lines[0] == _marker(800)
    assert len(lines) == SLICE_CAP + 1
    # Everything under it is a record, and the newest 200 at that.
    assert all(GAP_TAG not in line for line in lines[1:])
    assert lines[1].endswith("got=800")
    assert lines[-1].endswith("got=999")


def test_the_marker_is_not_evicted_by_its_own_pass(qapp: QApplication) -> None:
    """A pass appends at most 1 marker + 200 records against a 2000 cap.

    Driven on a pane ALREADY AT ITS CAP, which is the only state where
    eviction is live at all: 2600 records drawn 200 at a time fill it,
    then one 5000-record burst skips 4800 and draws the marker. The
    marker survives its own pass with about 1800 blocks of headroom,
    and the arithmetic is read off the widget rather than asserted.
    """
    with _collect() as sink, _console(qapp) as stub:
        for _ in range(13):
            _seed(sink, SLICE_CAP)
            stub._drain_signals()
        assert stub._signal_view.blockCount() == PANE_BLOCKS
        assert stub._signal_markers == 0
        _seed(sink, 5000)
        stub._drain_signals()
        lines = _pane_lines(stub)
        blocks = stub._signal_view.blockCount()
        markers = stub._signal_markers
    assert markers == 1
    assert blocks == PANE_BLOCKS
    marker_at = lines.index(_marker(4800))
    # 200 record lines were drawn under it and it is still on the pane.
    assert len(lines) - marker_at == SLICE_CAP + 1
    # The headroom that keeps it there, measured.
    assert marker_at >= PANE_BLOCKS - (SLICE_CAP + 1)


def test_the_marker_cannot_be_misread_as_a_record(qapp: QApplication) -> None:
    """VISUALLY DISTINCT, ASKED OF THE DOCUMENT AND NOT OF THE SOURCE.

    Records are green / red / grey TEXT on the pane's own ground and
    paint no ground of their own. The marker is the only line in the
    pane carrying a background brush, and it opens with a rule rather
    than with `OK`, `FAIL` or `--`. The rules do the same work in a
    plain-text copy, where the colour is gone.
    """
    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 250)
        stub._drain_signals()
        doc = stub._signal_view.document()
        marker_block = doc.firstBlock()
        record_block = marker_block.next()
        marker_text = marker_block.text()
        marker_formats = _fragment_formats(marker_block)
        record_formats = _fragment_formats(record_block)

    assert marker_text == _marker(50)
    assert len(marker_formats) == 1
    ground, ink = marker_formats[0]
    assert ground == "#33220a"  # its own ground
    assert ink == "#ffb000"  # amber, used nowhere else
    # No record fragment paints a ground at all.
    assert record_formats
    assert all(g is None for g, _ in record_formats)
    assert all(ink != i for _, i in record_formats)
    # And the shape of the line is not a record's shape.
    for lead in ("OK  ", "FAIL", "--  "):
        assert not marker_text.startswith(lead)


def test_the_pane_holds_the_markers_as_well_as_the_records(qapp: QApplication) -> None:
    """`14-002` RESTATED, AND THIS IS THE RESTATEMENT DRIVEN.

    Before issue #48 the pin compared the pane's block count against
    `_signal_rendered` alone, because records were the only thing the
    drain drew. A marker is a block too. The pin now counts both and
    reports `gap_markers` beside the verdict, so a reader of
    `session.jsonl` can take the two apart. Left as `_rendered` alone
    it would go red by exactly the number of markers -- red for drawing
    the notice that makes a skip visible.
    """
    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 250)
        stub._drain_signals()
        _seed(sink, 400)
        stub._drain_signals()
        _look(stub)
        rec = _only(sink, HOLDS)
        blocks = stub._signal_view.blockCount()
        rendered = stub._signal_rendered
        markers = stub._signal_markers
    assert (rendered, markers) == (400, 2)
    assert blocks == 402
    assert rec.ok is True, rec.context
    assert rec.actual == 402
    assert rec.expected == 402
    assert rec.context["gap_markers"] == 2
    assert rec.context["rendered"] == 400
    assert rec.context["evicted"] == 0


def test_a_marker_the_drain_did_not_draw_is_reported(qapp: QApplication) -> None:
    """THE FALSIFIER for the RESTATED `14-002`.

    A line on the pane that the drain's ledger does not know about is
    exactly what the pin exists to catch, and folding markers into the
    sum must not have opened a hole in it. One marker appended straight
    to the widget, `_signal_markers` untouched, and the pin goes red by
    one -- the same way
    `test_a_pane_emptied_behind_the_drain_is_reported` drives it red
    from the other direction.
    """
    from src.gui import main_window as mw

    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 4)
        stub._drain_signals()
        drawn = mw._draw_signal_gap_marker(stub._signal_view, skipped=7)
        assert drawn == 1
        _look(stub)
        rec = _only(sink, HOLDS)
    assert rec.ok is False
    assert rec.actual == 5  # four records and the marker
    assert rec.expected == 4  # the ledger knows of four
    assert rec.context["gap_markers"] == 0


def test_a_marker_does_not_count_as_a_record_rendered(qapp: QApplication) -> None:
    """`14-001` IS UNCHANGED, and that is asserted rather than assumed.

    A Console that quietly keeps up and one that quietly skips have to
    stay distinguishable in the record stream. If the marker were added
    to `_signal_rendered` the pin would read 201 against 250 -- still
    red here, but green the moment the skip was exactly one record, and
    the verdict would drift by the number of notices drawn.
    """
    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 250)
        stub._drain_signals()
        _look(stub)
        rec = _only(sink, RENDERED)
    assert rec.ok is False
    assert rec.actual == 200  # records, not 201
    assert rec.expected == 250
    assert rec.context["lost_to_slice"] == 50
    assert rec.context["slice_cap"] == SLICE_CAP
    assert "gap_markers" not in rec.context


def test_a_drain_that_skips_in_silence_is_reported(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE FALSIFIER for the marker, and it is the pre-repair pane.

    `_without_the_gap_marker` puts the tree back the way it was: the
    slice still throws 50 records away, `14-001` still counts them, and
    the pane draws the newest 200 with nothing at all to say the others
    existed. Every assertion here was TRUE of this file before the
    repair -- that is what makes the tests above evidence about this
    code rather than about arithmetic.
    """
    _without_the_gap_marker(monkeypatch)
    with _collect() as sink, _console(qapp) as stub:
        _seed(sink, 250)
        stub._drain_signals()
        text = stub._signal_view.toPlainText()
        _look(stub)
        rec = _only(sink, RENDERED)
        holds = _only(sink, HOLDS)
        # The pre-repair pane, exactly.
        assert stub._signal_view.blockCount() == SLICE_CAP
        assert stub._signal_markers == 0
        assert GAP_TAG not in text
        assert SIGNALS_FILE not in text
        assert text.splitlines()[0].endswith("got=50")
    # The loss is still counted. It was never the counting that failed.
    assert rec.ok is False
    assert rec.context["lost_to_slice"] == 50
    # And `14-002` is green about a pane that says nothing, which is
    # why the marker had to be drawn and not only reported.
    assert holds.ok is True, holds.context


# ── 14-005  the resume put the buffer on the pane ──────────────────────


def test_a_resume_delivers_every_buffered_line(qapp: QApplication) -> None:
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


def test_a_resume_the_pane_cap_eats_is_reported(qapp: QApplication) -> None:
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
    qapp: QApplication,
) -> None:
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


def test_the_pause_press_itself_writes_no_delivery_record(qapp: QApplication) -> None:
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


def test_the_duration_tracks_two_different_resume_workloads(qapp: QApplication) -> None:
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


def _drive_every_pin(qapp: QApplication, sink: SignalSink) -> None:
    """Fire all five console pins once: a health pass, then pause and resume."""
    with _console(qapp) as stub:
        stub._signal_drain_ticks = 1
        stub._emit_console_health()
        stub._console_pause_btn.setChecked(True)
        stub._toggle_console_pause()
        stub._console_log_handler.log("one held line")
        stub._console_pause_btn.setChecked(False)
        stub._toggle_console_pause()
    assert {r.name for r in sink.records()} == set(CONSOLE_PINS), sorted(
        {r.name for r in sink.records()}
    )


def test_only_the_resume_pin_carries_a_duration(qapp: QApplication) -> None:
    """One postcondition behind a bounded operation. The other four read
    counters and a flag, and carry no duration."""
    with _collect() as sink:
        _drive_every_pin(qapp, sink)
        carriers = {r.name for r in sink.records() if r.duration is not None}
    assert carriers == {DELIVERED}


def test_the_health_pins_fold_and_the_toggle_pins_do_not(qapp: QApplication) -> None:
    """A second health pass inside the fold window adds no record, while a
    second pause press adds one every time."""
    with _collect() as sink, _console(qapp) as stub:
        stub._signal_drain_ticks = 1
        stub._emit_console_health()
        stub._signal_drain_ticks = 2
        stub._emit_console_health()
        for checked in (True, False, True):
            stub._console_pause_btn.setChecked(checked)
            stub._toggle_console_pause()
        counts = {name: len(_records(sink, name)) for name in CONSOLE_PINS}
    for name in (RENDERED, HOLDS, ALIVE):
        assert counts[name] == 1, (name, counts)
    assert counts[QUIETS] == 3, counts


def test_the_health_pass_fires_exactly_the_three_cadence_pins(
    qapp: QApplication,
) -> None:
    """`_emit_console_health` emits the three cadence pins and neither
    toggle pin."""
    with _collect() as sink, _console(qapp) as stub:
        stub._signal_drain_ticks = 1
        stub._emit_console_health()
        fired = {r.name for r in sink.records()}
    assert fired == {RENDERED, HOLDS, ALIVE}, sorted(fired)


def test_a_pause_press_fires_only_the_toggle_pins(qapp: QApplication) -> None:
    """`_toggle_console_pause` emits only the two unthrottled pins."""
    with _collect() as sink, _console(qapp) as stub:
        stub._console_pause_btn.setChecked(True)
        stub._toggle_console_pause()
        stub._console_pause_btn.setChecked(False)
        stub._toggle_console_pause()
        fired = {r.name for r in sink.records()}
    assert fired == set(UNTHROTTLED), sorted(fired)


def test_every_pin_emits_from_its_own_site(qapp: QApplication) -> None:
    """Five records, five distinct `(name, site)` identities.

    `signal_contract` keys the fold window and the timing identity on that
    pair, so a shared identity would be one pin to the wire and two to a
    reader.
    """
    with _collect() as sink:
        _drive_every_pin(qapp, sink)
        identities = {(r.name, r.site) for r in sink.records()}
    assert len(identities) == 5, sorted(identities)


def test_no_context_carries_credential_material_or_a_bot_id(
    qapp: QApplication,
) -> None:
    """No emitted context holds credential material or operator text.

    A context is written to disk, and these hold counts, intervals and
    booleans.
    """
    with _collect() as sink:
        _drive_every_pin(qapp, sink)
        for record in sink.records():
            rendered = repr(record.context).lower()
            for banned in FORBIDDEN:
                assert banned not in rendered, (record.name, banned, record.context)
