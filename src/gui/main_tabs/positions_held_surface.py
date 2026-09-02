"""positions_held_surface.py -- the Positions Held tab, without Qt.

Describes the tab inside the live bot settings window that lists every
open Extractor position and gives each one its own Fire button. The tab
holds a summary box with four rows, then either an empty-state line or a
nine-column table whose last column carries one button per row, followed
by a footer line.

``PositionsHeldTabModel`` holds the tab's state. ``build`` reads the bot
and fills the summary, the table rows and the row colours. ``fire_handler``
returns the callable one Fire button runs. ``fire`` runs that callable and
reports which of its four paths it took: declined, no async loop, schedule
failed, or dispatched.

``BotSource``, ``BotConfig``, ``ManagerSource`` and ``ScheduleSink`` are
plain stand-ins for the Extractor bot, its config, the bot manager and
the loop hand-off, so the tab can be driven over the bridge from values
alone.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``positions_held_tab.state`` method, which is how the Electron
renderer reaches it. Every value below is written out here rather than
read from ``src.gui.live_settings.positions_held_tab``, so a value changed
on one side alone is reported. Nothing here imports Qt.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import design_system as ds

METHOD = "positions_held_tab.state"

ACCESSIBLE_NAME = ""

CONTENT_SPACING_PX = 8
CONTENT_MARGINS_SET = False

SUMMARY_GROUP_TITLE = "Extractor Pool Status"
SUMMARY_FORM_CONFIGURED_BY_HOST = True

POOL_ROW_LABEL = "Pool color:"
CHUNK_SIZE_ROW_FORMAT = "Chunk size ({base_currency} / USD):"
CHUNK_FREE_ROW_FORMAT = "Chunk free ({base_currency}):"
EXTRACTED_ROW_FORMAT = "Lifetime extracted ({base_currency}):"

STRONG_OPEN = "<b>"
STRONG_CLOSE = "</b>"
ITALIC_OPEN = "<i>"
ITALIC_CLOSE = "</i>"
BREAK_TAG = "<br>"
STRONG_WEIGHT = "bold"
ITALIC_STYLE = "italic"
NO_PIECE = ""

PLAIN_PIECE = "plain"
STRONG_PIECE = "strong"
BREAK_PIECE = "break"
PIECE_KINDS = (PLAIN_PIECE, STRONG_PIECE, BREAK_PIECE)

NO_WRAP = ""
ITALIC_WRAP = "italic"
WRAP_KINDS = (NO_WRAP, ITALIC_WRAP)

MARK_TAGS = {
    "strong_open": STRONG_OPEN,
    "strong_close": STRONG_CLOSE,
    "italic_open": ITALIC_OPEN,
    "italic_close": ITALIC_CLOSE,
    "break_tag": BREAK_TAG,
    "strong_weight": STRONG_WEIGHT,
    "italic_style": ITALIC_STYLE,
    "no_piece": NO_PIECE,
}

POOL_TEXT_FORMAT = STRONG_OPEN + "{pool_color}" + STRONG_CLOSE
POOL_STYLE_FORMAT = "color: {color_hex}; font-size: 14px;"
POOL_WRAP = NO_WRAP
CHUNK_SIZE_VALUE_FORMAT = "{chunk_size_base:.8f} / ${chunk_size_usd:,.2f}"
CHUNK_FREE_VALUE_FORMAT = "{chunk_free_base:.8f}"
EXTRACTED_VALUE_FORMAT = "{extracted_total:+.8f}"

POOL_GREEN = "green"
POOL_YELLOW = "yellow"
POOL_RED = "red"
POOL_FALLBACK = POOL_GREEN

POOL_COLOR_HEX = {
    POOL_GREEN: ds.SUCCESS,
    POOL_YELLOW: ds.WARNING,
    POOL_RED: ds.ERROR,
}
POOL_UNKNOWN_HEX = ds.TEXT_MED

EMPTY_LEAD = (
    "No open positions. Bot is watching its top-N "
    "watch list for bearish signals. Pool color is "
)
EMPTY_TAIL = " (fully in base currency)."
EMPTY_WRAP = ITALIC_WRAP
EMPTY_STYLE = f"color: {ds.TEXT_EMPTY_STATE}; padding: 16px;"
EMPTY_WORD_WRAP = True

READ_FAILED_LEAD = "Could not read the open positions from the bot. This tab shows "
READ_FAILED_STRONG = "no position data"
READ_FAILED_TAIL = (
    " and makes no claim about the pool. Re-open the dialog to read again."
)

FOOTER_STRONG = "Per-position Manual Fire"
FOOTER_TAIL = (
    " (operator decision #7): "
    "each button closes ITS position at current market "
    "price. Bypasses the auto path's base-unit-profitability "
    "gate per operator-sovereignty invariant (v3.18.15). "
    "MEM-257 FAIL-CLOSED still applies to any new buys the "
    "bot subsequently initiates (artillery, correction) on "
    "behalf of the pool."
)
FOOTER_WRAP = NO_WRAP
FOOTER_STYLE = f"color: {ds.TEXT_EMPTY_STATE}; padding: 8px; font-size: 11px;"
FOOTER_WORD_WRAP = True

COLUMNS = (
    "Pair",
    "State",
    "Tier",
    "Alt units",
    "Entry (USD)",
    "Current (USD)",
    "Δ% (USD)",
    "Corrections",
    "Manual Fire",
)
COLUMN_COUNT = 9
CELL_COLUMN_COUNT = 8
STATE_COLUMN = 1
DELTA_COLUMN = 6
FIRE_COLUMN = 8

HEADER_RESIZE_MODE = "ResizeToContents"
VERTICAL_HEADER_VISIBLE = False
EDIT_TRIGGERS = "NoEditTriggers"
SELECTION_BEHAVIOR = "SelectRows"
ALTERNATING_ROW_COLORS = True
CELL_ALIGNMENT = "AlignCenter"
CELL_ALIGNMENT_VALUE = 132
TABLE_STRETCH = 1

STATE_DRAWDOWN = "drawdown"
STATE_BULLISH_EXIT = "bullish_exit"

DRAWDOWN_COLOR = "#ff0000"
BULLISH_EXIT_COLOR = "#ffff00"
OPEN_STATE_COLOR = "#00ff00"
DELTA_UP_COLOR = OPEN_STATE_COLOR
DELTA_DOWN_COLOR = DRAWDOWN_COLOR
UNREADABLE_COLOR = ds.WARNING
NO_CELL_COLOR: Optional[str] = None

UNREADABLE_TEXT = "—"
UNREADABLE_COLUMNS = {
    "tier": 2,
    "alt_units": 3,
    "entry_usd": 4,
    "current_usd": 5,
    "delta_pct": 6,
    "corrections": 7,
}

PAIR_FORMAT = "{pair}"
TIER_FORMAT = "{tier}"
ALT_UNITS_FORMAT = "{alt_units:.6f}"
ENTRY_FORMAT = "${entry_usd:,.4f}"
CURRENT_FORMAT = "${current_usd:,.4f}"
DELTA_FORMAT = "{delta_pct:+.2f}%"
CORRECTIONS_FORMAT = "{corrections}"

FIRE_BUTTON_TEXT = "Fire"
FIRE_BUTTON_HEIGHT_PX = 24
FIRE_BUTTON_STYLE = (
    f"QPushButton {{ background: {ds.WARNING_STRONG}; color: white; "
    "border: none; border-radius: 4px; padding: 4px 12px; "
    "font-weight: bold; }"
    f"QPushButton:hover {{ background: {ds.SETTINGS_WARNING_HOVER}; }}"
)

CONFIRM_TITLE = "Manual Fire — confirm position close"
CONFIRM_LEAD = "Close position on "
CONFIRM_TAIL_ONE = " at current market price?"
CONFIRM_TAIL_TWO = (
    "This will fire a 100% market SELL on the "
    "alt units, returning base currency to the "
    "pool. Bypasses the auto path's "
    "base-unit-profitability gate per "
    "operator-sovereignty (v3.18.15 invariant)."
)
CONFIRM_TAIL_THREE = "MEM-257 fail-closed still applies."
CONFIRM_BREAKS = 2
CONFIRM_WRAP = NO_WRAP

NO_LOOP_TITLE = "Async loop unavailable"
NO_LOOP_TEXT = (
    "Bot manager async loop not running. Try again after platform launch completes."
)

SCHEDULE_FAILED_TITLE = "Schedule failed"
SCHEDULE_FAILED_TEXT_FORMAT = "Could not schedule the close:\n\n{error}: {message}"

DISPATCHED_TITLE = "Manual Fire dispatched"
DISPATCHED_LEAD = "Close dispatched for "
DISPATCHED_TAIL = (
    ". Watch the Activity Log for the completion "
    "line. Re-open this dialog after the order "
    "settles to see updated state."
)
DISPATCHED_WRAP = NO_WRAP

QUESTION_ICON = "question"
WARNING_ICON = "warning"
INFORMATION_ICON = "information"

YES_BUTTON_VALUE = 16384
NO_BUTTON_VALUE = 65536
OK_BUTTON_VALUE = 1024
CONFIRM_BUTTONS_VALUE = YES_BUTTON_VALUE | NO_BUTTON_VALUE
CONFIRM_DEFAULT_BUTTON_VALUE = NO_BUTTON_VALUE
NO_DEFAULT_BUTTON_VALUE = 0

ASYNC_LOOP_ATTRIBUTE = "_async_loop"

CHUNK_SIZE_USD_ATTRIBUTE = "_chunk_size_usd"
CHUNK_FREE_BASE_ATTRIBUTE = "_chunk_free_base"
CHUNK_SIZE_BASE_ATTRIBUTE = "_chunk_size_base"
EXTRACTED_TOTAL_ATTRIBUTE = "_chunk_extracted_total"

DEFAULT_CHUNK_USD = 0.0
DEFAULT_CHUNK_BASE = 0.0
DEFAULT_PAIR = ""
DEFAULT_STATE = ""
DEFAULT_TIER = 1
DEFAULT_ALT_UNITS = 0.0
DEFAULT_ENTRY_USD = 0.0
DEFAULT_CURRENT_USD = 0.0
DEFAULT_DELTA_PCT = 0.0
DEFAULT_CORRECTIONS = 0
DEFAULT_OPENED_AT = ""

PAIR_KEY = "pair"
STATE_KEY = "state"
TIER_KEY = "tier"
ALT_UNITS_KEY = "alt_units"
ENTRY_KEY = "entry_usd"
CURRENT_KEY = "current_usd_approx"
DELTA_KEY = "delta_pct_usd_approx"
CORRECTIONS_KEY = "corrections_fired"
OPENED_AT_KEY = "opened_at"

OUTCOME_DECLINED = "declined"
OUTCOME_NO_LOOP = "no_loop"
OUTCOME_SCHEDULE_FAILED = "schedule_failed"
OUTCOME_DISPATCHED = "dispatched"
NO_OUTCOME: Optional[str] = None

ACTIONS = {"fire_button.clicked": "fire_handler"}
TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()

BUILD_START = "build.start"
BUILD_FORM = "build.form"
BUILD_POOL_COLOR = "build.pool_color"
BUILD_POOL_FAILED = "build.pool_failed"
BUILD_SUMMARY_ROW = "build.summary_row"
BUILD_POSITIONS = "build.positions"
BUILD_POSITIONS_FAILED = "build.positions_failed"
BUILD_EMPTY = "build.empty"
BUILD_TABLE = "build.table"
BUILD_ROW = "build.row"
BUILD_FIRE_CONNECTED = "build.fire_connected"
BUILD_FOOTER = "build.footer"
BUILD_RETURN = "build.return"
FIRE_START = "fire.start"
FIRE_CONFIRM = "fire.confirm"
FIRE_DECLINED = "fire.declined"
FIRE_NO_LOOP = "fire.no_loop"
FIRE_CORO = "fire.coro"
FIRE_SCHEDULED = "fire.scheduled"
FIRE_SCHEDULE_FAILED = "fire.schedule_failed"
FIRE_DISPATCHED = "fire.dispatched"

ModelCall = list

CALL_NAMES = (
    BUILD_START,
    BUILD_FORM,
    BUILD_POOL_COLOR,
    BUILD_POOL_FAILED,
    BUILD_SUMMARY_ROW,
    BUILD_POSITIONS,
    BUILD_POSITIONS_FAILED,
    BUILD_EMPTY,
    BUILD_TABLE,
    BUILD_ROW,
    BUILD_FIRE_CONNECTED,
    BUILD_FOOTER,
    BUILD_RETURN,
    FIRE_START,
    FIRE_CONFIRM,
    FIRE_DECLINED,
    FIRE_NO_LOOP,
    FIRE_CORO,
    FIRE_SCHEDULED,
    FIRE_SCHEDULE_FAILED,
    FIRE_DISPATCHED,
)


def pool_color_hex(pool_color: Any) -> str:
    """The colour the pool line is drawn in, grey for a name nobody set."""
    return POOL_COLOR_HEX.get(pool_color, POOL_UNKNOWN_HEX)


def marked_text(wrap: Any, pieces: list) -> str:
    """The Qt rich text one wrapped list of pieces builds."""
    body = NO_PIECE
    for kind, piece in pieces:
        if kind == STRONG_PIECE:
            body += STRONG_OPEN + str(piece) + STRONG_CLOSE
        elif kind == BREAK_PIECE:
            body += BREAK_TAG * int(piece)
        else:
            body += str(piece)
    if wrap == ITALIC_WRAP:
        return ITALIC_OPEN + body + ITALIC_CLOSE
    return body


def pool_name(pool_color: Any) -> str:
    """The pool colour in capitals, whatever kind of value it arrived as."""
    return str(pool_color).upper()


def pool_pieces(pool_color: Any) -> list:
    """The one emphasised piece the pool line is built from."""
    return [[STRONG_PIECE, pool_name(pool_color)]]


def pool_text(pool_color: Any) -> str:
    """The pool line, in capitals and emphasised."""
    return marked_text(POOL_WRAP, pool_pieces(pool_color))


def empty_pieces(pool_color: Any) -> list:
    """The pieces the no-positions line is built from."""
    return [
        [PLAIN_PIECE, EMPTY_LEAD],
        [STRONG_PIECE, pool_name(pool_color)],
        [PLAIN_PIECE, EMPTY_TAIL],
    ]


def empty_text(pool_color: Any) -> str:
    """The no-positions line, naming the pool colour that was measured."""
    return marked_text(EMPTY_WRAP, empty_pieces(pool_color))


READ_FAILED_PIECES = [
    [PLAIN_PIECE, READ_FAILED_LEAD],
    [STRONG_PIECE, READ_FAILED_STRONG],
    [PLAIN_PIECE, READ_FAILED_TAIL],
]
READ_FAILED_TEXT = marked_text(EMPTY_WRAP, READ_FAILED_PIECES)

FOOTER_PIECES = [[STRONG_PIECE, FOOTER_STRONG], [PLAIN_PIECE, FOOTER_TAIL]]
FOOTER_TEXT = marked_text(FOOTER_WRAP, FOOTER_PIECES)

EMPTY_TEXT = empty_text(POOL_FALLBACK)


def confirm_pieces(pair: Any) -> list:
    """The pieces the confirm question is built from."""
    return [
        [PLAIN_PIECE, CONFIRM_LEAD],
        [STRONG_PIECE, pair],
        [PLAIN_PIECE, CONFIRM_TAIL_ONE],
        [BREAK_PIECE, CONFIRM_BREAKS],
        [PLAIN_PIECE, CONFIRM_TAIL_TWO],
        [BREAK_PIECE, CONFIRM_BREAKS],
        [PLAIN_PIECE, CONFIRM_TAIL_THREE],
    ]


def dispatched_pieces(pair: Any) -> list:
    """The pieces the dispatched line is built from."""
    return [
        [PLAIN_PIECE, DISPATCHED_LEAD],
        [STRONG_PIECE, pair],
        [PLAIN_PIECE, DISPATCHED_TAIL],
    ]


CONFIRM_TEXT_FORMAT = marked_text(CONFIRM_WRAP, confirm_pieces("{pair}"))
DISPATCHED_TEXT_FORMAT = marked_text(DISPATCHED_WRAP, dispatched_pieces("{pair}"))


def state_color(state: Any) -> str:
    """Red while the position is down, amber while it waits, green otherwise."""
    if state == STATE_DRAWDOWN:
        return DRAWDOWN_COLOR
    if state == STATE_BULLISH_EXIT:
        return BULLISH_EXIT_COLOR
    return OPEN_STATE_COLOR


def delta_color(delta_pct: Any) -> Optional[str]:
    """Green above break-even, red below it, no colour exactly at it."""
    if delta_pct > 0:
        return DELTA_UP_COLOR
    if delta_pct < 0:
        return DELTA_DOWN_COLOR
    return NO_CELL_COLOR


def read_whole(raw: Any, fallback: Any) -> list:
    """One whole-number reading, beside whether it could be read at all."""
    try:
        return [int(raw), True]
    except (TypeError, ValueError, OverflowError):
        return [fallback, False]


def read_amount(raw: Any, fallback: Any) -> list:
    """One amount reading, beside whether it could be read at all."""
    try:
        return [float(raw), True]
    except (TypeError, ValueError, OverflowError):
        return [fallback, False]


_NUMBER_PLAN = (
    ("tier", TIER_KEY, DEFAULT_TIER, True),
    ("alt_units", ALT_UNITS_KEY, DEFAULT_ALT_UNITS, False),
    ("entry_usd", ENTRY_KEY, DEFAULT_ENTRY_USD, False),
    ("current_usd", CURRENT_KEY, DEFAULT_CURRENT_USD, False),
    ("delta_pct", DELTA_KEY, DEFAULT_DELTA_PCT, False),
    ("corrections", CORRECTIONS_KEY, DEFAULT_CORRECTIONS, True),
)


def position_values(position: dict) -> dict:
    """The nine readings one open position hands the table row.

    A number the position does not carry, and one that cannot be read,
    are both named in ``unreadable`` so no row prints an invented value.
    """
    read = {
        "pair": str(position.get(PAIR_KEY, DEFAULT_PAIR)),
        "state": str(position.get(STATE_KEY, DEFAULT_STATE)),
        "opened_at": str(position.get(OPENED_AT_KEY, DEFAULT_OPENED_AT)),
    }
    unreadable = []
    for name, key, fallback, whole in _NUMBER_PLAN:
        if key not in position:
            read[name] = fallback
            unreadable.append(name)
            continue
        value, taken = (read_whole if whole else read_amount)(position[key], fallback)
        read[name] = value
        if not taken:
            unreadable.append(name)
    read["unreadable"] = unreadable
    return read


def position_identity(position: dict) -> list:
    """The pair and the opening stamp one position is told apart by."""
    read = position_values(position)
    return [read["pair"], read["opened_at"]]


def row_cells(position: dict) -> list:
    """The eight cell texts one open position fills a table row with."""
    read = position_values(position)
    cells = [
        PAIR_FORMAT.format(pair=read["pair"]),
        read["state"].upper(),
        TIER_FORMAT.format(tier=read["tier"]),
        ALT_UNITS_FORMAT.format(alt_units=read["alt_units"]),
        ENTRY_FORMAT.format(entry_usd=read["entry_usd"]),
        CURRENT_FORMAT.format(current_usd=read["current_usd"]),
        DELTA_FORMAT.format(delta_pct=read["delta_pct"]),
        CORRECTIONS_FORMAT.format(corrections=read["corrections"]),
    ]
    for name in read["unreadable"]:
        cells[UNREADABLE_COLUMNS[name]] = UNREADABLE_TEXT
    return cells


def row_colors(position: dict) -> list:
    """The colour each cell of one row is drawn in, or none where default."""
    read = position_values(position)
    colors: list = [NO_CELL_COLOR] * CELL_COLUMN_COUNT
    colors[STATE_COLUMN] = state_color(read["state"])
    colors[DELTA_COLUMN] = delta_color(read["delta_pct"])
    for name in read["unreadable"]:
        colors[UNREADABLE_COLUMNS[name]] = UNREADABLE_COLOR
    return colors


def row_unreadable(position: dict) -> list:
    """The columns of one row carrying no value the position could be read for."""
    read = position_values(position)
    return sorted(UNREADABLE_COLUMNS[name] for name in read["unreadable"])


def summary_rows(base_currency: Any, chunk: dict) -> list:
    """The three labelled money lines under the pool line."""
    return [
        [
            CHUNK_SIZE_ROW_FORMAT.format(base_currency=base_currency),
            CHUNK_SIZE_VALUE_FORMAT.format(
                chunk_size_base=chunk["chunk_size_base"],
                chunk_size_usd=chunk["chunk_size_usd"],
            ),
        ],
        [
            CHUNK_FREE_ROW_FORMAT.format(base_currency=base_currency),
            CHUNK_FREE_VALUE_FORMAT.format(chunk_free_base=chunk["chunk_free_base"]),
        ],
        [
            EXTRACTED_ROW_FORMAT.format(base_currency=base_currency),
            EXTRACTED_VALUE_FORMAT.format(extracted_total=chunk["extracted_total"]),
        ],
    ]


def confirm_text(pair: Any) -> str:
    """The question the operator answers before a position is closed."""
    return marked_text(CONFIRM_WRAP, confirm_pieces(pair))


def dispatched_text(pair: Any) -> str:
    """The line shown once the close is handed to the bot manager's loop."""
    return marked_text(DISPATCHED_WRAP, dispatched_pieces(pair))


def schedule_failed_text(error: Any, message: Any) -> str:
    """The line shown when the close could not be handed to the loop."""
    return SCHEDULE_FAILED_TEXT_FORMAT.format(error=error, message=message)


def message_box(
    icon: str,
    title: str,
    wrap: str,
    pieces: list,
    buttons_value: int,
    default_button_value: int,
) -> dict:
    """One message box the tab raises, its text beside the pieces building it."""
    return {
        "icon": icon,
        "title": title,
        "text": marked_text(wrap, pieces),
        "wrap": wrap,
        "pieces": [list(piece) for piece in pieces],
        "buttons_value": buttons_value,
        "default_button_value": default_button_value,
    }


def confirm_box(pair: Any) -> dict:
    """The Yes or No box shown before one position is closed."""
    return message_box(
        QUESTION_ICON,
        CONFIRM_TITLE,
        CONFIRM_WRAP,
        confirm_pieces(pair),
        CONFIRM_BUTTONS_VALUE,
        CONFIRM_DEFAULT_BUTTON_VALUE,
    )


def no_loop_box() -> dict:
    """The box shown when the bot manager has no loop to run the close on."""
    return message_box(
        WARNING_ICON,
        NO_LOOP_TITLE,
        NO_WRAP,
        [[PLAIN_PIECE, NO_LOOP_TEXT]],
        OK_BUTTON_VALUE,
        NO_DEFAULT_BUTTON_VALUE,
    )


def schedule_failed_box(error: Any, message: Any) -> dict:
    """The box shown when the close could not be handed to the loop."""
    return message_box(
        WARNING_ICON,
        SCHEDULE_FAILED_TITLE,
        NO_WRAP,
        [[PLAIN_PIECE, schedule_failed_text(error, message)]],
        OK_BUTTON_VALUE,
        NO_DEFAULT_BUTTON_VALUE,
    )


def dispatched_box(pair: Any) -> dict:
    """The box shown once the close is on its way to the exchange."""
    return message_box(
        INFORMATION_ICON,
        DISPATCHED_TITLE,
        DISPATCHED_WRAP,
        dispatched_pieces(pair),
        OK_BUTTON_VALUE,
        NO_DEFAULT_BUTTON_VALUE,
    )


class BotConfig:
    """The one config reading the tab takes: the bot's base currency."""

    def __init__(self, base_currency: Any = None) -> None:
        self.base_currency = base_currency


class BotSource:
    """The Extractor bot the tab reads, taken from plain data.

    ``pool_color`` and ``positions_for_gui`` raise when the caller asked
    for a failing reading, which is how the tab's two guarded reads are
    driven. ``manual_fire_position`` records the pair it was asked to
    close and returns a stand-in for the coroutine the real bot returns.
    """

    def __init__(
        self,
        base_currency: Any = None,
        chunk_size_usd: Any = DEFAULT_CHUNK_USD,
        chunk_free_base: Any = DEFAULT_CHUNK_BASE,
        chunk_size_base: Any = DEFAULT_CHUNK_BASE,
        extracted_total: Any = DEFAULT_CHUNK_BASE,
        pool_color_name: Any = POOL_GREEN,
        positions: Any = None,
        pool_color_raises: Optional[BaseException] = None,
        positions_raise: Optional[BaseException] = None,
        fire_raises: Optional[BaseException] = None,
    ) -> None:
        self.config = BotConfig(base_currency)
        setattr(self, CHUNK_SIZE_USD_ATTRIBUTE, chunk_size_usd)
        setattr(self, CHUNK_FREE_BASE_ATTRIBUTE, chunk_free_base)
        setattr(self, CHUNK_SIZE_BASE_ATTRIBUTE, chunk_size_base)
        setattr(self, EXTRACTED_TOTAL_ATTRIBUTE, extracted_total)
        self.pool_color_name = pool_color_name
        self.positions = list(positions or [])
        self.pool_color_raises = pool_color_raises
        self.positions_raise = positions_raise
        self.fire_raises = fire_raises
        self.fired: list = []

    def pool_color(self) -> Any:
        if self.pool_color_raises is not None:
            raise self.pool_color_raises
        return self.pool_color_name

    def positions_for_gui(self) -> list:
        if self.positions_raise is not None:
            raise self.positions_raise
        return self.positions

    def manual_fire_position(self, pair: Any) -> list:
        if self.fire_raises is not None:
            raise self.fire_raises
        self.fired.append(pair)
        return ["close", pair]


class ManagerSource:
    """The bot manager the fire path asks for its async loop."""

    def __init__(self, loop: Any = None) -> None:
        setattr(self, ASYNC_LOOP_ATTRIBUTE, loop)


class ScheduleSink:
    """Where a scheduled close is handed, and what it does with it.

    ``run`` records the coroutine and the loop it was given, and raises
    when the caller asked for a failing hand-off.
    """

    def __init__(self, raises: Optional[BaseException] = None) -> None:
        self.raises = raises
        self.scheduled: list = []

    def run(self, coro: Any, loop: Any) -> int:
        if self.raises is not None:
            raise self.raises
        self.scheduled.append([coro, loop])
        return len(self.scheduled)


class PositionsHeldTabModel:
    """The Positions Held tab's summary, table rows, buttons and fire path.

    ``build`` fills the four summary lines and either the empty-state
    line or the table. ``fire_handler`` returns the callable one Fire
    button runs; ``fire`` runs it with the answer the operator gave.
    Every step is appended to ``calls`` in the order the shipped tab
    makes it.
    """

    def __init__(
        self, bot: Any = None, manager: Any = None, schedule: Any = None
    ) -> None:
        self.bot = bot
        self.manager = manager
        self.schedule = schedule if schedule is not None else ScheduleSink()
        self.accessible_name = ACCESSIBLE_NAME
        self.form_configured = False
        self.pool_color = POOL_FALLBACK
        self.pool_text = pool_text(POOL_FALLBACK)
        self.pool_pieces = pool_pieces(POOL_FALLBACK)
        self.pool_style = POOL_STYLE_FORMAT.format(
            color_hex=pool_color_hex(POOL_FALLBACK)
        )
        self.summary_rows: list = []
        self.rows: list = []
        self.row_colors: list = []
        self.row_unreadable: list = []
        self.fire_pairs: list = []
        self.fire_identities: list = []
        self.table_shown = False
        self.empty_shown = False
        self.positions_read_failed = False
        self.empty_text = EMPTY_TEXT
        self.empty_pieces = empty_pieces(POOL_FALLBACK)
        self.footer_shown = False
        self.boxes: list = []
        self.outcome: Optional[str] = NO_OUTCOME
        self.calls: list[ModelCall] = []

    def build(self) -> None:
        """Fill the summary, then either the empty line or the table.

        No open position leaves the table and the footer out, exactly as
        the shipped tab returns early from the same branch.
        """
        self.calls.append([BUILD_START])
        self.form_configured = SUMMARY_FORM_CONFIGURED_BY_HOST
        self.calls.append([BUILD_FORM])
        chunk = {
            "chunk_size_usd": float(
                getattr(self.bot, CHUNK_SIZE_USD_ATTRIBUTE, DEFAULT_CHUNK_USD)
                or DEFAULT_CHUNK_USD
            ),
            "chunk_free_base": float(
                getattr(self.bot, CHUNK_FREE_BASE_ATTRIBUTE, DEFAULT_CHUNK_BASE)
                or DEFAULT_CHUNK_BASE
            ),
            "chunk_size_base": float(
                getattr(self.bot, CHUNK_SIZE_BASE_ATTRIBUTE, DEFAULT_CHUNK_BASE)
                or DEFAULT_CHUNK_BASE
            ),
            "extracted_total": float(
                getattr(self.bot, EXTRACTED_TOTAL_ATTRIBUTE, DEFAULT_CHUNK_BASE)
                or DEFAULT_CHUNK_BASE
            ),
        }
        base_currency = self.bot.config.base_currency
        try:
            self.pool_color = self.bot.pool_color()
            self.calls.append([BUILD_POOL_COLOR, self.pool_color])
        except Exception:
            self.pool_color = POOL_FALLBACK
            self.calls.append([BUILD_POOL_FAILED])
        self.pool_text = pool_text(self.pool_color)
        self.pool_pieces = pool_pieces(self.pool_color)
        self.pool_style = POOL_STYLE_FORMAT.format(
            color_hex=pool_color_hex(self.pool_color)
        )
        self.summary_rows = [[POOL_ROW_LABEL, self.pool_text]]
        self.summary_rows.extend(summary_rows(base_currency, chunk))
        for label, value in self.summary_rows:
            self.calls.append([BUILD_SUMMARY_ROW, label, value])

        try:
            positions = self.bot.positions_for_gui()
            self.calls.append([BUILD_POSITIONS, len(positions)])
        except Exception:
            positions = []
            self.positions_read_failed = True
            self.calls.append([BUILD_POSITIONS_FAILED])

        if not positions:
            self.empty_shown = True
            if self.positions_read_failed:
                self.empty_pieces = [list(one) for one in READ_FAILED_PIECES]
            else:
                self.empty_pieces = empty_pieces(self.pool_color)
            self.empty_text = marked_text(EMPTY_WRAP, self.empty_pieces)
            self.calls.append([BUILD_EMPTY])
            self.calls.append([BUILD_RETURN, 0])
            return None

        self.table_shown = True
        self.calls.append([BUILD_TABLE, len(positions)])
        for index, position in enumerate(positions):
            self.rows.append(row_cells(position))
            self.row_colors.append(row_colors(position))
            self.row_unreadable.append(row_unreadable(position))
            identity = position_identity(position)
            pair = identity[0]
            self.fire_pairs.append(pair)
            self.fire_identities.append(identity)
            self.calls.append([BUILD_ROW, index, pair])
            self.calls.append([BUILD_FIRE_CONNECTED, index, pair])
        self.footer_shown = True
        self.calls.append([BUILD_FOOTER])
        self.calls.append([BUILD_RETURN, len(self.rows)])
        return None

    def fire_handler(self, identity: Any):
        """The callable one Fire button runs, bound to its own position."""

        def run(answer: Any) -> Optional[str]:
            return self.fire(identity, answer)

        return run

    def fire(self, identity: Any, answer: Any) -> Optional[str]:
        """Close the position ``identity`` names, and report the path taken.

        ``identity`` is the pair and the opening stamp, so two rows on
        one pair stay apart. An answer other than Yes leaves the position
        open. A missing async loop and a hand-off that raises each raise
        their own warning box and stop.
        """
        pair = identity_pair(identity)
        self.calls.append([FIRE_START, pair])
        self.boxes.append(confirm_box(pair))
        self.calls.append([FIRE_CONFIRM, pair])
        if answer != YES_BUTTON_VALUE:
            self.outcome = OUTCOME_DECLINED
            self.calls.append([FIRE_DECLINED, pair])
            return self.outcome

        loop = (
            getattr(self.manager, ASYNC_LOOP_ATTRIBUTE, None) if self.manager else None
        )
        if loop is None:
            self.boxes.append(no_loop_box())
            self.outcome = OUTCOME_NO_LOOP
            self.calls.append([FIRE_NO_LOOP, pair])
            return self.outcome

        coro = self.bot.manual_fire_position(pair)
        self.calls.append([FIRE_CORO, pair])
        try:
            self.schedule.run(coro, loop)
            self.calls.append([FIRE_SCHEDULED, pair])
        except Exception as exc:
            self.boxes.append(schedule_failed_box(type(exc).__name__, str(exc)))
            self.outcome = OUTCOME_SCHEDULE_FAILED
            self.calls.append([FIRE_SCHEDULE_FAILED, pair, type(exc).__name__])
            return self.outcome

        self.boxes.append(dispatched_box(pair))
        self.outcome = OUTCOME_DISPATCHED
        self.calls.append([FIRE_DISPATCHED, pair])
        return self.outcome


def identity_pair(identity: Any) -> str:
    """The pair one identity names, whichever shape the identity arrived in."""
    if isinstance(identity, (list, tuple)) and identity:
        return str(identity[0])
    return str(identity)


def build_view_model(
    model: PositionsHeldTabModel,
    build_now: bool = False,
    fire_identity: Any = None,
    fire_answer: Any = None,
) -> dict:
    """Return every value the Positions Held tab holds as one dict.

    `build_now` reads the bot and fills the summary and the table.
    `fire_identity` runs that row's Fire button with `fire_answer`.
    """
    if build_now:
        model.build()
    if fire_identity is not None:
        model.fire_handler(fire_identity)(fire_answer)
    return {
        "accessible_name": model.accessible_name,
        "container": {
            "spacing_px": CONTENT_SPACING_PX,
            "margins_set": CONTENT_MARGINS_SET,
        },
        "summary_group": {"title": SUMMARY_GROUP_TITLE},
        "summary_form": {
            "configured_by_host": SUMMARY_FORM_CONFIGURED_BY_HOST,
            "configured": model.form_configured,
        },
        "pool_label": {
            "text": model.pool_text,
            "style_sheet": model.pool_style,
            "wrap": POOL_WRAP,
            "pieces": [list(one) for one in model.pool_pieces],
        },
        "pool_color": model.pool_color,
        "pool_color_hex": pool_color_hex(model.pool_color),
        "summary_rows": [list(row) for row in model.summary_rows],
        "empty_label": {
            "text": model.empty_text,
            "style_sheet": EMPTY_STYLE,
            "word_wrap": EMPTY_WORD_WRAP,
            "shown": model.empty_shown,
            "wrap": EMPTY_WRAP,
            "pieces": [list(one) for one in model.empty_pieces],
            "read_failed": model.positions_read_failed,
        },
        "positions_table": {
            "columns": list(COLUMNS),
            "column_count": COLUMN_COUNT,
            "cell_column_count": CELL_COLUMN_COUNT,
            "header_resize_mode": HEADER_RESIZE_MODE,
            "vertical_header_visible": VERTICAL_HEADER_VISIBLE,
            "edit_triggers": EDIT_TRIGGERS,
            "selection_behavior": SELECTION_BEHAVIOR,
            "alternating_row_colors": ALTERNATING_ROW_COLORS,
            "cell_alignment": CELL_ALIGNMENT,
            "cell_alignment_value": CELL_ALIGNMENT_VALUE,
            "state_column": STATE_COLUMN,
            "delta_column": DELTA_COLUMN,
            "fire_column": FIRE_COLUMN,
            "stretch": TABLE_STRETCH,
            "row_count": len(model.rows),
            "rows": [list(row) for row in model.rows],
            "row_colors": [list(row) for row in model.row_colors],
            "row_unreadable": [list(row) for row in model.row_unreadable],
            "unreadable_rows": [
                at for at, row in enumerate(model.row_unreadable) if row
            ],
            "shown": model.table_shown,
        },
        "fire_button": {
            "text": FIRE_BUTTON_TEXT,
            "fixed_height_px": FIRE_BUTTON_HEIGHT_PX,
            "style_sheet": FIRE_BUTTON_STYLE,
            "pairs": list(model.fire_pairs),
            "identities": [list(one) for one in model.fire_identities],
        },
        "footer_label": {
            "text": FOOTER_TEXT,
            "style_sheet": FOOTER_STYLE,
            "word_wrap": FOOTER_WORD_WRAP,
            "shown": model.footer_shown,
            "wrap": FOOTER_WRAP,
            "pieces": [list(one) for one in FOOTER_PIECES],
        },
        "boxes": [dict(one) for one in model.boxes],
        "fire_outcome": model.outcome,
        "pool_names": [POOL_GREEN, POOL_YELLOW, POOL_RED],
        "pool_fallback": POOL_FALLBACK,
        "pool_color_map": dict(POOL_COLOR_HEX),
        "pool_unknown_hex": POOL_UNKNOWN_HEX,
        "state_names": [STATE_DRAWDOWN, STATE_BULLISH_EXIT],
        "colors": {
            "drawdown": DRAWDOWN_COLOR,
            "bullish_exit": BULLISH_EXIT_COLOR,
            "open_state": OPEN_STATE_COLOR,
            "delta_up": DELTA_UP_COLOR,
            "delta_down": DELTA_DOWN_COLOR,
            "unreadable": UNREADABLE_COLOR,
        },
        "no_cell_color": NO_CELL_COLOR,
        "no_outcome": NO_OUTCOME,
        "outcomes": [
            OUTCOME_DECLINED,
            OUTCOME_NO_LOOP,
            OUTCOME_SCHEDULE_FAILED,
            OUTCOME_DISPATCHED,
        ],
        "icons": {
            "question": QUESTION_ICON,
            "warning": WARNING_ICON,
            "information": INFORMATION_ICON,
        },
        "button_values": {
            "yes": YES_BUTTON_VALUE,
            "no": NO_BUTTON_VALUE,
            "ok": OK_BUTTON_VALUE,
            "confirm_buttons": CONFIRM_BUTTONS_VALUE,
            "confirm_default": CONFIRM_DEFAULT_BUTTON_VALUE,
            "no_default": NO_DEFAULT_BUTTON_VALUE,
        },
        "titles": {
            "confirm": CONFIRM_TITLE,
            "no_loop": NO_LOOP_TITLE,
            "schedule_failed": SCHEDULE_FAILED_TITLE,
            "dispatched": DISPATCHED_TITLE,
        },
        "marks": dict(MARK_TAGS),
        "piece_kinds": list(PIECE_KINDS),
        "wrap_kinds": list(WRAP_KINDS),
        "pieces": {
            "empty_lead": EMPTY_LEAD,
            "empty_tail": EMPTY_TAIL,
            "read_failed_lead": READ_FAILED_LEAD,
            "read_failed_strong": READ_FAILED_STRONG,
            "read_failed_tail": READ_FAILED_TAIL,
            "read_failed": [list(one) for one in READ_FAILED_PIECES],
            "footer_strong": FOOTER_STRONG,
            "footer_tail": FOOTER_TAIL,
            "confirm_lead": CONFIRM_LEAD,
            "confirm_tail_one": CONFIRM_TAIL_ONE,
            "confirm_tail_two": CONFIRM_TAIL_TWO,
            "confirm_tail_three": CONFIRM_TAIL_THREE,
            "confirm_breaks": CONFIRM_BREAKS,
            "confirm_wrap": CONFIRM_WRAP,
            "dispatched_lead": DISPATCHED_LEAD,
            "dispatched_tail": DISPATCHED_TAIL,
            "dispatched_wrap": DISPATCHED_WRAP,
        },
        "unreadable": {
            "text": UNREADABLE_TEXT,
            "columns": dict(UNREADABLE_COLUMNS),
        },
        "texts": {"no_loop": NO_LOOP_TEXT, "read_failed": READ_FAILED_TEXT},
        "formats": {
            "pool_text": POOL_TEXT_FORMAT,
            "pool_style": POOL_STYLE_FORMAT,
            "chunk_size_row": CHUNK_SIZE_ROW_FORMAT,
            "chunk_free_row": CHUNK_FREE_ROW_FORMAT,
            "extracted_row": EXTRACTED_ROW_FORMAT,
            "chunk_size_value": CHUNK_SIZE_VALUE_FORMAT,
            "chunk_free_value": CHUNK_FREE_VALUE_FORMAT,
            "extracted_value": EXTRACTED_VALUE_FORMAT,
            "pair": PAIR_FORMAT,
            "tier": TIER_FORMAT,
            "alt_units": ALT_UNITS_FORMAT,
            "entry": ENTRY_FORMAT,
            "current": CURRENT_FORMAT,
            "delta": DELTA_FORMAT,
            "corrections": CORRECTIONS_FORMAT,
            "confirm_text": CONFIRM_TEXT_FORMAT,
            "schedule_failed_text": SCHEDULE_FAILED_TEXT_FORMAT,
            "dispatched_text": DISPATCHED_TEXT_FORMAT,
        },
        "labels": {"pool_row": POOL_ROW_LABEL},
        "keys": {
            "pair": PAIR_KEY,
            "state": STATE_KEY,
            "tier": TIER_KEY,
            "alt_units": ALT_UNITS_KEY,
            "entry": ENTRY_KEY,
            "current": CURRENT_KEY,
            "delta": DELTA_KEY,
            "corrections": CORRECTIONS_KEY,
            "opened_at": OPENED_AT_KEY,
        },
        "attributes": {
            "chunk_size_usd": CHUNK_SIZE_USD_ATTRIBUTE,
            "chunk_free_base": CHUNK_FREE_BASE_ATTRIBUTE,
            "chunk_size_base": CHUNK_SIZE_BASE_ATTRIBUTE,
            "extracted_total": EXTRACTED_TOTAL_ATTRIBUTE,
            "async_loop": ASYNC_LOOP_ATTRIBUTE,
        },
        "defaults": {
            "chunk_usd": DEFAULT_CHUNK_USD,
            "chunk_base": DEFAULT_CHUNK_BASE,
            "pair": DEFAULT_PAIR,
            "state": DEFAULT_STATE,
            "tier": DEFAULT_TIER,
            "alt_units": DEFAULT_ALT_UNITS,
            "entry_usd": DEFAULT_ENTRY_USD,
            "current_usd": DEFAULT_CURRENT_USD,
            "delta_pct": DEFAULT_DELTA_PCT,
            "corrections": DEFAULT_CORRECTIONS,
            "opened_at": DEFAULT_OPENED_AT,
        },
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "call_names": list(CALL_NAMES),
        "calls": [list(call) for call in model.calls],
    }


PANE_MODEL = PositionsHeldTabModel()


def view_model(params: dict) -> dict:
    """Bridge handler for ``positions_held_tab.state``.

    Reads ``reset``, ``bot``, ``manager``, ``schedule_error``, ``build``,
    ``fire_identity`` and ``fire_answer`` from the request parameters.
    ``schedule_error`` is what makes the loop hand-off refuse, which is
    the fourth fire path. The tab's last state persists between calls
    because the tab does; ``reset`` is what a fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = PositionsHeldTabModel()
    schedule_error = params.get("schedule_error")
    if schedule_error is not None:
        PANE_MODEL.schedule = ScheduleSink(RuntimeError(str(schedule_error)))
    bot = params.get("bot")
    if bot is not None:
        PANE_MODEL.bot = BotSource(
            base_currency=bot.get("base_currency"),
            chunk_size_usd=bot.get("chunk_size_usd", DEFAULT_CHUNK_USD),
            chunk_free_base=bot.get("chunk_free_base", DEFAULT_CHUNK_BASE),
            chunk_size_base=bot.get("chunk_size_base", DEFAULT_CHUNK_BASE),
            extracted_total=bot.get("extracted_total", DEFAULT_CHUNK_BASE),
            pool_color_name=bot.get("pool_color", POOL_GREEN),
            positions=bot.get("positions"),
        )
    manager = params.get("manager")
    if manager is not None:
        PANE_MODEL.manager = ManagerSource(manager.get("async_loop"))
    return build_view_model(
        PANE_MODEL,
        params.get("build", bot is not None),
        params.get("fire_identity"),
        params.get("fire_answer"),
    )
