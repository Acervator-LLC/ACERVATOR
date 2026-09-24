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
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src._variant import resolve_variant
from src.core.signal_contract import emit as _pin_emit
from src.gui import design_system as ds
from src.gui.main_tabs.native_chart_surface import (
    CAPTION_PX,
    CHART_PANEL_MIN_HEIGHT_PX,
    CHART_SCROLL_NAME,
    CONTROL_HEIGHT_PX,
    CROSSHAIR_TIME_FORMAT,
    FILL_TAG_FORMAT,
    FMT_GROUPED_DECIMALS,
    FOLD_SIDE,
    INDICATOR_STYLE_FORMAT,
    LEFT_MARGIN_PX,
    LEGEND_INVISIBLE_FIELD,
    LEGEND_INVISIBLE_TEXT,
    LEGEND_ON_BOOK_FIELD,
    LEGEND_ON_BOOK_TEXT,
    MARK_GLYPHS,
    MARK_HEIGHT_FRACTION,
    MARK_OUTLINE_PX,
    MARK_WIDTH_RATIO,
    PANEL_SOURCE_FIELD,
    PRICE_FORMAT_BANDS,
    PRICE_PANE_LAYOUT_FLOOR_PX,
    PRICE_PANE_PAINT_FLOOR_PX,
    RIGHT_MARGIN_PX,
    SCRUM_SIDE,
    SUB_PANE_FOLD_PX,
    SUB_PANE_LABEL_PX,
    SUB_PANE_READABLE_PX,
    TAG_HEIGHT_PX,
    TIMEFRAME_COMBO_MAX_WIDTH_PX,
    TIMEFRAME_LABEL,
    TOGGLE_BOX_PX,
    Y_ZOOM_DEFAULT,
    candle_at_x,
    clamp_y_zoom,
    device_pen_width,
    fill_label,
    effective_visible_count,
    effective_visible_start,
    fmt_price,
    gmt_label,
    pan_start,
    readout_lines,
    sub_pane_height,
    zoom_factor,
    zoom_window,
)
from src.gui.theme_engine import CYBERPUNK_DARK, THEMES, applied_theme
from src.trading.ta_engine import (
    ADXIndicator,
    BollingerBands,
    IchimokuCloud,
    KaufmanERIndicator,
    MACD,
    RSIIndicator,
    SlingshotIndicator,
    StochasticRSI,
    SupertrendIndicator,
    VortexIndicator,
    ZScoreIndicator,
)

logger = logging.getLogger("acervator.gui")

# Fraction of one grid step the last price tick may overshoot by and still draw.
GRID_TICK_TOLERANCE = 1e-9

#: The pin ``ChartPainter.set_overlay`` writes once per press, through ``_pin_emit``.
TOGGLED_PIN = "charts.indicator.toggled"

#: The pin ``ChartPainter.set_candles`` writes once the series recompute.
DRAWN_PIN = "charts.indicators.drawn"

#: The pin ``ChartPainter.set_theme`` writes once every ``PALETTE_ROLES`` colour resolves.
THEME_PIN = "charts.theme.applied"

#: The pin ``paint_to`` writes when the set of annotations it drew changes.
ANNOTATIONS_PIN = "charts.annotations.drawn"

#: The pin ``ChartPainter._emit_view`` writes each time the visible window moves.
VIEW_PIN = "charts.view.changed"
VIEW_CAUSE_ZOOM = "zoom"
VIEW_CAUSE_Y_ZOOM = "y_zoom"
VIEW_CAUSE_PAN = "pan"
VIEW_CAUSE_RESET = "reset"

#: The pin ``ChartPainter._emit_crosshair`` writes, at most once per
#: ``CROSSHAIR_PIN_EVERY_S`` per painter, naming the candle under the pointer.
CROSSHAIR_PIN = "charts.crosshair.shown"
CROSSHAIR_PIN_EVERY_S = 0.25
CROSSHAIR_SOURCE_PAINT = "paint"
CROSSHAIR_SOURCE_PAGE = "page"

#: The design system's families and pixel sizes the painter sets its type in.
HEADER_FONT_PX = ds.TYPE_H4
OHLC_FONT_PX = ds.TYPE_SMALL
CAPTION_FONT_PX = ds.TYPE_CAPTION

#: A wick's width as a share of one candle column; never under one device pixel.
WICK_FRACTION = 0.14

#: The width of an indicator line, in logical pixels.
LINE_WIDTH_PX = 1.2

#: A right-edge tag's height, its text padding and its inset from the edge.
TAG_H_PX = TAG_HEIGHT_PX
TAG_PAD_PX = 5
TAG_INSET_PX = 2

#: The seconds one candle of each timeframe spans, for the strip's column count.
TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}
DEFAULT_CANDLE_SECONDS = 3600

#: The tag texts the annotations carry.
TARGET_TAG_FORMAT = "TARGET {price}"
CEILING_TAG_FORMAT = "CEILING {price}"
STRIP_TAG_FORMAT = "STRIP {side} {candles}c"
SCRUM_ARMED_TAG = "SCRUM ARMED"
FOLD_ARMED_TAG = "FOLD ARMED"
POSITION_TAG_FORMAT = "POSITION {price}"
STRIP_UPPER = "upper"
STRIP_LOWER = "lower"

#: The header texts naming the fills the paint refused, one format a reason,
#: so a market whose fills fall outside the drawn candles says so on screen.
FILLS_OLDER_HEADER_FORMAT = "{count} {fills} older than this chart"
FILLS_NEWER_HEADER_FORMAT = "{count} {fills} newer than this chart"
FILLS_OFF_SCALE_HEADER_FORMAT = "{count} {fills} off the price scale"
FILL_WORD = "fill"
FILLS_WORD = "fills"

#: The published reference levels each sub-pane rules: Wilder's RSI 30 and
#: 70, ADX 20 and 25, and the Z-Score reversal threshold either side of 0.
RSI_BANDS = (30.0, 70.0)
ADX_BANDS = (20.0, 25.0)
ZSCORE_BANDS = (-2.0, 2.0)

#: The fixed scales the RSI, ADX and KER sub-panes draw on.
PERCENT_SCALE = (0.0, 100.0)
RATIO_SCALE = (0.0, 1.0)

#: The least half-range the Z-Score sub-pane draws, so the bands sit inside it.
ZSCORE_SCALE_FLOOR = 3.0

#: The price pane's left margin and its right margin, which holds the price axis.
CHART_LEFT_MARGIN_PX = LEFT_MARGIN_PX
CHART_RIGHT_MARGIN_PX = RIGHT_MARGIN_PX

#: The pixel height of one legend line in the value field, the field's inset
#: from the price pane's left and bottom edges and its inner padding, and the
#: gap between a label and its value.
LEGEND_ROW_H = 13
FIELD_PAD_PX = 6
FIELD_LABEL_GAP_PX = 4

#: The legend text of an overlay switched off, and of a series with no value yet.
LEGEND_OFF_TEXT = "off"
LEGEND_NO_VALUE_TEXT = "-"

#: One toggle box's style sheet: the label in the overlay's colour at the
#: caption size, the indicator ``box`` pixels square with a one-pixel border.
TOGGLE_STYLE_FORMAT = (
    "QCheckBox {{ color: {color}; font-size: {font_px}px; spacing: {gap}px; }}"
    "QCheckBox::indicator {{ width: {box}px; height: {box}px; "
    "border-width: 1px; border-radius: 2px; }}"
)

try:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QComboBox,
        QCheckBox,
        QFrame,
        QScrollArea,
        QSizePolicy,
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
            "Slingshot marks — diamond at a squeeze release (Bollinger bands "
            "back outside the Keltner channel, signed by momentum), circle at "
            "a Bollinger snapback, from SlingshotIndicator.lines. Opaque marks "
            "sit over the bands, so it starts off."
        ),
        voter="slingshot",
    ),
    ChartOverlay(
        key="adx",
        label="ADX",
        colour_field="chart_last_price",
        pane=SUB_PANE,
        occludes=False,
        draw="_draw_adx",
        tooltip="ADX (14) with +DI and -DI, 0..100, 20 and 25 ruled, sub-pane",
        voter="adx",
    ),
    ChartOverlay(
        key="supertrend",
        label="STrd",
        colour_field="chart_up_edge",
        pane=PRICE_PANE,
        occludes=False,
        draw="_draw_supertrend",
        tooltip="Supertrend (10, 3.0): the ATR stop under price while bullish, over it while bearish",
        voter="supertrend",
    ),
    ChartOverlay(
        key="zscore",
        label="ZSc",
        colour_field="chart_zone_scrum",
        pane=SUB_PANE,
        occludes=False,
        draw="_draw_zscore",
        tooltip="Z-Score (50) of the close against its mean, VWMA-smoothed over 3, ±2 ruled, sub-pane",
        voter="zscore",
    ),
    ChartOverlay(
        key="ker",
        label="KER",
        colour_field="chart_trend_slow",
        pane=SUB_PANE,
        occludes=False,
        draw="_draw_ker",
        tooltip="Kaufman Efficiency Ratio (10), 0..1, sub-pane",
        voter="kaufman_er",
    ),
    ChartOverlay(
        key="rsi",
        label="RSI",
        colour_field="chart_down_edge",
        pane=SUB_PANE,
        occludes=False,
        draw="_draw_rsi",
        tooltip="Wilder RSI (14), 0..100, 30 and 70 ruled, sub-pane",
        voter="rsi",
    ),
    ChartOverlay(
        key="zscore_point",
        label="ZPt",
        colour_field="chart_zone_scrum",
        pane=PRICE_PANE,
        occludes=True,
        draw="_draw_zscore_point",
        tooltip=(
            "Z-Score algo point — the resistance and support prices the "
            "averaged reversals project (mean + target z × deviation). "
            "Lines over the price pane, so it starts off."
        ),
        voter="zscore",
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

#: The gap after each voter name on a folded strip row, and the text gap
#: after a swatch.
CALL_FOLD_GAP_PX = 14
CALL_SWATCH_GAP_PX = 6

#: The half-width and height of the triangle marking the call bar's close.
CALL_MARK_PX = 6

#: No ``set_call`` reading, so ``_call_strip_h`` takes no height.
NO_CALL_STRIP = 0

#: The pixel height one wrapped ``set_caption`` line takes under the voter
#: strip, the padding over and under the block, and its side margin.
CAPTION_ROW_H = 13
CAPTION_STRIP_PAD = 8
CAPTION_SIDE_PAD = 8

#: No ``set_caption`` text, so ``_caption_strip_h`` takes no height.
NO_CAPTION_STRIP = 0

#: A width ``_natural_height_for_panes`` was not given, which cannot be
#: wrapped in, so the caption takes no height at it.
NO_CAPTION_WIDTH = 0

#: A ``render_chart_png`` height at or under this takes the natural height.
NO_IMAGE_HEIGHT = 0

#: ``render_chart_png``'s note for a height under ``_least_height_for_panes``.
IMAGE_TOO_SHORT_NOTE = (
    "{width}x{height} cannot hold the panes: {least} px is the least height "
    "at that width."
)


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

    def css_colour(colour: QColor) -> str:
        """``colour`` as the CSS ``rgba()`` text a web page paints with."""
        return "rgba(%d, %d, %d, %.3f)" % (
            colour.red(),
            colour.green(),
            colour.blue(),
            colour.alphaF(),
        )

    def design_font(stack: str, size_px: int, bold: bool = False) -> QFont:
        """A ``QFont`` on the design system's family ``stack`` at ``size_px`` pixels."""
        font = QFont()
        font.setFamilies([one.strip().strip("'\"") for one in stack.split(",")])
        font.setPixelSize(int(size_px))
        font.setWeight(QFont.Bold if bold else QFont.Normal)
        font.setHintingPreference(QFont.PreferFullHinting)
        return font

    def caption_font() -> QFont:
        """The mono font the legend, the axes, the tags and the caption are set in."""
        return design_font(ds.FONT_FAMILY_MONO, CAPTION_FONT_PX)

    def header_font() -> QFont:
        """The UI font the header symbol is set in."""
        return design_font(ds.FONT_FAMILY_UI, HEADER_FONT_PX, bold=True)

    def ohlc_font() -> QFont:
        """The mono font the OHLC row is set in."""
        return design_font(ds.FONT_FAMILY_MONO, OHLC_FONT_PX, bold=True)

    def theme_in_force():
        """The ``ThemeTokens`` ``ThemeManager.apply_theme`` last painted."""
        return THEMES.get(applied_theme(), DEFAULT_THEME_TOKENS)

    @dataclass
    class PaintContext:
        """The geometry of one paint pass, handed to every overlay method.

        ``i2x`` maps a visible index to a pixel and ``p2y`` maps a price to one;
        ``pen_w`` maps a logical pen width to whole device pixels, ``snap`` a
        coordinate to the centre of its device pixel, and ``px`` is one device pixel.
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
        pen_w: object
        snap: object
        px: float
        paint_sub_grid: object = None
        rule_line: object = None
        sub_axis_label: object = None
        paint_oscillator: object = None
        strip_folded: bool = False

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
        ADX_LINE: QColor
        DI_PLUS: QColor
        DI_MINUS: QColor
        ST_BULL: QColor
        ST_BEAR: QColor
        ZSCORE_LINE: QColor
        ZSCORE_ZONE: QColor
        KER_LINE: QColor
        RSI_LINE: QColor
        GAP_MARK: QColor
        MARKER_SCRUM: QColor
        MARKER_FOLD: QColor
        MARKER_DIST: QColor
        MARKER_BUY: QColor
        MARKER_SELL: QColor
        TB_ANCHOR: QColor
        TB_CEILING: QColor
        GLOW_SCRUM: QColor
        GLOW_FOLD: QColor
        BADGE_SURFACE: QColor
        FIELD_SURFACE: QColor
        BADGE_EDGE: QColor
        MARKER_EDGE: QColor
        GRIP: QColor
        ERROR_TEXT: QColor
        PANEL_SOURCE_TEXT: QColor
        TAG_TEXT: QColor
        STRIP_FILL: QColor
        STRIP_EDGE: QColor
        FILL_TAG_SURFACE: QColor

        #: Each painted colour, as the theme field it reads and its alpha byte.
        PALETTE_ROLES: dict[str, tuple[str, int]] = {
            "PANEL_SOURCE_TEXT": (PANEL_SOURCE_FIELD, 255),
            "TAG_TEXT": ("chart_bg_top", 255),
            "STRIP_FILL": ("chart_band", 40),
            "STRIP_EDGE": ("chart_band", 210),
            "FILL_TAG_SURFACE": ("chart_bg_top", 215),
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
            "ADX_LINE": ("chart_last_price", 230),
            "DI_PLUS": ("chart_bull", 200),
            "DI_MINUS": ("chart_bear", 200),
            "ST_BULL": ("chart_bull", 230),
            "ST_BEAR": ("chart_bear", 230),
            "ZSCORE_LINE": ("chart_zone_scrum", 230),
            "ZSCORE_ZONE": ("chart_zone_scrum", 170),
            "KER_LINE": ("chart_trend_slow", 230),
            "RSI_LINE": ("chart_down_edge", 230),
            "GAP_MARK": ("chart_gap", 200),
            "MARKER_SCRUM": ("chart_last_price", 255),
            "MARKER_FOLD": ("chart_trend_slow", 255),
            "MARKER_DIST": ("chart_event_mark", 255),
            "MARKER_BUY": ("chart_bull", 255),
            "MARKER_SELL": ("chart_bear", 255),
            "TB_ANCHOR": ("chart_trend_slow", 200),
            "TB_CEILING": ("chart_zone_scrum", 220),
            "GLOW_SCRUM": ("chart_bull", 220),
            "GLOW_FOLD": ("chart_bear", 220),
            "BADGE_SURFACE": ("chart_bg_top", 235),
            "FIELD_SURFACE": ("chart_bg_top", 205),
            "BADGE_EDGE": ("chart_grid", 255),
            "MARKER_EDGE": ("chart_axis_text", 120),
            "GRIP": ("chart_axis_text", 110),
            "ERROR_TEXT": ("chart_bear", 255),
        }

        TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"]

        #: Only a chart in a window draws the resize grip; an image has no edge to drag.
        DRAWS_GRIP = False

        def _apply_tokens(self, tokens) -> int:
            """Resolve every ``PALETTE_ROLES`` colour from ``tokens`` onto this instance.

            A field ``tokens`` lacks keeps ``DEFAULT_THEME_TOKENS``' value for
            that role; the count answered is the roles ``tokens`` resolved.
            """
            self._theme_tokens = tokens
            resolved = 0
            for role, (field, alpha) in self.PALETTE_ROLES.items():
                source = tokens if hasattr(tokens, field) else DEFAULT_THEME_TOKENS
                resolved += source is tokens
                setattr(self, role, _role_colour(source, field, alpha))
            return resolved

        def set_theme(self, tokens) -> None:
            """Re-resolve every ``PALETTE_ROLES`` colour from ``tokens`` and write ``THEME_PIN``.

            The instance values shadow the class ones, so the chart repaints in
            the theme without any other object holding a colour.
            """
            resolved = self._apply_tokens(tokens)
            _pin_emit(
                THEME_PIN,
                actual=resolved,
                expected=len(self.PALETTE_ROLES),
                context={
                    "theme": str(getattr(tokens, "name", "") or ""),
                    "variant": resolve_variant(),
                    "symbol": self._symbol,
                },
            )
            self._repaint()

        def theme_name(self) -> str:
            """The name of the ``ThemeTokens`` the painter paints in."""
            return str(getattr(self._theme_tokens, "name", "") or "")

        def overlay_colour(self, overlay: ChartOverlay) -> QColor:
            """The colour one overlay's label and check box carry."""
            return self.field_colour(overlay.colour_field)

        def field_colour(self, field: str) -> QColor:
            """One ``ThemeTokens`` field of the painter's theme, opaque.

            A field the theme lacks reads ``DEFAULT_THEME_TOKENS``.
            """
            source = (
                self._theme_tokens
                if hasattr(self._theme_tokens, field)
                else DEFAULT_THEME_TOKENS
            )
            return _role_colour(source, field, 255)

        def _repaint(self) -> None:
            """Ask the host to redraw. A painter with no window has none."""
            return None

        def __init__(self, symbol: str = ""):
            self._theme_tokens = theme_in_force()
            self._apply_tokens(self._theme_tokens)
            self._annotations_digest = ""
            self._landing_strip: Optional[dict] = None
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
            self._caption_lines: tuple = ()
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
            self._slingshot_data: list = []  # [SlingshotBar | None, ...]
            self._adx_data: list = []  # [(di_plus, di_minus, adx) | None, ...]
            self._supertrend_data: list = []  # [(line, bullish, atr) | None, ...]
            self._zscore_data: list = []  # [ZScoreBar | None, ...]
            self._ker_data: list = []  # [ratio | None, ...]
            self._rsi_data: list = []  # [rsi | None, ...]
            self._bbullseye_data: list = []
            # The (vmin, vmax) each sub-pane last drew on, by overlay key.
            self._sub_scale: dict[str, tuple] = {}

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

            # None draws every sub-pane at SUB_PANE_READABLE_PX; a grip drag
            # writes the height set_pane_drag_height works out.
            self._sub_pane_px: Optional[int] = None

            # None on either bound fits all candles; _y_zoom_pct scales price padding.
            self._visible_start: Optional[int] = None
            self._visible_count: Optional[int] = None
            self._y_zoom_pct: float = Y_ZOOM_DEFAULT
            self._drag_active = False
            self._drag_start_x: Optional[int] = None
            self._drag_start_visible_start: Optional[int] = None
            # What the last paint_to laid out and drew for the crosshair.
            self._geometry: dict = {}
            self._readout: list = []
            self._readout_candle: Optional[int] = None
            # The fills of the window keyed by candle index, for the readout.
            self._fills_on_candle: dict = {}
            # The fills the last paint refused, by the reason it refused them:
            # older than the drawn window, past its end, or off the price scale.
            self._fills_before_window = 0
            self._fills_after_window = 0
            self._fills_off_price = 0

        @property
        def symbol(self) -> str:
            return self._symbol

        @symbol.setter
        def symbol(self, value: str):
            self._symbol = value
            self._repaint()

        def set_candles(self, candles: list[Candle]) -> None:
            """Take the candles, recompute every series and write ``DRAWN_PIN``.

            The pin's ``actual`` is the switched-on entries of
            ``legend_entries`` holding a value on the last candle, and
            ``expected`` is every switched-on entry.
            """
            self._candles = candles
            self._error_text = ""
            if candles:
                self._status_text = f"{len(candles)} candles"
                self._compute_indicators()
                shown = [one for one in self.legend_entries() if one["on"]]
                _pin_emit(
                    DRAWN_PIN,
                    actual=sum(1 for one in shown if one["has_value"]),
                    expected=len(shown),
                    context={
                        "symbol": self._symbol,
                        "timeframe": self._current_tf,
                        "candles": len(candles),
                        "keys": [one["key"] for one in shown],
                        "values": {one["key"]: one["text"] for one in shown},
                    },
                )
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

        def _call_strip_h(
            self, width: int = NO_CAPTION_WIDTH, folded: bool = False
        ) -> int:
            """The pixel height ``_call_readings`` takes under the time axis.

            One row per reading, or ``folded`` the rows ``_folded_call_rows``
            lays the voter names on at ``width``.
            """
            if not self._call_readings:
                return NO_CALL_STRIP
            rows = (
                len(self._folded_call_rows(width))
                if folded
                else len(self._call_readings)
            )
            return CALL_STRIP_PAD * 2 + CALL_ROW_H * rows

        def _folded_call_rows(self, width: int) -> tuple:
            """``_call_readings`` voters laid left to right, each as its ``_voter_label`` after a swatch.

            Each entry is ``(voter, label, x)``; a row wraps at the chart's right
            margin, and a width of ``NO_CAPTION_WIDTH`` lays one row.
            """
            metrics = QFontMetrics(caption_font())
            room = int(width) - CHART_RIGHT_MARGIN_PX
            rows: list = []
            row: list = []
            x = CHART_LEFT_MARGIN_PX
            for voter, _text in self._call_readings:
                label = self._voter_label(voter)
                span = (
                    CALL_SWATCH_PX
                    + CALL_SWATCH_GAP_PX
                    + metrics.horizontalAdvance(label)
                )
                if row and int(width) > NO_CAPTION_WIDTH and x + span > room:
                    rows.append(tuple(row))
                    row = []
                    x = CHART_LEFT_MARGIN_PX
                row.append((voter, label, x))
                x += span + CALL_FOLD_GAP_PX
            if row:
                rows.append(tuple(row))
            return tuple(rows)

        def set_caption(self, text: str) -> None:
            """Take the standardised message this chart image carries.

            ``_draw_caption_strip`` paints it under the voter strip, so a chart
            opened from the post folder reads with its own wording.
            """
            self._caption_lines = tuple(
                one.strip() for one in str(text or "").split("\n") if one.strip()
            )
            self._repaint()

        def _wrap_caption(self, width: int) -> tuple:
            """``_caption_lines`` broken at ``width``, measured in the caption font.

            A word wider than the room left stands on its own line rather than
            being cut.
            """
            metrics = QFontMetrics(caption_font())
            room = int(width) - CAPTION_SIDE_PAD * 2
            wrapped: list = []
            for line in self._caption_lines:
                held = ""
                for word in line.split():
                    trial = f"{held} {word}".strip()
                    if held and metrics.horizontalAdvance(trial) > room:
                        wrapped.append(held)
                        held = word
                    else:
                        held = trial
                if held:
                    wrapped.append(held)
            return tuple(wrapped)

        def _caption_strip_h(self, width: int) -> int:
            """The pixel height the wrapped caption takes under the voter strip."""
            if not self._caption_lines or int(width) <= NO_CAPTION_WIDTH:
                return NO_CAPTION_STRIP
            return CAPTION_STRIP_PAD * 2 + CAPTION_ROW_H * len(
                self._wrap_caption(width)
            )

        def _voter_label(self, voter: str) -> str:
            """The label of the switched-on overlay drawing ``voter``, else ``voter`` itself."""
            for one in CHART_OVERLAYS:
                if one.voter == voter and self._overlay_shown.get(one.key, False):
                    return str(one.label)
            return str(voter)

        def _voter_colour(self, voter: str) -> QColor:
            """The colour of the switched-on overlay drawing ``voter``.

            A voter no ``CHART_OVERLAYS`` entry draws reads ``TEXT_DIM``.
            """
            for one in CHART_OVERLAYS:
                if one.voter == voter and self._overlay_shown.get(one.key, False):
                    return self.overlay_colour(one)
            return self.TEXT_DIM

        def _compute_indicators(self):
            """Fill every ``_<key>_data`` series from the engine classes' own
            ``bands`` and ``lines``, one entry per candle.

            A ``None`` entry marks a candle with no value, and every draw
            method skips it.
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
            self._slingshot_data = SlingshotIndicator().lines(candles)
            di_plus, di_minus, adx = ADXIndicator().lines(candles)
            self._adx_data = [
                None if (p is None or m is None) else (p, m, a)
                for p, m, a in zip(di_plus, di_minus, adx)
            ]
            st_line, st_side, st_atr = SupertrendIndicator().lines(candles)
            self._supertrend_data = [
                None if (ln is None or bull is None) else (ln, bull, a)
                for ln, bull, a in zip(st_line, st_side, st_atr)
            ]
            self._zscore_data = ZScoreIndicator().lines(candles)
            self._ker_data = KaufmanERIndicator().lines(candles)
            self._rsi_data = RSIIndicator().lines(candles)

        def _fmt_ratio(self, value) -> str:
            """A sub-pane value as ``_sub_axis_label`` prints it."""
            return f"{value:.4f}" if abs(value) < 10 else f"{value:.2f}"

        def _legend_text(self, key: str) -> Optional[str]:
            """The last candle's reading of ``key``'s series as one legend value.

            ``None`` where the series holds no value on the last candle.
            """
            if not self._candles:
                return None
            fp = self._fmt_price
            fr = self._fmt_ratio
            if key == "bb" or key == "bbullseye":
                band = self._bb_data[-1] if self._bb_data else None
                if band is None:
                    return None
                if key == "bb":
                    return f"{fp(band[0])} / {fp(band[1])} / {fp(band[2])}"
                return f"u {fp(band[0])} l {fp(band[2])} ±0.5% ±0.2%"
            if key == "vortex":
                pair = self._vortex_data[-1] if self._vortex_data else None
                return None if pair is None else f"VI+ {fr(pair[0])} VI- {fr(pair[1])}"
            if key == "macd":
                three = self._macd_data[-1] if self._macd_data else None
                if three is None:
                    return None
                return f"{fr(three[0])} sig {fr(three[1])} hist {fr(three[2])}"
            if key == "stochrsi":
                value = self._stochrsi_data[-1] if self._stochrsi_data else None
                return None if value is None else fr(value)
            if key == "ichimoku":
                five = self._ichimoku_data[-1] if self._ichimoku_data else None
                if five is None or five[0] is None or five[1] is None:
                    return None
                return f"T {fp(five[0])} K {fp(five[1])}"
            if key == "volume":
                return self._fmt_volume(self._candles[-1].volume)
            if key == "slingshot":
                bar = self._slingshot_data[-1] if self._slingshot_data else None
                if bar is None:
                    return None
                parts = ["sqz on" if bar.sqz_on else "sqz off"]
                if bar.released:
                    parts.append("release " + ("+" if bar.momentum > 0 else "-"))
                if bar.snapback:
                    parts.append("snapback " + ("+" if "bull" in bar.snapback else "-"))
                return " ".join(parts)
            if key == "adx":
                three = self._adx_data[-1] if self._adx_data else None
                if three is None:
                    return None
                adx = LEGEND_NO_VALUE_TEXT if three[2] is None else f"{three[2]:.2f}"
                return f"{adx} +DI {three[0]:.2f} -DI {three[1]:.2f}"
            if key == "supertrend":
                three = self._supertrend_data[-1] if self._supertrend_data else None
                if three is None:
                    return None
                return f"{fp(three[0])} {'bull' if three[1] else 'bear'}"
            if key == "zscore" or key == "zscore_point":
                bar = self._zscore_data[-1] if self._zscore_data else None
                if bar is None:
                    return None
                if key == "zscore":
                    return f"{bar.z:+.2f}"
                return f"R {fp(bar.resistance_price)} S {fp(bar.support_price)}"
            if key == "ker":
                value = self._ker_data[-1] if self._ker_data else None
                return None if value is None else fr(value)
            if key == "rsi":
                value = self._rsi_data[-1] if self._rsi_data else None
                return None if value is None else f"{value:.2f}"
            return None

        @staticmethod
        def _fmt_volume(volume: float) -> str:
            """A volume as the strip's ``Vol`` label prints it."""
            if volume >= 1e9:
                return f"{volume / 1e9:.1f}B"
            if volume >= 1e6:
                return f"{volume / 1e6:.1f}M"
            if volume >= 1e3:
                return f"{volume / 1e3:.1f}K"
            return f"{volume:.0f}"

        def legend_entries(self) -> list:
            """One entry per ``CHART_OVERLAYS`` key, in registry order.

            Each carries ``key``, ``label``, ``text`` (the last candle's
            value, ``LEGEND_OFF_TEXT`` when switched off,
            ``LEGEND_NO_VALUE_TEXT`` when the series holds none),
            ``colour`` as a hex name, ``on`` and ``has_value``.
            """
            found = []
            for overlay in CHART_OVERLAYS:
                on = bool(self._overlay_shown.get(overlay.key, False))
                value = self._legend_text(overlay.key)
                if not on:
                    text = LEGEND_OFF_TEXT
                elif value is None:
                    text = LEGEND_NO_VALUE_TEXT
                else:
                    text = value
                found.append(
                    {
                        "key": overlay.key,
                        "label": overlay.label,
                        "text": text,
                        "colour": self.overlay_colour(overlay).name(),
                        "on": on,
                        "has_value": value is not None,
                    }
                )
            return found

        def draws_value_field(self) -> bool:
            """True when the chart carries a call, which makes it the ATA-SMP picture.

            Every venue PNG and the tab's ATA-SMP list call ``set_call`` with a
            direction; the Live list never does, so the tab draws no field.
            """
            return CALL_DIRECTION_ROLES.get(self._call_direction) is not None

        def _draw_legend(
            self, p: QPainter, left: int, price_bot: float, room: float, font_sm: QFont
        ) -> dict | None:
            """Draw the value field at the lower-left corner of the price pane.

            One ``LEGEND_ROW_H`` line per overlay that is on, its label in the
            overlay's colour and its value in ``TEXT_LIGHT``, on ``FIELD_SURFACE``
            inside a one-pixel ``GRID_MAJOR`` border, ``FIELD_PAD_PX`` in from
            ``left`` and ``price_bot``. ``room`` is the pane's height; lines past
            it are not drawn. Answers the rect drawn, None for no line.
            """
            entries = [one for one in self.legend_entries() if one["on"]]
            metrics = QFontMetrics(font_sm)
            fit = int((room - FIELD_PAD_PX * 4) // LEGEND_ROW_H)
            entries = entries[: max(0, fit)]
            if not entries:
                return None
            widths = [
                metrics.horizontalAdvance(one["label"])
                + FIELD_LABEL_GAP_PX
                + metrics.horizontalAdvance(one["text"])
                for one in entries
            ]
            field_w = max(widths) + FIELD_PAD_PX * 2
            field_h = len(entries) * LEGEND_ROW_H + FIELD_PAD_PX * 2
            field = QRectF(
                left + FIELD_PAD_PX,
                price_bot - FIELD_PAD_PX - field_h,
                field_w,
                field_h,
            )
            p.setBrush(QBrush(self.FIELD_SURFACE))
            p.setPen(
                QPen(self.GRID_MAJOR, device_pen_width(1.0, self._device_ratio(p)))
            )
            p.drawRect(field)
            p.setFont(font_sm)
            baseline = field.top() + FIELD_PAD_PX + LEGEND_ROW_H - 3
            x = field.left() + FIELD_PAD_PX
            for entry in entries:
                p.setPen(QPen(QColor(entry["colour"])))
                p.drawText(int(x), int(baseline), entry["label"])
                p.setPen(QPen(self.TEXT_LIGHT))
                p.drawText(
                    int(
                        x
                        + metrics.horizontalAdvance(entry["label"])
                        + FIELD_LABEL_GAP_PX
                    ),
                    int(baseline),
                    entry["text"],
                )
                baseline += LEGEND_ROW_H
            return {
                "left": float(field.left()),
                "top": float(field.top()),
                "width": float(field.width()),
                "height": float(field.height()),
                "lines": len(entries),
            }

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

        def set_positions(self, positions: list[PositionMarker]) -> None:
            self._positions = positions
            self._repaint()

        def set_landing_strip(self, strip: Optional[dict]) -> None:
            """Set ``_landing_strip`` from the bot's ``BBProximityResult`` reading, or clear it.

            The dict carries ``side``, ``candles``, ``upper``, ``lower``,
            ``tolerance_pct`` and the bot's ``timeframe``; ``_draw_landing_strip``
            paints the band between the side's band and its tolerance edge.
            """
            self._landing_strip = None if strip is None else dict(strip)
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

        def set_overlay(self, key: str, on: bool) -> bool:
            """Switch one ``CHART_OVERLAYS`` key on or off and write ``TOGGLED_PIN``.

            False for a key not in the registry, which writes no pin.
            """
            if key not in self._overlay_shown:
                return False
            self._overlay_shown[key] = bool(on)
            _pin_emit(
                TOGGLED_PIN,
                actual=self._overlay_shown[key],
                expected=bool(on),
                context={"key": key, "on": bool(on), "variant": resolve_variant()},
            )
            self._repaint()
            return True

        def overlays_shown(self) -> dict:
            """A copy of ``_overlay_shown``: every overlay key and whether it draws."""
            return dict(self._overlay_shown)

        def set_timeframe(self, tf: str) -> None:
            self._current_tf = tf

        def _sub_pane_height(self) -> int:
            """The height every sub-pane draws at: what a grip drag set, else
            ``SUB_PANE_READABLE_PX``."""
            return int(self._sub_pane_px or SUB_PANE_READABLE_PX)

        def set_pane_drag_height(
            self, dragged_height_px: int, width: int = NO_CAPTION_WIDTH
        ) -> int:
            """Take the widget height a grip drag asks for and write the
            sub-pane height ``sub_pane_height`` works out against
            ``_readable_height_for_panes`` at ``width``."""
            self._sub_pane_px = sub_pane_height(
                int(dragged_height_px), self._readable_height_for_panes(width)
            )
            return self._sub_pane_px

        def _readable_height_for_panes(self, width: int = NO_CAPTION_WIDTH) -> int:
            """The pixel height the toggled-on panes need with every sub-pane at
            ``SUB_PANE_READABLE_PX``, which no grip drag moves."""
            return self._height_for_panes(width, SUB_PANE_READABLE_PX)

        def _natural_height_for_panes(self, width: int = NO_CAPTION_WIDTH) -> int:
            """Return the pixel height the toggled-on panes need.

            The price pane takes ``PRICE_PANE_LAYOUT_FLOOR_PX``, the volume
            strip adds 28, each entry of ``_sub_overlays_with_data`` adds
            ``_sub_pane_height``, ``_call_strip_h`` adds the voter rows and
            ``_caption_strip_h`` adds the caption wrapped at ``width``, over a
            64px header. The value field draws inside the price pane and adds
            nothing.
            """
            return self._height_for_panes(width, self._sub_pane_height())

        def _minimum_height_for_panes(self, width: int = NO_CAPTION_WIDTH) -> int:
            """The least pixel height the toggled-on panes draw in: each
            sub-pane at ``SUB_PANE_FOLD_PX``, the rest as ``_natural_height_for_panes``.
            """
            return self._height_for_panes(width, SUB_PANE_FOLD_PX)

        def _folded_height_for_panes(self, width: int = NO_CAPTION_WIDTH) -> int:
            """``_minimum_height_for_panes`` with the reading strip folded to voter names."""
            return self._height_for_panes(width, SUB_PANE_FOLD_PX, folded=True)

        def _least_height_for_panes(self, width: int = NO_CAPTION_WIDTH) -> int:
            """The height under which ``paint_to`` overflows: ``_folded_height_for_panes``
            with the price pane at ``PRICE_PANE_PAINT_FLOOR_PX``.
            """
            return self._height_for_panes(
                width, SUB_PANE_FOLD_PX, PRICE_PANE_PAINT_FLOOR_PX, folded=True
            )

        def _height_for_panes(
            self,
            width: int,
            sub_pane_h: int,
            price_h: int = PRICE_PANE_LAYOUT_FLOOR_PX,
            folded: bool = False,
        ) -> int:
            """The pixel height of every pane with each sub-pane at ``sub_pane_h``,
            the price pane at ``price_h`` and the reading strip ``folded`` or not.
            """
            base = 28 + 18 + int(price_h) + 18  # header + OHLC + price + time
            if self._overlay_shown["volume"]:
                base += 28
            base += len(self._sub_overlays_with_data()) * int(sub_pane_h)
            return (
                base + self._call_strip_h(width, folded) + self._caption_strip_h(width)
            )

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
            """``effective_visible_start`` of the painter's window."""
            return effective_visible_start(self._visible_start, len(self._candles))

        def _effective_visible_count(self) -> int:
            """``effective_visible_count`` of the painter's window."""
            return effective_visible_count(self._visible_count, len(self._candles))

        def _fmt_price(self, price: float) -> str:
            return fmt_price(price)

        # -- the pointer, one arithmetic for both variants ---------------

        def pointer_pressed(self, x: int) -> None:
            """Start a drag pan at ``x``, holding the window it starts from."""
            self._drag_active = True
            self._drag_start_x = int(x)
            self._drag_start_visible_start = (
                self._visible_start if self._visible_start is not None else 0
            )

        def pointer_released(self) -> None:
            """End a drag pan."""
            self._drag_active = False
            self._drag_start_x = None

        def pan_to(self, x: int, width_px: int) -> bool:
            """Slide the window by the drag from ``_drag_start_x`` to ``x`` through
            ``pan_start``; True when ``_visible_start`` moved."""
            if not self._drag_active or self._drag_start_x is None:
                return False
            start = pan_start(
                self._drag_start_x,
                int(x),
                self._drag_start_visible_start,
                int(width_px),
                len(self._candles),
                self._effective_visible_count(),
            )
            if start is None or start == self._visible_start:
                return False
            self._visible_start = start
            self._emit_view(VIEW_CAUSE_PAN, start, self._visible_count)
            return True

        def pointer_moved(self, x: int, y: int, width_px: int) -> bool:
            """Place the crosshair at ``x``, ``y``, pan through ``pan_to`` while a drag
            is active, and repaint; True when the window moved."""
            self._mouse_x = int(x)
            self._mouse_y = int(y)
            moved = self.pan_to(x, width_px)
            self._repaint()
            return moved

        def wheel_turned(
            self, x: int, wheel_delta: float, width_px: int, control_held: bool = False
        ) -> bool:
            """Zoom the window about ``x`` through ``zoom_window``, or the price padding
            through ``clamp_y_zoom`` when control is held; True when something moved."""
            if not self._candles:
                return False
            if control_held:
                self._y_zoom_pct = clamp_y_zoom(
                    self._y_zoom_pct * zoom_factor(wheel_delta)
                )
                self._emit_view(
                    VIEW_CAUSE_Y_ZOOM, self._visible_start, self._visible_count
                )
                self._repaint()
                return True
            window = zoom_window(
                wheel_delta,
                int(x),
                int(width_px),
                len(self._candles),
                self._visible_start,
                self._visible_count,
            )
            if window is None:
                return False
            self._visible_start = window["start"]
            self._visible_count = window["count"]
            self._emit_view(VIEW_CAUSE_ZOOM, window["start"], window["count"])
            self._repaint()
            return True

        def view_reset(self) -> None:
            """Fit every candle again and repaint."""
            self._visible_start = None
            self._visible_count = None
            self._y_zoom_pct = Y_ZOOM_DEFAULT
            self._emit_view(VIEW_CAUSE_RESET, None, None)
            self._repaint()

        def pointer_left(self) -> None:
            """Take the crosshair off and repaint."""
            self._mouse_x = None
            self._mouse_y = None
            self._repaint()

        def crosshair_readout(self) -> list:
            """The label and text rows the last ``paint_to`` drew in the readout; empty
            when no candle was under the pointer."""
            return [list(row[:2]) for row in self._readout]

        def _emit_view(
            self, cause: str, start: Optional[int], count: Optional[int]
        ) -> None:
            """Write ``VIEW_PIN``: ``actual`` the window held, ``expected`` the window asked."""
            _pin_emit(
                VIEW_PIN,
                actual=[self._visible_start, self._visible_count],
                expected=[start, count],
                context={
                    "cause": cause,
                    "variant": resolve_variant(),
                    "symbol": self._symbol,
                    "candles": len(self._candles),
                    "y_zoom_pct": self._y_zoom_pct,
                },
            )

        def _emit_crosshair(
            self, x: int, width_px: int, named: Optional[int], source: str
        ) -> None:
            """Write ``CROSSHAIR_PIN`` at most once per ``CROSSHAIR_PIN_EVERY_S``: ``actual``
            the candle ``candle_at_x`` places under ``x``, ``expected`` the candle
            ``source`` named."""
            under = candle_at_x(int(x), int(width_px), self._effective_visible_count())
            placed = None if under is None else self._effective_visible_start() + under
            _pin_emit(
                CROSSHAIR_PIN,
                actual=placed,
                expected=named,
                context={
                    "source": source,
                    "variant": resolve_variant(),
                    "symbol": self._symbol,
                    "x": int(x),
                    "width": int(width_px),
                },
                every=CROSSHAIR_PIN_EVERY_S,
                instance=str(id(self)),
            )

        def crosshair_named(self, x: int, width_px: int, named: Optional[int]) -> None:
            """Write ``CROSSHAIR_PIN`` for a crosshair the page drew at ``x`` over candle ``named``."""
            self._emit_crosshair(x, width_px, named, CROSSHAIR_SOURCE_PAGE)

        def geometry_payload(self) -> dict:
            """What the last ``paint_to`` laid out, for a page drawing its own
            crosshair: the pane rect, the price scale, the candle column, the
            window, each visible candle's time label and ``readout_lines`` with
            the theme's colours, and the price bands."""
            held = dict(self._geometry)
            if not held:
                return held
            start = int(held["visible_start"])
            count = int(held["visible_count"])
            held["candles"] = [
                {
                    "time_label": gmt_label(one.time, CROSSHAIR_TIME_FORMAT),
                    "lines": [
                        [label, text, css_colour(getattr(self, role))]
                        for label, text, role in readout_lines(
                            one, self._fills_on_candle.get(start + at, ())
                        )
                    ],
                }
                for at, one in enumerate(self._candles[start : start + count], start)
            ]
            held["price_bands"] = [list(band) for band in PRICE_FORMAT_BANDS]
            held["grouped_decimals"] = FMT_GROUPED_DECIMALS
            held["crosshair_colour"] = css_colour(self.CROSSHAIR_COLOR)
            held["badge_fill"] = css_colour(self.BADGE_SURFACE)
            held["badge_edge"] = css_colour(self.BADGE_EDGE)
            held["text_light"] = css_colour(self.TEXT_LIGHT)
            held["text_dim"] = css_colour(self.TEXT_DIM)
            held["font_family"] = ds.FONT_FAMILY_MONO
            held["font_px"] = CAPTION_FONT_PX
            held["pin_every_ms"] = int(CROSSHAIR_PIN_EVERY_S * 1000)
            return held

        def paint_to(self, p: QPainter, w: int, h: int) -> None:
            """Draw the whole chart onto ``p`` over a ``w`` by ``h`` area.

            The painter's device is the caller's: a widget from ``paintEvent``
            and a ``QImage`` from ``render_chart_png``.
            """
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setRenderHint(QPainter.TextAntialiasing, True)
            ratio = self._device_ratio(p)
            px = 1.0 / ratio

            def snap(value: float) -> float:
                """``value`` moved to the centre of the device pixel it falls in."""
                return (int(value * ratio) + 0.5) / ratio

            def edge(value: float) -> float:
                """``value`` moved to the edge of the device pixel it falls in."""
                return int(value * ratio) / ratio

            def pen_w(width: float) -> float:
                """``width`` logical pixels as whole device pixels, through ``device_pen_width``."""
                return device_pen_width(width, ratio)

            bg_grad = QLinearGradient(0, 0, 0, h)
            bg_grad.setColorAt(0, self.BG_TOP)
            bg_grad.setColorAt(1, self.BG_BOT)
            p.fillRect(0, 0, w, h, bg_grad)

            font_sm = caption_font()
            font_hdr = header_font()
            font_ohlc = ohlc_font()
            fm = QFontMetrics(font_sm)

            self._fills_before_window = 0
            self._fills_after_window = 0
            self._fills_off_price = 0

            if not self._candles:
                p.setPen(QPen(self.TEXT_DIM))
                p.setFont(design_font(ds.FONT_FAMILY_UI, ds.TYPE_BODY))
                msg = self._error_text or self._status_text
                p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, msg)
                self._draw_header(p, w, font_hdr, font_sm)
                return

            ML = CHART_LEFT_MARGIN_PX
            MR = CHART_RIGHT_MARGIN_PX
            MT = 28  # header
            OHLC_H = 18  # OHLC info row at top of price pane
            # The strip folds to voter names when h cannot hold one row per
            # reading with the sub-panes at SUB_PANE_FOLD_PX.
            strip_folded = bool(
                self._call_readings
            ) and h < self._minimum_height_for_panes(w)
            # time axis, then the voter strip, then the caption
            MB = 18 + self._call_strip_h(w, strip_folded) + self._caption_strip_h(w)

            sub_overlays = self._sub_overlays_with_data()
            show_volume = self._overlay_shown["volume"]

            VOL_H = 28 if show_volume else 0
            # Every sub-pane takes _sub_pane_height, which a grip drag raises.
            # Only a fixed-height image whose h cannot hold them shrinks each
            # toward SUB_PANE_FOLD_PX.
            fixed_h = MT + OHLC_H + MB + VOL_H
            SUB_H = self._sub_pane_height()
            if (
                sub_overlays
                and h - fixed_h - SUB_H * len(sub_overlays) < PRICE_PANE_LAYOUT_FLOOR_PX
            ):
                SUB_H = max(
                    SUB_PANE_FOLD_PX,
                    (h - fixed_h - PRICE_PANE_LAYOUT_FLOOR_PX) // len(sub_overlays),
                )
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

            available = h - fixed_h - total_sub_h
            price_h = max(PRICE_PANE_PAINT_FLOOR_PX, available)

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

            # The grid is one device pixel, aliased and snapped, so it stays a hairline at every ratio.
            p.setRenderHint(QPainter.Antialiasing, False)
            grid_step = _nice_step(pr, target_ticks=6)
            if grid_step > 0:
                import math as _m

                g0 = _m.ceil(lo / grid_step) * grid_step
                g = g0
                while g <= hi + grid_step * GRID_TICK_TOLERANCE:
                    y = p2y(g)
                    if price_top <= y <= price_bot:
                        is_major = round((g - g0) / grid_step) % 2 == 0
                        gc = self.GRID_MAJOR if is_major else self.GRID_MINOR
                        p.setPen(QPen(gc, px, Qt.DotLine))
                        p.drawLine(QPointF(ML, snap(y)), QPointF(w - MR, snap(y)))
                        p.setPen(QPen(self.TEXT_LIGHT))
                        p.setFont(font_sm)
                        p.drawText(w - MR + 6, int(y) + 4, self._fmt_price(g))
                    g += grid_step

            # About 6 ticks; each line spans every pane above the label band.
            if n >= 2:
                import time as _t

                tick_stride = max(1, n // 6)
                span_sec = max(1, visible_candles[-1].time - visible_candles[0].time)
                use_date = span_sec > 24 * 3600
                for ti in range(0, n, tick_stride):
                    c = visible_candles[ti]
                    tx = i2x(ti) + cw / 2
                    if tx < ML or tx > w - MR:
                        continue
                    p.setPen(QPen(self.GRID_MINOR, px, Qt.DotLine))
                    p.drawLine(
                        QPointF(snap(tx), price_top), QPointF(snap(tx), time_axis_y)
                    )
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
                        p.drawText(int(tx) - 16, time_axis_y + 12, label)

            # One hairline separates the price pane from the strip under it.
            p.setPen(QPen(self.GRID_MAJOR, px))
            p.drawLine(QPointF(ML, snap(price_bot)), QPointF(w - MR, snap(price_bot)))
            p.setRenderHint(QPainter.Antialiasing, True)

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

            # The wick follows the candle spacing, in whole device pixels, never under one.
            wick_w = pen_w(cw * WICK_FRACTION)
            vol_bars = []
            for i, (ha_o, ha_h, ha_l, ha_c, _vol) in enumerate(ha_candles):
                x = i2x(i)
                is_up = ha_c >= ha_o

                fill = self.UP_FILL if is_up else self.DOWN_FILL
                border = self.UP_BORDER if is_up else self.DOWN_BORDER
                wick_c = self.UP_WICK if is_up else self.DOWN_WICK

                wx = snap(x + cw / 2)
                y_hi = p2y(ha_h)
                y_lo = p2y(ha_l)
                p.setPen(QPen(wick_c, wick_w, Qt.SolidLine, Qt.FlatCap))
                p.drawLine(QPointF(wx, y_hi), QPointF(wx, y_lo))

                y_open = p2y(ha_o)
                y_close = p2y(ha_c)
                bt = min(y_open, y_close)
                bh = max(abs(y_open - y_close), px)
                body = QRectF(snap(x + gap / 2), snap(bt), bw, bh)

                p.setBrush(QBrush(fill))
                p.setPen(QPen(border, px))
                p.drawRect(body)

                if show_volume and VOL_H > 0:
                    cvol = _vol
                    vh = (cvol / max_vol) * VOL_H if cvol > 0 else 0
                    if vh > 0:
                        vol_bars.append((x, vol_bot - vh, is_up))

            # Every bar sits on whole device pixels, aliased: its left edge, its
            # width and both ends snapped, one device pixel of border.
            p.setRenderHint(QPainter.Antialiasing, False)
            for x, vol_y, is_up in vol_bars:
                left = edge(x + gap / 2)
                top = edge(vol_y)
                vol_rect = QRectF(
                    left, top, max(px, edge(bw)), max(px, edge(vol_bot) - top)
                )
                vf = self.VOL_UP if is_up else self.VOL_DOWN
                vb = self.VOL_UP_BORDER if is_up else self.VOL_DOWN_BORDER
                p.setBrush(QBrush(vf))
                p.setPen(QPen(vb, px))
                p.drawRect(vol_rect)
            p.setRenderHint(QPainter.Antialiasing, True)

            for overlay in overlays_on(self, VOLUME_PANE):
                getattr(self, overlay.draw)(p, ML, w - MR, vol_top)

            # The price line reads the latest candle, not the last visible one.
            _fa = self._fire_armed_state or {}
            drawn_counts = {
                "fills": 0,
                "target": 0,
                "strip": 0,
                "glow": 0,
                "positions": sum(
                    1
                    for pos in self._positions
                    if price_top <= p2y(pos.price) <= price_top + price_h
                ),
            }
            if self._candles:
                last_close = self._candles[-1].close
                yp = p2y(last_close)
                p.setPen(QPen(self.PRICE_LINE_COLOR, px, Qt.DashLine))
                p.drawLine(QPointF(ML, snap(yp)), QPointF(w - MR, snap(yp)))
                self._right_tag(
                    p,
                    w,
                    yp,
                    self._fmt_price(last_close),
                    self.PRICE_LINE_COLOR,
                    font_sm,
                )

            if n > 0:

                def _draw_line_series(data, color, width=LINE_WIDTH_PX, dashed=False):
                    pen = QPen(color, pen_w(width))
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
                    pen_w=pen_w,
                    snap=snap,
                    px=px,
                    strip_folded=strip_folded,
                )
                for overlay in overlays_on(self, PRICE_PANE):
                    getattr(self, overlay.draw)(ctx)

                drawn_counts["strip"] = self._draw_landing_strip(ctx, snap)

                # Both Target Balance lines are dashed, tagged at the right edge in their colour.
                for tb_price, tb_colour, tb_format in (
                    (self._tb_anchor_price, self.TB_ANCHOR, TARGET_TAG_FORMAT),
                    (self._tb_ceiling_price, self.TB_CEILING, CEILING_TAG_FORMAT),
                ):
                    if tb_price is None:
                        continue
                    ty = p2y(float(tb_price))
                    if not price_top <= ty <= price_bot:
                        continue
                    p.setPen(QPen(tb_colour, pen_w(LINE_WIDTH_PX), Qt.DashLine))
                    p.drawLine(QPointF(ML, snap(ty)), QPointF(w - MR, snap(ty)))
                    self._right_tag(
                        p,
                        w,
                        ty,
                        tb_format.format(price=self._fmt_price(float(tb_price))),
                        tb_colour,
                        font_sm,
                    )
                    drawn_counts["target"] += 1

                # Right-edge glow: green when SCRUM is armed, red when FOLD is, each tagged.
                glow_x = w - MR - 4
                glow_w = 6
                for armed, glow_colour, glow_top, glow_bot, glow_tag in (
                    (
                        bool(_fa.get("scrum_armed")),
                        self.GLOW_SCRUM,
                        price_top + 4,
                        price_top + price_h * 0.5,
                        SCRUM_ARMED_TAG,
                    ),
                    (
                        bool(_fa.get("fold_armed")),
                        self.GLOW_FOLD,
                        price_top + price_h * 0.5,
                        price_bot - 4,
                        FOLD_ARMED_TAG,
                    ),
                ):
                    if not armed:
                        continue
                    grad = QLinearGradient(glow_x, glow_top, glow_x + glow_w, glow_top)
                    grad.setColorAt(0.0, _with_alpha(glow_colour, 0))
                    grad.setColorAt(1.0, glow_colour)
                    p.setBrush(QBrush(grad))
                    p.setPen(Qt.NoPen)
                    p.drawRect(QRectF(glow_x, glow_top, glow_w, glow_bot - glow_top))
                    tag_y = (
                        glow_top + TAG_H_PX
                        if glow_tag == SCRUM_ARMED_TAG
                        else glow_bot - TAG_H_PX
                    )
                    self._right_tag(p, w, tag_y, glow_tag, glow_colour, font_sm)
                    drawn_counts["glow"] += 1

                def _paint_sub_grid(top: float, bot: float, label: str) -> float:
                    """Paint the sub-pane's wash, its hairline separator and its name in
                    the label row; answer the plot's top, ``SUB_PANE_LABEL_PX`` under ``top``.
                    """
                    p.setPen(Qt.NoPen)
                    p.setBrush(QBrush(self.SUB_PANE_WASH))
                    p.drawRect(QRectF(ML, top, w - ML - MR, bot - top))
                    p.setRenderHint(QPainter.Antialiasing, False)
                    p.setPen(QPen(self.GRID_MAJOR, px))
                    p.drawLine(QPointF(ML, snap(top)), QPointF(w - MR, snap(top)))
                    p.setRenderHint(QPainter.Antialiasing, True)
                    p.setPen(QPen(self.TEXT_DIM))
                    p.setFont(font_sm)
                    p.drawText(int(ML + 6), int(top + 11), label)
                    return min(top + SUB_PANE_LABEL_PX, bot)

                def _rule_line(y: float, colour=None, dashed: bool = True) -> None:
                    """One ruled level across the pane at ``y``: one device pixel, aliased, snapped."""
                    pen = QPen(colour if colour is not None else self.GRID_MINOR, px)
                    if dashed:
                        pen.setStyle(Qt.DashLine)
                    p.setRenderHint(QPainter.Antialiasing, False)
                    p.setPen(pen)
                    p.drawLine(QPointF(ML, snap(y)), QPointF(w - MR, snap(y)))
                    p.setRenderHint(QPainter.Antialiasing, True)

                def _sub_axis_label(top: float, bot: float, value, color):
                    """Right-edge value tag of a sub-pane at the plot's middle, in the series colour."""
                    if value is None:
                        return
                    txt = f"{value:.4f}" if abs(value) < 10 else f"{value:.2f}"
                    self._right_tag(p, w, (top + bot) / 2, txt, color, font_sm)

                def _paint_oscillator(
                    top, bot, data, extract, color, width=1.2, vmin=None, vmax=None
                ):
                    """Draw one oscillator line between ``top`` and ``bot`` at ``width``
                    logical pixels rounded to whole device pixels.

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
                    pen = QPen(color, pen_w(width))
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
                ctx.rule_line = _rule_line
                ctx.sub_axis_label = _sub_axis_label
                ctx.paint_oscillator = _paint_oscillator
                for overlay, sp_top, sp_bot in sub_layout:
                    getattr(self, overlay.draw)(ctx, sp_top, sp_bot)

                self._draw_call(ctx, h)

            field_drawn = (
                self._draw_legend(p, ML, price_bot, price_h, font_sm)
                if self.draws_value_field()
                else None
            )
            self._draw_caption_strip(p, w, h, font_sm)

            type_colors = {
                "SCRUM": self.MARKER_SCRUM,
                "FOLD": self.MARKER_FOLD,
                "DIST": self.MARKER_DIST,
            }
            default_buy = self.MARKER_BUY
            default_sell = self.MARKER_SELL

            # A fill sits on the candle whose interval holds its stamp; the window
            # ends one interval past the last candle's open.
            interval = self._candle_interval(visible_candles)
            t_first = visible_candles[0].time
            t_end = visible_candles[-1].time + interval
            times = [c.time for c in visible_candles]
            mark_w = cw * MARK_WIDTH_RATIO
            mark_h = price_h * MARK_HEIGHT_FRACTION
            fills_in_window = 0
            fill_tags: list = []
            placed: list = []
            self._fills_on_candle.clear()
            # Every glyph draws first; a tag is placed against the glyphs and
            # the tags already drawn, and is left out where it would cross one.
            for m in self._markers:
                if m.time < t_first:
                    self._fills_before_window += 1
                    continue
                if m.time >= t_end:
                    self._fills_after_window += 1
                    continue
                idx = max(0, bisect_right(times, m.time) - 1)
                self._fills_on_candle.setdefault(v_start + idx, []).append(m)
                my = p2y(m.price)
                if not price_top <= my <= price_bot:
                    self._fills_off_price += 1
                    continue
                fills_in_window += 1
                mx = i2x(idx) + cw / 2
                is_buy = m.side == "buy"
                glyph = MARK_GLYPHS[FOLD_SIDE if is_buy else SCRUM_SIDE]
                tc = type_colors.get(m.label, default_buy if is_buy else default_sell)
                polygon = QPolygonF(
                    [
                        QPointF(mx + dx * mark_w, my + dy * mark_h)
                        for dx, dy in glyph["points"]
                    ]
                )
                p.setPen(QPen(tc, pen_w(MARK_OUTLINE_PX)))
                p.setBrush(QBrush(tc) if glyph["filled"] else Qt.NoBrush)
                p.drawPolygon(polygon)
                drawn_counts["fills"] += 1
                placed.append((m, mx, my, tc))
            obstacles = [
                [mx - mark_w / 2, my - mark_h / 2, mark_w, mark_h]
                for _m, mx, my, _tc in placed
            ]
            p.setFont(font_sm)
            for m, mx, my, tc in placed:
                text = FILL_TAG_FORMAT.format(
                    label=fill_label(m), price=self._fmt_price(m.price)
                )
                tw = fm.horizontalAdvance(text) + TAG_PAD_PX * 2
                tag = self._tag_place(
                    mx + mark_w / 2 + TAG_PAD_PX,
                    mx - mark_w / 2 - TAG_PAD_PX - tw,
                    my - TAG_H_PX / 2,
                    tw,
                    obstacles,
                    w - MR,
                )
                if tag is None:
                    continue
                rect = [tag.x(), tag.y(), tag.width(), tag.height()]
                fill_tags.append(rect)
                obstacles.append(rect)
                p.setBrush(QBrush(self.FILL_TAG_SURFACE))
                p.setPen(QPen(tc, px))
                p.drawRoundedRect(tag, 2, 2)
                p.setPen(QPen(tc))
                p.drawText(tag, Qt.AlignCenter, text)

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

            self._geometry = {
                "width": int(w),
                "height": int(h),
                "left": ML,
                "right": w - MR,
                "price_top": float(price_top),
                "price_bot": float(price_bot),
                "price_h": float(price_h),
                "time_axis_y": float(time_axis_y),
                "low": float(lo),
                "span": float(pr),
                "column_px": float(cw),
                "visible_start": int(v_start),
                "visible_count": int(n),
                "candle_count": int(n_total),
                "y_zoom_pct": float(self._y_zoom_pct),
                "field": field_drawn,
                "sub_panes": [
                    {"key": overlay.key, "top": float(sp_top), "bot": float(sp_bot)}
                    for overlay, sp_top, sp_bot in sub_layout
                ],
                "fill_tags": [[float(v) for v in one] for one in fill_tags],
            }
            self._readout = []
            self._readout_candle = None
            if self._mouse_x is not None and self._mouse_y is not None:
                mx, my = self._mouse_x, self._mouse_y
                if ML <= mx <= w - MR and price_top <= my <= time_axis_y:
                    p.setRenderHint(QPainter.Antialiasing, False)
                    p.setPen(QPen(self.CROSSHAIR_COLOR, px, Qt.DotLine))
                    p.drawLine(
                        QPointF(snap(mx), price_top), QPointF(snap(mx), time_axis_y)
                    )
                    p.drawLine(QPointF(ML, snap(my)), QPointF(w - MR, snap(my)))
                    p.setRenderHint(QPainter.Antialiasing, True)

                    if price_top <= my <= price_bot:
                        cp = lo + pr * (1 - (my - price_top) / price_h)
                        cp_txt = self._fmt_price(cp)
                        cp_w = fm.horizontalAdvance(cp_txt) + 12
                        badge = QRectF(w - MR, my - 9, cp_w, 18)
                        p.setBrush(QBrush(self.BADGE_SURFACE))
                        p.setPen(QPen(self.CROSSHAIR_COLOR, pen_w(1.0)))
                        p.drawRoundedRect(badge, 3, 3)
                        p.setPen(QPen(self.TEXT_LIGHT))
                        p.setFont(font_sm)
                        p.drawText(badge, Qt.AlignCenter, cp_txt)

                    ci = int((mx - ML) / cw)
                    if 0 <= ci < n:
                        c = visible_candles[ci]
                        self._readout_candle = v_start + ci
                        self._emit_crosshair(
                            mx, w, v_start + ci, CROSSHAIR_SOURCE_PAINT
                        )
                        tstr = gmt_label(c.time, CROSSHAIR_TIME_FORMAT)
                        if tstr:
                            tw = fm.horizontalAdvance(tstr) + 12
                            t_badge = QRectF(mx - tw / 2, time_axis_y - 1, tw, 16)
                            p.setBrush(QBrush(self.BADGE_SURFACE))
                            p.setPen(QPen(self.CROSSHAIR_COLOR, pen_w(1.0)))
                            p.drawRoundedRect(t_badge, 3, 3)
                            p.setPen(QPen(self.TEXT_LIGHT))
                            p.drawText(t_badge, Qt.AlignCenter, tstr)

                        self._readout = readout_lines(
                            c, self._fills_on_candle.get(v_start + ci, ())
                        )
                        lines = [
                            (label, text, getattr(self, role))
                            for label, text, role in self._readout
                        ]
                        tip_color = lines[3][2]
                        line_h = 14
                        pad = 8
                        label_w = max(
                            fm.horizontalAdvance(lbl) for lbl, _v, _c in lines
                        )
                        value_x = 6 + label_w + 12
                        tip_w = 0
                        for lbl, val, _col in lines:
                            line_w = value_x + fm.horizontalAdvance(val)
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
                        p.setPen(QPen(self.BADGE_EDGE, pen_w(1.0)))
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
                            p.drawText(tx + pad + value_x, int(y_line), val)

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

            # Three low-contrast dashes marking the draggable bottom edge of a window.
            if self.DRAWS_GRIP:
                grip_y = h - self._resize_grip_h // 2
                p.setPen(QPen(self.GRIP, pen_w(1.2)))
                cx = w / 2
                for off in (-12, 0, 12):
                    p.drawLine(
                        int(cx + off - 4), int(grip_y), int(cx + off + 4), int(grip_y)
                    )

            self._emit_annotations(
                drawn_counts,
                {
                    "fills": fills_in_window,
                    "target": sum(
                        1
                        for tb in (self._tb_anchor_price, self._tb_ceiling_price)
                        if tb is not None and price_top <= p2y(float(tb)) <= price_bot
                    ),
                    "strip": int(self._strip_bounds() is not None),
                    "glow": int(bool(_fa.get("scrum_armed")))
                    + int(bool(_fa.get("fold_armed"))),
                    "positions": drawn_counts["positions"],
                },
                {
                    "fills_fed": len(self._markers),
                    "fills_off_window": self._fills_before_window
                    + self._fills_after_window,
                    "fills_older_than_window": self._fills_before_window,
                    "fills_newer_than_window": self._fills_after_window,
                    "fills_off_price_scale": self._fills_off_price,
                },
            )

        def _emit_annotations(self, drawn: dict, expected: dict, context: dict) -> None:
            """Write ``ANNOTATIONS_PIN`` when the drawn, expected or fed annotation counts changed since the last pass."""
            digest = (
                repr(sorted(drawn.items()))
                + repr(sorted(expected.items()))
                + repr(sorted(context.items()))
            )
            if digest == self._annotations_digest:
                return
            self._annotations_digest = digest
            _pin_emit(
                ANNOTATIONS_PIN,
                actual=dict(drawn),
                expected=dict(expected),
                context={
                    "symbol": self._symbol,
                    "variant": resolve_variant(),
                    "theme": self.theme_name(),
                    **context,
                },
            )

        @staticmethod
        def _device_ratio(p: QPainter) -> float:
            """The device pixel ratio of the surface ``p`` paints, 1.0 when it reports none."""
            device = p.device()
            try:
                ratio = float(device.devicePixelRatio()) if device is not None else 1.0
            except (AttributeError, TypeError):
                ratio = 1.0
            return ratio if ratio > 0 else 1.0

        @staticmethod
        def _candle_interval(candles: list) -> int:
            """The seconds between two candles, read as the median gap; ``DEFAULT_CANDLE_SECONDS`` with one candle."""
            gaps = sorted(
                int(candles[i].time - candles[i - 1].time)
                for i in range(1, len(candles))
                if candles[i].time > candles[i - 1].time
            )
            return gaps[len(gaps) // 2] if gaps else DEFAULT_CANDLE_SECONDS

        def _tag_clear(self, rect: QRectF, drawn: list, scale_x: float) -> bool:
            """Whether ``rect`` lies inside the pane left of ``scale_x`` and crosses
            none of the ``drawn`` glyph and tag rects (``[x, y, w, h]`` each)."""
            if rect.x() < 0 or rect.x() + rect.width() > scale_x:
                return False
            for x, y, width, height in drawn:
                if (
                    rect.x() < x + width
                    and x < rect.x() + rect.width()
                    and rect.y() < y + height
                    and y < rect.y() + rect.height()
                ):
                    return False
            return True

        def _tag_place(
            self,
            right_x: float,
            left_x: float,
            y: float,
            width: float,
            drawn: list,
            scale_x: float,
        ) -> Optional[QRectF]:
            """The rect a fill tag draws in: ``TAG_H_PX`` tall at ``right_x`` when
            ``_tag_clear``, else at ``left_x`` when clear, else None and no tag."""
            for x in (right_x, left_x):
                rect = QRectF(x, y, width, TAG_H_PX)
                if self._tag_clear(rect, drawn, scale_x):
                    return rect
            return None

        def _right_tag(
            self, p: QPainter, w: int, y: float, text: str, colour: QColor, font: QFont
        ) -> QRectF:
            """Draw ``text`` on a badge filled with ``colour`` at the right edge, centred on ``y``.

            The badge starts in the price scale and grows leftwards over the
            pane when the text is wider than the scale; the text is ``TAG_TEXT``.
            """
            metrics = QFontMetrics(font)
            width = metrics.horizontalAdvance(text) + TAG_PAD_PX * 2
            x = min(w - CHART_RIGHT_MARGIN_PX + TAG_INSET_PX, w - width - TAG_INSET_PX)
            rect = QRectF(x, y - TAG_H_PX / 2, width, TAG_H_PX)
            p.setBrush(QBrush(colour))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(rect, 2, 2)
            p.setPen(QPen(self.TAG_TEXT))
            p.setFont(font)
            p.drawText(rect, Qt.AlignCenter, text)
            return rect

        def _strip_bounds(self) -> Optional[tuple]:
            """The landing strip's two prices, ``(top, bottom)``, or None with no strip set.

            The band lies between the side's Bollinger band and its tolerance
            edge, ``(upper - lower) * tolerance_pct / 100`` inside it.
            """
            strip = self._landing_strip
            if not strip:
                return None
            upper = float(strip.get("upper", 0.0) or 0.0)
            lower = float(strip.get("lower", 0.0) or 0.0)
            if upper <= lower:
                return None
            tolerance = (
                (upper - lower) * float(strip.get("tolerance_pct", 0.0) or 0.0) / 100.0
            )
            side = str(strip.get("side", ""))
            if side == STRIP_UPPER:
                return (upper, upper - tolerance)
            if side == STRIP_LOWER:
                return (lower + tolerance, lower)
            return None

        def _draw_landing_strip(self, ctx, snap) -> int:
            """Paint the landing strip band over its candles and tag it; 1 when drawn, else 0."""
            bounds = self._strip_bounds()
            if bounds is None:
                return 0
            strip = self._landing_strip or {}
            top_price, bottom_price = bounds
            y_top = ctx.p2y(top_price)
            y_bot = ctx.p2y(bottom_price)
            if y_bot < ctx.price_top or y_top > ctx.price_bot:
                return 0
            y_top = max(y_top, ctx.price_top)
            y_bot = min(y_bot, ctx.price_bot)
            candles = int(strip.get("candles", 0) or 0)
            bot_seconds = TIMEFRAME_SECONDS.get(
                str(strip.get("timeframe", "")), DEFAULT_CANDLE_SECONDS
            )
            span = (candles + 1) * bot_seconds
            interval = self._candle_interval(ctx.visible_candles)
            columns = min(ctx.n, max(1, -(-span // interval)))
            x_left = ctx.i2x(ctx.n - columns)
            x_right = ctx.i2x(ctx.n)
            p = ctx.p
            p.setBrush(QBrush(self.STRIP_FILL))
            p.setPen(Qt.NoPen)
            p.drawRect(QRectF(x_left, y_top, x_right - x_left, y_bot - y_top))
            p.setPen(QPen(self.STRIP_EDGE, ctx.pen_w(LINE_WIDTH_PX), Qt.DashLine))
            p.drawLine(QPointF(x_left, snap(y_top)), QPointF(x_right, snap(y_top)))
            p.drawLine(QPointF(x_left, snap(y_bot)), QPointF(x_right, snap(y_bot)))
            self._right_tag(
                p,
                ctx.w,
                (y_top + y_bot) / 2,
                STRIP_TAG_FORMAT.format(
                    side=str(strip.get("side", "")), candles=candles
                ),
                self.STRIP_EDGE,
                ctx.font_sm,
            )
            return 1

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
                p.setPen(QPen(chikou_color, ctx.pen_w(1.0)))
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

        def _draw_slingshot(self, ctx) -> None:
            """Paint one mark per ``SlingshotBar`` release or snapback in view.

            A release is a diamond, signed by the bar's momentum; a snapback
            is a circle, signed by its side, on the first bar of a run of the
            same reading. A bullish mark sits under the candle's low and a
            bearish one over its high.
            """
            p = ctx.p
            cw = ctx.cw
            visible_candles = ctx.visible_candles
            i2x = ctx.i2x
            p2y = ctx.p2y
            visible = self._slingshot_data[ctx.v_start : ctx.v_end]
            for vis_i, bar in enumerate(visible):
                if bar is None or vis_i >= len(visible_candles):
                    continue
                full_i = ctx.v_start + vis_i
                earlier = self._slingshot_data[full_i - 1] if full_i > 0 else None
                marks = []
                if bar.released and bar.momentum != 0.0:
                    marks.append(("release", bar.momentum > 0.0))
                if bar.snapback and (
                    earlier is None or earlier.snapback != bar.snapback
                ):
                    marks.append(("snapback", "bull" in bar.snapback))
                if not marks:
                    continue
                x = i2x(vis_i) + cw / 2
                cdl = visible_candles[vis_i]
                for kind, bullish in marks:
                    if bullish:
                        color = self.EVENT_BULL
                        anchor_y = p2y(cdl.low) + 14
                    else:
                        color = self.EVENT_BEAR
                        anchor_y = p2y(cdl.high) - 14
                    p.setBrush(QBrush(color))
                    p.setPen(QPen(color.lighter(140), ctx.pen_w(1.4)))
                    if kind == "release":
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
                        p.drawEllipse(QPointF(x, anchor_y), 5.5, 5.5)

        def _draw_supertrend(self, ctx) -> None:
            """Paint the Supertrend line: ``ST_BULL`` under price while bullish,
            ``ST_BEAR`` over it while bearish, broken at every flip."""
            visible = self._supertrend_data[ctx.v_start : ctx.v_end]
            if not visible:
                return
            bull_line = [
                one[0] if (one is not None and one[1]) else None for one in visible
            ]
            bear_line = [
                one[0] if (one is not None and not one[1]) else None for one in visible
            ]
            ctx.draw_line_series(bull_line, self.ST_BULL, 1.4, False)
            ctx.draw_line_series(bear_line, self.ST_BEAR, 1.4, False)

        def _draw_zscore_point(self, ctx) -> None:
            """Paint the Z-Score algo point: ``resistance_price`` and
            ``support_price`` from each ``ZScoreBar``, dashed, in ``ZSCORE_ZONE``."""
            visible = self._zscore_data[ctx.v_start : ctx.v_end]
            if not visible:
                return
            resistance = [
                None if one is None else one.resistance_price for one in visible
            ]
            support = [None if one is None else one.support_price for one in visible]
            ctx.draw_line_series(resistance, self.ZSCORE_ZONE, 1.0, True)
            ctx.draw_line_series(support, self.ZSCORE_ZONE, 1.0, True)

        def _rule_bands(self, ctx, top: float, bot: float, bands, scale) -> None:
            """Rule one dashed ``GRID_MINOR`` line per value of ``bands`` on ``scale``
            through ``ctx.rule_line``, between the plot's ``top`` and ``bot``."""
            vmin, vmax = scale
            span = (vmax - vmin) or 1e-9
            for ref in bands:
                ctx.rule_line(bot - ((ref - vmin) / span) * (bot - top))

        def _draw_adx(self, ctx, top: float, bot: float) -> None:
            """Paint +DI, -DI and ADX on ``PERCENT_SCALE`` with ``ADX_BANDS`` ruled."""
            visible = self._adx_data[ctx.v_start : ctx.v_end]
            if not visible:
                return
            top = ctx.paint_sub_grid(top, bot, "ADX (14)")
            self._sub_scale["adx"] = PERCENT_SCALE
            self._rule_bands(ctx, top, bot, ADX_BANDS, PERCENT_SCALE)
            vmin, vmax = PERCENT_SCALE
            ctx.paint_oscillator(
                top,
                bot,
                visible,
                lambda t: t[0] if t else None,
                self.DI_PLUS,
                1.0,
                vmin=vmin,
                vmax=vmax,
            )
            ctx.paint_oscillator(
                top,
                bot,
                visible,
                lambda t: t[1] if t else None,
                self.DI_MINUS,
                1.0,
                vmin=vmin,
                vmax=vmax,
            )
            last_adx = ctx.paint_oscillator(
                top,
                bot,
                visible,
                lambda t: t[2] if t else None,
                self.ADX_LINE,
                1.4,
                vmin=vmin,
                vmax=vmax,
            )
            ctx.sub_axis_label(top, bot, last_adx, self.ADX_LINE)

        def _draw_zscore(self, ctx, top: float, bot: float) -> None:
            """Paint the smoothed z on a symmetric scale of at least
            ``ZSCORE_SCALE_FLOOR``, with ``ZSCORE_BANDS`` ruled."""
            visible = self._zscore_data[ctx.v_start : ctx.v_end]
            if not visible:
                return
            top = ctx.paint_sub_grid(top, bot, "Z-Score (50)")
            values = [abs(one.z) for one in visible if one is not None]
            half = max([ZSCORE_SCALE_FLOOR] + values)
            scale = (-half, half)
            self._sub_scale["zscore"] = scale
            self._rule_bands(ctx, top, bot, ZSCORE_BANDS, scale)
            last_z = ctx.paint_oscillator(
                top,
                bot,
                visible,
                lambda t: t.z if t else None,
                self.ZSCORE_LINE,
                1.4,
                vmin=-half,
                vmax=half,
            )
            ctx.sub_axis_label(top, bot, last_z, self.ZSCORE_LINE)

        def _draw_ker(self, ctx, top: float, bot: float) -> None:
            """Paint Kaufman's Efficiency Ratio on ``RATIO_SCALE``."""
            visible = self._ker_data[ctx.v_start : ctx.v_end]
            if not visible:
                return
            top = ctx.paint_sub_grid(top, bot, "KER (10)")
            self._sub_scale["ker"] = RATIO_SCALE
            vmin, vmax = RATIO_SCALE
            last_ratio = ctx.paint_oscillator(
                top, bot, visible, lambda v: v, self.KER_LINE, 1.4, vmin=vmin, vmax=vmax
            )
            ctx.sub_axis_label(top, bot, last_ratio, self.KER_LINE)

        def _draw_rsi(self, ctx, top: float, bot: float) -> None:
            """Paint Wilder's RSI on ``PERCENT_SCALE`` with ``RSI_BANDS`` ruled."""
            visible = self._rsi_data[ctx.v_start : ctx.v_end]
            if not visible:
                return
            top = ctx.paint_sub_grid(top, bot, "RSI (14)")
            self._sub_scale["rsi"] = PERCENT_SCALE
            self._rule_bands(ctx, top, bot, RSI_BANDS, PERCENT_SCALE)
            vmin, vmax = PERCENT_SCALE
            last_rsi = ctx.paint_oscillator(
                top, bot, visible, lambda v: v, self.RSI_LINE, 1.4, vmin=vmin, vmax=vmax
            )
            ctx.sub_axis_label(top, bot, last_rsi, self.RSI_LINE)

        def _draw_macd(self, ctx, top: float, bot: float) -> None:
            """Paint the MACD histogram, its line and its signal in one sub-pane."""
            p = ctx.p
            visible = self._macd_data[ctx.v_start : ctx.v_end]
            if not visible:
                return
            top = ctx.paint_sub_grid(top, bot, "MACD (12, 26, 9)")
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
                ctx.rule_line(bot - ((0 - v_lo) / span) * (bot - top))
            # Every histogram bar sits on whole device pixels, aliased, one device pixel of edge.
            px = ctx.px
            p.setRenderHint(QPainter.Antialiasing, False)
            for index, one in enumerate(visible):
                if one is None or one[2] is None:
                    continue
                hist = one[2]
                left = ctx.snap(ctx.i2x(index) + ctx.gap / 2) - px / 2
                y0 = ctx.snap(bot - ((0 - v_lo) / span) * (bot - top)) - px / 2
                y1 = ctx.snap(bot - ((hist - v_lo) / span) * (bot - top)) - px / 2
                rising = hist >= 0
                p.setBrush(QBrush(self.HIST_UP if rising else self.HIST_DOWN))
                p.setPen(QPen(self.HIST_UP_EDGE if rising else self.HIST_DOWN_EDGE, px))
                p.drawRect(
                    QRectF(
                        left,
                        min(y0, y1),
                        max(px, ctx.snap(ctx.bw) - px / 2),
                        abs(y1 - y0) or px,
                    )
                )
            p.setRenderHint(QPainter.Antialiasing, True)
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
            visible = self._vortex_data[ctx.v_start : ctx.v_end]
            if not visible:
                return
            top = ctx.paint_sub_grid(top, bot, "Vortex (14)")
            ctx.rule_line(bot - ((1.0 - 0.3) / (1.7 - 0.3)) * (bot - top))
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
            visible = self._stochrsi_data[ctx.v_start : ctx.v_end]
            if not visible:
                return
            top = ctx.paint_sub_grid(top, bot, "Stoch RSI (14, 14)")
            for ref in (0.2, 0.8):
                ctx.rule_line(bot - ref * (bot - top))
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
            """Rule the line that separates the volume strip from the price pane:
            one device pixel, aliased, snapped. The bars are painted in ``paint_to``.
            """
            ratio = self._device_ratio(p)
            px = 1.0 / ratio
            y = (int(top_px * ratio) + 0.5) / ratio
            p.setRenderHint(QPainter.Antialiasing, False)
            p.setPen(QPen(self.GRID_MAJOR, px))
            p.drawLine(QPointF(left_px, y), QPointF(right_px, y))
            p.setRenderHint(QPainter.Antialiasing, True)

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

            pen_px = device_pen_width(1.0, self._device_ratio(p))
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
                    pen_px,
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
                    p.setPen(QPen(color.lighter(140), pen_px))
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
                    p.setPen(QPen(color, pen_px))
                    p.drawRect(rect)
                    p.setBrush(QBrush(color))
                    p.setPen(Qt.NoPen)
                    p.drawEllipse(QPointF(icon_x + icon_size * 1.5, icon_y), 2, 2)

                self._right_tag(
                    p,
                    w,
                    price_y_px,
                    POSITION_TAG_FORMAT.format(price=self._fmt_price(pos.price)),
                    color,
                    font,
                )

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
            if ctx.strip_folded:
                self._draw_folded_call_strip(p, ctx.w, h, ctx.font_sm)
            else:
                self._draw_call_strip(p, ctx.w, h, ctx.ML, ctx.font_sm)

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
            p.setPen(QPen(colour, device_pen_width(1.2, self._device_ratio(p))))
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
            p.setPen(QPen(colour, ctx.pen_w(1.0), Qt.DashLine))
            p.drawLine(
                QPointF(ctx.snap(x), ctx.price_top), QPointF(ctx.snap(x), ctx.price_bot)
            )
            up = self._call_direction == CALL_BULLISH
            if up:
                tip = ctx.p2y(bar.low)
                base = tip + CALL_MARK_PX
            else:
                tip = ctx.p2y(bar.high)
                base = tip - CALL_MARK_PX
            p.setBrush(QBrush(colour))
            p.setPen(QPen(colour, ctx.pen_w(1.0)))
            p.drawPolygon(
                QPolygonF(
                    [
                        QPointF(x, tip),
                        QPointF(x - CALL_MARK_PX, base),
                        QPointF(x + CALL_MARK_PX, base),
                    ]
                )
            )

        def _draw_caption_strip(self, p: QPainter, w: int, h: int, font_sm: QFont):
            """Draw the standardised message across the foot of the image.

            A chart with no ``set_caption`` text draws nothing here and
            ``_caption_strip_h`` gave it no room.
            """
            lines = self._wrap_caption(w) if self._caption_lines else ()
            if not lines:
                return
            top = h - self._caption_strip_h(w) + CAPTION_STRIP_PAD
            p.setFont(font_sm)
            p.setPen(QPen(self.TEXT_DIM))
            for index, line in enumerate(lines):
                p.drawText(
                    CAPTION_SIDE_PAD,
                    int(top + index * CAPTION_ROW_H + CAPTION_ROW_H - 3),
                    line,
                )

        def _draw_call_strip(
            self, p: QPainter, w: int, h: int, left: int, font_sm: QFont
        ):
            """Draw one row per ``_call_readings`` entry under the time axis.

            The strip sits above the caption, so ``_caption_strip_h`` at ``w``
            is taken off the foot first.
            """
            top = h - self._caption_strip_h(w) - self._call_strip_h(w) + CALL_STRIP_PAD
            p.setFont(font_sm)
            for index, (voter, text) in enumerate(self._call_readings):
                y = top + index * CALL_ROW_H
                self._draw_call_swatch(p, left, y, voter)
                p.drawText(
                    int(left + CALL_SWATCH_PX + CALL_SWATCH_GAP_PX),
                    int(y + CALL_SWATCH_PX + 1),
                    text,
                )

        def _draw_folded_call_strip(self, p: QPainter, w: int, h: int, font_sm: QFont):
            """Draw ``_folded_call_rows`` under the time axis: each voter's name after
            its swatch, the readings' sentences left to the caption.
            """
            rows = self._folded_call_rows(w)
            top = (
                h
                - self._caption_strip_h(w)
                - self._call_strip_h(w, True)
                + CALL_STRIP_PAD
            )
            p.setFont(font_sm)
            for index, row in enumerate(rows):
                y = top + index * CALL_ROW_H
                for voter, label, x in row:
                    self._draw_call_swatch(p, x, y, voter)
                    p.drawText(
                        int(x + CALL_SWATCH_PX + CALL_SWATCH_GAP_PX),
                        int(y + CALL_SWATCH_PX + 1),
                        label,
                    )

        def _draw_call_swatch(
            self, p: QPainter, x: float, y: float, voter: str
        ) -> None:
            """Fill one ``CALL_SWATCH_PX`` square at ``x``, ``y`` in ``voter``'s overlay colour."""
            colour = self._voter_colour(voter)
            p.setBrush(QBrush(colour))
            p.setPen(Qt.NoPen)
            p.drawRect(QRectF(x, y + 2, CALL_SWATCH_PX, CALL_SWATCH_PX))
            p.setPen(QPen(self.TEXT_LIGHT))

        def _refused_fill_texts(self) -> list:
            """One header text per reason the last paint refused a fill, empty
            when every fill it was fed landed on a candle.

            A market whose fills are older than the fetched candles draws no
            glyph, so the count says so rather than leaving the chart blank.
            """
            counted = (
                (self._fills_before_window, FILLS_OLDER_HEADER_FORMAT),
                (self._fills_after_window, FILLS_NEWER_HEADER_FORMAT),
                (self._fills_off_price, FILLS_OFF_SCALE_HEADER_FORMAT),
            )
            return [
                fmt.format(count=count, fills=FILL_WORD if count == 1 else FILLS_WORD)
                for count, fmt in counted
                if count > 0
            ]

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
            info_parts.extend(self._refused_fill_texts())
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
        DRAWS_GRIP = True

        def __init__(self, symbol: str = "", parent=None):
            QWidget.__init__(self, parent)
            ChartPainter.__init__(self, symbol)
            self.setAccessibleName("Candlestick Chart")
            self.setMinimumHeight(200)
            # The layout's spare height goes to the panes, which paint_to fits.
            self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            self.setMouseTracking(True)

            # _height_override holds a dragged height; auto-expand never goes under it.
            self._height_override: Optional[int] = None
            self._resize_active = False
            self._resize_start_y: Optional[int] = None
            self._resize_start_height: Optional[int] = None

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
            """Set the minimum height to ``_natural_height_for_panes`` at the widget's width.

            ``_height_override`` from a grip drag wins when it is taller. The
            scroll area holding the chart scrolls when its viewport is shorter
            than this height; a taller viewport's extra height goes to the price pane.
            """
            target = self._natural_height_for_panes(self.width())
            if self._height_override is not None:
                target = max(target, self._height_override)
            if target != self.minimumHeight():
                self.setMinimumHeight(target)
                self.updateGeometry()

        def mouseMoveEvent(self, event):
            """The grip drag when one is active, else ``pointer_moved`` on the painter.

            A drag sets the widget's height and, through
            ``set_pane_drag_height``, the height every sub-pane draws at, so
            the price pane and the oscillators follow the bottom bar together.
            """
            mouse_y = int(event.position().y())
            grip_top_px = self.height() - self._resize_grip_h
            in_grip = mouse_y >= grip_top_px
            if self._resize_active or in_grip:
                self.setCursor(Qt.SizeVerCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            if self._resize_active and self._resize_start_y is not None:
                self._mouse_x = int(event.position().x())
                self._mouse_y = mouse_y
                delta = self._mouse_y - self._resize_start_y
                new_h = max(
                    self._readable_height_for_panes(self.width()),
                    (self._resize_start_height or 200) + delta,
                )
                self.set_pane_drag_height(new_h, self.width())
                self._height_override = new_h
                self.setMinimumHeight(new_h)
                self.updateGeometry()
                self._repaint()
                return
            self.pointer_moved(int(event.position().x()), mouse_y, self.width())

        def mousePressEvent(self, event):
            """The grip when pressed in the bottom strip, else ``pointer_pressed``."""
            if event.button() == Qt.LeftButton:
                press_y_px = int(event.position().y())
                grip_top_px = self.height() - self._resize_grip_h
                if press_y_px >= grip_top_px:
                    self._resize_active = True
                    self._resize_start_y = press_y_px
                    self._resize_start_height = self.height()
                    return
                self.pointer_pressed(int(event.position().x()))

        def mouseReleaseEvent(self, event):
            """End the drag pan and the grip drag."""
            if event.button() == Qt.LeftButton:
                self.pointer_released()
                self._resize_active = False
                self._resize_start_y = None
                self._resize_start_height = None

        def mouseDoubleClickEvent(self, event):
            self.view_reset()

        def wheelEvent(self, event):
            """``wheel_turned`` at the cursor; Ctrl held moves the price padding."""
            self.wheel_turned(
                int(event.position().x()),
                event.angleDelta().y(),
                self.width(),
                bool(event.modifiers() & Qt.ControlModifier),
            )

        def leaveEvent(self, event):
            self.pointer_left()

        def resizeEvent(self, event):
            """Re-apply the pane height when the width changes, since the caption and the reading strip wrap at it."""
            super().resizeEvent(event)
            if event.oldSize().width() != event.size().width() and self._candles:
                try:
                    self._apply_height_for_panes()
                except Exception as exc:
                    logger.debug("chart height not re-applied on resize: %s", exc)

        def paintEvent(self, event):
            p = QPainter(self)
            self.paint_to(p, self.width(), self.height())
            p.end()

    class ChartPanel(QWidget):
        """One CandlestickChart in a scroll area, with the toggle row under it.

        The scroll area's bar appears when the panel is shorter than the
        chart's natural height; a wheel over the chart zooms and never scrolls.
        The timeframe menu, the two legend labels and the source label are
        built here and placed by the owner's control row through
        ``timeframe_widgets`` and ``legend_widgets``. The toggle row carries
        one check box per ``CHART_OVERLAYS`` entry, each starting at that
        entry's ``starts_on``, its box ``TOGGLE_BOX_PX`` square.
        """

        TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"]

        TOGGLE_ROW_SPACING_PX = 6
        TOGGLE_ROW_MARGIN_PX = 4
        TOGGLE_LABEL_GAP_PX = 3

        def __init__(self, symbol: str = "", parent=None):
            super().__init__(parent)
            self.setAccessibleName("Chart Panel")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2)

            self._tf_label = QLabel(TIMEFRAME_LABEL, self)
            self._tf_combo = QComboBox(self)
            self._tf_combo.setAccessibleName("Chart timeframe")
            self._tf_combo.addItems(self.TIMEFRAMES)
            self._tf_combo.setCurrentText("1h")
            self._tf_combo.setMaximumWidth(TIMEFRAME_COMBO_MAX_WIDTH_PX)
            self._tf_combo.setFixedHeight(CONTROL_HEIGHT_PX)
            self._tf_combo.currentTextChanged.connect(self._on_tf_changed)
            self._invisible_label = QLabel(LEGEND_INVISIBLE_TEXT, self)
            self._on_book_label = QLabel(LEGEND_ON_BOOK_TEXT, self)
            self._source_label = QLabel("", self)

            self._chart = CandlestickChart(symbol)
            self._chart.setMinimumHeight(CHART_PANEL_MIN_HEIGHT_PX)
            self._scroll = QScrollArea(self)
            self._scroll.setAccessibleName(CHART_SCROLL_NAME)
            self._scroll.setWidgetResizable(True)
            self._scroll.setFrameShape(QFrame.NoFrame)
            self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self._scroll.setWidget(self._chart)
            layout.addWidget(self._scroll)

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
                box = QCheckBox(overlay.label, self)
                box.setAccessibleName(f"{overlay.label} toggle")
                box.setToolTip(overlay.tooltip)
                box.setChecked(overlay.starts_on)
                box.toggled.connect(
                    lambda on, key=overlay.key: self._toggle_indicator(key, on)
                )
                toggle_row.addWidget(box)
                self._toggles[overlay.key] = box
            toggle_row.addStretch()
            layout.addLayout(toggle_row)
            self._restyle()

        def timeframe_widgets(self) -> list:
            """The ``TF:`` label and the timeframe menu, for the owner's control row."""
            return [self._tf_label, self._tf_combo]

        def legend_widgets(self) -> list:
            """The two legend labels and the source label, for the right end of the owner's control row."""
            return [self._invisible_label, self._on_book_label, self._source_label]

        def _restyle(self) -> None:
            """Colour the two legend labels, the source label and every box from the chart's theme."""
            chart = self._chart
            self._invisible_label.setStyleSheet(
                INDICATOR_STYLE_FORMAT.format(
                    color=chart.field_colour(LEGEND_INVISIBLE_FIELD).name()
                )
            )
            self._on_book_label.setStyleSheet(
                INDICATOR_STYLE_FORMAT.format(
                    color=chart.field_colour(LEGEND_ON_BOOK_FIELD).name()
                )
            )
            self._source_label.setStyleSheet(
                INDICATOR_STYLE_FORMAT.format(color=chart.PANEL_SOURCE_TEXT.name())
            )
            for overlay in CHART_OVERLAYS:
                self._toggles[overlay.key].setStyleSheet(
                    TOGGLE_STYLE_FORMAT.format(
                        color=chart.overlay_colour(overlay).name(),
                        font_px=CAPTION_PX,
                        gap=self.TOGGLE_LABEL_GAP_PX,
                        box=TOGGLE_BOX_PX,
                    )
                )

        def set_theme(self, tokens) -> None:
            """Repaint the chart in ``tokens`` and restyle the labels and boxes from it."""
            self._chart.set_theme(tokens)
            self._restyle()

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
            """Switch one overlay through ``ChartPainter.set_overlay`` and repaint.

            ``_apply_height_for_panes`` then raises the chart's minimum
            height for a newly visible sub-pane.
            """
            self._chart.set_overlay(name, on)
            self._apply_height()
            self._chart.update()

        def show_only(self, keys) -> None:
            """``ChartPainter.show_only`` over ``keys``, each box set to match without a press."""
            self._chart.show_only(keys)
            for key, box in self._toggles.items():
                blocked = box.blockSignals(True)
                box.setChecked(self._chart._overlay_shown.get(key, False))
                box.blockSignals(blocked)
            self._apply_height()
            self._chart.update()

        def choose_timeframe(self, timeframe: str) -> None:
            """Move the combo to ``timeframe`` without its signal, and set the chart's own."""
            asked = str(timeframe)
            if asked in self.TIMEFRAMES:
                blocked = self._tf_combo.blockSignals(True)
                self._tf_combo.setCurrentText(asked)
                self._tf_combo.blockSignals(blocked)
            self._chart.set_timeframe(asked)

        def _apply_height(self) -> None:
            """``_apply_height_for_panes`` on the chart, a refusal logged and not raised."""
            try:
                self._chart._apply_height_for_panes()
            except Exception as exc:
                logger.debug("chart height not re-applied on toggle: %s", exc)

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

    def paint_image(
        painter: ChartPainter,
        width_px: int,
        height_px: int,
        device_pixel_ratio: float = 1.0,
    ) -> QImage:
        """``painter.paint_to`` onto a ``QImage`` of ``width_px`` by ``height_px`` at ``device_pixel_ratio``.

        The image holds ``width_px * device_pixel_ratio`` device pixels across,
        so a 2x display gets twice the pixels for the same chart geometry.
        """
        ratio = float(device_pixel_ratio) if float(device_pixel_ratio) > 0 else 1.0
        image = QImage(
            int(round(int(width_px) * ratio)),
            int(round(int(height_px) * ratio)),
            QImage.Format_ARGB32,
        )
        image.setDevicePixelRatio(ratio)
        image.fill(painter.BG_TOP)
        image_painter = QPainter(image)
        painter.paint_to(image_painter, int(width_px), int(height_px))
        image_painter.end()
        return image

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
        caption: str = "",
        height_px: int = NO_IMAGE_HEIGHT,
    ) -> ChartImage:
        """Draw ``candles`` through ``ChartPainter`` and write a PNG at ``path``.

        No window is shown: ``paint_to`` draws onto a ``QImage``, which Qt
        allows off the GUI thread. ``voters`` are the confirming indicators,
        ``max_overlays`` is the cap the ATA-SPM settings page sets, ``set_call``
        takes ``direction`` with the ``readings`` those voters published, and
        ``set_caption`` takes the standardised message the image carries.
        ``tokens`` left None paints ``theme_in_force``, the theme the window is in.
        ``height_px`` over ``NO_IMAGE_HEIGHT`` is the image's height, and one
        under ``_least_height_for_panes`` at ``width_px`` writes nothing and
        answers ``IMAGE_TOO_SHORT_NOTE``.
        """
        if QGuiApplication.instance() is None:
            return ChartImage(note=NO_APPLICATION_NOTE)
        held = list(candles or [])
        drawn, undrawn = overlays_for_voters(voters, int(max_overlays))
        painter = ChartPainter(str(symbol))
        painter.set_theme(tokens if tokens is not None else theme_in_force())
        painter.set_timeframe(str(timeframe))
        painter.show_only(drawn)
        painter.set_candles(held)
        painter.set_call(direction, readings)
        painter.set_caption(caption)
        if not held:
            painter.set_error(
                NO_CANDLES_NOTE.format(symbol=symbol, timeframe=timeframe)
            )
        if undrawn:
            painter.set_source_label(NOT_DRAWN_NOTE.format(voters=", ".join(undrawn)))
        asked_height = int(height_px)
        if asked_height > NO_IMAGE_HEIGHT:
            least = painter._least_height_for_panes(int(width_px))
            if asked_height < least:
                return ChartImage(
                    note=IMAGE_TOO_SHORT_NOTE.format(
                        width=int(width_px), height=asked_height, least=least
                    ),
                    bars=len(held),
                    drawn=drawn,
                    undrawn=undrawn,
                )
        else:
            asked_height = painter._natural_height_for_panes(int(width_px))
        image = paint_image(painter, int(width_px), asked_height)
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
        caption: str = "",
        height_px: int = NO_IMAGE_HEIGHT,
    ) -> ChartImage:
        """Answer that no image was drawn, because PySide6 is not installed."""
        del candles, symbol, timeframe, path, voters, max_overlays, tokens, width_px
        del direction, readings, caption, height_px
        return ChartImage(note=NO_QT_NOTE)
