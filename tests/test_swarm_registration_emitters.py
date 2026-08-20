"""Pins the two Bot Swarm registration emitters — 10.5, subsystem `swarm`.

    swarm.11.001.postcondition.sim_run_registered
    swarm.11.002.postcondition.paper_run_registered

THERE IS NO THIRD, AND THE LIVE PATH IS NOT INSTRUMENTED. Read that
before anything else in this file. A pin numbered
`swarm.11.003.postcondition.live_run_registered` was planned for
`register_live_run` and withdrawn. That function raises AttributeError
on `self._live_rows_layout`, which src/gui/bot_visualizer.py reads near
line 2388 and defines nowhere, so the live path cannot be driven and a
pin placed in it would never fire. The defect is tracked as issue #25
and is not repaired here. An earlier revision of this docstring listed
the live pin among the emitters this module covers. It does not cover
it, it never did, and a reader auditing coverage from that list
concluded that the layer rendering real-money bots was watched. It is
not.

WHAT THEY ASSERT, AND WHY IT IS NOT THE ARGUMENT THAT WENT IN. Each
emitter reads the row back OUT of its layer's store and reports the
row's `kind` against the layer the function is for. `register_sim_run`
and `register_paper_run` take the same shape of argument and differ
only in which store and layout they touch, so a registration that lands
in the wrong layer returns exactly as cleanly as a correct one.
Reporting the argument back would never catch that.

THE ROUTING CONTROL IS THE MISROUTE. `test_a_misrouted_row_is_reported`
forces `_create_swarm_row` to hand back a row of the wrong kind and
asserts the emitter reports the wrong kind with `ok` False. Without it
these tests would prove only that the emitters fire, which is the
"40 wires, $0.00 routed" shape: a count that looks right while nothing
landed where it was addressed.

THE DURATION CONTROL IS THE LEVER. `duration` was pinned here by an
existence check alone — `is not None` and `>= 0.0` — and an existence
check is passed by a literal, by a stop clock moved above the work, and
by any other blinding that leaves the field's SHAPE intact. Measured
2026-08-19: substituting the literal `1.0` at both emit sites changed no
result. `test_the_duration_tracks_the_real_registration` drives the same
registration at two known workloads and asserts the recorded value moved
with them. See `_tracks_the_registration` for the predicate and
`test_the_registration_duration_predicate_can_fail` for the other half
of it.

The entry points had ZERO callers before this (`nuclear_verification.py:19`
and `nuclear_mode_panel.py:561` both say so, and `emit_contracts.py:33`
lists `register_sim_run()` among functions that "passed its tests without
ever running"). These tests are the first thing to drive them.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.core import signal_contract as sc  # noqa: E402
from src.core.signal_contract import SignalSink  # noqa: E402

# Imported, not forked. `_tracks` is the project's duration predicate
# and this module has no standing to relax it; the site rule below
# WRAPS it and only ever adds a condition.
from tests.test_signal_operation_duration import _busy_wait, _tracks  # noqa: E402

if TYPE_CHECKING:                       # pragma: no cover
    # Annotation only. PySide6 must not be imported at module scope:
    # the predicate control below is pure Python and has to run on a
    # box without Qt.
    from PySide6.QtWidgets import QApplication

SIM = "swarm.11.001.postcondition.sim_run_registered"
PAPER = "swarm.11.002.postcondition.paper_run_registered"

LAYERS = ((SIM, "sim"), (PAPER, "paper"))

# The two workloads the duration lever drives.
#
# MEASURED 2026-08-20, offscreen Qt on the target machine. An unlevered
# registration records 0.00109 s to 0.00114 s over 8 samples per layer.
# With the lever the same registration records, over 5 samples each:
#
#     lever 0.010 s  ->  0.01112 s .. 0.01195 s
#     lever 0.120 s  ->  0.12135 s .. 0.12247 s
#
# The bands are 10.8x apart with 0.109 s of clear air between them, and
# `_tracks` asks only for a factor of 2. The short reading would have to
# inflate 5.4x, or the long reading collapse 5.4x, before scheduler
# noise could close the gap. The lever is a busy wait and not
# `time.sleep`: it never yields, so the Qt event loop cannot be
# scheduled inside it and cannot widen an interval by a whole tick.
LEVER_SHORT_S = 0.010
LEVER_LONG_S = 0.120


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Build the QApplication the Qt tests in this module run against.

    `importorskip` is INSIDE the fixture on purpose. The predicate
    control in this file is pure Python and must still run on a box
    without PySide6, which a module-level skip would prevent. A skipped
    test is not evidence.
    """
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication as _QApplication

    # `instance()` is typed as the QCoreApplication base and can hand
    # back a bare QCoreApplication in a non-GUI process, which has no
    # widget machinery. Narrow it rather than assume.
    running = _QApplication.instance()
    if isinstance(running, _QApplication):
        return running
    return _QApplication(sys.argv)


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _tab():
    from src.gui.bot_visualizer import BotVisualizationTab
    return BotVisualizationTab()


def _register(tab, layer: str, ident: str):
    cfg = {"asset": "CHIP/USD", "pair": "CHIP/USD", "mode": layer.upper(),
           "timeframe": "5m", "capital": 100.0, "candle_total": 10}
    if layer == "sim":
        return tab.register_sim_run(ident, "CHIP", cfg)
    return tab.register_paper_run(ident, "CHIP", cfg)


def _records(sink: SignalSink, name: str):
    return [r for r in sink.records() if r.name == name]


def _tracks_the_registration(short: float | None,
                             long_: float | None) -> bool:
    """Ask `_tracks`, then add a floor. The floor is the whole point.

    `_tracks` asks that the long reading be more than twice the short
    one. That is the right rule at a site whose readings are real, and
    it is not sufficient here. Move the stop clock above the work and
    the bracket spans nothing: both readings collapse to the cost of two
    `time.monotonic()` calls, and two values that small differ by more
    than a factor of two on ordinary clock jitter.

    MEASURED 2026-08-20 with the stop clock planted above the work, 60
    pairs off the real sim site: every reading fell between 9.99e-08 s
    and 5.00e-07 s, and `_tracks` alone ACCEPTED 3 of the 60. A detector
    that misses one blinding in twenty is not a detector, it is a coin
    the suite flips, so the rule here removes the flip instead of
    tightening the ratio and hoping.

    So this adds one rule and relaxes none: the long reading must hold
    at least half the interval the lever burned. The lever is 0.120 s
    and an unlevered registration measured 0.0011 s, so any reading
    under 0.060 s is a bracket that did not span the work.
    """
    if short is None or long_ is None:
        return False
    if long_ < LEVER_LONG_S / 2.0:
        return False
    return _tracks(short, long_)


def _duration_of_a_registration(monkeypatch: pytest.MonkeyPatch,
                                emitter: str, layer: str, ident: str,
                                burn: float) -> float | None:
    """Time one real registration that carries `burn` seconds of work.

    The extra work goes INSIDE the bracketed region. The lever wraps
    `_create_swarm_row` — the same seam the misroute control uses — and
    the REAL row factory still runs behind it. It lengthens the
    operation. It never touches the clock, the emit call or the
    `duration` argument, so the value read back is the site's own
    measurement of work that genuinely took that long.
    """
    tab = _tab()
    real = tab._create_swarm_row

    def _slow(kind: str, label: str, cfg: dict) -> dict:
        _busy_wait(burn)
        return real(kind, label, cfg)

    monkeypatch.setattr(tab, "_create_swarm_row", _slow)
    sink = SignalSink()
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        _register(tab, layer, ident)
    finally:
        # Restore the PREVIOUS sink, never None — `set_sink` is
        # process-global.
        sc.set_sink(previous)
    monkeypatch.undo()
    duration = _records(sink, emitter)[0].duration
    assert duration is None or isinstance(duration, float), duration
    return duration


@pytest.mark.parametrize("emitter,layer", LAYERS)
def test_each_layer_registration_emits_once(emitter, layer):
    _app()
    sink = SignalSink()
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        _register(_tab(), layer, f"{layer}-1")
    finally:
        # Restore the PREVIOUS sink, never None — `set_sink` is process-global.
        sc.set_sink(previous)
    assert len(_records(sink, emitter)) == 1


@pytest.mark.parametrize("emitter,layer", LAYERS)
def test_the_row_lands_in_the_layer_it_was_addressed_to(emitter, layer):
    """`actual` is read back from the store, `expected` is the layer."""
    _app()
    sink = SignalSink()
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        _register(_tab(), layer, f"{layer}-2")
    finally:
        sc.set_sink(previous)
    rec = _records(sink, emitter)[0]
    assert rec.actual == layer
    assert rec.expected == layer
    assert rec.ok is True
    assert rec.context["layer"] == layer


@pytest.mark.parametrize("emitter,layer", LAYERS)
def test_a_misrouted_row_is_reported(monkeypatch, emitter, layer):
    """THE ROUTING CONTROL. A row of the wrong kind must be caught.

    Symmetric entry points taking the same argument shape make a
    misroute easy to write and impossible to see from the call site: the
    wrong layer returns just as cleanly as the right one.
    """
    _app()
    tab = _tab()
    wrong = "live" if layer != "live" else "sim"

    real = tab._create_swarm_row

    def _mis(_kind, label, cfg):
        # `_kind` is the layer the caller ASKED for. The fake ignores it
        # and builds the wrong layer, which is the misroute being staged.
        return real(wrong, label, cfg)

    monkeypatch.setattr(tab, "_create_swarm_row", _mis)

    sink = SignalSink()
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        _register(tab, layer, f"{layer}-3")
    finally:
        sc.set_sink(previous)

    rec = _records(sink, emitter)[0]
    assert rec.actual == wrong, (
        "the emitter reported the addressed layer, not the row's")
    assert rec.expected == layer
    assert rec.ok is False, "a misroute must fail the check"


@pytest.mark.parametrize("emitter,layer", LAYERS)
def test_each_registration_carries_a_duration(emitter, layer):
    """Check existence only, and existence alone proves nothing.

    A literal passes this. A stop clock moved above the work passes it.
    It is kept because an absent duration is still a defect worth its
    own line; the control a literal cannot survive is
    `test_the_duration_tracks_the_real_registration`.
    """
    _app()
    sink = SignalSink()
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        _register(_tab(), layer, f"{layer}-4")
    finally:
        sc.set_sink(previous)
    rec = _records(sink, emitter)[0]
    assert rec.duration is not None, "no duration recorded"
    assert rec.duration >= 0.0


# -- THE DURATION CONTROL: it tracks ---------------------------------


@pytest.mark.parametrize("emitter,layer", LAYERS)
def test_the_duration_tracks_the_real_registration(
        monkeypatch: pytest.MonkeyPatch, qapp: QApplication,
        emitter: str, layer: str) -> None:
    """Drive one registration at two known workloads and read the clock.

    THE duration control. A constant fails it; a dead clock fails it. A
    source scan proving the argument is passed would not catch a sink
    that swallowed it, a literal in its place, or a timer bracketing the
    emit instead of the work.
    """
    # Drain anything Qt has queued so it cannot be billed to the first
    # bracketed region. The measured region must contain the lever and
    # the registration, nothing else.
    qapp.processEvents()

    short = _duration_of_a_registration(
        monkeypatch, emitter, layer, f"{layer}-dur-short", LEVER_SHORT_S)
    long_ = _duration_of_a_registration(
        monkeypatch, emitter, layer, f"{layer}-dur-long", LEVER_LONG_S)

    assert short is not None, "no duration recorded for the short workload"
    assert long_ is not None, "no duration recorded for the long workload"
    # These tolerances cover the unlevered registration cost (0.0011 s
    # measured) plus headroom for a slower box. They are not the
    # control; the control is the predicate below.
    assert short == pytest.approx(LEVER_SHORT_S, abs=0.020), short
    assert long_ == pytest.approx(LEVER_LONG_S, abs=0.030), long_
    assert _tracks_the_registration(short, long_), (
        f"the duration did not track the work: {short} vs {long_}")


def test_the_registration_duration_predicate_can_fail() -> None:
    """Drive the site predicate in the failing direction as well.

    The other half of the control. A check never shown failing proves
    nothing. Each line here is one way this site could be blinded while
    still handing the sink a `duration` field of the right shape.
    """
    assert not _tracks_the_registration(1.0, 1.0), (
        "a constant duration must not read as tracking")
    assert not _tracks_the_registration(None, 0.121), (
        "an absent duration must not read as tracking")
    assert not _tracks_the_registration(0.011, None), (
        "an absent duration must not read as tracking")
    assert not _tracks_the_registration(0.121, 0.011), (
        "going backwards must not read as tracking")

    # The zero-length bracket, and the measured reason this site carries
    # a floor that `_tracks` does not. This pair is a real one: the
    # 2026-08-20 dead-clock run recorded 1.00000761e-07 against
    # 4.00003046e-07, rounded here to the significant figures, which
    # does not move either verdict. The shared predicate ACCEPTS it. The
    # site rule rejects it. That is an addition to `_tracks`, never a
    # relaxation of it.
    assert _tracks(1.0e-07, 4.0e-07), (
        "the shared predicate is expected to accept a dead clock here")
    assert not _tracks_the_registration(1.0e-07, 4.0e-07), (
        "a bracket that spans no work must not read as tracking")

    # The pair measured off the real site, 2026-08-20.
    assert _tracks_the_registration(0.01112, 0.12135), (
        "the real measured pair must read as tracking")
