# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The asset class filter every tab but Status and Console reads.

``asset_class_surface`` owns the class list and the venue map; this module
narrows a fleet, a venue list and a trade history to one of those classes, and
writes the sentence an emptied tab draws. Both variants read it, so the Qt tab
and the React page filter one fleet the same way. ``set_active`` records the
class the header strip group last selected and ``active`` answers it.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .asset_class_surface import (
    display_name,
    normalise,
    symbol_class,
    venue_classes,
    venues_for_class,
)

DERIVATIVES = "derivatives"

#: The suffixes a Coinbase derivatives product id carries. Source: the venue's
#: public product list, read by ``ata_asset_maps.futures_listings``, whose own
#: source note names dated futures on the CDE venue and perpetuals on
#: ``-PERP-INTX`` (``src/trading/ata_asset_maps.py``, ``MAP_SOURCES``).
DERIVATIVE_SUFFIXES = ("-CDE", "-PERP-INTX")

#: What each tab holds one of, for the sentence an emptied tab draws. A tab
#: absent here holds nothing an asset class owns and never filters.
TAB_SUBJECTS = {
    "Live": "bot",
    "Charts": "chart",
    "Inspector": "scanned market",
    "Swarm": "bot",
    "History": "trade",
    "Sim": "simulated bot",
    "Paper": "paper bot",
}

#: The tabs that hold no class-bearing content. Neither filters, by his rule.
UNFILTERED_TABS = ("Status", "Console")

#: The bridge method ``src/gui/web/class_note.js`` registers under, which is
#: also the renderer module the React empty panel draws the note with.
NOTE_METHOD = "class_note.model"

#: The menu the window's own bar carries on every tab, which stays on screen
#: while a note page covers the tab. ``MainWindow._setup_menu`` builds it and
#: its one item adds a venue.
ADD_VENUE_MENU = "Exchange"

EMPTY_HEADING = "{name} — nothing to show"
EMPTY_NOTE = "No {name} {subject} to show."

#: The second line an emptied tab draws. A sector one or more venues serve
#: carries the count, that the operator can trade it, and where he adds a
#: venue. A sector no venue serves carries that fact alone, because no
#: control on screen can act on it.
SERVED_HINT = (
    "You can trade {name}. {count} {venues} {serve} {name}. "
    "Add one from the {menu} menu."
)
UNSERVED_HINT = "No venue serves {name} yet."

VENUE_NOUN_ONE = "venue"
VENUE_NOUN_MANY = "venues"
VENUE_VERB_ONE = "serves"
VENUE_VERB_MANY = "serve"

_active = ""


def active() -> str:
    """The asset class the header strip group last selected."""
    return normalise(_active) if _active else normalise(None)


def set_active(name: Any) -> str:
    """Record ``name`` as the active asset class and answer the key held."""
    global _active
    _active = normalise(name)
    return _active


def is_derivative(symbol: Any) -> bool:
    """Whether one market symbol names a derivatives product.

    The venue's own product read answers first, and ``DERIVATIVE_SUFFIXES``
    answers while that read holds nothing.
    """
    asked = str(symbol or "").strip().upper()
    if not asked:
        return False
    try:
        from src.trading import ata_asset_maps
    except Exception:  # noqa: BLE001 - the asset maps are optional at import time
        listed: set = set()
    else:
        listed = set(ata_asset_maps.futures_tickers()) | set(
            ata_asset_maps.futures_silent()
        )
    if asked in listed:
        return True
    return any(asked.endswith(one) for one in DERIVATIVE_SUFFIXES)


def market_class(venue_id: Any, symbol: Any = "") -> str:
    """The asset class one market belongs to, or an empty string for none.

    A venue serving one class answers it, and a venue serving several is
    narrowed to the class ``symbol_class`` holds for the symbol.
    """
    served = venue_classes(venue_id)
    if not served:
        return ""
    if len(served) == 1:
        return next(iter(served))
    if DERIVATIVES in served and is_derivative(symbol):
        return DERIVATIVES
    return symbol_class(venue_id, symbol)


def bot_class(status: Any) -> str:
    """The asset class of the market one bot status trades, the class the bot
    published under ``asset_class`` answering first.

    ``BotContainer._asset_class`` resolved that class, and a status carrying
    none is narrowed by ``market_class`` from its venue and symbol.
    """
    held = status if isinstance(status, dict) else {}
    declared = str(held.get("asset_class") or "").strip()
    if declared:
        return normalise(declared)
    venue = held.get("exchange") or held.get("exchange_id") or ""
    return market_class(venue, held.get("symbol", ""))


def bots_of_class(statuses: Any, name: Optional[Any] = None) -> list:
    """Every bot status whose market belongs to one asset class."""
    key = normalise(name) if name is not None else active()
    return [one for one in (statuses or []) if bot_class(one) == key]


def venues_of_class(venue_ids: Iterable, name: Optional[Any] = None) -> list:
    """Every venue id in ``venue_ids`` that serves one asset class, sorted.

    ``venue_classes`` answers crypto and derivatives for Coinbase, and this
    answers that venue under both.
    """
    key = normalise(name) if name is not None else active()
    return sorted(one for one in (venue_ids or ()) if key in venue_classes(one))


def trades_of_class(rows: Any, name: Optional[Any] = None) -> list:
    """Every trade row whose market belongs to one asset class.

    A row names its venue under ``exchange`` and its market under ``symbol``,
    which is the shape the History table reads.
    """
    key = normalise(name) if name is not None else active()
    kept = []
    for row in rows or []:
        held = row if isinstance(row, dict) else {}
        venue = held.get("exchange") or held.get("exchange_id") or ""
        if market_class(venue, held.get("symbol", "")) == key:
            kept.append(row)
    return kept


def filters(tab: Any) -> bool:
    """Whether one tab title filters by asset class."""
    return str(tab) not in UNFILTERED_TABS


def empty_note(tab: Any, name: Optional[Any] = None) -> str:
    """The sentence one emptied tab draws, naming the active asset class.

    A tab outside ``TAB_SUBJECTS`` answers an empty string.
    """
    key = normalise(name) if name is not None else active()
    subject = TAB_SUBJECTS.get(str(tab))
    if not subject:
        return ""
    return EMPTY_NOTE.format(subject=subject, name=display_name(key))


def note_model(tab: Any, name: Optional[Any] = None) -> dict:
    """The view model the note page draws for one emptied tab.

    ``EmptyTabQtPanel`` and the React empty panel read the same four fields.
    """
    key = normalise(name) if name is not None else active()
    shown = display_name(key)
    return {
        "accessible_name": f"{tab} asset class note",
        "method": NOTE_METHOD,
        "heading": EMPTY_HEADING.format(name=shown),
        "state_text": empty_note(tab, key),
        "issue_text": empty_hint(key),
    }


def empty_hint(name: Optional[Any] = None) -> str:
    """The second line an emptied tab draws under ``empty_note``.

    A sector ``venues_for_class`` counts venues for takes ``SERVED_HINT`` and
    one it counts none for takes ``UNSERVED_HINT``, the count read on every
    call so no venue name is written into either.
    """
    key = normalise(name) if name is not None else active()
    shown = display_name(key)
    count = len(venues_for_class(key))
    if not count:
        return UNSERVED_HINT.format(name=shown)
    alone = count == 1
    return SERVED_HINT.format(
        name=shown,
        count=count,
        venues=VENUE_NOUN_ONE if alone else VENUE_NOUN_MANY,
        serve=VENUE_VERB_ONE if alone else VENUE_VERB_MANY,
        menu=ADD_VENUE_MENU,
    )


def tab_state(tab: Any, statuses: Any, name: Optional[Any] = None) -> dict:
    """What one tab holds for an asset class, and the note it draws when none.

    Both variants read this dict, so the Qt pane and the React page draw one
    count and one sentence.
    """
    key = normalise(name) if name is not None else active()
    kept = bots_of_class(statuses, key)
    return {
        "class": key,
        "name": display_name(key),
        "filters": filters(tab),
        "tab": str(tab),
        "bots": kept,
        "bot_count": len(kept),
        "empty": not kept,
        "note": empty_note(tab, key) if not kept else "",
        "hint": empty_hint(key) if not kept else "",
    }
