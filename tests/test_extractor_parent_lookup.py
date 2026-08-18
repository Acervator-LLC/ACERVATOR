"""Finding the parent bot that a returning Extractor should pay into.

WHAT THIS IS FOR
An Extractor works in one base currency. When it closes a position it
hands that base currency back. The operator's design says the money goes
to the Scrumming Bot that HOLDS that currency, so the parent can raise
its target and keep the gain instead of selling it away as surplus.

THE MATCHING RULE
A Scrumming Bot holds one asset. It is named in the bot's settings as
the target asset. So the parent of an Extractor working ETH is the
Scrumming Bot whose target asset is ETH.

AND IT MUST BE THE SAME EXCHANGE. A parent and its Extractor live on one
exchange. Money that came back on one exchange never landed on another,
so a bot on a different exchange is not a parent however well its
currency matches. Every bot's settings record the exchange it runs on,
and the Extractor names its own when it asks.

WHY IT REFUSES TO GUESS
If two Scrumming Bots hold the same asset, there is no way to tell which
one the money belongs to. The lookup returns nothing. Real money moves
on the answer, so a coin flip between two owners is worse than no
answer at all: the wrong parent would raise ITS target on money it never
received, and the right one would stay short.

An Extractor can never be a parent. It is the child in this
relationship, and it has no target balance to raise.

THE TABLE BELOW IS THE WHOLE ACCEPTED SET. It was written before the
lookup existed. Each row names the bots on the books, the currency
handed back, and the bot that must come out.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.event_bus import EventBus  # noqa: E402
from src.trading.bot_container import BotManager, BotMode  # noqa: E402
from src.trading.extractor_bot import ExtractorBot  # noqa: E402
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

SCRUMMING = "scrumming"
EXTRACTOR = "extractor"


def _bot(kind: str, bot_id: str, target_asset: str, exchange: str):
    """One entry for the manager's books.

    Built without running the real constructor, which would need an
    exchange, a bus and a live balance. The lookup reads the bot's type
    and its settings, and both of those are real here.
    """
    cls = ScrummingBot if kind == SCRUMMING else ExtractorBot
    mode = BotMode.SCRUMMING if kind == SCRUMMING else BotMode.EXTRACTOR
    bot = object.__new__(cls)
    bot.bot_id = bot_id
    bot.config = type("_Cfg", (), {
        "exchange_id": exchange,
        "mode": mode,
        "target_asset": target_asset,
        "base_currency": "USD",
    })()
    return bot


def _manager(entries):
    """A real BotManager holding the given bots, on its own private bus.

    A private bus keeps this file off the shared one, so nothing here
    can reach a live handler.
    """
    manager = BotManager(bus=EventBus())
    for kind, bot_id, target_asset, exchange in entries:
        bot = _bot(kind, bot_id, target_asset, exchange)
        manager._bots[bot_id] = bot
    return manager


COINBASE = "coinbase"
KRAKEN = "kraken"

ONE_ETH_HOLDER = [(SCRUMMING, "scrum-eth", "ETH", COINBASE)]

# (row name, bots on the books, exchange asking, currency handed back,
#  bot id expected)
TABLE = [
    ("1 one holder",
     ONE_ETH_HOLDER, COINBASE, "ETH", "scrum-eth"),
    ("2 no holder",
     [(SCRUMMING, "scrum-btc", "BTC", COINBASE)], COINBASE, "ETH", None),
    ("3 two holders refuse",
     [(SCRUMMING, "scrum-eth-a", "ETH", COINBASE),
      (SCRUMMING, "scrum-eth-b", "ETH", COINBASE)], COINBASE, "ETH", None),
    ("4 lower case",
     ONE_ETH_HOLDER, COINBASE, "eth", "scrum-eth"),
    ("5 surrounding spaces",
     ONE_ETH_HOLDER, COINBASE, "  ETH  ", "scrum-eth"),
    ("6a empty text",
     ONE_ETH_HOLDER, COINBASE, "", None),
    ("6b nothing",
     ONE_ETH_HOLDER, COINBASE, None, None),
    ("6c a number",
     ONE_ETH_HOLDER, COINBASE, 123, None),
    ("7 holder is an extractor",
     [(EXTRACTOR, "extract-eth", "ETH", COINBASE)], COINBASE, "ETH", None),
    # 8 and 9 are one pair. They differ in the holder's exchange and in
    # nothing else, so 9 finding nothing can only be the exchange.
    ("8 the holder is on the same exchange",
     [(SCRUMMING, "scrum-eth", "ETH", COINBASE)], COINBASE, "ETH",
     "scrum-eth"),
    ("9 the only holder is on another exchange",
     [(SCRUMMING, "scrum-eth", "ETH", KRAKEN)], COINBASE, "ETH", None),
]


@pytest.mark.parametrize(
    "entries,asked_from,handed_back,expected_id",
    [row[1:] for row in TABLE],
    ids=[row[0] for row in TABLE],
)
def test_parent_lookup_table(entries, asked_from, handed_back, expected_id):
    manager = _manager(entries)
    try:
        found = manager.find_parent_bot_for_base_currency(
            handed_back, exchange_id=asked_from)
    finally:
        manager.detach_bus()

    if expected_id is None:
        assert found is None, (
            f"expected no parent for {handed_back!r}, got "
            f"{getattr(found, 'bot_id', found)!r}")
    else:
        assert found is not None, f"expected {expected_id}, got nothing"
        assert found.bot_id == expected_id


def test_the_bot_that_comes_back_can_take_the_money():
    """The answer must be usable. A parent that cannot book an arrival
    is not a parent, and the caller would fail at the moment money moves.
    """
    manager = _manager(ONE_ETH_HOLDER)
    try:
        found = manager.find_parent_bot_for_base_currency(
            "ETH", exchange_id=COINBASE)
    finally:
        manager.detach_bus()
    assert callable(getattr(found, "apply_extractor_tranche_return", None))


def test_an_empty_set_of_books_finds_nothing():
    """CONTROL for the whole table. With no bots at all every row above
    would return nothing, so this proves the rows that DO find a bot are
    finding it because it is on the books.
    """
    manager = _manager([])
    try:
        assert manager.find_parent_bot_for_base_currency(
            "ETH", exchange_id=COINBASE) is None
    finally:
        manager.detach_bus()
