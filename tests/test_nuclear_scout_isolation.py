"""v3.24.32 — pin the Nuclear scout's isolation from live.

THE CROSSOVER
=============
``NuclearController._construct_scout`` built the scout as::

    scout = ScrummingBot(cfg, self._exchange, enable_phantoms=False)
    scout._bus = self._sim_bus

No ``sim_mode``. Three consequences, on the ONLY GUI-reachable Nuclear
path:

1. ``_sim_mode`` False meant the bot resolved the process-wide
   ``CapitalReservationRegistry`` and wrote into
   ``~/.acervator/reservation_state.json`` — LIVE capital state. That
   is the leak that accumulated **16,523 orphan reservations (6.5 MB)**
   before v3.24.14.

2. Bus isolation happens INSIDE ``ScrummingBot.__init__`` under
   ``if self._sim_mode:``. With it False the scout wired to the GLOBAL
   bus during construction; assigning ``_bus`` afterwards does not move
   subscriptions already made, so scout events could reach live
   subscribers.

3. ``enable_phantoms=False`` removed a subsystem rather than isolating
   it, which the 2026-08-05 directive rejects.

Operator, same session:

    "Just make sure you are not fucking with Live when we are working
    on Sim."

These are that guarantee, expressed as tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.core.event_bus import get_event_bus  # noqa: E402
from src.trading.capital_reservation import get_registry  # noqa: E402

_LIVE_STATE = Path.home() / ".acervator" / "reservation_state.json"


@pytest.fixture
def scout():
    """A constructed Nuclear scout, or skip if no tapes exist."""
    from src.simulator.nuclear_candle_source import (
        NuclearCandleSource,
    )
    from src.simulator.nuclear_controller import NuclearController

    src = NuclearCandleSource()
    tapes = src.list_tapes()
    if not tapes:
        pytest.skip("no Stone Tablet tapes on this machine")
    ctl = NuclearController(candle_source=src, tape_id=tapes[0])
    ctl._build_context()
    ctl._wire_bus_subscriptions()
    ctl._construct_scout()
    return ctl._scout


def test_scout_is_in_sim_mode(scout):
    """Without this the other two guarantees do not hold — bus
    isolation and registry resolution both key off it."""
    assert scout._sim_mode is True


def test_scout_does_not_resolve_the_live_registry(scout):
    """The 16,523-orphan leak. This is the one that reaches disk."""
    assert (
        scout._crr() is not get_registry()
    ), "Nuclear scout resolved the process-wide capital registry"


def test_scout_registry_does_not_autosave(scout):
    """autosave is what carried sim reservations into live state."""
    assert scout._crr()._autosave is False


def test_scout_registry_state_path_is_outside_the_runtime_tree(scout):
    resolved = scout._crr()._state_path.resolve()
    assert resolved != _LIVE_STATE.resolve()
    runtime = (Path.home() / ".acervator").resolve()
    assert (
        runtime not in resolved.parents
    ), f"scout registry writes inside the runtime tree: {resolved}"


def test_scout_is_not_on_the_global_bus(scout):
    """Bus isolation is applied during __init__, so it depends on
    sim_mode being set AT CONSTRUCTION — not on the later assignment."""
    assert scout._bus is not get_event_bus()


def test_scout_carries_phantoms_like_live(scout):
    """enable_phantoms=False removed the subsystem instead of isolating
    it. Phantom balance is per-bot in-memory state and needs no
    external isolation."""
    assert scout._phantoms_enabled is True


def test_construct_scout_passes_the_isolation_arguments():
    """Structural guard: if someone reconstructs the scout without
    these, the runtime tests above would still pass on a stale import.
    """
    import inspect

    from src.simulator.nuclear_controller import NuclearController

    src = inspect.getsource(NuclearController._construct_scout)
    # Comments are stripped: the method carries an explanation of the
    # OLD `enable_phantoms=False` construction, and that history is
    # worth keeping. Matching raw text would flag the explanation as
    # if it were the defect.
    code = "\n".join(ln for ln in src.split("\n") if not ln.strip().startswith("#"))
    assert "sim_mode=True" in code
    assert "capital_registry=" in code
    assert "enable_phantoms=True" in code
    assert (
        "enable_phantoms=False" not in code
    ), "scout reconstructed with phantoms disabled"
