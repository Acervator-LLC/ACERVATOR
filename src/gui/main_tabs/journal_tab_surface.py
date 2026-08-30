"""journal_tab_surface.py -- the Trade Journal and Recovery screen.

Describes the screen that lists completed trades, shows the detail of
one trade, and reports what the crash-recovery and reconciliation
services last found.

The screen carries a header strip with a running total and two drop
lists, a ten-column trade table, a detail pane written as marked-up
text, four recovery lines and two buttons.

``ComboBox`` is the drop-list behaviour the two filters need.
``JournalSource``, ``RecoverySource`` and ``ReconciliationSource``
hand the model the three readings the screen takes.
``JournalTabModel`` holds the label texts, the two filters, the table
rows and the detail text, and answers ``refresh``, ``entry_selected``
and ``update_bot_filter``.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``journal_tab.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.journal_tab``, so a value changed on one side alone is
reported. Nothing here imports Qt.
"""

from __future__ import annotations

import time
from typing import Any, Optional

METHOD = "journal_tab.state"

LOGGER_NAME = "acervator.gui"

ACCESSIBLE_NAME = "Journal Tab"

CONTAINER_MARGINS_PX = (8, 8, 8, 8)
CONTAINER_SPACING_PX = 8

ACCENT_COLOR = "#00ffcc"
POSITIVE_COLOR = "#00ff88"
NEGATIVE_COLOR = "#ff3366"
MUTED_COLOR = "#888"
INFO_COLOR = "#00aaff"
VOTES_COLOR = "#ffaa00"

COLORS = {
    "accent": ACCENT_COLOR,
    "positive": POSITIVE_COLOR,
    "negative": NEGATIVE_COLOR,
    "muted": MUTED_COLOR,
    "info": INFO_COLOR,
    "votes": VOTES_COLOR,
}

STATS_LABEL_TEXT = "Journal: 0 entries"
STATS_LABEL_STYLE = "color: #00ffcc; font-size: 13px; font-weight: bold;"
STATS_TEXT_FORMAT = (
    "Journal: {total_entries} entries | "
    "{unique_bots} bots | "
    "P/L: ${total_pnl:+,.4f}"
)

BOT_LABEL_TEXT = "Bot:"
PERIOD_LABEL_TEXT = "Period:"

ALL_BOTS_TEXT = "All Bots"
ALL_BOTS_DATA = ""
BOT_FILTER_MIN_WIDTH_PX = 150
BOT_FILTER_ITEM_FORMAT = "{symbol} [{bot_id}]"
BOT_ID_FILTER_SLICE = 8
DEFAULT_FILTER_SYMBOL = "???"

PERIOD_ITEMS = (
    ("1 Hour", 1),
    ("6 Hours", 6),
    ("24 Hours", 24),
    ("7 Days", 168),
    ("30 Days", 720),
)
PERIOD_DEFAULT_INDEX = 2
DEFAULT_HOURS = 24
ENTRY_LIMIT = 500

NO_SELECTION_INDEX = -1
NO_DATA: Optional[str] = None
NO_TEXT = ""

HEADER_ORDER = (
    "stats_label",
    "stretch",
    "bot_label",
    "bot_filter",
    "period_label",
    "period_filter",
)

SPLITTER_VERTICAL = "vertical"
SPLITTER_HORIZONTAL = "horizontal"
SPLITTER_HANDLE_WIDTH_PX = 5
SPLITTER_CHILDREN_COLLAPSIBLE = False
OUTER_SPLITTER_SIZES_PX = (350, 250)
OUTER_SPLITTER_CHILDREN = ("journal_group", "bottom_splitter")
BOTTOM_SPLITTER_SIZES_PX = (500, 300)
BOTTOM_SPLITTER_CHILDREN = ("detail_group", "recovery_group")

GROUP_STYLE = (
    "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
    "border-radius: 6px; color: #00ffcc; }"
)
JOURNAL_GROUP_TITLE = "Trade Journal"
DETAIL_GROUP_TITLE = "Entry Detail"
RECOVERY_GROUP_TITLE = "State Recovery"

COLUMNS = (
    "Time",
    "Bot",
    "Symbol",
    "Action",
    "Side",
    "Price",
    "Qty",
    "P/L",
    "TA Dir",
    "Reason",
)
COLUMN_COUNT = 10
HEADER_RESIZE_MODE = "Stretch"
ALTERNATING_ROW_COLORS = True
EDIT_TRIGGERS = "NoEditTriggers"
VERTICAL_HEADER_VISIBLE = False
SELECTION_BEHAVIOR = "SelectRows"
CELL_ALIGNMENT = "AlignCenter"
CELL_ALIGNMENT_VALUE = 132
PNL_COLUMN = 7
DIRECTION_COLUMN = 8
NO_CELL_COLOR: Optional[str] = None

BULLISH = "BULLISH"
BEARISH = "BEARISH"

DETAIL_READ_ONLY = True
DETAIL_FONT_FAMILY = "Consolas"
DETAIL_FONT_POINT_SIZE = 9
DETAIL_STYLE = "QTextEdit { background: #0a0a12; color: #c0c0c0; border: none; }"
DETAIL_JOIN = "<br>"
NO_DETAIL_HTML = ""

DETAIL_TITLE = '<span style="color:#00ffcc; font-weight:bold">Trade Detail</span>'
TA_CONTEXT_TITLE = '<span style="color:#00aaff; font-weight:bold">TA Context</span>'
VOTES_TITLE = '<span style="color:#ffaa00; font-weight:bold">Indicator Votes</span>'
BLANK_LINE = ""

FIELD_LINE_FORMAT = '<span style="color:#888">{label}:</span> {value}'
PNL_LINE_FORMAT = (
    '<span style="color:#888">P/L:</span> '
    '<span style="color:{color}">'
    "{amount}</span>"
)
VOTE_LINE_FORMAT = '  <span style="color:{color}">{indicator}: {direction}</span>'

TIME_LABEL = "Time"
BOT_LABEL = "Bot"
SYMBOL_LABEL = "Symbol"
ACTION_LABEL = "Action"
SIDE_LABEL = "Side"
PRICE_LABEL = "Price"
QUANTITY_LABEL = "Quantity"
COST_LABEL = "Cost"
DIRECTION_LABEL = "Direction"
CONFIDENCE_LABEL = "Confidence"
TIMEFRAME_LABEL = "Timeframe"
EXCHANGE_LABEL = "Exchange"
ORDER_ID_LABEL = "Order ID"
STRATEGY_LABEL = "Strategy"
SLIPPAGE_LABEL = "Slippage"
REASON_LABEL = "Reason"

DETAIL_PRICE_FORMAT = "${price:.8f}"
DETAIL_QUANTITY_FORMAT = "{quantity:.8f}"
DETAIL_COST_FORMAT = "${cost:.4f}"
DETAIL_PNL_FORMAT = "${pnl:+.4f}"
DETAIL_CONFIDENCE_FORMAT = "{confidence:.0%}"
DETAIL_SLIPPAGE_FORMAT = "{slippage_pct:.4f}%"
DETAIL_BOT_ID_SLICE = 12

ROW_TIME_FORMAT = "%H:%M:%S"
ROW_PRICE_FORMAT = "${price:.4f}"
ROW_QUANTITY_FORMAT = "{quantity:.6f}"
ROW_PNL_FORMAT = "${pnl:+.4f}"
ROW_BOT_ID_SLICE = 8
ROW_REASON_SLICE = 30

DEFAULT_TIMESTAMP = 0
DEFAULT_BOT_ID = ""
DEFAULT_SYMBOL = ""
DEFAULT_ACTION = ""
DEFAULT_SIDE = ""
DEFAULT_PRICE = 0
DEFAULT_QUANTITY = 0
DEFAULT_COST = 0
DEFAULT_PNL = 0
DEFAULT_DIRECTION_DETAIL = "N/A"
DEFAULT_DIRECTION_ROW = ""
DEFAULT_CONFIDENCE = 0
DEFAULT_TIMEFRAME = "N/A"
DEFAULT_EXCHANGE_ID = ""
DEFAULT_ORDER_ID = "N/A"
DEFAULT_STRATEGY = "market"
DEFAULT_SLIPPAGE_PCT = 0
DEFAULT_REASON_DETAIL = "N/A"
DEFAULT_REASON_ROW = ""
DEFAULT_TOTAL_ENTRIES = 0
DEFAULT_UNIQUE_BOTS = 0
DEFAULT_TOTAL_PNL = 0

SNAPSHOT_LABEL_TEXT = "Last Snapshot: None"
RECON_LABEL_TEXT = "Last Reconciliation: None"
ORPHANS_LABEL_TEXT = "Orphaned Orders: 0"
JOURNAL_FILES_LABEL_TEXT = "Journal Files: 0"
RECOVERY_LABEL_STYLE = "color: #aaa;"

SNAPSHOT_SECONDS_FORMAT = "{age_s:.0f}s ago"
SNAPSHOT_MINUTES_FORMAT = "{age_m:.1f}m ago"
SNAPSHOT_MINUTE_CUTOFF_S = 60
SNAPSHOT_TEXT_FORMAT = "Last Snapshot: {age_text} ({snapshot_bots} bots)"
JOURNAL_FILES_FORMAT = "Journal Files: {journal_files}"
RECON_TEXT_FORMAT = "Last Reconciliation: {clock} ({exchange})"
ORPHANS_FORMAT = "Orphaned Orders: {orphaned_count}"
SECONDS_PER_MINUTE = 60

DEFAULT_HAS_SNAPSHOT = False
DEFAULT_SNAPSHOT_AGE_S = 0
DEFAULT_SNAPSHOT_BOTS = 0
DEFAULT_JOURNAL_FILES = 0
DEFAULT_ORPHANED_COUNT = 0

RECON_BUTTON_TEXT = "Run Reconciliation"
RECON_BUTTON_STYLE = (
    "QPushButton { background: #1a1a3f; color: #00ffcc; "
    "border: 1px solid #00ffcc; border-radius: 4px; padding: 6px 12px; }"
    "QPushButton:hover { background: #2a2a5f; }"
)
SNAPSHOT_BUTTON_TEXT = "Save Snapshot"
SNAPSHOT_BUTTON_STYLE = (
    "QPushButton { background: #1a1a3f; color: #00aaff; "
    "border: 1px solid #00aaff; border-radius: 4px; padding: 6px 12px; }"
    "QPushButton:hover { background: #2a2a5f; }"
)
BUTTON_ENABLED = True
BUTTON_ROW_ORDER = ("recon_button", "snapshot_button")

RECOVERY_ORDER = (
    "snapshot_label",
    "recon_label",
    "orphans_label",
    "journal_files_label",
    "button_row",
    "stretch",
)

SKIN = {
    "stats_label": STATS_LABEL_STYLE,
    "group_box": GROUP_STYLE,
    "detail_view": DETAIL_STYLE,
    "recovery_label": RECOVERY_LABEL_STYLE,
    "recon_button": RECON_BUTTON_STYLE,
    "snapshot_button": SNAPSHOT_BUTTON_STYLE,
}

FORMATS = {
    "stats": STATS_TEXT_FORMAT,
    "bot_filter_item": BOT_FILTER_ITEM_FORMAT,
    "field_line": FIELD_LINE_FORMAT,
    "pnl_line": PNL_LINE_FORMAT,
    "vote_line": VOTE_LINE_FORMAT,
    "detail_price": DETAIL_PRICE_FORMAT,
    "detail_quantity": DETAIL_QUANTITY_FORMAT,
    "detail_cost": DETAIL_COST_FORMAT,
    "detail_pnl": DETAIL_PNL_FORMAT,
    "detail_confidence": DETAIL_CONFIDENCE_FORMAT,
    "detail_slippage": DETAIL_SLIPPAGE_FORMAT,
    "row_time": ROW_TIME_FORMAT,
    "row_price": ROW_PRICE_FORMAT,
    "row_quantity": ROW_QUANTITY_FORMAT,
    "row_pnl": ROW_PNL_FORMAT,
    "snapshot_seconds": SNAPSHOT_SECONDS_FORMAT,
    "snapshot_minutes": SNAPSHOT_MINUTES_FORMAT,
    "snapshot_text": SNAPSHOT_TEXT_FORMAT,
    "journal_files": JOURNAL_FILES_FORMAT,
    "recon_text": RECON_TEXT_FORMAT,
    "orphans": ORPHANS_FORMAT,
}

SLICES = {
    "detail_bot_id": DETAIL_BOT_ID_SLICE,
    "row_bot_id": ROW_BOT_ID_SLICE,
    "row_reason": ROW_REASON_SLICE,
    "filter_bot_id": BOT_ID_FILTER_SLICE,
}

TITLES = {
    "detail": DETAIL_TITLE,
    "ta_context": TA_CONTEXT_TITLE,
    "votes": VOTES_TITLE,
    "blank": BLANK_LINE,
}

LABELS = {
    "time": TIME_LABEL,
    "bot": BOT_LABEL,
    "symbol": SYMBOL_LABEL,
    "action": ACTION_LABEL,
    "side": SIDE_LABEL,
    "price": PRICE_LABEL,
    "quantity": QUANTITY_LABEL,
    "cost": COST_LABEL,
    "direction": DIRECTION_LABEL,
    "confidence": CONFIDENCE_LABEL,
    "timeframe": TIMEFRAME_LABEL,
    "exchange": EXCHANGE_LABEL,
    "order_id": ORDER_ID_LABEL,
    "strategy": STRATEGY_LABEL,
    "slippage": SLIPPAGE_LABEL,
    "reason": REASON_LABEL,
    "bot_filter": BOT_LABEL_TEXT,
    "period_filter": PERIOD_LABEL_TEXT,
}

DEFAULTS = {
    "timestamp": DEFAULT_TIMESTAMP,
    "bot_id": DEFAULT_BOT_ID,
    "symbol": DEFAULT_SYMBOL,
    "action": DEFAULT_ACTION,
    "side": DEFAULT_SIDE,
    "price": DEFAULT_PRICE,
    "quantity": DEFAULT_QUANTITY,
    "cost": DEFAULT_COST,
    "pnl": DEFAULT_PNL,
    "direction_detail": DEFAULT_DIRECTION_DETAIL,
    "direction_row": DEFAULT_DIRECTION_ROW,
    "confidence": DEFAULT_CONFIDENCE,
    "timeframe": DEFAULT_TIMEFRAME,
    "exchange_id": DEFAULT_EXCHANGE_ID,
    "order_id": DEFAULT_ORDER_ID,
    "strategy": DEFAULT_STRATEGY,
    "slippage_pct": DEFAULT_SLIPPAGE_PCT,
    "reason_detail": DEFAULT_REASON_DETAIL,
    "reason_row": DEFAULT_REASON_ROW,
    "total_entries": DEFAULT_TOTAL_ENTRIES,
    "unique_bots": DEFAULT_UNIQUE_BOTS,
    "total_pnl": DEFAULT_TOTAL_PNL,
    "has_snapshot": DEFAULT_HAS_SNAPSHOT,
    "snapshot_age_s": DEFAULT_SNAPSHOT_AGE_S,
    "snapshot_bots": DEFAULT_SNAPSHOT_BOTS,
    "journal_files": DEFAULT_JOURNAL_FILES,
    "orphaned_count": DEFAULT_ORPHANED_COUNT,
    "filter_symbol": DEFAULT_FILTER_SYMBOL,
    "hours": DEFAULT_HOURS,
    "entry_limit": ENTRY_LIMIT,
}

DEFAULT_TEXTS = {
    "stats": STATS_LABEL_TEXT,
    "snapshot": SNAPSHOT_LABEL_TEXT,
    "recon": RECON_LABEL_TEXT,
    "orphans": ORPHANS_LABEL_TEXT,
    "journal_files": JOURNAL_FILES_LABEL_TEXT,
}

ACTIONS = {
    "bot_filter.currentIndexChanged": "refresh",
    "period_filter.currentIndexChanged": "refresh",
    "journal_table.currentCellChanged": "entry_selected",
}
TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()

REFRESH_START = "refresh.start"
REFRESH_NO_JOURNAL = "refresh.no_journal"
REFRESH_STATS = "refresh.stats"
REFRESH_QUERY = "refresh.query"
REFRESH_ROWS = "refresh.rows"
REFRESH_NO_RECOVERY = "refresh.no_recovery"
REFRESH_SNAPSHOT = "refresh.snapshot"
REFRESH_NO_SNAPSHOT = "refresh.no_snapshot"
REFRESH_FILES = "refresh.files"
REFRESH_NO_RECON = "refresh.no_recon"
REFRESH_RECON = "refresh.recon"
REFRESH_NO_RESULT = "refresh.no_result"
REFRESH_RETURN = "refresh.return"
DETAIL_START = "detail.start"
DETAIL_SKIPPED = "detail.skipped"
DETAIL_VOTES = "detail.votes"
DETAIL_SET = "detail.set"
FILTER_START = "filter.start"
FILTER_ITEM = "filter.item"
FILTER_RESTORED = "filter.restored"
FILTER_LOST = "filter.lost"
FILTER_RETURN = "filter.return"

ModelCall = list

CALL_NAMES = (
    REFRESH_START,
    REFRESH_NO_JOURNAL,
    REFRESH_STATS,
    REFRESH_QUERY,
    REFRESH_ROWS,
    REFRESH_NO_RECOVERY,
    REFRESH_SNAPSHOT,
    REFRESH_NO_SNAPSHOT,
    REFRESH_FILES,
    REFRESH_NO_RECON,
    REFRESH_RECON,
    REFRESH_NO_RESULT,
    REFRESH_RETURN,
    DETAIL_START,
    DETAIL_SKIPPED,
    DETAIL_VOTES,
    DETAIL_SET,
    FILTER_START,
    FILTER_ITEM,
    FILTER_RESTORED,
    FILTER_LOST,
    FILTER_RETURN,
)


def last_query(model: "JournalTabModel") -> dict:
    """The filter values the screen last asked the journal for."""
    for call in reversed(model.calls):
        if call[0] == REFRESH_QUERY:
            return {"bot_id": call[1], "hours": call[2], "limit": call[3]}
    return {}


def stats_text(stats: dict) -> str:
    """The header total: entry count, bot count and running profit."""
    return STATS_TEXT_FORMAT.format(
        total_entries=stats.get("total_entries", DEFAULT_TOTAL_ENTRIES),
        unique_bots=stats.get("unique_bots", DEFAULT_UNIQUE_BOTS),
        total_pnl=stats.get("total_pnl", DEFAULT_TOTAL_PNL),
    )


def field_line(label: str, value: Any) -> str:
    """One labelled line of the detail pane."""
    return FIELD_LINE_FORMAT.format(label=label, value=value)


def pnl_color(pnl: Any) -> str:
    """Green at or above break-even, red below it."""
    return POSITIVE_COLOR if pnl >= 0 else NEGATIVE_COLOR


def direction_color(direction: Any) -> Optional[str]:
    """The table colour one TA direction is drawn in, or none for other text."""
    if direction == BULLISH:
        return POSITIVE_COLOR
    if direction == BEARISH:
        return NEGATIVE_COLOR
    return NO_CELL_COLOR


def vote_color(direction: Any) -> str:
    """The detail-pane colour one indicator vote is drawn in."""
    if direction == BULLISH:
        return POSITIVE_COLOR
    if direction == BEARISH:
        return NEGATIVE_COLOR
    return MUTED_COLOR


def detail_lines(entry: dict) -> list:
    """Every line of the detail pane for one journal entry, in order."""
    pnl = entry.get("pnl", DEFAULT_PNL)
    lines = [
        DETAIL_TITLE,
        field_line(TIME_LABEL, time.ctime(entry.get("timestamp", DEFAULT_TIMESTAMP))),
        field_line(
            BOT_LABEL, entry.get("bot_id", DEFAULT_BOT_ID)[:DETAIL_BOT_ID_SLICE]
        ),
        field_line(SYMBOL_LABEL, entry.get("symbol", DEFAULT_SYMBOL)),
        field_line(ACTION_LABEL, entry.get("action", DEFAULT_ACTION)),
        field_line(SIDE_LABEL, entry.get("side", DEFAULT_SIDE)),
        field_line(
            PRICE_LABEL,
            DETAIL_PRICE_FORMAT.format(price=entry.get("price", DEFAULT_PRICE)),
        ),
        field_line(
            QUANTITY_LABEL,
            DETAIL_QUANTITY_FORMAT.format(
                quantity=entry.get("quantity", DEFAULT_QUANTITY)
            ),
        ),
        field_line(
            COST_LABEL, DETAIL_COST_FORMAT.format(cost=entry.get("cost", DEFAULT_COST))
        ),
        PNL_LINE_FORMAT.format(
            color=pnl_color(pnl), amount=DETAIL_PNL_FORMAT.format(pnl=pnl)
        ),
        BLANK_LINE,
        TA_CONTEXT_TITLE,
        field_line(
            DIRECTION_LABEL, entry.get("ta_direction", DEFAULT_DIRECTION_DETAIL)
        ),
        field_line(
            CONFIDENCE_LABEL,
            DETAIL_CONFIDENCE_FORMAT.format(
                confidence=entry.get("ta_confidence", DEFAULT_CONFIDENCE)
            ),
        ),
        field_line(TIMEFRAME_LABEL, entry.get("ta_timeframe", DEFAULT_TIMEFRAME)),
    ]
    signals = entry.get("ta_signals", {})
    if signals:
        lines.append(BLANK_LINE)
        lines.append(VOTES_TITLE)
        for indicator, direction in signals.items():
            lines.append(
                VOTE_LINE_FORMAT.format(
                    color=vote_color(direction),
                    indicator=indicator,
                    direction=direction,
                )
            )
    lines.extend(
        [
            BLANK_LINE,
            field_line(EXCHANGE_LABEL, entry.get("exchange_id", DEFAULT_EXCHANGE_ID)),
            field_line(ORDER_ID_LABEL, entry.get("order_id", DEFAULT_ORDER_ID)),
            field_line(
                STRATEGY_LABEL, entry.get("execution_strategy", DEFAULT_STRATEGY)
            ),
            field_line(
                SLIPPAGE_LABEL,
                DETAIL_SLIPPAGE_FORMAT.format(
                    slippage_pct=entry.get("slippage_pct", DEFAULT_SLIPPAGE_PCT)
                ),
            ),
            field_line(REASON_LABEL, entry.get("reason", DEFAULT_REASON_DETAIL)),
        ]
    )
    return lines


def row_cells(entry: dict) -> list:
    """The ten cell texts one journal entry fills a table row with."""
    pnl = entry.get("pnl", DEFAULT_PNL)
    return [
        time.strftime(
            ROW_TIME_FORMAT,
            time.localtime(entry.get("timestamp", DEFAULT_TIMESTAMP)),
        ),
        entry.get("bot_id", DEFAULT_BOT_ID)[:ROW_BOT_ID_SLICE],
        entry.get("symbol", DEFAULT_SYMBOL),
        entry.get("action", DEFAULT_ACTION),
        entry.get("side", DEFAULT_SIDE),
        ROW_PRICE_FORMAT.format(price=entry.get("price", DEFAULT_PRICE)),
        ROW_QUANTITY_FORMAT.format(quantity=entry.get("quantity", DEFAULT_QUANTITY)),
        ROW_PNL_FORMAT.format(pnl=pnl),
        entry.get("ta_direction", DEFAULT_DIRECTION_ROW),
        entry.get("reason", DEFAULT_REASON_ROW)[:ROW_REASON_SLICE],
    ]


def row_colors(entry: dict) -> list:
    """The colour each cell of one row is drawn in, or none where default."""
    colors: list = [NO_CELL_COLOR] * COLUMN_COUNT
    colors[PNL_COLUMN] = pnl_color(entry.get("pnl", DEFAULT_PNL))
    colors[DIRECTION_COLUMN] = direction_color(
        entry.get("ta_direction", DEFAULT_DIRECTION_ROW)
    )
    return colors


def snapshot_age_text(age_s: Any) -> str:
    """The snapshot age in seconds under a minute, in minutes above it."""
    if age_s < SNAPSHOT_MINUTE_CUTOFF_S:
        return SNAPSHOT_SECONDS_FORMAT.format(age_s=age_s)
    return SNAPSHOT_MINUTES_FORMAT.format(age_m=age_s / SECONDS_PER_MINUTE)


class ComboBox:
    """The drop-list behaviour the bot filter and the period filter need.

    Holds the item texts and the value behind each, the selected
    position, and whether the list is answering its change signal. An
    empty list, and a position outside the list, select nothing.
    """

    def __init__(self) -> None:
        self.items: list = []
        self.index = NO_SELECTION_INDEX
        self.signals_blocked = False

    def add_item(self, text: str, data: Any) -> None:
        """Append one item; the first item added becomes the selected one."""
        self.items.append([text, data])
        if self.index == NO_SELECTION_INDEX:
            self.index = 0

    def clear(self) -> None:
        """Drop every item and select nothing."""
        self.items = []
        self.index = NO_SELECTION_INDEX

    def set_current_index(self, index: int) -> None:
        """Select one position; a position outside the list selects nothing."""
        self.index = index if 0 <= index < len(self.items) else NO_SELECTION_INDEX

    def find_data(self, data: Any) -> int:
        """The position of the first item holding `data`, or -1 for none."""
        for position, item in enumerate(self.items):
            if item[1] == data:
                return position
        return NO_SELECTION_INDEX

    def current_data(self) -> Any:
        """The value behind the selected item, or None when none is selected."""
        if 0 <= self.index < len(self.items):
            return self.items[self.index][1]
        return NO_DATA

    def current_text(self) -> str:
        """The text of the selected item, or the empty string for none."""
        if 0 <= self.index < len(self.items):
            return self.items[self.index][0]
        return NO_TEXT

    def block_signals(self, blocked: bool) -> bool:
        """Stop or resume the change signal; returns what it was before."""
        was = self.signals_blocked
        self.signals_blocked = bool(blocked)
        return was

    def count(self) -> int:
        return len(self.items)

    def state(self) -> dict:
        """Every value the drop list can be asked for."""
        return {
            "items": [list(item) for item in self.items],
            "index": self.index,
            "current_data": self.current_data(),
            "current_text": self.current_text(),
            "count": self.count(),
            "signals_blocked": self.signals_blocked,
        }


class JournalSource:
    """The trade journal's two readings, taken from plain data.

    ``get_entries`` keeps the arguments it was called with so a caller
    can check the filter values the screen queried on.
    """

    def __init__(self, statistics: Optional[dict] = None, entries=None) -> None:
        self.statistics = dict(statistics or {})
        self.entries = list(entries or [])
        self.query: dict = {}

    def get_statistics(self) -> dict:
        return self.statistics

    def get_entries(
        self,
        bot_id: str = ALL_BOTS_DATA,
        hours: Any = DEFAULT_HOURS,
        limit: int = ENTRY_LIMIT,
    ) -> list:
        self.query = {"bot_id": bot_id, "hours": hours, "limit": limit}
        return self.entries


class RecoverySource:
    """The crash-recovery service's one reading, taken from plain data."""

    def __init__(self, info: Optional[dict] = None) -> None:
        self.info = dict(info or {})

    def get_recovery_info(self) -> dict:
        return self.info


class ReconciliationSource:
    """The reconciliation engine's one reading, taken from plain data."""

    def __init__(self, result: Optional[dict] = None) -> None:
        self.result = dict(result) if result else None

    def get_latest_result(self) -> Optional[dict]:
        return self.result


class JournalTabModel:
    """The Journal screen's texts, filters, table rows and detail pane.

    ``refresh`` fills the header total, the table and the four recovery
    lines. ``entry_selected`` writes the detail pane for one row.
    ``update_bot_filter`` rebuilds the bot drop list and keeps the
    selected bot where the new list still holds it. Every step is
    appended to ``calls`` in the order the shipped screen makes it.
    """

    def __init__(
        self,
        journal: Any = None,
        reconciliation: Any = None,
        crash_recovery: Any = None,
    ) -> None:
        self.journal = journal
        self.recon = reconciliation
        self.recovery = crash_recovery
        self.accessible_name = ACCESSIBLE_NAME
        self.bot_filter = ComboBox()
        self.bot_filter.add_item(ALL_BOTS_TEXT, ALL_BOTS_DATA)
        self.period_filter = ComboBox()
        for label, hours in PERIOD_ITEMS:
            self.period_filter.add_item(label, hours)
        self.period_filter.set_current_index(PERIOD_DEFAULT_INDEX)
        self.stats_text = STATS_LABEL_TEXT
        self.snapshot_text = SNAPSHOT_LABEL_TEXT
        self.recon_text = RECON_LABEL_TEXT
        self.orphans_text = ORPHANS_LABEL_TEXT
        self.journal_files_text = JOURNAL_FILES_LABEL_TEXT
        self.rows: list = []
        self.row_colors: list = []
        self.current_entries: list = []
        self.detail_html = NO_DETAIL_HTML
        self.calls: list[ModelCall] = []

    def entry_selected(self, row: int, col: int, prev_row: int, prev_col: int) -> None:
        """Write the detail pane for `row`; a row outside the list writes nothing."""
        self.calls.append([DETAIL_START, row, col, prev_row, prev_col])
        if row < 0 or row >= len(self.current_entries):
            self.calls.append([DETAIL_SKIPPED, row])
            return None
        entry = self.current_entries[row]
        lines = detail_lines(entry)
        self.calls.append([DETAIL_VOTES, len(entry.get("ta_signals", {}) or {})])
        self.detail_html = DETAIL_JOIN.join(lines)
        self.calls.append([DETAIL_SET, len(lines)])
        return None

    def refresh(
        self,
        journal: Any = None,
        reconciliation: Any = None,
        crash_recovery: Any = None,
    ) -> None:
        """Fill the header total, the table and the recovery lines.

        Each of the three services falls back to the one the screen was
        built with. No journal at all leaves the screen untouched.
        """
        self.calls.append([REFRESH_START])
        source = journal or self.journal
        if not source:
            self.calls.append([REFRESH_NO_JOURNAL])
            return None
        stats = source.get_statistics()
        self.stats_text = stats_text(stats)
        self.calls.append([REFRESH_STATS, self.stats_text])

        bot_id = self.bot_filter.current_data() or ALL_BOTS_DATA
        hours = self.period_filter.current_data() or DEFAULT_HOURS
        self.calls.append([REFRESH_QUERY, bot_id, hours, ENTRY_LIMIT])

        entries = source.get_entries(bot_id=bot_id, hours=hours, limit=ENTRY_LIMIT)
        self.current_entries = entries
        self.rows = []
        self.row_colors = []
        for one in entries:
            self.rows.append(row_cells(one))
            self.row_colors.append(row_colors(one))
        self.calls.append([REFRESH_ROWS, len(entries)])

        recovery = crash_recovery or self.recovery
        if recovery:
            info = recovery.get_recovery_info()
            if info.get("has_snapshot"):
                age_s = info.get("snapshot_age", DEFAULT_SNAPSHOT_AGE_S)
                self.snapshot_text = SNAPSHOT_TEXT_FORMAT.format(
                    age_text=snapshot_age_text(age_s),
                    snapshot_bots=info.get("snapshot_bots", DEFAULT_SNAPSHOT_BOTS),
                )
                self.calls.append([REFRESH_SNAPSHOT, self.snapshot_text])
            else:
                self.calls.append([REFRESH_NO_SNAPSHOT])
            self.journal_files_text = JOURNAL_FILES_FORMAT.format(
                journal_files=info.get("journal_files", DEFAULT_JOURNAL_FILES)
            )
            self.calls.append([REFRESH_FILES, self.journal_files_text])
        else:
            self.calls.append([REFRESH_NO_RECOVERY])

        engine = reconciliation or self.recon
        if engine:
            latest = engine.get_latest_result()
            if latest:
                clock = time.strftime(
                    ROW_TIME_FORMAT, time.localtime(latest["timestamp"])
                )
                self.recon_text = RECON_TEXT_FORMAT.format(
                    clock=clock, exchange=latest["exchange"]
                )
                self.orphans_text = ORPHANS_FORMAT.format(
                    orphaned_count=latest.get("orphaned_count", DEFAULT_ORPHANED_COUNT)
                )
                self.calls.append([REFRESH_RECON, self.recon_text, self.orphans_text])
            else:
                self.calls.append([REFRESH_NO_RESULT])
        else:
            self.calls.append([REFRESH_NO_RECON])
        self.calls.append([REFRESH_RETURN, len(self.rows)])
        return None

    def update_bot_filter(self, bot_statuses: list) -> None:
        """Rebuild the bot drop list, keeping the selected bot where it survives."""
        current = self.bot_filter.current_data()
        self.calls.append([FILTER_START, current])
        self.bot_filter.block_signals(True)
        self.bot_filter.clear()
        self.bot_filter.add_item(ALL_BOTS_TEXT, ALL_BOTS_DATA)
        for status in bot_statuses:
            bot_id = status.get("bot_id", DEFAULT_BOT_ID)
            symbol = status.get("symbol", DEFAULT_FILTER_SYMBOL)
            text = BOT_FILTER_ITEM_FORMAT.format(
                symbol=symbol, bot_id=bot_id[:BOT_ID_FILTER_SLICE]
            )
            self.bot_filter.add_item(text, bot_id)
            self.calls.append([FILTER_ITEM, text, bot_id])
        index = self.bot_filter.find_data(current)
        if index >= 0:
            self.bot_filter.set_current_index(index)
            self.calls.append([FILTER_RESTORED, index])
        else:
            self.calls.append([FILTER_LOST, current])
        self.bot_filter.block_signals(False)
        self.calls.append([FILTER_RETURN, self.bot_filter.count()])
        return None


def build_view_model(
    model: JournalTabModel,
    bot_statuses=None,
    refresh_now: bool = False,
    selected_row: Any = None,
) -> dict:
    """Return every value the Journal screen holds as one dict.

    `bot_statuses` rebuilds the bot drop list before anything else, as
    the window does when its bot list changes. `refresh_now` takes the
    three service readings. `selected_row` writes the detail pane for
    one table row.
    """
    if bot_statuses is not None:
        model.update_bot_filter(bot_statuses)
    if refresh_now:
        model.refresh()
    if selected_row is not None:
        model.entry_selected(selected_row, 0, NO_SELECTION_INDEX, NO_SELECTION_INDEX)
    return {
        "accessible_name": model.accessible_name,
        "container": {
            "margins_px": list(CONTAINER_MARGINS_PX),
            "spacing_px": CONTAINER_SPACING_PX,
        },
        "header_order": list(HEADER_ORDER),
        "stats_label": {"text": model.stats_text, "style_sheet": STATS_LABEL_STYLE},
        "bot_label": {"text": BOT_LABEL_TEXT},
        "period_label": {"text": PERIOD_LABEL_TEXT},
        "bot_filter": dict(
            model.bot_filter.state(), minimum_width_px=BOT_FILTER_MIN_WIDTH_PX
        ),
        "period_filter": dict(
            model.period_filter.state(), default_index=PERIOD_DEFAULT_INDEX
        ),
        "period_items": [list(item) for item in PERIOD_ITEMS],
        "all_bots_item": [ALL_BOTS_TEXT, ALL_BOTS_DATA],
        "splitter": {
            "orientation": SPLITTER_VERTICAL,
            "handle_width_px": SPLITTER_HANDLE_WIDTH_PX,
            "children_collapsible": SPLITTER_CHILDREN_COLLAPSIBLE,
            "requested_sizes_px": list(OUTER_SPLITTER_SIZES_PX),
            "children": list(OUTER_SPLITTER_CHILDREN),
        },
        "bottom_splitter": {
            "orientation": SPLITTER_HORIZONTAL,
            "handle_width_px": SPLITTER_HANDLE_WIDTH_PX,
            "children_collapsible": SPLITTER_CHILDREN_COLLAPSIBLE,
            "requested_sizes_px": list(BOTTOM_SPLITTER_SIZES_PX),
            "children": list(BOTTOM_SPLITTER_CHILDREN),
        },
        "journal_group": {"title": JOURNAL_GROUP_TITLE, "style_sheet": GROUP_STYLE},
        "detail_group": {"title": DETAIL_GROUP_TITLE, "style_sheet": GROUP_STYLE},
        "recovery_group": {"title": RECOVERY_GROUP_TITLE, "style_sheet": GROUP_STYLE},
        "journal_table": {
            "columns": list(COLUMNS),
            "column_count": COLUMN_COUNT,
            "header_resize_mode": HEADER_RESIZE_MODE,
            "alternating_row_colors": ALTERNATING_ROW_COLORS,
            "edit_triggers": EDIT_TRIGGERS,
            "vertical_header_visible": VERTICAL_HEADER_VISIBLE,
            "selection_behavior": SELECTION_BEHAVIOR,
            "cell_alignment": CELL_ALIGNMENT,
            "cell_alignment_value": CELL_ALIGNMENT_VALUE,
            "pnl_column": PNL_COLUMN,
            "direction_column": DIRECTION_COLUMN,
            "row_count": len(model.rows),
            "rows": [list(row) for row in model.rows],
            "row_colors": [list(row) for row in model.row_colors],
        },
        "detail_view": {
            "read_only": DETAIL_READ_ONLY,
            "font_family": DETAIL_FONT_FAMILY,
            "font_point_size": DETAIL_FONT_POINT_SIZE,
            "style_sheet": DETAIL_STYLE,
            "join": DETAIL_JOIN,
            "html": model.detail_html,
        },
        "snapshot_label": {
            "text": model.snapshot_text,
            "style_sheet": RECOVERY_LABEL_STYLE,
        },
        "recon_label": {
            "text": model.recon_text,
            "style_sheet": RECOVERY_LABEL_STYLE,
        },
        "orphans_label": {
            "text": model.orphans_text,
            "style_sheet": RECOVERY_LABEL_STYLE,
        },
        "journal_files_label": {
            "text": model.journal_files_text,
            "style_sheet": RECOVERY_LABEL_STYLE,
        },
        "recon_button": {
            "text": RECON_BUTTON_TEXT,
            "style_sheet": RECON_BUTTON_STYLE,
            "enabled": BUTTON_ENABLED,
        },
        "snapshot_button": {
            "text": SNAPSHOT_BUTTON_TEXT,
            "style_sheet": SNAPSHOT_BUTTON_STYLE,
            "enabled": BUTTON_ENABLED,
        },
        "button_row_order": list(BUTTON_ROW_ORDER),
        "recovery_order": list(RECOVERY_ORDER),
        "snapshot_minute_cutoff_s": SNAPSHOT_MINUTE_CUTOFF_S,
        "seconds_per_minute": SECONDS_PER_MINUTE,
        "bullish": BULLISH,
        "bearish": BEARISH,
        "no_selection_index": NO_SELECTION_INDEX,
        "no_data": NO_DATA,
        "no_text": NO_TEXT,
        "no_cell_color": NO_CELL_COLOR,
        "no_detail_html": NO_DETAIL_HTML,
        "colors": dict(COLORS),
        "default_texts": dict(DEFAULT_TEXTS),
        "titles": dict(TITLES),
        "labels": dict(LABELS),
        "formats": dict(FORMATS),
        "slices": dict(SLICES),
        "defaults": dict(DEFAULTS),
        "skin": dict(SKIN),
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "entry_count": len(model.current_entries),
        "entry_query": last_query(model),
        "call_names": list(CALL_NAMES),
        "calls": [list(call) for call in model.calls],
    }


PANE_MODEL = JournalTabModel()


def view_model(params: dict) -> dict:
    """Bridge handler for ``journal_tab.state``.

    Reads ``reset``, ``statistics``, ``entries``, ``recovery_info``,
    ``reconciliation_result``, ``bot_statuses`` and ``selected_row``
    from the request parameters. The screen's filters and its last
    detail text persist between calls because the screen does; ``reset``
    is what a fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = JournalTabModel()
    statistics = params.get("statistics")
    entries = params.get("entries")
    recovery_info = params.get("recovery_info")
    reconciliation_result = params.get("reconciliation_result")
    has_journal = statistics is not None or entries is not None
    PANE_MODEL.journal = JournalSource(statistics, entries) if has_journal else None
    PANE_MODEL.recovery = (
        RecoverySource(recovery_info) if recovery_info is not None else None
    )
    PANE_MODEL.recon = (
        ReconciliationSource(reconciliation_result)
        if reconciliation_result is not None
        else None
    )
    return build_view_model(
        PANE_MODEL,
        params.get("bot_statuses"),
        params.get("refresh", has_journal),
        params.get("selected_row"),
    )
