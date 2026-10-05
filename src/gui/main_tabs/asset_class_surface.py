"""The asset class taxonomy the header strip group and Add Exchange share.

Both variants read this module, so the Qt strip and the React page draw one
class list, one venue map and one Add Exchange label. The class list comes
from ``src.trading.ata_spm.ASSET_CLASSES`` at call time, so a class added to
that tuple reaches the group with no edit here.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from .. import design_system as ds
from ..color_alpha import rgba

ADD_PREFIX = "＋ Add"

#: The alpha the checked button tints its accent with, as Qt reads it.
CHECKED_TINT_ALPHA = 40
HOVER_TINT_ALPHA = 70

# OVERTAKEN, quoted whole:
#   "The border and padding the button skin takes off its own text room."
# True today: the most the skin takes, since a segment past the first column
# suppresses its shared left border and one past the first row its shared top.
#: The border and padding the button skin takes off its own text room.
BUTTON_TEXT_PAD = 12

#: The text size one segment draws its class name at, in both variants.
SEGMENT_FONT_PX = 10

# OVERTAKEN, quoted whole:
#   "The narrowest one class button draws at. The group's floor is this times
#   the class count, which the counters share the header top row with."
# OVERTAKEN, quoted whole:
#   "True today: the square's side is this times its widest row's segment count,
#   because the segments fill a square rather than a line."
# True today: the floor segment_width_px may not fall below, which the widest
# class name sets above that floor.
#: The narrowest one class button draws at.
BUTTON_MIN_W = 34

#: The gap between two neighbouring segments, in both variants. Zero, so one
#: line draws between neighbours and never two.
GROUP_SPACING_PX = 0

#: The radius the square's four outer corners carry, in both variants. Every
#: corner inside the square is zero.
OUTER_RADIUS_PX = 3

#: The ``segment_cell`` fields every class button carries into both variants.
CELL_KEYS = (
    "row",
    "column",
    "rows",
    "columns",
    "row_holds",
    "grid_column",
    "column_span",
)

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
LAYERED_CLASSES = frozenset(
    {"crypto", "stocks", "commodities", "forex", "indices", "futures_perps"}
)

#: Display names. A class absent here is titled from its own key.
#: ``layer_card`` indexes ``LAYER_LABEL``, so a layered class absent here
#: refuses the React page.
CLASS_NAMES = {
    "crypto": "Crypto",
    "stocks": "Stock",
    "derivatives": "Derivatives",
    "forex": "Forex",
    "commodities": "Commodities",
    "indices": "Indices",
    "futures_perps": "Futures / Perps",
}

#: What a venue is called in each class. Equities are brokered, not exchanged.
CLASS_VENUE_NOUNS = {"stocks": "Broker"}
DEFAULT_VENUE_NOUN = "Exchange"

#: Accents, every one an existing design system token. ``futures_perps`` keeps
#: the accent ``derivatives`` carried, which no live class draws.
CLASS_ACCENTS = {
    "crypto": ds.LAYER_CRYPTO,
    "stocks": ds.LAYER_STOCK,
    "derivatives": ds.SECONDARY,
    "forex": ds.INFO,
    "commodities": ds.WARNING,
    "indices": ds.ACCENT_GOLD,
    "futures_perps": ds.SECONDARY,
}
DEFAULT_ACCENT = ds.STATUS_NEUTRAL

#: Venues serving a class other than the one their own id implies. Coinbase's
#: products endpoint answers 1000 EQUITY products and labels 21 futures with a
#: commodity underlying; ``derivatives`` resolves onto crypto through
#: ``RETIRED_CLASSES``.
EXTRA_VENUE_CLASSES = {"coinbase": ("derivatives", "stocks", "commodities")}

#: The two articles a sentence takes before a sector name, and the first
#: letters taking the second.
ARTICLE_DEFAULT = "a"
ARTICLE_VOWEL = "an"
ARTICLE_VOWEL_LETTERS = "aeio"

NO_VENUE_NOTE = "No configured venue serves {name} yet."
NO_LAYER_NOTE = "{name} has no trading layer yet."
SERVED_NOTE = "{count} venue(s) serve {name}."
EMPTY_LABEL = "{name} — no venue yet"
EMPTY_TOOLTIP = "{note} Nothing is added for this class."
ADD_TOOLTIP = "Add {article} {name} {noun_lower} connection"


def asset_classes() -> tuple:
    """Every asset class the taxonomy declares, read at call time.

    ``src.trading.ata_spm.ASSET_CLASSES`` owns the tuple.
    """
    from src.trading.ata_spm import ASSET_CLASSES

    return tuple(ASSET_CLASSES)


def grid_shape(count: Any = None) -> tuple:
    """The rows and columns ``count`` segments divide the square into.

    ``columns`` is the integer square root rounded up, so the grid is the one
    nearest to square for that count, and a ``count`` of None reads the live
    class list.
    """
    held = len(asset_classes()) if count is None else int(count)
    if held <= 0:
        return (0, 0)
    columns = math.isqrt(held)
    if columns * columns < held:
        columns += 1
    rows = held // columns + (1 if held % columns else 0)
    return (rows, columns)


def row_holds(count: Any = None) -> list:
    """How many segments each row of the square holds, the top row first.

    Every row but the last holds a full ``columns`` and the last holds what
    is left, so no row is empty.
    """
    held = len(asset_classes()) if count is None else int(count)
    rows, columns = grid_shape(held)
    if rows <= 0:
        return []
    counts = [columns] * (rows - 1)
    counts.append(held - columns * (rows - 1))
    return counts


def column_spans(columns: Any, holds: Any) -> list:
    """The grid columns each segment of one row spans, the leftmost first.

    ``holds`` segments share ``columns`` columns and the leftmost take the
    remainder one extra each, so every row fills the square's whole width.
    """
    wide = int(columns)
    many = int(holds)
    if many <= 0 or wide <= 0:
        return []
    base, extra = divmod(wide, many)
    return [base + (1 if at < extra else 0) for at in range(many)]


def segment_cell(at: Any, count: Any = None) -> dict:
    """Where segment ``at`` of ``count`` sits in the square, and what it spans.

    Carries the row, the column within that row, the grid column it starts at
    and the columns it spans, so a segment knows its place in two dimensions.
    """
    held = len(asset_classes()) if count is None else int(count)
    rows, columns = grid_shape(held)
    counts = row_holds(held)
    index = max(int(at), 0)
    row = 0
    before = 0
    for holds in counts:
        if index < before + holds:
            break
        before += holds
        row += 1
    if row >= len(counts):
        row = max(len(counts) - 1, 0)
        before = sum(counts[:row])
    holds = counts[row] if counts else 0
    column = index - before
    spans = column_spans(columns, holds)
    return {
        "row": row,
        "column": column,
        "rows": rows,
        "columns": columns,
        "row_holds": holds,
        "grid_column": sum(spans[:column]) if spans else 0,
        "column_span": spans[column] if spans and column < len(spans) else 1,
    }


def segment_font() -> Any:
    """The font one segment draws its class name in, at ``SEGMENT_FONT_PX``."""
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    running = QApplication.instance() is not None
    font = QFont(QApplication.font()) if running else QFont()
    font.setPixelSize(SEGMENT_FONT_PX)
    font.setBold(True)
    return font


def label_width_px(text: Any) -> int:
    """The room one class name takes at ``segment_font``, or 0 with no toolkit.

    ``QFontMetrics`` needs a running ``QApplication``, so a caller holding
    none reads 0 and ``segment_width_px`` answers ``BUTTON_MIN_W``.
    """
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        return 0
    from PySide6.QtGui import QFontMetrics

    return int(QFontMetrics(segment_font()).horizontalAdvance(str(text)))


def widest_label_px(labels: Any = None) -> int:
    """The widest declared class name's room at ``segment_font``."""
    names = (
        [display_name(each) for each in asset_classes()]
        if labels is None
        else [str(each) for each in labels]
    )
    return max((label_width_px(each) for each in names), default=0)


def segment_width_px(labels: Any = None) -> int:
    """One segment's width: its widest class name plus ``BUTTON_TEXT_PAD``.

    ``BUTTON_MIN_W`` is the floor the measured width may not fall below, so a
    shorter class list never narrows a segment past it.
    """
    return max(BUTTON_MIN_W, widest_label_px(labels) + BUTTON_TEXT_PAD)


# OVERTAKEN, quoted whole:
#   "Its widest row holds ``columns`` segments of ``BUTTON_MIN_W`` each, so the
#   side follows the class count and no variant measures its own row height."
# True today: its widest row holds ``columns`` segments of ``segment_width_px``
# each, so the side follows the class count and the widest class name.
def group_side_px(count: Any = None, labels: Any = None) -> int:
    """The square's side in pixels, the same number in both variants.

    Its widest row holds ``columns`` segments of ``BUTTON_MIN_W`` each, so the
    side follows the class count and no variant measures its own row height.
    """
    held = len(asset_classes()) if count is None else int(count)
    if held <= 0:
        return 0
    columns = grid_shape(held)[1]
    return columns * segment_width_px(labels) + (columns - 1) * GROUP_SPACING_PX


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


def article(label: Any) -> str:
    """The article a sentence takes before one display name.

    Answers ``ARTICLE_VOWEL`` while the name opens on a letter in
    ``ARTICLE_VOWEL_LETTERS``, so the Indices layer reads "an Indices".
    """
    first = str(label or "").strip()[:1].lower()
    return ARTICLE_VOWEL if first in ARTICLE_VOWEL_LETTERS else ARTICLE_DEFAULT


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


def retired_onto(name: Any) -> str:
    """The live class one retired or legacy class name resolves onto.

    A name neither ``LEGACY_CLASS_WORDS`` nor ``RETIRED_CLASSES`` holds is
    answered unchanged, which ``asset_classes`` then drops.
    """
    from src.trading.ata_spm import RETIRED_CLASSES

    asked = str(name or "").strip().lower()
    asked = LEGACY_CLASS_WORDS.get(asked, asked)
    return RETIRED_CLASSES.get(asked, asked)


def venue_classes(venue_id: Any) -> frozenset:
    """Every asset class one venue serves.

    A venue carries the class its own registry lists it under, plus every
    class ``EXTRA_VENUE_CLASSES`` adds through ``retired_onto``.
    """
    asked = str(venue_id or "").strip().lower()
    if not asked:
        return frozenset()
    found = {retired_onto(one) for one in EXTRA_VENUE_CLASSES.get(asked, ())}
    if asked in EQUITY_VENUES:
        found.add("stocks")
    if asked in crypto_venues():
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
    return ADD_TOOLTIP.format(
        article=article(state["name"]),
        name=state["name"],
        noun_lower=state["noun"].lower(),
    )


def add_exchange_enabled(name: Any) -> bool:
    """Whether Add Exchange can act for one asset class."""
    return class_state(name)["served"]


def segment_box(cell: Any = None) -> str:
    """The border and radius declarations one segment carries at ``cell``.

    A segment past the first column drops its shared left border and one past
    the first row its shared top, and only a corner of the square is rounded.
    """
    place = cell if isinstance(cell, dict) else segment_cell(0, 1)
    row = int(place.get("row", 0))
    column = int(place.get("column", 0))
    rows = int(place.get("rows", 1))
    holds = int(place.get("row_holds", 1))
    corner = f"{OUTER_RADIUS_PX}px"
    said = [f"border: 1px solid {ds.OUTLINE}"]
    if column > 0:
        said.append("border-left: none")
    if row > 0:
        said.append("border-top: none")
    said.append("border-radius: 0px")
    last_row = rows - 1
    last_column = holds - 1
    top = row == 0
    bottom = row == last_row
    left = column == 0
    right = column == last_column
    if top and left:
        said.append(f"border-top-left-radius: {corner}")
    if top and right:
        said.append(f"border-top-right-radius: {corner}")
    if bottom and left:
        said.append(f"border-bottom-left-radius: {corner}")
    if bottom and right:
        said.append(f"border-bottom-right-radius: {corner}")
    return "; ".join(said) + "; "


# OVERTAKEN, quoted whole:
#   "The segmented group's skin for one accent colour."
# True today: the skin for one accent colour at one segment_cell.
def button_style(colour: Any, cell: Any = None) -> str:
    """The segmented group's skin for one accent colour."""
    tint = str(colour)
    return (
        "QPushButton { background: transparent; "
        f"color: {ds.TEXT_LOW}; {segment_box(cell)}"
        f"font-weight: bold; font-size: {SEGMENT_FONT_PX}px; "
        "padding: 2px 4px; }"
        f"QPushButton:hover {{ color: {tint}; border-color: {tint}; "
        f"background: {rgba(tint, HOVER_TINT_ALPHA)}; }}"
        f"QPushButton:checked {{ color: {tint}; border-color: {tint}; "
        f"background: {rgba(tint, CHECKED_TINT_ALPHA)}; }}"
        f"QPushButton:disabled {{ color: {ds.TEXT_PLACEHOLDER}; "
        f"border-color: {ds.OUTLINE}; }}"
    )


def class_button(name: Any, active: Any = None, cell: Any = None) -> dict:
    """One segmented group button, as both variants render it.

    The ``cell`` fields travel in the button, so both variants place the
    segment in the same grid row and column without recomputing it.
    """
    state = class_state(name)
    place = cell if isinstance(cell, dict) else segment_cell(0, 1)
    state["text"] = state["name"]
    state["checked"] = state["class"] == normalise(active) if active else False
    state["tooltip"] = state["note"]
    state.update(
        {key: place[key] for key in CELL_KEYS if key in place},
    )
    state["style_sheet"] = button_style(state["accent"], place)
    return state


def class_buttons(active: Any = None) -> list:
    """The whole segmented group, one button per declared asset class.

    Each button carries the ``segment_cell`` its index names, so the four
    segments at the square's corners round one corner each and no other does.
    """
    held = asset_classes()
    return [
        class_button(name, active, segment_cell(at, len(held)))
        for at, name in enumerate(held)
    ]


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
