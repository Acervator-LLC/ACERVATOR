"""launcher_surface.py -- the Launcher screen.

Describes the first screen of the application: a heading, a prompt, two
large clickable cards side by side, and a footer line. One card opens
crypto trading, the other opens stock trading.

Each card carries an icon, a title, a subtitle, a list of feature lines
and a launch button. A press anywhere on a card, or on its button, asks
the window to open that mode.

``ModeCardModel`` is one card. ``LauncherModel`` is the whole screen and
holds the two cards, the texts around them and the record of what was
pressed. ``build_view_model`` returns every value the screen holds as
one dict.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``launcher.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.launcher``, so a value changed on one side alone is reported.
Nothing here imports Qt.
"""

from __future__ import annotations

from typing import Any, Optional

from ...trading.ta_engine import DEFAULT_WEIGHTS

METHOD = "launcher.state"

LOGGER_NAME = "acervator.gui"

WINDOW_BACKGROUND = "#08080f"
CARD_BACKGROUND = "#0e0e1a"
CARD_BORDER = "#1a1a2f"
HEADING_COLOR = "#e0e0f0"
PROMPT_COLOR = "#666"
SUBTITLE_COLOR = "#888"
FEATURE_COLOR = "#aaa"
FOOTER_COLOR = "#555"
BUTTON_TEXT_COLOR = "#0a0a12"
GRADIENT_TOP_COLOR = "#0a0a14"
GRADIENT_MIDDLE_COLOR = "#08081a"
GRADIENT_BOTTOM_COLOR = "#060612"
CRYPTO_COLOR = "#00ffcc"
STOCKS_COLOR = "#00aaff"

COLORS = {
    "window_background": WINDOW_BACKGROUND,
    "card_background": CARD_BACKGROUND,
    "card_border": CARD_BORDER,
    "heading": HEADING_COLOR,
    "prompt": PROMPT_COLOR,
    "subtitle": SUBTITLE_COLOR,
    "feature": FEATURE_COLOR,
    "footer": FOOTER_COLOR,
    "button_text": BUTTON_TEXT_COLOR,
    "gradient_top": GRADIENT_TOP_COLOR,
    "gradient_middle": GRADIENT_MIDDLE_COLOR,
    "gradient_bottom": GRADIENT_BOTTOM_COLOR,
    "crypto": CRYPTO_COLOR,
    "stocks": STOCKS_COLOR,
}

WINDOW_ACCESSIBLE_NAME = "Launcher Window"
WINDOW_TITLE = "Acervator"
WINDOW_WIDTH_PX = 900
WINDOW_HEIGHT_PX = 560
WINDOW_STYLE = "background: %s;" % WINDOW_BACKGROUND
WINDOW_MARGINS_PX = (40, 30, 40, 30)
WINDOW_SPACING_PX = 20

HEADING_TEXT = "QUANTUM AUTO TRADER"
HEADING_STYLE = (
    "font-size: 28px; font-weight: bold; color: %s; letter-spacing: 4px;"
    % HEADING_COLOR
)
PROMPT_TEXT = "Select Trading Mode"
PROMPT_STYLE = "font-size: 13px; color: %s;" % PROMPT_COLOR
HEADING_GAP_PX = 10
FOOTER_TEXT = (
    "Both modes can run simultaneously  •  "
    "Shared analytics, risk management, and notifications"
)
FOOTER_STYLE = "font-size: 11px; color: %s;" % FOOTER_COLOR

CARDS_ROW_SPACING_PX = 40

ALIGN_CENTER = "AlignCenter"
ALIGN_CENTER_VALUE = 132
FEATURE_ALIGNMENT_VALUE = 129

WORD_WRAP_ON = True
WORD_WRAP_OFF = False

GRADIENT_START_PX = (0, 0)
GRADIENT_END_X_PX = 0
GRADIENT_STOPS = (
    (0.0, GRADIENT_TOP_COLOR),
    (0.5, GRADIENT_MIDDLE_COLOR),
    (1.0, GRADIENT_BOTTOM_COLOR),
)

CARD_ACCESSIBLE_NAME = "Mode Card"
CARD_CURSOR = "PointingHandCursor"
CARD_WIDTH_PX = 380
CARD_HEIGHT_PX = 420
CARD_MARGINS_PX = (30, 30, 30, 30)
CARD_SPACING_PX = 12
CARD_GAP_PX = 10

CARD_TYPE_NAME = "ModeCard"
CARD_STYLE_FORMAT = (
    "%(type)s {{ background: %(background)s; border: 2px solid %(border)s; "
    "border-radius: 16px; }}"
    "%(type)s:hover {{ border-color: {color}; }}"
) % {"type": CARD_TYPE_NAME, "background": CARD_BACKGROUND, "border": CARD_BORDER}

ICON_STYLE_FORMAT = "font-size: 64px; color: {color};"
TITLE_STYLE_FORMAT = "font-size: 24px; font-weight: bold; color: {color};"
SUBTITLE_STYLE = "font-size: 12px; color: %s;" % SUBTITLE_COLOR
FEATURE_STYLE = "font-size: 11px; color: %s;" % FEATURE_COLOR
FEATURE_TEXT_FORMAT = "  {feature}"
BUTTON_TEXT_FORMAT = "Launch {title}"
BUTTON_STYLE_FORMAT = (
    "QPushButton {{ background: {color}; color: %s; "
    "border: none; border-radius: 8px; padding: 12px; "
    "font-size: 14px; font-weight: bold; }}"
    "QPushButton:hover {{ background: {hover}; }}"
) % BUTTON_TEXT_COLOR
HOVER_COLOR_FORMAT = "{color}{suffix}"
HOVER_COLOR_SUFFIX = "cc"

SHADOW_BLUR_RADIUS_PX = 30
SHADOW_OFFSET_PX = (0, 0)
SHADOW_ATTACHED = False

CRYPTO_TITLE = "Crypto Trading"
CRYPTO_SUBTITLE = "Multi-exchange cryptocurrency trading with Grid and Scrumming bots"
CRYPTO_ICON = "₿"
#: The voter count is filled from DEFAULT_WEIGHTS, never typed in.
CRYPTO_TA_FEATURE_FORMAT = "{indicator_count}-Indicator TA Voting Engine"


def crypto_features() -> tuple[str, ...]:
    """The Crypto card's feature lines, counting the voters
    ``DEFAULT_WEIGHTS`` declares."""
    return (
        "Multi-exchange (30+ supported)",
        "Grid Bot & Scrumming Bot",
        CRYPTO_TA_FEATURE_FORMAT.format(indicator_count=len(DEFAULT_WEIGHTS)),
        "Profit Folding & Distribution",
        "Phantom Balance Bots",
        "24/7 Trading",
    )


STOCKS_TITLE = "Stock Trading"
STOCKS_SUBTITLE = "Equity trading via TradingView signals with broker integration"
STOCKS_ICON = "↑"
STOCKS_FEATURES = (
    "TradingView Webhook Signals",
    "Alpaca Broker Integration",
    "Signal, DCA, Swing & Grid Bots",
    "Market Hours Awareness",
    "Paper Trading Support",
    "Stop-Loss & Take-Profit",
)

CRYPTO_CARD = "crypto_card"
STOCKS_CARD = "stocks_card"
CARD_ORDER = (CRYPTO_CARD, STOCKS_CARD)

WINDOW_ORDER = ("heading", "prompt", "spacing", "cards_row", "footer")
CARD_HEAD_ORDER = ("icon", "title", "subtitle", "spacing")
CARD_TAIL_ORDER = ("stretch", "button")
FEATURE_SLOT_FORMAT = "feature_{position}"

NO_TEXT = ""
NO_PRESSES: tuple = ()
FIRST_CLICK_COUNT = 0

CRYPTO_SIGNAL = "crypto_selected"
STOCKS_SIGNAL = "stocks_selected"
CARD_SIGNAL = "clicked"
CARD_SIGNALS = {CRYPTO_CARD: CRYPTO_SIGNAL, STOCKS_CARD: STOCKS_SIGNAL}
SIGNALS = (
    "ModeCard.clicked",
    "LauncherWindow.crypto_selected",
    "LauncherWindow.stocks_selected",
)

ACTIONS = {
    "launch_button.clicked": "ModeCardModel.emit_clicked",
    "crypto_card.clicked": "LauncherModel.crypto_selected",
    "stocks_card.clicked": "LauncherModel.stocks_selected",
}
TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()

PRESS_CARD = "press.card"
PRESS_BUTTON = "press.button"
CARD_CLICKED = "card.clicked"
CRYPTO_SELECTED = "window.crypto_selected"
STOCKS_SELECTED = "window.stocks_selected"

ModelCall = list

CALL_NAMES = (
    PRESS_CARD,
    PRESS_BUTTON,
    CARD_CLICKED,
    CRYPTO_SELECTED,
    STOCKS_SELECTED,
)

CARD_PRESS = "card"
BUTTON_PRESS = "button"
PRESS_KINDS = (CARD_PRESS, BUTTON_PRESS)

TEXT_REFUSAL = "a label takes text or nothing, not {kind}"


def label_text(value: Any) -> str:
    """The text one label shows.

    Nothing shows an empty label. Text shows itself. Any other value is
    refused, which is what the shipped screen does when it hands the
    value to a label.
    """
    if value is None:
        return NO_TEXT
    if not isinstance(value, str):
        raise TypeError(TEXT_REFUSAL.format(kind=type(value).__name__))
    return value


def hover_color(color: Any) -> str:
    """The card colour with the hover suffix added."""
    return HOVER_COLOR_FORMAT.format(color=color, suffix=HOVER_COLOR_SUFFIX)


def card_style(color: Any) -> str:
    """The card frame's own style, whose hover border is the card colour."""
    return CARD_STYLE_FORMAT.format(color=color)


def icon_style(color: Any) -> str:
    """The icon's style, drawn in the card colour at 64 pixels."""
    return ICON_STYLE_FORMAT.format(color=color)


def title_style(color: Any) -> str:
    """The title's style, drawn bold in the card colour."""
    return TITLE_STYLE_FORMAT.format(color=color)


def button_style(color: Any) -> str:
    """The launch button's style, filled with the card colour."""
    return BUTTON_STYLE_FORMAT.format(color=color, hover=hover_color(color))


def button_text(title: Any) -> str:
    """The launch button's wording for one mode title."""
    return BUTTON_TEXT_FORMAT.format(title=title)


def feature_text(feature: Any) -> str:
    """One feature line, indented by two spaces."""
    return FEATURE_TEXT_FORMAT.format(feature=feature)


def card_child_order(feature_count: int) -> list:
    """The names of a card's children, top to bottom, for that many features."""
    slots = [
        FEATURE_SLOT_FORMAT.format(position=position)
        for position in range(feature_count)
    ]
    return list(CARD_HEAD_ORDER) + slots + list(CARD_TAIL_ORDER)


def gradient(height_px: int) -> dict:
    """The background wash, running from the top of the window to `height_px`."""
    return {
        "start_px": list(GRADIENT_START_PX),
        "end_px": [GRADIENT_END_X_PX, height_px],
        "stops": [list(stop) for stop in GRADIENT_STOPS],
    }


class ModeCardModel:
    """One large clickable card for a trading mode.

    Holds the icon, title, subtitle, feature lines and launch button of
    one mode. ``press`` is a press anywhere on the card and
    ``click_button`` a press on its button; both make the card say it
    was clicked. Whoever is listening is told, which is how the window
    learns which mode to open.
    """

    def __init__(
        self,
        title: Any,
        subtitle: Any,
        icon_char: Any,
        color: Any,
        features: Any,
    ) -> None:
        self.accessible_name = CARD_ACCESSIBLE_NAME
        self.color = color
        self.hovered = False
        self.title = title
        self.icon_text = label_text(icon_char)
        self.title_text = label_text(title)
        self.subtitle_text = label_text(subtitle)
        self.feature_texts = [feature_text(one) for one in features]
        self.button_text = button_text(title)
        self.clicks = FIRST_CLICK_COUNT
        self.listeners: list = []

    def on_clicked(self, listener) -> None:
        """Ask to be told each time this card says it was clicked."""
        self.listeners.append(listener)

    def emit_clicked(self) -> None:
        """Say this card was clicked and tell everyone listening."""
        self.clicks += 1
        for listener in self.listeners:
            listener()

    def press(self) -> None:
        """A press anywhere on the card."""
        self.emit_clicked()

    def click_button(self) -> None:
        """A press on the card's launch button."""
        self.emit_clicked()

    def state(self) -> dict:
        """Every value this card can be asked for."""
        order = card_child_order(len(self.feature_texts))
        return {
            "accessible_name": self.accessible_name,
            "type_name": CARD_TYPE_NAME,
            "cursor": CARD_CURSOR,
            "width_px": CARD_WIDTH_PX,
            "height_px": CARD_HEIGHT_PX,
            "margins_px": list(CARD_MARGINS_PX),
            "spacing_px": CARD_SPACING_PX,
            "style_sheet": card_style(self.color),
            "icon": {
                "text": self.icon_text,
                "style_sheet": icon_style(self.color),
                "alignment_value": ALIGN_CENTER_VALUE,
                "word_wrap": WORD_WRAP_OFF,
            },
            "title": {
                "text": self.title_text,
                "style_sheet": title_style(self.color),
                "alignment_value": ALIGN_CENTER_VALUE,
                "word_wrap": WORD_WRAP_OFF,
            },
            "subtitle": {
                "text": self.subtitle_text,
                "style_sheet": SUBTITLE_STYLE,
                "alignment_value": ALIGN_CENTER_VALUE,
                "word_wrap": WORD_WRAP_ON,
            },
            "gap_px": CARD_GAP_PX,
            "features": [
                {
                    "text": text,
                    "style_sheet": FEATURE_STYLE,
                    "alignment_value": FEATURE_ALIGNMENT_VALUE,
                    "word_wrap": WORD_WRAP_OFF,
                }
                for text in self.feature_texts
            ],
            "button": {
                "text": self.button_text,
                "style_sheet": button_style(self.color),
            },
            "shadow": {
                "blur_radius_px": SHADOW_BLUR_RADIUS_PX,
                "offset_px": list(SHADOW_OFFSET_PX),
                "color": self.color,
                "attached": SHADOW_ATTACHED,
            },
            "child_order": order,
            "child_count": len(order),
            "color": self.color,
            "hovered": self.hovered,
            "clicks": self.clicks,
        }


class LauncherModel:
    """The Launcher screen: a heading, a prompt, two cards and a footer.

    ``press_card`` is a press anywhere on one card and ``click_button``
    a press on that card's button. Either makes the card say it was
    clicked, and the window then says which mode to open. Every step is
    appended to ``calls`` in the order the shipped screen makes it.
    """

    def __init__(self) -> None:
        self.accessible_name = WINDOW_ACCESSIBLE_NAME
        self.window_title = WINDOW_TITLE
        self.width_px = WINDOW_WIDTH_PX
        self.height_px = WINDOW_HEIGHT_PX
        self.calls: list[ModelCall] = []
        self.cards = {
            CRYPTO_CARD: ModeCardModel(
                title=CRYPTO_TITLE,
                subtitle=CRYPTO_SUBTITLE,
                icon_char=CRYPTO_ICON,
                color=CRYPTO_COLOR,
                features=crypto_features(),
            ),
            STOCKS_CARD: ModeCardModel(
                title=STOCKS_TITLE,
                subtitle=STOCKS_SUBTITLE,
                icon_char=STOCKS_ICON,
                color=STOCKS_COLOR,
                features=STOCKS_FEATURES,
            ),
        }
        self.card_row = [self.cards[name] for name in CARD_ORDER]
        self.cards[CRYPTO_CARD].on_clicked(self.crypto_selected)
        self.cards[STOCKS_CARD].on_clicked(self.stocks_selected)

    def crypto_selected(self) -> None:
        """The window says to open crypto trading."""
        self.calls.append([CARD_CLICKED, CRYPTO_CARD])
        self.calls.append([CRYPTO_SELECTED])

    def stocks_selected(self) -> None:
        """The window says to open stock trading."""
        self.calls.append([CARD_CLICKED, STOCKS_CARD])
        self.calls.append([STOCKS_SELECTED])

    def press_card(self, index: Any) -> None:
        """A press anywhere on the card at `index` in the row."""
        card = self.card_row[index]
        self.calls.append([PRESS_CARD, index])
        card.press()

    def click_button(self, index: Any) -> None:
        """A press on the launch button of the card at `index` in the row."""
        card = self.card_row[index]
        self.calls.append([PRESS_BUTTON, index])
        card.click_button()

    def apply(self, presses) -> None:
        """Run each press in order; each is a kind and a card position."""
        for kind, index in presses:
            if kind == BUTTON_PRESS:
                self.click_button(index)
            else:
                self.press_card(index)


def build_view_model(model: LauncherModel, presses=None) -> dict:
    """Return every value the Launcher screen holds as one dict.

    `presses` runs a list of presses before the values are read, as the
    operator does when choosing a mode.
    """
    if presses:
        model.apply(presses)
    return {
        "accessible_name": model.accessible_name,
        "window": {
            "title": model.window_title,
            "width_px": model.width_px,
            "height_px": model.height_px,
            "style_sheet": WINDOW_STYLE,
            "margins_px": list(WINDOW_MARGINS_PX),
            "spacing_px": WINDOW_SPACING_PX,
        },
        "window_order": list(WINDOW_ORDER),
        "heading": {
            "text": HEADING_TEXT,
            "style_sheet": HEADING_STYLE,
            "alignment": ALIGN_CENTER,
            "alignment_value": ALIGN_CENTER_VALUE,
            "word_wrap": WORD_WRAP_OFF,
        },
        "prompt": {
            "text": PROMPT_TEXT,
            "style_sheet": PROMPT_STYLE,
            "alignment": ALIGN_CENTER,
            "alignment_value": ALIGN_CENTER_VALUE,
            "word_wrap": WORD_WRAP_OFF,
        },
        "heading_gap_px": HEADING_GAP_PX,
        "footer": {
            "text": FOOTER_TEXT,
            "style_sheet": FOOTER_STYLE,
            "alignment": ALIGN_CENTER,
            "alignment_value": ALIGN_CENTER_VALUE,
            "word_wrap": WORD_WRAP_OFF,
        },
        "cards_row": {
            "spacing_px": CARDS_ROW_SPACING_PX,
            "order": list(CARD_ORDER),
        },
        "cards": {name: card.state() for name, card in model.cards.items()},
        "card_signal": CARD_SIGNAL,
        "card_signals": dict(CARD_SIGNALS),
        "card_head_order": list(CARD_HEAD_ORDER),
        "card_tail_order": list(CARD_TAIL_ORDER),
        "feature_slot_format": FEATURE_SLOT_FORMAT,
        "background": {
            "style_sheet": WINDOW_STYLE,
            "gradient": gradient(model.height_px),
        },
        "modes": {
            CRYPTO_CARD: {
                "title": CRYPTO_TITLE,
                "subtitle": CRYPTO_SUBTITLE,
                "icon_char": CRYPTO_ICON,
                "color": CRYPTO_COLOR,
                "features": list(crypto_features()),
            },
            STOCKS_CARD: {
                "title": STOCKS_TITLE,
                "subtitle": STOCKS_SUBTITLE,
                "icon_char": STOCKS_ICON,
                "color": STOCKS_COLOR,
                "features": list(STOCKS_FEATURES),
            },
        },
        "colors": dict(COLORS),
        "formats": {
            "card_style": CARD_STYLE_FORMAT,
            "icon_style": ICON_STYLE_FORMAT,
            "title_style": TITLE_STYLE_FORMAT,
            "button_style": BUTTON_STYLE_FORMAT,
            "button_text": BUTTON_TEXT_FORMAT,
            "feature_text": FEATURE_TEXT_FORMAT,
            "hover_color": HOVER_COLOR_FORMAT,
            "text_refusal": TEXT_REFUSAL,
        },
        "styles": {
            "window": WINDOW_STYLE,
            "heading": HEADING_STYLE,
            "prompt": PROMPT_STYLE,
            "footer": FOOTER_STYLE,
            "subtitle": SUBTITLE_STYLE,
            "feature": FEATURE_STYLE,
        },
        "hover_color_suffix": HOVER_COLOR_SUFFIX,
        "alignments": {
            "center": ALIGN_CENTER,
            "center_value": ALIGN_CENTER_VALUE,
            "feature_value": FEATURE_ALIGNMENT_VALUE,
        },
        "word_wrap": {"on": WORD_WRAP_ON, "off": WORD_WRAP_OFF},
        "no_text": NO_TEXT,
        "no_presses": list(NO_PRESSES),
        "first_click_count": FIRST_CLICK_COUNT,
        "press_kinds": list(PRESS_KINDS),
        "signals": list(SIGNALS),
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "call_names": list(CALL_NAMES),
        "calls": [list(call) for call in model.calls],
    }


SCREEN_MODEL = LauncherModel()


def view_model(params: dict) -> dict:
    """Bridge handler for ``launcher.state``.

    Reads ``reset`` and ``presses`` from the request parameters. The
    screen's click counts persist between calls because the screen does;
    ``reset`` is what a fresh paint sends. Each press is a kind and a
    card position, such as ``["card", 0]`` or ``["button", 1]``.
    """
    global SCREEN_MODEL
    if params.get("reset", False):
        SCREEN_MODEL = LauncherModel()
    presses: Optional[list] = params.get("presses")
    return build_view_model(SCREEN_MODEL, presses)
