"""native_chart_surface.py -- the candlestick chart, without Qt.

Describes the chart widget the Asset Charts tab draws: a header line, an
OHLC row, a price pane carrying candles and overlays, an optional volume
strip, up to three oscillator sub-panes, and a time axis. Every number the
chart works out before it paints lives here -- pane bounds, the price
range, the tick step, the price-to-pixel mapping, candle geometry, the
Heikin-Ashi bodies, colour rules, number formats and every threshold.

``ChartModel`` holds the chart's state and takes the same steps the widget
takes: ``set_candles``, ``set_positions``, ``set_tranche_floors``,
``set_target_balance_lines``, ``set_fire_armed_state``, ``set_timeframe``
and the zoom and pan steps. ``build_view_model`` returns the whole chart as
one dict.

``layout`` places the panes down the widget. ``price_range`` fits the price
axis to the visible candles. ``price_grid`` picks the tick step and the
tick prices. ``heikin_ashi`` folds raw candles into the bodies the chart
draws. ``fmt_price`` is the chart's price format.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for the
``native_chart.state`` method, which is how the Electron renderer reaches
it. Every value below is written out here rather than read from
``src.gui.native_chart``, so a value changed on one side alone is reported.
Nothing here imports Qt, and nothing runs at import time.
"""

from __future__ import annotations

import math
import time
from typing import Protocol, Sequence

Color = tuple[int, int, int, int]


class CandleLike(Protocol):
    """The five prices and the time every candle the chart draws carries."""

    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


METHOD = "native_chart.state"

ACCESSIBLE_NAME = "Candlestick Chart"

TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d", "1w")
DEFAULT_TIMEFRAME = "1h"
DEFAULT_STATUS_TEXT = "Waiting for data..."

ACTIONS = {
    "timeframe_combo.currentTextChanged": "set_timeframe",
    "bb_check.toggled": "toggle_indicator",
    "vortex_check.toggled": "toggle_indicator",
    "macd_check.toggled": "toggle_indicator",
    "stochrsi_check.toggled": "toggle_indicator",
    "ichimoku_check.toggled": "toggle_indicator",
    "volume_check.toggled": "toggle_indicator",
    "slingshot_check.toggled": "toggle_indicator",
    "bbullseye_check.toggled": "toggle_indicator",
}
SIGNALS = ("timeframe_changed",)
TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()
THREADS: tuple[str, ...] = ()

BG_TOP = (8, 8, 14, 255)
BG_BOT = (12, 12, 22, 255)
GRID_MAJOR = (28, 28, 48, 255)
GRID_MINOR = (28, 28, 48, 150)
TEXT_DIM = (180, 180, 210, 130)
TEXT_LIGHT = (180, 180, 210, 255)
ACCENT = (0, 255, 204, 255)

UP_FILL = (0, 229, 160, 255)
UP_BORDER = (92, 255, 208, 255)
DOWN_FILL = (255, 45, 111, 255)
DOWN_BORDER = (255, 134, 168, 255)
UP_WICK = (0, 229, 160, 220)
DOWN_WICK = (255, 45, 111, 220)

VOL_UP = (0, 229, 160, 60)
VOL_DOWN = (255, 45, 111, 60)
VOL_UP_BORDER = (0, 229, 160, 100)
VOL_DOWN_BORDER = (255, 45, 111, 100)

CROSSHAIR_COLOR = (60, 60, 100, 160)
PRICE_LINE_COLOR = (255, 200, 0, 200)
PRICE_BADGE_FILL = (8, 8, 14, 235)

BUY_POS_COLOR = (0, 255, 136, 255)
SELL_POS_COLOR = (255, 85, 119, 255)
INVISIBLE_ICON = (255, 140, 0, 255)
VISIBLE_ICON = (79, 195, 255, 255)

BB_CLOUD_FILL = (80, 160, 240, 32)
BB_UPPER_COLOR = (80, 160, 240, 200)
BB_MIDDLE_COLOR = (255, 200, 80, 160)
BB_LOWER_COLOR = (80, 160, 240, 200)
BB_LINE_WIDTH_PX = 1.2
BB_MIDDLE_WIDTH_PX = 0.8

KUMO_BULL_FILL = (0, 255, 136, 50)
KUMO_BEAR_FILL = (255, 85, 119, 50)
TENKAN_COLOR = (255, 140, 0, 220)
KIJUN_COLOR = (79, 195, 255, 220)
SPAN_A_COLOR = (0, 255, 136, 200)
SPAN_B_COLOR = (255, 85, 119, 200)
CHIKOU_COLOR = (180, 180, 210, 180)
ICHIMOKU_SHIFT = 26
ICHIMOKU_PERIODS = (9, 26, 52)

BULLSEYE_TOUCH_TOL = 0.005
BULLSEYE_WICK_TOL = 0.002
BULLSEYE_LOWER_TOUCH_FILL = (252, 238, 10, 55)
BULLSEYE_LOWER_WICK_FILL = (252, 238, 10, 95)
BULLSEYE_UPPER_TOUCH_FILL = (255, 0, 128, 55)
BULLSEYE_UPPER_WICK_FILL = (255, 0, 128, 95)

SLINGSHOT_BB_PERIOD = 20
SLINGSHOT_BB_STD = 2.0
SLINGSHOT_SQUEEZE_LOOKBACK = 30
SLINGSHOT_SNAPBACK_LOOKBACK = 5
SLINGSHOT_SQUEEZE_THRESHOLD = 0.6
SLINGSHOT_EXPANSION_RATIO = 1.02
SLINGSHOT_SQUEEZED_MINIMUM = 2
SLINGSHOT_RECENT_WINDOW = 4
SLINGSHOT_WINDOW_SLACK = 2
SLINGSHOT_BULL_COLOR = (0, 255, 136, 230)
SLINGSHOT_BEAR_COLOR = (255, 85, 119, 230)
SLINGSHOT_ANCHOR_OFFSET_PX = 14
SLINGSHOT_DIAMOND_PX = 6
SLINGSHOT_CIRCLE_PX = 5.5

TB_ANCHOR_COLOR = (79, 195, 255, 200)
TB_ANCHOR_BADGE_FILL = (8, 8, 14, 235)
TB_ANCHOR_LABEL = "TB-Anchor"
TB_CEILING_COLOR = (255, 0, 128, 220)
TB_CEILING_BADGE_FILL = (8, 8, 14, 235)
TB_CEILING_LABEL = "TB-Ceiling"
TB_LINE_WIDTH_PX = 1.4

GLOW_INSET_PX = 4
GLOW_WIDTH_PX = 6
GLOW_SCRUM_COLOR = (0, 255, 136, 220)
GLOW_FOLD_COLOR = (255, 85, 119, 220)
GLOW_PANE_SPLIT = 0.5

SUB_BACKDROP_FILL = (8, 8, 14, 150)
SUB_BADGE_FILL = (8, 8, 14, 235)
SUB_LABEL_INSET_PX = 6
SUB_LABEL_BASELINE_PX = 11
SUB_AXIS_SMALL_LIMIT = 10
MACD_TITLE = "MACD (12, 26, 9)"
MACD_PERIODS = (12, 26, 9)
MACD_PAD_RATIO = 0.1
MACD_PAD_FLOOR = 1e-6
MACD_LINE_COLOR = (255, 140, 0, 230)
MACD_SIGNAL_COLOR = (79, 195, 255, 220)
MACD_HIST_UP_FILL = (0, 229, 160, 160)
MACD_HIST_UP_BORDER = (92, 255, 208, 200)
MACD_HIST_DOWN_FILL = (255, 45, 111, 160)
MACD_HIST_DOWN_BORDER = (255, 134, 168, 200)
VORTEX_TITLE = "Vortex (14)"
VORTEX_PERIOD = 14
VORTEX_SCALE_MIN = 0.3
VORTEX_SCALE_MAX = 1.7
VORTEX_REFERENCE = 1.0
VORTEX_PLUS_COLOR = (0, 255, 136, 230)
VORTEX_MINUS_COLOR = (255, 85, 119, 230)
STOCHRSI_TITLE = "Stoch RSI (14, 14)"
STOCHRSI_SCALE_MIN = 0.0
STOCHRSI_SCALE_MAX = 1.0
STOCHRSI_REFERENCES = (0.2, 0.8)
STOCHRSI_COLOR = (255, 144, 96, 230)
OSCILLATOR_WIDTH_PX = 1.2
OSCILLATOR_ACCENT_WIDTH_PX = 1.4
OSCILLATOR_SIGNAL_WIDTH_PX = 1.0
OSCILLATOR_RANGE_FLOOR = 1e-9

BOLLINGER_PERIOD = 20
BOLLINGER_STD = 2.0

TRANCHE_FLOOR_COLOR = (255, 200, 0, 180)
TRANCHE_FLOOR_TEXT_COLOR = (255, 200, 0, 180)
TRANCHE_FLOOR_LABEL_FORMAT = "FLOOR {label}"
TRANCHE_FLOOR_LABEL_INSET_PX = 4
TRANCHE_FLOOR_LABEL_LIFT_PX = 2

MARKER_TYPE_COLORS = {
    "SCRUM": (255, 200, 0, 255),
    "FOLD": (79, 195, 255, 255),
    "DIST": (255, 0, 170, 255),
}
MARKER_DEFAULT_BUY = (0, 255, 136, 255)
MARKER_DEFAULT_SELL = (255, 85, 119, 255)
MARKER_OUTLINE = (180, 180, 210, 120)
MARKER_LABEL_BACKDROP = (8, 8, 14, 235)
MARKER_SIZE_PX = 5
MARKER_TICK_PX = 6
MARKER_LABEL_HEIGHT_PX = 13
MARKER_LABEL_PAD_PX = 6
MARKER_LABEL_DROP_PX = 18
MARKER_LABEL_RISE_PX = 8
MARKER_DEFAULT_ROLE = "FOLD"
MARKER_DEFAULT_SIDE = "buy"

POSITION_ICON_INSET_PX = 2
POSITION_ICON_SIZE_PX = 7
POSITION_LINE_ALPHA = 50
POSITION_LABEL_ALPHA = 140
POSITION_FILLED_ALPHA = 100
POSITION_ICON_LIGHTER_PCT = 140
POSITION_DOT_RADIUS_PX = 2
POSITION_LABEL_INSET_PX = 6
POSITION_LABEL_LIFT_PX = 3
POSITION_STATUS_FILLED = " FILLED"
POSITION_STATUS_TRACKED = " TRACKED"
POSITION_STATUS_ON_BOOK = " ON BOOK"
POSITION_INVISIBLE_KEY = "internal"
SIDE_BUY = "buy"

TOOLTIP_LINE_HEIGHT_PX = 14
TOOLTIP_PAD_PX = 8
TOOLTIP_FILL = (8, 8, 14, 235)
TOOLTIP_BORDER = (28, 28, 48, 255)
TOOLTIP_INSET_PX = 8
TOOLTIP_LABEL_INSET_PX = 6
TOOLTIP_VALUE_INSET_PX = 24
TOOLTIP_BASELINE_LIFT_PX = 3
TOOLTIP_STRIPE_WIDTH_PX = 3
CROSSHAIR_BADGE_FILL = (8, 8, 14, 235)
CROSSHAIR_TIME_FORMAT = "%Y-%m-%d %H:%M"

HEADER_HEIGHT_PX = 28
OHLC_ROW_HEIGHT_PX = 18
TIME_AXIS_HEIGHT_PX = 18
LEFT_MARGIN_PX = 8
RIGHT_MARGIN_PX = 78
VOLUME_STRIP_PX = 28
SUB_PANE_PX = 60
PRICE_PANE_PAINT_FLOOR_PX = 120
PRICE_PANE_LAYOUT_FLOOR_PX = 220
SUB_PANE_ORDER = ("macd", "vortex", "stochrsi")

MINIMUM_HEIGHT_PX = 200
RESIZE_GRIP_PX = 8
PARENT_HEIGHT_PAD_PX = 36
GRIP_DASH_OFFSETS_PX = (-12, 0, 12)
GRIP_DASH_HALF_PX = 4
GRIP_COLOR = (180, 180, 210, 110)
GRIP_LINE_WIDTH_PX = 1.2

ZOOM_IN_FACTOR = 0.85
ZOOM_OUT_FACTOR = 1.18
Y_ZOOM_MIN = 0.05
Y_ZOOM_MAX = 4.0
Y_ZOOM_DEFAULT = 1.0
MIN_VISIBLE_CANDLES = 8
PAN_PIXELS_PER_CANDLE_FLOOR = 0.001

PRICE_PAD_RATIO = 0.04
FLAT_RANGE_RATIO = 0.01
FLAT_RANGE_FALLBACK = 1.0
GRID_TARGET_TICKS = 6
GRID_TICK_TOLERANCE = 1e-9
NICE_STEP_BREAKS = ((1.5, 1), (3.5, 2), (7.5, 5))
NICE_STEP_TOP = 10
NICE_STEP_FALLBACK = 1.0
MAJOR_EVERY = 2

CANDLE_WIDTH_FLOOR_PX = 2
CANDLE_GAP_RATIO = 0.18
CANDLE_GAP_FLOOR_PX = 1
CANDLE_BODY_FLOOR_PX = 1

TIME_TICK_TARGET = 6
PAIR_MINIMUM = 2
DAY_SECONDS = 24 * 3600
TIME_LABEL_DATE = "%m-%d"
TIME_LABEL_CLOCK = "%H:%M"
TIME_LABEL_OFFSET_PX = 16
TIME_LABEL_BASELINE_PX = 12

PRICE_LABEL_INSET_PX = 6
PRICE_LABEL_BASELINE_PX = 4
PRICE_BADGE_PAD_PX = 10
PRICE_BADGE_HEIGHT_PX = 18
PRICE_BADGE_LIFT_PX = 9
PRICE_BADGE_RADIUS_PX = 3
TB_BADGE_PAD_PX = 10
TB_BADGE_HEIGHT_PX = 14
TB_BADGE_LIFT_PX = 8
TB_BADGE_INSET_PX = 4
TB_BADGE_RADIUS_PX = 2
SUB_BADGE_PAD_PX = 8
SUB_BADGE_HEIGHT_PX = 14
SUB_BADGE_LIFT_PX = 8
SUB_BADGE_INSET_PX = 2
CROSSHAIR_BADGE_PAD_PX = 12
CROSSHAIR_TIME_BADGE_HEIGHT_PX = 16

HEADER_SYMBOL_X_PX = 8
HEADER_BASELINE_PX = 18
HEADER_INFO_GAP_PX = 16
HEADER_ERROR_DROP_PX = 14
HEADER_ERROR_COLOR = (255, 85, 119, 255)
HEADER_SEPARATOR = "  •  "
HEADER_COUNT_FORMAT = "{count} candles"
HEADER_INVISIBLE_FORMAT = "{count} invisible"
HEADER_ON_BOOK_FORMAT = "{count} on book"
HEADER_POSITION_JOIN = " | "

OHLC_BASELINE_PX = 13
OHLC_INSET_PX = 4
OHLC_LABEL_GAP_PX = 4
OHLC_VALUE_GAP_PX = 12

VOLUME_BILLION = 1e9
VOLUME_MILLION = 1e6
VOLUME_THOUSAND = 1e3
VOLUME_AXIS_FORMAT = "Vol {value}"
VOLUME_AXIS_INSET_PX = 6
VOLUME_AXIS_BASELINE_PX = 10

FMT_SUB_MICRO = 0.0001
FMT_SUB_CENT = 0.01
FMT_SUB_UNIT = 1
FMT_THOUSAND = 1000

PANEL_SPACING_PX = 2
PANEL_MARGINS = (0, 0, 0, 0)
TOOLBAR_MARGINS = (4, 2, 4, 2)
INDICATOR_ROW_SPACING_PX = 6
LEGEND_SPACING_PX = 12
TIMEFRAME_LABEL = "TF:"
TIMEFRAME_COMBO_MAX_WIDTH_PX = 90
CHART_PANEL_MIN_HEIGHT_PX = 250
LEGEND_INVISIBLE_TEXT = "◆ Invisible"
LEGEND_INVISIBLE_STYLE = "color: #ffa000; font-size: 9px;"
LEGEND_ON_BOOK_TEXT = "□ On Book"
LEGEND_ON_BOOK_STYLE = "color: #00b4ff; font-size: 9px;"
PANEL_SOURCE_STYLE = "color: #555; font-size: 9px;"
INDICATOR_STYLE_FORMAT = "color: {color}; font-size: 9px;"

INDICATOR_TOGGLES = (
    ("bb", "BB", "#50a0f0"),
    ("vortex", "Vortex", "#00ff88"),
    ("macd", "MACD", "#ff8c00"),
    ("stochrsi", "SRsi", "#ff9060"),
    ("ichimoku", "Ichi", "#4fc3ff"),
    ("volume", "Vol", "#b4b4d2"),
    ("slingshot", "Sling", "#ff00aa"),
    ("bbullseye", "BBull", "#fcee0a"),
)

#: An overlay that paints a fill over the price pane, so it starts off.
INDICATOR_OCCLUDES = {
    "bb": False,
    "vortex": False,
    "macd": False,
    "stochrsi": False,
    "ichimoku": False,
    "volume": False,
    "slingshot": True,
    "bbullseye": True,
}
INDICATOR_DEFAULTS = {key: not occludes for key, occludes in INDICATOR_OCCLUDES.items()}

ALPHA_BYTE_TOP = 255
CSS_ALPHA_PLACES = 4
CSS_COLOR_FORMAT = "rgba({red}, {green}, {blue}, {alpha})"
BACKGROUND_FORMAT = "linear-gradient(to bottom, {top}, {bottom})"
SKIN_LENGTH_KEYS = ("panel_margins", "toolbar_margins")

CANDLE_BORDER_WIDTH_PX = 1
WICK_WIDTH_PX = 1
GRID_LINE_WIDTH_PX = 1
PRICE_LINE_WIDTH_PX = 1
GRID_LINE_STYLE = "dotted"
PRICE_LINE_STYLE = "dashed"
SOLID_LINE_STYLE = "solid"
# CSS carries no dash-dot border, so the position line takes the nearest.
POSITION_LINE_STYLE = "dashed"

LINE_KIND_LAST_PRICE = "last_price"
LINE_KIND_TB_ANCHOR = "tb_anchor"
LINE_KIND_TB_CEILING = "tb_ceiling"
LINE_KIND_TRANCHE_FLOOR = "tranche_floor"
LINE_KIND_POSITION = "position"
TB_LABEL_FORMAT = "{label} {price}"

SKIN = {
    "bg_top": BG_TOP,
    "bg_bot": BG_BOT,
    "grid_major": GRID_MAJOR,
    "grid_minor": GRID_MINOR,
    "text_dim": TEXT_DIM,
    "text_light": TEXT_LIGHT,
    "accent": ACCENT,
    "up_fill": UP_FILL,
    "up_border": UP_BORDER,
    "down_fill": DOWN_FILL,
    "down_border": DOWN_BORDER,
    "up_wick": UP_WICK,
    "down_wick": DOWN_WICK,
    "vol_up": VOL_UP,
    "vol_down": VOL_DOWN,
    "vol_up_border": VOL_UP_BORDER,
    "vol_down_border": VOL_DOWN_BORDER,
    "crosshair_color": CROSSHAIR_COLOR,
    "price_line_color": PRICE_LINE_COLOR,
    "price_badge_fill": PRICE_BADGE_FILL,
    "buy_pos_color": BUY_POS_COLOR,
    "sell_pos_color": SELL_POS_COLOR,
    "invisible_icon": INVISIBLE_ICON,
    "visible_icon": VISIBLE_ICON,
    "bb_cloud_fill": BB_CLOUD_FILL,
    "bb_upper_color": BB_UPPER_COLOR,
    "bb_middle_color": BB_MIDDLE_COLOR,
    "bb_lower_color": BB_LOWER_COLOR,
    "kumo_bull_fill": KUMO_BULL_FILL,
    "kumo_bear_fill": KUMO_BEAR_FILL,
    "tenkan_color": TENKAN_COLOR,
    "kijun_color": KIJUN_COLOR,
    "span_a_color": SPAN_A_COLOR,
    "span_b_color": SPAN_B_COLOR,
    "chikou_color": CHIKOU_COLOR,
    "bullseye_lower_touch_fill": BULLSEYE_LOWER_TOUCH_FILL,
    "bullseye_lower_wick_fill": BULLSEYE_LOWER_WICK_FILL,
    "bullseye_upper_touch_fill": BULLSEYE_UPPER_TOUCH_FILL,
    "bullseye_upper_wick_fill": BULLSEYE_UPPER_WICK_FILL,
    "slingshot_bull_color": SLINGSHOT_BULL_COLOR,
    "slingshot_bear_color": SLINGSHOT_BEAR_COLOR,
    "tb_anchor_color": TB_ANCHOR_COLOR,
    "tb_anchor_badge_fill": TB_ANCHOR_BADGE_FILL,
    "tb_ceiling_color": TB_CEILING_COLOR,
    "tb_ceiling_badge_fill": TB_CEILING_BADGE_FILL,
    "glow_scrum_color": GLOW_SCRUM_COLOR,
    "glow_fold_color": GLOW_FOLD_COLOR,
    "sub_backdrop_fill": SUB_BACKDROP_FILL,
    "sub_badge_fill": SUB_BADGE_FILL,
    "macd_line_color": MACD_LINE_COLOR,
    "macd_signal_color": MACD_SIGNAL_COLOR,
    "macd_hist_up_fill": MACD_HIST_UP_FILL,
    "macd_hist_up_border": MACD_HIST_UP_BORDER,
    "macd_hist_down_fill": MACD_HIST_DOWN_FILL,
    "macd_hist_down_border": MACD_HIST_DOWN_BORDER,
    "vortex_plus_color": VORTEX_PLUS_COLOR,
    "vortex_minus_color": VORTEX_MINUS_COLOR,
    "stochrsi_color": STOCHRSI_COLOR,
    "tranche_floor_color": TRANCHE_FLOOR_COLOR,
    "tranche_floor_text_color": TRANCHE_FLOOR_TEXT_COLOR,
    "marker_default_buy": MARKER_DEFAULT_BUY,
    "marker_default_sell": MARKER_DEFAULT_SELL,
    "marker_outline": MARKER_OUTLINE,
    "marker_label_backdrop": MARKER_LABEL_BACKDROP,
    "tooltip_fill": TOOLTIP_FILL,
    "tooltip_border": TOOLTIP_BORDER,
    "crosshair_badge_fill": CROSSHAIR_BADGE_FILL,
    "grip_color": GRIP_COLOR,
    "header_error_color": HEADER_ERROR_COLOR,
    "panel_margins": PANEL_MARGINS,
    "toolbar_margins": TOOLBAR_MARGINS,
}

METRICS = {
    "default_timeframe": DEFAULT_TIMEFRAME,
    "default_status_text": DEFAULT_STATUS_TEXT,
    "bb_line_width_px": BB_LINE_WIDTH_PX,
    "bb_middle_width_px": BB_MIDDLE_WIDTH_PX,
    "ichimoku_shift": ICHIMOKU_SHIFT,
    "ichimoku_periods": ICHIMOKU_PERIODS,
    "bullseye_touch_tol": BULLSEYE_TOUCH_TOL,
    "bullseye_wick_tol": BULLSEYE_WICK_TOL,
    "slingshot_bb_period": SLINGSHOT_BB_PERIOD,
    "slingshot_bb_std": SLINGSHOT_BB_STD,
    "slingshot_squeeze_lookback": SLINGSHOT_SQUEEZE_LOOKBACK,
    "slingshot_snapback_lookback": SLINGSHOT_SNAPBACK_LOOKBACK,
    "slingshot_squeeze_threshold": SLINGSHOT_SQUEEZE_THRESHOLD,
    "slingshot_expansion_ratio": SLINGSHOT_EXPANSION_RATIO,
    "slingshot_squeezed_minimum": SLINGSHOT_SQUEEZED_MINIMUM,
    "slingshot_recent_window": SLINGSHOT_RECENT_WINDOW,
    "slingshot_window_slack": SLINGSHOT_WINDOW_SLACK,
    "slingshot_anchor_offset_px": SLINGSHOT_ANCHOR_OFFSET_PX,
    "slingshot_diamond_px": SLINGSHOT_DIAMOND_PX,
    "slingshot_circle_px": SLINGSHOT_CIRCLE_PX,
    "tb_anchor_label": TB_ANCHOR_LABEL,
    "tb_ceiling_label": TB_CEILING_LABEL,
    "tb_line_width_px": TB_LINE_WIDTH_PX,
    "glow_inset_px": GLOW_INSET_PX,
    "glow_width_px": GLOW_WIDTH_PX,
    "glow_pane_split": GLOW_PANE_SPLIT,
    "sub_label_inset_px": SUB_LABEL_INSET_PX,
    "sub_label_baseline_px": SUB_LABEL_BASELINE_PX,
    "sub_axis_small_limit": SUB_AXIS_SMALL_LIMIT,
    "macd_title": MACD_TITLE,
    "macd_periods": MACD_PERIODS,
    "macd_pad_ratio": MACD_PAD_RATIO,
    "macd_pad_floor": MACD_PAD_FLOOR,
    "vortex_title": VORTEX_TITLE,
    "vortex_period": VORTEX_PERIOD,
    "vortex_scale_min": VORTEX_SCALE_MIN,
    "vortex_scale_max": VORTEX_SCALE_MAX,
    "vortex_reference": VORTEX_REFERENCE,
    "stochrsi_title": STOCHRSI_TITLE,
    "stochrsi_scale_min": STOCHRSI_SCALE_MIN,
    "stochrsi_scale_max": STOCHRSI_SCALE_MAX,
    "stochrsi_references": STOCHRSI_REFERENCES,
    "oscillator_width_px": OSCILLATOR_WIDTH_PX,
    "oscillator_accent_width_px": OSCILLATOR_ACCENT_WIDTH_PX,
    "oscillator_signal_width_px": OSCILLATOR_SIGNAL_WIDTH_PX,
    "oscillator_range_floor": OSCILLATOR_RANGE_FLOOR,
    "bollinger_period": BOLLINGER_PERIOD,
    "bollinger_std": BOLLINGER_STD,
    "tranche_floor_label_format": TRANCHE_FLOOR_LABEL_FORMAT,
    "tranche_floor_label_inset_px": TRANCHE_FLOOR_LABEL_INSET_PX,
    "tranche_floor_label_lift_px": TRANCHE_FLOOR_LABEL_LIFT_PX,
    "marker_type_colors": MARKER_TYPE_COLORS,
    "marker_size_px": MARKER_SIZE_PX,
    "marker_tick_px": MARKER_TICK_PX,
    "marker_label_height_px": MARKER_LABEL_HEIGHT_PX,
    "marker_label_pad_px": MARKER_LABEL_PAD_PX,
    "marker_label_drop_px": MARKER_LABEL_DROP_PX,
    "marker_label_rise_px": MARKER_LABEL_RISE_PX,
    "marker_default_role": MARKER_DEFAULT_ROLE,
    "marker_default_side": MARKER_DEFAULT_SIDE,
    "position_icon_inset_px": POSITION_ICON_INSET_PX,
    "position_icon_size_px": POSITION_ICON_SIZE_PX,
    "position_line_alpha": POSITION_LINE_ALPHA,
    "position_label_alpha": POSITION_LABEL_ALPHA,
    "position_filled_alpha": POSITION_FILLED_ALPHA,
    "position_icon_lighter_pct": POSITION_ICON_LIGHTER_PCT,
    "position_dot_radius_px": POSITION_DOT_RADIUS_PX,
    "position_label_inset_px": POSITION_LABEL_INSET_PX,
    "position_label_lift_px": POSITION_LABEL_LIFT_PX,
    "position_status_filled": POSITION_STATUS_FILLED,
    "position_status_tracked": POSITION_STATUS_TRACKED,
    "position_status_on_book": POSITION_STATUS_ON_BOOK,
    "position_invisible_key": POSITION_INVISIBLE_KEY,
    "side_buy": SIDE_BUY,
    "tooltip_line_height_px": TOOLTIP_LINE_HEIGHT_PX,
    "tooltip_pad_px": TOOLTIP_PAD_PX,
    "tooltip_inset_px": TOOLTIP_INSET_PX,
    "tooltip_label_inset_px": TOOLTIP_LABEL_INSET_PX,
    "tooltip_value_inset_px": TOOLTIP_VALUE_INSET_PX,
    "tooltip_baseline_lift_px": TOOLTIP_BASELINE_LIFT_PX,
    "tooltip_stripe_width_px": TOOLTIP_STRIPE_WIDTH_PX,
    "crosshair_time_format": CROSSHAIR_TIME_FORMAT,
    "header_height_px": HEADER_HEIGHT_PX,
    "ohlc_row_height_px": OHLC_ROW_HEIGHT_PX,
    "time_axis_height_px": TIME_AXIS_HEIGHT_PX,
    "left_margin_px": LEFT_MARGIN_PX,
    "right_margin_px": RIGHT_MARGIN_PX,
    "volume_strip_px": VOLUME_STRIP_PX,
    "sub_pane_px": SUB_PANE_PX,
    "price_pane_paint_floor_px": PRICE_PANE_PAINT_FLOOR_PX,
    "price_pane_layout_floor_px": PRICE_PANE_LAYOUT_FLOOR_PX,
    "sub_pane_order": SUB_PANE_ORDER,
    "minimum_height_px": MINIMUM_HEIGHT_PX,
    "resize_grip_px": RESIZE_GRIP_PX,
    "parent_height_pad_px": PARENT_HEIGHT_PAD_PX,
    "grip_dash_offsets_px": GRIP_DASH_OFFSETS_PX,
    "grip_dash_half_px": GRIP_DASH_HALF_PX,
    "grip_line_width_px": GRIP_LINE_WIDTH_PX,
    "zoom_in_factor": ZOOM_IN_FACTOR,
    "zoom_out_factor": ZOOM_OUT_FACTOR,
    "y_zoom_min": Y_ZOOM_MIN,
    "y_zoom_max": Y_ZOOM_MAX,
    "y_zoom_default": Y_ZOOM_DEFAULT,
    "min_visible_candles": MIN_VISIBLE_CANDLES,
    "pan_pixels_per_candle_floor": PAN_PIXELS_PER_CANDLE_FLOOR,
    "price_pad_ratio": PRICE_PAD_RATIO,
    "flat_range_ratio": FLAT_RANGE_RATIO,
    "flat_range_fallback": FLAT_RANGE_FALLBACK,
    "grid_target_ticks": GRID_TARGET_TICKS,
    "grid_tick_tolerance": GRID_TICK_TOLERANCE,
    "nice_step_breaks": NICE_STEP_BREAKS,
    "nice_step_top": NICE_STEP_TOP,
    "nice_step_fallback": NICE_STEP_FALLBACK,
    "major_every": MAJOR_EVERY,
    "candle_width_floor_px": CANDLE_WIDTH_FLOOR_PX,
    "candle_gap_ratio": CANDLE_GAP_RATIO,
    "candle_gap_floor_px": CANDLE_GAP_FLOOR_PX,
    "candle_body_floor_px": CANDLE_BODY_FLOOR_PX,
    "time_tick_target": TIME_TICK_TARGET,
    "pair_minimum": PAIR_MINIMUM,
    "day_seconds": DAY_SECONDS,
    "time_label_date": TIME_LABEL_DATE,
    "time_label_clock": TIME_LABEL_CLOCK,
    "time_label_offset_px": TIME_LABEL_OFFSET_PX,
    "time_label_baseline_px": TIME_LABEL_BASELINE_PX,
    "price_label_inset_px": PRICE_LABEL_INSET_PX,
    "price_label_baseline_px": PRICE_LABEL_BASELINE_PX,
    "price_badge_pad_px": PRICE_BADGE_PAD_PX,
    "price_badge_height_px": PRICE_BADGE_HEIGHT_PX,
    "price_badge_lift_px": PRICE_BADGE_LIFT_PX,
    "price_badge_radius_px": PRICE_BADGE_RADIUS_PX,
    "tb_badge_pad_px": TB_BADGE_PAD_PX,
    "tb_badge_height_px": TB_BADGE_HEIGHT_PX,
    "tb_badge_lift_px": TB_BADGE_LIFT_PX,
    "tb_badge_inset_px": TB_BADGE_INSET_PX,
    "tb_badge_radius_px": TB_BADGE_RADIUS_PX,
    "sub_badge_pad_px": SUB_BADGE_PAD_PX,
    "sub_badge_height_px": SUB_BADGE_HEIGHT_PX,
    "sub_badge_lift_px": SUB_BADGE_LIFT_PX,
    "sub_badge_inset_px": SUB_BADGE_INSET_PX,
    "crosshair_badge_pad_px": CROSSHAIR_BADGE_PAD_PX,
    "crosshair_time_badge_height_px": CROSSHAIR_TIME_BADGE_HEIGHT_PX,
    "header_symbol_x_px": HEADER_SYMBOL_X_PX,
    "header_baseline_px": HEADER_BASELINE_PX,
    "header_info_gap_px": HEADER_INFO_GAP_PX,
    "header_error_drop_px": HEADER_ERROR_DROP_PX,
    "header_separator": HEADER_SEPARATOR,
    "header_count_format": HEADER_COUNT_FORMAT,
    "header_invisible_format": HEADER_INVISIBLE_FORMAT,
    "header_on_book_format": HEADER_ON_BOOK_FORMAT,
    "header_position_join": HEADER_POSITION_JOIN,
    "ohlc_baseline_px": OHLC_BASELINE_PX,
    "ohlc_inset_px": OHLC_INSET_PX,
    "ohlc_label_gap_px": OHLC_LABEL_GAP_PX,
    "ohlc_value_gap_px": OHLC_VALUE_GAP_PX,
    "volume_billion": VOLUME_BILLION,
    "volume_million": VOLUME_MILLION,
    "volume_thousand": VOLUME_THOUSAND,
    "volume_axis_format": VOLUME_AXIS_FORMAT,
    "volume_axis_inset_px": VOLUME_AXIS_INSET_PX,
    "volume_axis_baseline_px": VOLUME_AXIS_BASELINE_PX,
    "fmt_sub_micro": FMT_SUB_MICRO,
    "fmt_sub_cent": FMT_SUB_CENT,
    "fmt_sub_unit": FMT_SUB_UNIT,
    "fmt_thousand": FMT_THOUSAND,
    "panel_spacing_px": PANEL_SPACING_PX,
    "indicator_row_spacing_px": INDICATOR_ROW_SPACING_PX,
    "legend_spacing_px": LEGEND_SPACING_PX,
    "timeframe_label": TIMEFRAME_LABEL,
    "timeframe_combo_max_width_px": TIMEFRAME_COMBO_MAX_WIDTH_PX,
    "chart_panel_min_height_px": CHART_PANEL_MIN_HEIGHT_PX,
    "legend_invisible_text": LEGEND_INVISIBLE_TEXT,
    "legend_invisible_style": LEGEND_INVISIBLE_STYLE,
    "legend_on_book_text": LEGEND_ON_BOOK_TEXT,
    "legend_on_book_style": LEGEND_ON_BOOK_STYLE,
    "panel_source_style": PANEL_SOURCE_STYLE,
    "indicator_style_format": INDICATOR_STYLE_FORMAT,
    "indicator_toggles": INDICATOR_TOGGLES,
    "candle_border_width_px": CANDLE_BORDER_WIDTH_PX,
    "wick_width_px": WICK_WIDTH_PX,
    "grid_line_width_px": GRID_LINE_WIDTH_PX,
    "price_line_width_px": PRICE_LINE_WIDTH_PX,
    "grid_line_style": GRID_LINE_STYLE,
    "price_line_style": PRICE_LINE_STYLE,
    "solid_line_style": SOLID_LINE_STYLE,
    "position_line_style": POSITION_LINE_STYLE,
    "tb_label_format": TB_LABEL_FORMAT,
    "alpha_byte_top": ALPHA_BYTE_TOP,
    "css_alpha_places": CSS_ALPHA_PLACES,
    "css_color_format": CSS_COLOR_FORMAT,
    "background_format": BACKGROUND_FORMAT,
    "skin_length_keys": SKIN_LENGTH_KEYS,
    "line_kind_last_price": LINE_KIND_LAST_PRICE,
    "line_kind_tb_anchor": LINE_KIND_TB_ANCHOR,
    "line_kind_tb_ceiling": LINE_KIND_TB_CEILING,
    "line_kind_tranche_floor": LINE_KIND_TRANCHE_FLOOR,
    "line_kind_position": LINE_KIND_POSITION,
}


STEP_NAMES = (
    "set_candles",
    "set_source_label",
    "set_error",
    "set_positions",
    "set_grid_lines",
    "set_tranche_floors",
    "set_target_balance_lines",
    "set_fire_armed_state",
    "set_timeframe",
    "set_markers",
    "toggle_indicator",
    "zoom",
    "pan",
    "reset_view",
)


def css_color(color: Color) -> str:
    """One skin colour as CSS text, its Qt alpha byte divided into a fraction."""
    red, green, blue, alpha = color
    return CSS_COLOR_FORMAT.format(
        red=red,
        green=green,
        blue=blue,
        alpha=round(alpha / ALPHA_BYTE_TOP, CSS_ALPHA_PLACES),
    )


def with_alpha(color: Color, alpha: int) -> Color:
    """One skin colour under a different alpha byte."""
    red, green, blue, _ = color
    return (red, green, blue, alpha)


def skin_css() -> dict:
    """Every skin colour as CSS text, under its skin name."""
    return {
        name: css_color(value)
        for name, value in SKIN.items()
        if name not in SKIN_LENGTH_KEYS
    }


def background_css() -> str:
    """The chart's ground, a top-to-bottom gradient between two skin colours."""
    return BACKGROUND_FORMAT.format(top=css_color(BG_TOP), bottom=css_color(BG_BOT))


def body_pixels(
    open_price: float,
    close_price: float,
    price_top_px: float,
    price_height_px: float,
    low: float,
    span: float,
) -> dict:
    """Top and height of one candle body, never thinner than the floor."""
    top = price_to_y(open_price, price_top_px, price_height_px, low, span)
    bottom = price_to_y(close_price, price_top_px, price_height_px, low, span)
    return {
        "y_px": min(top, bottom),
        "height_px": max(abs(top - bottom), CANDLE_BODY_FLOOR_PX),
    }


def wick_pixels(
    high_price: float,
    low_price: float,
    price_top_px: float,
    price_height_px: float,
    low: float,
    span: float,
) -> dict:
    """Top and height of one candle wick."""
    top = price_to_y(high_price, price_top_px, price_height_px, low, span)
    bottom = price_to_y(low_price, price_top_px, price_height_px, low, span)
    return {"y_px": top, "height_px": bottom - top}


def fmt_price(price: float) -> str:
    """The chart's price text, chosen by size band.

    Bands are open at the top, so 1000 formats with a thousands separator
    and 999.999 does not, rounding instead to 1000.00.
    """
    if price < FMT_SUB_MICRO:
        return f"{price:.8f}"
    elif price < FMT_SUB_CENT:
        return f"{price:.6f}"
    elif price < FMT_SUB_UNIT:
        return f"{price:.4f}"
    elif price < FMT_THOUSAND:
        return f"{price:.2f}"
    else:
        return f"{price:,.2f}"


def fmt_volume(volume: float) -> str:
    """Volume text for the axis label, in B, M, K or whole units."""
    if volume >= VOLUME_BILLION:
        return f"{volume / VOLUME_BILLION:.1f}B"
    if volume >= VOLUME_MILLION:
        return f"{volume / VOLUME_MILLION:.1f}M"
    if volume >= VOLUME_THOUSAND:
        return f"{volume / VOLUME_THOUSAND:.1f}K"
    return f"{volume:.0f}"


def fmt_tooltip_volume(volume: float) -> str:
    """Volume text inside the hover tooltip, in M, K or whole units."""
    if volume >= VOLUME_MILLION:
        return f"{volume / VOLUME_MILLION:.2f}M"
    if volume >= VOLUME_THOUSAND:
        return f"{volume / VOLUME_THOUSAND:.1f}K"
    return f"{volume:.0f}"


def fmt_ohlc_volume(volume: float) -> str:
    """Volume text on the OHLC row, which keeps two decimals below 1000."""
    if volume >= VOLUME_MILLION:
        return f"{volume / VOLUME_MILLION:.2f}M"
    if volume >= VOLUME_THOUSAND:
        return f"{volume / VOLUME_THOUSAND:.1f}K"
    return f"{volume:.2f}"


def fmt_sub_axis(value: float) -> str:
    """Sub-pane axis text: four decimals under 10, two at or above."""
    return f"{value:.4f}" if abs(value) < SUB_AXIS_SMALL_LIMIT else f"{value:.2f}"


def fmt_change(change: float) -> str:
    """Signed price change, six significant figures."""
    return f"{change:+.6g}"


def fmt_change_pct(change_pct_value: float) -> str:
    """Signed percent change, two decimals."""
    return f"{change_pct_value:+.2f}%"


def change_pct(open_price: float, close_price: float) -> float:
    """Percent move from open to close; zero when open is not above zero."""
    change = close_price - open_price
    return (change / open_price * 100) if open_price > 0 else 0


def nice_step(span: float, target_ticks: int = GRID_TARGET_TICKS) -> float:
    """A 1, 2, 5 or 10 times a power of ten step covering `span`."""
    if span <= 0:
        return NICE_STEP_FALLBACK
    count = max(target_ticks, 1)
    raw = span / count
    magnitude = 10 ** math.floor(math.log10(raw))
    for fraction_limit, multiple in NICE_STEP_BREAKS:
        if raw / magnitude < fraction_limit:
            return multiple * magnitude
    return NICE_STEP_TOP * magnitude


def effective_visible_start(visible_start: int | None, candle_count: int) -> int:
    """Where the visible window starts; 0 when the chart is fitting all."""
    if visible_start is None:
        return 0
    return max(0, min(candle_count - 1, visible_start))


def effective_visible_count(visible_count: int | None, candle_count: int) -> int:
    """How many candles the window shows; all of them when fitting all."""
    if visible_count is None:
        return candle_count
    return max(MIN_VISIBLE_CANDLES, min(candle_count, visible_count))


def natural_height(*, show_volume: bool, sub_pane_count: int) -> int:
    """Least widget height that draws the price pane and every sub-pane."""
    base = (
        HEADER_HEIGHT_PX
        + OHLC_ROW_HEIGHT_PX
        + PRICE_PANE_LAYOUT_FLOOR_PX
        + TIME_AXIS_HEIGHT_PX
    )
    if show_volume:
        base += VOLUME_STRIP_PX
    return base + sub_pane_count * SUB_PANE_PX


def active_sub_panes(flags: dict, series_present: dict) -> tuple[str, ...]:
    """The sub-panes that are both toggled on and hold a series."""
    return tuple(
        name
        for name in SUB_PANE_ORDER
        if flags.get("show_%s" % name) and series_present.get(name)
    )


def layout(
    width: int, height: int, *, show_volume: bool, sub_panes: Sequence[str]
) -> dict:
    """Pane bounds down the widget, and the plotting width."""
    volume_height = VOLUME_STRIP_PX if show_volume else 0
    sub_total = SUB_PANE_PX * len(sub_panes)
    available = (
        height
        - HEADER_HEIGHT_PX
        - OHLC_ROW_HEIGHT_PX
        - TIME_AXIS_HEIGHT_PX
        - volume_height
        - sub_total
    )
    price_height = max(PRICE_PANE_PAINT_FLOOR_PX, available)
    ohlc_top = HEADER_HEIGHT_PX
    price_top = ohlc_top + OHLC_ROW_HEIGHT_PX
    price_bottom = price_top + price_height
    volume_top = price_bottom
    volume_bottom = volume_top + volume_height
    bounds = []
    edge = volume_bottom
    for name in sub_panes:
        bounds.append([name, edge, edge + SUB_PANE_PX])
        edge += SUB_PANE_PX
    return {
        "left_margin_px": LEFT_MARGIN_PX,
        "right_margin_px": RIGHT_MARGIN_PX,
        "chart_width_px": width - LEFT_MARGIN_PX - RIGHT_MARGIN_PX,
        "chart_right_px": width - RIGHT_MARGIN_PX,
        "width_px": width,
        "height_px": height,
        "centre_px": width / 2,
        "ohlc_top_px": ohlc_top,
        "price_top_px": price_top,
        "price_bottom_px": price_bottom,
        "price_height_px": price_height,
        "volume_top_px": volume_top,
        "volume_bottom_px": volume_bottom,
        "volume_height_px": volume_height,
        "sub_panes": bounds,
        "time_axis_top_px": edge,
    }


def candle_geometry(chart_width_px: float, candle_count: int) -> dict:
    """Column width, gap and body width for one visible candle."""
    column = max(CANDLE_WIDTH_FLOOR_PX, chart_width_px / candle_count)
    gap = max(CANDLE_GAP_FLOOR_PX, column * CANDLE_GAP_RATIO)
    return {
        "column_px": column,
        "gap_px": gap,
        "body_px": max(CANDLE_BODY_FLOOR_PX, column - gap),
    }


def price_range(
    candles: Sequence[CandleLike], y_zoom_pct: float = Y_ZOOM_DEFAULT
) -> dict:
    """Low, high and span of the price axis over the visible candles.

    A flat series pads from one percent of the high, so the final span is
    twice that padding rather than the one percent itself.
    """
    high = max(one.high for one in candles)
    low = min(one.low for one in candles)
    span = high - low
    if span == 0:
        span = high * FLAT_RANGE_RATIO or FLAT_RANGE_FALLBACK
    pad = span * PRICE_PAD_RATIO * y_zoom_pct
    high += pad
    low -= pad
    return {"low": low, "high": high, "span": high - low, "pad": pad}


def price_to_y(
    price: float,
    price_top_px: float,
    price_height_px: float,
    low: float,
    span: float,
) -> float:
    """Where a price sits down the price pane."""
    return price_top_px + price_height_px * (1.0 - (price - low) / span)


def index_to_x(index: int, left_margin_px: float, column_px: float) -> float:
    """Where a visible candle's column starts across the pane."""
    return left_margin_px + index * column_px


def y_to_price(
    y: float,
    price_top_px: float,
    price_height_px: float,
    low: float,
    span: float,
) -> float:
    """The price under a pixel row, which the crosshair badge reads."""
    return low + span * (1 - (y - price_top_px) / price_height_px)


def price_grid(low: float, high: float, target_ticks: int = GRID_TARGET_TICKS) -> dict:
    """The tick step and every tick price across the price axis."""
    step = nice_step(high - low, target_ticks)
    ticks = []
    if step > 0:
        first = math.ceil(low / step) * step
        tick = first
        while tick <= high + step * GRID_TICK_TOLERANCE:
            ticks.append(
                {
                    "price": tick,
                    "label": fmt_price(tick),
                    "major": round((tick - first) / step) % MAJOR_EVERY == 0,
                }
            )
            tick += step
    return {"step": step, "ticks": ticks}


def gmt_label(timestamp: float, pattern: str) -> str:
    """A UTC label for a candle time; empty when the time cannot be read."""
    try:
        return time.strftime(pattern, time.gmtime(timestamp))
    except (ValueError, OverflowError, OSError, TypeError):
        return ""


def time_ticks(candles: Sequence[CandleLike]) -> dict:
    """Time-axis tick indexes and their labels over the visible candles."""
    count = len(candles)
    if count < PAIR_MINIMUM:
        return {"stride": 0, "use_date": False, "ticks": []}
    stride = max(1, count // TIME_TICK_TARGET)
    span_s = max(1, candles[-1].time - candles[0].time)
    use_date = span_s > DAY_SECONDS
    pattern = TIME_LABEL_DATE if use_date else TIME_LABEL_CLOCK
    ticks = [
        {"index": index, "label": gmt_label(candles[index].time, pattern)}
        for index in range(0, count, stride)
    ]
    return {"stride": stride, "use_date": use_date, "ticks": ticks}


def heikin_ashi(candles: Sequence[CandleLike]) -> list[tuple]:
    """Fold raw candles into Heikin-Ashi bodies.

    Fewer than two candles pass through as raw open, high, low, close and
    volume, which is what the chart draws for a one-point series.
    """
    if len(candles) < PAIR_MINIMUM:
        return [(one.open, one.high, one.low, one.close, one.volume) for one in candles]
    bodies = []
    prev_open = candles[0].open
    prev_close = candles[0].close
    for index, one in enumerate(candles):
        if index == 0:
            ha_open = (one.open + one.close) / 2
        else:
            ha_open = (prev_open + prev_close) / 2
        ha_close = (one.open + one.high + one.low + one.close) / 4
        bodies.append(
            (
                ha_open,
                max(one.high, ha_open, ha_close),
                min(one.low, ha_open, ha_close),
                ha_close,
                one.volume,
            )
        )
        prev_open = ha_open
        prev_close = ha_close
    return bodies


def candle_colors(*, is_up: bool) -> dict:
    """Fill, border and wick colours for one candle body."""
    return {
        "fill": UP_FILL if is_up else DOWN_FILL,
        "border": UP_BORDER if is_up else DOWN_BORDER,
        "wick": UP_WICK if is_up else DOWN_WICK,
    }


def volume_colors(*, is_up: bool) -> dict:
    """Fill and border colours for one volume bar."""
    return {
        "fill": VOL_UP if is_up else VOL_DOWN,
        "border": VOL_UP_BORDER if is_up else VOL_DOWN_BORDER,
    }


def volume_bar_height(
    volume: float, top_volume: float, strip_height_px: float
) -> float:
    """How tall one volume bar stands in the strip."""
    return (volume / top_volume) * strip_height_px if volume > 0 else 0


def max_volume(candles: Sequence[CandleLike]) -> float:
    """The tallest volume in the window; one when every volume is zero."""
    return max((one.volume for one in candles), default=1) or 1


def marker_color(label: str, *, is_buy: bool) -> Color:
    """The colour one trade marker paints, by role then by side."""
    return MARKER_TYPE_COLORS.get(
        label, MARKER_DEFAULT_BUY if is_buy else MARKER_DEFAULT_SELL
    )


def position_status(*, filled: bool, is_invisible: bool) -> str:
    """The word on a position's right-axis label."""
    if filled:
        return POSITION_STATUS_FILLED
    if is_invisible:
        return POSITION_STATUS_TRACKED
    return POSITION_STATUS_ON_BOOK


def position_label(side: str, level: int, *, filled: bool, is_invisible: bool) -> str:
    """A position's right-axis label: side letter, level, then status."""
    letter = "B" if side == SIDE_BUY else "S"
    return "%s%s%s" % (
        letter,
        level,
        position_status(filled=filled, is_invisible=is_invisible),
    )


def macd_scale(rows: Sequence) -> dict | None:
    """Low and high of the MACD pane, padded by a tenth of its extreme."""
    values = []
    for row in rows:
        if row is None:
            continue
        values.extend([row[0], row[1], row[2]])
    if not values:
        return None
    low, high = min(values), max(values)
    pad = max(abs(low), abs(high)) * MACD_PAD_RATIO or MACD_PAD_FLOOR
    return {"low": low - pad, "high": high + pad, "pad": pad}


def oscillator_y(
    value: float, top_px: float, bottom_px: float, low: float, high: float
) -> float:
    """Where one oscillator value sits inside its sub-pane."""
    span = (high - low) or OSCILLATOR_RANGE_FLOOR
    return bottom_px - ((value - low) / span) * (bottom_px - top_px)


def zoom_factor(wheel_delta: float) -> float:
    """Tighter on a wheel push away, wider on a pull back."""
    return ZOOM_IN_FACTOR if wheel_delta > 0 else ZOOM_OUT_FACTOR


def clamp_y_zoom(value: float) -> float:
    """Hold the vertical zoom inside its band."""
    return max(Y_ZOOM_MIN, min(Y_ZOOM_MAX, value))


def zoom_window(
    wheel_delta: float,
    cursor_x: float,
    width_px: int,
    candle_count: int,
    visible_start: int | None,
    visible_count: int | None,
) -> dict | None:
    """The window after one wheel step, anchored on the candle under the
    cursor. None when the step changes nothing."""
    current_count = effective_visible_count(visible_count, candle_count)
    current_start = effective_visible_start(visible_start, candle_count)
    new_count = max(
        MIN_VISIBLE_CANDLES,
        min(candle_count, int(current_count * zoom_factor(wheel_delta))),
    )
    if new_count == current_count:
        return None
    chart_width = max(1, width_px - LEFT_MARGIN_PX - RIGHT_MARGIN_PX)
    fraction = max(0.0, min(1.0, (cursor_x - LEFT_MARGIN_PX) / chart_width))
    anchor = current_start + fraction * current_count
    start = int(anchor - fraction * new_count)
    return {"start": max(0, min(candle_count - new_count, start)), "count": new_count}


def pan_start(
    drag_start_x: float,
    mouse_x: float,
    drag_start_visible_start: int | None,
    width_px: int,
    candle_count: int,
    count: int,
) -> int | None:
    """Where the window starts after a drag of that many pixels."""
    chart_width = max(1, width_px - LEFT_MARGIN_PX - RIGHT_MARGIN_PX)
    if count <= 0:
        return None
    per_candle = chart_width / count
    moved = int((drag_start_x - mouse_x) / max(per_candle, PAN_PIXELS_PER_CANDLE_FLOOR))
    return max(0, min(candle_count - count, (drag_start_visible_start or 0) + moved))


def resize_height(start_height_px: int | None, start_y: int, mouse_y: int) -> int:
    """The widget height a grip drag asks for, never under the floor."""
    return max(
        MINIMUM_HEIGHT_PX, (start_height_px or MINIMUM_HEIGHT_PX) + (mouse_y - start_y)
    )


def in_grip(mouse_y: int, height_px: int) -> bool:
    """Whether a pointer row sits in the bottom resize strip."""
    return mouse_y >= height_px - RESIZE_GRIP_PX


def header_parts(
    timeframe: str,
    source_label: str,
    candle_count: int,
    invisible_count: int,
    on_book_count: int,
) -> list[str]:
    """The pieces of the header's information line, in order."""
    parts = [timeframe]
    if source_label:
        parts.append(source_label)
    if candle_count:
        parts.append(HEADER_COUNT_FORMAT.format(count=candle_count))
    if invisible_count or on_book_count:
        held = []
        if invisible_count:
            held.append(HEADER_INVISIBLE_FORMAT.format(count=invisible_count))
        if on_book_count:
            held.append(HEADER_ON_BOOK_FORMAT.format(count=on_book_count))
        parts.append(HEADER_POSITION_JOIN.join(held))
    return parts


def ohlc_row(candle: CandleLike) -> list[list]:
    """The OHLC row's label, value and colour for the latest candle."""
    is_up = candle.close >= candle.open
    accent = UP_FILL if is_up else DOWN_FILL
    change = candle.close - candle.open
    return [
        ["O", fmt_price(candle.open), TEXT_LIGHT],
        ["H", fmt_price(candle.high), TEXT_LIGHT],
        ["L", fmt_price(candle.low), TEXT_LIGHT],
        ["C", fmt_price(candle.close), accent],
        ["", fmt_change(change), accent],
        ["", "(%s)" % fmt_change_pct(change_pct(candle.open, candle.close)), accent],
        ["VOL", fmt_ohlc_volume(candle.volume), TEXT_DIM],
    ]


def tooltip_rows(candle: CandleLike) -> list[list]:
    """The hover tooltip's label, value and colour rows."""
    is_up = candle.close >= candle.open
    accent = UP_FILL if is_up else DOWN_FILL
    change = candle.close - candle.open
    return [
        ["O", fmt_price(candle.open), TEXT_LIGHT],
        ["H", fmt_price(candle.high), TEXT_LIGHT],
        ["L", fmt_price(candle.low), TEXT_LIGHT],
        ["C", fmt_price(candle.close), accent],
        [
            "Δ",
            "%s (%s)"
            % (
                fmt_change(change),
                fmt_change_pct(change_pct(candle.open, candle.close)),
            ),
            accent,
        ],
        ["V", fmt_tooltip_volume(candle.volume), TEXT_DIM],
    ]


def tooltip_height(row_count: int) -> int:
    """How tall the hover tooltip stands for that many rows."""
    return TOOLTIP_LINE_HEIGHT_PX * row_count + TOOLTIP_PAD_PX * 2


def bullseye_envelope(band_price: float, tolerance: float) -> dict:
    """The upper and lower price of a bullseye ring around a band."""
    return {
        "upper": band_price * (1 + tolerance),
        "lower": band_price * (1 - tolerance),
    }


def ichimoku_shifted(rows: Sequence, candle_count: int) -> dict:
    """Span A and Span B pushed forward by the cloud's shift."""
    span_a = [None] * candle_count
    span_b = [None] * candle_count
    for index in range(candle_count - ICHIMOKU_SHIFT):
        row = rows[index] if index < len(rows) else None
        if row is None:
            continue
        if row[2] is not None:
            span_a[index + ICHIMOKU_SHIFT] = row[2]
        if row[3] is not None:
            span_b[index + ICHIMOKU_SHIFT] = row[3]
    return {"span_a": span_a, "span_b": span_b}


def kumo_segments(span_a: Sequence, span_b: Sequence) -> list[dict]:
    """Contiguous runs where both spans exist, each with its polarity.

    A gap ends a run. A crossover ends a run and starts the next at the
    same index, so the two runs meet rather than leaving a notch.
    """
    segments: list[dict] = []
    points: list[int] = []
    bullish: bool | None = None
    for index in range(len(span_a)):
        first, second = span_a[index], span_b[index]
        if first is None or second is None:
            if points:
                segments.append({"indexes": points, "bullish": bullish})
            points = []
            bullish = None
            continue
        now_bullish = first > second
        if bullish is not None and now_bullish != bullish:
            points.append(index)
            segments.append({"indexes": points, "bullish": bullish})
            points = [index]
        else:
            points.append(index)
        bullish = now_bullish
    if points:
        segments.append({"indexes": points, "bullish": bullish})
    return segments


def slingshot_bands(closes: Sequence[float]) -> list:
    """Close, upper, lower, middle and bandwidth per candle, or None."""
    rows: list[tuple[float, float, float, float, float] | None] = [None] * len(closes)
    for index in range(SLINGSHOT_BB_PERIOD - 1, len(closes)):
        window = closes[index - SLINGSHOT_BB_PERIOD + 1 : index + 1]
        middle_price = sum(window) / SLINGSHOT_BB_PERIOD
        if middle_price <= 0:
            continue
        variance = (
            sum((one - middle_price) ** 2 for one in window) / SLINGSHOT_BB_PERIOD
        )
        deviation = variance**0.5
        upper_price = middle_price + SLINGSHOT_BB_STD * deviation
        lower_price = middle_price - SLINGSHOT_BB_STD * deviation
        rows[index] = (
            closes[index],
            upper_price,
            lower_price,
            middle_price,
            (upper_price - lower_price) / middle_price,
        )
    return rows


def slingshot_fires(closes: Sequence[float]) -> list[dict]:
    """Every squeeze and snapback event, each with its index and polarity."""
    count = len(closes)
    if count < SLINGSHOT_BB_PERIOD + SLINGSHOT_SQUEEZE_LOOKBACK + 2:
        return []
    bands = slingshot_bands(closes)
    fires = []
    for index in range(SLINGSHOT_BB_PERIOD + SLINGSHOT_SQUEEZE_LOOKBACK, count):
        window = [
            one
            for one in bands[index - SLINGSHOT_SQUEEZE_LOOKBACK : index]
            if one is not None
        ]
        if len(window) < SLINGSHOT_SQUEEZE_LOOKBACK - SLINGSHOT_WINDOW_SLACK:
            continue
        average = sum(one[4] for one in window) / len(window)
        current, previous = bands[index], bands[index - 1]
        if current is None or previous is None:
            continue
        recent = [
            one
            for one in bands[index - (SLINGSHOT_RECENT_WINDOW - 1) : index + 1]
            if one is not None
        ]
        squeezed = sum(
            1 for one in recent if one[4] < average * SLINGSHOT_SQUEEZE_THRESHOLD
        )
        if (
            squeezed >= SLINGSHOT_SQUEEZED_MINIMUM
            and current[4] > previous[4] * SLINGSHOT_EXPANSION_RATIO
        ):
            fires.append(
                {"index": index, "kind": "squeeze", "bullish": current[0] > current[3]}
            )
            continue
        for back in range(
            max(SLINGSHOT_BB_PERIOD, index - SLINGSHOT_SNAPBACK_LOOKBACK), index
        ):
            past = bands[back]
            if past is None:
                continue
            past_close, past_upper, past_lower = past[0], past[1], past[2]
            bar_close, band_upper = current[0], current[1]
            band_lower, band_middle = current[2], current[3]
            if (
                past_close < past_lower
                and band_lower < bar_close < band_middle
                and bar_close > past_close
            ):
                fires.append({"index": index, "kind": "snapback", "bullish": True})
                break
            if (
                past_close > past_upper
                and band_middle < bar_close < band_upper
                and bar_close < past_close
            ):
                fires.append({"index": index, "kind": "snapback", "bullish": False})
                break
    return fires


class Candle:
    """One price bar the chart draws."""

    def __init__(
        self,
        time_s: int,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        volume: float = 0.0,
    ) -> None:
        """Hold one bar's time, its four prices and its volume."""
        self.time = time_s
        self.open = open_price
        self.high = high_price
        self.low = low_price
        self.close = close_price
        self.volume = volume


class TradeMarker:
    """One past trade the chart pins to a candle."""

    def __init__(self, time_s: int, side: str, price: float, label: str = "") -> None:
        """Hold one past trade's time, side, price and role."""
        self.time = time_s
        self.side = side
        self.price = price
        self.label = label


class PositionMarker:
    """One open position the chart draws on the price axis."""

    def __init__(
        self,
        price: float,
        side: str,
        visibility: str,
        level: int = 0,
        *,
        filled: bool = False,
        asset_held: float = 0.0,
    ) -> None:
        """Hold one open position's price, side, visibility and level."""
        self.price = price
        self.side = side
        self.visibility = visibility
        self.level = level
        self.filled = filled
        self.asset_held = asset_held


class GridLine:
    """One stored grid level. The chart keeps these and paints none."""

    def __init__(self, price: float, side: str, label: str = "") -> None:
        """Hold one grid level's price, side and label."""
        self.price = price
        self.side = side
        self.label = label


class Refused(Exception):
    """A step the chart could not take."""


class ChartModel:
    """The chart's state, and the steps the widget takes on it."""

    def __init__(self, symbol: str = "") -> None:
        """Start a chart holding no candles and fitting every one it gets."""
        self.symbol = symbol
        self.accessible_name = ACCESSIBLE_NAME
        self.candles: list = []
        self.markers: list = []
        self.positions: list = []
        self.grid_lines: list = []
        self.tranche_floors: list = []
        self.timeframe = DEFAULT_TIMEFRAME
        self.status_text = DEFAULT_STATUS_TEXT
        self.source_label = ""
        self.error_text = ""
        self.tb_anchor_price: float | None = None
        self.tb_ceiling_price: float | None = None
        self.fire_armed_state: dict = {
            "scrum_armed": False,
            "fold_armed": False,
            "scrum_blockers": [],
            "fold_blockers": [],
        }
        self.flags = {"show_%s" % k: v for k, v in INDICATOR_DEFAULTS.items()}
        self.bb_data: list = []
        self.vortex_data: list = []
        self.macd_data: list = []
        self.stochrsi_data: list = []
        self.ichimoku_data: list = []
        self.visible_start: int | None = None
        self.visible_count: int | None = None
        self.y_zoom_pct = Y_ZOOM_DEFAULT
        self.minimum_height_px = MINIMUM_HEIGHT_PX
        self.height_override: int | None = None
        self.steps: list = []

    def _record(self, name: str) -> None:
        self.steps.append([len(self.steps), name])

    def set_candles(self, candles: Sequence[CandleLike]) -> None:
        """Replace the series and refresh the status line."""
        self._record("set_candles")
        self.candles = list(candles)
        self.error_text = ""
        if self.candles:
            self.status_text = HEADER_COUNT_FORMAT.format(count=len(self.candles))

    def set_indicator_series(
        self,
        bb: Sequence | None = None,
        vortex: Sequence | None = None,
        macd: Sequence | None = None,
        stochrsi: Sequence | None = None,
        ichimoku: Sequence | None = None,
    ) -> None:
        """Take the series the engine computed for the overlays."""
        self.bb_data = list(bb or [])
        self.vortex_data = list(vortex or [])
        self.macd_data = list(macd or [])
        self.stochrsi_data = list(stochrsi or [])
        self.ichimoku_data = list(ichimoku or [])

    def set_source_label(self, source: str) -> None:
        """Name the feed the candles came from."""
        self._record("set_source_label")
        self.source_label = source

    def set_error(self, message: str) -> None:
        """Show a message in place of the chart."""
        self._record("set_error")
        self.error_text = message

    def set_positions(self, positions: Sequence) -> None:
        """Replace the open positions drawn on the price axis."""
        self._record("set_positions")
        self.positions = list(positions)

    def set_grid_lines(self, lines: Sequence) -> None:
        """Store the grid levels. Nothing paints them."""
        self._record("set_grid_lines")
        self.grid_lines = list(lines)

    def set_tranche_floors(self, floors: Sequence) -> None:
        """Replace the tranche minimum-target lines."""
        self._record("set_tranche_floors")
        self.tranche_floors = list(floors)

    def set_target_balance_lines(
        self, anchor_price: float | None, ceiling_price: float | None
    ) -> None:
        """Place the Target Balance anchor and ceiling on the price axis."""
        self._record("set_target_balance_lines")
        self.tb_anchor_price = anchor_price
        self.tb_ceiling_price = ceiling_price

    def set_fire_armed_state(
        self,
        scrum_armed: bool,
        fold_armed: bool,
        scrum_blockers: Sequence | None = None,
        fold_blockers: Sequence | None = None,
    ) -> None:
        """Mirror whether auto-fire would fire now."""
        self._record("set_fire_armed_state")
        self.fire_armed_state = {
            "scrum_armed": bool(scrum_armed),
            "fold_armed": bool(fold_armed),
            "scrum_blockers": list(scrum_blockers or []),
            "fold_blockers": list(fold_blockers or []),
        }

    def set_timeframe(self, timeframe: str) -> None:
        """Change the timeframe the header reports."""
        self._record("set_timeframe")
        self.timeframe = timeframe

    def set_markers(self, trades: Sequence[dict]) -> None:
        """Replace the trade markers, skipping any without time and price."""
        self._record("set_markers")
        self.markers = []
        for trade in trades:
            try:
                stamp = int(trade.get("ts", trade.get("time", 0)) or 0)
                price = float(trade.get("price", 0) or 0)
                if stamp <= 0 or price <= 0:
                    continue
                self.markers.append(
                    TradeMarker(
                        time_s=stamp,
                        side=str(trade.get("side", MARKER_DEFAULT_SIDE)),
                        price=price,
                        label=str(
                            trade.get("role", trade.get("label", MARKER_DEFAULT_ROLE))
                        ),
                    )
                )
            except (TypeError, ValueError, KeyError):
                continue

    def toggle_indicator(self, name: str, on: bool) -> None:
        """Turn one overlay or sub-pane on or off."""
        self._record("toggle_indicator")
        if name not in INDICATOR_DEFAULTS:
            raise Refused(name)
        self.flags["show_%s" % name] = on
        self.apply_height()

    def apply_height(self) -> int:
        """Grow the widget height to hold every active sub-pane."""
        target = natural_height(
            show_volume=self.flags["show_volume"],
            sub_pane_count=len(self.sub_panes()),
        )
        if self.height_override is not None:
            target = max(target, self.height_override)
        self.minimum_height_px = target
        return target

    def sub_panes(self) -> tuple:
        """The sub-panes that are on and hold a series."""
        return active_sub_panes(
            self.flags,
            {
                "macd": bool(self.macd_data),
                "vortex": bool(self.vortex_data),
                "stochrsi": bool(self.stochrsi_data),
            },
        )

    def zoom(
        self,
        wheel_delta: float,
        cursor_x: float,
        width_px: int,
        *,
        control_held: bool = False,
    ) -> None:
        """Take one wheel step, vertical when control is held."""
        self._record("zoom")
        if not self.candles:
            return
        if control_held:
            self.y_zoom_pct = clamp_y_zoom(self.y_zoom_pct * zoom_factor(wheel_delta))
            return
        window = zoom_window(
            wheel_delta,
            cursor_x,
            width_px,
            len(self.candles),
            self.visible_start,
            self.visible_count,
        )
        if window is None:
            return
        self.visible_start = window["start"]
        self.visible_count = window["count"]

    def pan(
        self,
        drag_start_x: float,
        mouse_x: float,
        drag_start_visible_start: int | None,
        width_px: int,
    ) -> None:
        """Slide the visible window by a drag."""
        self._record("pan")
        start = pan_start(
            drag_start_x,
            mouse_x,
            drag_start_visible_start,
            width_px,
            len(self.candles),
            self.visible_count_now(),
        )
        if start is not None:
            self.visible_start = start

    def reset_view(self) -> None:
        """Return to fitting every candle."""
        self._record("reset_view")
        self.visible_start = None
        self.visible_count = None
        self.y_zoom_pct = Y_ZOOM_DEFAULT

    def visible_start_now(self) -> int:
        """Where the visible window starts right now."""
        return effective_visible_start(self.visible_start, len(self.candles))

    def visible_count_now(self) -> int:
        """How many candles the window shows right now."""
        return effective_visible_count(self.visible_count, len(self.candles))

    def visible_candles(self) -> list:
        """The candles inside the window, snapping back when it runs off."""
        start = self.visible_start_now()
        count = self.visible_count_now()
        window = self.candles[start : min(len(self.candles), start + count)]
        if not window:
            return list(self.candles)
        return window


def candle_row(
    index: int, body: tuple, panes: dict, axis: dict, geometry: dict, top_volume: float
) -> dict:
    """One candle's prices, colours and pixel boxes, ready to draw."""
    is_up = body[3] >= body[0]
    colors = candle_colors(is_up=is_up)
    volume_paint = volume_colors(is_up=is_up)
    left = index_to_x(index, LEFT_MARGIN_PX, geometry["column_px"])
    box = body_pixels(
        body[0],
        body[3],
        panes["price_top_px"],
        panes["price_height_px"],
        axis["low"],
        axis["span"],
    )
    wick = wick_pixels(
        body[1],
        body[2],
        panes["price_top_px"],
        panes["price_height_px"],
        axis["low"],
        axis["span"],
    )
    bar_height = volume_bar_height(body[4], top_volume, panes["volume_height_px"])
    return {
        "index": index,
        "open": body[0],
        "high": body[1],
        "low": body[2],
        "close": body[3],
        "volume": body[4],
        "up": is_up,
        "x_px": left,
        "colors": colors,
        "volume_colors": volume_paint,
        "volume_height_px": bar_height,
        "body_x_px": left + geometry["gap_px"] / 2,
        "body_y_px": box["y_px"],
        "body_width_px": geometry["body_px"],
        "body_height_px": box["height_px"],
        "wick_x_px": left + geometry["column_px"] / 2,
        "wick_y_px": wick["y_px"],
        "wick_height_px": wick["height_px"],
        "volume_y_px": panes["volume_bottom_px"] - bar_height,
        "colors_css": {name: css_color(one) for name, one in colors.items()},
        "volume_colors_css": {
            name: css_color(one) for name, one in volume_paint.items()
        },
    }


def grid_rows(ticks: Sequence[dict], panes: dict, axis: dict) -> list:
    """Each price tick with its row down the pane, and whether it lands on it."""
    rows = []
    for tick in ticks:
        y = price_to_y(
            tick["price"],
            panes["price_top_px"],
            panes["price_height_px"],
            axis["low"],
            axis["span"],
        )
        rows.append(
            dict(
                tick,
                y_px=y,
                on_pane=panes["price_top_px"] <= int(y) <= panes["price_bottom_px"],
                color_css=css_color(GRID_MAJOR if tick["major"] else GRID_MINOR),
            )
        )
    return rows


def time_rows(ticks: Sequence[dict], panes: dict, geometry: dict) -> list:
    """Each time tick with its column across the pane, and whether it lands."""
    rows = []
    for tick in ticks:
        x = (
            index_to_x(tick["index"], panes["left_margin_px"], geometry["column_px"])
            + geometry["column_px"] / 2
        )
        rows.append(
            dict(
                tick,
                x_px=x,
                on_pane=panes["left_margin_px"] <= int(x) <= panes["chart_right_px"],
            )
        )
    return rows


def price_line_row(
    kind: str,
    price: float,
    label: str,
    color: Color,
    width_px: float,
    style: str,
    panes: dict,
    axis: dict,
) -> dict:
    """One horizontal price line, with its row down the pane."""
    y = price_to_y(
        price,
        panes["price_top_px"],
        panes["price_height_px"],
        axis["low"],
        axis["span"],
    )
    return {
        "kind": kind,
        "price": price,
        "label": label,
        "y_px": y,
        "color_css": css_color(color),
        "width_px": width_px,
        "style": style,
        "on_pane": panes["price_top_px"] <= y <= panes["price_bottom_px"],
    }


def target_balance_rows(model: ChartModel, panes: dict, axis: dict) -> list:
    """The Target Balance anchor and ceiling lines the chart draws."""
    rows = []
    wanted = (
        (LINE_KIND_TB_ANCHOR, model.tb_anchor_price, TB_ANCHOR_LABEL, TB_ANCHOR_COLOR),
        (
            LINE_KIND_TB_CEILING,
            model.tb_ceiling_price,
            TB_CEILING_LABEL,
            TB_CEILING_COLOR,
        ),
    )
    for kind, price, label, color in wanted:
        if price is None:
            continue
        rows.append(
            price_line_row(
                kind,
                price,
                TB_LABEL_FORMAT.format(label=label, price=fmt_price(price)),
                color,
                TB_LINE_WIDTH_PX,
                PRICE_LINE_STYLE,
                panes,
                axis,
            )
        )
    return rows


def tranche_floor_rows(model: ChartModel, panes: dict, axis: dict) -> list:
    """The tranche minimum-target lines the chart draws."""
    rows = []
    for floor in model.tranche_floors:
        price, label = floor[0], floor[1]
        rows.append(
            price_line_row(
                LINE_KIND_TRANCHE_FLOOR,
                price,
                TRANCHE_FLOOR_LABEL_FORMAT.format(label=label),
                TRANCHE_FLOOR_COLOR,
                GRID_LINE_WIDTH_PX,
                PRICE_LINE_STYLE,
                panes,
                axis,
            )
        )
    return rows


def position_rows(model: ChartModel, panes: dict, axis: dict) -> list:
    """The open-position lines the chart draws on the price axis."""
    rows = []
    for one in model.positions:
        invisible = one.visibility == POSITION_INVISIBLE_KEY
        base = BUY_POS_COLOR if one.side == SIDE_BUY else SELL_POS_COLOR
        row = price_line_row(
            LINE_KIND_POSITION,
            one.price,
            position_label(
                one.side, one.level, filled=one.filled, is_invisible=invisible
            ),
            with_alpha(base, POSITION_LINE_ALPHA),
            GRID_LINE_WIDTH_PX,
            POSITION_LINE_STYLE,
            panes,
            axis,
        )
        row["label_color_css"] = css_color(with_alpha(base, POSITION_LABEL_ALPHA))
        row["icon_color_css"] = css_color(INVISIBLE_ICON if invisible else VISIBLE_ICON)
        rows.append(row)
    return rows


def empty_view(model: ChartModel) -> dict:
    """What the chart shows with no candles: one centred line and a header."""
    return {
        "message": model.error_text or model.status_text,
        "color": TEXT_DIM,
        "color_css": css_color(TEXT_DIM),
        "centered": True,
    }


def build_view_model(model: ChartModel, width: int = 0, height: int = 0) -> dict:
    """Return every value the chart works out before it paints."""
    invisible = sum(
        1 for one in model.positions if one.visibility == POSITION_INVISIBLE_KEY
    )
    parts = header_parts(
        model.timeframe,
        model.source_label,
        len(model.candles),
        invisible,
        len(model.positions) - invisible,
    )
    payload = {
        "accessible_name": model.accessible_name,
        "symbol": model.symbol,
        "timeframe": model.timeframe,
        "timeframes": list(TIMEFRAMES),
        "status_text": model.status_text,
        "source_label": model.source_label,
        "error_text": model.error_text,
        "candle_count": len(model.candles),
        "flags": dict(model.flags),
        "sub_panes": list(model.sub_panes()),
        "natural_height_px": natural_height(
            show_volume=model.flags["show_volume"],
            sub_pane_count=len(model.sub_panes()),
        ),
        "minimum_height_px": model.minimum_height_px,
        "resize_grip_px": RESIZE_GRIP_PX,
        "parent_height_pad_px": PARENT_HEIGHT_PAD_PX,
        "visible_start": model.visible_start_now(),
        "visible_count": model.visible_count_now(),
        "y_zoom_pct": model.y_zoom_pct,
        "header_parts": parts,
        "header_text": HEADER_SEPARATOR.join(parts),
        "positions": [
            {
                "price": one.price,
                "side": one.side,
                "invisible": one.visibility == POSITION_INVISIBLE_KEY,
                "filled": one.filled,
                "label": position_label(
                    one.side,
                    one.level,
                    filled=one.filled,
                    is_invisible=one.visibility == POSITION_INVISIBLE_KEY,
                ),
                "line_color": BUY_POS_COLOR if one.side == SIDE_BUY else SELL_POS_COLOR,
                "icon_color": (
                    INVISIBLE_ICON
                    if one.visibility == POSITION_INVISIBLE_KEY
                    else VISIBLE_ICON
                ),
                "line_color_css": css_color(
                    BUY_POS_COLOR if one.side == SIDE_BUY else SELL_POS_COLOR
                ),
                "icon_color_css": css_color(
                    INVISIBLE_ICON
                    if one.visibility == POSITION_INVISIBLE_KEY
                    else VISIBLE_ICON
                ),
            }
            for one in model.positions
        ],
        "markers": [
            {
                "time": one.time,
                "side": one.side,
                "price": one.price,
                "label": one.label,
                "color": marker_color(one.label, is_buy=one.side == SIDE_BUY),
                "color_css": css_color(
                    marker_color(one.label, is_buy=one.side == SIDE_BUY)
                ),
            }
            for one in model.markers
        ],
        "tranche_floors": [list(one) for one in model.tranche_floors],
        "grid_lines_held": len(model.grid_lines),
        "target_balance": {
            "anchor_price": model.tb_anchor_price,
            "ceiling_price": model.tb_ceiling_price,
            "anchor_label": TB_ANCHOR_LABEL,
            "ceiling_label": TB_CEILING_LABEL,
        },
        "fire_armed_state": dict(model.fire_armed_state),
        "skin": dict(SKIN),
        "skin_css": skin_css(),
        "background_css": background_css(),
        "metrics": dict(METRICS),
        "actions": dict(ACTIONS),
        "signals": list(SIGNALS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "threads": list(THREADS),
        "steps": [list(one) for one in model.steps],
        "empty": None,
        "panes": None,
        "price_axis": None,
        "candles": None,
        "time_axis": None,
        "ohlc_row": None,
        "ohlc_row_css": None,
        "price_lines": None,
    }
    if not model.candles:
        payload["empty"] = empty_view(model)
        return payload
    payload["ohlc_row"] = ohlc_row(model.candles[-1])
    payload["ohlc_row_css"] = [
        [label, value, css_color(tone)] for label, value, tone in payload["ohlc_row"]
    ]
    if width <= 0 or height <= 0:
        return payload
    panes = layout(
        width,
        height,
        show_volume=model.flags["show_volume"],
        sub_panes=model.sub_panes(),
    )
    payload["panes"] = panes
    if panes["chart_width_px"] <= 0:
        return payload
    window = model.visible_candles()
    axis = price_range(window, model.y_zoom_pct)
    geometry = candle_geometry(panes["chart_width_px"], len(window))
    grid = price_grid(axis["low"], axis["high"])
    grid["ticks"] = grid_rows(grid["ticks"], panes, axis)
    last_price = model.candles[-1].close
    payload["price_axis"] = {
        "low": axis["low"],
        "high": axis["high"],
        "span": axis["span"],
        "pad": axis["pad"],
        "grid": grid,
        "last_price": last_price,
        "last_price_label": fmt_price(last_price),
    }
    payload["price_lines"] = (
        [
            price_line_row(
                LINE_KIND_LAST_PRICE,
                last_price,
                fmt_price(last_price),
                PRICE_LINE_COLOR,
                PRICE_LINE_WIDTH_PX,
                PRICE_LINE_STYLE,
                panes,
                axis,
            )
        ]
        + target_balance_rows(model, panes, axis)
        + tranche_floor_rows(model, panes, axis)
        + position_rows(model, panes, axis)
    )
    top_volume = max_volume(window)
    payload["candles"] = {
        "geometry": geometry,
        "max_volume": top_volume,
        "volume_label": fmt_volume(top_volume),
        "volume_axis_label": VOLUME_AXIS_FORMAT.format(value=fmt_volume(top_volume)),
        "bodies": [
            candle_row(index, body, panes, axis, geometry, top_volume)
            for index, body in enumerate(heikin_ashi(window))
        ],
    }
    time_axis = time_ticks(window)
    time_axis["ticks"] = time_rows(time_axis["ticks"], panes, geometry)
    payload["time_axis"] = time_axis
    return payload


PANE_MODEL = ChartModel()


def view_model(params: dict) -> dict:
    """Bridge handler for ``native_chart.state``.

    Reads ``reset``, ``symbol``, ``timeframe``, ``candles``, ``positions``,
    ``markers``, ``steps``, ``width`` and ``height`` from the request
    parameters. The chart's state persists between calls because the widget
    does; ``reset`` is what a fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = ChartModel(params.get("symbol", ""))
    elif params.get("symbol") is not None:
        PANE_MODEL.symbol = params["symbol"]
    if params.get("timeframe") is not None:
        PANE_MODEL.set_timeframe(params["timeframe"])
    candles = params.get("candles")
    if candles is not None:
        PANE_MODEL.set_candles(
            [
                Candle(
                    one["time"],
                    one["open"],
                    one["high"],
                    one["low"],
                    one["close"],
                    one.get("volume", 0.0),
                )
                for one in candles
            ]
        )
    positions = params.get("positions")
    if positions is not None:
        PANE_MODEL.set_positions(
            [
                PositionMarker(
                    one["price"],
                    one["side"],
                    one["visibility"],
                    one.get("level", 0),
                    filled=one.get("filled", False),
                    asset_held=one.get("asset_held", 0.0),
                )
                for one in positions
            ]
        )
    markers = params.get("markers")
    if markers is not None:
        PANE_MODEL.set_markers(markers)
    for step in params.get("steps", []):
        getattr(PANE_MODEL, step["name"])(*step.get("args", []))
    return build_view_model(PANE_MODEL, params.get("width", 0), params.get("height", 0))
