"""A fold tranche is worth what the venue credited, not the notional.

``_settled_sale_proceeds`` values a settled sell at ``units`` times
``price`` minus the fee the venue reported, and ``_record_venue_fee``
is the only thing that supplies that fee. ``PATHS`` fires the real
SCRUM, DIST and manual sells and reads the booked figure at the
tranche. ``GROSS``, ``NET`` and ``SYNTHESISED`` are the three numbers a
sale can be valued at, and only ``NET`` is the venue's.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.exchange.base import OrderSide  # noqa: E402
from src.exchange.ccxt_connector import CCXTConnector  # noqa: E402
from src.trading.scrumming_bot import ScrummingBot, SettledSellFee  # noqa: E402

# A recorded venue fill, quoted rather than recomputed from the code
# under test.
UNITS = 473.0
PRICE = 0.03376
VENUE_FEE = 0.19162
GROSS = 15.96848
NET = 15.77686

# The configured rate, deliberately 1.6% against the venue's 1.2%.
CONFIG_FEE_PCT = 1.6
SYNTHESISED = 15.71298

# Money is compared to five decimals, the reconciliation's precision.
PLACES = 5


def _round(value: float) -> float:
    return round(float(value), PLACES)


# ── STUBS ────────────────────────────────────────────────────────────


class _Bus:
    def __init__(self):
        self.messages = []

    def emit(self, event, **kwargs):
        self.messages.append((event, kwargs))


class _Config:
    def __init__(self, **overrides):
        self.symbol = "CHIP/USD"
        self.target_asset = "CHIP"
        self.scrumming_interval_pct = 1.0
        self.trading_fee_pct = CONFIG_FEE_PCT
        self.stack_mode = False
        self.position_ceiling_enabled = False
        self.max_target_growth_pct = 1.0
        for key, value in overrides.items():
            setattr(self, key, value)


class _Stats:
    def __init__(self):
        self.verify_samples = 0
        self.verify_clean = 0
        self.verify_adjusted = 0
        self.verify_canceled = 0
        self.total_sells = 0
        self.total_buys = 0
        self.total_trades = 0
        self.trade_volume = 0.0
        self.last_trade_time = 0.0


class _Order:
    """A settled order in the shape the connector builds one."""

    def __init__(
        self,
        *,
        price,
        fee=0.0,
        currency="USD",
        side=OrderSide.SELL,
        filled=0.0,
        order_id="stub-order",
    ):
        self.id = order_id
        self.side = side
        self.average = price
        self.price = price
        self.filled = filled
        self.fee = fee
        self.fee_currency = currency


class _Exchange:
    """Returns nothing open, and whatever order the test parks on it."""

    def __init__(self, fetched=None):
        self.fetched = fetched
        self.get_order_calls = 0

    async def get_open_orders(self, symbol):
        return []

    async def get_order(self, order_id, symbol):
        self.get_order_calls += 1
        return self.fetched


class _Summary:
    consensus_direction = "sell"
    consensus_confidence = 0.75


class _StubBot:
    """Minimum surface to run the REAL fee plumbing to completion.

    The four methods under test are bound off ``ScrummingBot`` itself,
    so the shipping code runs. Everything else is a permissive stub, in
    the pattern ``tests/test_ytd_per_trade_increment.py`` already uses
    to drive ``_execute_sell``.
    """

    def __init__(self, *, order=None, fetched=None, **config_overrides):
        self.bot_id = "net-proceeds-stub"
        self.config = _Config(**config_overrides)
        self.stats = _Stats()
        self._bus = _Bus()
        self.exchange = _Exchange(fetched=fetched)
        self._order = order
        self._quote_to_usd = 1.0
        self._current_holdings = 100000.0
        self._target_balance = 100000.0
        self._anchor_target_balance = 100000.0
        self._fold_tranches = []
        self._main_lots = []
        self._initialised = True
        self._invisible = True
        self._hyst_armed_scrum_side = False
        self._hyst_ref_scrum_side = 0.0
        self._hyst_armed_fold_side = False
        self._hyst_ref_fold_side = 0.0
        self._memorised_trades = []
        self._last_sell_venue_fee = None
        self.placed_orders = []
        self.notifications = []
        self.reconciles = []
        for name in (
            "_record_venue_fee",
            "_take_venue_fee",
            "_venue_quote_currency",
            "_settled_sale_proceeds",
        ):
            setattr(self, name, types.MethodType(getattr(ScrummingBot, name), self))
        self._settled_fill_label = ScrummingBot._settled_fill_label

    def _crr(self):
        return None

    def _emit_trade_notification(self, kind, state, detail):
        # Recorded rather than discarded: a stub that drops what it was
        # told cannot be asserted against.
        self.notifications.append((kind, state, detail))

    async def _reconcile_holdings(self, reason=""):
        self.reconciles.append(reason)
        return None

    async def guarded_place_order(self, symbol, side, order_type, amount, price):
        self.placed_orders.append(
            {
                "symbol": symbol,
                "side": side,
                "type": order_type,
                "amount": amount,
                "price": price,
            }
        )
        return self._order

    def log(self):
        return [kwargs.get("message", "") for _, kwargs in self._bus.messages]


def _sell(bot, amount, price):
    return asyncio.run(
        ScrummingBot._execute_sell(
            bot, amount=amount, price=price, summary=_Summary(), bypass_stack=True
        )
    )


def _settled(bot, order, requested, quoted):
    return asyncio.run(
        ScrummingBot._settled_fill(bot, order, bot.config.symbol, requested, quoted)
    )


def _proceeds(bot, units=UNITS, price=PRICE, label="SCRUM"):
    return bot._settled_sale_proceeds(units, price, label=label)


# ── THE RED PROOF ────────────────────────────────────────────────────


def test_a_settled_sale_books_what_the_venue_credited():
    """Red means a fold loop values a sale at the gross notional again.

    This is the operator's measured trade, driven through the REAL
    ``_execute_sell`` so the carry is proved rather than assumed.
    """
    bot = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE))

    fill = _sell(bot, UNITS, PRICE)
    assert fill == pytest.approx(PRICE), "the fill price must not move"

    booked = _proceeds(bot)

    # THE VACUOUS-PASS CONTROL. A path that books zero also never books
    # gross, so the exact value is asserted BEFORE the inequality.
    assert booked > 0.0, "a settled sale that books nothing is not a fix"
    assert _round(booked) == NET

    # THE RED PROOF.
    assert _round(booked) != GROSS, (
        f"booked ${booked:.5f}; the gross notional ${GROSS:.5f} is what "
        f"the venue did NOT credit"
    )
    assert _round(GROSS - booked) == _round(VENUE_FEE)


def test_the_gross_is_the_number_this_unit_refuses():
    """Red means the fixtures stopped describing the measured trade.

    Without this the red proof above could pass because GROSS and NET
    were never different numbers in the first place.
    """
    assert _round(UNITS * PRICE) == GROSS
    assert _round(GROSS - VENUE_FEE) == NET
    assert GROSS != NET


# ── THE SYNTHESIS CONTROL ────────────────────────────────────────────


def test_the_venue_fee_wins_over_the_configured_rate():
    """Red means a path derives the fee from ``trading_fee_pct``.

    The config is deliberately wrong: 1.6% against the venue's 1.2%.
    The venue's number must be the one booked.
    """
    bot = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE))
    assert bot.config.trading_fee_pct == CONFIG_FEE_PCT

    _sell(bot, UNITS, PRICE)
    booked = _proceeds(bot)

    assert _round(booked) == NET
    assert _round(booked) != SYNTHESISED, (
        f"booked ${booked:.5f}, which is the CONFIGURED "
        f"{CONFIG_FEE_PCT}% and not the venue's fee"
    )


@pytest.mark.parametrize("venue_fee", [0.05, 0.19162, 0.4, 1.25])
def test_any_fee_the_venue_reports_is_the_one_booked(venue_fee):
    """Red means the booked fee stopped tracking the venue's number.

    A single fixture cannot tell "reads the venue" from "happens to
    agree with the venue on one trade". Four unrelated rates can.
    """
    bot = _StubBot(order=_Order(price=PRICE, fee=venue_fee))
    _sell(bot, UNITS, PRICE)
    booked = _proceeds(bot)
    assert _round(booked) == _round(UNITS * PRICE - venue_fee)


# ── THE NO-FEE CONTROL ───────────────────────────────────────────────


def test_no_reported_fee_books_the_gross_and_says_so():
    """Red means the code guesses when the venue reports nothing."""
    bot = _StubBot(order=_Order(price=PRICE, fee=0.0))

    _sell(bot, UNITS, PRICE)
    booked = _proceeds(bot)

    assert _round(booked) == GROSS
    assert any("BOOKED GROSS" in line for line in bot.log())
    assert any("venue reported no fee" in line for line in bot.log())


def test_a_fee_in_another_currency_books_the_gross_and_says_so():
    """Red means a base-denominated fee is subtracted from quote."""
    bot = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE, currency="CHIP"))

    _sell(bot, UNITS, PRICE)
    booked = _proceeds(bot)

    assert _round(booked) == GROSS
    assert any("not the USD this sale is credited in" in line for line in bot.log())


def test_a_fee_that_swallows_the_sale_books_the_gross_and_says_so():
    """Red means an absurd fee can drive a tranche to zero or below."""
    bot = _StubBot(order=_Order(price=PRICE, fee=GROSS * 2.0))

    _sell(bot, UNITS, PRICE)
    booked = _proceeds(bot)

    assert _round(booked) == GROSS
    assert any("is not smaller than the gross" in line for line in bot.log())


def test_the_net_case_says_so_too():
    """Red means only the refusals are visible in the operator's log.

    The gross tests above pass on a code path that emits nothing at
    all. This is the control that refuses that reading.
    """
    bot = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE))
    _sell(bot, UNITS, PRICE)
    _proceeds(bot)
    assert any("BOOKED NET" in line for line in bot.log())
    assert any("the venue reported" in line for line in bot.log())


# ── THE CARRY, AND WHAT IT REFUSES TO CARRY ──────────────────────────


def test_a_fee_is_spent_once():
    """Red means one venue fee can be subtracted from two valuations."""
    bot = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE))
    _sell(bot, UNITS, PRICE)

    assert _round(_proceeds(bot)) == NET
    assert _round(_proceeds(bot)) == GROSS


@pytest.mark.parametrize(
    "units, price",
    [(UNITS + 1.0, PRICE), (UNITS, PRICE * 2.0), (UNITS * 0.5, PRICE * 0.5)],
)
def test_a_fee_from_another_order_is_not_applied(units, price):
    """Red means a stale fee can be booked against an unrelated fill."""
    bot = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE))
    _sell(bot, UNITS, PRICE)

    booked = bot._settled_sale_proceeds(units, price, label="SCRUM")
    assert _round(booked) == _round(units * price)


def test_a_sell_that_never_reached_the_exchange_clears_the_record():
    """Red means a refused sell leaves the previous sell's fee live."""
    bot = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE))
    _sell(bot, UNITS, PRICE)
    assert bot._last_sell_venue_fee is not None

    bot._order = None
    assert _sell(bot, UNITS, PRICE) is None
    assert bot._last_sell_venue_fee is None
    assert _round(_proceeds(bot)) == GROSS


def test_a_bot_built_without_init_can_still_value_a_sale():
    """Red means a sell raises AttributeError on a restored bot.

    The fee record has a CLASS-level default because bots are built
    with ``object.__new__`` -- across this suite and on the restore
    paths -- and a sale that raises rather than books is strictly
    worse than a sale booked at the gross.
    """
    bare = object.__new__(ScrummingBot)
    bare.bot_id = "no-init"
    bare.config = _Config()
    bare._bus = _Bus()

    assert bare._last_sell_venue_fee is None
    assert _round(bare._settled_sale_proceeds(UNITS, PRICE, label="SCRUM")) == GROSS


def test_one_bots_fee_is_never_readable_by_another():
    """Red means the class-level default became shared mutable state."""
    first = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE))
    second = _StubBot(order=_Order(price=PRICE, fee=VENUE_FEE))

    _sell(first, UNITS, PRICE)

    assert second._last_sell_venue_fee is None
    assert _round(_proceeds(second)) == GROSS
    assert _round(_proceeds(first)) == NET


def test_a_buy_fee_is_never_recorded_as_a_sale_fee():
    """Red means a fold's buy fee can be taken off a scrum's proceeds."""
    bot = _StubBot()
    buy = _Order(price=PRICE, fee=VENUE_FEE, side=OrderSide.BUY, filled=UNITS)

    bot._record_venue_fee(buy, UNITS, PRICE)

    assert bot._last_sell_venue_fee is None
    assert _round(_proceeds(bot)) == GROSS


# ── THE MANUAL PATH: ``_settled_fill`` CARRIES IT ────────────────────


def test_the_manual_path_carries_the_fee_off_the_placed_order():
    """Red means Manual Fire lost the venue's fee on a settled order."""
    bot = _StubBot()
    order = _Order(price=PRICE, fee=VENUE_FEE, filled=UNITS)

    amount, price, is_real = _settled(bot, order, UNITS, PRICE)

    assert (amount, price, is_real) == (UNITS, PRICE, True)
    assert _round(_proceeds(bot, amount, price)) == NET


def test_the_manual_path_carries_the_fee_off_the_RE_READ_order():
    """Red means the fee is read from the wrong order object.

    ``_settled_fill`` re-reads when the placed order carries no fill.
    The fee belongs to whichever object supplied the accepted fill --
    reading the caller's stale object would book a fee of zero.
    """
    stale = _Order(price=0.0, fee=0.0, currency="", filled=0.0)
    fetched = _Order(price=PRICE, fee=VENUE_FEE, filled=UNITS)
    bot = _StubBot(fetched=fetched)

    amount, price, is_real = _settled(bot, stale, UNITS, PRICE)

    assert bot.exchange.get_order_calls >= 1, "the re-read never happened"
    assert (amount, price, is_real) == (UNITS, PRICE, True)
    assert _round(_proceeds(bot, amount, price)) == NET


def test_an_estimated_fill_carries_no_fee_at_all():
    """Red means an unconfirmed fill books a fee the venue never gave.

    ``_settled_fill`` books an ESTIMATE when the venue confirms
    nothing. There is no settled order behind it, so there is no fee.
    """
    unsettled = _Order(price=0.0, fee=0.0, currency="", filled=0.0, order_id="")
    bot = _StubBot()

    amount, price, is_real = _settled(bot, unsettled, UNITS, PRICE)

    assert is_real is False
    assert bot._last_sell_venue_fee is None
    assert _round(_proceeds(bot, amount, price)) == GROSS


# ── THE RECORD TYPE ──────────────────────────────────────────────────


def test_the_record_cannot_be_edited_after_the_venue_wrote_it():
    """Red means a settled fee became rewritable in flight."""
    record = SettledSellFee(
        units=UNITS, price=PRICE, fee_amount=VENUE_FEE, currency="USD", reported=True
    )
    with pytest.raises(Exception):
        record.fee_amount = 0.0


# The two ccxt order dicts Coinbase can produce, as
# ``CCXTConnector._parse_order`` receives them.

# A Coinbase placement: `success_response` carries no `total_fees`, so
# the fee parses to None.
_PLACED = {
    "id": "52cfe5e2-0b29-4c19-a245-a6a773de5030",
    "symbol": "CHIP/USD",
    "side": "sell",
    "type": "market",
    "amount": None,
    "price": None,
    "filled": None,
    "remaining": None,
    "status": None,
    "average": None,
    "cost": None,
    "fee": {"cost": None, "currency": None},
    "timestamp": None,
}

# What ccxt builds from a Coinbase RE-READ, whose body does carry
# ``total_fees``. ccxt passes it through as a string.
_REREAD = dict(
    _PLACED,
    filled=UNITS,
    average=PRICE,
    status="closed",
    cost=GROSS,
    fee={"cost": str(VENUE_FEE), "currency": "USD"},
)


def test_a_coinbase_placement_carries_no_fee_and_a_re_read_does():
    """Red means the connector contract this unit relies on changed.

    Both halves matter. The first is why SCRUM and DIST book gross on
    live Coinbase; the second is why the manual path can book net.
    """
    placed = CCXTConnector._parse_order(_PLACED)
    reread = CCXTConnector._parse_order(_REREAD)

    assert placed.fee == 0.0
    assert placed.average == 0.0
    assert placed.filled == 0.0

    assert reread.fee == pytest.approx(VENUE_FEE)
    assert reread.fee_currency == "USD"
    assert reread.average == pytest.approx(PRICE)


def test_a_placed_coinbase_order_books_the_gross_and_says_so():
    """Red means the bot invented a fee Coinbase never sent it."""
    bot = _StubBot()
    bot._record_venue_fee(CCXTConnector._parse_order(_PLACED), UNITS, PRICE)

    assert bot._last_sell_venue_fee.reported is False
    assert bot._last_sell_venue_fee.fee_amount == 0.0
    assert _round(_proceeds(bot)) == GROSS
    assert any("venue reported no fee" in line for line in bot.log())


def test_a_re_read_coinbase_order_books_the_net():
    """Red means the manual path drops a fee the venue did send."""
    bot = _StubBot()
    bot._record_venue_fee(CCXTConnector._parse_order(_REREAD), UNITS, PRICE)

    booked = _proceeds(bot)
    assert booked > 0.0, "a settled sale that books nothing is not a fix"
    assert _round(booked) == NET
    assert _round(booked) != GROSS


# ── THE BOOKED FIGURE, READ AT THE TRANCHE ON EVERY PATH ─────────────


class _PathBus:
    def __init__(self):
        self.messages = []
        self.events = []

    def emit(self, topic, **payload):
        self.messages.append(f"{topic}|{payload.get('message', '')}")
        self.events.append((topic, payload))


class _PathTicker:
    def __init__(self, last):
        self.last = last


class _PathBB:
    lower = 0.0
    upper = 0.0


PATH_LOTS = ({"units": UNITS, "initial_buy_price": 0.03},)


def _path_bot(*, venue_fee=None, fee_currency="USD", trading_fee_pct=CONFIG_FEE_PCT):
    """A bot that can run any of the three real selling paths.

    ``venue_fee`` is parked as the record ``_record_venue_fee`` would
    have written, so ``_settled_sale_proceeds`` runs for real.
    """
    bot = object.__new__(ScrummingBot)
    bot.bot_id = "net-path-bot"
    bot.seen = {}
    bot._bus = _PathBus()
    bot.config = _Config(symbol="CHIP/USD", trading_fee_pct=trading_fee_pct)
    bot.config.scrum_fold_pct = 100
    bot.config.profit_folding_active = True
    bot.config.manual_fire_dust_band = 0.0
    bot.stats = _Stats()
    bot.stats.total_scrummed_usd = 0.0
    bot._fold_tranches = []
    bot._main_lots = [dict(lot) for lot in PATH_LOTS]
    bot._quote_to_usd = 1.0
    bot._last_sell_venue_fee = (
        SettledSellFee(
            units=UNITS,
            price=PRICE,
            fee_amount=venue_fee,
            currency=fee_currency,
            reported=True,
        )
        if venue_fee is not None
        else None
    )
    bot._tranches_created_lifetime = 0
    bot._tranches_discarded_lifetime = 0
    bot._tranches_closed_lifetime = 0
    bot._scrum_sells_lifetime = 0
    bot._last_trend_bull_candles = 0
    bot._fold_queue_usd = 0.0
    bot._fold_queue_ref_price = 0.0
    bot._fold_cycle_cap_consumed = 0.0
    bot._pending_wire_credits = 0.0
    bot._standing_surplus_usd = 0.0
    bot._below_min_scrum_log_ts = 0.0
    bot._scrum_target_mode = "search"
    bot._scrum_target_side = None
    bot._dist_accumulator = 0.0
    bot._manual_fire_pending = True
    bot._last_trade_side = None
    bot._last_trade_price = 0.0
    bot._last_bb = _PathBB()
    bot._current_holdings = UNITS
    bot._target_balance = 0.0
    bot._anchor_target_balance = 0.0

    def _route(scrum_usd, sell_fill, label):
        bot.seen.setdefault("routed", []).append((scrum_usd, sell_fill, label))
        return 0.0

    def _recorder(key):
        def _inner(*args, **kwargs):
            bot.seen.setdefault(key, []).append((args, kwargs))

        return _inner

    bot._route_scrum_proceeds_via_wires = _route
    bot._emit_trade_fire_snapshot = _recorder("fire_snapshots")
    bot._emit_voting_panel_snapshot_at_fire = _recorder("snapshots")
    bot._emit_gate_decision_at_fire = _recorder("gates")
    bot._reset_opposing_hysteresis_after_fill = _recorder("disarms")
    bot.note_scrum_retention_usd = _recorder("retained")
    bot._emit_trade_notification = _recorder("notifications")

    async def _limits(symbol):
        bot.seen.setdefault("limits", []).append(symbol)
        return 0.0, 0.0, 0.0

    async def _sell(amount, price_arg, summary):
        bot.seen.setdefault("sold", []).append((amount, price_arg, summary))
        return PRICE

    async def _balance(currency):
        bot.seen.setdefault("balances", []).append(currency)
        _held = bot._current_holdings
        return type("B", (), {"total": _held, "free": _held, "absent": False})()

    async def _refresh():
        return 1.0

    async def _place(**kwargs):
        bot.seen["placed"] = kwargs
        return _Order(price=PRICE, filled=UNITS)

    async def _settled(order, symbol, requested, tick_price):
        bot.seen["settled"] = (order.id, symbol, requested, tick_price)
        return requested, PRICE, True

    bot._get_market_limits = _limits
    bot._execute_sell = _sell
    bot._get_balance = _balance
    bot._refresh_quote_to_usd = _refresh
    bot.guarded_place_order = _place
    bot._settled_fill = _settled
    return bot


def _fire_scrum(bot):
    asyncio.run(
        bot._tick_execute_scrum(
            _PathTicker(PRICE),
            _Summary(),
            _PathBB(),
            -UNITS * PRICE,
            -1.0,
            0.0,
            0.5,
            type("D", (), {"name": "BEARISH"})(),
            0.9,
            0.5,
            0.0,
            None,
        )
    )


def _fire_dist(bot):
    bot._dist_accumulator = UNITS
    asyncio.run(bot._tick_distribute(_PathTicker(PRICE), _Summary(), _PathBB(), True))


def _fire_manual(bot):
    asyncio.run(bot._execute_manual_rebalance(_PathTicker(PRICE), "manual_button"))


PATHS = {"DIST": _fire_dist, "MANUAL": _fire_manual, "SCRUM": _fire_scrum}
PATH_NAMES = sorted(PATHS)


def _queued(bot):
    return sum(float(t["usd"]) for t in bot._fold_tranches)


@pytest.mark.parametrize("path", PATH_NAMES)
def test_every_selling_path_queues_the_net_the_venue_credited(path):
    """Red means a build loop queued the gross notional again."""
    bot = _path_bot(venue_fee=VENUE_FEE)
    PATHS[path](bot)
    booked = _queued(bot)
    assert booked > 0.0, f"{path} queued nothing; that is not a fix"
    assert _round(booked) == NET, (
        f"{path} queued ${booked:.5f}; the venue credited ${NET:.5f} "
        f"for {UNITS} @ ${PRICE}"
    )
    assert _round(booked) != GROSS, (
        f"{path} queued the gross notional ${GROSS:.5f}, which the "
        f"venue did not credit"
    )


@pytest.mark.parametrize("path", PATH_NAMES)
def test_control_a_path_with_no_reported_fee_queues_the_gross(path):
    """CONTROL. Red means the net above came from somewhere other than
    the venue's record, so the check cannot tell the two apart."""
    bot = _path_bot(venue_fee=None)
    PATHS[path](bot)
    booked = _queued(bot)
    assert _round(booked) == GROSS, (
        f"{path} queued ${booked:.5f} with no fee reported; the gross "
        f"${GROSS:.5f} is the only figure it can honestly book"
    )
    assert any("BOOKED GROSS" in m for m in bot._bus.messages), (
        f"{path} booked the gross and did not say so: " f"{bot._bus.messages}"
    )


@pytest.mark.parametrize("path", PATH_NAMES)
@pytest.mark.parametrize("configured", [0.0, 1.2, 1.6, 9.9])
def test_the_configured_rate_never_moves_what_a_path_queues(path, configured):
    """Red means a path started deriving the fee from the config."""
    bot = _path_bot(venue_fee=VENUE_FEE, trading_fee_pct=configured)
    PATHS[path](bot)
    booked = _queued(bot)
    assert _round(booked) == NET, (
        f"{path} queued ${booked:.5f} with trading_fee_pct={configured}; "
        f"the venue's ${NET:.5f} must not move with the config"
    )
    assert _round(booked) != SYNTHESISED


def test_control_the_configured_rate_would_give_a_different_answer():
    """Red means the sweep above proves nothing, because the configured
    rate and the venue's agree on this trade."""
    assert _round(GROSS * (1 - CONFIG_FEE_PCT / 100.0)) == SYNTHESISED
    assert SYNTHESISED != NET


@pytest.mark.parametrize("path", PATH_NAMES)
def test_a_fee_in_the_base_currency_never_reaches_a_tranche(path):
    """Red means a CHIP-denominated fee was subtracted from USD."""
    bot = _path_bot(venue_fee=VENUE_FEE, fee_currency="CHIP")
    PATHS[path](bot)
    assert _round(_queued(bot)) == GROSS
    assert any(
        "not the USD this sale is credited in" in m for m in bot._bus.messages
    ), f"{path} refused the foreign-currency fee without saying why"


@pytest.mark.parametrize("path", PATH_NAMES)
def test_a_fee_larger_than_the_sale_never_reaches_a_tranche(path):
    """Red means an absurd fee can drive a tranche to zero or below."""
    bot = _path_bot(venue_fee=GROSS * 2.0)
    PATHS[path](bot)
    assert _round(_queued(bot)) == GROSS
    assert any("is not smaller than the gross" in m for m in bot._bus.messages)


def test_a_detonation_still_values_its_sale_at_the_gross():
    """The standing record of where the gross notional remains.

    ``_execute_detonation`` clears ``_fold_tranches`` rather than
    building one, so its valuation reaches no tranche; this reads the
    figure it publishes on ``trade.filled``.
    """
    bot = _path_bot(venue_fee=VENUE_FEE)
    bot._anchor_target_balance = 0.0
    asyncio.run(bot._execute_detonation(_PathTicker(PRICE)))
    filled = [
        kwargs
        for topic, kwargs in _bus_events(bot)
        if topic == "trade.filled" and kwargs.get("data", {}).get("type")
    ]
    assert filled, "the detonation published no trade.filled"
    assert _round(filled[-1]["data"]["usd"]) == GROSS
    assert bot._fold_tranches == []


def _bus_events(bot):
    return bot._bus.events
