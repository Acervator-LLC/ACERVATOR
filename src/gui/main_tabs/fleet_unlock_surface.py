# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The unlock screen's one declaration, read by the Qt build and the drawn build.

``src/gui/fleet_unlock_dialog.py`` builds the Qt widgets from the names here and
``src/gui/web/fleet_unlock.js`` draws the payload ``view_model`` serves over
``METHOD``, so one module holds every word, size and colour of the screen.
``unlock_outcome`` is the whole decision about a typed value, and
``main_window_surface`` holds the sentences the Console already carries.
"""

from __future__ import annotations

import logging
from typing import Any

from .. import design_system as ds
from . import main_window_surface as mws

logger = logging.getLogger("acervator.gui.fleet_unlock")

METHOD = "fleet_unlock.state"

LOGGER_NAME = "acervator.gui.fleet_unlock"

ACCESSIBLE_NAME = "Fleet Unlock Dialog"
WINDOW_TITLE = "Acervator - the saved fleet is sealed"
MODAL = True
MINIMUM_WIDTH_PX = 560

HEADLINE_TEXT = "The saved fleet is sealed."
DETAIL_TEXT = mws.FLEET_LOCKED_TEXT
PHRASE_LABEL = "Password:"
PHRASE_PLACEHOLDER = "The password you set in Settings"
PHRASE_DESCRIPTION = "Opens the sealed fleet. Nothing on this computer can recover it."
REFUSED_TEXT = mws.FLEET_UNLOCK_REFUSED_TEXT
NO_WINDOW_TEXT = mws.FLEET_UNLOCK_NO_READER_TEXT
RESTING_TEXT = ""

DISMISS_TEXT = "Not now"
DISMISS_DESCRIPTION = "Leaves the fleet sealed. Open this screen again from Settings."
UNLOCK_TEXT = "Unlock the fleet"
UNLOCK_DESCRIPTION = "Gives the password to the saved fleet and loads every bot."
UNLOCK_BLOCKED_DESCRIPTION = "Type the password first. An empty row reaches no key."

HEADLINE = "headline"
DETAIL = "detail"
PHRASE = "phrase"
FEEDBACK = "feedback"
DISMISS = "dismiss"
UNLOCK = "unlock"
BUTTON_ROW = "button_row"

SURFACE_COLOR = ds.SURFACE_3
TEXT_HIGH_COLOR = ds.TEXT_HIGH
TEXT_MED_COLOR = ds.TEXT_MED
HEADLINE_COLOR = ds.WARNING
FEEDBACK_COLOR = ds.DANGER
DISMISS_COLOR = ds.PRIMARY
UNLOCK_COLOR = ds.SUCCESS
INPUT_SURFACE = ds.SURFACE_INPUT
OUTLINE_COLOR = ds.OUTLINE
FOCUS_RING_COLOR = ds.FOCUS_RING_COLOR
BORDER_WIDTH_PX = 1

SKIN = {
    "surface": SURFACE_COLOR,
    "text_high": TEXT_HIGH_COLOR,
    "text_med": TEXT_MED_COLOR,
    "headline": HEADLINE_COLOR,
    "feedback": FEEDBACK_COLOR,
    "dismiss": DISMISS_COLOR,
    "unlock": UNLOCK_COLOR,
    "input": INPUT_SURFACE,
    "outline": OUTLINE_COLOR,
    "focus_ring": FOCUS_RING_COLOR,
}

STYLE_SHEET = (
    f"QDialog {{ background: {SURFACE_COLOR}; color: {TEXT_HIGH_COLOR}; }}"
    f"QLabel {{ color: {TEXT_MED_COLOR};"
    f" font-family: {ds.FONT_FAMILY_UI};"
    f" font-size: {ds.TYPE_BODY}px; }}"
    f"QLabel#{HEADLINE} {{ color: {HEADLINE_COLOR};"
    f" font-size: {ds.TYPE_H3}px;"
    f" font-weight: {ds.WEIGHT_BOLD}; }}"
    f"QLabel#{DETAIL} {{ color: {TEXT_HIGH_COLOR}; }}"
    f"QLabel#{FEEDBACK} {{ color: {FEEDBACK_COLOR}; }}"
    f"QLineEdit#{PHRASE} {{ background: {INPUT_SURFACE};"
    f" color: {TEXT_HIGH_COLOR};"
    f" border: {BORDER_WIDTH_PX}px solid {OUTLINE_COLOR};"
    f" border-radius: {ds.RADIUS_SM}px;"
    f" padding: {ds.SPACE_S}px; }}"
    f"QPushButton {{ background: {ds.SURFACE_2};"
    f" color: {TEXT_HIGH_COLOR};"
    f" border: {BORDER_WIDTH_PX}px solid {OUTLINE_COLOR};"
    f" border-radius: {ds.RADIUS_SM}px;"
    f" padding: {ds.SPACE_S}px {ds.SPACE_L}px;"
    f" font-family: {ds.FONT_FAMILY_UI};"
    f" font-size: {ds.TYPE_BODY}px; }}"
    f"QPushButton#{DISMISS} {{ border: {ds.FOCUS_RING_WIDTH}px solid"
    f" {DISMISS_COLOR}; color: {DISMISS_COLOR}; }}"
    f"QPushButton#{UNLOCK} {{ color: {UNLOCK_COLOR};"
    f" border: {BORDER_WIDTH_PX}px solid {UNLOCK_COLOR}; }}"
    f"QPushButton:focus {{ outline: none;"
    f" border: {ds.FOCUS_RING_WIDTH}px solid {FOCUS_RING_COLOR}; }}"
)

WIDGET = {
    "accessible_name": ACCESSIBLE_NAME,
    "window_title": WINDOW_TITLE,
    "modal": MODAL,
    "minimum_width_px": MINIMUM_WIDTH_PX,
    "style_sheet": STYLE_SHEET,
}

LAYOUT_MARGINS_PX = [ds.SPACE_L, ds.SPACE_L, ds.SPACE_L, ds.SPACE_L]
LAYOUT_SPACING_PX = ds.SPACE_M
BUTTON_ROW_MARGINS_PX = [0, 0, 0, 0]
BUTTON_ROW_SPACING_PX = ds.SPACE_M

LAYOUT = {
    "margins_px": LAYOUT_MARGINS_PX,
    "spacing_px": LAYOUT_SPACING_PX,
}

BUTTON_ROW_LAYOUT = {
    "margins_px": BUTTON_ROW_MARGINS_PX,
    "spacing_px": BUTTON_ROW_SPACING_PX,
}

WORD_WRAP = True
ECHO_HIDDEN = True
STRETCH_WEIGHT = 1
BUTTON_MINIMUM_HEIGHT_PX = ds.TARGET_LARGE

HEADLINE_LABEL = {"object_name": HEADLINE, "word_wrap": WORD_WRAP}
DETAIL_LABEL = {"object_name": DETAIL, "word_wrap": WORD_WRAP}
FEEDBACK_LABEL = {"object_name": FEEDBACK, "word_wrap": WORD_WRAP}
PHRASE_ROW = {
    "object_name": PHRASE,
    "label": PHRASE_LABEL,
    "placeholder": PHRASE_PLACEHOLDER,
    "echo_hidden": ECHO_HIDDEN,
    "description": PHRASE_DESCRIPTION,
}

DISMISS_IS_DEFAULT = True
UNLOCK_IS_DEFAULT = False
FOCUS_ON = PHRASE

ANSWER_UNLOCKED = True
ANSWER_SEALED = False

ANSWERS = (ANSWER_UNLOCKED, ANSWER_SEALED)
BUTTON_ANSWERS = {DISMISS: ANSWER_SEALED, UNLOCK: ANSWER_UNLOCKED}

DEFAULT_ANSWER = ANSWER_SEALED
CLOSED_ANSWER = ANSWER_SEALED
BUILD_FAILED_ANSWER = ANSWER_SEALED

ACTIONS = {
    "dismiss.clicked": DISMISS,
    "unlock.clicked": UNLOCK,
    "phrase.textChanged": PHRASE,
}

OUTCOME_EMPTY = "empty"
OUTCOME_REFUSED = "refused"
OUTCOME_OPENED = "opened"
OUTCOME_NO_WINDOW = "no_window"

OUTCOME_WORDS = {
    OUTCOME_EMPTY: RESTING_TEXT,
    OUTCOME_REFUSED: REFUSED_TEXT,
    OUTCOME_OPENED: RESTING_TEXT,
    OUTCOME_NO_WINDOW: NO_WINDOW_TEXT,
}

DISMISSED_LOG = "fleet unlock: operator left the saved fleet sealed"
REFUSED_LOG = "fleet unlock: the password did not open the sealed master key"
OPENED_LOG = "fleet unlock: the saved fleet is open and the fleet start has run"
NO_WINDOW_LOG = (
    "fleet unlock: no window answering unlock_fleet was given, so the password "
    "reached nothing"
)
BUILD_FAILED_LOG = (
    "fleet unlock screen could not be shown (%s). The fleet stays sealed and "
    "no bot is loaded."
)
RELEASE_LOG = "fleet unlock screen was already destroyed: %s"


def takes_press(typed: Any) -> bool:
    """Whether the Unlock button is live for the value the row holds.

    An empty row answers False, so ``src/gui/fleet_unlock_dialog.py, in
    _on_unlock`` cannot reach ``src/core/encryption.py, in open_master_key``
    with nothing typed.
    """
    return bool(str(typed or ""))


def unlock_outcome(typed: Any, window: Any) -> str:
    """The outcome of pressing Unlock with *typed* against *window*.

    Answers ``OUTCOME_EMPTY`` for a row nothing was typed in,
    ``OUTCOME_NO_WINDOW`` where *window* answers no ``unlock_fleet``, and
    otherwise ``OUTCOME_OPENED`` or ``OUTCOME_REFUSED`` as that method answers.
    """
    if not takes_press(typed):
        return OUTCOME_EMPTY
    asked = getattr(window, "unlock_fleet", None)
    if not callable(asked):
        return OUTCOME_NO_WINDOW
    return OUTCOME_OPENED if asked(str(typed)) else OUTCOME_REFUSED


def outcome_words(outcome: Any) -> str:
    """The line the feedback label carries for one ``unlock_outcome`` answer."""
    return OUTCOME_WORDS.get(str(outcome), RESTING_TEXT)


def outcome_answer(outcome: Any) -> bool:
    """Whether one ``unlock_outcome`` answer means the fleet is open."""
    return str(outcome) == OUTCOME_OPENED


def rgb(colour: str) -> tuple[int, int, int]:
    """Split a colour token into its three 0-255 channels.

    Accepts ``#rgb`` and ``#rrggbb``, which is every form ``SKIN`` uses.
    """
    digits = colour.lstrip("#")
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))


def build_view_model(typed: Any = "", outcome: Any = OUTCOME_EMPTY) -> dict:
    """The whole unlock screen as one payload, from the row and its last outcome.

    ``src/gui/web/fleet_unlock.js`` draws every field of it and
    ``src/core/desktop_bridge.py`` serves it under ``METHOD``, so the drawn
    build carries no word the Qt build does not.
    """
    return {
        "widget": dict(WIDGET),
        "layout": dict(LAYOUT),
        "button_row": dict(BUTTON_ROW_LAYOUT),
        "skin": {name: list(rgb(token)) for name, token in SKIN.items()},
        "headline_label": dict(HEADLINE_LABEL),
        "detail_label": dict(DETAIL_LABEL),
        "feedback_label": dict(FEEDBACK_LABEL),
        "phrase_row": dict(PHRASE_ROW),
        "headline_text": HEADLINE_TEXT,
        "detail_text": DETAIL_TEXT,
        "feedback_text": outcome_words(outcome),
        "buttons": {
            DISMISS: {
                "text": DISMISS_TEXT,
                "enabled": True,
                "is_default": DISMISS_IS_DEFAULT,
                "minimum_height_px": BUTTON_MINIMUM_HEIGHT_PX,
                "description": DISMISS_DESCRIPTION,
            },
            UNLOCK: {
                "text": UNLOCK_TEXT,
                "enabled": takes_press(typed),
                "is_default": UNLOCK_IS_DEFAULT,
                "minimum_height_px": BUTTON_MINIMUM_HEIGHT_PX,
                "description": (
                    UNLOCK_DESCRIPTION
                    if takes_press(typed)
                    else UNLOCK_BLOCKED_DESCRIPTION
                ),
            },
        },
        "button_answers": dict(BUTTON_ANSWERS),
        "answers": list(ANSWERS),
        "actions": dict(ACTIONS),
        "default_answer": DEFAULT_ANSWER,
        "closed_answer": CLOSED_ANSWER,
        "build_failed_answer": BUILD_FAILED_ANSWER,
        "focus_on": FOCUS_ON,
        "outcome": str(outcome),
        "unlocked": outcome_answer(outcome),
    }


def view_model(params: Any = None, **_unused: Any) -> dict:
    """Bridge handler for ``METHOD``, serving the screen to the drawn build.

    ``params`` of a mapping carrying ``typed`` reports whether the Unlock
    button is live for that row; no password is read, stored or returned here,
    and no key is opened by this handler.
    """
    asked = params if isinstance(params, dict) else {}
    return build_view_model(asked.get("typed", ""), asked.get("outcome", OUTCOME_EMPTY))
