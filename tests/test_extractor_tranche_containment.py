"""An Extractor Tranche's return must ARRIVE ATOMICALLY, not in halves.

THE TWO HALVES ARE THE TWO TERMS OF ONE SUBTRACTION
The tick computes ``current_value = _current_holdings * ticker.last *
_quote_to_usd`` (`scrumming_bot.py:6247`) and then ``delta =
current_value - _target_balance`` (`scrumming_bot.py:7072`). An arrival
moves BOTH terms. Apply one half without the other and delta moves, in
whichever direction the missing half was:

    holdings booked, target not lifted -> delta POSITIVE.
        "If delta > 0 and delta_pct >= interval: SCRUM (sell excess...)"
        The parent sells the Extractor's gain straight back out as
        surplus. The child's work is undone by its own parent.

    target lifted, holdings not booked -> delta NEGATIVE.
        The parent buys to close a gap that does not exist, spending
        real USD on a phantom shortfall.

OPERATOR DESIGN, 2026-08-09:
    "rather than have an immediate Base Currency to USD sell fire this
     profit off as Surplus we want it protected by lifting the Target
     Balance to contain it and then have the received additional Base
     Currency to be distributed upward for further gains in terms of USD"

WHY THE LIFT IS SIZED FROM THE ARRIVAL
The lift equals what ACTUALLY LANDED in the balance -- an observed
quantity, already net of every fee the Extractor paid on both legs. It
does not compute a profit figure, so it cannot be gross or net. Measure
the arrival; do not compute the gain. Same exchange-truth principle as
``buy_safety``.

WHY IT MUST BE UNCAPPED
``_apply_fold_target_growth`` (`:1528`) applies a per-cycle Growth Rate
Cap (``max_target_growth_pct``, default 1.0% of anchor). A cap is WRONG
for containment: an Extractor returning more than 1% of anchor would have
its lift truncated, the uncontained remainder would read as excess, and
the parent would scrum it away -- the exact failure this prevents.

WHY THE HOLDINGS HALF IS A LOT AND NOT A NUMBER
Since v3.23.43 the bot owns exactly what is in ``_main_lots`` and derives
``_current_holdings`` from that source alone (`:6241`). The invariant
``sum(lot["units"]) == _current_holdings`` (`:553`) is checked by
``_main_lots_invariant_ok`` (`:12756`). Crediting holdings without a lot
breaks it, and the next drift-down reconcile rescales the lots and resets
holdings (`:10211-10219`), silently undoing the credit. Booking nothing at
all is no safer: the drift-UP policy (`:10221-10238`) refuses to claim
exchange units the bot never attributed to itself.

CONTRACT CHANGE, v3.25.5
v3.25.2 owned only the target half and delegated the holdings half to a
caller in prose. No caller was ever written. The method now performs both
writes itself, in one synchronous block. Two tests below were restated
for that: the purpose test no longer moves holdings by hand, and the
fail-closed test now also proves the holdings half is untouched on
refusal. Both assert the SAME invariant as before, more strongly.

CONTRACT CHANGE, v3.25.6 -- WHAT v3.25.5 SHIPPED THAT THESE TESTS MISSED
Both archetypes reported passed=True and the release gate exited 0 on the
v3.25.5 file, and ten defects were open in it. Three of them cost money
and every test in this file passed while they did:

    usd_value=True  ->  applied=True, target $200.00 -> $201.00.
        ``bool`` is an ``int`` subclass, ``float(True)`` is 1.0, and
        every numeric check below that reads 1.0 as a dollar.

    _anchor_target_balance = "not-a-number"  ->  ValueError raised, AND
        holdings 1.0 -> 1.1, target 200.0 -> 220.0, one lot appended,
        anchor untouched. The coercion sat INSIDE the atomic block,
        after three of the four writes. The method that exists to be
        atomic left durable half-applied state.

    base_units=1e-200 with quote_to_usd=1e-200  ->  ZeroDivisionError
        out of a documented fail-closed money path. Both factors were
        validated positive and finite; the PRODUCT was never checked,
        and it underflows to exactly 0.0.

And the atomicity emitter could not have caught any of it: its residual
expanded to ``b * u / (b * qrate) * qrate - u``, identically zero
whenever the two scalar writes ran, and it never read the lot. With a
ledger whose ``append`` silently dropped the write it still reported
``atomic: True``. Five source mutations survived the whole suite.

The tests added below are written so that each of those mutations FAILS
something. Every new assertion is paired with a positive control that
demonstrates the instrument can see the failure it screens for.

CONTRACT CHANGE, v3.25.7 -- WHAT v3.25.6 SHIPPED THAT THIS SUITE MISSED
v3.25.6 caught 19 of 19 mutations, passed both archetypes and cleared
the release gate at 2559 tests. Eleven defects were open in it. Three
were reproduced against the shipped file before anything was changed:

    usd_value="20.0", base_units="0.1"  ->  applied=True.
        Measured: holdings 1.0 -> 1.1, target $200.00 -> $220.00,
        anchor $200.00 -> $220.00, _main_lots 1 -> 2. The only type
        ground on the money path was ``isinstance(value, bool)``;
        everything else fell through to ``float()``, which parses
        strings. A money path was accepting text.

    the verdict reported atomic=True with nothing booked.
        ``_atomic_ok`` was three DIFFERENCES between writes plus a
        readability flag, and differences agree when nothing happens.
        Measured with the two scalar stores and the ledger append all
        dropped: delta_shift_usd 0.0, ledger_gap_usd 0.0,
        anchor_gap_usd 0.0, atomic True, main_lots_added 0.

    a ledger subclass raised from INSIDE the atomic block.
        ``isinstance(lots, list)`` admits a subclass, so ``append`` can
        be overridden. Measured with an append that stored the lot and
        then raised: RuntimeError escaped the method, _main_lots 1 -> 2,
        holdings and target unmoved, the :553 invariant 0.1 units apart.

Two more the same pass turned up: the D2 comment described a guard that
does not do what it says (an inf divisor is refused by the divisor
check, never by the price check), and the recorded KNOWN LIMITATION
named only half its blast radius -- a drift-down reconcile strands the
lifted ANCHOR as well as the lifted target, and the anchor is the base
the growth cap and the position ceiling are taken from.

The ledger is now required to be EXACTLY a list, which is what makes
"nothing inside the atomic block can raise" a proof instead of a claim.
That removes the overridden-``append`` fault injection, so the two tests
that used it are restated: one asserts the stronger outcome (refused
before any write, nothing mutated at all), and the read-back keeps a
live fault injection through ``_FlakyUnits`` -- a plain list whose
stored units do not read back the same twice.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import math
import re
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402


class _Bus:
    def __init__(self):
        self.events = []

    def emit(self, name, **kw):
        self.events.append((name, kw))


def _bot(*, target=200.0, anchor=200.0, holdings=1.0, price=200.0,
         quote_to_usd=1.0):
    """A parent base-currency bot, built the way the other tests build one.

    ``holdings`` is seeded through ``_main_lots`` as well, because the
    :553 invariant is one of the things under test and a fixture that
    started out violating it would prove nothing.
    """
    b = object.__new__(ScrummingBot)
    b.bot_id = "parent-eth"
    b.config = type("C", (), {
        "symbol": "ETH/USD",
        "target_asset": "ETH",
        "base_currency": "ETH",
        "target_balance": target,
        "max_target_growth_pct": 1.0,
        "profit_folding_active": True,
        "scrumming_interval_pct": 1.0,
    })()
    b._target_balance = target
    b._anchor_target_balance = anchor
    b._current_holdings = holdings
    b._quote_to_usd = quote_to_usd
    b._bus = _Bus()
    b._fold_tranches = []
    b._main_lots = ([{"units": holdings, "initial_buy_price": price}]
                    if holdings > 0 else [])
    return b


def _delta(bot, price):
    """The shipped decision quantity: scrumming_bot.py:6247 + :7072."""
    current_value = (bot._current_holdings * price
                     * float(bot._quote_to_usd or 1.0))
    return current_value - bot._target_balance


def _interval_usd(bot):
    """The scrum threshold in USD. USD on both sides of the comparison.

    Building a percentage and comparing it against the configured
    percentage is what TA Quant reports as TA004.
    """
    return bot._target_balance * bot.config.scrumming_interval_pct / 100.0


# ── the purpose test, and its controls ──────────────────────────────

def test_containment_holds_delta_flat_when_base_currency_arrives():
    """THE POINT. The arrival lands whole and delta does not move.

    RESTATED for v3.25.5. The old version moved ``_current_holdings`` by
    hand before calling, because the method owned only the target half.
    The invariant asserted is unchanged -- delta must not move -- but it
    is now asserted against the method doing BOTH halves, which is a
    stronger claim: no caller can get the pairing wrong.
    """
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    before = _delta(bot, 200.0)
    assert before == pytest.approx(0.0)

    # Extractor returns 0.1 ETH, worth $20 at the observed price. The
    # caller supplies both observed quantities and nothing else.
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    assert out["applied"] is True

    after = _delta(bot, 200.0)
    assert after == pytest.approx(before), (
        "containment must leave delta unchanged, else the parent scrums "
        f"the Extractor's gain (delta moved {before} -> {after})")
    # A method that did nothing at all would also leave delta flat.
    # Pin that both halves actually moved.
    assert bot._current_holdings == pytest.approx(1.1)
    assert bot._target_balance == pytest.approx(220.0)


def test_POSITIVE_CONTROL_without_containment_delta_goes_positive():
    """The paired case that must FAIL to contain.

    Same arrival, no lift. If this does not show a positive delta, the
    test above is measuring nothing and proves nothing.
    """
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    before = _delta(bot, 200.0)
    bot._current_holdings += 0.1          # arrival, no containment call
    after = _delta(bot, 200.0)

    assert after > before
    assert after == pytest.approx(20.0)
    assert abs(after) >= _interval_usd(bot), (
        "the uncontained arrival must exceed the scrum threshold, "
        "otherwise this control does not demonstrate the failure")


def test_POSITIVE_CONTROL_lift_without_units_drives_delta_negative():
    """The OTHER direction, which is what v3.25.2 actually shipped.

    Target lifted, holdings never booked. Delta goes negative by the
    whole arrival and the parent buys to close a gap that does not
    exist. If this does not show a negative delta past the threshold,
    the atomicity claim is untested in that direction.
    """
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    before = _delta(bot, 200.0)
    bot._target_balance += 20.0           # lift, no units booked
    after = _delta(bot, 200.0)

    assert after < before
    assert after == pytest.approx(-20.0)
    assert abs(after) >= _interval_usd(bot), (
        "the phantom shortfall must exceed the trade threshold, "
        "otherwise this control does not demonstrate the failure")


# ── the holdings half ───────────────────────────────────────────────

def test_the_method_books_the_holdings_half_itself():
    """No caller is required to pair anything. The method owns both."""
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    lots_before = len(bot._main_lots)

    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert out["applied"] is True
    assert bot._current_holdings == pytest.approx(1.1)
    assert len(bot._main_lots) == lots_before + 1
    assert out["main_lots_added"] == 1
    assert bot._main_lots[-1]["units"] == pytest.approx(0.1)


def test_the_arrival_keeps_the_main_lots_invariant():
    """sum(lot['units']) == _current_holdings, before and after."""
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    assert bot._main_lots_invariant_ok() is True

    bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert bot._main_lots_invariant_ok() is True


def test_POSITIVE_CONTROL_units_without_a_lot_break_the_invariant():
    """The instrument must be able to see the failure it screens for.

    Credit holdings and skip the lot -- exactly what an increment-only
    implementation would do. If ``_main_lots_invariant_ok`` still reads
    True here, the test above is checking nothing.
    """
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    bot._current_holdings += 0.1          # no matching lot appended
    assert bot._main_lots_invariant_ok() is False


def test_lot_price_is_the_observed_arrival_price():
    """The lot carries a price derived from the two observed quantities.

    ``_main_lots`` stores a QUOTE-side price (`:10928`, `:10945`), and
    USD = units x quote_price x quote_to_usd (`:4136`). With a non-USD
    quote the lot price must be quote-denominated, not the USD figure.
    """
    bot = _bot(target=200.0, holdings=1.0, price=100.0, quote_to_usd=2.0)
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert out["applied"] is True
    # $20 over 0.1 units at 2.0 USD per quote unit = 100.0 quote.
    assert out["arrival_price"] == pytest.approx(100.0)
    assert bot._main_lots[-1]["initial_buy_price"] == pytest.approx(100.0)


def test_delta_stays_flat_when_the_quote_is_not_usd():
    """The same invariant, with quote_to_usd != 1 so a unit slip shows."""
    bot = _bot(target=200.0, holdings=1.0, price=100.0, quote_to_usd=2.0)
    before = _delta(bot, 100.0)
    assert before == pytest.approx(0.0)

    bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert _delta(bot, 100.0) == pytest.approx(before)


# ── atomicity ───────────────────────────────────────────────────────

def _method_tree():
    src = textwrap.dedent(
        inspect.getsource(ScrummingBot.apply_extractor_tranche_return))
    return ast.parse(src)


def test_the_arrival_block_cannot_yield_to_the_event_loop():
    """The atomicity guarantee, stated as the property that produces it.

    Every coroutine in this app runs on the Qt GUI thread, so a
    synchronous block that never yields cannot be observed half
    applied. An ``await`` inside the method would hand control back to
    the loop between the two halves and reintroduce the transient delta.
    """
    assert not inspect.iscoroutinefunction(
        ScrummingBot.apply_extractor_tranche_return)
    suspends = [n for n in ast.walk(_method_tree())
                if isinstance(n, (ast.Await, ast.Yield, ast.YieldFrom))]
    assert suspends == [], (
        f"{len(suspends)} suspension point(s) inside the arrival method")


def test_POSITIVE_CONTROL_the_suspension_scanner_sees_an_await():
    """The scanner above must not be blind."""
    probe = ast.parse(
        "async def f():\n"
        "    x = 1\n"
        "    await g()\n"
        "    y = 2\n")
    suspends = [n for n in ast.walk(probe)
                if isinstance(n, (ast.Await, ast.Yield, ast.YieldFrom))]
    assert len(suspends) == 1


class _ObservingBus:
    """A bus that reads the bot's decision state at every emit.

    This is the closest a test can stand to a tick: anything the bot
    hands control to during the arrival sees whatever state exists at
    that moment.
    """

    def __init__(self, price):
        self.bot = None
        self.price = price
        self.deltas = []
        self.invariants = []
        self.events = []

    def emit(self, name, **kw):
        self.events.append((name, kw))
        self.deltas.append(_delta(self.bot, self.price))
        self.invariants.append(self.bot._main_lots_invariant_ok())


def test_no_observer_ever_sees_a_half_applied_arrival():
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    bus = _ObservingBus(200.0)
    bus.bot = bot
    bot._bus = bus

    bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert bus.deltas, "the observer never ran; this test proves nothing"
    for seen in bus.deltas:
        assert seen == pytest.approx(0.0)
    assert all(bus.invariants)


def test_POSITIVE_CONTROL_an_observer_between_the_halves_sees_the_gap():
    """Split the halves by hand; the same observer must report the gap."""
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    bus = _ObservingBus(200.0)
    bus.bot = bot
    bot._bus = bus

    bot._main_lots.append({"units": 0.1, "initial_buy_price": 200.0})
    bot._current_holdings += 0.1
    bus.emit("bot.log", message="a tick reads state here")
    bot._target_balance += 20.0

    assert bus.deltas[0] == pytest.approx(20.0)


def test_the_result_reports_the_residual_it_kept_at_zero():
    """USD gained by holdings minus USD added to target. USD both sides."""
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    assert out["atomic"] is True
    assert out["delta_shift_usd"] == pytest.approx(0.0, abs=1e-9)


# ── the invariants ──────────────────────────────────────────────────

def test_lift_is_exact_and_uncapped():
    """A return larger than the 1% Growth Rate Cap must lift in full."""
    bot = _bot(target=200.0, anchor=200.0)
    # 1% of anchor is $2.00. This return is 25x that.
    bot.apply_extractor_tranche_return(
        usd_value=50.0, source="extractor-1", base_units=0.25)
    assert bot._target_balance == pytest.approx(250.0)


def test_anchor_moves_with_target():
    bot = _bot(target=200.0, anchor=200.0)
    bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    assert bot._anchor_target_balance == pytest.approx(220.0)
    assert bot.config.target_balance == pytest.approx(220.0)


def test_result_is_structured():
    bot = _bot()
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    assert out["applied"] is True
    assert out["contained_usd"] == pytest.approx(20.0)
    assert out["new_target_balance"] == pytest.approx(220.0)
    assert out["new_holdings"] == pytest.approx(1.1)
    assert out["base_units"] == pytest.approx(0.1)


@pytest.mark.parametrize("bad", [0.0, -1.0, None, "x", float("nan"),
                                 float("inf")])
def test_bad_usd_value_mutates_nothing(bad):
    """FAIL-CLOSED. A money path must refuse rather than guess.

    RESTATED for v3.25.5: the same invariant -- a refusal mutates
    nothing -- now covers the holdings half too, which is where a
    half-applied refusal would cost money.
    """
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    out = bot.apply_extractor_tranche_return(
        usd_value=bad, source="extractor-1", base_units=0.1)
    assert out["applied"] is False
    assert "reason" in out
    assert bot._target_balance == pytest.approx(200.0)
    assert bot._anchor_target_balance == pytest.approx(200.0)
    assert bot._current_holdings == pytest.approx(1.0)
    assert len(bot._main_lots) == 1


@pytest.mark.parametrize("bad", [0.0, -1.0, None, "x", float("nan"),
                                 float("inf")])
def test_bad_base_units_mutates_nothing(bad):
    """``base_units`` is load-bearing now, so it is validated as hard.

    A tolerated 0.0 would lift the target and book no units, which is
    the negative-delta failure written as a default argument.
    """
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=bad)
    assert out["applied"] is False
    assert "reason" in out
    assert bot._target_balance == pytest.approx(200.0)
    assert bot._anchor_target_balance == pytest.approx(200.0)
    assert bot._current_holdings == pytest.approx(1.0)
    assert len(bot._main_lots) == 1


def test_base_units_has_no_default():
    """The signature must not offer the failing value as a convenience."""
    sig = inspect.signature(ScrummingBot.apply_extractor_tranche_return)
    assert sig.parameters["base_units"].default is inspect.Parameter.empty


@pytest.mark.parametrize("bad_rate", [-1.0, float("nan"), float("inf")])
def test_unusable_quote_rate_mutates_nothing(bad_rate):
    """Without a usable rate the arrival cannot be priced. Refuse.

    These three survive the ``or 1.0`` coercion the tick applies, so
    each would write a nonsense price into ``_main_lots``.
    """
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    bot._quote_to_usd = bad_rate
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    assert out["applied"] is False
    assert bot._target_balance == pytest.approx(200.0)
    assert bot._current_holdings == pytest.approx(1.0)


def test_zero_quote_rate_is_coerced_the_way_the_tick_coerces_it():
    """The containment arithmetic must read the rate the DECIDER reads.

    The tick prices the position as ``_current_holdings * ticker.last *
    float(self._quote_to_usd or 1.0)`` (`:6247`), so a stored 0.0 is
    read as 1.0 by the code that fires trades. Refusing it here, or
    pricing the arrival with 0.0, would put containment and decision on
    different numbers -- the one way a correct lift can still move
    delta. ``_delta`` below is the tick's own expression, so this
    passes only when the two coercions agree.
    """
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    bot._quote_to_usd = 0.0
    before = _delta(bot, 200.0)
    assert before == pytest.approx(0.0)

    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert out["applied"] is True
    assert _delta(bot, 200.0) == pytest.approx(before)
    assert bot._main_lots_invariant_ok() is True


def test_POSITIVE_CONTROL_a_mismatched_rate_moves_delta():
    """The instrument above must be able to see a coercion mismatch.

    Price the arrival at a rate of 2.0 while the decider reads 1.0.
    The units book at half the price the tick values them at, so delta
    drops by half the arrival and the parent chases a phantom gap.
    """
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    before = _delta(bot, 200.0)

    mispriced_units = 0.05          # $20 booked as if the rate were 2.0
    bot._main_lots.append({"units": mispriced_units,
                           "initial_buy_price": 200.0})
    bot._current_holdings += mispriced_units
    bot._target_balance += 20.0

    after = _delta(bot, 200.0)
    assert after < before
    assert after == pytest.approx(-10.0)


def test_missing_lot_ledger_mutates_nothing():
    """No ledger, no credit. Booking units it cannot hold breaks :553."""
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    del bot._main_lots
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    assert out["applied"] is False
    assert bot._target_balance == pytest.approx(200.0)
    assert bot._current_holdings == pytest.approx(1.0)


def test_emits_a_falsifiable_record():
    """Every claim needs an emitter that can falsify it."""
    bot = _bot()
    bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    names = [n for n, _ in bot._bus.events]
    assert any("extractor" in n or "bot.log" in n for n in names), names


def test_repeated_returns_accumulate_both_halves():
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0, price=200.0)
    for _ in range(3):
        bot.apply_extractor_tranche_return(
            usd_value=10.0, source="extractor-1", base_units=0.05)
    assert bot._target_balance == pytest.approx(230.0)
    assert bot._anchor_target_balance == pytest.approx(230.0)
    assert bot._current_holdings == pytest.approx(1.15)
    assert bot._main_lots_invariant_ok() is True
    assert _delta(bot, 200.0) == pytest.approx(0.0)


# ════════════════════════════════════════════════════════════════════
# v3.25.6 — the defects the v3.25.5 suite could not see
# ════════════════════════════════════════════════════════════════════

SOURCE_PATH = REPO_ROOT / "src" / "trading" / "scrumming_bot.py"


def _source_lines() -> list[str]:
    return SOURCE_PATH.read_text(encoding="utf-8").split("\n")


def _self_writes(func) -> set[str]:
    """Every ``self.<attr>`` written anywhere in ``func``.

    AST rather than grep: a plain assignment, an augmented assignment
    and an annotated assignment are three different nodes, and a scan
    that missed one would report a write site as clean.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    out: set[str] = set()
    for node in ast.walk(tree):
        targets: list = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for tgt in targets:
            if (isinstance(tgt, ast.Attribute)
                    and isinstance(tgt.value, ast.Name)
                    and tgt.value.id == "self"):
                out.add(tgt.attr)
    return out


def _lot_appends(func) -> list[int]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    return [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "append"
            and "main_lots" in ast.unparse(n.func.value)]


# ── D1: nothing is coerced inside the atomic block ──────────────────

def _atomic_block_tree() -> ast.Module:
    """Parse only the statements between the two ATOMIC ARRIVAL banners.

    The banners are load-bearing text, not decoration: they are what
    tells a future editor where the no-coercion rule applies, and this
    scanner reads them as the rule's boundary.
    """
    lines = textwrap.dedent(
        inspect.getsource(ScrummingBot.apply_extractor_tranche_return)
    ).split("\n")
    start = end = None
    for i, line in enumerate(lines):
        if "ATOMIC ARRIVAL" in line and "END ATOMIC" not in line:
            start = i
        elif "END ATOMIC ARRIVAL" in line:
            end = i
    assert start is not None, "the atomic block's opening banner is gone"
    assert end is not None, "the atomic block's closing banner is gone"
    assert end > start
    return ast.parse(textwrap.dedent("\n".join(lines[start + 1:end])))


def test_the_atomic_block_contains_assignments_only():
    """D1. The rule that makes a partial write impossible.

    v3.25.5 coerced ``_anchor_target_balance`` INSIDE this block, as the
    last of four writes. A stored "not-a-number" raised ValueError with
    the other three already durable. No amount of care at the call site
    fixes that; only the structural rule does -- every value the block
    writes is a validated local computed above it, and the block itself
    can do nothing but store them.
    """
    tree = _atomic_block_tree()
    assert tree.body, "the scanner found no statements; it proves nothing"

    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert len(calls) == 1, (
        f"the atomic block makes {len(calls)} calls; exactly one is "
        f"allowed, the ledger append, and it must take a name")
    assert isinstance(calls[0].func, ast.Attribute)
    assert calls[0].func.attr == "append"
    assert calls[0].args and isinstance(calls[0].args[0], ast.Name), (
        "the lot must be built and bound ABOVE the block; a dict "
        "literal here is a construction inside the atomic region")

    arithmetic = [n for n in ast.walk(tree)
                  if isinstance(n, (ast.BinOp, ast.BoolOp, ast.Compare,
                                    ast.IfExp, ast.Subscript))]
    assert arithmetic == [], (
        f"{len(arithmetic)} computation(s) inside the atomic block; "
        f"every one is a place a raise can strand a half write")

    for node in tree.body:
        assert isinstance(node, (ast.Assign, ast.Expr)), (
            f"{type(node).__name__} in the atomic block; assignments "
            f"and the single append only")


def test_POSITIVE_CONTROL_the_block_scanner_sees_a_coercion():
    """The scanner above must not be blind to the shape it screens for."""
    probe = ast.parse("x = float(y) + 1\nz.append({'a': 1})\n")
    calls = [n for n in ast.walk(probe) if isinstance(n, ast.Call)]
    arithmetic = [n for n in ast.walk(probe) if isinstance(n, ast.BinOp)]
    literal_args = [n for n in calls
                    if n.args and isinstance(n.args[0], ast.Dict)]
    assert len(calls) == 2
    assert len(arithmetic) == 1
    assert len(literal_args) == 1


def test_a_non_numeric_anchor_refuses_and_writes_nothing():
    """D1, behaviourally. The operator referee's probe 2, inverted.

    Before: ValueError escaped AND holdings 1.0 -> 1.1, target
    200.0 -> 220.0, lots 1 -> 2, anchor unmoved. After: a refusal, and
    all four values exactly where they started.
    """
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    bot._anchor_target_balance = "not-a-number"

    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert out["applied"] is False
    assert "_anchor_target_balance" in out["reason"]
    assert bot._current_holdings == pytest.approx(1.0)
    assert bot._target_balance == pytest.approx(200.0)
    assert len(bot._main_lots) == 1
    assert bot._anchor_target_balance == "not-a-number"
    assert bot._main_lots_invariant_ok() is True


def test_POSITIVE_CONTROL_a_coercion_between_writes_strands_three_of_four():
    """The v3.25.5 shape, run by hand, so the cost is on the record.

    Without this the test above could pass against a method that simply
    never writes anything, and the reader would have no evidence that
    the ordering was ever the difference.
    """
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    bot._anchor_target_balance = "not-a-number"

    with pytest.raises(ValueError):
        bot._main_lots.append({"units": 0.1, "initial_buy_price": 200.0})
        bot._current_holdings = bot._current_holdings + 0.1
        bot._target_balance = bot._target_balance + 20.0
        bot._anchor_target_balance = (
            float(bot._anchor_target_balance) + 20.0)

    assert bot._current_holdings == pytest.approx(1.1)
    assert bot._target_balance == pytest.approx(220.0)
    assert len(bot._main_lots) == 2
    assert bot._anchor_target_balance == "not-a-number"


# ── D2: the divisor is a product, and products underflow ────────────

@pytest.mark.parametrize("units,rate", [
    (1e-200, 1e-200),
    (5e-324, 1e-8),
    (1e-300, 1e-30),
])
def test_an_underflowing_price_divisor_refuses(units, rate):
    """D2. Both factors pass; their product is exactly 0.0.

    ``u / (b * qrate)`` raised ZeroDivisionError straight out of a
    method whose docstring promises to refuse rather than guess.
    """
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    bot._quote_to_usd = rate

    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=units)

    assert out["applied"] is False
    assert "divisor" in out["reason"]
    assert bot._target_balance == pytest.approx(200.0)
    assert bot._anchor_target_balance == pytest.approx(200.0)
    assert bot._current_holdings == pytest.approx(1.0)
    assert len(bot._main_lots) == 1


def test_POSITIVE_CONTROL_the_product_underflows_while_both_factors_pass():
    """Per-factor validation cannot see this. That is the whole defect."""
    units, rate = 1e-200, 1e-200
    for value in (units, rate):
        assert math.isfinite(value)
        assert value > 0
    assert units * rate == 0.0
    with pytest.raises(ZeroDivisionError):
        _ = 20.0 / (units * rate)


def test_an_overflowing_divisor_refuses_too():
    """The mirror case. An inf divisor gives a zero price, not a crash."""
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    bot._quote_to_usd = 1e300
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=1e300)
    assert out["applied"] is False
    assert bot._target_balance == pytest.approx(200.0)


# ── D3: a flag is not an amount ─────────────────────────────────────

@pytest.mark.parametrize("flag", [True, False])
def test_a_bool_usd_value_is_refused(flag):
    """D3. ``usd_value=True`` lifted the target by exactly $1.00."""
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    out = bot.apply_extractor_tranche_return(
        usd_value=flag, source="extractor-1", base_units=0.1)
    assert out["applied"] is False
    assert "bool" in out["reason"]
    assert bot._target_balance == pytest.approx(200.0)
    assert bot._anchor_target_balance == pytest.approx(200.0)
    assert bot._current_holdings == pytest.approx(1.0)
    assert len(bot._main_lots) == 1


@pytest.mark.parametrize("flag", [True, False])
def test_a_bool_base_units_is_refused(flag):
    """The other half. ``base_units=True`` booked 1.0 whole unit."""
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=flag)
    assert out["applied"] is False
    assert "bool" in out["reason"]
    assert bot._current_holdings == pytest.approx(1.0)
    assert len(bot._main_lots) == 1


def test_POSITIVE_CONTROL_the_numeric_checks_cannot_see_a_bool():
    """Why the refusal has to be by TYPE, ahead of every numeric test."""
    assert isinstance(True, int)
    assert float(True) == 1.0
    assert math.isfinite(float(True))
    assert float(True) > 0


# ── D4: the atomicity emitter must be able to fail ──────────────────

class _DropAppendLedger(list):
    """A ledger subclass that accepts the call and drops the write.

    v3.25.7 -- THIS IS NOW A REFUSAL CASE, NOT A DETECTION CASE. An
    overridden ``append`` is caller-supplied Python running inside the
    atomic block, which is the one region the method promises nothing
    can raise from. The method therefore requires the ledger to be
    EXACTLY a ``list``, and this class is refused before any write. Kept
    because the refusal is the assertion.
    """

    def append(self, item: object) -> None:
        """Swallow the lot; store nothing."""
        del item


class _RaiseAfterAppendLedger(list):
    """The subclass that actually cost money: it stores, then raises.

    Reproduced against v3.25.6: RuntimeError escaped the method with
    ``_main_lots`` 1 -> 2 and both scalars unmoved -- durable
    half-applied state out of the block whose only job is atomicity.
    """

    def append(self, item: object) -> None:
        """Store the lot, then fail the way a real index rebuild would."""
        list.append(self, item)
        raise RuntimeError("ledger index rebuild failed")


class _FlakyUnits:
    """A stored ``units`` value that does not read back the same twice.

    The live fault injection for the ledger read-back, and it needs no
    subclass: the ledger stays a plain ``list`` and a plain ``dict``
    lot, and only the number inside changes between the pre-write read
    and the post-write read. That is enough to hide an appended lot from
    ``_sum_lot_units``, which is exactly what an ``append`` that stored
    nothing used to do.
    """

    def __init__(self, first: float, then: float) -> None:
        self.reads = 0
        self._first = float(first)
        self._then = float(then)

    def __float__(self) -> float:
        self.reads += 1
        return self._first if self.reads <= 1 else self._then


def _flaky_ledger_bot(*, hidden: float = 0.1) -> ScrummingBot:
    """A healthy bot whose seeded lot hides ``hidden`` units on re-read.

    The ledger reads 1.0 units before the arrival and ``1.0 - hidden``
    after it, so the 0.1-unit lot the method appends is exactly masked
    and ``_lot_units_booked`` comes back 0.0.
    """
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    bot._main_lots = [{"units": _FlakyUnits(1.0, 1.0 - hidden),
                       "initial_buy_price": 200.0}]
    return bot


@pytest.fixture
def sink():
    """Install a SignalSink for the duration of one test."""
    from src.core import signal_contract as sc
    previous = sc.get_sink()
    collector = sc.SignalSink(path=None)
    sc.reset_throttle()
    sc.set_sink(collector)
    try:
        yield collector
    finally:
        sc.set_sink(previous)


def test_the_arrival_emits_its_atomicity_record(sink):
    """D4, mutation 1: DELETE THE EMITS. This test then fails."""
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert sink.count("extractor.02.002.invariant.arrival_atomic") == 1, (
        "no atomicity record was emitted; an emitter that no test "
        "exercises is decoration")
    assert sink.count("extractor.02.001.postcondition.tranche_contained") == 1


def test_the_atomicity_emitter_keeps_its_contract_name(sink):
    """D4, mutation 2: RENAME THE EMITTER. This test then fails.

    The name is the join key between the running platform and anything
    that reads its records. A renamed signal is a deleted signal to
    every consumer.
    """
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert "extractor.02.002.invariant.arrival_atomic" in sink.names()
    assert "extractor.02.001.postcondition.tranche_contained" in sink.names()


def test_a_ledger_that_drops_the_lot_is_refused_before_any_write(sink):
    """D4 RESTATED, v3.25.7, to the stronger outcome.

    v3.25.6 accepted this ledger, booked the two scalars against a lot
    the ledger never stored, and reported ``atomic: False`` afterwards.
    Reporting a half-applied arrival is better than missing one, and
    refusing it outright is better still: the exact-list guard runs
    before the first write, so no scalar moves and there is nothing to
    report on. Money not moved beats money moved and logged.
    """
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    bot._main_lots = _DropAppendLedger(bot._main_lots)

    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert out["applied"] is False
    assert "_main_lots" in out["reason"]
    assert "_DropAppendLedger" in out["reason"], out["reason"]
    assert bot._target_balance == pytest.approx(200.0)
    assert bot._anchor_target_balance == pytest.approx(200.0)
    assert bot._current_holdings == pytest.approx(1.0)
    assert len(bot._main_lots) == 1
    assert bot._main_lots_invariant_ok() is True
    assert sink.count("extractor.02.002.invariant.arrival_atomic") == 0


def test_a_ledger_that_raises_from_append_is_refused_before_any_write():
    """R3. The subclass that split the atomic block, measured.

    Against v3.25.6: ``RuntimeError`` escaped a method documented as
    fail-closed, ``_main_lots`` went 1 -> 2, ``_current_holdings`` and
    ``_target_balance`` did not move, and the :553 invariant was left
    0.1 units apart -- durable half-applied state produced BY the block
    that exists to prevent it. ``isinstance`` let it in; exact-list
    keeps it out.
    """
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    bot._main_lots = _RaiseAfterAppendLedger(bot._main_lots)

    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert out["applied"] is False
    assert "_main_lots" in out["reason"]
    assert len(bot._main_lots) == 1
    assert bot._current_holdings == pytest.approx(1.0)
    assert bot._target_balance == pytest.approx(200.0)
    assert bot._anchor_target_balance == pytest.approx(200.0)
    assert bot._main_lots_invariant_ok() is True


def test_POSITIVE_CONTROL_that_ledger_really_does_raise_and_strand():
    """The instrument above must screen for a failure that is real.

    Run the v3.25.6 block shape by hand -- append first, then the three
    stores -- and the raise lands between them, exactly as measured.
    """
    ledger = _RaiseAfterAppendLedger([{"units": 1.0,
                                       "initial_buy_price": 200.0}])
    assert isinstance(ledger, list), (
        "isinstance is what admitted this ledger; if that stops being "
        "true the defect being screened for has changed")
    assert type(ledger) is not list

    holdings, target = 1.0, 200.0
    with pytest.raises(RuntimeError):
        ledger.append({"units": 0.1, "initial_buy_price": 200.0})
        holdings = holdings + 0.1
        target = target + 20.0

    assert len(ledger) == 2
    assert holdings == pytest.approx(1.0)
    assert target == pytest.approx(200.0)


def test_a_ledger_that_does_not_read_back_is_reported_not_atomic(sink):
    """D4, mutations 3 and 4: HARDCODE ok=True, or WIDEN THE TOLERANCE.

    Either one makes this test fail. The ledger is a plain list and the
    append really lands; the SEEDED lot reads 1.0 before the arrival and
    0.9 after it, so the ledger's own witness says nothing was booked.
    That is the same observable as an append that stored nothing, and it
    keeps the read-back a live instrument now that the subclass route is
    refused up front.
    """
    bot = _flaky_ledger_bot()

    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert out["applied"] is True
    assert out["main_lots_added"] == 1
    assert out["lot_units_booked"] == pytest.approx(0.0)
    assert out["lot_gap_usd"] == pytest.approx(-20.0)
    assert out["atomic"] is False, (
        "the ledger read back no new units and the method still called "
        "the arrival atomic")
    assert out["ledger_gap_usd"] == pytest.approx(-20.0)

    records = sink.records("extractor.02.002.invariant.arrival_atomic")
    assert len(records) == 1
    assert records[0].ok is False
    assert records[0].context["lot_units_booked"] == pytest.approx(0.0)
    assert records[0].context["lot_units_expected"] == pytest.approx(0.1)


def test_POSITIVE_CONTROL_the_healthy_arrival_is_reported_atomic(sink):
    """The paired control.

    Without it the assertion above could be satisfied by a method that
    reports False unconditionally, which would be just as blind.
    """
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert out["atomic"] is True
    assert out["lot_units_booked"] == pytest.approx(0.1)
    assert out["ledger_gap_usd"] == pytest.approx(0.0, abs=1e-9)
    assert out["anchor_gap_usd"] == pytest.approx(0.0, abs=1e-9)
    records = sink.records("extractor.02.002.invariant.arrival_atomic")
    assert len(records) == 1
    assert records[0].ok is True


def test_the_tolerance_is_too_small_to_hide_an_arrival():
    """D4, mutation 5: WIDEN _ARRIVAL_ATOMIC_TOL_USD. Fails here.

    The mutation that survived was 1e-6 -> 1e9, which makes every
    residual this method can produce compare "within tolerance". The
    bound below is not arbitrary: an arrival worth less than a cent is
    not worth booking, so a tolerance at or above a cent could hide a
    whole arrival.
    """
    tolerance = ScrummingBot._ARRIVAL_ATOMIC_TOL_USD
    assert tolerance > 0
    assert tolerance < 0.01, (
        f"tolerance {tolerance!r} is large enough to hide a real "
        f"arrival; it is part of the check, not a knob")


def test_POSITIVE_CONTROL_a_wide_tolerance_would_swallow_the_residual():
    """The arithmetic the bound above protects, stated once."""
    residual_usd = -20.0
    assert abs(residual_usd) > ScrummingBot._ARRIVAL_ATOMIC_TOL_USD
    assert abs(residual_usd) <= 1e9


def test_a_corrupt_lot_after_a_good_arrival_refuses_the_next_one(sink):
    """A ledger that stops being summable cannot be added to again."""
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    assert out["atomic"] is True

    bot._main_lots[-1]["units"] = "corrupted"
    followup = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    assert followup["applied"] is False
    assert "units" in followup["reason"]
    assert bot._target_balance == pytest.approx(220.0)
    assert sink.count("extractor.02.002.invariant.arrival_atomic") == 1


# ── D6: the atomicity claim, with its condition ─────────────────────

def test_the_arrival_adds_no_delta_of_its_own_only_mark_to_market():
    """D6. ``d(delta) = base_units * quote_to_usd * (P - arrival_price)``.

    The v3.25.5 docstring said delta "cannot transiently move in either
    direction" and named no price. It is zero AT THE ARRIVAL PRICE; at
    any other price the newly booked units mark to market exactly as
    bought units would. Two bots, identical but for the arrival, make
    the difference measurable at several prices.
    """
    contained = _bot(target=200.0, holdings=1.0, price=200.0)
    untouched = _bot(target=200.0, holdings=1.0, price=200.0)

    out = contained.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    arrival_price = out["arrival_price"]

    assert _delta(contained, arrival_price) == pytest.approx(
        _delta(untouched, arrival_price)), (
        "at the arrival price the containment must be exact")

    for probe_price in (180.0, 210.0, 250.0):
        gap = (_delta(contained, probe_price)
               - _delta(untouched, probe_price))
        expected = 0.1 * 1.0 * (probe_price - arrival_price)
        assert gap == pytest.approx(expected), (
            f"at ${probe_price} the arrival moved delta by {gap}, not "
            f"the mark-to-market {expected} the docstring states")


def test_POSITIVE_CONTROL_the_condition_is_not_vacuous():
    """At $210 the mark-to-market term is real, not float noise."""
    assert 0.1 * 1.0 * (210.0 - 200.0) == pytest.approx(1.0)


# ── D5: the pairing does not survive reconciliation ─────────────────

def test_reconcile_holdings_never_writes_the_target_balance():
    """D5, structurally. The claim the docstring's limitation rests on."""
    writes = _self_writes(ScrummingBot._reconcile_holdings)
    assert "_current_holdings" in writes
    assert "_main_lots" in writes
    assert "_target_balance" not in writes, (
        "reconcile now moves the target; the KNOWN LIMITATION section of "
        "apply_extractor_tranche_return is stale and must be rewritten")


def test_KNOWN_LIMITATION_drift_down_reconcile_breaks_the_pairing():
    """D5, behaviourally. Recorded, not fixed. Read the docstring first.

    A drift-DOWN rescale removes the arrived units and leaves the lift
    in place, so delta goes to -$20.00 on a $20 arrival. This test
    exists so the limitation cannot change without the text that
    describes it changing too. It asserts the CURRENT behaviour on
    purpose; if it ever fails, the fix is to update the docstring, not
    to loosen the test.
    """
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0, price=200.0)
    bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    assert _delta(bot, 200.0) == pytest.approx(0.0)

    async def _balance(asset):
        assert asset == "ETH"
        return type("B", (), {"free": 1.0})()

    bot._get_balance = _balance
    assert asyncio.run(bot._reconcile_holdings(reason="test")) is True

    assert bot._current_holdings == pytest.approx(1.0)
    assert bot._target_balance == pytest.approx(220.0)
    assert bot._anchor_target_balance == pytest.approx(220.0), (
        "v3.25.7 -- the anchor is stranded too, and it is the wider "
        "half: the growth cap and the position ceiling are both taken "
        "from it")
    assert _delta(bot, 200.0) == pytest.approx(-20.0), (
        "the documented limitation changed; update the KNOWN LIMITATION "
        "section of the docstring to match")


# ── D7: how the rest of the file really maintains the two halves ────

def test_execute_buy_moves_the_scalar_and_appends_no_lot():
    """D7. The premise the v3.25.5 summary asserted, and got backwards.

    It claimed "every other credit site appends a lot AND moves the
    scalar". ``_execute_buy`` moves the scalar and appends nothing; its
    callers append after the await returns. That split is precisely why
    a caller-side pairing is unsafe, and therefore why this method owns
    both halves itself.
    """
    assert inspect.iscoroutinefunction(ScrummingBot._execute_buy)
    assert _lot_appends(ScrummingBot._execute_buy) == [], (
        "_execute_buy now appends a lot; the docstring's derivation of "
        "the two shapes is stale")
    assert "_current_holdings" in _self_writes(ScrummingBot._execute_buy)


def test_the_containment_method_does_both_halves_without_suspending():
    """The contrast that makes the split above matter.

    ``_lot_appends`` is not the right scanner here: this method binds
    the ledger to a local (``lots = getattr(self, "_main_lots", None)``)
    so the refusal path can run before any write, so the append reads
    ``lots.append(...)`` and not ``self._main_lots.append(...)``. The
    atomic-block scanner is the exact instrument, and it already proves
    there is precisely one append and that it takes a bound name.
    """
    assert not inspect.iscoroutinefunction(
        ScrummingBot.apply_extractor_tranche_return)
    appends = [n for n in ast.walk(_atomic_block_tree())
               if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Attribute)
               and n.func.attr == "append"]
    assert len(appends) == 1
    writes = _self_writes(ScrummingBot.apply_extractor_tranche_return)
    for attr in ("_current_holdings", "_target_balance",
                 "_anchor_target_balance"):
        assert attr in writes


def test_POSITIVE_CONTROL_the_append_scanner_finds_a_real_append():
    """The scanner used above must not report empty for every function."""
    assert _lot_appends(ScrummingBot._execute_manual_rebalance)


# ── D8 and D9: citations must point at what they claim ──────────────

CITATION_ANCHORS: dict[int, str] = {
    574: '# Invariant: sum(l["units"] for l in _main_lots)',
    1664: 'def _apply_fold_target_growth(self, accum_profit: float,',
    1738: '_cycle_cap_growth = self._anchor_target_balance * (_cap_pct',
    2414: 'self._target_balance = float(self._target_balance) + u',
    2418: 'self.config.target_balance = self._target_balance',
    2510: 'def _positive_observed_quantity(',
    2572: 'def _finite_state_number(',
    2617: 'def _sum_lot_units(lots: Any) -> tuple[float | None, str | None]:',
    3489: 'fill_price = await self._execute_buy(',
    3534: 'self._main_lots.append({',
    4655: 'return float(self._current_holdings) * float(price)',
    4750: 'return self._anchor_target_balance * mult',
    5722: '_tracked_units_bootstrap = sum(',
    5727: 'self._current_holdings = min(',
    6401: 'float(getattr(_bal1, "total", 0)',
    6443: 'getattr(_bal1, "absent", False) or',
    6664: 'self._current_holdings = sum(',
    6831: '# _main_lots and derives _current_holdings from that source',
    6837: 'self._current_holdings * ticker.last',
    7604: 'entry_fill = await self._execute_buy(',
    7627: 'self._main_lots.append({',
    7662: 'delta = current_value - self._target_balance',
    9316: 'price <= tranche["initial_buy_price"]',
    9584: '_patent_only_eligible = sum(',
    9845: '# MEM-171 / ADR-004 patent invariant is NOT abandoned in',
    9857: 'if ticker.last <= float(t.get("ref", 0)) * _otd_factor',
    10064: 'buy_fill = await self._execute_buy(',
    10121: 'self._main_lots.append({',
    10573: 'hedge_fill = await self._execute_buy(',
    10607: 'self._main_lots.append({',
    11524: 'async def _reconcile_holdings(self, reason:',
    # 2026-08-13 re-anchor, U2. ONE insertion into scrumming_bot.py --
    # the two units parsers, the block that widens the audited figure
    # from the scalar to the lot book, and the coerced rescale write --
    # placed between the fold-merge return above and the U1 label block
    # below. FOUR shift bands, not one, because the insertion is in
    # three pieces with anchors between them: +0 at and above :10992,
    # +122 through the reconcile docstring, +191 at the drift-down
    # branch, +202 below the rescale. A flat shift would have moved two
    # anchors to the wrong lines. Derived the same way as the notes
    # above, by anchor ordinal plus monotonic shift and no difflib:
    # each anchor's occurrence count in the pre-change file located the
    # same occurrence in the post-change file, the shifts were required
    # to be non-negative and non-decreasing, and every relocated line
    # was re-read and confirmed to still hold the text recorded beside
    # it. 22 anchors did not move; 12 moved. SIX ANCHORS ARE NEW:
    # :2289, :2351, :2396, :5486, :5491 and :6425, because the two new
    # parsers cite their three neighbours and the clamp they exist to
    # defend against, and DOCUMENTED_METHODS now reads them.
    #
    # TWELVE PROSE CITATIONS WERE SHIFTED TOO, at :2420, :2520, :2523,
    # :2563, :2568, :2572, :2582, :2583, :2590 and :2591. They are not
    # anchors; they are `:NNNN` tokens inside the documented methods
    # that named lines below the insertion. Re-anchoring the table
    # without them would have left the checker green over ten wrong
    # numbers.
    #
    # 2026-08-13 re-anchor, U2 SECOND PASS -- the venue field and the
    # absent marker. A SECOND insertion into the same method on top of
    # the one described above: the venue read now takes the wallet
    # TOTAL with the startup handshake's own fallback chain, an absent
    # reading is refused before anything is written, and the units
    # parser grew an exact int/float type ground. +97 lines.
    #
    # FOUR bands again, and they are NOT the bands above. These are
    # measured against the PREVIOUS pass, not against live: +0 at and
    # above the parser docstring, +19 through the reconcile docstring,
    # +94 at the drift-down branch, +97 below the rescale. Measured
    # against the pre-U2 file the same three anchors are +141, +285
    # and +299. The note above states its own pass and is left as it
    # was written, so the two records are additive and neither is
    # retro-edited.
    #
    # Same method as every note above: anchor ordinal plus monotonic
    # shift, never difflib; shifts required non-negative and
    # non-decreasing; every relocated line re-read and confirmed to
    # still hold the text recorded beside it. 28 anchors did not move,
    # 12 moved, and NO anchor is new -- this pass added no method.
    #
    # THE SAME TWELVE PROSE CITATIONS MOVED AGAIN and were rewritten
    # again, to the same numbers this table now records. A thirteenth
    # was corrected on a different ground: the absent block cited
    # `(:1117)`, and every other `:NNNN` token in that file reads as
    # "this file" while that one meant ccxt_connector.py. It is
    # written out in full now. That correction was made to fit inside
    # the three lines it replaced, because one added line above the
    # drift-down branch would have moved every anchor below it a
    # second time.
    11793: 'if exchange_units < internal_units - 1e-9:',
    11815: 'self._current_holdings = exchange_units',
    11817: '# Drift UP. Operator directive 2026-08-22, verbatim:',
    11849: '_adopt = min(exchange_units, _claimable)',
    12070: 'async def _execute_manual_rebalance(',
    # 2026-08-15 re-anchor, the nan-ladder unit. ONE insertion, +104
    # lines, entirely inside the U3 gate block in
    # `_execute_manual_rebalance`: the ref filter that replaced the bare
    # `max()` genexp, and the FOLD REF UNREADABLE emit beside it.
    #
    # TWO BANDS, and they are clean: +0 at and above :11557, +104 from
    # :12358 down. 36 anchors did not move, 6 moved, NO anchor is new --
    # this unit added no method, and `_execute_manual_rebalance` is not
    # in DOCUMENTED_METHODS, so the five `:NNNN` tokens the new comment
    # cites (:1748, :9549, :9638, :9645, :11021) are not read by
    # `_cited_line_numbers` and need no anchor. All five name lines
    # ABOVE the insertion and therefore did not move.
    #
    # Derived the same way as every note above: anchor ordinal plus
    # monotonic shift, never difflib. Each anchor's occurrence count in
    # the pre-change file located the SAME occurrence in the post-change
    # file -- which matters here, because ':12358' and ':12375' are the
    # 6th and 7th occurrences of `self._main_lots.append({` and a
    # first-match search would have collapsed them onto :3313. Shifts
    # were required non-negative and non-decreasing, and every relocated
    # line was re-read and confirmed to still hold the text beside it.
    # Zero violations.
    #
    # THE COUNT IS 42, NOT 34. The work order for this unit said "all 34
    # CITATION_ANCHORS". Counted twice -- once by a regex parser over
    # the source, once by `ast.literal_eval` of the dict itself -- and
    # both read 42. The stale number was the work order's, and it is
    # recorded here so the next reader does not trust it either.
    13031: 'self._main_lots.append({',
    13048: 'self._main_lots.append({',
    13057: 'self._current_holdings += fill_amount',
    14697: 'async def _execute_buy(',
    15174: 'self._current_holdings += amount',
    15299: 'def _main_lots_invariant_ok(self, tol: float = 1e-6) -> bool:',
    # 2026-08-20 re-anchor, ISSUE #21 -- the capital-reservation grant
    # postcondition. ONE insertion into `scrumming_bot.py`, +47 lines,
    # entirely inside the success branch of
    # `_ensure_capital_reservation`: the comment that states what the
    # two halves of the check now read, the two locals the record is
    # built from, and the explicit `ok`.
    #
    # TWO BANDS, and they are clean: +0 at :574, +47 from :1581 down.
    # 41 anchors moved, 1 did not, and NO anchor is new -- the unit
    # added no method and `_ensure_capital_reservation` is not in
    # DOCUMENTED_METHODS.
    #
    # Derived the same way as every note above: anchor ordinal plus
    # monotonic shift, never difflib. Each anchor's occurrence count in
    # the pre-change file located the SAME occurrence in the post-change
    # file -- which matters again here, because `self._main_lots.append({`
    # occurs seven times and a first-match search collapses all seven
    # onto one line. Shifts were required non-negative and
    # non-decreasing, and every relocated line was re-read from disk and
    # confirmed to still hold the text recorded beside it. Zero
    # violations.
    #
    # THE PROSE CITATIONS INSIDE `scrumming_bot.py` MOVED TOO, and they
    # were rewritten in the same unit: every `:NNNN` token in that file
    # naming a line below the insertion is +47. That is 61 lines of
    # prose, not only the ones `_cited_line_numbers` reads, because
    # `tests/test_autonomous_fold_price_gate.py` rewrites EVERY token in
    # the file through its reversal map and its pre-change digest goes
    # red on any token that was left behind.
}

# Every method whose prose is allowed to cite a line. v3.25.7 widened
# this from two to five: the three parsers acquired citations of their
# own, and a citation the checker does not read is a citation that rots.
#
# U2 widens it to eight, on the same reasoning. The two new units
# parsers cite their three neighbours to say how their contracts
# differ, and `_reconcile_holdings` cites the bootstrap clamp that
# created the divergence it now detects. Prose that names a line has to
# be readable by this checker or it rots exactly the way the numbers it
# replaced did.
DOCUMENTED_METHODS = (
    ScrummingBot.apply_extractor_tranche_return,
    ScrummingBot._main_lots_invariant_ok,
    ScrummingBot._positive_observed_quantity,
    ScrummingBot._finite_state_number,
    ScrummingBot._sum_lot_units,
    ScrummingBot._reconcilable_units,
    ScrummingBot._reconcilable_lot_book,
    ScrummingBot._reconcile_holdings,
)

_CITATION_RE = re.compile(r":(\d{3,5})(?:-(\d{3,5}))?")


def _cited_line_numbers() -> set[int]:
    """Every ``:NNNN`` the documented methods cite."""
    found: set[int] = set()
    for func in DOCUMENTED_METHODS:
        for match in _CITATION_RE.finditer(inspect.getsource(func)):
            for group in match.groups():
                if group:
                    found.add(int(group))
    return found


def test_every_citation_points_at_the_line_it_claims():
    """D8. A previous round shipped pre-edit numbers as post-edit ones.

    Line numbers rot on every edit above them, and prose cannot be
    trusted to notice. This reads the file and checks that each cited
    line still holds the thing it was cited for.
    """
    lines = _source_lines()
    for lineno, anchor_text in CITATION_ANCHORS.items():
        assert 1 <= lineno <= len(lines), (
            f"citation :{lineno} is past the end of the file")
        assert anchor_text in lines[lineno - 1], (
            f"citation :{lineno} claims {anchor_text!r} but that line reads "
            f"{lines[lineno - 1].strip()!r}")


def test_every_cited_number_has_an_anchor():
    """Closes the loop: a new citation must bring its own anchor.

    Without this the table above could go stale by omission -- somebody
    adds a citation, nothing checks it, and the drift is back.
    """
    missing = sorted(_cited_line_numbers() - set(CITATION_ANCHORS))
    assert missing == [], (
        f"cited but unanchored: {missing}. Add each to CITATION_ANCHORS "
        f"with a phrase from the line it names.")


def test_POSITIVE_CONTROL_the_citation_checker_catches_a_shifted_line():
    """The checker must fail on a number that no longer holds its token."""
    lines = _source_lines()
    lineno = 574
    anchor_text = '# Invariant: sum(l["units"] for l in _main_lots)'
    assert anchor_text in lines[lineno - 1]
    assert anchor_text not in lines[lineno]


def test_the_invariant_helper_names_test_files_that_exist():
    """D9. It named a caller that is not in the repo at all.

    Every test file the helper's docstring names must exist on disk and
    must actually call it.
    """
    doc = inspect.getdoc(ScrummingBot._main_lots_invariant_ok) or ""
    named = re.findall(r"tests/[A-Za-z0-9_]+\.py", doc)
    assert named, "the helper names no test file at all"
    for relative in named:
        path = REPO_ROOT / relative
        assert path.exists(), f"{relative} is cited and does not exist"
        body = path.read_text(encoding="utf-8")
        assert "_main_lots_invariant_ok" in body, (
            f"{relative} is cited as a caller and never calls it")


# ── D10: the fail-closed promise, made true ─────────────────────────

def test_a_non_numeric_target_balance_refuses():
    """Raised ValueError before.

    Nothing had been written at that point, so it cost no money -- it
    cost the refusal contract the docstring promises.
    """
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    bot._target_balance = "oops"
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    assert out["applied"] is False
    assert "_target_balance" in out["reason"]
    assert bot._target_balance == "oops"
    assert len(bot._main_lots) == 1


def test_a_missing_holdings_scalar_refuses():
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    bot._current_holdings = None
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    assert out["applied"] is False
    assert "_current_holdings" in out["reason"]
    assert len(bot._main_lots) == 1


def test_a_source_that_cannot_be_rendered_refuses():
    """A caller-supplied object may raise from ``__str__``."""

    class _Unrenderable:
        def __str__(self) -> str:
            raise RuntimeError("source.__str__ exploded")

    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source=_Unrenderable(), base_units=0.1)
    assert out["applied"] is False
    assert "source" in out["reason"]
    assert bot._target_balance == pytest.approx(200.0)
    assert len(bot._main_lots) == 1


def test_a_corrupt_lot_in_the_ledger_refuses_the_arrival():
    """A ledger that cannot be summed cannot be added to."""
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    bot._main_lots.append({"units": None, "initial_buy_price": 1.0})
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    assert out["applied"] is False
    assert "_main_lots" in out["reason"]
    assert bot._target_balance == pytest.approx(200.0)
    assert len(bot._main_lots) == 2


def test_an_overflowing_target_refuses_rather_than_writing_inf():
    """The last thing that can produce a non-finite value is the add."""
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    bot._target_balance = 1.7e308
    out = bot.apply_extractor_tranche_return(
        usd_value=1.7e308, source="extractor-1", base_units=0.1)
    assert out["applied"] is False
    assert bot._target_balance == 1.7e308
    assert bot._current_holdings == pytest.approx(1.0)
    assert len(bot._main_lots) == 1


def test_POSITIVE_CONTROL_that_addition_really_overflows():
    """The overflow the refusal above screens for is real."""
    assert math.isinf(1.7e308 + 1.7e308)


def test_the_operator_log_line_reports_the_verdict_not_the_conclusion():
    """The audit line must read differently when the check fails.

    v3.25.5 ended every containment line with "both halves booked
    together so the arrival is neither scrummed nor chased", including
    the runs where nothing was booked. A line that reads the same
    whether the mechanism worked or not tells the operator nothing.
    """
    bot = _flaky_ledger_bot()
    bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    messages = [kw.get("message", "") for _, kw in bot._bus.events]
    contained = [m for m in messages if "EXTRACTOR TRANCHE CONTAINED" in m]
    assert contained, "no containment line was logged"
    assert "NOT ATOMIC" in contained[0], contained[0]
    assert "neither scrummed nor chased" not in contained[0]


def test_POSITIVE_CONTROL_the_healthy_log_line_states_containment():
    """The paired control: the good path must still say it succeeded."""
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    messages = [kw.get("message", "") for _, kw in bot._bus.events]
    contained = [m for m in messages if "EXTRACTOR TRANCHE CONTAINED" in m]
    assert contained, "no containment line was logged"
    assert "neither scrummed nor chased" in contained[0]
    assert "NOT ATOMIC" not in contained[0]


# ── R4: the success branch must publish what it checked ─────────────

def test_the_success_line_publishes_the_measurements_it_passed_on():
    """R4. v3.25.6's success branch stated a conclusion and no numbers.

    The failure branch printed gaps; the success branch printed "both
    halves booked together, so the arrival is neither scrummed nor
    chased" and nothing else. An audit line that reports a verdict
    without reporting what was measured cannot be audited -- it reads
    identically on a run that checked four terms and on a run that
    checked none. Both branches now carry the same measurements.
    """
    bot = _bot(target=200.0, holdings=1.0, price=200.0)
    bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    messages = [kw.get("message", "") for _, kw in bot._bus.events]
    line = next(m for m in messages if "EXTRACTOR TRANCHE CONTAINED" in m)

    assert "neither scrummed nor chased" in line
    for token in ("CHECKED", "lot 0.1 of 0.1 units", "holdings $",
                  "target $", "anchor $", "ledger gap $", "tol $"):
        assert token in line, f"{token!r} missing from the success line: {line}"


def test_POSITIVE_CONTROL_both_branches_carry_the_same_measurements():
    """The measured block must be the SAME text on both branches.

    Without this the success line could carry a different, weaker set of
    numbers and the assertion above would still pass.
    """
    good = _bot(target=200.0, holdings=1.0, price=200.0)
    good.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    bad = _flaky_ledger_bot()
    bad.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    def _fields(bot) -> set[str]:
        """The NAMES in the measured block, without their values."""
        messages = [kw.get("message", "") for _, kw in bot._bus.events]
        line = next(m for m in messages
                    if "EXTRACTOR TRANCHE CONTAINED" in m)
        inner = line.split("[", 1)[1].split("]", 1)[0]
        return {part.strip().split(" ")[0]
                for part in re.split(r"[,;]", inner)}

    assert _fields(good) == _fields(bad)
    assert len(_fields(good)) >= 5
    assert {"lot", "holdings", "target", "anchor"} <= _fields(good)


# ════════════════════════════════════════════════════════════════════
# v3.25.7 — the eleven defects the v3.25.6 suite could not see
# ════════════════════════════════════════════════════════════════════

def _deaf_bot(*dropped: str, **kwargs) -> ScrummingBot:
    """A bot whose ``__setattr__`` silently drops the named stores.

    This is the one failure the method cannot refuse in advance, and so
    the only lever that can make a SCALAR write go missing. Everything
    else about the bot is the ordinary fixture, so a test using it is
    testing the verdict and not the fixture.
    """
    class _Deaf(ScrummingBot):
        _DROPPED = frozenset(dropped)

        def __setattr__(self, name: str, value: object) -> None:
            if name in _Deaf._DROPPED and getattr(self, "_armed", False):
                return
            object.__setattr__(self, name, value)

    bot = _bot(**kwargs)
    bot.__class__ = _Deaf
    bot._armed = True
    return bot


# ── R1: a money path must refuse a TYPE, not only a value ───────────

def test_the_operator_string_probe_now_refuses_and_mutates_nothing():
    """R1, the operator's probe, inverted.

    Against v3.25.6: applied=True, holdings 1.0 -> 1.1, target $200.00
    -> $220.00, anchor $200.00 -> $220.00, _main_lots 1 -> 2. A string
    was booked to real state, because the only type ground on the money
    path was ``isinstance(value, bool)``.
    """
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    out = bot.apply_extractor_tranche_return(
        usd_value="20.0", source="extractor-1", base_units="0.1")

    assert out["applied"] is False
    assert "str" in out["reason"], out["reason"]
    assert bot._current_holdings == pytest.approx(1.0)
    assert bot._target_balance == pytest.approx(200.0)
    assert bot._anchor_target_balance == pytest.approx(200.0)
    assert len(bot._main_lots) == 1
    assert bot._main_lots_invariant_ok() is True


@pytest.mark.parametrize("bad", ["20.0", "  20  ", b"20", bytearray(b"20"),
                                 [20.0], (20.0,), {"usd": 20.0},
                                 10 ** 400, complex(20, 0)])
def test_a_non_numeric_type_on_the_money_path_is_refused(bad):
    """Both halves, every shape a caller can hand a money path."""
    for keyword in ("usd_value", "base_units"):
        bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
        arguments = {"usd_value": 20.0, "base_units": 0.1,
                     "source": "extractor-1"}
        arguments[keyword] = bad
        out = bot.apply_extractor_tranche_return(**arguments)

        assert out["applied"] is False, f"{keyword}={bad!r} was accepted"
        assert keyword in out["reason"]
        assert bot._current_holdings == pytest.approx(1.0)
        assert bot._target_balance == pytest.approx(200.0)
        assert bot._anchor_target_balance == pytest.approx(200.0)
        assert len(bot._main_lots) == 1


def test_POSITIVE_CONTROL_float_reads_the_strings_the_type_gate_refuses():
    """Why the ground has to be the TYPE, ahead of the numeric tests.

    Every check below the parser -- finite, greater than zero -- reads a
    parsed string as a perfectly good dollar. The huge int is the other
    half: it is a valid ``int``, and ``float()`` raises ``OverflowError``
    on it, which the old two-member ``except`` did not catch.
    """
    parsed = float("20.0")
    assert parsed == 20.0
    assert math.isfinite(parsed)
    assert parsed > 0
    with pytest.raises(OverflowError):
        float(10 ** 400)


def test_a_numeric_string_in_the_bots_own_state_is_refused_too():
    """The same ground on the state parser, for a harder reason.

    A coerced string would be written back as a durable float, which
    launders a corrupt state into a valid-looking one.
    """
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    bot._target_balance = "200.0"
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert out["applied"] is False
    assert "_target_balance" in out["reason"]
    assert bot._target_balance == "200.0"
    assert len(bot._main_lots) == 1


def test_POSITIVE_CONTROL_the_decider_cannot_read_that_state_either():
    """The tick's own expression raises on it, so refusing is correct."""
    assert float("200.0") == 200.0
    with pytest.raises(TypeError):
        _ = 1.0 * 200.0 - "200.0"


# ── R2: the verdict must assert the arrival LANDED ──────────────────

def test_a_verdict_of_differences_cannot_see_an_absent_arrival(sink):
    """R2. Reproduced against v3.25.6, then closed.

    Measured there, with both scalar stores dropped and the ledger
    showing no new units: delta_shift_usd 0.0, ledger_gap_usd 0.0,
    anchor_gap_usd 0.0, atomic True, main_lots_added 0. Three
    differences and a readability flag all agreed, because a difference
    agrees when nothing happens. Only the anchor actually moved.
    """
    bot = _deaf_bot("_current_holdings", "_target_balance",
                    target=200.0, anchor=200.0, holdings=1.0, price=200.0)
    bot._main_lots = [{"units": _FlakyUnits(1.0, 0.9),
                       "initial_buy_price": 200.0}]

    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert bot._current_holdings == pytest.approx(1.0)
    assert bot._target_balance == pytest.approx(200.0)
    assert bot._anchor_target_balance == pytest.approx(220.0)

    assert out["atomic"] is False, (
        "nothing but the anchor moved and the verdict still said atomic")
    assert out["lot_gap_usd"] == pytest.approx(-20.0)
    assert out["holdings_gap_usd"] == pytest.approx(-20.0)
    assert out["target_gap_usd"] == pytest.approx(-20.0)
    assert out["anchor_gap_usd"] == pytest.approx(0.0, abs=1e-9)
    assert sink.records("extractor.02.002.invariant.arrival_atomic")[0].ok is False


def test_POSITIVE_CONTROL_the_v3_25_6_terms_all_read_zero_there(sink):
    """The blindness, rebuilt from the numbers the CURRENT run emits.

    v3.25.6's three terms were ``lot_usd_booked - target_usd_added``,
    the scoped ledger gap, and the anchor gap. All three are computed
    below from this run's own emitted context, so the control cannot go
    stale: if they ever stop reading zero here, the defect being
    screened for has changed and this text must change with it.
    """
    bot = _deaf_bot("_current_holdings", "_target_balance",
                    target=200.0, anchor=200.0, holdings=1.0, price=200.0)
    bot._main_lots = [{"units": _FlakyUnits(1.0, 0.9),
                       "initial_buy_price": 200.0}]
    bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    context = sink.records("extractor.02.002.invariant.arrival_atomic")[0].context
    old_delta_shift = (context["lot_usd_booked"]
                       - context["target_usd_added"])
    assert old_delta_shift == pytest.approx(0.0, abs=1e-9)
    assert context["ledger_gap_usd"] == pytest.approx(0.0, abs=1e-9)
    assert context["anchor_gap_usd"] == pytest.approx(0.0, abs=1e-9)


# ── R11: the term named for the scalar must measure the scalar ──────

def test_delta_shift_is_measured_from_the_scalar_the_tick_prices(sink):
    """R11. ``_delta_shift_usd`` is d(delta), so it reads d(holdings).

    v3.25.6 sourced its holdings term from the LEDGER read-back, so the
    quantity named after ``_current_holdings`` measured ``_main_lots``.
    Drop the scalar store and keep the lot: the tick's delta moves by
    -$20.00 while the old term reads exactly 0.00.
    """
    bot = _deaf_bot("_current_holdings",
                    target=200.0, anchor=200.0, holdings=1.0, price=200.0)
    assert _delta(bot, 200.0) == pytest.approx(0.0)

    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert bot._current_holdings == pytest.approx(1.0)
    assert bot._target_balance == pytest.approx(220.0)
    assert _delta(bot, 200.0) == pytest.approx(-20.0)
    assert out["delta_shift_usd"] == pytest.approx(-20.0), (
        "delta moved -$20 and the term named for it must say so")
    assert out["atomic"] is False

    context = sink.records("extractor.02.002.invariant.arrival_atomic")[0].context
    ledger_sourced = (context["lot_usd_booked"]
                      - context["target_usd_added"])
    assert ledger_sourced == pytest.approx(0.0, abs=1e-9), (
        "the v3.25.6 term reads zero here; that is the defect")


def test_POSITIVE_CONTROL_the_two_sources_agree_on_a_healthy_arrival():
    """They must be indistinguishable when nothing is wrong.

    Otherwise the test above would be detecting a permanent
    disagreement rather than a missing write.
    """
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0, price=200.0)
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    assert out["delta_shift_usd"] == pytest.approx(0.0, abs=1e-9)
    assert out["lot_gap_usd"] == pytest.approx(0.0, abs=1e-9)
    assert out["holdings_gap_usd"] == pytest.approx(0.0, abs=1e-9)
    assert _delta(bot, 200.0) == pytest.approx(0.0)


# ── R6: the condition names TWO quote rates, not one ────────────────

def test_the_delta_condition_needs_the_usd_price_to_be_unchanged():
    """R6. ``d(delta) = b * (P * q_tick - arrival_price * q_arr)``.

    v3.25.6 carried a single ``q`` through an expression that reads the
    rate at two different times, which made the condition read
    ``P == arrival_price``. Hold the quote-side price EXACTLY at the
    arrival price and move only the rate: delta moves anyway.
    """
    contained = _bot(target=200.0, holdings=1.0, price=200.0,
                     quote_to_usd=1.0)
    untouched = _bot(target=200.0, holdings=1.0, price=200.0,
                     quote_to_usd=1.0)
    out = contained.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    arrival_price = out["arrival_price"]

    for q_tick in (1.10, 0.90):
        contained._quote_to_usd = q_tick
        untouched._quote_to_usd = q_tick
        gap = (_delta(contained, arrival_price)
               - _delta(untouched, arrival_price))
        expected = 0.1 * (arrival_price * q_tick - arrival_price * 1.0)
        assert gap == pytest.approx(expected), (
            f"at q_tick={q_tick}, with P frozen at the arrival price, "
            f"the arrival moved delta by {gap}, not {expected}")
        assert abs(gap) > 1.0, "the rate move must be visible, not noise"


def test_POSITIVE_CONTROL_the_condition_holds_when_both_rates_agree():
    """The paired half: same price AND same rate, and delta is flat."""
    contained = _bot(target=200.0, holdings=1.0, price=200.0,
                     quote_to_usd=1.0)
    untouched = _bot(target=200.0, holdings=1.0, price=200.0,
                     quote_to_usd=1.0)
    out = contained.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    assert _delta(contained, out["arrival_price"]) == pytest.approx(
        _delta(untouched, out["arrival_price"]))


# ── R7: the drift-down reconcile strands the ANCHOR too ─────────────

def test_reconcile_holdings_never_writes_the_anchor_target_balance():
    """R7, structurally. The half of the claim v3.25.6 left out."""
    writes = _self_writes(ScrummingBot._reconcile_holdings)
    assert "_anchor_target_balance" not in writes, (
        "reconcile now moves the anchor; the KNOWN LIMITATION section of "
        "apply_extractor_tranche_return is stale and must be rewritten")


def test_the_stranded_anchor_widens_the_growth_cap_and_the_ceiling():
    """R7, behaviourally. Why the anchor is the WIDER half.

    The anchor is the base two other limits are taken from. A stranded
    lift is not a cosmetic leftover: it raises the per-cycle Growth Rate
    Cap and the Smart Ceiling for as long as it stands.
    """
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0, price=200.0)
    bot.config.position_ceiling_enabled = True
    bot.config.position_ceiling_multiple = 2.0

    def _growth_cap() -> float:
        return (bot._anchor_target_balance
                * float(bot.config.max_target_growth_pct) / 100.0)

    cap_before = _growth_cap()
    ceiling_before = bot.position_ceiling_usd
    assert ceiling_before == pytest.approx(400.0)

    bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    async def _balance(asset):
        assert asset == "ETH"
        return type("B", (), {"free": 1.0})()

    bot._get_balance = _balance
    assert asyncio.run(bot._reconcile_holdings(reason="test")) is True

    assert bot._current_holdings == pytest.approx(1.0)
    assert bot._anchor_target_balance == pytest.approx(220.0), (
        "the anchor lift survived the reconcile; that is the limitation")
    assert _growth_cap() == pytest.approx(cap_before * 1.1)
    assert bot.position_ceiling_usd == pytest.approx(ceiling_before + 40.0)


def test_POSITIVE_CONTROL_both_limits_really_read_the_anchor():
    """The two consumers must move with the anchor and nothing else."""
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0, price=200.0)
    bot.config.position_ceiling_enabled = True
    bot.config.position_ceiling_multiple = 2.0
    assert bot.position_ceiling_usd == pytest.approx(400.0)

    bot._target_balance = 999.0
    assert bot.position_ceiling_usd == pytest.approx(400.0)

    bot._anchor_target_balance = 300.0
    assert bot.position_ceiling_usd == pytest.approx(600.0)


# ── R3: the premise the exact-list guard rests on ───────────────────

def test_every_main_lots_assignment_builds_a_plain_list():
    """Nothing legitimate is refused by the exact-list guard.

    If a future edit ever assigns a wrapper to ``self._main_lots``, the
    guard would start refusing real arrivals in production, and this
    test is what says so first.
    """
    tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (isinstance(target, ast.Attribute)
                    and target.attr == "_main_lots"
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"):
                sites.append((target.lineno, type(node.value).__name__))
    assert sites, "the scanner found no assignment; it proves nothing"
    for lineno, kind in sites:
        assert kind in ("List", "ListComp"), (
            f"scrumming_bot.py:{lineno} assigns a {kind} to _main_lots; "
            f"the exact-list guard would refuse every arrival on that bot")


def test_POSITIVE_CONTROL_the_ledger_shape_scanner_sees_a_wrapper():
    """The scanner must not report clean for every shape."""
    probe = ast.parse("self._main_lots = Wrapper([])\n")
    kinds = [type(node.value).__name__ for node in ast.walk(probe)
             if isinstance(node, ast.Assign)]
    assert kinds == ["Call"]


# ── R10: the fail-closed promise, made true and then measured ───────

def _corrupt_lot_type(bot):
    bot._main_lots.append(["units", 1.0])


class _BoomUnits:
    """A stored units value whose ``__float__`` raises."""

    def __float__(self) -> float:
        raise RuntimeError("units.__float__ exploded")


def _hostile_units(bot):
    bot._main_lots.append({"units": _BoomUnits(),
                           "initial_buy_price": 1.0})


def _huge_target(bot):
    bot._target_balance = 10 ** 400


def _shadowed_tolerance(bot):
    bot._ARRIVAL_ATOMIC_TOL_USD = "wide"


def _negative_tolerance(bot):
    bot._ARRIVAL_ATOMIC_TOL_USD = -1.0


def _unusable_rate(bot):
    bot._quote_to_usd = object()


def _huge_rate(bot):
    """A valid int that ``float()`` refuses: OverflowError, not ValueError."""
    bot._quote_to_usd = 10 ** 400


def _no_bot_id(bot):
    del bot.bot_id


HOSTILE_ARRANGEMENTS = [
    ("corrupt lot type", _corrupt_lot_type),
    ("hostile units", _hostile_units),
    ("huge target", _huge_target),
    ("shadowed tolerance", _shadowed_tolerance),
    ("negative tolerance", _negative_tolerance),
    ("unusable rate", _unusable_rate),
    ("huge rate", _huge_rate),
    ("no bot_id", _no_bot_id),
]


@pytest.mark.parametrize("label,arrange", HOSTILE_ARRANGEMENTS,
                         ids=[name for name, _ in HOSTILE_ARRANGEMENTS])
def test_the_method_never_raises_on_any_named_input(label, arrange):
    """R10. The promise says "returns a refusal"; this measures it.

    Each arrangement is a value the docstring names as covered. None may
    raise, and the ones that are refused must leave every balance
    exactly where it started.
    """
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0, price=200.0)
    arrange(bot)
    before = (bot._current_holdings, bot._target_balance,
              bot._anchor_target_balance, len(bot._main_lots))

    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert isinstance(out, dict), label
    assert "applied" in out, label
    if out["applied"] is False:
        assert "reason" in out, label
        after = (bot._current_holdings, bot._target_balance,
                 bot._anchor_target_balance, len(bot._main_lots))
        assert after == before, f"{label} refused and still mutated state"


def test_POSITIVE_CONTROL_those_arrangements_really_are_hostile():
    """Each one raises when handled the way v3.25.6 handled it."""
    not_a_lot = ["units", 1.0]
    with pytest.raises(TypeError):
        _ = not_a_lot["units"]
    with pytest.raises(OverflowError):
        float(10 ** 400)
    with pytest.raises(TypeError):
        _ = abs(-20.0) <= "wide"
    with pytest.raises(RuntimeError):
        float(_BoomUnits())


def test_a_shadowed_tolerance_is_refused_before_the_writes():
    """The specific one that would have raised AFTER all four writes."""
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0, price=200.0)
    bot._ARRIVAL_ATOMIC_TOL_USD = "wide"

    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)

    assert out["applied"] is False
    assert "_ARRIVAL_ATOMIC_TOL_USD" in out["reason"]
    assert bot._current_holdings == pytest.approx(1.0)
    assert bot._target_balance == pytest.approx(200.0)
    assert bot._anchor_target_balance == pytest.approx(200.0)
    assert len(bot._main_lots) == 1


def test_POSITIVE_CONTROL_the_class_tolerance_is_still_the_one_in_force():
    """The refusal above must not have disabled the real constant."""
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0, price=200.0)
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=0.1)
    assert out["applied"] is True
    assert out["atomic"] is True
    assert ScrummingBot._ARRIVAL_ATOMIC_TOL_USD == pytest.approx(1e-6)


# ── R5: the divisor guard is the one that refuses an inf product ────

def test_an_overflowing_divisor_is_named_by_the_divisor_guard():
    """R5. The D2 comment claimed the PRICE check caught this.

    It cannot: ``math.isfinite(_price_divisor)`` is evaluated first, so
    an inf product never reaches the price check at all. The reason
    string is the evidence.
    """
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    bot._quote_to_usd = 1e300
    out = bot.apply_extractor_tranche_return(
        usd_value=20.0, source="extractor-1", base_units=1e300)

    assert out["applied"] is False
    assert "divisor" in out["reason"], out["reason"]
    assert "inf" in out["reason"], out["reason"]
    assert "arrival price" not in out["reason"], out["reason"]


def test_POSITIVE_CONTROL_the_price_check_has_its_own_reachable_reason():
    """The price check is not dead code; it just does not catch inf.

    A finite divisor large enough to drive the quotient to zero is what
    reaches it, so both reasons are live and they are distinguishable.
    """
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0)
    out = bot.apply_extractor_tranche_return(
        usd_value=5e-324, source="extractor-1", base_units=1e300)
    assert out["applied"] is False
    assert "arrival price" in out["reason"], out["reason"]
    assert "divisor" not in out["reason"], out["reason"]


# ── R2b: a sub-tolerance arrival cannot be judged by residuals alone ──

def _stringifying_bot(**kwargs) -> ScrummingBot:
    """A bot whose ``__setattr__`` stores the three scalars as text.

    Not a drop and not a rewrite to a wrong number: the write LANDS, and
    what comes back cannot be read as money. That is the case the
    readability flag exists for, and it is the only one where the four
    residual terms cannot tell the story on their own.
    """
    class _Stringify(ScrummingBot):
        _SCALARS = frozenset(("_current_holdings", "_target_balance",
                              "_anchor_target_balance"))

        def __setattr__(self, name: str, value: object) -> None:
            if name in _Stringify._SCALARS and getattr(self, "_armed", False):
                object.__setattr__(self, name, repr(value))
                return
            object.__setattr__(self, name, value)

    bot = _bot(**kwargs)
    bot.__class__ = _Stringify
    bot._armed = True
    return bot


def test_an_unreadable_scalar_after_the_write_is_not_called_atomic():
    """The readability flag is load-bearing, not decoration.

    Every residual is scaled by the arrival, so an arrival SMALLER than
    the tolerance produces four gaps that all sit inside it whatever the
    state came back as. On a $0.000000001 arrival the four terms cannot
    separate a healthy bot from one whose three balances are now text.
    Only the read-back flag can, so it is in the conjunction.
    """
    bot = _stringifying_bot(target=200.0, anchor=200.0, holdings=1.0,
                            price=200.0)

    out = bot.apply_extractor_tranche_return(
        usd_value=1e-9, source="extractor-1", base_units=1e-11)

    assert out["applied"] is True
    assert out["state_readable"] is False
    assert out["ledger_readable"] is True
    for key in ("lot_gap_usd", "holdings_gap_usd", "target_gap_usd",
                "anchor_gap_usd"):
        assert abs(out[key]) <= ScrummingBot._ARRIVAL_ATOMIC_TOL_USD, (
            f"{key} is outside tolerance; this test needs an arrival the "
            f"residuals cannot resolve")
    assert out["atomic"] is False, (
        "three balances came back as text and the verdict still said "
        "the arrival was atomic")


def test_POSITIVE_CONTROL_the_same_tiny_arrival_is_atomic_when_readable():
    """The paired control: the tolerance is not what failed above.

    Same arrival, same tolerance, ordinary bot. If this reported False
    the test above would be measuring the arrival size and not the
    readability of the state.
    """
    bot = _bot(target=200.0, anchor=200.0, holdings=1.0, price=200.0)
    out = bot.apply_extractor_tranche_return(
        usd_value=1e-9, source="extractor-1", base_units=1e-11)

    assert out["applied"] is True
    assert out["state_readable"] is True
    assert out["atomic"] is True
