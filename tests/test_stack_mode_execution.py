"""Stack Mode runtime path tests.

Behavioural tests that drive the real Stack Mode methods
(``_open_stack_from_scrum``, ``_reconcile_stack_tranches_invisible``,
``_spend_activated_stack_tranches``, ``_execute_sell``) on minimal stub
bots, without spinning up a full ScrummingBot.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class _StubExchangeInterface:
    """Just holds a min_order_size attribute for _open_stack_from_scrum."""

    def __init__(self, min_order_size=0.0):
        self.min_order_size = min_order_size


class _StubConfig:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _StubBus:
    def __init__(self):
        self.messages = []

    def emit(self, event, **kwargs):
        self.messages.append((event, kwargs))


class _StubBot:
    """Minimum surface _open_stack_from_scrum needs. NOT a ScrummingBot."""

    def __init__(self, **overrides):
        self.bot_id = "stub-bot"
        self.config = _StubConfig(
            scrumming_interval_pct=1.0,
            trading_fee_pct=0.6,
            stack_tranche_count_target=3,
            split_distance_pct=1.0,
            stack_spacing_mode="linear",
            stack_mode=True,
            **overrides,
        )
        self.exchange_interface = _StubExchangeInterface()
        self._bus = _StubBus()
        self._stack_tranches: list[dict] = []
        self._stack_created: int = 0
        # v3.23.28 — Invisible=True keeps _open_stack out of the
        # Visible-mode exchange placement branch (which needs a real
        # exchange). Set _aggressive default to False.
        self._invisible: bool = True
        self._aggressive: bool = False


class TestOpenStackFromScrumBehavior:
    def _method(self):
        """Import the unbound method off ScrummingBot for testing on a stub."""
        from src.trading.scrumming_bot import ScrummingBot

        return ScrummingBot._open_stack_from_scrum

    def test_populates_ledger_with_n_tranches(self):
        bot = _StubBot()
        import asyncio

        n = asyncio.run(self._method()(bot, scrum_price=100.0, scrum_size=30.0))
        assert n == 3
        assert len(bot._stack_tranches) == 3
        assert bot._stack_created == 3

    def test_anchor_at_min_opposing_and_level_one_one_gap_above(self):
        """min_opposing = scrumming_interval_pct + trading_fee_pct = 1.6%.

        RESTATED from `test_first_tranche_at_min_opposing`, which pinned
        the retired law where rung 0 sat AT the anchor and the expected
        price was 101.6. Under the operator's spacing law (2026-08-11 /
        2026-08-12) level 1 sits one INITIAL GAP above that anchor, so
        the stub's 1% gap puts it at 100 x 1.016 x 1.01. This version
        asserts BOTH factors separately, so a change to either the
        opposing distance or the gap is caught on its own rather than
        hidden inside one product.
        """
        bot = _StubBot()
        import asyncio

        asyncio.run(self._method()(bot, scrum_price=100.0, scrum_size=30.0))
        first = bot._stack_tranches[0]
        anchor = 100.0 * (1.0 + (1.0 + 0.6) / 100.0)
        assert anchor == pytest.approx(
            101.6, rel=1e-12
        ), "the ANCHOR is still scrum_price x (1 + min_opposing/100)"
        assert first["price"] == pytest.approx(
            anchor * 1.01, rel=1e-9
        ), "level 1 must sit exactly one initial gap above the anchor"
        assert first["price"] > anchor, "retired contract: no rung sits AT the anchor"

    def test_all_tranches_pending(self):
        bot = _StubBot()
        import asyncio

        asyncio.run(self._method()(bot, scrum_price=100.0, scrum_size=30.0))
        for t in bot._stack_tranches:
            assert t["status"] == "pending"

    def test_tranche_has_open_metadata(self):
        bot = _StubBot()
        import asyncio

        asyncio.run(self._method()(bot, scrum_price=100.0, scrum_size=30.0))
        t = bot._stack_tranches[0]
        assert "opened_ts" in t
        assert "opened_at_scrum_price" in t
        assert t["opened_at_scrum_price"] == 100.0

    def test_returns_zero_on_invalid_inputs(self):
        """When split_scrum_into_tranches raises ValueError, return 0
        and log — don't crash the tick."""
        import asyncio

        bot = _StubBot()
        # Force Invisible so no exchange call is needed on the happy path
        bot._invisible = True
        bot._aggressive = False
        n = asyncio.run(self._method()(bot, scrum_price=0.0, scrum_size=30.0))
        assert n == 0
        assert bot._stack_tranches == []
        assert bot._stack_created == 0
        # A log message must have been emitted
        assert any(
            "STACK OPEN FAILED" in kwargs.get("message", "")
            for _, kwargs in bot._bus.messages
        )


# ---------------------------------------------------------------------------
# Invisible-mode tranche FIRE path — drives the real _execute_sell.
#
# The source-shape pins above never execute _execute_sell, so they were
# blind to this: _open_stack_from_scrum accepted `summary` and dropped it,
# and the reconciler passed summary=None into _execute_sell, which
# dereferences summary.consensus_confidence at the "SELL signal:" emit —
# BEFORE guarded_place_order. The AttributeError was swallowed by the
# method's own `except Exception`, which emitted "SELL FAILED" and
# returned None, so no invisible tranche could ever fire.
#
# These tests execute the real method. Each negative assertion is paired
# with a positive control that must FAIL if the stub goes blind.
# ---------------------------------------------------------------------------


class _StubOrder:
    def __init__(self, price: float):
        self.id = "stub-order-1"
        self.average = price
        self.price = price


class _StubStats:
    def __init__(self):
        self.verify_samples = 0
        self.verify_clean = 0
        self.verify_adjusted = 0
        self.verify_canceled = 0
        self.total_sells = 0
        self.total_trades = 0
        self.trade_volume = 0.0
        self.last_trade_time = 0.0
        self.ytd_scrummed_usd = 0.0


class _StubExchange:
    """No open orders — keeps the P0b stacked-SELL guard permissive."""

    def __init__(self):
        self.get_open_orders_calls = 0

    async def get_open_orders(self, symbol):
        self.get_open_orders_calls += 1
        return []


class _SellStubBot:
    """Minimum surface _execute_sell needs, with every internal gate set
    permissive. NOT a ScrummingBot. Records the orders it was asked to
    place so a test can assert placement actually happened."""

    def __init__(self, **cfg_overrides):
        self.bot_id = "sell-stub"
        self.config = _StubConfig(
            symbol="ETH/USD",
            target_asset="ETH",
            scrumming_interval_pct=1.0,
            trading_fee_pct=0.6,
            stack_mode=True,
            stack_tranche_count_target=3,
            split_distance_pct=1.0,
            stack_spacing_mode="linear",
            **cfg_overrides,
        )
        self.exchange = _StubExchange()
        self.exchange_interface = _StubExchangeInterface()
        self._bus = _StubBus()
        self.stats = _StubStats()
        self._invisible = True
        self._aggressive = False
        # Opposing-direction hysteresis disarmed => gate is a no-op.
        self._hyst_armed_scrum_side = False
        self._hyst_ref_scrum_side = 0.0
        self._current_holdings = 100.0
        self._memorised_trades: list = []
        self._quote_to_usd = 1.0
        self._stack_tranches: list[dict] = []
        self._stack_created = 0
        self.placed_orders: list[dict] = []
        self.notifications: list[tuple] = []
        self.reconcile_reasons: list[str] = []

    def _crr(self):
        """No capital-reservation registry. _execute_sell raises inside its
        own try, catches it, and falls through to the remaining gates."""
        return None

    def _emit_trade_notification(self, kind, state, detail):
        self.notifications.append((kind, state, detail))

    async def _execute_sell(self, amount, price, summary, bypass_stack=False):
        """Delegate to the REAL ScrummingBot._execute_sell. The reconciler
        calls self._execute_sell, so without this the stub would fail with
        AttributeError and the test would pass for the wrong reason."""
        from src.trading.scrumming_bot import ScrummingBot

        return await ScrummingBot._execute_sell(
            self, amount=amount, price=price, summary=summary, bypass_stack=bypass_stack
        )

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
        return _StubOrder(100.0 if price is None else float(price))

    async def _reconcile_holdings(self, reason=""):
        self.reconcile_reasons.append(reason)
        return None

    def log_messages(self) -> list[str]:
        return [kwargs.get("message", "") for _, kwargs in self._bus.messages]


class _RealSummary:
    """Stands in for a VotingSummary. Only the two attributes
    _execute_sell reads are needed."""

    consensus_direction = "sell"
    consensus_confidence = 0.75


def _execute_sell_method():
    from src.trading.scrumming_bot import ScrummingBot

    return ScrummingBot._execute_sell


def _reconcile_invisible_method():
    """STAGE ONE -- activation. Places nothing."""
    from src.trading.scrumming_bot import ScrummingBot

    return ScrummingBot._reconcile_stack_tranches_invisible


def _spend_method():
    """STAGE TWO -- spend, called only inside the chain's should_fire."""
    from src.trading.scrumming_bot import ScrummingBot

    return ScrummingBot._spend_activated_stack_tranches


class TestExecuteSellStubIsHonest:
    """POSITIVE CONTROLS. If these fail, the stub is broken and every
    assertion in the next class is void."""

    def test_stub_places_order_with_a_real_summary(self):
        """The gates are permissive: a well-formed summary reaches
        guarded_place_order. Proves a later 'no order placed' result is
        caused by the summary, not by a gate refusing the stub."""
        import asyncio

        bot = _SellStubBot()
        fill = asyncio.run(
            _execute_sell_method()(
                bot, amount=1.0, price=100.0, summary=_RealSummary(), bypass_stack=True
            )
        )
        assert bot.placed_orders, (
            "positive control failed: a valid summary must reach "
            "guarded_place_order. The stub's gates are not permissive."
        )
        assert fill is not None
        assert not any("SELL FAILED" in m for m in bot.log_messages())

    def test_stub_detects_a_missing_attribute(self):
        """Blind the summary and the stub must NOTICE. A stub that passes
        either way measures nothing."""
        import asyncio

        class _Blind:
            consensus_direction = "sell"
            # consensus_confidence deliberately absent

        bot = _SellStubBot()
        asyncio.run(
            _execute_sell_method()(
                bot, amount=1.0, price=100.0, summary=_Blind(), bypass_stack=True
            )
        )
        assert not bot.placed_orders, (
            "control is blind: a summary missing consensus_confidence "
            "must not reach guarded_place_order"
        )


class _RefusingSellStubBot(_SellStubBot):
    """`_execute_sell` refuses. The real method returns None on the P0b
    stacked-sell guard, the capital-reservation gate, opposing hysteresis
    and a Verify-Hit cancel; every one of those places no order. Flip
    `refusing` to False and the stub delegates to the real method again,
    so one bot can be refused and then authorised."""

    def __init__(self, **cfg_overrides):
        super().__init__(**cfg_overrides)
        self.refusing = True
        self.refused_calls: list[tuple] = []

    async def _execute_sell(self, amount, price, summary, bypass_stack=False):
        if self.refusing:
            self.refused_calls.append((amount, price))
            return None
        return await super()._execute_sell(
            amount=amount, price=price, summary=summary, bypass_stack=bypass_stack
        )


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def _opened_bot(confidence=0.75, cls=_SellStubBot):
    """Open a real Invisible stack and return the bot, untouched by any
    stage. Three tranches, thresholds ascending from $101.60."""
    from src.trading.scrumming_bot import ScrummingBot

    bot = cls()
    summary = _RealSummary()
    summary.consensus_confidence = confidence
    _run(
        ScrummingBot._open_stack_from_scrum(
            bot, scrum_price=100.0, scrum_size=30.0, summary=summary
        )
    )
    assert bot._stack_tranches, "stack must open before anything else"
    assert not bot.placed_orders, "Invisible mode must place nothing at stack-open time"
    return bot


class TestStageOneActivatesAndSellsNothing:
    """THE DEFECT. Operator directive 2026-08-11: "A price threshold being
    passed activates the tranche which allows it to be spent when the
    trading condition manifests."

    Stage one runs at the top of `tick`, above every trading gate and
    above nine returns that end the tick outright. Whatever it does, it
    happens on ticks the bot has refused to trade on. So it may mark, and
    it may not sell.
    """

    def test_crossing_the_threshold_places_no_order(self):
        bot = _opened_bot()
        target = float(bot._stack_tranches[0]["price"])
        activated = _run(_reconcile_invisible_method()(bot, current_price=target + 1.0))
        assert activated == 1
        assert bot.placed_orders == [], (
            "stage one placed an order. A crossed price threshold is not a "
            "trading gate; it may only make the tranche a candidate."
        )
        assert (
            bot.exchange.get_open_orders_calls == 0
        ), "stage one reached the exchange at all"

    def test_crossing_the_threshold_marks_the_tranche_activated(self):
        bot = _opened_bot()
        target = float(bot._stack_tranches[0]["price"])
        _run(_reconcile_invisible_method()(bot, current_price=target + 1.0))
        t = bot._stack_tranches[0]
        assert t["activated"] is True
        assert t["activated_price"] == pytest.approx(target + 1.0)
        assert t["activated_ts"] > 0

    def test_status_stays_pending_so_the_ledger_keeps_three_states(self):
        """Activation is a flag, not a fourth status. Every reader of
        `status` -- the Stack Tranches tab's pending/filled/cancelled
        counts, the Visible reconciler's filter -- keeps working."""
        bot = _opened_bot()
        target = float(bot._stack_tranches[0]["price"])
        _run(_reconcile_invisible_method()(bot, current_price=target + 1.0))
        assert bot._stack_tranches[0]["status"] == "pending"

    def test_below_threshold_does_not_activate(self):
        bot = _opened_bot()
        target = float(bot._stack_tranches[0]["price"])
        activated = _run(_reconcile_invisible_method()(bot, current_price=target - 1.0))
        assert activated == 0
        assert bot._stack_tranches[0]["activated"] is False
        assert not bot.placed_orders

    def test_activation_is_idempotent_across_repeated_ticks(self):
        bot = _opened_bot()
        target = float(bot._stack_tranches[0]["price"])
        method = _reconcile_invisible_method()
        first = _run(method(bot, current_price=target + 1.0))
        second = _run(method(bot, current_price=target + 1.0))
        assert (first, second) == (1, 0), (
            "re-crossing an already-activated tranche must count nothing "
            "new, or the operator's log fills with duplicate ACTIVATED lines"
        )

    def test_activation_survives_a_retrace(self):
        """STICKY BY DESIGN. The operator separated "activates" from "is
        spent". A tranche crossed at $X that retraces before the chain
        authorises must stay a candidate -- otherwise the two conditions
        collapse into one instant, which is not what was asked for."""
        bot = _opened_bot()
        target = float(bot._stack_tranches[0]["price"])
        method = _reconcile_invisible_method()
        _run(method(bot, current_price=target + 1.0))
        _run(method(bot, current_price=target - 5.0))
        assert bot._stack_tranches[0]["activated"] is True


class TestStageTwoSpendsOnlyWhatTheGateAuthorises:
    def test_an_activated_tranche_is_spent(self):
        """THE CONVERSE. Without this the refusal proof is vacuous: a
        method that never fires trivially never fires under a refusal."""
        bot = _opened_bot()
        target = float(bot._stack_tranches[0]["price"])
        _run(_reconcile_invisible_method()(bot, current_price=target + 1.0))
        spent = _run(
            _spend_method()(bot, current_price=target + 1.0, summary=_RealSummary())
        )
        assert spent == 1
        assert bot.placed_orders, (
            "with the chain authorising, an activated tranche must actually " "be spent"
        )
        assert bot._stack_tranches[0]["status"] == "filled"

    def test_an_unactivated_tranche_is_not_spent(self):
        """Authority alone is not enough either. Both stages must have
        happened -- the gate does not reach past the threshold."""
        bot = _opened_bot()
        spent = _run(_spend_method()(bot, current_price=100.0, summary=_RealSummary()))
        assert spent == 0
        assert not bot.placed_orders

    def test_the_sell_is_priced_at_the_live_price_not_the_threshold(self):
        """Invisible mode sells at MARKET, and `_execute_sell` measures
        opposing hysteresis and Verify-Hit against the price it is
        handed. Deferring the fire to a later tick means the threshold is
        no longer that price."""
        bot = _opened_bot()
        target = float(bot._stack_tranches[0]["price"])
        live = target + 7.25
        _run(_reconcile_invisible_method()(bot, current_price=live))
        _run(_spend_method()(bot, current_price=live, summary=_RealSummary()))
        signal = [m for m in bot.log_messages() if "SELL signal:" in m]
        assert signal, "no SELL signal line emitted"
        assert f"${live:.8f}" in signal[0], (
            f"sell was priced at something other than the live price: " f"{signal[0]}"
        )

    def test_the_live_vote_is_what_reaches_the_sell_log(self):
        """RESTATED, v3.23.44. This test used to require the FROZEN
        stack-open confidence in the SELL line. That was a record of a
        past condition standing in for a present one. The spend stage
        runs where the live VotingSummary is in scope, so the live vote
        is what gets logged -- and the frozen one survives untouched as
        the forensic record it always was."""
        bot = _opened_bot(confidence=0.62)
        live = _RealSummary()
        live.consensus_confidence = 0.91
        target = float(bot._stack_tranches[0]["price"])
        _run(_reconcile_invisible_method()(bot, current_price=target + 1.0))
        _run(_spend_method()(bot, current_price=target + 1.0, summary=live))
        signal = [m for m in bot.log_messages() if "SELL signal:" in m]
        assert signal, "no SELL signal line emitted"
        assert (
            "confidence=0.91" in signal[0]
        ), f"the live vote did not reach the sell log: {signal[0]}"
        assert bot._stack_tranches[0]["open_confidence"] == pytest.approx(
            0.62
        ), "the forensic record of the opening vote was overwritten"

    def test_the_recorded_open_vote_is_the_fallback_with_no_live_vote(self):
        """The v3.23.43 fix stays load-bearing: `_execute_sell` reads
        `summary.consensus_confidence` before it places the order, so a
        caller with no live vote must still get a well-formed summary
        rather than an AttributeError that silently kills the fire."""
        bot = _opened_bot(confidence=0.62)
        target = float(bot._stack_tranches[0]["price"])
        _run(_reconcile_invisible_method()(bot, current_price=target + 1.0))
        spent = _run(_spend_method()(bot, current_price=target + 1.0, summary=None))
        assert spent == 1
        signal = [m for m in bot.log_messages() if "SELL signal:" in m]
        assert (
            "confidence=0.62" in signal[0]
        ), f"fallback to the recorded open vote failed: {signal[0]}"

    def test_memorised_trade_carries_the_live_summary(self):
        bot = _opened_bot(confidence=0.62)
        live = _RealSummary()
        live.consensus_confidence = 0.91
        target = float(bot._stack_tranches[0]["price"])
        _run(_reconcile_invisible_method()(bot, current_price=target + 1.0))
        _run(_spend_method()(bot, current_price=target + 1.0, summary=live))
        assert bot._memorised_trades, "sell must be memorised"
        vs = bot._memorised_trades[0].voting_summary
        assert vs is not None
        assert vs.consensus_confidence == pytest.approx(0.91)

    def test_no_sell_failed_line_on_the_spend_path(self):
        bot = _opened_bot()
        target = float(bot._stack_tranches[0]["price"])
        _run(_reconcile_invisible_method()(bot, current_price=target + 1.0))
        _run(_spend_method()(bot, current_price=target + 1.0, summary=_RealSummary()))
        failures = [m for m in bot.log_messages() if "SELL FAILED" in m]
        assert not failures, f"tranche spend emitted failures: {failures}"

    def test_a_spent_tranche_is_never_spent_twice(self):
        bot = _opened_bot()
        target = float(bot._stack_tranches[0]["price"])
        _run(_reconcile_invisible_method()(bot, current_price=target + 1.0))
        spend = _spend_method()
        _run(spend(bot, current_price=target + 1.0, summary=_RealSummary()))
        placed_after_first = len(bot.placed_orders)
        calls_after_first = bot.exchange.get_open_orders_calls
        _run(spend(bot, current_price=target + 1.0, summary=_RealSummary()))
        assert (
            len(bot.placed_orders) == placed_after_first
        ), "tranche re-spent on a later authorised tick"
        assert bot.exchange.get_open_orders_calls == calls_after_first, (
            "spend stage still burns a get_open_orders call on a filled " "tranche"
        )


class TestTheTrancheSurvivesARefusal:
    """Losing an activated tranche is the same family of defect as
    spending it without authority, pointed the other way."""

    def test_a_refused_tick_leaves_it_pending_and_activated(self):
        """A chain refusal is expressed by NOT CALLING the spend stage --
        that is what "inside the should_fire block" means. Ten refused
        ticks in a row must change nothing but the activation flag."""
        bot = _opened_bot()
        target = float(bot._stack_tranches[0]["price"])
        method = _reconcile_invisible_method()
        for _ in range(10):
            _run(method(bot, current_price=target + 1.0))
        t = bot._stack_tranches[0]
        assert bot.placed_orders == [], "a refused tick sold something"
        assert t["status"] == "pending"
        assert t["activated"] is True
        assert len(bot._stack_tranches) == 3, "the ledger changed size"
        spent = _run(
            _spend_method()(bot, current_price=target + 1.0, summary=_RealSummary())
        )
        assert (
            spent == 1
        ), "the tranche did not survive ten refusals in a spendable state"

    def test_an_execute_sell_refusal_leaves_it_pending_and_activated(self):
        """The other refusal surface: the chain authorised, but a gate
        inside `_execute_sell` (P0b stacked sell, capital reservation,
        opposing hysteresis, Verify-Hit) said no. Same requirement."""
        bot = _opened_bot(cls=_RefusingSellStubBot)
        target = float(bot._stack_tranches[0]["price"])
        _run(_reconcile_invisible_method()(bot, current_price=target + 1.0))
        spent = _run(
            _spend_method()(bot, current_price=target + 1.0, summary=_RealSummary())
        )
        t = bot._stack_tranches[0]
        assert spent == 0
        assert bot.refused_calls, (
            "positive control: the refusing stub was never asked to sell, "
            "so this test proves nothing about refusals"
        )
        assert t["status"] == "pending"
        assert t["activated"] is True
        assert any(
            "NOT SPENT" in m for m in bot.log_messages()
        ), "a refused spend must say so in the operator's log"

    def test_repeated_refusals_never_duplicate_or_lose_the_tranche(self):
        bot = _opened_bot(cls=_RefusingSellStubBot)
        target = float(bot._stack_tranches[0]["price"])
        _run(_reconcile_invisible_method()(bot, current_price=target + 1.0))
        spend = _spend_method()
        for _ in range(5):
            _run(spend(bot, current_price=target + 1.0, summary=_RealSummary()))
        assert len(bot.refused_calls) == 5
        assert len(bot._stack_tranches) == 3
        assert [t["status"] for t in bot._stack_tranches] == [
            "pending",
            "pending",
            "pending",
        ]
        assert bot.placed_orders == []

        bot.refusing = False
        spent = _run(spend(bot, current_price=target + 1.0, summary=_RealSummary()))
        assert spent == 1, "five refusals consumed the tranche"
        assert len(bot.placed_orders) == 1, (
            "five refusals plus one authorisation placed "
            f"{len(bot.placed_orders)} orders"
        )


class TestShipsDormant:
    """stack_mode is False on all 37 live bots and this change does not
    turn it on anywhere."""

    def test_the_config_default_is_off(self):
        from src.trading.bot_container import BotConfig
        import dataclasses

        field = {f.name: f for f in dataclasses.fields(BotConfig)}["stack_mode"]
        assert field.default is False

    def test_both_stages_are_no_ops_when_stack_mode_is_off(self):
        bot = _opened_bot()
        target = float(bot._stack_tranches[0]["price"])
        bot.config.stack_mode = False
        assert _run(_reconcile_invisible_method()(bot, current_price=target + 1.0)) == 0
        assert (
            _run(
                _spend_method()(bot, current_price=target + 1.0, summary=_RealSummary())
            )
            == 0
        )
        assert not bot.placed_orders

    def test_both_stages_are_no_ops_in_visible_mode(self):
        """Visible mode is untouched: gates are evaluated once, at
        placement time, which is ordinary limit-order semantics."""
        bot = _opened_bot()
        target = float(bot._stack_tranches[0]["price"])
        bot._invisible = False
        assert _run(_reconcile_invisible_method()(bot, current_price=target + 1.0)) == 0
        assert (
            _run(
                _spend_method()(bot, current_price=target + 1.0, summary=_RealSummary())
            )
            == 0
        )
        assert not bot.placed_orders
