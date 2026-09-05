"""``max_adoptable_usd`` caps what a never-scrummed bot adopts from the wallet.

``_adopt`` drives the real ``ScrummingBot._tick_initialise`` against ``_Bot``, a
stand-in carrying only the attributes that phase reads. The adopted position is
read off ``_main_lots``; the operator-facing refusal is read off the ``bot.log``
messages ``_Bus`` collects.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.exchange.base import Balance, Ticker  # noqa: E402
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

SYM = "BICO/USDC"
ASSET = "BICO"
PX = 0.0706380489


class _Bus:
    """Collects every ``bot.log`` message ``_tick_initialise`` emits."""

    def __init__(self):
        self.messages: list[str] = []

    def emit(self, topic, **payload):
        """Record the ``message`` of a ``bot.log`` event."""
        if topic == "bot.log":
            self.messages.append(str(payload.get("message", "")))


class _Phantoms:
    """Phantom manager stand-in; ``_tick_initialise`` reaches it only when
    ``_phantoms_enabled`` is set, which ``_adopt`` leaves False."""


def _bot(units_on_exchange, cap_usd, target_balance, price, lots):
    """Return a ``ScrummingBot`` posed for the boot handshake with ``price`` and
    ``units_on_exchange`` on the wallet."""
    bot = object.__new__(ScrummingBot)
    bot.bot_id = "bot-adoption"
    bot.config = type(
        "C",
        (),
        {
            "symbol": SYM,
            "target_asset": ASSET,
            "max_adoptable_usd": cap_usd,
        },
    )()
    bot._bus = _Bus()
    bot._main_lots = list(lots)
    bot._target_balance = target_balance
    bot._tranches_created_lifetime = 0
    bot._tranches_counters_reset_ts = 0.0
    bot._current_holdings = 0.0
    bot._quote_to_usd = 1.0
    bot._initialised = False
    bot._invisible = True
    bot._aggressive = False
    bot._last_price = 0.0
    bot._phantom_gate_logged = True
    bot._phantoms_enabled = False
    bot._phantoms_started = False
    bot._phantom_timeframes = []
    bot._phantom_mgr = _Phantoms()
    bot.stats = type(
        "S", (), {"current_price": 0.0, "cost_basis_total_exchange": 0.0}
    )()

    async def _get_ticker(_symbol):
        return Ticker(
            symbol=SYM,
            bid=price,
            ask=price,
            last=price,
            volume_24h=0.0,
            timestamp=0.0,
        )

    async def _get_balance(currency):
        return Balance(
            currency=currency,
            free=units_on_exchange,
            used=0.0,
            total=units_on_exchange,
        )

    async def _refresh_quote_to_usd():
        return 1.0

    bot._get_ticker = _get_ticker
    bot._get_balance = _get_balance
    bot._refresh_quote_to_usd = _refresh_quote_to_usd
    return bot


def _adopt(units_on_exchange, cap_usd=0.0, target_balance=25.0, price=PX, lots=()):
    """Run the real ``_tick_initialise`` and return the ``ScrummingBot`` it left."""
    bot = _bot(units_on_exchange, cap_usd, target_balance, price, lots)
    asyncio.run(ScrummingBot._tick_initialise(bot, SYM))
    return bot


def _adopted_units(bot) -> float:
    """Sum the units ``_tick_initialise`` wrote into ``_main_lots``."""
    return sum(float(lot.get("units", 0) or 0) for lot in bot._main_lots)


def _capped_message(bot) -> str:
    """Return the ``ADOPTION CAPPED`` message, or an empty string."""
    for message in bot._bus.messages:
        if "ADOPTION CAPPED" in message:
            return message
    return ""


class TestTheInstrumentWorks:
    def test_the_handshake_completes_and_records_a_lot(self):
        """Positive control: ``_tick_initialise`` reaches the adoption branch and
        marks the bot ``_initialised``."""
        bot = _adopt(25.0 / PX)
        assert bot._initialised is True
        assert bot._main_lots, bot._bus.messages

    def test_the_field_exists_on_botconfig(self):
        from src.trading.bot_container import BotConfig

        assert hasattr(BotConfig, "max_adoptable_usd")
        assert BotConfig.max_adoptable_usd == 0.0


class TestTheDefaultIsTargetBalance:
    def test_zero_means_use_target_balance(self):
        """A ``max_adoptable_usd`` of 0.0 is unset, not adopt-nothing; every bot
        predating the field carries 0.0."""
        bot = _adopt(10_000.0, cap_usd=0.0, target_balance=25.0)
        assert _adopted_units(bot) == pytest.approx(25.0 / PX)

    def test_a_bot_asked_to_hold_25_adopts_at_most_25(self):
        bot = _adopt(10_000.0, cap_usd=0.0, target_balance=25.0)
        assert _adopted_units(bot) * PX == pytest.approx(25.0)

    def test_an_explicit_cap_overrides_the_default(self):
        bot = _adopt(10_000.0, cap_usd=10.0, target_balance=25.0)
        assert _adopted_units(bot) * PX == pytest.approx(10.0)


class TestTheCapOnlyEverReduces:
    def test_a_small_holding_is_adopted_whole(self):
        """The operator's manual $25 against a $25 target: ``_main_lots`` keeps
        every unit and no ``ADOPTION CAPPED`` message is emitted."""
        units = 25.0 / PX
        bot = _adopt(units, cap_usd=0.0, target_balance=25.0)
        assert _adopted_units(bot) == pytest.approx(units)
        assert _capped_message(bot) == ""

    def test_it_never_invents_units(self):
        """A ``max_adoptable_usd`` above the holding must not raise it."""
        units = 5.0 / PX
        bot = _adopt(units, cap_usd=1000.0, target_balance=25.0)
        assert _adopted_units(bot) == pytest.approx(units)

    def test_a_zero_price_discards_nothing_already_tracked(self):
        """A ticker ``last`` of 0.0 gives no cost basis, so ``_tick_initialise``
        writes no lot and the 60 units already in ``_main_lots`` survive."""
        held = [{"units": 60.0, "initial_buy_price": PX}]
        bot = _adopt(100.0, cap_usd=25.0, target_balance=25.0, price=0.0, lots=held)
        assert _adopted_units(bot) == pytest.approx(60.0)
        assert _capped_message(bot) == "", bot._bus.messages

    def test_a_live_price_does_adopt_over_the_tracked_units(self):
        """Positive control for the zero-price case: the same 60 tracked units are
        replaced when the ticker carries a price."""
        held = [{"units": 60.0, "initial_buy_price": PX}]
        bot = _adopt(100.0, cap_usd=1000.0, target_balance=25.0, lots=held)
        assert _adopted_units(bot) == pytest.approx(100.0)

    def test_no_target_and_no_cap_leaves_the_holding_alone(self):
        bot = _adopt(100.0, cap_usd=0.0, target_balance=0.0)
        assert _adopted_units(bot) == pytest.approx(100.0)


class TestTheOperatorsSurplusIsWithheld:
    def test_the_withheld_amount_is_the_difference(self):
        """The operator holds 500 ``BICO``; the bot may adopt $25 of it."""
        held = 500.0
        bot = _adopt(held, cap_usd=0.0, target_balance=25.0)
        adopted = _adopted_units(bot)
        assert adopted * PX == pytest.approx(25.0)
        assert held - adopted == pytest.approx(held - 25.0 / PX)

    def test_a_cap_above_the_holding_takes_the_lot(self):
        """Negative control: without a binding ``max_adoptable_usd`` the bot
        adopts everything, which is what the cap exists to stop."""
        held = 500.0
        bot = _adopt(held, cap_usd=held * PX * 10, target_balance=25.0)
        assert _adopted_units(bot) == pytest.approx(held)
        assert _capped_message(bot) == ""


class TestTheOperatorIsTold:
    def test_the_refusal_is_announced(self):
        bot = _adopt(500.0, cap_usd=0.0, target_balance=25.0)
        assert _capped_message(bot), bot._bus.messages

    def test_the_message_names_the_lever(self):
        """A cap the operator cannot find is a cap they report as a bug, so the
        ``ADOPTION CAPPED`` line names ``max_adoptable_usd``."""
        message = _capped_message(_adopt(500.0, cap_usd=0.0, target_balance=25.0))
        assert "max_adoptable_usd" in message, message
        assert "unmanaged" in message, message

    def test_the_message_carries_both_sizes(self):
        """The line reports the wallet holding and the adopted size."""
        message = _capped_message(_adopt(500.0, cap_usd=0.0, target_balance=25.0))
        assert "500.000000" in message, message
        assert f"{25.0 / PX:.6f}" in message, message


class TestTheCapReachesTheLot:
    def test_the_lot_records_the_capped_size(self):
        """Capping after ``_main_lots`` was written would record the uncapped
        position and then contradict it."""
        bot = _adopt(500.0, cap_usd=0.0, target_balance=25.0)
        assert len(bot._main_lots) == 1, bot._main_lots
        assert bot._main_lots[0]["units"] == pytest.approx(25.0 / PX)

    def test_current_holdings_matches_the_lot(self):
        bot = _adopt(500.0, cap_usd=0.0, target_balance=25.0)
        assert bot._current_holdings == pytest.approx(_adopted_units(bot))
