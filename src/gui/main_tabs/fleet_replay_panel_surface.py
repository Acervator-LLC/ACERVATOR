"""fleet_replay_panel_surface.py -- the Fleet Replay panel, without Qt.

Describes the Simulator's left-hand Fleet Replay panel: a header, a load
bar carrying four controls, a three-column table of the loaded fleet, a
progress line and the Start and Stop buttons.

``FleetReplayPanelModel`` holds the panel's state. ``load`` reads the
stored fleet, fills the table and spawns the sim bots. ``fetch_ytd``,
``start``, ``stop`` and ``reset`` are the other four buttons.
``refresh_progress`` and ``drain`` are what the panel's two timers run.

``FleetLoaderSource``, ``TabletRegistrySource``, ``ControllerSource``,
``TapeSource``, ``BotSource``, ``StatsSource``, ``ProgressSource`` and
``ScheduleSink`` are plain stand-ins for the stored-fleet loader, the
Stone Tablet registry, the replay controller, its tape, a sim bot, that
bot's counters, the controller's progress record and the loop hand-off,
so the panel can be driven over the bridge from values alone.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``fleet_replay_panel.state`` method, which is how the Electron
renderer reaches it. Every value below is written out here rather than
read from ``src.gui.simulator_tab.fleet.fleet_replay_panel``, so a value
changed on one side alone is reported. Nothing here imports Qt, and
nothing here starts a replay.
"""

from __future__ import annotations

import math
from typing import Any, Optional

METHOD = "fleet_replay_panel.state"

ACCESSIBLE_NAME = "Fleet Replay Panel"

GATE_HOST_PANEL = "panel"
GATE_HOST_TABLE = "table"

OUTER_MARGIN_PX = 10
OUTER_SPACING_PX = 10

HEADER_STYLE = (
    "QFrame{background:rgba(0,255,204,10);"
    "border:1px solid rgba(0,204,204,68);"
    "border-radius:6px;}"
)
TITLE_TEXT = "Fleet Replay — sim the live fleet against YTD data"
TITLE_STYLE = "color:#00ffcc;font-size:15px;font-weight:bold;border:none;"
SUBTITLE_TEXT = (
    "Loads every live bot config from bot_state.json and "
    "runs isolated ScrummingBot instances against a fake "
    "FleetSimExchange. Bot class code is unmodified — "
    "parity with live is the point. Start Replay currently "
    "plays synthetic candles for immediate observability; "
    "real YTD candle feed lands v3.23.79-B via History "
    "Tab's Refresh signal."
)
SUBTITLE_STYLE = "color:#aaa;font-size:11px;border:none;"
SUBTITLE_WORD_WRAP = True

LOAD_BUTTON_TEXT = "Load live fleet"
LOAD_BUTTON_TOOLTIP = (
    "Read ~/.acervator/bot_state.json and load every "
    "Scrumming bot config as a fresh sim instance."
)
FETCH_BUTTON_TEXT = "Fetch YTD"
FETCH_BUTTON_TOOLTIP = (
    "Pull real 1d OHLCV (limit=200 candles ≈ 6.5 months) "
    "per loaded-bot symbol from the connected exchange. "
    "Coalesced through MarketDataPool. After this "
    "completes, Start Replay uses real market data "
    "instead of synthetic sine waves."
)
RESET_BUTTON_TEXT = "Reset"
RESET_BUTTON_TOOLTIP = "Clear the loaded fleet + stop any running replay."
FULL_EVAL_TEXT = "Full evaluation"
FULL_EVAL_TOOLTIP = (
    "Unchecked (default): validation run — only candles "
    "with a historical trade are evaluated, each preceded "
    "by a warm-up window so indicators are valid. Much "
    "faster.\n\n"
    "Checked: strategy run — every candle is evaluated. "
    "Slower, but required when developing or tuning a "
    "strategy, and the only mode that detects the sim "
    "trading where live did not."
)
FULL_EVAL_DEFAULT = False

START_BUTTON_TEXT = "Start Replay"
START_BUTTON_TOOLTIP = (
    "Play synthetic candles through each loaded bot's "
    "tick(). Real YTD data lands v3.23.79-B."
)
STOP_BUTTON_TEXT = "Stop"
STOP_BUTTON_TOOLTIP = (
    "Cooperative stop; tick loop drains its current iteration and exits."
)

STATUS_STYLE = "color:#888;font-size:11px;"
IDLE_STATUS_TEXT = "No fleet loaded — press Load live fleet."
CLEARED_STATUS_TEXT = "Fleet cleared — press Load live fleet."

FLEET_GROUP_TITLE = "Loaded fleet"
COLUMNS = ("Symbol", "Target USD", "Sim Trades")
COLUMN_COUNT = 3
SYMBOL_COLUMN = 0
TARGET_COLUMN = 1
TRADES_COLUMN = 2
TABLE_TOOLTIP = (
    "One row per Scrumming bot from bot_state.json. "
    "Sim Trades increments live during Start Replay."
)
ALTERNATING_ROW_COLORS = True
EDIT_TRIGGERS = "NoEditTriggers"
HEADER_RESIZE_MODE = "ResizeToContents"
STRETCH_LAST_SECTION = True
TABLE_STRETCH = 1

PROGRESS_STYLE = "color:#7fb3ff; font-size:11px; padding:2px 6px;"
PROGRESS_WORD_WRAP = True
IDLE_PROGRESS_TEXT = "Replay idle — load a fleet + press Start Replay."
STARTING_PROGRESS_TEXT = "Replay starting…"

TARGET_FORMAT = "${target:,.2f}"
ZERO_TRADES_TEXT = "0"
EMPTY_CELL = None
TRADE_COUNT_FORMAT = "{count}"

LOAD_FAILED_FORMAT = "Load failed: {error}: {message}"
SPAWN_FAILED_FORMAT = "Fleet spawn failed: {error}: {message}"
LOADED_FORMAT = (
    "Loaded {bot_count} bot(s) across {symbol_count} symbol(s) — "
    "${total_target_usd:,.0f} total target"
)
SPAWNED_SUFFIX_FORMAT = " — {spawned} simulated bot(s) spawned."
NO_SPAWN_SUFFIX = " — NO bots spawned (no tablets?)."

HISTORY_LOADED_FORMAT = (
    "YTD front-loaded from History: {count:,} trades across {symbols} symbol(s)."
)
HISTORY_EMPTY_TEXT = "History refresh emitted 0 trades (nothing to front-load)."

FETCH_NO_LOOP_TEXT = "Cannot fetch: async loop not wired."
FETCH_LOOP_GONE_TEXT = "Cannot fetch: async loop unavailable."
FETCH_NO_MANAGER_TEXT = (
    "Cannot fetch: bot_manager not wired (same requirement History Tab has)."
)
FETCH_RUNNING_TEXT = (
    "Fetching YTD trades via history_helpers (same call History Tab uses)…"
)
FETCH_SCHEDULE_FAILED_FORMAT = "Fetch schedule failed: {message}"
FETCH_EMPTY_TEXT = (
    "Fetch YTD returned no trades. "
    "(Same behaviour as History Tab under identical "
    "conditions.) Check console log for details."
)
FETCH_DONE_FORMAT = "YTD trades fetched: {count:,} across {symbols} symbol(s)."

START_BUSY_TEXT = (
    "A replay is already running. Press Stop or wait "
    "for it to finish before starting another."
)
START_NO_FLEET_TEXT = "Cannot start: no fleet loaded. Press 'Load live fleet' first."
START_NO_LOOP_TEXT = "Cannot start: async loop not wired by MainWindow."
START_LOOP_GONE_TEXT = "Cannot start: async loop unavailable."
START_NO_TABLETS_TEXT = (
    "Cannot start: no Stone Tablets available for "
    "any loaded bot. Run Fetch YTD first."
)
START_NO_TABLETS_LOG = "Cannot start: no bots have Stone Tablets. Aborting."
START_SCHEDULE_FAILED_FORMAT = "Schedule failed: {message}"

STOP_REFUSED_FORMAT = (
    "Stop: the replay did not accept the stop "
    "request ({error}: {message}). It may still be running."
)
RESET_REFUSED_FORMAT = (
    "Reset: could not stop the running replay "
    "({error}: {message}). It may still be "
    "running — check the Simulator log."
)
RESET_CONFIRM_TITLE = "Reset replay"
RESET_CONFIRM_TEXT = (
    "A replay is still running.\n\n" "Reset will stop it and clear the fleet. Continue?"
)

UNSPECIFIED_FAILURE_TEXT = "Unspecified failure (no reason was recorded)."

PARITY_ACTIVE_FORMAT = "Parity active: {count} live YTD trade(s) loaded for comparison."
PARITY_SKIPPED_TEXT = (
    "Parity check SKIPPED — no live YTD trades loaded. "
    "This run is synthetic and is NOT comparable to "
    "live. Press Fetch YTD first if you want parity."
)
PARITY_NO_LIVE_TEXT = (
    "Parity: skipped — no live trades loaded. "
    "Run Fetch YTD before Start Replay to "
    "measure sim-vs-live reproduction."
)
PARITY_NO_SIM_FORMAT = (
    "Parity: sim produced 0 trades against "
    "{live_count:,} live trades — 0% reproduction."
)
PARITY_FAILED_FORMAT = "Parity comparison failed: {error}: {message}"

MISSING_TABLET_FORMAT = "No Stone Tablet for {count} symbol(s): {symbols}"
MISSING_TABLET_LIMIT = 8
MISSING_TABLET_MORE = " ..."
SIM_STATE_SAVED_FORMAT = (
    "simulator_bot_state saved: {count} bot(s); parity green on {green}/{total}."
)
PARITY_MISMATCH_FORMAT = "  PARITY MISMATCH {bot_id}: {reason}"
FIRST_SPAWN_TEXT = "spawn drift: first spawn, no prior state."
SPAWN_DRIFT_FORMAT = (
    "spawn drift vs last Load: "
    "{added} added, {removed} removed, "
    "{changed} live-source changed, {unchanged} identical."
)
LIVE_SOURCE_MOVED_FORMAT = "  LIVE SOURCE MOVED {bot_id}"
SIM_STATE_FAILED_FORMAT = "simulator_bot_state FAILED: {message}"
SIM_STATE_PATH_NAME = "simulator_bot_state.json"
MISMATCH_ROW_LIMIT = 5
DRIFT_ROW_LIMIT = 5
PIN_CONTEXT_LIMIT = 8

SPAWNED_LOG_FORMAT = (
    "Spawned {count} simulated bot(s) from bot_state "
    "({symbols} symbol(s) with tablets)."
)

ACTIVITY_PREFIX = "[FleetReplay] %s"
PERFORMANCE_PREFIX = "[FleetReplay perf] %s"

YTD_WINDOW_FORMAT = (
    "YTD window: {days:.1f} days · expected "
    "~{expected:,} candles per symbol "
    "(122 days × 288 5m candles)."
)
TABLET_TOTALS_FORMAT = (
    "Stone Tablets: {symbols} symbol(s) "
    "loaded · {candles:,} YTD candles "
    "total · {shortfall:,} candle shortfall "
    "(gap between YTD expected and what tablets "
    "actually cover)."
)
SHORTFALL_ROW_FORMAT = (
    "  {symbol:<10} {got:>6,} / {expected:>6,} = {pct:5.1f}%  short {short:>6,}"
)
SHORTFALL_MORE_FORMAT = "  ... and {count} more (check console log for full list)"
SHORTFALL_ROW_LIMIT = 10
SKIPPED_SYMBOLS_FORMAT = (
    "Skipped {count} symbol(s) with no tablet (bot not instantiated): {symbols}"
)
AVAILABILITY_HEADER_FORMAT = (
    "Availability flags ({count} "
    "symbol(s) not fully covering the "
    "requested YTD window):"
)
AVAILABILITY_ROW_FORMAT = "  [{status}] {notice}"
AVAILABILITY_MORE_FORMAT = "  ... and {count} more (see console log)"
AVAILABILITY_ROW_LIMIT = 20
WINDOW_STATUS_FULL = "FULL"

SKIPPED_FIX_TEXT = (
    "Fix: run the Fetch YTD build (v3.24.x GUI "
    "button) or CLI `python -m "
    "src.trading.stone_tablets.fetcher build-ytd`."
)

FULL_EVAL_LOG_TEXT = (
    "Evaluation mode: FULL — every candle. Slower; "
    "required for strategy work and the only mode "
    "that detects sim-only trades."
)
ANCHORED_LOG_FORMAT = (
    "Evaluation mode: ANCHORED — "
    "{anchors:,} of {candles:,} candles "
    "({pct:.1f}%) carry a historical trade "
    "or its 100-candle warm-up; the rest are skipped."
)
ANCHORED_NOTE_TEXT = (
    "  Note: bots are not evaluated on skipped "
    "candles, so sim-only divergence is not "
    "reliably measured in this mode. (The "
    "exchange still steps, so a resting limit "
    "CAN fill on a skipped candle.) Tick 'Full "
    "evaluation' for strategy runs."
)
ANCHOR_FALLBACK_TEXT = (
    "Evaluation mode: FULL (fallback) — no "
    "historical trades landed inside the "
    "candle window, so there is nothing to anchor on."
)
ANCHOR_FAILED_FORMAT = "Evaluation mode: FULL (anchor build failed: {error})"
NO_WINDOW_TEXT = (
    "Validation window: no gate data found — replaying "
    "the full YTD span (nothing can be validated "
    "against, so this is a strategy run, not parity)."
)

ETA_HOURS_FORMAT = "  ·  ETA {hours:.1f} h"
ETA_MINUTES_FORMAT = "  ·  ETA {minutes:.0f} min"
ETA_SECONDS_FORMAT = "  ·  ETA {seconds:.0f} s"
ETA_HOUR_THRESHOLD_S = 3600
ETA_MINUTE_THRESHOLD_S = 60
NO_ETA_TEXT = ""

RATE_FORMAT = "  ·  {rate:.1f} candles/s"
PROGRESS_FORMAT = (
    "Replay: {played:,}/{total:,} "
    "candles ({pct:.1f}%)  ·  {trades} sim "
    "trades  ·  {exceptions} exceptions"
)
EXCEPTION_SAMPLE_FORMAT = "{key} ×{count}"
EXCEPTION_SAMPLE_JOIN = "  |  "
EXCEPTION_SAMPLE_LIMIT = 3

SPENDABLE_CURRENCIES = ("USD", "USDC")
MONEY_FORMAT = "${amount:,.2f}"
COUNT_FORMAT = "{count:,}"
PLAIN_COUNT_FORMAT = "{count}"
EXCHANGE_COUNT_TEXT = "1"
STAT_FIELDS = (
    "Spendable",
    "Realised",
    "Locked",
    "Mature",
    "Exch",
    "Scrummed",
    "Folded",
    "Trades",
    "Bots",
    "Errors",
)
NO_STAT_FIELDS: dict = {}

RUNNING_STATE = "RUNNING"
IDLE_STATE = "IDLE"
DEFAULT_MODE = "scrumming"
DEFAULT_EXCHANGE = "coinbase"
DEFAULT_QUOTE_TO_USD = 1.0
CLOSE_INDEX = 4

PROGRESS_TIMER_MS = 500
DRAIN_TIMER_MS = 250
VISUAL_REFRESH_EVERY_N_CANDLES = 15
TIMERS = {"progress": PROGRESS_TIMER_MS, "drain": DRAIN_TIMER_MS}
TIMER_DELAYS_MS = (PROGRESS_TIMER_MS, DRAIN_TIMER_MS)
BUS_TOPICS: tuple[str, ...] = ()

TABLET_TIMEFRAME = "5m"
SPAWN_SINCE_MS = 0
SPAWN_UNTIL_MS = 9_999_999_999_999
MS_PER_DAY = 86_400_000
CANDLES_PER_DAY = 288
CANDLE_MS = 300_000
ANCHOR_WARMUP_CANDLES = 100
SOFT_START_WARMUP_CANDLES = 100
EXPECTED_INDEX_WARMUP = 0

SYNTH_CANDLE_COUNT = 200
SYNTH_BASE_PRICE = 100.0
SYNTH_BASE_TS_MS = 1_700_000_000_000
SYNTH_STEP_MS = 3600_000
SYNTH_WAVE_RATE = 0.05
SYNTH_WAVE_SCALE = 0.03
SYNTH_DRIFT_PER_CANDLE = 0.001
SYNTH_HIGH_MULTIPLIER = 1.005
SYNTH_LOW_MULTIPLIER = 0.995
SYNTH_VOLUME = 100.0

TELEMETRY_GATE = "sim.gate_lights.update"
TELEMETRY_CHART = "sim.price_chart.append"
TELEMETRY_VOTING = "sim.voting_readout.update"
TELEMETRY_STRIP = "sim.stat_strip.feed"
TELEMETRY_SNAPSHOT = "sim.visual_snapshot.collect"
TELEMETRY_PARITY = "sim.parity.compare_trades"

SKIP_NO_CELL = "no cell for symbol"
SKIP_NO_GATE_STATE = "bot has no _last_gate_state"
SKIP_NO_CHART = "chart widget absent"
SKIP_NO_CANDLE = "no candle at cursor"
SKIP_NO_READOUT = "readout widget absent"
SKIP_NO_SUMMARY = "bot has no _last_summary"
SKIP_NO_STRIP = "no strip widget"
SKIP_NO_CONTROLLER = "no controller"
SKIP_NO_LIVE_TRADES = "no live trades loaded (run Fetch YTD)"
SKIP_NO_SIM_TRADES = "sim produced no trades"

SPAWN_PIN = "sim.06.007.postcondition.fleet_spawned"
STATE_PIN = "sim.06.008.invariant.state_persisted"
DRIFT_PIN = "sim.06.009.invariant.spawn_drift"
BOT_TABLE_PIN = "sim.06.010.postcondition.bot_table.rendered"
CHART_PIN = "sim.06.011.postcondition.price_chart.fed"
GATE_PIN = "sim.06.012.postcondition.gate_status.rendered"
YTD_FETCHED_PIN = "ytd.10.001.gauge.trades_fetched"
YTD_COVERAGE_PIN = "ytd.10.002.postcondition.fleet_symbol_coverage"
YTD_PER_SYMBOL_PIN = "ytd.10.003.gauge.per_symbol_counts"
PIN_NAMES = (
    SPAWN_PIN,
    STATE_PIN,
    DRIFT_PIN,
    BOT_TABLE_PIN,
    CHART_PIN,
    GATE_PIN,
    YTD_FETCHED_PIN,
    YTD_COVERAGE_PIN,
    YTD_PER_SYMBOL_PIN,
)
BOT_TABLE_PIN_EVERY_S = 2.0
PINS_WITH_DURATION = (SPAWN_PIN, YTD_COVERAGE_PIN)

SIGNALS = ("fleetLoaded", "replayStarted", "replayStopped")
ACTIONS = {
    "load_button.clicked": "load",
    "fetch_button.clicked": "fetch_ytd",
    "reset_button.clicked": "reset",
    "start_button.clicked": "start",
    "stop_button.clicked": "stop",
    "progress_timer.timeout": "refresh_progress",
    "drain_timer.timeout": "drain",
}
CONNECTIONS_AT_BUILD = 5

SYMBOL_KEY = "symbol"
TARGET_KEY = "target_balance"
EXCHANGE_KEY = "exchange_id"
TIMESTAMP_KEY = "timestamp"
DEFAULT_SYMBOL = ""
DEFAULT_TARGET = 0.0

LOAD_START = "load.start"
LOAD_FAILED = "load.failed"
LOAD_TABLE = "load.table"
LOAD_SPAWNED = "load.spawned"
LOAD_SPAWN_FAILED = "load.spawn_failed"
LOAD_STATUS = "load.status"
LOAD_EMIT = "load.emit"
FETCH_START = "fetch.start"
FETCH_NO_LOOP = "fetch.no_loop"
FETCH_NO_MANAGER = "fetch.no_manager"
FETCH_SCHEDULED = "fetch.scheduled"
FETCH_SCHEDULE_FAILED = "fetch.schedule_failed"
FETCH_DONE = "fetch.done"
START_START = "start.start"
START_BUSY = "start.busy"
START_NO_FLEET = "start.no_fleet"
START_PARITY = "start.parity"
START_NO_LOOP = "start.no_loop"
START_TABLETS = "start.tablets"
START_NO_TABLETS = "start.no_tablets"
START_EVALUATION = "start.evaluation"
START_SCHEDULED = "start.scheduled"
START_SCHEDULE_FAILED = "start.schedule_failed"
STOP_START = "stop.start"
STOP_REFUSED = "stop.refused"
RESET_START = "reset.start"
RESET_DECLINED = "reset.declined"
RESET_REFUSED = "reset.refused"
RESET_TIMERS = "reset.timers"
RESET_CLEARED = "reset.cleared"
PROGRESS_REFRESH = "progress.refresh"
PROGRESS_COLUMN = "progress.column"
PROGRESS_COLUMN_FAILED = "progress.column_failed"
PROGRESS_FINISHED = "progress.finished"
DRAIN_START = "drain.start"
DRAIN_EMPTY = "drain.empty"
DRAIN_SYMBOL = "drain.symbol"
DRAIN_MARKERS = "drain.markers"
HISTORY_RECEIVED = "history.received"
HISTORY_REFUSED = "history.refused"

ModelCall = list

CALL_NAMES = (
    LOAD_START,
    LOAD_FAILED,
    LOAD_TABLE,
    LOAD_SPAWNED,
    LOAD_SPAWN_FAILED,
    LOAD_STATUS,
    LOAD_EMIT,
    FETCH_START,
    FETCH_NO_LOOP,
    FETCH_NO_MANAGER,
    FETCH_SCHEDULED,
    FETCH_SCHEDULE_FAILED,
    FETCH_DONE,
    START_START,
    START_BUSY,
    START_NO_FLEET,
    START_PARITY,
    START_NO_LOOP,
    START_TABLETS,
    START_NO_TABLETS,
    START_EVALUATION,
    START_SCHEDULED,
    START_SCHEDULE_FAILED,
    STOP_START,
    STOP_REFUSED,
    RESET_START,
    RESET_DECLINED,
    RESET_REFUSED,
    RESET_TIMERS,
    RESET_CLEARED,
    PROGRESS_REFRESH,
    PROGRESS_COLUMN,
    PROGRESS_COLUMN_FAILED,
    PROGRESS_FINISHED,
    DRAIN_START,
    DRAIN_EMPTY,
    DRAIN_SYMBOL,
    DRAIN_MARKERS,
    HISTORY_RECEIVED,
    HISTORY_REFUSED,
)


def synthesize_candles(
    symbol: Any,
    n_candles: int = SYNTH_CANDLE_COUNT,
    base_price: float = SYNTH_BASE_PRICE,
) -> list:
    """The sine-wave candles one symbol gets when no tablet covers it.

    Row shape is the exchange's own: timestamp, open, high, low, close,
    volume. The seed is the symbol's letters, so the same symbol always
    draws the same wave.
    """
    seed = sum(ord(letter) for letter in symbol) or 1
    rows: list = []
    for index in range(n_candles):
        wave = math.sin((index + seed) * SYNTH_WAVE_RATE) * SYNTH_WAVE_SCALE
        drift = SYNTH_DRIFT_PER_CANDLE * index
        close = base_price * (1.0 + wave + drift)
        open_price = base_price * (
            1.0
            + math.sin((index - 1 + seed) * SYNTH_WAVE_RATE) * SYNTH_WAVE_SCALE
            + SYNTH_DRIFT_PER_CANDLE * (index - 1)
        )
        rows.append(
            [
                SYNTH_BASE_TS_MS + index * SYNTH_STEP_MS,
                open_price,
                max(open_price, close) * SYNTH_HIGH_MULTIPLIER,
                min(open_price, close) * SYNTH_LOW_MULTIPLIER,
                close,
                SYNTH_VOLUME,
            ]
        )
    return rows


def asset_of(symbol: Any) -> str:
    """The base asset a pair names, in capitals, or the pair itself."""
    text = str(symbol)
    return text.split("/", 1)[0].upper() if "/" in text else text


def config_symbol(config: dict) -> str:
    """The symbol one stored config names, empty when it names none."""
    return str(config.get(SYMBOL_KEY, DEFAULT_SYMBOL) or DEFAULT_SYMBOL)


def config_exchange(config: dict) -> str:
    """The venue one stored config names, Coinbase when it names none."""
    return str(config.get(EXCHANGE_KEY, DEFAULT_EXCHANGE) or DEFAULT_EXCHANGE)


def config_target(config: dict) -> float:
    """The dollar target one stored config carries."""
    return float(config.get(TARGET_KEY, DEFAULT_TARGET) or DEFAULT_TARGET)


def fleet_row(config: dict) -> list:
    """The three cells one stored config fills a table row with."""
    return [
        config_symbol(config),
        TARGET_FORMAT.format(target=config_target(config)),
        ZERO_TRADES_TEXT,
    ]


def summarize(configs: list) -> dict:
    """How many bots, how many symbols and how much target the fleet holds."""
    by_symbol: dict = {}
    total = 0.0
    for config in configs:
        symbol = config_symbol(config)
        by_symbol[symbol] = by_symbol.get(symbol, 0) + 1
        try:
            total += config_target(config)
        except (TypeError, ValueError):
            continue
    return {
        "bot_count": len(configs),
        "symbol_count": len(by_symbol),
        "total_target_usd": total,
        "by_symbol": by_symbol,
    }


def loaded_text(summary: dict, spawned: int) -> str:
    """The status line one finished Load writes."""
    head = LOADED_FORMAT.format(
        bot_count=summary["bot_count"],
        symbol_count=summary["symbol_count"],
        total_target_usd=summary["total_target_usd"],
    )
    if spawned:
        return head + SPAWNED_SUFFIX_FORMAT.format(spawned=spawned)
    return head + NO_SPAWN_SUFFIX


def failure_text(template: str, exc: BaseException) -> str:
    """One refusal line, naming the error's type and its message."""
    return template.format(error=type(exc).__name__, message=exc)


def status_error_text(message: Any) -> str:
    """The status line a failure writes, never empty.

    An empty reason reads on screen as "the button did nothing", so a
    blank message is replaced rather than shown.
    """
    text = str(message or "").strip()
    return text or UNSPECIFIED_FAILURE_TEXT


def by_symbol_counts(trades: list) -> dict:
    """How many trades each symbol carries, symbols with no name dropped."""
    counts: dict = {}
    for trade in trades:
        symbol = str(trade.get(SYMBOL_KEY, ""))
        if symbol:
            counts[symbol] = counts.get(symbol, 0) + 1
    return counts


def history_text(trades: list) -> str:
    """The status line a History refresh writes."""
    if not trades:
        return HISTORY_EMPTY_TEXT
    return HISTORY_LOADED_FORMAT.format(
        count=len(trades), symbols=len(by_symbol_counts(trades))
    )


def fetch_done_text(trades: list) -> str:
    """The status line a finished Fetch YTD writes."""
    if not trades:
        return FETCH_EMPTY_TEXT
    return FETCH_DONE_FORMAT.format(
        count=len(trades), symbols=len(by_symbol_counts(trades))
    )


def parity_state_text(trades: list) -> str:
    """Whether this run can be compared with live, said before it starts."""
    if trades:
        return PARITY_ACTIVE_FORMAT.format(count=len(trades))
    return PARITY_SKIPPED_TEXT


def trade_timestamps(trades: list) -> list:
    """Every readable trade time above zero, in the order they arrived."""
    found: list = []
    for trade in trades or []:
        try:
            stamp = float(trade.get(TIMESTAMP_KEY, 0) or 0)
        except (TypeError, ValueError):
            continue
        if stamp > 0:
            found.append(stamp)
    return found


def eta_text(seconds: float) -> str:
    """How long the replay has left, in hours, minutes or seconds."""
    if seconds >= ETA_HOUR_THRESHOLD_S:
        return ETA_HOURS_FORMAT.format(hours=seconds / 3600)
    if seconds >= ETA_MINUTE_THRESHOLD_S:
        return ETA_MINUTES_FORMAT.format(minutes=seconds / 60)
    return ETA_SECONDS_FORMAT.format(seconds=seconds)


def rate_and_eta(progress: Any, now_s: float) -> list:
    """The candles-per-second and the time left, both as text.

    Returns the rate as a number and the time left as the text that
    follows it, so a run that has played nothing carries neither.
    """
    rate = 0.0
    tail = NO_ETA_TEXT
    try:
        elapsed = now_s - float(getattr(progress, "started_at_wall", 0.0) or 0.0)
        played = progress.candles_played
        if elapsed > 0 and played > 0:
            rate = played / elapsed
            left = max(0, progress.total_candles - played)
            if rate > 0 and left > 0:
                tail = eta_text(left / rate)
    except (TypeError, ValueError, ZeroDivisionError):
        return [0.0, NO_ETA_TEXT]
    return [rate, tail]


def exception_tail(samples: dict) -> str:
    """The three commonest tick failures, or nothing when there are none."""
    if not samples:
        return ""
    top = sorted(samples.items(), key=lambda pair: pair[1], reverse=True)[
        :EXCEPTION_SAMPLE_LIMIT
    ]
    return "\n" + EXCEPTION_SAMPLE_JOIN.join(
        EXCEPTION_SAMPLE_FORMAT.format(key=key, count=count) for key, count in top
    )


def progress_text(progress: Any, now_s: float) -> str:
    """The whole progress line: counts, percentage, rate, time left, failures."""
    played = progress.candles_played
    total = progress.total_candles
    rate, tail = rate_and_eta(progress, now_s)
    line = PROGRESS_FORMAT.format(
        played=played,
        total=total,
        pct=(100.0 * played / total if total else 0.0),
        trades=progress.trades_fired,
        exceptions=progress.exceptions,
    )
    if rate:
        line += RATE_FORMAT.format(rate=rate)
    return line + tail + exception_tail(progress.exception_samples)


def run_in_flight(controller: Any) -> bool:
    """True while a replay is live enough that Reset would discard work.

    A controller that was built but never started is not in flight. A
    controller that cannot answer is treated as running, so Reset never
    throws away a run it could not read.
    """
    if controller is None:
        return False
    try:
        task = getattr(controller, "_task", None)
        if task is not None:
            return not task.done()
        progress = controller.progress
        if not float(getattr(progress, "started_at_wall", 0.0) or 0.0):
            return False
        return not bool(getattr(progress, "finished", False))
    except Exception:  # R28-OK: unreadable progress -> assume in flight
        return True


def ytd_window(now_ms: int, ytd_start_ms: int) -> list:
    """How many days the year-to-date window spans, and its candle count."""
    days = (now_ms - ytd_start_ms) / MS_PER_DAY
    return [days, int(days * CANDLES_PER_DAY)]


def shortfall_lines(from_tablet: list, expected: int) -> list:
    """One line per symbol, worst shortfall first, ten at most."""
    ordered = sorted(from_tablet, key=lambda row: row[2], reverse=True)
    lines = [
        SHORTFALL_ROW_FORMAT.format(
            symbol=symbol,
            got=got,
            expected=expected,
            pct=(100.0 * got / expected if expected else 0.0),
            short=short,
        )
        for symbol, got, short in ordered[:SHORTFALL_ROW_LIMIT]
    ]
    if len(ordered) > SHORTFALL_ROW_LIMIT:
        lines.append(
            SHORTFALL_MORE_FORMAT.format(count=len(ordered) - SHORTFALL_ROW_LIMIT)
        )
    return lines


def missing_tablet_text(missing: list) -> str:
    """The line naming which symbols have no tablet, eight at most."""
    return MISSING_TABLET_FORMAT.format(
        count=len(missing), symbols=", ".join(missing[:MISSING_TABLET_LIMIT])
    ) + (MISSING_TABLET_MORE if len(missing) > MISSING_TABLET_LIMIT else "")


def anchored_text(anchors: int, candles: int) -> str:
    """The line saying how much of the tape carries a historical trade."""
    return ANCHORED_LOG_FORMAT.format(
        anchors=anchors, candles=candles, pct=100.0 * anchors / max(candles, 1)
    )


def money(amount: float) -> str:
    """One dollar amount, to the cent, with thousands separated."""
    return MONEY_FORMAT.format(amount=amount)


def stat_fields(bots: list, ledger: Any, exceptions: Any, on_error: Any = None) -> dict:
    """The ten readings the header strip shows, already formatted.

    Spendable comes from the tape's own balances; the rest are summed
    across the sim bots. Returns nothing at all when a reading raises,
    because a partial strip reads as a real number nobody stored.
    """
    try:
        snapshot = ledger.snapshot() if ledger is not None else {}
        balances = snapshot.get("balances") or {}
        spendable = 0.0
        for currency in SPENDABLE_CURRENCIES:
            spendable += float(balances.get(currency, 0.0) or 0.0)
        realised = 0.0
        locked = 0.0
        mature = 0.0
        scrummed = 0.0
        folded = 0.0
        for bot in bots:
            stats = getattr(bot, "stats", None)
            if stats is not None:
                realised += float(getattr(stats, "realised_pnl", 0.0) or 0.0)
                mature += float(getattr(stats, "accumulated_fold", 0.0) or 0.0)
                scrummed += float(getattr(stats, "total_scrummed_usd", 0.0) or 0.0)
                folded += float(getattr(stats, "total_folded_usd", 0.0) or 0.0)
            holdings = float(getattr(bot, "_current_holdings", 0.0) or 0.0)
            price = float(getattr(bot, "_last_price", 0.0) or 0.0)
            locked += holdings * price
        trades = int(snapshot.get("trades", 0) or 0)
        errors = int(exceptions or 0)
        return {
            "Spendable": money(spendable),
            "Realised": money(realised),
            "Locked": money(locked),
            "Mature": money(mature),
            "Exch": EXCHANGE_COUNT_TEXT,
            "Scrummed": money(scrummed),
            "Folded": money(folded),
            "Trades": COUNT_FORMAT.format(count=trades),
            "Bots": PLAIN_COUNT_FORMAT.format(count=len(bots)),
            "Errors": COUNT_FORMAT.format(count=errors),
        }
    except Exception as exc:  # R28-OK: a partial strip is worse than empty
        if on_error is not None:
            on_error(exc)
        return dict(NO_STAT_FIELDS)


def bot_status(bot: Any, price: float, running: bool) -> Optional[dict]:
    """One sim bot as the row the Trading Tab's bot table already draws.

    Returns nothing for a bot carrying no config, which is the row the
    shipped adapter skips.
    """
    config = getattr(bot, "config", None)
    if config is None:
        return None
    holdings = float(getattr(bot, "_current_holdings", 0.0) or 0.0)
    return {
        "bot_id": str(getattr(bot, "bot_id", "")),
        "symbol": str(getattr(config, "symbol", "") or ""),
        "mode": str(
            getattr(getattr(config, "mode", None), "value", "")
            or getattr(config, "mode", "")
            or DEFAULT_MODE
        ),
        "state": RUNNING_STATE if running else IDLE_STATE,
        "exchange": str(getattr(config, "exchange_id", "") or DEFAULT_EXCHANGE),
        "target_balance": float(getattr(config, "target_balance", 0.0) or 0.0),
        "live_target_balance": float(getattr(bot, "_target_balance", 0.0) or 0.0),
        "current_holdings": holdings,
        "quote_to_usd": float(
            getattr(bot, "_quote_to_usd", DEFAULT_QUOTE_TO_USD) or DEFAULT_QUOTE_TO_USD
        ),
        "stats": {"current_price": price, "position_value": holdings * price},
    }


def snapshot_entry(bot: Any, rows: list, has_data: bool) -> dict:
    """One symbol's gate state and its latest bar, as plain values."""
    gate = getattr(bot, "_last_gate_state", None) or {}
    scrum_fixture = gate.get("scrum_fixture") or {}
    fold_fixture = gate.get("fold_fixture") or {}
    entry: dict = {
        "has_gate_state": bool(gate),
        "scrum_armed": bool(gate.get("scrum_armed")),
        "fold_armed": bool(gate.get("fold_armed")),
        "scrum_blockers": list(gate.get("scrum_blockers") or []),
        "fold_blockers": list(gate.get("fold_blockers") or []),
        "landing_strip_side": str(
            scrum_fixture.get("landing_strip_side")
            or fold_fixture.get("landing_strip_side")
            or ""
        ),
        "ts": None,
        "open": None,
        "high": None,
        "low": None,
        "close": None,
        "volume": None,
        "summary": getattr(bot, "_last_summary", None),
        "tape_has_data": bool(has_data),
    }
    if rows:
        bar = rows[-1]
        entry["ts"] = int(bar[0])
        entry["open"] = float(bar[1])
        entry["high"] = float(bar[2])
        entry["low"] = float(bar[3])
        entry["close"] = float(bar[4])
        entry["volume"] = float(bar[5])
    return entry


def gate_accounting(per_symbol: dict) -> int:
    """How many symbols report gate state, which is what a refresh should draw."""
    return sum(1 for entry in per_symbol.values() if entry.get("has_gate_state"))


def chart_accounting(per_symbol: dict) -> dict:
    """What the chart feed drew against what the tape could supply."""
    return {
        "actual": sum(
            1 for entry in per_symbol.values() if entry.get("close") is not None
        ),
        "expected": sum(
            1 for entry in per_symbol.values() if entry.get("tape_has_data")
        ),
        "symbols": len(per_symbol),
        "with_ohlc": sum(
            1 for entry in per_symbol.values() if entry.get("open") is not None
        ),
    }


def voting_payload(summary: Any, symbol: Any) -> list:
    """The reading one bot's indicator vote hands the shared voting panel."""
    timeframe = str(getattr(summary, "timeframe", "") or TABLET_TIMEFRAME)
    return [
        {
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
        },
        symbol,
    ]


class StatsSource:
    """The counters one sim bot keeps, as the strip reads them."""

    def __init__(
        self,
        realised_pnl: Any = 0.0,
        accumulated_fold: Any = 0.0,
        total_scrummed_usd: Any = 0.0,
        total_folded_usd: Any = 0.0,
    ) -> None:
        self.realised_pnl = realised_pnl
        self.accumulated_fold = accumulated_fold
        self.total_scrummed_usd = total_scrummed_usd
        self.total_folded_usd = total_folded_usd


class BotConfigSource:
    """The config one sim bot carries, as the bot table reads it."""

    def __init__(
        self,
        symbol: Any = "",
        mode: Any = DEFAULT_MODE,
        exchange_id: Any = DEFAULT_EXCHANGE,
        target_balance: Any = 0.0,
    ) -> None:
        self.symbol = symbol
        self.mode = mode
        self.exchange_id = exchange_id
        self.target_balance = target_balance


class BotSource:
    """One spawned sim bot, taken from plain data."""

    def __init__(
        self,
        bot_id: Any = "",
        config: Any = None,
        holdings: Any = 0.0,
        last_price: Any = 0.0,
        target_balance: Any = 0.0,
        quote_to_usd: Any = DEFAULT_QUOTE_TO_USD,
        stats: Any = None,
        gate_state: Any = None,
        summary: Any = None,
    ) -> None:
        self.bot_id = bot_id
        self.config = config
        self._current_holdings = holdings
        self._last_price = last_price
        self._target_balance = target_balance
        self._quote_to_usd = quote_to_usd
        self.stats = stats
        self._last_gate_state = gate_state
        self._last_summary = summary


class ProgressSource:
    """The controller's own record of how far the replay has run."""

    def __init__(
        self,
        candles_played: Any = 0,
        total_candles: Any = 0,
        trades_fired: Any = 0,
        exceptions: Any = 0,
        exception_samples: Any = None,
        per_symbol_trade_count: Any = None,
        started_at_wall: Any = 0.0,
        finished: Any = False,
    ) -> None:
        self.candles_played = candles_played
        self.total_candles = total_candles
        self.trades_fired = trades_fired
        self.exceptions = exceptions
        self.exception_samples = exception_samples or {}
        self.per_symbol_trade_count = per_symbol_trade_count or {}
        self.started_at_wall = started_at_wall
        self.finished = finished
        self.anchored = False


class TaskSource:
    """The scheduled run the controller keeps a handle on."""

    def __init__(self, done: bool = True) -> None:
        self._done = done

    def done(self) -> bool:
        return self._done


class TapeSource:
    """The candle tape the controller plays, and the trades it recorded."""

    def __init__(
        self,
        rows_by_symbol: Any = None,
        balances: Any = None,
        trade_count: Any = 0,
        my_trades: Any = None,
        snapshot_raises: Optional[BaseException] = None,
        history_raises: Optional[BaseException] = None,
    ) -> None:
        self.rows_by_symbol = dict(rows_by_symbol or {})
        self.balances = dict(balances or {})
        self.trade_count = trade_count
        self.my_trades = list(my_trades or [])
        self.snapshot_raises = snapshot_raises
        self.history_raises = history_raises

    def has_data(self, symbol: Any) -> bool:
        return bool(self.rows_by_symbol.get(symbol))

    def history(self, symbol: Any, count: int) -> list:
        if self.history_raises is not None:
            raise self.history_raises
        return list(self.rows_by_symbol.get(symbol, []))[-count:]

    def snapshot(self) -> dict:
        if self.snapshot_raises is not None:
            raise self.snapshot_raises
        return {"balances": dict(self.balances), "trades": self.trade_count}

    def fetch_my_trades(self) -> list:
        return list(self.my_trades)


class ControllerSource:
    """The replay controller the panel builds, never started from here."""

    def __init__(
        self,
        bots: Any = None,
        tape: Any = None,
        progress: Any = None,
        markers: Any = None,
        task: Any = None,
        stop_raises: Optional[BaseException] = None,
    ) -> None:
        self._bots = list(bots or [])
        self._tape = tape
        self.tape = tape
        self.progress = progress if progress is not None else ProgressSource()
        self._markers = list(markers or [])
        self._task = task
        self.stop_raises = stop_raises
        self.stopped = 0

    def request_stop(self) -> None:
        if self.stop_raises is not None:
            raise self.stop_raises
        self.stopped += 1

    def drain_markers(self) -> list:
        drained = list(self._markers)
        self._markers = []
        return drained


class FleetLoaderSource:
    """The stored fleet load, as the panel's Load button reads it.

    ``configs`` are the rows a real ``bot_state.json`` read returns. The
    panel never invents a fleet: what is handed here is what Load sees.
    """

    def __init__(
        self,
        configs: Any = None,
        wires: Any = None,
        raises: Optional[BaseException] = None,
    ) -> None:
        self.configs = list(configs or [])
        self.wires = list(wires or [])
        self.raises = raises

    def load(self) -> list:
        if self.raises is not None:
            raise self.raises
        return list(self.configs)

    def smart_wires(self) -> list:
        return list(self.wires)


class TabletRegistrySource:
    """The Stone Tablet registry, as the spawn and the start read it."""

    def __init__(
        self,
        rows_by_asset: Any = None,
        raises: Optional[BaseException] = None,
        window_status: Any = None,
        availability: Any = None,
    ) -> None:
        self.rows_by_asset = dict(rows_by_asset or {})
        self.raises = raises
        self.window_status = dict(window_status or {})
        self.availability = dict(availability or {})
        self.asked: list = []

    def get_candles(
        self,
        asset: Any,
        since_ms: Any,
        until_ms: Any,
        timeframe: Any,
        exchange_id: Any,
    ) -> list:
        self.asked.append([asset, since_ms, until_ms, timeframe, exchange_id])
        if self.raises is not None:
            raise self.raises
        return list(self.rows_by_asset.get(asset, []))

    def check_window_availability(
        self, asset: Any, since_ms: Any, until_ms: Any, exchange_id: Any
    ) -> Any:
        del since_ms, until_ms, exchange_id
        return self.window_status.get(asset, WINDOW_STATUS_FULL)

    def get_asset_availability(self, asset: Any, exchange_id: Any) -> Any:
        del exchange_id
        return self.availability.get(asset)


class AvailabilitySource:
    """What one asset's tablet says about the history the venue holds."""

    def __init__(self, notice: str = "") -> None:
        self.notice = notice

    def listing_notice(self) -> str:
        return self.notice


class AnchorSource:
    """The candle positions carrying a historical trade, as the run reads them."""

    def __init__(self, indices: Any = None) -> None:
        self.indices = list(indices or [])
        self.asked: list = []

    def build(self, trade_timestamps: list, n_candles: int, warmup: int) -> list:
        self.asked.append([len(trade_timestamps), n_candles, warmup])
        return list(self.indices)


class SimStateSink:
    """Where the sim fleet's own state is written, and what it reports back.

    ``parity`` names, per sim bot, how its imported state compares with the
    live entry it was cloned from. ``drift`` names what moved since the
    last Load.
    """

    def __init__(
        self,
        parity: Any = None,
        drift: Any = None,
        raises: Optional[BaseException] = None,
    ) -> None:
        self.parity = dict(parity or {})
        self.drift = dict(
            drift
            or {
                "first_spawn": True,
                "added": [],
                "removed": [],
                "changed": [],
                "unchanged": 0,
            }
        )
        self.raises = raises
        self.saved: list = []

    def save(self, bot_count: int) -> dict:
        if self.raises is not None:
            raise self.raises
        self.saved.append(bot_count)
        return {"bot_count": bot_count, "parity": dict(self.parity)}


class ParitySource:
    """The sim-against-live report, as the parity harness produces it."""

    def __init__(
        self, lines: Any = None, raises: Optional[BaseException] = None
    ) -> None:
        self.lines = list(lines or [])
        self.raises = raises
        self.asked: list = []

    def report(self, live_trades: list, sim_trades: list) -> list:
        self.asked.append([len(live_trades), len(sim_trades)])
        if self.raises is not None:
            raise self.raises
        return list(self.lines)


class ScheduleSink:
    """Where a replay or a fetch is handed, and what it does with it."""

    def __init__(self, raises: Optional[BaseException] = None) -> None:
        self.raises = raises
        self.scheduled: list = []

    def run(self, name: Any, loop: Any) -> int:
        if self.raises is not None:
            raise self.raises
        self.scheduled.append([name, loop])
        return len(self.scheduled)


class TelemetrySink:
    """The advisory counter the drain reports its calls and skips to."""

    def __init__(self) -> None:
        self.calls: list = []
        self.skips: list = []
        self.exceptions: list = []

    def call(self, name: str) -> None:
        self.calls.append(name)

    def skip(self, name: str, reason: str) -> None:
        self.skips.append([name, reason])

    def exception(self, name: str, exc: BaseException) -> None:
        self.exceptions.append([name, type(exc).__name__])


class PinSink:
    """The contract pins the panel emits, kept in the order they fire."""

    def __init__(self) -> None:
        self.rows: list = []

    def emit(
        self,
        name: str,
        actual: Any,
        expected: Any = None,
        context: Any = None,
        every: Any = None,
    ) -> None:
        self.rows.append([name, actual, expected, dict(context or {}), every])


class FleetReplayPanelModel:
    """The Fleet Replay panel's fleet table, status line, progress and timers.

    ``load`` reads the stored fleet and spawns the sim bots. ``start``
    and ``stop`` drive the replay, ``reset`` clears it, and
    ``refresh_progress`` and ``drain`` are what the two timers run. Every
    step is appended to ``calls`` in the order the shipped panel takes it.
    """

    def __init__(
        self,
        loader: Any = None,
        registry: Any = None,
        controller_factory: Any = None,
        schedule: Any = None,
        loop: Any = None,
        loop_wired: bool = True,
        telemetry: Any = None,
        pins: Any = None,
        anchors: Any = None,
        activity_wired: bool = True,
        sim_state: Any = None,
        chart_wired: bool = False,
        readout_wired: bool = False,
        strip_wired: bool = True,
        parity: Any = None,
    ) -> None:
        self.loader = loader
        self.registry = registry
        self.controller_factory = controller_factory
        self.schedule = schedule if schedule is not None else ScheduleSink()
        self.loop = loop
        self.loop_wired = loop_wired
        self.anchors = anchors if anchors is not None else AnchorSource()
        self.activity_wired = activity_wired
        self.sim_state = sim_state if sim_state is not None else SimStateSink()
        self.chart_wired = chart_wired
        self.readout_wired = readout_wired
        self.strip_wired = strip_wired
        self.parity = parity if parity is not None else ParitySource()
        self.telemetry = telemetry if telemetry is not None else TelemetrySink()
        self.pins = pins if pins is not None else PinSink()

        self.accessible_name = ACCESSIBLE_NAME
        self.gate_host_kind = GATE_HOST_PANEL
        self.configs: list = []
        self.smart_wires: list = []
        self.controller = None
        self.ytd_trades: list = []
        self.rows: list = []
        self.status_text = IDLE_STATUS_TEXT
        self.progress_text = IDLE_PROGRESS_TEXT
        self.start_enabled = False
        self.stop_enabled = False
        self.fetch_enabled = False
        self.full_evaluation = FULL_EVAL_DEFAULT
        self.progress_timer_running = False
        self.drain_timer_running = False
        self.activity_lines: list = []
        self.performance_lines: list = []
        self.signals_emitted: list = []
        self.pending_snapshot: Optional[dict] = None
        self.gate_rows_drawn = 0
        self.stat_fields: dict = dict(NO_STAT_FIELDS)
        self.chart_bars: list = []
        self.chart_markers: list = []
        self.voting_rows: list = []
        self.chart_symbols: list = []
        self.chart_cleared = 0
        self.voting_bot_list: list = []
        self.visual_refresh_every: Optional[int] = None
        self.confirm_reset = True
        self.calls: list[ModelCall] = []

    def activity(self, line: str) -> None:
        """Write one line to the Simulator's Activity log.

        A panel with no log callback wired writes to the console
        instead, which reaches no on-screen panel.
        """
        if self.activity_wired:
            self.activity_lines.append(line)

    def performance(self, line: str) -> None:
        """Write one line to the Simulator's Performance log."""
        self.performance_lines.append(line)

    def status_error(self, message: Any) -> None:
        """Show one failure on the status line, never blank."""
        self.status_text = status_error_text(message)

    def set_bot_manager(self, present: bool) -> None:
        """Enable Fetch YTD exactly when a bot manager is wired."""
        self.fetch_enabled = bool(present)

    def on_history_refreshed(self, trades: Any) -> None:
        """Take the History tab's year-to-date trades as the parity reference."""
        try:
            self.ytd_trades = list(trades or [])
        except Exception:  # R28-OK: an unreadable payload leaves the old one
            self.calls.append([HISTORY_REFUSED])
            return
        self.calls.append([HISTORY_RECEIVED, len(self.ytd_trades)])
        self.status_text = history_text(self.ytd_trades)

    def populate_table(self) -> None:
        """Fill one table row per loaded config.

        The table is given its row count first, so a config that
        cannot be read leaves an empty row where its reading would
        have gone rather than shortening the table.
        """
        self.rows = [[EMPTY_CELL] * COLUMN_COUNT for _ in self.configs]
        for index, config in enumerate(self.configs):
            self.rows[index] = fleet_row(config)
        self.calls.append([LOAD_TABLE, len(self.rows)])

    def load(self) -> None:
        """Read the stored fleet, fill the table and spawn the sim bots."""
        self.calls.append([LOAD_START])
        try:
            self.configs = self.loader.load()
            self.smart_wires = self.loader.smart_wires()
        except Exception as exc:  # R28-OK: the loader is the outward edge
            self.calls.append([LOAD_FAILED, type(exc).__name__])
            self.status_text = failure_text(LOAD_FAILED_FORMAT, exc)
            return
        summary = summarize(self.configs)
        self.populate_table()
        spawned = 0
        try:
            spawned = self.spawn()
        except Exception as exc:  # R28-OK: a failed spawn still reports a fleet
            self.calls.append([LOAD_SPAWN_FAILED, type(exc).__name__])
            self.status_error(failure_text(SPAWN_FAILED_FORMAT, exc))
        self.status_text = loaded_text(summary, spawned)
        self.calls.append([LOAD_STATUS, spawned])
        self.start_enabled = len(self.configs) > 0
        self.signals_emitted.append(["fleetLoaded", len(self.configs)])
        self.calls.append([LOAD_EMIT])

    def spawn_candles(self) -> list:
        """The candles Load reads, in the order the stored fleet lists them.

        A tablet that cannot be read counts as a missing one, so a bot
        with no history is named rather than dropped in silence.
        """
        candles: dict = {}
        missing: list = []
        for config in self.configs:
            symbol = config_symbol(config)
            if not symbol or symbol in candles:
                continue
            try:
                rows = self.registry.get_candles(
                    asset=asset_of(symbol),
                    since_ms=SPAWN_SINCE_MS,
                    until_ms=SPAWN_UNTIL_MS,
                    timeframe=TABLET_TIMEFRAME,
                    exchange_id=config_exchange(config),
                )
            except Exception:  # R28-OK: an unreadable tablet is a missing one
                rows = None
            if rows:
                candles[symbol] = list(rows)
            else:
                missing.append(symbol)
        return [candles, missing]

    def exchange_by_symbol(self) -> dict:
        """The venue each symbol trades on, the first config to name it winning."""
        found: dict = {}
        for config in self.configs:
            symbol = config_symbol(config)
            if symbol:
                found.setdefault(symbol, config_exchange(config))
        return found

    def start_candles(self, since_ms: int, until_ms: int) -> list:
        """The candles Start reads, one per symbol, in symbol order.

        Start reads a window rather than the whole tablet, and a symbol
        with nothing in that window is skipped with no candles at all.
        """
        venues = self.exchange_by_symbol()
        candles: dict = {}
        skipped: list = []
        for symbol in sorted(venues):
            rows = self.registry.get_candles(
                asset=asset_of(symbol),
                since_ms=since_ms,
                until_ms=until_ms,
                timeframe=TABLET_TIMEFRAME,
                exchange_id=venues[symbol],
            )
            if rows:
                candles[symbol] = list(rows)
            else:
                skipped.append(symbol)
        return [candles, skipped]

    def spawn(self) -> int:
        """Build the sim bots Load spawns, and report how many exist.

        The controller is built and never started: the bots hold their
        imported state and the tape only moves on Start Replay.
        """
        if not self.configs:
            return 0
        candles, missing = self.spawn_candles()
        if missing:
            self.activity(missing_tablet_text(missing))
        if not candles:
            return 0
        self.controller = self.controller_factory(
            configs=list(self.configs),
            candles_by_symbol=candles,
            smart_wires=list(self.smart_wires),
        )
        spawned = len(list(getattr(self.controller, "_bots", []) or []))
        self.pins.emit(
            SPAWN_PIN,
            actual=spawned,
            expected=len(self.configs),
            context={
                "symbols_with_tablet": len(candles),
                "missing_tablets": len(missing),
            },
        )
        self.activity(SPAWNED_LOG_FORMAT.format(count=spawned, symbols=len(candles)))
        self.persist_state(spawned)
        self.calls.append([LOAD_SPAWNED, spawned])
        return spawned

    def persist_state(self, spawned: int) -> None:
        """Write the sim fleet's own state and report its parity with live.

        A sim bot that differs from the live entry it was cloned from is
        named, because a faithful import is what makes the run comparable.
        """
        try:
            state = self.sim_state.save(spawned)
        except Exception as exc:  # R28-OK: a failed write must not hide the fleet
            self.activity(SIM_STATE_FAILED_FORMAT.format(message=exc))
            return
        parity = state["parity"]
        bad = {
            bot_id: reading
            for bot_id, reading in parity.items()
            if reading.get("differing") or reading.get("error")
        }
        self.activity(
            SIM_STATE_SAVED_FORMAT.format(
                count=state["bot_count"],
                green=len(parity) - len(bad),
                total=len(parity),
            )
        )
        for bot_id, reading in list(bad.items())[:MISMATCH_ROW_LIMIT]:
            self.activity(
                PARITY_MISMATCH_FORMAT.format(
                    bot_id=bot_id,
                    reason=reading.get("error") or reading.get("differing"),
                )
            )
        drift = self.sim_state.drift
        if drift.get("first_spawn"):
            self.activity(FIRST_SPAWN_TEXT)
        else:
            self.activity(
                SPAWN_DRIFT_FORMAT.format(
                    added=len(drift["added"]),
                    removed=len(drift["removed"]),
                    changed=len(drift["changed"]),
                    unchanged=drift["unchanged"],
                )
            )
            for bot_id in drift["changed"][:DRIFT_ROW_LIMIT]:
                self.activity(LIVE_SOURCE_MOVED_FORMAT.format(bot_id=bot_id))
        self.pins.emit(
            STATE_PIN,
            actual=len(parity) - len(bad),
            expected=len(parity),
            context={
                "path": SIM_STATE_PATH_NAME,
                "mismatched": sorted(bad)[:PIN_CONTEXT_LIMIT],
            },
        )
        self.pins.emit(
            DRIFT_PIN,
            actual=len(drift["changed"]),
            expected=0,
            context={
                "first_spawn": drift["first_spawn"],
                "added": drift["added"][:PIN_CONTEXT_LIMIT],
                "removed": drift["removed"][:PIN_CONTEXT_LIMIT],
                "changed": drift["changed"][:PIN_CONTEXT_LIMIT],
                "unchanged": drift["unchanged"],
            },
        )

    def fetch_ytd(self) -> None:
        """Hand the year-to-date trade fetch to the application's loop."""
        self.calls.append([FETCH_START])
        if not self.loop_wired:
            self.calls.append([FETCH_NO_LOOP])
            self.status_text = FETCH_NO_LOOP_TEXT
            return
        if self.loop is None:
            self.calls.append([FETCH_NO_LOOP])
            self.status_text = FETCH_LOOP_GONE_TEXT
            return
        if not self.fetch_enabled:
            self.calls.append([FETCH_NO_MANAGER])
            self.status_text = FETCH_NO_MANAGER_TEXT
            return
        self.fetch_enabled = False
        self.status_text = FETCH_RUNNING_TEXT
        try:
            self.schedule.run("fetch", self.loop)
        except Exception as exc:  # R28-OK: the loop is the outward edge
            self.calls.append([FETCH_SCHEDULE_FAILED, type(exc).__name__])
            self.status_text = FETCH_SCHEDULE_FAILED_FORMAT.format(message=exc)
            self.fetch_enabled = True
            return
        self.calls.append([FETCH_SCHEDULED])

    def fetch_arrived(self, trades: Any, since_ts: float = 0.0) -> None:
        """Take the fetched trades and pin what the fleet is covered for.

        A fleet symbol with no year-to-date trade has no live reference,
        so nothing can be checked against it.
        """
        self.ytd_trades = list(trades or [])
        counts = by_symbol_counts(self.ytd_trades)
        fleet = {config_symbol(one) for one in self.configs if config_symbol(one)}
        self.pins.emit(
            YTD_FETCHED_PIN,
            actual=len(self.ytd_trades),
            context={"since_ts": since_ts, "symbols": len(counts)},
        )
        self.pins.emit(
            YTD_COVERAGE_PIN,
            actual=sorted(set(counts) & fleet),
            expected=sorted(fleet),
            context={"uncovered": sorted(fleet - set(counts))},
        )
        self.pins.emit(YTD_PER_SYMBOL_PIN, actual=dict(sorted(counts.items())))

    def fetch_done(self, trades: Any) -> None:
        """Report what the finished fetch returned."""
        self.ytd_trades = list(trades or [])
        self.status_text = fetch_done_text(self.ytd_trades)
        self.fetch_enabled = True
        self.calls.append([FETCH_DONE, len(self.ytd_trades)])

    def note_parity_state(self) -> None:
        """Say whether this run can be compared with live, before it starts."""
        self.status_text = parity_state_text(self.ytd_trades)
        self.calls.append([START_PARITY, bool(self.ytd_trades)])

    def tablet_report(self, from_tablet: list, skipped: list, window: list) -> None:
        """Write the tablet coverage table to the Activity log."""
        days, expected = window
        self.activity(YTD_WINDOW_FORMAT.format(days=days, expected=expected))
        self.activity(
            TABLET_TOTALS_FORMAT.format(
                symbols=len(from_tablet),
                candles=sum(got for _, got, _ in from_tablet),
                shortfall=sum(short for _, _, short in from_tablet),
            )
        )
        for line in shortfall_lines(from_tablet, expected):
            self.activity(line)
        if skipped:
            self.activity(
                SKIPPED_SYMBOLS_FORMAT.format(
                    count=len(skipped), symbols=", ".join(skipped)
                )
            )
            self.activity(SKIPPED_FIX_TEXT)

    def availability_report(self, from_tablet: list) -> None:
        """Name every symbol whose tablet does not cover the whole window.

        Stays silent when every tablet is full, which is the usual case.
        """
        venues = self.exchange_by_symbol()
        notices: list = []
        for symbol, _got, _short in from_tablet:
            asset = asset_of(symbol)
            venue = venues.get(symbol, DEFAULT_EXCHANGE)
            status = self.registry.check_window_availability(
                asset=asset,
                since_ms=SPAWN_SINCE_MS,
                until_ms=SPAWN_UNTIL_MS,
                exchange_id=venue,
            )
            if status == WINDOW_STATUS_FULL:
                continue
            info = self.registry.get_asset_availability(asset=asset, exchange_id=venue)
            if info is None:
                continue
            notices.append(
                AVAILABILITY_ROW_FORMAT.format(
                    status=status, notice=info.listing_notice()
                )
            )
        if not notices:
            return
        self.activity(AVAILABILITY_HEADER_FORMAT.format(count=len(notices)))
        for line in notices[:AVAILABILITY_ROW_LIMIT]:
            self.activity(line)
        if len(notices) > AVAILABILITY_ROW_LIMIT:
            self.activity(
                AVAILABILITY_MORE_FORMAT.format(
                    count=len(notices) - AVAILABILITY_ROW_LIMIT
                )
            )

    def evaluation_report(self, candle_count: int) -> None:
        """Say which candles this run evaluates, and set the anchored flag."""
        if self.full_evaluation:
            self.activity(FULL_EVAL_LOG_TEXT)
            self.calls.append([START_EVALUATION, True])
            return
        found = self.anchors.build(
            trade_timestamps(self.ytd_trades),
            n_candles=candle_count,
            warmup=ANCHOR_WARMUP_CANDLES,
        )
        if found:
            self.activity(anchored_text(len(found), candle_count))
            self.activity(ANCHORED_NOTE_TEXT)
        else:
            self.activity(ANCHOR_FALLBACK_TEXT)
            self.controller.progress.anchored = False
        self.calls.append([START_EVALUATION, False])

    def prime_visuals(self, symbols: list) -> None:
        """Give the chart and the voting panel the fleet's symbols."""
        if self.chart_wired:
            self.chart_cleared += 1
            self.chart_symbols = list(symbols)
        if self.readout_wired:
            self.voting_bot_list = [
                {"bot_id": one, "symbol": one, "mode": DEFAULT_MODE} for one in symbols
            ]
        self.visual_refresh_every = VISUAL_REFRESH_EVERY_N_CANDLES

    def start(self, now_ms: int = 0, ytd_start_ms: int = 0) -> None:
        """Refuse or schedule a replay of the loaded fleet.

        Nothing here plays a candle: the run is handed to the
        application's loop, and the two timers begin polling it.
        """
        self.calls.append([START_START])
        if self.controller is not None and run_in_flight(self.controller):
            self.calls.append([START_BUSY])
            self.status_error(START_BUSY_TEXT)
            return
        if not self.configs:
            self.calls.append([START_NO_FLEET])
            self.status_error(START_NO_FLEET_TEXT)
            return
        self.note_parity_state()
        if not self.loop_wired:
            self.calls.append([START_NO_LOOP])
            self.status_text = START_NO_LOOP_TEXT
            return
        if self.loop is None:
            self.calls.append([START_NO_LOOP])
            self.status_text = START_LOOP_GONE_TEXT
            return
        candles, skipped = self.start_candles(ytd_start_ms, now_ms)
        days, expected = ytd_window(now_ms, ytd_start_ms)
        from_tablet = [
            [symbol, len(rows), max(0, expected - len(rows))]
            for symbol, rows in sorted(candles.items())
        ]
        self.tablet_report(from_tablet, skipped, [days, expected])
        self.availability_report(from_tablet)
        self.calls.append([START_TABLETS, len(from_tablet)])
        if not candles:
            self.calls.append([START_NO_TABLETS])
            self.status_text = START_NO_TABLETS_TEXT
            self.activity(START_NO_TABLETS_LOG)
            return
        self.controller = self.controller_factory(
            configs=list(self.configs),
            candles_by_symbol=candles,
            smart_wires=list(self.smart_wires),
        )
        self.activity(NO_WINDOW_TEXT)
        self.controller.progress.anchored = not self.full_evaluation
        self.prime_visuals(sorted(candles))
        self.evaluation_report(max((len(rows) for rows in candles.values()), default=0))
        try:
            self.schedule.run("replay", self.loop)
        except Exception as exc:  # R28-OK: the loop is the outward edge
            self.calls.append([START_SCHEDULE_FAILED, type(exc).__name__])
            self.status_text = START_SCHEDULE_FAILED_FORMAT.format(message=exc)
            return
        self.start_enabled = False
        self.stop_enabled = True
        self.progress_text = STARTING_PROGRESS_TEXT
        self.signals_emitted.append(["replayStarted", None])
        self.progress_timer_running = True
        self.drain_timer_running = True
        self.calls.append([START_SCHEDULED])

    def stop(self) -> None:
        """Ask the replay to stop, and say so when it refuses."""
        self.calls.append([STOP_START])
        if self.controller is not None:
            try:
                self.controller.request_stop()
            except Exception as exc:  # R28-OK: a swallowed refusal reads as a stop
                self.calls.append([STOP_REFUSED, type(exc).__name__])
                self.status_error(failure_text(STOP_REFUSED_FORMAT, exc))
        self.stop_enabled = False

    def reset(self) -> None:
        """Stop any run, clear the fleet and put the panel back to idle.

        The timers are stopped before the controller is dropped: a timer
        that self-stops on a missing controller never reaches that branch.
        """
        self.calls.append([RESET_START])
        if run_in_flight(self.controller) and not self.confirm_reset:
            self.calls.append([RESET_DECLINED])
            return
        stop_failed = False
        if self.controller is not None:
            try:
                self.controller.request_stop()
            except Exception as exc:  # R28-OK: Reset must report a failed stop
                stop_failed = True
                self.calls.append([RESET_REFUSED, type(exc).__name__])
                self.status_error(failure_text(RESET_REFUSED_FORMAT, exc))
        self.progress_timer_running = False
        self.drain_timer_running = False
        self.calls.append([RESET_TIMERS])
        self.controller = None
        self.configs = []
        self.rows = []
        self.start_enabled = False
        self.stop_enabled = False
        if not stop_failed:
            self.status_text = CLEARED_STATUS_TEXT
        self.progress_text = IDLE_PROGRESS_TEXT
        self.calls.append([RESET_CLEARED])

    def refresh_progress(self, now_s: float = 0.0, refill_raises_at: int = -1) -> None:
        """Redraw the progress line and the Sim Trades column.

        ``refill_raises_at`` is the row index at which the column refill
        refuses, so a half-written column can be driven.
        """
        if self.controller is None:
            return
        progress = self.controller.progress
        self.progress_text = progress_text(progress, now_s)
        self.calls.append([PROGRESS_REFRESH, self.progress_text])
        counts = getattr(progress, "per_symbol_trade_count", {}) or {}
        try:
            for index, row in enumerate(self.rows):
                if index == refill_raises_at:
                    raise RuntimeError("table refill refused")
                if row[SYMBOL_COLUMN] is EMPTY_CELL:
                    continue
                count = int(counts.get(row[SYMBOL_COLUMN], 0))
                row[TRADES_COLUMN] = TRADE_COUNT_FORMAT.format(count=count)
            self.calls.append([PROGRESS_COLUMN, len(self.rows)])
        except Exception as exc:  # R28-OK: a paint failure must not stop the run
            self.calls.append([PROGRESS_COLUMN_FAILED, type(exc).__name__])
        if progress.finished:
            self.progress_timer_running = False
            self.drain()
            self.drain_timer_running = False
            self.start_enabled = True
            self.stop_enabled = False
            self.run_parity_comparison()
            self.signals_emitted.append(["replayStopped", None])
            self.calls.append([PROGRESS_FINISHED])

    def collect_snapshot(self) -> dict:
        """Read the sim's state into plain values, off the drawing thread."""
        controller = self.controller
        tape = getattr(controller, "_tape", None)
        bots = list(getattr(controller, "_bots", []) or [])
        per_symbol: dict = {}
        for bot in bots:
            symbol = getattr(getattr(bot, "config", None), "symbol", "") or ""
            if not symbol:
                continue
            has_data = bool(tape.has_data(symbol)) if tape is not None else False
            try:
                rows = tape.history(symbol, 1) if tape is not None else []
            except Exception:  # R28-OK: the tape may be idle
                rows = []
            per_symbol[symbol] = snapshot_entry(bot, rows, has_data)
        return {
            "per_symbol": per_symbol,
            "trade_markers": (
                controller.drain_markers() if controller is not None else []
            ),
            "stat_fields": stat_fields(
                bots,
                tape,
                getattr(controller.progress, "exceptions", 0),
                on_error=self.strip_failed,
            ),
        }

    def strip_failed(self, exc: BaseException) -> None:
        """Record a strip reading that raised rather than showing a zero."""
        self.telemetry.exception(TELEMETRY_STRIP, exc)

    def visual_refresh_tick(self) -> None:
        """Store the newest snapshot, dropping any frame not yet drawn."""
        if self.controller is None:
            return
        try:
            self.pending_snapshot = self.collect_snapshot()
        except Exception as exc:  # R28-OK: a dropped frame must not stop the run
            self.telemetry.exception(TELEMETRY_SNAPSHOT, exc)

    def drain(
        self, chart: bool = True, readout: bool = True, cells: Any = None
    ) -> None:
        """Draw the newest snapshot, at the drawing timer's own cadence."""
        self.calls.append([DRAIN_START])
        snapshot = self.pending_snapshot
        self.pending_snapshot = None
        if not snapshot:
            self.calls.append([DRAIN_EMPTY])
            return
        fields = snapshot.get("stat_fields") or {}
        if fields and not self.strip_wired:
            self.telemetry.skip(TELEMETRY_STRIP, SKIP_NO_STRIP)
        elif fields:
            self.stat_fields = dict(fields)
            self.telemetry.call(TELEMETRY_STRIP)
        per_symbol = snapshot.get("per_symbol") or {}
        expected_gates = gate_accounting(per_symbol)
        drawn = 0
        for symbol, entry in per_symbol.items():
            if cells is not None and symbol not in cells:
                self.telemetry.skip(TELEMETRY_GATE, SKIP_NO_CELL)
            elif not entry.get("has_gate_state"):
                self.telemetry.skip(TELEMETRY_GATE, SKIP_NO_GATE_STATE)
            else:
                drawn += 1
                self.telemetry.call(TELEMETRY_GATE)
            if not chart:
                self.telemetry.skip(TELEMETRY_CHART, SKIP_NO_CHART)
            elif entry.get("close") is None:
                self.telemetry.skip(TELEMETRY_CHART, SKIP_NO_CANDLE)
            else:
                self.chart_bars.append(
                    [
                        symbol,
                        entry["close"],
                        entry["volume"] or 0.0,
                        entry.get("ts"),
                        entry.get("open"),
                        entry.get("high"),
                        entry.get("low"),
                    ]
                )
                self.telemetry.call(TELEMETRY_CHART)
            if not readout:
                self.telemetry.skip(TELEMETRY_VOTING, SKIP_NO_READOUT)
            elif entry.get("summary") is None:
                self.telemetry.skip(TELEMETRY_VOTING, SKIP_NO_SUMMARY)
            else:
                self.voting_rows.append(voting_payload(entry["summary"], symbol))
                self.telemetry.call(TELEMETRY_VOTING)
            self.calls.append([DRAIN_SYMBOL, symbol])
        self.gate_rows_drawn = drawn
        counted = chart_accounting(per_symbol)
        self.pins.emit(
            CHART_PIN,
            actual=counted["actual"],
            expected=counted["expected"],
            context={
                "symbols": counted["symbols"],
                "with_ohlc": counted["with_ohlc"],
            },
        )
        self.pins.emit(
            GATE_PIN,
            actual=drawn,
            expected=expected_gates,
            context={"host": self.gate_host_kind},
        )
        if chart:
            self.chart_markers.extend(snapshot.get("trade_markers") or [])
        self.calls.append([DRAIN_MARKERS, len(snapshot.get("trade_markers") or [])])

    def run_parity_comparison(self) -> None:
        """Compare the sim's trades with live's, once the replay has finished."""
        if self.controller is None:
            self.telemetry.skip(TELEMETRY_PARITY, SKIP_NO_CONTROLLER)
            return
        tape = getattr(self.controller, "tape", None)
        sim_trades = list(tape.fetch_my_trades()) if tape is not None else []
        if not self.ytd_trades:
            self.telemetry.skip(TELEMETRY_PARITY, SKIP_NO_LIVE_TRADES)
            self.performance(PARITY_NO_LIVE_TEXT)
            return
        if not sim_trades:
            self.telemetry.skip(TELEMETRY_PARITY, SKIP_NO_SIM_TRADES)
            self.performance(
                PARITY_NO_SIM_FORMAT.format(live_count=len(self.ytd_trades))
            )
            return
        try:
            lines = self.parity.report(self.ytd_trades, sim_trades)
        except Exception as exc:  # R28-OK: a failed report must not stop a run
            self.telemetry.exception(TELEMETRY_PARITY, exc)
            self.performance(failure_text(PARITY_FAILED_FORMAT, exc))
            return
        self.telemetry.call(TELEMETRY_PARITY)
        for line in lines:
            self.performance(line)

    def bot_statuses(self) -> list:
        """The fleet as the rows the Trading Tab's bot table already draws."""
        controller = self.controller
        bots = list(getattr(controller, "_bots", []) or [])
        tape = getattr(controller, "_tape", None)
        found: list = []
        for bot in bots:
            symbol = str(getattr(getattr(bot, "config", None), "symbol", "") or "")
            price = 0.0
            if tape is not None:
                try:
                    rows = tape.history(symbol, 1)
                    if rows:
                        price = float(rows[-1][CLOSE_INDEX])
                except Exception:  # R28-OK: the tape may be idle
                    price = 0.0
            row = bot_status(bot, price, bool(bots))
            if row is not None:
                found.append(row)
        return found

    def loaded_configs(self) -> list:
        """A copy of the fleet the panel currently holds."""
        return list(self.configs)


def build_view_model(
    model: FleetReplayPanelModel,
    steps: Any = None,
) -> dict:
    """Every value the Fleet Replay panel draws, as plain data."""
    return {
        "accessible_name": model.accessible_name,
        "gate_host_kind": model.gate_host_kind,
        "outer": {"margin_px": OUTER_MARGIN_PX, "spacing_px": OUTER_SPACING_PX},
        "header": {
            "style_sheet": HEADER_STYLE,
            "title": TITLE_TEXT,
            "title_style": TITLE_STYLE,
            "subtitle": SUBTITLE_TEXT,
            "subtitle_style": SUBTITLE_STYLE,
            "subtitle_word_wrap": SUBTITLE_WORD_WRAP,
        },
        "buttons": {
            "load": {"text": LOAD_BUTTON_TEXT, "tooltip": LOAD_BUTTON_TOOLTIP},
            "fetch": {
                "text": FETCH_BUTTON_TEXT,
                "tooltip": FETCH_BUTTON_TOOLTIP,
                "enabled": model.fetch_enabled,
            },
            "reset": {"text": RESET_BUTTON_TEXT, "tooltip": RESET_BUTTON_TOOLTIP},
            "start": {
                "text": START_BUTTON_TEXT,
                "tooltip": START_BUTTON_TOOLTIP,
                "enabled": model.start_enabled,
            },
            "stop": {
                "text": STOP_BUTTON_TEXT,
                "tooltip": STOP_BUTTON_TOOLTIP,
                "enabled": model.stop_enabled,
            },
        },
        "full_evaluation": {
            "text": FULL_EVAL_TEXT,
            "tooltip": FULL_EVAL_TOOLTIP,
            "checked": model.full_evaluation,
        },
        "status": {"text": model.status_text, "style_sheet": STATUS_STYLE},
        "fleet_table": {
            "title": FLEET_GROUP_TITLE,
            "tooltip": TABLE_TOOLTIP,
            "columns": list(COLUMNS),
            "column_count": COLUMN_COUNT,
            "row_count": len(model.rows),
            "rows": [list(row) for row in model.rows],
            "alternating_row_colors": ALTERNATING_ROW_COLORS,
            "edit_triggers": EDIT_TRIGGERS,
            "header_resize_mode": HEADER_RESIZE_MODE,
            "stretch_last_section": STRETCH_LAST_SECTION,
            "table_stretch": TABLE_STRETCH,
        },
        "progress": {
            "text": model.progress_text,
            "style_sheet": PROGRESS_STYLE,
            "word_wrap": PROGRESS_WORD_WRAP,
        },
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "timers_running": {
            "progress": model.progress_timer_running,
            "drain": model.drain_timer_running,
        },
        "visual_refresh_every_n_candles": VISUAL_REFRESH_EVERY_N_CANDLES,
        "bus_topics": list(BUS_TOPICS),
        "signals": list(SIGNALS),
        "signals_emitted": [list(one) for one in model.signals_emitted],
        "actions": dict(ACTIONS),
        "connections_at_build": CONNECTIONS_AT_BUILD,
        "columns_index": {
            "symbol": SYMBOL_COLUMN,
            "target": TARGET_COLUMN,
            "trades": TRADES_COLUMN,
        },
        "stat_field_names": list(STAT_FIELDS),
        "stat_fields": dict(model.stat_fields),
        "gate_rows_drawn": model.gate_rows_drawn,
        "chart_symbols": list(model.chart_symbols),
        "chart_cleared": model.chart_cleared,
        "voting_bot_list": [dict(one) for one in model.voting_bot_list],
        "visual_refresh_every": model.visual_refresh_every,
        "chart_bars": [list(one) for one in model.chart_bars],
        "chart_markers": [list(one) for one in model.chart_markers],
        "voting_rows": [list(one) for one in model.voting_rows],
        "bot_statuses": model.bot_statuses(),
        "configs": model.loaded_configs(),
        "ytd_trade_count": len(model.ytd_trades),
        "activity_lines": list(model.activity_lines),
        "performance_lines": list(model.performance_lines),
        "telemetry": {
            "calls": list(model.telemetry.calls),
            "skips": [list(one) for one in model.telemetry.skips],
            "exceptions": [list(one) for one in model.telemetry.exceptions],
        },
        "pins": [
            [name, actual, expected, context, every]
            for name, actual, expected, context, every in model.pins.rows
        ],
        "pin_names": list(PIN_NAMES),
        "pins_with_duration": list(PINS_WITH_DURATION),
        "texts": {
            "idle_status": IDLE_STATUS_TEXT,
            "cleared_status": CLEARED_STATUS_TEXT,
            "idle_progress": IDLE_PROGRESS_TEXT,
            "starting_progress": STARTING_PROGRESS_TEXT,
            "history_empty": HISTORY_EMPTY_TEXT,
            "fetch_no_loop": FETCH_NO_LOOP_TEXT,
            "fetch_loop_gone": FETCH_LOOP_GONE_TEXT,
            "fetch_no_manager": FETCH_NO_MANAGER_TEXT,
            "fetch_running": FETCH_RUNNING_TEXT,
            "fetch_empty": FETCH_EMPTY_TEXT,
            "start_busy": START_BUSY_TEXT,
            "start_no_fleet": START_NO_FLEET_TEXT,
            "start_no_loop": START_NO_LOOP_TEXT,
            "start_loop_gone": START_LOOP_GONE_TEXT,
            "start_no_tablets": START_NO_TABLETS_TEXT,
            "start_no_tablets_log": START_NO_TABLETS_LOG,
            "unspecified_failure": UNSPECIFIED_FAILURE_TEXT,
            "parity_skipped": PARITY_SKIPPED_TEXT,
            "parity_no_live": PARITY_NO_LIVE_TEXT,
            "reset_confirm_title": RESET_CONFIRM_TITLE,
            "reset_confirm": RESET_CONFIRM_TEXT,
            "full_eval_log": FULL_EVAL_LOG_TEXT,
            "anchored_note": ANCHORED_NOTE_TEXT,
            "anchor_fallback": ANCHOR_FALLBACK_TEXT,
            "no_window": NO_WINDOW_TEXT,
            "skipped_fix": SKIPPED_FIX_TEXT,
            "missing_tablet_more": MISSING_TABLET_MORE,
            "no_eta": NO_ETA_TEXT,
            "zero_trades": ZERO_TRADES_TEXT,
            "exchange_count": EXCHANGE_COUNT_TEXT,
            "running_state": RUNNING_STATE,
            "idle_state": IDLE_STATE,
            "no_spawn_suffix": NO_SPAWN_SUFFIX,
            "first_spawn": FIRST_SPAWN_TEXT,
            "sim_state_path": SIM_STATE_PATH_NAME,
            "exception_sample_join": EXCEPTION_SAMPLE_JOIN,
            "activity_prefix": ACTIVITY_PREFIX,
            "performance_prefix": PERFORMANCE_PREFIX,
        },
        "formats": {
            "target": TARGET_FORMAT,
            "trade_count": TRADE_COUNT_FORMAT,
            "load_failed": LOAD_FAILED_FORMAT,
            "spawn_failed": SPAWN_FAILED_FORMAT,
            "loaded": LOADED_FORMAT,
            "spawned_suffix": SPAWNED_SUFFIX_FORMAT,
            "history_loaded": HISTORY_LOADED_FORMAT,
            "fetch_schedule_failed": FETCH_SCHEDULE_FAILED_FORMAT,
            "fetch_done": FETCH_DONE_FORMAT,
            "start_schedule_failed": START_SCHEDULE_FAILED_FORMAT,
            "stop_refused": STOP_REFUSED_FORMAT,
            "reset_refused": RESET_REFUSED_FORMAT,
            "parity_active": PARITY_ACTIVE_FORMAT,
            "parity_no_sim": PARITY_NO_SIM_FORMAT,
            "parity_failed": PARITY_FAILED_FORMAT,
            "missing_tablet": MISSING_TABLET_FORMAT,
            "spawned_log": SPAWNED_LOG_FORMAT,
            "sim_state_saved": SIM_STATE_SAVED_FORMAT,
            "parity_mismatch": PARITY_MISMATCH_FORMAT,
            "spawn_drift": SPAWN_DRIFT_FORMAT,
            "live_source_moved": LIVE_SOURCE_MOVED_FORMAT,
            "sim_state_failed": SIM_STATE_FAILED_FORMAT,
            "ytd_window": YTD_WINDOW_FORMAT,
            "tablet_totals": TABLET_TOTALS_FORMAT,
            "shortfall_row": SHORTFALL_ROW_FORMAT,
            "shortfall_more": SHORTFALL_MORE_FORMAT,
            "skipped_symbols": SKIPPED_SYMBOLS_FORMAT,
            "availability_header": AVAILABILITY_HEADER_FORMAT,
            "availability_row": AVAILABILITY_ROW_FORMAT,
            "availability_more": AVAILABILITY_MORE_FORMAT,
            "anchored_log": ANCHORED_LOG_FORMAT,
            "anchor_failed": ANCHOR_FAILED_FORMAT,
            "eta_hours": ETA_HOURS_FORMAT,
            "eta_minutes": ETA_MINUTES_FORMAT,
            "eta_seconds": ETA_SECONDS_FORMAT,
            "rate": RATE_FORMAT,
            "progress": PROGRESS_FORMAT,
            "exception_sample": EXCEPTION_SAMPLE_FORMAT,
            "money": MONEY_FORMAT,
            "count": COUNT_FORMAT,
            "plain_count": PLAIN_COUNT_FORMAT,
        },
        "numbers": {
            "eta_hour_threshold_s": ETA_HOUR_THRESHOLD_S,
            "eta_minute_threshold_s": ETA_MINUTE_THRESHOLD_S,
            "exception_sample_limit": EXCEPTION_SAMPLE_LIMIT,
            "shortfall_row_limit": SHORTFALL_ROW_LIMIT,
            "missing_tablet_limit": MISSING_TABLET_LIMIT,
            "availability_row_limit": AVAILABILITY_ROW_LIMIT,
            "mismatch_row_limit": MISMATCH_ROW_LIMIT,
            "drift_row_limit": DRIFT_ROW_LIMIT,
            "pin_context_limit": PIN_CONTEXT_LIMIT,
            "ms_per_day": MS_PER_DAY,
            "candles_per_day": CANDLES_PER_DAY,
            "candle_ms": CANDLE_MS,
            "anchor_warmup_candles": ANCHOR_WARMUP_CANDLES,
            "soft_start_warmup_candles": SOFT_START_WARMUP_CANDLES,
            "expected_index_warmup": EXPECTED_INDEX_WARMUP,
            "spawn_since_ms": SPAWN_SINCE_MS,
            "spawn_until_ms": SPAWN_UNTIL_MS,
            "close_index": CLOSE_INDEX,
            "default_quote_to_usd": DEFAULT_QUOTE_TO_USD,
            "default_target": DEFAULT_TARGET,
            "bot_table_pin_every_s": BOT_TABLE_PIN_EVERY_S,
            "synth_candle_count": SYNTH_CANDLE_COUNT,
            "synth_base_price": SYNTH_BASE_PRICE,
            "synth_base_ts_ms": SYNTH_BASE_TS_MS,
            "synth_step_ms": SYNTH_STEP_MS,
            "synth_wave_rate": SYNTH_WAVE_RATE,
            "synth_wave_scale": SYNTH_WAVE_SCALE,
            "synth_drift_per_candle": SYNTH_DRIFT_PER_CANDLE,
            "synth_high_multiplier": SYNTH_HIGH_MULTIPLIER,
            "synth_low_multiplier": SYNTH_LOW_MULTIPLIER,
            "synth_volume": SYNTH_VOLUME,
        },
        "keys": {
            "symbol": SYMBOL_KEY,
            "target": TARGET_KEY,
            "exchange": EXCHANGE_KEY,
            "timestamp": TIMESTAMP_KEY,
        },
        "defaults": {
            "symbol": DEFAULT_SYMBOL,
            "mode": DEFAULT_MODE,
            "exchange": DEFAULT_EXCHANGE,
            "full_evaluation": FULL_EVAL_DEFAULT,
            "gate_host_panel": GATE_HOST_PANEL,
            "gate_host_table": GATE_HOST_TABLE,
            "tablet_timeframe": TABLET_TIMEFRAME,
            "window_status_full": WINDOW_STATUS_FULL,
        },
        "spendable_currencies": list(SPENDABLE_CURRENCIES),
        "telemetry_names": {
            "gate": TELEMETRY_GATE,
            "chart": TELEMETRY_CHART,
            "voting": TELEMETRY_VOTING,
            "strip": TELEMETRY_STRIP,
            "snapshot": TELEMETRY_SNAPSHOT,
            "parity": TELEMETRY_PARITY,
        },
        "skip_reasons": {
            "no_cell": SKIP_NO_CELL,
            "no_gate_state": SKIP_NO_GATE_STATE,
            "no_chart": SKIP_NO_CHART,
            "no_candle": SKIP_NO_CANDLE,
            "no_readout": SKIP_NO_READOUT,
            "no_summary": SKIP_NO_SUMMARY,
            "no_strip": SKIP_NO_STRIP,
            "no_controller": SKIP_NO_CONTROLLER,
            "no_live_trades": SKIP_NO_LIVE_TRADES,
            "no_sim_trades": SKIP_NO_SIM_TRADES,
        },
        "call_names": list(CALL_NAMES),
        "calls": [list(call) for call in model.calls],
        "steps": list(steps or []),
    }


def bridge_controller(
    configs: list, candles_by_symbol: dict, smart_wires: list
) -> ControllerSource:
    """The controller a bridge request gets: built, holding no bot, never run."""
    del configs, candles_by_symbol, smart_wires
    return ControllerSource()


PANE_MODEL = FleetReplayPanelModel()


def view_model(params: dict) -> dict:
    """Bridge handler for ``fleet_replay_panel.state``.

    Reads ``reset``, ``fleet``, ``ytd_trades``, ``full_evaluation`` and
    ``steps`` from the request parameters. The panel's last state
    persists between calls because the panel does; ``reset`` is what a
    fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = FleetReplayPanelModel()
    fleet = params.get("fleet")
    if fleet is not None:
        PANE_MODEL.loader = FleetLoaderSource(configs=fleet)
        PANE_MODEL.registry = TabletRegistrySource()
        PANE_MODEL.controller_factory = bridge_controller
    trades = params.get("ytd_trades")
    if trades is not None:
        PANE_MODEL.ytd_trades = list(trades)
    if "full_evaluation" in params:
        PANE_MODEL.full_evaluation = bool(params["full_evaluation"])
    taken: list = []
    for step in params.get("steps") or []:
        name = step[0] if isinstance(step, list) else step
        if name in ("load", "fetch_ytd", "stop", "reset", "start"):
            getattr(PANE_MODEL, name)()
            taken.append(name)
    return build_view_model(PANE_MODEL, taken)
