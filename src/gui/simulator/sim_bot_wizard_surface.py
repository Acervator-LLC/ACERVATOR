"""The Simulator's bot wizard: its bridge method and the readings both forks
share.

``METHOD`` names the method ``sim_bot_wizard.js`` asks and ``view_model``
answers it with Live's ``bot_wizard_surface.build_view_model`` under that
name. ``tablet_markets`` lists one market row per tablet asset under each base
currency, ``seated_exchanges`` builds the venue list from the seated ids,
``wizard_exchanges`` adds the tablets' exchanges to it, ``venue_timeframes``
lists each venue's timeframes for the React fork, ``stored_defaults`` reads
the operator's settings file, and ``extractor_parent_refusal`` is the
window's parent rule over ``SimBot`` records.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from ...core.settings import SettingsManager
from ...simulator.fleet_source import SCRUMMING_MODE, SimBot
from ..main_tabs import bot_wizard_surface as live
from ..main_tabs.trading_tab_surface import exchange_display_name

METHOD = "sim_bot_wizard.state"

#: The volume and volatility a tablet row carries: a tablet records neither.
NO_VOLUME = 0
NO_VOLATILITY = 0

CREATED_FORMAT = "Bot {bot_id} created: {symbol} ({mode}) - IDLE"
REJECTED_FORMAT = "Bot creation REJECTED — mode-shape violation: {error}"
REFUSED_FORMAT = "Extractor creation REFUSED — {reason}"
CANCELLED_TEXT = "Bot creation cancelled."
OPENING_FORMAT = "Creating new bot for {exchange_id}..."
FAILED_FORMAT = "Failed to create bot: {error}"
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
    """Answer the ``sim_bot_wizard.state`` request with Live's payload under
    ``METHOD``."""
    found = live.view_model(params)
    found["method"] = METHOD
    return found


def tablet_markets(tablet_source: Any) -> dict[str, list[dict]]:
    """One market row per tablet asset on each exchange, under every base in
    ``live.BASE_CURRENCIES``, keyed by exchange id.

    A tablet is filed by asset and exchange and names no quote, so its asset
    is offered whatever base the wizard picks, at ``NO_VOLUME``.
    """
    out: dict[str, list[dict]] = {}
    seen: set[tuple[str, str]] = set()
    for entry in tablet_source.entries():
        exchange_id = str(entry.exchange_id)
        asset = str(entry.asset).upper()
        key = (exchange_id, asset)
        if key in seen or not asset:
            continue
        seen.add(key)
        rows = out.setdefault(exchange_id, [])
        for base in live.BASE_CURRENCIES:
            rows.append(
                {
                    live.MARKET_SYMBOL_KEY: f"{asset}/{base}",
                    live.MARKET_BASE_KEY: asset,
                    live.MARKET_QUOTE_KEY: base,
                    live.MARKET_VOLUME_KEY: NO_VOLUME,
                    live.MARKET_VOLATILITY_KEY: NO_VOLATILITY,
                }
            )
    return out


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


def wizard_exchanges(exchange_ids: Iterable[str], tablet_source: Any) -> list[dict]:
    """``seated_exchanges`` over the seated ids, then every exchange
    ``tablet_source.entries`` names that is not seated, sorted."""
    seated = [str(eid) for eid in exchange_ids if str(eid)]
    filed = sorted(
        {str(entry.exchange_id) for entry in tablet_source.entries()} - set(seated)
    )
    return seated_exchanges([*seated, *filed])


def venue_timeframes(exchanges: Iterable[dict]) -> dict[str, list[str]]:
    """The timeframes ``available_timeframes`` lists per venue in
    ``exchanges``, the bag the React wizard narrows its pages with."""
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
    bots: Iterable[SimBot], base_currency: str, exchange_id: str
) -> list[SimBot]:
    """Every scrumming ``SimBot`` on ``exchange_id`` whose asset is
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
    bots: Iterable[SimBot], base_currency: str, exchange_id: str
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


def created_line(bot: SimBot) -> str:
    """The Activity Log line Live writes for a created bot."""
    return CREATED_FORMAT.format(bot_id=bot.bot_id, symbol=bot.symbol, mode=bot.mode)


__all__ = [
    "CANCELLED_TEXT",
    "CREATED_FORMAT",
    "FAILED_FORMAT",
    "MANY_HOLDERS_FORMAT",
    "METHOD",
    "NO_HOLDER_FORMAT",
    "NO_VOLATILITY",
    "NO_VOLUME",
    "OPENING_FORMAT",
    "REFUSAL_BOX_FORMAT",
    "REFUSAL_TITLE",
    "REFUSED_FORMAT",
    "REJECTED_FORMAT",
    "created_line",
    "extractor_parent_refusal",
    "scrumming_holders",
    "seated_exchanges",
    "stored_defaults",
    "tablet_markets",
    "venue_timeframes",
    "view_model",
    "wizard_exchanges",
]
