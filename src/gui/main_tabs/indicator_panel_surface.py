"""indicator_panel_surface.py -- the Indicator Voting Panel as plain data.

``IndicatorTableModel`` turns one ``multi_tf_summary`` into the rows and
cells a table draws, cell text and cell colours included.
``ConfidenceBarsModel`` holds the bar targets and steps the animation one
frame per call, so a caller drives frames rather than waiting on a clock.
``IndicatorPanelModel`` holds the header, the selector and the empty-state
text, and ``build_payload`` renders it.

``src.core.desktop_bridge`` registers ``view_model`` under ``METHOD``, which
is how the Electron renderer reaches this module.
``market_inspector_surface`` imports it as ``ivp``. Every value below is
written out here rather than read from ``src.gui.indicator_panel``. Nothing
here imports Qt.

``RAW_VALUE_INDICATORS`` render a raw value; every other indicator renders a
percentage. No indicator arithmetic happens here -- the voting engine has
already produced direction and confidence.
"""

from __future__ import annotations

from typing import Any, Optional

from ...exchange.timeframes import ALL_TIMEFRAMES

METHOD = "indicator_panel.state"

LOGGER_NAME = "acervator.gui"

PANEL_KIND = "IndicatorVotingPanel"
PANEL_BASE_KIND = "QWidget"
BARS_KIND = "ConfidenceBarsWidget"
BARS_BASE_KIND = "QWidget"
DOT_KIND = "_IVPPrivacyDot"
DOT_BASE_KIND = "QPushButton"
TABLE_KIND = "QTableWidget"
CELL_KIND = "QTableWidgetItem"

TITLE_TEXT = "Indicator Voting Panel"
BARS_ACCESSIBLE_NAME = "Indicator Confidence Bar Graph"
STALENESS_ACCESSIBLE_NAME = "TA Staleness Banner"
RATE_STRIP_ACCESSIBLE_NAME = "Currency Rate Strip"

# Qt's alpha channel is a 0-255 byte; CSS wants 0-1. A published byte
# is multiplied by ALPHA_UNIT on the way to a CSS colour.
ALPHA_SCALE = 255.0
ALPHA_UNIT = 1.0 / ALPHA_SCALE

#: A 0-1 fraction reaches CSS as a percentage of this.
PERCENT_SCALE = 100.0

CONTAINER = {
    "margins_px": [0, 0, 0, 0],
    "spacing_px": 2,
    "children": [
        "header",
        "staleness",
        "rate_strip",
        "row_a",
        "row_b",
        "locks",
    ],
}

HEADER = {
    "margins_px": [4, 2, 4, 2],
    "bot_label_text": "Bot:",
    "selector_minimum_width_px": 180,
}

TITLE_HEADING_PROPERTY = "heading"
LOCKS_MUTED_PROPERTY = "muted"

# -- the twelve indicator columns -------------------------------------

#: (key, short label, group) -- T=Trend, M=Momentum, S=Structure.
INDICATOR_COLS = [
    ("bollinger_bands", "BB", "S"),
    ("vortex", "VTX", "T"),
    ("macd", "MACD", "M"),
    ("stochastic_rsi", "SRsi", "M"),
    ("ichimoku", "Ichi", "T"),
    ("volume", "Vol", "S"),
    ("slingshot", "Sling", "S"),
    ("adx", "ADX", "T"),
    ("supertrend", "STrd", "T"),
    ("zscore", "ZSc", "M"),
    ("kaufman_er", "KER", "M"),
    ("rsi", "RSI", "M"),
]

ROW_A_INDICATOR_COLS = INDICATOR_COLS[:6]
ROW_B_INDICATOR_COLS = INDICATOR_COLS[6:]

TF_COLUMN_TITLE = "TF"
AGGREGATE_TITLES = ["Net", "Comp", "Conf"]
EMPTY_TITLE = ""

#: The ground both mini-panels and the pillars behind them are painted on.
PANEL_GROUND_RGB = (10, 10, 18)


#: The share of its column a pillar leaves as padding on each side.
PILLAR_PAD_FRACTION = 0.12

#: The alpha of the halo drawn behind a pillar body.
PILLAR_GLOW_ALPHA = 30

#: Columns in each mini-panel: TF, six indicators and AGGREGATE_TITLES.
PANEL_COLUMN_COUNT = 1 + len(ROW_A_INDICATOR_COLS) + len(AGGREGATE_TITLES)

#: Columns the row partition rules: TF and the six indicators.
RULED_COLUMNS = PANEL_COLUMN_COUNT - len(AGGREGATE_TITLES)

GROUP_COLORS = {
    "T": "#00AAFF",
    "M": "#FFAA00",
    "S": "#00FFAA",
}

DIR_SYMBOLS = {
    "BULLISH": "▲",
    "BEARISH": "▼",
    "NEUTRAL": "─",
}

DEFAULT_DIRECTION = "NEUTRAL"
DEFAULT_SYMBOL = DIR_SYMBOLS[DEFAULT_DIRECTION]

#: Indicators whose cell shows a raw reading rather than a percentage.
RAW_VALUE_INDICATORS = ("adx", "zscore", "kaufman_er")

ADX_RANGING_FORMAT = "Rng {value:.0f}"
ADX_TRENDING_FORMAT = "{symbol} {value:.0f}"
ZSCORE_FORMAT = "{symbol} {value:+.1f}"
KAUFMAN_FORMAT = "{symbol} {value:.2f}"
CONFIDENCE_FORMAT = "{symbol} {value:.0%}"

NET_FORMAT = "{value:+.2f}"
COMP_FORMAT = "{value:+.2f}"
COMP_ABSENT_TEXT = "—"
COMP_SKIPPED_FORMAT = (
    "Left out of Comp, at or below this bot's TA Timeframe: {timeframes}"
)
CONF_FORMAT = "{bar} {value:.0%}"

CONF_BAR_FILLED = "█"
CONF_BAR_EMPTY = "░"
CONF_BAR_CELLS = 10

# -- cell colours ------------------------------------------------------

BULLISH_TEXT_COLOR = "#00ff88"
BEARISH_TEXT_COLOR = "#ff3366"
NEUTRAL_TEXT_COLOR = "#888888"
ABSENT_TEXT_COLOR = "#666666"
WARNING_TEXT_COLOR = "#ffaa00"

#: Cell tints, as Qt writes them: (red, green, blue) with the alpha byte
#: supplied per cell. The bearish tint's blue is 100 while the bearish
#: text is #ff3366, whose blue is 102.
BULLISH_CELL_RGB = (0, 200, 100)
BEARISH_CELL_RGB = (255, 51, 100)
NEUTRAL_CELL_RGB = (60, 60, 80)

NEUTRAL_CELL_ALPHA = 12
CELL_ALPHA_SPAN = 50
CELL_ALPHA_FLOOR = 5

CONF_STRONG_LIMIT = 0.6
CONF_FAIR_LIMIT = 0.3

# -- the confidence bar graph -----------------------------------------

BAR_COLORS = {
    "BULLISH": (0, 255, 136),
    "BEARISH": (255, 51, 102),
    "NEUTRAL": (80, 80, 120),
}

BARS_MINIMUM_HEIGHT_PX = 100
BARS_FRAME_INTERVAL_MS = 16
BARS_LERP_FACTOR = 0.12
BARS_SETTLE_DELTA = 0.002
BARS_EMPTY_TEXT = "Awaiting TA signals..."

BARS_MARGIN_TOP_PX = 8
BARS_MARGIN_BOTTOM_PX = 22
BARS_MARGIN_LEFT_PX = 10
BARS_MARGIN_RIGHT_PX = 10
BARS_GAP_PX = 6
BARS_FALLBACK_MIN_WIDTH_PX = 12
BARS_MIN_WIDTH_PX = 2
BARS_MIN_HEIGHT_PX = 2
BARS_COLUMN_PAD_FRACTION = 0.12
BARS_COLUMN_MIN_PAD_PX = 2
BARS_GRID_FRACTIONS = [0.25, 0.50, 0.75, 1.00]
BARS_SHINE_LIMIT_PX = 20
BARS_SHINE_FRACTION = 0.3
BARS_SHINE_MIN_HEIGHT_PX = 8
BARS_ARROW_MIN_HEIGHT_PX = 24
BARS_GLOW_INSET_PX = 3
BARS_GLOW_RADIUS_PX = 6
BARS_BODY_RADIUS_PX = 3
BARS_SHINE_RADIUS_PX = 2
BARS_LABEL_HEIGHT_PX = 16
BARS_LABEL_OFFSET_PX = 4
BARS_ARROW_HEIGHT_PX = 20

BARS_BACKGROUND_RGB = (10, 10, 18)
BARS_EMPTY_TEXT_RGB = (60, 60, 80)
BARS_GRID_RGB = (25, 25, 40)
BARS_LABEL_RGB = (160, 160, 190)
BARS_BASELINE_RGB = (40, 40, 60)
BARS_SHINE_RGB = (255, 255, 255)

BARS_GLOW_ALPHA = 30
BARS_GRADIENT_ALPHAS = [220, 160, 60]
BARS_GRADIENT_STOPS = [0.0, 0.6, 1.0]
BARS_OUTLINE_ALPHA = 180
BARS_SHINE_START_ALPHA = 40
BARS_SHINE_END_ALPHA = 0
BARS_ARROW_ALPHA = 150

BARS_EMPTY_FONT = ("Segoe UI", 9)
BARS_GRID_FONT = ("Consolas", 7)
BARS_LABEL_FONT = ("Consolas", 8)
BARS_ARROW_FONT = ("Segoe UI", 12)

# -- the table ---------------------------------------------------------

ROW_HEIGHT_PX = 28
TABLE_SLACK_ROWS = 2
TABLE_SLACK_PX = 4
HEADER_MIN_PAD_PX = 2
FONT_POINT_DROP = 1
FONT_POINT_FLOOR = 6
ALTERNATING_ROW_COLORS = False
VERTICAL_HEADER_VISIBLE = False
SELECTION_BEHAVIOR = "SelectRows"
EDIT_TRIGGERS = "NoEditTriggers"
HORIZONTAL_SCROLL_POLICY = "ScrollBarAlwaysOff"
VERTICAL_SCROLL_POLICY = "ScrollBarAlwaysOff"
RESIZE_MODE = "Stretch"
STRETCH_LAST_SECTION = False
CELL_ALIGNMENT = "AlignCenter"
TABLE_SIZE_POLICY = ["Expanding", "Fixed"]
BARS_SIZE_POLICY = ["Expanding", "Expanding"]
PANEL_SIZE_POLICY = ["Expanding", "Expanding"]

#: Timeframes in the order the table lists them; anything else sorts last.
TIMEFRAME_ORDER = list(ALL_TIMEFRAMES)
UNKNOWN_TIMEFRAME_RANK = 99

BOT_SELECTED_TOPIC = "indicator.bot_selected"
BUS_TOPICS = [BOT_SELECTED_TOPIC]

# -- the bot selector --------------------------------------------------

SELECTOR_PLACEHOLDER_TEXT = "(select a bot)"
SELECTOR_PLACEHOLDER_VALUE = ""
SELECTOR_EMPTY_TEXT = "(no accumulation bots)"
SELECTOR_ITEM_FORMAT = "{symbol} [{short_id}] ({state})"
SELECTOR_ID_PREFIX_LEN = 8
ACCUMULATION_MODES = ("accumulation", "scrumming")
DEFAULT_SYMBOL_TEXT = "???"
DEFAULT_STATE_TEXT = "idle"
DEFAULT_TA_TIMEFRAME = "1h"

PRIVACY_FIELD_ID = "ivp.bot_selector"
PRIVACY_MASK_TEXT = "****"
PRIVACY_DOT_SIZE_PX = 12
PRIVACY_DOT_RADIUS_PX = PRIVACY_DOT_SIZE_PX // 2
PRIVACY_BORDER_WIDTH_PX = 1
PRIVACY_MASKED_COLOR = "#1a2a4a"
PRIVACY_REVEALED_COLOR = "#3344ff"
PRIVACY_HOVER_BORDER_COLOR = "#ffffff"
PRIVACY_BORDER_RGB = (0, 0, 0)
PRIVACY_BORDER_ALPHA = 120
PRIVACY_STATE_MASKED = "MASKED"
PRIVACY_STATE_REVEALED = "REVEALED"
PRIVACY_TOOLTIP_FORMAT = "{field}: {state}. Click to {action}."
PRIVACY_ACTION_REVEAL = "reveal"
PRIVACY_ACTION_MASK = "mask"

# -- the staleness banner and the rate strip ---------------------------

STALENESS_TEXT_COLOR = "#ffb020"
STALENESS_BACKGROUND_RGB = (60, 45, 15)
STALENESS_BACKGROUND_ALPHA = 90
STALENESS_FORMAT = "⏱ LAST TA READ, NOT CURRENT — taken {when}, {age}. {message}"

STALENESS_TOOLTIP = (
    "Shown when the panel is displaying the LAST TA read "
    "this bot produced rather than a current one, with the "
    "age of that reading and the reason no current one "
    "exists. Nothing is recomputed to draw it."
)

RATE_STRIP_TEXT_COLOR = "#66ccff"
RATE_STRIP_BACKGROUND_RGB = (30, 40, 60)
RATE_STRIP_BACKGROUND_ALPHA = 60
RATE_STRIP_PENDING_TEXT = "BTC —   ETH —   (currency rates pending)"
RATE_STRIP_ABSENT_TEXT = "BTC —   ETH —   (currency rates unavailable)"
RATE_STRIP_BTC_ABSENT_TEXT = "BTC —"
RATE_STRIP_ETH_ABSENT_TEXT = "ETH —"
RATE_STRIP_BTC_FORMAT = (
    "BTC ${usd:,.2f}  1$={per_dollar:,.0f} sat  1¢={per_cent:,.0f} sat"
)
RATE_STRIP_ETH_FORMAT = (
    "ETH ${usd:,.2f}  1$={per_dollar:,.0f} gwei  1¢={per_cent:,.0f} gwei"
)
RATE_STRIP_JOIN = "   "
RATE_STRIP_SOURCE_FORMAT = "  ·  {source}"
RATE_STRIP_SOURCE_NONE = "none"

RATE_STRIP_TOOLTIP = (
    "Live BTC/USD and ETH/USD spot from the connected "
    "exchange plus satoshi-per-USD and gwei-per-USD "
    "conversions (1 gwei = 10⁹ wei). Refreshed on the "
    "dashboard tick."
)

BARS_TOOLTIP = (
    "Animated bar graph: per-indicator vote confidence for "
    "the parent bot's timeframe, colour-coded by direction "
    "(green=bullish, red=bearish, grey=neutral)."
)

LOCKS_IDLE_TEXT = "No active timeframe locks"
LOCKS_ACTIVE_PREFIX = "Active locks: "
LOCKS_JOIN = " | "
LOCK_ENTRY_FORMAT = (
    "{source_tf} → {locked_direction} lock ({candles_remaining} candles remaining)"
)
LOCKS_MAXIMUM_HEIGHT_PX = 20
LOCKS_MARGINS_PX = [4, 2, 4, 2]

NO_DATA_FORMAT = "No TA data — {message}"

EMPTY_TEXT = ""


def _bar_fraction(threshold_px: int) -> float:
    """The confidence at which a bar first stands ``threshold_px`` tall.

    Qt measures the ornament thresholds against the painted bar; the
    pane's own minimum height is the one height that is known before
    layout, so a frontend gets the fraction rather than a pixel count.
    """
    usable = BARS_MINIMUM_HEIGHT_PX - BARS_MARGIN_TOP_PX - BARS_MARGIN_BOTTOM_PX
    if usable <= 0:
        return 1.0
    return min(1.0, threshold_px / usable)


def arrow_min_fraction() -> float:
    """The confidence at which a bar is tall enough to carry its arrow."""
    return _bar_fraction(BARS_ARROW_MIN_HEIGHT_PX)


def shine_min_fraction() -> float:
    """The confidence at which a bar is tall enough to carry its highlight."""
    return _bar_fraction(BARS_SHINE_MIN_HEIGHT_PX)


def _number(value: Any, fallback: float = 0.0) -> float:
    """One published reading as a float, or ``fallback`` when it is not one."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number:
        return fallback
    return number


def _clamped(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(max(value, low), high)


def cell_alpha(confidence: Any) -> int:
    """The tint's Qt alpha byte for one vote confidence.

    Runs from ``CELL_ALPHA_FLOOR`` at no confidence to
    ``CELL_ALPHA_FLOOR + CELL_ALPHA_SPAN`` at full confidence.
    """
    return int(_clamped(_number(confidence)) * CELL_ALPHA_SPAN) + CELL_ALPHA_FLOOR


def confidence_bar(confidence: Any) -> str:
    """The ten-cell block bar the Conf column prints."""
    filled = int(_clamped(_number(confidence)) * CONF_BAR_CELLS)
    return CONF_BAR_FILLED * filled + CONF_BAR_EMPTY * (CONF_BAR_CELLS - filled)


def indicator_cell_text(indicator_key: str, signal: Optional[dict]) -> str:
    """The text one indicator cell prints.

    ADX, Z-Score and the Kaufman Efficiency Ratio print a raw reading;
    every other indicator prints its vote confidence as a percentage.
    """
    reading = signal if isinstance(signal, dict) else {}
    direction = str(reading.get("direction", DEFAULT_DIRECTION))
    symbol = DIR_SYMBOLS.get(direction, DEFAULT_SYMBOL)
    details = reading.get("details")
    details = details if isinstance(details, dict) else {}
    if indicator_key == "adx":
        value = _number(details.get("adx"))
        if details.get("ranging"):
            return ADX_RANGING_FORMAT.format(value=value)
        return ADX_TRENDING_FORMAT.format(symbol=symbol, value=value)
    if indicator_key == "zscore":
        return ZSCORE_FORMAT.format(symbol=symbol, value=_number(details.get("z")))
    if indicator_key == "kaufman_er":
        return KAUFMAN_FORMAT.format(symbol=symbol, value=_number(details.get("er")))
    return CONFIDENCE_FORMAT.format(
        symbol=symbol, value=_number(reading.get("confidence"))
    )


def indicator_cell_tooltip(indicator_key: str, signal: Optional[dict]) -> str:
    """The hover text one indicator cell carries: its vote, then its details."""
    reading = signal if isinstance(signal, dict) else {}
    direction = str(reading.get("direction", DEFAULT_DIRECTION))
    confidence = _number(reading.get("confidence"))
    lines = [f"{str(indicator_key).upper()}: {direction}  ({confidence:.0%} conf)"]
    details = reading.get("details")
    for name, value in (details if isinstance(details, dict) else {}).items():
        if isinstance(value, bool):
            if value:
                lines.append(f"  {name}: ✓")
        elif isinstance(value, float):
            lines.append(f"  {name}: {value:.3f}")
        else:
            lines.append(f"  {name}: {value}")
    return "\n".join(lines)


def indicator_cell_colors(signal: Optional[dict]) -> dict:
    """One indicator cell's text colour and its tint, as Qt paints them."""
    reading = signal if isinstance(signal, dict) else {}
    direction = str(reading.get("direction", DEFAULT_DIRECTION))
    if direction == "BULLISH":
        return {
            "text_color": BULLISH_TEXT_COLOR,
            "fill_rgb": list(BULLISH_CELL_RGB),
            "fill_alpha": cell_alpha(reading.get("confidence")),
        }
    if direction == "BEARISH":
        return {
            "text_color": BEARISH_TEXT_COLOR,
            "fill_rgb": list(BEARISH_CELL_RGB),
            "fill_alpha": cell_alpha(reading.get("confidence")),
        }
    return {
        "text_color": NEUTRAL_TEXT_COLOR,
        "fill_rgb": list(NEUTRAL_CELL_RGB),
        "fill_alpha": NEUTRAL_CELL_ALPHA,
    }


def net_cell(tf_data: dict) -> dict:
    """The Net column's cell: the weighted bull-minus-bear tally."""
    net = _number((tf_data or {}).get("net_score"))
    color = None
    if net > 0:
        color = BULLISH_TEXT_COLOR
    elif net < 0:
        color = BEARISH_TEXT_COLOR
    return {"text": NET_FORMAT.format(value=net), "text_color": color}


def comp_skipped_tooltip(tf_data: dict) -> str:
    """The Comp cell's note naming the phantoms left out of the composite.

    Empty while ``composite_skipped`` names none.
    """
    skipped = (tf_data or {}).get("composite_skipped") or []
    if not skipped:
        return ""
    return COMP_SKIPPED_FORMAT.format(timeframes=", ".join(str(one) for one in skipped))


def comp_cell(tf_data: dict) -> dict:
    """The Comp column's cell, an em-dash on a row carrying no composite.

    Carries ``comp_skipped_tooltip`` so a phantom the composite refused is
    named on the cell the operator reads.
    """
    tooltip = comp_skipped_tooltip(tf_data)
    comp = (tf_data or {}).get("composite_net")
    if comp is None:
        return {
            "text": COMP_ABSENT_TEXT,
            "text_color": ABSENT_TEXT_COLOR,
            "tooltip": tooltip,
        }
    value = _number(comp)
    color = None
    if value > 0:
        color = BULLISH_TEXT_COLOR
    elif value < 0:
        color = BEARISH_TEXT_COLOR
    return {
        "text": COMP_FORMAT.format(value=value),
        "text_color": color,
        "tooltip": tooltip,
    }


def conf_cell(tf_data: dict) -> dict:
    """The Conf column's cell: a block bar, then the breadth percentage."""
    conf = _number((tf_data or {}).get("confidence"))
    if conf >= CONF_STRONG_LIMIT:
        color = BULLISH_TEXT_COLOR
    elif conf >= CONF_FAIR_LIMIT:
        color = WARNING_TEXT_COLOR
    else:
        color = ABSENT_TEXT_COLOR
    return {
        "text": CONF_FORMAT.format(bar=confidence_bar(conf), value=conf),
        "text_color": color,
    }


def ordered_timeframes(multi_tf_summary: dict) -> list:
    """The summary's timeframes, shortest first, unknown names last."""
    names = list((multi_tf_summary or {}).keys())

    def rank(name: str) -> int:
        if name in TIMEFRAME_ORDER:
            return TIMEFRAME_ORDER.index(name)
        return UNKNOWN_TIMEFRAME_RANK

    return sorted(names, key=rank)


def signals_by_indicator(tf_data: dict) -> dict:
    """One timeframe's signal list keyed by its indicator name."""
    found: dict = {}
    for signal in (tf_data or {}).get("signals") or []:
        if isinstance(signal, dict) and "indicator" in signal:
            found[signal["indicator"]] = signal
    return found


def lock_line(lock: dict) -> str:
    """One active lock as the single line the locks label prints."""
    entry = lock if isinstance(lock, dict) else {}
    return LOCK_ENTRY_FORMAT.format(
        source_tf=entry.get("source_tf", EMPTY_TEXT),
        locked_direction=entry.get("locked_direction", EMPTY_TEXT),
        candles_remaining=entry.get("candles_remaining", EMPTY_TEXT),
    )


def locks_text(locks: list) -> str:
    """Every active lock on one line, or the idle sentence."""
    lines = [lock_line(one) for one in locks or []]
    if not lines:
        return LOCKS_IDLE_TEXT
    return LOCKS_ACTIVE_PREFIX + LOCKS_JOIN.join(lines)


def privacy_style_sheet(*, masked: bool) -> str:
    """The dot's Qt style sheet: blue when revealed, dark blue when masked."""
    color = PRIVACY_MASKED_COLOR if masked else PRIVACY_REVEALED_COLOR
    red, green, blue = PRIVACY_BORDER_RGB
    return (
        f"{DOT_KIND} {{ "
        f"  background-color: {color}; "
        f"  border: {PRIVACY_BORDER_WIDTH_PX}px solid "
        f"rgba({red},{green},{blue},{PRIVACY_BORDER_ALPHA}); "
        f"  border-radius: {PRIVACY_DOT_RADIUS_PX}px; "
        "  padding: 0px; "
        "} "
        f"{DOT_KIND}:hover {{ border: {PRIVACY_BORDER_WIDTH_PX}px solid "
        f"{PRIVACY_HOVER_BORDER_COLOR}; }}"
    )


def privacy_tooltip(*, masked: bool) -> str:
    """The dot's hover text, naming the state and what a click does."""
    return PRIVACY_TOOLTIP_FORMAT.format(
        field=PRIVACY_FIELD_ID,
        state=PRIVACY_STATE_MASKED if masked else PRIVACY_STATE_REVEALED,
        action=PRIVACY_ACTION_REVEAL if masked else PRIVACY_ACTION_MASK,
    )


STALENESS_STYLE_SHEET = (
    f"color: {STALENESS_TEXT_COLOR}; font-family: Consolas; font-size: 10px; "
    f"padding: 2px 6px; background: rgba({STALENESS_BACKGROUND_RGB[0]}, "
    f"{STALENESS_BACKGROUND_RGB[1]}, {STALENESS_BACKGROUND_RGB[2]}, "
    f"{STALENESS_BACKGROUND_ALPHA}); "
    "border-radius: 2px;"
)

RATE_STRIP_STYLE_SHEET = (
    f"color: {RATE_STRIP_TEXT_COLOR}; font-family: Consolas; "
    "font-size: 10px; padding: 2px 6px; "
    f"background: rgba({RATE_STRIP_BACKGROUND_RGB[0]}, "
    f"{RATE_STRIP_BACKGROUND_RGB[1]}, {RATE_STRIP_BACKGROUND_RGB[2]}, "
    f"{RATE_STRIP_BACKGROUND_ALPHA}); "
    "border-radius: 2px;"
)

HEADER_TOOLTIPS = {
    "TF": (
        "Timeframe identifier. Each row = one timeframe's "
        "verdict (5m/15m/1h/4h/1d/phantoms)."
    ),
    "BB": (
        "Bollinger Bands — distance from band extremes as "
        "% conviction. ▲▼ shows direction; NN% shows "
        "vote confidence."
    ),
    "VTX": ("Vortex — VI+ vs VI− crossover conviction. ▲▼ direction + NN% confidence."),
    "MACD": (
        "MACD — histogram + crossover + divergence. ▲▼ direction + NN% confidence."
    ),
    "SRsi": (
        "Stochastic RSI — K/D crossover in oversold/"
        "overbought zones. ▲▼ direction + NN% confidence."
    ),
    "Ichi": (
        "Ichimoku Cloud — future twist + cloud breakout + "
        "Tenkan/Kijun. ▲▼ direction + NN% confidence."
    ),
    "Vol": (
        "Volume composite — OBV divergence + MFI + CMF + "
        "volume spike ratio. ▲▼ direction + NN% confidence."
    ),
    "Sling": (
        "Slingshot — name is Chris Moody's; squeeze is Carter's "
        "TTM Squeeze (via LazyBear), snapback is Bollinger's own "
        "band rules. ▲▼ direction + NN% confidence."
    ),
    "ADX": (
        "ADX — Average Directional Index. Cell shows the "
        "RAW ADX value (NOT a percentage), 0–100. "
        "ADX <20: ranging (cell reads 'Rng NN'). "
        "ADX 20–35: developing trend. ADX >35: strong "
        "trend. ADX >50: parabolic / unsustainable. "
        "Direction symbol from DI+/DI− cross when "
        "trending.\n\nDUAL THRESHOLDS (intentional): the "
        "voter goes NEUTRAL below ADX 20; the separate "
        "ADXTrendSuppressionGate blocks SCRUM only at "
        "ADX≥30, not below it. An ADX of 25 shows a "
        "developing trend here and does not trip the "
        "gate."
    ),
    "STrd": (
        "Supertrend — ATR-banded trend line. ▲▼ direction "
        "+ NN% confidence (proportional to distance from "
        "band)."
    ),
    "ZSc": (
        "Z-Score — statistical extremity. Cell shows the "
        "RAW signed z-value (NOT a percentage). "
        "|z| >2: strong bearish/bullish mean-revert "
        "signal. |z| <1.5: NEUTRAL (no action).\n\n"
        "ZScoreExtremityGate is ASYMMETRIC: "
        "blocks SCRUM at z<-2 (don't sell the statistical "
        "bottom), blocks FOLD at z>+2 (don't buy the "
        "statistical top). High +z is exactly the right "
        "condition for SCRUM; low -z is exactly the right "
        "condition for FOLD; the gate filters only the "
        "contrarian-wrong action on each side."
    ),
    "KER": (
        "Kaufman Efficiency Ratio — trend efficiency 0–1. "
        "Cell shows the RAW ER value (NOT a percentage). "
        "ER ≤0.05: no-edge market (gate suppresses scrum). "
        "ER ≥0.50: trending (voter contributes direction). "
        "ER ≥0.70: highly efficient trend.\n\nDIRECTION "
        "SYMBOL SEMANTICS: at ER <0.50 the voter is "
        "NEUTRAL (─), not directional. The ▲/▼ symbols "
        "only appear when ER ≥0.50 and reflect the "
        "PRICE direction during the trend, not 'KER says "
        "market is bullish/bearish.' KER doesn't have an "
        "opinion about market direction — it measures "
        "trend QUALITY only.\n\nDUAL THRESHOLDS "
        "(intentional): voter activates at ER ≥0.50; gate "
        "(EfficiencyRatioRegimeGate) suppresses scrum at "
        "ER ≤0.05 or ER ≥0.70. Different consumers, "
        "different thresholds, same field."
    ),
    "RSI": (
        "RSI — classic 70/30 overbought/oversold + "
        "divergence. ▲▼ direction + NN% confidence."
    ),
    "Net": (
        "Net — weighted bull − bear vote tally. "
        "Sum of (confidence × weight) for BULLISH voters "
        "minus same for BEARISH voters. NEUTRAL voters "
        "contribute 0. Theoretical range ±11.7; in "
        "practice rarely outside ±3."
    ),
    "Comp": (
        "Composite Net — parent Net rank-weighted with all "
        "active higher-TF phantom bot summaries. "
        "Phantoms boost (bullish) or suppress (bearish) "
        "the parent's signal only when Phantom Bots "
        "are enabled and have completed their first "
        "signal cycle. Populated on the parent bot's TF "
        "row only; phantom TF rows read “—”."
    ),
    "Conf": (
        "Confidence — |Net| / total_weight_of_active_voters, "
        "capped at 1.0. Reflects BREADTH of agreement, not "
        "magnitude. A 30% reading typically means 6 voters "
        "strongly agree + 6 are NEUTRAL — not 'panel "
        "disagrees'. Green ≥60%, amber ≥30%, gray <30%."
    ),
}


def column_titles(subset: list, *, include_aggregates: bool = False) -> list:
    """TF and ``subset``, padded to PANEL_COLUMN_COUNT.

    ``include_aggregates`` heads the collated columns with AGGREGATE_TITLES,
    which the table carrying the aggregate cells asks for; the other table
    pads with EMPTY_TITLE so a title is printed once over each pillar.
    """
    titles = [TF_COLUMN_TITLE] + [short for _, short, _ in subset]
    pad = AGGREGATE_TITLES if include_aggregates else []
    titles = titles + list(pad)
    return titles + [EMPTY_TITLE] * (PANEL_COLUMN_COUNT - len(titles))


class IndicatorTableModel:
    """One mini-panel's table: its columns, and a row per timeframe.

    ``set_summary`` takes the dict ``TimeframeCoordinator`` publishes and
    rebuilds every row. Cell text, cell colours and hover text are
    settled here so a frontend paints what it is handed.
    """

    def __init__(self, subset: list, *, include_aggregates: bool) -> None:
        self.subset = list(subset)
        self.include_aggregates = bool(include_aggregates)
        self.titles = column_titles(
            self.subset, include_aggregates=self.include_aggregates
        )
        self.rows: list = []

    def column_count(self) -> int:
        return len(self.titles)

    def tooltips(self) -> list:
        return [HEADER_TOOLTIPS.get(title, title) for title in self.titles]

    def _indicator_cells(self, signals: dict) -> list:
        cells = []
        for key, _short, group in self.subset:
            signal = signals.get(key)
            cell = {
                "kind": "indicator",
                "indicator": key,
                "group": group,
                "group_color": GROUP_COLORS.get(group),
                "text": indicator_cell_text(key, signal),
                "tooltip": indicator_cell_tooltip(key, signal),
            }
            cell.update(indicator_cell_colors(signal))
            cells.append(cell)
        return cells

    def _aggregate_cells(self, tf_data: dict) -> list:
        net = net_cell(tf_data)
        net["kind"] = "net"
        comp = comp_cell(tf_data)
        comp["kind"] = "comp"
        conf = conf_cell(tf_data)
        conf["kind"] = "conf"
        return [net, comp, conf]

    def set_summary(self, multi_tf_summary: dict) -> list:
        """Rebuild every row from one multi-timeframe summary."""
        summary = multi_tf_summary if isinstance(multi_tf_summary, dict) else {}
        self.rows = []
        for timeframe in ordered_timeframes(summary):
            tf_data = summary.get(timeframe)
            tf_data = tf_data if isinstance(tf_data, dict) else {}
            cells = [{"kind": "timeframe", "text": str(timeframe), "bold": True}]
            cells.extend(self._indicator_cells(signals_by_indicator(tf_data)))
            if self.include_aggregates:
                cells.extend(self._aggregate_cells(tf_data))
            while len(cells) < PANEL_COLUMN_COUNT:
                cells.append({"kind": "pad", "text": EMPTY_TITLE})
            self.rows.append({"timeframe": str(timeframe), "cells": cells})
        return self.rows

    def payload(self) -> dict:
        return {
            "kind": TABLE_KIND,
            "cell_kind": CELL_KIND,
            "titles": list(self.titles),
            "tooltips": self.tooltips(),
            "column_count": self.column_count(),
            "row_count": len(self.rows),
            "row_height_px": ROW_HEIGHT_PX,
            "rows": [dict(row) for row in self.rows],
            "include_aggregates": self.include_aggregates,
            "alternating_row_colors": ALTERNATING_ROW_COLORS,
            "vertical_header_visible": VERTICAL_HEADER_VISIBLE,
            "selection_behavior": SELECTION_BEHAVIOR,
            "edit_triggers": EDIT_TRIGGERS,
            "horizontal_scroll_policy": HORIZONTAL_SCROLL_POLICY,
            "vertical_scroll_policy": VERTICAL_SCROLL_POLICY,
            "resize_mode": RESIZE_MODE,
            "stretch_last_section": STRETCH_LAST_SECTION,
            "cell_alignment": CELL_ALIGNMENT,
            "size_policy": list(TABLE_SIZE_POLICY),
            "header_min_pad_px": HEADER_MIN_PAD_PX,
            "font_point_drop": FONT_POINT_DROP,
            "font_point_floor": FONT_POINT_FLOOR,
            "slack_rows": TABLE_SLACK_ROWS,
            "slack_px": TABLE_SLACK_PX,
        }


class ConfidenceBarsModel:
    """One mini-panel's bar graph, and the animation that fills it.

    ``set_bars`` names the targets; ``step`` advances every bar one
    frame toward them and answers whether the animation has settled.
    Frames are counted, never timed, so a caller drives the animation
    without a clock.
    """

    def __init__(self) -> None:
        self.targets: list = []
        self.current: list = []
        self.running = False
        self.column_positions: list = []

    def set_bars(self, bars: list) -> list:
        """Name the target bars, restarting the animation from zero."""
        self.targets = [dict(one) for one in bars or [] if isinstance(one, dict)]
        if len(self.current) != len(self.targets):
            self.current = [
                {
                    "name": one.get("name"),
                    "confidence": 0.0,
                    "direction": one.get("direction", DEFAULT_DIRECTION),
                }
                for one in self.targets
            ]
        self.running = bool(self.targets)
        return self.current

    def set_column_positions(self, positions: list) -> list:
        """Align the bars under the table's columns above them."""
        self.column_positions = [list(one) for one in positions or []]
        return self.column_positions

    def step(self) -> bool:
        """Advance one frame. Answers True once every bar has settled."""
        if not self.targets:
            self.running = False
            return True
        settled = True
        for at, target in enumerate(self.targets):
            if at >= len(self.current):
                break
            here = _number(self.current[at].get("confidence"))
            there = _number(target.get("confidence"))
            gap = there - here
            if abs(gap) > BARS_SETTLE_DELTA:
                self.current[at]["confidence"] = here + gap * BARS_LERP_FACTOR
                settled = False
            else:
                self.current[at]["confidence"] = there
            self.current[at]["direction"] = target.get("direction", DEFAULT_DIRECTION)
        if settled:
            self.running = False
        return settled

    def payload(self) -> dict:
        return {
            "kind": BARS_KIND,
            "base_kind": BARS_BASE_KIND,
            "accessible_name": BARS_ACCESSIBLE_NAME,
            "tooltip": BARS_TOOLTIP,
            "minimum_height_px": BARS_MINIMUM_HEIGHT_PX,
            "frame_interval_ms": BARS_FRAME_INTERVAL_MS,
            "lerp_factor": BARS_LERP_FACTOR,
            "settle_delta": BARS_SETTLE_DELTA,
            "running": self.running,
            "empty_text": BARS_EMPTY_TEXT,
            "targets": [dict(one) for one in self.targets],
            "bars": [dict(one) for one in self.current],
            "column_positions": [list(one) for one in self.column_positions],
            "colors": {name: list(rgb) for name, rgb in BAR_COLORS.items()},
            "size_policy": list(BARS_SIZE_POLICY),
            "geometry": {
                "margin_top_px": BARS_MARGIN_TOP_PX,
                "margin_bottom_px": BARS_MARGIN_BOTTOM_PX,
                "margin_left_px": BARS_MARGIN_LEFT_PX,
                "margin_right_px": BARS_MARGIN_RIGHT_PX,
                "gap_px": BARS_GAP_PX,
                "fallback_min_width_px": BARS_FALLBACK_MIN_WIDTH_PX,
                "min_width_px": BARS_MIN_WIDTH_PX,
                "min_height_px": BARS_MIN_HEIGHT_PX,
                "column_pad_fraction": BARS_COLUMN_PAD_FRACTION,
                "column_body_fraction": column_body_fraction(),
                "column_min_pad_px": BARS_COLUMN_MIN_PAD_PX,
                "grid_fractions": list(BARS_GRID_FRACTIONS),
                "shine_limit_px": BARS_SHINE_LIMIT_PX,
                "shine_fraction": BARS_SHINE_FRACTION,
                "shine_min_height_px": BARS_SHINE_MIN_HEIGHT_PX,
                "shine_min_fraction": shine_min_fraction(),
                "arrow_min_height_px": BARS_ARROW_MIN_HEIGHT_PX,
                "arrow_min_fraction": arrow_min_fraction(),
                "glow_inset_px": BARS_GLOW_INSET_PX,
                "glow_radius_px": BARS_GLOW_RADIUS_PX,
                "body_radius_px": BARS_BODY_RADIUS_PX,
                "shine_radius_px": BARS_SHINE_RADIUS_PX,
                "label_height_px": BARS_LABEL_HEIGHT_PX,
                "label_offset_px": BARS_LABEL_OFFSET_PX,
                "arrow_height_px": BARS_ARROW_HEIGHT_PX,
            },
            "paint": {
                "background_rgb": list(BARS_BACKGROUND_RGB),
                "empty_text_rgb": list(BARS_EMPTY_TEXT_RGB),
                "grid_rgb": list(BARS_GRID_RGB),
                "label_rgb": list(BARS_LABEL_RGB),
                "baseline_rgb": list(BARS_BASELINE_RGB),
                "shine_rgb": list(BARS_SHINE_RGB),
                "glow_alpha": BARS_GLOW_ALPHA,
                "gradient_alphas": list(BARS_GRADIENT_ALPHAS),
                "gradient_stops": list(BARS_GRADIENT_STOPS),
                "outline_alpha": BARS_OUTLINE_ALPHA,
                "shine_start_alpha": BARS_SHINE_START_ALPHA,
                "shine_end_alpha": BARS_SHINE_END_ALPHA,
                "arrow_alpha": BARS_ARROW_ALPHA,
                "empty_font": list(BARS_EMPTY_FONT),
                "grid_font": list(BARS_GRID_FONT),
                "label_font": list(BARS_LABEL_FONT),
                "arrow_font": list(BARS_ARROW_FONT),
                "symbols": dict(DIR_SYMBOLS),
            },
        }


def selector_items(bot_statuses: list) -> list:
    """The bot dropdown's entries, accumulation bots only.

    "accumulation" is the operator's word and "scrumming" is the mode
    enum's; both name the same bot and both are kept.
    """
    items: list = []
    for status in bot_statuses or []:
        if not isinstance(status, dict):
            continue
        mode = str(status.get("mode", EMPTY_TEXT)).lower()
        if mode not in ACCUMULATION_MODES:
            continue
        bot_id = str(status.get("bot_id", EMPTY_TEXT))
        items.append(
            {
                "text": SELECTOR_ITEM_FORMAT.format(
                    symbol=status.get("symbol", DEFAULT_SYMBOL_TEXT),
                    short_id=bot_id[:SELECTOR_ID_PREFIX_LEN],
                    state=status.get("state", DEFAULT_STATE_TEXT),
                ),
                "value": bot_id,
                "ta_timeframe": str(
                    status.get("ta_timeframe", DEFAULT_TA_TIMEFRAME)
                    or DEFAULT_TA_TIMEFRAME
                ),
            }
        )
    if not items:
        return [{"text": SELECTOR_EMPTY_TEXT, "value": SELECTOR_PLACEHOLDER_VALUE}]
    return items


def rate_strip_text(snapshot: Optional[dict]) -> str:
    """The BTC/ETH spot line, with an em-dash for a side that is missing."""
    if snapshot is None:
        return RATE_STRIP_ABSENT_TEXT
    reading = snapshot if isinstance(snapshot, dict) else {}
    parts = []
    btc = _number(reading.get("btc_usd"))
    if btc > 0:
        parts.append(
            RATE_STRIP_BTC_FORMAT.format(
                usd=btc,
                per_dollar=_number(reading.get("sat_per_dollar")),
                per_cent=_number(reading.get("sat_per_cent")),
            )
        )
    else:
        parts.append(RATE_STRIP_BTC_ABSENT_TEXT)
    eth = _number(reading.get("eth_usd"))
    if eth > 0:
        parts.append(
            RATE_STRIP_ETH_FORMAT.format(
                usd=eth,
                per_dollar=_number(reading.get("gwei_per_dollar")),
                per_cent=_number(reading.get("gwei_per_cent")),
            )
        )
    else:
        parts.append(RATE_STRIP_ETH_ABSENT_TEXT)
    source = str(reading.get("source", EMPTY_TEXT) or EMPTY_TEXT)
    tail = EMPTY_TEXT
    if source and source != RATE_STRIP_SOURCE_NONE:
        tail = RATE_STRIP_SOURCE_FORMAT.format(source=source)
    return RATE_STRIP_JOIN.join(parts) + tail


def no_data_text(multi_tf_summary: dict, message: str) -> str:
    """``message`` through ``NO_DATA_FORMAT``, or empty while a summary exists.

    A panel drawing a reading says nothing, so ``show_stored`` keeps its
    ``no_data_message`` for ``staleness_line`` without raising this line.
    """
    summary = multi_tf_summary if isinstance(multi_tf_summary, dict) else {}
    if summary or not message:
        return EMPTY_TEXT
    return NO_DATA_FORMAT.format(message=message)


def collected_locks(multi_tf_summary: dict) -> list:
    """Every active lock the summary carries, in timeframe order."""
    summary = multi_tf_summary if isinstance(multi_tf_summary, dict) else {}
    found: list = []
    for timeframe in ordered_timeframes(summary):
        tf_data = summary.get(timeframe)
        found.extend((tf_data or {}).get("locks") or [])
    return found


def sign_direction(value: Any) -> str:
    """The vote direction one signed score reads as; ``None`` reads NEUTRAL."""
    if value is None:
        return DEFAULT_DIRECTION
    number = _number(value)
    if number > 0.0:
        return "BULLISH"
    if number < 0.0:
        return "BEARISH"
    return DEFAULT_DIRECTION


def column_body_fraction() -> float:
    """The share of one column a bar body takes, BARS_COLUMN_PAD_FRACTION aside."""
    return 1.0 - 2.0 * BARS_COLUMN_PAD_FRACTION


def collated_pillars(tf_data: dict) -> list:
    """One pillar per AGGREGATE_TITLES entry, each taking its own sign.

    A pillar carries a name, a direction and the grid column it stands in.
    The table cell above carries the value; the pillar runs the height of
    the panel, past both mini-panels.
    """
    entry = tf_data if isinstance(tf_data, dict) else {}
    directions = [
        sign_direction(entry.get("net_score")),
        sign_direction(entry.get("composite_net")),
        str(entry.get("direction", DEFAULT_DIRECTION)),
    ]
    first = PANEL_COLUMN_COUNT - len(AGGREGATE_TITLES)
    return [
        {"name": title, "direction": way, "column": first + at}
        for at, (title, way) in enumerate(zip(AGGREGATE_TITLES, directions))
    ]


def bars_for(subset: list, tf_data: dict) -> list:
    """One mini-panel's bars for the timeframe the table lists first."""
    signals = signals_by_indicator(tf_data)
    return [
        {
            "name": short,
            "confidence": _number((signals.get(key) or {}).get("confidence")),
            "direction": str(
                (signals.get(key) or {}).get("direction", DEFAULT_DIRECTION)
            ),
            "group": group,
        }
        for key, short, group in subset
    ]


class IndicatorPanelModel:
    """The whole panel: its chrome, its two mini-panels and its state.

    ``set_summary`` is the live path and ``show_no_data`` the empty one;
    ``show_stored`` draws a persisted reading and raises the amber age
    banner over it, because a stale reading shown as current is worse
    than an empty panel.
    """

    def __init__(self, *, sim_mode: bool = False) -> None:
        self.sim_mode = bool(sim_mode)
        self.table_a = IndicatorTableModel(
            ROW_A_INDICATOR_COLS, include_aggregates=True
        )
        self.table_b = IndicatorTableModel(
            ROW_B_INDICATOR_COLS, include_aggregates=False
        )
        self.bars_a = ConfidenceBarsModel()
        self.bars_b = ConfidenceBarsModel()
        self.pillars: list = []
        self.summary: dict = {}
        self.symbol = EMPTY_TEXT
        self.locks_line = LOCKS_IDLE_TEXT
        self.selector = [
            {"text": SELECTOR_PLACEHOLDER_TEXT, "value": SELECTOR_PLACEHOLDER_VALUE}
        ]
        self.selected_bot_id = EMPTY_TEXT
        self.bot_timeframes: dict = {}
        self.masked = False
        self.showing_stored = False
        self.staleness_line = EMPTY_TEXT
        self.no_data_cause = EMPTY_TEXT
        self.no_data_message = EMPTY_TEXT
        self.rate_line = RATE_STRIP_PENDING_TEXT

    def set_summary(self, multi_tf_summary: dict, symbol: str = EMPTY_TEXT) -> None:
        """Draw a live reading, clearing any staleness banner over it."""
        self.summary = multi_tf_summary if isinstance(multi_tf_summary, dict) else {}
        self.symbol = str(symbol or EMPTY_TEXT)
        self.showing_stored = False
        self.staleness_line = EMPTY_TEXT
        self.table_a.set_summary(self.summary)
        self.table_b.set_summary(self.summary)
        self.locks_line = locks_text(collected_locks(self.summary))
        timeframes = ordered_timeframes(self.summary)
        if not timeframes:
            self.bars_a.set_bars([])
            self.bars_b.set_bars([])
            self.pillars = []
            return
        first = self.summary.get(timeframes[0]) or {}
        self.bars_a.set_bars(bars_for(ROW_A_INDICATOR_COLS, first))
        self.bars_b.set_bars(bars_for(ROW_B_INDICATOR_COLS, first))
        self.pillars = collated_pillars(first)

    def show_no_data(self, message: str, cause: str = EMPTY_TEXT) -> None:
        """Empty the tables and say the one reason there is nothing to draw."""
        self.no_data_cause = str(cause or EMPTY_TEXT)
        self.no_data_message = str(message or EMPTY_TEXT)
        self.set_summary({}, self.symbol)

    def show_stored(self, stored: dict, when: str, age: str, message: str) -> None:
        """Draw a persisted reading under the amber banner naming its age."""
        reading = stored if isinstance(stored, dict) else {}
        self.set_summary(
            reading.get("timeframes") or {},
            str(reading.get("symbol") or self.symbol or EMPTY_TEXT),
        )
        self.showing_stored = True
        self.no_data_message = str(message or EMPTY_TEXT)
        self.staleness_line = STALENESS_FORMAT.format(
            when=when, age=age, message=self.no_data_message
        )

    def set_bots(self, bot_statuses: list) -> list:
        """Rebuild the dropdown, keeping the selection when it survives."""
        self.selector = selector_items(bot_statuses)
        self.bot_timeframes = {
            one["value"]: one["ta_timeframe"]
            for one in self.selector
            if one.get("value") and "ta_timeframe" in one
        }
        values = [one.get("value") for one in self.selector]
        if self.selected_bot_id not in values:
            self.selected_bot_id = values[0] if values else EMPTY_TEXT
        return self.selector

    def select_bot(self, bot_id: str) -> str:
        self.selected_bot_id = str(bot_id or EMPTY_TEXT)
        return self.selected_bot_id

    def set_masked(self, *, masked: bool) -> bool:
        self.masked = bool(masked)
        return self.masked

    def set_rates(self, snapshot: Optional[dict]) -> str:
        self.rate_line = rate_strip_text(snapshot)
        return self.rate_line

    def selector_payload(self) -> list:
        """The dropdown as drawn: masked entries show ``****``, values intact."""
        drawn = []
        for one in self.selector:
            entry = dict(one)
            entry["raw_text"] = one.get("text")
            if self.masked:
                entry["text"] = PRIVACY_MASK_TEXT
            drawn.append(entry)
        return drawn


def build_payload(model: IndicatorPanelModel) -> dict:
    """The whole ``indicator_panel.state`` answer for one model."""
    return {
        "method": METHOD,
        "kind": PANEL_KIND,
        "base_kind": PANEL_BASE_KIND,
        "logger_name": LOGGER_NAME,
        "alpha_scale": ALPHA_SCALE,
        "alpha_unit": ALPHA_UNIT,
        "percent_scale": PERCENT_SCALE,
        "title_text": TITLE_TEXT,
        "title_heading_property": TITLE_HEADING_PROPERTY,
        "container": dict(CONTAINER),
        "header": dict(HEADER),
        "size_policy": list(PANEL_SIZE_POLICY),
        "sim_mode": model.sim_mode,
        "bus_topics": list(BUS_TOPICS),
        "selector": model.selector_payload(),
        "selector_placeholder": {
            "text": SELECTOR_PLACEHOLDER_TEXT,
            "value": SELECTOR_PLACEHOLDER_VALUE,
        },
        "selected_bot_id": model.selected_bot_id,
        "bot_timeframes": dict(model.bot_timeframes),
        "privacy": {
            "kind": DOT_KIND,
            "base_kind": DOT_BASE_KIND,
            "field_id": PRIVACY_FIELD_ID,
            "size_px": PRIVACY_DOT_SIZE_PX,
            "border_radius_px": PRIVACY_DOT_RADIUS_PX,
            "border_width_px": PRIVACY_BORDER_WIDTH_PX,
            "masked": model.masked,
            "state": (PRIVACY_STATE_MASKED if model.masked else PRIVACY_STATE_REVEALED),
            "mask_text": PRIVACY_MASK_TEXT,
            "masked_color": PRIVACY_MASKED_COLOR,
            "revealed_color": PRIVACY_REVEALED_COLOR,
            "hover_border_color": PRIVACY_HOVER_BORDER_COLOR,
            "border_rgb": list(PRIVACY_BORDER_RGB),
            "border_alpha": PRIVACY_BORDER_ALPHA,
            "style_sheet": privacy_style_sheet(masked=model.masked),
            "tooltip": privacy_tooltip(masked=model.masked),
        },
        "staleness": {
            "visible": model.showing_stored,
            "text": model.staleness_line,
            "style_sheet": STALENESS_STYLE_SHEET,
            "text_color": STALENESS_TEXT_COLOR,
            "background_rgb": list(STALENESS_BACKGROUND_RGB),
            "background_alpha": STALENESS_BACKGROUND_ALPHA,
            "accessible_name": STALENESS_ACCESSIBLE_NAME,
            "tooltip": STALENESS_TOOLTIP,
        },
        "rate_strip": {
            "text": model.rate_line,
            "pending_text": RATE_STRIP_PENDING_TEXT,
            "absent_text": RATE_STRIP_ABSENT_TEXT,
            "style_sheet": RATE_STRIP_STYLE_SHEET,
            "text_color": RATE_STRIP_TEXT_COLOR,
            "background_rgb": list(RATE_STRIP_BACKGROUND_RGB),
            "background_alpha": RATE_STRIP_BACKGROUND_ALPHA,
            "accessible_name": RATE_STRIP_ACCESSIBLE_NAME,
            "tooltip": RATE_STRIP_TOOLTIP,
        },
        "tables": [model.table_a.payload(), model.table_b.payload()],
        "pillars": {
            "columns": [dict(one) for one in model.pillars],
            "column_count": PANEL_COLUMN_COUNT,
            "ground_rgb": list(PANEL_GROUND_RGB),
            "label_strip_px": BARS_MARGIN_BOTTOM_PX,
            "ceiling_px": BARS_MARGIN_TOP_PX,
            "ruled_columns": RULED_COLUMNS,
            "rule_rgb": list(BARS_BASELINE_RGB),
            "pad_fraction": PILLAR_PAD_FRACTION,
            "glow_alpha": PILLAR_GLOW_ALPHA,
            "glow_inset_px": BARS_GLOW_INSET_PX,
            "label_rgb": list(BARS_LABEL_RGB),
            "label_font": list(BARS_LABEL_FONT),
            "colors": {name: list(rgb) for name, rgb in BAR_COLORS.items()},
            "gradient_alphas": list(BARS_GRADIENT_ALPHAS),
            "gradient_stops": list(BARS_GRADIENT_STOPS),
            "outline_alpha": BARS_OUTLINE_ALPHA,
            "body_radius_px": BARS_BODY_RADIUS_PX,
            "glow_radius_px": BARS_GLOW_RADIUS_PX,
        },
        "bars": [model.bars_a.payload(), model.bars_b.payload()],
        "locks": {
            "text": model.locks_line,
            "idle_text": LOCKS_IDLE_TEXT,
            "muted_property": LOCKS_MUTED_PROPERTY,
            "maximum_height_px": LOCKS_MAXIMUM_HEIGHT_PX,
            "margins_px": list(LOCKS_MARGINS_PX),
        },
        "indicator_cols": [list(one) for one in INDICATOR_COLS],
        "row_a_cols": [list(one) for one in ROW_A_INDICATOR_COLS],
        "row_b_cols": [list(one) for one in ROW_B_INDICATOR_COLS],
        "group_colors": dict(GROUP_COLORS),
        "direction_symbols": dict(DIR_SYMBOLS),
        "raw_value_indicators": list(RAW_VALUE_INDICATORS),
        "timeframe_order": list(TIMEFRAME_ORDER),
        "header_tooltips": dict(HEADER_TOOLTIPS),
        "colors": {
            "bullish_text": BULLISH_TEXT_COLOR,
            "bearish_text": BEARISH_TEXT_COLOR,
            "neutral_text": NEUTRAL_TEXT_COLOR,
            "absent_text": ABSENT_TEXT_COLOR,
            "warning_text": WARNING_TEXT_COLOR,
            "bullish_fill_rgb": list(BULLISH_CELL_RGB),
            "bearish_fill_rgb": list(BEARISH_CELL_RGB),
            "neutral_fill_rgb": list(NEUTRAL_CELL_RGB),
            "neutral_fill_alpha": NEUTRAL_CELL_ALPHA,
            "cell_alpha_span": CELL_ALPHA_SPAN,
            "cell_alpha_floor": CELL_ALPHA_FLOOR,
            "conf_strong_limit": CONF_STRONG_LIMIT,
            "conf_fair_limit": CONF_FAIR_LIMIT,
        },
        "no_data": {
            "cause": model.no_data_cause,
            "message": model.no_data_message,
            "format": NO_DATA_FORMAT,
            "text": no_data_text(model.summary, model.no_data_message),
        },
        "showing_stored": model.showing_stored,
    }


PANEL_MODEL = IndicatorPanelModel()

ACTIONS = (
    "set_summary",
    "show_no_data",
    "show_stored",
    "set_bots",
    "select_bot",
    "set_masked",
    "set_rates",
    "step_bars",
    "set_column_positions",
)


def _apply(model: IndicatorPanelModel, action: str, params: dict) -> None:
    if action == "set_summary":
        model.set_summary(params.get("summary") or {}, params.get("symbol", EMPTY_TEXT))
    elif action == "show_no_data":
        model.show_no_data(
            params.get("message", EMPTY_TEXT), params.get("cause", EMPTY_TEXT)
        )
    elif action == "show_stored":
        model.show_stored(
            params.get("stored") or {},
            params.get("when", EMPTY_TEXT),
            params.get("age", EMPTY_TEXT),
            params.get("message", EMPTY_TEXT),
        )
    elif action == "set_bots":
        model.set_bots(params.get("bots") or [])
    elif action == "select_bot":
        model.select_bot(params.get("bot_id", EMPTY_TEXT))
    elif action == "set_masked":
        model.set_masked(masked=bool(params.get("masked", False)))
    elif action == "set_rates":
        model.set_rates(params.get("snapshot"))
    elif action == "step_bars":
        for _frame in range(int(_number(params.get("frames"), 1.0)) or 1):
            model.bars_a.step()
            model.bars_b.step()
    elif action == "set_column_positions":
        model.bars_a.set_column_positions(params.get("row_a") or [])
        model.bars_b.set_column_positions(params.get("row_b") or [])


def view_model(params: dict) -> dict:
    """Bridge handler for ``indicator_panel.state``.

    Reads ``reset`` and one ``action``. The rows, the selection and the
    bar animation persist between calls because the panel on screen
    does; ``reset`` is what a fresh mount sends.
    """
    global PANEL_MODEL
    asked = params if isinstance(params, dict) else {}
    if asked.get("reset", False):
        PANEL_MODEL = IndicatorPanelModel(sim_mode=bool(asked.get("sim_mode", False)))
    _apply(PANEL_MODEL, str(asked.get("action", EMPTY_TEXT)), asked)
    return build_payload(PANEL_MODEL)
