"""A shared pool total must never quietly leave a bot's claim out.

BotManager.sum_sibling_base_currency_claims adds up how much of one
currency every OTHER bot has already claimed. A bot asks this so it
can work out how much of the shared pool is genuinely free, and then
it spends against the answer.

Measured before this file existed, with three bots each claiming
$1,000 of one pool:

    every bot readable          -> 3000.0
    one bot's claim unreadable  -> 2000.0, and not one line of log

The reported total was a third short and nothing said so. A short
total tells the asking bot that money is free when another bot has
already claimed it. That is how two bots come to spend the same money.

The rule this file pins: when any bot in the pool cannot be read, no
total is returned at all, and the log names the bot, the reason, and
the size of the gap.

Half these tests are controls. They demand real numbers back for
every honest case, so a "fix" that simply refused everything would be
caught here rather than in production.
"""
from __future__ import annotations

import logging
import math
from typing import Any

import pytest

from src.trading.bot_container import BotConfig, BotManager

EXCHANGE = "coinbase"
CLAIM_USD = 1000.0
BTC_USD = 61234.5
LOGGER = "acervator.bot"


def _cfg(base_currency: str = "USD", target_balance: float = CLAIM_USD,
         exchange_id: str = EXCHANGE) -> BotConfig:
    """A real config, so the field names stay pinned to the real one."""
    return BotConfig(
        exchange_id=exchange_id,
        base_currency=base_currency,
        target_asset="ETH",
        symbol=f"ETH/{base_currency}",
        target_balance=target_balance,
    )


class _Bot:
    """Stands in for a registered bot. Only what the sum reads."""

    def __init__(self, cfg: Any, rate: Any = 1.0, chunk: Any = 0.0) -> None:
        self.config = cfg
        self._quote_to_usd = rate
        self._chunk_size_base = chunk


class _RateRaises(_Bot):
    """A bot whose cached rate blows up when read."""

    @property
    def _quote_to_usd(self) -> float:
        raise RuntimeError("rate cache blown")

    @_quote_to_usd.setter
    def _quote_to_usd(self, _value: Any) -> None:
        pass


class _NoRateAttribute:
    """A bot that has no cached rate at all."""

    def __init__(self, cfg: Any) -> None:
        self.config = cfg


class _ChunkRaises(_Bot):
    """A bot whose allocated chunk blows up when read."""

    @property
    def _chunk_size_base(self) -> float:
        raise RuntimeError("chunk record corrupt")

    @_chunk_size_base.setter
    def _chunk_size_base(self, _value: Any) -> None:
        pass


class _CfgAllocationRaises:
    """A config whose dollar allocation blows up when read."""

    exchange_id = EXCHANGE
    base_currency = "USD"

    @property
    def target_balance(self) -> float:
        raise RuntimeError("settings row corrupt")


class _CfgUnreadable:
    """A config that cannot be read at all, so we cannot even tell
    which pool this bot belongs to."""

    base_currency = "USD"
    target_balance = CLAIM_USD

    @property
    def exchange_id(self) -> str:
        raise RuntimeError("settings row corrupt")


def _manager(**bots: Any) -> BotManager:
    manager = BotManager.__new__(BotManager)
    manager._bots = dict(bots)
    return manager


def _dollar_fleet(third: Any) -> BotManager:
    """The asking bot and three siblings, all on the dollar pool."""
    return _manager(
        asker=_Bot(_cfg()),
        sib_1=_Bot(_cfg()),
        sib_2=_Bot(_cfg()),
        sib_3=third,
    )


def _bitcoin_fleet(third: Any) -> BotManager:
    """The same shape on a Bitcoin pool, where a rate is really needed."""
    return _manager(
        asker=_Bot(_cfg("BTC"), rate=BTC_USD),
        sib_1=_Bot(_cfg("BTC"), rate=BTC_USD),
        sib_2=_Bot(_cfg("BTC"), rate=BTC_USD),
        sib_3=third,
    )


def _ask(manager: BotManager, currency: str = "USD") -> Any:
    return manager.sum_sibling_base_currency_claims(
        "asker", EXCHANGE, currency)


@pytest.fixture
def warned():
    """Everything this code logs at warning level or worse.

    This listens on the logger the code actually writes to. pytest's
    own capture listens on the root logger instead, and anything that
    builds the app's logging engine stops these records reaching the
    root for the rest of the run. The capture then sees nothing and
    the check quietly stops checking. Measured: alone these tests
    passed, in the full suite fourteen of them failed on an empty
    capture while the code under test was doing exactly the right
    thing. Listening on the real logger does not depend on what any
    other test did first.
    """
    caught: list[str] = []

    class _Catch(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.levelno >= logging.WARNING:
                caught.append(record.getMessage())

    log = logging.getLogger(LOGGER)
    handler = _Catch()
    was = log.level
    log.addHandler(handler)
    log.setLevel(logging.WARNING)
    try:
        yield caught
    finally:
        log.removeHandler(handler)
        log.setLevel(was)


# ---------------------------------------------------------------------
# The paired test the whole file turns on.
# ---------------------------------------------------------------------

def test_one_unreadable_sibling_is_never_silently_dropped(warned) -> None:
    """Same fleet, twice. Readable gives the true total and says
    nothing. Unreadable gives no total and says whose claim went
    missing and how big the gap was.

    If the drop ever stops being reported, the second half fails.
    """
    readable = _ask(_dollar_fleet(_Bot(_cfg())))
    assert readable == pytest.approx(3 * CLAIM_USD)
    assert warned == [], "An honest total must not raise an alarm."

    broken = _ask(_dollar_fleet(_Bot(_CfgAllocationRaises())))

    assert broken is None, (
        "A total that leaves a bot's claim out is lower than the truth. "
        f"It reported {broken!r} where the truth is {3 * CLAIM_USD}.")
    assert len(warned) == 1
    assert "sib_3" in warned[0]
    assert "2000.00000000" in warned[0], (
        "The warning must say how big the gap was.")


# ---------------------------------------------------------------------
# Controls. Every honest case must still hand back a real number.
# ---------------------------------------------------------------------

def test_every_sibling_readable_totals_all_claims() -> None:
    assert _ask(_dollar_fleet(_Bot(_cfg()))) == pytest.approx(
        3 * CLAIM_USD)


def test_the_asking_bot_does_not_claim_against_itself() -> None:
    """Three siblings claim $1,000 each. The asker's own $1,000 is not
    part of the answer, so the answer is 3000 and not 4000."""
    assert _ask(_dollar_fleet(_Bot(_cfg()))) == pytest.approx(3000.0)


def test_a_bot_on_another_exchange_is_not_a_claim() -> None:
    """A different exchange is a different pool of money. Excluding it
    is correct and is not a dropped claim, so a number comes back."""
    total = _ask(_dollar_fleet(_Bot(_cfg(exchange_id="kraken"))))
    assert total == pytest.approx(2 * CLAIM_USD)


def test_a_bot_on_another_currency_is_not_a_claim() -> None:
    total = _ask(_dollar_fleet(_Bot(_cfg("EUR"))))
    assert total == pytest.approx(2 * CLAIM_USD)


def test_a_bot_that_claims_nothing_is_a_real_zero() -> None:
    """No allocation means no claim. It does not mean unknown."""
    total = _ask(_dollar_fleet(_Bot(_cfg(target_balance=0.0))))
    assert total == pytest.approx(2 * CLAIM_USD)


def test_an_allocated_chunk_counts_towards_the_total() -> None:
    """A chunk is already in pool units and is added as it stands."""
    total = _ask(_dollar_fleet(
        _Bot(_cfg(target_balance=0.0), chunk=250.0)))
    assert total == pytest.approx(2 * CLAIM_USD + 250.0)


def test_a_bitcoin_pool_converts_dollars_with_the_cached_rate() -> None:
    total = _bitcoin_fleet(
        _Bot(_cfg("BTC"), rate=BTC_USD)
    ).sum_sibling_base_currency_claims("asker", EXCHANGE, "BTC")
    assert total == pytest.approx(3 * CLAIM_USD / BTC_USD)


@pytest.mark.parametrize("bot", [
    _Bot(_cfg(), rate=0.0),
    _Bot(_cfg(), rate=math.nan),
    _NoRateAttribute(_cfg()),
    _RateRaises(_cfg()),
], ids=["rate-zero", "rate-not-a-number", "no-rate", "rate-raises"])
def test_a_dollar_pool_needs_no_rate_and_still_counts_in_full(
        bot: Any) -> None:
    """One dollar per unit is the true rate for a dollar pool, not a
    stand-in for a rate we could not get. So an unusable cached rate
    costs nothing here and the claim is still counted."""
    assert _ask(_dollar_fleet(bot)) == pytest.approx(3 * CLAIM_USD)


# ---------------------------------------------------------------------
# Defect rows. Each one used to vanish from the total in silence.
# ---------------------------------------------------------------------

@pytest.mark.parametrize("bot,expect_in_warning", [
    (_Bot(_CfgUnreadable()), "settings could not be read"),
    (_Bot(_CfgAllocationRaises()), "dollar allocation could not be read"),
    (_Bot(_cfg(target_balance=math.nan)), "is not a number"),
    (_Bot(_cfg(target_balance=-5.0)), "negative"),
    (_ChunkRaises(_cfg()), "allocated chunk could not be read"),
    (_Bot(_cfg(), chunk=math.nan), "not a number"),
    (_Bot(_cfg(), chunk=-3.0), "negative"),
], ids=["config-unreadable", "allocation-raises", "allocation-not-a-number",
        "allocation-negative", "chunk-raises", "chunk-not-a-number",
        "chunk-negative"])
def test_an_unreadable_sibling_stops_the_total(
        bot: Any, expect_in_warning: str, warned) -> None:
    total = _ask(_dollar_fleet(bot))
    assert total is None
    messages = " ".join(warned)
    assert "sib_3" in messages
    assert expect_in_warning in messages


@pytest.mark.parametrize("bot", [
    _RateRaises(_cfg("BTC")),
    _Bot(_cfg("BTC"), rate=0.0),
    _Bot(_cfg("BTC"), rate=-1.0),
    _Bot(_cfg("BTC"), rate=math.nan),
    _NoRateAttribute(_cfg("BTC")),
], ids=["rate-raises", "rate-zero", "rate-negative", "rate-not-a-number",
        "no-rate"])
def test_no_usable_rate_on_a_real_pool_stops_the_total(
        bot: Any, warned) -> None:
    """Without a rate a dollar allocation cannot be turned into pool
    units. The old code used one dollar per unit, which read a $1,000
    allocation as a claim on 1,000 Bitcoin."""
    total = _bitcoin_fleet(bot).sum_sibling_base_currency_claims(
        "asker", EXCHANGE, "BTC")
    assert total is None
    assert "sib_3" in " ".join(warned)


def test_two_unreadable_siblings_are_both_named(warned) -> None:
    fleet = _manager(
        asker=_Bot(_cfg()),
        sib_1=_Bot(_cfg()),
        sib_2=_Bot(_CfgAllocationRaises()),
        sib_3=_Bot(_CfgUnreadable()),
    )
    total = _ask(fleet)
    assert total is None
    messages = " ".join(warned)
    assert "sib_2" in messages
    assert "sib_3" in messages


def test_no_currency_named_gives_no_total_rather_than_zero(warned) -> None:
    """Zero is the most dangerous answer of all. Zero says the whole
    pool is free."""
    total = _ask(_dollar_fleet(_Bot(_cfg())), currency="")
    assert total is None
    assert len(warned) == 1


def test_nothing_can_be_mistaken_for_a_pool_with_no_claims() -> None:
    """An empty fleet really does have no claims, and says so with a
    number. An unreadable fleet says nothing at all. The two answers
    must never be the same value."""
    empty = _manager(asker=_Bot(_cfg()))
    assert empty.sum_sibling_base_currency_claims(
        "asker", EXCHANGE, "USD") == 0.0
    assert _ask(_dollar_fleet(_Bot(_CfgUnreadable()))) is None
