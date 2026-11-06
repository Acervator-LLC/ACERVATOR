# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The asset class filter every tab but Status and Console reads.

``asset_class_surface`` owns the class list and the venue map; this module
narrows a fleet, a venue list and a trade history to one of those classes.
Both variants read ``bots_of_class``, so the Qt tab
and the React page filter one fleet the same way. ``set_active`` records the
class the header strip group last selected and ``active`` answers it.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .asset_class_surface import (
    display_name,
    normalise,
    recorded_symbol_classes,
    recorded_venue_classes,
    symbol_class,
    venue_classes,
)

# OVERTAKEN, quoted whole:
#   "What each tab holds one of, for ``empty_note``. No tab draws that sentence:
#   ``tools/capture_screen_figure.py``, in ``class_note``, is its one caller."
# True today: every tab named below draws that sentence on its own page, seated
# by ``class_filter_tab.ClassFilterTabMixin._draw_class_notes`` while the tab
# keeps no row of the active class. ``class_note`` reads that label.
#: What each tab holds one of, for ``empty_note``.
TAB_SUBJECTS = {
    "Live": "bot",
    "Charts": "chart",
    "Inspector": "scanned market",
    "Swarm": "bot",
    "History": "trade",
    "Sim": "simulated bot",
    "Paper": "paper bot",
}

EMPTY_NOTE = "No {name} {subject} to show."

_active = ""


def active() -> str:
    """The asset class the header strip group last selected."""
    return normalise(_active) if _active else normalise(None)


def set_active(name: Any) -> str:
    """Record ``name`` as the active asset class and answer the key held."""
    global _active
    _active = normalise(name)
    return _active


# OVERTAKEN, quoted whole:
#   "A venue serving one class answers it, and a venue serving several is
#   narrowed to the class ``symbol_class`` holds for the symbol."
# True today: ``symbol_class`` reads the recording first on every venue, so a
# pair recorded under one sector is never answered under another.
def market_class(
    venue_id: Any, symbol: Any = "", venues: Any = None, symbols: Any = None
) -> str:
    """The asset class one market belongs to, or an empty string for none.

    ``symbol_class`` reads the venue's own recording, then the one class the
    venue serves, and answers an empty string where neither can; ``venues`` and
    ``symbols`` stand in for the two recording reads.
    """
    if not venue_classes(venue_id, venues):
        return ""
    return symbol_class(venue_id, symbol, symbols, venues)


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


# OVERTAKEN, quoted whole:
#   "``venue_classes`` answers crypto and derivatives for Coinbase, and this
#   answers that venue under both."
# True today: ``venue_classes`` intersects its answer with ``asset_classes``,
# which holds no ``derivatives``, and a venue serving several declared sectors
# is answered under each of them.
def venues_of_class(venue_ids: Iterable, name: Optional[Any] = None) -> list:
    """Every venue id in ``venue_ids`` that serves one asset class, sorted.

    ``venue_classes`` answers every sector one venue could serve, and a venue
    serving several is answered under each of them.
    """
    key = normalise(name) if name is not None else active()
    return sorted(one for one in (venue_ids or ()) if key in venue_classes(one))


def trades_by_class(rows: Any, answered: Optional[dict] = None) -> dict:
    """Every trade row filed under the class ``market_class`` answers for its
    ``exchange`` and ``symbol``, each list in the order given.

    ``market_class`` answers each distinct venue and symbol pair once from one
    read of the recording, and ``answered`` carries those answers across calls.
    """
    if answered is None:
        answered = {}
    venues: Optional[dict] = None
    symbols: dict = {}
    filed: dict = {}
    for row in rows or []:
        held = row if isinstance(row, dict) else {}
        venue = str(held.get("exchange") or held.get("exchange_id") or "")
        pair = (venue, str(held.get("symbol", "") or ""))
        if pair not in answered:
            if venues is None:
                venues = recorded_venue_classes()
            if venue not in symbols:
                symbols[venue] = recorded_symbol_classes(venue)
            answered[pair] = market_class(venue, pair[1], venues, symbols[venue])
        filed.setdefault(answered[pair], []).append(row)
    return filed


# OVERTAKEN, quoted whole:
#   "No tab draws this: ``tools/capture_screen_figure.py``, in ``class_note``,
#   is the one caller, and a tab outside ``TAB_SUBJECTS`` answers an empty
#   string."
# True today: ``class_filter_tab.ClassFilterTabMixin._draw_class_notes`` draws
# this on the tab it names, and ``class_note`` reads the label it seats.
def empty_note(tab: Any, name: Optional[Any] = None) -> str:
    """The sentence naming what one tab holds none of for an asset class.

    A tab outside ``TAB_SUBJECTS`` answers an empty string.
    """
    key = normalise(name) if name is not None else active()
    subject = TAB_SUBJECTS.get(str(tab))
    if not subject:
        return ""
    return EMPTY_NOTE.format(subject=subject, name=display_name(key))
