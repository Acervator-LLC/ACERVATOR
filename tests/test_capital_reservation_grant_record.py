"""The grant-path record must be able to come back False. Issue #21.

WHAT WAS WRONG
==============
``_ensure_capital_reservation`` reports on its SUCCESS path, which is
the whole point of the emitter network: a satisfied expectation is
recorded so that silence cannot be mistaken for never-executed. The
record it made was::

    actual=round(float(_qty), 10),
    expected=round(float(_qty), 10),

One expression, passed twice. ``emit`` derives ``ok`` by equality when
no verdict is given, so the verdict was True on every tick of every bot
for the whole life of the pin. It claimed "the reservation granted the
requested quantity" by comparing the request with itself, and a green
record from it was evidence of nothing.

WHAT IT READS NOW
=================
``actual``   the quantity the registry is HOLDING, mirrored in
             ``self._crr_last_reserved_qty``.
``expected`` the quantity THIS tick computed as needed, ``_qty``.
``ok``       ``held > 0`` and the two are within 1 % of the held value.

The 1 % is not chosen here. It is read off the update path a few lines
above the record, which pushes a new quantity to the registry only once
the drift exceeds it. The held quantity is therefore allowed to sit
anywhere inside that band and nowhere outside it, and the record says
whether it did.

WHY A CONTROL FILE, AND WHY IT DRIVES THE WHOLE METHOD
======================================================
A check that cannot fail is exactly what was wrong, so a test that only
showed the repaired pin coming back GREEN would repeat the defect in a
new place. Every verdict below is produced by awaiting the real
``_ensure_capital_reservation`` and reading the record the real
``signal_contract`` sink received. Nothing here calls the arithmetic
directly, and nothing here asserts a verdict this file computed.

HOW A FALSE IS REACHED, AND WHY IT TAKES AN INJECTION
=====================================================
Inside one call the method writes the mirror on every path that touches
the registry -- after ``reserve()``, and after ``update()`` -- so by the
time the record is made the mirror agrees with the request by
construction. That is what the postcondition asserts, and a
postcondition on a property the code establishes is still a real check:
it goes red when the construction stops holding.

The state it exists to catch is a mirror that stops agreeing with the
registry BETWEEN those writes -- an update that did not land, or the
value written from somewhere else. ``heartbeat()`` is the last registry
call before the record is made, so the divergence is planted there.
Everything after it is the shipping code: the read, the arithmetic, the
verdict, and the record.

The same injection carries both halves. An in-band value must come back
True and an out-of-band value must come back False, so no test here can
pass because the injection itself decided the answer.
"""
from __future__ import annotations

import asyncio
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core import signal_contract as sc  # noqa: E402
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

PIN = "bot.01.002.postcondition.capital_reservation"

# The bot below wants $200 at $100 a unit. `_compute_reservation_qty`
# adds the 10 % drift margin, so it needs 2.20 units.
# `test_the_needed_quantity_is_what_this_file_says_it_is` is the
# positive control for that number; nothing here hard-codes it blind.
TARGET_BALANCE = 200.0
PRICE = 100.0
NEEDED = 2.20

# Held quantities, one each side of the band. The band the update path
# keeps the reservation inside is 1 % of the HELD value.
INSIDE_BAND = NEEDED * 1.005
OUTSIDE_BAND = NEEDED * 1.05

# Plenty of inventory, so the over-commit cap above the record leaves
# `_qty` alone and `capped` stays False. A capped tick is a different
# story and is not what this file is about.
HOLDINGS = 100.0


class _Registry:
    """The least registry the ensure path can finish against.

    ``after_heartbeat`` is the injection seam. It runs at the end of
    ``heartbeat()``, which is the last thing the method does before it
    builds the record, and it is how a mirror that no longer agrees
    with the registry is put in front of the check.

    Every argument each call carries is recorded rather than dropped.
    A stub that swallows them cannot say whether the shipping code
    still passes ``total_holdings``, and that argument is the whole
    reason the ensure path is async.
    """

    def __init__(self) -> None:
        self.reserved: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []
        self.heartbeats: list[str] = []
        self.after_heartbeat: Callable[[], None] | None = None

    def reserve(self, bot_id: str, asset: str, qty: float, reason: str,
                bot_kind: str = "unknown",
                total_holdings: float | None = None) -> str:
        self.reserved.append({
            "bot_id": bot_id, "asset": asset, "qty": float(qty),
            "reason": reason, "bot_kind": bot_kind,
            "total_holdings": total_holdings})
        return f"reservation-{len(self.reserved):04d}"

    def update(self, handle: str, bot_id: str, new_qty: float,
               total_holdings: float | None = None) -> None:
        self.updated.append({
            "handle": handle, "bot_id": bot_id,
            "new_qty": float(new_qty), "total_holdings": total_holdings})

    def heartbeat(self, bot_id: str) -> None:
        self.heartbeats.append(bot_id)
        if self.after_heartbeat is not None:
            self.after_heartbeat()


def _bot(registry: _Registry) -> SimpleNamespace:
    """A stub carrying only what the ensure path reads.

    The registry is INJECTED through ``_capital_registry`` rather than
    patched onto the module. ``_crr`` is bound to the real
    implementation, so the resolution the shipping code does is
    exercised instead of replaced.
    """
    stub = SimpleNamespace(
        bot_id="bot-grant01",
        _capital_registry=registry,
        _target_balance=TARGET_BALANCE,
        _quote_to_usd=1.0,
        _crr_token=None,
        _crr_last_reserved_qty=0.0,
        _exchange_balance_cache={"BTC": (HOLDINGS, time.time())},
        config=SimpleNamespace(
            target_asset="BTC",
            personal_hold_qty=0.0,
            self_reserve_capital=True,
        ),
    )
    stub._crr = MethodType(ScrummingBot._crr, stub)
    stub._compute_reservation_qty = MethodType(
        ScrummingBot._compute_reservation_qty, stub)
    stub._get_cached_exchange_balance = MethodType(
        ScrummingBot._get_cached_exchange_balance, stub)
    return stub


def _ensure(stub: SimpleNamespace) -> None:
    """One tick of the real method."""
    asyncio.run(ScrummingBot._ensure_capital_reservation(stub, PRICE))


def _desync_to(stub: SimpleNamespace, held: float) -> Callable[[], None]:
    """Leave the mirror at ``held`` once the registry work is done."""
    def _plant() -> None:
        stub._crr_last_reserved_qty = held
    return _plant


@pytest.fixture
def sink() -> Iterator[Any]:
    """Collect this test's records, and start with a clean throttle.

    The pin is throttled to one record per 60 s per site, so a stamp
    left by an earlier test would silence the record this one reads and
    the assertion would run on an empty tuple.
    """
    previous = sc.get_sink()
    collector = sc.SignalSink(path=None)
    sc.reset_throttle()
    sc.set_sink(collector)
    try:
        yield collector
    finally:
        sc.set_sink(previous)
        sc.reset_throttle()


def _one_record(collector: Any) -> Any:
    """The single record this pin made, or a failure that says so."""
    records = collector.records(PIN)
    assert len(records) == 1, (
        f"expected exactly one {PIN} record, got {len(records)}. A pin "
        f"that made none is a pin that did not run; more than one means "
        f"throttle state leaked into this test.")
    return records[0]


# -- the numbers this file rests on -----------------------------------

def test_the_needed_quantity_is_what_this_file_says_it_is() -> None:
    """POSITIVE CONTROL for every band below.

    If the margin in `_compute_reservation_qty` changed, NEEDED would
    be stale, INSIDE_BAND and OUTSIDE_BAND would be measured against
    the wrong centre, and the two-sided control would still look green
    while testing neither side.
    """
    stub = _bot(_Registry())
    assert stub._compute_reservation_qty(PRICE) == pytest.approx(NEEDED)


def test_the_planted_values_are_one_each_side_of_the_band() -> None:
    """POSITIVE CONTROL for the injection, not for the code.

    Read from the constants alone. If both landed on the same side, the
    pair below would agree for a reason that has nothing to do with the
    pin.
    """
    assert abs(NEEDED - INSIDE_BAND) / INSIDE_BAND <= 0.01
    assert abs(NEEDED - OUTSIDE_BAND) / OUTSIDE_BAND > 0.01


# -- the record exists, and it reads live state -----------------------

def test_the_grant_path_records_its_postcondition(sink: Any) -> None:
    """An undriven emitter is decoration. This is the one that runs."""
    registry = _Registry()
    stub = _bot(registry)

    _ensure(stub)

    assert len(registry.reserved) == 1
    assert registry.reserved[0]["qty"] == pytest.approx(NEEDED)
    assert registry.reserved[0]["bot_kind"] == "scrumming"
    assert registry.reserved[0]["total_holdings"] == pytest.approx(HOLDINGS)
    assert registry.heartbeats == ["bot-grant01"]
    record = _one_record(sink)
    assert record.ok is True
    assert record.actual == pytest.approx(NEEDED)
    assert record.expected == pytest.approx(NEEDED)
    assert record.context["bot_id"] == "bot-grant01"
    assert record.context["asset"] == "BTC"
    assert record.context["capped"] is False


# -- the two-sided control --------------------------------------------

def test_the_verdict_is_true_when_the_held_quantity_is_inside_the_band(
        sink: Any) -> None:
    """Inside the band the update path keeps the reservation in.

    The two halves are DIFFERENT NUMBERS here and the verdict is still
    True. Before the repair they were the same expression, so this case
    could not exist at all.
    """
    registry = _Registry()
    stub = _bot(registry)
    registry.after_heartbeat = _desync_to(stub, INSIDE_BAND)

    _ensure(stub)

    record = _one_record(sink)
    assert record.actual == pytest.approx(INSIDE_BAND)
    assert record.expected == pytest.approx(NEEDED)
    assert record.actual != record.expected, (
        "the record carried one value twice, which is the defect this "
        "unit removed")
    assert record.ok is True


def test_the_verdict_is_false_when_the_held_quantity_is_outside_the_band(
        sink: Any) -> None:
    """THE HALF THAT COULD NOT HAPPEN BEFORE.

    Same method, same emitter, same injection seam as the case above,
    and one number changed. A held reservation 5 % away from what the
    tick needs is a reservation the update path was supposed to have
    corrected and did not.
    """
    registry = _Registry()
    stub = _bot(registry)
    registry.after_heartbeat = _desync_to(stub, OUTSIDE_BAND)

    _ensure(stub)

    record = _one_record(sink)
    assert record.actual == pytest.approx(OUTSIDE_BAND)
    assert record.expected == pytest.approx(NEEDED)
    assert record.ok is False, (
        "the held reservation is outside the 1 % band the update path "
        "maintains and the pin reported it green")


@pytest.mark.parametrize("held", [0.0, -1.0])
def test_a_held_quantity_of_zero_or_less_is_not_a_pass(
        sink: Any, held: float) -> None:
    """There is nothing for a band to be measured against.

    The update path above the record reads this state the same way: it
    sets `_drift = 1.0` and pushes an update. Reporting it green here
    would be the unconditional pass this unit exists to remove, wearing
    a divisor that does not exist.
    """
    registry = _Registry()
    stub = _bot(registry)
    registry.after_heartbeat = _desync_to(stub, held)

    _ensure(stub)

    record = _one_record(sink)
    assert record.actual == pytest.approx(held)
    assert record.ok is False


# -- the verdict has to survive the wire ------------------------------

def test_a_failing_verdict_is_not_throttled_away(sink: Any) -> None:
    """The pin admits one record per 60 s. A red is never one of them.

    Both ticks happen inside the same second, so the second record is
    admitted only because its verdict is False. Rate-limiting the thing
    the network was built to catch is how a spam control becomes a
    blindfold.

    The divergence is planted at the END of the second tick, after the
    drift test has already read a mirror that agreed. So the tick has
    nothing to update, and the record is the only thing on the tick
    that can report the state it was left in.
    """
    registry = _Registry()
    stub = _bot(registry)

    _ensure(stub)
    registry.after_heartbeat = _desync_to(stub, OUTSIDE_BAND)
    _ensure(stub)

    records = sink.records(PIN)
    assert [r.ok for r in records] == [True, False], (
        "the second tick's failing record was suppressed by the 60 s "
        "throttle, so a real divergence would go unrecorded for a "
        "minute")
    assert registry.updated == [], (
        "the second tick pushed an update, so it corrected the mirror "
        "itself and the red the record carries is not the one this "
        "test planted")


def test_the_verdict_can_be_recomputed_from_the_record_itself(
        sink: Any) -> None:
    """Both halves are rounded, and the verdict is judged on them.

    So a reader of the JSONL can reproduce `ok` from the two numbers
    the record carries instead of taking the verdict on trust. This
    asserts that property on both sides of the band.
    """
    for held in (INSIDE_BAND, OUTSIDE_BAND):
        registry = _Registry()
        stub = _bot(registry)
        registry.after_heartbeat = _desync_to(stub, held)
        sc.reset_throttle()

        _ensure(stub)

    records = sink.records(PIN)
    assert len(records) == 2
    for record in records:
        recomputed = bool(
            record.actual > 0.0
            and abs(record.expected - record.actual)
            / record.actual <= 0.01)
        assert record.ok is recomputed, (
            f"the record says ok={record.ok} but its own actual="
            f"{record.actual} and expected={record.expected} recompute "
            f"to {recomputed}")
