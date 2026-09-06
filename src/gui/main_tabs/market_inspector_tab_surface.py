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
FALLBACK_SPACING_SET = False
FALLBACK_MARGINS_SET = False
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
        self.source = source
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
