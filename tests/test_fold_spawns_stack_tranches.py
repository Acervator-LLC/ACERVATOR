"""A fold spawns stack tranches, the mirror of the scrum that opens them.

``_execute_buy`` calls ``_open_stack_from_scrum`` on a filled fold, so
``bot._stack_tranches`` gains a ladder anchored on the FILL price and starting at
the minimum opposing distance. Each verdict is one ``_check_*`` oracle, and
``TestPlantedFailures`` runs the same oracle against a broken mechanism and
requires it to go red. The ladder's own arithmetic belongs to
``test_stack_math.py``; nothing here asserts a spacing number.
"""

import asyncio
import inspect

import pytest

from src.trading import stack_math
from src.trading.scrumming_bot import ScrummingBot

FOLD_PRICE = 100.0
FOLD_SIZE = 30.0
# The stub's scrumming_interval_pct + trading_fee_pct.
MIN_OPPOSING_PCT = 1.6
# `_StubConfig` sets no `split_distance`, so `_open_stack_from_scrum` takes its default.
OPENER_GAP_PCT = 1.0


class _StubExchangeInterface:
    def __init__(self, min_order_size: float = 0.0):
        self.min_order_size = min_order_size


class _StubConfig:
    def __init__(self, **kwargs: object) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


class _StubBus:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []

    def emit(self, event: str, **kwargs: object) -> None:
        self.messages.append((event, dict(kwargs)))


class _StubOrder:
    def __init__(self, price: float):
        self.id = "stub-buy-order-1"
        self.average = price
        self.price = price


class _StubStats:
    def __init__(self) -> None:
        self.verify_samples = 0
        self.verify_clean = 0
        self.verify_adjusted = 0
        self.verify_canceled = 0
        self.total_buys = 0
        self.total_trades = 0
        self.trade_volume = 0.0
        self.last_trade_time = 0.0
        self.ytd_folded_usd = 0.0


class _StubExchange:
    """No open orders, so the P0b stacked-BUY guard stays permissive."""

    def __init__(self) -> None:
        self.open_order_queries: list[str] = []
        self.ohlcv_queries: list[str] = []

    async def get_open_orders(self, symbol: str) -> list:
        self.open_order_queries.append(symbol)
        return []

    async def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> list:
        """A flat tape long enough for the detonation trigger to grade."""
        self.ohlcv_queries.append(f"{symbol}:{timeframe}:{limit}")
        return [
            [1_800_000_000_000 + i * 60_000, 100.0, 101.0, 99.0, 100.0, 10.0]
            for i in range(limit)
        ]


class _Summary:
    consensus_direction = "buy"
    consensus_confidence = 0.75


class _SpawnStubBot:
    """Minimum surface ``_spawn_stack_from_fold`` and the opener read."""

    def __init__(self, **cfg_overrides: object) -> None:
        self.bot_id = "spawn-stub"
        settings: dict[str, object] = {
            "symbol": "ETH/USD",
            "target_asset": "ETH",
            "scrumming_interval_pct": 1.0,
            "trading_fee_pct": 0.6,
            "stack_mode": True,
            "stack_tranche_count_target": 3,
            "stack_spacing_mode": "linear",
        }
        settings.update(cfg_overrides)
        self.config = _StubConfig(**settings)
        self.exchange_interface = _StubExchangeInterface()
        self._bus = _StubBus()
        self._stack_tranches: list[dict] = []
        self._stack_created = 0
        self._invisible = True
        self._aggressive = False

    async def _open_stack_from_scrum(self, **kwargs: object) -> int:
        """Delegate to the REAL opener.

        Without this the stub would answer with a mock and every test
        would pass against an implementation that opens nothing.
        """
        return await ScrummingBot._open_stack_from_scrum(self, **kwargs)

    def log_messages(self) -> list[str]:
        return [str(kwargs.get("message", "")) for _, kwargs in self._bus.messages]


class _BuyStubBot(_SpawnStubBot):
    """Adds the surface the REAL ``_execute_buy`` reads, with every gate
    of its own set permissive, so a fold reaches the spawn site."""

    def __init__(self, **cfg_overrides: object) -> None:
        settings: dict[str, object] = {
            "max_entry_price": None,
            "min_entry_price": None,
            "max_target_growth_pct": 1.0,
            "position_ceiling_enabled": False,
        }
        settings.update(cfg_overrides)
        super().__init__(**settings)
        self.exchange = _StubExchange()
        self.stats = _StubStats()
        self._hyst_armed_fold_side = False
        self._hyst_ref_fold_side = 0.0
        self._current_holdings = 0.0
        self._target_balance = 1000.0
        self._anchor_target_balance = 1000.0
        self._quote_to_usd = 1.0
        self._initialised = True
        self._fold_tranches: list[dict] = []
        self._main_lots: list[dict] = []
        self._memorised_trades: list = []
        self._hedge_bal = 0.0
        self.placed_orders: list[dict] = []
        self.notifications: list[tuple] = []
        self.reconcile_reasons: list[str] = []
        self.spawn_calls: list[dict] = []
        # `fill_ratio` keeps the fill off the offer, so the anchor checks discriminate.
        self.offered_price = FOLD_PRICE
        self.fill_ratio = 0.97

    async def _verify_buy_safe_or_refuse(self, path: str = "") -> tuple[float, str]:
        """Report units known and no refusal, so the buy is not held back."""
        self.reconcile_reasons.append(f"verify:{path}")
        return 0.0, ""

    def _emit_trade_notification(self, kind: str, state: str, detail: str) -> None:
        self.notifications.append((kind, state, detail))

    async def guarded_place_order(self, symbol, side, order_type, amount, price):
        self.placed_orders.append(
            {
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "amount": amount,
                "price": price,
            }
        )
        # Invisible mode sends MARKET with price=None, so the fill comes from the offer.
        return _StubOrder(self.offered_price * self.fill_ratio)

    async def _reconcile_holdings(self, reason: str = "") -> None:
        self.reconcile_reasons.append(f"reconcile:{reason}")

    async def _spawn_stack_from_fold(self, **kwargs: object) -> int:
        """Delegate to the REAL spawn. Recorded so a test can prove
        ``_execute_buy`` reached it with the arguments it claims."""
        self.spawn_calls.append(dict(kwargs))
        return await ScrummingBot._spawn_stack_from_fold(self, **kwargs)


def _spawn(bot, **kwargs):
    """Drive the REAL ``_spawn_stack_from_fold`` on a stub."""
    return asyncio.run(ScrummingBot._spawn_stack_from_fold(bot, **kwargs))


def _terminal_bot(**overrides):
    """A ``_TerminalStubBot`` holding a position above its anchor."""
    bot = _TerminalStubBot(**overrides)
    bot.offered_price = FOLD_PRICE
    return bot


def _sell(bot, amount, price):
    """Drive the REAL ``_execute_sell`` on a stub."""
    return asyncio.run(
        ScrummingBot._execute_sell(bot, amount=amount, price=price, summary=_Summary())
    )


def _buy(bot, cost, price, path):
    """Drive the REAL ``_execute_buy`` on a stub."""
    bot.offered_price = price
    return asyncio.run(
        ScrummingBot._execute_buy(
            bot,
            cost=cost,
            price=price,
            summary=_Summary(),
            trace_context={"path": path},
        )
    )


class _Ticker:
    def __init__(self, last):
        self.last = last


class _TerminalStubBot(_BuyStubBot):
    """A bot whose buy executor and both openers record every call.

    ``terminal_calls`` names the ones a driven method reached, so a run
    that opened a tranche is visible without reading any source.
    """

    def __init__(self, **cfg_overrides: object) -> None:
        super().__init__(**cfg_overrides)
        self.terminal_calls: list[str] = []
        self.sold: list[dict] = []
        self.state = None
        self._standing_surplus_usd = 0.0
        self._retained_this_cycle_usd = 0.0
        self._last_sell_venue_fee = None
        self._scrum_sells_lifetime = 0
        self._current_holdings = 20.0
        self._anchor_target_balance = 1000.0
        self._detonation_last_check_ts = 0.0
        self._detonation_last_signal_bullish = False
        self._fold_queue_usd = 0.0
        self._tranches_closed_lifetime = 0

    def _reset_opposing_hysteresis_after_fill(self, *args: object) -> None:
        del args

    def _emit_voting_panel_snapshot_at_fire(self, *args: object, **kw: object) -> None:
        del args, kw

    def _emit_gate_decision_at_fire(self, *args: object, **kw: object) -> None:
        del args, kw

    def _route_scrum_proceeds_via_wires(self, *args: object, **kwargs: object):
        del args, kwargs
        return 0.0

    def note_scrum_retention_usd(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    async def _execute_buy(self, **kwargs: object):
        self.terminal_calls.append("_execute_buy")
        return await ScrummingBot._execute_buy(self, **kwargs)

    async def _open_stack_from_scrum(self, **kwargs: object) -> int:
        self.terminal_calls.append("_open_stack_from_scrum")
        return await ScrummingBot._open_stack_from_scrum(self, **kwargs)

    async def _spawn_stack_from_fold(self, **kwargs: object) -> int:
        self.terminal_calls.append("_spawn_stack_from_fold")
        self.spawn_calls.append(dict(kwargs))
        return await ScrummingBot._spawn_stack_from_fold(self, **kwargs)

    async def guarded_place_order(self, symbol, side, order_type, amount, price):
        _side = getattr(side, "value", side)
        if _side == "sell":
            self.sold.append({"amount": amount, "price": price})
        return await _BuyStubBot.guarded_place_order(
            self, symbol, side, order_type, amount, price
        )

    async def _get_balance(self, currency: str):
        units = self._current_holdings if currency == "ETH" else 1_000_000.0
        return type("B", (), {"total": units, "free": units, "absent": False})()

    async def _get_ticker(self, _symbol: str):
        return _Ticker(self.offered_price)

    async def _refresh_quote_to_usd(self) -> float:
        return 1.0

    async def _settled_fill(self, order, symbol_, requested, tick_price):
        del order, symbol_, tick_price
        return requested, self.offered_price * self.fill_ratio, True

    def _record_venue_fee(self, *args: object, **kwargs: object) -> None:
        del args, kwargs


def _check_gate_withheld_the_spawn(opened: int, tranches: list[dict]) -> None:
    assert opened == 0, f"stack_mode was off but {opened} tranches opened"
    assert tranches == [], f"stack_mode was off but the ledger holds {tranches}"


def _check_only_a_fold_spawned(opened: int, tranches: list[dict]) -> None:
    assert opened == 0, f"a non-fold path opened {opened} tranches"
    assert tranches == [], "a non-fold path populated the stack ledger"


def _check_ladder_is_a_sell_side_above(
    anchor_price: float, prices: list[float]
) -> None:
    assert prices, "no ladder at all"
    assert prices == sorted(prices), f"ladder is not ascending: {prices}"
    assert all(p > anchor_price for p in prices), (
        f"a fold-spawned stack must sell ABOVE the fold at "
        f"{anchor_price}; got {prices}"
    )


def _check_spacing_mode_reached_the_ladder(
    linear_prices: list[float], quad_prices: list[float]
) -> None:
    assert linear_prices != quad_prices, (
        "the fold spawn ignored stack_spacing_mode -- two different "
        "modes produced the same ladder"
    )


def _check_anchored_on_the_fill(spawned_anchor: float, fill_price: float) -> None:
    assert spawned_anchor == fill_price, (
        f"the ladder was anchored on {spawned_anchor} but the fold "
        f"filled at {fill_price}"
    )


def _check_terminal_never_reaches_the_buy_executor(calls: set[str]) -> None:
    assert "_execute_buy" not in calls
    assert "_spawn_stack_from_fold" not in calls
    assert "_open_stack_from_scrum" not in calls


def _check_sell_still_spawns_fold_tranches(calls: set[str]) -> None:
    assert "_open_stack_from_scrum" in calls, "_execute_sell lost its stack intercept"
    assert "_spawn_stack_from_fold" not in calls, (
        "the fold spawn leaked onto the sell path -- that opens a stack "
        "on top of a stack"
    )


def _check_the_fill_survived(fill, messages: list[str]) -> None:
    assert (
        fill is not None and fill > 0
    ), "a bookkeeping spawn was allowed to fail a filled trade"
    assert not any(
        "BUY FAILED" in m for m in messages
    ), "the buy reported failure after it had already filled"


class TestTheHarnessCanSeeASpawn:
    def test_the_stub_reaches_the_real_opener(self):
        bot = _SpawnStubBot()
        opened = asyncio.run(
            ScrummingBot._open_stack_from_scrum(
                bot, scrum_price=FOLD_PRICE, scrum_size=FOLD_SIZE
            )
        )
        assert opened == 3
        assert len(bot._stack_tranches) == 3

    def test_execute_buy_reaches_the_spawn_site(self):
        bot = _BuyStubBot()
        fill = _buy(bot, cost=100.0, price=FOLD_PRICE, path="fold_rebuy")
        assert (
            fill is not None and fill > 0
        ), f"the buy stub never filled; logs: {bot.log_messages()}"
        assert bot.spawn_calls, (
            "_execute_buy did not call _spawn_stack_from_fold at all -- "
            "every no-spawn assertion below would be vacuous"
        )

    def test_the_call_recorder_is_not_blind(self):
        """POSITIVE CONTROL: the same recorder that reports zero on a
        terminal action sees ``_open_stack_from_scrum`` on a real sell."""
        bot = _TerminalStubBot()
        _sell(bot, amount=FOLD_SIZE, price=FOLD_PRICE)
        assert "_open_stack_from_scrum" in bot.terminal_calls

    def test_the_fill_is_distinguishable_from_the_offer(self):
        """THE CONTROL THAT WAS MISSING, and its absence was measured.

        With the stub filling at exactly the price it was offered, an
        anchor read from the offer and an anchor read from the fill are
        the same number. Mutating `_execute_buy` to hand the spawn
        `price` instead of `actual_fill` left this entire file green.
        The anchor check is only evidence while these two differ.
        """
        bot = _BuyStubBot()
        fill = _buy(bot, cost=100.0, price=FOLD_PRICE, path="fold_rebuy")
        assert fill != FOLD_PRICE, (
            "the stub fills at the offered price, so the anchor check "
            "cannot tell the two apart and proves nothing"
        )
        assert bot.spawn_calls, "no spawn to read an anchor from"


# THE UNIT: a fold spawns stack tranches.


class TestAFoldSpawnsStackTranches:
    def test_a_fold_spawns_when_the_gate_allows(self):
        bot = _SpawnStubBot(stack_mode=True)
        opened = _spawn(
            bot,
            fold_price=FOLD_PRICE,
            fold_size=FOLD_SIZE,
            summary=_Summary(),
            path="fold_rebuy",
        )
        assert opened == 3
        assert len(bot._stack_tranches) == 3
        assert bot._stack_created == 3

    def test_the_spawned_tranches_are_a_SELL_ladder_ABOVE_the_fold(self):
        """A fold buys; the ladder it spawns sells higher. That is what
        closes the pair."""
        bot = _SpawnStubBot()
        _spawn(
            bot,
            fold_price=FOLD_PRICE,
            fold_size=FOLD_SIZE,
            summary=_Summary(),
            path="fold_rebuy",
        )
        _check_ladder_is_a_sell_side_above(
            FOLD_PRICE, [t["price"] for t in bot._stack_tranches]
        )

    def test_the_anchor_is_one_min_opposing_distance_above_the_fold(self):
        """ "...starting at the minimum opposing trade distance."

        The opener reads that distance as
        ``scrumming_interval_pct + trading_fee_pct``, 1.6% here, and
        stack_math puts level 1 one initial gap above the anchor. Both
        factors are asserted separately, so a change to either is caught
        on its own instead of hiding inside one product.
        """
        bot = _SpawnStubBot()
        _spawn(
            bot,
            fold_price=FOLD_PRICE,
            fold_size=FOLD_SIZE,
            summary=_Summary(),
            path="fold_rebuy",
        )
        anchor = FOLD_PRICE * (1.0 + MIN_OPPOSING_PCT / 100.0)
        assert anchor == pytest.approx(101.6, rel=1e-12)
        assert bot._stack_tranches[0]["price"] == pytest.approx(
            anchor * (1.0 + OPENER_GAP_PCT / 100.0), rel=1e-9
        )

    def test_the_anchor_is_the_FILL_price_not_the_offered_price(self):
        bot = _BuyStubBot()
        fill = _buy(bot, cost=100.0, price=FOLD_PRICE, path="fold_rebuy")
        _check_anchored_on_the_fill(bot.spawn_calls[0]["fold_price"], fill)

    def test_the_spawn_size_is_the_units_the_fold_booked(self):
        """The ladder sells back WHAT THE LEDGER HOLDS.

        `_execute_buy` sizes the order as `cost / price` and credits
        exactly that to `_current_holdings`; it does NOT re-derive units
        from the fill it later reads back. So the spawn must be sized on
        the booked amount. Sizing it on `cost / actual_fill` would put
        rungs against units the ledger never recorded -- measured here
        as 2.577 against a booked 2.5 on a 3% slip.

        (That `_execute_buy` books pre-slip units at all is an existing
        property of the buy executor, not something this unit changes.
        It is read here, not asserted as correct.)
        """
        bot = _BuyStubBot()
        _buy(bot, cost=250.0, price=FOLD_PRICE, path="fold_rebuy")
        booked = bot.placed_orders[-1]["amount"]
        assert bot.spawn_calls[0]["fold_size"] == pytest.approx(booked, rel=1e-12), (
            "the ladder must sell back the base units the buy booked, "
            "not the USD it spent and not a re-derived number"
        )
        assert booked != 250.0, "USD and units must differ here or this check is blind"

    def test_the_tranche_records_that_a_fold_opened_it(self):
        bot = _SpawnStubBot()
        _spawn(
            bot,
            fold_price=FOLD_PRICE,
            fold_size=FOLD_SIZE,
            summary=_Summary(),
            path="fold_rebuy",
        )
        assert all(t["origin"] == "fold" for t in bot._stack_tranches)

    def test_a_scrum_opened_stack_still_records_scrum(self):
        """The default keeps every existing caller unchanged."""
        bot = _SpawnStubBot()
        asyncio.run(
            ScrummingBot._open_stack_from_scrum(
                bot, scrum_price=FOLD_PRICE, scrum_size=FOLD_SIZE
            )
        )
        assert all(t["origin"] == "scrum" for t in bot._stack_tranches)

    def test_a_series_of_folds_spawns_a_series_of_tranches(self):
        """ "Bear Trends will spawn multiple Stack Tranches in a series."

        Each fold ADDS to the ledger; a later fold does not replace an
        earlier fold's rungs.
        """
        bot = _SpawnStubBot()
        _spawn(
            bot,
            fold_price=FOLD_PRICE,
            fold_size=FOLD_SIZE,
            summary=_Summary(),
            path="fold_rebuy",
        )
        _spawn(
            bot,
            fold_price=90.0,
            fold_size=FOLD_SIZE,
            summary=_Summary(),
            path="fold_rebuy",
        )
        assert len(bot._stack_tranches) == 6
        assert bot._stack_created == 6


class TestTheGateIsInherited:
    def test_a_fold_spawns_none_when_stack_mode_is_off(self):
        bot = _SpawnStubBot(stack_mode=False)
        opened = _spawn(
            bot,
            fold_price=FOLD_PRICE,
            fold_size=FOLD_SIZE,
            summary=_Summary(),
            path="fold_rebuy",
        )
        _check_gate_withheld_the_spawn(opened, bot._stack_tranches)
        assert bot._stack_created == 0

    def test_stack_mode_off_is_the_shipping_state_end_to_end(self):
        """Through the real `_execute_buy`, not just the helper. The buy
        must still fill; only the spawn is withheld."""
        bot = _BuyStubBot(stack_mode=False)
        fill = _buy(bot, cost=100.0, price=FOLD_PRICE, path="fold_rebuy")
        _check_the_fill_survived(fill, bot.log_messages())
        _check_gate_withheld_the_spawn(0, bot._stack_tranches)

    def test_a_missing_stack_mode_attribute_spawns_none(self):
        bot = _SpawnStubBot()
        delattr(bot.config, "stack_mode")
        opened = _spawn(
            bot,
            fold_price=FOLD_PRICE,
            fold_size=FOLD_SIZE,
            summary=_Summary(),
            path="fold_rebuy",
        )
        _check_gate_withheld_the_spawn(opened, bot._stack_tranches)


class TestOnlyAFoldSpawns:
    """The accepted set, one row per partition. Closed and finite."""

    @pytest.mark.parametrize("path", ["fold_rebuy", "manual_tranche_fire"])
    def test_the_fold_paths_spawn(self, path):
        bot = _SpawnStubBot()
        assert (
            _spawn(
                bot,
                fold_price=FOLD_PRICE,
                fold_size=FOLD_SIZE,
                summary=_Summary(),
                path=path,
            )
            == 3
        )

    @pytest.mark.parametrize(
        "path",
        [
            "zero_balance_initial_entry",
            "hedge_replenish",
            "unspecified",
            "",
            "FOLD_REBUY",
            "fold_rebuy ",
        ],
    )
    def test_every_other_path_spawns_nothing(self, path):
        bot = _SpawnStubBot()
        opened = _spawn(
            bot,
            fold_price=FOLD_PRICE,
            fold_size=FOLD_SIZE,
            summary=_Summary(),
            path=path,
        )
        _check_only_a_fold_spawned(opened, bot._stack_tranches)

    def test_an_entry_through_the_real_executor_spawns_nothing(self):
        bot = _BuyStubBot()
        fill = _buy(
            bot, cost=100.0, price=FOLD_PRICE, path="zero_balance_initial_entry"
        )
        _check_the_fill_survived(fill, bot.log_messages())
        _check_only_a_fold_spawned(0, bot._stack_tranches)

    def test_a_hedge_through_the_real_executor_spawns_nothing(self):
        bot = _BuyStubBot()
        bot._hedge_bal = 500.0
        fill = _buy(bot, cost=100.0, price=FOLD_PRICE, path="hedge_replenish")
        _check_the_fill_survived(fill, bot.log_messages())
        _check_only_a_fold_spawned(0, bot._stack_tranches)


class TestTerminalActionsSpawnNothing:
    """ "Detonations and Self-Destruct actions do not spawn or populate
    tranches. These two are considered terminal actions."

    They are terminal by CONSTRUCTION, not by a check: neither reaches
    `_execute_buy`. These assert that construction, so a future edit
    routing a terminal action through the buy executor is caught here
    rather than in a live account.
    """

    def test_a_detonation_sells_and_opens_nothing(self):
        bot = _terminal_bot()
        asyncio.run(ScrummingBot._execute_detonation(bot, _Ticker(FOLD_PRICE)))
        assert bot.sold, (
            f"the detonation placed no sell, so the zero below means "
            f"nothing; logs: {bot.log_messages()}"
        )
        _check_terminal_never_reaches_the_buy_executor(set(bot.terminal_calls))
        assert bot._stack_tranches == []

    def test_a_self_destruct_sells_and_opens_nothing(self):
        bot = _terminal_bot()
        answer = asyncio.run(ScrummingBot.self_destruct(bot, "SELF-DESTRUCT"))
        assert answer["ok"] is True, answer
        assert bot.sold, f"self_destruct placed no sell; logs: {bot.log_messages()}"
        _check_terminal_never_reaches_the_buy_executor(set(bot.terminal_calls))
        assert bot._stack_tranches == []

    def test_a_detonation_check_reads_candles_and_opens_nothing(self):
        bot = _terminal_bot(detonation_enabled=True)
        asyncio.run(ScrummingBot._check_detonation_trigger(bot, _Ticker(FOLD_PRICE)))
        assert bot.exchange.ohlcv_queries, (
            f"the trigger never reached the candle fetch, so it proves "
            f"nothing; logs: {bot.log_messages()}"
        )
        _check_terminal_never_reaches_the_buy_executor(set(bot.terminal_calls))
        assert bot._stack_tranches == []

    def test_a_terminal_label_handed_to_the_spawn_is_refused(self):
        """Belt as well as braces: even if a future path did route a
        terminal action here, its label is not in the accepted set."""
        bot = _SpawnStubBot()
        for label in ("AUTO_DETONATION", "SELF_DESTRUCT", "detonation"):
            opened = _spawn(
                bot,
                fold_price=FOLD_PRICE,
                fold_size=FOLD_SIZE,
                summary=_Summary(),
                path=label,
            )
            _check_only_a_fold_spawned(opened, bot._stack_tranches)


class TestTheSpawnFollowsTheConfiguredSpacing:
    """ROUTING ONLY. That the fold spawn goes through the configured
    spacing mode -- never what any mode's numbers should be. Those
    belong to item 6 and are pinned by test_stack_math.py and
    test_ladder_spacing_modes.py, which this file does not duplicate.
    """

    @staticmethod
    def _ladder(mode: str) -> list[float]:
        bot = _SpawnStubBot(stack_spacing_mode=mode)
        _spawn(
            bot,
            fold_price=FOLD_PRICE,
            fold_size=FOLD_SIZE,
            summary=_Summary(),
            path="fold_rebuy",
        )
        return [t["price"] for t in bot._stack_tranches]

    def test_two_modes_give_two_different_ladders_from_one_fold(self):
        _check_spacing_mode_reached_the_ladder(
            self._ladder("linear"), self._ladder("quadratic")
        )

    def test_the_ladder_is_the_one_stack_math_computes(self):
        """Read against the item-6 helper itself, so the spawn cannot
        drift onto arithmetic of its own."""
        expected = stack_math.scrum_ladder_prices(
            trigger_price=FOLD_PRICE,
            levels=3,
            initial_gap_pct=OPENER_GAP_PCT,
            spacing_mode="quadratic",
            min_opposing_pct=MIN_OPPOSING_PCT,
        )
        assert self._ladder("quadratic") == pytest.approx(expected, rel=1e-12)

    def test_an_unknown_spacing_mode_spawns_nothing_and_says_so(self):
        bot = _SpawnStubBot(stack_spacing_mode="not-a-mode")
        opened = _spawn(
            bot,
            fold_price=FOLD_PRICE,
            fold_size=FOLD_SIZE,
            summary=_Summary(),
            path="fold_rebuy",
        )
        _check_only_a_fold_spawned(opened, bot._stack_tranches)
        assert any("STACK OPEN FAILED" in m for m in bot.log_messages())


class TestTheSellSideIsUnchanged:
    """The half that already worked must still work. Regression only --
    the sell path's own behaviour is pinned by its own files, which are
    run by name as a regression check rather than re-asserted here.
    """

    def test_execute_sell_still_spawns_the_way_it_did(self):
        bot = _TerminalStubBot()
        _sell(bot, amount=FOLD_SIZE, price=FOLD_PRICE)
        _check_sell_still_spawns_fold_tranches(set(bot.terminal_calls))

    def test_the_opener_keeps_its_old_arity_for_old_callers(self):
        """`origin` must be optional, or every existing caller breaks."""
        sig = inspect.signature(ScrummingBot._open_stack_from_scrum)
        assert sig.parameters["origin"].default == "scrum"


class TestTheSpawnCannotFailTheTrade:
    """A bookkeeping spawn must never turn a filled buy into a reported
    failure. The call site sits inside `_execute_buy`'s try block, whose
    handler emits BUY FAILED and returns None.
    """

    def test_a_raising_opener_still_leaves_the_buy_filled(self):
        bot = _BuyStubBot()
        reached: list[dict] = []

        async def _boom(**kwargs: object) -> int:
            reached.append(dict(kwargs))
            raise RuntimeError("opener exploded")

        bot._open_stack_from_scrum = _boom
        fill = _buy(bot, cost=100.0, price=FOLD_PRICE, path="fold_rebuy")
        assert reached, (
            "the planted raise was never reached, so a green result here "
            "says nothing about the handler"
        )
        _check_the_fill_survived(fill, bot.log_messages())
        assert any("FOLD STACK SPAWN FAILED" in m for m in bot.log_messages())

    @pytest.mark.parametrize(
        "price,size",
        [
            (0.0, FOLD_SIZE),
            (-1.0, FOLD_SIZE),
            (FOLD_PRICE, 0.0),
            (FOLD_PRICE, -1.0),
            (None, FOLD_SIZE),
            (FOLD_PRICE, None),
        ],
    )
    def test_a_nonsense_fill_spawns_nothing_without_raising(self, price, size):
        bot = _SpawnStubBot()
        opened = _spawn(
            bot, fold_price=price, fold_size=size, summary=_Summary(), path="fold_rebuy"
        )
        _check_only_a_fold_spawned(opened, bot._stack_tranches)


async def _ungated_spawn(bot, fold_price, fold_size, summary, path):
    """The helper with its stack_mode gate deleted. Nothing else."""
    if path not in ("fold_rebuy", "manual_tranche_fire"):
        return 0
    return await bot._open_stack_from_scrum(
        scrum_price=float(fold_price),
        scrum_size=float(fold_size),
        summary=summary,
        origin="fold",
    )


async def _any_path_spawn(bot, fold_price, fold_size, summary, path):
    """The helper with its path predicate deleted. Nothing else."""
    if not getattr(bot.config, "stack_mode", False):
        return 0
    assert path is not None
    return await bot._open_stack_from_scrum(
        scrum_price=float(fold_price),
        scrum_size=float(fold_size),
        summary=summary,
        origin="fold",
    )


async def _leaky_spawn(bot, fold_price, fold_size, summary, path):
    """The helper with its try/except deleted, so a spawn failure
    escapes into `_execute_buy`'s handler."""
    if path not in ("fold_rebuy", "manual_tranche_fire"):
        return 0
    return await bot._open_stack_from_scrum(
        scrum_price=float(fold_price),
        scrum_size=float(fold_size),
        summary=summary,
        origin="fold",
    )


class TestPlantedFailures:
    def test_PLANT_a_spawn_that_ignores_stack_mode_goes_red(self):
        bot = _SpawnStubBot(stack_mode=False)
        opened = asyncio.run(
            _ungated_spawn(bot, FOLD_PRICE, FOLD_SIZE, _Summary(), "fold_rebuy")
        )
        with pytest.raises(AssertionError):
            _check_gate_withheld_the_spawn(opened, bot._stack_tranches)

    def test_PLANT_a_spawn_on_a_non_fold_path_goes_red(self):
        bot = _SpawnStubBot()
        opened = asyncio.run(
            _any_path_spawn(
                bot, FOLD_PRICE, FOLD_SIZE, _Summary(), "zero_balance_initial_entry"
            )
        )
        with pytest.raises(AssertionError):
            _check_only_a_fold_spawned(opened, bot._stack_tranches)

    def test_PLANT_a_terminal_label_that_spawns_goes_red(self):
        bot = _SpawnStubBot()
        opened = asyncio.run(
            _any_path_spawn(bot, FOLD_PRICE, FOLD_SIZE, _Summary(), "AUTO_DETONATION")
        )
        with pytest.raises(AssertionError):
            _check_only_a_fold_spawned(opened, bot._stack_tranches)

    def test_PLANT_a_ladder_on_the_wrong_side_goes_red(self):
        """The spawn builds a FOLD ladder, below the buy, instead of a
        STACK ladder above it -- the wrong side of the pair."""
        wrong = stack_math.fold_ladder_prices(
            trigger_price=FOLD_PRICE,
            levels=3,
            initial_gap_pct=OPENER_GAP_PCT,
            spacing_mode="linear",
            min_opposing_pct=MIN_OPPOSING_PCT,
        )
        with pytest.raises(AssertionError):
            _check_ladder_is_a_sell_side_above(FOLD_PRICE, list(wrong))

    def test_PLANT_a_ladder_that_ignores_spacing_mode_goes_red(self):
        """Both modes hard-wired to linear."""
        hardwired = stack_math.scrum_ladder_prices(
            trigger_price=FOLD_PRICE,
            levels=3,
            initial_gap_pct=OPENER_GAP_PCT,
            spacing_mode="linear",
            min_opposing_pct=MIN_OPPOSING_PCT,
        )
        with pytest.raises(AssertionError):
            _check_spacing_mode_reached_the_ladder(list(hardwired), list(hardwired))

    def test_PLANT_an_anchor_on_the_offered_price_goes_red(self):
        """`_execute_buy` hands the spawn its OFFERED price while the
        exchange fills somewhere else.

        This is the plant that caught the real hole. It was green until
        the stub stopped filling at the price it was offered.
        """
        bot = _BuyStubBot()
        fill = _buy(bot, cost=100.0, price=FOLD_PRICE, path="fold_rebuy")
        assert fill != FOLD_PRICE, "the plant needs a slipped fill"
        with pytest.raises(AssertionError):
            _check_anchored_on_the_fill(FOLD_PRICE, fill)

    def test_PLANT_an_anchor_on_the_USD_cost_goes_red(self):
        """The spawn sized in dollars rather than base units."""
        bot = _BuyStubBot()
        fill = _buy(bot, cost=250.0, price=FOLD_PRICE, path="fold_rebuy")
        units = 250.0 / fill
        with pytest.raises(AssertionError):
            assert 250.0 == pytest.approx(units, rel=1e-9)

    def test_PLANT_a_terminal_routed_to_the_buy_executor_goes_red(self):
        with pytest.raises(AssertionError):
            _check_terminal_never_reaches_the_buy_executor(
                {"_execute_buy", "guarded_place_order"}
            )

    def test_PLANT_a_sell_that_lost_the_opener_goes_red(self):
        with pytest.raises(AssertionError):
            _check_sell_still_spawns_fold_tranches(
                {"guarded_place_order", "_emit_trade_notification"}
            )

    def test_PLANT_the_fold_spawn_leaking_onto_the_sell_path_goes_red(self):
        with pytest.raises(AssertionError):
            _check_sell_still_spawns_fold_tranches(
                {"_open_stack_from_scrum", "_spawn_stack_from_fold"}
            )

    def test_PLANT_a_spawn_that_fails_the_trade_goes_red(self):
        """The helper lets the exception escape, so `_execute_buy`
        reports BUY FAILED and returns None -- the fill is lost."""
        bot = _BuyStubBot()

        async def _boom(**kwargs: object) -> int:
            raise RuntimeError("opener exploded")

        async def _leaky(**kwargs: object) -> int:
            return await _leaky_spawn(bot, **kwargs)

        bot._open_stack_from_scrum = _boom
        bot._spawn_stack_from_fold = _leaky
        fill = _buy(bot, cost=100.0, price=FOLD_PRICE, path="fold_rebuy")
        assert any("BUY FAILED" in m for m in bot.log_messages()), (
            "the plant never reached _execute_buy's handler, so it " "proves nothing"
        )
        with pytest.raises(AssertionError):
            _check_the_fill_survived(fill, bot.log_messages())
