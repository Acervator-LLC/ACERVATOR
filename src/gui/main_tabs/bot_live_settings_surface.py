"""bot_live_settings_surface.py -- the Live Bot Settings window, without Qt.

Describes the window the operator opens from a running bot's Detail
button. It carries a title, a header line naming the pair and the mode,
a coloured state badge, a Prev and a Next button for walking the swarm,
a row of tabs chosen by the bot's mode, an Apply Changes button, a Close
button and a line reporting what is pending or what was applied.

``BotLiveSettingsModel`` holds the window's state. ``build`` fills it
from the bot. ``mark_changed`` records one edited field and
``apply_changes`` sends the edits to the bot, routing the fields that
have a live-update method on the bot and writing the rest onto the
config. ``BotSource``, ``BotConfigSource`` and ``BotManagerSource`` are
plain stand-ins for the running bot, its config and its manager, so the
window can be driven over the bridge from values alone.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``bot_live_settings.state`` method, which is how the Electron
renderer reaches it. Every value below is written out here rather than
read from ``src.gui.bot_live_settings``, so a value changed on one side
alone is reported. Nothing here imports Qt.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import design_system as ds
from ..color_alpha import rgba

METHOD = "bot_live_settings.state"

LOGGER_NAME = "acervator.gui"

DIALOG_SCREEN_MARGIN_W_PX = 32
DIALOG_SCREEN_MARGIN_H_PX = 72

MINIMUM_W_PX = 640
MINIMUM_H_PX = 720

BOT_ID_SHORT_LENGTH = 8

WINDOW_TITLE_FORMAT = "Bot Settings — {symbol} [{short_id}]"

HEADER_FORMAT = "{symbol}  •  {mode}"
HEADER_STYLE_FORMAT = "font-size: 18px; font-weight: bold; color: {color_hex};"
HEADER_COLOR = ds.PRIMARY

STATE_LABEL_FORMAT = "  {state}"
STATE_STYLE_FORMAT = (
    "font-size: 14px; font-weight: bold; "
    "color: {fg_hex}; "
    "background: {bg_rgba}; "
    "padding: 2px 8px; border-radius: 4px;"
)
STATE_BACKGROUND_ALPHA = 34

STATE_RUNNING = "running"
STATE_IDLE = "idle"
STATE_PAUSED = "paused"
STATE_ERROR = "error"
STATE_STOPPED = "stopped"
STATE_COOLDOWN = "cooldown"

STATE_COLORS = {
    STATE_RUNNING: ds.SUCCESS,
    STATE_IDLE: ds.CARD_METRIC_LABEL,
    STATE_PAUSED: ds.WARNING,
    STATE_ERROR: ds.ERROR,
    STATE_STOPPED: ds.TEXT_MUTED,
    STATE_COOLDOWN: ds.WARNING,
}
# The badge foreground and its tinted ground are one colour, so an
# unknown state names the same token twice.
STATE_UNKNOWN_FG = ds.TEXT_NEUTRAL
STATE_UNKNOWN_BG = ds.TEXT_NEUTRAL

NAV_BUTTON_STYLE = (
    f"QPushButton {{ background: {ds.SURFACE_CONTROL}; color: {ds.PRIMARY}; "
    f"border: 1px solid {ds.GLOW_PRIMARY_EDGE}; border-radius: 4px; "
    "padding: 4px 10px; font-weight: bold; font-size: 12px; "
    "min-width: 70px; }"
    f"QPushButton:hover {{ background: {ds.GLOW_PRIMARY_FAINT}; "
    f"border: 1px solid {ds.PRIMARY}; }}"
    f"QPushButton:disabled {{ background: {ds.CARD_METRIC_BORDER}; "
    f"color: {ds.TEXT_PLACEHOLDER}; border: 1px solid {ds.CARD_METRIC_BORDER}; }}"
)

PREV_LABEL = "◀ Prev"
NEXT_LABEL = "Next ▶"
PREV_TOOLTIP = (
    "Switch to the previous bot in the swarm without " "closing this dialog (Ctrl+Left)"
)
NEXT_TOOLTIP = (
    "Switch to the next bot in the swarm without " "closing this dialog (Ctrl+Right)"
)
PREV_STEP = -1
NEXT_STEP = 1
NAV_SHOWN_ABOVE_SIBLINGS = 1
NAV_NEEDS_SIBLINGS = 2

APPLY_LABEL = "Apply Changes"
APPLY_STYLE = (
    f"QPushButton {{ background: {ds.PRIMARY}; color: {ds.SURFACE_CHART}; "
    "border: none; border-radius: 6px; padding: 8px 20px; "
    "font-weight: bold; font-size: 12px; }"
    f"QPushButton:hover {{ background: {ds.SETTINGS_PRIMARY_HOVER}; }}"
    f"QPushButton:disabled {{ background: {ds.SETTINGS_DISABLED_DEEP}; "
    f"color: {ds.TEXT_MUTED}; }}"
)
APPLY_ENABLED_AT_START = False

CLOSE_LABEL = "Close"
CLOSE_STYLE = (
    f"QPushButton {{ background: {ds.CARD_METRIC_BORDER}; color: {ds.TEXT_INACTIVE}; "
    f"border: 1px solid {ds.MENU_BORDER}; border-radius: 6px; "
    "padding: 8px 20px; }"
    f"QPushButton:hover {{ background: {ds.MENU_BORDER}; }}"
)

CHANGE_EMPTY_TEXT = ""
CHANGE_PENDING_FORMAT = "Pending changes: {fields}"
CHANGE_FIELD_SEPARATOR = ", "
CHANGE_PENDING_STYLE = f"color: {ds.WARNING}; font-size: 11px;"
CHANGE_APPLIED_FORMAT = "Applied {count} change(s) — active immediately"
CHANGE_APPLIED_STYLE = f"color: {ds.SUCCESS}; font-size: 11px;"

MODE_SCRUMMING = "scrumming"
MODE_EXTRACTOR = "extractor"

TAB_STATUS = "Status"
TAB_SETTINGS = "Settings"
TAB_FOLD_TRANCHES = "Fold Tranches"
TAB_STACK_TRANCHES = "Stack Tranches"
TAB_BOT_SWARM = "Bot Swarm"
TAB_MARKET_INSPECTOR = "Market Inspector"
TAB_PHANTOM_BOTS = "Phantom Bots"
TAB_POSITIONS_HELD = "Positions Held"

ANY_MODE = ""
INSTALLED_BY_HOST = "host"
INSTALLED_BY_WINDOW = "window"

# The request names a tab surface reads: the bot for a tab page, and the
# build flag fold_chrome answers its row controls under.
TAB_BOT_PARAM = "bot"
FOLD_CHROME_CONTROLS_PARAM = "controls"

# One row per tab: its name, the mode that gets it, whether the window
# wraps it in a scroller itself, and which side installs it.
TAB_PLAN = (
    (TAB_STATUS, ANY_MODE, True, INSTALLED_BY_WINDOW),
    (TAB_SETTINGS, ANY_MODE, True, INSTALLED_BY_WINDOW),
    (TAB_FOLD_TRANCHES, MODE_SCRUMMING, False, INSTALLED_BY_HOST),
    (TAB_STACK_TRANCHES, MODE_SCRUMMING, False, INSTALLED_BY_HOST),
    (TAB_BOT_SWARM, MODE_SCRUMMING, True, INSTALLED_BY_WINDOW),
    (TAB_MARKET_INSPECTOR, MODE_SCRUMMING, True, INSTALLED_BY_WINDOW),
    (TAB_PHANTOM_BOTS, MODE_SCRUMMING, True, INSTALLED_BY_WINDOW),
    (TAB_POSITIONS_HELD, MODE_EXTRACTOR, True, INSTALLED_BY_WINDOW),
)
FIRST_TAB_INDEX = 0

SHORTCUTS = (("Ctrl+Left", PREV_STEP), ("Ctrl+Right", NEXT_STEP))
SHORTCUT_FAILED_LOG = "sibling navigation shortcuts unavailable: %s"

SCROLL_RESIZABLE = True
SCROLL_FRAME_SHAPE = "NoFrame"

FORM_FIELD_GROWTH = "AllNonFixedFieldsGrow"
FORM_ROW_WRAP = "DontWrapRows"
FORM_HORIZONTAL_SPACING_PX = 12
FORM_VERTICAL_SPACING_PX = 8
FORM_MARGINS_PX = (8, 8, 8, 8)

PHANTOM_ENABLE_FIELD = "enable_phantoms"
PHANTOM_TIMEFRAMES_FIELD = "phantom_timeframes"
PHANTOM_LOCK_FIELD = "lock_candle_count"
PHANTOM_FIELDS = (
    PHANTOM_ENABLE_FIELD,
    PHANTOM_TIMEFRAMES_FIELD,
    PHANTOM_LOCK_FIELD,
)
PHANTOM_ENABLE_ATTRIBUTE = "_phantoms_enabled"
PHANTOM_TIMEFRAMES_ATTRIBUTE = "_phantom_timeframes"
COORDINATOR_ATTRIBUTE = "_coordinator"
COORDINATOR_LOCK_ATTRIBUTE = "lock_candle_count"
PHANTOM_UPDATE_METHOD = "update_phantom_config"
PHANTOM_APPLIED_KEY = "applied"
PHANTOM_CAVEATS_KEY = "caveats"

RUNTIME_ROUTED = {
    "target_balance": "set_target_balance_live",
    "visibility": "set_visibility_live",
    "aggressive_trading": "set_aggressive_live",
    "hedge_balance": "set_hedge_balance_live",
    "extractor_chunk_size_usd": "set_chunk_size_usd",
}
ROUTE_APPLIED_KEY = "applied"
ROUTE_REASON_KEY = "reason"
ROUTE_UNKNOWN_REASON = "unknown"

APPLIED_ENTRY_FORMAT = "{field}={value}"
APPLIED_SYNCED_FORMAT = "{field}={value} (runtime+anchor synced)"
APPLIED_REFUSED_FORMAT = "{field}={value} (REFUSED: {reason})"
APPLIED_ERROR_FORMAT = "{field}={value} (ERROR: {exc})"
APPLIED_ENTRY_SEPARATOR = "="
APPLIED_JOIN = ", "

PHANTOM_CAVEAT_LOG = "Bot %s phantom caveat: %s"
PHANTOM_FAILED_LOG = "Bot %s: phantom config update failed: %s"
ROUTE_REFUSED_LOG = "Bot %s: %s live-update refused: %s"
ROUTE_RAISED_LOG = "Bot %s: %s live-update raised: %s"
APPLIED_LOG = "Bot %s: live settings changed: %s"
SAVE_FAILED_LOG = (
    "%s: cleared in memory but NOT saved (%s: %s); a "
    "restart before the next rolling save will restore "
    "it."
)

SAVE_METHOD = "save_all_state"
HELD_BOTS_ATTR = "_bots"
BOT_MANAGER_ATTRIBUTE = "_bot_manager"
NO_MANAGER_REASON = "no bot manager is attached to this panel"
SAVED_REASON = ""
SAVE_FAILED_FORMAT = "{kind}: {message}"

AGE_SECONDS_FORMAT = "{seconds}s"
AGE_MINUTES_FORMAT = "{minutes}m"
AGE_HOURS_FORMAT = "{hours:.1f}h"
AGE_DAYS_FORMAT = "{days:.1f}d"
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400

FOLD_SORT_QUEUE_ORDER = "Queue order"

NO_TABS = 0
NO_SIBLINGS: list = []
NO_NAVIGATION: Optional[str] = None
NO_CHANGES = 0
NO_MANAGER = None
SIGNAL_NAME = "settings_changed"

ACTIONS = {
    "prev_clicked": "navigate_to_prev",
    "next_clicked": "navigate_to_next",
    "apply_clicked": "apply_changes",
    "close_clicked": "accept",
}

TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()
SKIN: dict = {}
STYLE_SHEET = ""

BUILD_START = "build.start"
BUILD_TITLE = "build.title"
BUILD_MINIMUM = "build.minimum"
BUILD_HEADER = "build.header"
BUILD_STATE = "build.state"
BUILD_NAV = "build.nav"
BUILD_NAV_SHOWN = "build.nav_shown"
BUILD_NAV_HIDDEN = "build.nav_hidden"
BUILD_TAB = "build.tab"
BUILD_TAB_SKIPPED = "build.tab_skipped"
BUILD_APPLY = "build.apply"
BUILD_CLOSE = "build.close"
BUILD_CHANGE_LABEL = "build.change_label"
BUILD_SHORTCUTS = "build.shortcuts"
BUILD_NO_SHORTCUTS = "build.no_shortcuts"
BUILD_SIZED = "build.sized"
MARK_RECORDED = "mark.recorded"
MARK_REVERTED = "mark.reverted"
APPLY_NOTHING = "apply.nothing"
APPLY_PHANTOM = "apply.phantom"
APPLY_PHANTOM_FAILED = "apply.phantom_failed"
APPLY_ROUTED = "apply.routed"
APPLY_REFUSED = "apply.refused"
APPLY_RAISED = "apply.raised"
APPLY_SETATTR = "apply.setattr"
APPLY_DROPPED = "apply.dropped"
APPLY_SENT = "apply.sent"
NAVIGATE_REFUSED = "navigate.refused"
NAVIGATE_LOST = "navigate.lost"
NAVIGATE_STAGED = "navigate.staged"
SAVE_REFUSED = "save.refused"
SAVE_RAISED = "save.raised"
SAVE_DONE = "save.done"

CALL_NAMES = (
    BUILD_START,
    BUILD_TITLE,
    BUILD_MINIMUM,
    BUILD_HEADER,
    BUILD_STATE,
    BUILD_NAV,
    BUILD_NAV_SHOWN,
    BUILD_NAV_HIDDEN,
    BUILD_TAB,
    BUILD_TAB_SKIPPED,
    BUILD_APPLY,
    BUILD_CLOSE,
    BUILD_CHANGE_LABEL,
    BUILD_SHORTCUTS,
    BUILD_NO_SHORTCUTS,
    BUILD_SIZED,
    MARK_RECORDED,
    MARK_REVERTED,
    APPLY_NOTHING,
    APPLY_PHANTOM,
    APPLY_PHANTOM_FAILED,
    APPLY_ROUTED,
    APPLY_REFUSED,
    APPLY_RAISED,
    APPLY_SETATTR,
    APPLY_DROPPED,
    APPLY_SENT,
    NAVIGATE_REFUSED,
    NAVIGATE_LOST,
    NAVIGATE_STAGED,
    SAVE_REFUSED,
    SAVE_RAISED,
    SAVE_DONE,
)

ModelCall = list


def tab_content_demand_px(pages: Any) -> tuple:
    """The widest and tallest content, and the widest and tallest page.

    ``pages`` is one pair of sizes per tab: what the tab's content asks
    for, and what the scroller standing in front of it reports. The two
    disagree wherever a scroller caps the answer, and that gap is what
    the window has to read past.
    """
    content_w = content_h = page_w = page_h = 0
    for page in pages or ():
        if page is None:
            continue
        content, wrapper = page
        content_w = max(content_w, content[0])
        content_h = max(content_h, content[1])
        page_w = max(page_w, wrapper[0])
        page_h = max(page_h, wrapper[1])
    return content_w, content_h, page_w, page_h


def dialog_content_size_px(
    dialog_hint_w: int,
    dialog_hint_h: int,
    page_w: int,
    page_h: int,
    content_w: int,
    content_h: int,
) -> tuple:
    """The window size that puts the content inside the tab viewport.

    The gap between what the window's layout asks for and what its
    largest page asks for is the chrome drawn around that page.
    """
    return (
        int(content_w) + int(dialog_hint_w) - int(page_w),
        int(content_h) + int(dialog_hint_h) - int(page_h),
    )


def dialog_open_size_px(
    needed_w: int,
    needed_h: int,
    available_w: int,
    available_h: int,
    minimum_w: int,
    minimum_h: int,
) -> tuple:
    """The size the window opens at: its content, capped by the screen.

    A window larger than the display is worse than one too small, so the
    content size is capped. The cap never falls below the window's own
    minimum.
    """
    ceiling_w = max(int(minimum_w), int(available_w) - DIALOG_SCREEN_MARGIN_W_PX)
    ceiling_h = max(int(minimum_h), int(available_h) - DIALOG_SCREEN_MARGIN_H_PX)
    return (
        min(max(int(needed_w), int(minimum_w)), ceiling_w),
        min(max(int(needed_h), int(minimum_h)), ceiling_h),
    )


def window_title(symbol: Any, bot_id: Any) -> str:
    """The words in the window's own title bar."""
    return WINDOW_TITLE_FORMAT.format(
        symbol=symbol, short_id=bot_id[:BOT_ID_SHORT_LENGTH]
    )


def header_text(symbol: Any, mode: Any) -> str:
    """The pair and the mode, as the header line reads them."""
    return HEADER_FORMAT.format(symbol=symbol, mode=mode.upper())


def state_text(state: Any) -> str:
    """The words on the state badge."""
    return STATE_LABEL_FORMAT.format(state=state.upper())


def state_style(state: Any) -> str:
    """The colours on the state badge for one bot state."""
    return STATE_STYLE_FORMAT.format(
        fg_hex=STATE_COLORS.get(state, STATE_UNKNOWN_FG),
        bg_rgba=rgba(
            STATE_COLORS.get(state, STATE_UNKNOWN_BG),
            STATE_BACKGROUND_ALPHA,
        ),
    )


def tabs_for_mode(mode: Any) -> list:
    """The tabs one bot mode is given, in the order they are added."""
    return [row[0] for row in TAB_PLAN if row[1] in (ANY_MODE, mode)]


def pending_text(fields: Any) -> str:
    """The line reporting which fields are edited but not yet sent."""
    return CHANGE_PENDING_FORMAT.format(
        fields=CHANGE_FIELD_SEPARATOR.join(fields),
    )


def applied_text(count: Any) -> str:
    """The line reporting how many edits were sent."""
    return CHANGE_APPLIED_FORMAT.format(count=count)


def format_age(seconds: Any) -> str:
    """One age in seconds, minutes, hours or days.

    Whole seconds and whole minutes below an hour, then one decimal
    place. The reading is not checked here: a caller that hands this an
    unbounded number gets the answer that number produces.
    """
    if seconds < SECONDS_PER_MINUTE:
        return AGE_SECONDS_FORMAT.format(seconds=int(seconds))
    if seconds < SECONDS_PER_HOUR:
        return AGE_MINUTES_FORMAT.format(minutes=int(seconds / SECONDS_PER_MINUTE))
    if seconds < SECONDS_PER_DAY:
        return AGE_HOURS_FORMAT.format(hours=seconds / SECONDS_PER_HOUR)
    return AGE_DAYS_FORMAT.format(days=seconds / SECONDS_PER_DAY)


class BotConfigSource:
    """The bot's config, holding only the fields the window reads.

    A field named in ``missing`` is absent from the object, which is how
    a window driven against a config without that field is built.
    """

    def __init__(
        self,
        symbol: Any = "CHIP/USD",
        mode: Any = MODE_SCRUMMING,
        fields: Any = None,
        missing: Any = None,
    ) -> None:
        self.symbol = symbol
        self.mode = mode
        absent = list(missing or ())
        for name, value in dict(fields or {}).items():
            if name not in absent:
                setattr(self, name, value)


class BotManagerSource:
    """The manager the window asks for its sibling bots and for a save."""

    def __init__(
        self,
        bot_ids: Any = None,
        ids_raise: Optional[BaseException] = None,
        save_raises: Optional[BaseException] = None,
        can_save: bool = True,
    ) -> None:
        self.bot_ids = list(bot_ids or ())
        self.ids_raise = ids_raise
        self.save_raises = save_raises
        self.saves: list = []
        if can_save:
            setattr(self, SAVE_METHOD, self.save_all)

    def ordered_bot_ids(self) -> list:
        if self.ids_raise is not None:
            raise self.ids_raise
        return list(self.bot_ids)

    def save_all(self) -> None:
        if self.save_raises is not None:
            raise self.save_raises
        self.saves.append(1)


class BotSource:
    """The running bot the window reads and writes.

    ``routes`` names the live-update methods this bot carries and what
    each returns; a route named here but absent from the bot is how the
    plain config write is driven.
    """

    def __init__(
        self,
        config: Any = None,
        bot_id: Any = "botalpha0001beta",
        state: Any = STATE_RUNNING,
        runtime: Any = None,
        routes: Any = None,
        phantom_answer: Any = None,
        phantom_raises: Optional[BaseException] = None,
        with_phantom_update: bool = False,
        manager: Any = NO_MANAGER,
    ) -> None:
        self.config = BotConfigSource() if config is None else config
        self.bot_id = bot_id
        self.state = state
        self.routes = dict(routes or {})
        self.route_calls: list = []
        self.phantom_answer = phantom_answer
        self.phantom_raises = phantom_raises
        self.phantom_calls: list = []
        for name, value in dict(runtime or {}).items():
            setattr(self, name, value)
        if manager is not NO_MANAGER:
            setattr(self, BOT_MANAGER_ATTRIBUTE, manager)
        if with_phantom_update:
            setattr(self, PHANTOM_UPDATE_METHOD, self.run_phantom_update)
        for route in self.routes:
            setattr(self, route, self.route_runner(route))

    def route_runner(self, route: Any):
        """One live-update method, answering what ``routes`` named for it."""

        def run(value):
            self.route_calls.append([route, value])
            answer = self.routes[route]
            if isinstance(answer, BaseException):
                raise answer
            return answer

        return run

    def run_phantom_update(self, **changes) -> dict:
        """The bot's phantom method, present only when the caller asked for it."""
        self.phantom_calls.append(dict(changes))
        if self.phantom_raises is not None:
            raise self.phantom_raises
        return dict(self.phantom_answer or {})


class BotLiveSettingsModel:
    """The Live Bot Settings window, its parts and its branch trail.

    ``build`` fills the title, the header, the state badge, the two
    navigation buttons, the tabs the bot's mode is given, the Apply and
    Close buttons and the change line. ``mark_changed`` and
    ``apply_changes`` carry the operator's edits. Every step is appended
    to ``calls`` in the order the shipped window takes it.
    """

    fold_sort_key: str = FOLD_SORT_QUEUE_ORDER

    def __init__(
        self,
        bot: Any = None,
        bot_manager: Any = None,
        shortcuts_raise: Optional[BaseException] = None,
    ) -> None:
        self.bot = bot
        self.bot_manager = bot_manager
        self.shortcuts_raise = shortcuts_raise
        self.changes: dict = {}
        self.pending_navigate_to = NO_NAVIGATION
        self.title = CHANGE_EMPTY_TEXT
        self.minimum_size_px = (MINIMUM_W_PX, MINIMUM_H_PX)
        self.header_label = CHANGE_EMPTY_TEXT
        self.header_style = CHANGE_EMPTY_TEXT
        self.state_label = CHANGE_EMPTY_TEXT
        self.state_style = CHANGE_EMPTY_TEXT
        self.nav_shown = False
        self.tabs: list = []
        self.wrapped_tabs: list = []
        self.current_tab = FIRST_TAB_INDEX
        self.apply_enabled = APPLY_ENABLED_AT_START
        self.change_label = CHANGE_EMPTY_TEXT
        self.change_style = CHANGE_PENDING_STYLE
        self.shortcuts: list = []
        self.opened_size_px = (MINIMUM_W_PX, MINIMUM_H_PX)
        self.applied: list = []
        self.sent: list = []
        self.logged: list = []
        self.accepted = False
        self.forms: list = []
        self.calls: list = []

    def build(self, pages: Any = None, hint: Any = None, available: Any = None) -> None:
        """Fill the window in the order the shipped window fills it.

        ``pages``, ``hint`` and ``available`` are the sizes the window
        asks its tabs, its own layout and the display for. Left out, the
        window keeps its minimum size, which is what the shipped window
        settles at when its tabs ask for nothing.
        """
        self.calls = []
        self.tabs = []
        self.wrapped_tabs = []
        self.shortcuts = []
        self.calls.append([BUILD_START])
        config = self.bot.config
        self.title = window_title(config.symbol, self.bot.bot_id)
        self.calls.append([BUILD_TITLE, self.title])
        self.minimum_size_px = (MINIMUM_W_PX, MINIMUM_H_PX)
        self.calls.append([BUILD_MINIMUM])
        self.header_label = header_text(config.symbol, config.mode)
        self.header_style = HEADER_STYLE_FORMAT.format(color_hex=HEADER_COLOR)
        self.calls.append([BUILD_HEADER, self.header_label])
        state = self.bot.state
        self.state_label = state_text(state)
        self.state_style = state_style(state)
        self.calls.append([BUILD_STATE, state])
        self.calls.append([BUILD_NAV])
        siblings = self.sibling_bot_ids()
        self.nav_shown = len(siblings) > NAV_SHOWN_ABOVE_SIBLINGS
        self.calls.append([BUILD_NAV_SHOWN if self.nav_shown else BUILD_NAV_HIDDEN])
        for name, mode, wrapped, _installed in TAB_PLAN:
            if mode not in (ANY_MODE, config.mode):
                self.calls.append([BUILD_TAB_SKIPPED, name])
                continue
            self.tabs.append(name)
            if wrapped:
                self.wrapped_tabs.append(self.wrap_scrollable(name))
            self.calls.append([BUILD_TAB, name])
        self.apply_enabled = APPLY_ENABLED_AT_START
        self.calls.append([BUILD_APPLY])
        self.calls.append([BUILD_CLOSE])
        self.change_label = CHANGE_EMPTY_TEXT
        self.change_style = CHANGE_PENDING_STYLE
        self.calls.append([BUILD_CHANGE_LABEL])
        self.install_shortcuts(self.nav_shown)
        self.opened_size_px = self.open_at_content_size(pages, hint, available)
        self.calls.append([BUILD_SIZED, list(self.opened_size_px)])
        return None

    def install_shortcuts(self, can_navigate: bool) -> None:
        """Wire the two keyboard shortcuts, or record why they are absent."""
        if self.shortcuts_raise is not None:
            self.logged.append(
                [SHORTCUT_FAILED_LOG, str(self.shortcuts_raise), "debug"]
            )
            self.calls.append([BUILD_NO_SHORTCUTS])
            return None
        if can_navigate:
            self.shortcuts = [list(pair) for pair in SHORTCUTS]
            self.calls.append([BUILD_SHORTCUTS, len(self.shortcuts)])
        else:
            self.calls.append([BUILD_NO_SHORTCUTS])
        return None

    def open_at_content_size(
        self, pages: Any = None, hint: Any = None, available: Any = None
    ) -> tuple:
        """The size the window opens at, given what its tabs ask for.

        Not a minimum. The window can still be shrunk to the floor it
        already carried.
        """
        if not pages or hint is None:
            return self.minimum_size_px
        content_w, content_h, page_w, page_h = tab_content_demand_px(pages)
        needed_w, needed_h = dialog_content_size_px(
            hint[0], hint[1], page_w, page_h, content_w, content_h
        )
        if available is None:
            available = (needed_w, needed_h)
        return dialog_open_size_px(
            needed_w,
            needed_h,
            available[0],
            available[1],
            self.minimum_size_px[0],
            self.minimum_size_px[1],
        )

    def wrap_scrollable(self, name: Any) -> list:
        """One tab put inside a scroller, as the scroller is asked for."""
        return [name, SCROLL_RESIZABLE, SCROLL_FRAME_SHAPE]

    def configure_form(self, form: Any) -> None:
        """Apply the row sizing every form on this window is given."""
        record = dict(form or {})
        record["field_growth"] = FORM_FIELD_GROWTH
        record["row_wrap"] = FORM_ROW_WRAP
        record["horizontal_spacing_px"] = FORM_HORIZONTAL_SPACING_PX
        record["vertical_spacing_px"] = FORM_VERTICAL_SPACING_PX
        record["margins_px"] = list(FORM_MARGINS_PX)
        self.forms.append(record)
        return None

    def sibling_bot_ids(self) -> list:
        """The ordered bot ids in the manager, or none when it cannot answer.

        ``BotManager`` keeps the fleet in ``_bots`` in insertion order and
        offers no ``ordered_bot_ids``, so both routes are read.
        """
        if self.bot_manager is None:
            return list(NO_SIBLINGS)
        try:
            return list(self.bot_manager.ordered_bot_ids())
        except AttributeError:
            pass
        except Exception:
            return list(NO_SIBLINGS)
        try:
            return list(getattr(self.bot_manager, HELD_BOTS_ATTR).keys())
        except Exception:
            return list(NO_SIBLINGS)

    def navigate_to_sibling(self, direction: Any) -> None:
        """Stage a move to the next or previous bot and close the window.

        Edits not yet applied are dropped, the same as pressing Close.
        """
        ids = self.sibling_bot_ids()
        if len(ids) < NAV_NEEDS_SIBLINGS:
            self.calls.append([NAVIGATE_REFUSED, len(ids)])
            return None
        try:
            here = ids.index(self.bot.bot_id)
        except ValueError:
            here = 0 if direction > 0 else 1
            self.calls.append([NAVIGATE_LOST, here])
        self.pending_navigate_to = ids[(here + direction) % len(ids)]
        self.accepted = True
        self.calls.append([NAVIGATE_STAGED, self.pending_navigate_to])
        return None

    def navigate_to_prev(self) -> None:
        """Move to the previous bot in the swarm."""
        return self.navigate_to_sibling(PREV_STEP)

    def navigate_to_next(self) -> None:
        """Move to the next bot in the swarm."""
        return self.navigate_to_sibling(NEXT_STEP)

    def accept(self) -> None:
        """Close the window."""
        self.accepted = True
        return None

    def active_tab_index(self) -> int:
        """Which tab the operator is looking at, or the first one."""
        try:
            return int(self.current_tab)
        except Exception:
            return FIRST_TAB_INDEX

    def original_value(self, field: Any) -> Any:
        """What the bot holds for one field before the operator edits it.

        The three phantom fields are runtime values on the bot, not
        config fields, so each is read from the place that holds it.
        """
        if field == PHANTOM_ENABLE_FIELD:
            return getattr(self.bot, PHANTOM_ENABLE_ATTRIBUTE, None)
        if field == PHANTOM_TIMEFRAMES_FIELD:
            return list(getattr(self.bot, PHANTOM_TIMEFRAMES_ATTRIBUTE, []))
        if field == PHANTOM_LOCK_FIELD:
            coordinator = getattr(self.bot, COORDINATOR_ATTRIBUTE, None)
            if coordinator:
                return getattr(coordinator, COORDINATOR_LOCK_ATTRIBUTE, None)
            return None
        return getattr(self.bot.config, field, None)

    def mark_changed(self, field: Any, value: Any) -> None:
        """Record one edited field, or drop it when it is back where it was."""
        if field == PHANTOM_TIMEFRAMES_FIELD:
            value = list(value)
        original = self.original_value(field)
        if value == original:
            self.changes.pop(field, None)
            self.calls.append([MARK_REVERTED, field])
        else:
            self.changes[field] = value
            self.calls.append([MARK_RECORDED, field])
        if self.changes:
            self.apply_enabled = True
            self.change_label = pending_text(list(self.changes.keys()))
        else:
            self.apply_enabled = False
            self.change_label = CHANGE_EMPTY_TEXT
        return None

    def apply_changes(self) -> None:
        """Send every pending edit to the bot and report what was sent."""
        if not self.changes:
            self.calls.append([APPLY_NOTHING])
            return None
        config = self.bot.config
        short_id = self.bot.bot_id[:BOT_ID_SHORT_LENGTH]
        self.applied = []
        phantom = {
            field: value
            for field, value in self.changes.items()
            if field in PHANTOM_FIELDS
        }
        other = {
            field: value
            for field, value in self.changes.items()
            if field not in PHANTOM_FIELDS
        }
        if phantom and hasattr(self.bot, PHANTOM_UPDATE_METHOD):
            self.send_phantom(phantom, short_id)
        for field, value in other.items():
            self.send_one(field, value, config, short_id)
        self.logged.append(
            [APPLIED_LOG, short_id, APPLIED_JOIN.join(self.applied), "info"]
        )
        self.changes.clear()
        self.apply_enabled = False
        self.change_label = applied_text(len(self.applied))
        self.change_style = CHANGE_APPLIED_STYLE
        self.sent.append(
            [
                self.bot.bot_id,
                {
                    name: getattr(config, name, None)
                    for name in [
                        entry.split(APPLIED_ENTRY_SEPARATOR)[0]
                        for entry in self.applied
                    ]
                },
            ]
        )
        self.calls.append([APPLY_SENT, len(self.applied)])
        return None

    def send_phantom(self, phantom: Any, short_id: Any) -> None:
        """Send the phantom fields through the bot's own phantom method."""
        try:
            answer = getattr(self.bot, PHANTOM_UPDATE_METHOD)(**phantom)
            for field, value in answer.get(PHANTOM_APPLIED_KEY, {}).items():
                self.applied.append(
                    APPLIED_ENTRY_FORMAT.format(field=field, value=value)
                )
            for caveat in answer.get(PHANTOM_CAVEATS_KEY, []):
                self.logged.append([PHANTOM_CAVEAT_LOG, short_id, caveat, "info"])
            self.calls.append([APPLY_PHANTOM, len(phantom)])
        except Exception as exc:
            self.logged.append([PHANTOM_FAILED_LOG, short_id, str(exc), "warning"])
            self.calls.append([APPLY_PHANTOM_FAILED, type(exc).__name__])
        return None

    def send_one(self, field: Any, value: Any, config: Any, short_id: Any) -> None:
        """Send one non-phantom field, by its route or onto the config."""
        route = RUNTIME_ROUTED.get(field)
        if route and hasattr(self.bot, route):
            try:
                answer = getattr(self.bot, route)(value)
                if answer.get(ROUTE_APPLIED_KEY):
                    self.applied.append(
                        APPLIED_SYNCED_FORMAT.format(field=field, value=value)
                    )
                    self.calls.append([APPLY_ROUTED, field])
                else:
                    reason = answer.get(ROUTE_REASON_KEY, ROUTE_UNKNOWN_REASON)
                    self.logged.append(
                        [ROUTE_REFUSED_LOG, short_id, field, reason, "warning"]
                    )
                    self.applied.append(
                        APPLIED_REFUSED_FORMAT.format(
                            field=field, value=value, reason=reason
                        )
                    )
                    self.calls.append([APPLY_REFUSED, field])
            except Exception as exc:
                self.logged.append(
                    [ROUTE_RAISED_LOG, short_id, field, str(exc), "warning"]
                )
                self.applied.append(
                    APPLIED_ERROR_FORMAT.format(field=field, value=value, exc=exc)
                )
                self.calls.append([APPLY_RAISED, field])
        elif hasattr(config, field):
            setattr(config, field, value)
            self.applied.append(APPLIED_ENTRY_FORMAT.format(field=field, value=value))
            self.calls.append([APPLY_SETATTR, field])
        else:
            self.calls.append([APPLY_DROPPED, field])
        return None

    def bot_manager_for_save(self) -> Any:
        """The object that owns the fleet save, or none when there is none."""
        for candidate in (
            self.bot_manager,
            getattr(self.bot, BOT_MANAGER_ATTRIBUTE, None),
        ):
            if callable(getattr(candidate, SAVE_METHOD, None)):
                return candidate
        return None

    def save_fleet_state_now(self, what: Any) -> tuple:
        """Write the fleet to disk in this click. Reports saved and why not.

        A clear that ran in memory and did not reach disk comes back as
        text, so the operator reads the failure rather than losing the
        records at the next restart.
        """
        manager = self.bot_manager_for_save()
        saver = getattr(manager, SAVE_METHOD, None)
        if not callable(saver):
            self.calls.append([SAVE_REFUSED])
            return (False, NO_MANAGER_REASON)
        try:
            saver()
        except Exception as exc:
            kind = type(exc).__name__
            self.logged.append([SAVE_FAILED_LOG, what, kind, str(exc), "warning"])
            self.calls.append([SAVE_RAISED, kind])
            return (False, SAVE_FAILED_FORMAT.format(kind=kind, message=exc))
        self.calls.append([SAVE_DONE])
        return (True, SAVED_REASON)


def build_model(
    bot: Any = None,
    bot_manager: Any = None,
    build_now: bool = False,
    **wiring,
) -> BotLiveSettingsModel:
    """One window driven from one bot."""
    model = BotLiveSettingsModel(
        BotSource() if bot is None else bot, bot_manager, **wiring
    )
    if build_now:
        model.build()
    return model


PANE_MODEL: Optional[BotLiveSettingsModel] = None


def pane_model() -> BotLiveSettingsModel:
    """The one window the bridge keeps between calls.

    Built on the first request, never at import: building one reads the
    bot, and reading a bot reaches the operator's own settings.
    """
    global PANE_MODEL
    if PANE_MODEL is None:
        PANE_MODEL = BotLiveSettingsModel(BotSource())
    return PANE_MODEL


def tab_bot(model: BotLiveSettingsModel) -> dict:
    """The bot a tab of this window is asked for, read off ``model.bot``.

    The tab surfaces build against the bot named in their request, so the
    window publishes the one it holds rather than each tab opening on its
    own stand-in.
    """
    config = model.bot.config
    return {
        "bot_id": model.bot.bot_id,
        "symbol": config.symbol,
        "mode": config.mode,
        "state": model.bot.state,
    }


def build_view_model(model: BotLiveSettingsModel) -> dict:
    """Return every value the window holds as one dict."""
    return {
        "method": METHOD,
        "logger_name": LOGGER_NAME,
        "bot": tab_bot(model),
        "tab_bot_param": TAB_BOT_PARAM,
        "fold_chrome_controls_param": FOLD_CHROME_CONTROLS_PARAM,
        "title": model.title,
        "title_format": WINDOW_TITLE_FORMAT,
        "bot_id_short_length": BOT_ID_SHORT_LENGTH,
        "minimum_size_px": list(model.minimum_size_px),
        "minimum_w_px": MINIMUM_W_PX,
        "minimum_h_px": MINIMUM_H_PX,
        "screen_margin_w_px": DIALOG_SCREEN_MARGIN_W_PX,
        "screen_margin_h_px": DIALOG_SCREEN_MARGIN_H_PX,
        "opened_size_px": list(model.opened_size_px),
        "header_label": model.header_label,
        "header_format": HEADER_FORMAT,
        "header_style": model.header_style,
        "header_style_format": HEADER_STYLE_FORMAT,
        "header_color": HEADER_COLOR,
        "state_label": model.state_label,
        "state_label_format": STATE_LABEL_FORMAT,
        "state_style": model.state_style,
        "state_style_format": STATE_STYLE_FORMAT,
        "state_colors": dict(STATE_COLORS),
        "state_unknown_fg": STATE_UNKNOWN_FG,
        "state_unknown_bg": STATE_UNKNOWN_BG,
        "state_running": STATE_RUNNING,
        "state_idle": STATE_IDLE,
        "state_paused": STATE_PAUSED,
        "state_error": STATE_ERROR,
        "state_stopped": STATE_STOPPED,
        "state_cooldown": STATE_COOLDOWN,
        "nav_style": NAV_BUTTON_STYLE,
        "prev_label": PREV_LABEL,
        "next_label": NEXT_LABEL,
        "prev_tooltip": PREV_TOOLTIP,
        "next_tooltip": NEXT_TOOLTIP,
        "prev_step": PREV_STEP,
        "next_step": NEXT_STEP,
        "nav_shown": model.nav_shown,
        "nav_shown_above_siblings": NAV_SHOWN_ABOVE_SIBLINGS,
        "nav_needs_siblings": NAV_NEEDS_SIBLINGS,
        "siblings": model.sibling_bot_ids(),
        "pending_navigate_to": model.pending_navigate_to,
        "accepted": model.accepted,
        "tabs": list(model.tabs),
        "tab_plan": [list(row) for row in TAB_PLAN],
        "wrapped_tabs": [list(one) for one in model.wrapped_tabs],
        "current_tab": model.active_tab_index(),
        "first_tab_index": FIRST_TAB_INDEX,
        "no_tabs": NO_TABS,
        "tab_status": TAB_STATUS,
        "tab_settings": TAB_SETTINGS,
        "tab_fold_tranches": TAB_FOLD_TRANCHES,
        "tab_stack_tranches": TAB_STACK_TRANCHES,
        "tab_bot_swarm": TAB_BOT_SWARM,
        "tab_market_inspector": TAB_MARKET_INSPECTOR,
        "tab_phantom_bots": TAB_PHANTOM_BOTS,
        "tab_positions_held": TAB_POSITIONS_HELD,
        "mode_scrumming": MODE_SCRUMMING,
        "mode_extractor": MODE_EXTRACTOR,
        "any_mode": ANY_MODE,
        "installed_by_host": INSTALLED_BY_HOST,
        "installed_by_window": INSTALLED_BY_WINDOW,
        "scroll_resizable": SCROLL_RESIZABLE,
        "scroll_frame_shape": SCROLL_FRAME_SHAPE,
        "form_field_growth": FORM_FIELD_GROWTH,
        "form_row_wrap": FORM_ROW_WRAP,
        "form_horizontal_spacing_px": FORM_HORIZONTAL_SPACING_PX,
        "form_vertical_spacing_px": FORM_VERTICAL_SPACING_PX,
        "form_margins_px": list(FORM_MARGINS_PX),
        "forms": [dict(one) for one in model.forms],
        "apply_label": APPLY_LABEL,
        "apply_style": APPLY_STYLE,
        "apply_enabled": model.apply_enabled,
        "apply_enabled_at_start": APPLY_ENABLED_AT_START,
        "close_label": CLOSE_LABEL,
        "close_style": CLOSE_STYLE,
        "change_label": model.change_label,
        "change_style": model.change_style,
        "change_empty_text": CHANGE_EMPTY_TEXT,
        "change_pending_format": CHANGE_PENDING_FORMAT,
        "change_field_separator": CHANGE_FIELD_SEPARATOR,
        "change_pending_style": CHANGE_PENDING_STYLE,
        "change_applied_format": CHANGE_APPLIED_FORMAT,
        "change_applied_style": CHANGE_APPLIED_STYLE,
        "changes": {name: value for name, value in model.changes.items()},
        "no_changes": NO_CHANGES,
        "applied": list(model.applied),
        "applied_entry_format": APPLIED_ENTRY_FORMAT,
        "applied_synced_format": APPLIED_SYNCED_FORMAT,
        "applied_refused_format": APPLIED_REFUSED_FORMAT,
        "applied_error_format": APPLIED_ERROR_FORMAT,
        "applied_entry_separator": APPLIED_ENTRY_SEPARATOR,
        "applied_join": APPLIED_JOIN,
        "sent": [list(one) for one in model.sent],
        "signal_name": SIGNAL_NAME,
        "phantom_fields": list(PHANTOM_FIELDS),
        "phantom_enable_field": PHANTOM_ENABLE_FIELD,
        "phantom_timeframes_field": PHANTOM_TIMEFRAMES_FIELD,
        "phantom_lock_field": PHANTOM_LOCK_FIELD,
        "phantom_enable_attribute": PHANTOM_ENABLE_ATTRIBUTE,
        "phantom_timeframes_attribute": PHANTOM_TIMEFRAMES_ATTRIBUTE,
        "coordinator_attribute": COORDINATOR_ATTRIBUTE,
        "coordinator_lock_attribute": COORDINATOR_LOCK_ATTRIBUTE,
        "phantom_update_method": PHANTOM_UPDATE_METHOD,
        "phantom_applied_key": PHANTOM_APPLIED_KEY,
        "phantom_caveats_key": PHANTOM_CAVEATS_KEY,
        "runtime_routed": dict(RUNTIME_ROUTED),
        "route_applied_key": ROUTE_APPLIED_KEY,
        "route_reason_key": ROUTE_REASON_KEY,
        "route_unknown_reason": ROUTE_UNKNOWN_REASON,
        "shortcuts": [list(pair) for pair in model.shortcuts],
        "shortcut_plan": [list(pair) for pair in SHORTCUTS],
        "shortcut_failed_log": SHORTCUT_FAILED_LOG,
        "logged": [list(line) for line in model.logged],
        "phantom_caveat_log": PHANTOM_CAVEAT_LOG,
        "phantom_failed_log": PHANTOM_FAILED_LOG,
        "route_refused_log": ROUTE_REFUSED_LOG,
        "route_raised_log": ROUTE_RAISED_LOG,
        "applied_log": APPLIED_LOG,
        "save_failed_log": SAVE_FAILED_LOG,
        "save_method": SAVE_METHOD,
        "bot_manager_attribute": BOT_MANAGER_ATTRIBUTE,
        "no_manager_reason": NO_MANAGER_REASON,
        "saved_reason": SAVED_REASON,
        "save_failed_format": SAVE_FAILED_FORMAT,
        "age_seconds_format": AGE_SECONDS_FORMAT,
        "age_minutes_format": AGE_MINUTES_FORMAT,
        "age_hours_format": AGE_HOURS_FORMAT,
        "age_days_format": AGE_DAYS_FORMAT,
        "seconds_per_minute": SECONDS_PER_MINUTE,
        "seconds_per_hour": SECONDS_PER_HOUR,
        "seconds_per_day": SECONDS_PER_DAY,
        "fold_sort_key": model.fold_sort_key,
        "fold_sort_queue_order": FOLD_SORT_QUEUE_ORDER,
        "no_siblings": list(NO_SIBLINGS),
        "no_navigation": NO_NAVIGATION,
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "skin": dict(SKIN),
        "style_sheet": STYLE_SHEET,
        "call_names": list(CALL_NAMES),
        "calls": [list(call) for call in model.calls],
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``bot_live_settings.state``.

    Reads ``reset``, ``bot``, ``siblings``, ``build``, ``mark``,
    ``apply`` and ``navigate`` from the request parameters. The window
    keeps its edits between calls because the shipped window does;
    ``reset`` is what a fresh open sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = BotLiveSettingsModel(BotSource())
    model = pane_model()
    given_bot = params.get("bot")
    if given_bot is not None:
        model.bot = BotSource(
            config=BotConfigSource(
                symbol=given_bot.get("symbol", "CHIP/USD"),
                mode=given_bot.get("mode", MODE_SCRUMMING),
                fields=given_bot.get("fields"),
            ),
            bot_id=given_bot.get("bot_id", "botalpha0001beta"),
            state=given_bot.get("state", STATE_RUNNING),
            runtime=given_bot.get("runtime"),
        )
    given_siblings = params.get("siblings")
    if given_siblings is not None:
        model.bot_manager = BotManagerSource(bot_ids=given_siblings)
    if params.get("build", given_bot is not None):
        model.build()
    for field, value in dict(params.get("mark") or {}).items():
        model.mark_changed(field, value)
    if params.get("apply", False):
        model.apply_changes()
    navigate = params.get("navigate")
    if navigate is not None:
        model.navigate_to_sibling(int(navigate))
    return build_view_model(model)
