"""Item 9 -- THE TRANCHE DESPAWN TIMER.

Operator spec 2026-08-13, verbatim:

    "We can also add a tranche despawn timer that delists aged tranches
     from the tracker. This will be a user setting under the Scrumming
     Bot -> Details -> Settings and also available during initial
     configuration."

And the governing principle of the same day:

    "Functionality should be mirrored between either side of the
     ladder."

ONE VERB. The timer DELISTS. It places no order, cancels no order,
moves no balance. A tranche is a record and not a lock -- no tokens are
reserved behind one and no market position is taken by one -- so
dropping it frees nothing and strands nothing.

BOTH SIDES MEANS BOTH LEDGERS, NOT TWO GUI SURFACES. The fold ledger
ages on `created_ts` and the stack ledger on `opened_ts`, from one
setting. The live-settings panel is the only surface this unit ships;
the creation-time surface was dropped, and the sweep reads the setting
with a defaulting `getattr`, so a bot created without the key is Off.

WHAT THIS FILE DOES NOT TEST. Merge, consumption, spacing, spawn and
distribution are separate items with their own specs and their own test
files, and the `stack_mode` gate is item 14. Nothing here asserts a
property of any of them. The stack half is exercised only as the MIRROR
of the fold half: same setting, same age comparison, same delist.

NO ASSERTION IN THIS FILE READS SOURCE TEXT. An earlier build proved
the widget existed with `inspect.getsource` plus a substring match. That
oracle passes on an incorrect state: a widget that is built, assigned to
its attribute and then never added to a layout satisfies every substring
while the operator never sees it. The widget tests below construct the
real dialog and interrogate the constructed object, and
`TestPlantedFailures` builds exactly that never-laid-out widget and
requires the new oracle to go red on it.

A TYPE IS NOT A DOMAIN. `type(float("nan")) is float` is True, so the
strictest possible type gate still admits `nan` and the infinities, and
`int(nan)` raises. `TestTheThresholdValueTable` is the closed value
table that closes it, and the planted failure re-runs THAT SAME TABLE
against the previous build's type-only gate.

TWO-SIDED CONTROL. Every oracle is written ONCE as a `_check_*` function
and `TestPlantedFailures` runs the same function against a deliberately
broken mechanism, requiring it to fail. A plant judged by a re-written
assertion instead of the real oracle would prove nothing, so none is.
"""

from __future__ import annotations

import asyncio
import ast
import dataclasses
import inspect
import math
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from src.trading.bot_container import (
    DESPAWN_MAX_DAYS,
    BotConfig,
    BotMode,
    as_finite_float,
    despawn_threshold_days,
    make_bot_config,
)
from src.trading.scrumming_bot import ScrummingBot

DAY = 86400.0
NOW = 1_760_000_000.0  # fixed clock; the sweep takes `now` injected

NAN = float("nan")
INF = float("inf")
NINF = float("-inf")


# ---------------------------------------------------------------------------
# Stubs. Deliberately NOT ScrummingBot instances: each carries only the
# surface the sweep reads, so an accidental dependence on anything else
# surfaces as an AttributeError instead of passing quietly.
# ---------------------------------------------------------------------------


class _Bus:
    def __init__(self):
        self.msgs = []

    def emit(self, _ev, **kw):
        self.msgs.append(kw.get("message", ""))

    def text(self):
        return "\n".join(self.msgs)


class _Bot:
    """Only what `_despawn_aged_tranches` touches, plus the money-side
    state it must leave alone so a test can read it back."""

    _despawn_aged_tranches = ScrummingBot._despawn_aged_tranches
    _despawn_threshold_days = ScrummingBot._despawn_threshold_days
    # Re-wrapped, because reading it off the class unwraps the
    # descriptor: assigning the bare function here would make it an
    # INSTANCE method on the stub and pass `self` as `tranche`, which is
    # a shape the real class never has.
    _tranche_age_seconds = staticmethod(ScrummingBot._tranche_age_seconds)

    def __init__(self, fold=(), stack=(), days=0, pending=0.0):
        self.bot_id = "bot-despawn-0001"
        self.config = type(
            "C",
            (),
            {
                "symbol": "RAVE/USD",
                "tranche_despawn_days": days,
            },
        )()
        self._fold_tranches = [dict(t) for t in fold]
        self._stack_tranches = [dict(t) for t in stack]
        # The guarded reader, not the sibling `float(x or 0)`
        # expression, because one of the fixtures below deliberately
        # carries a usd that the sibling expression cannot convert. See
        # `test_the_sibling_expression_really_does_raise`.
        self._fold_queue_usd = sum(
            (as_finite_float(t.get("usd", 0)) or 0.0) for t in self._fold_tranches
        )
        self._pending_wire_credits = pending
        self._tranches_created_lifetime = 40
        self._tranches_closed_lifetime = 40 - len(self._fold_tranches)
        self._tranches_discarded_lifetime = 0
        # The stack ledger, seeded so that
        # `created - closed - discarded == standing` already holds
        # BEFORE the sweep runs. A stub that started out of balance
        # would let a sweep that miscounts still land on a number that
        # happens to reconcile.
        self._stack_created = len(self._stack_tranches)
        self._stack_discarded = 0
        # Money-side state. The sweep must not read or write any of it.
        self._current_holdings = 12.5
        self._main_lots = [{"units": 12.5, "initial_buy_price": 0.30}]
        self._target_balance = 50.0
        self._anchor_target_balance = 50.0
        self.stats = type("S", (), {})()
        self._bus = _Bus()


def fold_tr(age_days, usd=1.0, units=3.0, ref=0.30, ibp=0.35, dated=True):
    """A fold tranche `age_days` old. `dated=False` builds the
    pre-v3.16.39 shape: no `created_ts` key at all."""
    t = {"usd": usd, "units": units, "ref": ref, "initial_buy_price": ibp}
    if dated:
        t["created_ts"] = NOW - age_days * DAY
    return t


def stack_tr(age_days, index=0, status="pending", order_id=None, dated=True):
    """A stack tranche `age_days` old, Invisible-mode by default
    (`order_id=None`, which is what `_open_stack_from_scrum` writes when
    the bot is not in Visible mode)."""
    t = {
        "index": index,
        "price": 0.40,
        "size": 2.0,
        "status": status,
        "order_id": order_id,
        "visible": order_id is not None,
        "activated": False,
    }
    if dated:
        t["opened_ts"] = NOW - age_days * DAY
    return t


def _cfg_with(raw):
    """A config object carrying `raw` as the despawn setting."""
    return type("C", (), {"tranche_despawn_days": raw})()


def _cfg_without():
    """A config predating the field, which every pre-2026-08-13 state
    file restores to."""
    return type("C", (), {})()


# ---------------------------------------------------------------------------
# The oracles. Each is written once and reused by the planted-failure
# class below, so a blinded mechanism is judged by the same instrument
# the real one is.
# ---------------------------------------------------------------------------


def _check_old_fold_is_delisted(bot) -> None:
    """A fold tranche older than the threshold must be gone."""
    bot._despawn_aged_tranches(now=NOW)
    refs = [t.get("created_ts") for t in bot._fold_tranches]
    assert (
        NOW - 40 * DAY not in refs
    ), "a 40-day fold tranche survived a 7-day despawn threshold"


def _check_young_fold_survives(bot) -> None:
    """A fold tranche younger than the threshold must remain."""
    bot._despawn_aged_tranches(now=NOW)
    refs = [t.get("created_ts") for t in bot._fold_tranches]
    assert (
        NOW - 2 * DAY in refs
    ), "a 2-day fold tranche was delisted at a 7-day threshold"


def _check_boundary_is_inclusive(bot) -> None:
    """Exactly at the threshold counts as old enough."""
    bot._despawn_aged_tranches(now=NOW)
    assert bot._fold_tranches == [], (
        "a tranche aged EXACTLY the threshold survived; the documented "
        "rule is age >= threshold"
    )


def _check_ageless_is_kept(bot) -> None:
    """A record with no usable timestamp is never delisted."""
    before = len(bot._fold_tranches)
    bot._despawn_aged_tranches(now=NOW)
    assert len(bot._fold_tranches) == before, (
        "an undated tranche was delisted; the rule is that the timer "
        "delists on MEASURED age and there is none"
    )


def _check_off_delists_nothing(bot) -> None:
    """threshold 0 is off, and off is the default."""
    fold_before = len(bot._fold_tranches)
    stack_before = len(bot._stack_tranches)
    bot._despawn_aged_tranches(now=NOW)
    assert (
        len(bot._fold_tranches) == fold_before
    ), "fold tranches were delisted with the timer switched off"
    assert (
        len(bot._stack_tranches) == stack_before
    ), "stack tranches were delisted with the timer switched off"


def _check_both_sides_agree(bot) -> None:
    """One setting, both ledgers. The mirroring principle."""
    fold_before = len(bot._fold_tranches)
    stack_before = len(bot._stack_tranches)
    bot._despawn_aged_tranches(now=NOW)
    fold_gone = fold_before - len(bot._fold_tranches)
    stack_gone = stack_before - len(bot._stack_tranches)
    assert fold_gone == stack_gone == 1, (
        f"the same setting delisted {fold_gone} fold and {stack_gone} "
        f"stack tranche(s) from identically-aged ledgers"
    )


def _fold_ledger(bot) -> tuple[int, int]:
    """(created - closed - discarded, standing) on the FOLD ledger."""
    return (
        int(bot._tranches_created_lifetime)
        - int(bot._tranches_closed_lifetime)
        - int(bot._tranches_discarded_lifetime),
        len(bot._fold_tranches),
    )


def _stack_ledger(bot) -> tuple[int, int]:
    """(created - closed - discarded, standing) on the STACK ledger.

    The `closed` term is read through `getattr` rather than written as a
    literal 0, so this oracle keeps meaning the same thing if a
    stack-side close counter is ever added. It reads 0 today because
    nothing closes a stack tranche by REMOVING it: a fill sets
    ``status`` and leaves the record listed, which
    `test_a_filled_stack_tranche_still_counts_as_standing` pins.
    """
    return (
        int(bot._stack_created)
        - int(getattr(bot, "_stack_closed", 0) or 0)
        - int(bot._stack_discarded),
        len(bot._stack_tranches),
    )


def _check_both_ledgers_reconcile(bot) -> None:
    """`created - closed - discarded == standing`, on BOTH ledgers.

    THE WHOLE POINT OF THE DISCARD/CLOSE SPLIT. A delist that records
    itself nowhere leaves the ledger lying: the created total keeps
    climbing while the standing list shrinks, and every surface that
    divides one by the other drifts with nothing to explain it.
    """
    bot._despawn_aged_tranches(now=NOW)
    fold_lhs, fold_standing = _fold_ledger(bot)
    assert fold_lhs == fold_standing, (
        f"FOLD ledger does not reconcile after the sweep: created "
        f"{bot._tranches_created_lifetime} - closed "
        f"{bot._tranches_closed_lifetime} - discarded "
        f"{bot._tranches_discarded_lifetime} = {fold_lhs}, but "
        f"{fold_standing} tranche(s) are standing"
    )
    stack_lhs, stack_standing = _stack_ledger(bot)
    assert stack_lhs == stack_standing, (
        f"STACK ledger does not reconcile after the sweep: created "
        f"{bot._stack_created} - closed "
        f"{getattr(bot, '_stack_closed', 0)} - discarded "
        f"{bot._stack_discarded} = {stack_lhs}, but {stack_standing} "
        f"tranche(s) are standing. Every removal must record itself."
    )


ALLOWED_REACHES = frozenset(
    {
        "_despawn_aged_tranches",
        "_despawn_threshold_days",
        "_tranche_age_seconds",
        "config",
        "_fold_tranches",
        "_stack_tranches",
        "_tranches_discarded_lifetime",
        "stats",
        "_pending_wire_credits",
        "_bus",
        "bot_id",
        "_fold_queue_usd",
        # The stack ledger's own discard counter. Admitted for exactly the
        # reason `_tranches_discarded_lifetime` is: it is record-keeping,
        # not money. A sweep that removes records without recording the
        # removal is what this name exists to stop.
        "_stack_discarded",
    }
)

#: Names whose mere READ would mean the sweep had gone near an order or
#: a balance. Kept explicit as well as the subset rule above, so the
#: failure message names the thing that was touched.
MONEY_REACHES = frozenset(
    {
        "exchange",
        "exchange_interface",
        "guarded_place_order",
        "place_order",
        "cancel_order",
        "_execute_sell",
        "_execute_buy",
        "_execute_detonation",
        "_current_holdings",
        "_main_lots",
        "_target_balance",
        "_anchor_target_balance",
        "_quote_to_usd",
        "phantom_balance",
        "_phantom_balance",
        "_hedge_balance",
    }
)


class _Spy(_Bot):
    """Records EVERY attribute reach, present or missing.

    `__getattribute__` is deliberately over-broad -- it fires for
    attributes that EXIST, which a `__getattr__` hook alone never sees,
    and `__getattr__` catches the misses on top. Between them nothing
    the sweep looks at goes unrecorded.
    """

    def __init__(self, *a, **kw):
        self.reached = []
        super().__init__(*a, **kw)

    def __getattribute__(self, name):
        object.__getattribute__(self, "reached").append(name)
        return object.__getattribute__(self, name)

    def __getattr__(self, name):
        object.__getattribute__(self, "reached").append(name)
        raise AttributeError(name)


def _check_no_money_was_reached(spy) -> None:
    """The whole safety case, read at the reach log."""
    spy._despawn_aged_tranches(now=NOW)
    reached = set(object.__getattribute__(spy, "reached"))
    reached.discard("reached")
    touched_money = sorted(reached & MONEY_REACHES)
    assert touched_money == [], (
        f"the despawn sweep reached for {touched_money}; delisting a "
        f"record must not go near an order or a balance"
    )
    stray = sorted(reached - ALLOWED_REACHES)
    assert stray == [], (
        f"the despawn sweep reached for {stray}, which is outside the "
        f"record-keeping surface it is allowed to touch"
    )


# ---------------------------------------------------------------------------
# The behaviour, on the real mechanism.
# ---------------------------------------------------------------------------


class TestTheInstrumentWorks:
    """Without these, every 'it was delisted' assertion below would also
    pass against a bot that never held a tranche."""

    def test_the_fixture_starts_populated(self):
        bot = _Bot(fold=[fold_tr(40), fold_tr(2)], stack=[stack_tr(40)], days=7)
        assert len(bot._fold_tranches) == 2
        assert len(bot._stack_tranches) == 1

    def test_the_threshold_is_read_off_the_config(self):
        assert _Bot(days=0)._despawn_threshold_days() == 0
        assert _Bot(days=7)._despawn_threshold_days() == 7


class TestAgeDecidesIt:
    def test_older_than_the_threshold_is_delisted(self):
        _check_old_fold_is_delisted(_Bot(fold=[fold_tr(40), fold_tr(2)], days=7))

    def test_younger_than_the_threshold_survives(self):
        _check_young_fold_survives(_Bot(fold=[fold_tr(40), fold_tr(2)], days=7))

    def test_exactly_at_the_threshold_is_delisted(self):
        """The documented boundary. `age >= threshold` delists, so a
        tranche whose age is the threshold to the second goes."""
        _check_boundary_is_inclusive(_Bot(fold=[fold_tr(7)], days=7))

    def test_one_second_under_the_threshold_survives(self):
        """The other side of the same boundary, so 'inclusive' is
        pinned rather than 'always delists'."""
        t = fold_tr(7)
        t["created_ts"] += 1.0
        bot = _Bot(fold=[t], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert len(bot._fold_tranches) == 1

    def test_a_future_dated_tranche_is_not_delisted(self):
        """It yields a negative age, which is younger than every
        threshold. No special case, and none needed."""
        bot = _Bot(fold=[fold_tr(-30)], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert len(bot._fold_tranches) == 1


class TestTheAgelessRule:
    """THE STATED RULE: a tranche with no usable `created_ts` is never
    delisted. Measured on a pinned read-only copy of bot_state.json
    2026-08-13 08:43, all 471 open fold tranches across 24 of 37 bots
    carry
    one, so this is the rule for a shape that no longer occurs -- which
    is exactly why it must be pinned rather than assumed away."""

    def test_a_tranche_with_no_timestamp_key_is_kept(self):
        _check_ageless_is_kept(_Bot(fold=[fold_tr(40, dated=False)], days=7))

    def test_a_none_timestamp_is_kept(self):
        bot = _Bot(fold=[fold_tr(40)], days=7)
        bot._fold_tranches[0]["created_ts"] = None
        _check_ageless_is_kept(bot)

    def test_a_zero_timestamp_is_kept(self):
        """Zero is the epoch, which would date the record to 1970 and
        make it older than any threshold. It means 'unset'."""
        bot = _Bot(fold=[fold_tr(40)], days=7)
        bot._fold_tranches[0]["created_ts"] = 0
        _check_ageless_is_kept(bot)

    def test_a_true_timestamp_is_kept(self):
        """`bool` is a subclass of `int`, so an isinstance test would
        admit `True` and `float(True)` is 1.0 -- an age of 56 years."""
        bot = _Bot(fold=[fold_tr(40)], days=7)
        bot._fold_tranches[0]["created_ts"] = True
        _check_ageless_is_kept(bot)

    def test_a_false_timestamp_is_kept(self):
        bot = _Bot(fold=[fold_tr(40)], days=7)
        bot._fold_tranches[0]["created_ts"] = False
        _check_ageless_is_kept(bot)

    def test_a_string_timestamp_is_kept(self):
        bot = _Bot(fold=[fold_tr(40)], days=7)
        bot._fold_tranches[0]["created_ts"] = "1600000000"
        _check_ageless_is_kept(bot)

    @pytest.mark.parametrize("bad", [NAN, INF, NINF])
    def test_a_non_finite_timestamp_is_kept(self, bad):
        """A type gate alone admits all three: they are exactly `float`.
        None is a measured age, so none of them delists anything."""
        bot = _Bot(fold=[fold_tr(40)], days=7)
        bot._fold_tranches[0]["created_ts"] = bad
        _check_ageless_is_kept(bot)

    def test_an_out_of_float_range_timestamp_is_kept(self):
        """`float()` of an int this large raises OverflowError, so it is
        refused by an integer comparison rather than converted."""
        bot = _Bot(fold=[fold_tr(40)], days=7)
        bot._fold_tranches[0]["created_ts"] = 10**400
        _check_ageless_is_kept(bot)

    def test_a_decimal_timestamp_is_kept(self):
        bot = _Bot(fold=[fold_tr(40)], days=7)
        bot._fold_tranches[0]["created_ts"] = Decimal("1600000000")
        _check_ageless_is_kept(bot)

    def test_an_ageless_tranche_is_counted_not_silently_ignored(self):
        bot = _Bot(fold=[fold_tr(40, dated=False), fold_tr(40)], days=7)
        report = bot._despawn_aged_tranches(now=NOW)
        assert report["ageless_kept"] == 1
        assert report["fold_delisted"] == 1


# ---------------------------------------------------------------------------
# RULE B -- A TYPE IS NOT A DOMAIN. The closed value table.
# ---------------------------------------------------------------------------


class _HasFloat:
    def __float__(self):
        return 30.0


class _FloatSubclass(float):
    pass


#: (label, stored value, expected whole days). Exhaustive over the
#: accepted set: exactly `int` or exactly `float`, finite, within float
#: range. Everything else is OFF. Value rows come first because the type
#: rows are the ones a type-only gate already passes.
THRESHOLD_TABLE = [
    # --- VALUE rows: these are `float` by exact type and still refused
    ("nan", NAN, 0),
    ("inf", INF, 0),
    ("-inf", NINF, 0),
    ("-0.0", -0.0, 0),
    # --- boundary rows of the claimed range
    ("0 (off, the default)", 0, 0),
    ("-1", -1, 0),
    ("1 (smallest live threshold)", 1, 1),
    ("7", 7, 7),
    ("365 (spinbox maximum)", 365, 365),
    ("366 (past the spinbox, still honoured)", 366, 366),
    ("30.7 truncates toward zero", 30.7, 30),
    ("-0.5", -0.5, 0),
    ("large finite float saturates", 1e300, DESPAWN_MAX_DAYS),
    ("DESPAWN_MAX_DAYS itself", DESPAWN_MAX_DAYS, DESPAWN_MAX_DAYS),
    ("int beyond float range is refused", 10**400, 0),
    # --- TYPE rows
    ("True", True, 0),
    ("False", False, 0),
    ("'30'", "30", 0),
    ("None", None, 0),
    ("Decimal('30')", Decimal("30"), 0),
    ("Fraction(30, 1)", Fraction(30, 1), 0),
    ("float subclass", _FloatSubclass(30.0), 0),
    ("object with __float__", _HasFloat(), 0),
]


def _check_threshold_table(reader) -> None:
    """Drive `reader` over the whole closed value table.

    An exception is a FAILURE, not an error to propagate: the sweep's
    call site in `tick` sits outside every `try`, so a setting must be
    refused by value and never by raising.
    """
    for label, raw, expected in THRESHOLD_TABLE:
        try:
            got = reader(_cfg_with(raw))
        except Exception as exc:
            raise AssertionError(
                f"{label}: the reader raised {type(exc).__name__}: {exc}. "
                f"A despawn setting must be refused by value; this call "
                f"site is outside every try in tick, so raising here "
                f"ends the tick."
            ) from exc
        assert got == expected, (
            f"{label}: stored {raw!r} read back as {got!r}, expected " f"{expected!r}"
        )


def _type_only_gate(config) -> int:
    """The previous build's reader, kept verbatim as the planted defect.

    Exact type membership and nothing else -- which is what this repo's
    own sizing rule prescribed, and which is still not enough, because
    exact type closes WHICH TYPES are accepted and says nothing about
    which VALUES they carry.
    """
    raw = getattr(config, "tranche_despawn_days", 0)
    if not (type(raw) is int or type(raw) is float):
        return 0
    return max(0, int(raw))


class TestTheThresholdValueTable:
    def test_the_whole_table_reads_back_as_documented(self):
        _check_threshold_table(despawn_threshold_days)

    def test_a_config_without_the_field_is_off(self):
        assert despawn_threshold_days(_cfg_without()) == 0

    @pytest.mark.parametrize(
        "label,raw,expected", THRESHOLD_TABLE, ids=[r[0] for r in THRESHOLD_TABLE]
    )
    def test_each_row_individually(self, label, raw, expected):
        """Per-row too, so a failure names the shape rather than the
        table."""
        assert despawn_threshold_days(_cfg_with(raw)) == expected

    @pytest.mark.parametrize(
        "raw", [NAN, INF, NINF, 10**400, "30", None, True, Decimal("30")]
    )
    def test_a_refused_setting_delists_nothing_on_a_real_sweep(self, raw):
        """Read at the ledger, not at the reader. A threshold that reads
        as 0 must also leave a 400-day-old tranche standing."""
        _check_off_delists_nothing(
            _Bot(fold=[fold_tr(400)], stack=[stack_tr(400)], days=raw)
        )

    @pytest.mark.parametrize("raw", [1e300, DESPAWN_MAX_DAYS])
    def test_an_absurd_threshold_delists_nothing_either(self, raw):
        """The two absurd inputs take different routes -- one saturates,
        one is refused -- and converge on the same observable: nothing
        is ever that old, so nothing goes."""
        _check_off_delists_nothing(
            _Bot(fold=[fold_tr(400)], stack=[stack_tr(400)], days=raw)
        )


class TestTheSharedFiniteReader:
    """`as_finite_float` is the one rule every conversion in this unit
    goes through, so its own domain is pinned directly as well."""

    @pytest.mark.parametrize(
        "raw",
        [
            NAN,
            INF,
            NINF,
            10**400,
            True,
            False,
            "30",
            None,
            Decimal("30"),
            Fraction(30, 1),
            _HasFloat(),
            _FloatSubclass(30.0),
        ],
    )
    def test_refused_values_read_as_none(self, raw):
        assert as_finite_float(raw) is None

    @pytest.mark.parametrize(
        "raw,expected",
        [
            (0, 0.0),
            (-0.0, -0.0),
            (1, 1.0),
            (-1, -1.0),
            (30.7, 30.7),
            (365, 365.0),
            (1e300, 1e300),
        ],
    )
    def test_accepted_values_read_back_exactly(self, raw, expected):
        got = as_finite_float(raw)
        assert got == expected
        assert type(got) is float


class TestNoConversionInThisUnitCanRaise:
    """One probe per conversion site the unit owns, each driven with the
    value that used to break it. The verdict is 'the sweep returned',
    read at the sweep, because the call site has no handler above it."""

    def test_site_1_the_threshold(self):
        bot = _Bot(fold=[fold_tr(400)], days=NAN)
        assert bot._despawn_aged_tranches(now=NOW)["threshold_days"] == 0

    def test_site_2_a_fold_timestamp(self):
        bot = _Bot(fold=[fold_tr(400)], days=7)
        bot._fold_tranches[0]["created_ts"] = NAN
        assert bot._despawn_aged_tranches(now=NOW)["ageless_kept"] == 1

    def test_site_2_a_stack_timestamp(self):
        bot = _Bot(stack=[stack_tr(400)], days=7)
        bot._stack_tranches[0]["opened_ts"] = INF
        assert bot._despawn_aged_tranches(now=NOW)["ageless_kept"] == 1

    @pytest.mark.parametrize(
        "bad", [NAN, INF, NINF, "now", Decimal("1760000000"), True]
    )
    def test_site_3_the_injected_now(self, bad):
        """An unmeasurable clock delists nothing rather than raising."""
        bot = _Bot(fold=[fold_tr(400)], days=7)
        report = bot._despawn_aged_tranches(now=bad)
        assert report["fold_delisted"] == 0
        assert len(bot._fold_tranches) == 1

    def test_site_4_the_delisted_usd_total(self):
        bot = _Bot(fold=[fold_tr(400, usd=NAN)], days=7)
        report = bot._despawn_aged_tranches(now=NOW)
        assert report["fold_delisted"] == 1
        assert (
            report["usd_delisted"] == 0.0
        ), "a non-finite usd was added to the report total"

    def test_site_5_the_queue_total_recompute(self):
        """A SURVIVING tranche carrying an out-of-float-range usd. The
        six sibling recompute sites would raise OverflowError here; this
        one is deliberately stricter, which is the documented
        divergence."""
        bot = _Bot(fold=[fold_tr(400, usd=2.0), fold_tr(1, usd=10**400)], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert bot._fold_queue_usd == 0.0
        assert math.isfinite(bot._fold_queue_usd)

    def test_the_sibling_expression_really_does_raise(self):
        """THE MEASUREMENT BEHIND THE DIVERGENCE, not an assertion about
        it. Site 5 is stricter than the six sibling recompute sites only
        because the shared expression genuinely raises on this value."""
        with pytest.raises(OverflowError):
            float({"usd": 10**400}.get("usd", 0) or 0)

    def test_site_6_the_parked_credit_read(self):
        bot = _Bot(fold=[fold_tr(400)], days=7, pending=NAN)
        bot._despawn_aged_tranches(now=NOW)
        assert (
            "absorb window" not in bot._bus.text()
        ), "a non-finite parked total produced a dollar warning"


class TestOffByDefault:
    def test_the_dataclass_default_is_zero(self):
        field = {f.name: f for f in dataclasses.fields(BotConfig)}.get(
            "tranche_despawn_days"
        )
        assert field is not None, "BotConfig has no tranche_despawn_days"
        assert field.default == 0, (
            f"default is {field.default!r}; a timer that shipped enabled "
            f"would start delisting standing records on the first tick "
            f"after upgrade, on bots that never opted in"
        )

    def test_zero_delists_nothing(self):
        _check_off_delists_nothing(
            _Bot(fold=[fold_tr(400)], stack=[stack_tr(400)], days=0)
        )

    def test_a_bot_built_with_defaults_delists_nothing(self):
        """Read through the factory, not the dataclass, because that is
        what every creation path actually calls."""
        cfg = make_bot_config(
            BotMode.SCRUMMING,
            exchange_id="coinbase",
            base_currency="USD",
            target_asset="RAVE",
            symbol="RAVE/USD",
        )
        bot = _Bot(fold=[fold_tr(400)], stack=[stack_tr(400)])
        bot.config = cfg
        _check_off_delists_nothing(bot)

    def test_a_negative_setting_is_off(self):
        _check_off_delists_nothing(
            _Bot(fold=[fold_tr(400)], stack=[stack_tr(400)], days=-5)
        )


class TestBothSidesMirror:
    def test_the_same_setting_sweeps_both_ledgers(self):
        _check_both_sides_agree(
            _Bot(
                fold=[fold_tr(40), fold_tr(2)],
                stack=[stack_tr(40), stack_tr(2, index=1)],
                days=7,
            )
        )

    def test_the_stack_side_ages_on_opened_ts(self):
        """Its own field, not the fold side's. A stack tranche carrying
        a `created_ts` and no `opened_ts` is ageless."""
        t = stack_tr(40, dated=False)
        t["created_ts"] = NOW - 40 * DAY
        bot = _Bot(stack=[t], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert len(bot._stack_tranches) == 1

    def test_a_filled_stack_tranche_is_delisted_like_any_record(self):
        bot = _Bot(stack=[stack_tr(40, status="filled")], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert bot._stack_tranches == []

    def test_a_stack_tranche_holding_a_live_order_is_kept(self):
        """THE ONE ASYMMETRY, and it is a refusal. A Visible-mode
        pending tranche owns a resting LIMIT order; dropping the record
        would leave that order on the book with nothing tracking it,
        which is the single way this sweep could strand something."""
        bot = _Bot(stack=[stack_tr(40, status="pending", order_id="ORD-1")], days=7)
        report = bot._despawn_aged_tranches(now=NOW)
        assert len(bot._stack_tranches) == 1
        assert report["stack_kept_live_order"] == 1
        assert report["stack_delisted"] == 0

    def test_a_cancelled_visible_tranche_is_delisted(self):
        """NEGATIVE CONTROL for the rule above: the guard is about a
        LIVE order, not about having an order_id at all."""
        bot = _Bot(stack=[stack_tr(40, status="cancelled", order_id="ORD-1")], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert bot._stack_tranches == []


class TestTheStackHalfShipsDormant:
    """Measured on the pinned state 2026-08-13: zero stack tranches
    exist and `stack_mode` is False on all 37 bots. The stack half is
    written and tested and delists nothing in production today."""

    def test_an_empty_stack_ledger_is_a_no_op(self):
        bot = _Bot(fold=[fold_tr(40)], stack=[], days=7)
        report = bot._despawn_aged_tranches(now=NOW)
        assert report["stack_delisted"] == 0
        assert bot._stack_tranches == []

    def test_the_fold_side_still_delists_with_no_stack_ledger(self):
        """Dormant on one side must not mean dormant on both."""
        bot = _Bot(fold=[fold_tr(40)], stack=[], days=7)
        report = bot._despawn_aged_tranches(now=NOW)
        assert report["fold_delisted"] == 1
        assert bot._fold_tranches == []


class TestItTouchesNothingElse:
    def test_no_order_and_no_balance_was_reached(self):
        _check_no_money_was_reached(
            _Spy(fold=[fold_tr(40)], stack=[stack_tr(40)], days=7)
        )

    def test_holdings_and_lots_are_unchanged(self):
        bot = _Bot(fold=[fold_tr(40)], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert bot._current_holdings == pytest.approx(12.5)
        assert bot._main_lots == [{"units": 12.5, "initial_buy_price": 0.30}]

    def test_target_and_anchor_are_unchanged(self):
        bot = _Bot(fold=[fold_tr(40)], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert bot._target_balance == pytest.approx(50.0)
        assert bot._anchor_target_balance == pytest.approx(50.0)

    def test_pending_wire_credits_are_untouched(self):
        """That pool is real routed income, not a tranche. The sweep
        warns that emptying the queue opens the absorb window; it does
        not take the credits."""
        bot = _Bot(fold=[fold_tr(40)], days=7, pending=342.26)
        bot._despawn_aged_tranches(now=NOW)
        assert bot._pending_wire_credits == pytest.approx(342.26)
        assert "absorb window" in bot._bus.text()

    def test_no_absorb_warning_when_tranches_remain(self):
        """NEGATIVE CONTROL: warning on every sweep would train the
        operator to ignore it."""
        bot = _Bot(fold=[fold_tr(40), fold_tr(2)], days=7, pending=342.26)
        bot._despawn_aged_tranches(now=NOW)
        assert "absorb window" not in bot._bus.text()


class TestTheDerivedBookkeeping:
    def test_the_queue_total_is_recomputed(self):
        """A stale `_fold_queue_usd` would keep the tick's `== 0`
        short-circuit and the panel's Parked USD both reporting money
        with no tranche behind it."""
        bot = _Bot(fold=[fold_tr(40, usd=4.0), fold_tr(2, usd=1.5)], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert bot._fold_queue_usd == pytest.approx(1.5)

    def test_a_despawn_counts_as_discarded_not_closed(self):
        """A closed tranche is one that FOLDED. Conflating the two is
        what made created-minus-closed unreconcilable."""
        bot = _Bot(fold=[fold_tr(40), fold_tr(2)], days=7)
        closed_before = bot._tranches_closed_lifetime
        bot._despawn_aged_tranches(now=NOW)
        assert bot._tranches_closed_lifetime == closed_before
        assert bot._tranches_discarded_lifetime == 1

    def test_created_minus_closed_minus_discarded_is_standing(self):
        bot = _Bot(fold=[fold_tr(40), fold_tr(2)], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert (
            bot._tranches_created_lifetime
            - bot._tranches_closed_lifetime
            - bot._tranches_discarded_lifetime
        ) == len(bot._fold_tranches)

    def test_a_stack_despawn_counts_as_discarded_too(self):
        """The mirror. Round 2 dropped stack records and touched no
        counter at all, so `_stack_created` climbed against a shrinking
        list and nothing recorded the difference."""
        bot = _Bot(stack=[stack_tr(40), stack_tr(2, index=1)], days=7)
        report = bot._despawn_aged_tranches(now=NOW)
        assert report["stack_delisted"] == 1
        assert bot._stack_discarded == 1
        assert bot._stack_created == 2

    def test_both_ledgers_reconcile_after_a_sweep(self):
        _check_both_ledgers_reconcile(
            _Bot(
                fold=[fold_tr(40), fold_tr(2)],
                stack=[stack_tr(40), stack_tr(2, index=1)],
                days=7,
            )
        )

    def test_both_ledgers_reconcile_when_nothing_ages_out(self):
        """NEGATIVE CONTROL: a sweep that delists nothing must not
        record a discard either."""
        bot = _Bot(fold=[fold_tr(2)], stack=[stack_tr(2)], days=7)
        _check_both_ledgers_reconcile(bot)
        assert bot._tranches_discarded_lifetime == 0
        assert bot._stack_discarded == 0

    def test_a_kept_live_order_is_not_counted_as_discarded(self):
        """The one asymmetry must not leak into the ledger: a tranche
        that was KEPT was not removed, so nothing was discarded."""
        bot = _Bot(
            stack=[
                stack_tr(40, status="pending", order_id="ORD-1"),
                stack_tr(40, index=1),
            ],
            days=7,
        )
        _check_both_ledgers_reconcile(bot)
        assert bot._stack_discarded == 1

    def test_a_filled_stack_tranche_still_counts_as_standing(self):
        """Why the stack ledger's `closed` term is structurally zero: a
        fill changes `status` and leaves the record listed, so the
        despawn sweep is the only thing that takes one out."""
        bot = _Bot(stack=[stack_tr(2, status="filled")], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert len(bot._stack_tranches) == 1
        assert bot._stack_tranches[0]["status"] == "filled"
        _check_both_ledgers_reconcile(bot)

    def test_repeated_sweeps_accumulate_on_both_ledgers(self):
        """The counters are running totals, not per-sweep ones."""
        bot = _Bot(
            fold=[fold_tr(40), fold_tr(30), fold_tr(2)],
            stack=[stack_tr(40), stack_tr(30, index=1), stack_tr(2, index=2)],
            days=7,
        )
        bot._despawn_aged_tranches(now=NOW)
        assert (bot._tranches_discarded_lifetime, bot._stack_discarded) == (2, 2)
        # Second sweep, clock advanced so the survivor is now old too.
        bot._despawn_aged_tranches(now=NOW + 10 * DAY)
        assert (bot._tranches_discarded_lifetime, bot._stack_discarded) == (3, 3)
        _check_both_ledgers_reconcile(bot)

    def test_it_is_logged_as_not_a_trade(self):
        bot = _Bot(fold=[fold_tr(40)], days=7)
        bot._despawn_aged_tranches(now=NOW)
        msg = bot._bus.text()
        assert "TRANCHES DESPAWNED" in msg
        assert "No order was placed or cancelled" in msg

    def test_a_sweep_that_delists_nothing_stays_silent(self):
        bot = _Bot(fold=[fold_tr(2)], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert bot._bus.msgs == [], "logged a no-op sweep"


# ---------------------------------------------------------------------------
# The setting round-trips. Every assertion here drives the real factory,
# the real dataclass and the real asdict -- never a source scan.
# ---------------------------------------------------------------------------


class TestItRoundTrips:
    def test_the_factory_accepts_it_for_scrumming(self):
        cfg = make_bot_config(
            BotMode.SCRUMMING,
            exchange_id="coinbase",
            base_currency="USD",
            target_asset="RAVE",
            symbol="RAVE/USD",
            tranche_despawn_days=45,
        )
        assert cfg.tranche_despawn_days == 45

    def test_it_survives_asdict_and_rebuild(self):
        """`BotContainer.get_full_state` saves via `asdict(self.config)`
        and the restore path rebuilds through the factory. This is that
        loop, run for real."""
        cfg = make_bot_config(
            BotMode.SCRUMMING,
            exchange_id="coinbase",
            base_currency="USD",
            target_asset="RAVE",
            symbol="RAVE/USD",
            tranche_despawn_days=45,
        )
        saved = dataclasses.asdict(cfg)
        assert saved["tranche_despawn_days"] == 45
        rebuilt = make_bot_config(
            BotMode.SCRUMMING,
            exchange_id=saved["exchange_id"],
            base_currency=saved["base_currency"],
            target_asset=saved["target_asset"],
            symbol=saved["symbol"],
            tranche_despawn_days=saved["tranche_despawn_days"],
        )
        assert rebuilt.tranche_despawn_days == 45

    def test_an_older_state_file_restores_to_off(self):
        """No state file written before 2026-08-13 carries the key."""
        cfg = make_bot_config(
            BotMode.SCRUMMING,
            exchange_id="coinbase",
            base_currency="USD",
            target_asset="RAVE",
            symbol="RAVE/USD",
        )
        assert cfg.tranche_despawn_days == 0

    def test_it_is_declared_on_the_dataclass_not_merely_set(self):
        """`asdict` only saves DECLARED fields, and `_apply_changes`
        writes a field only when `hasattr(cfg, field)` already holds. An
        attribute stuck on at runtime would survive neither."""
        assert "tranche_despawn_days" in {f.name for f in dataclasses.fields(BotConfig)}

    def test_it_is_scrumming_only(self):
        """The two ledgers it sweeps are ScrummingBot state; neither
        exists on ExtractorBot."""
        with pytest.raises(ValueError):
            make_bot_config(
                BotMode.EXTRACTOR,
                exchange_id="coinbase",
                base_currency="USD",
                tranche_despawn_days=45,
            )


# ---------------------------------------------------------------------------
# THE STACK DISCARD COUNTER SURVIVES A RESTART, driven through the real
# export and the real import.
# ---------------------------------------------------------------------------


class _ExportBot:
    """Only what `export_scrumming_state` reads off `self`. Every name
    was found by driving the real method until it stopped raising, not
    by reading its source."""

    export_scrumming_state = ScrummingBot.export_scrumming_state

    def __init__(self):
        self.bot_id = "bot-despawn-0001"
        self.config = type("C", (), {"symbol": "RAVE/USD"})()
        for _n in (
            "_main_lots",
            "_fold_tranches",
            "_stack_tranches",
            "_pending_wire_ledger",
        ):
            setattr(self, _n, [])
        for _n in (
            "_last_trade_side",
            "_scrum_target_mode",
            "_scrum_target_side",
            "_target_grow_last_side",
        ):
            setattr(self, _n, "")
        for _n in (
            "_target_balance",
            "_anchor_target_balance",
            "_last_trade_price",
            "_quote_to_usd",
            "_fold_queue_usd",
            "_dist_accumulator",
            "_hedge_bal",
            "_hedge_trades",
        ):
            setattr(self, _n, 0.0)
        self._stack_created = 0
        self._stack_discarded = 0


class _RestoreBot:
    """Only what `import_scrumming_state` reads off `self`."""

    import_scrumming_state = ScrummingBot.import_scrumming_state

    def __init__(self):
        self.bot_id = "bot-despawn-0001"
        self.config = type("C", (), {"symbol": "RAVE/USD", "target_balance": 50.0})()
        self._bus = _Bus()
        self._current_holdings = 0.0
        self._anchor_target_balance = 50.0
        self._target_balance = 50.0
        self._standing_surplus_usd = 0.0
        self._fold_cycle_cap_consumed = 0.0
        self._pending_wire_credits = 0.0
        self._last_trade_price = 0.0
        self._last_trade_side = ""
        self._hyst_ref_fold_side = 0.0
        self._hyst_ref_scrum_side = 0.0
        self._hyst_armed_fold_side = False
        self._hyst_armed_scrum_side = False
        self._dist_accumulator = 0.0
        self._hedge_bal = 0.0
        self._hedge_trades = 0
        self._cb_hard_tripped = False
        self._compact_wire_credits = lambda *_a, **_k: None


class TestTheStackDiscardCounterPersists:
    """Without this the ledger silently repairs itself on every launch:
    the discards would be forgotten while `stack_created` and the
    standing list both survive, so the gap re-opens."""

    def test_the_export_stub_works(self):
        """POSITIVE CONTROL. A stub that could not export would make
        every assertion below pass for the wrong reason."""
        assert "stack_created" in _ExportBot().export_scrumming_state()

    def test_the_restore_stub_works(self):
        bot = _RestoreBot()
        bot.import_scrumming_state({"stack_created": 3})
        assert bot._stack_created == 3

    def test_the_counter_is_exported(self):
        bot = _ExportBot()
        bot._stack_discarded = 7
        assert bot.export_scrumming_state()["stack_discarded"] == 7

    def test_the_counter_is_restored(self):
        bot = _RestoreBot()
        bot.import_scrumming_state({"stack_discarded": 7})
        assert bot._stack_discarded == 7

    def test_a_state_file_written_before_the_key_restores_to_zero(self):
        bot = _RestoreBot()
        bot.import_scrumming_state({})
        assert bot._stack_discarded == 0

    def test_the_ledger_still_reconciles_across_the_round_trip(self):
        """Export what a swept bot holds, restore it into a fresh one,
        and require the invariant to survive the trip."""
        swept = _Bot(stack=[stack_tr(40), stack_tr(2, index=1)], days=7)
        swept._despawn_aged_tranches(now=NOW)
        exporter = _ExportBot()
        exporter._stack_tranches = swept._stack_tranches
        exporter._stack_created = swept._stack_created
        exporter._stack_discarded = swept._stack_discarded
        saved = exporter.export_scrumming_state()

        restored = _RestoreBot()
        restored.import_scrumming_state(saved)
        assert (restored._stack_created - restored._stack_discarded) == len(
            restored._stack_tranches
        )

    def test_dropping_the_counter_from_the_file_breaks_the_round_trip(self):
        """PLANTED FAILURE: the state file a build without this key
        would write. The tranches and the created total come back, the
        discards do not, and the ledger no longer reconciles."""
        swept = _Bot(stack=[stack_tr(40), stack_tr(2, index=1)], days=7)
        swept._despawn_aged_tranches(now=NOW)
        exporter = _ExportBot()
        exporter._stack_tranches = swept._stack_tranches
        exporter._stack_created = swept._stack_created
        exporter._stack_discarded = swept._stack_discarded
        saved = exporter.export_scrumming_state()
        saved.pop("stack_discarded")

        restored = _RestoreBot()
        restored.import_scrumming_state(saved)
        assert (restored._stack_created - restored._stack_discarded) != len(
            restored._stack_tranches
        )


# ---------------------------------------------------------------------------
# THE LIVE-SETTINGS SURFACE, built for real and read off the constructed
# object. No source text anywhere below.
# ---------------------------------------------------------------------------


def _scrum_config(**kw):
    return make_bot_config(
        BotMode.SCRUMMING,
        exchange_id="coinbase",
        base_currency="USD",
        target_asset="RAVE",
        symbol="RAVE/USD",
        **kw,
    )


class _GuiBot:
    """The only surface `_create_settings_tab` reads is `.config`."""

    def __init__(self, cfg):
        self.bot_id = "bot-despawn-0001"
        self.config = cfg


def _build_settings_tab(cfg=None, cls=None):
    """Build the REAL Settings tab from the production code.

    `QDialog.__init__` is called directly rather than the dialog's own
    `__init__`, so the object is a genuine dialog carrying every real
    method without the full construction path that wants a live bot, an
    exchange and a bus. The tab itself is built by the code under test.
    """
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QLabel,
        QPushButton,
    )
    from src.gui.bot_live_settings import BotLiveSettingsDialog

    if QApplication.instance() is None:
        QApplication([])
    klass = cls or BotLiveSettingsDialog
    dlg = klass.__new__(klass)
    QDialog.__init__(dlg)
    dlg._bot = _GuiBot(cfg if cfg is not None else _scrum_config())
    dlg._bm = None
    dlg._changes = {}
    dlg._apply_btn = QPushButton("Apply", dlg)
    dlg._change_lbl = QLabel("", dlg)
    return dlg, dlg._create_settings_tab()


def _check_the_control_is_really_on_the_tab(dlg, tab) -> None:
    """THE ORACLE THE SOURCE SCAN COULD NOT BE.

    Read at the constructed widget tree, which is what Qt renders. A
    widget that is built and assigned but never added to a layout is not
    a child of the tab and has no parent, so it never reaches the
    operator -- and every substring the old tests looked for is still
    present in the file.
    """
    from PySide6.QtWidgets import QFormLayout, QSpinBox

    spin = getattr(dlg, "_tranche_despawn_days", None)
    assert spin is not None, "the dialog built no despawn control at all"
    assert isinstance(
        spin, QSpinBox
    ), f"the despawn control is a {type(spin).__name__}, not a spin box"
    assert spin.parentWidget() is not None, (
        "the despawn spin box has no parent: it was constructed and "
        "never added to a layout, so nothing ever shows it"
    )
    assert spin in tab.findChildren(
        QSpinBox
    ), "the despawn spin box is not in the Settings tab's widget tree"

    layout = spin.parentWidget().layout()
    assert isinstance(layout, QFormLayout), (
        f"the despawn control sits in a {type(layout).__name__}, not the "
        f"QFormLayout the rest of the Advanced group uses"
    )
    row: int = layout.getWidgetPosition(spin)[0]
    assert row >= 0, "the despawn spin box is not in a form row"
    label = layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
    assert (
        label is not None and label.widget() is not None
    ), "the despawn row has no label, so the control is unnamed"
    assert (
        "Despawn" in label.widget().text()
    ), f"the despawn row is labelled {label.widget().text()!r}"


def _check_a_change_reaches_the_consumer(dlg) -> None:
    """Drive the control and read the value the SWEEP reads.

    Freshening the widget or the pending-changes dict proves nothing:
    the consumer is `despawn_threshold_days(bot.config)`, so that is
    where the verdict is taken.
    """
    assert despawn_threshold_days(dlg._bot.config) == 0
    dlg._tranche_despawn_days.setValue(30)
    assert (
        dlg._changes.get("tranche_despawn_days") == 30
    ), "moving the control registered no pending change"
    dlg._apply_changes()
    assert (
        despawn_threshold_days(dlg._bot.config) == 30
    ), "Apply did not reach the value the sweep reads"


class TestTheLiveSettingsSurface:
    def test_the_control_is_built_and_laid_out(self):
        dlg, tab = _build_settings_tab()
        _check_the_control_is_really_on_the_tab(dlg, tab)

    def test_it_reads_off_by_default(self):
        dlg, _tab = _build_settings_tab()
        assert dlg._tranche_despawn_days.value() == 0
        assert (
            dlg._tranche_despawn_days.specialValueText() == "Off"
        ), "0 must read as Off rather than as '0 days'"

    def test_seeding_the_control_is_not_an_operator_edit(self):
        """`setValue` runs before `valueChanged` is connected, so simply
        opening the dialog must not arm Apply."""
        dlg, _tab = _build_settings_tab(_scrum_config(tranche_despawn_days=45))
        assert dlg._tranche_despawn_days.value() == 45
        assert dlg._changes == {}

    def test_a_change_reaches_the_value_the_sweep_reads(self):
        dlg, _tab = _build_settings_tab()
        _check_a_change_reaches_the_consumer(dlg)

    def test_the_control_offers_the_documented_range(self):
        dlg, _tab = _build_settings_tab()
        assert dlg._tranche_despawn_days.minimum() == 0
        assert dlg._tranche_despawn_days.maximum() == 365

    def test_a_corrupt_stored_value_still_builds_the_tab(self):
        """The reason the seed goes through the shared reader. Reading
        the field raw would put `int(float('nan'))` in the middle of
        building the Settings tab and hand the operator a traceback."""
        cfg = _scrum_config()
        cfg.tranche_despawn_days = NAN
        dlg, tab = _build_settings_tab(cfg)
        _check_the_control_is_really_on_the_tab(dlg, tab)
        assert dlg._tranche_despawn_days.value() == 0

    def test_an_extractor_bot_still_gets_a_settings_tab(self):
        """`_create_settings_tab` runs for every mode; the Advanced
        group is not behind the scrumming branch."""
        cfg = make_bot_config(
            BotMode.EXTRACTOR,
            exchange_id="coinbase",
            base_currency="USD",
            target_asset="*",
            symbol="",
        )
        dlg, tab = _build_settings_tab(cfg)
        _check_the_control_is_really_on_the_tab(dlg, tab)


# ---------------------------------------------------------------------------
# THE STACK PANEL. The surface the missing counter reached: its health
# ratio is `filled / created`, `filled` counts only STANDING tranches,
# and the sweep removes standing tranches while leaving `created` alone.
# Built for real and read off the constructed widget tree.
# ---------------------------------------------------------------------------


class _GuiStackBot:
    """The surface `_create_stack_tranches_tab` reads."""

    def __init__(self, tranches, created, discarded):
        self.bot_id = "bot-despawn-0001"
        self.config = _scrum_config()
        self._stack_tranches = [dict(t) for t in tranches]
        self._stack_created = created
        self._stack_discarded = discarded

    @classmethod
    def after_a_real_sweep(cls, bot):
        """Seeded from a bot that has actually run the sweep, so the
        panel is driven by the production ledger rather than by numbers
        the test made up."""
        return cls(bot._stack_tranches, bot._stack_created, bot._stack_discarded)


def _build_stack_tab(bot, cls=None):
    """Build the REAL Stack Tranches tab, same construction route the
    Settings tab test uses."""
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QLabel,
        QPushButton,
    )
    from src.gui.bot_live_settings import BotLiveSettingsDialog

    if QApplication.instance() is None:
        QApplication([])
    klass = cls or BotLiveSettingsDialog
    dlg = klass.__new__(klass)
    QDialog.__init__(dlg)
    dlg._bot = bot
    dlg._bm = None
    dlg._changes = {}
    dlg._apply_btn = QPushButton("Apply", dlg)
    dlg._change_lbl = QLabel("", dlg)
    return dlg, dlg._create_stack_tranches_tab()


def _panel_rows(tab) -> dict:
    """Every summary row on the constructed tab, label text -> field
    text. Read off the widget tree, never off source."""
    from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel

    rows = {}
    for box in tab.findChildren(QGroupBox):
        form = box.layout()
        if not isinstance(form, QFormLayout):
            continue
        for i in range(form.rowCount()):
            lab = form.itemAt(i, QFormLayout.ItemRole.LabelRole)
            fld = form.itemAt(i, QFormLayout.ItemRole.FieldRole)
            lw = lab.widget() if lab is not None else None
            fw = fld.widget() if fld is not None else None
            if not isinstance(lw, QLabel) or not isinstance(fw, QLabel):
                continue
            rows[lw.text()] = fw.text()
    return rows


def _row_matching(rows, needle):
    hits = [v for k, v in rows.items() if needle in k.lower()]
    return hits[0] if hits else None


def _check_the_stack_panel_accounts_for_discards(bot, tab) -> None:
    """THE ORACLE FOR THE SURFACE.

    The Fill ratio row divides STANDING filled tranches by the lifetime
    created total. A sweep removes standing tranches and leaves the
    created total alone, so the ratio falls. That is only honest if the
    panel also shows where the missing tranches went — which is what
    the Fold panel's own discarded row does for the fold ratio.
    """
    rows = _panel_rows(tab)
    opened = _row_matching(rows, "opened")
    assert opened is not None, (
        f"the Stack panel reports no lifetime opened total; rows=" f"{sorted(rows)}"
    )
    discarded = _row_matching(rows, "discarded")
    assert discarded is not None, (
        f"the Stack panel shows no discarded row, so its fill ratio "
        f"{_row_matching(rows, 'fill ratio')!r} fell after the sweep "
        f"with nothing on screen accounting for the "
        f"{bot._stack_discarded} delisted tranche(s); rows={sorted(rows)}"
    )
    assert discarded == str(bot._stack_discarded), (
        f"the panel reports {discarded!r} discarded, the ledger says "
        f"{bot._stack_discarded}"
    )
    standing = sum(
        int(_row_matching(rows, w) or 0) for w in ("pending", "filled", "cancelled")
    )
    assert standing + int(discarded) == int(opened), (
        f"the panel does not add up: {standing} standing + {discarded} "
        f"discarded != {opened} opened. Every tranche ever created must "
        f"be on screen as either standing or discarded, or the ratio "
        f"drop is unexplained."
    )


def _blinded_stack_dialog():
    """A real dialog whose Stack tab is built correctly and then has the
    discarded row taken back out."""
    from src.gui.bot_live_settings import BotLiveSettingsDialog

    class _Blinded(BotLiveSettingsDialog):
        def _create_stack_tranches_tab(self):
            tab = super()._create_stack_tranches_tab()
            _strip_discarded_row(tab)
            return tab

    return _Blinded


def _strip_discarded_row(tab) -> None:
    """Remove the discarded row from a correctly-built panel."""
    from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel

    for box in tab.findChildren(QGroupBox):
        form = box.layout()
        if not isinstance(form, QFormLayout):
            continue
        for i in reversed(range(form.rowCount())):
            item = form.itemAt(i, QFormLayout.ItemRole.LabelRole)
            w = item.widget() if item is not None else None
            if isinstance(w, QLabel) and "discarded" in w.text().lower():
                form.removeRow(i)


def _swept_stack_bot():
    """Four stack tranches, two of them aged out by a real sweep."""
    bot = _Bot(
        stack=[
            stack_tr(40),
            stack_tr(40, index=1, status="filled"),
            stack_tr(2, index=2),
            stack_tr(2, index=3, status="filled"),
        ],
        days=7,
    )
    report = bot._despawn_aged_tranches(now=NOW)
    assert report["stack_delisted"] == 2, "fixture did not delist two"
    return bot


class TestTheStackPanelSurface:
    def test_the_panel_accounts_for_what_the_sweep_removed(self):
        swept = _swept_stack_bot()
        gui_bot = _GuiStackBot.after_a_real_sweep(swept)
        _dlg, tab = _build_stack_tab(gui_bot)
        _check_the_stack_panel_accounts_for_discards(gui_bot, tab)

    def test_the_ratio_row_is_still_the_documented_one(self):
        """The row itself is unchanged; only the accounting beside it
        is added. This unit does not redefine the health metric."""
        gui_bot = _GuiStackBot.after_a_real_sweep(_swept_stack_bot())
        _dlg, tab = _build_stack_tab(gui_bot)
        assert _row_matching(_panel_rows(tab), "fill ratio") == "25.0%  (1/4)"

    def test_a_bot_that_was_never_swept_shows_no_extra_row(self):
        """Shown only once non-zero, exactly as the Fold panel does, so
        the panel stays quiet on the 37 bots that have never swept."""
        gui_bot = _GuiStackBot([stack_tr(2)], created=1, discarded=0)
        _dlg, tab = _build_stack_tab(gui_bot)
        assert _row_matching(_panel_rows(tab), "discarded") is None

    def test_an_empty_stack_ledger_still_builds(self):
        gui_bot = _GuiStackBot([], created=0, discarded=0)
        _dlg, tab = _build_stack_tab(gui_bot)
        assert _row_matching(_panel_rows(tab), "opened") == "0"


# ---------------------------------------------------------------------------
# The sweep is wired into the tick, proved by RUNNING the tick.
# ---------------------------------------------------------------------------


class _TickSentinel(Exception):
    """Raised from the stubbed sweep so the tick stops at the call site."""


class _Ticker:
    last = 100.0


def _tickable_bot(days=7):
    """A real ScrummingBot, carrying only what `tick` reads before the
    sweep. Everything else the prologue reaches for is inside a `try`
    and its AttributeError is caught there."""
    bot = object.__new__(ScrummingBot)
    bot.bot_id = "bot-tick-0001"
    bot.config = type(
        "C",
        (),
        {
            "symbol": "RAVE/USD",
            "scrum_read_rate_min": 0,  # bypasses the read-rate skip gate
            "tranche_despawn_days": days,
        },
    )()
    bot._initialised = True  # skips the initialisation branch
    bot._manual_fire_pending = False  # read by the gate's elif branch
    bot._reconcile_tick_counter = 0
    bot._reconcile_interval = 0  # skips the periodic reconcile
    bot._last_price = 100.0
    # `tick_interval` is a read-only property and is not set here: with
    # `scrum_read_rate_min` at 0 the read-rate gate short-circuits
    # before anything reads it.
    bot.stats = type("S", (), {"current_price": 0.0})()

    async def _get_ticker(_symbol):
        return _Ticker()

    bot._get_ticker = _get_ticker
    return bot


def _tick_reaches_the_sweep(bot) -> list:
    """Run the real `tick` and return the arguments the sweep saw.

    The stub RAISES, so a call site buried inside a `try` would swallow
    it and this returns nothing -- which is the discriminator. The sweep
    must not be wrapped, because it is the one thing in the tick with no
    handler above it.
    """
    seen: list = []

    def _sweep(now=None):
        seen.append(now)
        raise _TickSentinel

    bot._despawn_aged_tranches = _sweep
    with pytest.raises(_TickSentinel):
        asyncio.run(bot.tick())
    return seen


class TestItIsWiredIn:
    def test_running_a_tick_runs_the_sweep(self):
        assert _tick_reaches_the_sweep(_tickable_bot()) == [
            None
        ], "a full tick never reached the despawn sweep"

    def test_the_tick_passes_no_clock_so_the_sweep_uses_its_own(self):
        assert _tick_reaches_the_sweep(_tickable_bot())[0] is None

    def test_it_is_not_a_coroutine(self):
        """Every coroutine in this platform runs on the Qt GUI thread.
        A list filter has no reason to be one."""
        assert not inspect.iscoroutinefunction(ScrummingBot._despawn_aged_tranches)

    def test_it_runs_above_the_below_interval_return(self):
        """That return ends the tick on every quiet cycle, so below it
        the sweep would only run on ticks the bot was already busy on.

        Read off the parsed syntax tree, not off the source text: this
        is an ORDERING claim about two statements, and their line
        numbers are what carries it.
        """
        call_line, quiet_line = _tick_statement_lines()
        assert call_line < quiet_line, (
            f"the sweep is called at line {call_line}, below the "
            f"below-interval return at {quiet_line}"
        )


def _tick_statement_lines() -> tuple[int, int]:
    """(sweep call line, below-interval branch line) inside `tick`."""
    source = Path(inspect.getsourcefile(ScrummingBot))
    tree = ast.parse(source.read_text(encoding="utf-8"))
    tick = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "tick"
    )
    call_line = next(
        n.lineno
        for n in ast.walk(tick)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "_despawn_aged_tranches"
    )
    quiet_line = min(
        n.lineno
        for n in ast.walk(tick)
        if isinstance(n, ast.Name) and n.id == "below_interval"
    )
    return call_line, quiet_line


# ---------------------------------------------------------------------------
# THE BLINDED SURFACES. One defect each, applied to the REAL tab after
# the production code has finished building it, so everything except the
# planted fault is genuine.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# EVERY CONVERSION SITE THIS UNIT OWNS, DRIVEN WITH EVERY HOSTILE.
#
# The enumeration is the point. An earlier build named seven sites and
# an adversary found ten; the sweep's own discard counter was reached by
# a bare `int()` outside every `try` in `tick`, so `nan` ended the tick.
# What follows is the whole list, each site driven by exercising the
# REAL code path rather than by re-typing its expression.
#
# RULE B: a type is not a domain. `type(float("nan")) is float` is True,
# so the value rows come first and carry the weight.
# ---------------------------------------------------------------------------


#: (label, value). Sixteen shapes, every one of them reachable from a
#: JSON state file or a hand-edited config.
HOSTILES = [
    ("nan", NAN),
    ("inf", INF),
    ("-inf", NINF),
    ("-0.0", -0.0),
    ("0", 0),
    ("-1", -1),
    ("'30'", "30"),
    ("None", None),
    ("True", True),
    ("Decimal('30')", Decimal("30")),
    ("10**400", 10**400),
    ("1e308", 1e308),
    ("float subclass", _FloatSubclass(30.0)),
    ("object with __float__", _HasFloat()),
    ("[1]", [1]),
    ("b'30'", b"30"),
]


def _site_01_shared_reader(raw):
    """`as_finite_float` — bot_container.py, the rule the rest share."""
    as_finite_float(raw)


def _site_02_threshold_reader(raw):
    """`despawn_threshold_days` — `int(days)` on a config field."""
    despawn_threshold_days(_cfg_with(raw))


def _site_03_fold_timestamp(raw):
    """`_tranche_age_seconds(t, "created_ts", now)` — `now - _ts`."""
    bot = _Bot(fold=[fold_tr(400)], days=7)
    bot._fold_tranches[0]["created_ts"] = raw
    bot._despawn_aged_tranches(now=NOW)


def _site_04_stack_timestamp(raw):
    """The same helper on the stack ledger's own field."""
    bot = _Bot(stack=[stack_tr(400)], days=7)
    bot._stack_tranches[0]["opened_ts"] = raw
    bot._despawn_aged_tranches(now=NOW)


def _site_05_injected_now(raw):
    """`_now = time.time() if now is None else as_finite_float(now)`."""
    _Bot(fold=[fold_tr(400)], days=7)._despawn_aged_tranches(now=raw)


def _site_06_cutoff_arithmetic(raw):
    """`_cutoff = _days * 86400.0`, the multiplication `DESPAWN_MAX_DAYS`
    exists to keep in range."""
    _Bot(fold=[fold_tr(400)], stack=[stack_tr(400)], days=raw)._despawn_aged_tranches(
        now=NOW
    )


def _site_07_delisted_usd_total(raw):
    """`report["usd_delisted"] += _usd` on a DELISTED tranche."""
    _Bot(fold=[fold_tr(400, usd=raw)], days=7)._despawn_aged_tranches(now=NOW)


def _site_08_queue_total_recompute(raw):
    """The `sum(...)` over SURVIVING tranches. Deliberately stricter than
    its six siblings, which is the documented divergence."""
    _Bot(fold=[fold_tr(400), fold_tr(1, usd=raw)], days=7)._despawn_aged_tranches(
        now=NOW
    )


def _site_09_fold_discard_counter(raw):
    """THE SITE ROUND 2's LIST OMITTED. A bare `int()` on a counter read
    back from state, inside the sweep, outside every `try` in `tick`."""
    bot = _Bot(fold=[fold_tr(400)], days=7)
    bot._tranches_discarded_lifetime = raw
    bot._despawn_aged_tranches(now=NOW)


def _site_10_stack_discard_counter(raw):
    """Its stack-side mirror, added by this round."""
    bot = _Bot(stack=[stack_tr(400)], days=7)
    bot._stack_discarded = raw
    bot._despawn_aged_tranches(now=NOW)


def _site_11_parked_wire_credit(raw):
    """`_parked = as_finite_float(...)` and the `${_parked:.4f}` format
    that follows it."""
    _Bot(fold=[fold_tr(400)], days=7, pending=raw)._despawn_aged_tranches(now=NOW)


def _site_12_state_export(raw):
    """The `stack_discarded` key on the way OUT to the state file."""
    bot = _ExportBot()
    bot._stack_discarded = raw
    bot.export_scrumming_state()


def _site_13_state_restore(raw):
    """The same key on the way IN — the actual JSON boundary, where
    `NaN` and `Infinity` are both representable."""
    _RestoreBot().import_scrumming_state({"stack_discarded": raw})


def _site_14_settings_spinbox_seed(raw):
    """`setValue(despawn_threshold_days(cfg))` while the Settings tab is
    under construction."""
    cfg = _scrum_config()
    cfg.tranche_despawn_days = raw
    _build_settings_tab(cfg)


def _site_15_stack_panel_discarded_row(raw):
    """The Stack panel's read of the counter, while the tab is being
    built. A raise here hands the operator a traceback, not a panel."""
    _build_stack_tab(_GuiStackBot([stack_tr(2)], created=1, discarded=raw))


CONVERSION_SITES = [
    ("01 shared reader `as_finite_float`", _site_01_shared_reader),
    ("02 threshold reader `despawn_threshold_days`", _site_02_threshold_reader),
    ("03 fold timestamp `created_ts`", _site_03_fold_timestamp),
    ("04 stack timestamp `opened_ts`", _site_04_stack_timestamp),
    ("05 injected `now`", _site_05_injected_now),
    ("06 cutoff `_days * 86400.0`", _site_06_cutoff_arithmetic),
    ("07 delisted usd total", _site_07_delisted_usd_total),
    ("08 fold queue total recompute", _site_08_queue_total_recompute),
    ("09 fold discard counter", _site_09_fold_discard_counter),
    ("10 stack discard counter", _site_10_stack_discard_counter),
    ("11 parked wire credit", _site_11_parked_wire_credit),
    ("12 state export `stack_discarded`", _site_12_state_export),
    ("13 state restore `stack_discarded`", _site_13_state_restore),
    ("14 settings spinbox seed", _site_14_settings_spinbox_seed),
    ("15 stack panel discarded row", _site_15_stack_panel_discarded_row),
]


def _check_a_site_refuses_by_value(driver, label, raw) -> None:
    """The oracle: refused by VALUE, never by raising.

    Written once and reused by the planted failure below, so the blinded
    expression is judged by the same instrument the real one is.
    """
    try:
        driver(raw)
    except Exception as exc:
        raise AssertionError(
            f"{label} raised {type(exc).__name__}: {exc} on {raw!r}. "
            f"Every one of these sites is reached from the despawn sweep "
            f"or from a tab under construction, and neither has a handler "
            f"above it."
        ) from exc


class TestEveryConversionSiteSurvivesEveryHostile:
    @pytest.mark.parametrize(
        "label,driver", CONVERSION_SITES, ids=[s[0] for s in CONVERSION_SITES]
    )
    @pytest.mark.parametrize("hostile,raw", HOSTILES, ids=[h[0] for h in HOSTILES])
    def test_site(self, label, driver, hostile, raw):
        _check_a_site_refuses_by_value(driver, f"{label} [{hostile}]", raw)

    def test_the_site_list_is_not_silently_shrinking(self):
        """A site removed from the table is a site nobody drives. Pinned
        so deleting one is a decision rather than an omission."""
        assert len(CONVERSION_SITES) == 15
        assert len(HOSTILES) == 16


def _bare_int_counter(raw):
    """THE EXPRESSION THIS ROUND REPLACED, kept verbatim as the plant.

    `int(getattr(self, "_tranches_discarded_lifetime", 0) or 0)`, which
    is what stood at the fold-discard site while the seven other
    conversions around it went through the shared reader.
    """
    return int(raw or 0) + 1


class TestThePlantedConversionDefect:
    """Two-sided control for the whole table above."""

    #: MEASURED, not assumed. A first pass at this table claimed `"30"`,
    #: `b"30"` and `Decimal("30")` raised too; they do not — see the
    #: laundering test below, which is what they do instead.
    RAISING_ROWS = [
        (NAN, ValueError),
        (INF, OverflowError),
        (NINF, OverflowError),
        ([1], TypeError),
        (_HasFloat(), TypeError),
    ]

    @pytest.mark.parametrize("raw,exc", RAISING_ROWS)
    def test_the_bare_int_really_does_raise(self, raw, exc):
        """THE MEASUREMENT BEHIND THE REPAIR, not an assertion about it.
        Each of these left the sweep and propagated out of `tick`."""
        with pytest.raises(exc):
            _bare_int_counter(raw)

    @pytest.mark.parametrize("raw", ["30", b"30", Decimal("30")])
    def test_the_bare_int_launders_the_rows_it_does_not_raise_on(self, raw):
        """THE SECOND DEFECT AT THE SAME SITE, and the quieter one.

        `int()` accepts a numeric string, bytes and a Decimal and
        converts them, so a corrupted counter would come back as a
        plausible number with nothing to show it had ever been wrong.
        The shared rule refuses all three by type, which is the whole
        difference between refusing a value and laundering it.
        """
        assert _bare_int_counter(raw) == 31
        assert as_finite_float(raw) is None

    @pytest.mark.parametrize("raw", [r for r, _ in RAISING_ROWS])
    def test_the_oracle_goes_red_on_the_bare_int(self, raw):
        """The same oracle the fifteen sites are judged by, run against
        the expression they replaced."""
        with pytest.raises(AssertionError, match="raised"):
            _check_a_site_refuses_by_value(_bare_int_counter, "the bare int()", raw)

    @pytest.mark.parametrize("raw", [NAN, INF, NINF, "30", [1], b"30"])
    def test_the_guarded_counter_survives_the_same_rows(self, raw):
        """The other side of the control: same inputs, real site, no
        exception and the counter still advances by the delisted count."""
        bot = _Bot(fold=[fold_tr(400)], days=7)
        bot._tranches_discarded_lifetime = raw
        report = bot._despawn_aged_tranches(now=NOW)
        assert report["fold_delisted"] == 1
        assert bot._tranches_discarded_lifetime == 1


def _detach(dlg) -> None:
    """Constructed, assigned to its attribute, and in no layout."""
    dlg._tranche_despawn_days.setParent(None)


def _disconnect(dlg) -> None:
    """The control moves and nothing is listening."""
    dlg._tranche_despawn_days.valueChanged.disconnect()


def _rewire_to_undeclared_field(dlg) -> None:
    """The change is recorded under a key `BotConfig` does not declare,
    so `_apply_changes` skips it and the setting never lands."""
    dlg._tranche_despawn_days.valueChanged.disconnect()
    dlg._tranche_despawn_days.valueChanged.connect(
        lambda v: dlg._mark_changed("tranche_despawn_days_NOT_A_FIELD", v)
    )


def _blinded_dialog(blind):
    """A real dialog whose Settings tab is built normally and then
    broken by `blind`, one defect at a time."""
    from src.gui.bot_live_settings import BotLiveSettingsDialog

    class _Blinded(BotLiveSettingsDialog):
        def _create_settings_tab(self):
            tab = super()._create_settings_tab()
            blind(self)
            return tab

    return _Blinded


# ---------------------------------------------------------------------------
# PLANTED FAILURES. Each blinded mechanism is judged by the SAME oracle
# the real one is, and every one of them must go red.
# ---------------------------------------------------------------------------


class _BlindNeverDelists(_Bot):
    """The commonest way a sweep goes quietly wrong: it runs and does
    nothing."""

    def _despawn_aged_tranches(self, now=None):
        return {
            "threshold_days": 0,
            "fold_delisted": 0,
            "stack_delisted": 0,
            "stack_kept_live_order": 0,
            "ageless_kept": 0,
            "usd_delisted": 0.0,
        }


class _BlindDelistsEverything(_Bot):
    def _despawn_aged_tranches(self, now=None):
        self._fold_tranches = []
        self._stack_tranches = []
        return {
            "threshold_days": 1,
            "fold_delisted": 0,
            "stack_delisted": 0,
            "stack_kept_live_order": 0,
            "ageless_kept": 0,
            "usd_delisted": 0.0,
        }


class _BlindExclusiveBoundary(_Bot):
    """`>` where the rule says `>=`."""

    def _despawn_aged_tranches(self, now=None):
        days = self._despawn_threshold_days()
        if days <= 0:
            return {"fold_delisted": 0}
        cut = days * DAY
        self._fold_tranches = [
            t
            for t in self._fold_tranches
            if not ((t.get("created_ts") or 0) > 0 and (now - t["created_ts"]) > cut)
        ]
        return {"fold_delisted": 0}


class _BlindAgelessIsAncient(_Bot):
    """Reads a missing timestamp as the epoch, which is the exact
    mistake the exact-type test exists to prevent."""

    def _despawn_aged_tranches(self, now=None):
        days = self._despawn_threshold_days()
        if days <= 0:
            return {"fold_delisted": 0}
        cut = days * DAY
        self._fold_tranches = [
            t
            for t in self._fold_tranches
            if (now - float(t.get("created_ts") or 0)) < cut
        ]
        return {"fold_delisted": 0}


class _BlindIsinstanceTimestamp(_Bot):
    """`isinstance` where the rule says exact type, so `True` reads as
    1.0 and dates the record to the epoch."""

    def _despawn_aged_tranches(self, now=None):
        days = self._despawn_threshold_days()
        if days <= 0:
            return {"fold_delisted": 0}
        cut = days * DAY
        self._fold_tranches = [
            t
            for t in self._fold_tranches
            if not (
                isinstance(t.get("created_ts"), (int, float))
                and (now - float(t["created_ts"])) >= cut
            )
        ]
        return {"fold_delisted": 0}


class _BlindIgnoresTheOffSwitch(_Bot):
    def _despawn_aged_tranches(self, now=None):
        cut = 7 * DAY
        self._fold_tranches = [
            t
            for t in self._fold_tranches
            if (now - float(t.get("created_ts") or now)) < cut
        ]
        self._stack_tranches = [
            t
            for t in self._stack_tranches
            if (now - float(t.get("opened_ts") or now)) < cut
        ]
        return {"fold_delisted": 0}


class _BlindSweepsFoldOnly(_Bot):
    """The mirroring failure: one side of the ladder gets the feature."""

    def _despawn_aged_tranches(self, now=None):
        days = self._despawn_threshold_days()
        if days <= 0:
            return {"fold_delisted": 0}
        cut = days * DAY
        self._fold_tranches = [
            t
            for t in self._fold_tranches
            if (now - float(t.get("created_ts") or now)) < cut
        ]
        return {"fold_delisted": 0}


class _BlindFoldDiscardNotCounted(_Bot):
    """The fold records go and the fold counter does not move.

    Written as "run the real sweep, then undo the one increment", so the
    plant is EXACTLY the missing bookkeeping and nothing else. Any other
    difference would let the oracle pass or fail for the wrong reason.
    """

    def _despawn_aged_tranches(self, now=None):
        before = self._tranches_discarded_lifetime
        report = _Bot._despawn_aged_tranches(self, now=now)
        self._tranches_discarded_lifetime = before
        return report


class _BlindStackDiscardNotCounted(_Bot):
    """ROUND 2's STACK BRANCH, RESTORED.

    `self._stack_tranches = _stack_keep` and no counter touched. This
    shipped, no test in that build caught it, and it drove the Stack
    panel's fill ratio down on every sweep with nothing accounting for
    the tranches that went.
    """

    def _despawn_aged_tranches(self, now=None):
        before = self._stack_discarded
        report = _Bot._despawn_aged_tranches(self, now=now)
        self._stack_discarded = before
        return report


class _BlindDiscardCountedAsClosed(_Bot):
    """The conflation the split exists to prevent: a delist booked as a
    fold-back. The ledger still reconciles, so only a test that reads
    the two counters APART can see it."""

    def _despawn_aged_tranches(self, now=None):
        before = self._tranches_discarded_lifetime
        report = _Bot._despawn_aged_tranches(self, now=now)
        moved = self._tranches_discarded_lifetime - before
        self._tranches_discarded_lifetime = before
        self._tranches_closed_lifetime += moved
        return report


class _SpyThatTouchesMoney(_Spy):
    """A sweep that consults the position on its way past."""

    def _despawn_aged_tranches(self, now=None):
        _ = self._current_holdings
        _ = self._main_lots
        return _Bot._despawn_aged_tranches(self, now=now)


class TestPlantedFailures:
    """Rule 1 of two-sided control: each check is observed FAILING on a
    defect of the kind it exists to catch, at the surface it reports
    through."""

    def test_never_delisting_fails_the_old_tranche_check(self):
        with pytest.raises(AssertionError):
            _check_old_fold_is_delisted(
                _BlindNeverDelists(fold=[fold_tr(40), fold_tr(2)], days=7)
            )

    def test_delisting_everything_fails_the_young_tranche_check(self):
        with pytest.raises(AssertionError):
            _check_young_fold_survives(
                _BlindDelistsEverything(fold=[fold_tr(40), fold_tr(2)], days=7)
            )

    def test_an_exclusive_boundary_fails_the_boundary_check(self):
        with pytest.raises(AssertionError):
            _check_boundary_is_inclusive(
                _BlindExclusiveBoundary(fold=[fold_tr(7)], days=7)
            )

    def test_treating_ageless_as_ancient_fails_the_ageless_check(self):
        with pytest.raises(AssertionError):
            _check_ageless_is_kept(
                _BlindAgelessIsAncient(fold=[fold_tr(40, dated=False)], days=7)
            )

    def test_an_isinstance_timestamp_gate_fails_the_ageless_check(self):
        """`True` is an `int` by isinstance, so the blinded sweep dates
        the record to 1970 and deletes it."""
        bot = _BlindIsinstanceTimestamp(fold=[fold_tr(40)], days=7)
        bot._fold_tranches[0]["created_ts"] = True
        with pytest.raises(AssertionError):
            _check_ageless_is_kept(bot)

    def test_ignoring_the_off_switch_fails_the_off_check(self):
        with pytest.raises(AssertionError):
            _check_off_delists_nothing(
                _BlindIgnoresTheOffSwitch(
                    fold=[fold_tr(400)], stack=[stack_tr(400)], days=0
                )
            )

    def test_sweeping_one_side_fails_the_mirror_check(self):
        with pytest.raises(AssertionError):
            _check_both_sides_agree(
                _BlindSweepsFoldOnly(
                    fold=[fold_tr(40), fold_tr(2)],
                    stack=[stack_tr(40), stack_tr(2, index=1)],
                    days=7,
                )
            )

    # -- the ledger accounting, broken on each side in turn -------------

    def test_an_uncounted_fold_discard_fails_the_ledger_check(self):
        with pytest.raises(AssertionError, match="FOLD ledger"):
            _check_both_ledgers_reconcile(
                _BlindFoldDiscardNotCounted(
                    fold=[fold_tr(40), fold_tr(2)],
                    stack=[stack_tr(40), stack_tr(2, index=1)],
                    days=7,
                )
            )

    def test_an_uncounted_stack_discard_fails_the_ledger_check(self):
        """THE GAP ROUND 2 LEFT. Its stack branch removed records and
        recorded nothing, and no test in that build went red."""
        with pytest.raises(AssertionError, match="STACK ledger"):
            _check_both_ledgers_reconcile(
                _BlindStackDiscardNotCounted(
                    fold=[fold_tr(40), fold_tr(2)],
                    stack=[stack_tr(40), stack_tr(2, index=1)],
                    days=7,
                )
            )

    def test_each_break_is_caught_on_its_OWN_side(self):
        """Neither plant may be caught by the other side's assertion, or
        the oracle would be reporting one ledger under two names."""
        fold_blind = _BlindFoldDiscardNotCounted(
            fold=[fold_tr(40), fold_tr(2)],
            stack=[stack_tr(40), stack_tr(2, index=1)],
            days=7,
        )
        fold_blind._despawn_aged_tranches(now=NOW)
        assert _stack_ledger(fold_blind)[0] == _stack_ledger(fold_blind)[1]
        stack_blind = _BlindStackDiscardNotCounted(
            fold=[fold_tr(40), fold_tr(2)],
            stack=[stack_tr(40), stack_tr(2, index=1)],
            days=7,
        )
        stack_blind._despawn_aged_tranches(now=NOW)
        assert _fold_ledger(stack_blind)[0] == _fold_ledger(stack_blind)[1]

    def test_booking_a_discard_as_closed_fails_the_split_check(self):
        """The ledger still reconciles under this defect, which is why
        the separate counters are asserted separately."""
        bot = _BlindDiscardCountedAsClosed(fold=[fold_tr(40), fold_tr(2)], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert (
            _fold_ledger(bot)[0] == _fold_ledger(bot)[1]
        ), "the plant was meant to keep the ledger balanced"
        assert bot._tranches_discarded_lifetime == 0
        assert bot._tranches_closed_lifetime == 39

    def test_reaching_for_the_position_fails_the_no_money_check(self):
        with pytest.raises(AssertionError):
            _check_no_money_was_reached(
                _SpyThatTouchesMoney(fold=[fold_tr(40)], days=7)
            )

    def test_the_reach_recorder_actually_records(self):
        """The no-money oracle is only worth anything if the recorder
        sees reaches at all. A silent recorder would pass everything."""
        spy = _Spy(fold=[fold_tr(40)], days=7)
        spy._despawn_aged_tranches(now=NOW)
        reached = set(object.__getattribute__(spy, "reached"))
        assert "_fold_tranches" in reached
        assert "config" in reached

    # -- the NaN hole, planted back --------------------------------------

    def test_the_value_table_catches_the_old_type_only_gate(self):
        """The previous build's reader, judged by the SAME table the
        real one passes."""
        with pytest.raises(AssertionError):
            _check_threshold_table(_type_only_gate)

    @pytest.mark.parametrize(
        "label,raw,exc",
        [
            ("nan", NAN, ValueError),
            ("inf", INF, OverflowError),
            ("-inf", NINF, OverflowError),
        ],
    )
    def test_the_old_gate_raises_on_each_non_finite_row(self, label, raw, exc):
        """Named individually, because "the table failed" does not say
        which rows carried it. Each of these left the sweep and
        propagated out of `tick`."""
        with pytest.raises(exc):
            _type_only_gate(_cfg_with(raw))

    @pytest.mark.parametrize("raw", [NAN, INF, NINF])
    def test_the_real_reader_survives_the_same_rows(self, raw):
        """The other side of the control: the same three inputs, the
        same table, and no exception."""
        assert despawn_threshold_days(_cfg_with(raw)) == 0

    # -- the widget that is built and never laid out ---------------------

    def test_a_never_laid_out_control_fails_the_widget_check(self):
        """THE ORACLE FALSE NEGATIVE THIS FILE REPLACES.

        The widget is constructed, assigned to its attribute and then
        detached, which is indistinguishable from "never added to a
        layout" as far as Qt and the operator are concerned. Every
        substring the old source-scan looked for is still in the file,
        so the old assertion passes on this state and the new one must
        not.
        """
        dlg, tab = _build_settings_tab(cls=_blinded_dialog(_detach))
        with pytest.raises(AssertionError):
            _check_the_control_is_really_on_the_tab(dlg, tab)

    def test_a_control_wired_to_nothing_fails_the_consumer_check(self):
        """A spin box that moves and never marks a change is the second
        way the surface can be decorative."""
        dlg, _tab = _build_settings_tab(cls=_blinded_dialog(_disconnect))
        with pytest.raises(AssertionError):
            _check_a_change_reaches_the_consumer(dlg)

    def test_a_field_missing_from_the_dataclass_fails_the_consumer_check(self):
        """`_apply_changes` writes only where `hasattr(cfg, field)`, so
        a widget whose key is not a declared field silently applies
        nothing. This is why bot_container.py is in the touch set."""
        dlg, _tab = _build_settings_tab(
            cls=_blinded_dialog(_rewire_to_undeclared_field)
        )
        with pytest.raises(AssertionError):
            _check_a_change_reaches_the_consumer(dlg)

    # -- the Stack panel -------------------------------------------------

    def test_the_round_2_state_fails_the_stack_panel_check(self):
        """THE DEFECT AT ITS SURFACE. The sweep removed the records and
        never bumped the counter, so the panel has four opened, two
        standing and nothing saying where the other two went."""
        swept = _swept_stack_bot()
        gui_bot = _GuiStackBot(swept._stack_tranches, swept._stack_created, discarded=0)
        _dlg, tab = _build_stack_tab(gui_bot)
        with pytest.raises(AssertionError, match="no discarded row"):
            _check_the_stack_panel_accounts_for_discards(gui_bot, tab)

    def test_a_stripped_row_fails_the_stack_panel_check(self):
        """The oracle reads the WIDGET, not the bot: a correct ledger
        with the row missing from the panel must still go red."""
        gui_bot = _GuiStackBot.after_a_real_sweep(_swept_stack_bot())
        _dlg, tab = _build_stack_tab(gui_bot, cls=_blinded_stack_dialog())
        with pytest.raises(AssertionError, match="no discarded row"):
            _check_the_stack_panel_accounts_for_discards(gui_bot, tab)

    def test_a_miscounted_row_fails_the_stack_panel_check(self):
        """A row that is present but wrong is the third way the surface
        can lie, and the arithmetic assertion is what catches it."""
        swept = _swept_stack_bot()
        gui_bot = _GuiStackBot(
            swept._stack_tranches, swept._stack_created, discarded=99
        )
        _dlg, tab = _build_stack_tab(gui_bot)
        with pytest.raises(AssertionError, match="does not add up"):
            _check_the_stack_panel_accounts_for_discards(gui_bot, tab)

    # -- the tick wiring -------------------------------------------------

    def test_an_unwired_tick_fails_the_wiring_check(self):
        """A bot whose sweep is never called from `tick` must not reach
        the sentinel. Driven by overriding the whole tick, because the
        production one does call it.

        `pytest.raises` reports a missing exception as `Failed`, so that
        is what the blinded run must produce.
        """
        bot = _tickable_bot()

        async def _tick_without_the_sweep():
            return None

        bot.tick = _tick_without_the_sweep
        with pytest.raises(pytest.fail.Exception):
            _tick_reaches_the_sweep(bot)
