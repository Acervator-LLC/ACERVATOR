"""trade_charts_tab_surface.py -- the Asset Charts tab, without Qt.

Describes the second main tab: a scrolling column holding one chart panel
per running bot. The tab draws nothing itself. It decides which bots get a
panel, what each panel is labelled, which overlay lines each panel carries,
when each panel is refetched, and which panels are dropped. The candles,
the axes, the tick steps and the colours belong to
``src/gui/native_chart.py`` and are not described here.

``TradeChartsTabModel`` holds the tab's state. ``update_charts`` creates,
follows, feeds and drops panels for one pass of bot statuses.
``on_timeframe_changed`` re-arms one panel's fetch. ``fetch_chart_data``
runs one fetch pass over every panel. ``log_trade`` records a trade for
chart markup. ``push_synthetic_candles`` injects a Nuclear Mode scenario.

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
is reported. Nothing here imports Qt, and nothing runs at import time.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional

METHOD = "trade_charts_tab.state"

ACCESSIBLE_NAME = "Trade Charts Tab"

OUTER_MARGINS_PX = (8, 8, 8, 8)
OUTER_SPACING_PX = 8
SCROLL_RESIZABLE = True
SCROLL_HORIZONTAL_POLICY = "ScrollBarAlwaysOff"
SCROLL_HORIZONTAL_POLICY_VALUE = 1
CONTENT_SPACING_PX = 12
CONTENT_MARGINS_PX = (4, 4, 4, 4)
CONTENT_STRETCH_ADDED = True

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
    """One Nuclear Mode candle as six numbers, from an object or from a dict."""
    if hasattr(candle, CANDLE_OPEN_KEY):
        return [
            int(getattr(candle, CANDLE_TIME_KEY, DEFAULT_CANDLE_TIME)),
            float(candle.open),
            float(candle.high),
            float(candle.low),
            float(candle.close),
            float(getattr(candle, CANDLE_VOLUME_KEY, DEFAULT_CANDLE_VOLUME)),
        ]
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
    hold after those calls: the header text, the candles, the error line,
    the source attribution, the markers, the floor lines, the two overlay
    prices and the glow. ``timeframe`` is the combo reading the fetch
    uses, which ``set_chart_timeframe`` does not move.
    """

    def __init__(self, symbol: Any) -> None:
        self.built_with = symbol
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
            "built_with": self.built_with,
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


class TradeChartsTabModel:
    """The Asset Charts tab: which bots get a panel, and what each one shows.

    ``update_charts`` runs one pass of bot statuses. ``fetch_chart_data``
    runs one fetch pass. ``on_timeframe_changed`` re-arms one panel.
    Every step is appended to ``calls`` in the order the shipped tab
    makes it, and every emitted signal to ``signals``.
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
        self.panels: dict = {}
        self.order: list = []
        self.dropped: list = []
        self.trade_log: list = []
        self.logs: list = []
        self.signals: list = []
        self.calls: list[ModelCall] = []

    def _now(self) -> float:
        """The wall clock the fetch stamps panels with, or the one supplied."""
        return time.time() if self.clock is None else float(self.clock)

    def _tick(self) -> float:
        """The next reading of the counter the fetch duration is measured on."""
        if self.ticks:
            return float(self.ticks.pop(0))
        return time.monotonic()

    def _emit(self, record: SignalRecord) -> None:
        self.signals.append(record)

    def _mounted_count(self) -> int:
        """How many panels are really in the column."""
        return sum(1 for bot_id in self.order if bot_id in self.panels)

    def _layout_slots(self) -> int:
        """How many slots the column holds: the panels plus the trailing stretch."""
        return self._mounted_count() + STRETCH_SLOTS

    def update_charts(
        self,
        bot_statuses: list,
        manager: Any = None,
        exchange_connectors: Optional[dict] = None,
    ) -> None:
        """Create, follow, feed and drop panels for one pass of bot statuses.

        Extractor bots are filtered out before the loop: their symbol is
        a wildcard the exchange refuses. A panel whose bot changed pair
        follows it, and everything anchored to the old pair is cleared
        with it. A bot that sent no status this pass loses its panel.
        """
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

        seen: set = set()
        for status in kept_statuses:
            bot_id = status.get(BOT_ID_KEY, DEFAULT_BOT_ID)
            symbol = status.get(SYMBOL_KEY, DEFAULT_SYMBOL)
            if not bot_id or not symbol:
                self.calls.append([UPDATE_SKIPPED_BLANK, bot_id, symbol])
                continue
            if WILDCARD in symbol:
                self.calls.append([UPDATE_SKIPPED_WILDCARD, bot_id, symbol])
                continue
            seen.add(bot_id)

            if bot_id not in self.panels:
                panel = PanelSink(symbol)
                panel.set_chart_timeframe(PANEL_TIMEFRAME)
                panel.set_minimum_height(PANEL_MINIMUM_HEIGHT_PX)
                self.order.append(bot_id)
                self.panels[bot_id] = {
                    PANEL_KEY: panel,
                    SYMBOL_KEY: symbol,
                    EXCHANGE_ID_KEY: status.get(EXCHANGE_KEY, DEFAULT_EXCHANGE_ID),
                    LAST_FETCH_KEY: NEVER_FETCHED,
                }
                panel.connect_timeframe()
                self.calls.append([UPDATE_PANEL_CREATED, bot_id, symbol])
            else:
                self.calls.append([UPDATE_PANEL_KEPT, bot_id, symbol])

            info = self.panels[bot_id]
            stats = status.get(STATS_KEY, {})
            price = stats.get(PRICE_KEY, DEFAULT_PRICE)
            state = status.get(STATE_KEY, DEFAULT_STATE)
            panel = info[PANEL_KEY]

            if info[SYMBOL_KEY] != symbol:
                self.logs.append(
                    [
                        FOLLOW_LOG_FORMAT,
                        bot_id[:BOT_ID_LOG_LENGTH],
                        info[SYMBOL_KEY],
                        symbol,
                    ]
                )
                self.calls.append(
                    [UPDATE_SYMBOL_FOLLOWED, bot_id, info[SYMBOL_KEY], symbol]
                )
                info[SYMBOL_KEY] = symbol
                info[LAST_FETCH_KEY] = NEVER_FETCHED
                panel.set_symbol_property(symbol)
                panel.set_candles([])
                panel.set_markers([])
                panel.set_source(EMPTY_SOURCE)
                panel.set_error(awaiting_text(symbol))

            if price > 0:
                panel.set_label(price_label(symbol, price, state))
                self.calls.append([UPDATE_LABEL_SET, bot_id, panel.label])
            else:
                self.calls.append([UPDATE_LABEL_SKIPPED, bot_id])

            if self.manager:
                bot = self.manager.get_bot(bot_id)
                if bot:
                    self._feed_overlays(bot_id, symbol, bot, panel)
                else:
                    self.calls.append([UPDATE_NO_BOT, bot_id])
            else:
                self.calls.append([UPDATE_NO_MANAGER, bot_id])

            panel.repaint_chart()
            self.calls.append([UPDATE_CHART_REPAINTED, bot_id])

        for bot_id in list(self.panels):
            if bot_id not in seen:
                info = self.panels.pop(bot_id)
                self.order.remove(bot_id)
                info[PANEL_KEY].drop()
                self.dropped.append(bot_id)
                self.calls.append([UPDATE_PANEL_DROPPED, bot_id])

        mounted = self._mounted_count()
        drift = 0
        for status in kept_statuses:
            held = self.panels.get(status.get(BOT_ID_KEY, DEFAULT_BOT_ID))
            if held is not None and held.get(SYMBOL_KEY) != status.get(
                SYMBOL_KEY, DEFAULT_SYMBOL
            ):
                drift += 1

        self._emit(
            SignalRecord(
                MOUNTED_SIGNAL,
                actual=mounted,
                expected=len(self.panels),
                every=SIGNAL_EVERY_S,
                context={
                    "layout_items": self._layout_slots(),
                    "statuses": len(kept_statuses),
                    "kept": len(seen),
                },
            )
        )
        self.calls.append([UPDATE_EMIT_MOUNTED, mounted, len(self.panels)])
        self._emit(
            SignalRecord(
                SYMBOLS_SIGNAL,
                actual=drift,
                expected=NO_DRIFT,
                every=SIGNAL_EVERY_S,
                context={
                    "panels": len(self.panels),
                    "statuses": len(kept_statuses),
                    "mounted": mounted,
                },
            )
        )
        self.calls.append([UPDATE_EMIT_SYMBOLS, drift])
        return None

    def _feed_overlays(self, bot_id: Any, symbol: Any, bot: Any, panel: Any) -> None:
        """Put this bot's markers, overlay lines, glow and floors on its panel.

        Each of the four is guarded on its own, so one that refuses
        leaves the other three drawn.
        """
        try:
            for_this_bot = [
                one
                for one in self.trade_log
                if one.get(BOT_ID_KEY) == bot_id and one.get(SYMBOL_KEY) == symbol
            ]
            if for_this_bot:
                panel.set_markers(for_this_bot)
                self.calls.append([UPDATE_MARKERS_SET, bot_id, len(for_this_bot)])
            else:
                self.calls.append([UPDATE_MARKERS_NONE, bot_id])
        except Exception as exc:
            self.calls.append([UPDATE_MARKERS_FAILED, bot_id, type(exc).__name__])

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

    def on_timeframe_changed(self, bot_id: Any, timeframe: Any) -> None:
        """Re-arm one panel's fetch after the operator moved its timeframe combo.

        A signal from a panel this tab has already dropped re-arms
        nothing, and the emitted record says so rather than staying quiet.
        """
        self.calls.append([TF_START, bot_id, timeframe])
        if bot_id in self.panels:
            self.panels[bot_id][LAST_FETCH_KEY] = NEVER_FETCHED
        info = self.panels.get(bot_id) or {}
        panel = info.get(PANEL_KEY)
        rearmed = bool(
            panel is not None
            and info.get(LAST_FETCH_KEY, MISSING_LAST_FETCH) == NEVER_FETCHED
            and panel.timeframe == timeframe
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
                    "panel_tf": ("" if panel is None else panel.timeframe),
                    "known_bot": panel is not None,
                    "panels": len(self.panels),
                },
            )
        )
        self.calls.append([TF_EMIT, rearmed])
        return None

    async def fetch_chart_data(
        self, exchange_connectors: Optional[dict] = None
    ) -> None:
        """Run one fetch pass over every panel, and report which went stale.

        A panel refetched inside the throttle window is left alone. A
        wildcard symbol is declined and its last-fetch stamp is left
        where it was, which is the one path that can starve a panel for
        the life of the process.
        """
        now = self._now()
        self.calls.append([FETCH_START, len(self.panels)])

        for bot_id in list(self.panels):
            info = self.panels[bot_id]
            if now - info.get(LAST_FETCH_KEY, NEVER_FETCHED) < FETCH_THROTTLE_S:
                self.calls.append([FETCH_THROTTLED, bot_id])
                continue

            symbol = info[SYMBOL_KEY]
            if WILDCARD in symbol:
                self.calls.append([FETCH_WILDCARD_SKIPPED, bot_id, symbol])
                continue

            panel = info[PANEL_KEY]
            timeframe = panel.timeframe
            exchange = None
            if exchange_connectors:
                exchange = exchange_connectors.get(
                    info.get(EXCHANGE_ID_KEY, DEFAULT_EXCHANGE_ID)
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
                    panel.set_candles([list(one) for one in rows])
                    panel.set_source(answered)
                    outcome = OUTCOME_CANDLES
                    self.calls.append([FETCH_CANDLES, bot_id, returned, source])
                else:
                    panel.set_error(answered)
                    outcome = OUTCOME_EMPTY
                    self.calls.append([FETCH_EMPTY, bot_id, source])

                info[LAST_FETCH_KEY] = now
            except Exception as exc:
                if elapsed is None:
                    elapsed = self._tick() - started
                panel.set_error(str(exc)[:ERROR_TEXT_LIMIT])
                source = type(exc).__name__
                info[LAST_FETCH_KEY] = now
                self.calls.append([FETCH_RAISED, bot_id, source])

            shown = len(panel.candles)
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
                        "exchange_id": info.get(EXCHANGE_ID_KEY, DEFAULT_EXCHANGE_ID),
                        "throttle_s": FETCH_THROTTLE_S,
                    },
                )
            )
            self.calls.append([FETCH_EMIT_REFRESHED, bot_id, shown, returned, outcome])

        stale = 0
        never = 0
        oldest = 0.0
        for info in self.panels.values():
            last = float(info.get(LAST_FETCH_KEY, NEVER_FETCHED) or 0)
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
                    "panels": len(self.panels),
                    "never_fetched": never,
                    "oldest_age_s": round(oldest, AGE_DECIMALS),
                    "stale_after_s": STALE_AFTER_S,
                    "throttle_s": FETCH_THROTTLE_S,
                    "connectors": len(exchange_connectors or {}),
                },
            )
        )
        self.calls.append([FETCH_EMIT_FRESH, stale, never])
        return None

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
        """Put one Nuclear Mode scenario's candles straight on a panel.

        No fetch and no network: the candles are made for the scenario.
        A bot with no panel gets one, sized for a Nuclear panel and
        marked as synthetic.
        """
        if bot_id not in self.panels:
            panel = PanelSink(symbol)
            panel.set_chart_timeframe(NUCLEAR_TIMEFRAME)
            panel.set_minimum_height(NUCLEAR_MINIMUM_HEIGHT_PX)
            panel.set_maximum_height(NUCLEAR_MAXIMUM_HEIGHT_PX)
            self.order.append(bot_id)
            self.panels[bot_id] = {
                PANEL_KEY: panel,
                SYMBOL_KEY: symbol,
                EXCHANGE_ID_KEY: NUCLEAR_EXCHANGE_ID,
                LAST_FETCH_KEY: NEVER_FETCHED,
                SYNTHETIC_KEY: True,
            }
            self.calls.append([NUCLEAR_PANEL_CREATED, bot_id, symbol])
        else:
            self.calls.append([NUCLEAR_PANEL_KEPT, bot_id, symbol])

        info = self.panels[bot_id]
        panel = info[PANEL_KEY]
        rows = [candle_row(one) for one in candles]
        panel.set_candles(rows)
        label_price = last_price or (
            rows[-1][CANDLE_CLOSE_INDEX] if rows else NO_LAST_PRICE
        )
        panel.set_label(nuclear_label(symbol, label_price, scenario))
        panel.repaint_panel()
        self.calls.append([NUCLEAR_CANDLES_SET, bot_id, len(rows), panel.label])
        return None


def build_view_model(
    model: TradeChartsTabModel,
    statuses: Optional[list] = None,
    connectors: Optional[dict] = None,
    timeframe_change: Optional[list] = None,
    fetch_now: bool = False,
    trades: Optional[list] = None,
    synthetic: Optional[list] = None,
) -> dict:
    """Return every value the Asset Charts tab holds as one dict.

    Each argument runs one of the tab's five entry points, in the order
    the running window calls them: trades are recorded, statuses drive a
    pass, a timeframe change re-arms a panel, a fetch pass runs, and a
    Nuclear scenario is injected.
    """
    import asyncio

    for trade in trades or []:
        model.log_trade(trade[0], trade[1] if len(trade) > 1 else None)
    if statuses is not None:
        model.update_charts(statuses, exchange_connectors=connectors)
    if timeframe_change is not None:
        model.on_timeframe_changed(timeframe_change[0], timeframe_change[1])
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
        "scroll": {
            "widget_resizable": SCROLL_RESIZABLE,
            "horizontal_policy": SCROLL_HORIZONTAL_POLICY,
            "horizontal_policy_value": SCROLL_HORIZONTAL_POLICY_VALUE,
        },
        "content": {
            "margins_px": list(CONTENT_MARGINS_PX),
            "spacing_px": CONTENT_SPACING_PX,
            "stretch_added": CONTENT_STRETCH_ADDED,
            "stretch_slots": STRETCH_SLOTS,
            "layout_slots": model._layout_slots(),
        },
        "panel_order": list(model.order),
        "panel_count": len(model.panels),
        "panels": {
            bot_id: {
                "symbol": info[SYMBOL_KEY],
                "exchange_id": info[EXCHANGE_ID_KEY],
                "last_fetch": info[LAST_FETCH_KEY],
                "synthetic": info.get(SYNTHETIC_KEY, False),
                "panel": info[PANEL_KEY].as_values(),
            }
            for bot_id, info in model.panels.items()
        },
        "dropped": list(model.dropped),
        "trade_log": [dict(one) for one in model.trade_log],
        "logs": [list(one) for one in model.logs],
        "signals": [one.as_values() for one in model.signals],
        "signal_names": list(SIGNAL_NAMES),
        "throttled_signals": list(THROTTLED_SIGNALS),
        "panel_defaults": {
            "timeframe": PANEL_TIMEFRAME,
            "combo_timeframe": COMBO_TIMEFRAME,
            "minimum_height_px": PANEL_MINIMUM_HEIGHT_PX,
            "maximum_height_px": PANEL_MAXIMUM_HEIGHT_PX,
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


def view_model(params: dict) -> dict:
    """Bridge handler for ``trade_charts_tab.state``.

    Reads ``reset``, ``bots``, ``answers``, ``now``, ``ticks``,
    ``statuses``, ``connectors``, ``timeframe_change``, ``fetch``,
    ``trades`` and ``synthetic`` from the request parameters. The tab's
    panels persist between calls because the tab does; ``reset`` is what
    a fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = TradeChartsTabModel()
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
    )
