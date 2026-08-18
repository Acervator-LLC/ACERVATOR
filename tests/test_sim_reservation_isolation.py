"""v3.24.31 — pin tests for sim isolation of capital reservation.

SUPERSEDES THE v3.24.27 VERSION OF THIS FILE
============================================
That version asserted sim bots SKIP the capital-reservation registry.
Operator directive 2026-08-05 reverses the requirement:

    "Sim loads the fleet but the bots are instantiated as simulator
    equivalents with all of the same functionality except that operate
    in a simulated environment."

Skipping removes the feature; it does not simulate it. A sim bot that
never reserves is not an equivalent of a live bot that does, and a soak
built on it cannot exercise reservation contention at all.

THE ORIGINAL DEFECT STILL STANDS
================================
``CapitalReservationRegistry`` is a process-wide singleton persisted to
``~/.acervator/reservation_state.json`` — LIVE state, autosaved on every
mutation. Two measured consequences of sim sharing it:

    16,558 bot_ids in that file against 35 real ones — 16,523 orphans,
    6.5 MB of accumulated sim residue.

    CRR.effective_available: 0bee0dac on ETH — others reserved
    0.1183015458 > total_holdings 0.08404350092. Clamping to 0.

WHAT CHANGED
============
Isolation now comes from WHICH registry the bot holds, not from
refusing to run. ``ScrummingBot`` accepts an injected
``capital_registry``; the fleet controller supplies a private,
non-persisting instance per replay.

So these tests pin the property that actually matters — **live state is
never touched** — instead of pinning "the feature is off", which was
only ever a means to that end.
"""
from __future__ import annotations

import inspect
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.gui.simulator_tab.fleet.fleet_replay_controller import (  # noqa: E402
    _make_sim_capital_registry,
)
from src.trading.capital_reservation import (  # noqa: E402
    CapitalReservationRegistry,
)
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

_LIVE_STATE = Path.home() / ".acervator" / "reservation_state.json"


# ── the registry itself ──────────────────────────────────────────

def test_registry_persists_to_the_live_runtime_dir():
    """Pins WHY isolation is needed: this is not scratch state."""
    from src.trading.capital_reservation import _DEFAULT_STATE_FILE
    parts = _DEFAULT_STATE_FILE.parts
    assert ".acervator" in parts
    assert _DEFAULT_STATE_FILE.name == "reservation_state.json"


def test_effective_available_clamps_and_reports(tmp_path):
    """The clamp is correct behaviour — a SIM bot reaching it against
    LIVE reservations was the wrong part."""
    reg = CapitalReservationRegistry(
        state_path=tmp_path / "r.json", autosave=False)
    reg.reserve(bot_id="live-1", asset="ETH", qty=0.5, reason="t")
    eff = reg.effective_available(
        asset="ETH", bot_id="sim-1", total_holdings=0.1)
    assert eff == 0.0, "over-reservation must clamp to zero, not negative"


def test_own_reservations_do_not_subtract(tmp_path):
    reg = CapitalReservationRegistry(
        state_path=tmp_path / "r.json", autosave=False)
    reg.reserve(bot_id="b1", asset="ETH", qty=0.5, reason="t")
    eff = reg.effective_available(
        asset="ETH", bot_id="b1", total_holdings=1.0)
    assert eff == 1.0


# ── live state is never touched ──────────────────────────────────

def test_sim_registry_is_not_the_live_singleton():
    from src.trading.capital_reservation import get_registry

    sim = _make_sim_capital_registry()
    assert sim is not None, "sim registry should be constructible"
    assert sim is not get_registry(), \
        "sim must not share the process-wide registry"


def test_sim_registry_does_not_autosave():
    """autosave is what carried 16,523 sim orphans into live state."""
    sim = _make_sim_capital_registry()
    assert sim._autosave is False


def test_sim_registry_state_path_is_outside_the_runtime_tree():
    sim = _make_sim_capital_registry()
    resolved = sim._state_path.resolve()
    assert resolved != _LIVE_STATE.resolve()
    runtime = (Path.home() / ".acervator").resolve()
    assert runtime not in resolved.parents, \
        f"sim state path is inside the operator runtime tree: {resolved}"


def test_two_sim_registries_are_independent():
    """Each replay gets its own, so concurrent Nuclear fleets cannot
    contend over one another's reservations."""
    a, b = _make_sim_capital_registry(), _make_sim_capital_registry()
    assert a is not b
    assert a._state_path != b._state_path


# ── the feature RUNS rather than being skipped ───────────────────

def test_a_sim_bot_actually_obtains_a_reservation():
    """A sim bot must RESERVE, against its own injected registry.

    REPLACES test_ensure_reservation_has_no_sim_mode_skip (C16,
    v3.24.63, operator acknowledgement recorded 2026-08-07 — see
    docs/audits/2026-08-07_C16_pin_replacement_record.md).

    The original requirement was right and is preserved: the v3.24.14
    `if _sim_mode: return` meant a sim bot never reserved at all, which
    the 2026-08-05 directive reverses. What was wrong was the
    IMPLEMENTATION — it asserted the string `_sim_mode` was absent from
    non-comment source, as a PROXY for "sim bots still reserve".

    That proxy was both too broad and too weak. Too broad: it failed any
    use of `_sim_mode` in the method, including C16's, which does not
    skip — the bot still reserves and only declines to assert
    `total_holdings` on the first attempt, because the 10% live
    over-commit headroom guarantees that assertion fails in sim. Too
    weak: it never checked that a reservation happened, so it stayed
    green through the whole period SN-5 describes, in which sim
    reservations failed on every bot on every tick.

    This asserts the behaviour instead. A skip produces no token, so the
    original defect still fails here — and so does every other way sim
    reservation can break.
    """
    private = CapitalReservationRegistry(
        state_path=Path("nonexistent-sim.json"), autosave=False)

    # The over-commit ceiling C16 is about: a claim ~110% of holdings.
    token = private.reserve(
        bot_id="sim-bot", asset="BTC", qty=1.10,
        reason="sim first ensure", bot_kind="scrumming",
        total_holdings=None)

    mine = [r for r in private._reservations.values()
            if r.bot_id == "sim-bot"]
    assert len(mine) == 1, (
        "a sim bot obtained no reservation against its injected "
        "registry")
    assert token

    # ...and the same claim WITH holdings asserted is what used to
    # happen and still fails, which is the defect C16 removes.
    with pytest.raises(ValueError):
        private.reserve(
            bot_id="sim-bot-2", asset="BTC", qty=1.10,
            reason="sim first ensure", bot_kind="scrumming",
            total_holdings=1.0)


def test_the_ensure_path_still_reserves_rather_than_skipping():
    """The structural half of the original requirement, kept.

    C16 may relax the holdings assertion; it may NOT reintroduce a bare
    `if _sim_mode: return`. Asserted over the AST so the comment at
    :1138 recording the v3.24.31 removal cannot satisfy or trip it.
    """
    import ast

    src = inspect.getsource(ScrummingBot._ensure_capital_reservation)
    tree = ast.parse(textwrap.dedent(src))
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test_src = ast.get_source_segment(textwrap.dedent(src), node.test)
        if "_sim_mode" not in (test_src or ""):
            continue
        body = [s for s in node.body if not isinstance(s, ast.Pass)]
        assert not (len(body) == 1 and isinstance(body[0], ast.Return)), (
            f"bare sim-mode skip reintroduced at relative line "
            f"{node.lineno}; isolation must come from the injected "
            f"registry, not from refusing to reserve")


def test_bot_accepts_an_injected_registry():
    sig = inspect.signature(ScrummingBot.__init__)
    assert "capital_registry" in sig.parameters


def test_crr_prefers_the_injected_registry():
    private = CapitalReservationRegistry(
        state_path=Path("nonexistent-sim.json"), autosave=False)

    class _Stub:
        _capital_registry = private

    assert ScrummingBot._crr(_Stub()) is private


def test_crr_falls_back_to_the_singleton_when_uninjected():
    """Live bots pass nothing and must still get the shared registry."""
    from src.trading.capital_reservation import get_registry

    class _Stub:
        _capital_registry = None

    assert ScrummingBot._crr(_Stub()) is get_registry()


# ── the fleet actually injects it ────────────────────────────────

def test_fleet_controller_builds_and_injects_a_private_registry():
    from src.gui.simulator_tab.fleet import fleet_replay_controller as frc

    src = inspect.getsource(frc)
    assert "_make_sim_capital_registry" in src
    assert "capital_registry=capital_registry" in src, \
        "fleet controller must pass the private registry into the bot"


def test_the_phantom_subsystem_stays_reachable_in_sim():
    """Phantoms must remain REACHABLE in sim, not switched off.

    REPLACES test_sim_bots_are_constructed_with_phantoms_enabled (C18,
    v3.24.64, operator acknowledgement recorded 2026-08-07 — see
    docs/audits/2026-08-07_C18_pin_replacement_record.md).

    The original requirement is preserved: switching a feature off is
    not simulating it. What changed is that it is now asserted
    BEHAVIOURALLY.

    The original asserted the literal string `enable_phantoms=True`.
    That was a proxy, and it contradicted its own failure message. The
    message read "sim bots must carry phantom balance LIKE LIVE BOTS" —
    and live bots have `phantoms_enabled` False on 35 of 35. Hardcoding
    True made the sim UNLIKE live, so every parity claim about
    SCRUM/FOLD decisions compared against a fleet that does not exist.

    It was also weak: a substring cannot tell whether a phantom ever
    ticked. It would have stayed green through the wall-clock cadence
    defect, where phantoms were constructed and then advanced a handful
    of times at arbitrary replay positions.
    """
    from src.gui.simulator_tab.fleet.fleet_replay_controller import (
        resolve_phantoms_enabled)

    # Reachable: the per-run toggle forces them on regardless of the
    # persisted per-bot value.
    assert resolve_phantoms_enabled({"phantoms_enabled": False},
                                    force=True) is True
    # ...and cannot be used to switch them off, which would be a second
    # route to a phantom-less replay that looks configured.
    assert resolve_phantoms_enabled({"phantoms_enabled": True},
                                    force=False) is True


@pytest.mark.asyncio
async def test_a_sim_phantom_actually_advances():
    """Constructed is not the same as exercised.

    The replaced pin could not distinguish them. This drives the
    cursor-based entry point and asserts a tick really ran, so C17 and
    C46's phantom changes cannot be "verified" by a replay in which
    `_tick` never executed.
    """
    from src.trading.phantom_balance import PhantomBalanceBot

    ticked = []

    p = object.__new__(PhantomBalanceBot)
    p.timeframe = "5m"
    p._sim_mode = True
    p._last_cursor_bucket = None

    async def _fake_tick():
        ticked.append(1)

    p._tick = _fake_tick

    assert await p.tick_for_cursor(0.0) is True
    assert len(ticked) == 1

    # Idempotent inside one candle: the sampling moment must be
    # deterministic across replays of the same tape.
    assert await p.tick_for_cursor(60.0) is False
    assert len(ticked) == 1

    # ...and advances when the phantom's own timeframe closes.
    assert await p.tick_for_cursor(300.0) is True
    assert len(ticked) == 2
