"""Item 7 -- A FOLD SPAWNS STACK TRANCHES.

Operator spec:
  "When a fold occurs, it should generate stack tranches and, when some
   or all of those tranches fill, the fold tranches spawn on the other
   side starting at the minimum opposing trade distance."
  "Scrum fires using existing Stack Tranches, Fold Tranches Spawn, Fold
   fires using existing Fold Tranches."

The sell half already worked. The buy half did not: an AST walk of the
two executors read ``_execute_sell -> ['_open_stack_from_scrum']`` and
``_execute_buy -> []``, so a fold closed no pair.

WHAT THIS FILE DOES NOT TEST. Merge, consumption, spacing arithmetic and
distribution are separate items with their own specs and their own test
files. Nothing here asserts a property of any of them. The spacing check
below tests only that the fold spawn ROUTES THROUGH the configured
mode -- that two modes give two ladders off the same fold -- never what
either mode's numbers should be. ``test_stack_math.py`` and
``test_ladder_spacing_modes.py`` own the numbers.

TWO-SIDED CONTROL. Every verdict here is read at the surface it reports
through: ``bot._stack_tranches``, the ledger a fold is supposed to fill,
and the fill price ``_execute_buy`` returns. Each oracle is written once
as a ``_check_*`` function, and ``TestPlantedFailures`` runs THE SAME
FUNCTION against a deliberately broken mechanism and requires it to go
red. A plant that re-asserted a hand-written constant instead of driving
the real oracle would prove nothing, so none of them do that.
"""

import ast
import asyncio
import inspect
import textwrap

import pytest

from src.trading import stack_math
from src.trading.scrumming_bot import ScrummingBot

FOLD_PRICE = 100.0
FOLD_SIZE = 30.0
# The stub's scrumming_interval_pct + trading_fee_pct.
MIN_OPPOSING_PCT = 1.6
# `_open_stack_from_scrum` reads `split_distance_pct` off the config.
# ScrummingBotConfig does not define that name -- it defines
# `split_distance` -- so the opener always takes its own 1.0 default.
# This stub deliberately does NOT define either one, so the ladder here
# is the ladder live would build. See the note in the return report.
OPENER_GAP_PCT = 1.0


# Stubs. Deliberately NOT ScrummingBot instances: each carries only the
# surface the method under test reads, so an accidental dependence on
# anything else surfaces as an AttributeError instead of passing.


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

    async def get_open_orders(self, symbol: str) -> list:
        self.open_order_queries.append(symbol)
        return []


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
        # THE FILL NEVER EQUALS THE OFFER, and that is load-bearing.
        # A stub that filled at exactly the price it was handed makes
        # "anchored on the fill" and "anchored on the offer" the same
        # number, so the anchor check would pass on either. Measured:
        # with the two equal, mutating `_execute_buy` to hand the spawn
        # the OFFERED price left this whole file green. They are kept
        # apart so that mutation goes red.
        self.offered_price = FOLD_PRICE
        self.fill_ratio = 0.97

    async def _verify_buy_safe_or_refuse(self, path: str = "") -> tuple[float, str]:
        """MEM-257 verification satisfied: units known, no refusal."""
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
        # Invisible mode sends MARKET with price=None, so the fill is
        # derived from the OFFERED price the test handed _execute_buy,
        # scaled by fill_ratio. See the fill_ratio note in __init__.
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


def _self_calls(func_name: str) -> set[str]:
    """Every ``self.<attr>()`` a named ScrummingBot method makes."""
    src = textwrap.dedent(inspect.getsource(getattr(ScrummingBot, func_name)))
    out: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ):
            out.add(node.func.attr)
    return out


# THE ORACLES. Written once, driven by the real tests below and by the
# planted failures at the bottom. A plant that ran a different assertion
# from the one it claims to control would be no control at all.


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


# POSITIVE CONTROLS ON THE HARNESS ITSELF.
#
# Everything below reads `bot._stack_tranches`. If the stub cannot reach
# the real opener, or `_execute_buy` cannot reach the spawn site, an
# empty ledger means "the harness is broken", not "the code refused" --
# and every no-spawn assertion in this file passes for the wrong reason.


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

    def test_the_call_reader_is_not_blind(self):
        """The known edge must be visible, or the terminal-path zeros
        and the sell-side regression check mean nothing."""
        assert "_open_stack_from_scrum" in _self_calls("_execute_sell")

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

    @pytest.mark.parametrize(
        "terminal",
        ["self_destruct", "_execute_detonation", "_check_detonation_trigger"],
    )
    def test_a_terminal_action_never_reaches_the_buy_executor(self, terminal):
        _check_terminal_never_reaches_the_buy_executor(_self_calls(terminal))

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
        _check_sell_still_spawns_fold_tranches(_self_calls("_execute_sell"))

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


# PLANTED FAILURES.
#
# Each one breaks the real mechanism and runs THE SAME `_check_*` oracle
# the corresponding test above runs, requiring it to go red. A check
# never observed failing is not evidence.


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
