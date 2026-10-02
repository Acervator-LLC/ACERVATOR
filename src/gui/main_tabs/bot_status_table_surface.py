"""bot_status_table_surface.py -- the scrumming-bot dashboard table.

Describes the table the operator's running bots are listed in. Ten
columns per bot: the target asset's logo, its pair, what its holdings
are worth at the exchange's own price, how many trades it has done, the
target balance in dollars and restated in BTC and in ETH, the Ammo
figure that says how far the position sits from that target, a Manual
Fire button and a Detail button.

The logo cell opens its asset's own organisation in the system browser
when it is clicked, and ``opening_address`` refuses any address that is
not https with a host. A cell whose asset resolves no address is not a
link and its tooltip says so.

The Symbol cell carries the state colour and names the mode and the
state in its tooltip. The Current Position Value cell is blank whenever
no fresh exchange price exists, and its tooltip names what is missing;
it never falls back to a last-known figure or to a ledger value.

Every column header wraps its own label inside its own column's width,
and a maskable column carries one dot centred beneath that label, which
the operator clicks to hide or show the column. The Fire button changes
its colour, its border and its tooltip with what the engine would do
next, and with the risk controls the bot reports.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``bot_status_table.state`` method, which is how the Electron
renderer reaches it. Nothing here imports Qt.
"""

from __future__ import annotations

import base64
import logging
import urllib.parse
from typing import Any, Dict, Optional

from ...core.asset_logos import LogoCache, image_extension
from ...core.privacy_mask_registry import get_privacy_mask_registry, mask_or
from ...core.safe_url import openable_url
from ...exchange.crypto_assets import AssetManager
from ...exchange.exchange_chart_urls import chart_url
from ...trading.ata_asset_maps import organisation_page
from ...trading.target_bands import ammo_target
from .. import design_system as ds
from .table_cells_surface import (
    NO_TARGET_TEXT,
    POSITION_BLANK_TEXT,
    POSITION_PATHS,
    PRICE_STALE_AFTER_S,
    TableCellsModel,
    magnitude,
    priced_position,
)

logger = logging.getLogger("acervator.gui")

METHOD = "bot_status_table.state"

LOGGER_NAME = "acervator.gui"
SKIP_LOGGER_NAME = __name__

COLUMN_LABELS = (
    "Asset",
    "Symbol",
    "Current Position Value",
    "Trades",
    "Target",
    "Target BTC",
    "Target ETH",
    "Ammo",
    "Fire",
    "",
)

COLUMN_COUNT = len(COLUMN_LABELS)

COLUMN_TOOLTIPS = {
    0: (
        "The target asset this bot accumulates, drawn as that asset's own\n"
        "official logo. An asset with no logo kept yet shows its ticker.\n"
        "Click a mark to open that asset's own organisation in your browser.\n"
        "A mark for an asset with no web address is not a link and says so.\n"
        "The bot's own id is no longer shown here: it stays in the record\n"
        "and in the logs, and the Detail button opens the bot that holds it."
    ),
    1: (
        "Trading pair (Target Asset / Base Currency), coloured by current state.\n"
        "Green = RUNNING · Amber = PAUSED · Gray = IDLE/STOPPED\n"
        "Red = ERROR · Orange = COOLDOWN · Cyan = STARTING\n"
        "Hover a cell to read the mode and the state in full."
    ),
    2: (
        "Current Position Value — what this bot's holdings are worth now,\n"
        "priced from the exchange (holdings × exchange price × quote rate).\n"
        "Blank whenever no fresh exchange price exists: the cell never shows\n"
        "a last-known figure, a computed stand-in or a ledger value.\n"
        "Hover a blank cell to read which of those is missing."
    ),
    3: "Total number of executed buy and sell trades",
    4: "Target Balance — the operator-set balance this bot trades\n"
    "relative to. Hard-capped per MEM-246 Phase B.",
    5: (
        "Target Balance denominated in BTC (target USD ÷ BTC/USD spot).\n"
        "Suffix Δ = 24h % change of <target>/BTC minus 24h % of "
        "<target>/USD.\n"
        "Positive Δ (green) = BTC-quoted pair cheaper in USD terms than USD-quoted.\n"
        "Blank when pair unlisted on this exchange or target is BTC itself."
    ),
    6: (
        "Target Balance denominated in ETH (target USD ÷ ETH/USD spot).\n"
        "Suffix Δ = 24h % change of <target>/ETH minus 24h % of "
        "<target>/USD.\n"
        "Positive Δ (green) = ETH-quoted pair cheaper in USD terms than USD-quoted.\n"
        "Blank when pair unlisted on this exchange or target is ETH itself."
    ),
    7: (
        "Ammo — distance of current position value from Target.\n"
        "Green = surplus above target (Scrum territory, next action = SELL).\n"
        "Red = deficit below target (Fold territory, next action = BUY).\n"
        "Neutral grey = within dust band around target (no action pending)."
    ),
    8: "Manual Fire — force immediate scrum/fold evaluation on next tick",
    9: "Click for full bot detail and status explanation",
}

FIXED_WIDTHS = {8: ds.TABLE_COL_FIRE_W, 9: ds.TABLE_COL_DETAIL_W}

ACCESSIBLE_NAME = ""

STATE_COLORS = {
    "running": ds.SUCCESS,
    "idle": ds.CARD_METRIC_LABEL,
    "paused": ds.WARNING,
    "error": ds.ERROR,
    "cooldown": ds.WARNING_STRONG,
    "stopped": ds.TEXT_MUTED,
    "starting": ds.STATE_STARTING,
}

DEFAULT_STATE_COLOR = ds.TEXT_HIGH

PRIVACY_FIELD_BY_COL = {
    0: "bot_table.bot_id",
    1: "bot_table.symbol",
    2: "bot_table.ammo",  # position value reuses the ammo mask
    3: "bot_table.trades",
    4: "bot_table.target",
    5: "bot_table.target",
    6: "bot_table.target",
    7: "bot_table.ammo",
    8: "bot_table.fire",
}

FIRE_COLUMN = 8
DETAIL_COLUMN = 9
BUTTON_COLUMNS = (FIRE_COLUMN, DETAIL_COLUMN)
BOT_ID_COLUMN = 0
SYMBOL_COLUMN = 1
POSITION_VALUE_COLUMN = 2
TRADES_COLUMN = 3
TARGET_COLUMN = 4
TARGET_BTC_COLUMN = 5
TARGET_ETH_COLUMN = 6
AMMO_COLUMN = 7

#: The cell field a click on each column opens. A column absent from it opens
#: nothing, and both surfaces read this one map rather than naming a column.
LINK_FIELD_BY_COLUMN: Dict[int, str] = {
    BOT_ID_COLUMN: "link_url",
    SYMBOL_COLUMN: "chart_url",
}

REVEALED_GLYPH = "●"
MASKED_GLYPH = "○"
STATE_MASKED = "MASKED"
STATE_REVEALED = "REVEALED"
HEADER_STATE_TIP_FORMAT = (
    "\n\nPrivacy: {state} (field {field_id}).\n" "Click the dot under this label."
)
HEADER_DOT_TIP_FORMAT = "{field_id}: {state}. Click to {action}."
HEADER_DOT_ACTION_MASK = "mask"
HEADER_DOT_ACTION_REVEAL = "reveal"

HEADER_LABEL_WRAP = True
HEADER_LABEL_FONT_PX = ds.TYPE_SMALL
HEADER_LABEL_MIN_FONT_PX = ds.TYPE_CAPTION
HEADER_DOT_FONT_PX = ds.TYPE_BODY
HEADER_DOT_ROW_PX = ds.TYPE_BODY + ds.SPACE_XS
HEADER_CELL_PAD_PX = ds.SPACE_XXS
HEADER_CELL_GAP_PX = ds.SPACE_XXS
# The skin carries no size, because a Qt style sheet's font-size outranks
# the font a widget is given, and the label's size is chosen per column.
HEADER_LABEL_SKIN = f"color: {ds.MAIN_TABLE_HEADER}; font-weight: bold;"
HEADER_LABEL_SIZE_FORMAT = " font-size: {px}px;"
HEADER_LABEL_STYLE = HEADER_LABEL_SKIN + HEADER_LABEL_SIZE_FORMAT.format(
    px=HEADER_LABEL_FONT_PX
)
HEADER_DOT_STYLE = (
    f"color: {ds.PRIMARY_BRIGHT}; "
    "background: transparent; "
    "border: none; "
    "padding: 0; "
    f"font-size: {HEADER_DOT_FONT_PX}px;"
)

# The mark sits in the header cell's own top-right corner, over the label,
# so neither the wrap nor the dot's centring moves when a column sorts.
HEADER_SORT_MARK_FONT_PX = ds.TYPE_CAPTION
HEADER_SORT_MARK_STYLE = (
    f"color: {ds.PRIMARY_BRIGHT}; "
    "background: transparent; "
    f"font-size: {HEADER_SORT_MARK_FONT_PX}px;"
)
HEADER_SORT_MARK_BOX_PX = ds.TYPE_CAPTION + ds.SPACE_XS

ALIGNMENT = "AlignCenter"
ALIGNMENT_VALUE = 132

MODE_SCRUMMING = "scrumming"
ACTIVE_STATES = ("running", "paused")
UNKNOWN_STATE_TEXT = "UNKNOWN"
MODE_TIP_FORMAT = "Mode: {mode}\nState: {state}"
TOOLTIP_LINE_GAP = "\n"

SKIP_LOG_FORMAT = (
    "BotStatusTable.update_bots received non-scrumming "
    "status (mode=%r bot=%r) — should have been routed "
    "to ExtractorBotTable. Skipping row."
)
SKIP_BOT_ID_LENGTH = 8
SKIP_BOT_ID_MISSING = "?"

ROW_REFUSED_LOG = "Bot table row %d refused for bot %r: %s: %s"

ICON_ASSET_SIZE_PX = ds.COIN_ICON_SIZE_PX
ICON_DOWNLOAD = False

#: The size the first column draws a kept logo at, and the row that fits it.
LOGO_SIZE_PX = 32
#: The room a row keeps above and below its content, ``PM_FocusFrameVMargin``.
ROW_LOGO_MARGIN_PX = 2
ROW_HEIGHT_PX = LOGO_SIZE_PX + 2 * ROW_LOGO_MARGIN_PX

LOGO_TIP_FORMAT = "{asset} — the target asset this bot accumulates"
NO_LOGO_TIP_FORMAT = "{asset} — no logo is kept for this asset yet"
LOGO_DATA_FORMAT = "data:image/{extension};base64,{body}"
LOGO_READ_FAILED_LOG = "Logo read failed for %r: %s: %s"
LOGO_READ_ERRORS = (OSError, ValueError, TypeError)

#: The only scheme ``opening_address`` answers an address for. It narrows
#: ``openable_url``, which allows http as well, and never widens it.
OPENING_SCHEMES: tuple[str, ...] = ("https",)

ORGANISATION_TIP_FORMAT = "Open {host} in default browser: {address}"
NO_ORGANISATION_TIP_FORMAT = (
    "no web address is known for {asset}, so this mark is not a link"
)
ORGANISATION_READ_FAILED_LOG = "Organisation address read failed for %r: %s: %s"
ORGANISATION_READ_ERRORS = (AttributeError, KeyError, TypeError, ValueError)

#: One ``LogoCache`` reader over the kept directory; ``resolve`` is never called.
KEPT_LOGOS = LogoCache()
#: One ``AssetManager`` over the same directory; only ``organisation_url`` is asked.
CRYPTO_RECORDS = AssetManager()
_LOGO_PATHS: Dict[str, str] = {}
_LOGO_DATA: Dict[str, str] = {}
_ORGANISATION_ADDRESSES: Dict[str, str] = {}

LINK_COLOR = ds.TEXT_INFO_SOFT
LINK_UNDERLINE = True
LINK_TIP_FORMAT = "Open chart on {exchange_id} " "in default browser: {url}"
CHART_URL_SKIPPED_LOG = "Chart-URL decoration skipped: %s: %s"
CHART_OPEN_FAILED_LOG = "Chart URL open failed for %r: %s"
BROWSER_NEW_WINDOW = 2

FIRE_LABEL = "Fire"
FIRE_MASK_FIELD = "bot_table.fire"
DETAIL_LABEL = "Detail"
BUTTON_HEIGHT_PX = 22
FOCUS_POLICY = "NoFocus"

GLOW_BLUR_RADIUS = 18
GLOW_OFFSET = (0, 0)

FIRE_STYLE_HEAD = "font-size: 10px; padding: 1px 6px; "

FIRE_STYLE_SCRUM_SOLID = (
    FIRE_STYLE_HEAD + f"color: {ds.TEXT_MAX}; font-weight: bold; "
    f"background-color: {ds.MAIN_ALERT_SURFACE}; "
    f"border: 1px solid {ds.ERROR};"
)
FIRE_STYLE_SCRUM_OUTLINE = (
    FIRE_STYLE_HEAD + f"color: {ds.ERROR}; font-weight: bold; "
    "background-color: transparent; "
    f"border: 1px dashed {ds.ERROR};"
)
FIRE_STYLE_FOLD_CEILING = (
    FIRE_STYLE_HEAD + f"color: {ds.TEXT_NEUTRAL}; font-weight: bold; "
    f"background-color: {ds.STATE_ENGAGED_DIM}; "
    f"border: 1px dashed {ds.CARD_METRIC_LABEL};"
)
FIRE_STYLE_FOLD_SOLID = (
    FIRE_STYLE_HEAD + f"color: {ds.TEXT_MAX}; font-weight: bold; "
    f"background-color: {ds.STATE_ENGAGED_DIM}; "
    f"border: 1px solid {ds.STATE_ARMED};"
)
FIRE_STYLE_FOLD_OUTLINE = (
    FIRE_STYLE_HEAD + f"color: {ds.STATE_ARMED}; font-weight: bold; "
    "background-color: transparent; "
    f"border: 1px dashed {ds.STATE_ARMED};"
)
FIRE_STYLE_PHASE_FIRE = (
    FIRE_STYLE_HEAD + f"color: {ds.TEXT_ON_LIGHT}; font-weight: bold; "
    f"background-color: {ds.WARNING}; "
    f"border: 1px solid {ds.STATE_PENDING};"
)
FIRE_STYLE_PHASE_TRACK = FIRE_STYLE_HEAD + f"color: {ds.WARNING}; font-weight: bold;"
FIRE_STYLE_PHASE_SEARCH = FIRE_STYLE_HEAD + f"color: {ds.ERROR}; font-weight: bold;"
FIRE_STYLE_DISABLED = (
    "font-size: 10px; padding: 1px 6px; color: " f"{ds.TEXT_PLACEHOLDER};"
)
DETAIL_STYLE = "font-size: 10px; padding: 1px 6px;"

FIRE_PATH_SCRUM_SOLID = "scrum_armed"
FIRE_PATH_SCRUM_OUTLINE = "scrum_override"
FIRE_PATH_FOLD_CEILING = "fold_ceiling"
FIRE_PATH_FOLD_SOLID = "fold_armed"
FIRE_PATH_FOLD_OUTLINE = "fold_override"
FIRE_PATH_PHASE_FIRE = "phase_fire"
FIRE_PATH_PHASE_TRACK = "phase_track"
FIRE_PATH_PHASE_SEARCH = "phase_search"
FIRE_PATH_NOT_SCRUMMING = "not_scrumming"
FIRE_PATH_INACTIVE = "inactive"

FIRE_PATHS = (
    FIRE_PATH_SCRUM_SOLID,
    FIRE_PATH_SCRUM_OUTLINE,
    FIRE_PATH_FOLD_CEILING,
    FIRE_PATH_FOLD_SOLID,
    FIRE_PATH_FOLD_OUTLINE,
    FIRE_PATH_PHASE_FIRE,
    FIRE_PATH_PHASE_TRACK,
    FIRE_PATH_PHASE_SEARCH,
    FIRE_PATH_NOT_SCRUMMING,
    FIRE_PATH_INACTIVE,
)

FIRE_STYLES = {
    FIRE_PATH_SCRUM_SOLID: FIRE_STYLE_SCRUM_SOLID,
    FIRE_PATH_SCRUM_OUTLINE: FIRE_STYLE_SCRUM_OUTLINE,
    FIRE_PATH_FOLD_CEILING: FIRE_STYLE_FOLD_CEILING,
    FIRE_PATH_FOLD_SOLID: FIRE_STYLE_FOLD_SOLID,
    FIRE_PATH_FOLD_OUTLINE: FIRE_STYLE_FOLD_OUTLINE,
    FIRE_PATH_PHASE_FIRE: FIRE_STYLE_PHASE_FIRE,
    FIRE_PATH_PHASE_TRACK: FIRE_STYLE_PHASE_TRACK,
    FIRE_PATH_PHASE_SEARCH: FIRE_STYLE_PHASE_SEARCH,
    FIRE_PATH_NOT_SCRUMMING: FIRE_STYLE_DISABLED,
    FIRE_PATH_INACTIVE: FIRE_STYLE_DISABLED,
}

NO_GLOW = ""
FIRE_GLOWS = {
    FIRE_PATH_SCRUM_SOLID: ds.ERROR,
    FIRE_PATH_SCRUM_OUTLINE: NO_GLOW,
    FIRE_PATH_FOLD_CEILING: ds.STATE_ENGAGED_GLOW,
    FIRE_PATH_FOLD_SOLID: ds.STATE_ARMED,
    FIRE_PATH_FOLD_OUTLINE: NO_GLOW,
    FIRE_PATH_PHASE_FIRE: ds.STATE_PENDING,
    FIRE_PATH_PHASE_TRACK: NO_GLOW,
    FIRE_PATH_PHASE_SEARCH: NO_GLOW,
    FIRE_PATH_NOT_SCRUMMING: NO_GLOW,
    FIRE_PATH_INACTIVE: NO_GLOW,
}

FIRE_TIP_SCRUM_SOLID = (
    "ARMED for SCRUM (auto would fire). "
    "Holdings above target; all gates clear. "
    "Clicking fires a MARKET sell to "
    "rebalance back to target."
)
FIRE_TIP_SCRUM_OUTLINE = (
    "Manual SCRUM override available — "
    "delta > 0 but auto-fire blocked. "
    "Clicking fires a MARKET sell sized to "
    "rebalance back to target (bypasses "
    "auto's TA/BB/HTF gates)."
)
FIRE_TIP_FOLD_CEILING = (
    "Fold would be armed, but POSITION "
    "CEILING has been reached. Fold is "
    "hard-stopped. Manual Fire will still "
    "attempt to rebalance (operator "
    "override bypasses the ceiling)."
)
FIRE_TIP_FOLD_SOLID = (
    "ARMED for FOLD (auto would fire). "
    "Holdings below target; all gates clear. "
    "Clicking fires a MARKET buy to "
    "rebalance back to target."
)
FIRE_TIP_FOLD_OUTLINE = (
    "Manual FOLD override available — "
    "delta < 0 but auto-fire blocked. "
    "Clicking fires a MARKET buy sized to "
    "rebalance back to target (bypasses "
    "auto's TA/BB/MEM-171 gates)."
)
FIRE_TIP_PHASE_FIRE = (
    "Organic FIRE phase — bot at band but "
    "holdings within dust band of target. "
    "Clicking has no effect."
)
FIRE_TIP_PHASE_TRACK = (
    "TRACKING — bot detected band approach. "
    "Fire is available but bot is within dust "
    "band; rebalance would be a no-op."
)
FIRE_TIP_PHASE_SEARCH = (
    "Bot within dust band of target. " "Manual Fire would be a no-op."
)
FIRE_TIP_NOT_SCRUMMING = "Manual Fire is scrumming-only."
FIRE_TIP_INACTIVE_FORMAT = "Bot is {state}; start or resume to enable Fire."
DETAIL_TIP = "View full bot status, configuration, and error details"

BLOCKERS_TIP_FORMAT = "\nBlocked by: {blockers}"
BLOCKERS_SEPARATOR = ", "
NO_BLOCKERS_TEXT = ""

CEILING_HARD_STOP_RATIO = 1.0
CEILING_APPROACH_RATIO = 0.5
PERCENT_SCALE = 100

CEILING_REACHED_FORMAT = (
    "\n\n⚠ CEILING REACHED "
    "({pct:.1f}% of ${ceiling_usd:.2f}) — "
    "fold hard-stopped, scrum only."
)
CEILING_APPROACH_FORMAT = (
    "\n\n⚠ Approaching ceiling "
    "({pct:.1f}% of ${ceiling_usd:.2f}) — "
    "fold rate tapered to {taper_pct:.0f}%."
)
CEILING_NORMAL_FORMAT = (
    "\n\nCeiling: {pct:.1f}% of " "${ceiling_usd:.2f} " "(fold rate: {taper_pct:.0f}%)."
)
DETONATION_FORMAT = (
    "\nDetonation armed: monitoring " "{timeframe} for BULLISH " "auto-harvest."
)

DEFAULT_FOLD_TAPER = 1.0
DEFAULT_DETONATION_TIMEFRAME = "1d"
DEFAULT_QUOTE_TO_USD = 1.0
NO_TARGET_VALUE = 0.0
NO_PRICE = 0.0
NO_HOLDINGS = 0.0
NO_TRADES = 0
SYMBOL_SEPARATOR = "/"
QUOTE_BTC = "BTC"
QUOTE_ETH = "ETH"
EMPTY_TEXT = ""
NO_SELECTION_ROW = -1
NO_SELECTION_BOT_ID = ""

SORT_KIND_TEXT = "text"
SORT_KIND_NUMBER = "number"
SORT_KIND_NONE = "none"

# The Detail column holds one identical button a row, so it carries no
# value to order by and is the one column a press does not sort.
SORT_KIND_BY_COL = {
    BOT_ID_COLUMN: SORT_KIND_TEXT,
    SYMBOL_COLUMN: SORT_KIND_TEXT,
    POSITION_VALUE_COLUMN: SORT_KIND_NUMBER,
    TRADES_COLUMN: SORT_KIND_NUMBER,
    TARGET_COLUMN: SORT_KIND_NUMBER,
    TARGET_BTC_COLUMN: SORT_KIND_NUMBER,
    TARGET_ETH_COLUMN: SORT_KIND_NUMBER,
    AMMO_COLUMN: SORT_KIND_NUMBER,
    FIRE_COLUMN: SORT_KIND_NUMBER,
    DETAIL_COLUMN: SORT_KIND_NONE,
}

SORTABLE_COLUMNS = tuple(
    column
    for column, kind in sorted(SORT_KIND_BY_COL.items())
    if kind != SORT_KIND_NONE
)

NO_SORT_COLUMN = -1
SORT_ASCENDING = "ascending"
SORT_DESCENDING = "descending"
SORT_UNSORTED = ""
SORT_MARK_ASCENDING = "▲"
SORT_MARK_DESCENDING = "▼"
SORT_MARK_NONE = ""

SORT_TIP_BY_KIND = {
    SORT_KIND_TEXT: {
        SORT_ASCENDING: "\n\nSorted A to Z. Press the label to reverse.",
        SORT_DESCENDING: "\n\nSorted Z to A. Press the label to reverse.",
        SORT_UNSORTED: "\n\nPress the label to sort this column A to Z.",
    },
    SORT_KIND_NUMBER: {
        SORT_ASCENDING: "\n\nSorted lowest first. Press the label to reverse.",
        SORT_DESCENDING: "\n\nSorted highest first. Press the label to reverse.",
        SORT_UNSORTED: "\n\nPress the label to sort this column lowest first.",
    },
    SORT_KIND_NONE: {
        SORT_ASCENDING: EMPTY_TEXT,
        SORT_DESCENDING: EMPTY_TEXT,
        SORT_UNSORTED: EMPTY_TEXT,
    },
}

# Armed first, then the two organic phases, then idle, then the rows whose
# Fire button is disabled.
FIRE_SORT_RANK = {"scrum": 0.0, "fold": 1.0, "fire": 2.0, "track": 3.0}
FIRE_SORT_IDLE = 4.0
FIRE_SORT_DISABLED = 5.0

SORTING_ENABLED = True
SELECTION_BEHAVIOR = "SelectRows"
EDIT_TRIGGERS = "NoEditTriggers"
ALTERNATING_ROW_COLORS = True
VERTICAL_HEADER_VISIBLE = False
HEADER_RESIZE_MODE = "Stretch"
FIXED_RESIZE_MODE = "Fixed"

SKIN: dict[str, str] = {}
STYLE_SHEET = ""
TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()

ACTIONS = {
    "privacy_toggled": "on_privacy_toggled",
    "header_sorted": "on_header_sorted",
    "cell_clicked": "on_cell_clicked",
    "fire_clicked": "on_fire",
    "detail_clicked": "on_detail",
    "row_pressed": "on_row_pressed",
    "view_scrolled": "on_view_scrolled",
}

ROW_COUNT_SET = "rows.count"
ROW_SKIPPED = "row.skipped"
ROW_REFUSED = "row.refused"
ROW_BUILT = "row.built"
ROW_TARGET = "row.target"
ROW_SYMBOL_LINK = "row.link"
ROW_SYMBOL_LINK_FAILED = "row.link_failed"
ROW_LOGO = "row.logo"
FIRE_BUILT = "fire.built"
FIRE_GLOW = "fire.glow"
DETAIL_BUILT = "detail.built"
HEADER_REFRESHED = "header.refreshed"
HEADER_TOGGLED = "header.toggled"
SORT_APPLIED = "sort.applied"
SORT_IGNORED = "sort.ignored"
HEADER_IGNORED = "header.ignored"
HEADER_FAILED = "header.failed"
SELECTION_READ = "selection.read"
SELECTION_ANCHORED = "selection.anchored"
SELECTION_CLEARED = "selection.cleared"
SELECTION_RELEASED = "selection.released"
SELECTION_ROW = "selection.row"
ROW_PRESSED = "row.pressed"
ROW_HIGHLIGHTED = "row.highlighted"
DETAIL_CLICKED = "detail.clicked"
FIRE_CLICKED = "fire.clicked"
CELL_IGNORED = "cell.ignored"
CELL_OPENED = "cell.opened"
CELL_REFUSED = "cell.refused"

CellCall = list


def header_glyph(masked: bool) -> str:
    """The dot under a maskable column's label: filled shown, hollow hidden."""
    return MASKED_GLYPH if masked else REVEALED_GLYPH


def header_state(masked: bool) -> str:
    """The word the header tooltip names this column's privacy state with."""
    return STATE_MASKED if masked else STATE_REVEALED


def header_tooltip(column: int, field_id: str, masked: bool) -> str:
    """One maskable column header's tooltip, its privacy state appended."""
    tip = COLUMN_TOOLTIPS.get(column, EMPTY_TEXT)
    state_tip = HEADER_STATE_TIP_FORMAT.format(
        state=header_state(masked), field_id=field_id
    )
    return (tip + state_tip).strip()


def header_dot_tooltip(field_id: str, masked: bool) -> str:
    """The tooltip the dot under one column's label carries."""
    return HEADER_DOT_TIP_FORMAT.format(
        field_id=field_id,
        state=header_state(masked),
        action=HEADER_DOT_ACTION_REVEAL if masked else HEADER_DOT_ACTION_MASK,
    )


def header_view(
    column: int,
    label: str,
    masked: Optional[bool],
    sort_column: int = NO_SORT_COLUMN,
    descending: bool = False,
) -> dict:
    """One column header: its label, its sort mark, and the dot beneath it.

    A ``masked`` of None names a column ``PRIVACY_FIELD_BY_COL`` does not
    carry, which draws its label with no dot under it.
    """
    field_id = PRIVACY_FIELD_BY_COL.get(column, EMPTY_TEXT)
    direction = sort_direction(column, sort_column, descending)
    found = {
        "text": label,
        "tooltip": COLUMN_TOOLTIPS.get(column, EMPTY_TEXT),
        "field_id": EMPTY_TEXT,
        "masked": False,
        "dot_text": EMPTY_TEXT,
        "dot_tooltip": EMPTY_TEXT,
        "sortable": column in SORTABLE_COLUMNS,
        "sort_kind": SORT_KIND_BY_COL.get(column, SORT_KIND_NONE),
        "sort_direction": direction,
        "sort_mark": sort_mark(direction),
    }
    if field_id and masked is not None:
        found["tooltip"] = header_tooltip(column, field_id, masked)
        found["field_id"] = field_id
        found["masked"] = bool(masked)
        found["dot_text"] = header_glyph(masked)
        found["dot_tooltip"] = header_dot_tooltip(field_id, masked)
    found["tooltip"] = (found["tooltip"] + sort_tooltip(column, direction)).strip()
    return found


def target_text(target_val: float) -> str:
    """The Target figure without its sign, or dashes when there is no target."""
    return magnitude(target_val) if target_val > 0 else NO_TARGET_TEXT


def state_color(state: Any) -> str:
    """The colour the Symbol cell is drawn in for one bot state."""
    return STATE_COLORS.get(state, DEFAULT_STATE_COLOR)


def mode_tooltip(mode: Any, state: Any) -> str:
    """The Symbol cell tooltip, which names the mode and the state in full."""
    shown = state.upper() if state else UNKNOWN_STATE_TEXT
    return MODE_TIP_FORMAT.format(mode=mode, state=shown)


def base_asset_of(symbol: Any) -> str:
    """The traded asset's name, taken from the left of the pair."""
    if SYMBOL_SEPARATOR in symbol:
        return symbol.split(SYMBOL_SEPARATOR)[0].upper()
    return EMPTY_TEXT


def icon_asset_of(text: str) -> str:
    """The asset whose logo the first column asks for, masked text included."""
    return text.split(SYMBOL_SEPARATOR)[0] if SYMBOL_SEPARATOR in text else text


def kept_logo_path(symbol: str) -> str:
    """``KEPT_LOGOS.kept_path`` for ``symbol``'s base asset, then for the whole pair.

    A crypto record is kept under its base and a currency pair under the
    pair, so both keys are asked and a hit is held in ``_LOGO_PATHS``.
    """
    if not symbol:
        return EMPTY_TEXT
    held = _LOGO_PATHS.get(symbol)
    if held:
        return held
    for asked in (icon_asset_of(symbol), symbol):
        if not asked:
            continue
        try:
            found = KEPT_LOGOS.kept_path(asked)
        except LOGO_READ_ERRORS as exc:
            logger.debug(LOGO_READ_FAILED_LOG, asked, type(exc).__name__, exc)
            continue
        if found is not None:
            _LOGO_PATHS[symbol] = str(found)
            return str(found)
    return EMPTY_TEXT


def opening_address(value: Any) -> str:
    """``value`` when it is an ``https`` address carrying a host, empty for every other.

    Both surfaces read a cell's stored address through this before any
    browser is asked to open it, so an http, file, javascript, data or
    scheme-less value never reaches one.
    """
    address, _ = openable_url(str(value or EMPTY_TEXT), allowed_schemes=OPENING_SCHEMES)
    if not address:
        return EMPTY_TEXT
    try:
        host = urllib.parse.urlsplit(address).hostname
    except ValueError:
        return EMPTY_TEXT
    return address if host else EMPTY_TEXT


def organisation_address(symbol: str) -> str:
    """``symbol``'s own organisation address, empty for an asset resolving none.

    A crypto base answers its record's own site and a listed name answers
    ``organisation_page``; the regulator's company-search page is not an
    organisation's own site and is never answered. Each answer is held in
    ``_ORGANISATION_ADDRESSES``.
    """
    if not symbol:
        return EMPTY_TEXT
    held = _ORGANISATION_ADDRESSES.get(symbol)
    if held is not None:
        return held
    found = EMPTY_TEXT
    for asked in (icon_asset_of(symbol), symbol):
        if not asked:
            continue
        try:
            site, _ = CRYPTO_RECORDS.organisation_url(asked)
            found = site or organisation_page(asked)
        except ORGANISATION_READ_ERRORS as exc:
            logger.debug(ORGANISATION_READ_FAILED_LOG, asked, type(exc).__name__, exc)
            continue
        if found:
            break
    address = opening_address(found)
    _ORGANISATION_ADDRESSES[symbol] = address
    return address


def organisation_tooltip(asset: str, address: str) -> str:
    """The line a mark's tooltip carries: where a click goes, or that it is not a link."""
    if not address:
        return NO_ORGANISATION_TIP_FORMAT.format(asset=asset)
    host = urllib.parse.urlsplit(address).hostname or address
    return ORGANISATION_TIP_FORMAT.format(host=host, address=address)


def logo_data_address(path: str) -> str:
    """``path``'s bytes in ``LOGO_DATA_FORMAT``, held in ``_LOGO_DATA`` after one read."""
    if not path:
        return EMPTY_TEXT
    held = _LOGO_DATA.get(path)
    if held is not None:
        return held
    try:
        with open(path, "rb") as handle:
            body = handle.read()
    except LOGO_READ_ERRORS as exc:
        logger.debug(LOGO_READ_FAILED_LOG, path, type(exc).__name__, exc)
        _LOGO_DATA[path] = EMPTY_TEXT
        return EMPTY_TEXT
    extension = image_extension(body)
    found = (
        LOGO_DATA_FORMAT.format(
            extension=extension, body=base64.b64encode(body).decode("ascii")
        )
        if extension
        else EMPTY_TEXT
    )
    _LOGO_DATA[path] = found
    return found


def logo_cell(asset: str, shown: str, path: str, link: str = EMPTY_TEXT) -> dict:
    """The first column's cell: ``asset``'s logo at ``path``, its ticker, or ``shown``.

    ``link`` is the organisation address a click opens, and its tooltip line
    names where that click goes or says the mark is not a link.
    """
    if shown != asset or not asset:
        return cell(shown)
    mark_tip = organisation_tooltip(asset, link)
    address = logo_data_address(path)
    if path and address:
        return cell(
            EMPTY_TEXT,
            tooltip=LOGO_TIP_FORMAT.format(asset=asset) + TOOLTIP_LINE_GAP + mark_tip,
            logo_path=path,
            logo_image=address,
            logo_size=LOGO_SIZE_PX,
            link_url=link,
        )
    return cell(
        asset,
        tooltip=NO_LOGO_TIP_FORMAT.format(asset=asset) + TOOLTIP_LINE_GAP + mark_tip,
        link_url=link,
    )


def blockers_text(blockers: list) -> str:
    """The line naming the gates that hold automatic fire back."""
    if not blockers:
        return NO_BLOCKERS_TEXT
    return BLOCKERS_TIP_FORMAT.format(blockers=BLOCKERS_SEPARATOR.join(blockers))


def target_value(status: Any) -> float:
    """The target the engine re-zeros to, or the configured target_balance.

    ``ammo_target`` holds the rule, so the header strip's AMMO total reads
    the same target this row's Ammo cell is measured against.
    """
    return ammo_target(
        status.get("live_target_balance", NO_TARGET_VALUE),
        status.get("target_balance", NO_TARGET_VALUE),
    )


def quote_rate_of(status: Any) -> float:
    """The quote_to_usd rate that turns this bot's quote asset into dollars."""
    return float(
        status.get("quote_to_usd", DEFAULT_QUOTE_TO_USD) or DEFAULT_QUOTE_TO_USD
    )


def holdings_of(status: Any) -> float:
    """The current_holdings of the target asset this bot reports."""
    return float(status.get("current_holdings", NO_HOLDINGS) or NO_HOLDINGS)


class SortLookups:
    """The two live readings ``sort_value`` needs, one pair per build variant.

    ``price`` answers one bot's price and its age in seconds, and
    ``denom_text`` answers what a Target-BTC or Target-ETH cell would draw.
    """

    def __init__(self, price, denom_text) -> None:
        self.price = price
        self.denom_text = denom_text


def surface_lookups() -> SortLookups:
    """The ``SortLookups`` the page's own ``TableCellsModel`` answers.

    The recorder is a throwaway ``TableCellsModel``, which keeps the
    ordering pass out of the table's own ``calls`` list.
    """
    cells = TableCellsModel()

    def price(status: Any) -> tuple:
        stats = status.get("stats") or {}
        return cells.fresh_price(
            cells.price_pool(),
            str(status.get("exchange", EMPTY_TEXT) or EMPTY_TEXT),
            str(status.get("symbol", EMPTY_TEXT) or EMPTY_TEXT),
            float(stats.get("current_price", NO_PRICE) or NO_PRICE),
        )

    def denom_text(quote: str, base: str, exchange_id: str, target: float) -> str:
        return cells.target_denom_cell(quote, base, exchange_id, target)[0]

    return SortLookups(price, denom_text)


def position_sort_value(status: Any, lookups: SortLookups):
    """The figure the Position Value cell draws, or None where it is blank.

    The cell blanks on no holdings, on no price, on a price ``lookups``
    did not age, and on an age past ``PRICE_STALE_AFTER_S``.
    """
    holdings = holdings_of(status)
    if holdings <= NO_HOLDINGS:
        return None
    price, age_s = lookups.price(status)
    if float(price or NO_PRICE) <= NO_PRICE:
        return None
    if age_s is None or float(age_s) > PRICE_STALE_AFTER_S:
        return None
    return priced_position(holdings, float(price), quote_rate_of(status))


def ammo_sort_value(status: Any, lookups: SortLookups):
    """The figure the Ammo cell draws, or None where that cell is blank.

    ``ammo_text`` writes that distance from target without its sign, so
    ``ammo_sort_value`` answers it without its sign too.
    """
    stats = status.get("stats") or {}
    holdings = holdings_of(status)
    price, _age_s = lookups.price(status)
    price = float(price or NO_PRICE)
    stats_pv = float(stats.get("position_value", NO_TARGET_VALUE) or NO_TARGET_VALUE)
    fresh = holdings > NO_HOLDINGS and price > NO_PRICE
    position = (
        priced_position(holdings, price, quote_rate_of(status)) if fresh else stats_pv
    )
    target = target_value(status)
    if position <= NO_TARGET_VALUE and holdings > NO_HOLDINGS:
        return None
    if target <= NO_TARGET_VALUE:
        return None
    if position <= NO_TARGET_VALUE:
        return abs(NO_TARGET_VALUE - target)
    return abs(position - target)


def denom_sort_value(column: int, status: Any, lookups: SortLookups):
    """The target a denom column orders by, or None where the cell is blank.

    Every row divides its target by one quote price, so ordering on the
    target orders on the units ``denom_text`` draws.
    """
    target = target_value(status)
    if target <= NO_TARGET_VALUE:
        return None
    quote = QUOTE_BTC if column == TARGET_BTC_COLUMN else QUOTE_ETH
    base = base_asset_of(status.get("symbol", EMPTY_TEXT) or EMPTY_TEXT)
    if not base or base == quote:
        return None
    drawn = lookups.denom_text(
        quote, base, str(status.get("exchange", EMPTY_TEXT) or EMPTY_TEXT), target
    )
    return target if drawn else None


def fire_sort_value(status: Any) -> float:
    """Where one bot ranks in FIRE_SORT_RANK: armed first, disabled last."""
    if status.get("mode", EMPTY_TEXT) != MODE_SCRUMMING:
        return FIRE_SORT_DISABLED
    if status.get("state", EMPTY_TEXT) not in ACTIVE_STATES:
        return FIRE_SORT_DISABLED
    armed = status.get("armed_action")
    if armed in FIRE_SORT_RANK:
        return FIRE_SORT_RANK[armed]
    phase = status.get("scrum_target_mode")
    if phase in FIRE_SORT_RANK:
        return FIRE_SORT_RANK[phase]
    return FIRE_SORT_IDLE


def sort_value(column: int, status: Any, lookups: SortLookups):
    """What one bot sorts by in one column, or None where its cell is blank.

    A SORT_KIND_NUMBER column answers the figure its cell was computed
    from, never the text the cell draws.
    """
    if SORT_KIND_BY_COL.get(column, SORT_KIND_NONE) == SORT_KIND_NONE:
        return None
    if column == BOT_ID_COLUMN:
        return icon_asset_of(
            str(status.get("symbol", EMPTY_TEXT) or EMPTY_TEXT)
        ).casefold()
    if column == SYMBOL_COLUMN:
        return str(status.get("symbol", EMPTY_TEXT) or EMPTY_TEXT).casefold()
    if column == POSITION_VALUE_COLUMN:
        return position_sort_value(status, lookups)
    if column == TRADES_COLUMN:
        stats = status.get("stats") or {}
        return float(stats.get("total_trades", NO_TRADES) or NO_TRADES)
    if column == TARGET_COLUMN:
        target = target_value(status)
        return target if target > NO_TARGET_VALUE else None
    if column in (TARGET_BTC_COLUMN, TARGET_ETH_COLUMN):
        return denom_sort_value(column, status, lookups)
    if column == AMMO_COLUMN:
        return ammo_sort_value(status, lookups)
    return fire_sort_value(status)


def order_statuses(
    statuses: list, column: int, descending: bool, lookups: SortLookups
) -> list:
    """One fleet ordered by one column, every blank cell beneath the figures.

    A column outside SORTABLE_COLUMNS answers the list unchanged, and the
    bot's own id breaks a tie so one fleet always lands one way.
    """
    if column not in SORTABLE_COLUMNS:
        return list(statuses)
    drawn = []
    blank = []
    for status in statuses:
        found = sort_value(column, status, lookups)
        if found is None:
            blank.append(status)
        else:
            drawn.append(
                (found, str(status.get("bot_id", EMPTY_TEXT) or EMPTY_TEXT), status)
            )
    drawn.sort(key=lambda row: (row[0], row[1]), reverse=descending)
    return [row[2] for row in drawn] + blank


def sort_direction(column: int, sort_column: int, descending: bool) -> str:
    """Which way one column is ordered, or SORT_UNSORTED when it is not sorted."""
    if column != sort_column or column not in SORTABLE_COLUMNS:
        return SORT_UNSORTED
    return SORT_DESCENDING if descending else SORT_ASCENDING


def sort_mark(direction: str) -> str:
    """The arrow one column's heading carries for its own sort_direction."""
    if direction == SORT_ASCENDING:
        return SORT_MARK_ASCENDING
    if direction == SORT_DESCENDING:
        return SORT_MARK_DESCENDING
    return SORT_MARK_NONE


def sort_tooltip(column: int, direction: str) -> str:
    """The line one column's tooltip carries from SORT_TIP_BY_KIND."""
    kind = SORT_KIND_BY_COL.get(column, SORT_KIND_NONE)
    return SORT_TIP_BY_KIND[kind][direction]


def selection_after_press(pressed_bot_id: str, shown_bot_id: str) -> str:
    """The bot a press on one row leaves selected.

    A press naming the bot already shown answers no bot, so the second
    press on one row turns the Voting Panel off; a press naming another
    bot answers that bot. ``BotStatusTable.mousePressEvent`` and
    ``BotStatusTableModel.on_row_pressed`` both decide it here, so the
    two build variants cannot drift apart.
    """
    pressed = str(pressed_bot_id or "")
    if not pressed or pressed == str(shown_bot_id or ""):
        return NO_SELECTION_BOT_ID
    return pressed


def selection_after_view_moved(
    selected_row: int, first_drawn_row: int, last_drawn_row: int
) -> int:
    """The row that keeps the highlight once the rows or the scroll moved.

    A ``selected_row`` outside the drawn band answers ``NO_SELECTION_ROW``, so
    a bot list releases its highlight rather than scroll to it.
    ``BotStatusTable.release_selection_off_view`` and
    ``BotStatusTableModel.on_view_scrolled`` both decide it here.
    """
    row = int(selected_row)
    first = int(first_drawn_row)
    last = int(last_drawn_row)
    if row < 0 or first < 0 or last < first:
        return NO_SELECTION_ROW
    if first <= row <= last:
        return row
    return NO_SELECTION_ROW


def cell(
    text: str, color: str = EMPTY_TEXT, tooltip: str = EMPTY_TEXT, **extra
) -> dict:
    """One table cell: its text, its colour, its tooltip and its alignment."""
    found = {
        "text": text,
        "color": color,
        "tooltip": tooltip,
        "alignment": ALIGNMENT,
        "alignment_value": ALIGNMENT_VALUE,
        "icon_asset": EMPTY_TEXT,
        "icon_size": ICON_ASSET_SIZE_PX,
        "icon_color": EMPTY_TEXT,
        "icon_letter": EMPTY_TEXT,
        "logo_path": EMPTY_TEXT,
        "logo_image": EMPTY_TEXT,
        "logo_size": LOGO_SIZE_PX,
        "link_url": EMPTY_TEXT,
        "chart_url": EMPTY_TEXT,
        "underline": False,
    }
    found.update(extra)
    return found


def blank_row() -> dict:
    """One row the rewrite made room for and has not written into yet.

    Ten empty cells and no buttons, which is what a table holds for a
    row it has counted and not filled.
    """
    return {"cells": [None] * COLUMN_COUNT, "fire": None, "detail": None}


class BotStatusTableModel:
    """The bot table: its headers, its rows, its buttons and its selection.

    ``update_bots`` rewrites every row from one list of bot statuses.
    ``refresh_header_dots`` rebuilds the ten column headers from the
    privacy register. ``on_privacy_toggled``, ``on_cell_clicked``,
    ``on_fire``, ``on_detail`` and ``on_row_pressed`` are the five things
    the operator can press. ``highlight_bot`` is the one the window calls
    instead, when the Voting Panel moved the selection. Every step is
    appended to ``calls`` in the order the shipped table makes it.
    """

    def __init__(
        self, on_bot_clicked=None, on_fire_clicked=None, on_bot_selected=None
    ) -> None:
        self.on_bot_clicked = on_bot_clicked
        self.on_fire_clicked = on_fire_clicked
        self.on_bot_selected = on_bot_selected
        self.exchange_id = ""
        self.bot_ids: list = []
        self.last_statuses: list = []
        self.rows: list = []
        self.skipped_rows: list = []
        self.headers: list = []
        self.calls: list[CellCall] = []
        self.current_row = NO_SELECTION_ROW
        self.has_selection = False
        self.opened_urls: list = []
        self.detail_clicks: list = []
        self.fire_clicks: list = []
        self.glows: list = []
        self.cells = TableCellsModel()
        self.sort_column = NO_SORT_COLUMN
        self.sort_descending = False
        self.refresh_header_dots()

    # ----- headers -----

    def refresh_header_dots(self) -> None:
        """Rebuild the ten column headers, each with its own dot's state."""
        try:
            registry = get_privacy_mask_registry()
        except Exception:
            self.calls.append([HEADER_FAILED])
            return
        found = []
        for column, label in enumerate(COLUMN_LABELS):
            field_id = PRIVACY_FIELD_BY_COL.get(column)
            masked = registry.is_masked(field_id) if field_id else None
            found.append(
                header_view(
                    column, label, masked, self.sort_column, self.sort_descending
                )
            )
        self.headers = found
        self.calls.append([HEADER_REFRESHED, len(found)])

    def on_header_sorted(self, column: int) -> None:
        """Order the rows by one column, reversing when it is already the one.

        A column outside SORTABLE_COLUMNS is recorded and changes nothing.
        """
        if column not in SORTABLE_COLUMNS:
            self.calls.append([SORT_IGNORED, column])
            return
        if column == self.sort_column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = column
            self.sort_descending = False
        self.calls.append([SORT_APPLIED, column, self.sort_descending])
        self.refresh_header_dots()
        if self.last_statuses:
            self.update_bots(self.last_statuses)

    def on_privacy_toggled(self, column: int) -> None:
        """Hide or show one column, then repaint the rows under the new state."""
        field_id = PRIVACY_FIELD_BY_COL.get(column)
        if not field_id:
            self.calls.append([HEADER_IGNORED, column])
            return
        try:
            registry = get_privacy_mask_registry()
            registry.set_masked(field_id, not registry.is_masked(field_id))
        except Exception:
            self.calls.append([HEADER_FAILED])
            return
        self.calls.append([HEADER_TOGGLED, column, field_id])
        self.refresh_header_dots()
        if self.last_statuses:
            self.update_bots(self.last_statuses)

    # ----- rows -----

    def set_row_count(self, count: int) -> None:
        """Make room for `count` rows, keeping the rows that already fit.

        A shrink drops the rows off the end and a growth adds empty ones,
        which is what the table itself does. A rewrite that stops part
        way therefore leaves the rows it did not reach as they were.
        """
        while len(self.rows) > count:
            self.rows.pop()
        while len(self.rows) < count:
            self.rows.append(blank_row())
        self.calls.append([ROW_COUNT_SET, count])

    def _sort_lookups(self) -> SortLookups:
        """The two readings ``order_statuses`` orders this model's rows by."""
        return surface_lookups()

    def update_bots(self, bot_statuses: list) -> None:
        """Rewrite every row from one list of bot statuses.

        The order is recomputed here, on every rewrite, so a column whose
        figures keep moving keeps the order the operator pressed for.
        """
        self.last_statuses = list(bot_statuses)
        bot_statuses = order_statuses(
            self.last_statuses,
            self.sort_column,
            self.sort_descending,
            self._sort_lookups(),
        )
        selected_before = self.get_selected_bot_id()
        self.set_row_count(len(bot_statuses))
        self.bot_ids = []
        self.skipped_rows = []
        for row, status in enumerate(bot_statuses):
            stats = status.get("stats", {})
            bot_id = status.get("bot_id", EMPTY_TEXT)
            self.bot_ids.append(bot_id)
            state = status.get("state", EMPTY_TEXT)
            mode = status.get("mode", EMPTY_TEXT)
            if mode != MODE_SCRUMMING:
                logging.getLogger(SKIP_LOGGER_NAME).warning(
                    SKIP_LOG_FORMAT,
                    mode,
                    bot_id[:SKIP_BOT_ID_LENGTH] if bot_id else SKIP_BOT_ID_MISSING,
                )
                self.rows[row] = blank_row()
                self.skipped_rows.append(row)
                self.calls.append([ROW_SKIPPED, row, mode])
                continue
            try:
                self._write_row(row, status, stats, state, mode)
            except Exception as exc:
                # One bad field stops one row; every other bot still paints.
                logger.warning(
                    ROW_REFUSED_LOG,
                    row,
                    bot_id[:SKIP_BOT_ID_LENGTH] if bot_id else SKIP_BOT_ID_MISSING,
                    type(exc).__name__,
                    exc,
                )
                self.rows[row] = blank_row()
                self.skipped_rows.append(row)
                self.calls.append([ROW_REFUSED, row, type(exc).__name__])
                continue
            self.calls.append([ROW_BUILT, row, bot_id])
        self.reanchor_selection(selected_before)

    def set_cell(self, row: int, column: int, found: dict) -> None:
        """Put one cell in one place, replacing whatever was there."""
        self.rows[row]["cells"][column] = found

    def cell_at(self, row: int, column: int) -> Optional[dict]:
        """The cell in one place, or None where the table holds none."""
        if not 0 <= row < len(self.rows):
            return None
        return self.rows[row]["cells"][column]

    def _write_row(self, row, status, stats, state, mode) -> None:
        """Write one row's eight cells and its two buttons, in paint order.

        Every value the row needs is computed before the first cell is
        written, and each cell is written as it is made, so a value that
        refuses part way leaves exactly the cells the table would keep.
        """
        target_val = self._target_value(status)
        price, price_age_s, quote_rate = self._price_reading(status, stats)
        holdings = float(status.get("current_holdings", NO_HOLDINGS))
        position = self.cells.position_value_cell(
            holdings, price, quote_rate, price_age_s
        )
        ammo = self._ammo_cell(
            stats, target_val, holdings, price, quote_rate, price_age_s
        )
        symbol = status.get("symbol", EMPTY_TEXT) or EMPTY_TEXT
        base_asset = base_asset_of(symbol)
        exchange_id = status.get("exchange", EMPTY_TEXT) or EMPTY_TEXT
        btc_text, btc_color = self.cells.target_denom_cell(
            QUOTE_BTC, base_asset, exchange_id, target_val
        )
        eth_text, eth_color = self.cells.target_denom_cell(
            QUOTE_ETH, base_asset, exchange_id, target_val
        )
        logo_asset = icon_asset_of(symbol)
        texts = [
            mask_or(logo_asset, PRIVACY_FIELD_BY_COL[0]),
            mask_or(status.get("symbol", EMPTY_TEXT), PRIVACY_FIELD_BY_COL[1]),
            mask_or(position["text"], PRIVACY_FIELD_BY_COL[2]),
            mask_or(str(stats.get("total_trades", NO_TRADES)), PRIVACY_FIELD_BY_COL[3]),
            mask_or(target_text(target_val), PRIVACY_FIELD_BY_COL[4]),
            mask_or(btc_text, PRIVACY_FIELD_BY_COL[5]),
            mask_or(eth_text, PRIVACY_FIELD_BY_COL[6]),
            mask_or(ammo["text"], PRIVACY_FIELD_BY_COL[7]),
        ]
        colors = {
            TARGET_BTC_COLUMN: btc_color,
            TARGET_ETH_COLUMN: eth_color,
            AMMO_COLUMN: ammo["color"],
        }
        for column, text in enumerate(texts):
            if column == BOT_ID_COLUMN:
                found = self._logo_cell(symbol, text)
            elif column == SYMBOL_COLUMN:
                found = self._symbol_cell(text, status, exchange_id, state, mode)
            elif column == POSITION_VALUE_COLUMN:
                found = cell(text, position["color"], position["tip"])
            elif column == AMMO_COLUMN:
                found = cell(text, colors[column], ammo["tip"])
            elif column in colors:
                found = cell(text, colors[column])
            else:
                found = cell(text)
            self.set_cell(row, column, found)
        self.rows[row]["fire"] = self._fire_button(status, state, mode)
        self.rows[row]["detail"] = self._detail_button()

    def _target_value(self, status) -> float:
        """The ``target_value`` of one status, recorded as the row reads it."""
        found = target_value(status)
        self.calls.append([ROW_TARGET, found])
        return found

    def _price_reading(self, status, stats) -> tuple:
        """One price for this row, its age in seconds, and the quote rate.

        Read once per row, so the Position Value cell and the Ammo cell
        are priced from the same lookup rather than from two of them.
        """
        price, price_age_s = self.cells.fresh_price(
            self.cells.price_pool(),
            str(status.get("exchange", EMPTY_TEXT) or EMPTY_TEXT),
            str(status.get("symbol", EMPTY_TEXT) or EMPTY_TEXT),
            float(stats.get("current_price", NO_PRICE)),
        )
        quote_rate = float(
            status.get("quote_to_usd", DEFAULT_QUOTE_TO_USD) or DEFAULT_QUOTE_TO_USD
        )
        return price, price_age_s, quote_rate

    def _ammo_cell(
        self, stats, target_val, holdings, price, quote_rate, price_age_s
    ) -> dict:
        """The Ammo cell, computed from a fresh price wherever one exists."""
        stats_pv = float(stats.get("position_value", NO_TARGET_VALUE))
        return self.cells.ammo_cell(
            stats_pv, holdings, price, quote_rate, target_val, price_age_s=price_age_s
        )

    def _logo_cell(self, symbol, shown) -> dict:
        """The first column's cell, ``logo_cell`` over ``symbol``'s kept file and address."""
        asset = icon_asset_of(symbol)
        path = kept_logo_path(symbol)
        link = organisation_address(symbol)
        self.calls.append([ROW_LOGO, asset, LOGO_SIZE_PX, bool(path), bool(link)])
        return logo_cell(asset, shown, path, link)

    def _symbol_cell(self, text, status, exchange_id, state, mode) -> dict:
        """The Symbol cell: the state colour, the mode tooltip, and the chart link."""
        if not text:
            return cell(text)
        found = cell(text, state_color(state), mode_tooltip(mode, state))
        try:
            url = chart_url(exchange_id, status.get("symbol", EMPTY_TEXT) or EMPTY_TEXT)
        except Exception as exc:
            logger.debug(CHART_URL_SKIPPED_LOG, type(exc).__name__, exc)
            self.calls.append([ROW_SYMBOL_LINK_FAILED, type(exc).__name__])
            return found
        if url:
            found["chart_url"] = url
            found["underline"] = LINK_UNDERLINE
            found["tooltip"] = (
                found["tooltip"]
                + TOOLTIP_LINE_GAP
                + LINK_TIP_FORMAT.format(exchange_id=exchange_id, url=url)
            )
            self.calls.append([ROW_SYMBOL_LINK, url])
        return found

    def _fire_button(self, status, state, mode) -> dict:
        """The Manual Fire button: its look, its tooltip and its glow."""
        is_scrumming = mode == MODE_SCRUMMING
        is_active = state in ACTIVE_STATES
        enabled = is_scrumming and is_active
        if enabled:
            path, tip = self._armed_fire(status)
        elif not is_scrumming:
            path, tip = FIRE_PATH_NOT_SCRUMMING, FIRE_TIP_NOT_SCRUMMING
        else:
            path = FIRE_PATH_INACTIVE
            tip = FIRE_TIP_INACTIVE_FORMAT.format(state=state)
        glow = FIRE_GLOWS[path]
        if glow:
            self.glows.append(
                {
                    "color": glow,
                    "blur_radius": GLOW_BLUR_RADIUS,
                    "offset": list(GLOW_OFFSET),
                }
            )
            self.calls.append([FIRE_GLOW, glow])
        self.calls.append([FIRE_BUILT, path, enabled])
        return {
            "text": mask_or(FIRE_LABEL, FIRE_MASK_FIELD),
            "enabled": enabled,
            "height": BUTTON_HEIGHT_PX,
            "focus_policy": FOCUS_POLICY,
            "style_sheet": FIRE_STYLES[path],
            "tooltip": tip,
            "path": path,
            "glow": glow,
            "glow_blur_radius": GLOW_BLUR_RADIUS if glow else 0,
            "glow_offset": list(GLOW_OFFSET),
        }

    def _armed_fire(self, status) -> tuple:
        """The path and the tooltip an enabled Fire button carries."""
        scrum_phase = status.get("scrum_target_mode")
        armed_action = status.get("armed_action")
        ceiling_enabled = status.get("position_ceiling_enabled", False)
        ceiling_ratio = status.get("ceiling_ratio")
        ceiling_usd = status.get("position_ceiling_usd")
        fold_taper = status.get("fold_rate_taper", DEFAULT_FOLD_TAPER)
        detonation_enabled = status.get("detonation_enabled", False)
        detonation_tf = status.get("detonation_timeframe", DEFAULT_DETONATION_TIMEFRAME)
        fold_blocked = (
            ceiling_enabled
            and ceiling_ratio is not None
            and ceiling_ratio >= CEILING_HARD_STOP_RATIO
        )
        risk = self.risk_suffix(
            ceiling_enabled,
            ceiling_ratio,
            ceiling_usd,
            fold_taper,
            fold_blocked,
            detonation_enabled,
            detonation_tf,
        )
        auto_fire = status.get("auto_fire", {}) or {}
        if armed_action == "scrum":
            if bool(auto_fire.get("scrum_armed", False)):
                return FIRE_PATH_SCRUM_SOLID, FIRE_TIP_SCRUM_SOLID + risk
            blockers = list(auto_fire.get("scrum_blockers", []) or [])
            return (
                FIRE_PATH_SCRUM_OUTLINE,
                FIRE_TIP_SCRUM_OUTLINE + blockers_text(blockers) + risk,
            )
        if armed_action == "fold":
            blockers = list(auto_fire.get("fold_blockers", []) or [])
            if fold_blocked:
                return FIRE_PATH_FOLD_CEILING, FIRE_TIP_FOLD_CEILING + risk
            if bool(auto_fire.get("fold_armed", False)):
                return FIRE_PATH_FOLD_SOLID, FIRE_TIP_FOLD_SOLID + risk
            return (
                FIRE_PATH_FOLD_OUTLINE,
                FIRE_TIP_FOLD_OUTLINE + blockers_text(blockers) + risk,
            )
        if scrum_phase == "fire":
            return FIRE_PATH_PHASE_FIRE, FIRE_TIP_PHASE_FIRE + risk
        if scrum_phase == "track":
            return FIRE_PATH_PHASE_TRACK, FIRE_TIP_PHASE_TRACK
        return FIRE_PATH_PHASE_SEARCH, FIRE_TIP_PHASE_SEARCH

    def risk_suffix(
        self,
        ceiling_enabled,
        ceiling_ratio,
        ceiling_usd,
        fold_taper,
        fold_blocked,
        detonation_enabled,
        detonation_tf,
    ) -> str:
        """The lines the Fire tooltip carries about this bot's risk controls."""
        parts = []
        if ceiling_enabled and ceiling_ratio is not None:
            pct = ceiling_ratio * PERCENT_SCALE
            taper_pct = fold_taper * PERCENT_SCALE
            if fold_blocked:
                parts.append(
                    CEILING_REACHED_FORMAT.format(pct=pct, ceiling_usd=ceiling_usd)
                )
            elif ceiling_ratio >= CEILING_APPROACH_RATIO:
                parts.append(
                    CEILING_APPROACH_FORMAT.format(
                        pct=pct, ceiling_usd=ceiling_usd, taper_pct=taper_pct
                    )
                )
            else:
                parts.append(
                    CEILING_NORMAL_FORMAT.format(
                        pct=pct, ceiling_usd=ceiling_usd, taper_pct=taper_pct
                    )
                )
        if detonation_enabled:
            parts.append(DETONATION_FORMAT.format(timeframe=detonation_tf.upper()))
        return EMPTY_TEXT.join(parts)

    def _detail_button(self) -> dict:
        """The Detail button, which is the same on every row."""
        self.calls.append([DETAIL_BUILT])
        return {
            "text": DETAIL_LABEL,
            "enabled": True,
            "height": BUTTON_HEIGHT_PX,
            "style_sheet": DETAIL_STYLE,
            "tooltip": DETAIL_TIP,
        }

    # ----- selection -----

    def get_selected_bot_id(self) -> str:
        """The bot the highlight is on, or nothing when none is highlighted."""
        if not self.has_selection:
            self.calls.append([SELECTION_READ, NO_SELECTION_BOT_ID])
            return NO_SELECTION_BOT_ID
        row = self.current_row
        found = (
            self.bot_ids[row] if 0 <= row < len(self.bot_ids) else NO_SELECTION_BOT_ID
        )
        self.calls.append([SELECTION_READ, found])
        return found

    def select_row(self, row: int) -> None:
        """Put the highlight on one row."""
        self.current_row = row
        self.has_selection = True
        self.calls.append([SELECTION_ROW, row])

    def clear_selection(self) -> None:
        """Take the highlight off every row."""
        self.has_selection = False
        self.calls.append([SELECTION_CLEARED])

    def _row_has_first_cell(self, row: int) -> bool:
        """Whether one row carries a first cell, so the highlight can rest on it."""
        return 0 <= row < len(self.rows) and self.rows[row]["cells"][0] is not None

    def reanchor_selection(self, previous_bot_id: str) -> None:
        """Put the highlight back on the BOT it was on, not on its row."""
        if not previous_bot_id:
            return
        if self.get_selected_bot_id() == previous_bot_id:
            return
        target = None
        for row, bot_id in enumerate(self.bot_ids):
            if bot_id == previous_bot_id:
                target = row
                break
        if target is not None and not self._row_has_first_cell(target):
            target = None
        self.clear_selection()
        if target is None:
            self.current_row = NO_SELECTION_ROW
        else:
            self.select_row(target)
        self.calls.append([SELECTION_ANCHORED, previous_bot_id, target])

    def select_row_for_bot(self, bot_id: str) -> None:
        """Put the highlight on the row whose Detail button was pressed."""
        if not bot_id:
            return
        target = None
        for row, found in enumerate(self.bot_ids):
            if found == bot_id:
                target = row
                break
        if target is None:
            return
        if not self._row_has_first_cell(target):
            return
        self.select_row(target)

    def highlight_bot(self, bot_id: str) -> str:
        """Put the highlight on the bot the Voting Panel draws, and answer it.

        The window calls this when the panel's own dropdown or an arrow
        moved the selection, so it tells nobody back.
        """
        wanted = str(bot_id or "")
        if wanted:
            self.select_row_for_bot(wanted)
        else:
            self.clear_selection()
            self.current_row = NO_SELECTION_ROW
        found = self.get_selected_bot_id()
        self.calls.append([ROW_HIGHLIGHTED, wanted, found])
        return found

    # ----- the five things the operator can press -----

    def on_row_pressed(self, bot_id: str) -> str:
        """Answer a press on one row and report the bot it leaves selected.

        ``selection_after_press`` decides it, so a press on the row already
        shown clears the selection instead of setting it again.
        """
        wanted = selection_after_press(str(bot_id or ""), self.get_selected_bot_id())
        if wanted:
            self.select_row_for_bot(wanted)
        else:
            self.clear_selection()
            self.current_row = NO_SELECTION_ROW
        self.calls.append([ROW_PRESSED, str(bot_id or ""), wanted])
        if self.on_bot_selected:
            self.on_bot_selected(wanted)
        return wanted

    def on_view_scrolled(self, band: Any) -> str:
        """Release the highlight when the rows drawn no longer carry it.

        ``band`` is the first and last drawn row. ``on_bot_selected`` is not
        called, so the Voting Panel keeps the bot it is drawing.
        """
        first, last = band
        if not self.has_selection:
            return NO_SELECTION_BOT_ID
        kept = selection_after_view_moved(self.current_row, first, last)
        self.calls.append([SELECTION_RELEASED, int(first), int(last), kept])
        if kept != NO_SELECTION_ROW:
            return self.get_selected_bot_id()
        self.clear_selection()
        self.current_row = NO_SELECTION_ROW
        return NO_SELECTION_BOT_ID

    def on_detail(self, bot_id: str) -> None:
        """Select the row, then hand the bot to whatever opens the detail."""
        self.select_row_for_bot(bot_id)
        self.detail_clicks.append(bot_id)
        self.calls.append([DETAIL_CLICKED, bot_id])
        if self.on_bot_clicked:
            self.on_bot_clicked(bot_id)

    def on_fire(self, bot_id: str) -> None:
        """Hand the bot to whatever runs Manual Fire."""
        self.fire_clicks.append(bot_id)
        self.calls.append([FIRE_CLICKED, bot_id])
        if self.on_fire_clicked:
            self.on_fire_clicked(bot_id)

    def on_cell_clicked(self, row: int, column: int) -> str:
        """The address a click on one cell asks to be opened, empty for every other cell.

        ``LINK_FIELD_BY_COLUMN`` names the field each column's click reads,
        and ``opening_address`` refuses one that is not https with a host.
        """
        field = LINK_FIELD_BY_COLUMN.get(int(column))
        if field is None:
            self.calls.append([CELL_IGNORED, column])
            return EMPTY_TEXT
        found = self.cell_at(row, column)
        if found is None:
            self.calls.append([CELL_IGNORED, column])
            return EMPTY_TEXT
        held = found.get(field, EMPTY_TEXT)
        if not held:
            self.calls.append([CELL_IGNORED, column])
            return EMPTY_TEXT
        url = opening_address(held)
        if not url:
            self.calls.append([CELL_REFUSED, column, held])
            return EMPTY_TEXT
        self.opened_urls.append(url)
        self.calls.append([CELL_OPENED, url])
        return url


PANE_MODEL: Optional[BotStatusTableModel] = None

PANE_MODELS: Dict[str, BotStatusTableModel] = {}


def pane_model() -> BotStatusTableModel:
    """The one ``BotStatusTableModel`` the bridge keeps between calls.

    ``BotStatusTableModel`` is built on the first call and never at import,
    since ``refresh_header_dots`` reads the privacy register.
    """
    global PANE_MODEL
    if PANE_MODEL is None:
        PANE_MODEL = BotStatusTableModel()
    return PANE_MODEL


RESET_PARAM = "reset"
STATUSES_PARAM = "statuses"
# The Simulator and the Paper forks still send a header press under this name.
HEADER_CLICK_PARAM = "header_click"
PRIVACY_TOGGLE_PARAM = "privacy_toggle"
SORT_COLUMN_PARAM = "sort_column"
CELL_CLICK_PARAM = "cell_click"
# The three request names below differ from the row keys ``fire``, ``detail``
# and ``exchange_id`` the payload already carries.
FIRE_PARAM = "fire_bot"
DETAIL_PARAM = "detail_bot"
SELECT_BOT_PARAM = "select_bot"
VIEW_BAND_PARAM = "view_band"
EXCHANGE_ID_PARAM = "for_exchange"


def pane_model_for(exchange_id: str) -> BotStatusTableModel:
    """The table ``PANE_MODELS`` keeps for one exchange.

    One ``BotStatusTableModel`` per exchange id, so two screens on the
    same page do not share rows or a highlight.
    """
    held = PANE_MODELS.get(exchange_id)
    if held is None:
        held = BotStatusTableModel()
        PANE_MODELS[exchange_id] = held
    held.exchange_id = exchange_id
    return held


def build_model(statuses: Optional[list] = None) -> BotStatusTableModel:
    """One model driven from a list of bot statuses."""
    model = BotStatusTableModel()
    if statuses is not None:
        model.update_bots(statuses)
    return model


def build_view_model(model: BotStatusTableModel) -> dict:
    """Return the whole surface state as one serialisable dict."""
    return {
        "method": METHOD,
        "accessible_name": ACCESSIBLE_NAME,
        "columns": list(COLUMN_LABELS),
        "column_count": COLUMN_COUNT,
        "column_tooltips": dict(COLUMN_TOOLTIPS),
        "fixed_widths": dict(FIXED_WIDTHS),
        "privacy_field_by_col": dict(PRIVACY_FIELD_BY_COL),
        "state_colors": dict(STATE_COLORS),
        "default_state_color": DEFAULT_STATE_COLOR,
        "revealed_glyph": REVEALED_GLYPH,
        "masked_glyph": MASKED_GLYPH,
        "state_masked": STATE_MASKED,
        "state_revealed": STATE_REVEALED,
        "headers": [dict(found) for found in model.headers],
        "rows": [
            {
                "bot_id": (
                    model.bot_ids[index]
                    if index < len(model.bot_ids)
                    else NO_SELECTION_BOT_ID
                ),
                "skipped": index in model.skipped_rows,
                "cells": [
                    dict(found) if found is not None else None for found in row["cells"]
                ],
                "fire": dict(row["fire"]) if row["fire"] else None,
                "detail": dict(row["detail"]) if row["detail"] else None,
            }
            for index, row in enumerate(model.rows)
        ],
        "row_count": len(model.rows),
        "skipped_rows": list(model.skipped_rows),
        "bot_ids": list(model.bot_ids),
        "selected_bot_id": (
            model.bot_ids[model.current_row]
            if model.has_selection and 0 <= model.current_row < len(model.bot_ids)
            else NO_SELECTION_BOT_ID
        ),
        "current_row": model.current_row,
        "has_selection": model.has_selection,
        "alignment": ALIGNMENT,
        "alignment_value": ALIGNMENT_VALUE,
        "fire_column": FIRE_COLUMN,
        "detail_column": DETAIL_COLUMN,
        "button_columns": list(BUTTON_COLUMNS),
        "bot_id_column": BOT_ID_COLUMN,
        "symbol_column": SYMBOL_COLUMN,
        "position_value_column": POSITION_VALUE_COLUMN,
        "position_blank_text": POSITION_BLANK_TEXT,
        "position_paths": list(POSITION_PATHS),
        "target_btc_column": TARGET_BTC_COLUMN,
        "target_eth_column": TARGET_ETH_COLUMN,
        "ammo_column": AMMO_COLUMN,
        "fire_paths": list(FIRE_PATHS),
        "fire_styles": dict(FIRE_STYLES),
        "fire_glows": dict(FIRE_GLOWS),
        "fire_label": FIRE_LABEL,
        "fire_mask_field": FIRE_MASK_FIELD,
        "detail_label": DETAIL_LABEL,
        "detail_style": DETAIL_STYLE,
        "detail_tooltip": DETAIL_TIP,
        "button_height": BUTTON_HEIGHT_PX,
        "focus_policy": FOCUS_POLICY,
        "glow_blur_radius": GLOW_BLUR_RADIUS,
        "glow_offset": list(GLOW_OFFSET),
        "glows": [dict(found) for found in model.glows],
        "icon_size": ICON_ASSET_SIZE_PX,
        "icon_download": ICON_DOWNLOAD,
        "logo_size": LOGO_SIZE_PX,
        "row_height": ROW_HEIGHT_PX,
        "link_color": LINK_COLOR,
        "link_underline": LINK_UNDERLINE,
        "link_field_by_column": {
            str(column): field for column, field in LINK_FIELD_BY_COLUMN.items()
        },
        "opening_schemes": list(OPENING_SCHEMES),
        "browser_new_window": BROWSER_NEW_WINDOW,
        "opened_urls": list(model.opened_urls),
        "detail_clicks": list(model.detail_clicks),
        "fire_clicks": list(model.fire_clicks),
        "mode_scrumming": MODE_SCRUMMING,
        "active_states": list(ACTIVE_STATES),
        "unknown_state_text": UNKNOWN_STATE_TEXT,
        "no_target_text": NO_TARGET_TEXT,
        "skip_bot_id_length": SKIP_BOT_ID_LENGTH,
        "skip_bot_id_missing": SKIP_BOT_ID_MISSING,
        "ceiling_hard_stop_ratio": CEILING_HARD_STOP_RATIO,
        "ceiling_approach_ratio": CEILING_APPROACH_RATIO,
        "percent_scale": PERCENT_SCALE,
        "default_fold_taper": DEFAULT_FOLD_TAPER,
        "default_detonation_timeframe": DEFAULT_DETONATION_TIMEFRAME,
        "default_quote_to_usd": DEFAULT_QUOTE_TO_USD,
        "fire_tooltips": {
            FIRE_PATH_SCRUM_SOLID: FIRE_TIP_SCRUM_SOLID,
            FIRE_PATH_SCRUM_OUTLINE: FIRE_TIP_SCRUM_OUTLINE,
            FIRE_PATH_FOLD_CEILING: FIRE_TIP_FOLD_CEILING,
            FIRE_PATH_FOLD_SOLID: FIRE_TIP_FOLD_SOLID,
            FIRE_PATH_FOLD_OUTLINE: FIRE_TIP_FOLD_OUTLINE,
            FIRE_PATH_PHASE_FIRE: FIRE_TIP_PHASE_FIRE,
            FIRE_PATH_PHASE_TRACK: FIRE_TIP_PHASE_TRACK,
            FIRE_PATH_PHASE_SEARCH: FIRE_TIP_PHASE_SEARCH,
            FIRE_PATH_NOT_SCRUMMING: FIRE_TIP_NOT_SCRUMMING,
        },
        "fire_inactive_tooltip_format": FIRE_TIP_INACTIVE_FORMAT,
        "header_state_tip_format": HEADER_STATE_TIP_FORMAT,
        "header_dot_tip_format": HEADER_DOT_TIP_FORMAT,
        "header_dot_action_mask": HEADER_DOT_ACTION_MASK,
        "header_dot_action_reveal": HEADER_DOT_ACTION_REVEAL,
        "header_label_wrap": HEADER_LABEL_WRAP,
        "header_label_font_px": HEADER_LABEL_FONT_PX,
        "header_label_min_font_px": HEADER_LABEL_MIN_FONT_PX,
        "header_label_style": HEADER_LABEL_STYLE,
        "header_dot_font_px": HEADER_DOT_FONT_PX,
        "header_dot_row_px": HEADER_DOT_ROW_PX,
        "header_dot_style": HEADER_DOT_STYLE,
        "header_cell_pad_px": HEADER_CELL_PAD_PX,
        "header_cell_gap_px": HEADER_CELL_GAP_PX,
        "mode_tip_format": MODE_TIP_FORMAT,
        "link_tip_format": LINK_TIP_FORMAT,
        "blockers_tip_format": BLOCKERS_TIP_FORMAT,
        "blockers_separator": BLOCKERS_SEPARATOR,
        "ceiling_reached_format": CEILING_REACHED_FORMAT,
        "ceiling_approach_format": CEILING_APPROACH_FORMAT,
        "ceiling_normal_format": CEILING_NORMAL_FORMAT,
        "detonation_format": DETONATION_FORMAT,
        "skip_log_format": SKIP_LOG_FORMAT,
        "row_refused_log": ROW_REFUSED_LOG,
        "chart_url_skipped_log": CHART_URL_SKIPPED_LOG,
        "chart_open_failed_log": CHART_OPEN_FAILED_LOG,
        "fire_style_head": FIRE_STYLE_HEAD,
        "no_glow": NO_GLOW,
        "no_blockers_text": NO_BLOCKERS_TEXT,
        "empty_text": EMPTY_TEXT,
        "symbol_separator": SYMBOL_SEPARATOR,
        "quote_btc": QUOTE_BTC,
        "quote_eth": QUOTE_ETH,
        "no_selection_row": NO_SELECTION_ROW,
        "no_selection_bot_id": NO_SELECTION_BOT_ID,
        "no_target_value": NO_TARGET_VALUE,
        "no_price": NO_PRICE,
        "no_holdings": NO_HOLDINGS,
        "no_trades": NO_TRADES,
        "sorting_enabled": SORTING_ENABLED,
        "sortable_columns": list(SORTABLE_COLUMNS),
        "sort_kind_by_col": dict(SORT_KIND_BY_COL),
        "sort_column": model.sort_column,
        "sort_descending": model.sort_descending,
        "no_sort_column": NO_SORT_COLUMN,
        "sort_ascending": SORT_ASCENDING,
        "sort_descending_word": SORT_DESCENDING,
        "sort_unsorted": SORT_UNSORTED,
        "sort_mark_ascending": SORT_MARK_ASCENDING,
        "sort_mark_descending": SORT_MARK_DESCENDING,
        "sort_mark_none": SORT_MARK_NONE,
        "sort_column_param": SORT_COLUMN_PARAM,
        "header_sort_mark_style": HEADER_SORT_MARK_STYLE,
        "header_sort_mark_box_px": HEADER_SORT_MARK_BOX_PX,
        "selection_behavior": SELECTION_BEHAVIOR,
        "edit_triggers": EDIT_TRIGGERS,
        "alternating_row_colors": ALTERNATING_ROW_COLORS,
        "vertical_header_visible": VERTICAL_HEADER_VISIBLE,
        "header_resize_mode": HEADER_RESIZE_MODE,
        "fixed_resize_mode": FIXED_RESIZE_MODE,
        "skin": dict(SKIN),
        "style_sheet": STYLE_SHEET,
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "actions": dict(ACTIONS),
        "exchange_id": model.exchange_id,
        "reset_param": RESET_PARAM,
        "statuses_param": STATUSES_PARAM,
        "exchange_id_param": EXCHANGE_ID_PARAM,
        "header_click_param": HEADER_CLICK_PARAM,
        "privacy_toggle_param": PRIVACY_TOGGLE_PARAM,
        "cell_click_param": CELL_CLICK_PARAM,
        "fire_param": FIRE_PARAM,
        "detail_param": DETAIL_PARAM,
        "select_bot_param": SELECT_BOT_PARAM,
        "view_band_param": VIEW_BAND_PARAM,
        "logger_name": LOGGER_NAME,
        "skip_logger_name": SKIP_LOGGER_NAME,
        "calls": [list(call) for call in model.calls],
    }


def drive(model: BotStatusTableModel, params: dict) -> dict:
    """Apply one request to ``model``, reading each ``*_PARAM`` field.

    ``view_model`` and ``live_view_model`` both run their request here.
    """
    statuses = params.get(STATUSES_PARAM)
    if statuses is not None:
        model.update_bots(statuses)
    if params.get(PRIVACY_TOGGLE_PARAM) is not None:
        model.on_privacy_toggled(params[PRIVACY_TOGGLE_PARAM])
    if params.get(SORT_COLUMN_PARAM) is not None:
        model.on_header_sorted(int(params[SORT_COLUMN_PARAM]))
    if params.get(CELL_CLICK_PARAM) is not None:
        row, column = params[CELL_CLICK_PARAM]
        model.on_cell_clicked(row, column)
    if params.get(FIRE_PARAM) is not None:
        model.on_fire(params[FIRE_PARAM])
    if params.get(DETAIL_PARAM) is not None:
        model.on_detail(params[DETAIL_PARAM])
    if params.get(SELECT_BOT_PARAM) is not None:
        model.on_row_pressed(str(params[SELECT_BOT_PARAM]))
    if params.get(VIEW_BAND_PARAM) is not None:
        model.on_view_scrolled(params[VIEW_BAND_PARAM])
    return build_view_model(model)


def view_model(params: dict) -> dict:
    """Bridge handler for ``bot_status_table.state``.

    Reads each request field a ``*_PARAM`` constant names. The table keeps
    its rows and its highlight between calls because the shipped table
    does; ``RESET_PARAM`` is what a fresh paint sends.
    """
    global PANE_MODEL
    if params.get(RESET_PARAM, False):
        PANE_MODEL = BotStatusTableModel()
    held = pane_model()
    held.exchange_id = str(params.get(EXCHANGE_ID_PARAM) or "")
    return drive(held, params)


def scrumming_statuses(statuses: Any) -> list:
    """The records of ``statuses`` whose mode is ``MODE_SCRUMMING``.

    ``update_bots`` skips and logs any other mode, so the Scrumming table
    is only ever handed the bots that belong in it.
    """
    return [
        found
        for found in statuses or []
        if isinstance(found, dict) and found.get("mode") == MODE_SCRUMMING
    ]


def live_view_model(params: dict, live: Any) -> dict:
    """Build the table ``EXCHANGE_ID_PARAM`` names from the running fleet.

    ``live.bot_manager.list_bots_by_exchange`` names the bots, filtered to
    ``MODE_SCRUMMING``; ``view_model`` answers while no manager is bound.
    """
    manager = getattr(live, "bot_manager", None)
    if manager is None or not hasattr(manager, "list_bots_by_exchange"):
        return view_model(params)
    asked = dict(params or {})
    exchange_id = str(asked.get(EXCHANGE_ID_PARAM) or "")
    if asked.pop(RESET_PARAM, False):
        PANE_MODELS.pop(exchange_id, None)
    if asked.get(STATUSES_PARAM) is None:
        asked[STATUSES_PARAM] = scrumming_statuses(
            manager.list_bots_by_exchange(exchange_id)
        )
    return drive(pane_model_for(exchange_id), asked)


def bind_live(live: Any) -> Any:
    """Return a ``bot_status_table.state`` handler reading ``live``.

    ``build_registry`` calls this when the running program serves the bridge.
    """

    def handler(params: dict) -> dict:
        return live_view_model(params or {}, live)

    return handler
