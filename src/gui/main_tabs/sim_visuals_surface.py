"""sim_visuals_surface.py -- the Simulator's drawn panels as plain data.

Describes the four screens ``src/gui/simulator_tab/fleet/sim_visuals.py``
paints: the gate status pane, one bot's labelled gate row, the stacked
price and VWAP chart with its focused candle view, and the per-bot voting
table. It also holds the behaviour those screens own rather than describe
-- the rolling VWAP, the point decimation that keeps a marked candle, the
band scales, the candle geometry, the vote direction and the colour each
value paints in -- plus the expand dialog's re-entry guard and geometry.

Every drawing routine returns a draw program: a list of primitives, each
naming its pen, its brush, its rectangle and its text. A frontend replays
the program; nothing here needs a painter.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``sim_visuals.state`` method, which is how the Electron renderer
reaches it. Nothing here imports Qt, so the same code serves any
frontend.

The gate labels, the blocker map and the light-state rules come from
``src.trading.gate_vocabulary``, the Qt-free module the History gate cell
also reads. One vocabulary, so a gate added on one surface cannot be
missing from the other.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Optional

from src.trading.gate_vocabulary import (
    _GATE_ORDER_FOLD,
    _GATE_ORDER_SCRUM,
    LIGHT_COLORS,
    _blocked_labels,
    gate_light_color,
    gate_light_state,
)

METHOD = "sim_visuals.state"

NO_PEN = "none"
NO_BRUSH = "none"
SOLID_LINE = "solid"
DASH_LINE = "dash"

TEXT = "text"
LINE = "line"
ELLIPSE = "ellipse"
RECT = "rect"
FILL = "fill"

ALIGN_LABEL = "hcenter|vcenter"
ALIGN_MARKER = "right|vcenter"
ALIGN_SYMBOL = "left|vcenter"

# The expand dialog

EXPAND_STYLE = "QDialog{background:#0a0a14;}"
EXPAND_MARGINS_PX = (8, 8, 8, 8)
EXPAND_CLAIM_FIELD = "_acv_expand_dlg"
EXPAND_DELETE_ON_CLOSE = True

EXPAND_OPENED = "expand_opened"
EXPAND_RAISED = "expand_raised"
EXPAND_STALE_CLAIM_DROPPED = "expand_stale_claim_dropped"
EXPAND_RESTORED = "expand_restored"

EXPAND_CALL_NAMES = (
    EXPAND_OPENED,
    EXPAND_RAISED,
    EXPAND_STALE_CLAIM_DROPPED,
    EXPAND_RESTORED,
)


def expand_geometry(available: Any) -> dict:
    """Where the expand dialog sits on the screen it opens over.

    `available` is the screen area free of the task bar, as
    ``(x, y, width, height)``. Full width, half height, centred on that
    area's own centre.
    """
    left, top, width, height = (int(one) for one in available)
    centre_x = left + width // 2
    centre_y = top + height // 2
    return {
        "width": width,
        "height": height // 2,
        "x": centre_x - width // 2,
        "y": centre_y - height // 4,
    }


class ExpandModel:
    """The expand dialog's claim on one widget, with no Qt behind it.

    One widget holds at most one dialog. A second request raises the one
    already open rather than opening a second: the widget records where
    it came from as the dialog opens, and a second record would send it
    home to a container nobody can see.
    """

    def __init__(self) -> None:
        self.claim: Optional[dict] = None
        self.parent: Optional[str] = None
        self.minimum_height_px: int = 0
        self.calls: list = []

    def open(self, title: Any, parent: Any = None, minimum_height_px: Any = 0) -> dict:
        """Open the dialog for `title`, or raise the one already open."""
        if self.claim is not None:
            self.calls.append(EXPAND_RAISED)
            return dict(self.claim)
        self.parent = None if parent is None else str(parent)
        self.minimum_height_px = int(minimum_height_px)
        self.claim = {
            "title": str(title),
            "style_sheet": EXPAND_STYLE,
            "margins_px": list(EXPAND_MARGINS_PX),
            "delete_on_close": EXPAND_DELETE_ON_CLOSE,
            "claim_field": EXPAND_CLAIM_FIELD,
        }
        self.calls.append(EXPAND_OPENED)
        return dict(self.claim)

    def drop_stale_claim(self) -> None:
        """Forget a dialog the frontend destroyed under the claim."""
        self.claim = None
        self.calls.append(EXPAND_STALE_CLAIM_DROPPED)

    def close(self) -> dict:
        """Release the claim, then hand the widget back to its parent.

        The claim is released first, so the button works again even when
        the hand-back fails.
        """
        self.claim = None
        self.calls.append(EXPAND_RESTORED)
        return {
            "parent": self.parent,
            "minimum_height_px": self.minimum_height_px,
            "shown": self.parent is not None,
        }


# GateLightsCell -- one labelled row of trading gates

GATE_LED_PX = 9
GATE_GAP_PX = 4
GATE_LABEL_HEIGHT_PX = 10
GATE_PAD_PX = 2
GATE_BANK_GAP_PX = 12
GATE_FONT_PT = 6

GATE_SCRUM_BANK = "S"
GATE_FOLD_BANK = "F"
GATE_BANKS = (GATE_SCRUM_BANK, GATE_FOLD_BANK)
GATE_ORDER = {
    GATE_SCRUM_BANK: tuple(_GATE_ORDER_SCRUM),
    GATE_FOLD_BANK: tuple(_GATE_ORDER_FOLD),
}
GATE_COUNT = len(_GATE_ORDER_SCRUM) + len(_GATE_ORDER_FOLD)

LANDING_STRIP_SCRUM = "upper"
LANDING_STRIP_FOLD = "lower"

GATE_LABEL_COLOUR = "#9aa0b5"
GATE_MARKER_COLOUR = "#6b7280"
LIGHT_COLOURS_BY_STATE = dict(LIGHT_COLORS)

GATE_TOOLTIP = (
    "Trading gates. Left bank = SCRUM (sell-high), "
    "right bank = FOLD (buy-low).\n"
    "\n"
    "SCRUM:\n"
    "  TGT   position delta vs target (delta<=0 blocks)\n"
    "  INT   move smaller than scrumming_interval_pct\n"
    "  BB    price below the upper-band detect level\n"
    "  FIRE  detect/fire state machine not armed\n"
    "  TA    voting consensus not bullish\n"
    "  LS    landing-strip OVERRIDE active (cyan) —\n"
    "        forces bullish, can fire despite TA\n"
    "  TRND  holding through an uptrend\n"
    "  HTF   higher-timeframe bias opposes\n"
    "  CB    circuit breaker tripped\n"
    "  OTD   opposing-trade-distance hysteresis\n"
    "\n"
    "FOLD:\n"
    "  BB    price above the lower-band detect level\n"
    "  MID   BB midline gate\n"
    "  TA    voting consensus not bearish\n"
    "  LS    landing-strip OVERRIDE active (cyan)\n"
    "  TRNQ  no fold tranches queued — the fold-side\n"
    "        equivalent of TGT; tranches are created by\n"
    "        a prior scrum, so a fold cannot fire until\n"
    "        a scrum has\n"
    "  CEIL  MEM-253 position ceiling\n"
    "  HTF   higher-timeframe bias opposes\n"
    "  CB    circuit breaker tripped\n"
    "  OTD   opposing-trade-distance hysteresis\n\n"
    "green = passed, red = this gate blocked, "
    "amber = not armed (other reason), grey = not "
    "evaluated at this candle."
)

GATES_UPDATED = "gates_updated"
GATES_CLEARED = "gates_cleared"


def gate_pitch_px(widest_label_px: Any) -> int:
    """The horizontal step one gate takes, given the widest label.

    The label decides the step, not the light: a five-letter label in a
    light-sized box overlaps its neighbour. The caller measures the label
    width in the run's own font and hands it in.
    """
    return max(GATE_LED_PX, int(widest_label_px)) + GATE_GAP_PX


def gate_cell_height_px() -> int:
    """How tall one gate row is, labels and lights together."""
    return GATE_LABEL_HEIGHT_PX + GATE_LED_PX + GATE_PAD_PX * 2 + 1


def gate_cell_min_width_px(pitch_px: Any) -> int:
    """The narrowest one gate row may be drawn at."""
    return GATE_COUNT * int(pitch_px) + GATE_BANK_GAP_PX + GATE_PAD_PX * 2


class GateLightsModel:
    """One bot's gate row between updates, with no Qt object behind it.

    ``clear_gates`` returns the row to the not-evaluated state. It
    releases the scrum landing strip and leaves the fold landing strip
    where it was, which is what the shipped row does.
    """

    def __init__(self) -> None:
        self.evaluated = False
        self.scrum_armed = False
        self.fold_armed = False
        self.scrum_blocked: set = set()
        self.fold_blocked: set = set()
        self.scrum_landing_strip = False
        self.fold_landing_strip = False
        self.calls: list = []

    def update_gates(
        self,
        scrum_armed: Any,
        fold_armed: Any,
        scrum_blockers: Any,
        fold_blockers: Any,
        landing_strip_side: Any = "",
    ) -> None:
        """Take one candle's gate reading. Any call means it was read."""
        self.scrum_armed = bool(scrum_armed)
        self.fold_armed = bool(fold_armed)
        self.scrum_blocked = _blocked_labels(scrum_blockers)
        self.fold_blocked = _blocked_labels(fold_blockers)
        side = str(landing_strip_side or "").lower()
        self.scrum_landing_strip = side == LANDING_STRIP_SCRUM
        self.fold_landing_strip = side == LANDING_STRIP_FOLD
        self.evaluated = True
        self.calls.append(GATES_UPDATED)

    def clear_gates(self) -> None:
        """Return the row to the not-evaluated state."""
        self.evaluated = False
        self.scrum_armed = False
        self.fold_armed = False
        self.scrum_blocked = set()
        self.fold_blocked = set()
        self.scrum_landing_strip = False
        self.calls.append(GATES_CLEARED)

    def bank(self, name: str) -> dict:
        """One bank's arm state, its blockers and its landing strip."""
        if name == GATE_SCRUM_BANK:
            return {
                "armed": self.scrum_armed,
                "blocked": self.scrum_blocked,
                "landing_strip": self.scrum_landing_strip,
            }
        return {
            "armed": self.fold_armed,
            "blocked": self.fold_blocked,
            "landing_strip": self.fold_landing_strip,
        }

    def lights(self) -> list:
        """The nineteen lights, scrum bank then fold, in draw order."""
        found = []
        for name in GATE_BANKS:
            side = self.bank(name)
            for label in GATE_ORDER[name]:
                found.append(
                    {
                        "bank": name,
                        "label": label,
                        "state": gate_light_state(
                            label,
                            self.evaluated,
                            side["armed"],
                            side["blocked"],
                            side["landing_strip"],
                        ),
                        "colour": gate_light_color(
                            label,
                            self.evaluated,
                            side["armed"],
                            side["blocked"],
                            side["landing_strip"],
                        ),
                    }
                )
        return found


def _gate_bank_program(program: list, x: int, name: str, side: dict, pitch: int) -> int:
    """Add one bank's labels and lights. Returns the next bank's x."""
    led_y = GATE_PAD_PX + GATE_LABEL_HEIGHT_PX
    box_w = pitch - GATE_GAP_PX
    for label in GATE_ORDER[name]:
        program.append(
            {
                "op": TEXT,
                "pen": GATE_LABEL_COLOUR,
                "rect": [x, GATE_PAD_PX, box_w, GATE_LABEL_HEIGHT_PX],
                "align": ALIGN_LABEL,
                "text": label,
            }
        )
        program.append(
            {
                "op": ELLIPSE,
                "pen": NO_PEN,
                "brush": gate_light_color(
                    label,
                    side["evaluated"],
                    side["armed"],
                    side["blocked"],
                    side["landing_strip"],
                ),
                "rect": [
                    x + (box_w - GATE_LED_PX) // 2,
                    led_y,
                    GATE_LED_PX,
                    GATE_LED_PX,
                ],
            }
        )
        x += pitch
    program.append(
        {
            "op": TEXT,
            "pen": GATE_MARKER_COLOUR,
            "rect": [x - pitch, led_y, box_w, GATE_LED_PX],
            "align": ALIGN_MARKER,
            "text": name,
        }
    )
    return x


def gate_program(model: "GateLightsModel", pitch_px: Any) -> list:
    """Everything one gate row paints, in the order it paints it."""
    pitch = int(pitch_px)
    program: list = []
    x = GATE_PAD_PX
    for index, name in enumerate(GATE_BANKS):
        if index:
            x += GATE_BANK_GAP_PX
        side = dict(model.bank(name), evaluated=model.evaluated)
        x = _gate_bank_program(program, x, name, side, pitch)
    return program


# GateStatusPanel -- every bot's gate row in one scrollable pane

PANEL_ACCESSIBLE_NAME = "Gate Status Panel"
PANEL_MARGINS_PX = (0, 0, 0, 0)
PANEL_SPACING_PX = 0
PANEL_SCROLL_STYLE = "QScrollArea{background:#0a0a14;border:1px solid #2a2a44;}"
PANEL_SCROLL_RESIZABLE = True
PANEL_HOST_MARGINS_PX = (6, 4, 6, 4)
PANEL_HOST_SPACING_PX = 2
PANEL_EMPTY_TEXT = "No fleet loaded."
PANEL_EMPTY_STYLE = "color:#666677;font-size:11px;padding:8px;"
PANEL_ROW_MARGINS_PX = (0, 0, 0, 0)
PANEL_ROW_SPACING_PX = 8
PANEL_LABEL_MIN_WIDTH_PX = 96
PANEL_LABEL_STYLE = (
    "color:#00e5ff;font-size:11px;" "font-family:'Cascadia Code','Consolas',monospace;"
)
PANEL_TRAILING_STRETCH = True

PANEL_LOADED = "panel_loaded"
PANEL_EMPTIED = "panel_emptied"


class GateRow:
    """One symbol's labelled row inside the gate pane."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.lights = GateLightsModel()


class GatePanelModel:
    """The gate pane's rows between fleet loads, with no Qt behind it.

    A load drops the rows the pane can still reach and builds one row per
    symbol. A row the pane lost track of stays in the column, which is
    what the shipped pane does with a repeated symbol.
    """

    def __init__(self) -> None:
        self.built: list = []
        self.rows: dict = {}
        self.empty_visible = True
        self.calls: list = []

    def set_symbols(self, symbols: Any) -> None:
        """Build one labelled gate row per symbol, replacing the last set."""
        for row in list(self.rows.values()):
            self.built.remove(row)
        self.rows = {}
        named = [str(one) for one in (symbols or []) if str(one)]
        self.empty_visible = not named
        for symbol in named:
            row = GateRow(symbol)
            self.built.append(row)
            self.rows[symbol] = row
        self.calls.append(PANEL_EMPTIED if not named else PANEL_LOADED)

    def cell_for(self, symbol: Any):
        """One symbol's gate row, or None when the pane carries none."""
        row = self.rows.get(str(symbol))
        return row.lights if row else None

    def symbols(self) -> list:
        """Every symbol the pane can reach, in name order."""
        return sorted(self.rows)

    def items(self) -> list:
        """The pane's column, item by item, in the order it holds them."""
        found: list = [{"kind": "empty", "visible": self.empty_visible}]
        found.extend({"kind": "row", "symbol": row.symbol} for row in self.built)
        if PANEL_TRAILING_STRETCH:
            found.append({"kind": "stretch"})
        return found


# SimPriceVwapChart -- stacked bands, or one bot's candles

CHART_BAND_HEIGHT_PX = 36
CHART_LABEL_WIDTH_PX = 128
CHART_MAX_POINTS = 500
CHART_VWAP_WINDOW = 30
CHART_MAX_MARKERS = 2000
CHART_FOCUS_MIN_HEIGHT_PX = 320
CHART_MAX_CANDLES = 400
CHART_CANDLE_WIDTH_PX = 5
CHART_CANDLE_GAP_PX = 2

CHART_ACCESSIBLE_NAME = "Sim Price + VWAP Chart"
CHART_ACCESSIBLE_DESCRIPTION = (
    "Stacked bands, one per simulated bot. White line "
    "= price, cyan line = rolling VWAP. Updates each "
    "visual-refresh tick."
)
CHART_TOOLTIP = "White = price close, cyan = rolling VWAP over " "the last 30 candles."
CHART_STYLE = "background:#0a0a14;"
CHART_SIZE_POLICY = ("Expanding", "Expanding")

CHART_SEPARATOR_COLOUR = "#1a1a2a"
CHART_SYMBOL_COLOUR = "#7fb3ff"
CHART_PRICE_COLOUR = "#ccccdd"
CHART_VWAP_COLOUR = "#00ffcc"
CHART_FRAME_COLOUR = "#2a2a44"
CHART_MARKER_OK_COLOUR = "#00ff66"
CHART_MARKER_MISSED_COLOUR = "#ff3355"

CHART_BAND_INSET_PX = 3
CHART_BAND_RIGHT_PX = 4
CHART_LABEL_INSET_PX = 2
CHART_MARKER_RADIUS_PX = 1.5
CHART_FLAT_SPAN = 1e-9
CHART_MIN_LINE_POINTS = 2

FOCUS_PAD_PX = 8
FOCUS_TOP_Y_PX = 16
FOCUS_GAP_PX = 10
FOCUS_MIN_BAND_PX = 40
FOCUS_HEAD_ROOM_PX = 30
FOCUS_FOOT_ROOM_PX = 14
FOCUS_BASELINE_PX = 2
FOCUS_WAITING_Y_PX = 18
FOCUS_HEADING_LIFT_PX = 4
FOCUS_MARKER_RADIUS_PX = 2
FOCUS_YTD_TEXT_INSET_PX = 3
FOCUS_YTD_TEXT_DROP_PX = 10
FOCUS_HIGH_LABEL_INSET_PX = 70
FOCUS_BARS_LABEL_INSET_PX = 150
FOCUS_BARS_LABEL_DROP_PX = 10

FOCUS_WAITING_COLOUR = "#666677"
FOCUS_HEADING_COLOUR = "#00e5ff"
FOCUS_PRICE_COLOUR = "#8888aa"
FOCUS_MARKER_OK_COLOUR = "#00ff88"
FOCUS_MARKER_MISSED_COLOUR = "#ffaa00"
FOCUS_CANDLE_UP_COLOUR = "#00ff88"
FOCUS_CANDLE_DOWN_COLOUR = "#ff3366"
FOCUS_AXIS_COLOUR = "#666677"
FOCUS_YTD_FILL_RGBA = (0, 229, 255, 18)

FOCUS_WAITING_SUFFIX = " — waiting for candles"
FOCUS_PRICE_HEADING_SUFFIX = "  price vs position VWAP"
FOCUS_CANDLE_HEADING = "Stone Tablet candles"
FOCUS_YTD_LABEL = "YTD"
FOCUS_BARS_SUFFIX = " bars"
FOCUS_PRICE_FORMAT = "{:.8g}"

CHART_SYMBOLS_SET = "chart_symbols_set"
CHART_TICK_APPENDED = "chart_tick_appended"
CHART_TICK_IGNORED = "chart_tick_ignored"
CHART_POINTS_DECIMATED = "chart_points_decimated"
CHART_MARKED = "chart_marked"
CHART_MARK_IGNORED = "chart_mark_ignored"
CHART_MARKERS_CLEARED = "chart_markers_cleared"
CHART_DATA_CLEARED = "chart_data_cleared"
CHART_FOCUS_SET = "chart_focus_set"
CHART_YTD_SET = "chart_ytd_set"
CHART_YTD_REFUSED = "chart_ytd_refused"

CHART_CALL_NAMES = (
    CHART_SYMBOLS_SET,
    CHART_TICK_APPENDED,
    CHART_TICK_IGNORED,
    CHART_POINTS_DECIMATED,
    CHART_MARKED,
    CHART_MARK_IGNORED,
    CHART_MARKERS_CLEARED,
    CHART_DATA_CLEARED,
    CHART_FOCUS_SET,
    CHART_YTD_SET,
    CHART_YTD_REFUSED,
)


def candle_step_px() -> int:
    """The horizontal step one candle takes, body and gap together."""
    return CHART_CANDLE_WIDTH_PX + CHART_CANDLE_GAP_PX


def band_span(low: float, high: float) -> float:
    """Return the divisor for a band running low to high.

    A fixed floor would outrank the real span at BONK scale; the
    substitute applies only when high equals low.
    """
    return (high - low) or 1.0


def rolling_vwap(window: list, close_price: float) -> float:
    """Volume-weighted average price over `window`.

    Total of price times volume, divided by total volume. A window whose
    volumes total nothing has no weighted average, so the close stands in
    for it.
    """
    weighted = 0.0
    volume = 0.0
    for price, size in window:
        weighted += price * size
        volume += size
    if volume > 0:
        return weighted / volume
    return float(close_price)


def scale(low: float, high: float, top: int, height: int):
    """A reading-to-y mapping for one band, the high value at the top.

    A band whose high is not above its low is opened by the smallest step
    the mapping carries, so a flat series maps rather than dividing by
    zero.
    """
    if high <= low:
        high = low + CHART_FLAT_SPAN
    span = high - low
    return lambda value: int(top + height - ((float(value) - low) / span) * height)


class PriceVwapModel:
    """The chart's buffers between refreshes, with no Qt behind it.

    Prices, the rolling VWAP window, the candles and the trade markers,
    per symbol. A marker anchors on the candle's ordinal, which the
    decimation keeps, rather than on its position in a list the
    decimation rewrites.
    """

    def __init__(self) -> None:
        self.symbols: list = []
        self.series: dict = {}
        self.vwap_window: dict = {}
        self.markers: dict = {}
        self.ordinals: dict = {}
        self.next_ordinal: dict = {}
        self.candles: dict = {}
        self.focus = ""
        self.ytd_from: dict = {}
        self.height_px = 0
        self.calls: list = []

    def new_marker_store(self):
        """A marker store bounded so a long replay keeps the live end."""
        return deque(maxlen=CHART_MAX_MARKERS)

    def set_symbols(self, symbols: Any) -> None:
        """Track this fleet, dropping every buffer the last one filled."""
        self.symbols = list(symbols)
        self.series = {one: ([], []) for one in symbols}
        self.vwap_window = {one: [] for one in symbols}
        self.markers = {one: self.new_marker_store() for one in symbols}
        self.ordinals = {one: [] for one in symbols}
        self.next_ordinal = {one: 0 for one in symbols}
        self.candles = {one: [] for one in symbols}
        if self.focus and self.focus not in symbols:
            self.focus = ""
        self.apply_height()
        self.calls.append(CHART_SYMBOLS_SET)

    def apply_height(self) -> int:
        """Set the chart's least height: one focused view, or a band each.

        Only a fleet load and a focus change ask for it, so a chart that
        has been given neither keeps whatever height it was built with.
        """
        if self.focus:
            self.height_px = CHART_FOCUS_MIN_HEIGHT_PX
        else:
            self.height_px = CHART_BAND_HEIGHT_PX * max(1, len(self.symbols))
        return self.height_px

    def set_focus_symbol(self, symbol: Any) -> None:
        """Show one bot's candles, or "" for a band per bot."""
        named = str(symbol or "")
        self.focus = named if named in self.series else ""
        self.apply_height()
        self.calls.append(CHART_FOCUS_SET)

    def focus_symbol(self) -> str:
        """The symbol filling the chart, or "" when bands are shown."""
        return self.focus

    def set_ytd_start(self, symbol: Any, ts_ms: Any) -> None:
        """Where the YTD overlay begins for `symbol`.

        The timestamp of the first documented historical trade. The
        overlay is not drawn before it: the replay opens with warm-up
        candles that predate any gate decision.
        """
        try:
            self.ytd_from[str(symbol)] = int(ts_ms)
        except (TypeError, ValueError):
            self.calls.append(CHART_YTD_REFUSED)
            return
        self.calls.append(CHART_YTD_SET)

    def resolved_markers(self, symbol: Any) -> list:
        """Markers as positions in the series as it stands now.

        Resolved here rather than at record time, so a decimation between
        the two cannot move one. An ordinal whose candle is gone is left
        out rather than sliding onto its neighbour.
        """
        marks = self.markers.get(symbol)
        if not marks:
            return []
        ordinals = self.ordinals.get(symbol) or []
        if not ordinals:
            return []
        at = {ordinal: index for index, ordinal in enumerate(ordinals)}
        found = []
        for ordinal, validated in marks:
            index = at.get(ordinal)
            if index is not None:
                found.append((index, bool(validated)))
        return found

    def mark_trade(self, symbol: Any, validated: Any) -> None:
        """Pin a trade marker on the candle now at the end of the series.

        Called after ``append_tick`` for the same tick, so the marker
        lands on that tick's candle rather than the one before it.
        """
        ordinals = self.ordinals.get(symbol)
        if not ordinals:
            self.calls.append(CHART_MARK_IGNORED)
            return
        store = self.markers.get(symbol)
        if store is None:
            store = self.new_marker_store()
            self.markers[symbol] = store
        store.append((ordinals[-1], bool(validated)))
        self.calls.append(CHART_MARKED)

    def clear_markers(self, symbol: Any = None) -> None:
        """Drop every marker, or only the ones on one symbol."""
        if symbol is None:
            self.markers = {one: self.new_marker_store() for one in self.symbols}
        else:
            self.markers[symbol] = self.new_marker_store()
        self.calls.append(CHART_MARKERS_CLEARED)

    def append_tick(
        self,
        symbol: Any,
        close_price: Any,
        volume: Any,
        ts: Any = None,
        open_price: Any = None,
        high: Any = None,
        low: Any = None,
    ) -> None:
        """Take one bar. A bar with only a close degenerates to a doji."""
        if symbol not in self.series:
            self.calls.append(CHART_TICK_IGNORED)
            return
        close = float(close_price)
        opened = float(open_price) if open_price is not None else close
        highest = float(high) if high is not None else max(opened, close)
        lowest = float(low) if low is not None else min(opened, close)
        bars = self.candles.setdefault(symbol, [])
        bars.append((int(ts) if ts is not None else 0, opened, highest, lowest, close))
        if len(bars) > CHART_MAX_CANDLES:
            del bars[: len(bars) - CHART_MAX_CANDLES]
        prices, vwaps = self.series[symbol]
        prices.append(close)
        ordinal = self.next_ordinal.get(symbol, 0)
        self.ordinals.setdefault(symbol, []).append(ordinal)
        self.next_ordinal[symbol] = ordinal + 1
        window = self.vwap_window[symbol]
        window.append((close, float(volume)))
        if len(window) > CHART_VWAP_WINDOW:
            window.pop(0)
        vwaps.append(rolling_vwap(window, close))
        self.calls.append(CHART_TICK_APPENDED)
        if len(prices) > CHART_MAX_POINTS:
            self._decimate(symbol, prices, vwaps)

    def _decimate(self, symbol, prices, vwaps) -> None:
        """Halve the series, keeping every candle that carries a marker."""
        ordinals = self.ordinals.get(symbol) or []
        marked = {ordinal for ordinal, _ in (self.markers.get(symbol) or [])}
        keep = [
            index
            for index, ordinal in enumerate(ordinals)
            if (index % 2 == 0) or (ordinal in marked)
        ]
        self.series[symbol] = (
            [prices[index] for index in keep],
            [vwaps[index] for index in keep],
        )
        self.ordinals[symbol] = [ordinals[index] for index in keep]
        self.calls.append(CHART_POINTS_DECIMATED)

    def clear_data(self) -> None:
        """Drop the prices, the VWAP window, the ordinals and the markers."""
        for symbol in self.series:
            self.series[symbol] = ([], [])
            self.vwap_window[symbol] = []
            self.ordinals[symbol] = []
            self.next_ordinal[symbol] = 0
            self.markers[symbol] = self.new_marker_store()
        self.calls.append(CHART_DATA_CLEARED)


def band_program(model: "PriceVwapModel", width_px: Any) -> list:
    """Everything the stacked band view paints, band by band."""
    width = int(width_px)
    program: list = []
    for index, symbol in enumerate(model.symbols):
        band_y = index * CHART_BAND_HEIGHT_PX
        program.append(
            {
                "op": LINE,
                "pen": CHART_SEPARATOR_COLOUR,
                "width": 1,
                "style": SOLID_LINE,
                "line": [0, band_y, width, band_y],
            }
        )
        program.append(
            {
                "op": TEXT,
                "pen": CHART_SYMBOL_COLOUR,
                "rect": [
                    CHART_LABEL_INSET_PX,
                    band_y + CHART_LABEL_INSET_PX,
                    CHART_LABEL_WIDTH_PX - CHART_BAND_RIGHT_PX,
                    CHART_BAND_HEIGHT_PX - CHART_BAND_RIGHT_PX,
                ],
                "align": ALIGN_SYMBOL,
                "text": symbol,
            }
        )
        prices, vwaps = model.series.get(symbol, ([], []))
        if len(prices) < CHART_MIN_LINE_POINTS:
            continue
        plot_x = CHART_LABEL_WIDTH_PX
        plot_w = max(1, width - plot_x - CHART_BAND_RIGHT_PX)
        plot_h = CHART_BAND_HEIGHT_PX - 2 * CHART_BAND_INSET_PX
        plot_y = band_y + CHART_BAND_INSET_PX
        both = prices + vwaps
        low = min(both)
        span = band_span(low, max(both))
        count = len(prices)
        step_px = plot_w / max(count - 1, 1)

        def at(position, value):
            return (
                plot_x + int(position * step_px),
                plot_y + plot_h - int((value - low) / span * plot_h),
            )

        for colour, values in (
            (CHART_PRICE_COLOUR, prices),
            (CHART_VWAP_COLOUR, vwaps),
        ):
            previous = None
            for position, value in enumerate(values):
                point = at(position, value)
                if previous is not None:
                    program.append(
                        {
                            "op": LINE,
                            "pen": colour,
                            "width": 1,
                            "style": SOLID_LINE,
                            "line": [previous[0], previous[1], point[0], point[1]],
                        }
                    )
                previous = point
        program.append(
            {
                "op": RECT,
                "pen": CHART_FRAME_COLOUR,
                "brush": NO_BRUSH,
                "width": 1,
                "style": SOLID_LINE,
                "rect": [plot_x - 1, plot_y - 1, plot_w + 1, plot_h + 1],
            }
        )
        for position, validated in model.resolved_markers(symbol):
            if position < 0 or position >= count:
                continue
            colour = CHART_MARKER_OK_COLOUR if validated else CHART_MARKER_MISSED_COLOUR
            centre_x, centre_y = at(position, prices[position])
            program.append(
                {
                    "op": ELLIPSE,
                    "pen": colour,
                    "brush": colour,
                    "width": 1,
                    "rect": [
                        centre_x - CHART_MARKER_RADIUS_PX,
                        centre_y - CHART_MARKER_RADIUS_PX,
                        CHART_MARKER_RADIUS_PX * 2,
                        CHART_MARKER_RADIUS_PX * 2,
                    ],
                }
            )
    return program


def focused_program(model: "PriceVwapModel", width_px: Any, height_px: Any) -> list:
    """Everything the focused view paints: VWAP above, candles below."""
    width, height = int(width_px), int(height_px)
    symbol = model.focus
    bars = model.candles.get(symbol) or []
    prices, vwaps = model.series.get(symbol, ([], []))
    if not bars:
        return [
            {
                "op": TEXT,
                "pen": FOCUS_WAITING_COLOUR,
                "width": 1,
                "style": SOLID_LINE,
                "at": [FOCUS_PAD_PX, FOCUS_WAITING_Y_PX],
                "text": f"{symbol}{FOCUS_WAITING_SUFFIX}",
            }
        ]

    program: list = []
    plot_w = max(1, width - FOCUS_PAD_PX * 2)
    step = candle_step_px()
    shown = bars[-max(1, plot_w // step) :]

    top_h = max(FOCUS_MIN_BAND_PX, (height - FOCUS_HEAD_ROOM_PX - FOCUS_GAP_PX) // 2)
    bottom_y = FOCUS_TOP_Y_PX + top_h + FOCUS_GAP_PX
    bottom_h = max(FOCUS_MIN_BAND_PX, height - bottom_y - FOCUS_FOOT_ROOM_PX)
    divider_y = bottom_y - FOCUS_GAP_PX // 2
    program.append(
        {
            "op": LINE,
            "pen": CHART_SEPARATOR_COLOUR,
            "width": 1,
            "style": SOLID_LINE,
            "line": [0, divider_y, width, divider_y],
        }
    )

    window = list(vwaps[-len(shown) :]) if vwaps else []
    closes = [float(bar[4]) for bar in shown]
    readings = closes + [one for one in window if one]
    to_top = scale(min(readings), max(readings), FOCUS_TOP_Y_PX, top_h)
    program.append(
        {
            "op": TEXT,
            "pen": FOCUS_HEADING_COLOUR,
            "width": 1,
            "style": SOLID_LINE,
            "at": [FOCUS_PAD_PX, FOCUS_TOP_Y_PX - FOCUS_HEADING_LIFT_PX],
            "text": f"{symbol}{FOCUS_PRICE_HEADING_SUFFIX}",
        }
    )
    centre = CHART_CANDLE_WIDTH_PX // 2
    previous = None
    for position, close in enumerate(closes):
        point = (FOCUS_PAD_PX + position * step + centre, to_top(close))
        if previous is not None:
            program.append(
                {
                    "op": LINE,
                    "pen": FOCUS_PRICE_COLOUR,
                    "width": 1,
                    "style": SOLID_LINE,
                    "line": [previous[0], previous[1], point[0], point[1]],
                }
            )
        previous = point
    if len(window) >= CHART_MIN_LINE_POINTS:
        offset = len(shown) - len(window)
        previous = None
        for position, value in enumerate(window):
            point = (FOCUS_PAD_PX + (position + offset) * step + centre, to_top(value))
            if previous is not None:
                program.append(
                    {
                        "op": LINE,
                        "pen": FOCUS_HEADING_COLOUR,
                        "width": 2,
                        "style": SOLID_LINE,
                        "line": [previous[0], previous[1], point[0], point[1]],
                    }
                )
            previous = point
    for position, validated in model.resolved_markers(symbol):
        index = position - (len(prices) - len(shown))
        if 0 <= index < len(shown):
            program.append(
                {
                    "op": ELLIPSE,
                    "pen": (
                        FOCUS_MARKER_OK_COLOUR
                        if validated
                        else FOCUS_MARKER_MISSED_COLOUR
                    ),
                    "brush": NO_BRUSH,
                    "width": 1,
                    "rect": [
                        FOCUS_PAD_PX + index * step + centre - FOCUS_MARKER_RADIUS_PX,
                        to_top(closes[index]) - FOCUS_MARKER_RADIUS_PX,
                        FOCUS_MARKER_RADIUS_PX * 2,
                        FOCUS_MARKER_RADIUS_PX * 2,
                    ],
                }
            )

    low = min(bar[3] for bar in shown)
    high = max(bar[2] for bar in shown)
    to_bottom = scale(low, high, bottom_y, bottom_h)
    program.append(
        {
            "op": TEXT,
            "pen": FOCUS_HEADING_COLOUR,
            "width": 1,
            "style": SOLID_LINE,
            "at": [FOCUS_PAD_PX, bottom_y - FOCUS_HEADING_LIFT_PX],
            "text": FOCUS_CANDLE_HEADING,
        }
    )

    ytd_from = model.ytd_from.get(symbol)
    if ytd_from:
        first = next(
            (
                position
                for position, bar in enumerate(shown)
                if bar[0] and bar[0] >= ytd_from
            ),
            None,
        )
        if first is not None:
            start_x = FOCUS_PAD_PX + first * step
            program.append(
                {
                    "op": FILL,
                    "brush": list(FOCUS_YTD_FILL_RGBA),
                    "rect": [
                        start_x,
                        bottom_y,
                        max(0, width - FOCUS_PAD_PX - start_x),
                        bottom_h,
                    ],
                }
            )
            program.append(
                {
                    "op": LINE,
                    "pen": FOCUS_HEADING_COLOUR,
                    "width": 1,
                    "style": DASH_LINE,
                    "line": [start_x, bottom_y, start_x, bottom_y + bottom_h],
                }
            )
            program.append(
                {
                    "op": TEXT,
                    "pen": FOCUS_HEADING_COLOUR,
                    "width": 1,
                    "style": DASH_LINE,
                    "at": [
                        start_x + FOCUS_YTD_TEXT_INSET_PX,
                        bottom_y + FOCUS_YTD_TEXT_DROP_PX,
                    ],
                    "text": FOCUS_YTD_LABEL,
                }
            )

    for position, bar in enumerate(shown):
        _stamp, opened, highest, lowest, close = bar
        left = FOCUS_PAD_PX + position * step
        colour = FOCUS_CANDLE_UP_COLOUR if close >= opened else FOCUS_CANDLE_DOWN_COLOUR
        program.append(
            {
                "op": LINE,
                "pen": colour,
                "width": 1,
                "style": SOLID_LINE,
                "line": [
                    left + centre,
                    to_bottom(highest),
                    left + centre,
                    to_bottom(lowest),
                ],
            }
        )
        open_y, close_y = to_bottom(opened), to_bottom(close)
        program.append(
            {
                "op": FILL,
                "brush": colour,
                "rect": [
                    left,
                    min(open_y, close_y),
                    CHART_CANDLE_WIDTH_PX,
                    max(1, abs(close_y - open_y)),
                ],
            }
        )

    for at_point, text in (
        ([FOCUS_PAD_PX, height - FOCUS_BASELINE_PX], FOCUS_PRICE_FORMAT.format(low)),
        (
            [
                width - FOCUS_PAD_PX - FOCUS_HIGH_LABEL_INSET_PX,
                height - FOCUS_BASELINE_PX,
            ],
            FOCUS_PRICE_FORMAT.format(high),
        ),
        (
            [
                width - FOCUS_PAD_PX - FOCUS_BARS_LABEL_INSET_PX,
                FOCUS_TOP_Y_PX + FOCUS_BARS_LABEL_DROP_PX,
            ],
            f"{len(shown)}/{len(bars)}{FOCUS_BARS_SUFFIX}",
        ),
    ):
        program.append(
            {
                "op": TEXT,
                "pen": FOCUS_AXIS_COLOUR,
                "width": 1,
                "style": SOLID_LINE,
                "at": at_point,
                "text": text,
            }
        )
    return program


def chart_program(model: "PriceVwapModel", width_px: Any, height_px: Any) -> list:
    """The chart's whole draw program: one focused view, or every band.

    A chart tracking no symbol paints nothing at all.
    """
    if not model.symbols:
        return []
    if model.focus:
        return focused_program(model, width_px, height_px)
    return band_program(model, width_px)


# PerBotVotingReadout -- one row per bot, the voting summary

VOTE_COLUMNS = ("Symbol", "Net", "Conf", "Bull", "Bear", "Direction")
VOTE_PLACEHOLDER = "—"

VOTE_ACCESSIBLE_NAME = "Per-Bot Voting Readout"
VOTE_ACCESSIBLE_DESCRIPTION = (
    "One row per simulated bot. Columns show the bot's "
    "latest voting-engine summary — Net score, "
    "consensus confidence, bullish/bearish indicator "
    "counts, and derived direction."
)
VOTE_TOOLTIP = (
    "Sim bot voting summary — Net > +0.1 = BULL, " "< -0.1 = BEAR, otherwise NEUT."
)
VOTE_STYLE = (
    "QTableWidget{background:#0a0a14;color:#ccccdd;"
    "font-family:'Cascadia Code','Consolas',monospace;"
    "font-size:11px;border:1px solid #2a2a44;}"
    "QHeaderView::section{background:#1a1a2a;"
    "color:#00ffcc;padding:4px;border:none;}"
)

VOTE_ALTERNATE_ROW_COLOUR = "#181822"
VOTE_ROW_HEIGHT_PX = 30
VOTE_HEADER_HEIGHT_PX = 32

VOTE_EDIT_TRIGGERS = "NoEditTriggers"
VOTE_SELECTION_BEHAVIOUR = "SelectRows"
VOTE_ALTERNATING_ROWS = True
VOTE_ROW_HEADER_VISIBLE = False
VOTE_COLUMN_MODE = "Stretch"
VOTE_SYMBOL_COLUMN_MODE = "ResizeToContents"
VOTE_STRETCH_LAST_COLUMN = True

VOTE_BULL_ABOVE = 0.1
VOTE_BEAR_BELOW = -0.1
VOTE_BULL = "BULL"
VOTE_BEAR = "BEAR"
VOTE_NEUTRAL = "NEUT"
VOTE_BULL_COLOUR = "#00cc55"
VOTE_BEAR_COLOUR = "#ff3366"
VOTE_NEUTRAL_COLOUR = "#888"
VOTE_NET_FORMAT = "{:+.2f}"
VOTE_CONF_FORMAT = "{:.2f}"
VOTE_COUNT_FORMAT = "{}"

VOTE_DIRECTION_COLOURS = {
    VOTE_BULL: VOTE_BULL_COLOUR,
    VOTE_BEAR: VOTE_BEAR_COLOUR,
    VOTE_NEUTRAL: VOTE_NEUTRAL_COLOUR,
}

VOTE_BOTS_SET = "vote_bots_set"
VOTE_ROW_WRITTEN = "vote_row_written"
VOTE_ROW_UNKNOWN = "vote_row_unknown"
VOTE_ROW_REFUSED = "vote_row_refused"

VOTE_CALL_NAMES = (
    VOTE_BOTS_SET,
    VOTE_ROW_WRITTEN,
    VOTE_ROW_UNKNOWN,
    VOTE_ROW_REFUSED,
)


def cell_text(value: Any) -> str:
    """The text one table cell shows for `value`.

    A cell is built from text. A whole number reaches the cell's own kind
    instead of its text and shows nothing, so anything that is not text
    shows nothing.
    """
    return value if isinstance(value, str) else ""


def vote_direction(net_score: float) -> str:
    """Which way a net score points: bull, bear or neutral."""
    if net_score > VOTE_BULL_ABOVE:
        return VOTE_BULL
    if net_score < VOTE_BEAR_BELOW:
        return VOTE_BEAR
    return VOTE_NEUTRAL


def blank_row(symbol: Any) -> list:
    """One row as the table builds it, before any summary arrives."""
    return [cell_text(symbol)] + [VOTE_PLACEHOLDER] * (len(VOTE_COLUMNS) - 1)


class VotingReadoutModel:
    """The voting table's rows between refreshes, with no Qt behind it.

    A summary whose counts cannot be read as whole numbers leaves the row
    as it was rather than half-writing it.
    """

    def __init__(self) -> None:
        self.rows: list = []
        self.colours: list = []
        self.row_for: dict = {}
        self.calls: list = []

    def set_bots(self, symbols: Any) -> None:
        """One row per symbol, every value at the placeholder."""
        self.rows = []
        self.colours = []
        self.row_for = {}
        for index, symbol in enumerate(symbols):
            self.row_for[symbol] = index
            self.rows.append(blank_row(symbol))
            self.colours.append(None)
        self.calls.append(VOTE_BOTS_SET)

    def update_bot_row(self, symbol: Any, summary: Any) -> None:
        """Write one bot's latest voting summary into its row."""
        index = self.row_for.get(symbol)
        if index is None or summary is None:
            self.calls.append(VOTE_ROW_UNKNOWN)
            return
        try:
            net = float(getattr(summary, "net_score", 0.0))
            confidence = float(getattr(summary, "consensus_confidence", 0.0))
            bullish = int(getattr(summary, "bullish_count", 0))
            bearish = int(getattr(summary, "bearish_count", 0))
        except (TypeError, ValueError):
            self.calls.append(VOTE_ROW_REFUSED)
            return
        direction = vote_direction(net)
        row = self.rows[index]
        row[1] = VOTE_NET_FORMAT.format(net)
        row[2] = VOTE_CONF_FORMAT.format(confidence)
        row[3] = VOTE_COUNT_FORMAT.format(bullish)
        row[4] = VOTE_COUNT_FORMAT.format(bearish)
        row[5] = direction
        self.colours[index] = VOTE_DIRECTION_COLOURS[direction]
        self.calls.append(VOTE_ROW_WRITTEN)

    def table(self) -> list:
        """Every row, with the colour its direction cell paints in."""
        return [
            {"cells": list(row), "direction_colour": self.colours[index]}
            for index, row in enumerate(self.rows)
        ]


# The whole screen

ACTIONS = {"dialog_finished": "ExpandModel.close"}
TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()
BUS_EMITS: tuple = ()
SIGNALS: tuple = ()

CALL_NAMES = (
    EXPAND_CALL_NAMES
    + (GATES_UPDATED, GATES_CLEARED, PANEL_LOADED, PANEL_EMPTIED)
    + CHART_CALL_NAMES
    + VOTE_CALL_NAMES
)


def build_view_model(
    panel: Optional["GatePanelModel"] = None,
    chart: Optional["PriceVwapModel"] = None,
    votes: Optional["VotingReadoutModel"] = None,
    expand: Optional["ExpandModel"] = None,
    width_px: int = 0,
    height_px: int = 0,
    gate_pitch: int = 0,
) -> dict:
    """Return every panel's state as one serialisable dict."""
    panel = GatePanelModel() if panel is None else panel
    chart = PriceVwapModel() if chart is None else chart
    votes = VotingReadoutModel() if votes is None else votes
    expand = ExpandModel() if expand is None else expand
    pitch = int(gate_pitch) or gate_pitch_px(GATE_LED_PX)
    return {
        "method": METHOD,
        "gate_panel": {
            "accessible_name": PANEL_ACCESSIBLE_NAME,
            "margins_px": list(PANEL_MARGINS_PX),
            "spacing_px": PANEL_SPACING_PX,
            "scroll_style": PANEL_SCROLL_STYLE,
            "scroll_resizable": PANEL_SCROLL_RESIZABLE,
            "host_margins_px": list(PANEL_HOST_MARGINS_PX),
            "host_spacing_px": PANEL_HOST_SPACING_PX,
            "empty_text": PANEL_EMPTY_TEXT,
            "empty_style": PANEL_EMPTY_STYLE,
            "empty_visible": panel.empty_visible,
            "row_margins_px": list(PANEL_ROW_MARGINS_PX),
            "row_spacing_px": PANEL_ROW_SPACING_PX,
            "label_min_width_px": PANEL_LABEL_MIN_WIDTH_PX,
            "label_style": PANEL_LABEL_STYLE,
            "trailing_stretch": PANEL_TRAILING_STRETCH,
            "items": panel.items(),
            "symbols": panel.symbols(),
        },
        "gate_row": {
            "tooltip": GATE_TOOLTIP,
            "font_pt": GATE_FONT_PT,
            "pitch_px": pitch,
            "height_px": gate_cell_height_px(),
            "min_width_px": gate_cell_min_width_px(pitch),
            "banks": {name: list(GATE_ORDER[name]) for name in GATE_BANKS},
            "label_colour": GATE_LABEL_COLOUR,
            "marker_colour": GATE_MARKER_COLOUR,
            "light_colours": dict(LIGHT_COLOURS_BY_STATE),
            "rows": {
                row.symbol: {
                    "lights": row.lights.lights(),
                    "program": gate_program(row.lights, pitch),
                }
                for row in panel.built
            },
        },
        "chart": {
            "accessible_name": CHART_ACCESSIBLE_NAME,
            "accessible_description": CHART_ACCESSIBLE_DESCRIPTION,
            "tooltip": CHART_TOOLTIP,
            "style_sheet": CHART_STYLE,
            "size_policy": list(CHART_SIZE_POLICY),
            "band_height_px": CHART_BAND_HEIGHT_PX,
            "label_width_px": CHART_LABEL_WIDTH_PX,
            "max_points": CHART_MAX_POINTS,
            "vwap_window": CHART_VWAP_WINDOW,
            "max_markers": CHART_MAX_MARKERS,
            "max_candles": CHART_MAX_CANDLES,
            "candle_width_px": CHART_CANDLE_WIDTH_PX,
            "candle_gap_px": CHART_CANDLE_GAP_PX,
            "focus_min_height_px": CHART_FOCUS_MIN_HEIGHT_PX,
            "minimum_height_px": chart.height_px,
            "focus": chart.focus_symbol(),
            "symbols": list(chart.symbols),
            "program": chart_program(chart, width_px, height_px),
        },
        "votes": {
            "accessible_name": VOTE_ACCESSIBLE_NAME,
            "accessible_description": VOTE_ACCESSIBLE_DESCRIPTION,
            "tooltip": VOTE_TOOLTIP,
            "style_sheet": VOTE_STYLE,
            "columns": list(VOTE_COLUMNS),
            "edit_triggers": VOTE_EDIT_TRIGGERS,
            "selection_behaviour": VOTE_SELECTION_BEHAVIOUR,
            "alternating_rows": VOTE_ALTERNATING_ROWS,
            "alternate_row_colour": VOTE_ALTERNATE_ROW_COLOUR,
            "row_height_px": VOTE_ROW_HEIGHT_PX,
            "header_height_px": VOTE_HEADER_HEIGHT_PX,
            "row_header_visible": VOTE_ROW_HEADER_VISIBLE,
            "column_mode": VOTE_COLUMN_MODE,
            "symbol_column_mode": VOTE_SYMBOL_COLUMN_MODE,
            "stretch_last_column": VOTE_STRETCH_LAST_COLUMN,
            "placeholder": VOTE_PLACEHOLDER,
            "rows": votes.table(),
        },
        "expand": {
            "style_sheet": EXPAND_STYLE,
            "margins_px": list(EXPAND_MARGINS_PX),
            "claim_field": EXPAND_CLAIM_FIELD,
            "delete_on_close": EXPAND_DELETE_ON_CLOSE,
            "open": expand.claim is not None,
        },
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "bus_emits": list(BUS_EMITS),
        "signals": list(SIGNALS),
        "call_names": list(CALL_NAMES),
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``sim_visuals.state``.

    Loads the fleet the request names, takes the gate readings and the
    ticks it carries, and returns every panel's state.
    """
    asked = params or {}
    symbols = list(asked.get("symbols") or [])
    panel = GatePanelModel()
    panel.set_symbols(symbols)
    chart = PriceVwapModel()
    chart.set_symbols(symbols)
    votes = VotingReadoutModel()
    votes.set_bots(symbols)
    for reading in asked.get("gates") or []:
        row = panel.cell_for(reading.get("symbol"))
        if row is not None:
            row.update_gates(
                reading.get("scrum_armed"),
                reading.get("fold_armed"),
                reading.get("scrum_blockers"),
                reading.get("fold_blockers"),
                reading.get("landing_strip_side", ""),
            )
    for tick in asked.get("ticks") or []:
        chart.append_tick(
            tick.get("symbol"),
            tick.get("close"),
            tick.get("volume"),
            tick.get("ts"),
            tick.get("open"),
            tick.get("high"),
            tick.get("low"),
        )
    focus = asked.get("focus")
    if focus is not None:
        chart.set_focus_symbol(focus)
    return build_view_model(
        panel=panel,
        chart=chart,
        votes=votes,
        width_px=int(asked.get("width_px") or 0),
        height_px=int(asked.get("height_px") or 0),
        gate_pitch=int(asked.get("gate_pitch_px") or 0),
    )
