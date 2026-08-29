"""instance_consent_surface.py -- the instance consent view model.

Describes the modal the launch raises when the instance guard refuses to
start the saved fleet by itself: the window, its skin, the headline, the
detail line, the two-line fact block, the consequence line and the two
answer buttons. It also holds the rules the dialog sits behind -- the
answer a closed window means, the answer a dialog that cannot be drawn
means, and the release order the owner follows once it has the answer.

Two answers leave this surface. ``True`` means the operator took
ownership and authorised the fleet. ``False`` means every other way out:
the refuse button, the Escape key, the window close button, and a dialog
that failed to build. ``False`` is the value the surface is born with, so
no path that skips the operator can start a bot.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``instance_consent.state`` method, which is how the Electron
renderer reaches it. Nothing here imports Qt, and it sits beside the
other surfaces rather than beside ``instance_consent_dialog.py`` because
that module imports Qt at the top.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Callable, Optional

from .. import design_system as ds

logger = logging.getLogger("acervator.gui.instance_consent")

METHOD = "instance_consent.state"

LOGGER_NAME = "acervator.gui.instance_consent"

ACCESSIBLE_NAME = "Instance Consent Dialog"
WINDOW_TITLE = "Acervator - start the saved fleet?"
MODAL = True
MINIMUM_WIDTH_PX = 560
DEFAULT_SIZE_PX = (640, 480)
STAYS_ON_TOP = False

SURFACE_COLOR = ds.SURFACE_3
FACTS_SURFACE = ds.SURFACE_1
BUTTON_SURFACE = ds.SURFACE_2
TEXT_HIGH_COLOR = ds.TEXT_HIGH
TEXT_MED_COLOR = ds.TEXT_MED
HEADLINE_COLOR = ds.WARNING
CONSEQUENCE_COLOR = ds.DANGER
REFUSE_COLOR = ds.PRIMARY
CONSENT_COLOR = ds.DANGER
OUTLINE_COLOR = ds.OUTLINE
FOCUS_RING_COLOR = ds.FOCUS_RING_COLOR

SKIN = {
    "surface": SURFACE_COLOR,
    "facts_surface": FACTS_SURFACE,
    "button_surface": BUTTON_SURFACE,
    "text_high": TEXT_HIGH_COLOR,
    "text_med": TEXT_MED_COLOR,
    "headline": HEADLINE_COLOR,
    "consequence": CONSEQUENCE_COLOR,
    "refuse": REFUSE_COLOR,
    "consent": CONSENT_COLOR,
    "outline": OUTLINE_COLOR,
    "focus_ring": FOCUS_RING_COLOR,
}

STYLE_SHEET = (
    f"QDialog {{ background: {ds.SURFACE_3}; color: {ds.TEXT_HIGH}; }}"
    f"QLabel {{ color: {ds.TEXT_MED};"
    f" font-family: {ds.FONT_FAMILY_UI};"
    f" font-size: {ds.TYPE_BODY}px; }}"
    f"QLabel#headline {{ color: {ds.WARNING};"
    f" font-size: {ds.TYPE_H3}px;"
    f" font-weight: {ds.WEIGHT_BOLD}; }}"
    f"QLabel#detail {{ color: {ds.TEXT_HIGH}; }}"
    f"QLabel#fact {{ color: {ds.TEXT_HIGH};"
    f" font-family: {ds.FONT_FAMILY_MONO};"
    f" font-size: {ds.TYPE_SMALL}px; }}"
    f"QLabel#consequence {{ color: {ds.DANGER}; }}"
    f"QFrame#facts {{ background: {ds.SURFACE_1};"
    f" border: 1px solid {ds.OUTLINE};"
    f" border-radius: {ds.RADIUS_SM}px; }}"
    f"QPushButton {{ background: {ds.SURFACE_2};"
    f" color: {ds.TEXT_HIGH};"
    f" border: 1px solid {ds.OUTLINE};"
    f" border-radius: {ds.RADIUS_SM}px;"
    f" padding: {ds.SPACE_S}px {ds.SPACE_L}px;"
    f" font-family: {ds.FONT_FAMILY_UI};"
    f" font-size: {ds.TYPE_BODY}px; }}"
    f"QPushButton#refuse {{ border: {ds.FOCUS_RING_WIDTH}px solid"
    f" {ds.PRIMARY}; color: {ds.PRIMARY}; }}"
    f"QPushButton#consent {{ color: {ds.DANGER};"
    f" border: 1px solid {ds.DANGER}; }}"
    f"QPushButton:focus {{ outline: none;"
    f" border: {ds.FOCUS_RING_WIDTH}px solid {ds.FOCUS_RING_COLOR}; }}"
)

WIDGET = {
    "accessible_name": ACCESSIBLE_NAME,
    "window_title": WINDOW_TITLE,
    "modal": MODAL,
    "minimum_width_px": MINIMUM_WIDTH_PX,
    "size_px": list(DEFAULT_SIZE_PX),
    "style_sheet": STYLE_SHEET,
    "stays_on_top": STAYS_ON_TOP,
}

HEADLINE = "headline"
DETAIL = "detail"
FACTS = "facts"
CONSEQUENCE = "consequence"
BUTTON_ROW = "button_row"

OWNER = "owner"
THIS_MACHINE = "this_machine"
FACT_OBJECT_NAME = "fact"

STRETCH = "stretch"
REFUSE = "refuse"
CONSENT = "consent"

LAYOUT_MARGINS_PX = [ds.SPACE_L, ds.SPACE_L, ds.SPACE_L, ds.SPACE_L]
LAYOUT_SPACING_PX = ds.SPACE_M
FACTS_MARGINS_PX = [ds.SPACE_M, ds.SPACE_M, ds.SPACE_M, ds.SPACE_M]
FACTS_SPACING_PX = ds.SPACE_S
BUTTON_ROW_MARGINS_PX = [0, 0, 0, 0]
BUTTON_ROW_SPACING_PX = ds.SPACE_M

LAYOUT = {
    "margins_px": list(LAYOUT_MARGINS_PX),
    "spacing_px": LAYOUT_SPACING_PX,
    "order": [HEADLINE, DETAIL, FACTS, CONSEQUENCE, BUTTON_ROW],
    "child_stretch": [0, 0, 0, 0, 0],
}

FACTS_LAYOUT = {
    "margins_px": list(FACTS_MARGINS_PX),
    "spacing_px": FACTS_SPACING_PX,
    "order": [OWNER, THIS_MACHINE],
    "child_stretch": [0, 0],
}

BUTTON_ROW_LAYOUT = {
    "margins_px": list(BUTTON_ROW_MARGINS_PX),
    "spacing_px": BUTTON_ROW_SPACING_PX,
    "order": [STRETCH, REFUSE, CONSENT],
    "child_stretch": [1, 0, 0],
}

STRETCH_WEIGHT = 1

WORD_WRAP = True
PLAIN_TEXT_INTERACTION = "LinksAccessibleByMouse"
PLAIN_TEXT_INTERACTION_VALUE = 4
SELECTABLE_TEXT_INTERACTION = "TextSelectableByMouse"
SELECTABLE_TEXT_INTERACTION_VALUE = 1

HEADLINE_LABEL = {
    "object_name": HEADLINE,
    "word_wrap": WORD_WRAP,
    "text_interaction": PLAIN_TEXT_INTERACTION,
    "text_interaction_value": PLAIN_TEXT_INTERACTION_VALUE,
}

DETAIL_LABEL = {
    "object_name": DETAIL,
    "word_wrap": WORD_WRAP,
    "text_interaction": PLAIN_TEXT_INTERACTION,
    "text_interaction_value": PLAIN_TEXT_INTERACTION_VALUE,
}

FACT_LABEL = {
    "object_name": FACT_OBJECT_NAME,
    "word_wrap": WORD_WRAP,
    "text_interaction": SELECTABLE_TEXT_INTERACTION,
    "text_interaction_value": SELECTABLE_TEXT_INTERACTION_VALUE,
}

CONSEQUENCE_LABEL = {
    "object_name": CONSEQUENCE,
    "word_wrap": WORD_WRAP,
    "text_interaction": PLAIN_TEXT_INTERACTION,
    "text_interaction_value": PLAIN_TEXT_INTERACTION_VALUE,
}

FACTS_FRAME = {"object_name": FACTS}

REFUSE_TEXT = "Do not start bots"
CONSENT_TEXT_FORMAT = "Take ownership and start {count} bot(s)"

BUTTON_MINIMUM_HEIGHT_PX = ds.TARGET_LARGE

REFUSE_IS_DEFAULT = True
CONSENT_IS_DEFAULT = False

REFUSE_ENABLED = True

CONSENT_BLOCKED_TOOLTIP = (
    "Another Acervator holds the exclusive handle on this " "directory. Close it first."
)
NO_TOOLTIP = ""

FOCUS_ON = REFUSE

ACTIONS = {
    "refuse.clicked": "refuse",
    "consent.clicked": "consent",
}

ANSWER_CONSENT = True
ANSWER_REFUSE = False

ANSWERS = (ANSWER_CONSENT, ANSWER_REFUSE)
BUTTON_ANSWERS = {REFUSE: ANSWER_REFUSE, CONSENT: ANSWER_CONSENT}

DEFAULT_ANSWER = ANSWER_REFUSE
CLOSED_ANSWER = ANSWER_REFUSE
BUILD_FAILED_ANSWER = ANSWER_REFUSE

TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()

MISSING_VERDICT = "unknown"
MISSING_BOT_COUNT = 0

REFUSE_LOG = (
    "instance consent: operator DECLINED to start the fleet on "
    "this machine (verdict %s)"
)
CONSENT_LOG = (
    "instance consent: operator GRANTED ownership to this machine "
    "and authorised %s bot(s) (verdict %s)"
)
RELEASE_LOG = "instance consent dialog was already destroyed: %s"
BUILD_FAILED_LOG = (
    "instance consent dialog could not be shown (%s). Treating "
    "this as a refusal: no bot starts without a surface the "
    "operator can read."
)

DIALOG_CONSENTED = "dialog.consented"
DIALOG_SET_ACCESSIBLE_NAME = "dialog.setAccessibleName"
DIALOG_SET_WINDOW_TITLE = "dialog.setWindowTitle"
DIALOG_SET_MODAL = "dialog.setModal"
DIALOG_SET_MINIMUM_WIDTH = "dialog.setMinimumWidth"
DIALOG_SET_STYLE_SHEET = "dialog.setStyleSheet"
LAYOUT_CREATE = "layout.create"
LAYOUT_SET_MARGINS = "layout.setContentsMargins"
LAYOUT_SET_SPACING = "layout.setSpacing"
LAYOUT_ADD_WIDGET = "layout.addWidget"
LAYOUT_ADD_LAYOUT = "layout.addLayout"
FACTS_CREATE = "facts.create"
FACTS_SET_OBJECT_NAME = "facts.setObjectName"
FACTS_LAYOUT_CREATE = "facts_layout.create"
FACTS_LAYOUT_SET_MARGINS = "facts_layout.setContentsMargins"
FACTS_LAYOUT_SET_SPACING = "facts_layout.setSpacing"
FACTS_LAYOUT_ADD_WIDGET = "facts_layout.addWidget"
ROW_CREATE = "row.create"
ROW_SET_SPACING = "row.setSpacing"
ROW_ADD_STRETCH = "row.addStretch"
ROW_ADD_WIDGET = "row.addWidget"
LABEL_CREATE = "label.create"
LABEL_SET_OBJECT_NAME = "label.setObjectName"
LABEL_SET_WORD_WRAP = "label.setWordWrap"
LABEL_SET_TEXT_INTERACTION = "label.setTextInteractionFlags"
BUTTON_CREATE = "button.create"
BUTTON_SET_OBJECT_NAME = "button.setObjectName"
BUTTON_SET_MINIMUM_HEIGHT = "button.setMinimumHeight"
BUTTON_SET_DEFAULT = "button.setDefault"
BUTTON_SET_AUTO_DEFAULT = "button.setAutoDefault"
BUTTON_SET_ENABLED = "button.setEnabled"
BUTTON_SET_TOOL_TIP = "button.setToolTip"
BUTTON_SET_FOCUS = "button.setFocus"
DIALOG_ACCEPT = "dialog.accept"
DIALOG_REJECT = "dialog.reject"
DIALOG_EXEC = "dialog.exec"
DIALOG_CLOSE = "dialog.close"
DIALOG_SET_PARENT = "dialog.setParent"

ModelCall = list[object]


def rgb(colour: str) -> tuple[int, int, int]:
    """Split a colour token into its three 0-255 channels.

    Accepts ``#rgb`` and ``#rrggbb``, which is every form the skin uses.
    """
    digits = colour.lstrip("#")
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    return (
        int(digits[0:2], 16),
        int(digits[2:4], 16),
        int(digits[4:6], 16),
    )


def bot_count(value: Any) -> int:
    """The number the consent button carries.

    Mirrors the dialog's own coercion: a falsy count becomes zero, and
    anything else is read as a whole number.
    """
    return int(value or 0)


def consent_text(count: int) -> str:
    """The consent button's label, carrying its own bot count."""
    return CONSENT_TEXT_FORMAT.format(count=count)


def decision_facts(**fields: Any) -> SimpleNamespace:
    """A stand-in guard decision carrying only what the surface reads."""
    return SimpleNamespace(**fields)


class InstanceConsentModel:
    """The consent dialog's texts, its answer and its release order.

    ``build`` walks the window the launch raises. ``refuse`` and
    ``consent`` press the two buttons. ``close_window`` is the Escape key
    and the window close button. Every change is also appended to
    ``calls`` in the order the Qt dialog makes it, so a caller can replay
    the same sequence on a widget it owns.
    """

    def __init__(self) -> None:
        self.decision: Any = None
        self._consented = DEFAULT_ANSWER
        self.headline_text = ""
        self.detail_text = ""
        self.owner_text = ""
        self.this_machine_text = ""
        self.consequence_text = ""
        self.refuse_text = REFUSE_TEXT
        self.consent_button_text = ""
        self.consent_enabled = True
        self.consent_tool_tip = NO_TOOLTIP
        self.button_bot_count = MISSING_BOT_COUNT
        self.built = False
        self.released = False
        self.calls: list[ModelCall] = []

    @property
    def consented(self) -> bool:
        """True only when the operator pressed the ownership button."""
        return self._consented

    def build(self, decision: Any) -> None:
        """Build the window and its seven children, in the dialog's order.

        Every text comes off ``decision`` at the point the dialog reads
        it, so a decision whose line raises stops both sides after the
        same call. The refuse answer is armed first, and the consent
        button is disabled when the guard says consent cannot be offered.
        """
        self.decision = decision
        self._consented = DEFAULT_ANSWER
        self.built = False
        self.calls.extend(
            [
                [DIALOG_CONSENTED, DEFAULT_ANSWER],
                [DIALOG_SET_ACCESSIBLE_NAME, ACCESSIBLE_NAME],
                [DIALOG_SET_WINDOW_TITLE, WINDOW_TITLE],
                [DIALOG_SET_MODAL, MODAL],
                [DIALOG_SET_MINIMUM_WIDTH, MINIMUM_WIDTH_PX],
                [DIALOG_SET_STYLE_SHEET, STYLE_SHEET],
                [LAYOUT_CREATE],
                [LAYOUT_SET_MARGINS, list(LAYOUT_MARGINS_PX)],
                [LAYOUT_SET_SPACING, LAYOUT_SPACING_PX],
            ]
        )
        self.headline_text = str(decision.headline)
        self.calls.extend(
            [
                [LABEL_CREATE, HEADLINE, self.headline_text],
                [LABEL_SET_OBJECT_NAME, HEADLINE, HEADLINE],
                [LABEL_SET_WORD_WRAP, HEADLINE, WORD_WRAP],
                [LAYOUT_ADD_WIDGET, HEADLINE],
            ]
        )
        self.detail_text = str(decision.detail)
        self.calls.extend(
            [
                [LABEL_CREATE, DETAIL, self.detail_text],
                [LABEL_SET_OBJECT_NAME, DETAIL, DETAIL],
                [LABEL_SET_WORD_WRAP, DETAIL, WORD_WRAP],
                [LAYOUT_ADD_WIDGET, DETAIL],
                [FACTS_CREATE],
                [FACTS_SET_OBJECT_NAME, FACTS],
                [FACTS_LAYOUT_CREATE],
                [FACTS_LAYOUT_SET_MARGINS, list(FACTS_MARGINS_PX)],
                [FACTS_LAYOUT_SET_SPACING, FACTS_SPACING_PX],
            ]
        )
        self.owner_text = str(decision.owner_line)
        self.this_machine_text = str(decision.this_machine_line)
        for name, text in (
            (OWNER, self.owner_text),
            (THIS_MACHINE, self.this_machine_text),
        ):
            self.calls.extend(
                [
                    [LABEL_CREATE, name, text],
                    [LABEL_SET_OBJECT_NAME, name, FACT_OBJECT_NAME],
                    [LABEL_SET_WORD_WRAP, name, WORD_WRAP],
                    [LABEL_SET_TEXT_INTERACTION, name, SELECTABLE_TEXT_INTERACTION],
                    [FACTS_LAYOUT_ADD_WIDGET, name],
                ]
            )
        self.calls.append([LAYOUT_ADD_WIDGET, FACTS])
        self.consequence_text = str(decision.consequence_line)
        self.calls.extend(
            [
                [LABEL_CREATE, CONSEQUENCE, self.consequence_text],
                [LABEL_SET_OBJECT_NAME, CONSEQUENCE, CONSEQUENCE],
                [LABEL_SET_WORD_WRAP, CONSEQUENCE, WORD_WRAP],
                [LAYOUT_ADD_WIDGET, CONSEQUENCE],
                [ROW_CREATE],
                [ROW_SET_SPACING, BUTTON_ROW_SPACING_PX],
                [ROW_ADD_STRETCH, STRETCH_WEIGHT],
                [BUTTON_CREATE, REFUSE, REFUSE_TEXT],
                [BUTTON_SET_OBJECT_NAME, REFUSE, REFUSE],
                [BUTTON_SET_MINIMUM_HEIGHT, REFUSE, BUTTON_MINIMUM_HEIGHT_PX],
                [BUTTON_SET_DEFAULT, REFUSE, REFUSE_IS_DEFAULT],
                [BUTTON_SET_AUTO_DEFAULT, REFUSE, REFUSE_IS_DEFAULT],
                [ROW_ADD_WIDGET, REFUSE],
            ]
        )
        self.button_bot_count = bot_count(
            getattr(decision, "fleet_bot_count", MISSING_BOT_COUNT)
        )
        self.consent_button_text = consent_text(self.button_bot_count)
        self.calls.extend(
            [
                [BUTTON_CREATE, CONSENT, self.consent_button_text],
                [BUTTON_SET_OBJECT_NAME, CONSENT, CONSENT],
                [BUTTON_SET_MINIMUM_HEIGHT, CONSENT, BUTTON_MINIMUM_HEIGHT_PX],
                [BUTTON_SET_DEFAULT, CONSENT, CONSENT_IS_DEFAULT],
                [BUTTON_SET_AUTO_DEFAULT, CONSENT, CONSENT_IS_DEFAULT],
            ]
        )
        self.consent_enabled = bool(decision.consent_is_possible)
        self.consent_tool_tip = NO_TOOLTIP
        if not self.consent_enabled:
            self.consent_tool_tip = CONSENT_BLOCKED_TOOLTIP
            self.calls.append([BUTTON_SET_ENABLED, CONSENT, False])
            self.calls.append([BUTTON_SET_TOOL_TIP, CONSENT, CONSENT_BLOCKED_TOOLTIP])
        self.calls.extend(
            [
                [ROW_ADD_WIDGET, CONSENT],
                [LAYOUT_ADD_LAYOUT, BUTTON_ROW],
                [BUTTON_SET_FOCUS, FOCUS_ON],
            ]
        )
        self.built = True

    def refuse(self) -> None:
        """Press the refuse button: clear the answer, log it, reject."""
        self._consented = ANSWER_REFUSE
        self.calls.append([DIALOG_CONSENTED, ANSWER_REFUSE])
        logger.warning(
            REFUSE_LOG,
            getattr(self.decision, "verdict", MISSING_VERDICT),
        )
        self.close_window()

    def consent(self) -> None:
        """Press the ownership button: keep the answer, log it, accept."""
        self._consented = ANSWER_CONSENT
        self.calls.append([DIALOG_CONSENTED, ANSWER_CONSENT])
        logger.warning(
            CONSENT_LOG,
            getattr(self.decision, "fleet_bot_count", MISSING_BOT_COUNT),
            getattr(self.decision, "verdict", MISSING_VERDICT),
        )
        self.calls.append([DIALOG_ACCEPT])

    def close_window(self) -> None:
        """Escape and the window close button land here, and both mean no."""
        self._consented = CLOSED_ANSWER
        self.calls.append([DIALOG_CONSENTED, CLOSED_ANSWER])
        self.calls.append([DIALOG_REJECT])

    def close(self) -> None:
        """Hide the surface. Stands in for the dialog's inherited close."""
        self.calls.append([DIALOG_CLOSE])

    def set_parent(self, parent: Any = None) -> None:
        """Detach the surface. Stands in for the inherited setParent."""
        self.calls.append([DIALOG_SET_PARENT, parent])
        self.released = True


def release_model(model: Optional[Any]) -> None:
    """Destroy the surface now, in the dialog's own two steps.

    A surface that is already gone is reported at debug level and
    nothing is lost, because the answer is read before this call.
    """
    if model is None:
        return
    try:
        model.close()
        model.set_parent(None)
    except RuntimeError as exc:
        logger.debug(RELEASE_LOG, exc)


def ask_model_for_consent(
    decision: Any,
    button: Optional[str] = None,
    closed: bool = False,
    factory: Optional[Callable[[], Any]] = None,
) -> bool:
    """Raise the surface and return True only on an explicit grant.

    Any failure to build returns False. A consent surface that cannot be
    drawn has collected no consent, and the caller must treat that
    exactly as a refusal.

    The answer is read into a local first, the surface is released
    second, and the local is returned third. A surface that never got
    built is never released.
    """
    model: Optional[Any] = None
    build = InstanceConsentModel if factory is None else factory
    try:
        model = build()
        model.build(decision)
        model.calls.append([DIALOG_EXEC])
        if closed:
            model.close_window()
        elif button is not None:
            BUTTON_ACTS[button](model)
        granted = bool(model.consented)
    except Exception as exc:
        logger.error(BUILD_FAILED_LOG, exc)
        granted = BUILD_FAILED_ANSWER
    finally:
        release_model(model)
    return granted


BUTTON_ACTS: dict[str, Callable[[Any], None]] = {
    REFUSE: InstanceConsentModel.refuse,
    CONSENT: InstanceConsentModel.consent,
}

PANE_MODEL = InstanceConsentModel()


def build_view_model(
    model: InstanceConsentModel,
    headline: str = "",
    detail: str = "",
    owner_line: str = "",
    this_machine_line: str = "",
    consequence_line: str = "",
    fleet_bot_count: Any = 0,
    consent_is_possible: bool = True,
    verdict: str = MISSING_VERDICT,
    button: Optional[str] = None,
    closed: bool = False,
) -> dict:
    """Return the whole surface state as one serialisable dict."""
    model.build(
        decision_facts(
            headline=headline,
            detail=detail,
            owner_line=owner_line,
            this_machine_line=this_machine_line,
            consequence_line=consequence_line,
            fleet_bot_count=fleet_bot_count,
            consent_is_possible=consent_is_possible,
            verdict=verdict,
        )
    )
    if closed:
        model.close_window()
    elif button is not None:
        BUTTON_ACTS[button](model)
    return {
        "widget": dict(WIDGET),
        "layout": dict(LAYOUT),
        "facts_layout": dict(FACTS_LAYOUT),
        "button_row": dict(BUTTON_ROW_LAYOUT),
        "headline_label": dict(HEADLINE_LABEL),
        "detail_label": dict(DETAIL_LABEL),
        "fact_label": dict(FACT_LABEL),
        "consequence_label": dict(CONSEQUENCE_LABEL),
        "facts_frame": dict(FACTS_FRAME),
        "buttons": {
            REFUSE: {
                "text": model.refuse_text,
                "enabled": REFUSE_ENABLED,
                "is_default": REFUSE_IS_DEFAULT,
                "minimum_height_px": BUTTON_MINIMUM_HEIGHT_PX,
                "tool_tip": NO_TOOLTIP,
            },
            CONSENT: {
                "text": model.consent_button_text,
                "enabled": model.consent_enabled,
                "is_default": CONSENT_IS_DEFAULT,
                "minimum_height_px": BUTTON_MINIMUM_HEIGHT_PX,
                "tool_tip": model.consent_tool_tip,
            },
        },
        "actions": dict(ACTIONS),
        "answers": list(ANSWERS),
        "button_answers": dict(BUTTON_ANSWERS),
        "default_answer": DEFAULT_ANSWER,
        "closed_answer": CLOSED_ANSWER,
        "build_failed_answer": BUILD_FAILED_ANSWER,
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "focus_on": FOCUS_ON,
        "headline_text": model.headline_text,
        "detail_text": model.detail_text,
        "owner_text": model.owner_text,
        "this_machine_text": model.this_machine_text,
        "consequence_text": model.consequence_text,
        "button_bot_count": model.button_bot_count,
        "consented": model.consented,
        "built": model.built,
        "released": model.released,
        "calls": [list(call) for call in model.calls],
        "skin": {name: list(rgb(token)) for name, token in SKIN.items()},
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``instance_consent.state``.

    Reads ``reset``, the eight decision fields, ``button`` and ``closed``
    from the request parameters. The answer persists between calls
    because the dialog's own does; ``reset`` is what a fresh launch
    sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = InstanceConsentModel()
    return build_view_model(
        PANE_MODEL,
        params.get("headline", ""),
        params.get("detail", ""),
        params.get("owner_line", ""),
        params.get("this_machine_line", ""),
        params.get("consequence_line", ""),
        params.get("fleet_bot_count", 0),
        params.get("consent_is_possible", True),
        params.get("verdict", MISSING_VERDICT),
        params.get("button"),
        params.get("closed", False),
    )
