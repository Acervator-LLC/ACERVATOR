"""nuclear_mode_panel_surface.py -- the Nuclear Mode fleet-soak panel as a
view model, without Qt.

Nuclear Mode loops the fleet stored in bot_state over its own Stone
Tablets under varying market noise and system load. The panel shows what
Start will load, four run settings, a Start and a Stop button, and
seventeen live-status rows.

Nothing here reads bot_state, builds a controller, schedules a run,
starts a thread, reads a clock or opens a file. Every outward fact the
panel reads -- what bot_state answered, whether an event loop exists,
what the controller did when built, prepared, scheduled and asked for a
snapshot, what the swarm and the Market Inspector answered -- is handed
in on ``PanelWorld``. A caller that wants any of it to happen does that
itself.

``PanelModel.build`` returns the screen: the cards, the labels, their
colours, their style sheets, the two spin boxes, the two tick boxes, the
two buttons and the status grid. ``start`` and ``stop`` are the two run
controls, ``rescan_fleet`` the fleet preview, and ``refresh_status`` one
tick of the status timer. ``run_steps`` drives a named sequence and
reports each step's index, name, refusal type and what the panel shows
after it, so a sequence that refuses part way is read step by step.

A refusal is a type. A world that cannot build, prepare or schedule
raises the class the world carries; the model answers with False and the
message it shows the operator.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``nuclear_mode_panel.state`` method, which is how the Electron
renderer reaches it. Every value below is written out here rather than
read from ``src.gui.simulator_tab.nuclear_mode_panel``, so a value
changed on one side alone is reported.
"""

from __future__ import annotations

from typing import Any

METHOD = "nuclear_mode_panel.state"

ACCESSIBLE_NAME = "Nuclear Mode Panel"
LOGGER_NAME = "acervator.nuclear_panel"

TEAL = "#00ffcc"
GOLD = "#ffcc44"
SUBTITLE_GREY = "#aab"
CARD_BG = "#0a0a14"
CARD_BORDER = "#2a2a44"
EMPTY_ORANGE = "#ff9966"
FLEET_BLUE = "#88c0ff"
LABEL_BLUE = "#88aaff"
VALUE_WHITE = "#fff"
RELOAD_BG = "#1a1a3a"
RELOAD_HOVER = "#222250"
START_BG = "#1a3a2a"
START_HOVER = "#225040"
STOP_FG = "#ff6688"
STOP_BG = "#3a1a1a"
STOP_HOVER = "#502222"
DISABLED_BG = "#202030"
DISABLED_FG = "#666"
DISABLED_BORDER = "#444"
HEADER_CARD_BG = "rgba(255,200,80,8)"
HEADER_CARD_BORDER = "rgba(255,204,68,68)"

TITLE = "Nuclear Mode — Fleet Soak"
SUBTITLE = (
    "Loops the LIVE fleet from bot_state — bots, Smart Wires and "
    "all — over its own Stone Tablets, re-rolling 10-25% "
    "market-structure noise every cycle so no two loops present "
    "the same conditions, while system load oscillates "
    "independently. Exercises real production code paths: trades, "
    "the Simulator Swarm, fold/stack tranches, and data "
    "reliability under load. Tablets are read-only and bot_state "
    "is never written; noise is applied to a copy. This is an "
    "abuse test, not a validation run — it measures coverage and "
    "survival, never trade accuracy."
)

FLEET_SECTION = "Fleet (from bot_state)"
CONFIG_SECTION = "Run configuration"
STATUS_SECTION = "Live status"

FLEET_ROW_LABEL = "Fleet:"
RELOAD_LABEL = "Reload fleet"
START_LABEL = "Start Scout"
STOP_LABEL = "Stop"

CYCLE_ROW_LABEL = "Cycle length:"
MAX_CYCLES_ROW_LABEL = "Max cycles:"
NOISE_LABEL = "Vary market structure per cycle"
LOAD_LABEL = "Oscillate system load"

PLACEHOLDER = "—"
BLANK = "-"
EMPTY_LABEL_TEXT = ""

EMPTY_FLEET_TEXT = (
    "bot_state has no scrumming bots, so there is no fleet to "
    "stress.\n\n"
    "Nuclear Mode loops the LIVE fleet's own Stone Tablets "
    "under varying\nmarket structure and system load. It does "
    "not synthesise bots, and it\nnever writes to bot_state or "
    "to the tablet archive."
)

CYCLE_TIP = (
    "Candles played per cycle. Each cycle replays the fleet's "
    "tablets under a freshly drawn market structure."
)
MAX_CYCLES_TIP = (
    "Stop after this many cycles. 0 = run until Stop is " "clicked — the soak case."
)
NOISE_TIP = (
    "Re-roll a 10–25% noise amplitude for every cycle, so "
    "successive loops present different market conditions. "
    "Stone Tablets are never modified — the noise is applied to "
    "a copy. Untick to replay the tablets unperturbed, which is "
    "how you ask whether a failure also happens on clean data."
)
LOAD_TIP = (
    "Sweep concurrency across cycles so the platform is "
    "stressed under varying load. Independent of market noise: "
    "this varies how hard the machine works, not what the "
    "market does."
)

DEFAULT_CYCLE_CANDLES = 3000
CYCLE_MIN = 120
CYCLE_MAX = 50_000
CYCLE_STEP = 500
CYCLE_SUFFIX = " candles"
MAX_CYCLES_MIN = 0
MAX_CYCLES_MAX = 100_000
MAX_CYCLES_DEFAULT = 0
UNLIMITED_TEXT = "unlimited"
NOISE_DEFAULT = True
LOAD_DEFAULT = True

REFRESH_INTERVAL_MS = 500
OUTER_MARGINS_PX = (8, 8, 8, 8)
OUTER_SPACING_PX = 8
CARD_MARGINS_PX = (8, 8, 8, 8)
HEADER_SPACING_PX = 4
FORM_SPACING_PX = 6
GRID_HORIZONTAL_SPACING_PX = 18
GRID_VERTICAL_SPACING_PX = 5
TITLE_FONT_PX = 15
SMALL_FONT_PX = 11
VALUE_FONT_PX = 12
BUTTON_FONT_PX = 13
CARD_RADIUS_PX = 4
HEADER_RADIUS_PX = 6
RELOAD_RADIUS_PX = 3
RELOAD_PADDING = "4px 12px"
RUN_BUTTON_PADDING = "8px 22px"
COLUMN_STRETCH = (0, 1, 0, 1)

NOISE_PERCENT_SCALE = 100.0
UPTIME_DECIMALS = 1
NOISE_DECIMALS = 1
MULTIPLIER_DECIMALS = 2
FLOAT_DECIMALS = 2
MULTIPLIER_SUFFIX = "x"
PERCENT_SUFFIX = "%"

RUNNING_TEXT = "RUNNING"
STOPPED_TEXT = "stopped"
YES_TEXT = "yes"
NO_TEXT = "no"

FLEET_SUMMARY_PARTS = (
    " bot(s) · ",
    " symbol(s) · ",
    " Smart Wire(s) from bot_state",
)
LOADER_FAILURE_PREFIX = "Could not read bot_state — "
TYPE_MESSAGE_JOIN = ": "

NO_LOOP_MESSAGE = (
    "Nuclear: no async loop available; cannot start the soak. "
    "(SimulatorTab must call set_async_loop before launch.)"
)
BUILD_FAILED_PREFIX = "Nuclear: controller construction failed: "
PREPARE_FAILED_PREFIX = "Nuclear: fleet load failed: "
SCHEDULE_FAILED_PREFIX = "Nuclear: could not schedule the soak: "
NO_SWARM_MESSAGE = (
    "Nuclear: Simulator Swarm unavailable — the soak will run "
    "but will not draw swarm rows."
)
INJECTING_PREFIX = "Nuclear: injecting "
INJECTING_SUFFIX = (
    " Market Inspector topology proposal(s) on top of the fleet's own wires."
)
NO_TOPOLOGY_MESSAGE = (
    "Nuclear: no Market Inspector proposal injected — "
    "stressing the fleet's own bot_state topology."
)

SWARM_HOOK_NAMES = ("register_sim_run", "update_sim_run", "stop_sim_run")

STATUS_FIELDS = (
    ("Run state", "running"),
    ("Uptime (s)", "uptime_seconds"),
    ("Fleet size", "fleet_size"),
    ("Symbols", "symbols"),
    ("Smart Wires loaded", "wires_loaded"),
    ("Cycle", "current_cycle"),
    ("Cycles completed", "cycles_completed"),
    ("Market noise", "noise_pct"),
    ("Load multiplier", "load_multiplier"),
    ("Cooling", "cooling"),
    ("Load sensed", "load_sensed"),
    ("Candles played", "total_candles"),
    ("Trades fired", "total_trades"),
    ("Exceptions", "total_exceptions"),
    ("Failed cycles", "failed_cycles"),
    ("Last error", "last_error"),
)

LAST_EXCEPTION_LABEL = "Last exception"
LABEL_SUFFIX = ":"
CELL_ALIGNMENT = "AlignLeft"
LAST_EXCEPTION_KEY = "last_exception"
LAST_EXCEPTION_SOURCE_KEY = "last_error"

BOOLEAN_STATUS_KEYS = ("cooling", "load_sensed")
RUN_STATE_KEY = "running"
UPTIME_KEY = "uptime_seconds"
NOISE_KEY = "noise_pct"
MULTIPLIER_KEY = "load_multiplier"

VOTING_SUMMARY_KEY = "voting_summary"
SYMBOL_KEY = "symbol"
LAST_PRICE_KEY = "last_price"
LAST_VOLUME_KEY = "last_volume"
DEFAULT_TIMEFRAME = "5m"
TIMEFRAME_ATTRIBUTE = "timeframe"
VOTING_KEYS = (
    "bullish",
    "bearish",
    "neutral",
    "net_score",
    "confidence",
    "direction",
    "signals",
    "locks",
)
SIGNAL_KEYS = ("indicator", "direction", "confidence", "details")

ACTIONS = {
    "reload_button_clicked": "rescan_fleet",
    "start_button_clicked": "start",
    "stop_button_clicked": "stop",
    "refresh_timer_tick": "refresh_status",
}

TIMERS = {"refresh_timer": "refresh_status"}

SIGNALS = ()
EMITTED_SIGNALS = ()
BUS_TOPICS = ()
BUS_EMITS = ()
THREADS = ()

STEP_NAMES = ("rescan_fleet", "start", "stop", "refresh_status")

SCREEN_ORDER = ("header_card", "fleet_card", "config_card", "buttons", "status_card")

RUN_CONTROL_KEYS = ("cycle_candles", "max_cycles", "noise", "load_oscillation")
FLEET_CARD_ORDER = ("heading", "empty", "detail", "reload_button")
CONFIG_CARD_ORDER = ("cycle_candles", "max_cycles", "noise", "load_oscillation")


def section_label_style() -> str:
    """The style sheet every card heading carries."""
    return f"color: {TEAL}; font-weight: bold;"


def card_style() -> str:
    """The style sheet the fleet, config and status cards carry."""
    return (
        f"QFrame{{background:{CARD_BG};border:1px solid {CARD_BORDER};"
        f"border-radius:{CARD_RADIUS_PX}px;}}"
    )


def header_card_style() -> str:
    """The style sheet the gold header card carries."""
    return (
        f"QFrame{{background:{HEADER_CARD_BG};"
        f"border:1px solid {HEADER_CARD_BORDER};"
        f"border-radius:{HEADER_RADIUS_PX}px;}}"
    )


def title_style() -> str:
    """The style sheet the panel title carries."""
    return f"color:{GOLD};font-size:{TITLE_FONT_PX}px;font-weight:bold;border:none;"


def small_text_style(colour: str) -> str:
    """The style sheet every 11px borderless line carries, in `colour`."""
    return f"color:{colour};border:none;font-size:{SMALL_FONT_PX}px;"


def status_label_style() -> str:
    """The style sheet a status row's name carries."""
    return f"color:{LABEL_BLUE};font-size:{SMALL_FONT_PX}px;border:none;"


def status_value_style() -> str:
    """The style sheet a status row's value carries."""
    return (
        f"color:{VALUE_WHITE};font-size:{VALUE_FONT_PX}px;"
        f"font-weight:bold;border:none;"
    )


def reload_button_style() -> str:
    """The style sheet the Reload fleet button carries."""
    return (
        f"QPushButton{{background:{RELOAD_BG};color:{LABEL_BLUE};"
        f"border:1px solid {LABEL_BLUE};border-radius:{RELOAD_RADIUS_PX}px;"
        f"padding:{RELOAD_PADDING};font-size:{SMALL_FONT_PX}px;}}"
        f"QPushButton:hover{{background:{RELOAD_HOVER};}}"
    )


def run_button_style(
    background: str, foreground: str, hover: str, is_bold: bool
) -> str:
    """The style sheet a run button carries, with its disabled look."""
    weight = "font-weight:bold;" if is_bold else ""
    return (
        f"QPushButton{{background:{background};color:{foreground};"
        f"border:1px solid {foreground};border-radius:{CARD_RADIUS_PX}px;"
        f"padding:{RUN_BUTTON_PADDING};{weight}"
        f"font-size:{BUTTON_FONT_PX}px;}}"
        f"QPushButton:hover{{background:{hover};}}"
        f"QPushButton:disabled{{background:{DISABLED_BG};color:{DISABLED_FG};"
        f"border-color:{DISABLED_BORDER};}}"
    )


def start_button_style() -> str:
    """The style sheet the Start button carries."""
    return run_button_style(START_BG, TEAL, START_HOVER, True)


def stop_button_style() -> str:
    """The style sheet the Stop button carries."""
    return run_button_style(STOP_BG, STOP_FG, STOP_HOVER, False)


def status_half() -> int:
    """How many status rows the left column-pair holds."""
    return (len(STATUS_FIELDS) + 1) // 2


def status_cells() -> list:
    """Every status row as its key, its row and its label column."""
    half = status_half()
    placed = []
    for index, (label, key) in enumerate(STATUS_FIELDS):
        row = index if index < half else index - half
        column = 0 if index < half else 2
        placed.append(
            {
                "key": key,
                "label": label,
                "text": f"{label}{LABEL_SUFFIX}",
                "row": row,
                "column": column,
            }
        )
    return placed


def last_exception_cell() -> dict:
    """The full-width row the last exception is written on."""
    return {
        "key": LAST_EXCEPTION_KEY,
        "label": LAST_EXCEPTION_LABEL,
        "text": f"{LAST_EXCEPTION_LABEL}{LABEL_SUFFIX}",
        "row": status_half(),
        "column": 0,
        "column_span": 3,
        "word_wrap": True,
    }


def fleet_summary(bot_count: int, symbol_count: int, wire_count: int) -> str:
    """The one-line fleet preview the panel shows above Start."""
    first, second, third = FLEET_SUMMARY_PARTS
    return f"{bot_count}{first}{symbol_count}{second}{wire_count}{third}"


def failure_text(prefix: str, exc: BaseException) -> str:
    """`prefix` followed by the refusal's type and its message."""
    return f"{prefix}{type(exc).__name__}{TYPE_MESSAGE_JOIN}{exc}"


def symbols_of(bot_configs) -> list:
    """Every symbol the loaded bots name, sorted and without repeats."""
    return sorted(
        {
            str(config.get(SYMBOL_KEY, "") or "")
            for config in bot_configs
            if config.get(SYMBOL_KEY)
        }
    )


def format_status(key: str, value) -> str:
    """Render one snapshot value for the status grid.

    Raises whatever a value refuses to become a number, which is what the
    shipped panel catches one field at a time.
    """
    if value is None:
        return BLANK
    if key == RUN_STATE_KEY:
        return RUNNING_TEXT if value else STOPPED_TEXT
    if key == UPTIME_KEY:
        return f"{float(value):.{UPTIME_DECIMALS}f}"
    if key == NOISE_KEY:
        if not value:
            return BLANK
        scaled = float(value) * NOISE_PERCENT_SCALE
        return f"{scaled:.{NOISE_DECIMALS}f}{PERCENT_SUFFIX}"
    if key == MULTIPLIER_KEY:
        return f"{float(value):.{MULTIPLIER_DECIMALS}f}{MULTIPLIER_SUFFIX}"
    if key in BOOLEAN_STATUS_KEYS:
        return YES_TEXT if value else NO_TEXT
    if isinstance(value, bool):
        return YES_TEXT if value else NO_TEXT
    if isinstance(value, float):
        return f"{value:,.{FLOAT_DECIMALS}f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value) if str(value) else BLANK


def last_exception_text(snapshot: dict) -> str:
    """What the full-width last-exception row shows for `snapshot`."""
    text = str(snapshot.get(LAST_EXCEPTION_SOURCE_KEY, "") or "")
    return text if text else BLANK


def voting_payload(summary) -> dict:
    """The indicator-voting feed one snapshot summary produces."""
    timeframe = str(getattr(summary, TIMEFRAME_ATTRIBUTE, "") or DEFAULT_TIMEFRAME)
    return {
        timeframe: {
            "bullish": summary.bullish_count,
            "bearish": summary.bearish_count,
            "neutral": summary.neutral_count,
            "net_score": summary.net_score,
            "confidence": summary.consensus_confidence,
            "direction": summary.consensus_direction.name,
            "signals": [
                {
                    "indicator": one.indicator,
                    "direction": one.direction.name,
                    "confidence": one.confidence,
                    "details": {},
                }
                for one in summary.signals
            ],
            "locks": [],
        }
    }


class PanelWorld:
    """What the panel reads outside itself, handed in rather than read.

    ``bot_configs`` and ``smart_wires`` are what bot_state answered, and
    ``loader_error`` an exception instance for a bot_state that refused.
    ``loop`` stands for the event loop the tab supplies and ``loop_error``
    for a getter that raised. ``build_error``, ``prepare_result``,
    ``prepare_error`` and ``schedule_error`` are what the controller did
    when built, prepared and scheduled, and ``runs_immediately`` whether
    the event loop had already picked the run up. ``snapshots`` is what each status
    tick answers in turn, or an exception instance for a tick that
    refused. ``swarm`` and ``topologies`` are what the Simulator Swarm and
    the Market Inspector answered, with ``swarm_error`` and
    ``topology_error`` for a getter that raised.
    """

    def __init__(
        self,
        bot_configs=(),
        smart_wires=(),
        loader_error: Exception | None = None,
        loop: Any = None,
        loop_error: Exception | None = None,
        build_error: Exception | None = None,
        prepare_result: bool = True,
        prepare_error: Exception | None = None,
        schedule_error: Exception | None = None,
        runs_immediately: bool = False,
        snapshots: Any = (),
        swarm: Any = None,
        swarm_error: Exception | None = None,
        topologies: Any = None,
        topology_error: Exception | None = None,
        has_swarm_getter: bool = False,
        has_topology_getter: bool = False,
        chart: Any = None,
        voting_readout: Any = None,
    ):
        self.bot_configs = list(bot_configs)
        self.smart_wires = list(smart_wires)
        self.loader_error = loader_error
        self.loop = loop
        self.loop_error = loop_error
        self.build_error = build_error
        self.prepare_result = prepare_result
        self.prepare_error = prepare_error
        self.schedule_error = schedule_error
        self.runs_immediately = runs_immediately
        self.snapshots = list(snapshots)
        self.swarm = swarm
        self.swarm_error = swarm_error
        self.topologies = topologies
        self.topology_error = topology_error
        self.has_swarm_getter = has_swarm_getter
        self.has_topology_getter = has_topology_getter
        self.chart = chart
        self.voting_readout = voting_readout
        self.snapshot_calls = 0
        self.loader_calls = 0
        self.built_runs: list = []
        self.swarm_hooks_set: list = []
        self.topologies_set: list = []
        self.scheduled = 0
        self.stops = 0
        self.chart_ticks: list = []
        self.voting_updates: list = []

    def load_fleet(self):
        """What bot_state answers this preview. Raises what it refuses."""
        self.loader_calls += 1
        if self.loader_error is not None:
            raise self.loader_error
        return list(self.bot_configs), list(self.smart_wires)

    def event_loop(self):
        """The loop the tab supplies. Raises what its getter refuses."""
        if self.loop_error is not None:
            raise self.loop_error
        return self.loop

    def next_snapshot(self):
        """The next status tick this world answers, or the last for ever."""
        if not self.snapshots:
            answer: Any = {}
        elif self.snapshot_calls < len(self.snapshots):
            answer = self.snapshots[self.snapshot_calls]
        else:
            answer = self.snapshots[-1]
        self.snapshot_calls += 1
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def resolve_swarm(self):
        """The Simulator Swarm. Raises what its getter refuses."""
        if self.swarm_error is not None:
            raise self.swarm_error
        return self.swarm

    def resolve_topologies(self):
        """The Market Inspector proposals. Raises what its getter refuses."""
        if self.topology_error is not None:
            raise self.topology_error
        return self.topologies


class SoakRun:
    """One controller, holding no fleet and scheduling no coroutine."""

    def __init__(self, world: PanelWorld, **settings):
        if world.build_error is not None:
            raise world.build_error
        self.world = world
        self.settings = dict(settings)
        self.is_running = False
        world.built_runs.append(dict(settings))

    def prepare(self) -> bool:
        """Whether the fleet loaded. Raises what the loader refuses."""
        if self.world.prepare_error is not None:
            raise self.world.prepare_error
        return bool(self.world.prepare_result)

    def set_swarm_hooks(self, register=None, update=None, stop=None) -> None:
        """Record the three swarm hooks this run was handed."""
        self.world.swarm_hooks_set.append((register, update, stop))

    def set_topologies(self, proposals) -> None:
        """Record the Market Inspector proposals this run was handed."""
        self.world.topologies_set.append(list(proposals))

    def schedule(self) -> None:
        """Ask for the run. Raises what the scheduler refuses.

        Asking is not running. The scheduler hands the run to an event
        loop and returns at once, so the run reports itself as running
        only once that loop has picked it up.
        """
        if self.world.schedule_error is not None:
            raise self.world.schedule_error
        self.world.scheduled += 1
        self.is_running = bool(self.world.runs_immediately)

    def snapshot(self) -> dict:
        """The status this run answers now."""
        return self.world.next_snapshot()

    def stop(self) -> None:
        """Ask the run to drain its current cycle."""
        self.world.stops += 1
        self.is_running = False


class PanelModel:
    """The Nuclear Mode panel: a fleet preview, four settings and a run.

    ``rescan_fleet`` previews what Start will load. ``start`` builds a
    run, prepares it, hands it the swarm and the proposals and asks for
    it. ``stop`` puts every control back. ``refresh_status`` is one tick
    of the 500 ms timer.
    """

    def __init__(self, world: PanelWorld):
        self.world = world
        self.run: SoakRun | None = None
        self.cycle_candles = DEFAULT_CYCLE_CANDLES
        self.max_cycles = MAX_CYCLES_DEFAULT
        self.noise_enabled = NOISE_DEFAULT
        self.load_oscillation = LOAD_DEFAULT
        self.fleet_detail = PLACEHOLDER
        self.empty_text = EMPTY_LABEL_TEXT
        self.empty_visible = False
        self.start_enabled = True
        self.stop_enabled = False
        self.reload_enabled = True
        self.control_enabled = {name: True for name in RUN_CONTROL_KEYS}
        self.timer_running = False
        self.activity: list = []
        self.logged: list = []
        self.status_text = {key: PLACEHOLDER for _label, key in STATUS_FIELDS}
        self.status_text[LAST_EXCEPTION_KEY] = PLACEHOLDER
        self.rescan_fleet()

    def _say(self, message: str) -> None:
        self.activity.append(message)

    def rescan_fleet(self) -> bool:
        """Preview the fleet Start will load. False when it cannot."""
        self.empty_visible = False
        try:
            configs, wires = self.world.load_fleet()
        except Exception as exc:
            self.fleet_detail = failure_text(LOADER_FAILURE_PREFIX, exc)
            self.start_enabled = False
            return False
        if not configs:
            self.fleet_detail = PLACEHOLDER
            self.start_enabled = False
            self.empty_text = EMPTY_FLEET_TEXT
            self.empty_visible = True
            return False
        self.fleet_detail = fleet_summary(
            len(configs), len(symbols_of(configs)), len(wires)
        )
        self.start_enabled = True
        return True

    def swarm_hooks(self) -> tuple:
        """The three bound swarm hooks, or three Nones."""
        if not self.world.has_swarm_getter:
            return None, None, None
        try:
            swarm = self.world.resolve_swarm()
        except Exception as exc:
            self.logged.append(("swarm getter", type(exc).__name__))
            return None, None, None
        if swarm is None:
            return None, None, None
        return tuple(getattr(swarm, name, None) for name in SWARM_HOOK_NAMES)

    def topology_proposals(self) -> list:
        """The proposals to inject this run, or an empty list."""
        if not self.world.has_topology_getter:
            return []
        try:
            return list(self.world.resolve_topologies() or [])
        except Exception as exc:
            self.logged.append(("topology getter", type(exc).__name__))
            return []

    def start(self) -> bool:
        """Build, prepare and ask for a soak. False when it did not begin."""
        if self.run is not None and self.run.is_running:
            return False
        try:
            loop = self.world.event_loop()
        except Exception:
            loop = None
        if loop is None:
            self._say(NO_LOOP_MESSAGE)
            return False
        try:
            self.run = SoakRun(
                self.world,
                cycle_candles=int(self.cycle_candles),
                max_cycles=(int(self.max_cycles) or None),
                load_oscillation=self.load_oscillation,
                noise_enabled=self.noise_enabled,
            )
        except Exception as exc:
            self._say(failure_text(BUILD_FAILED_PREFIX, exc))
            self.run = None
            return False
        try:
            ready = self.run.prepare()
        except Exception as exc:
            self._say(failure_text(PREPARE_FAILED_PREFIX, exc))
            self.run = None
            return False
        if not ready:
            self.run = None
            return False
        register, update, stop = self.swarm_hooks()
        if register is None:
            self._say(NO_SWARM_MESSAGE)
        self.run.set_swarm_hooks(register=register, update=update, stop=stop)
        proposals = self.topology_proposals()
        if proposals:
            self.run.set_topologies(proposals)
            self._say(f"{INJECTING_PREFIX}{len(proposals)}{INJECTING_SUFFIX}")
        else:
            self._say(NO_TOPOLOGY_MESSAGE)
        try:
            self.run.schedule()
        except Exception as exc:
            self._say(failure_text(SCHEDULE_FAILED_PREFIX, exc))
            self.run = None
            return False
        self.start_enabled = False
        self.stop_enabled = True
        self.reload_enabled = False
        self.control_enabled = {name: False for name in RUN_CONTROL_KEYS}
        self.timer_running = True
        return True

    def stop(self) -> None:
        """Ask the soak to stop and put every control back."""
        if self.run is not None:
            self.run.stop()
        self.stop_enabled = False
        self.start_enabled = True
        self.reload_enabled = True
        self.control_enabled = {name: True for name in RUN_CONTROL_KEYS}
        self.refresh_status()
        self.timer_running = False

    def feed_visuals(self, snapshot: dict) -> None:
        """Push one snapshot into the shared Simulator panels."""
        symbol = str(snapshot.get(SYMBOL_KEY, "") or "")
        if not symbol:
            return
        if self.world.chart is not None:
            try:
                price = float(snapshot.get(LAST_PRICE_KEY, 0.0) or 0.0)
                if price > 0:
                    volume = float(snapshot.get(LAST_VOLUME_KEY, 0.0) or 0.0)
                    self.world.chart_ticks.append((symbol, price, volume))
            except Exception as exc:
                self.logged.append(("price chart", type(exc).__name__))
        summary = snapshot.get(VOTING_SUMMARY_KEY)
        if self.world.voting_readout is not None and summary is not None:
            try:
                self.world.voting_updates.append((voting_payload(summary), symbol))
            except Exception as exc:
                self.logged.append(("voting readout", type(exc).__name__))

    def refresh_status(self) -> bool:
        """One status tick. False when there was nothing to read."""
        if self.run is None:
            return False
        try:
            snapshot = self.run.snapshot()
        except Exception as exc:
            self.logged.append(("snapshot", type(exc).__name__))
            return False
        try:
            self.feed_visuals(snapshot)
        except Exception as exc:
            self.logged.append(("visual feed", type(exc).__name__))
        for _label, key in STATUS_FIELDS:
            try:
                self.status_text[key] = format_status(key, snapshot.get(key))
            except Exception as exc:
                self.logged.append((key, type(exc).__name__))
        self.status_text[LAST_EXCEPTION_KEY] = last_exception_text(snapshot)
        return True

    def state(self) -> dict:
        """What a reader sees on the panel right now."""
        return {
            "fleet_detail": self.fleet_detail,
            "empty_text": self.empty_text,
            "empty_visible": self.empty_visible,
            "start_enabled": self.start_enabled,
            "stop_enabled": self.stop_enabled,
            "reload_enabled": self.reload_enabled,
            "control_enabled": dict(self.control_enabled),
            "timer_running": self.timer_running,
            "status_text": dict(self.status_text),
            "activity": list(self.activity),
        }

    def build(self) -> dict:
        """The whole panel as one serialisable screen."""
        return {
            "accessible_name": ACCESSIBLE_NAME,
            "layout": {
                "margins_px": list(OUTER_MARGINS_PX),
                "spacing_px": OUTER_SPACING_PX,
                "order": list(SCREEN_ORDER),
            },
            "header_card": {
                "style": header_card_style(),
                "spacing_px": HEADER_SPACING_PX,
                "title": {"text": TITLE, "style": title_style()},
                "subtitle": {
                    "text": SUBTITLE,
                    "style": small_text_style(SUBTITLE_GREY),
                    "word_wrap": True,
                },
            },
            "fleet_card": {
                "style": card_style(),
                "margins_px": list(CARD_MARGINS_PX),
                "heading": {"text": FLEET_SECTION, "style": section_label_style()},
                "empty": {
                    "text": self.empty_text,
                    "style": small_text_style(EMPTY_ORANGE),
                    "visible": self.empty_visible,
                    "word_wrap": True,
                },
                "form_spacing_px": FORM_SPACING_PX,
                "detail_row_label": FLEET_ROW_LABEL,
                "reload_row_label": EMPTY_LABEL_TEXT,
                "detail": {
                    "text": self.fleet_detail,
                    "style": small_text_style(FLEET_BLUE),
                    "word_wrap": True,
                },
                "reload_button": {
                    "text": RELOAD_LABEL,
                    "style": reload_button_style(),
                    "enabled": self.reload_enabled,
                },
                "order": list(FLEET_CARD_ORDER),
            },
            "config_card": {
                "style": card_style(),
                "margins_px": list(CARD_MARGINS_PX),
                "heading": {"text": CONFIG_SECTION, "style": section_label_style()},
                "form_spacing_px": FORM_SPACING_PX,
                "order": list(CONFIG_CARD_ORDER),
                "cycle_candles": {
                    "row_label": CYCLE_ROW_LABEL,
                    "minimum": CYCLE_MIN,
                    "maximum": CYCLE_MAX,
                    "single_step": CYCLE_STEP,
                    "value": self.cycle_candles,
                    "suffix": CYCLE_SUFFIX,
                    "tooltip": CYCLE_TIP,
                    "enabled": self.control_enabled["cycle_candles"],
                },
                "max_cycles": {
                    "row_label": MAX_CYCLES_ROW_LABEL,
                    "minimum": MAX_CYCLES_MIN,
                    "maximum": MAX_CYCLES_MAX,
                    "value": self.max_cycles,
                    "special_value_text": UNLIMITED_TEXT,
                    "tooltip": MAX_CYCLES_TIP,
                    "enabled": self.control_enabled["max_cycles"],
                },
                "noise": {
                    "text": NOISE_LABEL,
                    "checked": self.noise_enabled,
                    "tooltip": NOISE_TIP,
                    "row_label": EMPTY_LABEL_TEXT,
                    "enabled": self.control_enabled["noise"],
                },
                "load_oscillation": {
                    "text": LOAD_LABEL,
                    "checked": self.load_oscillation,
                    "tooltip": LOAD_TIP,
                    "row_label": EMPTY_LABEL_TEXT,
                    "enabled": self.control_enabled["load_oscillation"],
                },
            },
            "buttons": {
                "start": {
                    "text": START_LABEL,
                    "style": start_button_style(),
                    "enabled": self.start_enabled,
                },
                "stop": {
                    "text": STOP_LABEL,
                    "style": stop_button_style(),
                    "enabled": self.stop_enabled,
                },
            },
            "status_card": {
                "style": card_style(),
                "margins_px": list(CARD_MARGINS_PX),
                "heading": {"text": STATUS_SECTION, "style": section_label_style()},
                "horizontal_spacing_px": GRID_HORIZONTAL_SPACING_PX,
                "vertical_spacing_px": GRID_VERTICAL_SPACING_PX,
                "column_stretch": list(COLUMN_STRETCH),
                "alignment": CELL_ALIGNMENT,
                "label_style": status_label_style(),
                "value_style": status_value_style(),
                "cells": status_cells(),
                "last_exception": last_exception_cell(),
                "values": dict(self.status_text),
            },
            "timer": {
                "interval_ms": REFRESH_INTERVAL_MS,
                "running": self.timer_running,
            },
        }


def run_steps(model: PanelModel, steps) -> list:
    """Drive `steps` in order and report each one.

    Each step is a name from ``STEP_NAMES``. Each report names the step's
    index, its name, the refusal type it raised or None, and what the
    panel shows after it. A step that raises ends the sequence.
    """
    report = []
    for index, step in enumerate(steps):
        refusal = None
        try:
            _run_one_step(model, step)
        except Exception as exc:
            refusal = type(exc).__name__
        report.append(dict(index=index, step=step, refusal=refusal, **model.state()))
        if refusal is not None:
            break
    return report


def _run_one_step(model: PanelModel, name: str):
    if name == "rescan_fleet":
        return model.rescan_fleet()
    if name == "start":
        return model.start()
    if name == "stop":
        return model.stop()
    if name == "refresh_status":
        return model.refresh_status()
    raise LookupError(name)


def build_view_model(
    bot_configs=(),
    smart_wires=(),
    cycle_candles: int = DEFAULT_CYCLE_CANDLES,
    max_cycles: int = MAX_CYCLES_DEFAULT,
) -> dict:
    """The panel screen a fleet of these bots and wires paints."""
    model = PanelModel(PanelWorld(bot_configs=bot_configs, smart_wires=smart_wires))
    model.cycle_candles = cycle_candles
    model.max_cycles = max_cycles
    return model.build()


def view_model(params: dict) -> dict:
    """The bridge handler for ``nuclear_mode_panel.state``."""
    params = params or {}
    return {
        "screen": build_view_model(
            bot_configs=list(params.get("bot_configs", ()) or ()),
            smart_wires=list(params.get("smart_wires", ()) or ()),
            cycle_candles=int(params.get("cycle_candles", DEFAULT_CYCLE_CANDLES)),
            max_cycles=int(params.get("max_cycles", MAX_CYCLES_DEFAULT)),
        ),
        "status_fields": [list(pair) for pair in STATUS_FIELDS],
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "signals": list(SIGNALS),
        "bus_topics": list(BUS_TOPICS),
        "step_names": list(STEP_NAMES),
    }
