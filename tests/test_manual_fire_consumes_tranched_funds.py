"""Manual Fire's buy draws on the fold-tranche queue before wallet cash.

Issue #133 unit 13. ``_execute_manual_rebalance`` serves Manual Fire,
Wire Stack Fire and Max Cartridge Fire. On its BUY branch every unit it
acquires must come off the tranche queue until the queue is empty; only
the remainder opens a fresh lot at the fill price.

SOURCING, NOT CALL ORDER. Tranche USD is demarked wallet cash, never
reserved and never locked. The quote-currency balance read is a
solvency clip on the order size, not a competing source. These tests
assert where the ACQUIRED UNITS came from and by how much the queue
fell.

Every test drives ``_execute_manual_rebalance``. Only the outward edges
are stubbed: exchange, emitters, settled fill.
"""

from __future__ import annotations

import asyncio

import pytest

from src.trading.scrumming_bot import ScrummingBot

PRICE = 0.5
HOLDINGS = 50.0
TARGET = 100.0
DEFICIT_USD = 75.0
TRANCHE_IBP = 0.8
CALLERS = ("manual_button", "wire_stack", "max_cartridge")


class _Bus:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def emit(self, topic, **payload):
        self.messages.append(f"{topic}|{payload.get('message', '')}")


class _Stats:
    def __init__(self) -> None:
        self.total_trades = 0
        self.total_folded_usd = 0.0
        self.total_scrummed_usd = 0.0
        self.trade_volume = 0.0


class _Config:
    def __init__(self, growth_pct=0.0):
        self.symbol = "CHIP/USD"
        self.target_asset = "CHIP"
        self.exchange_id = "coinbase"
        self.scrumming_interval_pct = 1.0
        self.trading_fee_pct = 0.6
        self.max_target_growth_pct = growth_pct
        self.profit_folding_active = True
        self.scrum_fold_pct = 100


class _Order:
    id = "u13"
    filled = 0.0
    average = 0.0


class _Ticker:
    def __init__(self, last):
        self.last = last


class _Fire:
    """One driven Manual Fire and the state either side of it."""

    def __init__(self, bot, placed, before, after):
        self.bot = bot
        self.placed = placed
        self.before = before
        self.after = after

    @property
    def units_bought(self) -> float:
        return self.after["holdings"] - self.before["holdings"]

    @property
    def usd_spent(self) -> float:
        return self.units_bought * PRICE

    @property
    def queue_usd_drop(self) -> float:
        return self.before["queue_usd"] - self.after["queue_usd"]

    @property
    def queue_units_drop(self) -> float:
        return self.before["queue_units"] - self.after["queue_units"]

    @property
    def units_from_queue(self) -> float:
        """Units the discharge moved out of the queue into ``_main_lots``."""
        return self.queue_units_drop

    @property
    def units_from_wallet(self) -> float:
        """Units opened as a fresh lot at the fill price."""
        return sum(
            lot["units"]
            for lot in self.bot._main_lots
            if lot.get("initial_buy_price") == PRICE
            and lot.get("operator_initiated") is not None
        )


def _snapshot(bot) -> dict:
    return {
        "queue_usd": sum(t["usd"] for t in bot._fold_tranches),
        "queue_units": sum(t["units"] for t in bot._fold_tranches),
        "holdings": bot._current_holdings,
        "target": bot._target_balance,
        "closed_lifetime": bot._tranches_closed_lifetime,
        "rows": len(bot._fold_tranches),
    }


def _bot(tranches, *, wallet_usd=1_000_000.0, growth_pct=0.0):
    bot = object.__new__(ScrummingBot)
    bot.bot_id = "u13-bot"
    bot._bus = _Bus()
    bot.config = _Config(growth_pct=growth_pct)
    bot.stats = _Stats()
    bot._fold_tranches = [dict(t) for t in tranches]
    bot._main_lots = [{"units": HOLDINGS, "initial_buy_price": TRANCHE_IBP}]
    bot._current_holdings = HOLDINGS
    bot._target_balance = TARGET
    bot._anchor_target_balance = TARGET
    bot._quote_to_usd = 1.0
    bot._manual_fire_pending = True
    bot._fold_queue_usd = sum(t["usd"] for t in tranches)
    bot._fold_cycle_cap_consumed = 0.0
    bot._standing_surplus_usd = 0.0
    bot._retained_this_cycle_usd = 0.0
    bot._fold_accumulator = 0.0
    bot._target_grow_last_side = None
    bot._tranches_closed_lifetime = 0
    bot._tranches_created_lifetime = 0
    bot._tranches_malformed_dropped = 0
    bot._pending_wire_credits = 0.0
    bot._last_trade_side = None
    bot._last_trade_price = 0.0
    bot._last_bb = None
    bot.placed = []

    async def _refresh():
        return 1.0

    async def _place(**kwargs):
        bot.placed.append(dict(kwargs))
        return _Order()

    async def _settled(order, symbol_, requested, tick_price):
        del order, symbol_, tick_price
        return requested, PRICE, True

    async def _balance(currency):
        free = HOLDINGS if currency == "CHIP" else wallet_usd
        return type("B", (), {"total": free, "free": free, "absent": False})()

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


def _fire(tranches, *, intent="manual_button", wallet_usd=1_000_000.0, growth_pct=0.0):
    bot = _bot(tranches, wallet_usd=wallet_usd, growth_pct=growth_pct)
    before = _snapshot(bot)
    asyncio.run(bot._execute_manual_rebalance(_Ticker(PRICE), intent))
    return _Fire(bot, list(bot.placed), before, _snapshot(bot))


def _row(usd, units, ref, **extra):
    row = {"usd": usd, "units": units, "ref": ref, "initial_buy_price": TRANCHE_IBP}
    row.update(extra)
    return row


# ── the vacuous-pass control ─────────────────────────────────────────


def _assert_money_moved(fire: _Fire) -> None:
    """A fire that bought nothing satisfies every ordering claim below."""
    assert len(fire.placed) == 1, f"expected one order, saw {fire.placed}"
    assert fire.placed[0]["side"].value == "buy"
    assert fire.units_bought > 0, "no units acquired; the fire was a no-op"
    assert fire.usd_spent > 0, "no USD spent; the fire was a no-op"


@pytest.mark.parametrize("intent", CALLERS)
def test_the_fire_actually_buys(intent):
    """The scenario is a no-op, so every sourcing assertion is vacuous."""
    fire = _fire([_row(50.0, 100.0, 0.6)], intent=intent)
    _assert_money_moved(fire)
    assert fire.usd_spent == pytest.approx(DEFICIT_USD)


# ── a. the queue is the first source ─────────────────────────────────


@pytest.mark.parametrize("intent", CALLERS)
def test_a_buy_larger_than_the_queue_empties_it_before_touching_the_wallet(intent):
    """Wallet cash opened a lot while tranche units were left standing."""
    fire = _fire([_row(50.0, 100.0, 0.6)], intent=intent)
    _assert_money_moved(fire)

    assert fire.usd_spent == pytest.approx(DEFICIT_USD)
    assert fire.units_bought == pytest.approx(150.0)

    # The queue held 100 units at $0.50 parked per unit.
    assert fire.queue_units_drop == pytest.approx(100.0)
    assert fire.queue_usd_drop == pytest.approx(50.0)
    assert fire.after["queue_usd"] == pytest.approx(0.0)
    assert fire.after["rows"] == 0
    assert fire.after["closed_lifetime"] == 1

    # Queue first, wallet for the remainder only.
    assert fire.units_from_queue == pytest.approx(100.0)
    assert fire.units_from_wallet == pytest.approx(50.0)
    assert fire.units_from_queue + fire.units_from_wallet == pytest.approx(
        fire.units_bought
    )


@pytest.mark.parametrize("intent", CALLERS)
def test_a_buy_smaller_than_the_queue_takes_every_unit_from_it(intent):
    """A buy the queue could fund opened a fresh wallet lot anyway."""
    fire = _fire([_row(200.0, 400.0, 0.6)], intent=intent)
    _assert_money_moved(fire)

    assert fire.usd_spent == pytest.approx(DEFICIT_USD)
    assert fire.units_bought == pytest.approx(150.0)

    assert fire.units_from_queue == pytest.approx(150.0)
    assert fire.units_from_wallet == pytest.approx(0.0)

    # The queue is smaller by exactly what the buy spent.
    assert fire.queue_usd_drop == pytest.approx(DEFICIT_USD)
    assert fire.queue_units_drop == pytest.approx(150.0)
    assert fire.after["queue_usd"] == pytest.approx(125.0)
    assert fire.after["rows"] == 1
    assert fire.after["closed_lifetime"] == 0


@pytest.mark.parametrize("intent", CALLERS)
def test_the_queue_falls_by_what_the_buy_took_from_it(intent):
    """The queue's fall and the units it supplied do not reconcile."""
    fire = _fire([_row(50.0, 100.0, 0.6)], intent=intent)
    _assert_money_moved(fire)
    # Parked rate: $50.00 over 100 units.
    assert fire.queue_usd_drop == pytest.approx(fire.queue_units_drop * 0.5)
    assert fire.queue_usd_drop == pytest.approx(fire.units_from_queue * 0.5)


@pytest.mark.parametrize("intent", CALLERS)
def test_a_ladder_discharges_the_highest_ref_first(intent):
    """The discharge order is not ref-descending."""
    fire = _fire(
        [_row(30.0, 60.0, 0.58), _row(60.0, 120.0, 0.62)],
        intent=intent,
    )
    _assert_money_moved(fire)
    assert fire.units_bought == pytest.approx(150.0)
    # 120 units off ref 0.62, then 30 off ref 0.58.
    assert fire.after["rows"] == 1
    assert fire.bot._fold_tranches[0]["ref"] == pytest.approx(0.58)
    assert fire.bot._fold_tranches[0]["units"] == pytest.approx(30.0)
    assert fire.bot._fold_tranches[0]["usd"] == pytest.approx(15.0)
    assert fire.after["closed_lifetime"] == 1


# ── b. the wallet is a solvency clip, not a source ───────────────────


def test_a_wallet_smaller_than_the_deficit_clips_the_buy_and_the_queue():
    """A clipped buy discharged more or less than it bought."""
    fire = _fire([_row(50.0, 100.0, 0.6)], wallet_usd=10.0)
    _assert_money_moved(fire)
    assert fire.usd_spent == pytest.approx(10.0)
    assert fire.units_bought == pytest.approx(20.0)
    assert fire.queue_usd_drop == pytest.approx(10.0)
    assert fire.queue_units_drop == pytest.approx(20.0)
    assert fire.units_from_wallet == pytest.approx(0.0)
    assert fire.after["rows"] == 1


def test_an_empty_wallet_places_no_order_and_leaves_the_queue_standing():
    """An unfundable buy was sent, or the ladder moved without a fill."""
    fire = _fire([_row(50.0, 100.0, 0.6)], wallet_usd=0.0)
    assert fire.placed == []
    assert fire.units_bought == pytest.approx(0.0)
    assert fire.queue_usd_drop == pytest.approx(0.0)
    assert fire.after["rows"] == 1


def test_no_queue_at_all_opens_one_wallet_lot():
    """A buy with no ladder failed to open a lot for what it bought."""
    fire = _fire([])
    _assert_money_moved(fire)
    assert fire.units_bought == pytest.approx(150.0)
    assert fire.units_from_wallet == pytest.approx(150.0)
    assert fire.after["rows"] == 0


# ── c. an unreadable row never swallows the fill ─────────────────────


def test_a_row_with_no_ref_key_still_discharges():
    """The buy filled and the discharge raised, losing the fill."""
    fire = _fire([{"usd": 50.0, "units": 100.0, "initial_buy_price": TRANCHE_IBP}])
    _assert_money_moved(fire)
    assert fire.units_bought == pytest.approx(150.0)
    assert fire.queue_usd_drop == pytest.approx(50.0)
    assert fire.queue_units_drop == pytest.approx(100.0)
    assert fire.after["rows"] == 0


def test_a_row_with_no_ref_key_discharges_last():
    """A missing ref read as 0.0 outranked a real ref in the discharge."""
    fire = _fire(
        [
            {"usd": 50.0, "units": 100.0, "initial_buy_price": TRANCHE_IBP},
            _row(30.0, 60.0, 0.62),
        ]
    )
    _assert_money_moved(fire)
    assert fire.units_bought == pytest.approx(150.0)
    # 60 units off ref 0.62 first, then 90 of the 100 unreadable ones.
    assert fire.after["rows"] == 1
    assert "ref" not in fire.bot._fold_tranches[0]
    assert fire.bot._fold_tranches[0]["units"] == pytest.approx(10.0)


@pytest.mark.parametrize("intent", CALLERS)
def test_all_three_callers_discharge_past_a_row_with_no_ref_key(intent):
    """One caller loses the fill on a ladder the others discharge."""
    fire = _fire(
        [
            {"usd": 50.0, "units": 100.0, "initial_buy_price": TRANCHE_IBP},
            _row(30.0, 60.0, 0.62),
        ],
        intent=intent,
    )
    _assert_money_moved(fire)
    assert fire.units_bought == pytest.approx(150.0)
    assert fire.queue_units_drop == pytest.approx(150.0)
    assert fire.queue_usd_drop == pytest.approx(75.0)
    assert fire.after["rows"] == 1


def test_a_non_finite_ref_is_not_discharged():
    """The sizing skipped the row and the discharge spent it anyway."""
    fire = _fire(
        [_row(25.0, 50.0, float("nan")), _row(25.0, 50.0, 0.6)],
        growth_pct=0.0,
    )
    _assert_money_moved(fire)
    # Only the readable row discharges. The nan row keeps its parked USD.
    assert fire.queue_usd_drop == pytest.approx(25.0)
    assert fire.queue_units_drop == pytest.approx(50.0)
    assert fire.after["rows"] == 1
    assert fire.bot._fold_tranches[0]["units"] == pytest.approx(50.0)
    assert fire.bot._fold_tranches[0]["usd"] == pytest.approx(25.0)


def test_non_finite_units_never_reach_main_lots():
    """A nan-unit row was discharged and poisoned the lot ledger."""
    fire = _fire(
        [_row(25.0, float("nan"), 0.7), _row(25.0, 50.0, 0.6)],
        growth_pct=0.0,
    )
    _assert_money_moved(fire)
    assert all(
        lot["units"] == lot["units"] for lot in fire.bot._main_lots
    ), "a nan-unit lot reached _main_lots"
    assert fire.queue_usd_drop == pytest.approx(25.0)
    assert fire.after["rows"] == 1


def test_a_numeric_string_ref_beside_a_float_ref_still_discharges():
    """A string ref met a float ref in the sort and raised after the fill."""
    fire = _fire([_row(25.0, 50.0, "0.62"), _row(25.0, 50.0, 0.58)])
    _assert_money_moved(fire)
    assert fire.units_bought == pytest.approx(150.0)
    assert fire.queue_usd_drop == pytest.approx(50.0)
    assert fire.queue_units_drop == pytest.approx(100.0)
    assert fire.after["rows"] == 0


# ── d. the control: the same assertions on a broken fire ─────────────


class _WalletFirstFire(_Fire):
    """A Manual Fire that spends wallet cash and leaves the queue whole."""

    @property
    def queue_usd_drop(self) -> float:
        return 0.0

    @property
    def queue_units_drop(self) -> float:
        return 0.0

    @property
    def units_from_wallet(self) -> float:
        return self.units_bought


def test_the_sourcing_assertions_reject_a_wallet_first_fire():
    """The assertions above pass on a fire that consumed no tranche."""
    fire = _fire([_row(50.0, 100.0, 0.6)])
    broken = _WalletFirstFire(fire.bot, fire.placed, fire.before, fire.after)

    # The vacuous-pass control still passes: money did move.
    _assert_money_moved(broken)

    with pytest.raises(AssertionError):
        assert broken.queue_units_drop == pytest.approx(100.0)
    with pytest.raises(AssertionError):
        assert broken.queue_usd_drop == pytest.approx(50.0)
    with pytest.raises(AssertionError):
        assert broken.units_from_queue == pytest.approx(100.0)
    with pytest.raises(AssertionError):
        assert broken.units_from_wallet == pytest.approx(50.0)
