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
    normalise,
    symbol_class,
    venue_classes,
)

DERIVATIVES = "derivatives"

#: The suffixes a Coinbase derivatives product id carries. Source: the venue's
#: public product list, read by ``ata_asset_maps.futures_listings``, whose own
#: source note names dated futures on the CDE venue and perpetuals on
#: ``-PERP-INTX`` (``src/trading/ata_asset_maps.py``, ``MAP_SOURCES``).
DERIVATIVE_SUFFIXES = ("-CDE", "-PERP-INTX")

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
