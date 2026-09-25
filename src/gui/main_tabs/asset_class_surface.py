"""The asset class taxonomy the header strip group and Add Exchange share.

Both variants read this module, so the Qt strip and the React page draw one
class list, one venue map and one Add Exchange label. The class list comes
from ``src.trading.ata_spm.ASSET_CLASSES`` at call time, so a class added to
that tuple reaches the group with no edit here.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import design_system as ds
from ..color_alpha import rgba

ADD_PREFIX = "＋ Add"

#: The alpha the checked button tints its accent with, as Qt reads it.
CHECKED_TINT_ALPHA = 40
HOVER_TINT_ALPHA = 70

#: The narrowest one class button draws at. The group's floor is this times
#: the class count, which the counters share the header top row with.
BUTTON_MIN_W = 34

#: The border and padding the button skin takes off its own text room.
BUTTON_TEXT_PAD = 12

#: The gap one class button leaves to the next, in both variants.
GROUP_SPACING_PX = 2

#: The venue ids that trade equities. Every consumer reads this one name.
EQUITY_VENUES = frozenset(
    {
        "alpaca",
        "ibkr",
        "schwab",
        "tdameritrade",
        "webull",
        "tastytrade",
        "fidelity",
        "etrade",
        "interactivebrokers",
    }
)

#: The wing words that predate the asset class taxonomy, mapped onto it.
LEGACY_CLASS_WORDS = {"stock": "stocks", "equities": "stocks", "equity": "stocks"}

#: The classes a trading layer stands behind. A class outside this set draws
#: its state and offers no venue.
LAYERED_CLASSES = frozenset({"crypto", "stocks"})

#: Display names. A class absent here is titled from its own key.
CLASS_NAMES = {
    "crypto": "Crypto",
    "stocks": "Stock",
    "derivatives": "Derivatives",
    "forex": "Forex",
    "commodities": "Commodities",
}

#: What a venue is called in each class. Equities are brokered, not exchanged.
CLASS_VENUE_NOUNS = {"stocks": "Broker"}
DEFAULT_VENUE_NOUN = "Exchange"

#: Accents, every one an existing design system token.
CLASS_ACCENTS = {
    "crypto": ds.LAYER_CRYPTO,
    "stocks": ds.LAYER_STOCK,
    "derivatives": ds.SECONDARY,
    "forex": ds.INFO,
    "commodities": ds.WARNING,
}
DEFAULT_ACCENT = ds.STATUS_NEUTRAL

#: Venues serving a class other than the one their own id implies. Coinbase
#: lists dated futures and perpetuals, read by ata_asset_maps.futures_listings.
EXTRA_VENUE_CLASSES = {"coinbase": ("derivatives",)}

NO_VENUE_NOTE = "No configured venue serves {name} yet."
NO_LAYER_NOTE = "{name} has no trading layer yet."
SERVED_NOTE = "{count} venue(s) serve {name}."
EMPTY_LABEL = "{name} — no venue yet"
EMPTY_TOOLTIP = "{note} Nothing is added for this class."
ADD_TOOLTIP = "Add a {name} {noun_lower} connection"


def asset_classes() -> tuple:
    """Every asset class the taxonomy declares, read at call time.

    ``src.trading.ata_spm.ASSET_CLASSES`` owns the tuple.
    """
    from src.trading.ata_spm import ASSET_CLASSES

    return tuple(ASSET_CLASSES)


def group_min_w(count: Any = None) -> int:
    """The narrowest the whole group draws at, holding every class button.

    ``count`` classes each take ``BUTTON_MIN_W`` and leave
    ``GROUP_SPACING_PX`` to the next. A ``count`` of None reads the live
    class list, so a class added to the taxonomy widens the floor with it.
    """
    held = len(asset_classes()) if count is None else int(count)
    if held <= 0:
        return 0
    return held * BUTTON_MIN_W + (held - 1) * GROUP_SPACING_PX


def normalise(name: Any) -> str:
    """The declared asset class *name* names, or the first declared class.

    ``LEGACY_CLASS_WORDS`` resolves a stored ``"stock"`` onto ``"stocks"``,
    and ``ata_spm.RETIRED_CLASSES`` resolves a retired name onto the live
    class now holding its markets.
    """
    from src.trading.ata_spm import RETIRED_CLASSES

    classes = asset_classes()
    asked = str(name or "").strip().lower()
    asked = LEGACY_CLASS_WORDS.get(asked, asked)
    asked = RETIRED_CLASSES.get(asked, asked)
    if asked in classes:
        return asked
    return classes[0] if classes else ""


def display_name(name: Any) -> str:
    """The name a button and a label carry for one asset class."""
    key = normalise(name)
    return CLASS_NAMES.get(key, key.replace("_", " ").title())


def venue_noun(name: Any) -> str:
    """What one asset class calls a venue."""
    return CLASS_VENUE_NOUNS.get(normalise(name), DEFAULT_VENUE_NOUN)


def accent(name: Any) -> str:
    """The design system colour one asset class paints with."""
    return CLASS_ACCENTS.get(normalise(name), DEFAULT_ACCENT)


def crypto_venues() -> frozenset:
    """Every venue id ``SUPPORTED_EXCHANGES`` lists, or none while it is absent."""
    try:
        from src.exchange.ccxt_connector import SUPPORTED_EXCHANGES
    except Exception:  # noqa: BLE001 - the connector is optional at import time
        return frozenset()
    return frozenset(SUPPORTED_EXCHANGES)


def venue_classes(venue_id: Any) -> frozenset:
    """Every asset class one venue serves.

    A venue carries the class its own registry lists it under, plus every
    class ``EXTRA_VENUE_CLASSES`` adds to it.
    """
    asked = str(venue_id or "").strip().lower()
    if not asked:
        return frozenset()
    found = set(EXTRA_VENUE_CLASSES.get(asked, ()))
    if asked in EQUITY_VENUES:
        found.add("stocks")
    elif asked in crypto_venues():
        found.add("crypto")
    return frozenset(found & set(asset_classes()))


def venues_for_class(name: Any) -> frozenset:
    """Every venue id serving one asset class.

    A venue whose ``venue_classes`` holds two classes is answered for both.
    """
    key = normalise(name)
    known = set(crypto_venues()) | set(EQUITY_VENUES) | set(EXTRA_VENUE_CLASSES)
    return frozenset(vid for vid in known if key in venue_classes(vid))


def serves(venue_id: Any, name: Any) -> bool:
    """Whether one venue serves one asset class."""
    return normalise(name) in venue_classes(venue_id)


def has_layer(name: Any) -> bool:
    """Whether a trading layer stands behind one asset class."""
    return normalise(name) in LAYERED_CLASSES


def layered_classes() -> tuple:
    """Every declared class a trading layer stands behind, in taxonomy order."""
    return tuple(name for name in asset_classes() if name in LAYERED_CLASSES)


def layer_page(name: Any) -> int:
    """The trading stack page one asset class draws.

    A layered class takes its position in ``layered_classes``, and every
    class without a layer draws the one page after them.
    """
    layered = layered_classes()
    key = normalise(name)
    return layered.index(key) if key in layered else len(layered)


def stack_pages() -> int:
    """How many pages the trading stack holds: one a layer, and one note page."""
    return len(layered_classes()) + 1


def class_state(name: Any) -> dict:
    """What one asset class holds, and the note it draws.

    A class ``venues_for_class`` answers empty carries ``NO_VENUE_NOTE``.
    """
    key = normalise(name)
    shown = display_name(key)
    venues = sorted(venues_for_class(key))
    layered = has_layer(key)
    if not venues:
        note = NO_VENUE_NOTE.format(name=shown)
    elif not layered:
        note = NO_LAYER_NOTE.format(name=shown)
    else:
        note = SERVED_NOTE.format(count=len(venues), name=shown)
    return {
        "class": key,
        "name": shown,
        "venues": venues,
        "venue_count": len(venues),
        "layer": layered,
        "served": bool(venues),
        "note": note,
        "accent": accent(key),
        "noun": venue_noun(key),
    }


def add_exchange_label(name: Any) -> str:
    """The Add Exchange button's text for one asset class.

    A class ``class_state`` reports unserved carries ``EMPTY_LABEL``.
    """
    state = class_state(name)
    if not state["served"]:
        return EMPTY_LABEL.format(name=state["name"])
    return f"{ADD_PREFIX} {state['name']} {state['noun']}"


def add_exchange_tooltip(name: Any) -> str:
    """The Add Exchange button's tooltip for one asset class."""
    state = class_state(name)
    if not state["served"]:
        return EMPTY_TOOLTIP.format(note=state["note"])
    return ADD_TOOLTIP.format(name=state["name"], noun_lower=state["noun"].lower())


def add_exchange_enabled(name: Any) -> bool:
    """Whether Add Exchange can act for one asset class."""
    return class_state(name)["served"]


def button_style(colour: Any) -> str:
    """The segmented group's skin for one accent colour."""
    tint = str(colour)
    return (
        "QPushButton { background: transparent; "
        f"color: {ds.TEXT_LOW}; border: 1px solid {ds.OUTLINE}; "
        "border-radius: 3px; font-weight: bold; font-size: 10px; "
        "padding: 2px 4px; }"
        f"QPushButton:hover {{ color: {tint}; border-color: {tint}; "
        f"background: {rgba(tint, HOVER_TINT_ALPHA)}; }}"
        f"QPushButton:checked {{ color: {tint}; border-color: {tint}; "
        f"background: {rgba(tint, CHECKED_TINT_ALPHA)}; }}"
        f"QPushButton:disabled {{ color: {ds.TEXT_PLACEHOLDER}; "
        f"border-color: {ds.OUTLINE}; }}"
    )


def class_button(name: Any, active: Any = None) -> dict:
    """One segmented group button, as both variants render it."""
    state = class_state(name)
    state["text"] = state["name"]
    state["checked"] = state["class"] == normalise(active) if active else False
    state["tooltip"] = state["note"]
    state["style_sheet"] = button_style(state["accent"])
    return state


def class_buttons(active: Any = None) -> list:
    """The whole segmented group, one button per declared asset class."""
    return [class_button(name, active) for name in asset_classes()]


def window_title(name: Any) -> str:
    """The main window's title while one asset class is active."""
    return f"Acervator — {display_name(name).upper()} LAYER"


def selection_log(name: Any) -> str:
    """The line the status log carries when the active class changes."""
    state = class_state(name)
    return f"→ {state['name'].upper()} LAYER: {state['note']}"


def view_model(active: Any = None, stored: Optional[Any] = None) -> dict:
    """The whole group state as one serialisable dict, for the React page."""
    key = normalise(active if active is not None else stored)
    return {
        "active": key,
        "classes": list(asset_classes()),
        "buttons": class_buttons(key),
        "add_exchange": {
            "label": add_exchange_label(key),
            "tooltip": add_exchange_tooltip(key),
            "enabled": add_exchange_enabled(key),
        },
        "state": class_state(key),
    }
