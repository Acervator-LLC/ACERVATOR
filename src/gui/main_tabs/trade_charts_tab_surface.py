"""trade_charts_tab_surface.py -- the Asset Charts tab, without Qt.

Describes the second main tab: one chart panel, and a selector that chooses
which traded asset it draws. The tab draws nothing itself. It decides which
bots reach the asset list, what the chart is labelled, which overlay lines it
carries, and when it is refetched. The candles, the axes, the tick steps and
the colours belong to ``src/gui/native_chart.py`` and are not described here.

``TradeChartsTabModel`` holds the tab's state. ``update_charts`` rebuilds the
asset list for one pass of bot statuses. ``step`` and ``pick`` change the
asset on screen. ``on_timeframe_changed`` re-arms its fetch.
``fetch_chart_data`` refetches it. ``log_trade`` records a trade for chart
markup. ``push_synthetic_candles`` injects a Nuclear Mode scenario.

``PanelSink`` is a plain stand-in for ``ChartPanel`` and its chart: it
records every call the tab makes and the arguments it makes them with.
``BotSource``, ``ManagerSource`` and ``FetchSource`` stand in for the
ScrummingBot, the bot manager and ``ChartDataFetcher``, so the tab can be
driven over the bridge from values alone. ``SignalRecord`` holds one
emitted signal.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for the
``trade_charts_tab.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.widgets.trade_charts_tab``, so a value changed on one side alone
is reported. The one exception is the timeframe list the per-panel combo
offers: ``ChartPanel`` owns it, so it is imported from
``native_chart_surface`` rather than written twice. Nothing here imports
Qt, and nothing runs at import time.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional

from .native_chart_surface import INDICATOR_DEFAULTS as PANEL_INDICATOR_DEFAULTS
from .native_chart_surface import INDICATOR_TOGGLES as PANEL_INDICATOR_TOGGLES
from .native_chart_surface import INDICATOR_ROW_SPACING_PX as PANEL_TOGGLE_GAP_PX
from .native_chart_surface import LEGEND_INVISIBLE_FIELD as PANEL_LEGEND_INVISIBLE_FIELD
from .native_chart_surface import LEGEND_INVISIBLE_TEXT as PANEL_LEGEND_INVISIBLE
from .native_chart_surface import LEGEND_ON_BOOK_FIELD as PANEL_LEGEND_ON_BOOK_FIELD
from .native_chart_surface import LEGEND_SPACING_PX as PANEL_LEGEND_GAP_PX
from .native_chart_surface import LEGEND_ON_BOOK_TEXT as PANEL_LEGEND_ON_BOOK
from .native_chart_surface import TIMEFRAMES as PANEL_TIMEFRAME_OPTIONS

METHOD = "trade_charts_tab.state"

ACCESSIBLE_NAME = "Trade Charts Tab"

OUTER_MARGINS_PX = (8, 8, 8, 8)
OUTER_SPACING_PX = 8
CONTENT_SPACING_PX = 12
CONTENT_MARGINS_PX = (4, 4, 4, 4)

EXTRACTOR_MODE = "extractor"
WILDCARD = "*"

MODE_KEY = "mode"
BOT_ID_KEY = "bot_id"
SYMBOL_KEY = "symbol"
STATE_KEY = "state"
EXCHANGE_KEY = "exchange"
STATS_KEY = "stats"
PRICE_KEY = "current_price"

DEFAULT_MODE = ""
DEFAULT_BOT_ID = ""
DEFAULT_SYMBOL = ""
DEFAULT_STATE = "idle"
DEFAULT_EXCHANGE_ID = ""
DEFAULT_PRICE = 0

PANEL_KEY = "panel"
LAST_FETCH_KEY = "last_fetch"
EXCHANGE_ID_KEY = "exchange_id"
SYNTHETIC_KEY = "synthetic"
VOTE_KEY = "vote"
TIMEFRAMES_KEY = "timeframes"
DEFAULT_VOTE = ""

PANEL_TIMEFRAME = "1h"
PANEL_MINIMUM_HEIGHT_PX = 300
PANEL_MAXIMUM_HEIGHT_PX: Optional[int] = None
COMBO_TIMEFRAME = "1h"

NUCLEAR_TIMEFRAME = "1m"
NUCLEAR_MINIMUM_HEIGHT_PX = 260
NUCLEAR_MAXIMUM_HEIGHT_PX = 340
NUCLEAR_EXCHANGE_ID = "NUCLEAR"

STRETCH_SLOTS = 1

PRICE_LABEL_FORMAT = "{symbol}  •  ${price:.8f}  •  {state}"
NUCLEAR_LABEL_FORMAT = "{symbol}  •  ${price:.4f}  •  ⚡{scenario}"
AWAITING_FORMAT = "{symbol}: awaiting candles"
FLOOR_SMALL_FORMAT = "${price:.4f}"
FLOOR_LARGE_FORMAT = "${price:.2f}"
FLOOR_FORMAT_SWITCH = 1
EMPTY_SOURCE = ""
ERROR_TEXT_LIMIT = 60
BOT_ID_LOG_LENGTH = 8
FOLLOW_LOG_FORMAT = "Asset Charts: panel for bot %s follows %s -> %s"

FETCH_THROTTLE_S = 30
FETCH_LIMIT = 100
STALE_AFTER_S = 90.0
AGE_DECIMALS = 3
NEVER_FETCHED = 0
MISSING_LAST_FETCH = -1

ANCHOR_ATTRIBUTE = "_anchor_target_balance"
TARGET_ATTRIBUTE = "_target_balance"
CAP_ATTRIBUTE = "cycle_growth_cap_usd"
CONSUMED_ATTRIBUTE = "_fold_cycle_cap_consumed"
HOLDINGS_ATTRIBUTE = "_current_holdings"
QUOTE_RATE_ATTRIBUTE = "_quote_to_usd"
GATE_STATE_ATTRIBUTE = "_last_gate_state"
LOTS_ATTRIBUTE = "_main_lots"
TRANCHES_ATTRIBUTE = "_fold_tranches"
BB_ATTRIBUTE = "_last_bb"
STATS_ATTRIBUTE = "stats"
AVG_ENTRY_ATTRIBUTE = "avg_entry_exchange"
CONFIG_ATTRIBUTE = "config"
VISIBILITY_ATTRIBUTE = "visibility"
DEFAULT_VISIBILITY = "orderbook"

# The BBProximityResult fields the landing strip band reads.
BB_STRIP_FLAG = "landing_strip"
BB_STRIP_SIDE = "landing_strip_side"
BB_STRIP_CANDLES = "landing_strip_candles"
BB_UPPER = "upper"
BB_LOWER = "lower"
BB_TOLERANCE = "tolerance_pct"
STRIP_SIDE_KEY = "side"
STRIP_CANDLES_KEY = "candles"
STRIP_UPPER_KEY = "upper"
STRIP_LOWER_KEY = "lower"
STRIP_TOLERANCE_KEY = "tolerance_pct"
STRIP_TIMEFRAME_KEY = "timeframe"
TIMEFRAME_ATTRIBUTE = "ta_timeframe"

POSITION_PRICE_KEY = "price"
POSITION_SIDE_KEY = "side"
POSITION_VISIBILITY_KEY = "visibility"
POSITION_HELD_KEY = "asset_held"

# A fold tranche's fields and a fill row's keys, as the painter's markers read them.
TRANCHE_REF_KEY = "ref"
TRANCHE_CREATED_KEY = "created_ts"
FILL_TS_KEY = "ts"
FILL_SIDE_KEY = "side"
FILL_PRICE_KEY = "price"
FILL_ROLE_KEY = "role"
FILL_TYPE_KEY = "type"
FILL_DATA_KEY = "data"
SCRUM_ROLE = "SCRUM"
SELL_SIDE = "sell"
BUY_SIDE = "buy"
FILL_MATCH_WINDOW_S = 60
FILL_MATCH_PRICE = 1e-9

DEFAULT_ANCHOR_USD = 0
DEFAULT_CAP_USD = 0.0
DEFAULT_CONSUMED_USD = 0.0
DEFAULT_HOLDINGS = 0
DEFAULT_QUOTE_RATE = 1.0
CYCLE_OPEN_FLOOR_USD = 0.0

FLOOR_PRICE_KEY = "initial_buy_price"
FLOOR_UNITS_KEY = "units"
DEFAULT_FLOOR_PRICE = 0
DEFAULT_FLOOR_UNITS = 0
NO_FLOOR_UNITS = 0.0

SCRUM_ARMED_KEY = "scrum_armed"
FOLD_ARMED_KEY = "fold_armed"
SCRUM_BLOCKERS_KEY = "scrum_blockers"
FOLD_BLOCKERS_KEY = "fold_blockers"

TIMESTAMP_KEY = "timestamp"

CANDLE_TIME_KEY = "time"
CANDLE_OPEN_KEY = "open"
CANDLE_HIGH_KEY = "high"
CANDLE_LOW_KEY = "low"
CANDLE_CLOSE_KEY = "close"
CANDLE_VOLUME_KEY = "volume"
CANDLE_CLOSE_INDEX = 4
DEFAULT_CANDLE_TIME = 0
DEFAULT_CANDLE_VOLUME = 0
NO_LAST_PRICE = 0.0

MOUNTED_SIGNAL = "charts.13.001.invariant.panels_mounted"
SYMBOLS_SIGNAL = "charts.13.002.postcondition.panel_symbols_current"
REARMED_SIGNAL = "charts.13.003.postcondition.timeframe_rearmed"
REFRESHED_SIGNAL = "charts.13.004.postcondition.panel_refreshed"
FRESH_SIGNAL = "charts.13.005.invariant.panels_fresh"

SIGNAL_NAMES = (
    MOUNTED_SIGNAL,
    SYMBOLS_SIGNAL,
    REARMED_SIGNAL,
    REFRESHED_SIGNAL,
    FRESH_SIGNAL,
)
THROTTLED_SIGNALS = (MOUNTED_SIGNAL, SYMBOLS_SIGNAL, FRESH_SIGNAL)
SIGNAL_EVERY_S = 30.0
NO_THROTTLE = 0.0
NO_DURATION: Optional[float] = None
NO_DRIFT = 0
NO_STALE = 0
REARM_EXPECTED = True

OUTCOME_CANDLES = "candles"
OUTCOME_EMPTY = "empty"
OUTCOME_RAISED = "raised"
OUTCOMES = (OUTCOME_CANDLES, OUTCOME_EMPTY, OUTCOME_RAISED)

ACTIONS = {"panel.chart.timeframe_changed": "on_timeframe_changed"}
TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()

UPDATE_START = "update.start"
UPDATE_FILTERED = "update.filtered"
UPDATE_SKIPPED_BLANK = "update.skipped_blank"
UPDATE_SKIPPED_WILDCARD = "update.skipped_wildcard"
UPDATE_PANEL_CREATED = "update.panel_created"
UPDATE_PANEL_KEPT = "update.panel_kept"
UPDATE_SYMBOL_FOLLOWED = "update.symbol_followed"
UPDATE_LABEL_SET = "update.label_set"
UPDATE_LABEL_SKIPPED = "update.label_skipped"
UPDATE_NO_MANAGER = "update.no_manager"
UPDATE_NO_BOT = "update.no_bot"
UPDATE_MARKERS_SET = "update.markers_set"
UPDATE_MARKERS_NONE = "update.markers_none"
UPDATE_MARKERS_FAILED = "update.markers_failed"
UPDATE_TB_DRAWN = "update.tb_drawn"
UPDATE_TB_CLEARED = "update.tb_cleared"
UPDATE_TB_FAILED = "update.tb_failed"
UPDATE_FIRE_ARMED = "update.fire_armed"
UPDATE_FIRE_FAILED = "update.fire_failed"
UPDATE_FLOORS_SET = "update.floors_set"
UPDATE_FLOORS_NONE = "update.floors_none"
UPDATE_FLOORS_FAILED = "update.floors_failed"
UPDATE_STRIP_SET = "update.strip_set"
UPDATE_STRIP_FAILED = "update.strip_failed"
UPDATE_POSITION_SET = "update.position_set"
UPDATE_POSITION_FAILED = "update.position_failed"
UPDATE_CHART_REPAINTED = "update.chart_repainted"
UPDATE_PANEL_DROPPED = "update.panel_dropped"
UPDATE_EMIT_MOUNTED = "update.emit_mounted"
UPDATE_EMIT_SYMBOLS = "update.emit_symbols"
TF_START = "timeframe.start"
TF_REARMED = "timeframe.rearmed"
TF_NOT_REARMED = "timeframe.not_rearmed"
TF_EMIT = "timeframe.emit"
FETCH_START = "fetch.start"
FETCH_THROTTLED = "fetch.throttled"
FETCH_WILDCARD_SKIPPED = "fetch.wildcard_skipped"
FETCH_CANDLES = "fetch.candles"
FETCH_EMPTY = "fetch.empty"
FETCH_RAISED = "fetch.raised"
FETCH_EMIT_REFRESHED = "fetch.emit_refreshed"
FETCH_EMIT_FRESH = "fetch.emit_fresh"
LOG_TRADE = "log_trade"
NUCLEAR_PANEL_CREATED = "nuclear.panel_created"
NUCLEAR_PANEL_KEPT = "nuclear.panel_kept"
NUCLEAR_CANDLES_SET = "nuclear.candles_set"

CALL_NAMES = (
    UPDATE_START,
    UPDATE_FILTERED,
    UPDATE_SKIPPED_BLANK,
    UPDATE_SKIPPED_WILDCARD,
    UPDATE_PANEL_CREATED,
    UPDATE_PANEL_KEPT,
    UPDATE_SYMBOL_FOLLOWED,
    UPDATE_LABEL_SET,
    UPDATE_LABEL_SKIPPED,
    UPDATE_NO_MANAGER,
    UPDATE_NO_BOT,
    UPDATE_MARKERS_SET,
    UPDATE_MARKERS_NONE,
    UPDATE_MARKERS_FAILED,
    UPDATE_TB_DRAWN,
    UPDATE_TB_CLEARED,
    UPDATE_TB_FAILED,
    UPDATE_FIRE_ARMED,
    UPDATE_FIRE_FAILED,
    UPDATE_FLOORS_SET,
    UPDATE_FLOORS_NONE,
    UPDATE_FLOORS_FAILED,
    UPDATE_CHART_REPAINTED,
    UPDATE_PANEL_DROPPED,
    UPDATE_EMIT_MOUNTED,
    UPDATE_EMIT_SYMBOLS,
    TF_START,
    TF_REARMED,
    TF_NOT_REARMED,
    TF_EMIT,
    FETCH_START,
    FETCH_THROTTLED,
    FETCH_WILDCARD_SKIPPED,
    FETCH_CANDLES,
    FETCH_EMPTY,
    FETCH_RAISED,
    FETCH_EMIT_REFRESHED,
    FETCH_EMIT_FRESH,
    LOG_TRADE,
    NUCLEAR_PANEL_CREATED,
    NUCLEAR_PANEL_KEPT,
    NUCLEAR_CANDLES_SET,
)

ModelCall = list


def floor_label(price: Any) -> str:
    """The text one tranche floor line carries: four places under a dollar."""
    if price < FLOOR_FORMAT_SWITCH:
        return FLOOR_SMALL_FORMAT.format(price=price)
    return FLOOR_LARGE_FORMAT.format(price=price)


def price_label(symbol: Any, price: Any, state: Any) -> str:
    """The chart header while a price is known: pair, price, state in capitals."""
    return PRICE_LABEL_FORMAT.format(symbol=symbol, price=price, state=state.upper())


def nuclear_label(symbol: Any, price: Any, scenario: Any) -> str:
    """The chart header a Nuclear Mode scenario writes."""
    return NUCLEAR_LABEL_FORMAT.format(symbol=symbol, price=price, scenario=scenario)


def awaiting_text(symbol: Any) -> str:
    """The error line a panel shows between following a pair and its candles."""
    return AWAITING_FORMAT.format(symbol=symbol)


def tranche_floors(lots: Any) -> list:
    """The dashed floor lines one bot's open lots draw, one per distinct price.

    Lots at one price are folded together and the list comes back in
    price order. A lot priced at or below zero anchors no line. Units
    are read and totalled but reach no line: see the note in the parity
    test on the shipped tab's unused total.
    """
    totals: dict = {}
    for lot in lots:
        price = float(lot.get(FLOOR_PRICE_KEY, DEFAULT_FLOOR_PRICE) or 0)
        if price <= 0:
            continue
        units = float(lot.get(FLOOR_UNITS_KEY, DEFAULT_FLOOR_UNITS) or 0)
        totals[price] = totals.get(price, NO_FLOOR_UNITS) + units
    return [[price, floor_label(price)] for price in sorted(totals)]


def fire_armed_state(gate_state: Any) -> dict:
    """The right-edge glow: whether auto-fire would fire now, and what blocks it."""
    return {
        SCRUM_ARMED_KEY: bool(gate_state.get(SCRUM_ARMED_KEY)),
        FOLD_ARMED_KEY: bool(gate_state.get(FOLD_ARMED_KEY)),
        SCRUM_BLOCKERS_KEY: list(gate_state.get(SCRUM_BLOCKERS_KEY) or []),
        FOLD_BLOCKERS_KEY: list(gate_state.get(FOLD_BLOCKERS_KEY) or []),
    }


def landing_strip(bb: Any, timeframe: Any = "") -> Optional[dict]:
    """The band the bot's ``_last_bb`` names, or None while it names no strip.

    Five keys are the ``BBProximityResult`` fields the painter draws from,
    the side, the candle count, both Bollinger bands and the tolerance, and
    ``timeframe`` is the bot's own, which the candle count is read on.
    """
    if bb is None or not bool(getattr(bb, BB_STRIP_FLAG, False)):
        return None
    return {
        STRIP_SIDE_KEY: str(getattr(bb, BB_STRIP_SIDE, "") or ""),
        STRIP_CANDLES_KEY: int(getattr(bb, BB_STRIP_CANDLES, 0) or 0),
        STRIP_UPPER_KEY: float(getattr(bb, BB_UPPER, 0.0) or 0.0),
        STRIP_LOWER_KEY: float(getattr(bb, BB_LOWER, 0.0) or 0.0),
        STRIP_TOLERANCE_KEY: float(getattr(bb, BB_TOLERANCE, 0.0) or 0.0),
        STRIP_TIMEFRAME_KEY: str(timeframe or ""),
    }


def bot_timeframe(bot: Any) -> str:
    """The ``ta_timeframe`` the bot's config names, empty without one."""
    config = getattr(bot, CONFIG_ATTRIBUTE, None)
    return str(getattr(config, TIMEFRAME_ATTRIBUTE, "") or "")


def position_reading(bot: Any) -> Optional[dict]:
    """The bot's holding as one position: the venue's average entry, the units held and the visibility.

    None while the venue has reported no average entry or the bot holds nothing.
    """
    stats = getattr(bot, STATS_ATTRIBUTE, None)
    price = float(getattr(stats, AVG_ENTRY_ATTRIBUTE, 0.0) or 0.0)
    holdings = float(getattr(bot, HOLDINGS_ATTRIBUTE, DEFAULT_HOLDINGS) or 0)
    if price <= 0 or holdings <= 0:
        return None
    config = getattr(bot, CONFIG_ATTRIBUTE, None)
    return {
        POSITION_PRICE_KEY: price,
        POSITION_SIDE_KEY: BUY_SIDE,
        POSITION_VISIBILITY_KEY: str(
            getattr(config, VISIBILITY_ATTRIBUTE, "") or DEFAULT_VISIBILITY
        ),
        POSITION_HELD_KEY: holdings,
    }


def tranche_scrums(tranches: Any, bot_id: Any, symbol: Any) -> list:
    """One SCRUM fill per standing fold tranche: ``ref`` is the sell price and ``created_ts`` its time."""
    found = []
    for one in tranches or []:
        stamp = float(one.get(TRANCHE_CREATED_KEY, 0) or 0)
        price = float(one.get(TRANCHE_REF_KEY, 0) or 0)
        if stamp <= 0 or price <= 0:
            continue
        found.append(
            {
                BOT_ID_KEY: bot_id,
                SYMBOL_KEY: symbol,
                FILL_TS_KEY: int(stamp),
                FILL_SIDE_KEY: SELL_SIDE,
                FILL_PRICE_KEY: price,
                FILL_ROLE_KEY: SCRUM_ROLE,
            }
        )
    return found


def fill_record(stamp: Any, data: Any, symbol: Any) -> Optional[dict]:
    """A ``trade.filled`` event as the row ``log_trade`` records, or None with no price.

    A nested ``data`` dict is merged over the top-level fields, the side is
    lowered and ``type`` becomes the upper-case role.
    """
    merged = dict(data or {})
    inner = merged.get(FILL_DATA_KEY)
    if isinstance(inner, dict):
        merged.update(inner)
    try:
        price = float(merged.get(FILL_PRICE_KEY, 0) or 0)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    role = merged.get(FILL_TYPE_KEY) or merged.get(FILL_ROLE_KEY) or ""
    return {
        BOT_ID_KEY: str(merged.get(BOT_ID_KEY, "") or ""),
        SYMBOL_KEY: str(symbol or merged.get(SYMBOL_KEY, "") or ""),
        FILL_TS_KEY: int(float(stamp or 0)),
        FILL_SIDE_KEY: str(merged.get(FILL_SIDE_KEY, "") or "").lower(),
        FILL_PRICE_KEY: price,
        FILL_ROLE_KEY: str(role).upper(),
    }


def merged_fills(logged: Any, standing: Any) -> list:
    """``logged`` fills, then each ``standing`` scrum no logged fill already names.

    A logged fill names a standing scrum when the two prices are equal and
    their stamps sit within ``FILL_MATCH_WINDOW_S`` of each other.
    """
    kept = [dict(one) for one in logged]
    for scrum in standing:
        already = any(
            abs(float(one.get(FILL_PRICE_KEY, 0) or 0) - scrum[FILL_PRICE_KEY])
            <= FILL_MATCH_PRICE
            and abs(int(one.get(FILL_TS_KEY, 0) or 0) - scrum[FILL_TS_KEY])
            <= FILL_MATCH_WINDOW_S
            for one in kept
        )
        if not already:
            kept.append(dict(scrum))
    return kept


def bot_readings(bot: Any) -> dict:
    """The six money readings the two overlay lines are projected from."""
    anchor_usd = float(
        getattr(
            bot, ANCHOR_ATTRIBUTE, getattr(bot, TARGET_ATTRIBUTE, DEFAULT_ANCHOR_USD)
        )
        or 0
    )
    return {
        "anchor_usd": anchor_usd,
        "target_usd": float(getattr(bot, TARGET_ATTRIBUTE, anchor_usd) or anchor_usd),
        "cap_usd": float(getattr(bot, CAP_ATTRIBUTE, DEFAULT_CAP_USD) or 0.0),
        "consumed_usd": float(
            getattr(bot, CONSUMED_ATTRIBUTE, DEFAULT_CONSUMED_USD) or 0.0
        ),
        "holdings": float(getattr(bot, HOLDINGS_ATTRIBUTE, DEFAULT_HOLDINGS) or 0),
        "quote_rate": float(
            getattr(bot, QUOTE_RATE_ATTRIBUTE, DEFAULT_QUOTE_RATE) or 1.0
        ),
    }


def target_balance_lines(readings: dict) -> list:
    """The anchor and ceiling prices, or two blanks when no projection exists.

    Both come from USD amounts divided by the units held and the quote
    rate. The ceiling is the cycle-open target plus the whole cycle cap,
    where the cycle-open target is the live target less the cap already
    spent.
    """
    anchor_usd = readings["anchor_usd"]
    holdings = readings["holdings"]
    quote_rate = readings["quote_rate"]
    if not (anchor_usd > 0 and holdings > 0 and quote_rate > 0):
        return [None, None]
    cycle_open_usd = max(
        CYCLE_OPEN_FLOOR_USD, readings["target_usd"] - readings["consumed_usd"]
    )
    return [
        anchor_usd / holdings / quote_rate,
        (cycle_open_usd + readings["cap_usd"]) / holdings / quote_rate,
    ]


def candle_row(candle: Any) -> list:
    """One candle as six numbers, from an ``OHLCVCandle``, a dict or a six-number row."""
    if hasattr(candle, CANDLE_OPEN_KEY):
        return [
            int(getattr(candle, CANDLE_TIME_KEY, DEFAULT_CANDLE_TIME)),
            float(candle.open),
            float(candle.high),
            float(candle.low),
            float(candle.close),
            float(getattr(candle, CANDLE_VOLUME_KEY, DEFAULT_CANDLE_VOLUME)),
        ]
    if not isinstance(candle, dict):
        return list(candle)
    return [
        int(candle.get(CANDLE_TIME_KEY, DEFAULT_CANDLE_TIME)),
        float(candle[CANDLE_OPEN_KEY]),
        float(candle[CANDLE_HIGH_KEY]),
        float(candle[CANDLE_LOW_KEY]),
        float(candle[CANDLE_CLOSE_KEY]),
        float(candle.get(CANDLE_VOLUME_KEY, DEFAULT_CANDLE_VOLUME)),
    ]


class SignalRecord:
    """One emitted signal, as the values the emitter was handed."""

    def __init__(
        self,
        name: str,
        actual: Any,
        expected: Any,
        every: float = NO_THROTTLE,
        duration: Optional[float] = NO_DURATION,
        context: Optional[dict] = None,
    ) -> None:
        self.name = name
        self.actual = actual
        self.expected = expected
        self.every = every
        self.duration = duration
        self.context = dict(context or {})

    def as_values(self) -> dict:
        """This signal as the plain values a reader compares."""
        return {
            "name": self.name,
            "actual": self.actual,
            "expected": self.expected,
            "every": self.every,
            "duration": self.duration,
            "context": dict(self.context),
        }


class PanelSink:
    """One chart panel, as the calls the tab makes on it.

    Holds what the shipped ``ChartPanel`` and its ``CandlestickChart``
    hold after those calls: the symbol, the header text, the candles, the
    error line, the source attribution, the markers, the floor lines, the
    two overlay prices and the glow. ``timeframe`` is the combo reading the
    fetch uses, which ``set_chart_timeframe`` does not move.
    """

    def __init__(self, symbol: Any) -> None:
        self.symbol = symbol
        self.label = symbol
        self.timeframe = COMBO_TIMEFRAME
        self.chart_timeframe = ""
        self.candles: list = []
        self.error_text = ""
        self.source = ""
        self.markers: list = []
        self.floors: list = []
        self.tb_anchor: Optional[float] = None
        self.tb_ceiling: Optional[float] = None
        self.armed: Optional[dict] = None
        self.strip: Optional[dict] = None
        self.position: Optional[dict] = None
        self.minimum_height_px: Optional[int] = None
        self.maximum_height_px: Optional[int] = None
        self.chart_repaints = 0
        self.panel_repaints = 0
        self.parent_cleared = False
        self.deleted = False
        self.timeframe_connected = False
        self.calls: list = []

    def set_chart_timeframe(self, timeframe: Any) -> None:
        """Set the chart's own timeframe. The combo the fetch reads does not move."""
        self.chart_timeframe = timeframe
        self.calls.append(["chart.set_timeframe", timeframe])

    def set_timeframe(self, timeframe: Any) -> bool:
        """Move the combo to ``timeframe`` and report whether it moved.

        A value outside ``PANEL_TIMEFRAME_OPTIONS`` leaves ``timeframe``
        where it was, which is what a non-editable combo does.
        """
        moved = timeframe in PANEL_TIMEFRAME_OPTIONS
        if moved:
            self.timeframe = timeframe
        self.calls.append(["chart.combo_set", timeframe, moved])
        return moved

    def set_minimum_height(self, pixels: Any) -> None:
        """Ask for a floor on this panel's height."""
        self.minimum_height_px = pixels
        self.calls.append(["setMinimumHeight", pixels])

    def set_maximum_height(self, pixels: Any) -> None:
        """Ask for a ceiling on this panel's height."""
        self.maximum_height_px = pixels
        self.calls.append(["setMaximumHeight", pixels])

    def connect_timeframe(self) -> None:
        """Wire this panel's timeframe combo back to the tab."""
        self.timeframe_connected = True
        self.calls.append(["chart.timeframe_changed.connect"])

    def set_symbol_property(self, symbol: Any) -> None:
        """Rename the chart through its public setter, which repaints."""
        self.symbol = symbol
        self.label = symbol
        self.chart_repaints += 1
        self.calls.append(["chart.symbol", symbol])

    def set_label(self, text: Any) -> None:
        """Write the header text straight onto the chart, with no repaint."""
        self.label = text
        self.calls.append(["chart._symbol", text])

    def set_candles(self, candles: Any) -> None:
        """Replace the candles, which clears any error line."""
        self.candles = [list(one) for one in candles]
        self.error_text = ""
        self.chart_repaints += 1
        self.calls.append(["chart.set_candles", len(self.candles)])

    def set_error(self, message: Any) -> None:
        """Show an error line. The candles already drawn stay drawn."""
        self.error_text = message
        self.chart_repaints += 1
        self.calls.append(["chart.set_error", message])

    def set_source(self, source: Any) -> None:
        """Name where the candles came from."""
        self.source = source
        self.chart_repaints += 1
        self.calls.append(["set_source", source])

    def set_markers(self, trades: Any) -> None:
        """Replace the historical scrum and fold markers."""
        self.markers = [dict(one) for one in trades]
        self.chart_repaints += 1
        self.calls.append(["chart.set_trade_history_markers", len(self.markers)])

    def set_floors(self, floors: Any) -> None:
        """Replace the dashed tranche floor lines."""
        self.floors = [list(one) for one in floors]
        self.chart_repaints += 1
        self.calls.append(["chart.set_tranche_floors", len(self.floors)])

    def set_target_balance_lines(self, anchor: Any, ceiling: Any) -> None:
        """Set the anchor and ceiling overlay prices, or clear both."""
        self.tb_anchor = anchor
        self.tb_ceiling = ceiling
        self.chart_repaints += 1
        self.calls.append(["chart.set_target_balance_lines", anchor, ceiling])

    def set_armed(self, state: dict) -> None:
        """Set the right-edge glow that says auto-fire would fire now."""
        self.armed = dict(state)
        self.chart_repaints += 1
        self.calls.append(["chart.set_fire_armed_state", dict(state)])

    def set_landing_strip(self, strip: Optional[dict]) -> None:
        """Set the landing strip band ``landing_strip`` read, or clear it."""
        self.strip = None if strip is None else dict(strip)
        self.chart_repaints += 1
        self.calls.append(["chart.set_landing_strip", self.strip])

    def set_position(self, position: Optional[dict]) -> None:
        """Set the one position marker ``position_reading`` read, or clear it."""
        self.position = None if position is None else dict(position)
        self.chart_repaints += 1
        self.calls.append(["chart.set_positions", self.position])

    def repaint_chart(self) -> None:
        """Repaint the chart."""
        self.chart_repaints += 1
        self.calls.append(["chart.update"])

    def repaint_panel(self) -> None:
        """Repaint the whole panel."""
        self.panel_repaints += 1
        self.calls.append(["update"])

    def drop(self) -> None:
        """Take this panel out of the column and schedule it for deletion."""
        self.parent_cleared = True
        self.deleted = True
        self.calls.append(["dropped"])

    def as_values(self) -> dict:
        """Everything this panel holds, as the plain values a reader compares."""
        return {
            "symbol": self.symbol,
            "label": self.label,
            "timeframe": self.timeframe,
            "chart_timeframe": self.chart_timeframe,
            "candles": [list(one) for one in self.candles],
            "candle_count": len(self.candles),
            "error_text": self.error_text,
            "source": self.source,
            "markers": [dict(one) for one in self.markers],
            "floors": [list(one) for one in self.floors],
            "tb_anchor": self.tb_anchor,
            "tb_ceiling": self.tb_ceiling,
            "armed": None if self.armed is None else dict(self.armed),
            "strip": None if self.strip is None else dict(self.strip),
            "position": None if self.position is None else dict(self.position),
            "minimum_height_px": self.minimum_height_px,
            "maximum_height_px": self.maximum_height_px,
            "chart_repaints": self.chart_repaints,
            "panel_repaints": self.panel_repaints,
            "parent_cleared": self.parent_cleared,
            "deleted": self.deleted,
            "timeframe_connected": self.timeframe_connected,
            "calls": [list(one) for one in self.calls],
        }


class BotSource:
    """The ScrummingBot the tab reads its overlay lines off, from plain data."""

    def __init__(self, **readings: Any) -> None:
        for name, value in readings.items():
            setattr(self, name, value)


class ManagerSource:
    """The bot manager the tab asks for one bot by id."""

    def __init__(self, bots: Optional[dict] = None) -> None:
        self.bots = dict(bots or {})
        self.asked: list = []

    def get_bot(self, bot_id: Any) -> Any:
        """The bot behind one id, or nothing when the manager has dropped it."""
        self.asked.append(bot_id)
        return self.bots.get(bot_id)


class FetchSource:
    """``ChartDataFetcher`` as one answer per call, or a refusal.

    ``answers`` is read in order. Each entry is either a list of candle
    rows with a source name, or an exception to raise. ``asked`` records
    every call, so a pass that skipped a panel is visible.
    """

    def __init__(self, answers: Optional[list] = None) -> None:
        self.answers = list(answers or [])
        self.asked: list = []

    async def fetch(
        self,
        symbol: Any,
        timeframe: Any,
        exchange: Any = None,
        limit: int = FETCH_LIMIT,
    ) -> tuple:
        """One fetch: the next answer, or the next refusal."""
        self.asked.append([symbol, timeframe, exchange, limit])
        if not self.answers:
            return [], EMPTY_SOURCE
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer[0], answer[1]


PREV_TEXT = "◀"
NEXT_TEXT = "▶"
PREV_TOOLTIP = "Show the previous asset."
NEXT_TOOLTIP = "Show the next asset."
TICKER_TOOLTIP = "The asset on screen. Pick another from the list."
POSITION_FORMAT = "{at} of {total}"
EMPTY_TICKER_TEXT = "No asset"
EMPTY_POSITION_TEXT = "0 of 0"

LIST_LIVE = "live"
LIST_ATA = "ata_smp"
LIST_MODES = (LIST_LIVE, LIST_ATA)
LIST_LIVE_TEXT = "Live"
LIST_ATA_TEXT = "ATA-SMP"
LIST_TEXTS = {LIST_LIVE: LIST_LIVE_TEXT, LIST_ATA: LIST_ATA_TEXT}
LIST_TOGGLE_TOOLTIP = (
    "The list the arrows walk: the traded markets, or the markets "
    "ATA-SMP has called."
)
ATA_EMPTY_TICKER_TEXT = "No called market"
ATA_EMPTY_HINT = "A market joins this list when it reaches Ready to Send."
LIST_TOGGLE_WIDTH_PX = 92
LIST_TOGGLE_HEIGHT_PX = 26
ATA_EXCHANGE_ID = ""
NO_TIMEFRAMES: tuple = ()

ARROW_WIDTH_PX = 34
ARROW_HEIGHT_PX = 26
TICKER_MIN_WIDTH_PX = 220
SELECTOR_SPACING_PX = 8

#: The list-toggle row, the selector row, the chart and the toggle row.
LAYOUT_SLOTS = 4
ONE_PANEL = 1
NO_PANEL = 0
FIRST_ASSET = 0
ONE_ASSET = 1

SELECT_LIST_TOGGLED = "select.list_toggled"
UPDATE_ATA_ADDED = "update.ata_added"
UPDATE_ATA_KEPT = "update.ata_kept"
UPDATE_ATA_DROPPED = "update.ata_dropped"
UPDATE_ATA_NO_SOURCE = "update.ata_no_source"
UPDATE_ATA_REFUSED = "update.ata_refused"
SELECT_STEP = "select.step"
SELECT_STEPPED = "select.stepped"
SELECT_NONE = "select.none"
SELECT_PICK = "select.pick"
SELECT_PICKED = "select.picked"
SELECT_REFUSED = "select.refused"
SELECT_UNCHANGED = "select.unchanged"
SELECT_FOLLOWED = "select.followed"
SELECT_ALREADY = "select.already"
UPDATE_ASSET_ADDED = "update.asset_added"
UPDATE_ASSET_KEPT = "update.asset_kept"
UPDATE_ASSET_DROPPED = "update.asset_dropped"
UPDATE_SELECTOR = "update.selector"
FETCH_NO_ASSET = "fetch.no_asset"
NUCLEAR_ASSET_ADDED = "nuclear.asset_added"
NUCLEAR_ASSET_KEPT = "nuclear.asset_kept"

#: The selector's own call names, beside the ones ``CALL_NAMES`` already holds.
SELECTOR_CALL_NAMES = (
    SELECT_STEP,
    SELECT_STEPPED,
    SELECT_NONE,
    SELECT_PICK,
    SELECT_PICKED,
    SELECT_REFUSED,
    SELECT_UNCHANGED,
    SELECT_FOLLOWED,
    SELECT_ALREADY,
    SELECT_LIST_TOGGLED,
    UPDATE_ASSET_ADDED,
    UPDATE_ASSET_KEPT,
    UPDATE_ASSET_DROPPED,
    UPDATE_ATA_ADDED,
    UPDATE_ATA_KEPT,
    UPDATE_ATA_DROPPED,
    UPDATE_ATA_NO_SOURCE,
    UPDATE_ATA_REFUSED,
    UPDATE_SELECTOR,
    FETCH_NO_ASSET,
    NUCLEAR_ASSET_ADDED,
    NUCLEAR_ASSET_KEPT,
)


class TradeChartsTabModel:
    """The Asset Charts tab: which asset the one chart draws, and what it shows.

    ``update_charts`` runs one pass of bot statuses, ``step``, ``pick`` and
    ``toggle_list`` change the asset on screen, and ``fetch_chart_data``
    refetches it.
    """

    def __init__(
        self,
        manager: Any = None,
        fetcher: Any = None,
        clock: Any = None,
        ticks: Optional[list] = None,
    ) -> None:
        self.manager = manager
        self.fetcher = fetcher if fetcher is not None else FetchSource()
        self.clock = clock
        self.ticks = list(ticks or [])
        self.accessible_name = ACCESSIBLE_NAME
        self.panel = PanelSink("")
        self.panel.set_chart_timeframe(PANEL_TIMEFRAME)
        self.panel.set_minimum_height(PANEL_MINIMUM_HEIGHT_PX)
        self.panel.connect_timeframe()
        self.assets: dict = {}
        self.order: list = []
        self.shown = FIRST_ASSET
        self.ata_source: Any = None
        self.ata_assets: dict = {}
        self.ata_order: list = []
        self.ata_shown = FIRST_ASSET
        self.list_mode = LIST_LIVE
        self.followed = ""
        self.dropped: list = []
        self.trade_log: list = []
        self.logs: list = []
        self.signals: list = []
        self.calls: list[ModelCall] = []

    def set_ata_source(self, source: Any) -> None:
        """Take the callable answering the markets ATA-SMP has called.

        ``PushBoard.watched_markets`` is what the running window binds here.
        """
        self.ata_source = source

    def showing_ata(self) -> bool:
        """Whether ``list_mode`` is ``LIST_ATA``."""
        return self.list_mode == LIST_ATA

    def list_text(self) -> str:
        """The list on screen, as the toggle button reads."""
        return LIST_TEXTS[self.list_mode]

    def list_order(self) -> list:
        """The ids of the list the arrows walk."""
        return self.ata_order if self.showing_ata() else self.order

    def list_records(self) -> dict:
        """The records of the list the arrows walk, keyed by id."""
        return self.ata_assets if self.showing_ata() else self.assets

    def list_shown(self) -> int:
        """The index into ``list_order`` the chart draws."""
        return self.ata_shown if self.showing_ata() else self.shown

    def set_list_shown(self, at: int) -> None:
        """Move the shown index of the list the arrows walk."""
        if self.showing_ata():
            self.ata_shown = at
            return
        self.shown = at

    def empty_ticker_text(self) -> str:
        """The one item the ticker offers while the list on screen is empty."""
        return ATA_EMPTY_TICKER_TEXT if self.showing_ata() else EMPTY_TICKER_TEXT

    def toggle_list(self) -> str:
        """Move the arrows to the other list and answer the mode on screen."""
        self.list_mode = LIST_ATA if self.list_mode == LIST_LIVE else LIST_LIVE
        self.calls.append([SELECT_LIST_TOGGLED, self.list_mode, len(self.list_order())])
        self._follow_shown()
        self._label_shown()
        self._feed_shown()
        return self.list_mode

    def _now(self) -> float:
        """The wall clock the fetch stamps the shown asset with."""
        return time.time() if self.clock is None else float(self.clock)

    def _tick(self) -> float:
        """The next reading of the counter the fetch duration is measured on."""
        if self.ticks:
            return float(self.ticks.pop(0))
        return time.monotonic()

    def _emit(self, record: SignalRecord) -> None:
        self.signals.append(record)

    def _mounted_count(self) -> int:
        """How many charts are in the column, which is one whenever it exists."""
        return ONE_PANEL if self.panel is not None else NO_PANEL

    def _layout_slots(self) -> int:
        """The selector row, the chart and the toggle row."""
        return LAYOUT_SLOTS

    def shown_id(self) -> str:
        """The id of the asset on screen, or an empty string for none."""
        order = self.list_order()
        at = self.list_shown()
        if not order or at >= len(order):
            return DEFAULT_BOT_ID
        return order[at]

    def current(self) -> dict:
        """The record of the asset on screen, or an empty one for none."""
        return self.list_records().get(self.shown_id(), {})

    def ticker_items(self) -> list:
        """Every label the ticker list offers, in the order it offers them."""
        order = self.list_order()
        if not order:
            return [self.empty_ticker_text()]
        records = self.list_records()
        return [records[bot_id][SYMBOL_KEY] for bot_id in order]

    def position_text(self) -> str:
        """Which asset is on screen and how many there are."""
        order = self.list_order()
        if not order:
            return EMPTY_POSITION_TEXT
        return POSITION_FORMAT.format(at=self.list_shown() + 1, total=len(order))

    def stepping_enabled(self) -> bool:
        """Whether the arrows can move anywhere."""
        return len(self.list_order()) > ONE_ASSET

    def step(self, by: Any) -> int:
        """Move the shown asset by ``by``, wrapping, and answer the new index."""
        self.calls.append([SELECT_STEP, by])
        order = self.list_order()
        if not order:
            self.calls.append([SELECT_NONE])
            return FIRST_ASSET
        self.set_list_shown((self.list_shown() + int(by)) % len(order))
        self.calls.append([SELECT_STEPPED, self.list_shown(), self.shown_id()])
        self._follow_shown()
        return self.list_shown()

    def pick(self, index: Any) -> int:
        """Draw the asset at ``index`` in the ticker list."""
        self.calls.append([SELECT_PICK, index])
        chosen = int(index)
        if chosen < FIRST_ASSET or chosen >= len(self.list_order()):
            self.calls.append([SELECT_REFUSED, chosen])
            return self.list_shown()
        if chosen == self.list_shown():
            self.calls.append([SELECT_UNCHANGED, chosen])
            return self.list_shown()
        self.set_list_shown(chosen)
        self.calls.append([SELECT_PICKED, self.list_shown(), self.shown_id()])
        self._follow_shown()
        return self.list_shown()

    def _follow_shown(self) -> None:
        """Point the one chart at the shown asset and clear the last one's tape.

        ``followed`` is the plain symbol; the panel's label carries the price
        and the state, so it cannot answer this.
        """
        record = self.current()
        symbol = record.get(SYMBOL_KEY, DEFAULT_SYMBOL)
        if self.followed == symbol:
            self.calls.append([SELECT_ALREADY, symbol])
            return
        self.followed = symbol
        self.panel.set_symbol_property(symbol)
        self.panel.set_candles([])
        self.panel.set_markers([])
        self.panel.set_source(EMPTY_SOURCE)
        if symbol:
            self.panel.set_error(awaiting_text(symbol))
        if record:
            record[LAST_FETCH_KEY] = NEVER_FETCHED
        self.calls.append([SELECT_FOLLOWED, symbol])

    def update_charts(
        self,
        bot_statuses: list,
        manager: Any = None,
        exchange_connectors: Optional[dict] = None,
    ) -> None:
        """Rebuild the asset list for one pass of bot statuses.

        An Extractor bot is filtered out first, and a bot that sent no status
        this pass leaves the list while the shown asset stays with its own bot.
        """
        del exchange_connectors
        if manager is not None:
            self.manager = manager
        self.calls.append([UPDATE_START, len(bot_statuses)])
        kept_statuses = [
            one
            for one in bot_statuses
            if one.get(MODE_KEY, DEFAULT_MODE) != EXTRACTOR_MODE
        ]
        if len(kept_statuses) != len(bot_statuses):
            self.calls.append([UPDATE_FILTERED, len(bot_statuses) - len(kept_statuses)])

        held_id = (
            self.order[self.shown] if self.shown < len(self.order) else DEFAULT_BOT_ID
        )
        seen: list = []
        for status in kept_statuses:
            bot_id = status.get(BOT_ID_KEY, DEFAULT_BOT_ID)
            symbol = status.get(SYMBOL_KEY, DEFAULT_SYMBOL)
            if not bot_id or not symbol:
                self.calls.append([UPDATE_SKIPPED_BLANK, bot_id, symbol])
                continue
            if WILDCARD in symbol:
                self.calls.append([UPDATE_SKIPPED_WILDCARD, bot_id, symbol])
                continue
            seen.append(bot_id)

            if bot_id not in self.assets:
                self.assets[bot_id] = {
                    SYMBOL_KEY: symbol,
                    EXCHANGE_ID_KEY: status.get(EXCHANGE_KEY, DEFAULT_EXCHANGE_ID),
                    LAST_FETCH_KEY: NEVER_FETCHED,
                }
                self.calls.append([UPDATE_ASSET_ADDED, bot_id, symbol])
            else:
                self.calls.append([UPDATE_ASSET_KEPT, bot_id, symbol])

            record = self.assets[bot_id]
            if record[SYMBOL_KEY] != symbol:
                self.logs.append(
                    [
                        FOLLOW_LOG_FORMAT,
                        bot_id[:BOT_ID_LOG_LENGTH],
                        record[SYMBOL_KEY],
                        symbol,
                    ]
                )
                self.calls.append(
                    [UPDATE_SYMBOL_FOLLOWED, bot_id, record[SYMBOL_KEY], symbol]
                )
                record[SYMBOL_KEY] = symbol
                record[LAST_FETCH_KEY] = NEVER_FETCHED
            record[EXCHANGE_ID_KEY] = status.get(EXCHANGE_KEY, DEFAULT_EXCHANGE_ID)
            stats = status.get(STATS_KEY, {})
            record[PRICE_KEY] = stats.get(PRICE_KEY, DEFAULT_PRICE)
            record[STATE_KEY] = status.get(STATE_KEY, DEFAULT_STATE)

        for bot_id in list(self.assets):
            if bot_id not in seen:
                self.assets.pop(bot_id)
                self.dropped.append(bot_id)
                self.calls.append([UPDATE_ASSET_DROPPED, bot_id])

        self.order = seen
        self.shown = next(
            (at for at, one in enumerate(self.order) if one == held_id), FIRST_ASSET
        )
        self._rebuild_ata()
        self.calls.append([UPDATE_SELECTOR, len(self.list_order()), self.list_shown()])
        self._follow_shown()
        self._label_shown()
        self._feed_shown()
        self.panel.repaint_chart()
        self.calls.append([UPDATE_CHART_REPAINTED, self.shown_id()])

        drift = 0
        for status in kept_statuses:
            record = self.assets.get(status.get(BOT_ID_KEY, DEFAULT_BOT_ID))
            if record is not None and record.get(SYMBOL_KEY) != status.get(
                SYMBOL_KEY, DEFAULT_SYMBOL
            ):
                drift += 1

        mounted = self._mounted_count()
        self._emit(
            SignalRecord(
                MOUNTED_SIGNAL,
                actual=mounted,
                expected=ONE_PANEL,
                every=SIGNAL_EVERY_S,
                context={
                    "layout_items": self._layout_slots(),
                    "statuses": len(kept_statuses),
                    "kept": len(seen),
                },
            )
        )
        self.calls.append([UPDATE_EMIT_MOUNTED, mounted, ONE_PANEL])
        self._emit(
            SignalRecord(
                SYMBOLS_SIGNAL,
                actual=drift,
                expected=NO_DRIFT,
                every=SIGNAL_EVERY_S,
                context={
                    "assets": len(self.assets),
                    "statuses": len(kept_statuses),
                    "shown_symbol": self.current().get(SYMBOL_KEY, DEFAULT_SYMBOL),
                },
            )
        )
        self.calls.append([UPDATE_EMIT_SYMBOLS, drift])
        return None

    def _rebuild_ata(self) -> None:
        """Rebuild the ATA-SMP list from ``ata_source``, keyed by symbol.

        No source, or a source that raises, leaves the list empty; no entry
        is written that the source did not answer.
        """
        held_symbol = (
            self.ata_order[self.ata_shown]
            if self.ata_shown < len(self.ata_order)
            else DEFAULT_SYMBOL
        )
        if self.ata_source is None:
            if self.ata_order:
                self.ata_order = []
                self.ata_assets = {}
            self.calls.append([UPDATE_ATA_NO_SOURCE])
            self.ata_shown = FIRST_ASSET
            return
        try:
            watched = list(self.ata_source())
        except Exception as exc:
            self.calls.append([UPDATE_ATA_REFUSED, type(exc).__name__])
            return

        seen: list = []
        for market in watched:
            symbol = str(getattr(market, SYMBOL_KEY, DEFAULT_SYMBOL))
            if not symbol or WILDCARD in symbol:
                continue
            timeframes = list(getattr(market, TIMEFRAMES_KEY, NO_TIMEFRAMES))
            vote = str(getattr(market, VOTE_KEY, DEFAULT_VOTE))
            if symbol in self.ata_assets:
                self.calls.append([UPDATE_ATA_KEPT, symbol, vote])
            else:
                self.ata_assets[symbol] = {
                    SYMBOL_KEY: symbol,
                    EXCHANGE_ID_KEY: ATA_EXCHANGE_ID,
                    LAST_FETCH_KEY: NEVER_FETCHED,
                }
                self.calls.append([UPDATE_ATA_ADDED, symbol, vote])
            record = self.ata_assets[symbol]
            record[VOTE_KEY] = vote
            record[TIMEFRAMES_KEY] = timeframes
            seen.append(symbol)

        for symbol in list(self.ata_assets):
            if symbol not in seen:
                self.ata_assets.pop(symbol)
                self.calls.append([UPDATE_ATA_DROPPED, symbol])

        self.ata_order = seen
        self.ata_shown = next(
            (at for at, one in enumerate(seen) if one == held_symbol), FIRST_ASSET
        )

    def _label_shown(self) -> None:
        """Write the shown asset's price and state into the chart header."""
        record = self.current()
        bot_id = self.shown_id()
        price = record.get(PRICE_KEY, DEFAULT_PRICE)
        if price > 0:
            self.panel.set_label(
                price_label(
                    record.get(SYMBOL_KEY, DEFAULT_SYMBOL),
                    price,
                    record.get(STATE_KEY, DEFAULT_STATE),
                )
            )
            self.calls.append([UPDATE_LABEL_SET, bot_id, self.panel.label])
        else:
            self.calls.append([UPDATE_LABEL_SKIPPED, bot_id])

    def _feed_shown(self) -> None:
        """Put the shown bot's markers, lines, glow and floors on the chart."""
        bot_id = self.shown_id()
        if not self.manager:
            self.calls.append([UPDATE_NO_MANAGER, bot_id])
            return
        bot = self.manager.get_bot(bot_id) if bot_id else None
        if not bot:
            self.calls.append([UPDATE_NO_BOT, bot_id])
            return
        self._feed_overlays(
            bot_id, self.current().get(SYMBOL_KEY, DEFAULT_SYMBOL), bot, self.panel
        )

    def _feed_overlays(self, bot_id: Any, symbol: Any, bot: Any, panel: Any) -> None:
        """Put this bot's markers, overlay lines, glow and floors on the chart.

        Each of the four is guarded on its own, so one that refuses
        leaves the other three drawn.
        """
        try:
            for_this_bot = merged_fills(
                [
                    one
                    for one in self.trade_log
                    if one.get(BOT_ID_KEY) == bot_id and one.get(SYMBOL_KEY) == symbol
                ],
                tranche_scrums(getattr(bot, TRANCHES_ATTRIBUTE, []), bot_id, symbol),
            )
            if for_this_bot:
                panel.set_markers(for_this_bot)
                self.calls.append([UPDATE_MARKERS_SET, bot_id, len(for_this_bot)])
            else:
                self.calls.append([UPDATE_MARKERS_NONE, bot_id])
        except Exception as exc:
            self.calls.append([UPDATE_MARKERS_FAILED, bot_id, type(exc).__name__])

        try:
            panel.set_landing_strip(
                landing_strip(getattr(bot, BB_ATTRIBUTE, None), bot_timeframe(bot))
            )
            self.calls.append([UPDATE_STRIP_SET, bot_id, panel.strip is not None])
        except Exception as exc:
            self.calls.append([UPDATE_STRIP_FAILED, bot_id, type(exc).__name__])

        try:
            panel.set_position(position_reading(bot))
            self.calls.append([UPDATE_POSITION_SET, bot_id, panel.position is not None])
        except Exception as exc:
            self.calls.append([UPDATE_POSITION_FAILED, bot_id, type(exc).__name__])

        try:
            lines = target_balance_lines(bot_readings(bot))
            panel.set_target_balance_lines(lines[0], lines[1])
            if lines[0] is None:
                self.calls.append([UPDATE_TB_CLEARED, bot_id])
            else:
                self.calls.append([UPDATE_TB_DRAWN, bot_id, lines[0], lines[1]])
        except Exception as exc:
            self.calls.append([UPDATE_TB_FAILED, bot_id, type(exc).__name__])

        try:
            armed = fire_armed_state(getattr(bot, GATE_STATE_ATTRIBUTE, None) or {})
            panel.set_armed(armed)
            self.calls.append(
                [
                    UPDATE_FIRE_ARMED,
                    bot_id,
                    armed[SCRUM_ARMED_KEY],
                    armed[FOLD_ARMED_KEY],
                ]
            )
        except Exception as exc:
            self.calls.append([UPDATE_FIRE_FAILED, bot_id, type(exc).__name__])

        try:
            lots = getattr(bot, LOTS_ATTRIBUTE, [])
            if lots:
                floors = tranche_floors(lots)
                panel.set_floors(floors)
                self.calls.append([UPDATE_FLOORS_SET, bot_id, len(floors)])
            else:
                self.calls.append([UPDATE_FLOORS_NONE, bot_id])
        except Exception as exc:
            self.calls.append([UPDATE_FLOORS_FAILED, bot_id, type(exc).__name__])

    def move_timeframe_combo(self, timeframe: Any) -> bool:
        """Move the chart's combo to ``timeframe``, as Qt's own does.

        Qt runs this inside ``ChartPanel`` before the tab hears the signal,
        and the frontend draws that combo.
        """
        if not self.panel.set_timeframe(timeframe):
            return False
        self.panel.set_chart_timeframe(timeframe)
        return True

    def on_timeframe_changed(self, timeframe: Any) -> None:
        """Re-arm the shown asset's fetch after the operator moved the combo."""
        bot_id = self.shown_id()
        self.calls.append([TF_START, bot_id, timeframe])
        record = self.current()
        if record:
            record[LAST_FETCH_KEY] = NEVER_FETCHED
        rearmed = bool(
            record
            and record.get(LAST_FETCH_KEY, MISSING_LAST_FETCH) == NEVER_FETCHED
            and self.panel.timeframe == timeframe
        )
        if rearmed:
            self.calls.append([TF_REARMED, bot_id, timeframe])
        else:
            self.calls.append([TF_NOT_REARMED, bot_id, timeframe])
        self._emit(
            SignalRecord(
                REARMED_SIGNAL,
                actual=rearmed,
                expected=REARM_EXPECTED,
                context={
                    "requested_tf": timeframe,
                    "panel_tf": self.panel.timeframe,
                    "known_bot": bool(record),
                    "assets": len(self.assets),
                },
            )
        )
        self.calls.append([TF_EMIT, rearmed])
        return None

    async def fetch_chart_data(
        self, exchange_connectors: Optional[dict] = None
    ) -> None:
        """Fetch the shown asset, at most once every throttle window.

        Neither error path clears the candles, so the emitted record reads
        the count back off the chart with the source beside it.
        """
        now = self._now()
        self.calls.append([FETCH_START, len(self.assets)])
        record = self.current()
        bot_id = self.shown_id()

        if not record:
            self.calls.append([FETCH_NO_ASSET])
            self._emit_freshness(now, exchange_connectors)
            return None
        if now - record.get(LAST_FETCH_KEY, NEVER_FETCHED) < FETCH_THROTTLE_S:
            self.calls.append([FETCH_THROTTLED, bot_id])
            self._emit_freshness(now, exchange_connectors)
            return None

        symbol = record[SYMBOL_KEY]
        if WILDCARD in symbol:
            self.calls.append([FETCH_WILDCARD_SKIPPED, bot_id, symbol])
            self._emit_freshness(now, exchange_connectors)
            return None

        timeframe = self.panel.timeframe
        exchange = None
        if exchange_connectors:
            exchange = exchange_connectors.get(
                record.get(EXCHANGE_ID_KEY, DEFAULT_EXCHANGE_ID)
            )

        started = self._tick()
        elapsed: Optional[float] = None
        outcome = OUTCOME_RAISED
        returned = 0
        source = EMPTY_SOURCE
        try:
            rows, answered = await self.fetcher.fetch(
                symbol, timeframe, exchange=exchange, limit=FETCH_LIMIT
            )
            elapsed = self._tick() - started
            returned = len(rows or [])
            source = str(answered)
            if rows:
                self.panel.set_candles([candle_row(one) for one in rows])
                self.panel.set_source(answered)
                outcome = OUTCOME_CANDLES
                self.calls.append([FETCH_CANDLES, bot_id, returned, source])
            else:
                self.panel.set_error(answered)
                outcome = OUTCOME_EMPTY
                self.calls.append([FETCH_EMPTY, bot_id, source])
        except Exception as exc:
            if elapsed is None:
                elapsed = self._tick() - started
            self.panel.set_error(str(exc)[:ERROR_TEXT_LIMIT])
            source = type(exc).__name__
            self.calls.append([FETCH_RAISED, bot_id, source])
        record[LAST_FETCH_KEY] = now

        shown = len(self.panel.candles)
        self._emit(
            SignalRecord(
                REFRESHED_SIGNAL,
                actual=shown,
                expected=returned,
                duration=elapsed,
                context={
                    "outcome": outcome,
                    "source": source,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "exchange_id": record.get(EXCHANGE_ID_KEY, DEFAULT_EXCHANGE_ID),
                    "throttle_s": FETCH_THROTTLE_S,
                },
            )
        )
        self.calls.append([FETCH_EMIT_REFRESHED, bot_id, shown, returned, outcome])
        self._emit_freshness(now, exchange_connectors)
        return None

    def _emit_freshness(self, now: float, exchange_connectors: Any) -> None:
        """Report how many assets on both lists have gone past three windows."""
        stale = 0
        never = 0
        oldest = 0.0
        watched = list(self.assets.values()) + list(self.ata_assets.values())
        for record in watched:
            last = float(record.get(LAST_FETCH_KEY, NEVER_FETCHED) or 0)
            if last <= 0:
                never += 1
                stale += 1
                continue
            age = now - last
            oldest = max(oldest, age)
            if age > STALE_AFTER_S:
                stale += 1
        self._emit(
            SignalRecord(
                FRESH_SIGNAL,
                actual=stale,
                expected=NO_STALE,
                every=SIGNAL_EVERY_S,
                context={
                    "assets": len(watched),
                    "live_assets": len(self.assets),
                    "ata_assets": len(self.ata_assets),
                    "never_fetched": never,
                    "oldest_age_s": round(oldest, AGE_DECIMALS),
                    "stale_after_s": STALE_AFTER_S,
                    "throttle_s": FETCH_THROTTLE_S,
                    "connectors": len(exchange_connectors or {}),
                },
            )
        )
        self.calls.append([FETCH_EMIT_FRESH, stale, never])

    def log_trade(self, trade: dict, stamp: Any = None) -> None:
        """Record one trade for chart markup, stamped with the time it arrived."""
        recorded = {
            TIMESTAMP_KEY: datetime.now().isoformat() if stamp is None else stamp,
            **trade,
        }
        self.trade_log.append(recorded)
        self.calls.append(
            [LOG_TRADE, recorded.get(BOT_ID_KEY), recorded.get(SYMBOL_KEY)]
        )
        return None

    def push_synthetic_candles(
        self,
        bot_id: Any,
        symbol: Any,
        candles: list,
        scenario: Any = "",
        last_price: Any = NO_LAST_PRICE,
    ) -> None:
        """Draw one Nuclear Mode scenario's candles on the chart, with no fetch.

        The bot joins the Live list if it is new, and the chart switches to it.
        """
        self.list_mode = LIST_LIVE
        if bot_id not in self.assets:
            self.assets[bot_id] = {
                SYMBOL_KEY: symbol,
                EXCHANGE_ID_KEY: NUCLEAR_EXCHANGE_ID,
                LAST_FETCH_KEY: NEVER_FETCHED,
                SYNTHETIC_KEY: True,
            }
            self.order.append(bot_id)
            self.calls.append([NUCLEAR_ASSET_ADDED, bot_id, symbol])
        else:
            self.calls.append([NUCLEAR_ASSET_KEPT, bot_id, symbol])

        self.assets[bot_id][SYMBOL_KEY] = symbol
        if bot_id not in self.order:
            self.order.append(bot_id)
        self.shown = self.order.index(bot_id)
        self._follow_shown()
        self.panel.set_chart_timeframe(NUCLEAR_TIMEFRAME)

        rows = [candle_row(one) for one in candles]
        self.panel.set_candles(rows)
        label_price = last_price or (
            rows[-1][CANDLE_CLOSE_INDEX] if rows else NO_LAST_PRICE
        )
        self.panel.set_label(nuclear_label(symbol, label_price, scenario))
        self.panel.repaint_panel()
        self.calls.append([NUCLEAR_CANDLES_SET, bot_id, len(rows), self.panel.label])
        return None


def selector_values(model: TradeChartsTabModel) -> dict:
    """The toggle row and the selector row: every value either host draws."""
    return {
        "prev_text": PREV_TEXT,
        "next_text": NEXT_TEXT,
        "prev_tooltip": PREV_TOOLTIP,
        "next_tooltip": NEXT_TOOLTIP,
        "ticker_tooltip": TICKER_TOOLTIP,
        "arrow_width_px": ARROW_WIDTH_PX,
        "arrow_height_px": ARROW_HEIGHT_PX,
        "ticker_min_width_px": TICKER_MIN_WIDTH_PX,
        "spacing_px": SELECTOR_SPACING_PX,
        "items": model.ticker_items(),
        "shown": model.list_shown(),
        "position_text": model.position_text(),
        "stepping_enabled": model.stepping_enabled(),
        "position_format": POSITION_FORMAT,
        "empty_ticker_text": model.empty_ticker_text(),
        "empty_position_text": EMPTY_POSITION_TEXT,
        "list_mode": model.list_mode,
        "list_text": model.list_text(),
        "list_modes": list(LIST_MODES),
        "list_texts": dict(LIST_TEXTS),
        "showing_ata": model.showing_ata(),
        "toggle_tooltip": LIST_TOGGLE_TOOLTIP,
        "toggle_width_px": LIST_TOGGLE_WIDTH_PX,
        "toggle_height_px": LIST_TOGGLE_HEIGHT_PX,
        "live_empty_ticker_text": EMPTY_TICKER_TEXT,
        "ata_empty_ticker_text": ATA_EMPTY_TICKER_TEXT,
        "ata_empty_hint": ATA_EMPTY_HINT,
    }


def list_values(model: TradeChartsTabModel) -> dict:
    """Both lists the one selector walks, whichever is on screen."""
    return {
        LIST_LIVE: {
            "order": list(model.order),
            "count": len(model.assets),
            "shown": model.shown,
        },
        LIST_ATA: {
            "order": list(model.ata_order),
            "count": len(model.ata_assets),
            "shown": model.ata_shown,
            "source_bound": model.ata_source is not None,
            "markets": [
                {
                    "symbol": info[SYMBOL_KEY],
                    "vote": info.get(VOTE_KEY, DEFAULT_VOTE),
                    "timeframes": list(info.get(TIMEFRAMES_KEY, NO_TIMEFRAMES)),
                }
                for info in model.ata_assets.values()
            ],
        },
    }


def build_view_model(
    model: TradeChartsTabModel,
    statuses: Optional[list] = None,
    connectors: Optional[dict] = None,
    timeframe_change: Optional[str] = None,
    fetch_now: bool = False,
    trades: Optional[list] = None,
    synthetic: Optional[list] = None,
    step_by: Optional[int] = None,
    pick_at: Optional[int] = None,
    toggle_list: bool = False,
) -> dict:
    """Return every value the Asset Charts tab holds as one dict.

    Each argument runs one of the tab's entry points, in the order the running
    window calls them.
    """
    import asyncio

    for trade in trades or []:
        model.log_trade(trade[0], trade[1] if len(trade) > 1 else None)
    if statuses is not None:
        model.update_charts(statuses, exchange_connectors=connectors)
    if toggle_list:
        model.toggle_list()
    if step_by is not None:
        model.step(step_by)
    if pick_at is not None:
        model.pick(pick_at)
    if timeframe_change is not None:
        model.move_timeframe_combo(timeframe_change)
        model.on_timeframe_changed(timeframe_change)
    if fetch_now:
        asyncio.run(model.fetch_chart_data(connectors))
    for one in synthetic or []:
        model.push_synthetic_candles(*one)

    return {
        "accessible_name": model.accessible_name,
        "container": {
            "margins_px": list(OUTER_MARGINS_PX),
            "spacing_px": OUTER_SPACING_PX,
        },
        "content": {
            "margins_px": list(CONTENT_MARGINS_PX),
            "spacing_px": CONTENT_SPACING_PX,
            "layout_slots": model._layout_slots(),
        },
        "selector": selector_values(model),
        "asset_order": list(model.list_order()),
        "asset_count": len(model.list_records()),
        "shown_id": model.shown_id(),
        "shown_symbol": model.current().get(SYMBOL_KEY, DEFAULT_SYMBOL),
        "followed": model.followed,
        "panel": model.panel.as_values(),
        "assets": {
            bot_id: {
                "symbol": info[SYMBOL_KEY],
                "exchange_id": info[EXCHANGE_ID_KEY],
                "last_fetch": info[LAST_FETCH_KEY],
                "synthetic": info.get(SYNTHETIC_KEY, False),
            }
            for bot_id, info in model.list_records().items()
        },
        "lists": list_values(model),
        "dropped": list(model.dropped),
        "trade_log": [dict(one) for one in model.trade_log],
        "logs": [list(one) for one in model.logs],
        "signals": [one.as_values() for one in model.signals],
        "signal_names": list(SIGNAL_NAMES),
        "throttled_signals": list(THROTTLED_SIGNALS),
        "panel_defaults": {
            "timeframe": PANEL_TIMEFRAME,
            "combo_timeframe": COMBO_TIMEFRAME,
            "timeframe_options": list(PANEL_TIMEFRAME_OPTIONS),
            "minimum_height_px": PANEL_MINIMUM_HEIGHT_PX,
            "maximum_height_px": PANEL_MAXIMUM_HEIGHT_PX,
        },
        "panel_chrome": {
            "toggles": [
                {
                    "key": key,
                    "label": label,
                    "color": colour,
                    "checked": PANEL_INDICATOR_DEFAULTS[key],
                }
                for key, label, colour in PANEL_INDICATOR_TOGGLES
            ],
            "legend": [PANEL_LEGEND_INVISIBLE, PANEL_LEGEND_ON_BOOK],
            "legend_fields": [
                PANEL_LEGEND_INVISIBLE_FIELD,
                PANEL_LEGEND_ON_BOOK_FIELD,
            ],
            "legend_styles": [],
            "toggle_gap_px": PANEL_TOGGLE_GAP_PX,
            "legend_gap_px": PANEL_LEGEND_GAP_PX,
        },
        "nuclear_defaults": {
            "timeframe": NUCLEAR_TIMEFRAME,
            "minimum_height_px": NUCLEAR_MINIMUM_HEIGHT_PX,
            "maximum_height_px": NUCLEAR_MAXIMUM_HEIGHT_PX,
            "exchange_id": NUCLEAR_EXCHANGE_ID,
        },
        "fetch": {
            "throttle_s": FETCH_THROTTLE_S,
            "limit": FETCH_LIMIT,
            "stale_after_s": STALE_AFTER_S,
            "age_decimals": AGE_DECIMALS,
            "never_fetched": NEVER_FETCHED,
            "missing_last_fetch": MISSING_LAST_FETCH,
            "error_text_limit": ERROR_TEXT_LIMIT,
            "asked": [list(one) for one in getattr(model.fetcher, "asked", [])],
        },
        "filters": {"extractor_mode": EXTRACTOR_MODE, "wildcard": WILDCARD},
        "outcomes": list(OUTCOMES),
        "formats": {
            "price_label": PRICE_LABEL_FORMAT,
            "nuclear_label": NUCLEAR_LABEL_FORMAT,
            "awaiting": AWAITING_FORMAT,
            "floor_small": FLOOR_SMALL_FORMAT,
            "floor_large": FLOOR_LARGE_FORMAT,
            "follow_log": FOLLOW_LOG_FORMAT,
        },
        "floor_format_switch": FLOOR_FORMAT_SWITCH,
        "empty_source": EMPTY_SOURCE,
        "bot_id_log_length": BOT_ID_LOG_LENGTH,
        "candle_close_index": CANDLE_CLOSE_INDEX,
        "keys": {
            "mode": MODE_KEY,
            "bot_id": BOT_ID_KEY,
            "symbol": SYMBOL_KEY,
            "state": STATE_KEY,
            "exchange": EXCHANGE_KEY,
            "stats": STATS_KEY,
            "price": PRICE_KEY,
            "panel": PANEL_KEY,
            "last_fetch": LAST_FETCH_KEY,
            "exchange_id": EXCHANGE_ID_KEY,
            "synthetic": SYNTHETIC_KEY,
            "timestamp": TIMESTAMP_KEY,
            "floor_price": FLOOR_PRICE_KEY,
            "floor_units": FLOOR_UNITS_KEY,
            "scrum_armed": SCRUM_ARMED_KEY,
            "fold_armed": FOLD_ARMED_KEY,
            "scrum_blockers": SCRUM_BLOCKERS_KEY,
            "fold_blockers": FOLD_BLOCKERS_KEY,
            "candle_time": CANDLE_TIME_KEY,
            "candle_open": CANDLE_OPEN_KEY,
            "candle_high": CANDLE_HIGH_KEY,
            "candle_low": CANDLE_LOW_KEY,
            "candle_close": CANDLE_CLOSE_KEY,
            "candle_volume": CANDLE_VOLUME_KEY,
        },
        "attributes": {
            "anchor": ANCHOR_ATTRIBUTE,
            "target": TARGET_ATTRIBUTE,
            "cap": CAP_ATTRIBUTE,
            "consumed": CONSUMED_ATTRIBUTE,
            "holdings": HOLDINGS_ATTRIBUTE,
            "quote_rate": QUOTE_RATE_ATTRIBUTE,
            "gate_state": GATE_STATE_ATTRIBUTE,
            "lots": LOTS_ATTRIBUTE,
        },
        "defaults": {
            "mode": DEFAULT_MODE,
            "bot_id": DEFAULT_BOT_ID,
            "symbol": DEFAULT_SYMBOL,
            "state": DEFAULT_STATE,
            "exchange_id": DEFAULT_EXCHANGE_ID,
            "price": DEFAULT_PRICE,
            "anchor_usd": DEFAULT_ANCHOR_USD,
            "cap_usd": DEFAULT_CAP_USD,
            "consumed_usd": DEFAULT_CONSUMED_USD,
            "holdings": DEFAULT_HOLDINGS,
            "quote_rate": DEFAULT_QUOTE_RATE,
            "cycle_open_floor_usd": CYCLE_OPEN_FLOOR_USD,
            "floor_price": DEFAULT_FLOOR_PRICE,
            "floor_units": DEFAULT_FLOOR_UNITS,
            "no_floor_units": NO_FLOOR_UNITS,
            "candle_time": DEFAULT_CANDLE_TIME,
            "candle_volume": DEFAULT_CANDLE_VOLUME,
            "last_price": NO_LAST_PRICE,
        },
        "signal_settings": {
            "every_s": SIGNAL_EVERY_S,
            "no_throttle": NO_THROTTLE,
            "no_duration": NO_DURATION,
            "no_drift": NO_DRIFT,
            "no_stale": NO_STALE,
            "rearm_expected": REARM_EXPECTED,
        },
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "call_names": list(CALL_NAMES),
        "calls": [list(one) for one in model.calls],
    }


PANE_MODEL = TradeChartsTabModel()


def ata_markets_source() -> list:
    """The markets ATA-SMP has called, off the Market Inspector's ``PushBoard``.

    Answers an empty list while no Market Inspector screen has been built, so
    asking never builds one.
    """
    from . import market_inspector_surface

    board = getattr(market_inspector_surface.PANE_MODEL, "push", None)
    if board is None:
        return []
    return board.watched_markets()


def view_model(params: dict) -> dict:
    """Bridge handler for ``trade_charts_tab.state``.

    Reads ``reset``, ``bots``, ``answers``, ``now``, ``ticks``, ``statuses``,
    ``connectors``, ``timeframe_change``, ``fetch``, ``trades``,
    ``synthetic``, ``step_by``, ``pick_at`` and ``toggle_list`` from the
    request parameters. The tab's panels persist between calls because the
    tab does; ``reset`` is what a fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = TradeChartsTabModel()
    if PANE_MODEL.ata_source is None:
        PANE_MODEL.set_ata_source(ata_markets_source)
    bots = params.get("bots")
    if bots is not None:
        PANE_MODEL.manager = ManagerSource(
            {bot_id: BotSource(**readings) for bot_id, readings in bots.items()}
        )
    answers = params.get("answers")
    if answers is not None:
        PANE_MODEL.fetcher = FetchSource(answers)
    if params.get("now") is not None:
        PANE_MODEL.clock = params["now"]
    if params.get("ticks") is not None:
        PANE_MODEL.ticks = list(params["ticks"])
    return build_view_model(
        PANE_MODEL,
        params.get("statuses"),
        params.get("connectors"),
        params.get("timeframe_change"),
        params.get("fetch", False),
        params.get("trades"),
        params.get("synthetic"),
        params.get("step_by"),
        params.get("pick_at"),
        params.get("toggle_list", False),
    )


def live_view_model(params: dict, live: Any) -> dict:
    """Build the Asset Charts view model from the running fleet.

    ``live.bot_manager.list_bots`` names the bots ``update_charts`` builds a
    panel for, and that same manager answers ``get_bot`` for the overlays.
    ``view_model`` answers while no manager is bound.
    """
    global PANE_MODEL
    manager = getattr(live, "bot_manager", None)
    if manager is None or not hasattr(manager, "list_bots"):
        return view_model(params)
    asked = dict(params or {})
    if asked.pop("reset", False):
        PANE_MODEL = TradeChartsTabModel()
    if asked.get("statuses") is None:
        asked["statuses"] = list(manager.list_bots())
    PANE_MODEL.manager = manager
    return view_model(asked)


def bind_live(live: Any) -> Any:
    """Return a ``trade_charts_tab.state`` handler reading ``live``.

    ``src.core.desktop_bridge.build_registry`` calls this when the running
    program serves the bridge, and the handler defers to ``live_view_model``.
    """

    def handler(params: dict) -> dict:
        return live_view_model(params or {}, live)

    return handler
