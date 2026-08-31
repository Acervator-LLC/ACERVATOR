"""stack_tranches_tab_surface.py -- the Stack Tranches tab, without Qt.

Describes the tab inside the live bot settings dialog that reports the
stack ladder. The tab holds a summary box of seven or eight rows, then
two clear buttons, then either an empty-state line or a detail box with
a header line and one line per tranche.

``StackTranchesTabModel`` holds the tab's state. ``build`` reads the bot
and fills the summary rows, the two buttons and the detail lines.
``refresh`` rebuilds the tab in place and reports why it could not.
``settle_after_clear`` saves, refreshes and reports the two lines the
operator reads. ``clear_tranches`` and ``clear_lifetime_counters`` run
the two clear paths and record every box they raise.

``BotConfig``, ``BotSource``, ``TabHost`` and ``StateSaver`` are plain
stand-ins for the bot, its config, the dialog's tab strip and the fleet
save, so the tab can be driven over the bridge from values alone.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``stack_tranches_tab.state`` method, which is how the Electron
renderer reaches it. Every value below is written out here rather than
read from ``src.gui.live_settings.stack_tranches_tab``, so a value
changed on one side alone is reported. Nothing here imports Qt, and
nothing here reads the clock: ``build`` takes the epoch second it ages
tranches against.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import design_system as ds

METHOD = "stack_tranches_tab.state"

TAB_LABEL = "Stack Tranches"

ACCESSIBLE_NAME = ""
CONTENT_SPACING_PX = 8
CONTENT_MARGINS_SET = False

TRANCHES_ATTRIBUTE = "_stack_tranches"
CREATED_ATTRIBUTE = "_stack_created"
DISCARDED_ATTRIBUTE = "_stack_discarded"
RESET_TS_ATTRIBUTE = "_stack_counters_reset_ts"
CLEAR_TRANCHES_ATTRIBUTE = "clear_stack_tranches"
CLEAR_COUNTERS_ATTRIBUTE = "clear_stack_lifetime_counters"

CLEAR_REASON = "operator (GUI)"

STATUS_PENDING = "pending"
STATUS_FILLED = "filled"
STATUS_CANCELLED = "cancelled"
STATUS_UNKNOWN = "unknown"

SIZE_KEY = "size"
INDEX_KEY = "index"
PRICE_KEY = "price"
FILL_PRICE_KEY = "fill_price"
OPENED_TS_KEY = "opened_ts"
STATUS_KEY = "status"
VISIBLE_KEY = "visible"
ORDER_ID_KEY = "order_id"

SUMMARY_GROUP_TITLE = "Stack-Tranche Cycle Health"
SUMMARY_FORM_CONFIGURED_BY_HOST = True

PENDING_ROW_LABEL = "Pending tranches:"
FILLED_ROW_LABEL = "Filled tranches:"
CANCELLED_ROW_LABEL = "Cancelled tranches:"
PENDING_SIZE_ROW_LABEL = "Pending size (unfilled):"
OLDEST_AGE_ROW_LABEL = "Oldest pending age:"
OPENED_ROW_LABEL = "Lifetime tranches opened:"
FILL_RATIO_ROW_LABEL = "Fill ratio (filled/opened):"
DISCARDED_ROW_LABEL = "Lifetime tranches discarded (delisted, not filled):"

COUNT_FORMAT = "{count}"
PENDING_SIZE_FORMAT = "{size_total:,.6f} base units"
UNREADABLE_SUFFIX_FORMAT = "  (+{unreadable} unreadable)"
PENDING_SIZE_STYLE = (
    f"font-weight: bold; font-size: 13px; color: {ds.FOLD_RATIO_AMBER};"
)

NO_VALUE = "—"
NO_TIMESTAMP_TEXT = "— (no timestamp)"
NO_PENDING_TEXT = "no pending tranches"

FILL_RATIO_FORMAT = "{ratio:.1%}  ({filled}/{created})"
FILL_RATIO_CLEARED_TEXT = "—  (counters cleared)"
FILL_RATIO_NEVER_OPENED_TEXT = "—  (no stacks opened yet)"

RATIO_STYLE_FORMAT = "color: {colour};"
RATIO_NO_STYLE = ""
RATIO_MIN_OPENED = 3
RATIO_RED_BELOW = 0.3
RATIO_AMBER_BELOW = 0.7
RATIO_RED = ds.ERROR
RATIO_AMBER = ds.FOLD_RATIO_AMBER
RATIO_GREEN = ds.SUCCESS

CLEAR_BUTTON_COUNTED_FORMAT = "Clear {droppable} Stack Tranche(s)"
CLEAR_BUTTON_PLAIN_TEXT = "Clear Stack Tranches"
CLEAR_BUTTON_TOOLTIP = (
    "Discard this bot's standing stack tranches.\n\n"
    "Places NO order and cancels NO order. Holdings, cost "
    "basis and target balance are untouched. A tranche "
    "holding a resting exchange order is KEPT - delisting "
    "it would leave that order on the book with nothing "
    "tracking it."
)

COUNTERS_BUTTON_COUNTED_FORMAT = "Clear Lifetime Counters ({created} opened)"
COUNTERS_BUTTON_PLAIN_TEXT = "Clear Lifetime Counters"
COUNTERS_BUTTON_TOOLTIP = (
    "Set this bot's two stack lifetime counters to "
    "zero.\n\n"
    "Places NO order and removes NO tranche. Standing stack "
    "tranches, holdings, cost basis and target balance are "
    "all untouched - this clears the record of what "
    "happened, not what the bot holds."
)

DANGER_BUTTON_STYLE = (
    f"QPushButton {{ background: {ds.SETTINGS_DANGER_SURFACE}; "
    f"color: {ds.FOLD_RATIO_AMBER}; "
    f"border: 1px solid {ds.ERROR}; padding: 6px 12px; }} "
    f"QPushButton:disabled {{ color: {ds.TEXT_MUTED}; "
    f"border-color: {ds.BORDER_DISABLED}; }}"
)

EMPTY_TEXT = (
    "No stack tranches yet. When Stack Mode is enabled "
    "and a SCRUM fires, tranches will appear here."
)
EMPTY_STYLE = f"color: {ds.CARD_METRIC_LABEL}; padding: 12px;"
EMPTY_WORD_WRAP = True

DETAIL_GROUP_TITLE_FORMAT = "Tranches ({count})"
HEADER_TEXT = (
    "  #  |  Target Price  |    Size      |  Mode     |  "
    "Status     |  Fill Price   |  Age"
)
HEADER_STYLE = (
    "font-family: monospace; font-weight: bold; "
    f"color: {ds.TEXT_INFO_SOFT}; padding: 2px;"
)

ROW_FORMAT = (
    "  {index} |  {price}  |  {size}  |  {mode:<9}|  "
    "{status:<10} |  {fill:<12} |  {age}"
)
ROW_BASE_STYLE = "font-family: monospace; padding: 1px;"
ROW_FILLED_STYLE = f" color: {ds.SUCCESS};"
ROW_CANCELLED_STYLE = f" color: {ds.ERROR};"
ROW_PLAIN_STYLE = ""

INDEX_FORMAT = "{value:>2}"
INDEX_REFUSED_FORMAT = "{dash:>2}"
PRICE_FORMAT = "${value:>10.8f}"
PRICE_REFUSED_FORMAT = "{dash:>11}"
SIZE_FORMAT = "{value:>10.6f}"
SIZE_REFUSED_FORMAT = "{dash:>10}"
FILL_FORMAT = "${value:.8f}"

MODE_VISIBLE = "VISIBLE"
MODE_INVISIBLE = "INVISIBLE"

AGE_SECONDS_MINUTE = 60
AGE_SECONDS_HOUR = 3600
AGE_SECONDS_DAY = 86400
AGE_SECONDS_FORMAT = "{whole}s"
AGE_MINUTES_FORMAT = "{whole}m"
AGE_HOURS_FORMAT = "{value:.1f}h"
AGE_DAYS_FORMAT = "{value:.1f}d"

REFRESHED = "refreshed"
NO_TAB_INSTALLED = "not refreshed: this dialog has no Stack " "Tranches tab installed"
TAB_NOT_LOCATED_FORMAT = "not refreshed: the tab could not be located ({error})"
TAB_GONE = "not refreshed: the Stack Tranches tab is no " "longer in this dialog"
REBUILD_RAISED_FORMAT = "not refreshed: rebuilding the tab raised {error}: {detail}"

REBUILT_LINE = (
    "The panel behind this message has been rebuilt " "and now shows the new state."
)
NOT_REBUILT_LINE_FORMAT = (
    "The panel was {refresh}. Close and reopen this " "dialog to see the new state."
)
SAVED_LINE = "Saved to disk."
NOT_SAVED_LINE_FORMAT = (
    "NOT SAVED TO DISK - {why}. The change holds in "
    "memory, and the platform's rolling save should "
    "write it within 60 seconds; a restart before "
    "that would bring it back."
)

CLEAR_TRANCHES_TITLE = "Clear stack tranches"
NOTHING_TO_DISCARD_TEXT = "This bot has no stack tranche this clear may " "discard."
KEPT_LIVE_NOTE_FORMAT = (
    "\n\n{live} tranche(s) hold resting " "exchange orders and are never delisted."
)
NO_CLEAR_SUPPORT_TEXT = "This bot type does not support clearing stack " "tranches."
CONFIRM_DISCARD_FORMAT = "Discard {droppable} stack tranche(s) for {symbol}?"
CONFIRM_NO_ORDER_TEXT = (
    "This places NO order and cancels NO order. Holdings, "
    "cost basis and target balance are untouched - only the "
    "queued intent to sell is discarded."
)
CONFIRM_UNDONE_TEXT = "This cannot be undone."
CONFIRM_LIVE_NOTE_FORMAT = (
    "NOTE - {live} tranche(s) hold resting "
    "exchange orders and are KEPT. Delisting a record "
    "that owns a live order would leave that order on "
    "the book with nothing tracking it."
)
CLEAR_FAILED_FORMAT = "Nothing was cleared - the call failed:\n\n{detail}"
DISCARDED_RESULT_FORMAT = (
    "Discarded {count} stack tranche(s) covering {size:.8f} base units."
)
KEPT_RESULT_FORMAT = (
    "No order was placed or cancelled. "
    "{kept} tranche(s) holding resting exchange "
    "orders were kept, and every holding, cost "
    "basis and target balance is unchanged."
)

CLEAR_COUNTERS_TITLE = "Clear stack lifetime counters"
COUNTERS_ALREADY_ZERO_TEXT = "This bot's lifetime stack counters already read " "zero."
NO_COUNTER_SUPPORT_TEXT = (
    "This bot type does not support clearing stack " "lifetime counters."
)
CONFIRM_COUNTERS_FORMAT = "Set the two lifetime stack counters for {symbol} to zero?"
CONFIRM_OPENED_LINE_FORMAT = "    opened    {opened}"
CONFIRM_DISCARDED_LINE_FORMAT = "    discarded {discarded}"
CONFIRM_COUNTERS_NO_ORDER_TEXT = (
    "This places NO order and removes NO tranche. Standing "
    "stack tranches, holdings, cost basis and target balance "
    "are all unchanged - this clears the record of what "
    "happened, not what the bot holds."
)
CONFIRM_STILL_HOLDS_FORMAT = (
    "NOTE - this bot still holds {open_now} stack "
    "tranche(s). The panel reconciles opened minus "
    "discarded against that count, so it will read 0 "
    "against {open_now} until the next stack opens. No "
    "tranche is lost."
)
COUNTERS_RESULT_FORMAT = (
    "Cleared {cleared} counted stack event(s): opened "
    "{opened} and discarded {discarded}."
)
COUNTERS_BOTH_ZERO_TEXT = "Both now read 0 for this bot."
COUNTERS_KEPT_FORMAT = (
    "No order was placed and no tranche was removed. "
    "This bot still holds {standing} stack tranche(s) and "
    "every holding it had."
)

BLANK_LINE = ""
BODY_JOIN = "\n"
RESULT_JOIN = "\n\n"

REPORT_COUNT_KEY = "count"
REPORT_SIZE_KEY = "size"
REPORT_KEPT_KEY = "kept_live_order"
REPORT_CLEARED_KEY = "cleared"
REPORT_BEFORE_KEY = "before"
REPORT_CREATED_KEY = "created"
REPORT_DISCARDED_KEY = "discarded"

INFORMATION_ICON = "information"
WARNING_ICON = "warning"
CRITICAL_ICON = "critical"
QUESTION_ICON = "warning_dialog"

YES_ANSWER = "yes"
NO_ANSWER = "cancel"
CONFIRM_DEFAULT_ANSWER = NO_ANSWER

ACTIONS = {
    "clear_button.clicked": "clear_tranches",
    "counters_button.clicked": "clear_lifetime_counters",
}

TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()
THREADS: tuple = ()
SIGNALS: tuple = ()
BUS_EMITS: tuple = ()

STEP_READ_BOT = "read_bot"
STEP_SUMMARY = "summary"
STEP_BUTTONS = "buttons"
STEP_EMPTY = "empty"
STEP_DETAIL = "detail"
STEP_NOTHING_TO_DISCARD = "nothing_to_discard"
STEP_NO_CLEAR_SUPPORT = "no_clear_support"
STEP_CONFIRM = "confirm"
STEP_DECLINED = "declined"
STEP_CALL_FAILED = "call_failed"
STEP_CLEARED = "cleared"
STEP_COUNTERS_ZERO = "counters_zero"
STEP_NO_COUNTER_SUPPORT = "no_counter_support"
STEP_COUNTERS_CLEARED = "counters_cleared"
STEP_SETTLED = "settled"

CALL_NAMES = (
    STEP_READ_BOT,
    STEP_SUMMARY,
    STEP_BUTTONS,
    STEP_EMPTY,
    STEP_DETAIL,
    STEP_NOTHING_TO_DISCARD,
    STEP_NO_CLEAR_SUPPORT,
    STEP_CONFIRM,
    STEP_DECLINED,
    STEP_CALL_FAILED,
    STEP_CLEARED,
    STEP_COUNTERS_ZERO,
    STEP_NO_COUNTER_SUPPORT,
    STEP_COUNTERS_CLEARED,
    STEP_SETTLED,
)

OUTCOME_NOTHING_TO_DISCARD = STEP_NOTHING_TO_DISCARD
OUTCOME_UNSUPPORTED = "unsupported"
OUTCOME_DECLINED = STEP_DECLINED
OUTCOME_FAILED = "failed"
OUTCOME_CLEARED = STEP_CLEARED
OUTCOME_ALREADY_ZERO = "already_zero"
OUTCOME_COUNTERS_CLEARED = STEP_COUNTERS_CLEARED

OUTCOMES = (
    OUTCOME_NOTHING_TO_DISCARD,
    OUTCOME_UNSUPPORTED,
    OUTCOME_DECLINED,
    OUTCOME_FAILED,
    OUTCOME_CLEARED,
    OUTCOME_ALREADY_ZERO,
    OUTCOME_COUNTERS_CLEARED,
)


def as_finite_float(value) -> Optional[float]:
    """`value` as a float when it is EXACTLY int or float AND finite.

    The one admission rule the tab reads every stored number through,
    imported from the trading package inside the call so that loading
    this module drags no trading code in.
    """
    from ...trading.bot_container import as_finite_float as admitted

    return admitted(value)


def format_age(seconds: float) -> str:
    """`seconds` as the age string the dialog prints beside a tranche.

    The dialog owns this helper and the tab calls it; the surface
    carries it so a payload can be built from values alone.
    """
    if seconds < AGE_SECONDS_MINUTE:
        return AGE_SECONDS_FORMAT.format(whole=int(seconds))
    if seconds < AGE_SECONDS_HOUR:
        return AGE_MINUTES_FORMAT.format(whole=int(seconds / AGE_SECONDS_MINUTE))
    if seconds < AGE_SECONDS_DAY:
        return AGE_HOURS_FORMAT.format(value=seconds / AGE_SECONDS_HOUR)
    return AGE_DAYS_FORMAT.format(value=seconds / AGE_SECONDS_DAY)


class BotConfig:
    """The bot config the tab reads its symbol from."""

    def __init__(self, symbol: str = ""):
        self.symbol = symbol


class BotSource:
    """The bot the tab reads its stack ledger and its counters from."""

    def __init__(
        self,
        tranches=None,
        created: Any = 0,
        discarded: Any = 0,
        reset_ts: Any = 0.0,
        symbol: str = "",
        clear_report=None,
        counters_report=None,
        clear_raises=None,
        counters_raises=None,
        with_config: bool = True,
        supports_clear: bool = True,
        supports_counters: bool = True,
    ):
        if with_config:
            self.config = BotConfig(symbol)
        setattr(self, TRANCHES_ATTRIBUTE, list(tranches or []))
        setattr(self, CREATED_ATTRIBUTE, created)
        setattr(self, DISCARDED_ATTRIBUTE, discarded)
        setattr(self, RESET_TS_ATTRIBUTE, reset_ts)
        self.clear_report = clear_report or {}
        self.counters_report = counters_report or {}
        self.clear_raises = clear_raises
        self.counters_raises = counters_raises
        self.cleared_with: list = []
        self.counters_cleared_with: list = []
        if supports_clear:
            self.clear_stack_tranches = self._discard_tranches
        if supports_counters:
            self.clear_stack_lifetime_counters = self._zero_counters

    def _discard_tranches(self, reason: str = ""):
        """Discard the standing stack tranches and report what went."""
        self.cleared_with.append(reason)
        if self.clear_raises is not None:
            raise self.clear_raises
        return self.clear_report

    def _zero_counters(self, reason: str = ""):
        """Zero the two lifetime counters and report what they held."""
        self.counters_cleared_with.append(reason)
        if self.counters_raises is not None:
            raise self.counters_raises
        return self.counters_report


class StateSaver:
    """The fleet save the clear paths run before they rebuild."""

    def __init__(self, saved: bool = True, why: str = ""):
        self.saved = saved
        self.why = why
        self.asked: list = []

    def save(self, what: str):
        """Persist the fleet and report ``(saved, reason)``."""
        self.asked.append(what)
        return (self.saved, self.why)


class TabHost:
    """The dialog's tab strip, as the refresh path uses it."""

    def __init__(
        self,
        installed: bool = True,
        index: int = 0,
        label: str = TAB_LABEL,
        current: int = 0,
        index_raises=None,
        rebuild_raises=None,
    ):
        self.installed = installed
        self.index = index
        self.label = label
        self.current = current
        self.index_raises = index_raises
        self.rebuild_raises = rebuild_raises
        self.removed: list = []
        self.inserted: list = []
        self.made_current: list = []
        self.deleted: list = []
        self.builds = 0

    def index_of(self) -> int:
        """Where the tab sits, or a negative number when it is gone."""
        if self.index_raises is not None:
            raise self.index_raises
        return self.index

    def tab_text(self, index: int) -> str:
        """The label the tab strip shows at `index`."""
        return self.label

    def current_index(self) -> int:
        """The tab the operator is looking at."""
        return self.current

    def rebuild(self):
        """Build a fresh page for the tab, or raise as the build would."""
        if self.rebuild_raises is not None:
            raise self.rebuild_raises
        self.builds += 1
        return "page %d" % self.builds

    def remove_tab(self, index: int) -> None:
        """Take the tab out of the strip at `index`."""
        self.removed.append(index)

    def insert_tab(self, index: int, page, label: str) -> None:
        """Put `page` back at `index` under `label`."""
        self.inserted.append((index, page, label))

    def set_current_index(self, index: int) -> None:
        """Bring the tab at `index` back to the front."""
        self.made_current.append(index)

    def delete_page(self, page) -> None:
        """Drop the page the strip reparented rather than deleted."""
        self.deleted.append(page)


class TabState:
    """Everything one build of the tab puts on the screen.

    A fresh one is what a rebuilt tab starts from, so the defaults live
    here once and no build inherits a value from the build before it.
    """

    def __init__(self):
        self.calls: list = []
        self.boxes: list = []
        self.summary_rows: list = []
        self.summary_styles: list = []
        self.pending_count = 0
        self.filled_count = 0
        self.cancelled_count = 0
        self.pending_size_total = 0.0
        self.pending_size_unreadable = 0
        self.created_lifetime = 0
        self.discarded_lifetime = 0
        self.reset_ts = 0.0
        self.droppable = 0
        self.live_order_count = 0
        self.clear_button_text = CLEAR_BUTTON_PLAIN_TEXT
        self.clear_button_enabled = False
        self.counters_button_text = COUNTERS_BUTTON_PLAIN_TEXT
        self.counters_button_enabled = False
        self.detail_rows: list = []
        self.detail_styles: list = []
        self.detail_title = DETAIL_GROUP_TITLE_FORMAT.format(count=0)
        self.empty_shown = False
        self.detail_shown = False
        self.forms_configured = 0
        self.outcome: Optional[str] = None
        self.settled_lines: list = []
        self.refresh_status = ""


class StackTranchesTabModel:
    """The Stack Tranches tab, as values.

    Stands in for ``StackTranchesTabMixin``. ``build`` fills the rows
    the operator reads; the two clear methods run the paths the two
    buttons run.
    """

    def __init__(self, bot=None, saver=None, host=None):
        self.bot = bot
        self.saver = saver
        self.host = host
        self.state = TabState()

    def _record(self, name: str) -> None:
        self.state.calls.append(name)

    def _box(self, icon: str, title: str, text: str) -> None:
        self.state.boxes.append({"icon": icon, "title": title, "text": text})

    def _tranches(self) -> list:
        return list(getattr(self.bot, TRANCHES_ATTRIBUTE, []) or [])

    def _symbol(self) -> str:
        return getattr(getattr(self.bot, "config", None), "symbol", "")

    def _droppable_of(self, tranches: list) -> tuple:
        live = [
            row
            for row in tranches
            if row.get(STATUS_KEY) == STATUS_PENDING and row.get(ORDER_ID_KEY)
        ]
        return (len(tranches) - len(live), len(live))

    def build(self, now_ts: float):
        """Fill every row, button and line the tab shows.

        `now_ts` is the epoch second every pending age is measured
        against. It is a parameter and never a clock reading, so one
        input always produces one payload.
        """
        self.state = TabState()
        self._record(STEP_READ_BOT)
        tranches = self._tranches()
        self.state.created_lifetime = int(getattr(self.bot, CREATED_ATTRIBUTE, 0) or 0)
        self.state.discarded_lifetime = int(
            as_finite_float(getattr(self.bot, DISCARDED_ATTRIBUTE, 0)) or 0.0
        )
        self.state.reset_ts = (
            as_finite_float(getattr(self.bot, RESET_TS_ATTRIBUTE, 0.0)) or 0.0
        )
        self.state.forms_configured = 1

        pending = [row for row in tranches if row.get(STATUS_KEY) == STATUS_PENDING]
        filled = [row for row in tranches if row.get(STATUS_KEY) == STATUS_FILLED]
        cancelled = [row for row in tranches if row.get(STATUS_KEY) == STATUS_CANCELLED]
        self.state.pending_count = len(pending)
        self.state.filled_count = len(filled)
        self.state.cancelled_count = len(cancelled)

        for row in pending:
            size = as_finite_float(row.get(SIZE_KEY, 0))
            if size is None:
                self.state.pending_size_unreadable += 1
            else:
                self.state.pending_size_total += size

        self._record(STEP_SUMMARY)
        self._add_row(PENDING_ROW_LABEL, COUNT_FORMAT.format(count=len(pending)))
        self._add_row(FILLED_ROW_LABEL, COUNT_FORMAT.format(count=len(filled)))
        self._add_row(CANCELLED_ROW_LABEL, COUNT_FORMAT.format(count=len(cancelled)))

        size_text = PENDING_SIZE_FORMAT.format(size_total=self.state.pending_size_total)
        if self.state.pending_size_unreadable:
            size_text += UNREADABLE_SUFFIX_FORMAT.format(
                unreadable=self.state.pending_size_unreadable
            )
        self._add_row(PENDING_SIZE_ROW_LABEL, size_text, PENDING_SIZE_STYLE)

        ages = []
        for row in pending:
            opened = as_finite_float(row.get(OPENED_TS_KEY))
            if opened is not None and opened > 0:
                ages.append(now_ts - opened)
        if ages:
            oldest = format_age(max(ages))
        elif pending:
            oldest = NO_TIMESTAMP_TEXT
        else:
            oldest = NO_PENDING_TEXT
        self._add_row(OLDEST_AGE_ROW_LABEL, oldest)

        self._add_row(
            OPENED_ROW_LABEL, COUNT_FORMAT.format(count=self.state.created_lifetime)
        )
        self._add_row(
            FILL_RATIO_ROW_LABEL,
            self._ratio_text(len(filled)),
            self._ratio_style(len(filled), len(pending)),
        )
        if self.state.discarded_lifetime:
            self._add_row(
                DISCARDED_ROW_LABEL,
                COUNT_FORMAT.format(count=self.state.discarded_lifetime),
            )

        self._record(STEP_BUTTONS)
        self.state.droppable = len(
            [
                row
                for row in tranches
                if not (row.get(STATUS_KEY) == STATUS_PENDING and row.get(ORDER_ID_KEY))
            ]
        )
        self.state.clear_button_text = (
            CLEAR_BUTTON_COUNTED_FORMAT.format(droppable=self.state.droppable)
            if self.state.droppable
            else CLEAR_BUTTON_PLAIN_TEXT
        )
        self.state.clear_button_enabled = bool(self.state.droppable)
        counter_total = self.state.created_lifetime + self.state.discarded_lifetime
        self.state.counters_button_text = (
            COUNTERS_BUTTON_COUNTED_FORMAT.format(created=self.state.created_lifetime)
            if counter_total
            else COUNTERS_BUTTON_PLAIN_TEXT
        )
        self.state.counters_button_enabled = bool(counter_total)

        if not tranches:
            self._record(STEP_EMPTY)
            self.state.empty_shown = True
            return self

        self._record(STEP_DETAIL)
        self.state.detail_shown = True
        self.state.detail_title = DETAIL_GROUP_TITLE_FORMAT.format(count=len(tranches))
        for row in tranches:
            self.state.detail_rows.append(self._detail_line(row, now_ts))
            self.state.detail_styles.append(self._detail_style(row))
        return self

    def _add_row(self, label: str, value: str, style: str = RATIO_NO_STYLE) -> None:
        self.state.summary_rows.append([label, value])
        self.state.summary_styles.append(style)

    def _ratio_text(self, filled: int) -> str:
        if self.state.created_lifetime > 0:
            return FILL_RATIO_FORMAT.format(
                ratio=filled / self.state.created_lifetime,
                filled=filled,
                created=self.state.created_lifetime,
            )
        if self.state.reset_ts > 0:
            return FILL_RATIO_CLEARED_TEXT
        return FILL_RATIO_NEVER_OPENED_TEXT

    def _ratio_style(self, filled: int, pending: int) -> str:
        if self.state.created_lifetime < RATIO_MIN_OPENED or pending <= 0:
            return RATIO_NO_STYLE
        ratio = filled / self.state.created_lifetime
        if ratio < RATIO_RED_BELOW:
            return RATIO_STYLE_FORMAT.format(colour=RATIO_RED)
        if ratio < RATIO_AMBER_BELOW:
            return RATIO_STYLE_FORMAT.format(colour=RATIO_AMBER)
        return RATIO_STYLE_FORMAT.format(colour=RATIO_GREEN)

    def _detail_line(self, row: dict, now_ts: float) -> str:
        index = as_finite_float(row.get(INDEX_KEY, 0))
        index_text = (
            INDEX_FORMAT.format(value=int(index))
            if index is not None
            else INDEX_REFUSED_FORMAT.format(dash=NO_VALUE)
        )
        price = as_finite_float(row.get(PRICE_KEY, 0))
        price_text = (
            PRICE_FORMAT.format(value=price)
            if price is not None
            else PRICE_REFUSED_FORMAT.format(dash=NO_VALUE)
        )
        size = as_finite_float(row.get(SIZE_KEY, 0))
        size_text = (
            SIZE_FORMAT.format(value=size)
            if size is not None
            else SIZE_REFUSED_FORMAT.format(dash=NO_VALUE)
        )
        status = str(row.get(STATUS_KEY, STATUS_UNKNOWN))
        mode = MODE_VISIBLE if row.get(VISIBLE_KEY) else MODE_INVISIBLE
        stored_fill = row.get(FILL_PRICE_KEY)
        fill = as_finite_float(stored_fill) if stored_fill else None
        fill_text = FILL_FORMAT.format(value=fill) if fill is not None else NO_VALUE
        opened = as_finite_float(row.get(OPENED_TS_KEY))
        age_text = (
            format_age(now_ts - opened)
            if opened is not None and opened > 0
            else NO_VALUE
        )
        return ROW_FORMAT.format(
            index=index_text,
            price=price_text,
            size=size_text,
            mode=mode,
            status=status,
            fill=fill_text,
            age=age_text,
        )

    def _detail_style(self, row: dict) -> str:
        status = str(row.get(STATUS_KEY, STATUS_UNKNOWN))
        if status == STATUS_FILLED:
            return ROW_BASE_STYLE + ROW_FILLED_STYLE
        if status == STATUS_CANCELLED:
            return ROW_BASE_STYLE + ROW_CANCELLED_STYLE
        return ROW_BASE_STYLE + ROW_PLAIN_STYLE

    def refresh(self) -> str:
        """Rebuild the tab in place and report why it could not."""
        host = self.host
        if host is None or not host.installed:
            self.state.refresh_status = NO_TAB_INSTALLED
            return self.state.refresh_status
        try:
            index = host.index_of()
        except Exception as exc:
            self.state.refresh_status = TAB_NOT_LOCATED_FORMAT.format(
                error=type(exc).__name__
            )
            return self.state.refresh_status
        if index < 0:
            self.state.refresh_status = TAB_GONE
            return self.state.refresh_status
        label = host.tab_text(index)
        was_current = host.current_index() == index
        try:
            fresh = host.rebuild()
        except Exception as exc:
            self.state.refresh_status = REBUILD_RAISED_FORMAT.format(
                error=type(exc).__name__, detail=exc
            )
            return self.state.refresh_status
        host.remove_tab(index)
        host.insert_tab(index, fresh, label)
        if was_current:
            host.set_current_index(index)
        host.delete_page(index)
        self.state.refresh_status = REFRESHED
        return self.state.refresh_status

    def settle_after_clear(self, what: str) -> list:
        """Save, rebuild the tab, and report the two lines it produced."""
        self._record(STEP_SETTLED)
        saved, why = (
            self.saver.save(what) if self.saver is not None else (False, "no saver")
        )
        status = self.refresh()
        lines = []
        if status == REFRESHED:
            lines.append(REBUILT_LINE)
        else:
            lines.append(NOT_REBUILT_LINE_FORMAT.format(refresh=status))
        if saved:
            lines.append(SAVED_LINE)
        else:
            lines.append(NOT_SAVED_LINE_FORMAT.format(why=why))
        self.state.settled_lines = lines
        return lines

    def clear_tranches(self, answer: str = NO_ANSWER) -> str:
        """Run the Clear Stack Tranches path and report where it stopped."""
        tranches = self._tranches()
        droppable, live = self._droppable_of(tranches)
        self.state.droppable = droppable
        self.state.live_order_count = live
        if not droppable:
            self._record(STEP_NOTHING_TO_DISCARD)
            self._box(
                INFORMATION_ICON,
                CLEAR_TRANCHES_TITLE,
                NOTHING_TO_DISCARD_TEXT
                + (KEPT_LIVE_NOTE_FORMAT.format(live=live) if live else BLANK_LINE),
            )
            self.state.outcome = OUTCOME_NOTHING_TO_DISCARD
            return self.state.outcome
        discard = getattr(self.bot, CLEAR_TRANCHES_ATTRIBUTE, None)
        if not callable(discard):
            self._record(STEP_NO_CLEAR_SUPPORT)
            self._box(WARNING_ICON, CLEAR_TRANCHES_TITLE, NO_CLEAR_SUPPORT_TEXT)
            self.state.outcome = OUTCOME_UNSUPPORTED
            return self.state.outcome

        body = [
            CONFIRM_DISCARD_FORMAT.format(droppable=droppable, symbol=self._symbol()),
            BLANK_LINE,
            CONFIRM_NO_ORDER_TEXT,
            BLANK_LINE,
            CONFIRM_UNDONE_TEXT,
        ]
        if live:
            body += [BLANK_LINE, CONFIRM_LIVE_NOTE_FORMAT.format(live=live)]
        self._record(STEP_CONFIRM)
        self._box(QUESTION_ICON, CLEAR_TRANCHES_TITLE, BODY_JOIN.join(body))
        if answer != YES_ANSWER:
            self._record(STEP_DECLINED)
            self.state.outcome = OUTCOME_DECLINED
            return self.state.outcome

        try:
            report = discard(reason=CLEAR_REASON)
        except Exception as exc:
            self._record(STEP_CALL_FAILED)
            self._box(
                CRITICAL_ICON,
                CLEAR_TRANCHES_TITLE,
                CLEAR_FAILED_FORMAT.format(detail=exc),
            )
            self.state.outcome = OUTCOME_FAILED
            return self.state.outcome

        settled = self.settle_after_clear(CLEAR_TRANCHES_TITLE)
        kept = int(report.get(REPORT_KEPT_KEY, 0))
        self._record(STEP_CLEARED)
        self._box(
            INFORMATION_ICON,
            CLEAR_TRANCHES_TITLE,
            RESULT_JOIN.join(
                [
                    DISCARDED_RESULT_FORMAT.format(
                        count=int(report.get(REPORT_COUNT_KEY, 0)),
                        size=float(report.get(REPORT_SIZE_KEY, 0.0)),
                    ),
                    BODY_JOIN.join(settled),
                    KEPT_RESULT_FORMAT.format(kept=kept),
                ]
            ),
        )
        self.state.outcome = OUTCOME_CLEARED
        return self.state.outcome

    def clear_lifetime_counters(self, answer: str = NO_ANSWER) -> str:
        """Run the Clear Lifetime Counters path and report where it stopped."""
        opened = int(getattr(self.bot, CREATED_ATTRIBUTE, 0) or 0)
        discarded = int(getattr(self.bot, DISCARDED_ATTRIBUTE, 0) or 0)
        if not opened + discarded:
            self._record(STEP_COUNTERS_ZERO)
            self._box(
                INFORMATION_ICON, CLEAR_COUNTERS_TITLE, COUNTERS_ALREADY_ZERO_TEXT
            )
            self.state.outcome = OUTCOME_ALREADY_ZERO
            return self.state.outcome
        zero = getattr(self.bot, CLEAR_COUNTERS_ATTRIBUTE, None)
        if not callable(zero):
            self._record(STEP_NO_COUNTER_SUPPORT)
            self._box(WARNING_ICON, CLEAR_COUNTERS_TITLE, NO_COUNTER_SUPPORT_TEXT)
            self.state.outcome = OUTCOME_UNSUPPORTED
            return self.state.outcome

        open_now = len(self._tranches())
        body = [
            CONFIRM_COUNTERS_FORMAT.format(symbol=self._symbol()),
            BLANK_LINE,
            CONFIRM_OPENED_LINE_FORMAT.format(opened=opened),
            CONFIRM_DISCARDED_LINE_FORMAT.format(discarded=discarded),
            BLANK_LINE,
            CONFIRM_COUNTERS_NO_ORDER_TEXT,
            BLANK_LINE,
            CONFIRM_UNDONE_TEXT,
        ]
        if open_now:
            body += [
                BLANK_LINE,
                CONFIRM_STILL_HOLDS_FORMAT.format(open_now=open_now),
            ]
        self._record(STEP_CONFIRM)
        self._box(QUESTION_ICON, CLEAR_COUNTERS_TITLE, BODY_JOIN.join(body))
        if answer != YES_ANSWER:
            self._record(STEP_DECLINED)
            self.state.outcome = OUTCOME_DECLINED
            return self.state.outcome

        try:
            report = zero(reason=CLEAR_REASON)
        except Exception as exc:
            self._record(STEP_CALL_FAILED)
            self._box(
                CRITICAL_ICON,
                CLEAR_COUNTERS_TITLE,
                CLEAR_FAILED_FORMAT.format(detail=exc),
            )
            self.state.outcome = OUTCOME_FAILED
            return self.state.outcome

        settled = self.settle_after_clear(CLEAR_COUNTERS_TITLE)
        before = report.get(REPORT_BEFORE_KEY, {}) or {}
        self._record(STEP_COUNTERS_CLEARED)
        self._box(
            INFORMATION_ICON,
            CLEAR_COUNTERS_TITLE,
            RESULT_JOIN.join(
                [
                    COUNTERS_RESULT_FORMAT.format(
                        cleared=int(report.get(REPORT_CLEARED_KEY, 0)),
                        opened=int(before.get(REPORT_CREATED_KEY, 0)),
                        discarded=int(before.get(REPORT_DISCARDED_KEY, 0)),
                    ),
                    COUNTERS_BOTH_ZERO_TEXT,
                    BODY_JOIN.join(settled),
                    COUNTERS_KEPT_FORMAT.format(standing=len(self._tranches())),
                ]
            ),
        )
        self.state.outcome = OUTCOME_COUNTERS_CLEARED
        return self.state.outcome


PANE_MODEL: Optional[StackTranchesTabModel] = None


def pane_model() -> StackTranchesTabModel:
    """The tab state the bridge keeps, built on the first request."""
    global PANE_MODEL
    if PANE_MODEL is None:
        PANE_MODEL = StackTranchesTabModel()
    return PANE_MODEL


def payload_labels() -> dict:
    """The summary row labels, keyed by the row they name."""
    return {
        "pending": PENDING_ROW_LABEL,
        "filled": FILLED_ROW_LABEL,
        "cancelled": CANCELLED_ROW_LABEL,
        "pending_size": PENDING_SIZE_ROW_LABEL,
        "oldest_age": OLDEST_AGE_ROW_LABEL,
        "opened": OPENED_ROW_LABEL,
        "fill_ratio": FILL_RATIO_ROW_LABEL,
        "discarded": DISCARDED_ROW_LABEL,
    }


def payload_texts() -> dict:
    """Every fixed string the tab prints."""
    return {
        "no_value": NO_VALUE,
        "no_timestamp": NO_TIMESTAMP_TEXT,
        "no_pending": NO_PENDING_TEXT,
        "ratio_cleared": FILL_RATIO_CLEARED_TEXT,
        "ratio_never_opened": FILL_RATIO_NEVER_OPENED_TEXT,
        "clear_button_plain": CLEAR_BUTTON_PLAIN_TEXT,
        "counters_button_plain": COUNTERS_BUTTON_PLAIN_TEXT,
        "nothing_to_discard": NOTHING_TO_DISCARD_TEXT,
        "no_clear_support": NO_CLEAR_SUPPORT_TEXT,
        "no_counter_support": NO_COUNTER_SUPPORT_TEXT,
        "counters_already_zero": COUNTERS_ALREADY_ZERO_TEXT,
        "confirm_no_order": CONFIRM_NO_ORDER_TEXT,
        "confirm_undone": CONFIRM_UNDONE_TEXT,
        "confirm_counters_no_order": CONFIRM_COUNTERS_NO_ORDER_TEXT,
        "counters_both_zero": COUNTERS_BOTH_ZERO_TEXT,
        "rebuilt": REBUILT_LINE,
        "saved": SAVED_LINE,
        "refreshed": REFRESHED,
        "no_tab_installed": NO_TAB_INSTALLED,
        "tab_gone": TAB_GONE,
        "blank_line": BLANK_LINE,
        "body_join": BODY_JOIN,
        "result_join": RESULT_JOIN,
        "mode_visible": MODE_VISIBLE,
        "mode_invisible": MODE_INVISIBLE,
        "status_unknown": STATUS_UNKNOWN,
        "clear_reason": CLEAR_REASON,
    }


def payload_titles() -> dict:
    """The two message box titles."""
    return {
        "clear_tranches": CLEAR_TRANCHES_TITLE,
        "clear_counters": CLEAR_COUNTERS_TITLE,
    }


def payload_formats() -> dict:
    """Every format string the tab fills in."""
    return {
        "count": COUNT_FORMAT,
        "pending_size": PENDING_SIZE_FORMAT,
        "unreadable_suffix": UNREADABLE_SUFFIX_FORMAT,
        "fill_ratio": FILL_RATIO_FORMAT,
        "ratio_style": RATIO_STYLE_FORMAT,
        "clear_button_counted": CLEAR_BUTTON_COUNTED_FORMAT,
        "counters_button_counted": COUNTERS_BUTTON_COUNTED_FORMAT,
        "detail_group_title": DETAIL_GROUP_TITLE_FORMAT,
        "row": ROW_FORMAT,
        "index": INDEX_FORMAT,
        "index_refused": INDEX_REFUSED_FORMAT,
        "price": PRICE_FORMAT,
        "price_refused": PRICE_REFUSED_FORMAT,
        "size": SIZE_FORMAT,
        "size_refused": SIZE_REFUSED_FORMAT,
        "fill": FILL_FORMAT,
        "age_seconds": AGE_SECONDS_FORMAT,
        "age_minutes": AGE_MINUTES_FORMAT,
        "age_hours": AGE_HOURS_FORMAT,
        "age_days": AGE_DAYS_FORMAT,
        "tab_not_located": TAB_NOT_LOCATED_FORMAT,
        "rebuild_raised": REBUILD_RAISED_FORMAT,
        "not_rebuilt_line": NOT_REBUILT_LINE_FORMAT,
        "not_saved_line": NOT_SAVED_LINE_FORMAT,
        "kept_live_note": KEPT_LIVE_NOTE_FORMAT,
        "confirm_discard": CONFIRM_DISCARD_FORMAT,
        "confirm_live_note": CONFIRM_LIVE_NOTE_FORMAT,
        "clear_failed": CLEAR_FAILED_FORMAT,
        "discarded_result": DISCARDED_RESULT_FORMAT,
        "kept_result": KEPT_RESULT_FORMAT,
        "confirm_counters": CONFIRM_COUNTERS_FORMAT,
        "confirm_opened_line": CONFIRM_OPENED_LINE_FORMAT,
        "confirm_discarded_line": CONFIRM_DISCARDED_LINE_FORMAT,
        "confirm_still_holds": CONFIRM_STILL_HOLDS_FORMAT,
        "counters_result": COUNTERS_RESULT_FORMAT,
        "counters_kept": COUNTERS_KEPT_FORMAT,
    }


def payload_styles() -> dict:
    """Every style sheet the tab applies."""
    return {
        "pending_size": PENDING_SIZE_STYLE,
        "ratio_none": RATIO_NO_STYLE,
        "danger_button": DANGER_BUTTON_STYLE,
        "empty": EMPTY_STYLE,
        "header": HEADER_STYLE,
        "row_base": ROW_BASE_STYLE,
        "row_filled": ROW_FILLED_STYLE,
        "row_cancelled": ROW_CANCELLED_STYLE,
        "row_plain": ROW_PLAIN_STYLE,
    }


def payload_colours() -> dict:
    """The three fill-ratio colours."""
    return {
        "ratio_red": RATIO_RED,
        "ratio_amber": RATIO_AMBER,
        "ratio_green": RATIO_GREEN,
    }


def payload_thresholds() -> dict:
    """The numbers the ratio colour and the age wording turn on."""
    return {
        "ratio_min_opened": RATIO_MIN_OPENED,
        "ratio_red_below": RATIO_RED_BELOW,
        "ratio_amber_below": RATIO_AMBER_BELOW,
        "age_minute_s": AGE_SECONDS_MINUTE,
        "age_hour_s": AGE_SECONDS_HOUR,
        "age_day_s": AGE_SECONDS_DAY,
    }


def payload_keys() -> dict:
    """The stored keys the tab and the clear reports read."""
    return {
        "size": SIZE_KEY,
        "index": INDEX_KEY,
        "price": PRICE_KEY,
        "fill_price": FILL_PRICE_KEY,
        "opened_ts": OPENED_TS_KEY,
        "status": STATUS_KEY,
        "visible": VISIBLE_KEY,
        "order_id": ORDER_ID_KEY,
        "report_count": REPORT_COUNT_KEY,
        "report_size": REPORT_SIZE_KEY,
        "report_kept": REPORT_KEPT_KEY,
        "report_cleared": REPORT_CLEARED_KEY,
        "report_before": REPORT_BEFORE_KEY,
        "report_created": REPORT_CREATED_KEY,
        "report_discarded": REPORT_DISCARDED_KEY,
    }


def payload_statuses() -> dict:
    """The three tranche statuses the tab groups by."""
    return {
        "pending": STATUS_PENDING,
        "filled": STATUS_FILLED,
        "cancelled": STATUS_CANCELLED,
    }


def payload_attributes() -> dict:
    """The bot attributes the tab reads."""
    return {
        "tranches": TRANCHES_ATTRIBUTE,
        "created": CREATED_ATTRIBUTE,
        "discarded": DISCARDED_ATTRIBUTE,
        "reset_ts": RESET_TS_ATTRIBUTE,
        "clear_tranches": CLEAR_TRANCHES_ATTRIBUTE,
        "clear_counters": CLEAR_COUNTERS_ATTRIBUTE,
    }


def payload_icons() -> dict:
    """The four message box icons."""
    return {
        "information": INFORMATION_ICON,
        "warning": WARNING_ICON,
        "critical": CRITICAL_ICON,
        "question": QUESTION_ICON,
    }


def payload_answers() -> dict:
    """The confirm answers and the default."""
    return {
        "yes": YES_ANSWER,
        "no": NO_ANSWER,
        "default": CONFIRM_DEFAULT_ANSWER,
    }


def build_view_model(model: StackTranchesTabModel) -> dict:
    """Every value the renderer needs to paint the tab, as plain data."""
    return {
        "method": METHOD,
        "accessible_name": ACCESSIBLE_NAME,
        "tab_label": TAB_LABEL,
        "actions": ACTIONS,
        "bus_topics": list(BUS_TOPICS),
        "timers": TIMERS,
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "threads": list(THREADS),
        "signals": list(SIGNALS),
        "bus_emits": list(BUS_EMITS),
        "call_names": list(CALL_NAMES),
        "outcomes": list(OUTCOMES),
        "calls": list(model.state.calls),
        "boxes": list(model.state.boxes),
        "outcome": model.state.outcome,
        "settled_lines": list(model.state.settled_lines),
        "refresh_status": model.state.refresh_status,
        "container": {
            "spacing_px": CONTENT_SPACING_PX,
            "margins_set": CONTENT_MARGINS_SET,
        },
        "summary_group": {
            "title": SUMMARY_GROUP_TITLE,
            "configured_by_host": SUMMARY_FORM_CONFIGURED_BY_HOST,
            "forms_configured": model.state.forms_configured,
        },
        "summary_rows": [list(row) for row in model.state.summary_rows],
        "summary_styles": list(model.state.summary_styles),
        "counts": {
            "pending": model.state.pending_count,
            "filled": model.state.filled_count,
            "cancelled": model.state.cancelled_count,
            "created_lifetime": model.state.created_lifetime,
            "discarded_lifetime": model.state.discarded_lifetime,
            "droppable": model.state.droppable,
            "live_orders": model.state.live_order_count,
            "pending_size_unreadable": model.state.pending_size_unreadable,
        },
        "pending_size_total": model.state.pending_size_total,
        "reset_ts": model.state.reset_ts,
        "clear_button": {
            "text": model.state.clear_button_text,
            "enabled": model.state.clear_button_enabled,
            "tooltip": CLEAR_BUTTON_TOOLTIP,
            "style_sheet": DANGER_BUTTON_STYLE,
        },
        "counters_button": {
            "text": model.state.counters_button_text,
            "enabled": model.state.counters_button_enabled,
            "tooltip": COUNTERS_BUTTON_TOOLTIP,
            "style_sheet": DANGER_BUTTON_STYLE,
        },
        "empty_label": {
            "shown": model.state.empty_shown,
            "text": EMPTY_TEXT,
            "style_sheet": EMPTY_STYLE,
            "word_wrap": EMPTY_WORD_WRAP,
        },
        "detail": {
            "shown": model.state.detail_shown,
            "title": model.state.detail_title,
            "header_text": HEADER_TEXT,
            "header_style": HEADER_STYLE,
            "rows": list(model.state.detail_rows),
            "row_styles": list(model.state.detail_styles),
            "row_count": len(model.state.detail_rows),
        },
        "labels": payload_labels(),
        "texts": payload_texts(),
        "titles": payload_titles(),
        "formats": payload_formats(),
        "styles": payload_styles(),
        "colours": payload_colours(),
        "thresholds": payload_thresholds(),
        "keys": payload_keys(),
        "statuses": payload_statuses(),
        "attributes": payload_attributes(),
        "icons": payload_icons(),
        "answers": payload_answers(),
    }


def view_model(params: dict) -> dict:
    """Answer the bridge with the tab's state.

    ``reset`` starts a fresh tab. ``bot`` seeds the bot readings and
    builds against ``now_ts``. ``clear`` and ``clear_counters`` run the
    two button paths with the answer ``answer`` names.
    """
    params = params or {}
    global PANE_MODEL
    if params.get("reset"):
        PANE_MODEL = StackTranchesTabModel()
    model = pane_model()
    described = params.get("bot")
    if described is not None:
        model.bot = BotSource(
            tranches=described.get("tranches"),
            created=described.get("created", 0),
            discarded=described.get("discarded", 0),
            reset_ts=described.get("reset_ts", 0.0),
            symbol=described.get("symbol", ""),
            clear_report=described.get("clear_report"),
            counters_report=described.get("counters_report"),
        )
        model.saver = StateSaver(
            saved=bool(described.get("saved", True)),
            why=str(described.get("save_why", "")),
        )
        model.host = TabHost()
        model.build(float(params.get("now_ts", 0.0)))
    if params.get("clear"):
        model.clear_tranches(str(params.get("answer", NO_ANSWER)))
    if params.get("clear_counters"):
        model.clear_lifetime_counters(str(params.get("answer", NO_ANSWER)))
    return build_view_model(model)
