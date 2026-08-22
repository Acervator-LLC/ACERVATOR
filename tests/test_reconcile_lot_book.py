"""``_reconcile_holdings`` must audit the LOT BOOK, not only the scalar.

THE DEFECT THIS PINS
====================
``bootstrap_exchange_state`` sets the holdings scalar with

    self._current_holdings = min(
        max(0.0, _units), _tracked_units_bootstrap)

(``scrumming_bot.py:5491``). ``min`` can pull the SCALAR down to the
wallet. It can never pull the LOT LIST down with it, and it can never
leave the scalar above the lot sum. So the divergence it creates runs in
exactly one direction.

``_reconcile_holdings`` then read ``internal_units =
self._current_holdings`` -- the very number the clamp had already set
equal to the wallet. For ORCA that compared 48.73 against 48.73,
reported alignment, and never looked at the 5.32 units stranded in
``_main_lots``. A counter nobody audits does not self-correct.

Measured in a read-only pin of ``~/.acervator/bot_state.json`` taken
2026-08-13T19:18:32Z (sha256
0cedbc2d9354a004075e101510bf8ff6c5b26910725bdcc9ab5b60adb0eeecd3,
838489 bytes): 20 of 37 bots carry a lot book ABOVE their scalar and
ZERO carry one below.

WHY CAP IS THE CONTROL AND NOT THE COUNTEREXAMPLE
=================================================
CAP's excess had reached the AUDITED counter as well -- lot sum and
scalar both 1136.227658 -- so the old comparison could see it, and at
12.43% it cleared the deadband and fired at 2026-08-13T08:10:54Z. CAP
now reads -0.00%. The rows that REMAIN are the ones where the same
excess hides in the counter nobody audits. CAP was the most VISIBLE
case, never the worst one.

THE FIXTURE BOOK IS A RECORDING, NOT AN INVENTION
=================================================
``ORCA_UNITS`` below is ORCA's real 48-lot book, read out of that pin.
A literal that pinned "what the bot used to hold" would prove nothing
if the literal were made up, so it is a capture: ``sum(ORCA_UNITS)`` is
54.053407815409216 and the bot's scalar and wallet both read 48.73.

WHICH VENUE NUMBER THE AUDIT READS
==================================
Coinbase reports TWO numbers per coin. ``total`` is every coin owned.
``free`` is only the coins not tied up in a resting order:
``free = total - used``.

``_reconcile_holdings`` read ``balance.free``. The startup handshake
reads ``total`` (``scrumming_bot.py:6162``, MEM-255) and so does
``bootstrap_exchange_state`` (``:5465``). One wallet, three readers, and
one of them on a different field.

That was inert while the rescale almost never ran. U2 makes it run, and
the rescale multiplies EVERY lot by ``venue / internal``: on a bot with
a resting order ``free`` is short by exactly the committed units, so the
book would be rescaled down to exclude coins the operator still owns and
their ``initial_buy_price`` would go with them. The drift-UP branch
never claims units back, so that loss is permanent.

Measured in the pin: ``active_buy_orders`` and ``active_sell_orders``
are 0 on all 37 bots, so exposure TODAY is zero. Stack tranches place
resting orders.

AN ABSENT READING IS NOT A ZERO
===============================
``ccxt_connector.get_balance`` returns ``Balance(free=0, used=0,
total=0, absent=True)`` when the exchange response OMITTED the currency
(``ccxt_connector.py:1136``), and ``absent=False`` with the same three
zeros when the exchange really did report zero (``:1131``). The audit
read only the numbers, so both arrived as the same ``0.0``.

Read as a zero it is maximally destructive on the branch U2 makes
reachable: ratio 0.0, every lot multiplied to zero, every lot dropped by
the ``> 1e-12`` filter, holdings 0.0 -- a whole position and its cost
basis erased from a response that never mentioned the coin. No
information is not a reading.

WHY THE DEADBAND IS SWEPT AND NOT TABULATED
===========================================
The fire/silent decision turns on a 0.5% threshold. A hand-written pair
of rows either side of it encodes the same mental model as the code and
agrees with itself. ``test_the_deadband_decision_matches_an_independent
_model`` sweeps the ratio instead and compares every outcome against a
model written from the tolerance rule alone.
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import logging
import math

import pytest

from src.trading.scrumming_bot import ScrummingBot

# ORCA's real book, 48 lots, from the 2026-08-13T19:18:32Z pin.
ORCA_UNITS = (
    1.7652658685753126, 0.8748767081914804, 0.2360478787022957,
    0.38852154583977605, 0.29047286294813196, 1.2073185489325209,
    1.0963999940422426, 3.1861695485046857, 0.3399731647384277,
    0.0015985228388475583, 0.07737179731963027, 0.04072237921584787,
    0.1879377624912088, 0.2848984255605254, 0.46427544871914256,
    0.46979487575392176, 0.32524729103550837, 0.03873009622465764,
    0.4571573978299236, 0.7615015366744311, 0.023219324199201703,
    0.11712866479168059, 5.621341529445916, 2.2195092732274384,
    1.8813795251632013, 0.1013763614684873, 0.3696227460384178,
    0.7527348482830185, 0.06123787707883497, 0.9633958789710729,
    0.08146952771754509, 0.27756796746624557, 1.9850073873635223,
    0.8026706693558375, 3.0353296010040745, 4.6887172591441315,
    5.4687405232864075, 7.000526027990965, 0.6181511692746956,
    0.06721344278205922, 0.2825467025555889, 0.6244848264810394,
    0.3832539493799721, 1.2683456154771273, 0.0653547695707293,
    0.22880069375348386, 0.12999999999999992, 2.44,
)
ORCA_PRICES = (
    1.715, 1.715, 1.6245, 1.6245, 1.6245, 1.6245, 1.6245, 1.5427,
    1.5134, 1.5134, 1.5134, 1.5134, 1.5134, 1.5134, 1.5134, 1.4866,
    1.4866, 1.485, 1.4825, 1.4825, 1.4825, 1.4825, 1.4605, 1.4605,
    1.4605, 1.1584, 1.1584, 1.1584, 1.1584, 1.1584, 1.1584, 1.1584,
    1.1389, 1.1312, 1.103, 1.0621, 1.0225, 0.9715, 0.9681, 1.7699,
    1.7699, 1.7699, 1.7699, 1.7699, 1.7699, 1.715, 1.0894,
    1.0356741075,
)
ORCA_WALLET = 48.73
TOLERANCE_PCT = 0.5

NAN = float("nan")
INF = float("inf")


class _Bus:
    """Captures what reaches the operator's log, which is the surface."""

    def __init__(self) -> None:
        self.emits: list[tuple[str, dict]] = []

    def emit(self, name: str, **kw) -> None:
        self.emits.append((name, kw))


def _used_of(total, free):
    """The wallet's third number, for realism only.

    Nothing under test reads ``used``; it is present so the fixture is a
    wallet and not a two-field stub. Non-numeric rows get 0.0 rather
    than a raise, because those rows exist to be refused.
    """
    try:
        return float(total) - float(free)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _bot(*, lots, scalar, venue, asset="ORCA", free=None, absent=False):
    """``venue`` is the wallet TOTAL. ``free`` defaults to it.

    Splitting the two models a resting order, which is the only
    condition under which the venue-field choice changes an outcome.
    """
    bot = object.__new__(ScrummingBot)
    bot.bot_id = "recon-test"
    bot.config = type("C", (), {
        "symbol": f"{asset}/USD",
        "target_asset": asset,
        "base_currency": asset,
        "target_balance": 250.0,
        "max_target_growth_pct": 1.0,
    })()
    bot._target_balance = 250.0
    bot._anchor_target_balance = 250.0
    bot._current_holdings = scalar
    bot._quote_to_usd = 1.0
    bot._bus = _Bus()
    bot._fold_tranches = []
    bot._main_lots = copy.deepcopy(list(lots))

    _free = venue if free is None else free

    async def _balance(currency):
        if currency != asset:
            raise RuntimeError(f"asked for {currency!r}, not {asset!r}")
        return type("B", (), {"free": _free, "total": venue,
                              "used": _used_of(venue, _free),
                              "absent": absent})()

    bot._get_balance = _balance
    return bot


def _orca_book():
    return [{"units": u, "initial_buy_price": p, "operator_initiated": True}
            for u, p in zip(ORCA_UNITS, ORCA_PRICES, strict=True)]


def _run(bot):
    return asyncio.run(bot._reconcile_holdings(reason="test"))


def _messages(bot):
    return [kw.get("message", "") for name, kw in bot._bus.emits
            if name == "bot.log"]


def _book_sum(bot):
    return sum(float(lot.get("units", 0) or 0) for lot in bot._main_lots)


# ── the fixture's own control ───────────────────────────────────────

def test_the_recorded_orca_book_is_the_one_the_docstring_describes():
    """A fixture that did not reproduce the pin would prove nothing."""
    assert len(ORCA_UNITS) == 48
    assert len(ORCA_PRICES) == 48
    assert sum(ORCA_UNITS) == 54.053407815409216
    assert sum(ORCA_UNITS) > ORCA_WALLET, (
        "the whole unit is about a book that sits ABOVE the wallet")
    excess = sum(ORCA_UNITS) - ORCA_WALLET
    assert excess == pytest.approx(5.3234078154, abs=1e-9)
    # And the excess must clear the deadband, or the positive control
    # below would be passing for the wrong reason.
    assert excess / sum(ORCA_UNITS) * 100.0 > TOLERANCE_PCT


# ── THE POSITIVE CONTROL ────────────────────────────────────────────

def test_the_lot_book_above_the_venue_fires_and_is_brought_down():
    """ORCA's real book against a scalar AND a venue of 48.73.

    Read at the two surfaces a consumer reads: the line that reaches
    the operator's log, and the book that is left behind.

    THIS IS THE TEST THAT GOES RED ON THE DEFECT. Restore
    ``internal_units = self._current_holdings`` and the bot reports
    alignment, emits nothing, and leaves 5.32 units stranded.
    """
    bot = _bot(lots=_orca_book(), scalar=ORCA_WALLET, venue=ORCA_WALLET)
    assert _book_sum(bot) == 54.053407815409216

    assert _run(bot) is True

    messages = _messages(bot)
    assert len(messages) == 1, (
        f"expected exactly one operator line, got {messages}")
    assert messages[0].startswith("BALANCE DRIFT (test):")
    assert "internal=54.053408" in messages[0]
    assert "exchange=48.730000" in messages[0]
    assert "drift=-5.323408" in messages[0]
    assert "(9.85%)" in messages[0]

    assert _book_sum(bot) == pytest.approx(ORCA_WALLET, abs=1e-9)
    assert bot._current_holdings == pytest.approx(ORCA_WALLET, abs=1e-12)
    assert len(bot._main_lots) == 48, (
        "a rescale changes units, never the number of lots or their "
        "cost basis")
    assert [lot["initial_buy_price"] for lot in bot._main_lots] == \
        list(ORCA_PRICES), "MEM-171 cost basis must survive the rescale"


def test_the_rescale_preserves_every_lot_share_of_the_book():
    """The correction is ONE ratio, so relative sizes cannot move.

    Stated as a SHARE on both sides -- lot units over book total, which
    is dimensionless -- and compared with a dimensionless tolerance.
    Two earlier drafts of this test put an absolute units quantity
    against a dimensionless expression and TA Quant refused both, which
    is the same class of error it exists to catch. The absolute half of
    the claim is asserted where it belongs, in units on both sides:
    the book total equals the venue reading, above.
    """
    bot = _bot(lots=_orca_book(), scalar=ORCA_WALLET, venue=ORCA_WALLET)
    _run(bot)
    total_before = sum(ORCA_UNITS)
    total_after = _book_sum(bot)
    for lot, before in zip(bot._main_lots, ORCA_UNITS, strict=True):
        share_after = lot["units"] / total_after
        share_before = before / total_before
        assert share_after == pytest.approx(share_before, rel=1e-12)


# ── THE NEGATIVE CONTROL ────────────────────────────────────────────

def test_an_already_aligned_bot_stays_silent_with_an_unchanged_book():
    """Nothing to reconcile means nothing said and nothing written."""
    lots = [{"units": 30.0, "initial_buy_price": 1.10},
            {"units": 18.73, "initial_buy_price": 1.25}]
    bot = _bot(lots=lots, scalar=ORCA_WALLET, venue=ORCA_WALLET)
    before = copy.deepcopy(bot._main_lots)

    assert _run(bot) is True
    assert bot._bus.emits == [], (
        "an aligned bot must not reach the operator's log at all")
    assert bot._main_lots == before
    assert bot._current_holdings == ORCA_WALLET


def test_a_scalar_above_the_book_still_reconciles_as_it_always_did():
    """Widening the audit must not silence the drift it already caught.

    The audited figure is the LARGER of the two counters, so a bot
    whose scalar leads keeps the exact behaviour it had.
    """
    lots = [{"units": 10.0, "initial_buy_price": 1.10}]
    bot = _bot(lots=lots, scalar=48.73, venue=40.0)
    assert _run(bot) is True
    messages = _messages(bot)
    assert len(messages) == 1
    assert "internal=48.730000" in messages[0]
    assert bot._current_holdings == pytest.approx(40.0)


def test_drift_up_above_both_counters_is_adopted_from_the_exchange():
    """The venue holds 60; the book is the authority on cost basis only.

    This test asserted the opposite until 2026-08-22 -- that the bot
    kept 48.73 and left the book untouched. That refusal is what let
    bot 95340bda trade against 14131 units while 15778 sat in the
    wallet, and it inverted the Target Delta. Operator: "ANYTHING that
    induces disagreement with exchange values is broken."

    The surplus is still measured against the BOOK, not the scalar --
    that part of this unit is unchanged.
    """
    lots = [{"units": 54.05340782, "initial_buy_price": 1.10}]
    bot = _bot(lots=lots, scalar=48.73, venue=60.0)
    assert _run(bot) is True
    messages = _messages(bot)
    assert any("DRIFT UP" in m for m in messages)
    assert "5.94659218" in " ".join(messages), (
        "the surplus is measured against the BOOK now, not the scalar")
    assert bot._current_holdings == pytest.approx(60.0)
    assert sum(float(l["units"]) for l in bot._main_lots) == pytest.approx(60.0)


# ── THE CLOSED INPUT TABLE ──────────────────────────────────────────
#
# A type is not a domain. Every row here is a VALUE, and each names
# which of the three inputs carries it.

ACCEPT_ROWS = [
    ("empty book, sum([]) is int 0", [], 0.0, 0.0, True),
    ("ordinary positive floats", [{"units": 48.73}], 48.73, 48.73, True),
    ("a -0.0 lot is a zero",
     [{"units": 48.73}, {"units": -0.0}], 48.73, 48.73, True),
    ("a -0.0 scalar is a zero", [{"units": 0.0}], -0.0, 0.0, True),
    ("a -0.0 venue is a zero", [{"units": 0.0}], 0.0, -0.0, True),
    ("a lot with no units key counts as zero",
     [{"units": 48.73}, {"initial_buy_price": 1.25}], 48.73, 48.73, True),
    ("a None units value counts as zero",
     [{"units": None}, {"units": 48.73}], 48.73, 48.73, True),
    ("a zero venue is a real reading",
     [{"units": 48.73}], 48.73, 0.0, True),
]

REFUSE_ROWS = [
    ("nan lot", [{"units": 30.0}, {"units": NAN}], 48.73, 48.73),
    ("nan lot alone", [{"units": NAN}], 48.73, 48.73),
    ("inf lot", [{"units": 30.0}, {"units": INF}], 48.73, 48.73),
    ("-inf lot", [{"units": 30.0}, {"units": -INF}], 48.73, 48.73),
    ("negative lot", [{"units": 30.0}, {"units": -5.0}], 48.73, 48.73),
    ("lot units past the float range",
     [{"units": 30.0}, {"units": 10 ** 400}], 48.73, 48.73),
    ("book sums past the float range",
     [{"units": 1e308}, {"units": 1e308}], 48.73, 48.73),
    ("a lot that is not a dict at all",
     [{"units": 48.73}, ["not", "a", "dict"]], 48.73, 48.73),
    ("nan scalar", [{"units": 48.73}], NAN, 48.73),
    ("inf scalar", [{"units": 48.73}], INF, 48.73),
    ("-inf scalar", [{"units": 48.73}], -INF, 48.73),
    ("negative scalar", [{"units": 48.73}], -3.0, 48.73),
    ("nan venue", [{"units": 54.05340782}], 48.73, NAN),
    ("inf venue", [{"units": 54.05340782}], 48.73, INF),
    ("-inf venue", [{"units": 54.05340782}], 48.73, -INF),
    ("negative venue", [{"units": 54.05340782}], 48.73, -2.0),
]


@pytest.mark.parametrize(
    "label,lots,scalar,venue,expected",
    ACCEPT_ROWS, ids=[r[0] for r in ACCEPT_ROWS])
def test_accepted_value_rows_complete_the_reconcile(
        label, lots, scalar, venue, expected):
    bot = _bot(lots=lots, scalar=scalar, venue=venue)
    assert _run(bot) is expected, label


@pytest.mark.parametrize(
    "label,lots,scalar,venue", REFUSE_ROWS, ids=[r[0] for r in REFUSE_ROWS])
def test_refused_value_rows_touch_nothing(label, lots, scalar, venue):
    """REFUSE means False, no operator line, and no write of any kind.

    Read at the surfaces, not at the guard: a refusal that still
    rescaled would be a refusal in name only.
    """
    bot = _bot(lots=lots, scalar=scalar, venue=venue)
    before_lots = copy.deepcopy(bot._main_lots)
    before_scalar = bot._current_holdings

    assert _run(bot) is False, label
    assert bot._bus.emits == [], (
        f"{label}: a refusal reached the operator's log")
    assert repr(bot._main_lots) == repr(before_lots), (
        f"{label}: a refusal wrote to the book")
    assert repr(bot._current_holdings) == repr(before_scalar), (
        f"{label}: a refusal wrote to the scalar")


# ── the nan row, at the surface it destroys ─────────────────────────

def test_a_nan_lot_no_longer_reaches_the_ratio_that_drops_it():
    """THE ROW THAT MATTERS, pinned as a behaviour and not as a guard.

    Unguarded, this exact input produced: ratio 40/48.73 = 0.8208,
    nan * 0.8208 = nan, and the surviving `> 1e-12` filter reads nan as
    False and DROPS the lot. Two lots in, ONE lot out, book 24.625487
    standing against a scalar of 40.0, and the dropped lot's
    initial_buy_price gone with it.

    ``json.loads('NaN')`` returns nan, so a hand-edited or half-written
    state file reaches this.
    """
    lots = [{"units": 30.0, "initial_buy_price": 1.10},
            {"units": NAN, "initial_buy_price": 1.25}]
    bot = _bot(lots=lots, scalar=48.73, venue=40.0)

    assert _run(bot) is False
    assert len(bot._main_lots) == 2, (
        "the nan lot was dropped -- the book has been destroyed")
    assert bot._main_lots[0]["units"] == 30.0, (
        "the surviving lot was rescaled against a book that had already "
        "lost units")
    assert math.isnan(bot._main_lots[1]["units"])
    assert bot._current_holdings == 48.73
    assert bot._bus.emits == []


def test_a_lot_with_no_units_key_no_longer_raises_mid_rescale():
    """Unguarded, this raised KeyError AFTER the operator had already
    been told the reset happened, with lot 1 rescaled and lot 2 not.

    The keyless lot is worth zero units, so a firing reconcile scales
    it to zero and the existing filter drops it. Nothing raises.
    """
    lots = [{"units": 48.73, "initial_buy_price": 1.10},
            {"initial_buy_price": 1.25}]
    bot = _bot(lots=lots, scalar=48.73, venue=40.0)

    assert _run(bot) is True
    assert len(bot._main_lots) == 1
    assert _book_sum(bot) == pytest.approx(40.0)
    assert bot._current_holdings == pytest.approx(40.0)


def test_a_string_units_lot_is_refused_and_still_never_raises():
    """Unguarded, `"12.5" *= ratio` raised TypeError on this path.

    RESTATED, NOT WEAKENED. An earlier draft of this test pinned the
    string as ACCEPTED and coerced, on the argument that the restore
    paths' `.get`/`float` idiom accepts one. The closed input table
    refuses it, and refusing is the stricter reading of the same
    invariant -- the string still never reaches the multiply. The
    argument for coercing was also backwards: the drift-down branch
    writes the coerced value BACK into the book, so accepting a string
    would let an audit silently retype persisted state under cover of a
    rescale. A units field only `float()` can read is broken state, and
    an audit refuses broken state rather than repairing it in passing.
    """
    lots = [{"units": "12.5", "initial_buy_price": 1.10}]
    bot = _bot(lots=lots, scalar=12.5, venue=10.0)

    assert _run(bot) is False
    assert bot._main_lots[0]["units"] == "12.5", (
        "a refusal must leave the book exactly as it found it")
    assert bot._current_holdings == 12.5
    assert bot._bus.emits == []


# ── the guard's own two-sided control ───────────────────────────────

def test_the_coercion_accepts_and_refuses_the_right_values():
    """``_reconcilable_units`` read directly, so the table above cannot
    pass by never reaching it."""
    def coerce(value):
        number, why = ScrummingBot._reconcilable_units(value, "probe")
        assert (number is None) != (why is None), (
            f"{value!r}: a reading and a refusal must not both be set")
        return number

    assert coerce(0) == 0.0
    assert coerce(0.0) == 0.0
    assert coerce(48.73) == 48.73
    # -0.0 is a zero AND is normalised, so no caller formats "-0.00".
    assert coerce(-0.0) == 0.0
    assert math.copysign(1.0, coerce(-0.0)) == 1.0
    # `"12.5"` and `True` were ACCEPTED by an earlier draft. Both are
    # refused now -- strictly fewer inputs accepted, never more.
    # `type(True) is bool` and bool subclasses int, so `float(True)` is
    # 1.0 and every numeric test below would have passed it through.
    for bad in (NAN, INF, -INF, -1e-9, -5.0, 10 ** 400, None, [], (),
                object(), "banana", "", "12.5", True, False,
                complex(1, 0)):
        assert coerce(bad) is None, f"{bad!r} was accepted"


def test_a_refusal_says_which_input_it_refused():
    """The reason reaches the developer log, so it must name a field."""
    _, why = ScrummingBot._reconcilable_units(NAN, "exchange balance")
    assert why == "exchange balance must be finite; got nan"
    _, why = ScrummingBot._reconcilable_units(-2.0, "_current_holdings")
    assert why == "_current_holdings must be >= 0; got -2.0"
    bot = _bot(lots=[{"units": 1.0}, {"units": NAN}], scalar=1.0,
               venue=1.0)
    per_lot, why = bot._reconcilable_lot_book()
    assert per_lot is None
    assert why == "_main_lots[1]['units'] must be finite; got nan"


def test_max_would_have_swallowed_the_nan_the_guard_catches():
    """Why the guard runs BEFORE any comparison, not inside one.

    This asserts a property of the language, which is the reason the
    implementation cannot be a one-line ``max``.
    """
    assert max(48.73, NAN) == 48.73
    assert math.isnan(max(NAN, 48.73))
    assert not (NAN > 48.73)
    assert not (NAN < 48.73)
    with pytest.raises(OverflowError):
        float(10 ** 400)


def test_the_audited_total_matches_the_scalar_the_restore_path_builds():
    """One book must not produce two different totals.

    ``sum`` compensates and a ``+=`` loop does not; on ORCA's book they
    differ by one ULP. :5486 and :6425 both use ``sum``, so the audit
    does too.
    """
    bot = _bot(lots=_orca_book(), scalar=0.0, venue=0.0)
    per_lot, why = bot._reconcilable_lot_book()
    assert why is None
    total = sum(per_lot)
    restore_idiom = sum(float(lot.get("units", 0) or 0)
                        for lot in bot._main_lots)
    assert total == restore_idiom
    assert len(per_lot) == 48
    accumulator_loop = 0.0
    for units in per_lot:
        accumulator_loop += units
    assert accumulator_loop != total, (
        "if these ever agree, the ULP note above is stale -- rewrite it "
        "rather than deleting the test")


# ── RULE 2: sweep the threshold, do not tabulate it ─────────────────

def _model(scalar, book, venue):
    """The decision, written from the tolerance rule alone.

    Deliberately not a copy of the implementation: it takes the larger
    counter, builds the tolerance in units, and says fire or not.
    """
    internal = max(scalar, book)
    tolerance = abs(internal) * TOLERANCE_PCT / 100.0
    if abs(venue - internal) <= tolerance:
        return "silent"
    if venue < internal - 1e-9:
        return "down"
    return "up"


@pytest.mark.parametrize("step", range(0, 401))
def test_the_deadband_decision_matches_an_independent_model(step):
    """Sweep the book/venue ratio across and well past the threshold.

    401 rows from 0.0% to 4.0% excess in 0.01% steps, which walks the
    0.5% boundary in both directions rather than asserting two
    hand-picked rows either side of it.
    """
    venue = 100.0
    book = venue * (1.0 + step / 10000.0)
    bot = _bot(lots=[{"units": book, "initial_buy_price": 1.0}],
               scalar=venue, venue=venue)
    assert _run(bot) is True

    expected = _model(venue, book, venue)
    messages = _messages(bot)
    if expected == "silent":
        assert messages == [], f"step {step}: fired at book={book!r}"
        assert bot._main_lots[0]["units"] == book
        assert bot._current_holdings == venue
    else:
        assert expected == "down", f"step {step}: model said {expected}"
        assert len(messages) == 1, f"step {step}: {messages}"
        assert messages[0].startswith("BALANCE DRIFT (test):")
        assert bot._main_lots[0]["units"] == pytest.approx(venue,
                                                           abs=1e-9)
        assert bot._current_holdings == venue


def test_POSITIVE_CONTROL_the_sweep_covers_both_verdicts():
    """A sweep that never changed its answer would prove nothing."""
    verdicts = {_model(100.0, 100.0 * (1.0 + s / 10000.0), 100.0)
                for s in range(0, 401)}
    assert verdicts == {"silent", "down"}


# ── WHICH VENUE NUMBER THE AUDIT READS ──────────────────────────────

TOTAL_WITH_A_RESTING_ORDER = 48.73
FREE_WITH_A_RESTING_ORDER = 30.0


def test_the_venue_reading_is_the_wallet_total_not_the_free_balance():
    """A bot holding 48.73 with 18.73 committed to a resting order.

    WHAT A FAILURE HERE WOULD MEAN. The audit is reading `free`. On
    every bot with an open order it would see a wallet 18.73 units
    short of the truth, call it a drift DOWN, and rescale the book to
    exclude coins the operator still owns -- discarding those units and
    their cost basis permanently, because the drift-UP branch never
    claims units back.
    """
    assert FREE_WITH_A_RESTING_ORDER != TOTAL_WITH_A_RESTING_ORDER, (
        "with total == free this test cannot tell the two fields apart")
    lots = [{"units": TOTAL_WITH_A_RESTING_ORDER,
             "initial_buy_price": 1.10}]
    bot = _bot(lots=lots, scalar=TOTAL_WITH_A_RESTING_ORDER,
               venue=TOTAL_WITH_A_RESTING_ORDER,
               free=FREE_WITH_A_RESTING_ORDER)

    assert _run(bot) is True
    assert bot._bus.emits == [], (
        "reading total, this bot is aligned and says nothing")
    assert bot._main_lots[0]["units"] == TOTAL_WITH_A_RESTING_ORDER
    assert bot._current_holdings == TOTAL_WITH_A_RESTING_ORDER

    # The other half: what reading `free` would have done to it.
    assert _model(TOTAL_WITH_A_RESTING_ORDER,
                  TOTAL_WITH_A_RESTING_ORDER,
                  FREE_WITH_A_RESTING_ORDER) == "down", (
        "if free no longer fires here the fixture stopped modelling a "
        "resting order and this test proves nothing")


def test_the_venue_falls_back_to_free_exactly_as_the_handshake_does():
    """`total, else free, else zero` -- the handshake's own chain.

    WHAT A FAILURE HERE WOULD MEAN. The reconcile invented its own
    fallback. A connector that reports only `free` would then be read
    as a zero wallet by the audit and as a real wallet by the
    handshake, and the two would fight over the same book.
    """
    lots = [{"units": 48.73, "initial_buy_price": 1.10}]
    bot = _bot(lots=lots, scalar=48.73, venue=0.0, free=48.73)
    assert _run(bot) is True
    assert bot._bus.emits == []
    assert bot._current_holdings == 48.73

    # And with neither, the chain ends at zero rather than raising.
    bot = _bot(lots=lots, scalar=48.73, venue=None, free=None)
    assert _run(bot) is True
    assert bot._current_holdings == 0.0


def test_the_reconcile_reads_the_same_field_as_the_startup_handshake():
    """Read the two call sites, not a behaviour that could agree by luck.

    WHAT A FAILURE HERE WOULD MEAN. The two readers of one wallet have
    drifted onto different fields again, which is the whole defect.
    """
    recon = inspect.getsource(ScrummingBot._reconcile_holdings)
    assert 'getattr(balance, "total", 0)' in recon
    assert "float(balance.free or 0.0)" not in recon, (
        "the reconcile is reading FREE as its venue number again")
    assert recon.index('getattr(balance, "total", 0)') < \
        recon.index("or balance.free"), (
        "free must be the fallback, never the first choice")
    # The fail-closed pin, at the source. A `getattr` DEFAULT on free
    # is what let a None balance become an invented 0.0, and a 0.0
    # against a real book is a 100% drift DOWN that empties it.
    assert 'getattr(balance, "free"' not in recon, (
        "a getattr default on free swallows a broken balance object; "
        "the read must be bare so it raises into the fetch handler")

    handshake = inspect.getsource(ScrummingBot.tick)
    assert 'getattr(_bal1, "total", 0)' in handshake
    bootstrap = inspect.getsource(ScrummingBot.bootstrap_exchange_state)
    assert 'getattr(_bal, "total", 0)' in bootstrap


# ── AN ABSENT READING IS NOT A ZERO ─────────────────────────────────

def test_an_absent_venue_reading_reconciles_nothing_and_says_why(
        capture_log):
    """The exchange omitted the coin. That is no information.

    WHAT A FAILURE HERE WOULD MEAN. `absent=True` is being read as a
    holding of zero. Against a real book that is a drift DOWN with
    ratio 0.0: every lot multiplied to zero, every lot then dropped by
    the `> 1e-12` filter, holdings 0.0. A whole position and its entire
    cost basis erased from a response that never mentioned the coin.
    """
    bot = _bot(lots=_orca_book(), scalar=ORCA_WALLET, venue=0.0,
               absent=True)
    before = copy.deepcopy(bot._main_lots)

    with capture_log("acervator.scrumming") as records:
        assert _run(bot) is False

    assert len(bot._main_lots) == 48, "the book was rescaled to nothing"
    assert bot._main_lots == before
    assert bot._current_holdings == ORCA_WALLET
    assert _book_sum(bot) == 54.053407815409216

    messages = _messages(bot)
    assert len(messages) == 1, f"expected one operator line, got {messages}"
    assert "RECONCILE REFUSED (test)" in messages[0]
    assert "OMITTED" in messages[0]
    assert "UNKNOWN, not" in messages[0] and "zero" in messages[0]
    assert "ORCA" in messages[0]
    assert not any(m.startswith("BALANCE DRIFT") for m in messages), (
        "a refusal must never claim it reset anything")

    warnings = [r.getMessage() for r in records
                if r.levelno >= logging.WARNING]
    assert any("REFUSED" in m and "UNKNOWN" in m for m in warnings), (
        f"the reason never reached the developer log: {warnings}")


def test_an_absent_marker_wins_even_when_the_numbers_look_healthy():
    """`absent` is the discriminator, not the size of the number.

    WHAT A FAILURE HERE WOULD MEAN. The guard is inferring absence from
    a zero instead of reading the flag, so a connector that sets the
    flag alongside a stale non-zero figure would still be trusted.
    """
    bot = _bot(lots=_orca_book(), scalar=ORCA_WALLET,
               venue=ORCA_WALLET, absent=True)
    assert _run(bot) is False
    assert _book_sum(bot) == 54.053407815409216


def test_a_genuine_zero_venue_keeps_the_behaviour_it_already_had():
    """absent=False with total 0.0 is a real reading of nothing.

    WHAT A FAILURE HERE WOULD MEAN. The absent guard is over-reaching
    and has swallowed the genuine-zero case too, so a bot really
    liquidated off-platform would never reconcile down.

    This outcome is destructive AND correct: the exchange said zero.
    The contrast with the test above is the whole point of the fix.
    """
    bot = _bot(lots=_orca_book(), scalar=ORCA_WALLET, venue=0.0,
               absent=False)
    assert _run(bot) is True
    assert bot._main_lots == [], (
        "a real zero rescales the book to nothing and the filter drops it")
    assert bot._current_holdings == 0.0
    assert any(m.startswith("BALANCE DRIFT") for m in _messages(bot))


def test_a_balance_object_with_no_absent_attribute_is_not_absent():
    """Older connectors predate the flag; missing means present.

    WHAT A FAILURE HERE WOULD MEAN. `getattr(..., True)` was used as
    the default and every bot on a connector without the flag would
    stop reconciling for ever, silently.
    """
    bot = _bot(lots=[{"units": 48.73}], scalar=48.73, venue=48.73)

    async def _bare(_currency):
        return type("B", (), {"free": 48.73, "total": 48.73,
                              "used": 0.0})()

    bot._get_balance = _bare
    assert _run(bot) is True
    assert bot._bus.emits == []


# ── THE HOLE A NAIVE max() WOULD HAVE OPENED ────────────────────────

def test_an_inf_lot_is_refused_out_loud_and_never_reads_as_aligned(
        capture_log):
    """Drive it. A refusal and an alignment both leave the book alone.

    WHAT A FAILURE HERE WOULD MEAN. The audit went permanently silent
    on this bot. `max(inf, x)` is inf, `inf * 0.005` is inf, and
    `abs(venue - inf) <= inf` is True -- so the naive widening reports
    ALIGNED, returns True, says nothing, and never fires again however
    far the real position drifts. The two outcomes are
    indistinguishable at the book, so the discriminator asserted here
    is the return value plus the developer log.
    """
    lots = [{"units": 30.0, "initial_buy_price": 1.10},
            {"units": INF, "initial_buy_price": 1.25}]
    bot = _bot(lots=lots, scalar=48.73, venue=48.73)

    with capture_log("acervator.scrumming") as records:
        result = _run(bot)

    assert result is False, "an inf lot read as aligned"
    assert bot._bus.emits == []
    warnings = [r.getMessage() for r in records
                if r.levelno >= logging.WARNING]
    assert any("REFUSED" in m for m in warnings), (
        f"silence and refusal are not the same thing: {warnings}")
    assert any("must be finite" in m for m in warnings)


def test_POSITIVE_CONTROL_the_naive_widening_really_does_go_silent():
    """The hole is real, so the test above is not shadow-boxing.

    A model of `internal = max(sum(lots), scalar)` with no guards.
    """
    def naive(scalar, lots, venue):
        internal = max(sum(lots), scalar)
        tolerance = abs(internal) * TOLERANCE_PCT / 100.0
        return "silent" if abs(venue - internal) <= tolerance else "fires"

    assert naive(48.73, [30.0, INF], 48.73) == "silent"
    assert naive(48.73, [30.0, INF], 0.0) == "silent"
    assert naive(48.73, [30.0, INF], 1e300) == "silent"
    # and the guarded path refuses every one of those three
    for venue in (48.73, 0.0, 1e300):
        bot = _bot(lots=[{"units": 30.0}, {"units": INF}],
                   scalar=48.73, venue=venue)
        assert _run(bot) is False, venue


# ── A MISSING READING IS NOT A ZERO READING, VIA THE OBJECT ─────────
#
# The absent MARKER and a broken balance OBJECT are the same mistake
# arriving by two routes. Both used to end as an invented 0.0, and a
# 0.0 against a real book is a 100% drift DOWN.


def _bot_with_balance(balance_factory, *, lots=None, scalar=48.73):
    bot = _bot(lots=lots or [{"units": 48.73, "initial_buy_price": 1.10}],
               scalar=scalar, venue=scalar)

    async def _get(_currency):
        return balance_factory()

    bot._get_balance = _get
    return bot


BROKEN_BALANCES = [
    ("None instead of a Balance", lambda: None),
    ("an object with no total and no free", lambda: type("B", (), {})()),
]


@pytest.mark.parametrize("label,factory", BROKEN_BALANCES,
                         ids=[r[0] for r in BROKEN_BALANCES])
def test_a_broken_balance_object_fails_closed(label, factory):
    """WHAT A FAILURE HERE WOULD MEAN. The venue read is using a
    `getattr` DEFAULT where it needs a bare attribute access, so a
    balance the connector never really produced is being read as a
    holding of zero.

    MEASURED on this exact input while that defect was live: returned
    True, book [] (one lot dropped), scalar 0.0 -- a whole position
    erased and reported as a successful reconcile. The pre-U2 code
    returned False with the book untouched, because `balance.free`
    raised into the fetch handler. That behaviour is the contract.
    """
    bot = _bot_with_balance(factory)
    before = copy.deepcopy(bot._main_lots)

    assert _run(bot) is False, label
    assert bot._main_lots == before, f"{label}: the book was rewritten"
    assert bot._current_holdings == 48.73
    assert bot._bus.emits == [], (
        f"{label}: a fetch that could not be read reached the operator "
        f"as a drift")


WORKING_ONE_FIELD = [
    ("total only, no free attribute",
     lambda: type("B", (), {"total": 48.73, "absent": False})()),
    ("free only, no total attribute",
     lambda: type("B", (), {"free": 48.73, "absent": False})()),
]


@pytest.mark.parametrize("label,factory", WORKING_ONE_FIELD,
                         ids=[r[0] for r in WORKING_ONE_FIELD])
def test_one_field_is_enough_exactly_as_it_is_for_the_handshake(
        label, factory):
    """WHAT A FAILURE HERE WOULD MEAN. The fail-closed fix over-reached
    and now demands BOTH fields, so a connector that reports only one
    would stop reconciling although the handshake reads it fine.

    `total` alone must not need `free`; `free` alone must satisfy the
    fallback. Neither is a drift.
    """
    bot = _bot_with_balance(factory)
    assert _run(bot) is True, label
    assert bot._bus.emits == []
    assert bot._current_holdings == 48.73
