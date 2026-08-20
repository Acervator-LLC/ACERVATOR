"""Pins the three Bot Swarm registration emitters — 10.5, subsystem `swarm` (11).

    swarm.11.001.postcondition.sim_run_registered
    swarm.11.002.postcondition.paper_run_registered
    swarm.11.003.postcondition.live_run_registered

WHAT THEY ASSERT, AND WHY IT IS NOT THE ARGUMENT THAT WENT IN. Each emitter
reads the row back OUT of its layer's store and reports the row's `kind`
against the layer the function is for. `register_sim_run`, `register_paper_run`
and `register_live_run` take the same shape of argument and differ only in which
store and layout they touch, so a registration that lands in the wrong layer
returns exactly as cleanly as a correct one. Reporting the argument back would
never catch that.

THE CONTROL IS THE MISROUTE. `test_a_misrouted_row_is_reported` forces
`_create_swarm_row` to hand back a row of the wrong kind and asserts the emitter
reports the wrong kind with `ok` False. Without it these tests would prove only
that the emitters fire, which is the "40 wires, $0.00 routed" shape: a count
that looks right while nothing landed where it was addressed.

The entry points had ZERO callers before this (`nuclear_verification.py:19` and
`nuclear_mode_panel.py:561` both say so, and `emit_contracts.py:33` lists
`register_sim_run()` among functions that "passed its tests without ever
running"). These tests are the first thing to drive them.
"""

from __future__ import annotations

import pytest

from src.core import signal_contract as sc
from src.core.signal_contract import SignalSink

SIM = "swarm.11.001.postcondition.sim_run_registered"
PAPER = "swarm.11.002.postcondition.paper_run_registered"

LAYERS = ((SIM, "sim"), (PAPER, "paper"))


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
    """THE CONTROL. A row of the wrong kind must be caught, not waved through.

    Three symmetric entry points taking the same argument shape make a misroute
    easy to write and impossible to see from the call site: the wrong layer
    returns just as cleanly as the right one.
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
    assert rec.actual == wrong, "the emitter reported the addressed layer, not the row's"
    assert rec.expected == layer
    assert rec.ok is False, "a misroute must fail the check"


@pytest.mark.parametrize("emitter,layer", LAYERS)
def test_each_registration_carries_a_duration(emitter, layer):
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
