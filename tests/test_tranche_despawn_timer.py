"""``ScrummingBot._despawn_aged_tranches`` — the tranche despawn timer.

The sweep removes fold tranches aged on ``created_ts`` and stack tranches
aged on ``opened_ts`` once ``despawn_threshold_days`` reads above zero.
``_Bot`` drives the real method, ``_Spy`` records every attribute it
reaches, and ``_build_settings_tab`` builds the real spin box that writes
the setting. ``THRESHOLD_TABLE`` and ``HOSTILES`` fix the value domain each
``_check_*`` oracle is driven over.
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import math
import types
from decimal import Decimal
from fractions import Fraction

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


# Each stub carries only the surface `_despawn_aged_tranches` reads, so
# any other reach raises AttributeError.
class _Bus:
    def __init__(self):
        self.msgs = []

    def emit(self, _ev, **kw):
        self.msgs.append(kw.get("message", ""))

    def text(self):
        return "\n".join(self.msgs)


class _Bot:
    """What `_despawn_aged_tranches` touches, plus money-side state it leaves alone."""

    _despawn_aged_tranches = ScrummingBot._despawn_aged_tranches
    _despawn_threshold_days = ScrummingBot._despawn_threshold_days
    # Reading it off the class unwraps the descriptor, so it is re-wrapped
    # to keep `tranche` as the first argument.
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
        # `as_finite_float`, not `float(x or 0)`: one fixture carries a usd
        # the latter raises on.
        self._fold_queue_usd = sum(
            (as_finite_float(t.get("usd", 0)) or 0.0) for t in self._fold_tranches
        )
        self._pending_wire_credits = pending
        self._tranches_created_lifetime = 40
        self._tranches_closed_lifetime = 40 - len(self._fold_tranches)
        self._tranches_discarded_lifetime = 0
        # Seeded so `created - closed - discarded == standing` already holds
        # before `_despawn_aged_tranches` runs.
        self._stack_created = len(self._stack_tranches)
        self._stack_discarded = 0
        self._current_holdings = 12.5
        self._main_lots = [{"units": 12.5, "initial_buy_price": 0.30}]
        self._target_balance = 50.0
        self._anchor_target_balance = 50.0
        self.stats = type("S", (), {})()
        self._bus = _Bus()


def fold_tr(age_days, usd=1.0, units=3.0, ref=0.30, ibp=0.35, dated=True):
    """A fold tranche ``age_days`` old; ``dated=False`` omits ``created_ts``."""
    t = {"usd": usd, "units": units, "ref": ref, "initial_buy_price": ibp}
    if dated:
        t["created_ts"] = NOW - age_days * DAY
    return t


def stack_tr(age_days, index=0, status="pending", order_id=None, dated=True):
    """A stack tranche ``age_days`` old, Invisible-mode by default.

    ``order_id=None`` is what ``_open_stack_from_scrum`` writes outside
    Visible mode.
    """
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
    """A config object carrying ``raw`` as ``tranche_despawn_days``."""
    return type("C", (), {"tranche_despawn_days": raw})()


def _cfg_without():
    """A config with no ``tranche_despawn_days`` attribute at all."""
    return type("C", (), {})()


# Each `_check_*` oracle is written once here and re-run against a broken
# sweep by `TestPlantedFailures`.
def _check_old_fold_is_delisted(bot) -> None:
    """``_despawn_aged_tranches`` removes a fold tranche older than the threshold."""
    bot._despawn_aged_tranches(now=NOW)
    refs = [t.get("created_ts") for t in bot._fold_tranches]
    assert (
        NOW - 40 * DAY not in refs
    ), "a 40-day fold tranche survived a 7-day despawn threshold"


def _check_young_fold_survives(bot) -> None:
    """``_despawn_aged_tranches`` keeps a fold tranche younger than the threshold."""
    bot._despawn_aged_tranches(now=NOW)
    refs = [t.get("created_ts") for t in bot._fold_tranches]
    assert (
        NOW - 2 * DAY in refs
    ), "a 2-day fold tranche was delisted at a 7-day threshold"


def _check_boundary_is_inclusive(bot) -> None:
    """A tranche aged exactly the threshold is removed by ``_despawn_aged_tranches``."""
    bot._despawn_aged_tranches(now=NOW)
    assert bot._fold_tranches == [], (
        "a tranche aged EXACTLY the threshold survived; the documented "
        "rule is age >= threshold"
    )


def _check_ageless_is_kept(bot) -> None:
    """``_despawn_aged_tranches`` keeps a record with no usable timestamp."""
    before = len(bot._fold_tranches)
    bot._despawn_aged_tranches(now=NOW)
    assert len(bot._fold_tranches) == before, (
        "an undated tranche was removed; the sweep removes on measured "
        "age and this record has none"
    )


def _check_off_delists_nothing(bot) -> None:
    """A ``despawn_threshold_days`` of 0 leaves both ledgers untouched."""
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
    """One `tranche_despawn_days` sweeps `_fold_tranches` and `_stack_tranches`."""
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
    """``(created - closed - discarded, len(_fold_tranches))``."""
    return (
        int(bot._tranches_created_lifetime)
        - int(bot._tranches_closed_lifetime)
        - int(bot._tranches_discarded_lifetime),
        len(bot._fold_tranches),
    )


def _stack_ledger(bot) -> tuple[int, int]:
    """``(created - closed - discarded, len(_stack_tranches))``.

    ``_stack_closed`` is read through ``getattr`` and is absent today, since
    a fill sets ``status`` and leaves the record listed.
    """
    return (
        int(bot._stack_created)
        - int(getattr(bot, "_stack_closed", 0) or 0)
        - int(bot._stack_discarded),
        len(bot._stack_tranches),
    )


def _check_both_ledgers_reconcile(bot) -> None:
    """`_fold_ledger` and `_stack_ledger` both balance after a sweep."""
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
        # Record-keeping, like `_tranches_discarded_lifetime`, not money.
        "_stack_discarded",
    }
)

#: Reading any of these would put `_despawn_aged_tranches` near an order
#: or a balance; named separately so the failure message says which.
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
    """Records every attribute reach into ``reached``.

    ``__getattribute__`` catches the names that exist and ``__getattr__``
    catches the misses.
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
    """No name in ``MONEY_REACHES`` and nothing outside ``ALLOWED_REACHES`` was read."""
    spy._despawn_aged_tranches(now=NOW)
    reached = set(object.__getattribute__(spy, "reached"))
    reached.discard("reached")
    touched_money = sorted(reached & MONEY_REACHES)
    assert touched_money == [], (
        f"the despawn sweep reached for {touched_money}; removing a "
        f"record must not go near an order or a balance"
    )
    stray = sorted(reached - ALLOWED_REACHES)
    assert stray == [], (
        f"the despawn sweep reached for {stray}, which is outside the "
        f"record-keeping surface it is allowed to touch"
    )


class TestTheInstrumentWorks:
    """``_Bot`` starts populated and ``_despawn_threshold_days`` reads the config."""

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
        """`age >= threshold` removes a tranche aged the threshold to the second."""
        _check_boundary_is_inclusive(_Bot(fold=[fold_tr(7)], days=7))

    def test_one_second_under_the_threshold_survives(self):
        """One second under the threshold keeps the tranche in ``_fold_tranches``."""
        t = fold_tr(7)
        t["created_ts"] += 1.0
        bot = _Bot(fold=[t], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert len(bot._fold_tranches) == 1

    def test_a_future_dated_tranche_is_not_delisted(self):
        """A future `created_ts` yields a negative age, younger than every threshold."""
        bot = _Bot(fold=[fold_tr(-30)], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert len(bot._fold_tranches) == 1


class TestTheAgelessRule:
    """A tranche whose ``created_ts`` ``as_finite_float`` refuses is never removed."""

    def test_a_tranche_with_no_timestamp_key_is_kept(self):
        _check_ageless_is_kept(_Bot(fold=[fold_tr(40, dated=False)], days=7))

    def test_a_none_timestamp_is_kept(self):
        bot = _Bot(fold=[fold_tr(40)], days=7)
        bot._fold_tranches[0]["created_ts"] = None
        _check_ageless_is_kept(bot)

    def test_a_zero_timestamp_is_kept(self):
        """A ``created_ts`` of 0 reads as unset, not as the epoch."""
        bot = _Bot(fold=[fold_tr(40)], days=7)
        bot._fold_tranches[0]["created_ts"] = 0
        _check_ageless_is_kept(bot)

    def test_a_true_timestamp_is_kept(self):
        """`as_finite_float` refuses `True`, which `isinstance` would read as 1.0."""
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
        """`nan` and the infinities are exactly `float`.

        `as_finite_float` refuses all three.
        """
        bot = _Bot(fold=[fold_tr(40)], days=7)
        bot._fold_tranches[0]["created_ts"] = bad
        _check_ageless_is_kept(bot)

    def test_an_out_of_float_range_timestamp_is_kept(self):
        """``as_finite_float`` refuses an int too large for ``float()``."""
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


class _HasFloat:
    def __float__(self):
        return 30.0


class _FloatSubclass(float):
    pass


#: (label, stored value, whole days `despawn_threshold_days` returns).
THRESHOLD_TABLE = [
    # `float` by exact type and still refused
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
    """Drive ``reader`` over every row of ``THRESHOLD_TABLE``.

    A raise is reported as an assertion failure, since the call site of
    ``_despawn_aged_tranches`` in ``tick`` carries no handler.
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
    """A threshold reader gating on exact type alone, run against `THRESHOLD_TABLE`."""
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
        """One ``THRESHOLD_TABLE`` row per test, so a failure names the shape."""
        assert despawn_threshold_days(_cfg_with(raw)) == expected

    @pytest.mark.parametrize(
        "raw", [NAN, INF, NINF, 10**400, "30", None, True, Decimal("30")]
    )
    def test_a_refused_setting_delists_nothing_on_a_real_sweep(self, raw):
        """`despawn_threshold_days` reading 0 leaves a 400-day-old tranche standing."""
        _check_off_delists_nothing(
            _Bot(fold=[fold_tr(400)], stack=[stack_tr(400)], days=raw)
        )

    @pytest.mark.parametrize("raw", [1e300, DESPAWN_MAX_DAYS])
    def test_an_absurd_threshold_delists_nothing_either(self, raw):
        """1e300 saturates to ``DESPAWN_MAX_DAYS`` and nothing is ever that old."""
        _check_off_delists_nothing(
            _Bot(fold=[fold_tr(400)], stack=[stack_tr(400)], days=raw)
        )


class TestTheSharedFiniteReader:
    """``as_finite_float`` is the conversion every other site here goes through."""

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
    """Each conversion site inside `_despawn_aged_tranches`, driven with a hostile.

    The verdict is read at the sweep returning, since its call site in
    ``tick`` carries no handler.
    """

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
        """A ``now`` ``as_finite_float`` refuses removes nothing and raises nothing."""
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
        """A surviving out-of-range `usd` leaves `_fold_queue_usd` finite."""
        bot = _Bot(fold=[fold_tr(400, usd=2.0), fold_tr(1, usd=10**400)], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert bot._fold_queue_usd == 0.0
        assert math.isfinite(bot._fold_queue_usd)

    def test_the_sibling_expression_really_does_raise(self):
        """`float(t.get("usd", 0) or 0)` raises where `as_finite_float` refuses."""
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
            f"default is {field.default!r}; a non-zero default would remove "
            f"standing records on the first tick after upgrade"
        )

    def test_zero_delists_nothing(self):
        _check_off_delists_nothing(
            _Bot(fold=[fold_tr(400)], stack=[stack_tr(400)], days=0)
        )

    def test_a_bot_built_with_defaults_delists_nothing(self):
        """A config from `make_bot_config` leaves `tranche_despawn_days` off."""
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
        """A stack tranche with `created_ts` and no `opened_ts` is unmeasurable."""
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
        """A pending stack tranche with an `order_id` owns a resting order and is kept.

        ``stack_kept_live_order`` counts it and ``stack_delisted`` stays 0.
        """
        bot = _Bot(stack=[stack_tr(40, status="pending", order_id="ORD-1")], days=7)
        report = bot._despawn_aged_tranches(now=NOW)
        assert len(bot._stack_tranches) == 1
        assert report["stack_kept_live_order"] == 1
        assert report["stack_delisted"] == 0

    def test_a_cancelled_visible_tranche_is_delisted(self):
        """A cancelled tranche with an ``order_id`` is still removed."""
        bot = _Bot(stack=[stack_tr(40, status="cancelled", order_id="ORD-1")], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert bot._stack_tranches == []


class TestTheStackHalfShipsDormant:
    """An empty ``_stack_tranches`` is a no-op and leaves the fold half working."""

    def test_an_empty_stack_ledger_is_a_no_op(self):
        bot = _Bot(fold=[fold_tr(40)], stack=[], days=7)
        report = bot._despawn_aged_tranches(now=NOW)
        assert report["stack_delisted"] == 0
        assert bot._stack_tranches == []

    def test_the_fold_side_still_delists_with_no_stack_ledger(self):
        """``fold_delisted`` still reads 1 with ``_stack_tranches`` empty."""
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
        """`_pending_wire_credits` is unchanged and the absorb-window warning fires."""
        bot = _Bot(fold=[fold_tr(40)], days=7, pending=342.26)
        bot._despawn_aged_tranches(now=NOW)
        assert bot._pending_wire_credits == pytest.approx(342.26)
        assert "absorb window" in bot._bus.text()

    def test_no_absorb_warning_when_tranches_remain(self):
        """No absorb-window warning while ``_fold_tranches`` still holds a record."""
        bot = _Bot(fold=[fold_tr(40), fold_tr(2)], days=7, pending=342.26)
        bot._despawn_aged_tranches(now=NOW)
        assert "absorb window" not in bot._bus.text()


class TestTheDerivedBookkeeping:
    def test_the_queue_total_is_recomputed(self):
        """``_fold_queue_usd`` is recomputed from the surviving ``_fold_tranches``."""
        bot = _Bot(fold=[fold_tr(40, usd=4.0), fold_tr(2, usd=1.5)], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert bot._fold_queue_usd == pytest.approx(1.5)

    def test_a_despawn_counts_as_discarded_not_closed(self):
        """A removal moves `_tranches_discarded_lifetime`.

        `_tranches_closed_lifetime` never moves.
        """
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
        """A stack removal moves `_stack_discarded` and leaves `_stack_created`."""
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
        """A sweep that removes nothing leaves both discard counters at 0."""
        bot = _Bot(fold=[fold_tr(2)], stack=[stack_tr(2)], days=7)
        _check_both_ledgers_reconcile(bot)
        assert bot._tranches_discarded_lifetime == 0
        assert bot._stack_discarded == 0

    def test_a_kept_live_order_is_not_counted_as_discarded(self):
        """A tranche in `stack_kept_live_order` is not in `_stack_discarded`."""
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
        """A ``status`` of ``filled`` leaves the record in ``_stack_tranches``."""
        bot = _Bot(stack=[stack_tr(2, status="filled")], days=7)
        bot._despawn_aged_tranches(now=NOW)
        assert len(bot._stack_tranches) == 1
        assert bot._stack_tranches[0]["status"] == "filled"
        _check_both_ledgers_reconcile(bot)

    def test_repeated_sweeps_accumulate_on_both_ledgers(self):
        """`_tranches_discarded_lifetime` and `_stack_discarded` are running totals."""
        bot = _Bot(
            fold=[fold_tr(40), fold_tr(30), fold_tr(2)],
            stack=[stack_tr(40), stack_tr(30, index=1), stack_tr(2, index=2)],
            days=7,
        )
        bot._despawn_aged_tranches(now=NOW)
        assert (bot._tranches_discarded_lifetime, bot._stack_discarded) == (2, 2)
        # `now` advanced 10 days, which ages the survivor past the threshold.
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
        """`tranche_despawn_days` survives `asdict` and a `make_bot_config` rebuild."""
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
        """`make_bot_config` without the keyword leaves `tranche_despawn_days` at 0."""
        cfg = make_bot_config(
            BotMode.SCRUMMING,
            exchange_id="coinbase",
            base_currency="USD",
            target_asset="RAVE",
            symbol="RAVE/USD",
        )
        assert cfg.tranche_despawn_days == 0

    def test_it_is_declared_on_the_dataclass_not_merely_set(self):
        """`tranche_despawn_days` is a declared `BotConfig` field `asdict` saves."""
        assert "tranche_despawn_days" in {f.name for f in dataclasses.fields(BotConfig)}

    def test_it_is_scrumming_only(self):
        """`make_bot_config` refuses `tranche_despawn_days` for `BotMode.EXTRACTOR`."""
        with pytest.raises(ValueError):
            make_bot_config(
                BotMode.EXTRACTOR,
                exchange_id="coinbase",
                base_currency="USD",
                tranche_despawn_days=45,
            )


class _ExportBot:
    """Only what ``export_scrumming_state`` reads off ``self``."""

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
    """Only what ``import_scrumming_state`` reads off ``self``."""

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
        # Bound as the real methods, so the restore runs the shipping code.
        self._fold_tranches = []
        self._pending_wire_ledger = []
        self._fold_queue_usd = 0.0
        self._add_wire_credits = types.MethodType(ScrummingBot._add_wire_credits, self)
        self._spread_wire_usd_over_fold_queue = types.MethodType(
            ScrummingBot._spread_wire_usd_over_fold_queue, self
        )
        self._refresh_fold_queue_total = types.MethodType(
            ScrummingBot._refresh_fold_queue_total, self
        )
        self._land_pending_wire_credits = types.MethodType(
            ScrummingBot._land_pending_wire_credits, self
        )


class TestTheStackDiscardCounterPersists:
    """`stack_discarded` survives `export_scrumming_state` and the restore."""

    def test_the_export_stub_works(self):
        """`_ExportBot` really does produce a state dict carrying `stack_created`."""
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
        """`_stack_created` minus `_stack_discarded` still matches the list."""
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
        """A state with `stack_discarded` removed no longer reconciles on restore."""
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
    """The only surface ``_create_settings_tab`` reads is ``config``."""

    def __init__(self, cfg):
        self.bot_id = "bot-despawn-0001"
        self.config = cfg


def _build_settings_tab(cfg=None, cls=None):
    """Build the real Settings tab by calling ``_create_settings_tab``.

    ``QDialog.__init__`` is called directly, which skips the construction
    path ``BotLiveSettingsDialog`` uses for a live bot and a bus.
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
    """`_tranche_despawn_days` is a `QSpinBox` in the tab tree with a labelled row.

    A widget built and never added to a layout has no parent and is not a
    child of the tab.
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
    """Move `_tranche_despawn_days`, apply, then read `despawn_threshold_days`."""
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
        """Seeding ``_tranche_despawn_days`` leaves ``_changes`` empty."""
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
        """A `tranche_despawn_days` of `nan` still builds the tab, with the box at 0."""
        cfg = _scrum_config()
        cfg.tranche_despawn_days = NAN
        dlg, tab = _build_settings_tab(cfg)
        _check_the_control_is_really_on_the_tab(dlg, tab)
        assert dlg._tranche_despawn_days.value() == 0

    def test_an_extractor_bot_still_gets_a_settings_tab(self):
        """`_create_settings_tab` builds `_tranche_despawn_days` for an extractor."""
        cfg = make_bot_config(
            BotMode.EXTRACTOR,
            exchange_id="coinbase",
            base_currency="USD",
            target_asset="*",
            symbol="",
        )
        dlg, tab = _build_settings_tab(cfg)
        _check_the_control_is_really_on_the_tab(dlg, tab)


# The Stack panel's fill ratio is `filled / created`, and `filled` counts
# only standing tranches.
class _GuiStackBot:
    """The surface ``_create_stack_tranches_tab`` reads."""

    def __init__(self, tranches, created, discarded):
        self.bot_id = "bot-despawn-0001"
        self.config = _scrum_config()
        self._stack_tranches = [dict(t) for t in tranches]
        self._stack_created = created
        self._stack_discarded = discarded

    @classmethod
    def after_a_real_sweep(cls, bot):
        """Seed `_GuiStackBot` from a `_Bot` that has run `_despawn_aged_tranches`."""
        return cls(bot._stack_tranches, bot._stack_created, bot._stack_discarded)


def _build_stack_tab(bot, cls=None):
    """Build the real Stack Tranches tab by calling ``_create_stack_tranches_tab``."""
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
    """Every summary row on the constructed tab, label text to field text."""
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
    """The Stack panel shows a discarded row matching ``_stack_discarded``.

    Standing rows plus discarded must equal the opened total.
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
    """A ``BotLiveSettingsDialog`` subclass whose Stack tab loses its discarded row."""
    from src.gui.bot_live_settings import BotLiveSettingsDialog

    class _Blinded(BotLiveSettingsDialog):
        def _create_stack_tranches_tab(self):
            tab = super()._create_stack_tranches_tab()
            _strip_discarded_row(tab)
            return tab

    return _Blinded


def _strip_discarded_row(tab) -> None:
    """Remove the discarded row from a built ``QFormLayout``."""
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
    """A `_Bot` with four stack tranches, two removed by `_despawn_aged_tranches`."""
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
        """The fill ratio row still reads ``25.0%  (1/4)`` after a sweep."""
        gui_bot = _GuiStackBot.after_a_real_sweep(_swept_stack_bot())
        _dlg, tab = _build_stack_tab(gui_bot)
        assert _row_matching(_panel_rows(tab), "fill ratio") == "25.0%  (1/4)"

    def test_a_bot_that_was_never_swept_shows_no_extra_row(self):
        """A ``_GuiStackBot`` with ``discarded=0`` shows no discarded row."""
        gui_bot = _GuiStackBot([stack_tr(2)], created=1, discarded=0)
        _dlg, tab = _build_stack_tab(gui_bot)
        assert _row_matching(_panel_rows(tab), "discarded") is None

    def test_an_empty_stack_ledger_still_builds(self):
        gui_bot = _GuiStackBot([], created=0, discarded=0)
        _dlg, tab = _build_stack_tab(gui_bot)
        assert _row_matching(_panel_rows(tab), "opened") == "0"


class _TickSentinel(Exception):
    """Raised from the stubbed sweep, which stops ``tick`` at the call site."""


class _Ticker:
    last = 100.0


def _tickable_bot(days=7):
    """A real ``ScrummingBot`` carrying only what ``tick`` reads before the sweep.

    Every other name the prologue reaches sits inside a ``try``.
    """
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
    bot._manual_fire_pending = False  # read by the read-rate elif branch
    bot._reconcile_tick_counter = 0
    bot._reconcile_interval = 0  # skips the periodic reconcile
    bot._last_price = 100.0
    # `tick_interval` is a read-only property; `scrum_read_rate_min` at 0
    # short-circuits before anything reads it.
    bot.stats = type("S", (), {"current_price": 0.0})()

    async def _get_ticker(_symbol):
        return _Ticker()

    bot._get_ticker = _get_ticker
    return bot


def _tick_reaches_the_sweep(bot) -> list:
    """Run the real ``tick`` and return the ``now`` arguments the sweep saw.

    The stub raises ``_TickSentinel``, which a call site inside a ``try``
    would swallow.
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
        """``_despawn_aged_tranches`` is a plain method, not a coroutine."""
        assert not inspect.iscoroutinefunction(ScrummingBot._despawn_aged_tranches)


#: (label, value). Each shape is reachable from a JSON state file or a
#: hand-edited config.
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
    """``as_finite_float``, the conversion the other sites share."""
    as_finite_float(raw)


def _site_02_threshold_reader(raw):
    """``despawn_threshold_days`` on a config field."""
    despawn_threshold_days(_cfg_with(raw))


def _site_03_fold_timestamp(raw):
    """``_tranche_age_seconds`` on ``created_ts``."""
    bot = _Bot(fold=[fold_tr(400)], days=7)
    bot._fold_tranches[0]["created_ts"] = raw
    bot._despawn_aged_tranches(now=NOW)


def _site_04_stack_timestamp(raw):
    """``_tranche_age_seconds`` on ``opened_ts``."""
    bot = _Bot(stack=[stack_tr(400)], days=7)
    bot._stack_tranches[0]["opened_ts"] = raw
    bot._despawn_aged_tranches(now=NOW)


def _site_05_injected_now(raw):
    """The ``now`` argument of ``_despawn_aged_tranches``."""
    _Bot(fold=[fold_tr(400)], days=7)._despawn_aged_tranches(now=raw)


def _site_06_cutoff_arithmetic(raw):
    """The cutoff multiplication ``DESPAWN_MAX_DAYS`` keeps in range."""
    _Bot(fold=[fold_tr(400)], stack=[stack_tr(400)], days=raw)._despawn_aged_tranches(
        now=NOW
    )


def _site_07_delisted_usd_total(raw):
    """The ``usd_delisted`` total, summed over removed tranches."""
    _Bot(fold=[fold_tr(400, usd=raw)], days=7)._despawn_aged_tranches(now=NOW)


def _site_08_queue_total_recompute(raw):
    """The ``_fold_queue_usd`` recompute over surviving tranches."""
    _Bot(fold=[fold_tr(400), fold_tr(1, usd=raw)], days=7)._despawn_aged_tranches(
        now=NOW
    )


def _site_09_fold_discard_counter(raw):
    """``_tranches_discarded_lifetime`` read back from state inside the sweep."""
    bot = _Bot(fold=[fold_tr(400)], days=7)
    bot._tranches_discarded_lifetime = raw
    bot._despawn_aged_tranches(now=NOW)


def _site_10_stack_discard_counter(raw):
    """``_stack_discarded`` read back from state inside the sweep."""
    bot = _Bot(stack=[stack_tr(400)], days=7)
    bot._stack_discarded = raw
    bot._despawn_aged_tranches(now=NOW)


def _site_11_parked_wire_credit(raw):
    """``_pending_wire_credits`` and the dollar format the warning applies to it."""
    _Bot(fold=[fold_tr(400)], days=7, pending=raw)._despawn_aged_tranches(now=NOW)


def _site_12_state_export(raw):
    """``stack_discarded`` on the way out through ``export_scrumming_state``."""
    bot = _ExportBot()
    bot._stack_discarded = raw
    bot.export_scrumming_state()


def _site_13_state_restore(raw):
    """``stack_discarded`` on the way in through ``import_scrumming_state``."""
    _RestoreBot().import_scrumming_state({"stack_discarded": raw})


def _site_14_settings_spinbox_seed(raw):
    """The ``_tranche_despawn_days`` seed while ``_create_settings_tab`` runs."""
    cfg = _scrum_config()
    cfg.tranche_despawn_days = raw
    _build_settings_tab(cfg)


def _site_15_stack_panel_discarded_row(raw):
    """The discarded-row read while ``_create_stack_tranches_tab`` runs."""
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
    """``driver`` returns on ``raw`` and does not raise."""
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


def _bare_int_counter(raw):
    """A bare ``int()`` on the discard counter, standing in for ``as_finite_float``."""
    return int(raw or 0) + 1


class TestThePlantedConversionDefect:
    """``_bare_int_counter`` is judged by the same oracle ``CONVERSION_SITES`` are."""

    #: The rows `_bare_int_counter` raises on. `"30"`, `b"30"` and
    #: `Decimal("30")` are not among them; it converts those.
    RAISING_ROWS = [
        (NAN, ValueError),
        (INF, OverflowError),
        (NINF, OverflowError),
        ([1], TypeError),
        (_HasFloat(), TypeError),
    ]

    @pytest.mark.parametrize("raw,exc", RAISING_ROWS)
    def test_the_bare_int_really_does_raise(self, raw, exc):
        """`_bare_int_counter` raises the named class on each `RAISING_ROWS` value."""
        with pytest.raises(exc):
            _bare_int_counter(raw)

    @pytest.mark.parametrize("raw", ["30", b"30", Decimal("30")])
    def test_the_bare_int_launders_the_rows_it_does_not_raise_on(self, raw):
        """``_bare_int_counter`` converts a numeric string, bytes and a ``Decimal``.

        ``as_finite_float`` returns None for all three.
        """
        assert _bare_int_counter(raw) == 31
        assert as_finite_float(raw) is None

    @pytest.mark.parametrize("raw", [r for r, _ in RAISING_ROWS])
    def test_the_oracle_goes_red_on_the_bare_int(self, raw):
        """``_check_a_site_refuses_by_value`` goes red on ``_bare_int_counter``."""
        with pytest.raises(AssertionError, match="raised"):
            _check_a_site_refuses_by_value(_bare_int_counter, "the bare int()", raw)

    @pytest.mark.parametrize("raw", [NAN, INF, NINF, "30", [1], b"30"])
    def test_the_guarded_counter_survives_the_same_rows(self, raw):
        """The real site takes the same values without raising.

        `_tranches_discarded_lifetime` still advances by the removed count.
        """
        bot = _Bot(fold=[fold_tr(400)], days=7)
        bot._tranches_discarded_lifetime = raw
        report = bot._despawn_aged_tranches(now=NOW)
        assert report["fold_delisted"] == 1
        assert bot._tranches_discarded_lifetime == 1


def _detach(dlg) -> None:
    """Detach ``_tranche_despawn_days`` from its parent, leaving it in no layout."""
    dlg._tranche_despawn_days.setParent(None)


def _disconnect(dlg) -> None:
    """Disconnect ``valueChanged`` on ``_tranche_despawn_days``."""
    dlg._tranche_despawn_days.valueChanged.disconnect()


def _rewire_to_undeclared_field(dlg) -> None:
    """Record the change under a key `BotConfig` does not declare."""
    dlg._tranche_despawn_days.valueChanged.disconnect()
    dlg._tranche_despawn_days.valueChanged.connect(
        lambda v: dlg._mark_changed("tranche_despawn_days_NOT_A_FIELD", v)
    )


def _blinded_dialog(blind):
    """A `BotLiveSettingsDialog` subclass whose Settings tab is broken by `blind`."""
    from src.gui.bot_live_settings import BotLiveSettingsDialog

    class _Blinded(BotLiveSettingsDialog):
        def _create_settings_tab(self):
            tab = super()._create_settings_tab()
            blind(self)
            return tab

    return _Blinded


class _BlindNeverDelists(_Bot):
    """A sweep that runs and removes nothing."""

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
    """A sweep using ``>`` where ``_despawn_aged_tranches`` uses ``>=``."""

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
    """A sweep reading a missing ``created_ts`` as the epoch."""

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
    """A sweep gating ``created_ts`` on ``isinstance``, which admits ``True`` as 1.0."""

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
    """A sweep that touches ``_fold_tranches`` and never ``_stack_tranches``."""

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
    """The real sweep with the ``_tranches_discarded_lifetime`` increment undone."""

    def _despawn_aged_tranches(self, now=None):
        before = self._tranches_discarded_lifetime
        report = _Bot._despawn_aged_tranches(self, now=now)
        self._tranches_discarded_lifetime = before
        return report


class _BlindStackDiscardNotCounted(_Bot):
    """The real sweep with the ``_stack_discarded`` increment undone."""

    def _despawn_aged_tranches(self, now=None):
        before = self._stack_discarded
        report = _Bot._despawn_aged_tranches(self, now=now)
        self._stack_discarded = before
        return report


class _BlindDiscardCountedAsClosed(_Bot):
    """The real sweep with the removal booked to ``_tranches_closed_lifetime``.

    The ledger still reconciles under it.
    """

    def _despawn_aged_tranches(self, now=None):
        before = self._tranches_discarded_lifetime
        report = _Bot._despawn_aged_tranches(self, now=now)
        moved = self._tranches_discarded_lifetime - before
        self._tranches_discarded_lifetime = before
        self._tranches_closed_lifetime += moved
        return report


class _SpyThatTouchesMoney(_Spy):
    """A sweep that reads ``_current_holdings`` and ``_main_lots`` on its way past."""

    def _despawn_aged_tranches(self, now=None):
        _ = self._current_holdings
        _ = self._main_lots
        return _Bot._despawn_aged_tranches(self, now=now)


class TestPlantedFailures:
    """Each `_check_*` oracle is observed failing on a broken sweep or a broken tab."""

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
        """`_BlindIsinstanceTimestamp` removes a record whose `created_ts` is `True`."""
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
        """`_BlindStackDiscardNotCounted` fails the stack half of the ledger check."""
        with pytest.raises(AssertionError, match="STACK ledger"):
            _check_both_ledgers_reconcile(
                _BlindStackDiscardNotCounted(
                    fold=[fold_tr(40), fold_tr(2)],
                    stack=[stack_tr(40), stack_tr(2, index=1)],
                    days=7,
                )
            )

    def test_each_break_is_caught_on_its_OWN_side(self):
        """`_fold_ledger` and `_stack_ledger` each balance under the other break."""
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
        """`_BlindDiscardCountedAsClosed` balances the ledger on the wrong counter."""
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
        """``_Spy`` records ``_fold_tranches`` and ``config`` during a real sweep."""
        spy = _Spy(fold=[fold_tr(40)], days=7)
        spy._despawn_aged_tranches(now=NOW)
        reached = set(object.__getattribute__(spy, "reached"))
        assert "_fold_tranches" in reached
        assert "config" in reached

    def test_the_value_table_catches_the_old_type_only_gate(self):
        """``_type_only_gate`` fails ``_check_threshold_table``."""
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
        """``_type_only_gate`` raises the named class on each non-finite row."""
        with pytest.raises(exc):
            _type_only_gate(_cfg_with(raw))

    @pytest.mark.parametrize("raw", [NAN, INF, NINF])
    def test_the_real_reader_survives_the_same_rows(self, raw):
        """``despawn_threshold_days`` returns 0 on the same three rows."""
        assert despawn_threshold_days(_cfg_with(raw)) == 0

    def test_a_never_laid_out_control_fails_the_widget_check(self):
        """A detached `_tranche_despawn_days` fails the laid-out-control check."""
        dlg, tab = _build_settings_tab(cls=_blinded_dialog(_detach))
        with pytest.raises(AssertionError):
            _check_the_control_is_really_on_the_tab(dlg, tab)

    def test_a_control_wired_to_nothing_fails_the_consumer_check(self):
        """A disconnected `_tranche_despawn_days` fails the consumer check."""
        dlg, _tab = _build_settings_tab(cls=_blinded_dialog(_disconnect))
        with pytest.raises(AssertionError):
            _check_a_change_reaches_the_consumer(dlg)

    def test_a_field_missing_from_the_dataclass_fails_the_consumer_check(self):
        """A change keyed off `BotConfig` never reaches `despawn_threshold_days`."""
        dlg, _tab = _build_settings_tab(
            cls=_blinded_dialog(_rewire_to_undeclared_field)
        )
        with pytest.raises(AssertionError):
            _check_a_change_reaches_the_consumer(dlg)

    def test_a_zero_discard_counter_fails_the_stack_panel_check(self):
        """A swept ledger reported with ``discarded=0`` shows no discarded row."""
        swept = _swept_stack_bot()
        gui_bot = _GuiStackBot(swept._stack_tranches, swept._stack_created, discarded=0)
        _dlg, tab = _build_stack_tab(gui_bot)
        with pytest.raises(AssertionError, match="no discarded row"):
            _check_the_stack_panel_accounts_for_discards(gui_bot, tab)

    def test_a_stripped_row_fails_the_stack_panel_check(self):
        """A correct ledger with the row stripped from the panel still goes red."""
        gui_bot = _GuiStackBot.after_a_real_sweep(_swept_stack_bot())
        _dlg, tab = _build_stack_tab(gui_bot, cls=_blinded_stack_dialog())
        with pytest.raises(AssertionError, match="no discarded row"):
            _check_the_stack_panel_accounts_for_discards(gui_bot, tab)

    def test_a_miscounted_row_fails_the_stack_panel_check(self):
        """A discarded row of 99 fails the standing-plus-discarded arithmetic."""
        swept = _swept_stack_bot()
        gui_bot = _GuiStackBot(
            swept._stack_tranches, swept._stack_created, discarded=99
        )
        _dlg, tab = _build_stack_tab(gui_bot)
        with pytest.raises(AssertionError, match="does not add up"):
            _check_the_stack_panel_accounts_for_discards(gui_bot, tab)

    def test_an_unwired_tick_fails_the_wiring_check(self):
        """A `tick` that never calls the sweep makes `_tick_reaches_the_sweep` red."""
        bot = _tickable_bot()

        async def _tick_without_the_sweep():
            return None

        bot.tick = _tick_without_the_sweep
        with pytest.raises(pytest.fail.Exception):
            _tick_reaches_the_sweep(bot)
