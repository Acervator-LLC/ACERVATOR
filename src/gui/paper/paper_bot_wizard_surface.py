# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Paper Trader's bot wizard: its bridge method and the readings both forks
share.

``METHOD`` names the method ``bot_wizard.js`` asks and ``view_model`` answers it
with Live's ``bot_wizard_surface.build_view_model`` under that name.
``venue_markets`` lists one market row per product the venue trades,
``seated_exchanges`` builds the venue list from the seated ids,
``wizard_exchanges`` adds the venue the adapter reads to it, ``venue_timeframes``
lists each venue's timeframes for the React fork, ``stored_defaults`` reads the
operator's settings file, and ``extractor_parent_refusal`` is the window's
parent rule over ``PaperBot`` records.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from ...core.settings import SettingsManager
from ...paper.fleet_source import SCRUMMING_MODE, PaperBot
from ...trading.container.config import as_finite_float
from ..main_tabs import bot_wizard_surface as live
from ..main_tabs.trading_tab_surface import exchange_display_name

METHOD = "paper_bot_wizard.state"

#: The volume and volatility a product row carries: ``Product`` records neither.
NO_VOLUME = 0
NO_VOLATILITY = 0

#: Below this the last price is printed to eight places, above it to two.
WHOLE_UNIT_PRICE = 1.0
SMALL_PRICE_PLACES = 8
PAIRS_FORMAT = "{pairs} {base} pairs, {priced} carrying a last price"
POOL_PAIRS_FORMAT = (
    "{pairs} */{base} pairs available, {priced} carrying a last price. "
    "The Extractor auto-scans the top-N of them."
)

CREATED_FORMAT = "Bot {bot_id} created: {symbol} ({mode}) - IDLE"
REJECTED_FORMAT = "Bot creation REJECTED — mode-shape violation: {error}"
REFUSED_FORMAT = "Extractor creation REFUSED — {reason}"
CANCELLED_TEXT = "Bot creation cancelled."
OPENING_FORMAT = "Creating new bot for {exchange_id}..."
REFUSAL_TITLE = "Extractor needs a parent bot"
REFUSAL_BOX_FORMAT = "{reason}\n\nBot creation aborted."

NO_HOLDER_FORMAT = (
    "No Scrumming Bot on {venue} holds {asset}.\n\n"
    "An Extractor is a sibling of the Scrumming Bot that holds its base "
    "currency: when the Extractor closes a position it hands {asset} back to "
    "that bot, which raises its target balance to keep the gain. With no such "
    "bot there is nowhere for the money to go.\n\n"
    "Create a Scrumming Bot for {asset} on {venue} first, then create this "
    "Extractor."
)
MANY_HOLDERS_FORMAT = (
    "{count} Scrumming Bots on {venue} hold {asset}: {ids}.\n\n"
    "The parent is ambiguous. An Extractor hands {asset} back to ONE holder, "
    "and nothing here can tell which of these earned it — choosing for you "
    "would raise the wrong bot's target on money it never received, while the "
    "right one stayed short.\n\n"
    "Naming the parent is your call. Leave exactly one Scrumming Bot holding "
    "{asset} on {venue}, then create this Extractor."
)
UNKNOWN_ASSET = "?"
UNKNOWN_VENUE = "this exchange"


def view_model(params: dict) -> dict:
    """Answer the ``paper_bot_wizard.state`` request with Live's payload under
    ``METHOD``."""
    found = live.view_model(params)
    found["method"] = METHOD
    return found


def venue_markets(exchange: Any) -> dict[str, list[dict]]:
    """One market row per product ``exchange.products`` answers, keyed by
    ``exchange.venue``.

    A ``Product`` carries a last price and neither a volume nor a volatility,
    so each row reads ``NO_VOLUME`` and ``NO_VOLATILITY`` and the asset page
    labels by price.
    """
    venue = str(exchange.venue())
    rows: list[dict] = []
    seen: set[str] = set()
    for product in exchange.products():
        base = str(product.base).upper()
        quote = str(product.quote).upper()
        symbol = f"{base}/{quote}"
        if not base or not quote or symbol in seen:
            continue
        seen.add(symbol)
        rows.append(
            {
                live.MARKET_SYMBOL_KEY: symbol,
                live.MARKET_BASE_KEY: base,
                live.MARKET_QUOTE_KEY: quote,
                live.MARKET_VOLUME_KEY: NO_VOLUME,
                live.MARKET_VOLATILITY_KEY: NO_VOLATILITY,
                live.MARKET_PRICE_KEY: product.price,
            }
        )
    return {venue: rows} if rows else {}


def price_label(price: Any, quote: str) -> str:
    """The last-price tail an asset row carries, empty when ``price`` is not a
    finite number.

    A price of ``WHOLE_UNIT_PRICE`` or more prints to two places and a smaller
    one to ``SMALL_PRICE_PLACES``, with the trailing zeros cut; the quote is
    named because a row on ``ETH/BTC`` prices in BTC, not in dollars.
    """
    found = as_finite_float(price)
    if found is None:
        return ""
    if abs(found) >= WHOLE_UNIT_PRICE:
        printed = f"{found:,.2f}"
    else:
        printed = f"{found:.{SMALL_PRICE_PLACES}f}".rstrip("0").rstrip(".")
    return f"  ({printed} {quote})"


def seated_exchanges(exchange_ids: Iterable[str]) -> list[dict]:
    """The wizard's venue list from the seated ids, each captioned as
    ``exchange_display_name`` captions its sub-tab."""
    return [
        {
            live.EXCHANGE_ID_KEY: str(eid),
            live.EXCHANGE_DISPLAY_KEY: exchange_display_name({"exchange_id": str(eid)}),
        }
        for eid in exchange_ids
        if str(eid)
    ]


def wizard_exchanges(exchange_ids: Iterable[str], exchange: Any) -> list[dict]:
    """``seated_exchanges`` over the seated ids, then ``exchange.venue`` when it
    is not seated."""
    seated = [str(eid) for eid in exchange_ids if str(eid)]
    venue = str(exchange.venue())
    filed = [venue] if venue and venue not in seated else []
    return seated_exchanges([*seated, *filed])


def venue_timeframes(exchanges: Iterable[dict]) -> dict[str, list[str]]:
    """The timeframes ``available_timeframes`` lists per venue in ``exchanges``,
    the bag the React wizard narrows its pages with."""
    from ...exchange.timeframes import available_timeframes

    out: dict[str, list[str]] = {}
    for venue in exchanges:
        eid = str(venue.get(live.EXCHANGE_ID_KEY) or "")
        if eid:
            out[eid] = list(available_timeframes(eid))
    return out


def stored_defaults() -> dict:
    """The operator's stored settings, read through ``SettingsManager.get_all``
    as the window reads them for the wizard; nothing is written."""
    return SettingsManager().get_all()


def scrumming_holders(
    bots: Iterable[PaperBot], base_currency: str, exchange_id: str
) -> list[PaperBot]:
    """Every scrumming ``PaperBot`` on ``exchange_id`` whose asset is
    ``base_currency``, matched as the registry matches ``target_asset``."""
    wanted = str(base_currency or "").strip().upper()
    if not wanted:
        return []
    return [
        bot
        for bot in bots
        if bot.mode == SCRUMMING_MODE
        and bot.exchange_id == exchange_id
        and bot.asset.strip().upper() == wanted
    ]


def extractor_parent_refusal(
    bots: Iterable[PaperBot], base_currency: str, exchange_id: str
) -> Optional[str]:
    """The window's refusal text when no single scrumming bot holds
    ``base_currency`` on ``exchange_id``, or None when exactly one does."""
    asset = str(base_currency or "").strip().upper() or UNKNOWN_ASSET
    venue = str(exchange_id or "").strip() or UNKNOWN_VENUE
    holders = scrumming_holders(bots, base_currency, exchange_id)
    if len(holders) == 1:
        return None
    if not holders:
        return NO_HOLDER_FORMAT.format(venue=venue, asset=asset)
    return MANY_HOLDERS_FORMAT.format(
        count=len(holders),
        venue=venue,
        asset=asset,
        ids=", ".join(bot.bot_id for bot in holders),
    )


def created_line(bot: PaperBot) -> str:
    """The Activity Log line Live writes for a created bot."""
    return CREATED_FORMAT.format(bot_id=bot.bot_id, symbol=bot.symbol, mode=bot.mode)


__all__ = [
    "CANCELLED_TEXT",
    "CREATED_FORMAT",
    "MANY_HOLDERS_FORMAT",
    "METHOD",
    "NO_HOLDER_FORMAT",
    "NO_VOLATILITY",
    "NO_VOLUME",
    "OPENING_FORMAT",
    "PAIRS_FORMAT",
    "POOL_PAIRS_FORMAT",
    "REFUSAL_BOX_FORMAT",
    "REFUSAL_TITLE",
    "REFUSED_FORMAT",
    "REJECTED_FORMAT",
    "SMALL_PRICE_PLACES",
    "WHOLE_UNIT_PRICE",
    "created_line",
    "extractor_parent_refusal",
    "price_label",
    "scrumming_holders",
    "seated_exchanges",
    "stored_defaults",
    "venue_markets",
    "venue_timeframes",
    "view_model",
    "wizard_exchanges",
]
