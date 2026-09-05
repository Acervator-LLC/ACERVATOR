"""A Stack tranche is spent only under an authorised gate-chain verdict.

``_gate_bot`` poses a real ``ScrummingBot`` and ``_run_tick`` drives the real
``ScrummingBot.tick`` over it, recording every call to
``_spend_activated_stack_tranches`` and ``_reconcile_stack_tranches_invisible``.
``REFUSALS`` names one runtime pose per pre-chain refusal, and each pose must
reach the activation and never the spend.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.container.config import BotConfig  # noqa: E402
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402
from src.trading.ta_engine import VotingEngine  # noqa: E402

PRICE = 100.0
TARGET = 100.0


class _Bus:
    """Collects every event ``tick`` emits."""

    def __init__(self):
        self.events: list[tuple] = []

    def emit(self, name, **payload):
        """Record one event."""
        self.events.append((name, payload))

    def text(self) -> str:
        """Join every ``message`` the recorded events carry."""
        return "\n".join(str(kw.get("message", "")) for _n, kw in self.events)


class _Ticker:
    """The price snapshot ``_get_ticker`` answers with."""

    def __init__(self, last):
        self.last = last
        self.bid = last
        self.ask = last
        self.volume_24h = 0.0
        self.timestamp = 0.0


class _Verdict:
    """One gate-chain decision; ``should_fire`` is what ``tick`` reads."""

    def __init__(self, fire):
        self.should_fire = fire
        self.blockers = []
        self.reasons = []
        self.armed = fire
        self.decision = "FIRE" if fire else "HOLD"


class _Chain:
    """A gate chain whose ``evaluate`` answers with one fixed ``_Verdict`` and
    records every context it was given."""

    def __init__(self, fire):
        self._fire = fire
        self.seen: list = []

    def evaluate(self, context):
        """Record ``context`` and answer with the fixed verdict."""
        self.seen.append(context)
        return _Verdict(self._fire)


class _Coordinator:
    """Multi-timeframe coordinator stand-in; nothing is locked and no bias is
    reported."""

    def is_locked(self, *_tf):
        """Report no timeframe lock."""
        return False

    def get_higher_tf_bias(self, *_a, **_kw):
        """Report no higher-timeframe bias."""
        return None, {}


class _Venue:
    """Exchange handle stand-in; every wallet read refuses, so any path that
    reaches the venue ends without an order."""

    min_order_size = 0.0

    async def fetch_balance(self, *_a, **_kw):
        """Refuse the read, as an unreachable venue would."""
        raise ConnectionError("no venue in this test")

    async def get_balance(self, *_a, **_kw):
        """Refuse the read, as an unreachable venue would."""
        raise ConnectionError("no venue in this test")

    async def get_open_orders(self, *_a, **_kw):
        """Report no resting order."""
        return []


def _candles(count=100):
    """Return ``count`` OHLCV rows that oscillate around ``PRICE``."""
    rows = []
    for i in range(count):
        px = PRICE + (i % 7) - 3.0
        rows.append([1_700_000_000_000 + i * 3_600_000, px, px + 1, px - 1, px, 10.0])
    return rows


def _gate_bot(*, scrum_fires=True, fold_fires=False, holdings=1.2, candles=100, **pose):
    """Return a ``ScrummingBot`` posed to run one full ``tick``.

    ``pose`` overrides any attribute after the defaults are set, which is how each
    entry of ``REFUSALS`` states its condition.
    """
    bot = object.__new__(ScrummingBot)
    bot.bot_id = "gate-bot"
    bot.config = BotConfig(
        exchange_id="coinbase",
        base_currency="USD",
        target_asset="ETH",
        symbol="ETH/USD",
        target_balance=TARGET,
        scrum_read_rate_min=0,
        tranche_despawn_days=0,
        max_cartridge_size_pct=0.0,
        detonation_enabled=False,
        stack_mode=True,
    )
    bot._bus = _Bus()
    bot.stats = type("S", (), {"current_price": 0.0})()
    bot.exchange = _Venue()
    bot.exchange_interface = bot.exchange
    bot._coordinator = _Coordinator()
    bot._voting_engine = VotingEngine()
    bot._scrum_chain = _Chain(scrum_fires)
    bot._fold_chain = _Chain(fold_fires)

    bot._initialised = True
    bot._invisible = True
    bot._aggressive = False
    bot._manual_fire_pending = False
    bot._cb_hard_tripped = False
    bot._cb_soft_active_side = None
    bot._reconcile_tick_counter = 0
    bot._reconcile_interval = 0
    bot._hold_tick_counter = 0
    bot._last_price = PRICE
    bot._last_trade_price = 0.0
    bot._last_trade_side = None
    bot._target_grow_last_side = None
    bot._scrum_target_side = None
    bot._scrum_target_mode = "delta"
    bot._current_holdings = holdings
    bot._target_balance = TARGET
    bot._fold_tranches = []
    bot._stack_tranches = []
    bot._stack_created = 0
    bot._hedge_bal = 0.0
    bot._dist_accumulator = 0.0

    rows = _candles(candles)

    async def _get_ticker(_symbol):
        return _Ticker(PRICE)

    async def _get_ohlcv(_symbol, **_window):
        return rows

    bot._get_ticker = _get_ticker
    bot._get_ohlcv = _get_ohlcv

    for name, value in pose.items():
        setattr(bot, name, value)
    return bot


class _TickRecord:
    """What one driven ``tick`` did: its spends, its activations and any order it
    tried to place."""

    def __init__(self, bot):
        self.bot = bot
        self.spends: list[dict] = []
        self.activations: list[dict] = []
        self.orders: list[tuple] = []


def _run_tick(bot) -> _TickRecord:
    """Drive the real ``ScrummingBot.tick`` once and return a ``_TickRecord``.

    ``guarded_place_order`` records the attempt and then raises, so a tick that
    reached the venue is visible and no order is ever sent.
    """
    record = _TickRecord(bot)

    async def _spend(**call):
        record.spends.append(call)
        return 1

    async def _activate(**call):
        record.activations.append(call)
        return 0

    async def _place(*order, **kwargs):
        record.orders.append((order, kwargs))
        raise AssertionError("the tick tried to place an order")

    bot._spend_activated_stack_tranches = _spend
    bot._reconcile_stack_tranches_invisible = _activate
    bot.guarded_place_order = _place
    asyncio.run(ScrummingBot.tick(bot))
    return record


class TestTheInstrumentReachesTheSpend:
    def test_an_authorised_verdict_reaches_the_spend(self):
        """POSITIVE CONTROL for every refusal below. A clean tick with a firing
        scrum chain reaches ``_spend_activated_stack_tranches``."""
        record = _run_tick(_gate_bot(scrum_fires=True))
        assert len(record.spends) == 1, record.bot._bus.text()
        assert record.spends[0]["current_price"] == pytest.approx(PRICE)

    def test_the_activation_runs_on_the_same_tick(self):
        """Stage one runs before the chain is built, on the same clean tick."""
        record = _run_tick(_gate_bot(scrum_fires=True))
        assert len(record.activations) == 1, record.bot._bus.text()

    def test_the_chain_was_the_thing_that_decided(self):
        """The scrum chain really was evaluated, so a refused verdict below is a
        decision and not an unreached branch."""
        bot = _gate_bot(scrum_fires=True)
        _run_tick(bot)
        assert bot._scrum_chain.seen, "the scrum chain was never evaluated"


class TestARefusedVerdictBlocksTheSpend:
    def test_a_refused_chain_never_reaches_the_spend(self):
        """A refusal is expressed by ``_spend_activated_stack_tranches`` being
        unreachable, which is what makes the refusal protective."""
        record = _run_tick(_gate_bot(scrum_fires=False))
        assert record.spends == [], record.bot._bus.text()

    def test_a_refused_chain_still_runs_the_activation(self):
        """Stage one is deliberately ungated: it makes a tranche sticky and places
        nothing."""
        record = _run_tick(_gate_bot(scrum_fires=False))
        assert len(record.activations) == 1


#: One runtime pose per pre-chain refusal, keyed by what it refuses on.
REFUSALS = {
    "dust band": {"holdings": 1.0},
    "manual fire pending": {"_manual_fire_pending": True},
    "wire-stack pending": {"_pending_stack_buy_usd": 25.0},
    "max cartridge": {},
    "HARD circuit breaker": {"_cb_hard_tripped": True},
    "zero-balance acquisition": {"holdings": 0.0001},
    "insufficient candles for TA": {"candles": 10},
}


#: Every refusal but the operator's own fire, which is allowed to reach the venue.
AUTONOMOUS_REFUSALS = sorted(set(REFUSALS) - {"manual fire pending"})


def _posed(label):
    """Return a ``_gate_bot`` posed for the refusal named by ``label``."""
    bot = _gate_bot(scrum_fires=True, **REFUSALS[label])
    if label == "max cartridge":
        bot.config.max_cartridge_size_pct = 10.0
    return bot


class TestEveryPreChainRefusalPreventsTheSpend:
    @pytest.mark.parametrize("label", sorted(REFUSALS))
    def test_the_refusal_blocks_the_spend(self, label):
        record = _run_tick(_posed(label))
        assert record.spends == [], (
            f"{label} did not stop the tick before the spend:\n"
            f"{record.bot._bus.text()}"
        )

    @pytest.mark.parametrize("label", sorted(REFUSALS))
    def test_the_refusal_still_lets_stage_one_run(self, label):
        """Stage one sits above every refusal, so a refused tick still activates a
        tranche whose price threshold has passed."""
        record = _run_tick(_posed(label))
        assert len(record.activations) == 1, record.bot._bus.text()

    @pytest.mark.parametrize("label", AUTONOMOUS_REFUSALS)
    def test_the_refusal_places_no_order(self, label):
        record = _run_tick(_posed(label))
        assert record.orders == [], record.bot._bus.text()

    def test_manual_fire_places_the_operators_order_and_spends_no_tranche(self):
        """``_manual_fire_pending`` is the operator's own fire, so it reaches the
        venue; it still never reaches ``_spend_activated_stack_tranches``."""
        record = _run_tick(_posed("manual fire pending"))
        assert record.orders, record.bot._bus.text()
        assert record.spends == [], record.bot._bus.text()


class TestStageOnePlacesNothing:
    """``_reconcile_stack_tranches_invisible`` marks a tranche activated and never
    reaches ``guarded_place_order``."""

    def _one_pending(self):
        """Return a bot carrying one pending stack tranche below ``PRICE``."""
        bot = _gate_bot(scrum_fires=True)
        bot._stack_tranches = [
            {
                "index": 0,
                "price": PRICE - 1.0,
                "size": 0.1,
                "status": "pending",
                "created_ts": 1.0,
            }
        ]
        return bot

    def test_the_real_activation_places_no_order(self):
        bot = self._one_pending()
        placed: list = []

        async def _place(*order, **kwargs):
            placed.append((order, kwargs))
            raise AssertionError("stage one placed an order")

        bot.guarded_place_order = _place
        asyncio.run(
            ScrummingBot._reconcile_stack_tranches_invisible(bot, current_price=PRICE)
        )
        assert placed == [], bot._bus.text()

    def test_it_activates_the_tranche_the_price_passed(self):
        """POSITIVE CONTROL: the call above reached the ledger, so its silence at
        the venue is a fact about stage one and not about an unreached call."""
        bot = self._one_pending()
        tranche = bot._stack_tranches[0]
        asyncio.run(
            ScrummingBot._reconcile_stack_tranches_invisible(bot, current_price=PRICE)
        )
        assert tranche.get("activated") is True, bot._bus.text()
        assert tranche["activated_price"] == pytest.approx(PRICE)


class TestTheFoldSideIsGatedTheSameWay:
    def test_a_refused_fold_verdict_places_no_buy(self):
        record = _run_tick(_gate_bot(scrum_fires=False, fold_fires=False, holdings=0.8))
        assert record.orders == [], record.bot._bus.text()

    def test_the_fold_chain_is_evaluated_on_a_below_target_tick(self):
        """POSITIVE CONTROL for the refusal above: the fold chain decided the tick,
        so its refusal is what stopped the buy."""
        bot = _gate_bot(scrum_fires=False, fold_fires=False, holdings=0.8)
        _run_tick(bot)
        assert bot._fold_chain.seen, "the fold chain was never evaluated"
