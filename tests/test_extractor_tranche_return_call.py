"""Telling the parent bot when an Extractor tranche sells.

WHAT THIS IS FOR
An Extractor works in one currency. When it sells a tranche, that
currency comes back. The operator's design says the Scrumming Bot that
HOLDS that currency must be told, so it can raise its own target balance
by what arrived and keep the gain. If nobody tells it, the arrival looks
like spare money and the parent sells it straight back out.

The booking already existed. The lookup already existed. Nothing called
them. This file is the call.

WHAT GETS PASSED
What actually landed, and only that. The dollar figure and the unit
figure both come off the fill, through this bot's own money conversion.
No profit is worked out here. The booking refuses anything that is not
exactly a plain number, so the values are handed over as plain numbers or
not at all.

WHY A MISSING PARENT MUST NOT BREAK THE SALE
Not finding a parent costs one lift. Breaking the exit strands real money
in a half-sold position. So the sale always finishes, whatever the lookup
or the booking does.

THE TABLE BELOW IS THE WHOLE ACCEPTED SET. It was written before the call
existed. Each row names what the sale did, which bots are on the books,
and whether the parent hears about it.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.event_bus import EventBus  # noqa: E402
from src.trading.bot_container import BotManager, BotMode  # noqa: E402
from src.trading.extractor_bot import ExtractorBot, ExtractorPosition  # noqa: E402
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

# The one sale every row uses, so the rows differ only in the thing they
# are testing. Eight alt units leave at 0.00125 base each, so 0.01 base
# comes back. The bot's stored money rate turns 0.01 base into $20.
SOLD_UNITS = 8.0
FILL_PRICE = 0.00125
BASE_BACK = SOLD_UNITS * FILL_PRICE
USD_PER_BASE = 2000.0
USD_BACK = BASE_BACK * USD_PER_BASE

PARENT_START_TARGET = 200.0
PARENT_START_HOLDINGS = 1.0

# The one exchange every bot in this file runs on. A parent and its
# Extractor are bound to one exchange, so the sale can only reach a
# parent that names the same one.
EXCHANGE = "coinbase"


class _Bus:
    """Collects what the bot announces instead of putting it on the real
    bus, so nothing here can reach a live handler."""

    def __init__(self):
        self.events = []

    def emit(self, name, **kw):
        self.events.append((name, kw))


class _Order:
    """A filled order, shaped the way the exit reads one."""

    def __init__(self, filled, average_price):
        self.filled = filled
        self.average_price = average_price


def _parent(bot_id="parent-eth", holds="ETH"):
    """A Scrumming Bot that holds a currency and can book an arrival.

    Built the way the booking's own tests build one: real class, real
    booking method, real numbers, no exchange and no live bus.

    Every bot built here records the booking calls it receives in its own
    `seen` list, and then lets the real booking run. EVERY bot records,
    not just the one a row expects to be paid, because a row that only
    watches the right bot cannot see the money going to the wrong one.
    """
    b = object.__new__(ScrummingBot)
    b.bot_id = bot_id
    b.config = type(
        "C",
        (),
        {
            "exchange_id": EXCHANGE,
            "symbol": f"{holds}/USD",
            "target_asset": holds,
            "base_currency": holds,
            "target_balance": PARENT_START_TARGET,
            "max_target_growth_pct": 1.0,
            "profit_folding_active": True,
            "scrumming_interval_pct": 1.0,
        },
    )()
    b._target_balance = PARENT_START_TARGET
    b._anchor_target_balance = PARENT_START_TARGET
    b._current_holdings = PARENT_START_HOLDINGS
    b._quote_to_usd = 1.0
    b._bus = _Bus()
    b._fold_tranches = []
    b._main_lots = [
        {"units": PARENT_START_HOLDINGS, "initial_buy_price": PARENT_START_TARGET}
    ]
    b.seen = []
    real = b.apply_extractor_tranche_return

    def spy(*args, **kwargs):
        b.seen.append(dict(kwargs))
        return real(*args, **kwargs)

    b.apply_extractor_tranche_return = spy
    return b


def _state(parent):
    """The three parent numbers an arrival is supposed to move."""
    return (parent._target_balance, parent._current_holdings, len(parent._main_lots))


def _extractor(sale, manager):
    """An Extractor holding one position, about to sell all of it.

    ``sale`` decides what the exchange does: "fill" returns a filled
    order, "none" returns nothing at all, "raise" fails outright.
    """
    bot = object.__new__(ExtractorBot)
    bot.bot_id = "extract-eth"
    bot.config = type(
        "C",
        (),
        {
            "exchange_id": EXCHANGE,
            "mode": BotMode.EXTRACTOR,
            "symbol": "LINK/ETH",
            "target_asset": "LINK",
            "base_currency": "ETH",
            "extractor_direction": "normal",
            "extractor_exit_pct": 100.0,
            "extractor_max_compounding_tier": 1,
        },
    )()
    bot._bus = _Bus()
    bot._bot_manager = manager
    bot._chunk_to_base_rate = USD_PER_BASE
    bot._chunk_free_base = 0.0
    bot._cycle_extracted_total = 0.0
    bot._lifetime_extracted_total = 0.0
    bot._chunk_extracted_total = 0.0
    bot._closed_position_log = []
    bot._closed_log_max = 200
    bot._last_correction_tick = {}

    pos = ExtractorPosition(
        pair="LINK/ETH",
        state="IN_FLIGHT",
        artillery_size_base=0.008,
        artillery_size_usd_at_entry=16.0,
        alt_units=SOLD_UNITS,
        entry_price_base_per_alt=0.001,
        avg_buy_price_base_per_alt=0.001,
        cost_basis_base=0.008,
        opened_at=1000.0,
    )
    bot._positions = {"LINK/ETH": pos}

    async def _sell(**kwargs):
        if sale == "raise":
            raise RuntimeError("exchange refused the sell")
        if sale == "none":
            return None
        return _Order(SOLD_UNITS, FILL_PRICE)

    bot.guarded_place_order = _sell
    return bot, pos


def _books(kind, parent):
    """The bots the manager is holding, for this row.

    Returns the manager to hand the Extractor -- None when the row says
    no manager is wired at all -- and every bot that could possibly be
    paid, so a row can check that NOBODY was paid, not merely that the
    expected one was not.
    """
    everyone = [parent]
    if kind == "no-manager":
        return None, everyone
    manager = BotManager(bus=EventBus())
    if kind == "eth-parent":
        manager._bots["parent-eth"] = parent
    elif kind == "btc-only":
        other = _parent("parent-btc", holds="BTC")
        manager._bots["parent-btc"] = other
        everyone.append(other)
    elif kind == "two-eth":
        other = _parent("parent-eth-2", holds="ETH")
        manager._bots["parent-eth"] = parent
        manager._bots["parent-eth-2"] = other
        everyone.append(other)
    return manager, everyone


TOLD = "told"
NOT_TOLD = "not told"

# (row name, what the sale did, which bots are on the books, outcome)
TABLE = [
    ("1 it sells and a parent holds the currency", "fill", "eth-parent", TOLD),
    ("2 no parent: nothing on the books holds it", "fill", "btc-only", NOT_TOLD),
    (
        "3 no parent: two bots hold it, so the lookup refuses",
        "fill",
        "two-eth",
        NOT_TOLD,
    ),
    ("4 the sale did not fill", "none", "eth-parent", NOT_TOLD),
    ("5 the sale failed outright", "raise", "eth-parent", NOT_TOLD),
    ("6 no manager is wired to this bot", "fill", "no-manager", NOT_TOLD),
]


@pytest.mark.parametrize(
    "sale,books,outcome",
    [row[1:] for row in TABLE],
    ids=[row[0] for row in TABLE],
)
def test_parent_is_told_table(sale, books, outcome):
    parent = _parent()
    before = _state(parent)
    manager, everyone = _books(books, parent)
    bot, pos = _extractor(sale, manager)
    try:
        asyncio.run(bot._execute_bullish_exit(pos, FILL_PRICE))
    finally:
        if manager is not None:
            manager.detach_bus()

    calls = [c for b in everyone for c in b.seen]
    if outcome == NOT_TOLD:
        assert calls == [], f"a bot was told anyway: {calls}"
        for b in everyone:
            assert _state(b) == (
                PARENT_START_TARGET,
                PARENT_START_HOLDINGS,
                1,
            ), f"{b.bot_id} moved with no arrival"
        return

    assert len(calls) == 1, f"expected exactly one call, got {len(calls)}"
    assert parent.seen == calls, "the wrong bot was paid"
    only = calls[0]
    assert only["usd_value"] == pytest.approx(USD_BACK)
    assert only["base_units"] == pytest.approx(BASE_BACK)
    assert type(only["usd_value"]) is float
    assert type(only["base_units"]) is float
    assert only["source"] == "extract-eth"
    after = _state(parent)
    assert after[0] == pytest.approx(before[0] + USD_BACK)
    assert after[1] == pytest.approx(before[1] + BASE_BACK)
    assert after[2] == before[2] + 1


def test_the_values_passed_are_the_ones_that_landed():
    """THE POINT, with the numbers written out.

    Eight alt units leave at 0.00125 base each. 0.01 base comes back.
    At $2000 the base, that is $20. The parent must be told $20 and
    0.01 units -- what arrived, not a profit. The profit on this sale
    was 0.002 base, and 0.002 is not what gets passed.
    """
    parent = _parent()
    manager, _everyone = _books("eth-parent", parent)
    bot, pos = _extractor("fill", manager)
    try:
        asyncio.run(bot._execute_bullish_exit(pos, FILL_PRICE))
    finally:
        manager.detach_bus()

    assert len(parent.seen) == 1
    assert parent.seen[0]["usd_value"] == pytest.approx(20.0)
    assert parent.seen[0]["base_units"] == pytest.approx(0.01)
    gain_base = BASE_BACK - 0.008
    assert parent.seen[0]["base_units"] != pytest.approx(gain_base)


def test_the_booking_accepts_what_is_handed_to_it():
    """The values must be usable, not merely present. The booking
    refuses anything that is not exactly a plain number, and a refusal
    would leave the parent unlifted while every call count still read 1.
    """
    parent = _parent()
    manager, _everyone = _books("eth-parent", parent)
    bot, pos = _extractor("fill", manager)
    try:
        asyncio.run(bot._execute_bullish_exit(pos, FILL_PRICE))
    finally:
        manager.detach_bus()

    assert parent._target_balance == pytest.approx(PARENT_START_TARGET + USD_BACK)
    assert parent._current_holdings == pytest.approx(PARENT_START_HOLDINGS + BASE_BACK)


def test_a_broken_lookup_does_not_break_the_sale():
    """Losing the lift is a missed gain. Breaking the exit strands real
    money in a half-sold position. So a lookup that blows up must not
    stop the Extractor finishing.
    """
    parent = _parent()
    manager, _everyone = _books("eth-parent", parent)

    def _explode(_currency, **_kwargs):
        raise RuntimeError("lookup is broken")

    manager.find_parent_bot_for_base_currency = _explode
    bot, pos = _extractor("fill", manager)
    try:
        asyncio.run(bot._execute_bullish_exit(pos, FILL_PRICE))
    finally:
        manager.detach_bus()

    assert bot._positions == {}, "the position was not closed"
    assert bot._chunk_free_base == pytest.approx(BASE_BACK)
    assert len(bot._closed_position_log) == 1
    assert _state(parent) == (PARENT_START_TARGET, PARENT_START_HOLDINGS, 1)


def test_a_broken_booking_does_not_break_the_sale():
    """Same promise, one step later: the parent is found, and then the
    booking itself blows up."""
    parent = _parent()

    def _explode(**_kwargs):
        raise RuntimeError("booking is broken")

    parent.apply_extractor_tranche_return = _explode
    manager, _everyone = _books("eth-parent", parent)
    bot, pos = _extractor("fill", manager)
    try:
        asyncio.run(bot._execute_bullish_exit(pos, FILL_PRICE))
    finally:
        manager.detach_bus()

    assert bot._positions == {}, "the position was not closed"
    assert bot._chunk_free_base == pytest.approx(BASE_BACK)
    assert len(bot._closed_position_log) == 1


def test_the_sale_completes_on_every_row():
    """CONTROL for the whole table. Every row above that expects silence
    would also be satisfied by an exit that never ran at all. This proves
    the sale really happened on the rows where the exchange filled it, so
    the silence is the caller declining and not the exit dying early.
    """
    for sale, books in (
        ("fill", "eth-parent"),
        ("fill", "btc-only"),
        ("fill", "two-eth"),
        ("fill", "no-manager"),
    ):
        parent = _parent()
        manager, _everyone = _books(books, parent)
        bot, pos = _extractor(sale, manager)
        try:
            asyncio.run(bot._execute_bullish_exit(pos, FILL_PRICE))
        finally:
            if manager is not None:
                manager.detach_bus()
        assert bot._positions == {}, f"{books}: position not closed"
        assert bot._chunk_free_base == pytest.approx(BASE_BACK), books

    for sale in ("none", "raise"):
        parent = _parent()
        manager, _everyone = _books("eth-parent", parent)
        bot, pos = _extractor(sale, manager)
        try:
            asyncio.run(bot._execute_bullish_exit(pos, FILL_PRICE))
        finally:
            manager.detach_bus()
        assert bot._positions != {}, f"{sale}: position closed without a fill"
        assert bot._chunk_free_base == 0.0, sale
