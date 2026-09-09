# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""QPainter candlestick chart widgets.

``CandlestickChart`` paints candles, a volume strip, price grid lines,
position markers and a crosshair without a WebEngine dependency.
``ChartPanel`` wraps it with a timeframe selector and one checkbox per
indicator overlay. ``Candle``, ``TradeMarker``, ``PositionMarker`` and
``GridLine`` are the records it draws from.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.gui.theme_engine import CYBERPUNK_DARK
from src.trading.ta_engine import (
    BollingerBands,
    IchimokuCloud,
    MACD,
    StochasticRSI,
    VortexIndicator,
)

logger = logging.getLogger("acervator.gui")

# Fraction of one grid step the last price tick may overshoot by and still draw.
GRID_TICK_TOLERANCE = 1e-9

try:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QComboBox,
        QCheckBox,
    )
    from PySide6.QtCore import Qt, QRectF, QPointF, Signal
    from PySide6.QtGui import (
        QPainter,
        QPen,
        QBrush,
        QColor,
        QFont,
        QFontMetrics,
        QGuiApplication,
        QImage,
        QLinearGradient,
        QPolygonF,
    )

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


@dataclass
class Candle:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class TradeMarker:
    time: int
    side: str  # "buy" or "sell"
    price: float
    label: str = ""


@dataclass
class PositionMarker:
    """Active position shown on chart with visibility mode icon."""

    price: float
    side: str  # "buy" or "sell"
    visibility: str  # "internal" (invisible) or "orderbook" (visible)
    level: int = 0
    filled: bool = False
    asset_held: float = 0.0


@dataclass
class GridLine:
    price: float
    side: str
    label: str = ""


PRICE_PANE = "price"
SUB_PANE = "sub"
VOLUME_PANE = "volume"


@dataclass(frozen=True)
class ChartOverlay:
    """One indicator ``CandlestickChart`` draws and ``ChartPanel`` offers.

    ``colour_field`` names the ``ThemeTokens`` field its label colour comes from,
    ``pane`` is where it paints, and ``draw`` names the method that paints it.
    The pane fixes what ``draw`` is handed: ``PRICE_PANE`` takes one
    ``PaintContext``, ``SUB_PANE`` takes one and its top and bottom, and
    ``VOLUME_PANE`` takes the painter, both edges and the strip's top.
    ``voter`` is the ``ta_engine`` indicator whose reading this overlay draws,
    empty where the overlay draws no voter.
    """

    key: str
    label: str
    colour_field: str
    pane: str
    occludes: bool
    draw: str
    tooltip: str
    voter: str = ""

    @property
    def starts_on(self) -> bool:
        """An overlay starts on unless it paints a fill over the price pane."""
        return not self.occludes


#: Every overlay the chart can draw. Append one entry and one draw method to
#: add another; nothing else in this file enumerates them.
CHART_OVERLAYS: tuple[ChartOverlay, ...] = (
    ChartOverlay(
        key="bb",
        label="BB",
        colour_field="chart_band",
        pane=PRICE_PANE,
        occludes=False,
        draw="_draw_bollinger",
        tooltip="Bollinger Bands (20, 2σ) with cloud fill",
        voter="bollinger_bands",
    ),
    ChartOverlay(
        key="vortex",
        label="Vortex",
        colour_field="chart_bull",
        pane=SUB_PANE,
        occludes=False,
        draw="_draw_vortex",
        tooltip="Vortex Indicator (VI+ / VI-, period 14, sub-pane)",
        voter="vortex",
    ),
    ChartOverlay(
        key="macd",
        label="MACD",
        colour_field="chart_trend_fast",
        pane=SUB_PANE,
        occludes=False,
        draw="_draw_macd",
        tooltip="MACD line and signal, 12/26/9, sub-pane",
        voter="macd",
    ),
    ChartOverlay(
        key="stochrsi",
        label="SRsi",
        colour_field="chart_oscillator",
        pane=SUB_PANE,
        occludes=False,
        draw="_draw_stochrsi",
        tooltip="Stochastic RSI (14/14), 0..1 oscillator, sub-pane",
        voter="stochastic_rsi",
    ),
    ChartOverlay(
        key="ichimoku",
        label="Ichi",
        colour_field="chart_trend_slow",
        pane=PRICE_PANE,
        occludes=False,
        draw="_draw_ichimoku",
        tooltip="Ichimoku Cloud: Tenkan, Kijun, Span A, Span B, shift +26",
        voter="ichimoku",
    ),
    ChartOverlay(
        key="volume",
        label="Vol",
        colour_field="chart_axis_text",
        pane=VOLUME_PANE,
        occludes=False,
        draw="_draw_volume",
        tooltip="Volume bars (bottom strip)",
        voter="volume",
    ),
    ChartOverlay(
        key="slingshot",
        label="Sling",
        colour_field="chart_event_mark",
        pane=PRICE_PANE,
        occludes=True,
        draw="_draw_slingshot",
        tooltip=(
            "Slingshot marks — diamond at a Bollinger squeeze release, "
            "circle at a snapback. Opaque marks sit over the bands, so it "
            "starts off."
        ),
        voter="slingshot",
    ),
    ChartOverlay(
        key="bbullseye",
        label="BBull",
        colour_field="chart_zone_fold",
        pane=PRICE_PANE,
        occludes=True,
        draw="_draw_bullseye",
        tooltip=(
            "BB Bullseye zones — shaded ±0.5% and ±0.2% envelopes "
            "on the Bollinger bands. The fill covers the bands, so it starts off."
        ),
    ),
)

#: The overlay keys, in the order the toolbar offers them.
OVERLAY_KEYS: tuple[str, ...] = tuple(one.key for one in CHART_OVERLAYS)


#: The width in pixels ``render_chart_png`` draws a post image at.
POST_IMAGE_WIDTH_PX = 1200

#: ``max_overlays`` at or under this draws every overlay the voters name.
NO_OVERLAY_CAP = 0

NO_QT_NOTE = "PySide6 is not installed; no image drawn."
NO_APPLICATION_NOTE = "No Qt application running; no image drawn."
NO_CANDLES_NOTE = "No candles read for {symbol} on {timeframe}."
NOT_DRAWN_NOTE = "not drawn: {voters}"
IMAGE_NOT_WRITTEN_NOTE = "Qt refused to write {path}."

CALL_BULLISH = "bullish"
CALL_BEARISH = "bearish"

#: The palette role ``_draw_call`` paints one reversal direction in. A
#: direction outside these two draws no badge and no bar mark.
CALL_DIRECTION_ROLES = {CALL_BULLISH: "EVENT_BULL", CALL_BEARISH: "EVENT_BEAR"}

CALL_BADGE_FORMAT = "{direction} REVERSAL"

#: The pixel height one ``set_call`` reading takes in the strip under the
#: time axis, and the padding over and under those rows.
CALL_ROW_H = 15
CALL_STRIP_PAD = 8

#: The square each strip row draws its voter's overlay colour in.
CALL_SWATCH_PX = 8

#: The half-width and height of the triangle marking the call bar's close.
CALL_MARK_PX = 6

#: No ``set_call`` reading, so ``_call_strip_h`` takes no height.
NO_CALL_STRIP = 0


@dataclass
class ChartImage:
    """One rendered chart on disk, and what the renderer could not draw.

    ``drawn`` and ``undrawn`` name voters: ``undrawn`` holds the ones no
    overlay draws and the ones ``max_overlays`` cut.
    """

    path: str = ""
    width_px: int = 0
    height_px: int = 0
    bars: int = 0
    drawn: tuple = ()
    undrawn: tuple = ()
    note: str = ""


def overlays_for_voters(voters, max_overlays: int = NO_OVERLAY_CAP) -> tuple:
    """The overlay keys drawing ``voters``, and the voters no overlay draws.

    Registry order decides which survive ``max_overlays``, and a cap at or
    under ``NO_OVERLAY_CAP`` keeps every match.
    """
    named = [str(one) for one in voters or []]
    matched = [one.key for one in CHART_OVERLAYS if one.voter and one.voter in named]
    drawn = matched[:max_overlays] if max_overlays > NO_OVERLAY_CAP else matched
    by_key = {one.key: one.voter for one in CHART_OVERLAYS}
    reached = {by_key[key] for key in drawn}
    return tuple(drawn), tuple(one for one in named if one not in reached)


def overlays_on(chart, pane: str) -> tuple[ChartOverlay, ...]:
    """Every overlay of ``pane`` switched on in ``chart._overlay_shown``."""
    shown = getattr(chart, "_overlay_shown", {})
    return tuple(
        one for one in CHART_OVERLAYS if one.pane == pane and shown.get(one.key, False)
    )


if _HAS_QT:

    #: The theme a chart paints in until ``set_theme`` names another.
    DEFAULT_THEME_TOKENS = CYBERPUNK_DARK

    def _role_colour(tokens, field: str, alpha: int) -> QColor:
        """One ``ThemeTokens`` field as a ``QColor`` carrying ``alpha``."""
        colour = QColor(getattr(tokens, field))
        colour.setAlpha(alpha)
        return colour

    def _with_alpha(colour: QColor, alpha: int) -> QColor:
        """A copy of one palette colour at ``alpha``, for a gradient stop."""
        faded = QColor(colour)
        faded.setAlpha(alpha)
        return faded

    @dataclass
    class PaintContext:
        """The geometry of one paint pass, handed to every overlay method.

        ``i2x`` maps a visible index to a pixel and ``p2y`` maps a price to one.
        """

        p: object
        w: int
        ML: int
        MR: int
        price_top: float
        price_bot: float
        n: int
        cw: float
        gap: float
        bw: float
        v_start: int
        v_end: int
        visible_candles: list
        i2x: object
        p2y: object
        fm: object
        font_sm: object
        draw_line_series: object
        paint_sub_grid: object = None
        sub_axis_label: object = None
        paint_oscillator: object = None

    class ChartPainter:
        """The chart's drawing state and ``paint_to``, with no window behind it.

        ``paint_to`` takes any ``QPainter`` and a size, so ``CandlestickChart``
        paints onto a widget and ``render_chart_png`` onto a ``QImage``. Every
        colour resolves from a ``ThemeTokens`` field through ``PALETTE_ROLES``.
        """

        # Every colour a paint method reads. ``resolve_palette`` and
        # ``set_theme`` fill them from ``PALETTE_ROLES``.
        BG_TOP: QColor
        BG_BOT: QColor
        GRID_MAJOR: QColor
        GRID_MINOR: QColor
        TEXT_DIM: QColor
        TEXT_LIGHT: QColor
        ACCENT: QColor
        UP_FILL: QColor
        UP_BORDER: QColor
        DOWN_FILL: QColor
        DOWN_BORDER: QColor
        UP_WICK: QColor
        DOWN_WICK: QColor
        VOL_UP: QColor
        VOL_DOWN: QColor
        VOL_UP_BORDER: QColor
        VOL_DOWN_BORDER: QColor
        CROSSHAIR_COLOR: QColor
        PRICE_LINE_COLOR: QColor
        BUY_POS_COLOR: QColor
        SELL_POS_COLOR: QColor
        INVISIBLE_ICON: QColor
        VISIBLE_ICON: QColor
        BAND_LINE: QColor
        BAND_FILL: QColor
        BAND_MID: QColor
        CLOUD_BULL: QColor
        CLOUD_BEAR: QColor
        SPAN_A_LINE: QColor
        SPAN_B_LINE: QColor
        TENKAN_LINE: QColor
        KIJUN_LINE: QColor
        CHIKOU_LINE: QColor
        ZONE_SCRUM_TOUCH: QColor
        ZONE_SCRUM_WICK: QColor
        ZONE_FOLD_TOUCH: QColor
        ZONE_FOLD_WICK: QColor
        EVENT_BULL: QColor
        EVENT_BEAR: QColor
        SUB_PANE_WASH: QColor
        MACD_LINE: QColor
        MACD_SIGNAL: QColor
        HIST_UP: QColor
        HIST_UP_EDGE: QColor
        HIST_DOWN: QColor
        HIST_DOWN_EDGE: QColor
        VORTEX_PLUS: QColor
        VORTEX_MINUS: QColor
        OSC_LINE: QColor
        GAP_MARK: QColor
        MARKER_SCRUM: QColor
        MARKER_FOLD: QColor
        MARKER_DIST: QColor
        MARKER_BUY: QColor
        MARKER_SELL: QColor
        FLOOR_LINE: QColor
        TB_ANCHOR: QColor
        TB_CEILING: QColor
        GLOW_SCRUM: QColor
        GLOW_FOLD: QColor
        BADGE_SURFACE: QColor
        BADGE_EDGE: QColor
        MARKER_EDGE: QColor
        GRIP: QColor
        ERROR_TEXT: QColor

        #: Each painted colour, as the theme field it reads and its alpha byte.
        PALETTE_ROLES: dict[str, tuple[str, int]] = {
            "BG_TOP": ("chart_bg_top", 255),
            "BG_BOT": ("chart_bg_bottom", 255),
            "GRID_MAJOR": ("chart_grid", 255),
            "GRID_MINOR": ("chart_grid", 150),
            "TEXT_DIM": ("chart_axis_text", 130),
            "TEXT_LIGHT": ("chart_axis_text", 255),
            "ACCENT": ("accent_primary", 255),
            "UP_FILL": ("chart_up", 255),
            "UP_BORDER": ("chart_up_edge", 255),
            "DOWN_FILL": ("chart_down", 255),
            "DOWN_BORDER": ("chart_down_edge", 255),
            "UP_WICK": ("chart_up", 220),
            "DOWN_WICK": ("chart_down", 220),
            "VOL_UP": ("chart_up", 60),
            "VOL_DOWN": ("chart_down", 60),
            "VOL_UP_BORDER": ("chart_up", 100),
            "VOL_DOWN_BORDER": ("chart_down", 100),
            "CROSSHAIR_COLOR": ("chart_crosshair", 160),
            "PRICE_LINE_COLOR": ("chart_last_price", 200),
            "BUY_POS_COLOR": ("chart_bull", 255),
            "SELL_POS_COLOR": ("chart_bear", 255),
            "INVISIBLE_ICON": ("chart_trend_fast", 255),
            "VISIBLE_ICON": ("chart_trend_slow", 255),
            "BAND_LINE": ("chart_band", 200),
            "BAND_FILL": ("chart_band", 32),
            "BAND_MID": ("chart_band_mid", 160),
            "CLOUD_BULL": ("chart_bull", 50),
            "CLOUD_BEAR": ("chart_bear", 50),
            "SPAN_A_LINE": ("chart_bull", 200),
            "SPAN_B_LINE": ("chart_bear", 200),
            "TENKAN_LINE": ("chart_trend_fast", 220),
            "KIJUN_LINE": ("chart_trend_slow", 220),
            "CHIKOU_LINE": ("chart_axis_text", 180),
            "ZONE_SCRUM_TOUCH": ("chart_zone_scrum", 55),
            "ZONE_SCRUM_WICK": ("chart_zone_scrum", 95),
            "ZONE_FOLD_TOUCH": ("chart_zone_fold", 55),
            "ZONE_FOLD_WICK": ("chart_zone_fold", 95),
            "EVENT_BULL": ("chart_bull", 230),
            "EVENT_BEAR": ("chart_bear", 230),
            "SUB_PANE_WASH": ("chart_bg_top", 150),
            "MACD_LINE": ("chart_trend_fast", 230),
            "MACD_SIGNAL": ("chart_trend_slow", 220),
            "HIST_UP": ("chart_up", 160),
            "HIST_UP_EDGE": ("chart_up_edge", 200),
            "HIST_DOWN": ("chart_down", 160),
            "HIST_DOWN_EDGE": ("chart_down_edge", 200),
            "VORTEX_PLUS": ("chart_bull", 230),
            "VORTEX_MINUS": ("chart_bear", 230),
            "OSC_LINE": ("chart_oscillator", 230),
            "GAP_MARK": ("chart_gap", 200),
            "MARKER_SCRUM": ("chart_last_price", 255),
            "MARKER_FOLD": ("chart_trend_slow", 255),
            "MARKER_DIST": ("chart_event_mark", 255),
            "MARKER_BUY": ("chart_bull", 255),
            "MARKER_SELL": ("chart_bear", 255),
            "FLOOR_LINE": ("chart_last_price", 180),
            "TB_ANCHOR": ("chart_trend_slow", 200),
            "TB_CEILING": ("chart_zone_scrum", 220),
            "GLOW_SCRUM": ("chart_bull", 220),
            "GLOW_FOLD": ("chart_bear", 220),
            "BADGE_SURFACE": ("chart_bg_top", 235),
            "BADGE_EDGE": ("chart_grid", 255),
            "MARKER_EDGE": ("chart_axis_text", 120),
            "GRIP": ("chart_axis_text", 110),
            "ERROR_TEXT": ("chart_bear", 255),
        }

        TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"]

        def set_theme(self, tokens) -> None:
            """Re-resolve every ``PALETTE_ROLES`` colour from ``tokens``.

            The instance values shadow the class ones, so the chart repaints in
            the theme without any other object holding a colour.
            """
            self._theme_tokens = tokens
            for role, (field, alpha) in self.PALETTE_ROLES.items():
                setattr(self, role, _role_colour(tokens, field, alpha))
            self._repaint()

        def overlay_colour(self, overlay: ChartOverlay) -> QColor:
            """The colour one overlay's label and check box carry."""
            return _role_colour(self._theme_tokens, overlay.colour_field, 255)

        def _repaint(self) -> None:
            """Ask the host to redraw. A painter with no window has none."""
            return None

        def __init__(self, symbol: str = ""):
            self._theme_tokens = DEFAULT_THEME_TOKENS
            self._symbol = symbol
            self._candles: list[Candle] = []
            self._markers: list[TradeMarker] = []
            self._positions: list[PositionMarker] = []
            self._grid_lines: list[GridLine] = []
            self._current_tf = "1h"
            self._mouse_x: Optional[int] = None
            self._mouse_y: Optional[int] = None
            self._status_text = "Waiting for data..."
            self._source_label = ""
            self._error_text = ""
            self._call_direction = ""
            self._call_readings: tuple = ()
            self._overlay_shown: dict[str, bool] = {
                one.key: one.starts_on for one in CHART_OVERLAYS
            }
            self._bb_data: list[tuple] = []  # [(upper, middle, lower), ...]
            self._vortex_data: list[tuple] = []  # [(vi_plus, vi_minus), ...]
            self._macd_data: list[tuple] = []  # [(macd, signal, hist), ...]
            self._stochrsi_data: list[float] = []
            self._ichimoku_data: list[tuple] = (
                []
            )  # [(tenkan, kijun, span_a, span_b, chikou), ...]
            self._slingshot_data: list = []
            self._bbullseye_data: list = []
            self._tranche_floors: list[tuple] = []  # [(price, label), ...]

            self._tb_anchor_price: Optional[float] = None
            self._tb_ceiling_price: Optional[float] = None
            self._fire_armed_state: dict = {
                "scrum_armed": False,
                "fold_armed": False,
                "scrum_blockers": [],
                "fold_blockers": [],
            }

            # The grip band the paint routine draws along the bottom edge.
            self._resize_grip_h = 8

            # None on either bound fits all candles; _y_zoom_pct scales price padding.
            self._visible_start: Optional[int] = None
            self._visible_count: Optional[int] = None
            self._y_zoom_pct: float = 1.0

        @property
        def symbol(self) -> str:
            return self._symbol

        @symbol.setter
        def symbol(self, value: str):
            self._symbol = value
            self._repaint()

        def set_candles(self, candles: list[Candle]) -> None:
            self._candles = candles
            self._error_text = ""
            if candles:
                self._status_text = f"{len(candles)} candles"
                self._compute_indicators()
            self._repaint()

        def set_source_label(self, source: str) -> None:
            self._source_label = source
            self._repaint()

        def set_error(self, msg: str) -> None:
            self._error_text = msg
            self._repaint()

        def set_call(self, direction: str, readings=()) -> None:
            """Take one reversal direction and one reading line per voter.

            ``readings`` are ``(voter, text)`` pairs and ``_draw_call`` paints
            them under the time axis.
            """
            self._call_direction = str(direction or "")
            self._call_readings = tuple(
                (str(voter), str(text)) for voter, text in readings or ()
            )
            self._repaint()

        def _call_strip_h(self) -> int:
            """The pixel height ``_call_readings`` takes under the time axis."""
            if not self._call_readings:
                return NO_CALL_STRIP
            return CALL_STRIP_PAD * 2 + CALL_ROW_H * len(self._call_readings)

        def _voter_colour(self, voter: str) -> QColor:
            """The colour of the switched-on overlay drawing ``voter``.

            A voter no ``CHART_OVERLAYS`` entry draws reads ``TEXT_DIM``.
            """
            for one in CHART_OVERLAYS:
                if one.voter == voter and self._overlay_shown.get(one.key, False):
                    return self.overlay_colour(one)
            return self.TEXT_DIM

        def _compute_indicators(self):
            """Fill ``_bb_data``, ``_vortex_data``, ``_macd_data``,
            ``_stochrsi_data`` and ``_ichimoku_data`` from the engine
            classes. A ``None`` entry marks a candle with no value, and
            ``paintEvent`` skips it.
            """
            candles = self._candles
            self._bb_data = BollingerBands(20, 2.0).bands(candles)
            vi_plus, vi_minus = VortexIndicator(14).lines(candles)
            self._vortex_data = [
                None if (p is None or m is None) else (p, m)
                for p, m in zip(vi_plus, vi_minus)
            ]
            macd_line, signal_line, histogram = MACD(12, 26, 9).lines(candles)
            self._macd_data = [
                None if (ln is None or sg is None or hi is None) else (ln, sg, hi)
                for ln, sg, hi in zip(macd_line, signal_line, histogram)
            ]
            self._stochrsi_data = StochasticRSI().lines(candles)
            # IchimokuCloud returns unshifted series; paintEvent shifts them 26 bars.
            self._ichimoku_data = IchimokuCloud(9, 26, 52).lines(candles)

        def add_marker(self, marker: TradeMarker) -> None:
            self._markers.append(marker)
            self._repaint()

        def set_trade_history_markers(self, trades: list[dict]) -> None:
            """Replace ``_markers`` with one ``TradeMarker`` per trade dict.

            Each dict carries ``ts`` or ``time``, ``side``, ``price``
            and ``role`` or ``label``; a dict without a positive ``ts``
            or a positive ``price`` is dropped.
            """
            self._markers = []
            for t in trades:
                try:
                    ts = int(t.get("ts", t.get("time", 0)) or 0)
                    price = float(t.get("price", 0) or 0)
                    if ts <= 0 or price <= 0:
                        continue
                    m = TradeMarker(
                        time=ts,
                        side=str(t.get("side", "buy")),
                        price=price,
                        label=str(t.get("role", t.get("label", "FOLD"))),
                    )
                    self._markers.append(m)
                except (TypeError, ValueError, KeyError):
                    continue
            self._repaint()

        def set_tranche_floors(self, floors: list[tuple]) -> None:
            """Set ``_tranche_floors`` from (price, label) tuples.

            Each price is a lot's ``initial_buy_price``, the level below
            which that lot does not fold.
            """
            self._tranche_floors = list(floors)
            self._repaint()

        def set_positions(self, positions: list[PositionMarker]) -> None:
            self._positions = positions
            self._repaint()

        def set_grid_lines(self, lines: list[GridLine]) -> None:
            self._grid_lines = lines
            self._repaint()

        def set_target_balance_lines(
            self, anchor_price: Optional[float], ceiling_price: Optional[float]
        ) -> None:
            """Set ``_tb_anchor_price`` and ``_tb_ceiling_price``, the
            two dashed lines on the price pane.

            ``TradeChartsTab.update_charts`` divides the USD anchor and
            ceiling by holdings and the quote rate; ``None`` hides that
            line.
            """
            self._tb_anchor_price = anchor_price
            self._tb_ceiling_price = ceiling_price
            self._repaint()

        def set_fire_armed_state(
            self,
            scrum_armed: bool,
            fold_armed: bool,
            scrum_blockers: list = None,
            fold_blockers: list = None,
        ) -> None:
            """Set ``_fire_armed_state`` from the bot's arming flags.

            ``paintEvent`` paints a green right-edge glow while
            ``scrum_armed`` and a red one while ``fold_armed``.
            """
            self._fire_armed_state = {
                "scrum_armed": bool(scrum_armed),
                "fold_armed": bool(fold_armed),
                "scrum_blockers": list(scrum_blockers or []),
                "fold_blockers": list(fold_blockers or []),
            }
            self._repaint()

        def show_only(self, keys) -> None:
            """Switch on the overlays ``keys`` names and switch every other off."""
            wanted = set(str(one) for one in keys or [])
            self._overlay_shown = {one.key: one.key in wanted for one in CHART_OVERLAYS}
            self._repaint()

        def set_timeframe(self, tf: str) -> None:
            self._current_tf = tf

        def _natural_height_for_panes(self) -> int:
            """Return the pixel height the toggled-on panes need.

            The price pane takes 220, the volume strip adds 28, each entry of
            ``_sub_overlays_with_data`` adds 60 and ``_call_strip_h`` adds the
            voter rows, over a 64px header.
            """
            base = 28 + 18 + 220 + 18  # header + OHLC + price + time
            if self._overlay_shown["volume"]:
                base += 28
            base += len(self._sub_overlays_with_data()) * 60
            return base + self._call_strip_h()

        def _sub_overlays_with_data(self) -> tuple:
            """Every sub-pane overlay that is switched on and holds values.

            The values come from ``_<key>_data``, which ``_compute_indicators``
            fills.
            """
            return tuple(
                one
                for one in overlays_on(self, SUB_PANE)
                if getattr(self, f"_{one.key}_data", None)
            )

        def _effective_visible_start(self) -> int:
            """Resolve _visible_start to an int, defaulting to 0 (fit-all)."""
            if self._visible_start is None:
                return 0
            n = len(self._candles)
            return max(0, min(n - 1, self._visible_start))

        def _effective_visible_count(self) -> int:
            """Resolve _visible_count to an int, defaulting to all candles."""
            n = len(self._candles)
            if self._visible_count is None:
                return n
            return max(8, min(n, self._visible_count))

        def _fmt_price(self, price: float) -> str:
            if price < 0.0001:
                return f"{price:.8f}"
            elif price < 0.01:
                return f"{price:.6f}"
            elif price < 1:
                return f"{price:.4f}"
            elif price < 1000:
                return f"{price:.2f}"
            else:
                return f"{price:,.2f}"

        def paint_to(self, p: QPainter, w: int, h: int) -> None:
            """Draw the whole chart onto ``p`` over a ``w`` by ``h`` area.

            The painter's device is the caller's: a widget from ``paintEvent``
            and a ``QImage`` from ``render_chart_png``.
            """
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.TextAntialiasing)

            bg_grad = QLinearGradient(0, 0, 0, h)
            bg_grad.setColorAt(0, self.BG_TOP)
            bg_grad.setColorAt(1, self.BG_BOT)
            p.fillRect(0, 0, w, h, bg_grad)

            font_sm = QFont("Consolas", 8)
            font_sm.setHintingPreference(QFont.PreferFullHinting)
            font_hdr = QFont("Segoe UI", 10, QFont.Bold)
            font_ohlc = QFont("Consolas", 9, QFont.Bold)
            fm = QFontMetrics(font_sm)

            if not self._candles:
                p.setPen(QPen(self.TEXT_DIM))
                p.setFont(QFont("Segoe UI", 11))
                msg = self._error_text or self._status_text
                p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, msg)
                self._draw_header(p, w, font_hdr, font_sm)
                return

            ML = 8
            MR = 78  # right margin (price axis + badges)
            MT = 28  # header
            OHLC_H = 18  # OHLC info row at top of price pane
            MB = 18 + self._call_strip_h()  # time axis, then the voter strip

            sub_overlays = self._sub_overlays_with_data()
            show_volume = self._overlay_shown["volume"]

            VOL_H = 28 if show_volume else 0
            SUB_H = 60  # height of each oscillator sub-pane
            total_sub_h = SUB_H * len(sub_overlays)

            chart_w = w - ML - MR
            n_total = len(self._candles)
            if n_total == 0 or chart_w <= 0:
                return

            v_start = self._effective_visible_start()
            v_count = self._effective_visible_count()
            v_end = min(n_total, v_start + v_count)
            visible_candles = self._candles[v_start:v_end]
            n = len(visible_candles)
            if n == 0:
                # If pan went out of range, snap back to fit-all
                visible_candles = self._candles
                n = n_total
                v_start = 0

            available = h - MT - OHLC_H - MB - VOL_H - total_sub_h
            price_h = max(120, available)

            ohlc_top = MT
            price_top = ohlc_top + OHLC_H
            price_bot = price_top + price_h
            vol_top = price_bot
            vol_bot = vol_top + VOL_H
            sub_layout = []  # [(overlay, top, bot), ...]
            sy = vol_bot
            for overlay in sub_overlays:
                sub_layout.append((overlay, sy, sy + SUB_H))
                sy += SUB_H
            time_axis_y = sy  # top of time-axis label band

            cw = max(2, chart_w / n)
            gap = max(1, cw * 0.18)
            bw = max(1, cw - gap)

            # hi and lo come from visible_candles, never the full list.
            hi = max(c.high for c in visible_candles)
            lo = min(c.low for c in visible_candles)
            pr = hi - lo
            if pr == 0:
                pr = hi * 0.01 or 1.0
            pad = pr * 0.04 * self._y_zoom_pct
            hi += pad
            lo -= pad
            pr = hi - lo

            def p2y(price: float) -> float:
                return price_top + price_h * (1.0 - (price - lo) / pr)

            def i2x(i: int) -> float:
                return ML + i * cw

            max_vol = max((c.volume for c in visible_candles), default=1) or 1

            # _nice_step snaps the step to 1, 2 or 5 times a power of ten.
            def _nice_step(span: float, target_ticks: int = 6) -> float:
                import math as _m

                if span <= 0:
                    return 1.0
                raw = span / max(target_ticks, 1)
                mag = 10 ** _m.floor(_m.log10(raw))
                frac = raw / mag
                if frac < 1.5:
                    return 1 * mag
                if frac < 3.5:
                    return 2 * mag
                if frac < 7.5:
                    return 5 * mag
                return 10 * mag

            grid_step = _nice_step(pr, target_ticks=6)
            if grid_step > 0:
                import math as _m

                g0 = _m.ceil(lo / grid_step) * grid_step
                g = g0
                while g <= hi + grid_step * GRID_TICK_TOLERANCE:
                    y = int(p2y(g))
                    if price_top <= y <= price_bot:
                        is_major = round((g - g0) / grid_step) % 2 == 0
                        gc = self.GRID_MAJOR if is_major else self.GRID_MINOR
                        p.setPen(QPen(gc, 1, Qt.DotLine))
                        p.drawLine(ML, y, w - MR, y)
                        p.setPen(QPen(self.TEXT_LIGHT))
                        p.setFont(font_sm)
                        p.drawText(w - MR + 6, y + 4, self._fmt_price(g))
                    g += grid_step

            # About 6 ticks; each line spans every pane above the label band.
            if n >= 2:
                import time as _t

                tick_stride = max(1, n // 6)
                span_sec = max(1, visible_candles[-1].time - visible_candles[0].time)
                use_date = span_sec > 24 * 3600
                for ti in range(0, n, tick_stride):
                    c = visible_candles[ti]
                    tx = int(i2x(ti) + cw / 2)
                    if tx < ML or tx > w - MR:
                        continue
                    p.setPen(QPen(self.GRID_MINOR, 1, Qt.DotLine))
                    p.drawLine(tx, price_top, tx, time_axis_y)
                    try:
                        tm = _t.gmtime(c.time)
                        if use_date:
                            label = _t.strftime("%m-%d", tm)
                        else:
                            label = _t.strftime("%H:%M", tm)
                    except Exception:
                        label = ""
                    if label:
                        p.setPen(QPen(self.TEXT_LIGHT))
                        p.setFont(font_sm)
                        p.drawText(tx - 16, time_axis_y + 12, label)

            self._draw_positions(p, w, ML, MR, price_top, price_h, p2y, font_sm)

            # Every candle body is Heikin-Ashi, never the raw OHLC.
            ha_candles = []
            if len(visible_candles) >= 2:
                prev_o = visible_candles[0].open
                prev_c = visible_candles[0].close
                for j, c in enumerate(visible_candles):
                    if j == 0:
                        ha_o = (c.open + c.close) / 2
                        ha_c = (c.open + c.high + c.low + c.close) / 4
                    else:
                        ha_o = (prev_o + prev_c) / 2
                        ha_c = (c.open + c.high + c.low + c.close) / 4
                    ha_h = max(c.high, ha_o, ha_c)
                    ha_l = min(c.low, ha_o, ha_c)
                    ha_candles.append((ha_o, ha_h, ha_l, ha_c, c.volume))
                    prev_o = ha_o
                    prev_c = ha_c
            else:
                ha_candles = [
                    (c.open, c.high, c.low, c.close, c.volume) for c in visible_candles
                ]

            for i, (ha_o, ha_h, ha_l, ha_c, _vol) in enumerate(ha_candles):
                x = i2x(i)
                is_up = ha_c >= ha_o

                fill = self.UP_FILL if is_up else self.DOWN_FILL
                border = self.UP_BORDER if is_up else self.DOWN_BORDER
                wick_c = self.UP_WICK if is_up else self.DOWN_WICK

                wx = x + cw / 2
                y_hi = p2y(ha_h)
                y_lo = p2y(ha_l)
                p.setPen(QPen(wick_c, 1))
                p.drawLine(int(wx), int(y_hi), int(wx), int(y_lo))

                y_open = p2y(ha_o)
                y_close = p2y(ha_c)
                bt = min(y_open, y_close)
                bh = max(abs(y_open - y_close), 1)
                body = QRectF(x + gap / 2, bt, bw, bh)

                p.setBrush(QBrush(fill))
                p.setPen(QPen(border, 1))
                p.drawRect(body)

                if show_volume and VOL_H > 0:
                    cvol = _vol
                    vh = (cvol / max_vol) * VOL_H if cvol > 0 else 0
                    if vh > 0:
                        vol_y = vol_bot - vh
                        vol_rect = QRectF(x + gap / 2, vol_y, bw, vh)
                        vf = self.VOL_UP if is_up else self.VOL_DOWN
                        vb = self.VOL_UP_BORDER if is_up else self.VOL_DOWN_BORDER
                        p.setBrush(QBrush(vf))
                        p.setPen(QPen(vb, 1))
                        p.drawRect(vol_rect)

            for overlay in overlays_on(self, VOLUME_PANE):
                getattr(self, overlay.draw)(p, ML, w - MR, vol_top)

            # The price line reads the latest candle, not the last visible one.
            if self._candles:
                last_close = self._candles[-1].close
                yp = p2y(last_close)
                p.setPen(QPen(self.PRICE_LINE_COLOR, 1, Qt.DashLine))
                p.drawLine(ML, int(yp), w - MR, int(yp))
                ptxt = self._fmt_price(last_close)
                tw = fm.horizontalAdvance(ptxt) + 10
                badge = QRectF(w - MR, yp - 9, tw, 18)
                p.setBrush(QBrush(self.BADGE_SURFACE))
                p.setPen(QPen(self.PRICE_LINE_COLOR, 1))
                p.drawRoundedRect(badge, 3, 3)
                p.setFont(font_sm)
                p.drawText(badge, Qt.AlignCenter, ptxt)

            if n > 0:

                def _draw_line_series(data, color, width=1.2, dashed=False):
                    pen = QPen(color, width)
                    if dashed:
                        pen.setStyle(Qt.DashLine)
                    p.setPen(pen)
                    prev = None
                    for i, val in enumerate(data):
                        if val is None:
                            prev = None
                            continue
                        x = i2x(i) + cw / 2
                        y = p2y(val)
                        if prev is not None:
                            p.drawLine(prev, QPointF(x, y))
                        prev = QPointF(x, y)

                ctx = PaintContext(
                    p=p,
                    w=w,
                    ML=ML,
                    MR=MR,
                    price_top=price_top,
                    price_bot=price_bot,
                    n=n,
                    cw=cw,
                    gap=gap,
                    bw=bw,
                    v_start=v_start,
                    v_end=v_end,
                    visible_candles=visible_candles,
                    i2x=i2x,
                    p2y=p2y,
                    fm=fm,
                    font_sm=font_sm,
                    draw_line_series=_draw_line_series,
                )
                for overlay in overlays_on(self, PRICE_PANE):
                    getattr(self, overlay.draw)(ctx)
                # Both Target Balance lines are dashed, with a right-edge badge.
                if self._tb_anchor_price is not None:
                    ay = p2y(float(self._tb_anchor_price))
                    if price_top <= ay <= price_bot:
                        anchor_color = self.TB_ANCHOR
                        p.setPen(QPen(anchor_color, 1.4, Qt.DashLine))
                        p.drawLine(ML, int(ay), w - MR, int(ay))
                        txt = f"TB-Anchor {self._fmt_price(self._tb_anchor_price)}"
                        tw = fm.horizontalAdvance(txt) + 10
                        badge = QRectF(ML + 4, ay - 8, tw, 14)
                        p.setBrush(QBrush(self.BADGE_SURFACE))
                        p.setPen(QPen(anchor_color, 1))
                        p.drawRoundedRect(badge, 2, 2)
                        p.setPen(QPen(anchor_color))
                        p.setFont(font_sm)
                        p.drawText(badge, Qt.AlignCenter, txt)

                if self._tb_ceiling_price is not None:
                    cyl = p2y(float(self._tb_ceiling_price))
                    if price_top <= cyl <= price_bot:
                        ceiling_color = self.TB_CEILING
                        p.setPen(QPen(ceiling_color, 1.4, Qt.DashLine))
                        p.drawLine(ML, int(cyl), w - MR, int(cyl))
                        txt = f"TB-Ceiling {self._fmt_price(self._tb_ceiling_price)}"
                        tw = fm.horizontalAdvance(txt) + 10
                        badge = QRectF(ML + 4, cyl - 8, tw, 14)
                        p.setBrush(QBrush(self.BADGE_SURFACE))
                        p.setPen(QPen(ceiling_color, 1))
                        p.drawRoundedRect(badge, 2, 2)
                        p.setPen(QPen(ceiling_color))
                        p.setFont(font_sm)
                        p.drawText(badge, Qt.AlignCenter, txt)

                # Right-edge glow: green when SCRUM is armed, red when FOLD is.
                _fa = self._fire_armed_state or {}
                _scrum_on = bool(_fa.get("scrum_armed"))
                _fold_on = bool(_fa.get("fold_armed"))
                if _scrum_on or _fold_on:
                    glow_x = w - MR - 4
                    glow_w = 6
                    if _scrum_on:
                        scrum_top = price_top + 4
                        scrum_bot = price_top + (price_h * 0.5)
                        grad = QLinearGradient(
                            glow_x, scrum_top, glow_x + glow_w, scrum_top
                        )
                        grad.setColorAt(0.0, _with_alpha(self.GLOW_SCRUM, 0))
                        grad.setColorAt(1.0, self.GLOW_SCRUM)
                        p.setBrush(QBrush(grad))
                        p.setPen(Qt.NoPen)
                        p.drawRect(
                            QRectF(glow_x, scrum_top, glow_w, scrum_bot - scrum_top)
                        )
                    if _fold_on:
                        fold_top = price_top + (price_h * 0.5)
                        fold_bot = price_bot - 4
                        grad = QLinearGradient(
                            glow_x, fold_top, glow_x + glow_w, fold_top
                        )
                        grad.setColorAt(0.0, _with_alpha(self.GLOW_FOLD, 0))
                        grad.setColorAt(1.0, self.GLOW_FOLD)
                        p.setBrush(QBrush(grad))
                        p.setPen(Qt.NoPen)
                        p.drawRect(
                            QRectF(glow_x, fold_top, glow_w, fold_bot - fold_top)
                        )

                def _paint_sub_grid(top: float, bot: float, label: str):
                    """Paint sub-pane backdrop + top separator + name label."""
                    p.setPen(Qt.NoPen)
                    p.setBrush(QBrush(self.SUB_PANE_WASH))
                    p.drawRect(QRectF(ML, top, w - ML - MR, bot - top))
                    p.setPen(QPen(self.GRID_MAJOR, 1))
                    p.drawLine(ML, int(top), w - MR, int(top))
                    p.setPen(QPen(self.TEXT_DIM))
                    p.setFont(font_sm)
                    p.drawText(int(ML + 6), int(top + 11), label)

                def _sub_axis_label(top: float, bot: float, value, color):
                    """Right-side numeric label for a sub-pane axis value."""
                    if value is None:
                        return
                    txt = f"{value:.4f}" if abs(value) < 10 else f"{value:.2f}"
                    tw = fm.horizontalAdvance(txt) + 8
                    badge_y = (top + bot) / 2 - 8
                    badge = QRectF(w - MR + 2, badge_y, tw, 14)
                    p.setBrush(QBrush(self.BADGE_SURFACE))
                    p.setPen(QPen(color, 1))
                    p.drawRoundedRect(badge, 2, 2)
                    p.setPen(QPen(color))
                    p.setFont(font_sm)
                    p.drawText(badge, Qt.AlignCenter, txt)

                def _paint_oscillator(
                    top, bot, data, extract, color, width=1.2, vmin=None, vmax=None
                ):
                    """Draw one oscillator line between ``top`` and ``bot``.

                    ``vmin`` and ``vmax`` fix the scale; ``None`` on
                    either fits it to the extracted values.
                    """
                    vals = [extract(d) for d in data if d is not None]
                    vals = [v for v in vals if v is not None]
                    if not vals:
                        return None  # nothing to label
                    sp_lo = vmin if vmin is not None else min(vals)
                    sp_hi = vmax if vmax is not None else max(vals)
                    rng = (sp_hi - sp_lo) or 1e-9
                    pen = QPen(color, width)
                    p.setPen(pen)
                    prev = None
                    last_val = None
                    for i, d in enumerate(data):
                        if d is None:
                            prev = None
                            continue
                        v = extract(d)
                        if v is None:
                            prev = None
                            continue
                        x = i2x(i) + cw / 2
                        y = bot - ((v - sp_lo) / rng) * (bot - top)
                        if prev is not None:
                            p.drawLine(prev, QPointF(x, y))
                        prev = QPointF(x, y)
                        last_val = v
                    return last_val

                ctx.paint_sub_grid = _paint_sub_grid
                ctx.sub_axis_label = _sub_axis_label
                ctx.paint_oscillator = _paint_oscillator
                for overlay, sp_top, sp_bot in sub_layout:
                    getattr(self, overlay.draw)(ctx, sp_top, sp_bot)

                # Tranche floor lines: the bot will not fold below these prices.
                if self._tranche_floors:
                    p.setPen(QPen(self.FLOOR_LINE, 1, Qt.DashLine))
                    font_fl = QFont("Consolas", 7)
                    p.setFont(font_fl)
                    for fp, label in self._tranche_floors:
                        try:
                            yf = p2y(float(fp))
                        except (TypeError, ValueError):
                            continue
                        p.setPen(QPen(self.FLOOR_LINE, 1, Qt.DashLine))
                        p.drawLine(ML, int(yf), w - MR, int(yf))
                        p.setPen(self.FLOOR_LINE)
                        p.drawText(QPointF(ML + 4, yf - 2), f"FLOOR {label}")

                self._draw_call(ctx, h)

            type_colors = {
                "SCRUM": self.MARKER_SCRUM,
                "FOLD": self.MARKER_FOLD,
                "DIST": self.MARKER_DIST,
            }
            default_buy = self.MARKER_BUY
            default_sell = self.MARKER_SELL

            for m in self._markers:
                # A marker outside the visible time range is skipped, not clamped.
                best_i = min(
                    range(n), key=lambda i: abs(visible_candles[i].time - m.time)
                )
                t_first = visible_candles[0].time
                t_last = visible_candles[-1].time
                if m.time < t_first or m.time > t_last:
                    continue
                mx = i2x(best_i) + cw / 2
                my = p2y(m.price)
                is_buy = m.side == "buy"
                tc = type_colors.get(m.label, default_buy if is_buy else default_sell)

                sz = 5
                diamond = QPolygonF(
                    [
                        QPointF(mx, my - sz),
                        QPointF(mx + sz, my),
                        QPointF(mx, my + sz),
                        QPointF(mx - sz, my),
                    ]
                )
                p.setBrush(QBrush(tc))
                p.setPen(QPen(self.MARKER_EDGE, 0.8))
                p.drawPolygon(diamond)

                p.setPen(QPen(tc, 1.2))
                if is_buy:
                    p.drawLine(int(mx), int(my + sz), int(mx), int(my + sz + 6))
                else:
                    p.drawLine(int(mx), int(my - sz), int(mx), int(my - sz - 6))

                # Type label (SCRUM/FOLD/DIST/BUY/SELL)
                label = m.label or ("BUY" if is_buy else "SELL")
                p.setFont(QFont("Consolas", 7, QFont.Bold))
                fm = p.fontMetrics()
                tw = fm.horizontalAdvance(label) + 6
                ty = my - sz - 18 if not is_buy else my + sz + 8
                p.setBrush(QBrush(self.BADGE_SURFACE))
                p.setPen(QPen(tc, 0.5))
                p.drawRoundedRect(QRectF(mx - tw / 2, ty, tw, 13), 2, 2)
                p.setPen(QPen(tc))
                p.drawText(QRectF(mx - tw / 2, ty, tw, 13), Qt.AlignCenter, label)

            if show_volume and max_vol > 0:
                p.setPen(QPen(self.TEXT_DIM))
                p.setFont(font_sm)
                if max_vol >= 1e9:
                    vl = f"{max_vol/1e9:.1f}B"
                elif max_vol >= 1e6:
                    vl = f"{max_vol/1e6:.1f}M"
                elif max_vol >= 1e3:
                    vl = f"{max_vol/1e3:.1f}K"
                else:
                    vl = f"{max_vol:.0f}"
                p.drawText(w - MR + 6, int(vol_top + 10), f"Vol {vl}")

            if self._mouse_x is not None and self._mouse_y is not None:
                mx, my = self._mouse_x, self._mouse_y
                if ML <= mx <= w - MR and price_top <= my <= time_axis_y:
                    p.setPen(QPen(self.CROSSHAIR_COLOR, 1, Qt.DotLine))
                    p.drawLine(mx, int(price_top), mx, int(time_axis_y))
                    p.drawLine(ML, my, w - MR, my)

                    if price_top <= my <= price_bot:
                        cp = lo + pr * (1 - (my - price_top) / price_h)
                        cp_txt = self._fmt_price(cp)
                        cp_w = fm.horizontalAdvance(cp_txt) + 12
                        badge = QRectF(w - MR, my - 9, cp_w, 18)
                        p.setBrush(QBrush(self.BADGE_SURFACE))
                        p.setPen(QPen(self.CROSSHAIR_COLOR, 1))
                        p.drawRoundedRect(badge, 3, 3)
                        p.setPen(QPen(self.TEXT_LIGHT))
                        p.setFont(font_sm)
                        p.drawText(badge, Qt.AlignCenter, cp_txt)

                    ci = int((mx - ML) / cw)
                    if 0 <= ci < n:
                        import time as _t2

                        c = visible_candles[ci]
                        try:
                            tstr = _t2.strftime("%Y-%m-%d %H:%M", _t2.gmtime(c.time))
                        except Exception:
                            tstr = ""
                        if tstr:
                            tw = fm.horizontalAdvance(tstr) + 12
                            t_badge = QRectF(mx - tw / 2, time_axis_y - 1, tw, 16)
                            p.setBrush(QBrush(self.BADGE_SURFACE))
                            p.setPen(QPen(self.CROSSHAIR_COLOR, 1))
                            p.drawRoundedRect(t_badge, 3, 3)
                            p.setPen(QPen(self.TEXT_LIGHT))
                            p.drawText(t_badge, Qt.AlignCenter, tstr)

                        is_up = c.close >= c.open
                        tip_color = self.UP_FILL if is_up else self.DOWN_FILL
                        chg = c.close - c.open
                        chg_pct = (chg / c.open * 100) if c.open > 0 else 0
                        lines = [
                            ("O", self._fmt_price(c.open), self.TEXT_LIGHT),
                            ("H", self._fmt_price(c.high), self.TEXT_LIGHT),
                            ("L", self._fmt_price(c.low), self.TEXT_LIGHT),
                            ("C", self._fmt_price(c.close), tip_color),
                            ("Δ", f"{chg:+.6g} ({chg_pct:+.2f}%)", tip_color),
                            (
                                "V",
                                (
                                    f"{c.volume/1e6:.2f}M"
                                    if c.volume >= 1e6
                                    else (
                                        f"{c.volume/1e3:.1f}K"
                                        if c.volume >= 1e3
                                        else f"{c.volume:.0f}"
                                    )
                                ),
                                self.TEXT_DIM,
                            ),
                        ]
                        line_h = 14
                        pad = 8
                        tip_w = 0
                        for lbl, val, _col in lines:
                            line_w = fm.horizontalAdvance(f"{lbl}  {val}")
                            tip_w = max(tip_w, line_w)
                        tip_w += pad * 2
                        tip_h = line_h * len(lines) + pad * 2
                        if mx < ML + chart_w / 2:
                            tx = w - MR - tip_w - 8
                        else:
                            tx = ML + 8
                        ty = price_top + 8
                        bg_rect = QRectF(tx, ty, tip_w, tip_h)
                        p.setBrush(QBrush(self.BADGE_SURFACE))
                        p.setPen(QPen(self.BADGE_EDGE, 1))
                        p.drawRoundedRect(bg_rect, 4, 4)
                        stripe = QRectF(tx, ty, 3, tip_h)
                        p.setBrush(QBrush(tip_color))
                        p.setPen(Qt.NoPen)
                        p.drawRoundedRect(stripe, 2, 2)
                        p.setFont(font_sm)
                        for li, (lbl, val, col) in enumerate(lines):
                            y_line = ty + pad + (li + 1) * line_h - 3
                            p.setPen(QPen(self.TEXT_DIM))
                            p.drawText(tx + pad + 6, int(y_line), lbl)
                            p.setPen(QPen(col))
                            p.drawText(tx + pad + 24, int(y_line), val)

            if self._candles:
                last = self._candles[-1]
                is_up = last.close >= last.open
                up_color = self.UP_FILL
                dn_color = self.DOWN_FILL
                acc = up_color if is_up else dn_color
                chg = last.close - last.open
                chg_pct = (chg / last.open * 100) if last.open > 0 else 0
                p.setFont(font_ohlc)
                fm_ohlc = QFontMetrics(font_ohlc)
                ohlc_y = ohlc_top + 13
                cur_x = ML + 4
                ohlc_parts = [
                    ("O", self._fmt_price(last.open), self.TEXT_LIGHT),
                    ("H", self._fmt_price(last.high), self.TEXT_LIGHT),
                    ("L", self._fmt_price(last.low), self.TEXT_LIGHT),
                    ("C", self._fmt_price(last.close), acc),
                    ("", f"{chg:+.6g}", acc),
                    ("", f"({chg_pct:+.2f}%)", acc),
                    (
                        "VOL",
                        (
                            f"{last.volume/1e6:.2f}M"
                            if last.volume >= 1e6
                            else (
                                f"{last.volume/1e3:.1f}K"
                                if last.volume >= 1e3
                                else f"{last.volume:.2f}"
                            )
                        ),
                        self.TEXT_DIM,
                    ),
                ]
                for lbl, val, col in ohlc_parts:
                    if lbl:
                        p.setPen(QPen(self.TEXT_DIM))
                        p.drawText(int(cur_x), int(ohlc_y), lbl)
                        cur_x += fm_ohlc.horizontalAdvance(lbl) + 4
                    p.setPen(QPen(col))
                    p.drawText(int(cur_x), int(ohlc_y), val)
                    cur_x += fm_ohlc.horizontalAdvance(val) + 12

            self._draw_header(p, w, font_hdr, font_sm)

            # Three low-contrast dashes marking the draggable bottom edge.
            grip_y = h - self._resize_grip_h // 2
            grip_color = self.GRIP
            p.setPen(QPen(grip_color, 1.2))
            cx = w / 2
            for off in (-12, 0, 12):
                p.drawLine(
                    int(cx + off - 4), int(grip_y), int(cx + off + 4), int(grip_y)
                )

        def _draw_bollinger(self, ctx) -> None:
            """Paint the Bollinger cloud and its upper, middle and lower lines."""
            p = ctx.p
            cw = ctx.cw
            i2x = ctx.i2x
            p2y = ctx.p2y
            _draw_line_series = ctx.draw_line_series
            bb_visible = self._bb_data[ctx.v_start : ctx.v_end]
            if self._overlay_shown["bb"] and bb_visible:
                # The cloud polygon paints before the span lines.
                pts_upper = []
                pts_lower = []
                for i, b in enumerate(bb_visible):
                    if b is None:
                        continue
                    x = i2x(i) + cw / 2
                    pts_upper.append(QPointF(x, p2y(b[0])))
                    pts_lower.append(QPointF(x, p2y(b[2])))
                if pts_upper and pts_lower:
                    fill_pts = pts_upper + list(reversed(pts_lower))
                    p.setBrush(QBrush(self.BAND_FILL))
                    p.setPen(Qt.NoPen)
                    p.drawPolygon(QPolygonF(fill_pts))
                uppers = [b[0] if b else None for b in bb_visible]
                middles = [b[1] if b else None for b in bb_visible]
                lowers = [b[2] if b else None for b in bb_visible]
                _draw_line_series(uppers, self.BAND_LINE, 1.2, False)
                _draw_line_series(middles, self.BAND_MID, 0.8, True)
                _draw_line_series(lowers, self.BAND_LINE, 1.2, False)

            # The kumo is the band between Span A and Span B, both shifted +26.

        def _draw_ichimoku(self, ctx) -> None:
            """Paint the Ichimoku kumo, Tenkan, Kijun, both spans and Chikou."""
            p = ctx.p
            cw = ctx.cw
            v_start = ctx.v_start
            v_end = ctx.v_end
            i2x = ctx.i2x
            p2y = ctx.p2y
            _draw_line_series = ctx.draw_line_series
            if self._overlay_shown["ichimoku"] and self._ichimoku_data:
                SHIFT = 26
                full_ichi = self._ichimoku_data
                n_full = len(self._candles)

                # Full-length shifted arrays; None where the shift leaves the index.
                span_a_full = [None] * n_full
                span_b_full = [None] * n_full
                for k in range(n_full - SHIFT):
                    d = full_ichi[k]
                    if d is None:
                        continue
                    if d[2] is not None:
                        span_a_full[k + SHIFT] = d[2]
                    if d[3] is not None:
                        span_b_full[k + SHIFT] = d[3]

                span_a = span_a_full[v_start:v_end]
                span_b = span_b_full[v_start:v_end]
                tenkan = [
                    full_ichi[k][0] if full_ichi[k] else None
                    for k in range(v_start, v_end)
                ]
                kijun = [
                    full_ichi[k][1] if full_ichi[k] else None
                    for k in range(v_start, v_end)
                ]

                # One polygon per run of equal polarity; a missing span ends a run.
                bull_color = self.CLOUD_BULL
                bear_color = self.CLOUD_BEAR
                seg_pts_top: list[QPointF] = []
                seg_pts_bot: list[QPointF] = []
                seg_bullish = None

                def _flush_segment():
                    if not seg_pts_top or not seg_pts_bot:
                        return
                    poly_pts = seg_pts_top + list(reversed(seg_pts_bot))
                    p.setBrush(QBrush(bull_color if seg_bullish else bear_color))
                    p.setPen(Qt.NoPen)
                    p.drawPolygon(QPolygonF(poly_pts))

                for k in range(len(span_a)):
                    sa = span_a[k]
                    sb = span_b[k]
                    if sa is None or sb is None:
                        _flush_segment()
                        seg_pts_top = []
                        seg_pts_bot = []
                        seg_bullish = None
                        continue
                    is_bull = sa > sb
                    x = i2x(k) + cw / 2
                    top_y = p2y(max(sa, sb))
                    bot_y = p2y(min(sa, sb))
                    if seg_bullish is not None and is_bull != seg_bullish:
                        seg_pts_top.append(QPointF(x, top_y))
                        seg_pts_bot.append(QPointF(x, bot_y))
                        _flush_segment()
                        seg_pts_top = [QPointF(x, top_y)]
                        seg_pts_bot = [QPointF(x, bot_y)]
                        seg_bullish = is_bull
                        continue
                    seg_pts_top.append(QPointF(x, top_y))
                    seg_pts_bot.append(QPointF(x, bot_y))
                    seg_bullish = is_bull
                _flush_segment()

                _draw_line_series(tenkan, self.TENKAN_LINE, 1.2)
                _draw_line_series(kijun, self.KIJUN_LINE, 1.2)
                _draw_line_series(span_a, self.SPAN_A_LINE, 1.0)
                _draw_line_series(span_b, self.SPAN_B_LINE, 1.0)

                # Chikou at visible k is the close at v_start + k + SHIFT.
                chikou_color = self.CHIKOU_LINE
                p.setPen(QPen(chikou_color, 1.0))
                prev_pt = None
                for k in range(len(span_a)):
                    src_idx = v_start + k + SHIFT
                    if src_idx >= n_full:
                        prev_pt = None
                        continue
                    cval = self._candles[src_idx].close
                    x = i2x(k) + cw / 2
                    y = p2y(cval)
                    if prev_pt is not None:
                        p.drawLine(prev_pt, QPointF(x, y))
                    prev_pt = QPointF(x, y)

        def _draw_bullseye(self, ctx) -> None:
            """Paint the four BB Bullseye envelopes on the upper and lower bands."""
            p = ctx.p
            cw = ctx.cw
            i2x = ctx.i2x
            p2y = ctx.p2y
            bb_visible = self._bb_data[ctx.v_start : ctx.v_end]
            if self._overlay_shown["bbullseye"] and bb_visible:
                TOUCH_TOL = 0.005  # 0.5%
                WICK_TOL = 0.002  # 0.2%

                def _band_zone_polygon(band_idx: int, tol: float):
                    """Return the upper and lower point lists of the
                    ±``tol`` envelope around ``bb_visible`` entry
                    ``band_idx``, 0 for upper and 2 for lower.
                    """
                    upper_pts, lower_pts = [], []
                    for k, b in enumerate(bb_visible):
                        if b is None or b[band_idx] <= 0:
                            continue
                        level = b[band_idx]
                        x = i2x(k) + cw / 2
                        upper_pts.append(QPointF(x, p2y(level * (1 + tol))))
                        lower_pts.append(QPointF(x, p2y(level * (1 - tol))))
                    return upper_pts, lower_pts

                # Lower-touch zone (gold, fold-side bullseye)
                p.setPen(Qt.NoPen)
                upr, lwr = _band_zone_polygon(2, TOUCH_TOL)
                if upr and lwr:
                    poly = upr + list(reversed(lwr))
                    p.setBrush(QBrush(self.ZONE_FOLD_TOUCH))
                    p.drawPolygon(QPolygonF(poly))
                # Lower-wick zone (gold, dimmer inner ring)
                upr, lwr = _band_zone_polygon(2, WICK_TOL)
                if upr and lwr:
                    poly = upr + list(reversed(lwr))
                    p.setBrush(QBrush(self.ZONE_FOLD_WICK))
                    p.drawPolygon(QPolygonF(poly))
                # Upper-touch zone (rose-pink, scrum-side bullseye)
                upr, lwr = _band_zone_polygon(0, TOUCH_TOL)
                if upr and lwr:
                    poly = upr + list(reversed(lwr))
                    p.setBrush(QBrush(self.ZONE_SCRUM_TOUCH))
                    p.drawPolygon(QPolygonF(poly))
                # Upper-wick zone (rose-pink, dimmer inner ring)
                upr, lwr = _band_zone_polygon(0, WICK_TOL)
                if upr and lwr:
                    poly = upr + list(reversed(lwr))
                    p.setBrush(QBrush(self.ZONE_SCRUM_WICK))
                    p.drawPolygon(QPolygonF(poly))

            # BB_PERIOD, BB_STD, SQ_LB, SQ_THR and SN_LB are SlingshotIndicator's
            # defaults; its Keltner release test is not drawn here.

        def _draw_slingshot(self, ctx) -> None:
            """Paint one mark per Slingshot squeeze release or snapback."""
            p = ctx.p
            cw = ctx.cw
            v_start = ctx.v_start
            v_end = ctx.v_end
            visible_candles = ctx.visible_candles
            i2x = ctx.i2x
            p2y = ctx.p2y
            if self._overlay_shown["slingshot"]:
                # Full history: the leftmost visible candle needs a run-up.
                full_closes = [c.close for c in self._candles]
                n_full = len(full_closes)
                BB_PERIOD = 20
                BB_STD = 2.0
                SQ_LB = 30  # squeeze lookback
                SN_LB = 5  # snapback lookback
                SQ_THR = 0.6  # bandwidth threshold (fraction of avg)
                if n_full >= BB_PERIOD + SQ_LB + 2:
                    sl_bb: list[Optional[tuple]] = [None] * n_full
                    for k in range(BB_PERIOD - 1, n_full):
                        window = full_closes[k - BB_PERIOD + 1 : k + 1]
                        mid = sum(window) / BB_PERIOD
                        if mid <= 0:
                            continue
                        var = sum((x - mid) ** 2 for x in window) / BB_PERIOD
                        std = var**0.5
                        up = mid + BB_STD * std
                        lo = mid - BB_STD * std
                        bw = (up - lo) / mid
                        sl_bb[k] = (full_closes[k], up, lo, mid, bw)

                    fires = []  # [(idx, kind, bullish)]; kind in {"squeeze","snapback"}
                    for k in range(BB_PERIOD + SQ_LB, n_full):
                        window = sl_bb[k - SQ_LB : k]
                        window = [b for b in window if b is not None]
                        if len(window) < SQ_LB - 2:
                            continue
                        avg_bw = sum(b[4] for b in window) / len(window)
                        curr = sl_bb[k]
                        prev = sl_bb[k - 1]
                        if curr is None or prev is None:
                            continue
                        recent4 = [b for b in sl_bb[k - 3 : k + 1] if b is not None]
                        n_squeezed = sum(1 for b in recent4 if b[4] < avg_bw * SQ_THR)
                        was_squeezed = n_squeezed >= 2
                        expanding = curr[4] > prev[4] * 1.02
                        if was_squeezed and expanding:
                            bullish = curr[0] > curr[3]  # close > middle
                            fires.append((k, "squeeze", bullish))
                            continue  # squeeze fired; don't double-mark snapback

                        # Snapback: a close broke the band within SN_LB bars.
                        for j in range(max(BB_PERIOD, k - SN_LB), k):
                            past = sl_bb[j]
                            if past is None:
                                continue
                            pc, pu, pl, pm, _ = past
                            cc, cu, cl, cm, _ = curr
                            if pc < pl and cl < cc < cm and cc > pc:
                                fires.append((k, "snapback", True))
                                break
                            if pc > pu and cm < cc < cu and cc < pc:
                                fires.append((k, "snapback", False))
                                break

                    for idx, kind, bullish in fires:
                        if idx < v_start or idx >= v_end:
                            continue
                        vis_i = idx - v_start
                        x = i2x(vis_i) + cw / 2
                        cdl = visible_candles[vis_i]
                        if bullish:
                            color = self.EVENT_BULL
                            anchor_y = p2y(cdl.low) + 14
                        else:
                            color = self.EVENT_BEAR
                            anchor_y = p2y(cdl.high) - 14
                        p.setBrush(QBrush(color))
                        p.setPen(QPen(color.lighter(140), 1.4))
                        if kind == "squeeze":
                            # Diamond — compression-then-release
                            sz = 6
                            diamond = QPolygonF(
                                [
                                    QPointF(x, anchor_y - sz),
                                    QPointF(x + sz, anchor_y),
                                    QPointF(x, anchor_y + sz),
                                    QPointF(x - sz, anchor_y),
                                ]
                            )
                            p.drawPolygon(diamond)
                        else:
                            # Circle — mean-reversion snapback
                            p.drawEllipse(QPointF(x, anchor_y), 5.5, 5.5)

        def _draw_macd(self, ctx, top: float, bot: float) -> None:
            """Paint the MACD histogram, its line and its signal in one sub-pane."""
            p, w = ctx.p, ctx.w
            visible = self._macd_data[ctx.v_start : ctx.v_end]
            if not visible:
                return
            ctx.paint_sub_grid(top, bot, "MACD (12, 26, 9)")
            all_vals: list[float] = []
            for one in visible:
                if one is None:
                    continue
                all_vals.extend([one[0], one[1], one[2]])
            if not all_vals:
                return
            v_lo, v_hi = min(all_vals), max(all_vals)
            v_pad = max(abs(v_lo), abs(v_hi)) * 0.1 or 1e-6
            v_lo -= v_pad
            v_hi += v_pad
            span = v_hi - v_lo
            if v_lo < 0 < v_hi:
                zero_y = bot - ((0 - v_lo) / span) * (bot - top)
                p.setPen(QPen(self.GRID_MINOR, 1, Qt.DashLine))
                p.drawLine(ctx.ML, int(zero_y), w - ctx.MR, int(zero_y))
            for index, one in enumerate(visible):
                if one is None or one[2] is None:
                    continue
                hist = one[2]
                x = ctx.i2x(index) + ctx.gap / 2
                y0 = bot - ((0 - v_lo) / span) * (bot - top)
                y1 = bot - ((hist - v_lo) / span) * (bot - top)
                rising = hist >= 0
                p.setBrush(QBrush(self.HIST_UP if rising else self.HIST_DOWN))
                p.setPen(QPen(self.HIST_UP_EDGE if rising else self.HIST_DOWN_EDGE, 1))
                p.drawRect(QRectF(x, min(y0, y1), ctx.bw, abs(y1 - y0) or 1))
            last_macd = ctx.paint_oscillator(
                top,
                bot,
                visible,
                lambda t: t[0] if t else None,
                self.MACD_LINE,
                1.4,
                vmin=v_lo,
                vmax=v_hi,
            )
            ctx.paint_oscillator(
                top,
                bot,
                visible,
                lambda t: t[1] if t else None,
                self.MACD_SIGNAL,
                1.0,
                vmin=v_lo,
                vmax=v_hi,
            )
            ctx.sub_axis_label(top, bot, last_macd, self.MACD_LINE)

        def _draw_vortex(self, ctx, top: float, bot: float) -> None:
            """Paint VI+ and VI- against the 1.0 reference in one sub-pane."""
            p, w = ctx.p, ctx.w
            visible = self._vortex_data[ctx.v_start : ctx.v_end]
            if not visible:
                return
            ctx.paint_sub_grid(top, bot, "Vortex (14)")
            ref_y = bot - ((1.0 - 0.3) / (1.7 - 0.3)) * (bot - top)
            p.setPen(QPen(self.GRID_MINOR, 1, Qt.DashLine))
            p.drawLine(ctx.ML, int(ref_y), w - ctx.MR, int(ref_y))
            last_plus = ctx.paint_oscillator(
                top,
                bot,
                visible,
                lambda t: t[0] if t else None,
                self.VORTEX_PLUS,
                1.4,
                vmin=0.3,
                vmax=1.7,
            )
            ctx.paint_oscillator(
                top,
                bot,
                visible,
                lambda t: t[1] if t else None,
                self.VORTEX_MINUS,
                1.4,
                vmin=0.3,
                vmax=1.7,
            )
            ctx.sub_axis_label(top, bot, last_plus, self.VORTEX_PLUS)

        def _draw_stochrsi(self, ctx, top: float, bot: float) -> None:
            """Paint the Stochastic RSI against its 0.2 and 0.8 references."""
            p, w = ctx.p, ctx.w
            visible = self._stochrsi_data[ctx.v_start : ctx.v_end]
            if not visible:
                return
            ctx.paint_sub_grid(top, bot, "Stoch RSI (14, 14)")
            for ref in (0.2, 0.8):
                ref_y = bot - ref * (bot - top)
                p.setPen(QPen(self.GRID_MINOR, 1, Qt.DashLine))
                p.drawLine(ctx.ML, int(ref_y), w - ctx.MR, int(ref_y))
            last_value = ctx.paint_oscillator(
                top,
                bot,
                visible,
                lambda v: v,
                self.OSC_LINE,
                1.4,
                vmin=0.0,
                vmax=1.0,
            )
            ctx.sub_axis_label(top, bot, last_value, self.OSC_LINE)

        def _draw_volume(
            self, p: QPainter, left_px: int, right_px: int, top_px: float
        ) -> None:
            """Rule the line that separates the volume strip from the price pane.

            Each bar is painted beside its candle body in the same pass.
            """
            p.setPen(QPen(self.GRID_MAJOR, 1))
            p.drawLine(left_px, int(top_px), right_px, int(top_px))

        def _draw_positions(
            self,
            p: QPainter,
            w: int,
            left_px: int,
            right_margin_px: int,
            pane_top_px: int,
            pane_height_px: int,
            p2y,
            font,
        ):
            """Draw one line, one icon and one label per entry in ``_positions``.

            A position whose price maps outside the price pane is skipped.
            """
            if not self._positions:
                return

            for pos in self._positions:
                price_y_px = p2y(pos.price)
                if (
                    price_y_px < pane_top_px
                    or price_y_px > pane_top_px + pane_height_px
                ):
                    continue

                is_buy = pos.side == "buy"
                is_invisible = pos.visibility == "internal"
                line_color = self.BUY_POS_COLOR if is_buy else self.SELL_POS_COLOR

                pen = QPen(
                    QColor(line_color.red(), line_color.green(), line_color.blue(), 50),
                    1,
                    Qt.DashDotLine,
                )
                p.setPen(pen)
                p.drawLine(
                    left_px, int(price_y_px), w - right_margin_px, int(price_y_px)
                )

                icon_x = left_px + 2
                icon_y = int(price_y_px)
                icon_size = 7

                if is_invisible:
                    # Internal visibility draws a filled diamond.
                    color = self.INVISIBLE_ICON
                    if pos.filled:
                        color = QColor(color.red(), color.green(), color.blue(), 100)
                    diamond = QPolygonF(
                        [
                            QPointF(icon_x + icon_size, icon_y),
                            QPointF(icon_x + icon_size * 2, icon_y - icon_size),
                            QPointF(icon_x + icon_size * 3, icon_y),
                            QPointF(icon_x + icon_size * 2, icon_y + icon_size),
                        ]
                    )
                    p.setBrush(QBrush(color))
                    p.setPen(QPen(color.lighter(140), 1))
                    p.drawPolygon(diamond)
                else:
                    # Order-book visibility draws an open square with a centre dot.
                    color = self.VISIBLE_ICON
                    if pos.filled:
                        color = QColor(color.red(), color.green(), color.blue(), 100)
                    rect = QRectF(
                        icon_x + icon_size * 0.5,
                        icon_y - icon_size,
                        icon_size * 2,
                        icon_size * 2,
                    )
                    p.setBrush(Qt.NoBrush)
                    p.setPen(QPen(color, 1.5))
                    p.drawRect(rect)
                    p.setBrush(QBrush(color))
                    p.setPen(Qt.NoPen)
                    p.drawEllipse(QPointF(icon_x + icon_size * 1.5, icon_y), 2, 2)

                status = ""
                if pos.filled:
                    status = " FILLED"
                elif is_invisible:
                    status = " TRACKED"
                else:
                    status = " ON BOOK"
                label = f"{'B' if is_buy else 'S'}{pos.level}{status}"
                p.setFont(font)
                p.setPen(
                    QPen(
                        QColor(
                            line_color.red(), line_color.green(), line_color.blue(), 140
                        )
                    )
                )
                p.drawText(w - right_margin_px + 6, icon_y + 3, label)

        def _draw_call(self, ctx, h: int) -> None:
            """Draw the reversal badge, the call bar mark and the voter strip.

            The bar marked is the last candle, which is the bar the direction
            ``set_call`` took was voted on.
            """
            role = CALL_DIRECTION_ROLES.get(self._call_direction)
            if role is None:
                return
            p = ctx.p
            colour = getattr(self, role)
            self._draw_call_badge(p, ctx.w, ctx.font_sm, colour)
            self._draw_call_bar(ctx, colour)
            self._draw_call_strip(p, h, ctx.ML, ctx.font_sm)

        def _draw_call_badge(self, p: QPainter, w: int, font_sm: QFont, colour) -> None:
            """Draw the direction word in the header band, against the right edge."""
            text = CALL_BADGE_FORMAT.format(direction=self._call_direction.upper())
            font_badge = QFont(font_sm)
            font_badge.setBold(True)
            metrics = QFontMetrics(font_badge)
            badge = QRectF(
                w - metrics.horizontalAdvance(text) - 24,
                4,
                metrics.horizontalAdvance(text) + 16,
                18,
            )
            p.setBrush(QBrush(self.BADGE_SURFACE))
            p.setPen(QPen(colour, 1.2))
            p.drawRoundedRect(badge, 3, 3)
            p.setFont(font_badge)
            p.setPen(QPen(colour))
            p.drawText(badge, Qt.AlignCenter, text)

        def _draw_call_bar(self, ctx, colour) -> None:
            """Mark the last candle with a rule and a triangle beside its body.

            A bullish call points up under the bar's low and a bearish one
            points down over its high, so neither covers the price badge.
            """
            bar = ctx.visible_candles[-1]
            x = ctx.i2x(ctx.n - 1) + ctx.cw / 2
            p = ctx.p
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(colour, 1.0, Qt.DashLine))
            p.drawLine(int(x), int(ctx.price_top), int(x), int(ctx.price_bot))
            up = self._call_direction == CALL_BULLISH
            if up:
                tip = ctx.p2y(bar.low)
                base = tip + CALL_MARK_PX
            else:
                tip = ctx.p2y(bar.high)
                base = tip - CALL_MARK_PX
            p.setBrush(QBrush(colour))
            p.setPen(QPen(colour, 1.0))
            p.drawPolygon(
                QPolygonF(
                    [
                        QPointF(x, tip),
                        QPointF(x - CALL_MARK_PX, base),
                        QPointF(x + CALL_MARK_PX, base),
                    ]
                )
            )

        def _draw_call_strip(self, p: QPainter, h: int, left: int, font_sm: QFont):
            """Draw one row per ``_call_readings`` entry under the time axis.

            Each row's square carries the colour of the overlay drawing that
            voter, which ``_voter_colour`` resolves.
            """
            top = h - self._call_strip_h() + CALL_STRIP_PAD
            p.setFont(font_sm)
            for index, (voter, text) in enumerate(self._call_readings):
                y = top + index * CALL_ROW_H
                colour = self._voter_colour(voter)
                p.setBrush(QBrush(colour))
                p.setPen(QPen(colour, 1.0))
                p.drawRect(QRectF(left, y + 2, CALL_SWATCH_PX, CALL_SWATCH_PX))
                p.setPen(QPen(self.TEXT_LIGHT))
                p.drawText(
                    int(left + CALL_SWATCH_PX + 6), int(y + CALL_SWATCH_PX + 1), text
                )

        def _draw_header(self, p: QPainter, w: int, font_hdr: QFont, font_sm: QFont):
            p.setFont(font_hdr)
            p.setPen(QPen(self.ACCENT))
            p.drawText(8, 18, self._symbol)

            p.setFont(font_sm)
            p.setPen(QPen(self.TEXT_DIM))
            offset = QFontMetrics(font_hdr).horizontalAdvance(self._symbol) + 16
            info_parts = [self._current_tf]
            if self._source_label:
                info_parts.append(self._source_label)
            if self._candles:
                info_parts.append(f"{len(self._candles)} candles")
            if self._positions:
                n_inv = sum(1 for pm in self._positions if pm.visibility == "internal")
                n_vis = len(self._positions) - n_inv
                parts = []
                if n_inv:
                    parts.append(f"{n_inv} invisible")
                if n_vis:
                    parts.append(f"{n_vis} on book")
                info_parts.append(" | ".join(parts))
            p.drawText(int(offset), 18, "  \u2022  ".join(info_parts))

            if self._error_text:
                p.setPen(QPen(self.ERROR_TEXT))
                p.drawText(8, 18 + 14, self._error_text)

    class CandlestickChart(ChartPainter, QWidget):
        """The Charts tab's chart: ``ChartPainter`` in a window that takes a mouse.

        ``paintEvent`` hands ``paint_to`` a widget painter, so the pixels come
        from the same routine ``render_chart_png`` draws a post image with.
        """

        timeframe_changed = Signal(str)

        def __init__(self, symbol: str = "", parent=None):
            QWidget.__init__(self, parent)
            ChartPainter.__init__(self, symbol)
            self.setAccessibleName("Candlestick Chart")
            self.setMinimumHeight(200)
            self.setMouseTracking(True)

            # _height_override holds a dragged height; auto-expand never goes under it.
            self._height_override: Optional[int] = None
            self._resize_active = False
            self._resize_start_y: Optional[int] = None
            self._resize_start_height: Optional[int] = None
            self._drag_active = False
            self._drag_start_x: Optional[int] = None
            self._drag_start_visible_start: Optional[int] = None

        def _repaint(self) -> None:
            """Schedule the widget's own repaint."""
            self.update()

        def set_candles(self, candles: list[Candle]) -> None:
            """Take the candles, then give the sub-panes they filled their height.

            The first candles decide which sub-panes hold a series, so the
            height the chart needs is only known once they have arrived.
            """
            super().set_candles(candles)
            try:
                self._apply_height_for_panes()
            except Exception as exc:
                logger.debug("chart height not re-applied on candles: %s", exc)

        def _apply_height_for_panes(self) -> None:
            """Raise the minimum height to ``_natural_height_for_panes``.

            ``_height_override`` from a grip drag wins when it is
            taller, and the parent widget is raised to the same height
            plus 36.
            """
            target = self._natural_height_for_panes()
            if self._height_override is not None:
                target = max(target, self._height_override)
            if target != self.minimumHeight():
                self.setMinimumHeight(target)
                self.updateGeometry()
                _parent = self.parent()
                if _parent is not None:
                    try:
                        _parent.setMinimumHeight(target + 36)
                        _parent.updateGeometry()
                    except Exception as exc:
                        logger.debug("chart parent height not raised: %s", exc)

        def mouseMoveEvent(self, event):
            self._mouse_x = int(event.position().x())
            self._mouse_y = int(event.position().y())
            grip_top_px = self.height() - self._resize_grip_h
            in_grip = self._mouse_y >= grip_top_px
            if self._resize_active or in_grip:
                self.setCursor(Qt.SizeVerCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            if self._resize_active and self._resize_start_y is not None:
                delta = self._mouse_y - self._resize_start_y
                new_h = max(200, (self._resize_start_height or 200) + delta)
                self._height_override = new_h
                self.setMinimumHeight(new_h)
                # The parent grows too, plus 36px for the toolbar above the chart.
                _parent = self.parent()
                if _parent is not None:
                    try:
                        _parent.setMinimumHeight(new_h + 36)
                        _parent.updateGeometry()
                    except Exception as exc:
                        logger.debug("chart parent height not dragged: %s", exc)
                self.updateGeometry()
                self._repaint()
                return
            if self._drag_active and self._drag_start_x is not None:
                w = self.width()
                ML, MR = 8, 78
                chart_w = max(1, w - ML - MR)
                count = self._effective_visible_count()
                if count > 0:
                    pixels_per_candle = chart_w / count
                    delta_pixels = self._drag_start_x - self._mouse_x
                    delta_candles = int(delta_pixels / max(pixels_per_candle, 0.001))
                    new_start = (self._drag_start_visible_start or 0) + delta_candles
                    n = len(self._candles)
                    new_start = max(0, min(n - count, new_start))
                    self._visible_start = new_start
            self._repaint()

        def mousePressEvent(self, event):
            if event.button() == Qt.LeftButton:
                # The bottom 8px grip takes precedence over pan.
                press_y_px = int(event.position().y())
                grip_top_px = self.height() - self._resize_grip_h
                if press_y_px >= grip_top_px:
                    self._resize_active = True
                    self._resize_start_y = press_y_px
                    self._resize_start_height = self.height()
                    return
                self._drag_active = True
                self._drag_start_x = int(event.position().x())
                self._drag_start_visible_start = (
                    self._visible_start if self._visible_start is not None else 0
                )

        def mouseReleaseEvent(self, event):
            if event.button() == Qt.LeftButton:
                self._drag_active = False
                self._drag_start_x = None
                self._resize_active = False
                self._resize_start_y = None
                self._resize_start_height = None

        def mouseDoubleClickEvent(self, event):
            self._visible_start = None
            self._visible_count = None
            self._y_zoom_pct = 1.0
            self._repaint()

        def wheelEvent(self, event):
            """Zoom on the wheel.

            A plain wheel moves ``_visible_count`` around the cursor;
            Ctrl and the wheel move ``_y_zoom_pct``.
            """
            n = len(self._candles)
            if n == 0:
                return
            delta = event.angleDelta().y()
            zoom_factor = 0.85 if delta > 0 else 1.18

            modifiers = event.modifiers()
            if modifiers & Qt.ControlModifier:
                new_y = self._y_zoom_pct * zoom_factor
                self._y_zoom_pct = max(0.05, min(4.0, new_y))
                self._repaint()
                return

            cur_count = self._effective_visible_count()
            cur_start = self._effective_visible_start()
            new_count = max(8, min(n, int(cur_count * zoom_factor)))
            if new_count == cur_count:
                return
            mx = int(event.position().x())
            ML, MR = 8, 78
            chart_w = max(1, self.width() - ML - MR)
            cursor_frac = max(0.0, min(1.0, (mx - ML) / chart_w))
            anchor_idx = cur_start + cursor_frac * cur_count
            new_start = int(anchor_idx - cursor_frac * new_count)
            new_start = max(0, min(n - new_count, new_start))
            self._visible_start = new_start
            self._visible_count = new_count
            self._repaint()

        def leaveEvent(self, event):
            self._mouse_x = None
            self._mouse_y = None
            self._repaint()

        def paintEvent(self, event):
            p = QPainter(self)
            self.paint_to(p, self.width(), self.height())
            p.end()

    class ChartPanel(QWidget):
        """One CandlestickChart with a timeframe picker above and toggles below.

        The toggle row carries one check box per ``CHART_OVERLAYS`` entry, each
        starting at that entry's ``starts_on``.
        """

        TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"]

        TOGGLE_FONT_PX = 9
        TOGGLE_ROW_SPACING_PX = 6
        TOGGLE_ROW_MARGIN_PX = 4

        def __init__(self, symbol: str = "", parent=None):
            super().__init__(parent)
            self.setAccessibleName("Chart Panel")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2)

            toolbar = QHBoxLayout()
            toolbar.setContentsMargins(4, 2, 4, 2)

            self._tf_combo = QComboBox()
            self._tf_combo.addItems(self.TIMEFRAMES)
            self._tf_combo.setCurrentText("1h")
            self._tf_combo.setMaximumWidth(90)
            self._tf_combo.currentTextChanged.connect(self._on_tf_changed)
            toolbar.addWidget(QLabel("TF:"))
            toolbar.addWidget(self._tf_combo)

            toolbar.addStretch()

            legend = QHBoxLayout()
            legend.setSpacing(12)
            inv_lbl = QLabel("\u25c6 Invisible")
            inv_lbl.setStyleSheet("color: #ffa000; font-size: 9px;")
            legend.addWidget(inv_lbl)
            vis_lbl = QLabel("\u25a1 On Book")
            vis_lbl.setStyleSheet("color: #00b4ff; font-size: 9px;")
            legend.addWidget(vis_lbl)
            toolbar.addLayout(legend)

            self._source_label = QLabel("")
            self._source_label.setStyleSheet("color: #555; font-size: 9px;")
            toolbar.addWidget(self._source_label)

            layout.addLayout(toolbar)

            self._chart = CandlestickChart(symbol)
            self._chart.setMinimumHeight(250)
            layout.addWidget(self._chart)

            self._toggles: dict[str, QCheckBox] = {}
            toggle_row = QHBoxLayout()
            toggle_row.setSpacing(self.TOGGLE_ROW_SPACING_PX)
            toggle_row.setContentsMargins(
                self.TOGGLE_ROW_MARGIN_PX,
                self.TOGGLE_ROW_MARGIN_PX,
                self.TOGGLE_ROW_MARGIN_PX,
                self.TOGGLE_ROW_MARGIN_PX,
            )
            for overlay in CHART_OVERLAYS:
                box = QCheckBox(overlay.label)
                box.setAccessibleName(f"{overlay.label} toggle")
                box.setStyleSheet(
                    f"color: {self._chart.overlay_colour(overlay).name()}; "
                    f"font-size: {self.TOGGLE_FONT_PX}px;"
                )
                box.setToolTip(overlay.tooltip)
                box.setChecked(overlay.starts_on)
                box.toggled.connect(
                    lambda on, key=overlay.key: self._toggle_indicator(key, on)
                )
                toggle_row.addWidget(box)
                self._toggles[overlay.key] = box
            toggle_row.addStretch()
            layout.addLayout(toggle_row)

        @property
        def chart(self) -> CandlestickChart:
            return self._chart

        @property
        def toggles(self) -> dict:
            """The check box drawn for each ``CHART_OVERLAYS`` key."""
            return self._toggles

        @property
        def timeframe(self) -> str:
            return self._tf_combo.currentText()

        def _on_tf_changed(self, tf: str):
            self._chart.set_timeframe(tf)
            self._chart.timeframe_changed.emit(tf)

        def _toggle_indicator(self, name: str, on: bool):
            """Switch one overlay key on the chart and repaint it.

            ``_apply_height_for_panes`` then raises the chart's minimum
            height for a newly visible sub-pane.
            """
            self._chart._overlay_shown[name] = on
            try:
                self._chart._apply_height_for_panes()
            except Exception as exc:
                logger.debug("chart height not re-applied on toggle: %s", exc)
            self._chart.update()

        def set_source(self, source: str):
            self._source_label.setText(source)
            self._chart.set_source_label(source)

    def resolve_palette(tokens=DEFAULT_THEME_TOKENS) -> None:
        """Write every ``PALETTE_ROLES`` colour onto ``ChartPainter``.

        Called once at import so a chart built before any theme is applied
        still paints, and again by ``set_theme`` for one instance.
        ``CandlestickChart`` inherits what is written here.
        """
        for role, (field, alpha) in ChartPainter.PALETTE_ROLES.items():
            setattr(ChartPainter, role, _role_colour(tokens, field, alpha))

    resolve_palette()

    def render_chart_png(
        candles,
        symbol: str,
        timeframe: str,
        path,
        voters=(),
        max_overlays: int = NO_OVERLAY_CAP,
        tokens=None,
        width_px: int = POST_IMAGE_WIDTH_PX,
        direction: str = "",
        readings=(),
    ) -> ChartImage:
        """Draw ``candles`` through ``ChartPainter`` and write a PNG at ``path``.

        No window is shown: ``paint_to`` draws onto a ``QImage``, which Qt
        allows off the GUI thread. ``voters`` are the confirming indicators,
        ``max_overlays`` is the cap the ATA-SPM settings page sets, and
        ``set_call`` takes ``direction`` with the ``readings`` those voters
        published.
        """
        if QGuiApplication.instance() is None:
            return ChartImage(note=NO_APPLICATION_NOTE)
        held = list(candles or [])
        drawn, undrawn = overlays_for_voters(voters, int(max_overlays))
        painter = ChartPainter(str(symbol))
        painter.set_theme(tokens if tokens is not None else DEFAULT_THEME_TOKENS)
        painter.set_timeframe(str(timeframe))
        painter.show_only(drawn)
        painter.set_candles(held)
        painter.set_call(direction, readings)
        if not held:
            painter.set_error(
                NO_CANDLES_NOTE.format(symbol=symbol, timeframe=timeframe)
            )
        if undrawn:
            painter.set_source_label(NOT_DRAWN_NOTE.format(voters=", ".join(undrawn)))
        height_px = painter._natural_height_for_panes()
        image = QImage(int(width_px), int(height_px), QImage.Format_ARGB32)
        image.fill(painter.BG_TOP)
        image_painter = QPainter(image)
        painter.paint_to(image_painter, int(width_px), int(height_px))
        image_painter.end()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not image.save(str(target)):
            return ChartImage(note=IMAGE_NOT_WRITTEN_NOTE.format(path=target.name))
        return ChartImage(
            path=str(target),
            width_px=image.width(),
            height_px=image.height(),
            bars=len(held),
            drawn=drawn,
            undrawn=undrawn,
        )

else:

    def render_chart_png(
        candles,
        symbol: str,
        timeframe: str,
        path,
        voters=(),
        max_overlays: int = NO_OVERLAY_CAP,
        tokens=None,
        width_px: int = POST_IMAGE_WIDTH_PX,
        direction: str = "",
        readings=(),
    ) -> ChartImage:
        """Answer that no image was drawn, because PySide6 is not installed."""
        del candles, symbol, timeframe, path, voters, max_overlays, tokens, width_px
        del direction, readings
        return ChartImage(note=NO_QT_NOTE)
