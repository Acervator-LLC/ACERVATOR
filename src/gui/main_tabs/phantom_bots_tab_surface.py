"""phantom_bots_tab_surface.py -- the Phantom Bots tab, without Qt.

Describes the sixth tab of the Live Bot Settings window, which opens on
Detail for a running bot. The tab holds a note, three setting boxes --
an enable switch, one timeframe picker and a lock-duration number
-- then a Coordinator Status box with six labelled rows, and, when the
bot has them, a seven-column per-phantom table and a four-column
cross-bot lock table. With neither table it shows one of three
explanatory lines instead.

``PhantomBotsTabModel`` holds the tab's state. ``build`` reads the bot
and fills every box. ``enable_changed``, ``timeframe_chosen`` and
``lock_changed`` are the three settings the operator can move; each
records the change the host dialog is told about. ``run_steps`` drives a
list of those in order and reports the step that refused.

``BotConfig``, ``PhantomSource``, ``PhantomManagerSource``,
``CoordinatorSource`` and ``BotSource`` are plain stand-ins for the
running bot, its phantom manager, its phantoms and the cross-bot
coordinator, so the tab can be driven over the bridge from values alone.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``phantom_bots_tab.state`` method, which is how the Electron
renderer reaches it. Every value below is written out here rather than
read from ``src.gui.live_settings.phantom_bots_tab``, so a value changed
on one side alone is reported. Nothing here imports Qt, and nothing here
reads a clock, a file or a network.
"""

from __future__ import annotations

from typing import Any, Optional

from ...exchange.timeframes import ALL_TIMEFRAMES
from .. import design_system as ds

METHOD = "phantom_bots_tab.state"

ACCESSIBLE_NAME = ""

CONTENT_SPACING_PX = 8
CONTENT_MARGINS_SET = False

INFO_TEXT = (
    "Multi-timeframe shadow bots. Higher TFs override lower TFs.\n"
    "Enable/disable and TF-set changes apply immediately to "
    "NEW phantoms. Already-started phantoms keep their "
    "original configuration until the next bot restart."
)
INFO_STYLE_FORMAT = "color: {color_hex}; font-size: 11px;"
INFO_WORD_WRAP = True

ENABLE_GROUP_TITLE = "Phantom Bots"
ENABLE_CHECK_TEXT = "Enable Phantom Bots"

TF_GROUP_TITLE = "Phantom Timeframe"
TF_ROW_LABEL = "Timeframe:"
TF_TOOLTIP = "The one phantom timeframe this bot runs"
TF_HINT_TEXT = (
    "One phantom, above this bot's own TA Timeframe. A timeframe at or "
    "below it is refused, and so is one the venue does not offer. "
    "Coinbase: 1m/5m/15m/30m/1h/2h/6h/1d. Binance: full set. Others vary."
)
TF_HINT_STYLE_FORMAT = "color: {color_hex}; font-size: 10px;"
TF_HINT_WORD_WRAP = True

TIMEFRAME_DEFAULT = "1d"
NOT_HIGHER_FORMAT = "{timeframe} is not above this bot's TA Timeframe {parent}"
NOT_OFFERED_FORMAT = "{timeframe} is not offered by {exchange}"
REFUSAL_NONE = ""

TIMEFRAMES = ALL_TIMEFRAMES
FALLBACK_TIMEFRAMES = ALL_TIMEFRAMES
TF_SUPPORTED_TOOLTIP_FORMAT = "{timeframe}: supported"
TF_UNSUPPORTED_TOOLTIP_FORMAT = "{timeframe}: NOT supported by exchange ({exchange_id})"
UNKNOWN_EXCHANGE_TEXT = "?"

LOCK_GROUP_TITLE = "Higher-TF Lock Duration"
LOCK_ROW_LABEL = "Candles to lock:"
LOCK_MIN = 1
LOCK_MAX = 10
LOCK_DEFAULT = 2
LOCK_TOOLTIP = (
    "When a higher-TF phantom locks a lower-TF phantom, "
    "how many candles does the lock persist?"
)

SUMMARY_GROUP_TITLE = "Coordinator Status"
FORM_CONFIGURED_BY_HOST = True

ENABLED_ROW_LABEL = "Phantoms enabled:"
STARTED_ROW_LABEL = "Phantoms started:"
TIMEFRAMES_ROW_LABEL = "Configured timeframes:"
DROPPED_ROW_LABEL = "Dropped by the venue:"
BELOW_PARENT_ROW_LABEL = "At or below the parent TF:"
LOCK_STATE_ROW_LABEL = "SCRUM lock state:"

YES_TEXT = "YES"
NO_TEXT = "NO"
FLAG_STYLE_FORMAT = "color: {color_hex}"
NO_TIMEFRAMES_TEXT = "— (none)"
TIMEFRAME_JOIN = ", "
LOCKED_TEXT_FORMAT = (
    "LOCKED — SCRUM suppressed by {timeframe} TF "
    "phantom (downside protection active)"
)
LOCKED_STYLE_FORMAT = "color: {color_hex}; font-weight: bold;"
UNLOCKED_TEXT = "UNLOCKED — SCRUM allowed"
UNLOCKED_STYLE_FORMAT = "color: {color_hex};"

ON_COLOR = ds.SUCCESS
WAITING_COLOR = ds.FOLD_RATIO_AMBER
OFF_COLOR = ds.TEXT_INACTIVE
LOSS_COLOR = ds.ERROR
NOTE_COLOR = ds.CARD_METRIC_LABEL
THIS_BOT_COLOR = ds.FOLD_SOURCE_MANUAL

PHANTOM_GROUP_TITLE_FORMAT = "Per-Phantom State ({count})"
PHANTOM_COLUMNS = (
    "TF",
    "State",
    "Target",
    "Trades",
    "P&L",
    "Bullish/Bearish",
    "Confidence",
)
PHANTOM_COLUMN_COUNT = 7
PHANTOM_TABLE_MAX_HEIGHT_PX = 280
PNL_COLUMN = 4
CONFIDENCE_COLUMN = 6

LOCKS_GROUP_TITLE_FORMAT = "Active Locks ({count})"
LOCK_COLUMNS = ("Source TF", "Source Bot", "Direction", "Candles left")
LOCK_COLUMN_COUNT = 4
LOCK_TABLE_MAX_HEIGHT_PX = 220
SOURCE_BOT_COLUMN = 1
DIRECTION_COLUMN = 2

HEADER_RESIZE_MODE = "ResizeToContents"
VERTICAL_HEADER_VISIBLE = True
EDIT_TRIGGERS = "NoEditTriggers"
ALTERNATING_ROW_COLORS = True

MISSING_TEXT = "?"
TARGET_FORMAT = "${target_balance:,.2f}"
TRADES_FORMAT = "{total_trades}"
PNL_FORMAT = "${pnl:+,.4f}"
VOTES_FORMAT = "{bullish}/{bearish}"
CONFIDENCE_FORMAT = "{confidence:.2%}"
CANDLES_FORMAT = "{candles_remaining}"
THIS_BOT_FORMAT = "{source_bot} (this bot)"

CONFIDENCE_STRONG_AT = 0.50
CONFIDENCE_FAIR_AT = 0.25
PNL_GAIN_ABOVE = 0
PNL_LOSS_BELOW = 0
NO_CELL_COLOR: Optional[str] = None

BULLISH_MARK = "BULLISH"
BEARISH_MARK = "BEARISH"

EMPTY_DISABLED_TEXT = (
    "Phantom Bots are DISABLED on this bot. "
    "Toggle 'Enable Phantom Bots' above "
    "to activate the multi-TF coordinator."
)
EMPTY_NOT_STARTED_TEXT = (
    "Phantoms enabled but not yet started. They "
    "spin up automatically on the first tick after "
    "bot is running. If this persists, check the "
    "Activity Log for phantom-startup errors."
)
EMPTY_NO_STATE_TEXT = (
    "Phantoms active but no per-phantom state "
    "available yet, and no locks currently held. "
    "State populates after each phantom completes "
    "its first signal cycle."
)
EMPTY_STYLE_FORMAT = "color: {color_hex}; font-style: italic; padding: 10px;"
EMPTY_WORD_WRAP = True
NO_EMPTY_TEXT = ""

ENABLED_ATTRIBUTE = "_phantoms_enabled"
STARTED_ATTRIBUTE = "_phantoms_started"
TIMEFRAMES_ATTRIBUTE = "_phantom_timeframes"
DROPPED_ATTRIBUTE = "_phantom_tf_dropped"
LOCKED_ATTRIBUTE = "_phantom_locked"
LOCK_TIMEFRAME_ATTRIBUTE = "_phantom_lock_timeframe"
COORDINATOR_ATTRIBUTE = "_coordinator"
PHANTOM_MANAGER_ATTRIBUTE = "_phantom_mgr"
BOT_ID_ATTRIBUTE = "bot_id"
CONFIG_ATTRIBUTE = "config"
EXCHANGE_ID_ATTRIBUTE = "exchange_id"
LOCK_COUNT_ATTRIBUTE = "lock_candle_count"
TA_TIMEFRAME_ATTRIBUTE = "ta_timeframe"
PARENT_TIMEFRAME_DEFAULT = "1h"

TIMEFRAME_KEY = "timeframe"
STATE_KEY = "state"
TARGET_KEY = "target_balance"
TRADES_KEY = "total_trades"
PNL_KEY = "realized_pnl_exchange"
SUMMARY_KEY = "last_summary"
BULLISH_KEY = "bullish"
BEARISH_KEY = "bearish"
CONFIDENCE_KEY = "confidence"
SOURCE_TF_KEY = "source_tf"
SOURCE_BOT_KEY = "source_bot"
DIRECTION_KEY = "locked_direction"
CANDLES_KEY = "candles_remaining"

DEFAULT_MONEY = 0
DEFAULT_COUNT = 0
DEFAULT_VOTES = 0
DEFAULT_CONFIDENCE = 0
DEFAULT_BOT_ID = ""
DEFAULT_LOCK_TIMEFRAME = ""
NO_EXCHANGE_ID: Optional[str] = None
NO_CONFIG: Optional[Any] = None

ENABLE_FIELD = "enable_phantoms"
TIMEFRAMES_FIELD = "phantom_timeframes"
LOCK_FIELD = "lock_candle_count"

ACTIONS = {
    "phantom_enable.toggled": "enable_changed",
    "timeframe_combo.changed": "timeframe_chosen",
    "lock_spin.valueChanged": "lock_changed",
}
TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()
BUS_EMITS: tuple = ()
THREAD_COUNT = 0
SIGNAL_COUNT = 0

STEP_BUILD = "build"
STEP_ENABLE = "enable"
STEP_TIMEFRAME = "timeframe"
STEP_LOCK = "lock"
NO_REFUSAL_INDEX = -1
NO_REFUSAL_NAME = ""

BUILD_START = "build.start"
BUILD_INFO = "build.info"
BUILD_ENABLE = "build.enable"
BUILD_TF_ALLOWED = "build.tf_allowed"
BUILD_TF_FALLBACK = "build.tf_fallback"
BUILD_TF_ITEM = "build.tf_item"
BUILD_TF_CURRENT = "build.tf_current"
BUILD_LOCK_FORM = "build.lock_form"
BUILD_LOCK_FROM_COORDINATOR = "build.lock_from_coordinator"
BUILD_LOCK_WITHOUT_COORDINATOR = "build.lock_without_coordinator"
BUILD_LOCK_CLAMPED = "build.lock_clamped"
BUILD_SUMMARY_FORM = "build.summary_form"
BUILD_SUMMARY_ROW = "build.summary_row"
BUILD_SCRUM_LOCKED = "build.scrum_locked"
BUILD_SCRUM_UNLOCKED = "build.scrum_unlocked"
BUILD_PHANTOMS = "build.phantoms"
BUILD_PHANTOMS_FAILED = "build.phantoms_failed"
BUILD_NO_MANAGER = "build.no_manager"
BUILD_PHANTOM_TABLE = "build.phantom_table"
BUILD_PHANTOM_ROW = "build.phantom_row"
BUILD_PHANTOM_STATUS_FAILED = "build.phantom_status_failed"
BUILD_LOCKS = "build.locks"
BUILD_LOCKS_FAILED = "build.locks_failed"
BUILD_NO_COORDINATOR = "build.no_coordinator"
BUILD_LOCK_TABLE = "build.lock_table"
BUILD_LOCK_ROW = "build.lock_row"
BUILD_EMPTY_DISABLED = "build.empty_disabled"
BUILD_EMPTY_NOT_STARTED = "build.empty_not_started"
BUILD_EMPTY_NO_STATE = "build.empty_no_state"
BUILD_RETURN = "build.return"
ENABLE_CHANGED = "enable.changed"
TIMEFRAME_CHOSEN = "timeframe.chosen"
TIMEFRAME_REFUSED = "timeframe.refused"
LOCK_CHANGED = "lock.changed"

ModelCall = list

CALL_NAMES = (
    BUILD_START,
    BUILD_INFO,
    BUILD_ENABLE,
    BUILD_TF_ALLOWED,
    BUILD_TF_FALLBACK,
    BUILD_TF_ITEM,
    BUILD_TF_CURRENT,
    BUILD_LOCK_FORM,
    BUILD_LOCK_FROM_COORDINATOR,
    BUILD_LOCK_WITHOUT_COORDINATOR,
    BUILD_LOCK_CLAMPED,
    BUILD_SUMMARY_FORM,
    BUILD_SUMMARY_ROW,
    BUILD_SCRUM_LOCKED,
    BUILD_SCRUM_UNLOCKED,
    BUILD_PHANTOMS,
    BUILD_PHANTOMS_FAILED,
    BUILD_NO_MANAGER,
    BUILD_PHANTOM_TABLE,
    BUILD_PHANTOM_ROW,
    BUILD_PHANTOM_STATUS_FAILED,
    BUILD_LOCKS,
    BUILD_LOCKS_FAILED,
    BUILD_NO_COORDINATOR,
    BUILD_LOCK_TABLE,
    BUILD_LOCK_ROW,
    BUILD_EMPTY_DISABLED,
    BUILD_EMPTY_NOT_STARTED,
    BUILD_EMPTY_NO_STATE,
    BUILD_RETURN,
    ENABLE_CHANGED,
    TIMEFRAME_CHOSEN,
    TIMEFRAME_REFUSED,
    LOCK_CHANGED,
)


def allowed_timeframes(exchange_id: Any) -> tuple:
    """The timeframes this bot's exchange serves, or the full set.

    An exchange the venue map does not name, and an exchange name that
    is not text, both give the full set: the tab greys nothing it is
    not sure about.
    """
    try:
        from ...exchange.timeframes import available_timeframes

        return tuple(available_timeframes(exchange_id))
    except Exception:
        return tuple(FALLBACK_TIMEFRAMES)


def timeframe_tooltip(timeframe: Any, supported: bool, exchange_id: Any) -> str:
    """The note on one timeframe entry, naming the exchange when greyed."""
    if supported:
        return TF_SUPPORTED_TOOLTIP_FORMAT.format(timeframe=timeframe)
    return TF_UNSUPPORTED_TOOLTIP_FORMAT.format(
        timeframe=timeframe, exchange_id=exchange_id
    )


def is_higher_timeframe(timeframe: Any, parent: Any) -> bool:
    """Say whether ``timeframe`` outranks ``parent`` in ``TIMEFRAMES``.

    ``TIMEFRAMES`` runs in the rank order ``TIMEFRAME_ORDER`` uses, which the
    Comp field and the higher-timeframe bias both read.
    """
    order = list(TIMEFRAMES)
    if timeframe not in order or parent not in order:
        return False
    return order.index(timeframe) > order.index(parent)


def chosen_timeframe(timeframes: Any) -> str:
    """Pick the highest-ranked name in ``timeframes``, else ``TIMEFRAME_DEFAULT``.

    A bot restored before one timeframe became the selection holds several, and
    the highest is the one the higher-timeframe bias weighs most.
    """
    order = list(TIMEFRAMES)
    held = [one for one in list(timeframes or ()) if one in order]
    if not held:
        return TIMEFRAME_DEFAULT
    return max(held, key=order.index)


def timeframe_refusal(
    timeframe: Any, parent: Any, offered: Any, exchange_id: Any
) -> str:
    """Refuse ``timeframe`` at or below ``parent``, or outside ``offered``.

    Hands back ``REFUSAL_NONE`` for a timeframe that passes both.
    """
    if not is_higher_timeframe(timeframe, parent):
        return NOT_HIGHER_FORMAT.format(timeframe=timeframe, parent=parent)
    if timeframe not in list(offered or ()):
        return NOT_OFFERED_FORMAT.format(
            timeframe=timeframe, exchange=exchange_id or UNKNOWN_EXCHANGE_TEXT
        )
    return REFUSAL_NONE


def clamp_lock(value: Any) -> int:
    """The lock count the number box holds, which has a floor and a ceiling.

    The box keeps the nearest value inside one to ten, so a coordinator
    asking for ninety-nine shows ten.
    """
    if value < LOCK_MIN:
        return LOCK_MIN
    if value > LOCK_MAX:
        return LOCK_MAX
    return int(value)


def flag_text(state: Any) -> str:
    """YES or NO, for one of the two coordinator flags."""
    return YES_TEXT if state else NO_TEXT


def enabled_color(enabled: Any) -> str:
    """Green while phantoms are switched on, grey while they are off."""
    return ON_COLOR if enabled else OFF_COLOR


def started_color(started: Any, enabled: Any) -> str:
    """Green once phantoms run, amber while they are only switched on."""
    if started:
        return ON_COLOR
    return WAITING_COLOR if enabled else OFF_COLOR


def timeframes_text(timeframes: Any) -> str:
    """The configured timeframes on one line, or a dash for none."""
    return TIMEFRAME_JOIN.join(timeframes) if timeframes else NO_TIMEFRAMES_TEXT


def below_parent_timeframes(timeframes: Any, parent: Any) -> list:
    """The held timeframes ``is_higher_timeframe`` refuses against ``parent``.

    No phantom on one of these names reaches the Comp field.
    """
    return [
        one for one in list(timeframes or ()) if not is_higher_timeframe(one, parent)
    ]


def pnl_color(pnl: Any) -> str:
    """Green above break-even, red below it, grey exactly at it."""
    if pnl > PNL_GAIN_ABOVE:
        return ON_COLOR
    if pnl < PNL_LOSS_BELOW:
        return LOSS_COLOR
    return OFF_COLOR


def confidence_color(confidence: Any) -> Optional[str]:
    """Green at half agreement or better, amber at a quarter, none below."""
    if confidence >= CONFIDENCE_STRONG_AT:
        return ON_COLOR
    if confidence >= CONFIDENCE_FAIR_AT:
        return WAITING_COLOR
    return NO_CELL_COLOR


def direction_color(direction: Any) -> Optional[str]:
    """Green for a bullish lock, red for a bearish one, none otherwise."""
    if BULLISH_MARK in direction:
        return ON_COLOR
    if BEARISH_MARK in direction:
        return LOSS_COLOR
    return NO_CELL_COLOR


def phantom_summary(status: Any) -> Any:
    """The vote block one phantom status carries, empty where it has none."""
    return status.get(SUMMARY_KEY, {}) or {}


def phantom_pnl(status: Any) -> float:
    """The profit one phantom row shows, coerced the way the tab coerces it."""
    return float(status.get(PNL_KEY, DEFAULT_MONEY) or DEFAULT_MONEY)


def phantom_confidence(summary: Any) -> float:
    """The agreement one phantom row shows, as a fraction of one."""
    return float(summary.get(CONFIDENCE_KEY, DEFAULT_CONFIDENCE) or DEFAULT_CONFIDENCE)


def phantom_row(status: Any) -> list:
    """The seven cell texts one phantom fills a table row with."""
    summary = phantom_summary(status)
    return [
        str(status.get(TIMEFRAME_KEY, MISSING_TEXT)),
        str(status.get(STATE_KEY, MISSING_TEXT)),
        TARGET_FORMAT.format(
            target_balance=float(status.get(TARGET_KEY, DEFAULT_MONEY) or DEFAULT_MONEY)
        ),
        TRADES_FORMAT.format(total_trades=status.get(TRADES_KEY, DEFAULT_COUNT)),
        PNL_FORMAT.format(pnl=phantom_pnl(status)),
        VOTES_FORMAT.format(
            bullish=summary.get(BULLISH_KEY, DEFAULT_VOTES),
            bearish=summary.get(BEARISH_KEY, DEFAULT_VOTES),
        ),
        CONFIDENCE_FORMAT.format(confidence=phantom_confidence(summary)),
    ]


def phantom_row_colors(status: Any) -> list:
    """The colour each cell of one phantom row is drawn in, or none."""
    colors: list = [NO_CELL_COLOR] * PHANTOM_COLUMN_COUNT
    colors[PNL_COLUMN] = pnl_color(phantom_pnl(status))
    colors[CONFIDENCE_COLUMN] = confidence_color(
        phantom_confidence(phantom_summary(status))
    )
    return colors


def lock_row(lock: Any, bot_id: Any) -> list:
    """The four cell texts one cross-bot lock fills a table row with."""
    source_bot = str(lock.get(SOURCE_BOT_KEY, MISSING_TEXT))
    return [
        str(lock.get(SOURCE_TF_KEY, MISSING_TEXT)),
        (
            THIS_BOT_FORMAT.format(source_bot=source_bot)
            if source_bot == bot_id
            else source_bot
        ),
        str(lock.get(DIRECTION_KEY, MISSING_TEXT)),
        CANDLES_FORMAT.format(
            candles_remaining=int(lock.get(CANDLES_KEY, DEFAULT_COUNT) or DEFAULT_COUNT)
        ),
    ]


def lock_row_colors(lock: Any, bot_id: Any) -> list:
    """The colour each cell of one lock row is drawn in, or none."""
    colors: list = [NO_CELL_COLOR] * LOCK_COLUMN_COUNT
    if str(lock.get(SOURCE_BOT_KEY, MISSING_TEXT)) == bot_id:
        colors[SOURCE_BOT_COLUMN] = THIS_BOT_COLOR
    colors[DIRECTION_COLUMN] = direction_color(
        str(lock.get(DIRECTION_KEY, MISSING_TEXT))
    )
    return colors


def empty_text(enabled: Any, started: Any) -> str:
    """The line shown when the bot has no phantom state and no lock."""
    if not enabled:
        return EMPTY_DISABLED_TEXT
    if not started:
        return EMPTY_NOT_STARTED_TEXT
    return EMPTY_NO_STATE_TEXT


class BotConfig:
    """The two config readings the tab takes: the bot's exchange and timeframe."""

    def __init__(
        self,
        exchange_id: Any = NO_EXCHANGE_ID,
        ta_timeframe: Any = PARENT_TIMEFRAME_DEFAULT,
    ) -> None:
        setattr(self, EXCHANGE_ID_ATTRIBUTE, exchange_id)
        setattr(self, TA_TIMEFRAME_ATTRIBUTE, ta_timeframe)


class PhantomSource:
    """One shadow bot the per-phantom table reads a status dict from.

    ``get_status`` raises when the caller asked for a failing reading,
    which is how the tab's guarded per-phantom read is driven. It hands
    back exactly what it was given, so a status of nothing reaches the
    tab as nothing rather than as an empty status.
    """

    def __init__(
        self, status: Any = None, raises: Optional[BaseException] = None
    ) -> None:
        self.status = status
        self.raises = raises

    def get_status(self) -> Any:
        if self.raises is not None:
            raise self.raises
        return self.status


class PhantomManagerSource:
    """The phantom manager the tab asks for this bot's shadow bots."""

    def __init__(
        self, phantoms: Any = None, raises: Optional[BaseException] = None
    ) -> None:
        self.phantoms = list(phantoms or [])
        self.raises = raises
        self.asked: list = []

    def get_phantoms(self, bot_id: Any) -> Any:
        self.asked.append(bot_id)
        if self.raises is not None:
            raise self.raises
        return self.phantoms


class CoordinatorSource:
    """The cross-bot coordinator the tab reads its lock count and locks from."""

    def __init__(
        self,
        lock_candle_count: Any = LOCK_DEFAULT,
        locks: Any = None,
        raises: Optional[BaseException] = None,
        with_lock_count: bool = True,
    ) -> None:
        if with_lock_count:
            setattr(self, LOCK_COUNT_ATTRIBUTE, lock_candle_count)
        self.locks = list(locks or [])
        self.raises = raises

    def get_active_locks(self) -> Any:
        if self.raises is not None:
            raise self.raises
        return self.locks


class BotSource:
    """The running bot the tab reads, taken from plain data.

    A reading named in ``missing`` is absent from the object, which is
    how the tab's own defaults are driven.
    """

    def __init__(
        self,
        exchange_id: Any = NO_EXCHANGE_ID,
        enabled: Any = False,
        started: Any = False,
        timeframes: Any = None,
        dropped: Any = None,
        locked: Any = False,
        lock_timeframe: Any = DEFAULT_LOCK_TIMEFRAME,
        bot_id: Any = DEFAULT_BOT_ID,
        manager: Any = None,
        coordinator: Any = None,
        with_config: bool = True,
        missing: Any = None,
        ta_timeframe: Any = PARENT_TIMEFRAME_DEFAULT,
    ) -> None:
        if with_config:
            setattr(self, CONFIG_ATTRIBUTE, BotConfig(exchange_id, ta_timeframe))
        absent = list(missing or ())
        held = [
            [ENABLED_ATTRIBUTE, enabled],
            [STARTED_ATTRIBUTE, started],
            [TIMEFRAMES_ATTRIBUTE, timeframes],
            [DROPPED_ATTRIBUTE, dropped],
            [LOCKED_ATTRIBUTE, locked],
            [LOCK_TIMEFRAME_ATTRIBUTE, lock_timeframe],
            [BOT_ID_ATTRIBUTE, bot_id],
            [PHANTOM_MANAGER_ATTRIBUTE, manager],
            [COORDINATOR_ATTRIBUTE, coordinator],
        ]
        for name, value in held:
            if name not in absent:
                setattr(self, name, value)


class PhantomBotsTabModel:
    """The Phantom Bots tab: its settings, its status rows and its tables.

    ``build`` reads the bot and fills the note, the three setting boxes,
    the six status rows and either the two tables or one explanatory
    line. ``dropped`` and ``below_parent`` name the timeframes no phantom
    runs on. ``enable_changed``, ``timeframe_chosen`` and ``lock_changed``
    are the three settings the operator moves.
    """

    def __init__(self, bot: Any = None) -> None:
        self.bot = bot
        self.accessible_name = ACCESSIBLE_NAME
        self.forms_configured = 0
        self.enable_checked = False
        self.timeframe_items: list = []
        self.timeframe_current = TIMEFRAME_DEFAULT
        self.parent_timeframe = PARENT_TIMEFRAME_DEFAULT
        self.refusal = REFUSAL_NONE
        self.exchange_id: Any = NO_EXCHANGE_ID
        self.allowed: tuple = ()
        self.lock_requested = LOCK_DEFAULT
        self.lock_value = LOCK_DEFAULT
        self.dropped: list = []
        self.below_parent: list = []
        self.summary_rows: list = []
        self.phantom_rows: list = []
        self.phantom_colors: list = []
        self.phantom_group_shown = False
        self.phantom_count = 0
        self.lock_rows: list = []
        self.lock_colors: list = []
        self.locks_group_shown = False
        self.locks_count = 0
        self.empty_shown = False
        self.empty_line = NO_EMPTY_TEXT
        self.stretch_shown = False
        self.changes: list = []
        self.calls: list = []

    def clear(self) -> None:
        """Empty every box, so a second build carries only its own values.

        The changes the host was told about survive, and so does the
        count of forms the host configured, because both live on the
        dialog rather than on the tab the dialog rebuilds.
        """
        self.enable_checked = False
        self.timeframe_items = []
        self.timeframe_current = TIMEFRAME_DEFAULT
        self.parent_timeframe = PARENT_TIMEFRAME_DEFAULT
        self.refusal = REFUSAL_NONE
        self.exchange_id = NO_EXCHANGE_ID
        self.allowed = ()
        self.lock_requested = LOCK_DEFAULT
        self.lock_value = LOCK_DEFAULT
        self.dropped = []
        self.below_parent = []
        self.summary_rows = []
        self.phantom_rows = []
        self.phantom_colors = []
        self.phantom_group_shown = False
        self.phantom_count = 0
        self.lock_rows = []
        self.lock_colors = []
        self.locks_group_shown = False
        self.locks_count = 0
        self.empty_shown = False
        self.empty_line = NO_EMPTY_TEXT
        self.stretch_shown = False
        return None

    def build(self) -> None:
        """Fill every box in the order the shipped tab fills it.

        Starts from an empty tab each time, exactly as the shipped tab
        hands back a freshly built tab on every call.
        """
        self.clear()
        bot = self.bot
        self.calls.append([BUILD_START])
        self.calls.append([BUILD_INFO])

        self.enable_checked = bool(getattr(bot, ENABLED_ATTRIBUTE, False))
        self.calls.append([BUILD_ENABLE, self.enable_checked])

        config = getattr(bot, CONFIG_ATTRIBUTE, NO_CONFIG)
        if config is NO_CONFIG:
            self.exchange_id = NO_EXCHANGE_ID
            self.allowed = tuple(FALLBACK_TIMEFRAMES)
            self.calls.append([BUILD_TF_FALLBACK])
        else:
            self.exchange_id = getattr(config, EXCHANGE_ID_ATTRIBUTE, NO_EXCHANGE_ID)
            self.allowed = allowed_timeframes(self.exchange_id)
            self.calls.append([BUILD_TF_ALLOWED, len(self.allowed)])
        named = getattr(config, EXCHANGE_ID_ATTRIBUTE, UNKNOWN_EXCHANGE_TEXT)
        self.parent_timeframe = str(
            getattr(config, TA_TIMEFRAME_ATTRIBUTE, PARENT_TIMEFRAME_DEFAULT)
            or PARENT_TIMEFRAME_DEFAULT
        )
        for timeframe in TIMEFRAMES:
            supported = timeframe in self.allowed
            self.timeframe_items.append(
                [
                    timeframe,
                    supported,
                    timeframe_tooltip(timeframe, supported, named),
                ]
            )
            self.calls.append([BUILD_TF_ITEM, timeframe, supported])
        self.timeframe_current = chosen_timeframe(
            getattr(bot, TIMEFRAMES_ATTRIBUTE, []) or []
        )
        self.calls.append(
            [BUILD_TF_CURRENT, self.timeframe_current, self.parent_timeframe]
        )

        self.forms_configured += 1
        self.calls.append([BUILD_LOCK_FORM])
        coordinator = getattr(bot, COORDINATOR_ATTRIBUTE, None)
        if coordinator:
            self.lock_requested = int(
                getattr(coordinator, LOCK_COUNT_ATTRIBUTE, LOCK_DEFAULT)
            )
            self.calls.append([BUILD_LOCK_FROM_COORDINATOR, self.lock_requested])
        else:
            self.lock_requested = int(LOCK_DEFAULT)
            self.calls.append([BUILD_LOCK_WITHOUT_COORDINATOR])
        self.lock_value = clamp_lock(self.lock_requested)
        if self.lock_value != self.lock_requested:
            self.calls.append(
                [BUILD_LOCK_CLAMPED, self.lock_requested, self.lock_value]
            )

        enabled = bool(getattr(bot, ENABLED_ATTRIBUTE, False))
        started = bool(getattr(bot, STARTED_ATTRIBUTE, False))
        timeframes = list(getattr(bot, TIMEFRAMES_ATTRIBUTE, []) or [])
        locked = bool(getattr(bot, LOCKED_ATTRIBUTE, False))
        lock_timeframe = str(
            getattr(bot, LOCK_TIMEFRAME_ATTRIBUTE, DEFAULT_LOCK_TIMEFRAME)
            or DEFAULT_LOCK_TIMEFRAME
        )

        self.forms_configured += 1
        self.calls.append([BUILD_SUMMARY_FORM])
        self.summary_rows.append(
            [
                ENABLED_ROW_LABEL,
                flag_text(enabled),
                FLAG_STYLE_FORMAT.format(color_hex=enabled_color(enabled)),
            ]
        )
        self.summary_rows.append(
            [
                STARTED_ROW_LABEL,
                flag_text(started),
                FLAG_STYLE_FORMAT.format(color_hex=started_color(started, enabled)),
            ]
        )
        self.summary_rows.append(
            [TIMEFRAMES_ROW_LABEL, timeframes_text(timeframes), ""]
        )
        self.dropped = [
            str(one) for one in (getattr(bot, DROPPED_ATTRIBUTE, []) or [])
        ]
        self.below_parent = below_parent_timeframes(
            timeframes, self.parent_timeframe
        )
        self.summary_rows.append(
            [DROPPED_ROW_LABEL, timeframes_text(self.dropped), ""]
        )
        self.summary_rows.append(
            [BELOW_PARENT_ROW_LABEL, timeframes_text(self.below_parent), ""]
        )
        if locked:
            self.summary_rows.append(
                [
                    LOCK_STATE_ROW_LABEL,
                    LOCKED_TEXT_FORMAT.format(timeframe=lock_timeframe),
                    LOCKED_STYLE_FORMAT.format(color_hex=WAITING_COLOR),
                ]
            )
            self.calls.append([BUILD_SCRUM_LOCKED, lock_timeframe])
        else:
            self.summary_rows.append(
                [
                    LOCK_STATE_ROW_LABEL,
                    UNLOCKED_TEXT,
                    UNLOCKED_STYLE_FORMAT.format(color_hex=ON_COLOR),
                ]
            )
            self.calls.append([BUILD_SCRUM_UNLOCKED])
        for label, value, _style in self.summary_rows:
            self.calls.append([BUILD_SUMMARY_ROW, label, value])

        manager = getattr(bot, PHANTOM_MANAGER_ATTRIBUTE, None)
        bot_id = getattr(bot, BOT_ID_ATTRIBUTE, DEFAULT_BOT_ID)
        phantoms: list = []
        if manager is not None:
            try:
                phantoms = list(manager.get_phantoms(bot_id) or [])
                self.calls.append([BUILD_PHANTOMS, len(phantoms)])
            except Exception:
                phantoms = []
                self.calls.append([BUILD_PHANTOMS_FAILED])
        else:
            self.calls.append([BUILD_NO_MANAGER])

        if phantoms:
            self.phantom_group_shown = True
            self.phantom_count = len(phantoms)
            self.calls.append([BUILD_PHANTOM_TABLE, len(phantoms)])
            for index, phantom in enumerate(phantoms):
                try:
                    status = phantom.get_status()
                except Exception:
                    status = {}
                    self.calls.append([BUILD_PHANTOM_STATUS_FAILED, index])
                self.phantom_rows.append(phantom_row(status))
                self.phantom_colors.append(phantom_row_colors(status))
                self.calls.append([BUILD_PHANTOM_ROW, index])

        coordinator = getattr(bot, COORDINATOR_ATTRIBUTE, None)
        locks: list = []
        if coordinator is not None:
            try:
                locks = list(coordinator.get_active_locks() or [])
                self.calls.append([BUILD_LOCKS, len(locks)])
            except Exception:
                locks = []
                self.calls.append([BUILD_LOCKS_FAILED])
        else:
            self.calls.append([BUILD_NO_COORDINATOR])

        if locks:
            self.locks_group_shown = True
            self.locks_count = len(locks)
            self.calls.append([BUILD_LOCK_TABLE, len(locks)])
            for index, lock in enumerate(locks):
                self.lock_rows.append(lock_row(lock, bot_id))
                self.lock_colors.append(lock_row_colors(lock, bot_id))
                self.calls.append([BUILD_LOCK_ROW, index])

        if not phantoms and not locks:
            self.empty_shown = True
            self.empty_line = empty_text(enabled, started)
            if not enabled:
                self.calls.append([BUILD_EMPTY_DISABLED])
            elif not started:
                self.calls.append([BUILD_EMPTY_NOT_STARTED])
            else:
                self.calls.append([BUILD_EMPTY_NO_STATE])

        self.stretch_shown = True
        self.calls.append([BUILD_RETURN, len(self.summary_rows)])
        return None

    def enable_changed(self, checked: Any) -> None:
        """The enable switch moved; the host is told the new setting."""
        self.enable_checked = bool(checked)
        self.changes.append([ENABLE_FIELD, bool(checked)])
        self.calls.append([ENABLE_CHANGED, bool(checked)])
        return None

    def timeframe_chosen(self, timeframe: Any) -> None:
        """Take one phantom timeframe, refusing one at or below the parent's.

        A refused timeframe leaves ``timeframe_current`` alone, writes the
        reason into ``refusal``, and tells the host nothing.
        """
        if timeframe not in [item[0] for item in self.timeframe_items]:
            raise KeyError(timeframe)
        refused = timeframe_refusal(
            timeframe, self.parent_timeframe, self.allowed, self.exchange_id
        )
        if refused:
            self.refusal = refused
            self.calls.append([TIMEFRAME_REFUSED, timeframe, refused])
            return None
        self.refusal = REFUSAL_NONE
        self.timeframe_current = timeframe
        self.changes.append([TIMEFRAMES_FIELD, [timeframe]])
        self.calls.append([TIMEFRAME_CHOSEN, timeframe])
        return None

    def lock_changed(self, value: Any) -> None:
        """The lock-duration number moved; the host is told the new count."""
        self.lock_requested = value
        self.lock_value = clamp_lock(value)
        self.changes.append([LOCK_FIELD, int(self.lock_value)])
        self.calls.append([LOCK_CHANGED, int(self.lock_value)])
        return None

    def take_step(self, step: Any) -> None:
        """Move one control, and tell the host only where the value changed.

        A switch set to the value it already holds reports nothing, and
        the number box reports the value it kept rather than the value
        it was asked for.
        """
        name = step[0]
        if name == STEP_BUILD:
            self.build()
        elif name == STEP_ENABLE:
            if bool(step[1]) != self.enable_checked:
                self.enable_changed(step[1])
        elif name == STEP_TIMEFRAME:
            if step[1] != self.timeframe_current:
                self.timeframe_chosen(step[1])
        elif name == STEP_LOCK:
            kept = clamp_lock(step[1])
            if kept != self.lock_value:
                self.lock_changed(kept)
        else:
            raise LookupError(name)
        return None

    def run_steps(self, steps: Any) -> dict:
        """Take each step in order and report the one that refused.

        Returns the index and the name of the step that refused with the
        type of the refusal, or an index of minus one when every step
        was taken.
        """
        wanted = list(steps or ())
        for index, step in enumerate(wanted):
            name = step[0]
            try:
                self.take_step(step)
            except Exception as exc:
                return {
                    "refused_at": index,
                    "refused_step": name,
                    "refusal": type(exc).__name__,
                    "steps_taken": index,
                }
        return {
            "refused_at": NO_REFUSAL_INDEX,
            "refused_step": NO_REFUSAL_NAME,
            "refusal": NO_REFUSAL_NAME,
            "steps_taken": len(wanted),
        }


def build_view_model(model: PhantomBotsTabModel, build_now: bool = False) -> dict:
    """Return every value the Phantom Bots tab holds as one dict.

    `build_now` reads the bot and fills every box.
    """
    if build_now:
        model.build()
    return {
        "accessible_name": model.accessible_name,
        "container": {
            "spacing_px": CONTENT_SPACING_PX,
            "margins_set": CONTENT_MARGINS_SET,
        },
        "info_label": {
            "text": INFO_TEXT,
            "style_sheet": INFO_STYLE_FORMAT.format(color_hex=NOTE_COLOR),
            "word_wrap": INFO_WORD_WRAP,
        },
        "enable_group": {"title": ENABLE_GROUP_TITLE},
        "enable_check": {"text": ENABLE_CHECK_TEXT, "checked": model.enable_checked},
        "timeframe_group": {"title": TF_GROUP_TITLE},
        "timeframe_hint": {
            "text": TF_HINT_TEXT,
            "style_sheet": TF_HINT_STYLE_FORMAT.format(color_hex=NOTE_COLOR),
            "word_wrap": TF_HINT_WORD_WRAP,
        },
        "timeframe_combo": {
            "row_label": TF_ROW_LABEL,
            "tooltip": TF_TOOLTIP,
            "items": [list(item) for item in model.timeframe_items],
            "current": model.timeframe_current,
            "parent": model.parent_timeframe,
            "default": TIMEFRAME_DEFAULT,
            "refusal": model.refusal,
        },
        "timeframes": list(TIMEFRAMES),
        "fallback_timeframes": list(FALLBACK_TIMEFRAMES),
        "allowed_timeframes": list(model.allowed),
        "exchange_id": model.exchange_id,
        "lock_group": {"title": LOCK_GROUP_TITLE},
        "lock_spin": {
            "row_label": LOCK_ROW_LABEL,
            "minimum": LOCK_MIN,
            "maximum": LOCK_MAX,
            "requested": model.lock_requested,
            "value": model.lock_value,
            "tooltip": LOCK_TOOLTIP,
        },
        "summary_group": {"title": SUMMARY_GROUP_TITLE},
        "forms": {
            "configured_by_host": FORM_CONFIGURED_BY_HOST,
            "configured": model.forms_configured,
        },
        "summary_rows": [list(row) for row in model.summary_rows],
        "phantom_group": {
            "title_format": PHANTOM_GROUP_TITLE_FORMAT,
            "title": PHANTOM_GROUP_TITLE_FORMAT.format(count=model.phantom_count),
            "shown": model.phantom_group_shown,
        },
        "phantom_table": {
            "columns": list(PHANTOM_COLUMNS),
            "column_count": PHANTOM_COLUMN_COUNT,
            "max_height_px": PHANTOM_TABLE_MAX_HEIGHT_PX,
            "pnl_column": PNL_COLUMN,
            "confidence_column": CONFIDENCE_COLUMN,
            "row_count": len(model.phantom_rows),
            "rows": [list(row) for row in model.phantom_rows],
            "row_colors": [list(row) for row in model.phantom_colors],
        },
        "locks_group": {
            "title_format": LOCKS_GROUP_TITLE_FORMAT,
            "title": LOCKS_GROUP_TITLE_FORMAT.format(count=model.locks_count),
            "shown": model.locks_group_shown,
        },
        "locks_table": {
            "columns": list(LOCK_COLUMNS),
            "column_count": LOCK_COLUMN_COUNT,
            "max_height_px": LOCK_TABLE_MAX_HEIGHT_PX,
            "source_bot_column": SOURCE_BOT_COLUMN,
            "direction_column": DIRECTION_COLUMN,
            "row_count": len(model.lock_rows),
            "rows": [list(row) for row in model.lock_rows],
            "row_colors": [list(row) for row in model.lock_colors],
        },
        "table_rules": {
            "header_resize_mode": HEADER_RESIZE_MODE,
            "vertical_header_visible": VERTICAL_HEADER_VISIBLE,
            "edit_triggers": EDIT_TRIGGERS,
            "alternating_row_colors": ALTERNATING_ROW_COLORS,
        },
        "empty_label": {
            "text": model.empty_line,
            "style_sheet": EMPTY_STYLE_FORMAT.format(color_hex=NOTE_COLOR),
            "word_wrap": EMPTY_WORD_WRAP,
            "shown": model.empty_shown,
        },
        "empty_texts": {
            "disabled": EMPTY_DISABLED_TEXT,
            "not_started": EMPTY_NOT_STARTED_TEXT,
            "no_state": EMPTY_NO_STATE_TEXT,
            "none": NO_EMPTY_TEXT,
        },
        "stretch_shown": model.stretch_shown,
        "changes": [list(one) for one in model.changes],
        "labels": {
            "enabled_row": ENABLED_ROW_LABEL,
            "started_row": STARTED_ROW_LABEL,
            "timeframes_row": TIMEFRAMES_ROW_LABEL,
            "dropped_row": DROPPED_ROW_LABEL,
            "below_parent_row": BELOW_PARENT_ROW_LABEL,
            "lock_state_row": LOCK_STATE_ROW_LABEL,
        },
        "texts": {
            "yes": YES_TEXT,
            "no": NO_TEXT,
            "no_timeframes": NO_TIMEFRAMES_TEXT,
            "unlocked": UNLOCKED_TEXT,
            "missing": MISSING_TEXT,
            "unknown_exchange": UNKNOWN_EXCHANGE_TEXT,
            "timeframe_join": TIMEFRAME_JOIN,
            "bullish_mark": BULLISH_MARK,
            "bearish_mark": BEARISH_MARK,
        },
        "formats": {
            "info_style": INFO_STYLE_FORMAT,
            "hint_style": TF_HINT_STYLE_FORMAT,
            "empty_style": EMPTY_STYLE_FORMAT,
            "flag_style": FLAG_STYLE_FORMAT,
            "locked_text": LOCKED_TEXT_FORMAT,
            "locked_style": LOCKED_STYLE_FORMAT,
            "unlocked_style": UNLOCKED_STYLE_FORMAT,
            "tf_supported_tooltip": TF_SUPPORTED_TOOLTIP_FORMAT,
            "tf_unsupported_tooltip": TF_UNSUPPORTED_TOOLTIP_FORMAT,
            "tf_not_higher": NOT_HIGHER_FORMAT,
            "tf_not_offered": NOT_OFFERED_FORMAT,
            "phantom_group_title": PHANTOM_GROUP_TITLE_FORMAT,
            "locks_group_title": LOCKS_GROUP_TITLE_FORMAT,
            "target": TARGET_FORMAT,
            "trades": TRADES_FORMAT,
            "pnl": PNL_FORMAT,
            "votes": VOTES_FORMAT,
            "confidence": CONFIDENCE_FORMAT,
            "candles": CANDLES_FORMAT,
            "this_bot": THIS_BOT_FORMAT,
        },
        "colors": {
            "on": ON_COLOR,
            "waiting": WAITING_COLOR,
            "off": OFF_COLOR,
            "loss": LOSS_COLOR,
            "note": NOTE_COLOR,
            "this_bot": THIS_BOT_COLOR,
        },
        "no_cell_color": NO_CELL_COLOR,
        "thresholds": {
            "confidence_strong_at": CONFIDENCE_STRONG_AT,
            "confidence_fair_at": CONFIDENCE_FAIR_AT,
            "pnl_gain_above": PNL_GAIN_ABOVE,
            "pnl_loss_below": PNL_LOSS_BELOW,
            "lock_minimum": LOCK_MIN,
            "lock_maximum": LOCK_MAX,
            "lock_default": LOCK_DEFAULT,
        },
        "attributes": {
            "enabled": ENABLED_ATTRIBUTE,
            "started": STARTED_ATTRIBUTE,
            "timeframes": TIMEFRAMES_ATTRIBUTE,
            "locked": LOCKED_ATTRIBUTE,
            "lock_timeframe": LOCK_TIMEFRAME_ATTRIBUTE,
            "coordinator": COORDINATOR_ATTRIBUTE,
            "phantom_manager": PHANTOM_MANAGER_ATTRIBUTE,
            "bot_id": BOT_ID_ATTRIBUTE,
            "config": CONFIG_ATTRIBUTE,
            "exchange_id": EXCHANGE_ID_ATTRIBUTE,
            "lock_count": LOCK_COUNT_ATTRIBUTE,
            "ta_timeframe": TA_TIMEFRAME_ATTRIBUTE,
        },
        "keys": {
            "timeframe": TIMEFRAME_KEY,
            "state": STATE_KEY,
            "target": TARGET_KEY,
            "trades": TRADES_KEY,
            "pnl": PNL_KEY,
            "summary": SUMMARY_KEY,
            "bullish": BULLISH_KEY,
            "bearish": BEARISH_KEY,
            "confidence": CONFIDENCE_KEY,
            "source_tf": SOURCE_TF_KEY,
            "source_bot": SOURCE_BOT_KEY,
            "direction": DIRECTION_KEY,
            "candles": CANDLES_KEY,
        },
        "fields": {
            "enable": ENABLE_FIELD,
            "timeframes": TIMEFRAMES_FIELD,
            "lock": LOCK_FIELD,
        },
        "defaults": {
            "money": DEFAULT_MONEY,
            "count": DEFAULT_COUNT,
            "votes": DEFAULT_VOTES,
            "confidence": DEFAULT_CONFIDENCE,
            "bot_id": DEFAULT_BOT_ID,
            "lock_timeframe": DEFAULT_LOCK_TIMEFRAME,
        },
        "no_exchange_id": NO_EXCHANGE_ID,
        "no_config": NO_CONFIG,
        "steps": [STEP_BUILD, STEP_ENABLE, STEP_TIMEFRAME, STEP_LOCK],
        "no_refusal": {"index": NO_REFUSAL_INDEX, "name": NO_REFUSAL_NAME},
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "bus_emits": list(BUS_EMITS),
        "thread_count": THREAD_COUNT,
        "signal_count": SIGNAL_COUNT,
        "call_names": list(CALL_NAMES),
        "calls": [list(call) for call in model.calls],
    }


PANE_MODEL = PhantomBotsTabModel()


def view_model(params: dict) -> dict:
    """Bridge handler for ``phantom_bots_tab.state``.

    Reads ``reset``, ``bot``, ``build`` and ``steps`` from the request
    parameters. The tab's last state persists between calls because the
    tab does; ``reset`` is what a fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = PhantomBotsTabModel()
    bot = params.get("bot")
    if bot is not None:
        given_phantoms = bot.get("phantoms")
        PANE_MODEL.bot = BotSource(
            exchange_id=bot.get("exchange_id", NO_EXCHANGE_ID),
            ta_timeframe=bot.get("ta_timeframe", PARENT_TIMEFRAME_DEFAULT),
            enabled=bot.get("enabled", False),
            started=bot.get("started", False),
            timeframes=bot.get("timeframes"),
            dropped=bot.get("dropped"),
            locked=bot.get("locked", False),
            lock_timeframe=bot.get("lock_timeframe", DEFAULT_LOCK_TIMEFRAME),
            bot_id=bot.get("bot_id", DEFAULT_BOT_ID),
            manager=(
                None
                if given_phantoms is None
                else PhantomManagerSource(
                    [PhantomSource(one) for one in given_phantoms]
                )
            ),
            coordinator=CoordinatorSource(
                bot.get("lock_candle_count", LOCK_DEFAULT), bot.get("locks")
            ),
        )
    steps = params.get("steps")
    if steps:
        PANE_MODEL.run_steps(steps)
        return build_view_model(PANE_MODEL)
    return build_view_model(PANE_MODEL, params.get("build", bot is not None))
