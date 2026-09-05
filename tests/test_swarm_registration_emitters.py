"""Pins `swarm.11.001` and `swarm.11.002` on `BotVisualizationTab`.

Each emitter reads the row back out of its layer store and reports the row
`kind` against the layer, so `test_a_misrouted_row_is_reported` forces
`_create_swarm_row` to hand back the wrong kind and asserts `ok` is False.
`test_the_duration_tracks_the_real_registration` drives one registration at
`LEVER_SHORT_S` and `LEVER_LONG_S` and reads the clock. There is no pin on
`register_live_run`, which raises AttributeError on `_live_rows_layout`.
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

from tests.test_signal_operation_duration import _busy_wait, _tracks  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    from PySide6.QtWidgets import QApplication

SIM = "swarm.11.001.postcondition.sim_run_registered"
PAPER = "swarm.11.002.postcondition.paper_run_registered"

LAYERS = ((SIM, "sim"), (PAPER, "paper"))

# The two workloads `_busy_wait` levers. A busy wait never yields, so the Qt
# event loop cannot be scheduled inside a measured region.
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

    # `instance()` can hand back a bare QCoreApplication, which has no widget
    # machinery.
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
    cfg = {
        "asset": "CHIP/USD",
        "pair": "CHIP/USD",
        "mode": layer.upper(),
        "timeframe": "5m",
        "capital": 100.0,
        "candle_total": 10,
    }
    if layer == "sim":
        return tab.register_sim_run(ident, "CHIP", cfg)
    return tab.register_paper_run(ident, "CHIP", cfg)


def _records(sink: SignalSink, name: str):
    return [r for r in sink.records() if r.name == name]


def _tracks_the_registration(short: float | None, long_: float | None) -> bool:
    """Ask `_tracks`, then require `long_` to hold half of `LEVER_LONG_S`.

    A bracket that spans no work reads a fraction of a microsecond at both
    levers, which `_tracks` accepts on ratio alone.
    """
    if short is None or long_ is None:
        return False
    if long_ < LEVER_LONG_S / 2.0:
        return False
    return _tracks(short, long_)


def _duration_of_a_registration(
    monkeypatch: pytest.MonkeyPatch, emitter: str, layer: str, ident: str, burn: float
) -> float | None:
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
    assert (
        rec.actual == wrong
    ), "the emitter reported the addressed layer, not the row's"
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
    monkeypatch: pytest.MonkeyPatch, qapp: QApplication, emitter: str, layer: str
) -> None:
    """Drive one registration at two known workloads and read the clock.

    THE duration control. A constant fails it; a dead clock fails it. A
    source scan proving the argument is passed would not catch a sink
    that swallowed it, a literal in its place, or a timer bracketing the
    emit instead of the work.
    """
    # Drain Qt's queue so it is not billed to the first bracketed region.
    qapp.processEvents()

    short = _duration_of_a_registration(
        monkeypatch, emitter, layer, f"{layer}-dur-short", LEVER_SHORT_S
    )
    long_ = _duration_of_a_registration(
        monkeypatch, emitter, layer, f"{layer}-dur-long", LEVER_LONG_S
    )

    assert short is not None, "no duration recorded for the short workload"
    assert long_ is not None, "no duration recorded for the long workload"
    # The tolerances cover the unlevered registration cost and a slower box.
    # `_tracks_the_registration` below is the control, not these.
    assert short == pytest.approx(LEVER_SHORT_S, abs=0.020), short
    assert long_ == pytest.approx(LEVER_LONG_S, abs=0.030), long_
    assert _tracks_the_registration(
        short, long_
    ), f"the duration did not track the work: {short} vs {long_}"


def test_the_registration_duration_predicate_can_fail() -> None:
    """Drive the site predicate in the failing direction as well.

    The other half of the control. A check never shown failing proves
    nothing. Each line here is one way this site could be blinded while
    still handing the sink a `duration` field of the right shape.
    """
    assert not _tracks_the_registration(
        1.0, 1.0
    ), "a constant duration must not read as tracking"
    assert not _tracks_the_registration(
        None, 0.121
    ), "an absent duration must not read as tracking"
    assert not _tracks_the_registration(
        0.011, None
    ), "an absent duration must not read as tracking"
    assert not _tracks_the_registration(
        0.121, 0.011
    ), "going backwards must not read as tracking"

    # A zero-length bracket: `_tracks` accepts this pair, the site rule adds a
    # floor and rejects it.
    assert _tracks(
        1.0e-07, 4.0e-07
    ), "the shared predicate is expected to accept a dead clock here"
    assert not _tracks_the_registration(
        1.0e-07, 4.0e-07
    ), "a bracket that spans no work must not read as tracking"

    # The pair measured off the real site, 2026-08-20.
    assert _tracks_the_registration(
        0.01112, 0.12135
    ), "the real measured pair must read as tracking"
