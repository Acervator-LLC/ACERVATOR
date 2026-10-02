"""extractor_bot_table_surface.py -- the Extractor bot dashboard table.

Describes the eight-column table the dashboard paints for the Extractor
fleet. Four things leave this surface. The column values name the header
labels, their tooltips and the two fixed widths. ``row_values`` composes
one row from one fleet status: six text cells, the colour and tooltip the
Mode and Liquid cells carry, and the two buttons.
``ExtractorBotTableModel`` holds the whole table and the highlight that
follows a bot rather than a row. ``view_model`` answers one request.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``extractor_bot_table.state`` method, which is how the Electron
renderer reaches it. Nothing here imports Qt.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from .. import design_system as ds
from ..color_alpha import coin_disc_color

METHOD = "extractor_bot_table.state"

LOGGER_NAME = "acervator.gui"

ACCESSIBLE_NAME = ""

TABLE_KIND = "ExtractorBotTable"
BASE_KIND = "ColumnarTableWidget"
BUTTON_KIND = "QPushButton"

COL_BOT_ID = 0
COL_SYMBOL = 1
COL_MODE = 2
COL_TRADES = 3
COL_POOL = 4
COL_LIQUID = 5
COL_FIRE = 6
COL_DETAIL = 7

COLUMN_LABELS = (
    "Bot ID",
    "Symbol",
    "Mode",
    "Trades",
    "Pool",
    "Liquid",
    "Fire",
    "",
)

COLUMN_TOOLTIPS = {
    0: "Unique identifier for this Extractor instance",
    1: "Base currency this Extractor accumulates",
    2: (
        "Trading mode + current state.\n"
        "Green = RUNNING · Amber = PAUSED · Gray = IDLE/STOPPED\n"
        "Red = ERROR · Orange = COOLDOWN · Cyan = STARTING"
    ),
    3: "Total number of executed trades across all positions",
    4: (
        "Pool — operator-set chunk size in USD (the budget "
        "this Extractor owns and rotates through positions). "
        "Live-edit in the bot's Settings tab → Extractor → "
        "Pool size (USD)."
    ),
    5: (
        "Liquid — USD-equivalent of the base-currency units "
        "currently NOT deployed to any open position. As "
        "positions close back to base, Liquid grows. Pool "
        "minus Liquid is the currently-deployed amount.\n"
        "Color: green = pool fully in base (no open "
        "positions), yellow = positions open, none in "
        "drawdown, red = at least one position in drawdown."
    ),
    6: (
        "Manual Fire is per-position for Extractors. "
        "Use the Detail dialog's Positions Held tab."
    ),
    7: "Click for full bot detail and status explanation",
}

COLUMN_FIXED_WIDTHS = {
    COL_FIRE: ds.TABLE_COL_FIRE_W,
    COL_DETAIL: ds.TABLE_COL_DETAIL_W,
}

COLUMN_COUNT = len(COLUMN_LABELS)
BUTTON_COLUMNS = (COL_FIRE, COL_DETAIL)
TEXT_COLUMNS = tuple(
    index for index in range(COLUMN_COUNT) if index not in BUTTON_COLUMNS
)
ICON_COLUMN = COL_SYMBOL
COLOURED_COLUMNS = (COL_MODE, COL_LIQUID)
STRETCH_COLUMNS = tuple(
    index for index in range(COLUMN_COUNT) if index not in COLUMN_FIXED_WIDTHS
)

ITEMS_PER_SELECTED_ROW = COLUMN_COUNT - len(BUTTON_COLUMNS)

SHORT_HEX_LENGTH = 4
HEX_MARK = "#"


def long_hex(colour: str) -> str:
    """One colour as six hex digits, whatever width the token is written in.

    A three-digit token names the same colour with each digit doubled,
    and that is the width the screen reports, so both sides of a colour
    comparison read one spelling.
    """
    if len(colour) == SHORT_HEX_LENGTH and colour.startswith(HEX_MARK):
        return HEX_MARK + "".join(digit * 2 for digit in colour[1:])
    return colour


STATE_COLORS = {
    "running": long_hex(ds.SUCCESS),
    "idle": long_hex(ds.CARD_METRIC_LABEL),
    "paused": long_hex(ds.WARNING),
    "error": long_hex(ds.ERROR),
    "cooldown": long_hex(ds.WARNING_STRONG),
    "stopped": long_hex(ds.TEXT_MUTED),
    "starting": long_hex(ds.STATE_STARTING),
}

POOL_COLORS = {
    "green": long_hex(ds.SUCCESS),
    "yellow": long_hex(ds.WARNING),
    "red": long_hex(ds.ERROR),
}

STATE_FALLBACK_COLOR = long_hex(ds.TEXT_HIGH)
POOL_FALLBACK_COLOR = long_hex(ds.TEXT_MED)

UNSET_COLOR = "#000000"
UNSET_BRUSH = "NoBrush"
SET_BRUSH = "SolidPattern"

ALIGNMENT = "AlignCenter"
ALIGNMENT_VALUE = 132

MODE_TEXT = "extractor"
UNKNOWN_STATE_TEXT = "UNKNOWN"
NO_VALUE_TEXT = "---"
EMPTY_TIP = ""
DEFAULT_POOL_COLOR_NAME = "green"

POOL_TEXT_FORMAT = "${amount:,.2f}"

MODE_TIP_FORMAT = (
    "Mode: extractor (Base Currency Extractor Multi-Target)\n"
    "State: {state}\n"
    "Accumulates base-currency units via top-N pair scanning."
)

LIQUID_TIP_FORMAT = (
    "Extractor pool: {pool_color_name}\n"
    "  • {n_positions} position(s) open\n"
    "  • {n_drawdown} in drawdown\n"
    "  • {base_currency} base currency\n"
    "  • {chunk_free_base:.8f} {base_currency} free ({free_usd:.2f} USD)\n"
    "  • {deployed_base:.8f} {base_currency} deployed ({deployed_usd:.2f} USD)"
)

FIRE_LABEL = "Fire"
DETAIL_LABEL = "Detail"
BUTTON_HEIGHT = 22
FIRE_ENABLED = False
DETAIL_ENABLED = True
FIRE_FOCUS_POLICY = "NoFocus"
DETAIL_FOCUS_POLICY = "StrongFocus"
FIRE_STYLE_SHEET = f"font-size: 10px; padding: 1px 6px; color: {ds.TEXT_PLACEHOLDER};"
DETAIL_STYLE_SHEET = "font-size: 10px; padding: 1px 6px;"
FIRE_TOOLTIP = (
    "Manual Fire is per-position for Extractor bots. "
    "Use the Detail dialog's Positions Held tab."
)
DETAIL_TOOLTIP = "View full bot status, configuration, and error details"

TABLE_STYLE_SHEET = ""
SKIN: dict[str, str] = {}
TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()

ACTIONS = {"detail.clicked": "_on_detail"}
BRIDGE_ACTIONS = ("update_bots", "detail", "select_row")

STATUS_KEYS = (
    "bot_id",
    "state",
    "chunk_size_usd",
    "chunk_free_base",
    "chunk_size_base",
    "n_positions_open",
    "n_positions_drawdown",
    "pool_color",
    "base_currency",
    "symbol",
    "stats",
)
TRADES_KEY = "total_trades"

MISSING_TEXT = ""
MISSING_AMOUNT = 0.0
MISSING_COUNT = 0
NO_DEPLOYMENT = 0.0
UNSET_ITEM_TYPE = 0

NO_ROW = -1
NO_BOT = ""
FIRST_COLUMN = 0

SELECT_PATH_NONE = "none"
SELECT_PATH_KEPT = "kept"
SELECT_PATH_MOVED = "moved"
SELECT_PATH_CLEARED = "cleared"
SELECT_PATHS = (
    SELECT_PATH_NONE,
    SELECT_PATH_KEPT,
    SELECT_PATH_MOVED,
    SELECT_PATH_CLEARED,
)

DETAIL_PATH_BLANK = "blank"
DETAIL_PATH_ABSENT = "absent"
DETAIL_PATH_SELECTED = "selected"
DETAIL_PATHS = (DETAIL_PATH_BLANK, DETAIL_PATH_ABSENT, DETAIL_PATH_SELECTED)

UPDATE_START = "update.start"
UPDATE_ROW = "update.row"
UPDATE_REANCHOR = "update.reanchor"
UPDATE_RETURN = "update.return"
DETAIL_START = "detail.start"
DETAIL_SELECT = "detail.select"
DETAIL_CALLBACK = "detail.callback"
DETAIL_RETURN = "detail.return"

ModelCall = list[object]


def cell_text(value: Any) -> str:
    """The text one table cell shows for `value`.

    A cell built from anything but a string shows nothing: the widget's
    other constructor reads a number as an item type, not as a text.
    """
    return value if isinstance(value, str) else MISSING_TEXT


def cell_type(value: Any) -> int:
    """The item type number one table cell carries for `value`.

    A string leaves the type at zero. A number becomes the type, which
    is where a number written into a text column survives.
    """
    if isinstance(value, str) or value is None:
        return UNSET_ITEM_TYPE
    return int(value)


def icon_shown(value: Any) -> bool:
    """Whether the Symbol cell carries a coin icon for `value`.

    The icon is drawn from the characters of the name, so a value that
    is not a non-empty string leaves the cell without one.
    """
    return isinstance(value, str) and bool(value)


def state_color(state: Any) -> str:
    """The colour the Mode cell is drawn in for one bot state."""
    return STATE_COLORS.get(state, STATE_FALLBACK_COLOR)


def pool_color(pool_color_name: Any) -> str:
    """The colour the Liquid cell is drawn in for one pool colour name."""
    return POOL_COLORS.get(pool_color_name, POOL_FALLBACK_COLOR)


def pool_amount_text(amount: float, chunk_size_usd: float) -> str:
    """One dollar figure, or the dashes a table with no pool shows."""
    if chunk_size_usd > 0:
        return POOL_TEXT_FORMAT.format(amount=amount)
    return NO_VALUE_TEXT


def deployment_split(
    chunk_size_usd: float, chunk_free_base: float, chunk_size_base: float
) -> tuple[float, float, float]:
    """Base units deployed, and the dollar value of free and deployed.

    Prices the undeployed base units at the pool's own dollar-per-base
    ratio, so Liquid reads in the same units as Pool. A pool with no
    base size has nothing to price and reports zeroes.
    """
    if chunk_size_base > 0:
        deployed_base = max(chunk_size_base - chunk_free_base, NO_DEPLOYMENT)
        usd_per_base = chunk_size_usd / chunk_size_base
        return (
            deployed_base,
            chunk_free_base * usd_per_base,
            deployed_base * usd_per_base,
        )
    return NO_DEPLOYMENT, NO_DEPLOYMENT, NO_DEPLOYMENT


def mode_tooltip(state: Any) -> str:
    """The Mode cell tooltip, naming the state in capitals."""
    return MODE_TIP_FORMAT.format(state=state.upper() if state else UNKNOWN_STATE_TEXT)


def liquid_tooltip(
    pool_color_name: Any,
    n_positions: int,
    n_drawdown: int,
    base_currency: Any,
    chunk_free_base: float,
    free_usd: float,
    deployed_base: float,
    deployed_usd: float,
) -> str:
    """The Liquid cell tooltip: the pool colour and what it is made of."""
    return LIQUID_TIP_FORMAT.format(
        pool_color_name=pool_color_name.upper(),
        n_positions=n_positions,
        n_drawdown=n_drawdown,
        base_currency=base_currency,
        chunk_free_base=chunk_free_base,
        free_usd=free_usd,
        deployed_base=deployed_base,
        deployed_usd=deployed_usd,
    )


def buttons() -> dict:
    """The two buttons every row carries, keyed by column."""
    return {
        str(COL_FIRE): {
            "kind": BUTTON_KIND,
            "text": FIRE_LABEL,
            "enabled": FIRE_ENABLED,
            "height": BUTTON_HEIGHT,
            "style_sheet": FIRE_STYLE_SHEET,
            "tooltip": FIRE_TOOLTIP,
            "focus_policy": FIRE_FOCUS_POLICY,
            "action": MISSING_TEXT,
        },
        str(COL_DETAIL): {
            "kind": BUTTON_KIND,
            "text": DETAIL_LABEL,
            "enabled": DETAIL_ENABLED,
            "height": BUTTON_HEIGHT,
            "style_sheet": DETAIL_STYLE_SHEET,
            "tooltip": DETAIL_TOOLTIP,
            "focus_policy": DETAIL_FOCUS_POLICY,
            "action": ACTIONS["detail.clicked"],
        },
    }


def row_values(status: dict) -> dict:
    """One table row composed from one fleet status.

    Reads the status in the order the dashboard reads it, so a status
    carrying a value of the wrong kind refuses at the same step and
    leaves the same rows already written.
    """
    state = status.get("state", MISSING_TEXT)
    chunk_size_usd = float(
        status.get("chunk_size_usd", MISSING_AMOUNT) or MISSING_AMOUNT
    )
    chunk_free_base = float(
        status.get("chunk_free_base", MISSING_AMOUNT) or MISSING_AMOUNT
    )
    chunk_size_base = float(
        status.get("chunk_size_base", MISSING_AMOUNT) or MISSING_AMOUNT
    )
    n_positions = int(status.get("n_positions_open", MISSING_COUNT) or MISSING_COUNT)
    n_drawdown = int(status.get("n_positions_drawdown", MISSING_COUNT) or MISSING_COUNT)
    pool_color_name = status.get("pool_color", DEFAULT_POOL_COLOR_NAME)
    base_currency = status.get("base_currency", MISSING_TEXT)

    deployed_base, free_usd, deployed_usd = deployment_split(
        chunk_size_usd, chunk_free_base, chunk_size_base
    )
    liquid_color = pool_color(pool_color_name)
    liquid_tip = liquid_tooltip(
        pool_color_name,
        n_positions,
        n_drawdown,
        base_currency,
        chunk_free_base,
        free_usd,
        deployed_base,
        deployed_usd,
    )

    values = [
        status.get("bot_id", MISSING_TEXT),
        base_currency or status.get("symbol", MISSING_TEXT),
        MODE_TEXT,
        str(status.get("stats", {}).get(TRADES_KEY, MISSING_COUNT)),
        pool_amount_text(chunk_size_usd, chunk_size_usd),
        pool_amount_text(free_usd, chunk_size_usd),
        MISSING_TEXT,
        MISSING_TEXT,
    ]

    texts: list = []
    types: list = []
    colors: list = []
    brushes: list = []
    tooltips: list = []
    icons: list = []
    icon_colors: list = []
    icon_letters: list = []
    for column in range(COLUMN_COUNT):
        if column in BUTTON_COLUMNS:
            texts.append(MISSING_TEXT)
            types.append(UNSET_ITEM_TYPE)
            colors.append(UNSET_COLOR)
            brushes.append(UNSET_BRUSH)
            tooltips.append(EMPTY_TIP)
            icons.append(False)
            icon_colors.append(EMPTY_TIP)
            icon_letters.append(EMPTY_TIP)
            continue
        value = values[column]
        texts.append(cell_text(value))
        types.append(cell_type(value))
        shown = column == ICON_COLUMN and icon_shown(value)
        icons.append(shown)
        icon_colors.append(coin_disc_color(value) if shown else EMPTY_TIP)
        icon_letters.append(str(value)[:1] if shown else EMPTY_TIP)
        if column == COL_MODE:
            colors.append(state_color(state))
            brushes.append(SET_BRUSH)
            tooltips.append(mode_tooltip(state))
        elif column == COL_LIQUID:
            colors.append(liquid_color)
            brushes.append(SET_BRUSH)
            tooltips.append(liquid_tip)
        else:
            colors.append(UNSET_COLOR)
            brushes.append(UNSET_BRUSH)
            tooltips.append(EMPTY_TIP)

    return {
        "bot_id": status.get("bot_id", MISSING_TEXT),
        "values": values,
        "texts": texts,
        "types": types,
        "alignments": [ALIGNMENT_VALUE] * COLUMN_COUNT,
        "colors": colors,
        "brushes": brushes,
        "tooltips": tooltips,
        "icons": icons,
        "icon_colors": icon_colors,
        "icon_letters": icon_letters,
        "buttons": buttons(),
        "state": state,
        "pool_color_name": pool_color_name,
        "chunk_size_usd": chunk_size_usd,
        "chunk_free_base": chunk_free_base,
        "chunk_size_base": chunk_size_base,
        "deployed_base": deployed_base,
        "free_usd": free_usd,
        "deployed_usd": deployed_usd,
        "n_positions": n_positions,
        "n_drawdown": n_drawdown,
    }


class ExtractorBotTableModel:
    """The Extractor table: its rows, its buttons and its highlight.

    ``update_bots`` rewrites every row from a fleet snapshot and puts the
    highlight back on the bot it was on. ``_on_detail`` runs the row's
    Detail button. ``get_selected_bot_id`` answers which bot is under the
    highlight. Every step is appended to ``calls`` in the order the
    dashboard makes it, so a caller can replay the same sequence on a
    table it owns.
    """

    def __init__(
        self,
        on_bot_clicked: Optional[Callable[[str], Any]] = None,
        parent: Any = None,
    ) -> None:
        self._on_bot_clicked = on_bot_clicked
        self._bot_ids: list = []
        self.exchange_id = ""
        self.parent = parent
        self.rows: list = []
        self.row_count = 0
        self.current_row = NO_ROW
        self.selected_row = NO_ROW
        self.select_path = SELECT_PATH_NONE
        self.detail_path = MISSING_TEXT
        self.detail_calls: list = []
        self.calls: list[ModelCall] = []

    @property
    def bot_ids(self) -> list:
        """The row-to-bot map the last rewrite built."""
        return list(self._bot_ids)

    @property
    def built_row_count(self) -> int:
        """How many rows carry cells. A row a refusal skipped carries none."""
        return sum(1 for row in self.rows if row is not None)

    @property
    def selected_item_count(self) -> int:
        """How many cells the highlight covers.

        A button carries no cell, and a row a refusal skipped carries
        none at all, so a highlight on one covers nothing.
        """
        return ITEMS_PER_SELECTED_ROW if self._row_has_cell(self.selected_row) else 0

    def _set_row_count(self, count: int) -> None:
        """Resize the table, dropping a highlight the resize removed.

        A removed row takes the highlight with it and leaves the cursor
        on the last row that survives.
        """
        if self.selected_row >= count:
            self.selected_row = NO_ROW
        if self.current_row >= count:
            self.current_row = count - 1
        self.row_count = count

    def _resized_rows(self, count: int) -> list:
        """The row list at `count` rows, each surviving row still as it was.

        A resize drops the rows past the end and leaves the rest holding
        what they last showed, so a rewrite that refuses part way through
        leaves the earlier paint on screen.
        """
        kept = self.rows
        return [kept[row] if row < len(kept) else None for row in range(count)]

    def _row_has_cell(self, row: int) -> bool:
        """Whether `row` carries a first-column cell to highlight."""
        return 0 <= row < len(self.rows) and self.rows[row] is not None

    def _row_of_bot(self, bot_id: str) -> Optional[int]:
        """The row `bot_id` sits on, or None when it left the fleet."""
        for row, found in enumerate(self._bot_ids):
            if found == bot_id:
                return row
        return None

    def update_bots(self, bot_statuses: list) -> None:
        """Rewrite every row from a fleet snapshot.

        Reads the bot under the highlight before the rewrite, because a
        row index means nothing once the rows have moved, and puts the
        highlight back on that bot at the end.
        """
        selected_before = self.get_selected_bot_id()
        self.calls.append([UPDATE_START, selected_before])
        self._set_row_count(len(bot_statuses))
        self._bot_ids = []
        self.rows = self._resized_rows(self.row_count)
        for row, status in enumerate(bot_statuses):
            self._bot_ids.append(status.get("bot_id", MISSING_TEXT))
            built = row_values(status)
            self.rows[row] = built
            self.calls.append([UPDATE_ROW, row, built["texts"][COL_BOT_ID]])
        self._reanchor(selected_before)
        self.calls.append([UPDATE_RETURN, self.select_path, self.built_row_count])

    def _reanchor(self, previous_bot_id: str) -> None:
        """Put the highlight back on the bot it was on, not on its row."""
        if not previous_bot_id:
            self.select_path = SELECT_PATH_NONE
            self.calls.append([UPDATE_REANCHOR, SELECT_PATH_NONE, NO_ROW])
            return
        if self.get_selected_bot_id() == previous_bot_id:
            self.select_path = SELECT_PATH_KEPT
            self.calls.append([UPDATE_REANCHOR, SELECT_PATH_KEPT, self.current_row])
            return
        target = self._row_of_bot(previous_bot_id)
        if target is not None and not self._row_has_cell(target):
            target = None
        self.selected_row = NO_ROW
        if target is None:
            self.current_row = NO_ROW
            self.select_path = SELECT_PATH_CLEARED
            self.calls.append([UPDATE_REANCHOR, SELECT_PATH_CLEARED, NO_ROW])
            return
        self.current_row = target
        self.selected_row = target
        self.select_path = SELECT_PATH_MOVED
        self.calls.append([UPDATE_REANCHOR, SELECT_PATH_MOVED, target])

    def _select_row_for_bot(self, bot_id: str) -> str:
        """Put the highlight on the row whose Detail button was pressed."""
        if not bot_id:
            return DETAIL_PATH_BLANK
        target = self._row_of_bot(bot_id)
        if target is None or not self._row_has_cell(target):
            return DETAIL_PATH_ABSENT
        self.current_row = target
        self.selected_row = target
        return DETAIL_PATH_SELECTED

    def _on_detail(self, bot_id: str) -> None:
        """Run one row's Detail button: select the row, then tell the tab.

        The highlight moves first, because a click on a button inside a
        cell moves no row selection of its own and the tab reads the
        selection to decide which bot a later command belongs to.
        """
        self.calls.append([DETAIL_START, bot_id])
        self.detail_path = self._select_row_for_bot(bot_id)
        self.calls.append([DETAIL_SELECT, self.detail_path, self.current_row])
        if self._on_bot_clicked:
            self.detail_calls.append(bot_id)
            self._on_bot_clicked(bot_id)
            self.calls.append([DETAIL_CALLBACK, bot_id])
        self.calls.append([DETAIL_RETURN, self.detail_path, self.get_selected_bot_id()])

    def get_selected_bot_id(self) -> str:
        """The bot under the highlight, or nothing when none is on."""
        if not self.selected_item_count:
            return NO_BOT
        row = self.current_row
        if 0 <= row < len(self._bot_ids):
            return self._bot_ids[row]
        return NO_BOT


PANE_MODEL = ExtractorBotTableModel()

PANE_MODELS: Dict[str, ExtractorBotTableModel] = {}

RESET_PARAM = "reset"
ACTION_PARAM = "action"
BOT_STATUSES_PARAM = "bot_statuses"
BOT_ID_PARAM = "bot_id"
# The request names its exchange under a field no payload key already spells.
EXCHANGE_ID_PARAM = "for_exchange"

UPDATE_ACTION, DETAIL_ACTION, SELECT_ACTION = BRIDGE_ACTIONS


def pane_model_for(exchange_id: str) -> ExtractorBotTableModel:
    """The table ``PANE_MODELS`` keeps for one exchange.

    One ``ExtractorBotTableModel`` per exchange id, so two screens on the
    same page do not share rows or a highlight.
    """
    held = PANE_MODELS.get(exchange_id)
    if held is None:
        held = ExtractorBotTableModel()
        PANE_MODELS[exchange_id] = held
    held.exchange_id = exchange_id
    return held


def build_payload(model: ExtractorBotTableModel) -> dict:
    """Return the whole surface state as one serialisable dict."""
    return {
        "method": METHOD,
        "logger_name": LOGGER_NAME,
        "accessible_name": ACCESSIBLE_NAME,
        "table_kind": TABLE_KIND,
        "base_kind": BASE_KIND,
        "button_kind": BUTTON_KIND,
        "column_labels": list(COLUMN_LABELS),
        "column_tooltips": {str(key): tip for key, tip in COLUMN_TOOLTIPS.items()},
        "column_fixed_widths": {
            str(key): width for key, width in COLUMN_FIXED_WIDTHS.items()
        },
        "column_count": COLUMN_COUNT,
        "text_columns": list(TEXT_COLUMNS),
        "button_columns": list(BUTTON_COLUMNS),
        "coloured_columns": list(COLOURED_COLUMNS),
        "stretch_columns": list(STRETCH_COLUMNS),
        "icon_column": ICON_COLUMN,
        "icon_size": ds.COIN_ICON_SIZE_PX,
        "items_per_selected_row": ITEMS_PER_SELECTED_ROW,
        "state_colors": dict(STATE_COLORS),
        "pool_colors": dict(POOL_COLORS),
        "state_fallback_color": STATE_FALLBACK_COLOR,
        "pool_fallback_color": POOL_FALLBACK_COLOR,
        "unset_color": UNSET_COLOR,
        "unset_brush": UNSET_BRUSH,
        "set_brush": SET_BRUSH,
        "unset_item_type": UNSET_ITEM_TYPE,
        "alignment": ALIGNMENT,
        "alignment_value": ALIGNMENT_VALUE,
        "mode_text": MODE_TEXT,
        "unknown_state_text": UNKNOWN_STATE_TEXT,
        "no_value_text": NO_VALUE_TEXT,
        "empty_tip": EMPTY_TIP,
        "default_pool_color_name": DEFAULT_POOL_COLOR_NAME,
        "pool_text_format": POOL_TEXT_FORMAT,
        "mode_tip_format": MODE_TIP_FORMAT,
        "liquid_tip_format": LIQUID_TIP_FORMAT,
        "buttons": buttons(),
        "fire_label": FIRE_LABEL,
        "detail_label": DETAIL_LABEL,
        "button_height": BUTTON_HEIGHT,
        "fire_enabled": FIRE_ENABLED,
        "detail_enabled": DETAIL_ENABLED,
        "fire_focus_policy": FIRE_FOCUS_POLICY,
        "detail_focus_policy": DETAIL_FOCUS_POLICY,
        "fire_style_sheet": FIRE_STYLE_SHEET,
        "detail_style_sheet": DETAIL_STYLE_SHEET,
        "fire_tooltip": FIRE_TOOLTIP,
        "detail_tooltip": DETAIL_TOOLTIP,
        "table_style_sheet": TABLE_STYLE_SHEET,
        "skin": dict(SKIN),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "actions": dict(ACTIONS),
        "bridge_actions": list(BRIDGE_ACTIONS),
        "status_keys": list(STATUS_KEYS),
        "trades_key": TRADES_KEY,
        "missing_text": MISSING_TEXT,
        "missing_amount": MISSING_AMOUNT,
        "missing_count": MISSING_COUNT,
        "no_deployment": NO_DEPLOYMENT,
        "no_row": NO_ROW,
        "no_bot": NO_BOT,
        "first_column": FIRST_COLUMN,
        "select_paths": list(SELECT_PATHS),
        "detail_paths": list(DETAIL_PATHS),
        "rows": [None if row is None else dict(row) for row in model.rows],
        "built_row_count": model.built_row_count,
        "bot_ids": model.bot_ids,
        "row_count": model.row_count,
        "current_row": model.current_row,
        "selected_row": model.selected_row,
        "selected_item_count": model.selected_item_count,
        "selected_bot_id": model.get_selected_bot_id(),
        "select_path": model.select_path,
        "detail_path": model.detail_path,
        "detail_calls": list(model.detail_calls),
        "has_parent": model.parent is not None,
        "exchange_id": model.exchange_id,
        "reset_param": RESET_PARAM,
        "action_param": ACTION_PARAM,
        "bot_statuses_param": BOT_STATUSES_PARAM,
        "bot_id_param": BOT_ID_PARAM,
        "exchange_id_param": EXCHANGE_ID_PARAM,
        "update_action": UPDATE_ACTION,
        "detail_action": DETAIL_ACTION,
        "select_action": SELECT_ACTION,
        "calls": [list(call) for call in model.calls],
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``extractor_bot_table.state``.

    Reads ``reset`` and one ``action``. The table's rows and its
    highlight persist between calls because the dashboard's own table
    does; ``reset`` is what a fresh paint sends.
    """
    global PANE_MODEL
    if params.get(RESET_PARAM, False):
        PANE_MODEL = ExtractorBotTableModel()
    PANE_MODEL.exchange_id = str(params.get(EXCHANGE_ID_PARAM) or MISSING_TEXT)
    return drive(PANE_MODEL, params)


def drive(model: ExtractorBotTableModel, params: dict) -> dict:
    """Apply one request to ``model``, reading each ``*_PARAM`` field.

    ``view_model`` and ``live_view_model`` both run their request here.
    """
    action = params.get(ACTION_PARAM, MISSING_TEXT)
    if action == UPDATE_ACTION:
        model.update_bots(params.get(BOT_STATUSES_PARAM) or [])
    elif action == DETAIL_ACTION:
        model._on_detail(str(params.get(BOT_ID_PARAM, NO_BOT)))
    elif action == SELECT_ACTION:
        model._select_row_for_bot(str(params.get(BOT_ID_PARAM, NO_BOT)))
    return build_payload(model)


def extractor_statuses(statuses: Any) -> list:
    """The records of ``statuses`` whose mode is ``MODE_TEXT``.

    ``update_bots`` builds a row for every record it is handed, so only the
    Extractor bots reach the Extractor table.
    """
    return [
        found
        for found in statuses or []
        if isinstance(found, dict) and found.get("mode") == MODE_TEXT
    ]


def live_view_model(params: dict, live: Any) -> dict:
    """Build the table ``EXCHANGE_ID_PARAM`` names from the running fleet.

    ``live.bot_manager.list_bots_by_exchange`` names the bots, filtered to
    ``MODE_TEXT``; ``view_model`` answers while no manager is bound.
    """
    manager = getattr(live, "bot_manager", None)
    if manager is None or not hasattr(manager, "list_bots_by_exchange"):
        return view_model(params)
    asked = dict(params or {})
    exchange_id = str(asked.get(EXCHANGE_ID_PARAM) or MISSING_TEXT)
    if asked.pop(RESET_PARAM, False):
        PANE_MODELS.pop(exchange_id, None)
    if asked.get(ACTION_PARAM) is None:
        asked[ACTION_PARAM] = UPDATE_ACTION
        asked[BOT_STATUSES_PARAM] = extractor_statuses(
            manager.list_bots_by_exchange(exchange_id)
        )
    return drive(pane_model_for(exchange_id), asked)


def bind_live(live: Any) -> Any:
    """Return an ``extractor_bot_table.state`` handler reading ``live``.

    ``build_registry`` calls this when the running program serves the bridge.
    """

    def handler(params: dict) -> dict:
        return live_view_model(params or {}, live)

    return handler
