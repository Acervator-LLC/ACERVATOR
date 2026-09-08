"""market_inspector_tab_surface.py -- the Market Inspector tab, without Qt.

Describes the per-bot Market Inspector tab of the Live Bot Settings
window. The tab builds nothing of its own while the shared analyzer
answers: it hands the bot to ``build_per_bot_view`` and returns that
view. When the analyzer cannot be reached, or the view raises, the tab
returns its own screen instead -- one amber wrapped line naming the
failure, above a stretch.

``MarketInspectorTabModel`` holds the tab's state and ``build`` runs the
delegation. ``MarketInspectorSource`` is a plain stand-in for the view
builder, so the tab can be driven over the bridge from values alone.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``market_inspector_tab.state`` method, which is how the Electron
renderer reaches it. Every value below is written out here rather than
read from ``src.gui.live_settings.market_inspector_tab``, so a value
changed on one side alone is reported. Nothing here imports Qt.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import design_system as ds

METHOD = "market_inspector_tab.state"

ACCESSIBLE_NAME = ""

DELEGATE_MODULE = "..market_inspector"
DELEGATE_FUNCTION = "build_per_bot_view"
BOT_ATTRIBUTE = "_bot"

LOGGER_NAME = "acervator.gui"
WARNING_FORMAT = "Market Inspector per-bot view unavailable: %s"

FALLBACK_HEADLINE = "<b>Market Inspector unavailable.</b><br><br>"
FALLBACK_TEXT_FORMAT = (
    "<b>Market Inspector unavailable.</b><br><br>{error_type}: {error_text}"
)
FALLBACK_HEADLINE_TEXT = "Market Inspector unavailable."
FALLBACK_HEADLINE_WEIGHT = "bold"
FALLBACK_HEADLINE_BREAKS = 2
FALLBACK_DETAIL_FORMAT = "{error_type}: {error_text}"
FALLBACK_STYLE_FORMAT = "color: {color_hex}; padding: {padding_px}px;"
FALLBACK_COLOR = ds.FOLD_RATIO_AMBER
FALLBACK_PADDING_PX = 12
FALLBACK_WORD_WRAP = True
FALLBACK_LABEL_CLASS = "QLabel"
FALLBACK_STRETCH = "stretch"
FALLBACK_SPACING_SET = True
FALLBACK_MARGINS_SET = True
ERROR_SEPARATOR = ": "

NO_VIEW: Optional[Any] = None
NO_MESSAGE = ""
NO_STYLE = ""
NO_WORD_WRAP = False

DEFAULT_ERROR_TYPE = "RuntimeError"

ACTIONS: dict = {}
TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()

BUILD_START = "build.start"
BUILD_DELEGATED = "build.delegated"
BUILD_VIEW = "build.view"
BUILD_FAILED = "build.failed"
BUILD_WARNED = "build.warned"
BUILD_MESSAGE = "build.message"
BUILD_LABEL = "build.label"
BUILD_STRETCH = "build.stretch"
BUILD_RETURN = "build.return"

CALL_NAMES = (
    BUILD_START,
    BUILD_DELEGATED,
    BUILD_VIEW,
    BUILD_FAILED,
    BUILD_WARNED,
    BUILD_MESSAGE,
    BUILD_LABEL,
    BUILD_STRETCH,
    BUILD_RETURN,
)

ERROR_TYPES = {
    "AttributeError": AttributeError,
    "Exception": Exception,
    "ImportError": ImportError,
    "KeyError": KeyError,
    "RuntimeError": RuntimeError,
    "TypeError": TypeError,
    "ValueError": ValueError,
    "ZeroDivisionError": ZeroDivisionError,
}


def fallback_text(error_type: Any, error_text: Any) -> str:
    """The one line the tab shows when the per-bot view cannot be built."""
    return FALLBACK_TEXT_FORMAT.format(error_type=error_type, error_text=error_text)


def fallback_detail(error_type: Any, error_text: Any) -> str:
    """The error type and text alone, with no markup for a renderer to read."""
    return FALLBACK_DETAIL_FORMAT.format(error_type=error_type, error_text=error_text)


def fallback_style(
    color_hex: Any = FALLBACK_COLOR, padding_px: Any = FALLBACK_PADDING_PX
) -> str:
    """The skin the failure line wears."""
    return FALLBACK_STYLE_FORMAT.format(color_hex=color_hex, padding_px=padding_px)


def warning_line(exc: Any) -> str:
    """The log line the tab writes when it falls back."""
    return WARNING_FORMAT % (exc,)


def error_from(type_name: Any, text: Any) -> BaseException:
    """An exception of the named type carrying `text`.

    A name the table does not hold becomes a class of that name, so a
    failure the renderer reports reaches the model under its own name.
    """
    kind = ERROR_TYPES.get(type_name)
    if kind is None:
        kind = type(str(type_name), (Exception,), {})
    return kind(text)


VIEW_SPACING_PX = 8
LAYOUT_MARGIN_PX = 9
FALLBACK_SPACING_PX = 6
GROUP_MARGIN_PX = 0
GROUP_SPACING_PX = 6
GROUP_BORDER_PX = 1
GROUP_BORDER_COLOR = "#2a2a44"
GROUP_RADIUS_PX = 4
GROUP_PADDING_PX = 8
GROUP_TITLE_HEIGHT_PX = 18
GROUP_STYLE_FORMAT = (
    "QGroupBox {{ border: {border_px}px solid {border_color}; "
    "border-radius: {radius_px}px; padding: {padding_px}px; "
    "padding-top: {top_px}px; margin: 0px; }}"
    "QGroupBox::title {{ subcontrol-origin: padding; "
    "subcontrol-position: top left; left: {padding_px}px; "
    "top: {padding_px}px; padding: 0px; }}"
)

ANALYZER_UNAVAILABLE_TEXT = "Market Inspector analyzer unavailable."

NO_SCAN_HEADLINE = "No Market Inspector scan yet."
NO_SCAN_BODY = (
    "Open the Market Inspector top-level tab and press "
    "Refresh to populate. The scan runs across the top-50 "
    "CoinGecko markets on daily and weekly candles; results "
    "are shared between the top-level tab and this per-bot "
    "view."
)
NO_SCAN_BREAKS = 2
NO_SCAN_COLOR = "#aaa"
NO_SCAN_PADDING_PX = 12

OWN_CARD_TITLE_FORMAT = "This Bot's Asset — {asset}"
UNKNOWN_ASSET = "?"
NO_SIGNAL_ASSET = "this asset"
NO_SIGNAL_FORMAT = (
    "No signal for {asset} in the current scan. The universe covers "
    "CoinGecko top-50; markets outside that set are not tracked."
)

SIGNAL_LINE_PREFIX = "Signal: "
SIGNAL_LINE_TAIL_FORMAT = "  |  Score: {score:.2f}  |  Direction: {direction}"
DIRECTION_NONE = "—"
SIGNAL_FONT_SIZE_PX = 13

TF_KEYS = ("1d", "1w")
TF_LINE_FORMAT = "{tf}: {state}"
TF_NONE = "—"
TF_UPPER_TAG = "▲"
TF_LOWER_TAG = "▼"
TF_FLAT_TAG = "·"
TF_TIGHT_TAG = " T"
TF_STATE_FORMAT = "{tag} bb={bb:.2f} z={z:+.2f}{tight}"

HIGHER_TITLE = "Higher-Scoring Markets (top-5)"
HIGHER_LIMIT = 5
HIGHER_ROW_FORMAT = "{symbol}  ·  {signal}  ·  score {score:.2f}"
HIGHER_ACTIVE_SUFFIX = "  ·  ACTIVE"

PAIRS_TITLE = "Opposing Pairs Featuring This Asset"
PAIR_ROW_FORMAT = "{long} (long) ⇄ {short} (short)  ·  corr {corr:+.3f}"

SIGNAL_COLOR_PREFIXES = (
    ("ENTRY_LONG_HIGH", "#00ff88"),
    ("ENTRY_LONG", "#66cc99"),
    ("ENTRY_SHORT_HIGH", "#ff3366"),
    ("ENTRY_SHORT", "#ff9966"),
)
WATCHLIST_SIGNAL = "WATCHLIST"
WATCHLIST_COLOR = "#ffcc00"
DEFAULT_SIGNAL_COLOR = "#888"

HTML_BREAK = "<br>"
BOLD_OPEN = "<b>"
BOLD_CLOSE = "</b>"
MONOSPACE_FAMILY = "monospace"


def signal_colour(signal: Any) -> str:
    """The colour one Market Inspector signal name is drawn in."""
    name = str(signal or "")
    for prefix, colour_hex in SIGNAL_COLOR_PREFIXES:
        if name.startswith(prefix):
            return colour_hex
    if name == WATCHLIST_SIGNAL:
        return WATCHLIST_COLOR
    return DEFAULT_SIGNAL_COLOR


def tf_state_text(analysis: Any) -> str:
    """One timeframe's band position, z-score and tightening as one line."""
    if analysis is None:
        return TF_NONE
    if analysis.at_upper_extreme:
        tag = TF_UPPER_TAG
    elif analysis.at_lower_extreme:
        tag = TF_LOWER_TAG
    else:
        tag = TF_FLAT_TAG
    return TF_STATE_FORMAT.format(
        tag=tag,
        bb=analysis.bb_position,
        z=analysis.z_score,
        tight=TF_TIGHT_TAG if analysis.tightening else NO_MESSAGE,
    )


def view_part(words: Any, bold: bool = False, breaks: int = 0) -> dict:
    """One run of a row's words, with the line breaks that come before it."""
    return {"text": str(words), "bold": bool(bold), "breaks": int(breaks)}


def view_row(
    parts: Any,
    color: str = NO_MESSAGE,
    font_size_px: int = 0,
    mono: bool = False,
    word_wrap: bool = False,
    padding_px: int = 0,
) -> dict:
    """One line of the per-bot view, with the skin its label wears."""
    return {
        "parts": list(parts),
        "color": color,
        "font_size_px": int(font_size_px),
        "mono": bool(mono),
        "word_wrap": bool(word_wrap),
        "padding_px": int(padding_px),
    }


def row_style(one: dict) -> str:
    """The Qt style sheet one row carries, empty when it wears none."""
    pieces = []
    if one.get("color"):
        pieces.append("color: {0};".format(one["color"]))
    if one.get("font_size_px"):
        pieces.append("font-size: {0}px;".format(one["font_size_px"]))
    if one.get("mono"):
        pieces.append("font-family: {0};".format(MONOSPACE_FAMILY))
    if one.get("padding_px"):
        pieces.append("padding: {0}px;".format(one["padding_px"]))
    return " ".join(pieces)


def row_html(one: dict) -> str:
    """One row as the rich text a Qt label draws."""
    out = []
    for piece in one.get("parts", []):
        out.append(HTML_BREAK * int(piece.get("breaks", 0) or 0))
        words = str(piece.get("text", NO_MESSAGE))
        out.append(BOLD_OPEN + words + BOLD_CLOSE if piece.get("bold") else words)
    return NO_MESSAGE.join(out)


def group_style() -> str:
    """The Qt style sheet that gives a group box the card shape
    ``bot_live_settings.css`` draws every group of this window in."""
    return GROUP_STYLE_FORMAT.format(
        border_px=GROUP_BORDER_PX,
        border_color=GROUP_BORDER_COLOR,
        radius_px=GROUP_RADIUS_PX,
        padding_px=GROUP_PADDING_PX,
        top_px=GROUP_PADDING_PX + GROUP_TITLE_HEIGHT_PX + GROUP_SPACING_PX,
    )


def bot_asset(bot: Any) -> str:
    """The base asset of ``bot``'s market, upper case, or ''."""
    try:
        symbol = str(getattr(getattr(bot, "config", None), "symbol", "") or "")
    except Exception:  # noqa: BLE001 - symbol read best-effort
        return NO_MESSAGE
    return symbol.split("/")[0].upper() if "/" in symbol else symbol.upper()


def per_bot_view(bot: Any) -> dict:
    """The per-bot Market Inspector screen as values, read off the shared
    analyzer's most recent scan.

    ``src.gui.market_inspector.build_per_bot_view`` draws these values as
    widgets and ``market_inspector_tab.js`` draws them as elements.
    """
    view: dict = {
        "available": True,
        "asset": NO_MESSAGE,
        "spacing_px": VIEW_SPACING_PX,
        "margin_px": LAYOUT_MARGIN_PX,
        "rows": [],
        "groups": [],
        "stretch": True,
    }
    try:
        from ...trading.market_inspector import get_shared_inspector

        inspector = get_shared_inspector()
    except Exception:  # noqa: BLE001 - analyzer import guard
        view["available"] = False
        view["rows"].append(view_row([view_part(ANALYZER_UNAVAILABLE_TEXT)]))
        return view

    asset = bot_asset(bot)
    view["asset"] = asset

    signals = list(inspector.last_signals)
    if not signals:
        view["rows"].append(
            view_row(
                [
                    view_part(NO_SCAN_HEADLINE, bold=True),
                    view_part(NO_SCAN_BODY, breaks=NO_SCAN_BREAKS),
                ],
                color=NO_SCAN_COLOR,
                word_wrap=True,
                padding_px=NO_SCAN_PADDING_PX,
            )
        )
        return view

    own = inspector.get_signal(asset)
    card: dict = {
        "title": OWN_CARD_TITLE_FORMAT.format(asset=asset or UNKNOWN_ASSET),
        "rows": [],
    }
    if own is None:
        card["rows"].append(
            view_row(
                [view_part(NO_SIGNAL_FORMAT.format(asset=asset or NO_SIGNAL_ASSET))]
            )
        )
    else:
        card["rows"].append(
            view_row(
                [
                    view_part(SIGNAL_LINE_PREFIX),
                    view_part(own.signal, bold=True),
                    view_part(
                        SIGNAL_LINE_TAIL_FORMAT.format(
                            score=own.score, direction=own.direction or DIRECTION_NONE
                        )
                    ),
                ],
                color=signal_colour(own.signal),
                font_size_px=SIGNAL_FONT_SIZE_PX,
            )
        )
        for tf_key in TF_KEYS:
            card["rows"].append(
                view_row(
                    [
                        view_part(
                            TF_LINE_FORMAT.format(
                                tf=tf_key, state=tf_state_text(own.per_tf.get(tf_key))
                            )
                        )
                    ]
                )
            )
    view["groups"].append(card)

    floor = own.score if own is not None else 0.0
    higher = [s for s in signals if s.score > floor and s.symbol != asset][
        :HIGHER_LIMIT
    ]
    if higher:
        group: dict = {"title": HIGHER_TITLE, "rows": []}
        for one in higher:
            words = HIGHER_ROW_FORMAT.format(
                symbol=one.symbol, signal=one.signal, score=one.score
            )
            if one.is_active:
                words += HIGHER_ACTIVE_SUFFIX
            group["rows"].append(
                view_row([view_part(words)], color=signal_colour(one.signal), mono=True)
            )
        view["groups"].append(group)

    related = [
        pair
        for pair in inspector.last_pairs
        if pair.long_side.symbol == asset or pair.short_side.symbol == asset
    ]
    if related:
        pairs: dict = {"title": PAIRS_TITLE, "rows": []}
        for pair in related:
            pairs["rows"].append(
                view_row(
                    [
                        view_part(
                            PAIR_ROW_FORMAT.format(
                                long=pair.long_side.symbol,
                                short=pair.short_side.symbol,
                                corr=pair.correlation_30d,
                            )
                        )
                    ]
                )
            )
        view["groups"].append(pairs)
    return view


class SharedAnalyzerSource:
    """The per-bot view builder the tab delegates to in the running program."""

    def build_per_bot_view(self, bot: Any) -> dict:
        """The per-bot screen for ``bot``, read off the shared analyzer."""
        return per_bot_view(bot)


class MarketInspectorSource:
    """The per-bot view builder the tab delegates to.

    ``raises`` is what the builder throws instead of answering, which is
    how the tab's fallback screen is driven.
    """

    def __init__(
        self, view: Any = NO_VIEW, raises: Optional[BaseException] = None
    ) -> None:
        self.view = view
        self.raises = raises
        self.seen: list = []

    def build_per_bot_view(self, bot: Any) -> Any:
        self.seen.append(bot)
        if self.raises is not None:
            raise self.raises
        return self.view


class MarketInspectorTabModel:
    """The Market Inspector tab, its delegation and its fallback screen.

    ``build`` hands the bot to the view builder. On an answer the tab
    carries that view and nothing else. On a failure it carries the
    warning line and the one wrapped amber row above a stretch. Every
    step is appended to ``calls`` in the order the shipped tab makes it.
    """

    def __init__(self, bot: Any = None, source: Any = None) -> None:
        self.bot = bot
        self.source = SharedAnalyzerSource() if source is None else source
        self.accessible_name = ACCESSIBLE_NAME
        self.delegated = False
        self.view = NO_VIEW
        self.message = NO_MESSAGE
        self.error_type = NO_MESSAGE
        self.error_text = NO_MESSAGE
        self.detail = NO_MESSAGE
        self.style_sheet = NO_STYLE
        self.word_wrap = NO_WORD_WRAP
        self.order: list = []
        self.warnings: list = []
        self.calls: list = []

    def build(self) -> Any:
        """Delegate to the view builder, or fill the fallback screen.

        Starts from an empty screen each time, so a second build carries
        what the first did, exactly as the shipped tab hands back a
        freshly built tab on every call. Only ``Exception`` is caught, so
        a builder that raises anything wider ends the build here.
        """
        self.delegated = False
        self.view = NO_VIEW
        self.message = NO_MESSAGE
        self.error_type = NO_MESSAGE
        self.error_text = NO_MESSAGE
        self.detail = NO_MESSAGE
        self.style_sheet = NO_STYLE
        self.word_wrap = NO_WORD_WRAP
        self.order = []
        self.warnings = []
        self.calls = [[BUILD_START]]
        try:
            self.view = self.source.build_per_bot_view(self.bot)
            self.delegated = True
            self.calls.append([BUILD_DELEGATED])
            self.calls.append([BUILD_VIEW])
            self.calls.append([BUILD_RETURN, self.delegated])
            return self.view
        except Exception as exc:
            self.calls.append([BUILD_FAILED, type(exc).__name__])
            self.warnings.append(warning_line(exc))
            self.calls.append([BUILD_WARNED])
            self.error_type = type(exc).__name__
            self.error_text = str(exc)
            self.message = fallback_text(self.error_type, exc)
            self.detail = fallback_detail(self.error_type, exc)
            self.style_sheet = fallback_style()
            self.word_wrap = FALLBACK_WORD_WRAP
            self.calls.append([BUILD_MESSAGE])
            self.order.append(FALLBACK_LABEL_CLASS)
            self.calls.append([BUILD_LABEL])
            self.order.append(FALLBACK_STRETCH)
            self.calls.append([BUILD_STRETCH])
            self.calls.append([BUILD_RETURN, self.delegated])
            return None


def build_view_model(model: MarketInspectorTabModel, build_now: bool = False) -> dict:
    """Return every value the Market Inspector tab holds as one dict.

    `build_now` runs the delegation and fills whichever screen follows.
    """
    if build_now:
        model.build()
    return {
        "accessible_name": model.accessible_name,
        "delegate": {
            "module": DELEGATE_MODULE,
            "function": DELEGATE_FUNCTION,
            "bot_attribute": BOT_ATTRIBUTE,
        },
        "delegated": model.delegated,
        "view": model.view,
        "message": model.message,
        "error_type": model.error_type,
        "error_text": model.error_text,
        "detail": model.detail,
        "style_sheet": model.style_sheet,
        "word_wrap": model.word_wrap,
        "order": list(model.order),
        "fallback": {
            "headline": FALLBACK_HEADLINE,
            "headline_text": FALLBACK_HEADLINE_TEXT,
            "headline_weight": FALLBACK_HEADLINE_WEIGHT,
            "headline_breaks": FALLBACK_HEADLINE_BREAKS,
            "detail_format": FALLBACK_DETAIL_FORMAT,
            "text_format": FALLBACK_TEXT_FORMAT,
            "style_format": FALLBACK_STYLE_FORMAT,
            "color": FALLBACK_COLOR,
            "padding_px": FALLBACK_PADDING_PX,
            "word_wrap": FALLBACK_WORD_WRAP,
            "label_class": FALLBACK_LABEL_CLASS,
            "stretch": FALLBACK_STRETCH,
            "spacing_set": FALLBACK_SPACING_SET,
            "margins_set": FALLBACK_MARGINS_SET,
            "error_separator": ERROR_SEPARATOR,
        },
        "layout": {
            "margin_px": LAYOUT_MARGIN_PX,
            "view_spacing_px": VIEW_SPACING_PX,
            "fallback_spacing_px": FALLBACK_SPACING_PX,
            "group_margin_px": GROUP_MARGIN_PX,
            "group_spacing_px": GROUP_SPACING_PX,
        },
        "logger": {"name": LOGGER_NAME, "warning_format": WARNING_FORMAT},
        "warnings": list(model.warnings),
        "texts": {"no_message": NO_MESSAGE, "no_style": NO_STYLE},
        "defaults": {
            "no_view": NO_VIEW,
            "no_word_wrap": NO_WORD_WRAP,
            "error_type": DEFAULT_ERROR_TYPE,
        },
        "error_types": sorted(ERROR_TYPES),
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "call_names": list(CALL_NAMES),
        "calls": [list(call) for call in model.calls],
    }


PANE_MODEL = MarketInspectorTabModel()


def view_model(params: dict) -> dict:
    """Bridge handler for ``market_inspector_tab.state``.

    Reads ``reset``, ``bot``, ``error``, ``view`` and ``build`` from the
    request parameters, and runs ``MarketInspectorTabModel.build`` only
    once ``error`` or ``view`` has given the model a source. The tab's
    last state persists between calls because the tab does; ``reset`` is
    what a fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = MarketInspectorTabModel()
    error = params.get("error")
    driven = False
    if error is not None:
        PANE_MODEL.source = MarketInspectorSource(
            raises=error_from(
                error.get("type", DEFAULT_ERROR_TYPE), error.get("text", NO_MESSAGE)
            )
        )
        driven = True
    elif "view" in params:
        PANE_MODEL.source = MarketInspectorSource(view=params["view"])
        driven = True
    if "bot" in params:
        PANE_MODEL.bot = params["bot"]
    asked = params.get("build", driven)
    return build_view_model(PANE_MODEL, asked and PANE_MODEL.source is not None)
