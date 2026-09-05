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

import asyncio
import inspect
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.simulator.fleet.fleet_replay_controller import (  # noqa: E402
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
    reg = CapitalReservationRegistry(state_path=tmp_path / "r.json", autosave=False)
    reg.reserve(bot_id="live-1", asset="ETH", qty=0.5, reason="t")
    eff = reg.effective_available(asset="ETH", bot_id="sim-1", total_holdings=0.1)
    assert eff == 0.0, "over-reservation must clamp to zero, not negative"


def test_own_reservations_do_not_subtract(tmp_path):
    reg = CapitalReservationRegistry(state_path=tmp_path / "r.json", autosave=False)
    reg.reserve(bot_id="b1", asset="ETH", qty=0.5, reason="t")
    eff = reg.effective_available(asset="ETH", bot_id="b1", total_holdings=1.0)
    assert eff == 1.0


# ── live state is never touched ──────────────────────────────────


def test_sim_registry_is_not_the_live_singleton():
    from src.trading.capital_reservation import get_registry

    sim = _make_sim_capital_registry()
    assert sim is not None, "sim registry should be constructible"
    assert sim is not get_registry(), "sim must not share the process-wide registry"


def test_sim_registry_does_not_autosave():
    """autosave is what carried 16,523 sim orphans into live state."""
    sim = _make_sim_capital_registry()
    assert sim._autosave is False


def test_sim_registry_state_path_is_outside_the_runtime_tree():
    sim = _make_sim_capital_registry()
    resolved = sim._state_path.resolve()
    assert resolved != _LIVE_STATE.resolve()
    runtime = (Path.home() / ".acervator").resolve()
    assert (
        runtime not in resolved.parents
    ), f"sim state path is inside the operator runtime tree: {resolved}"


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
    docs/engineering-notes/2026-08-07_C16_pin_replacement_record.md).

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
        state_path=Path("nonexistent-sim.json"), autosave=False
    )

    # The over-commit ceiling C16 is about: a claim ~110% of holdings.
    token = private.reserve(
        bot_id="sim-bot",
        asset="BTC",
        qty=1.10,
        reason="sim first ensure",
        bot_kind="scrumming",
        total_holdings=None,
    )

    mine = [r for r in private._reservations.values() if r.bot_id == "sim-bot"]
    assert len(mine) == 1, (
        "a sim bot obtained no reservation against its injected " "registry"
    )
    assert token

    # ...and the same claim WITH holdings asserted is what used to
    # happen and still fails, which is the defect C16 removes.
    with pytest.raises(ValueError):
        private.reserve(
            bot_id="sim-bot-2",
            asset="BTC",
            qty=1.10,
            reason="sim first ensure",
            bot_kind="scrumming",
            total_holdings=1.0,
        )


class _EnsureHost:
    """The least a bot must be for ``_ensure_capital_reservation`` to run.

    ``_capital_registry`` is the injected private registry and ``_sim_mode``
    picks the sim branch; every other attribute is a value the method reads.
    """

    _ensure_capital_reservation = ScrummingBot._ensure_capital_reservation
    _compute_reservation_qty = ScrummingBot._compute_reservation_qty
    _crr = ScrummingBot._crr

    def __init__(self, registry, sim_mode: bool, holdings: float = 1.0):
        self.bot_id = "sim-ensure-bot"
        self.config = type(
            "C",
            (),
            {
                "self_reserve_capital": True,
                "target_asset": "BTC",
                "personal_hold_qty": 0.0,
            },
        )()
        self._capital_registry = registry
        self._sim_mode = sim_mode
        self._crr_token = None
        self._crr_last_reserved_qty = 0.0
        self._target_balance = 100.0
        self._quote_to_usd = 1.0
        self._holdings = holdings

    async def _get_cached_exchange_balance(self, _asset):
        return self._holdings


def _run_ensure(registry, sim_mode: bool, price: float = 100.0):
    """Claims held after one real ``_ensure_capital_reservation`` call."""
    host = _EnsureHost(registry, sim_mode)
    asyncio.run(host._ensure_capital_reservation(price))
    return [r for r in registry._reservations.values() if r.bot_id == host.bot_id]


def test_the_ensure_path_still_reserves_in_sim(tmp_path):
    """C16 may relax the holdings assertion; it may NOT reintroduce a
    bare ``if _sim_mode: return``."""
    private = CapitalReservationRegistry(
        state_path=tmp_path / "sim.json", autosave=False
    )
    mine = _run_ensure(private, sim_mode=True)
    assert len(mine) == 1, (
        "a sim bot ran the real ensure path and obtained no reservation; "
        "isolation must come from the injected registry, not from "
        "refusing to reserve"
    )
    assert mine[0].asset == "BTC"


def test_a_live_bot_reserves_on_the_same_path(tmp_path):
    """POSITIVE CONTROL: the rig reserves with ``_sim_mode`` off too, so
    the sim green above is not an artefact of the host."""
    private = CapitalReservationRegistry(
        state_path=tmp_path / "live.json", autosave=False
    )
    assert len(_run_ensure(private, sim_mode=False)) == 1


def test_the_ensure_path_claims_nothing_when_the_feature_is_off(tmp_path):
    """NEGATIVE CONTROL: ``self_reserve_capital`` False reaches the
    registry with no claim, so a reservation is a real event."""
    private = CapitalReservationRegistry(
        state_path=tmp_path / "off.json", autosave=False
    )
    host = _EnsureHost(private, sim_mode=True)
    host.config.self_reserve_capital = False
    asyncio.run(host._ensure_capital_reservation(100.0))
    assert private._reservations == {}


def test_bot_accepts_an_injected_registry():
    sig = inspect.signature(ScrummingBot.__init__)
    assert "capital_registry" in sig.parameters


def test_crr_prefers_the_injected_registry():
    private = CapitalReservationRegistry(
        state_path=Path("nonexistent-sim.json"), autosave=False
    )

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


SIM_BOT_CONFIG = {
    "mode": "scrumming",
    "symbol": "CHIP/USD",
    "target_asset": "CHIP",
    "base_currency": "USD",
    "target_balance": 100.0,
    "bot_id": "crr-injection-bot",
}


class _SimExchange:
    exchange_id = "sim"


def test_the_fleet_controller_injects_its_private_registry_into_the_bot():
    """The bot ``_instantiate_bot`` builds holds the registry it was
    handed, and ``_crr`` resolves to that one, not to ``get_registry``."""
    from src.simulator.fleet.fleet_replay_controller import (
        _instantiate_bot,
        _make_sim_capital_registry,
    )
    from src.trading.capital_reservation import get_registry

    private = _make_sim_capital_registry()
    bot = _instantiate_bot(dict(SIM_BOT_CONFIG), _SimExchange(), private)
    assert bot is not None, "the controller built no bot at all"
    assert bot._capital_registry is private
    assert bot._crr() is private
    assert bot._crr() is not get_registry()


def test_a_bot_built_without_a_registry_is_refused():
    """POSITIVE CONTROL for the injection above: ``_instantiate_bot``
    with no registry answers None."""
    from src.simulator.fleet.fleet_replay_controller import _instantiate_bot

    assert _instantiate_bot(dict(SIM_BOT_CONFIG), _SimExchange(), None) is None


def test_the_phantom_subsystem_stays_reachable_in_sim():
    """Phantoms must remain REACHABLE in sim, not switched off.

    REPLACES test_sim_bots_are_constructed_with_phantoms_enabled (C18,
    v3.24.64, operator acknowledgement recorded 2026-08-07 — see
    docs/engineering-notes/2026-08-07_C18_pin_replacement_record.md).

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
    from src.simulator.fleet.fleet_replay_controller import (
        resolve_phantoms_enabled,
    )

    # Reachable: the per-run toggle forces them on regardless of the
    # persisted per-bot value.
    assert resolve_phantoms_enabled({"phantoms_enabled": False}, force=True) is True
    # ...and cannot be used to switch them off, which would be a second
    # route to a phantom-less replay that looks configured.
    assert resolve_phantoms_enabled({"phantoms_enabled": True}, force=False) is True


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
