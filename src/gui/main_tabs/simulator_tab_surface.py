"""simulator_tab_surface.py -- the Simulator tab, without Qt.

Describes the whole tab: the mode dropdown and what each mode routes to,
the active-bot and chart-bot dropdowns, the merged simulator log and its
pause button, the bot table mount, the gate-status host, and the fleet
load that fills all of it.

``SimulatorTabModel`` holds the tab. ``FleetPanel``, ``BotTable``,
``PriceChart`` and ``BotSettingsDialog`` are plain stand-ins for the
fleet-replay panel, the Trading tab's bot table, the price chart and the
settings screen, so the tab can be driven over the bridge from values
alone.

The fleet is never invented here. ``FleetPanel`` is handed the configs a
stored fleet load produced and hands them back; nothing in this module
builds a bot, a symbol or a topology of its own.

Nothing runs at import. The model is built on the first request, the tab
starts no run, and no method reads a clock, opens a file or starts a
thread.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``simulator_tab.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.simulator_tab.simulator_tab``, so a value changed on one side
alone is reported.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

METHOD = "simulator_tab.state"

LOGGER_NAME = "acervator.simulator_tab"

ACCESSIBLE_NAME = "Simulator Tab"
OBJECT_NAME = "SimulatorTab"

SECTION_LABEL_STYLE = "color: #00ffcc; font-weight: bold;"

OUTER_MARGINS = (2, 2, 2, 2)
OUTER_SPACING = 2

TELEMETRY_FEATURES = (
    "sim.stat_strip.feed",
    "sim.price_chart.append",
    "sim.voting_readout.update",
    "sim.gate_lights.update",
    "sim.parity.compare_trades",
    "sim.controller.tick",
    "sim.activity_log.write",
    "sim.performance_log.write",
)
TELEMETRY_DECLARE_FAILED_FORMAT = "feature telemetry declare failed: %s"
TELEMETRY_ACTIVITY_WRITE = "sim.activity_log.write"
TELEMETRY_PERFORMANCE_WRITE = "sim.performance_log.write"
TELEMETRY_PAUSED_REASON = "paused"

QT_UNSET_SPACING = 6
QT_NESTED_MARGINS = (0, 0, 0, 0)
SPLITTER_MINIMUM = 1

MAIN_SPLITTER_HANDLE_WIDTH = 5
MAIN_SPLITTER_COLLAPSIBLE = False
MAIN_SPLITTER_SIZES = (500, 350)
MAIN_SPLITTER_ORIENTATION = "vertical"

TOP_SPLITTER_HANDLE_WIDTH = 5
TOP_SPLITTER_COLLAPSIBLE = False
TOP_SPLITTER_SIZES = (600, 500)
TOP_SPLITTER_ORIENTATION = "horizontal"

LOG_SPLITTER_HANDLE_WIDTH = 5
LOG_SPLITTER_COLLAPSIBLE = False
LOG_SPLITTER_SIZES = (500, 500)
LOG_SPLITTER_ORIENTATION = "horizontal"

CONTENT_MARGINS = (0, 0, 0, 0)
CONTENT_SPACING = 0

MODE_ROW_MARGINS = (6, 2, 6, 2)
MODE_LABEL_TEXT = "Mode:"
MODE_LABEL_STYLE = "color:#888899;font-size:11px;"
MODE_SELECTOR_MIN_WIDTH = 210
MODE_SELECTOR_TOOLTIP = (
    "Validation — gate parity against documented YTD events.\n"
    "Looping Back Test — tablets looped with noise, for strategy work.\n"
    "Nuclear — load oscillation and swarm stress; measures the system, "
    "not the trades."
)
MODE_HINT_STYLE = "color:#666677;font-size:11px;"

VALIDATION_KEY = "validation"
LOOPING_KEY = "looping"
NUCLEAR_KEY = "nuclear"
DEFAULT_MODE_KEY = VALIDATION_KEY

SIM_MODES = (
    (
        "Validation",
        VALIDATION_KEY,
        "Stone Tablets paired with YTD data. Verifies trade-gate "
        "parity at documented events.",
    ),
    (
        "Looping Back Test",
        LOOPING_KEY,
        "Loops the tablets with market-restructuring noise at a fixed "
        "rate. Strategy development and calibration.",
    ),
    (
        "Nuclear",
        NUCLEAR_KEY,
        "Load oscillation, swarm injection and high-traffic smart "
        "wire. Measures performance, stability and reliability — not "
        "trade validity.",
    ),
)

MODE_HINTS = {
    VALIDATION_KEY: "collects: gate-latch parity vs documented YTD events",
    LOOPING_KEY: "collects: strategy behaviour under looped tapes + noise",
    NUCLEAR_KEY: "collects: performance, stability, reliability "
    "(NOT trade validity)",
}
NO_HINT = ""

FLEET_PAGE_INDEX = 0
NUCLEAR_PAGE_INDEX = 1
STACK_PAGE_TOTAL = 2
PAGE_FLEET = "fleet"
PAGE_NUCLEAR = "nuclear"

STACK_STRETCH = 1
FLEET_PANEL_STRETCH = 1
INDICATOR_CONTAINER_STRETCH = 1
SCROLL_STRETCH = 1

LABEL_WORD_WRAP = False
LABEL_SELECTABLE = False
LOG_SELECTABLE = True
LOG_WRAPS_AT_WIDTH = True

FOCUS_STRONG = "StrongFocus"
FOCUS_WHEEL = "WheelFocus"
FOCUS_POLICIES = {
    "mode_selector": FOCUS_WHEEL,
    "active_bot_picker": FOCUS_WHEEL,
    "chart_expand_button": FOCUS_STRONG,
    "chart_bot_picker": FOCUS_WHEEL,
    "voting_expand_button": FOCUS_STRONG,
    "activity_pause_button": FOCUS_STRONG,
    "log_pane": FOCUS_STRONG,
}
FOCUS_ORDER = (
    "mode_selector",
    "active_bot_picker",
    "chart_expand_button",
    "chart_bot_picker",
    "voting_expand_button",
    "activity_pause_button",
    "log_pane",
)

MOUNT_STAT_STRIP = "sim-stat-strip"
MOUNT_BOT_TABLE = "bot-status-table"
MOUNT_FLEET_REPLAY = "fleet-replay"
MOUNT_NUCLEAR = "nuclear-mode"
MOUNT_PRICE_CHART = "sim-price-chart"
MOUNT_VOTING_PANEL = "indicator-voting-panel"
MOUNT_GATE_PANEL = "gate-status-panel"
MOUNTS = (
    MOUNT_STAT_STRIP,
    MOUNT_BOT_TABLE,
    MOUNT_FLEET_REPLAY,
    MOUNT_NUCLEAR,
    MOUNT_PRICE_CHART,
    MOUNT_VOTING_PANEL,
    MOUNT_GATE_PANEL,
)

BOT_AREA_MARGINS = (0, 0, 0, 0)
BOT_AREA_SPACING = 2
ACTIVE_BOT_ROW_MARGINS = (4, 2, 4, 0)
ACTIVE_BOT_LABEL_TEXT = "Active simulator bots:"
ACTIVE_BOT_LABEL_STYLE = "color:#888899;font-size:11px;"
ACTIVE_BOT_PICKER_MIN_WIDTH = 220
ACTIVE_BOT_PICKER_TOOLTIP = "Bots currently loaded into the Simulator fleet."
ALL_BOTS_TEXT = "All bots"
ALL_BOTS_DATA = ""
ACTIVE_BOT_ITEM_FORMAT = "{symbol}  ({bot_id})"
BOT_ID_TRIM = 12

FLEET_PANEL_UNAVAILABLE_TEXT = "FleetReplayPanel unavailable (import failed)."
NUCLEAR_CONSTRUCT_FAILED_FORMAT = "Nuclear Mode panel failed to construct: %s"
NUCLEAR_UNAVAILABLE_LOG_FORMAT = "Nuclear Mode unavailable: {type_name}: {text}"
NUCLEAR_PANEL_UNAVAILABLE_TEXT = (
    "Nuclear Mode unavailable (panel failed to load). "
    "See the Activity log for the reason."
)

FLEET_PAGE_MARGINS = (0, 0, 0, 0)
FLEET_PAGE_SPACING = 2

MOUNT_FAILED_FORMAT = "bot status table mount failed: %s"
FLEET_LOADED_CONNECT_FAILED_FORMAT = "fleetLoaded connect failed: %s"
BOT_TABLE_CONSTRUCTION_FAILED_FORMAT = "BotStatusTable construction failed: %s"

INDICATOR_WRAP_MARGINS = (8, 8, 8, 8)
INDICATOR_OBJECT_NAME = "SimIndicatorContainer"
INDICATOR_STYLE = (
    "QFrame#SimIndicatorContainer{background:#0a0a14;"
    "border:1px solid #2a2a44;border-radius:4px;}"
)
INDICATOR_INNER_MARGINS = (0, 0, 0, 0)
INDICATOR_INNER_SPACING = 0

SCROLL_WIDGET_RESIZABLE = True
SCROLL_FRAME_SHAPE = "NoFrame"
SCROLL_HORIZONTAL_POLICY = "ScrollBarAlwaysOff"
SCROLL_MINIMUM_HEIGHT = 80

TITLED_MARGINS = (6, 4, 6, 0)
TITLED_SPACING = 2
TITLED_HEAD_MARGINS = (0, 0, 0, 0)
EXPAND_TEXT = "⤢ Expand"
EXPAND_TOOLTIP_FORMAT = (
    "Open {title} at full display width, half height, centred on this screen."
)
EXPAND_STYLE = (
    "QPushButton{background:#1a1a3a;color:#88aaff;"
    "border:1px solid #88aaff;border-radius:3px;"
    "padding:1px 8px;font-size:10px;}"
    "QPushButton:hover{background:#222250;}"
)

CHART_TITLE = "Historical Price vs. Position VWAP"
VOTING_TITLE = "Indicator Voting Panel"

CHART_PICK_ROW_MARGINS = (6, 0, 6, 2)
CHART_PICK_ROW_INDEX = 1
CHART_PICK_LABEL_TEXT = "Bot:"
CHART_PICK_LABEL_STYLE = "color:#888899;font-size:11px;"
CHART_PICKER_MIN_WIDTH = 150
CHART_PICKER_TOOLTIP = (
    "Which bot's Stone Tablet candles and VWAP to chart. "
    "Select a bot to chart its VWAP and Stone Tablet candles."
)
CHART_PICKER_EMPTY_TEXT = "(select a bot)"
CHART_PICKER_EMPTY_DATA = ""

INDICATOR_SPLITTER_HANDLE_WIDTH = 4
INDICATOR_SPLITTER_COLLAPSIBLE = False
INDICATOR_SPLITTER_STRETCH = (1, 1)
INDICATOR_SPLITTER_SIZES = (10000, 10000)
INDICATOR_SPLITTER_ORIENTATION = "vertical"
VISUALS_UNAVAILABLE_FORMAT = "sim visuals unavailable: %s"

ACTIVITY_WRAP_MARGINS = (2, 2, 2, 2)
ACTIVITY_WRAP_SPACING = 2
SIM_LOG_TITLE = "Simulator Log"
PAUSE_TEXT = "⏸  Pause"
RESUME_TEXT = "▶  Resume"
PAUSE_BUTTON_CHECKABLE = True
PAUSE_STYLE = (
    "QPushButton{background:#1a1a3a;color:#ffaa00;"
    "border:1px solid #ffaa00;border-radius:3px;"
    "padding:3px 10px;font-size:11px;}"
    "QPushButton:checked{background:#3a1a1a;color:#ff3366;"
    "border:1px solid #ff3366;}"
)
LOG_READ_ONLY = True
LOG_MAXIMUM_BLOCK_COUNT = 10000
LOG_STYLE = (
    "QPlainTextEdit{background:#0a0a14;color:#ccccdd;"
    "font-family:'Cascadia Code','Consolas',monospace;"
    "font-size:11px;border:1px solid #2a2a44;}"
)
PERFORMANCE_PREFIX = "[perf] "
APPEND_REFUSED_FORMAT = "the log pane takes a string, not {kind}"
ACTIVITY_STREAM = "activity"
PERFORMANCE_STREAM = "performance"

GATE_WRAP_MARGINS = (2, 2, 2, 2)
GATE_WRAP_SPACING = 2
GATE_TITLE = "Gate Status"
GATE_HOST_MARGINS = (0, 0, 0, 0)
GATE_UNAVAILABLE_TEXT = "Gate status unavailable."
GATE_UNAVAILABLE_STYLE = "color:#666677;font-size:11px;padding:8px;"

FIRE_COLUMN = "Fire"
FIRE_DISABLED_TOOLTIP = (
    "Manual Fire is disabled in the Simulator. This "
    "surface tests trading AUTOMATION; a result that "
    "depended on operator intervention would not "
    "measure the thing being tested."
)

DETAIL_MISSING_FORMAT = (
    "sim detail: no simulated bot %r (live bots are NOT reachable from here)"
)
DETAIL_DIALOG_FAILED_FORMAT = "sim detail dialog failed: %s"
PANEL_MODE_SET_FAILED_FORMAT = "panel mode set failed: %s"
CHART_SET_SYMBOLS_FAILED_FORMAT = "chart set_symbols failed: %s"
CHART_ROSTER_FAILED_FORMAT = "chart roster refresh failed: %s"
BOT_AREA_REFRESH_FAILED_FORMAT = "bot area refresh failed: %s"

LEVEL_DEBUG = "DEBUG"
LEVEL_WARNING = "WARNING"
LEVEL_EXCEPTION = "EXCEPTION"

LOG_LEVELS = {
    TELEMETRY_DECLARE_FAILED_FORMAT: LEVEL_DEBUG,
    NUCLEAR_CONSTRUCT_FAILED_FORMAT: LEVEL_EXCEPTION,
    MOUNT_FAILED_FORMAT: LEVEL_WARNING,
    FLEET_LOADED_CONNECT_FAILED_FORMAT: LEVEL_WARNING,
    BOT_TABLE_CONSTRUCTION_FAILED_FORMAT: LEVEL_DEBUG,
    DETAIL_MISSING_FORMAT: LEVEL_WARNING,
    DETAIL_DIALOG_FAILED_FORMAT: LEVEL_WARNING,
    PANEL_MODE_SET_FAILED_FORMAT: LEVEL_DEBUG,
    CHART_SET_SYMBOLS_FAILED_FORMAT: LEVEL_DEBUG,
    CHART_ROSTER_FAILED_FORMAT: LEVEL_DEBUG,
    BOT_AREA_REFRESH_FAILED_FORMAT: LEVEL_WARNING,
    VISUALS_UNAVAILABLE_FORMAT: LEVEL_DEBUG,
}

MODE_PIN = "sim.06.013.state_transition.mode_selected"
LOG_PIN = "sim.06.014.event.log.line"

STATE_KEY = "_src_scrumming_state"
STATS_KEY = "_src_stats"
SOURCE_BOT_ID_KEY = "_src_bot_id"
SOURCE_STATE_KEY = "_src_state"
MAIN_LOTS_KEY = "main_lots"
UNITS_KEY = "units"
DEFAULT_BOT_MODE = "scrumming"
DEFAULT_BOT_STATE = "IDLE"
DEFAULT_EXCHANGE = "coinbase"
DEFAULT_QUOTE_TO_USD = 1.0
NO_TEXT = ""
NO_UNITS = 0.0
NO_PRICE = 0.0
NO_TRADES = 0

ACTIONS = {
    "mode_selector.currentIndexChanged": "_on_sim_mode_changed",
    "fleet_replay.fleetLoaded": "_on_fleet_loaded",
    "chart_expand_button.clicked": "sim_visuals._show_expanded",
    "voting_expand_button.clicked": "sim_visuals._show_expanded",
    "chart_bot_picker.currentIndexChanged": "_on_chart_bot_changed",
    "activity_pause_button.toggled": "_on_activity_paused",
}
CONNECTIONS_AT_BUILD = 6

SIGNALS: tuple = ()
TIMERS: dict = {}
THREADS: tuple = ()
BUS_TOPICS: tuple = ()

BUILD_MOUNTED = "build.mounted"
BUILD_MOUNT_FAILED = "build.mount_failed"
BUILD_CONNECTED = "build.connected"
BUILD_CONNECT_FAILED = "build.connect_failed"
MODE_ROUTED = "mode.routed"
MODE_HINTED = "mode.hinted"
MODE_HANDED_OFF = "mode.handed_off"
MODE_HAND_OFF_REFUSED = "mode.hand_off_refused"
FLEET_SYMBOLS_SET = "fleet.symbols_set"
FLEET_SYMBOLS_REFUSED = "fleet.symbols_refused"
FLEET_CHART_ROSTER = "fleet.chart_roster"
FLEET_CHART_ROSTER_REFUSED = "fleet.chart_roster_refused"
FLEET_STATUSES_TAKEN = "fleet.statuses_taken"
FLEET_STATUSES_BUILT = "fleet.statuses_built"
FLEET_TABLE_FILLED = "fleet.table_filled"
FLEET_AREA_REFUSED = "fleet.area_refused"
FLEET_ROSTER_FILLED = "fleet.roster_filled"
MOUNT_NO_PANEL = "mount.no_panel"
MOUNT_NO_CLASS = "mount.no_class"
MOUNT_ALREADY = "mount.already"
MOUNT_BUILT = "mount.built"
MOUNT_REFUSED = "mount.refused"
FIRE_NO_WIDGET = "fire.no_widget"
FIRE_NO_COLUMN = "fire.no_column"
FIRE_DISABLED = "fire.disabled"
DETAIL_MISSING = "detail.missing"
DETAIL_OPENED = "detail.opened"
DETAIL_REFUSED = "detail.refused"
LOG_HELD = "log.held"
LOG_WRITTEN = "log.written"

CALL_NAMES = (
    BUILD_MOUNTED,
    BUILD_MOUNT_FAILED,
    BUILD_CONNECTED,
    BUILD_CONNECT_FAILED,
    MODE_ROUTED,
    MODE_HINTED,
    MODE_HANDED_OFF,
    MODE_HAND_OFF_REFUSED,
    FLEET_SYMBOLS_SET,
    FLEET_SYMBOLS_REFUSED,
    FLEET_CHART_ROSTER,
    FLEET_CHART_ROSTER_REFUSED,
    FLEET_STATUSES_TAKEN,
    FLEET_STATUSES_BUILT,
    FLEET_TABLE_FILLED,
    FLEET_AREA_REFUSED,
    FLEET_ROSTER_FILLED,
    MOUNT_NO_PANEL,
    MOUNT_NO_CLASS,
    MOUNT_ALREADY,
    MOUNT_BUILT,
    MOUNT_REFUSED,
    FIRE_NO_WIDGET,
    FIRE_NO_COLUMN,
    FIRE_DISABLED,
    DETAIL_MISSING,
    DETAIL_OPENED,
    DETAIL_REFUSED,
    LOG_HELD,
    LOG_WRITTEN,
)

ERROR_TYPES = {
    "AttributeError": AttributeError,
    "Exception": Exception,
    "KeyError": KeyError,
    "LookupError": LookupError,
    "OSError": OSError,
    "RuntimeError": RuntimeError,
    "TypeError": TypeError,
    "ValueError": ValueError,
    "ZeroDivisionError": ZeroDivisionError,
}
DEFAULT_ERROR_TYPE = "RuntimeError"


def error_from(type_name: Any, text: Any) -> BaseException:
    """An exception of the named type carrying `text`.

    A name the table does not hold becomes a class of that name, so a
    failure the renderer reports reaches the model under its own name.
    """
    known = ERROR_TYPES.get(type_name)
    kind: Any = known if known is not None else type(str(type_name), (Exception,), {})
    return kind(text)


def page_for(mode_key: Any) -> int:
    """The stack page one mode key routes to."""
    return NUCLEAR_PAGE_INDEX if mode_key == NUCLEAR_KEY else FLEET_PAGE_INDEX


def page_name(mode_key: Any) -> str:
    """The name of the page one mode key routes to."""
    return PAGE_NUCLEAR if mode_key == NUCLEAR_KEY else PAGE_FLEET


def hint_for(mode_key: Any) -> str:
    """The line under the dropdown saying what a mode collects."""
    return MODE_HINTS.get(mode_key, NO_HINT)


def expand_tooltip(title: Any) -> str:
    """The tooltip one Expand button wears."""
    return EXPAND_TOOLTIP_FORMAT.format(title=title)


def active_bot_item(symbol: Any, bot_id: Any) -> str:
    """The printed name of one row in the active-bot dropdown."""
    return ACTIVE_BOT_ITEM_FORMAT.format(
        symbol=symbol, bot_id=str(bot_id)[:BOT_ID_TRIM]
    )


def performance_line(line: Any) -> str:
    """One performance line, tagged so the two streams stay apart."""
    return f"{PERFORMANCE_PREFIX}{line}"


def nuclear_unavailable_line(exc: BaseException) -> str:
    """The activity-log line written when the Nuclear panel refused."""
    return NUCLEAR_UNAVAILABLE_LOG_FORMAT.format(type_name=type(exc).__name__, text=exc)


class Picker:
    """One dropdown: its rows, its selection and its blocked signals.

    ``current_data`` is what the tab reads back. ``find_data`` answers
    with the first row carrying a value, or -1, which is what the tab
    keeps a selection by.
    """

    def __init__(self, minimum_width: int = 0, tooltip: str = NO_TEXT) -> None:
        self.minimum_width = minimum_width
        self.tooltip = tooltip
        self.items: list = []
        self.item_tooltips: list = []
        self.index = -1
        self.signals_blocked = False
        self.changes = 0

    def add_item(self, text: Any, data: Any = None, tooltip: Any = None) -> None:
        """Append one row and select it when it is the first."""
        self.items.append([text, data])
        self.item_tooltips.append(tooltip)
        if self.index < 0:
            self.index = 0

    def clear(self) -> None:
        """Drop every row and the selection with them."""
        self.items = []
        self.item_tooltips = []
        self.index = -1

    def count(self) -> int:
        """How many rows the dropdown holds."""
        return len(self.items)

    def current_data(self) -> Any:
        """The value behind the selected row, or nothing."""
        if 0 <= self.index < len(self.items):
            return self.items[self.index][1]
        return None

    def current_text(self) -> Any:
        """The printed name of the selected row."""
        if 0 <= self.index < len(self.items):
            return self.items[self.index][0]
        return NO_TEXT

    def find_data(self, value: Any) -> int:
        """The first row carrying `value`, or -1."""
        for at, item in enumerate(self.items):
            if item[1] == value:
                return at
        return -1

    def set_current_index(self, at: int) -> None:
        """Select one row, counting the change when it is not blocked."""
        if at == self.index:
            return
        self.index = at
        if not self.signals_blocked:
            self.changes += 1

    def block_signals(self, blocked: bool) -> None:
        """Hold the change count still while rows are replaced."""
        self.signals_blocked = bool(blocked)


class Stack:
    """The two-page stack the mode dropdown routes.

    ``set_current_index`` ignores an index no page carries, which is
    what the shipped stack does with an out-of-range page.
    """

    def __init__(self, pages: int = STACK_PAGE_TOTAL) -> None:
        self.pages = pages
        self.index = 0 if pages else -1

    def count(self) -> int:
        """How many pages the stack holds."""
        return self.pages

    def current_index(self) -> int:
        """The page on display."""
        return self.index

    def set_current_index(self, at: int) -> None:
        """Show one page, or leave the stack alone."""
        if 0 <= at < self.pages:
            self.index = at


class LogPane:
    """The one pane both log streams land in."""

    def __init__(self, maximum_blocks: int = LOG_MAXIMUM_BLOCK_COUNT) -> None:
        self.maximum_blocks = maximum_blocks
        self.lines: list = []

    def append(self, line: Any) -> None:
        """Add one line, refusing anything that is neither text nor None.

        The shipped pane is a ``QPlainTextEdit``. It takes ``None`` as an
        empty line and refuses every other non-text value with a
        ``TypeError``. A pane still holding no text writes into the block
        it already has instead of adding one, so two empty lines leave
        the pane empty rather than holding a blank line.
        """
        if line is None:
            line = NO_TEXT
        elif not isinstance(line, str):
            raise TypeError(APPEND_REFUSED_FORMAT.format(kind=type(line).__name__))
        if self.text():
            self.lines.append(line)
        else:
            self.lines = [line]
        if len(self.lines) > self.maximum_blocks:
            del self.lines[: len(self.lines) - self.maximum_blocks]

    def text(self) -> str:
        """Everything the pane holds, as one block of text."""
        return "\n".join(self.lines)


class PriceChart:
    """The price and VWAP chart the fleet load points at."""

    def __init__(self, set_symbols_raises: Optional[BaseException] = None) -> None:
        self.set_symbols_raises = set_symbols_raises
        self.symbols: list = []
        self.focus_symbol = NO_TEXT
        self.focus_calls = 0

    def set_symbols(self, symbols: Any) -> None:
        self.set_symbols_calls = getattr(self, "set_symbols_calls", 0) + 1
        if self.set_symbols_raises is not None:
            raise self.set_symbols_raises
        self.symbols = list(symbols)

    def set_focus_symbol(self, symbol: Any) -> None:
        self.focus_calls += 1
        self.focus_symbol = symbol


class BotTable:
    """The Trading tab's bot table, as the Simulator mounts it.

    ``COLUMNS`` is the class attribute the tab reads the Fire column
    out of, so a build with no Fire column exercises the same refusal
    the shipped table would.
    """

    COLUMNS = (
        "Bot ID",
        "Symbol",
        "Mode",
        "Trades",
        "Target",
        "Target BTC",
        "Target ETH",
        "Ammo",
        "Fire",
        "",
    )

    def __init__(
        self,
        on_bot_clicked: Any = None,
        on_fire_clicked: Any = None,
        columns: Optional[tuple] = None,
    ) -> None:
        self.on_bot_clicked = on_bot_clicked
        self.on_fire_clicked = on_fire_clicked
        if columns is not None:
            self.COLUMNS = columns
        self.rows: list = []
        self.fire_cells: list = []

    def update_bots(self, statuses: Any) -> None:
        """Fill the table from the statuses the tab handed it."""
        self.rows = list(statuses)
        self.fire_cells = [FireCell() for _ in self.rows]

    def row_count(self) -> int:
        """How many rows the table holds."""
        return len(self.rows)

    def cell_widget(self, row: int, column: int) -> Any:
        """The control in one cell, or nothing."""
        try:
            fire_column = list(type(self).COLUMNS).index(FIRE_COLUMN)
        except ValueError:
            return None
        if column != fire_column:
            return None
        if 0 <= row < len(self.fire_cells):
            return self.fire_cells[row]
        return None


class FireCell:
    """The Fire control on one row of the bot table."""

    def __init__(self) -> None:
        self.enabled = True
        self.tooltip = NO_TEXT

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def set_tool_tip(self, tooltip: Any) -> None:
        self.tooltip = tooltip


class BotSettingsDialog:
    """The settings screen one bot row opens."""

    def __init__(self, bot: Any = None, raises: Optional[BaseException] = None) -> None:
        self.bot = bot
        self.raises = raises
        self.shown = 0

    def exec(self) -> None:
        if self.raises is not None:
            raise self.raises
        self.shown += 1


class SimBot:
    """One bot the sim controller holds, named by its id."""

    def __init__(self, bot_id: Any = NO_TEXT) -> None:
        self.bot_id = bot_id


class SimController:
    """The controller the Simulator resolves a bot id against."""

    def __init__(self, bots: Any = None) -> None:
        self._bots = list(bots or [])


class FleetPanel:
    """The fleet-replay panel the tab hangs everything off.

    ``statuses`` is what a fleet load already produced. Nothing here
    builds a fleet: the configs and the statuses are handed in.
    """

    def __init__(
        self,
        statuses: Any = None,
        table_class: Any = None,
        controller: Optional[SimController] = None,
        gate_panel: Any = None,
        statuses_raises: Optional[BaseException] = None,
        set_sim_mode_raises: Optional[BaseException] = None,
        table_raises: Optional[BaseException] = None,
    ) -> None:
        self.statuses = statuses
        self.table_class = table_class
        self._controller = controller
        self._gate_panel = gate_panel
        self.statuses_raises = statuses_raises
        self.set_sim_mode_raises = set_sim_mode_raises
        self.table_raises = table_raises
        self._bot_status_table_widget: Any = None
        self._bot_table_columns: list = []
        self.sim_mode_calls: list = []
        self.emitted_table_counts: list = []
        self.log_callbacks: Any = None
        self.async_loop_getter: Any = None
        self.connectors_getter: Any = None
        self.bot_manager: Any = None
        self.fleet_loaded_handlers: list = []

    def bot_status_table_class(self) -> Any:
        """The table class the Simulator mounts, or nothing."""
        if self.table_raises is not None:
            raise self.table_raises
        return self.table_class

    def sim_bot_statuses(self) -> Any:
        """The statuses a fleet load already produced."""
        if self.statuses_raises is not None:
            raise self.statuses_raises
        return list(self.statuses) if self.statuses is not None else []

    def set_sim_mode(self, key: Any) -> None:
        if self.set_sim_mode_raises is not None:
            raise self.set_sim_mode_raises
        self.sim_mode_calls.append(key)

    def emit_bot_table(self, total: int) -> None:
        self.emitted_table_counts.append(total)

    def set_log_callbacks(self, activity: Any, performance: Any) -> None:
        self.log_callbacks = [activity, performance]

    def set_async_loop_getter(self, getter: Any) -> None:
        self.async_loop_getter = getter

    def set_connectors_getter(self, getter: Any) -> None:
        self.connectors_getter = getter

    def set_bot_manager(self, bot_manager: Any) -> None:
        self.bot_manager = bot_manager

    def connect_fleet_loaded(self, handler: Callable) -> None:
        self.fleet_loaded_handlers.append(handler)


class NuclearPanel:
    """The Nuclear page, as far as the tab talks to it."""

    def __init__(self) -> None:
        self.swarm_getter: Any = None
        self.topology_getter: Any = None

    def set_swarm_getter(self, getter: Any) -> None:
        self.swarm_getter = getter

    def set_topology_getter(self, getter: Any) -> None:
        self.topology_getter = getter


def lot_units(lots: Any) -> float:
    """The units a bot holds, summed over the lots its state carries.

    A lot that is not a mapping is skipped, which is what the shipped
    sum does; every other value reaches ``float`` unguarded, so a lot
    carrying text raises here exactly as it does on the shipped side.
    """
    return sum(
        float(lot.get(UNITS_KEY, 0) or 0)
        for lot in (lots or [])
        if isinstance(lot, dict)
    )


def status_from_config(config: Any) -> dict:
    """One bot row built from the fleet load's own stored state.

    Every number comes off ``_src_scrumming_state`` and ``_src_stats``
    as the loader attached them, with the config as the last fallback.
    Nothing is invented and nothing is guarded: a stored value of the
    wrong kind raises here, which is what the shipped fallback does.
    """
    config = config or {}
    state = config.get(STATE_KEY) or {}
    stats = config.get(STATS_KEY) or {}
    units = lot_units(state.get(MAIN_LOTS_KEY))
    price = float(stats.get("current_price", NO_PRICE) or NO_PRICE)
    value = float(stats.get("position_value", NO_PRICE) or NO_PRICE)
    if value <= 0 and price > 0:
        value = units * price
    return {
        "bot_id": str(config.get(SOURCE_BOT_ID_KEY, NO_TEXT) or NO_TEXT),
        "symbol": str(config.get("symbol", NO_TEXT) or NO_TEXT),
        "mode": str(config.get("mode", DEFAULT_BOT_MODE) or DEFAULT_BOT_MODE),
        "state": str(config.get(SOURCE_STATE_KEY, NO_TEXT) or DEFAULT_BOT_STATE),
        "exchange": str(
            config.get("exchange_id", DEFAULT_EXCHANGE) or DEFAULT_EXCHANGE
        ),
        "target_balance": float(
            state.get("anchor_target_balance", config.get("target_balance", NO_PRICE))
            or NO_PRICE
        ),
        "live_target_balance": float(
            state.get("target_balance", config.get("target_balance", NO_PRICE))
            or NO_PRICE
        ),
        "current_holdings": units,
        "quote_to_usd": float(
            state.get("quote_to_usd", DEFAULT_QUOTE_TO_USD) or DEFAULT_QUOTE_TO_USD
        ),
        "stats": {
            "current_price": price,
            "position_value": value,
            "total_trades": int(stats.get("total_trades", NO_TRADES) or NO_TRADES),
        },
    }


def symbols_from(configs: Any) -> list:
    """The symbols one fleet load names, in the order it names them."""
    found = []
    for config in configs or []:
        symbol = str((config or {}).get("symbol", NO_TEXT) or NO_TEXT)
        if symbol:
            found.append(symbol)
    return found


class SimulatorTabModel:
    """The Simulator tab: its dropdowns, its stack, its log and its table.

    Built empty and wired by the setters, exactly as the shipped tab is.
    Nothing here reads a clock, opens a file, starts a thread or starts
    a run.
    """

    def __init__(self) -> None:
        self.accessible_name = ACCESSIBLE_NAME
        self.object_name = OBJECT_NAME
        self.async_loop: Any = None
        self.swarm_getter: Any = None
        self.topology_getter: Any = None
        self.connectors_getter: Any = None
        self.declared_features = list(TELEMETRY_FEATURES)

        self.mode_selector = Picker(MODE_SELECTOR_MIN_WIDTH, MODE_SELECTOR_TOOLTIP)
        for label, key, tooltip in SIM_MODES:
            self.mode_selector.add_item(label, key, tooltip)
        self.mode_hint_text = NO_TEXT
        self.stack = Stack()

        self.active_bot_picker = Picker(
            ACTIVE_BOT_PICKER_MIN_WIDTH, ACTIVE_BOT_PICKER_TOOLTIP
        )
        self.active_bot_picker.add_item(ALL_BOTS_TEXT, ALL_BOTS_DATA)
        self.chart_bot_picker = Picker(CHART_PICKER_MIN_WIDTH, CHART_PICKER_TOOLTIP)
        self.chart_bot_picker.add_item(CHART_PICKER_EMPTY_TEXT, CHART_PICKER_EMPTY_DATA)

        self.fleet_panel: Optional[FleetPanel] = None
        self.nuclear_panel: Optional[NuclearPanel] = None
        self.price_chart: Optional[PriceChart] = None
        self.settings_dialog: Optional[BotSettingsDialog] = None

        self.log_pane = LogPane()
        self.pause_button_text = PAUSE_TEXT
        self.activity_paused = False
        self.performance_paused = False

        self.calls: list = []
        self.warnings: list = []
        self.pins: list = []
        self.dialogs: list = []

    def declare_telemetry(self) -> None:
        """Name every Simulator feed up front, best effort."""
        self.declared_features = list(TELEMETRY_FEATURES)

    def set_fleet_panel(self, panel: Optional[FleetPanel]) -> None:
        """Attach the fleet panel and hand it the tab's log callbacks."""
        self.fleet_panel = panel
        if panel is not None:
            panel.set_async_loop_getter(lambda: self.async_loop)
            panel.set_log_callbacks(self.log_activity, self.log_performance)
            panel.connect_fleet_loaded(self.on_fleet_loaded)

    def set_nuclear_panel(self, panel: Optional[NuclearPanel]) -> None:
        """Attach the Nuclear page."""
        self.nuclear_panel = panel

    def set_price_chart(self, chart: Optional[PriceChart]) -> None:
        """Attach the price chart the fleet load points at."""
        self.price_chart = chart

    def build(self) -> None:
        """Do at build time what the shipped constructor does last.

        Mounts the bot table, wires ``fleetLoaded`` and routes the mode
        dropdown, each guarded so a refusal is logged rather than
        stopping the tab from being built.
        """
        try:
            self.mount_bot_status_table()
            self.calls.append([BUILD_MOUNTED])
        except Exception as exc:
            self.warnings.append([LEVEL_WARNING, MOUNT_FAILED_FORMAT % (exc,)])
            self.calls.append([BUILD_MOUNT_FAILED, type(exc).__name__])
        try:
            if self.fleet_panel is None:
                raise AttributeError("fleetLoaded")
            self.fleet_panel.connect_fleet_loaded(self.on_fleet_loaded)
            self.calls.append([BUILD_CONNECTED])
        except Exception as exc:
            self.warnings.append(
                [LEVEL_WARNING, FLEET_LOADED_CONNECT_FAILED_FORMAT % (exc,)]
            )
            self.calls.append([BUILD_CONNECT_FAILED, type(exc).__name__])
        self.on_sim_mode_changed()

    def sim_mode(self) -> str:
        """The selected mode key, or 'validation' before setup."""
        return str(self.mode_selector.current_data() or DEFAULT_MODE_KEY)

    def select_mode(self, key: Any) -> None:
        """Move the dropdown to one mode and route the stack."""
        at = self.mode_selector.find_data(key)
        self.mode_selector.set_current_index(at)
        self.on_sim_mode_changed()

    def on_sim_mode_changed(self) -> None:
        """Route the stack and say what the mode collects."""
        key = self.sim_mode()
        self.stack.set_current_index(page_for(key))
        self.calls.append([MODE_ROUTED, self.stack.current_index()])
        self.mode_hint_text = hint_for(key)
        self.calls.append([MODE_HINTED, self.mode_hint_text])
        panel = self.fleet_panel
        if panel is not None:
            try:
                panel.set_sim_mode(key)
                self.calls.append([MODE_HANDED_OFF, key])
            except Exception as exc:
                self.warnings.append(
                    [LEVEL_DEBUG, PANEL_MODE_SET_FAILED_FORMAT % (exc,)]
                )
                self.calls.append([MODE_HAND_OFF_REFUSED, type(exc).__name__])
        self.pins.append(
            {
                "name": MODE_PIN,
                "actual": self.stack.current_index(),
                "expected": page_for(key),
                "context": {
                    "mode": key,
                    "page": page_name(key),
                    "stack": True,
                },
            }
        )

    def mount_bot_status_table(self) -> bool:
        """Put the Trading tab's bot table in the Simulator."""
        panel = self.fleet_panel
        if panel is None:
            self.calls.append([MOUNT_NO_PANEL])
            return False
        table_class = panel.bot_status_table_class()
        if table_class is None:
            self.calls.append([MOUNT_NO_CLASS])
            return False
        if panel._bot_status_table_widget is not None:
            self.calls.append([MOUNT_ALREADY])
            return True
        try:
            widget = table_class(
                on_bot_clicked=self.on_sim_bot_detail, on_fire_clicked=None
            )
        except Exception as exc:
            self.warnings.append(
                [LEVEL_DEBUG, BOT_TABLE_CONSTRUCTION_FAILED_FORMAT % (exc,)]
            )
            self.calls.append([MOUNT_REFUSED, type(exc).__name__])
            return False
        panel._bot_status_table_widget = widget
        panel._bot_table_columns = list(getattr(table_class, "COLUMNS", []))
        self.calls.append([MOUNT_BUILT, len(panel._bot_table_columns)])
        return True

    def on_sim_bot_detail(self, bot_id: Any) -> None:
        """Open the settings screen for a SIMULATED bot, or refuse."""
        panel = self.fleet_panel
        controller = getattr(panel, "_controller", None) if panel else None
        bots = list(getattr(controller, "_bots", []) or []) if controller else []
        bot = next(
            (
                one
                for one in bots
                if str(getattr(one, "bot_id", NO_TEXT)) == str(bot_id)
            ),
            None,
        )
        if bot is None:
            self.warnings.append([LEVEL_WARNING, DETAIL_MISSING_FORMAT % (bot_id,)])
            self.calls.append([DETAIL_MISSING, str(bot_id)])
            return
        try:
            dialog = self.settings_dialog or BotSettingsDialog(bot)
            dialog.bot = bot
            dialog.exec()
            self.dialogs.append(str(bot_id))
            self.calls.append([DETAIL_OPENED, str(bot_id)])
        except Exception as exc:
            self.warnings.append([LEVEL_WARNING, DETAIL_DIALOG_FAILED_FORMAT % (exc,)])
            self.calls.append([DETAIL_REFUSED, type(exc).__name__])

    def disable_fire_buttons(self) -> None:
        """Grey out Fire on every row, with the reason on the tooltip."""
        panel = self.fleet_panel
        widget = getattr(panel, "_bot_status_table_widget", None)
        if widget is None:
            self.calls.append([FIRE_NO_WIDGET])
            return
        try:
            fire_column = list(type(widget).COLUMNS).index(FIRE_COLUMN)
        except (ValueError, AttributeError):
            self.calls.append([FIRE_NO_COLUMN])
            return
        disabled = 0
        for row in range(widget.row_count()):
            cell = widget.cell_widget(row, fire_column)
            if cell is not None:
                cell.set_enabled(False)
                cell.set_tool_tip(FIRE_DISABLED_TOOLTIP)
                disabled += 1
        self.calls.append([FIRE_DISABLED, disabled])

    def refresh_active_bot_roster(self, statuses: Any = None) -> None:
        """Repopulate the active-bot dropdown from the fleet's statuses."""
        picker = self.active_bot_picker
        panel = self.fleet_panel
        if statuses is None:
            statuses = panel.sim_bot_statuses() if panel is not None else []
        keep = picker.current_data() or ALL_BOTS_DATA
        picker.block_signals(True)
        picker.clear()
        picker.add_item(ALL_BOTS_TEXT, ALL_BOTS_DATA)
        for status in statuses:
            bot_id = str(status.get("bot_id", NO_TEXT))
            symbol = str(status.get("symbol", NO_TEXT))
            if bot_id:
                picker.add_item(active_bot_item(symbol, bot_id), bot_id)
        at = picker.find_data(keep)
        picker.set_current_index(at if at >= 0 else 0)
        picker.block_signals(False)
        self.calls.append([FLEET_ROSTER_FILLED, picker.count()])

    def active_bot_id(self) -> str:
        """The bot the operator has selected, or "" for all."""
        return str(self.active_bot_picker.current_data() or NO_TEXT)

    def on_chart_bot_changed(self) -> None:
        """Point the chart at one bot, or back to stacked bands."""
        chart = self.price_chart
        if chart is None:
            return
        chart.set_focus_symbol(str(self.chart_bot_picker.current_data() or NO_TEXT))

    def refresh_chart_bot_roster(self, symbols: Any) -> None:
        """Repopulate the chart picker after a fleet load."""
        picker = self.chart_bot_picker
        keep = picker.current_data() or CHART_PICKER_EMPTY_DATA
        picker.block_signals(True)
        picker.clear()
        picker.add_item(CHART_PICKER_EMPTY_TEXT, CHART_PICKER_EMPTY_DATA)
        for symbol in sorted({str(one) for one in (symbols or []) if str(one)}):
            picker.add_item(symbol, symbol)
        at = picker.find_data(keep)
        picker.set_current_index(at if at >= 0 else 0)
        picker.block_signals(False)
        self.on_chart_bot_changed()

    def select_chart_bot(self, symbol: Any) -> None:
        """Move the chart picker to one symbol and repoint the chart."""
        at = self.chart_bot_picker.find_data(symbol)
        self.chart_bot_picker.set_current_index(at)
        self.on_chart_bot_changed()

    def on_fleet_loaded(self, configs: Any) -> None:
        """Everything the fleet drives, from one signal."""
        panel = self.fleet_panel
        if panel is None:
            return
        symbols = symbols_from(configs)
        chart = self.price_chart
        if chart is not None:
            try:
                chart.set_symbols(symbols)
                self.calls.append([FLEET_SYMBOLS_SET, len(symbols)])
            except Exception as exc:
                self.warnings.append(
                    [LEVEL_DEBUG, CHART_SET_SYMBOLS_FAILED_FORMAT % (exc,)]
                )
                self.calls.append([FLEET_SYMBOLS_REFUSED, type(exc).__name__])
        try:
            self.refresh_chart_bot_roster(symbols)
            self.calls.append([FLEET_CHART_ROSTER, self.chart_bot_picker.count()])
        except Exception as exc:
            self.warnings.append([LEVEL_DEBUG, CHART_ROSTER_FAILED_FORMAT % (exc,)])
            self.calls.append([FLEET_CHART_ROSTER_REFUSED, type(exc).__name__])
        try:
            statuses = panel.sim_bot_statuses()
            self.calls.append([FLEET_STATUSES_TAKEN, len(statuses)])
            if not statuses:
                statuses = [status_from_config(config) for config in configs or []]
                self.calls.append([FLEET_STATUSES_BUILT, len(statuses)])
            widget = panel._bot_status_table_widget
            if widget is not None:
                widget.update_bots(statuses)
                self.disable_fire_buttons()
                panel.emit_bot_table(len(statuses))
                self.calls.append([FLEET_TABLE_FILLED, len(statuses)])
            self.refresh_active_bot_roster(statuses)
        except Exception as exc:
            self.warnings.append(
                [LEVEL_WARNING, BOT_AREA_REFRESH_FAILED_FORMAT % (exc,)]
            )
            self.calls.append([FLEET_AREA_REFUSED, type(exc).__name__])

    def on_activity_paused(self, checked: Any) -> None:
        """Hold the activity stream and rename the button.

        Only the activity flag moves. The performance flag is a separate
        value the shipped button never touches.
        """
        self.activity_paused = checked
        self.pause_button_text = RESUME_TEXT if checked else PAUSE_TEXT

    def emit_log_line(self, stream: str, line: Any, delivered: bool) -> None:
        """Record one log line and the stream that produced it.

        Best effort: a line whose length cannot be taken records nothing,
        exactly as the shipped emitter's own guard leaves it.
        """
        try:
            self.pins.append(
                {
                    "name": LOG_PIN,
                    "actual": stream,
                    "expected": None,
                    "context": {
                        "delivered": bool(delivered),
                        "chars": len(line or NO_TEXT),
                    },
                }
            )
        except Exception:
            return

    def log_activity(self, line: Any) -> None:
        """Append a line to the simulator log unless paused."""
        if self.activity_paused:
            self.calls.append([LOG_HELD, ACTIVITY_STREAM, TELEMETRY_ACTIVITY_WRITE])
            self.emit_log_line(ACTIVITY_STREAM, line, delivered=False)
            return
        self.log_pane.append(line)
        self.calls.append([LOG_WRITTEN, ACTIVITY_STREAM, TELEMETRY_ACTIVITY_WRITE])
        self.emit_log_line(ACTIVITY_STREAM, line, delivered=True)

    def log_performance(self, line: Any) -> None:
        """Append a tagged line to the simulator log unless paused."""
        if self.performance_paused:
            self.calls.append(
                [LOG_HELD, PERFORMANCE_STREAM, TELEMETRY_PERFORMANCE_WRITE]
            )
            self.emit_log_line(PERFORMANCE_STREAM, line, delivered=False)
            return
        self.log_pane.append(performance_line(line))
        self.calls.append(
            [LOG_WRITTEN, PERFORMANCE_STREAM, TELEMETRY_PERFORMANCE_WRITE]
        )
        self.emit_log_line(PERFORMANCE_STREAM, line, delivered=True)

    def set_async_loop(self, loop: Any) -> None:
        """Attach the loop Nuclear Mode schedules its work on."""
        self.async_loop = loop

    def set_connectors_getter(self, getter: Any) -> None:
        """Forward the connectors getter to the fleet panel."""
        self.connectors_getter = getter
        if self.fleet_panel is not None:
            self.fleet_panel.set_connectors_getter(getter)

    def set_swarm_getter(self, getter: Any) -> None:
        """Hand the Simulator swarm to the Nuclear page."""
        self.swarm_getter = getter
        if self.nuclear_panel is not None:
            self.nuclear_panel.set_swarm_getter(getter)

    def set_topology_getter(self, getter: Any) -> None:
        """Hand the Market Inspector's proposals to the Nuclear page."""
        self.topology_getter = getter
        if self.nuclear_panel is not None:
            self.nuclear_panel.set_topology_getter(getter)

    def set_bot_manager(self, bot_manager: Any) -> None:
        """Forward the live bot manager to the fleet panel."""
        if self.fleet_panel is not None:
            self.fleet_panel.set_bot_manager(bot_manager)


def build_view_model(model: SimulatorTabModel) -> dict:
    """Return every value the Simulator tab holds as one dict."""
    panel = model.fleet_panel
    widget = getattr(panel, "_bot_status_table_widget", None)
    return {
        "identity": {
            "accessible_name": model.accessible_name,
            "object_name": model.object_name,
            "logger": LOGGER_NAME,
            "section_label_style": SECTION_LABEL_STYLE,
        },
        "chrome": {
            "outer_margins": list(OUTER_MARGINS),
            "outer_spacing": OUTER_SPACING,
            "qt_unset_spacing": QT_UNSET_SPACING,
            "qt_nested_margins": list(QT_NESTED_MARGINS),
            "splitter_minimum": SPLITTER_MINIMUM,
            "stack_stretch": STACK_STRETCH,
            "fleet_panel_stretch": FLEET_PANEL_STRETCH,
            "indicator_container_stretch": INDICATOR_CONTAINER_STRETCH,
            "scroll_stretch": SCROLL_STRETCH,
            "main_splitter_handle_width": MAIN_SPLITTER_HANDLE_WIDTH,
            "main_splitter_collapsible": MAIN_SPLITTER_COLLAPSIBLE,
            "main_splitter_sizes": list(MAIN_SPLITTER_SIZES),
            "main_splitter_orientation": MAIN_SPLITTER_ORIENTATION,
            "top_splitter_handle_width": TOP_SPLITTER_HANDLE_WIDTH,
            "top_splitter_collapsible": TOP_SPLITTER_COLLAPSIBLE,
            "top_splitter_sizes": list(TOP_SPLITTER_SIZES),
            "top_splitter_orientation": TOP_SPLITTER_ORIENTATION,
            "log_splitter_handle_width": LOG_SPLITTER_HANDLE_WIDTH,
            "log_splitter_collapsible": LOG_SPLITTER_COLLAPSIBLE,
            "log_splitter_sizes": list(LOG_SPLITTER_SIZES),
            "log_splitter_orientation": LOG_SPLITTER_ORIENTATION,
            "content_margins": list(CONTENT_MARGINS),
            "content_spacing": CONTENT_SPACING,
            "fleet_page_margins": list(FLEET_PAGE_MARGINS),
            "fleet_page_spacing": FLEET_PAGE_SPACING,
            "indicator_wrap_margins": list(INDICATOR_WRAP_MARGINS),
            "indicator_object_name": INDICATOR_OBJECT_NAME,
            "indicator_style": INDICATOR_STYLE,
            "indicator_inner_margins": list(INDICATOR_INNER_MARGINS),
            "indicator_inner_spacing": INDICATOR_INNER_SPACING,
            "indicator_splitter_handle_width": INDICATOR_SPLITTER_HANDLE_WIDTH,
            "indicator_splitter_collapsible": INDICATOR_SPLITTER_COLLAPSIBLE,
            "indicator_splitter_stretch": list(INDICATOR_SPLITTER_STRETCH),
            "indicator_splitter_sizes": list(INDICATOR_SPLITTER_SIZES),
            "indicator_splitter_orientation": INDICATOR_SPLITTER_ORIENTATION,
            "scroll_widget_resizable": SCROLL_WIDGET_RESIZABLE,
            "scroll_frame_shape": SCROLL_FRAME_SHAPE,
            "scroll_horizontal_policy": SCROLL_HORIZONTAL_POLICY,
            "scroll_minimum_height": SCROLL_MINIMUM_HEIGHT,
            "titled_margins": list(TITLED_MARGINS),
            "titled_spacing": TITLED_SPACING,
            "titled_head_margins": list(TITLED_HEAD_MARGINS),
            "activity_wrap_margins": list(ACTIVITY_WRAP_MARGINS),
            "activity_wrap_spacing": ACTIVITY_WRAP_SPACING,
            "gate_wrap_margins": list(GATE_WRAP_MARGINS),
            "gate_wrap_spacing": GATE_WRAP_SPACING,
            "gate_host_margins": list(GATE_HOST_MARGINS),
            "bot_area_margins": list(BOT_AREA_MARGINS),
            "bot_area_spacing": BOT_AREA_SPACING,
            "active_bot_row_margins": list(ACTIVE_BOT_ROW_MARGINS),
            "mode_row_margins": list(MODE_ROW_MARGINS),
            "chart_pick_row_margins": list(CHART_PICK_ROW_MARGINS),
            "chart_pick_row_index": CHART_PICK_ROW_INDEX,
        },
        "text": {
            "mode_label": MODE_LABEL_TEXT,
            "mode_label_style": MODE_LABEL_STYLE,
            "mode_hint_style": MODE_HINT_STYLE,
            "active_bot_label": ACTIVE_BOT_LABEL_TEXT,
            "active_bot_label_style": ACTIVE_BOT_LABEL_STYLE,
            "all_bots": ALL_BOTS_TEXT,
            "all_bots_data": ALL_BOTS_DATA,
            "active_bot_item_format": ACTIVE_BOT_ITEM_FORMAT,
            "bot_id_trim": BOT_ID_TRIM,
            "chart_title": CHART_TITLE,
            "voting_title": VOTING_TITLE,
            "chart_pick_label": CHART_PICK_LABEL_TEXT,
            "chart_pick_label_style": CHART_PICK_LABEL_STYLE,
            "chart_picker_empty": CHART_PICKER_EMPTY_TEXT,
            "chart_picker_empty_data": CHART_PICKER_EMPTY_DATA,
            "expand": EXPAND_TEXT,
            "expand_tooltip_format": EXPAND_TOOLTIP_FORMAT,
            "expand_tooltips": [
                expand_tooltip(CHART_TITLE),
                expand_tooltip(VOTING_TITLE),
            ],
            "expand_style": EXPAND_STYLE,
            "sim_log_title": SIM_LOG_TITLE,
            "pause": PAUSE_TEXT,
            "resume": RESUME_TEXT,
            "pause_checkable": PAUSE_BUTTON_CHECKABLE,
            "pause_style": PAUSE_STYLE,
            "log_read_only": LOG_READ_ONLY,
            "log_maximum_block_count": LOG_MAXIMUM_BLOCK_COUNT,
            "log_style": LOG_STYLE,
            "label_word_wrap": LABEL_WORD_WRAP,
            "label_selectable": LABEL_SELECTABLE,
            "log_selectable": LOG_SELECTABLE,
            "log_wraps_at_width": LOG_WRAPS_AT_WIDTH,
            "performance_prefix": PERFORMANCE_PREFIX,
            "gate_title": GATE_TITLE,
            "gate_unavailable": GATE_UNAVAILABLE_TEXT,
            "gate_unavailable_style": GATE_UNAVAILABLE_STYLE,
            "fleet_panel_unavailable": FLEET_PANEL_UNAVAILABLE_TEXT,
            "nuclear_panel_unavailable": NUCLEAR_PANEL_UNAVAILABLE_TEXT,
            "fire_disabled_tooltip": FIRE_DISABLED_TOOLTIP,
            "fire_column": FIRE_COLUMN,
        },
        "modes": {
            "rows": [list(one) for one in SIM_MODES],
            "hints": dict(MODE_HINTS),
            "default_key": DEFAULT_MODE_KEY,
            "nuclear_key": NUCLEAR_KEY,
            "selector_min_width": MODE_SELECTOR_MIN_WIDTH,
            "selector_tooltip": MODE_SELECTOR_TOOLTIP,
            "fleet_page_index": FLEET_PAGE_INDEX,
            "nuclear_page_index": NUCLEAR_PAGE_INDEX,
            "page_total": STACK_PAGE_TOTAL,
            "selected": model.sim_mode(),
            "hint_text": model.mode_hint_text,
            "stack_index": model.stack.current_index(),
            "stack_count": model.stack.count(),
            "items": [list(one) for one in model.mode_selector.items],
            "item_tooltips": list(model.mode_selector.item_tooltips),
            "index": model.mode_selector.index,
        },
        "pickers": {
            "active": {
                "minimum_width": model.active_bot_picker.minimum_width,
                "tooltip": model.active_bot_picker.tooltip,
                "items": [list(one) for one in model.active_bot_picker.items],
                "index": model.active_bot_picker.index,
                "changes": model.active_bot_picker.changes,
                "selected": model.active_bot_id(),
                "selected_text": model.active_bot_picker.current_text(),
            },
            "chart": {
                "minimum_width": model.chart_bot_picker.minimum_width,
                "tooltip": model.chart_bot_picker.tooltip,
                "items": [list(one) for one in model.chart_bot_picker.items],
                "index": model.chart_bot_picker.index,
                "changes": model.chart_bot_picker.changes,
                "selected_text": model.chart_bot_picker.current_text(),
                "focus_symbol": getattr(model.price_chart, "focus_symbol", None),
                "focus_calls": getattr(model.price_chart, "focus_calls", 0),
                "symbols": list(getattr(model.price_chart, "symbols", [])),
            },
        },
        "log": {
            "lines": list(model.log_pane.lines),
            "text": model.log_pane.text(),
            "maximum_blocks": model.log_pane.maximum_blocks,
            "activity_paused": model.activity_paused,
            "performance_paused": model.performance_paused,
            "pause_button_text": model.pause_button_text,
        },
        "table": {
            "mounted": widget is not None,
            "columns": list(getattr(panel, "_bot_table_columns", [])),
            "rows": [dict(one) for one in getattr(widget, "rows", [])],
            "fire_enabled": [
                cell.enabled for cell in getattr(widget, "fire_cells", [])
            ],
            "fire_tooltips": [
                cell.tooltip for cell in getattr(widget, "fire_cells", [])
            ],
            "emitted_counts": list(getattr(panel, "emitted_table_counts", [])),
        },
        "wiring": {
            "actions": dict(ACTIONS),
            "connections_at_build": CONNECTIONS_AT_BUILD,
            "signals": list(SIGNALS),
            "timers": dict(TIMERS),
            "threads": list(THREADS),
            "bus_topics": list(BUS_TOPICS),
            "telemetry_features": list(model.declared_features),
            "telemetry_declare_failed_format": TELEMETRY_DECLARE_FAILED_FORMAT,
            "telemetry_paused_reason": TELEMETRY_PAUSED_REASON,
            "telemetry_activity_write": TELEMETRY_ACTIVITY_WRITE,
            "telemetry_performance_write": TELEMETRY_PERFORMANCE_WRITE,
            "visuals_unavailable_format": VISUALS_UNAVAILABLE_FORMAT,
            "fleet_panel_set": panel is not None,
            "nuclear_panel_set": model.nuclear_panel is not None,
            "log_callbacks_set": getattr(panel, "log_callbacks", None) is not None,
            "async_loop_getter_set": getattr(panel, "async_loop_getter", None)
            is not None,
            "fleet_loaded_handlers": len(getattr(panel, "fleet_loaded_handlers", [])),
            "gate_panel_set": getattr(panel, "_gate_panel", None) is not None,
            "sim_mode_calls": list(getattr(panel, "sim_mode_calls", [])),
            "async_loop_set": model.async_loop is not None,
            "swarm_getter_set": model.swarm_getter is not None,
            "topology_getter_set": model.topology_getter is not None,
            "connectors_getter_set": model.connectors_getter is not None,
            "nuclear_swarm_getter_set": getattr(
                model.nuclear_panel, "swarm_getter", None
            )
            is not None,
            "nuclear_topology_getter_set": getattr(
                model.nuclear_panel, "topology_getter", None
            )
            is not None,
            "panel_bot_manager_set": getattr(panel, "bot_manager", None) is not None,
            "panel_connectors_getter_set": getattr(panel, "connectors_getter", None)
            is not None,
        },
        "focus": {
            "policies": dict(FOCUS_POLICIES),
            "order": list(FOCUS_ORDER),
        },
        "mounts": list(MOUNTS),
        "state_keys": {
            "scrumming_state": STATE_KEY,
            "stats": STATS_KEY,
            "source_bot_id": SOURCE_BOT_ID_KEY,
            "source_state": SOURCE_STATE_KEY,
            "main_lots": MAIN_LOTS_KEY,
            "units": UNITS_KEY,
        },
        "streams": {
            "activity": ACTIVITY_STREAM,
            "performance": PERFORMANCE_STREAM,
        },
        "pages": {
            "fleet": PAGE_FLEET,
            "nuclear": PAGE_NUCLEAR,
        },
        "refusals": {
            "append": APPEND_REFUSED_FORMAT,
            "nuclear_unavailable": NUCLEAR_UNAVAILABLE_LOG_FORMAT,
        },
        "log_levels": dict(LOG_LEVELS),
        "pins": {"mode": MODE_PIN, "log": LOG_PIN, "emitted": list(model.pins)},
        "call_names": list(CALL_NAMES),
        "calls": [list(one) for one in model.calls],
        "warnings": [list(one) for one in model.warnings],
        "dialogs": list(model.dialogs),
        "dialogs_shown": getattr(model.settings_dialog, "shown", 0),
        "error_types": sorted(ERROR_TYPES),
        "defaults": {
            "error_type": DEFAULT_ERROR_TYPE,
            "no_text": NO_TEXT,
            "bot_mode": DEFAULT_BOT_MODE,
            "bot_state": DEFAULT_BOT_STATE,
            "exchange": DEFAULT_EXCHANGE,
            "quote_to_usd": DEFAULT_QUOTE_TO_USD,
            "units": NO_UNITS,
            "price": NO_PRICE,
            "trades": NO_TRADES,
        },
    }


TAB_MODEL: Optional[SimulatorTabModel] = None


def tab_model() -> SimulatorTabModel:
    """The tab the bridge keeps between calls, built on first request."""
    global TAB_MODEL
    if TAB_MODEL is None:
        TAB_MODEL = SimulatorTabModel()
    return TAB_MODEL


def view_model(params: dict) -> dict:
    """Bridge handler for ``simulator_tab.state``.

    Reads ``reset``, ``panel``, ``nuclear``, ``chart``, ``build``,
    ``mode``, ``fleet``, ``statuses``, ``symbols``, ``chart_bot``,
    ``active_bot``, ``detail``, ``pause``, ``activity``, ``performance``
    and the four setter parameters from the request. The tab's state
    persists between calls because the tab does; ``reset`` is what a
    fresh paint sends.
    """
    global TAB_MODEL
    if params.get("reset", False):
        TAB_MODEL = SimulatorTabModel()
    model = tab_model()
    if "panel" in params:
        spec = params["panel"]
        if spec is None:
            model.set_fleet_panel(None)
        else:
            spec = dict(spec)
            error = spec.get("error")
            model.set_fleet_panel(
                FleetPanel(
                    statuses=spec.get("statuses"),
                    table_class=BotTable if spec.get("table", True) else None,
                    controller=SimController(
                        [SimBot(one) for one in spec.get("bots", [])]
                    ),
                    gate_panel=object() if spec.get("gate", False) else None,
                    statuses_raises=(
                        error_from(error.get("type"), error.get("text"))
                        if error
                        else None
                    ),
                )
            )
    if params.get("nuclear", False):
        model.set_nuclear_panel(NuclearPanel())
    if params.get("chart", False):
        model.set_price_chart(PriceChart())
    if params.get("build", False):
        model.build()
    if "mode" in params:
        model.select_mode(params["mode"])
    if "async_loop" in params:
        model.set_async_loop(params["async_loop"])
    if params.get("swarm", False):
        model.set_swarm_getter(lambda: None)
    if params.get("topology", False):
        model.set_topology_getter(lambda: None)
    if params.get("connectors", False):
        model.set_connectors_getter(lambda: None)
    if params.get("bot_manager", False):
        model.set_bot_manager(object())
    if "symbols" in params:
        model.refresh_chart_bot_roster(params["symbols"])
    if "chart_bot" in params:
        model.select_chart_bot(params["chart_bot"])
    if "statuses" in params:
        model.refresh_active_bot_roster(params["statuses"])
    if "fleet" in params:
        model.on_fleet_loaded(params["fleet"])
    if "detail" in params:
        model.on_sim_bot_detail(params["detail"])
    if "pause" in params:
        model.on_activity_paused(params["pause"])
    for line in params.get("activity", []):
        model.log_activity(line)
    for line in params.get("performance", []):
        model.log_performance(line)
    return build_view_model(model)
