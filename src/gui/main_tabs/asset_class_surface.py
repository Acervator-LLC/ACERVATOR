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

#: The segments one row holds, fixed, so a further class divides the square's
#: height and never its width.
GRID_COLUMNS = 2

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

# OVERTAKEN, quoted whole:
#   "Venues serving a class other than the one their own id implies. Coinbase's
#   products endpoint answers 1000 EQUITY products and labels 21 futures with a
#   commodity underlying; ``derivatives`` resolves onto crypto through
#   ``RETIRED_CLASSES``."
# OVERTAKEN, quoted whole:
#   "True today: the same entry also names forex, indices and futures_perps,
#   which ``market_asset_class`` answers for 20, 6 and 168 of the venue's
#   products."
# True today: twenty venue ids carry an extra sector, not Coinbase alone.
#: Venues serving a class other than the one their own id implies. Coinbase's
#: products endpoint answers 1000 EQUITY products and labels 21 futures with a
#: commodity underlying; ``derivatives`` resolves onto crypto through
#: ``RETIRED_CLASSES``.
EXTRA_VENUE_CLASSES = {
    "coinbase": (
        "derivatives",
        "stocks",
        "commodities",
        "forex",
        "indices",
        "futures_perps",
    ),
    "binance": ("stocks", "commodities", "forex", "indices", "futures_perps"),
    "bitfinex": ("commodities", "indices", "futures_perps"),
    "bitget": ("stocks", "commodities", "indices", "futures_perps"),
    "bitstamp": ("commodities", "forex"),
    "bybit": ("futures_perps",),
    "cryptocom": ("stocks", "futures_perps"),
    "gateio": ("stocks", "commodities", "forex", "indices", "futures_perps"),
    "gemini": ("commodities", "forex", "futures_perps"),
    "huobi": ("stocks",),
    "kraken": ("stocks", "commodities", "indices", "futures_perps"),
    "kucoin": ("stocks", "commodities", "futures_perps"),
    "mexc": ("stocks", "futures_perps"),
    "okx": ("stocks", "commodities", "indices", "futures_perps"),
    "alpaca": ("crypto", "commodities", "indices"),
    "etrade": ("commodities", "indices"),
    "ibkr": ("crypto", "commodities", "forex", "indices", "futures_perps"),
    "schwab": ("crypto", "commodities", "indices", "futures_perps"),
    "tastytrade": ("crypto", "commodities", "indices", "futures_perps"),
    "webull": ("crypto", "commodities", "indices", "futures_perps"),
}

#: The two articles a sentence takes before a sector name, and the first
#: letters taking the second.
#: The last recording read, under its ``recording_stamp``. One Live tab refresh
#: asks ``venue_classes`` once a bot, and the file is 235 KB.
_RECORDED_CACHE: dict = {}

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


# OVERTAKEN, quoted whole:
#   "``columns`` is the integer square root rounded up, so the grid is the one
#   nearest to square for that count."
# True today: ``columns`` is ``GRID_COLUMNS``, or ``count`` while that is
# smaller, and the rows follow, so a further class divides only the height.
def grid_shape(count: Any = None) -> tuple:
    """The rows and columns ``count`` segments divide the square into.

    ``columns`` is the integer square root rounded up, so the grid is the one
    nearest to square for that count, and a ``count`` of None reads the live
    class list.
    """
    held = len(asset_classes()) if count is None else int(count)
    if held <= 0:
        return (0, 0)
    columns = min(GRID_COLUMNS, held)
    rows = math.ceil(held / columns)
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


def reference_labels() -> list:
    """The class names ``group_side_px`` measures the square's side from.

    The first ``GRID_COLUMNS`` squared classes fill the square once, so a
    class past them divides the height and leaves the side alone.
    """
    held = asset_classes()[: GRID_COLUMNS * GRID_COLUMNS]
    return [display_name(each) for each in held]


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
# OVERTAKEN, quoted whole:
#   "True today: its widest row holds ``columns`` segments of
#   ``segment_width_px`` each, so the side follows the class count and the
#   widest class name."
# True today: the side holds ``GRID_COLUMNS`` segments of ``reference_labels``
# room, so neither the class count nor a later class name moves it.
def group_side_px(count: Any = None, labels: Any = None) -> int:
    """The square's side in pixels, the same number in both variants.

    Its widest row holds ``columns`` segments of ``BUTTON_MIN_W`` each, so the
    side follows the class count and no variant measures its own row height.
    """
    held = len(asset_classes()) if count is None else int(count)
    if held <= 0:
        return 0
    names = reference_labels() if labels is None else labels
    width = segment_width_px(names)
    return GRID_COLUMNS * width + (GRID_COLUMNS - 1) * GROUP_SPACING_PX


def segment_size_px(count: Any = None) -> tuple:
    """One segment's width and height in pixels, the same in both variants.

    The square's side divides by its columns and by its rows, so every one of
    ``count`` segments draws the same rectangle.
    """
    rows, columns = grid_shape(count)
    if rows <= 0 or columns <= 0:
        return (0, 0)
    side = group_side_px(count)
    width = (side - (columns - 1) * GROUP_SPACING_PX) // columns
    height = (side - (rows - 1) * GROUP_SPACING_PX) // rows
    return (width, height)


def grid_margins_px(count: Any = None) -> tuple:
    """The square's left, top, right and bottom margins, in that order.

    They carry what ``segment_size_px`` leaves of the side after an uneven
    division, so the segments stay equal and the side stays whole.
    """
    rows, columns = grid_shape(count)
    if rows <= 0 or columns <= 0:
        return (0, 0, 0, 0)
    width, height = segment_size_px(count)
    side = group_side_px(count)
    spare_w = side - columns * width - (columns - 1) * GROUP_SPACING_PX
    spare_h = side - rows * height - (rows - 1) * GROUP_SPACING_PX
    return (spare_w // 2, spare_h // 2, spare_w - spare_w // 2, spare_h - spare_h // 2)


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


def ccxt_crypto_venues() -> frozenset:
    """Every venue id ``SUPPORTED_EXCHANGES`` lists, or none while it is absent."""
    try:
        from src.exchange.ccxt_connector import SUPPORTED_EXCHANGES
    except Exception:  # noqa: BLE001 - the connector is optional at import time
        return frozenset()
    return frozenset(SUPPORTED_EXCHANGES)


def written_crypto_venues() -> frozenset:
    """Every venue id ``CRYPTO_CONNECTORS`` holds a hand-written class for, or
    none while that connector is absent."""
    try:
        from src.exchange.robinhood_connector import hand_written_crypto_venues
    except Exception:  # noqa: BLE001 - the connector is optional at import time
        return frozenset()
    return frozenset(hand_written_crypto_venues())


def crypto_venues() -> frozenset:
    """Every venue id either crypto connector registry lists.

    ccxt carries no entry for a hand-written venue, so ``ccxt_crypto_venues``
    alone would list it under no sector.
    """
    return ccxt_crypto_venues() | written_crypto_venues()


def retired_onto(name: Any) -> str:
    """The live class one retired or legacy class name resolves onto.

    A name neither ``LEGACY_CLASS_WORDS`` nor ``RETIRED_CLASSES`` holds is
    answered unchanged, which ``asset_classes`` then drops.
    """
    from src.trading.ata_spm import RETIRED_CLASSES

    asked = str(name or "").strip().lower()
    asked = LEGACY_CLASS_WORDS.get(asked, asked)
    return RETIRED_CLASSES.get(asked, asked)


def recording_stamp() -> tuple:
    """The recording file's path, modification time and size, or an empty tuple
    while no file is there.

    ``recorded_venue_classes`` reads the recording again only when this moves.
    """
    try:
        from ...exchange.market_rules_store import store_path
    except ImportError:
        return ()
    try:
        target = store_path()
        held = target.stat()
    except OSError:
        return ()
    return (str(target), held.st_mtime_ns, held.st_size)


def recorded_venue_classes(document: Any = None) -> dict:
    """Every venue in the ``market_rules_store`` recording mapped to the asset
    classes its recorded rows carry under ``CLASS_FIELD``.

    ``document`` stands in for ``load_document`` and skips the
    ``recording_stamp`` cache, and neither asks a venue.
    """
    try:
        from ...exchange.market_rules_store import CLASS_FIELD, load_document
    except ImportError:
        return {}
    stamp = () if isinstance(document, dict) else recording_stamp()
    if stamp and _RECORDED_CACHE.get("stamp") == stamp:
        return dict(_RECORDED_CACHE["classes"])
    body = document if isinstance(document, dict) else load_document()
    declared = set(asset_classes())
    found: dict = {}
    for venue, rows in body.items():
        if not isinstance(rows, dict):
            continue
        held = set()
        for row in rows.values():
            if not isinstance(row, dict):
                continue
            named = retired_onto(row.get(CLASS_FIELD, ""))
            if named in declared:
                held.add(named)
        found[str(venue).strip().lower()] = frozenset(held)
    if stamp:
        _RECORDED_CACHE["stamp"] = stamp
        _RECORDED_CACHE["classes"] = dict(found)
    return found


def venue_classes(venue_id: Any, recorded: Any = None) -> frozenset:
    """Every asset class one venue could serve: the class its own registry
    lists it under, every class ``EXTRA_VENUE_CLASSES`` adds through
    ``retired_onto``, and every class its recorded rows carry.

    ``recorded`` stands in for ``recorded_venue_classes``, so one read of the
    recording serves a whole panel.
    """
    asked = str(venue_id or "").strip().lower()
    if not asked:
        return frozenset()
    found = {retired_onto(one) for one in EXTRA_VENUE_CLASSES.get(asked, ())}
    if asked in EQUITY_VENUES:
        found.add("stocks")
    if asked in crypto_venues():
        found.add("crypto")
    held = recorded if isinstance(recorded, dict) else recorded_venue_classes()
    found |= set(held.get(asked, frozenset()))
    return frozenset(found & set(asset_classes()))


def venue_served_classes(venue_id: Any, document: Any = None) -> frozenset:
    """Every asset class one venue's recorded rows carry, the recording alone
    and no registry.

    A venue ``recorded_venue_classes`` holds no rows for answers empty, while
    ``venue_classes`` still answers what that venue could serve.
    """
    asked = str(venue_id or "").strip().lower()
    if not asked:
        return frozenset()
    return frozenset(recorded_venue_classes(document).get(asked, frozenset()))


def recorded_symbol_classes(venue_id: Any) -> dict:
    """Every symbol one venue's recording holds mapped to its ``CLASS_FIELD``,
    empty while the recording cannot be read."""
    try:
        from ...exchange.market_rules_store import recorded_classes
    except ImportError:
        return {}
    asked = str(venue_id or "").strip().lower()
    if not asked:
        return {}
    return recorded_classes(asked)


def symbol_class(venue_id: Any, symbol: Any, recorded: Any = None) -> str:
    """The class ``recorded_symbol_classes`` holds for ``symbol`` on
    ``venue_id``, else ``CLASS_CRYPTO``, the class ``BotContainer._asset_class``
    answers for a symbol the recording holds none for.

    Every surface narrowing a market by sector reads this, so a bot and the tab
    filtering it answer one class.
    """
    from src.trading.ata_spm import CLASS_CRYPTO

    held = recorded if isinstance(recorded, dict) else recorded_symbol_classes(venue_id)
    return retired_onto(held.get(str(symbol or ""), "")) or CLASS_CRYPTO


def markets_of_class(rows: Any, venue_id: Any, name: Any, recorded: Any = None) -> list:
    """Every market row of ``rows`` whose ``symbol_class`` on ``venue_id`` is
    one asset class, in the order given.

    An empty ``name`` narrows nothing.
    """
    key = normalise(name)
    listed = [one for one in (rows or []) if isinstance(one, dict)]
    if not key:
        return listed
    held = recorded if isinstance(recorded, dict) else recorded_symbol_classes(venue_id)
    return [
        row for row in listed if symbol_class(venue_id, row.get("symbol"), held) == key
    ]


def known_venues(recorded: Any = None) -> frozenset:
    """Every venue id the platform holds: ``crypto_venues``, ``EQUITY_VENUES``,
    every venue ``EXTRA_VENUE_CLASSES`` adds a sector for, and every venue
    ``recorded_venue_classes`` holds rows for, with ``recorded`` standing in for
    that read.

    ``venues_for_class`` narrows this by sector and ``init_wizard_surface``'s
    ``exchange_ids`` offers it whole, so neither list can hold a venue the other
    does not.
    """
    held = recorded if isinstance(recorded, dict) else recorded_venue_classes()
    return frozenset(
        set(crypto_venues()) | set(EQUITY_VENUES) | set(EXTRA_VENUE_CLASSES) | set(held)
    )


def venues_for_class(name: Any) -> frozenset:
    """Every venue id serving one asset class, a venue whose ``venue_classes``
    holds two classes answered for both.

    A venue ``recorded_venue_classes`` alone knows is answered for the classes
    its recorded rows carry.
    """
    key = normalise(name)
    recorded = recorded_venue_classes()
    return frozenset(
        vid for vid in known_venues(recorded) if key in venue_classes(vid, recorded)
    )


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
