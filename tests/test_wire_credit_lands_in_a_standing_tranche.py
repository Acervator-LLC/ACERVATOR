"""A parked wire credit lands the moment a fold tranche exists.

Issue #133 unit 11. The operator saw the Clear Wire Credits button
carrying a dollar figure while fold tranches were standing, and read
that as a credit that had failed to land.

WHAT THE TWO STATES MEAN
========================
``apply_wire_income`` has exactly two destinations for incoming Smart
Wire USD:

* fold queue NON-EMPTY -- case 1 spreads the money evenly over the
  standing tranches and ``_pending_wire_credits`` never moves;
* fold queue EMPTY -- case 2 parks the money in
  ``_pending_wire_credits`` with a ledger entry.

So the parked bucket can only be filled while the queue holds nothing.
A parked pool standing BESIDE an open tranche is therefore never a
credit that arrived that way. It is a credit that was parked correctly
and then missed its destination when a tranche opened.

HOW IT MISSED
=============
Three build loops create fold tranches: the SCRUM sell in ``tick``, the
DIST sell in ``tick``, and ``_execute_manual_rebalance`` -- which serves
Manual Fire, Wire Stack Fire and Max Cartridge Fire. Only the SCRUM loop
drained the bucket, and only under ``_tranche_count_before == 0``. A
DIST or manual sell that opened the first tranche left the pool parked,
and from that point every later wire income took case 1 while the pool
itself stayed behind -- until the queue emptied again and a SCRUM fired.

Measured by driving ``_execute_manual_rebalance`` on the shipping code:
$5.0000 parked, zero tranches before, one $50.0000 tranche after, and
``_pending_wire_credits`` still $5.0000 with no ``wire_credits`` key on
the tranche the sell had just built.

THE REPAIR
==========
``_land_pending_wire_credits`` is called after every build loop and on
state restore. It spreads the pool with
``_spread_wire_usd_over_fold_queue``, the same routine
``apply_wire_income`` case 1 now uses, so the same money reaches the
same place whether it arrives with tranches standing or lands after.

It runs AFTER ``_top_up_remnant_fold_tranches`` at each site. That merge
blends ``ref`` from ``usd / ref`` per record, and wire USD carries no
units, so money added before the merge would skew the blended rebuy
threshold.

THE GROWTH CAP IS NOT TOUCHED, AND IS CONFIRMED HERE RATHER THAN
ASSUMED. ``TestTheGrowthCapStillBounds`` drives
``_plan_fold_consumption`` and ``_settle_fold_plan`` and shows a landed
credit makes a tranche survive a cycle part-consumed instead of lifting
what the cycle spends.

EVERY CLAIM HERE CARRIES A CONTROL
==================================
The end-to-end tests assert money moved before they assert where it
went, so a fire that bought nothing cannot pass. The blinded variants
re-run the same checks against the pre-repair behaviour and are
required to go red.
"""

from __future__ import annotations

import ast
import asyncio
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

PRICE = 0.5
PARKED = 5.0
MONEY_TOL_USD = 1e-9

SCRUMMING_BOT_SRC = (REPO / "src" / "trading" / "scrumming_bot.py").read_text(
    encoding="utf-8"
)


# -- stubs -----------------------------------------------------------


class _Bus:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def emit(self, topic, **payload):
        self.messages.append(f"{topic}|{payload.get('message', '')}")

    def logs(self) -> list[str]:
        return [m.split("|", 1)[1] for m in self.messages if m.startswith("bot.log|")]


class _Stats:
    def __init__(self) -> None:
        self.total_trades = 0
        self.total_folded_usd = 0.0
        self.total_scrummed_usd = 0.0
        self.trade_volume = 0.0


class _Config:
    def __init__(self, scrum_fold_pct: int = 100) -> None:
        self.symbol = "CHIP/USD"
        self.target_asset = "CHIP"
        self.exchange_id = "coinbase"
        self.scrumming_interval_pct = 1.0
        self.trading_fee_pct = 0.6
        self.max_target_growth_pct = 0.0
        self.profit_folding_active = True
        self.scrum_fold_pct = scrum_fold_pct
        self.wire_inflow_stack_pct = 0.0


class _Order:
    id = "u11"
    filled = 0.0
    average = 0.0


class _Ticker:
    def __init__(self, last: float) -> None:
        self.last = last


def _tranche(usd: float, units: float, ref: float, ibp: float = 0.4) -> dict:
    return {
        "usd": usd,
        "units": units,
        "ref": ref,
        "initial_buy_price": ibp,
        "created_ts": 1.0,
    }


def _bot(parked: float = 0.0, tranches: tuple = (), scrum_fold_pct: int = 100) -> Any:
    """A bot carrying only what the wire routing and the sell path read.

    Every wire-routing method is the REAL one, so the landing, the
    spread and the bounded provenance append run exactly as they do in
    production.
    """
    bot: Any = object.__new__(ScrummingBot)
    bot.bot_id = "u11-bot"
    bot._bus = _Bus()
    bot.config = _Config(scrum_fold_pct)
    bot.stats = _Stats()
    bot._fold_tranches = [dict(t) for t in tranches]
    bot._main_lots = [{"units": 300.0, "initial_buy_price": 0.4}]
    bot._current_holdings = 300.0
    bot._target_balance = 100.0
    bot._anchor_target_balance = 100.0
    bot._quote_to_usd = 1.0
    bot._manual_fire_pending = True
    bot._fold_queue_usd = sum(float(t["usd"]) for t in tranches)
    bot._fold_cycle_cap_consumed = 0.0
    bot._standing_surplus_usd = 0.0
    bot._retained_this_cycle_usd = 0.0
    bot._fold_accumulator = 0.0
    bot._target_grow_last_side = None
    bot._tranches_closed_lifetime = 0
    bot._tranches_created_lifetime = 0
    bot._tranches_malformed_dropped = 0
    bot._scrum_sells_lifetime = 0
    bot._pending_wire_credits = float(parked)
    bot._pending_wire_ledger = (
        [{"ts": 1.0, "source": "peer-bot", "usd": float(parked), "ref": "w1"}]
        if parked
        else []
    )
    bot._pending_stack_buy_usd = 0.0
    bot._smart_wire_mgr = None
    bot._last_trade_side = None
    bot._last_trade_price = 0.0
    bot._last_bb = None
    bot.placed = []

    async def _place(**kwargs):
        bot.placed.append(dict(kwargs))
        return _Order()

    async def _settled(order, symbol_, requested, tick_price):
        del order, symbol_, tick_price
        return requested, PRICE, True

    async def _balance(currency):
        free = 300.0 if currency == "CHIP" else 1_000_000.0
        return type("B", (), {"total": free, "free": free, "absent": False})()

    async def _refresh():
        return 1.0

    def _ignore(*args, **kwargs):
        del args, kwargs

    def _zero(*args, **kwargs):
        del args, kwargs
        return 0.0

    bot._refresh_quote_to_usd = _refresh
    bot.guarded_place_order = _place
    bot._settled_fill = _settled
    bot._get_balance = _balance
    bot._emit_voting_panel_snapshot_at_fire = _ignore
    bot._emit_gate_decision_at_fire = _ignore
    bot._reset_opposing_hysteresis_after_fill = _ignore
    bot._route_scrum_proceeds_via_wires = _zero
    bot.note_scrum_retention_usd = _ignore
    return bot


def _queue_usd(bot) -> float:
    return sum(float(t.get("usd", 0) or 0) for t in bot._fold_tranches)


def _recorded_usd(bot) -> float:
    """Wire provenance the tranches carry, detail plus rolled aggregate."""
    total = 0.0
    for t in bot._fold_tranches:
        total += sum(float(e.get("usd", 0.0) or 0.0) for e in t.get("wire_credits", []))
        rolled = t.get("wire_credits_rolled") or {}
        total += float(rolled.get("total_usd", 0.0) or 0.0)
    return total


def _blind(bot) -> None:
    """Restore the pre-repair behaviour: the build loops do not land."""
    bot._land_pending_wire_credits = lambda *_a, **_k: 0.0


# -- the vacuous-pass control ----------------------------------------


def _assert_the_credit_arrived(bot, parked: float) -> None:
    """A credit that never arrived can never land wrongly."""
    assert (
        abs(float(bot._pending_wire_credits) - parked) <= MONEY_TOL_USD
    ), f"the credit did not arrive: parked reads ${bot._pending_wire_credits}"
    assert bot._pending_wire_ledger, "the credit arrived with no ledger entry"


def _assert_the_sell_moved_money(bot, before_queue: float) -> None:
    """A sell that placed no order leaves every landing claim vacuous."""
    assert len(bot.placed) == 1, f"expected one order, saw {bot.placed}"
    assert bot.placed[0]["side"].value == "sell"
    assert bot._fold_tranches, "the sell opened no tranche"
    assert (
        _queue_usd(bot) > before_queue + MONEY_TOL_USD
    ), "the queue did not grow; the sell was a no-op"


# -- the arrival itself ----------------------------------------------


class TestTheCreditParksOnlyWithAnEmptyQueue:
    """The premise the whole unit rests on, driven not assumed."""

    def test_income_with_no_tranches_parks(self):
        bot = _bot()
        report = ScrummingBot.apply_wire_income(bot, 5.0, "peer-bot", "ref-1")
        assert report["mode"] == "pending"
        assert abs(bot._pending_wire_credits - 5.0) <= MONEY_TOL_USD
        assert len(bot._pending_wire_ledger) == 1

    def test_income_with_tranches_standing_never_parks(self):
        bot = _bot(tranches=(_tranche(10.0, 20.0, 0.6), _tranche(30.0, 60.0, 0.7)))
        report = ScrummingBot.apply_wire_income(bot, 5.0, "peer-bot", "ref-1")
        assert report["mode"] == "distributed"
        assert bot._pending_wire_credits == 0.0
        assert abs(_queue_usd(bot) - 45.0) <= MONEY_TOL_USD
        assert abs(bot._fold_tranches[0]["usd"] - 12.5) <= MONEY_TOL_USD
        assert abs(bot._fold_tranches[1]["usd"] - 32.5) <= MONEY_TOL_USD

    def test_so_parked_beside_a_tranche_is_never_how_it_arrived(self):
        """No call to ``apply_wire_income`` can produce that pairing."""
        bot = _bot()
        ScrummingBot.apply_wire_income(bot, 5.0, "peer-bot", "ref-1")
        assert bot._pending_wire_credits > 0 and not bot._fold_tranches
        bot._fold_tranches.append(_tranche(10.0, 20.0, 0.6))
        ScrummingBot.apply_wire_income(bot, 3.0, "peer-bot", "ref-2")
        assert (
            abs(bot._pending_wire_credits - 5.0) <= MONEY_TOL_USD
        ), "the second income must distribute, not add to the parked pool"
        assert abs(bot._fold_tranches[0]["usd"] - 13.0) <= MONEY_TOL_USD


# -- the landing, on the real method ---------------------------------


class TestTheLanding:
    def test_the_whole_pool_reaches_the_queue(self):
        bot = _bot(parked=PARKED, tranches=(_tranche(10.0, 20.0, 0.6),))
        _assert_the_credit_arrived(bot, PARKED)
        before = _queue_usd(bot)

        landed = ScrummingBot._land_pending_wire_credits(bot)

        assert abs(landed - PARKED) <= MONEY_TOL_USD
        assert abs(_queue_usd(bot) - (before + PARKED)) <= MONEY_TOL_USD
        assert bot._pending_wire_credits == 0.0
        assert bot._pending_wire_ledger == []

    def test_the_spread_is_even(self):
        bot = _bot(
            parked=9.0,
            tranches=(
                _tranche(10.0, 20.0, 0.6),
                _tranche(20.0, 40.0, 0.7),
                _tranche(30.0, 60.0, 0.8),
            ),
        )
        ScrummingBot._land_pending_wire_credits(bot)
        assert [round(t["usd"], 9) for t in bot._fold_tranches] == [13.0, 23.0, 33.0]

    def test_the_aggregate_matches_the_rows(self):
        """``_fold_queue_usd`` is the scalar the panel and the fold gate
        read. It must equal the rows after a landing."""
        bot = _bot(parked=PARKED, tranches=(_tranche(10.0, 20.0, 0.6),))
        ScrummingBot._land_pending_wire_credits(bot)
        assert abs(bot._fold_queue_usd - _queue_usd(bot)) <= MONEY_TOL_USD

    def test_provenance_follows_the_money(self):
        bot = _bot(parked=PARKED, tranches=(_tranche(10.0, 20.0, 0.6),))
        ScrummingBot._land_pending_wire_credits(bot)
        assert abs(_recorded_usd(bot) - PARKED) <= MONEY_TOL_USD
        assert bot._fold_tranches[0]["wire_credits"][0]["source"] == "peer-bot"

    def test_provenance_splits_with_the_money(self):
        bot = _bot(
            parked=6.0,
            tranches=(_tranche(10.0, 20.0, 0.6), _tranche(10.0, 20.0, 0.7)),
        )
        ScrummingBot._land_pending_wire_credits(bot)
        for t in bot._fold_tranches:
            recorded = sum(float(e["usd"]) for e in t["wire_credits"])
            assert abs(recorded - 3.0) <= MONEY_TOL_USD
        assert abs(_recorded_usd(bot) - 6.0) <= MONEY_TOL_USD

    def test_units_are_untouched(self):
        """The landing adds USD and no units. Anything reading
        ``usd / units`` must see the same divisor it saw before."""
        bot = _bot(parked=PARKED, tranches=(_tranche(10.0, 20.0, 0.6),))
        ScrummingBot._land_pending_wire_credits(bot)
        assert bot._fold_tranches[0]["units"] == 20.0

    def test_an_empty_pool_is_a_no_op(self):
        bot = _bot(tranches=(_tranche(10.0, 20.0, 0.6),))
        assert ScrummingBot._land_pending_wire_credits(bot) == 0.0
        assert bot._fold_tranches[0]["usd"] == 10.0
        assert "wire_credits" not in bot._fold_tranches[0]

    def test_an_empty_queue_keeps_the_pool_parked(self):
        """There is nothing to land into, so the money must stay. A
        landing that cleared the pool here would destroy it."""
        bot = _bot(parked=PARKED)
        assert ScrummingBot._land_pending_wire_credits(bot) == 0.0
        assert abs(bot._pending_wire_credits - PARKED) <= MONEY_TOL_USD
        assert len(bot._pending_wire_ledger) == 1

    def test_the_landing_is_idempotent(self):
        bot = _bot(parked=PARKED, tranches=(_tranche(10.0, 20.0, 0.6),))
        ScrummingBot._land_pending_wire_credits(bot)
        after_first = _queue_usd(bot)
        assert ScrummingBot._land_pending_wire_credits(bot) == 0.0
        assert abs(_queue_usd(bot) - after_first) <= MONEY_TOL_USD

    def test_the_operator_log_names_the_money_and_the_rows(self):
        bot = _bot(parked=PARKED, tranches=(_tranche(10.0, 20.0, 0.6),))
        ScrummingBot._land_pending_wire_credits(bot)
        line = [m for m in bot._bus.logs() if m.startswith("WIRE LANDED:")]
        assert len(line) == 1, bot._bus.logs()
        assert "$5.0000" in line[0]
        assert "1 standing tranche(s)" in line[0]


class TestConservationAcrossTheDomain:
    """Rule 2 of two-sided control: close the numeric domain.

    Pools span six decades against queues of one to eight tranches. The
    queue must grow by exactly the pool, every time.
    """

    @pytest.mark.parametrize("pool", [0.01, 0.13, 1.0, 12.34, 343.68, 1000.0, 99999.99])
    @pytest.mark.parametrize("rows", [1, 2, 3, 5, 8])
    def test_the_queue_grows_by_exactly_the_pool(self, pool, rows):
        bot = _bot(
            parked=pool,
            tranches=tuple(
                _tranche(7.5 + i, 15.0 + i, 0.6 + i / 100.0) for i in range(rows)
            ),
        )
        before = _queue_usd(bot)
        landed = ScrummingBot._land_pending_wire_credits(bot)
        assert abs(landed - pool) <= MONEY_TOL_USD
        assert abs(_queue_usd(bot) - (before + pool)) <= MONEY_TOL_USD * max(rows, 1)
        assert bot._pending_wire_credits == 0.0
        assert _recorded_usd(bot) <= _queue_usd(bot) + MONEY_TOL_USD


# -- end to end, on the real sell path -------------------------------


class TestAManualSellLandsTheCredit:
    """``_execute_manual_rebalance`` -- Manual Fire, Wire Stack Fire and
    Max Cartridge Fire. The build loop that opened the first tranche and
    left the pool behind."""

    @pytest.mark.parametrize("intent", ["manual_button", "wire_stack", "max_cartridge"])
    def test_the_first_tranche_a_manual_sell_opens_carries_the_credit(self, intent):
        bot = _bot(parked=PARKED)
        _assert_the_credit_arrived(bot, PARKED)

        asyncio.run(bot._execute_manual_rebalance(_Ticker(PRICE), intent))

        _assert_the_sell_moved_money(bot, before_queue=0.0)
        assert bot._pending_wire_credits == 0.0, (
            f"${bot._pending_wire_credits:.4f} of wire credit is still parked "
            f"beside {len(bot._fold_tranches)} standing tranche(s)"
        )
        assert abs(_queue_usd(bot) - (50.0 + PARKED)) <= MONEY_TOL_USD
        assert abs(_recorded_usd(bot) - PARKED) <= MONEY_TOL_USD

    def test_a_manual_sell_beside_a_standing_tranche_lands_it_too(self):
        bot = _bot(parked=PARKED, tranches=(_tranche(10.0, 20.0, 0.6),))
        before = _queue_usd(bot)

        asyncio.run(bot._execute_manual_rebalance(_Ticker(PRICE), "manual_button"))

        _assert_the_sell_moved_money(bot, before_queue=before)
        assert bot._pending_wire_credits == 0.0
        assert abs(_queue_usd(bot) - (before + 50.0 + PARKED)) <= MONEY_TOL_USD

    def test_a_sell_with_no_pool_leaves_the_queue_pure(self):
        bot = _bot()
        asyncio.run(bot._execute_manual_rebalance(_Ticker(PRICE), "manual_button"))
        _assert_the_sell_moved_money(bot, before_queue=0.0)
        assert abs(_queue_usd(bot) - 50.0) <= MONEY_TOL_USD
        assert _recorded_usd(bot) == 0.0

    def test_the_landing_is_exempt_from_the_fold_ratio(self):
        """Wired-in money is not this sell's proceeds, so
        ``scrum_fold_pct`` has no authority over it. The landing runs
        after the ratio, so the pool arrives whole."""
        bot = _bot(parked=PARKED, scrum_fold_pct=50)
        asyncio.run(bot._execute_manual_rebalance(_Ticker(PRICE), "manual_button"))
        _assert_the_sell_moved_money(bot, before_queue=0.0)
        assert abs(_queue_usd(bot) - (25.0 + PARKED)) <= MONEY_TOL_USD, (
            f"queue holds ${_queue_usd(bot):.4f}; expected $25.0000 of folded "
            f"proceeds plus the whole ${PARKED:.4f} wire credit"
        )


class TestTheBlindedSellFailsTheSameChecks:
    """The controls. Each re-runs a check above with the landing removed
    and is required to go red naming the real problem."""

    @pytest.mark.parametrize("intent", ["manual_button", "wire_stack", "max_cartridge"])
    def test_a_manual_sell_that_does_not_land_is_caught(self, intent):
        bot = _bot(parked=PARKED)
        _blind(bot)
        asyncio.run(bot._execute_manual_rebalance(_Ticker(PRICE), intent))
        _assert_the_sell_moved_money(bot, before_queue=0.0)
        with pytest.raises(AssertionError, match="still parked beside"):
            assert bot._pending_wire_credits == 0.0, (
                f"${bot._pending_wire_credits:.4f} of wire credit is still "
                f"parked beside {len(bot._fold_tranches)} standing tranche(s)"
            )

    def test_the_blinded_queue_is_short_by_exactly_the_pool(self):
        bot = _bot(parked=PARKED)
        _blind(bot)
        asyncio.run(bot._execute_manual_rebalance(_Ticker(PRICE), "manual_button"))
        assert abs(_queue_usd(bot) - 50.0) <= MONEY_TOL_USD
        assert abs(_queue_usd(bot) - (50.0 + PARKED)) > PARKED / 2

    def test_the_blinded_tranche_carries_no_provenance(self):
        bot = _bot(parked=PARKED)
        _blind(bot)
        asyncio.run(bot._execute_manual_rebalance(_Ticker(PRICE), "manual_button"))
        assert _recorded_usd(bot) == 0.0


# -- the two figures the panel reads ---------------------------------


class TestThePanelFiguresAgree:
    """``bot_live_settings`` reads ``_pending_wire_credits`` for the
    Clear Wire Credits button and ``_fold_tranches`` for the queue. The
    operator's report is the pairing of a populated button with a
    populated table."""

    @staticmethod
    def _panel_reads(bot) -> dict:
        parked = float(getattr(bot, "_pending_wire_credits", 0.0) or 0.0)
        tranches = list(getattr(bot, "_fold_tranches", []) or [])
        return {
            "wire_button_label": (
                f"Clear ${parked:,.2f} Wire Credits"
                if parked > 1e-9
                else "Clear Wire Credits"
            ),
            "wire_button_enabled": parked > 1e-9,
            "open_tranches": len(tranches),
            "queue_usd": sum(float(t.get("usd", 0) or 0) for t in tranches),
        }

    def test_the_button_goes_quiet_once_a_tranche_stands(self):
        bot = _bot(parked=PARKED)
        before = self._panel_reads(bot)
        assert before["wire_button_enabled"] is True
        assert before["open_tranches"] == 0

        asyncio.run(bot._execute_manual_rebalance(_Ticker(PRICE), "manual_button"))

        after = self._panel_reads(bot)
        assert after["open_tranches"] >= 1
        assert after["wire_button_enabled"] is False, (
            f"the panel would show {after['wire_button_label']!r} beside "
            f"{after['open_tranches']} standing tranche(s)"
        )
        assert after["wire_button_label"] == "Clear Wire Credits"
        assert abs(after["queue_usd"] - (50.0 + PARKED)) <= MONEY_TOL_USD

    def test_the_blinded_panel_shows_the_operators_report(self):
        """The control, at the surface he actually read."""
        bot = _bot(parked=PARKED)
        _blind(bot)
        asyncio.run(bot._execute_manual_rebalance(_Ticker(PRICE), "manual_button"))
        after = self._panel_reads(bot)
        assert after["wire_button_label"] == "Clear $5.00 Wire Credits"
        assert after["open_tranches"] == 1

    def test_the_queue_scalar_matches_the_rows_the_table_sums(self):
        bot = _bot(parked=PARKED, tranches=(_tranche(10.0, 20.0, 0.6),))
        asyncio.run(bot._execute_manual_rebalance(_Ticker(PRICE), "manual_button"))
        panel = self._panel_reads(bot)
        assert abs(bot._fold_queue_usd - panel["queue_usd"]) <= MONEY_TOL_USD


# -- every build loop lands the pool ---------------------------------


def _build_sites(source: str) -> list:
    """Every function in ``source`` that appends a fold tranche."""
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "append"
                and isinstance(sub.func.value, ast.Attribute)
                and sub.func.value.attr == "_fold_tranches"
            ):
                found.append(node)
                break
    return found


def _lands_the_pool(fn) -> bool:
    for sub in ast.walk(fn):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "_land_pending_wire_credits"
        ):
            return True
    return False


class TestEveryBuildLoopLandsThePool:
    """The invariant a fourth build loop must not be able to break.

    Unit 2 established three loops create fold tranches. Two of the
    three did not drain the parked pool, and nothing on the queue would
    have said so.
    """

    def test_the_three_build_loops_are_still_three(self):
        names = sorted({fn.name for fn in _build_sites(SCRUMMING_BOT_SRC)})
        assert names == ["_execute_manual_rebalance", "tick"], names
        appends = SCRUMMING_BOT_SRC.count("self._fold_tranches.append(")
        assert appends == 3, (
            f"{appends} fold-tranche append sites; the unit measured 3. A new "
            f"one must land the parked pool -- fix the code, not this count."
        )

    def test_every_enclosing_function_lands_the_pool(self):
        for fn in _build_sites(SCRUMMING_BOT_SRC):
            assert _lands_the_pool(fn), (
                f"{fn.name} builds a fold tranche and never calls "
                f"_land_pending_wire_credits; a parked wire credit would "
                f"stay parked beside the tranche it just opened"
            )

    def test_the_check_fails_when_the_call_is_removed(self):
        """The control. Blind the source and the check must go red."""
        blinded = SCRUMMING_BOT_SRC.replace("self._land_pending_wire_credits()", "pass")
        assert blinded != SCRUMMING_BOT_SRC, "the plant matched nothing"
        sites = _build_sites(blinded)
        assert sites, "the blinded source has no build loop; the plant missed"
        assert not any(_lands_the_pool(fn) for fn in sites)


# -- state restore ---------------------------------------------------


class _RestoreBot:
    """Only what ``import_scrumming_state`` reads off ``self``."""

    import_scrumming_state = ScrummingBot.import_scrumming_state

    def __init__(self) -> None:
        self.bot_id = "u11-restore"
        self.config = type("C", (), {"symbol": "CHIP/USD", "target_balance": 50.0})()
        self._bus = _Bus()
        self._current_holdings = 0.0
        self._anchor_target_balance = 50.0
        self._target_balance = 50.0
        self._standing_surplus_usd = 0.0
        self._fold_cycle_cap_consumed = 0.0
        self._pending_wire_credits = 0.0
        self._pending_wire_ledger: list[dict] = []
        self._fold_tranches: list[dict] = []
        self._fold_queue_usd = 0.0
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
        self._compact_wire_credits = types.MethodType(
            ScrummingBot._compact_wire_credits, self
        )
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


STRANDED_STATE = {
    "pending_wire_credits": 5.0,
    "pending_wire_ledger": [{"ts": 1.0, "source": "peer-bot", "usd": 5.0, "ref": "w1"}],
    "fold_tranches": [_tranche(10.0, 20.0, 0.6), _tranche(30.0, 60.0, 0.7)],
}


class TestARestoredFileCannotStayStranded:
    """A state file written before the build loops landed the pool can
    carry both fields populated. The restore re-asserts the invariant."""

    def test_the_stranded_file_is_the_operators_pairing(self):
        """The premise, read straight off the fixture."""
        assert STRANDED_STATE["pending_wire_credits"] > 0
        assert len(STRANDED_STATE["fold_tranches"]) == 2

    def test_the_restore_lands_it(self):
        bot = _RestoreBot()
        bot.import_scrumming_state(dict(STRANDED_STATE))
        assert bot._pending_wire_credits == 0.0
        assert bot._pending_wire_ledger == []
        assert abs(_queue_usd(bot) - 45.0) <= MONEY_TOL_USD
        assert abs(bot._fold_queue_usd - 45.0) <= MONEY_TOL_USD
        assert abs(_recorded_usd(bot) - 5.0) <= MONEY_TOL_USD

    def test_a_restore_with_no_tranches_keeps_the_pool(self):
        bot = _RestoreBot()
        bot.import_scrumming_state(
            {
                "pending_wire_credits": 5.0,
                "pending_wire_ledger": list(STRANDED_STATE["pending_wire_ledger"]),
                "fold_tranches": [],
            }
        )
        assert abs(bot._pending_wire_credits - 5.0) <= MONEY_TOL_USD
        assert len(bot._pending_wire_ledger) == 1

    def test_the_blinded_restore_leaves_it_stranded(self):
        bot = _RestoreBot()
        bot._land_pending_wire_credits = lambda *_a, **_k: 0.0
        bot.import_scrumming_state(dict(STRANDED_STATE))
        assert abs(bot._pending_wire_credits - 5.0) <= MONEY_TOL_USD
        assert abs(_queue_usd(bot) - 40.0) <= MONEY_TOL_USD


# -- the growth cap, confirmed rather than assumed --------------------


class TestTheGrowthCapStillBounds:
    """The operator's stated consequence: a landed credit does not lift
    what a cycle spends. It makes tranches survive part-consumed.

    ``_plan_fold_consumption`` decides what a cycle takes;
    ``_settle_fold_plan`` takes it. Both are driven here on real code.
    """

    def test_the_cycle_takes_the_cap_and_not_the_credit(self):
        bot = _bot(parked=PARKED, tranches=(_tranche(10.0, 20.0, 0.6),))
        ScrummingBot._land_pending_wire_credits(bot)
        assert abs(_queue_usd(bot) - 15.0) <= MONEY_TOL_USD

        cap_remaining = 6.0
        plan, _slices, partial = ScrummingBot._plan_fold_consumption(
            bot, list(bot._fold_tranches), cap_remaining
        )
        taken = sum(usd for _t, usd, _u in plan)
        assert (
            abs(taken - cap_remaining) <= MONEY_TOL_USD
        ), f"the cycle took ${taken:.4f} against a ${cap_remaining:.4f} cap"
        assert partial == 1

    def test_the_tranche_survives_the_cycle_holding_the_remainder(self):
        bot = _bot(parked=PARKED, tranches=(_tranche(10.0, 20.0, 0.6),))
        ScrummingBot._land_pending_wire_credits(bot)
        plan, _slices, _partial = ScrummingBot._plan_fold_consumption(
            bot, list(bot._fold_tranches), 6.0
        )

        removed, drained = ScrummingBot._settle_fold_plan(bot, plan)

        assert removed == 0 and drained == 0
        assert len(bot._fold_tranches) == 1
        assert abs(bot._fold_tranches[0]["usd"] - 9.0) <= MONEY_TOL_USD
        assert bot._fold_tranches[0]["fold_partial_spent"] is True

    def test_units_leave_in_proportion_to_the_dollars(self):
        bot = _bot(parked=PARKED, tranches=(_tranche(10.0, 20.0, 0.6),))
        ScrummingBot._land_pending_wire_credits(bot)
        plan, _slices, _partial = ScrummingBot._plan_fold_consumption(
            bot, list(bot._fold_tranches), 6.0
        )
        ScrummingBot._settle_fold_plan(bot, plan)
        assert abs(bot._fold_tranches[0]["units"] - 20.0 * (9.0 / 15.0)) <= 1e-9

    def test_without_the_credit_the_same_cap_drains_the_tranche(self):
        """The two-sided half: the survival is caused by the added money,
        not by the cap alone."""
        bot = _bot(tranches=(_tranche(10.0, 20.0, 0.6),))
        plan, _slices, partial = ScrummingBot._plan_fold_consumption(
            bot, list(bot._fold_tranches), 6.0
        )
        ScrummingBot._settle_fold_plan(bot, plan)
        assert partial == 1
        assert abs(bot._fold_tranches[0]["usd"] - 4.0) <= MONEY_TOL_USD

        plan2, _s2, partial2 = ScrummingBot._plan_fold_consumption(
            bot, list(bot._fold_tranches), 6.0
        )
        removed, drained = ScrummingBot._settle_fold_plan(bot, plan2)
        assert partial2 == 0
        assert removed == 1 and drained == 1
        assert bot._fold_tranches == []

    def test_the_cap_bounds_the_take_whatever_the_pool_was(self):
        """A landed pool of any size cannot make one cycle spend more."""
        for pool in (0.01, 5.0, 343.68, 99999.99):
            bot = _bot(parked=pool, tranches=(_tranche(10.0, 20.0, 0.6),))
            ScrummingBot._land_pending_wire_credits(bot)
            plan, _slices, _partial = ScrummingBot._plan_fold_consumption(
                bot, list(bot._fold_tranches), 6.0
            )
            taken = sum(usd for _t, usd, _u in plan)
            assert (
                taken <= 6.0 + MONEY_TOL_USD
            ), f"pool ${pool}: the cycle took ${taken:.4f} past a $6.0000 cap"
