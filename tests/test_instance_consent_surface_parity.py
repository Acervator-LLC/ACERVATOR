"""The Qt instance consent dialog and the Qt-free surface, side by side.

A failure means the view model writes a different headline, a different
fact line, a different button label, a different answer, a different
release order or a different sequence of calls than
``InstanceConsentDialog``, ``release_dialog`` and ``ask_for_consent`` do
on the same guard decision.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import instance_consent_dialog as qt_dialog
from src.gui.main_tabs import instance_consent_surface as surface
from tests.fixtures.host_fonts import has_real_fonts

REPO_ROOT = Path(__file__).resolve().parents[1]

LOGGER_NAME = "acervator.gui.instance_consent"

DIALOG_PATH = REPO_ROOT / "src/gui/instance_consent_dialog.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/instance_consent_surface.py"

BUILD = "build"
CLICK = "click"
CLOSE = "close"

PIXEL_SIZE = (640, 480)
WIDE_PIXEL_SIZE = (900, 480)

CLICKED_SIGNAL = "2clicked()"

LABEL_TAGS = (
    surface.HEADLINE,
    surface.DETAIL,
    surface.OWNER,
    surface.THIS_MACHINE,
    surface.CONSEQUENCE,
)
BUTTON_TAGS = (surface.REFUSE, surface.CONSENT)

CALLS: list[list] = []


def app():
    """The process application object every render and widget needs."""
    from qt_pixel import ensure_app

    return ensure_app()


def host_has_fonts() -> bool:
    """Whether this host paints a real glyph, asked at run time.

    ``tests.fixtures.host_fonts`` is the one helper that asks. A machine
    with no font installed for the offscreen platform paints every
    character as the same empty box, so the answer decides what a render
    is allowed to prove, and both answers get a live branch below.
    """
    app()
    return has_real_fonts()


def render_offscreen(widget, size):
    from qt_pixel import render_widget

    return render_widget(widget, size)


def colour_count(image, hex_colour):
    """How many pixels of the render carry exactly this colour."""
    from PySide6.QtGui import QColor

    target = QColor(hex_colour).rgb()
    return sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixel(x, y) == target
    )


def image_digest(image):
    return hashlib.sha256(bytes(image.constBits())).hexdigest()


def digest(trace):
    return hashlib.sha256(json.dumps(trace, sort_keys=True).encode("utf-8")).hexdigest()


class ClassPatch:
    """Replace methods on a class and put the class back exactly as found."""

    def __init__(self, target):
        self.target = target
        self.saved: list[tuple] = []

    def set(self, name, value):
        self.saved.append(
            (name, name in vars(self.target), vars(self.target).get(name))
        )
        setattr(self.target, name, value)

    def undo(self):
        for name, existed, old in reversed(self.saved):
            if existed:
                setattr(self.target, name, old)
            else:
                delattr(self.target, name)
        self.saved = []


def raising_line(name):
    """A guard decision line that raises when the dialog reads it."""

    def read(self):
        raise RuntimeError(f"guard decision {name} is unavailable")

    return property(read)


DECISIONS = {
    "plain": {
        "headline": "This fleet was last used by another machine.",
        "detail": "Starting it here takes ownership away from that machine.",
        "owner_line": "Last used by kiosk-01 (anthony) [a1b2c3d4e5f6] on 2026-08-24.",
        "this_machine_line": "This machine is laptop-02 (anthony) [f6e5d4c3b2a1].",
        "consequence_line": "If you continue, this machine starts 37 bot(s).",
        "fleet_bot_count": 37,
        "consent_is_possible": True,
        "verdict": "foreign_machine",
    },
    "empty": {
        "headline": "",
        "detail": "",
        "owner_line": "",
        "this_machine_line": "",
        "consequence_line": "",
        "fleet_bot_count": 0,
        "consent_is_possible": True,
        "verdict": "",
    },
    "zero_bots": {
        "headline": "No saved fleet.",
        "detail": "Nothing is waiting to start.",
        "owner_line": "This fleet carries no record of the machine that last used it.",
        "this_machine_line": "This machine is host (user) [000000000000].",
        "consequence_line": "If you continue, this machine starts 0 bot(s).",
        "fleet_bot_count": 0,
        "consent_is_possible": True,
        "verdict": "first_run",
    },
    "negative_bots": {
        "headline": "Negative count.",
        "detail": "The saved fleet reports a count below zero.",
        "owner_line": "Last used by a (b) [ffffffffffff].",
        "this_machine_line": "This machine is c (d) [eeeeeeeeeeee].",
        "consequence_line": "If you continue, this machine starts -4 bot(s).",
        "fleet_bot_count": -4,
        "consent_is_possible": True,
        "verdict": "uncertain",
    },
    "very_large_bots": {
        "headline": "Very large count.",
        "detail": "The saved fleet reports an implausible count.",
        "owner_line": "Last used by a (b) [ffffffffffff].",
        "this_machine_line": "This machine is c (d) [eeeeeeeeeeee].",
        "consequence_line": "If you continue, this machine starts many bot(s).",
        "fleet_bot_count": 10**18,
        "consent_is_possible": True,
        "verdict": "foreign_machine",
    },
    "unicode": {
        "headline": "Δ→⚡ another machine owns this fleet",
        "detail": "Δ→⚡ starting here takes ownership",
        "owner_line": "Last used by Δ-kiosk (⚡) [aaaaaaaaaaaa].",
        "this_machine_line": "This machine is →box (Δ) [bbbbbbbbbbbb].",
        "consequence_line": "Δ→⚡ 3 bot(s) against the live exchange account.",
        "fleet_bot_count": 3,
        "consent_is_possible": True,
        "verdict": "foreign_machine",
    },
    "long_headline": {
        "headline": "x" * 200,
        "detail": "A two hundred character headline.",
        "owner_line": "Last used by a (b) [ffffffffffff].",
        "this_machine_line": "This machine is c (d) [eeeeeeeeeeee].",
        "consequence_line": "If you continue, this machine starts 1 bot(s).",
        "fleet_bot_count": 1,
        "consent_is_possible": True,
        "verdict": "foreign_machine",
    },
    "long_spaced_headline": {
        "headline": "another machine owns this saved fleet " * 8,
        "detail": "A headline long enough to wrap.",
        "owner_line": "Last used by a (b) [ffffffffffff].",
        "this_machine_line": "This machine is c (d) [eeeeeeeeeeee].",
        "consequence_line": "If you continue, this machine starts 1 bot(s).",
        "fleet_bot_count": 1,
        "consent_is_possible": True,
        "verdict": "foreign_machine",
    },
    "markup_in_text": {
        "headline": "a <b>bold</b> & risky headline",
        "detail": "<i>italic</i> & ampersand",
        "owner_line": "Last used by <script> (&) [ffffffffffff].",
        "this_machine_line": "This machine is <b>c</b> (d) [eeeeeeeeeeee].",
        "consequence_line": "<b>37</b> bot(s) & the live exchange account.",
        "fleet_bot_count": 37,
        "consent_is_possible": True,
        "verdict": "foreign_machine",
    },
    "consent_blocked": {
        "headline": "Another Acervator is running on this machine.",
        "detail": "Two copies on one account read the same wallet.",
        "owner_line": "Last used by this machine, four minutes ago.",
        "this_machine_line": "This machine is laptop-02 (anthony) [f6e5d4c3b2a1].",
        "consequence_line": "If you continue, this machine starts 12 bot(s).",
        "fleet_bot_count": 12,
        "consent_is_possible": False,
        "verdict": "live_instance",
    },
    "float_count": {
        "headline": "Fractional count.",
        "detail": "The saved fleet reports a fraction.",
        "owner_line": "Last used by a (b) [ffffffffffff].",
        "this_machine_line": "This machine is c (d) [eeeeeeeeeeee].",
        "consequence_line": "If you continue, this machine starts 3.7 bot(s).",
        "fleet_bot_count": 3.7,
        "consent_is_possible": True,
        "verdict": "foreign_machine",
    },
    "string_count": {
        "headline": "Count arrives as text.",
        "detail": "The saved fleet reports a string.",
        "owner_line": "Last used by a (b) [ffffffffffff].",
        "this_machine_line": "This machine is c (d) [eeeeeeeeeeee].",
        "consequence_line": "If you continue, this machine starts 5 bot(s).",
        "fleet_bot_count": "5",
        "consent_is_possible": True,
        "verdict": "foreign_machine",
    },
    "none_count": {
        "headline": "Count is missing.",
        "detail": "The saved fleet reports nothing.",
        "owner_line": "Last used by a (b) [ffffffffffff].",
        "this_machine_line": "This machine is c (d) [eeeeeeeeeeee].",
        "consequence_line": "If you continue, this machine starts no bot(s).",
        "fleet_bot_count": None,
        "consent_is_possible": True,
        "verdict": "uncertain",
    },
    "none_headline": {
        "headline": None,
        "detail": "The headline is not a string.",
        "owner_line": "Last used by a (b) [ffffffffffff].",
        "this_machine_line": "This machine is c (d) [eeeeeeeeeeee].",
        "consequence_line": "If you continue, this machine starts 1 bot(s).",
        "fleet_bot_count": 1,
        "consent_is_possible": True,
        "verdict": "foreign_machine",
    },
    "truthy_flag_count": {
        "headline": "Count arrives as a flag.",
        "detail": "The saved fleet reports a boolean.",
        "owner_line": "Last used by a (b) [ffffffffffff].",
        "this_machine_line": "This machine is c (d) [eeeeeeeeeeee].",
        "consequence_line": "If you continue, this machine starts 1 bot(s).",
        "fleet_bot_count": True,
        "consent_is_possible": True,
        "verdict": "foreign_machine",
    },
    "missing_fields": {
        "headline": "The decision carries no verdict and no count.",
        "detail": "Both are read with a fallback.",
        "owner_line": "Last used by a (b) [ffffffffffff].",
        "this_machine_line": "This machine is c (d) [eeeeeeeeeeee].",
        "consequence_line": "If you continue, this machine starts 0 bot(s).",
        "consent_is_possible": True,
    },
    "unknown_input": {
        "headline": "The count is not a number.",
        "detail": "The saved fleet reports a word.",
        "owner_line": "Last used by a (b) [ffffffffffff].",
        "this_machine_line": "This machine is c (d) [eeeeeeeeeeee].",
        "consequence_line": "If you continue, this machine starts some bot(s).",
        "fleet_bot_count": "not-a-number",
        "consent_is_possible": True,
        "verdict": "foreign_machine",
    },
    "consequence_raises": {
        "headline": "The consequence line cannot be read.",
        "detail": "The guard decision refuses one of its own lines.",
        "owner_line": "Last used by a (b) [ffffffffffff].",
        "this_machine_line": "This machine is c (d) [eeeeeeeeeeee].",
        "raises": "consequence_line",
        "fleet_bot_count": 1,
        "consent_is_possible": True,
        "verdict": "foreign_machine",
    },
}

UNBUILDABLE = ("unknown_input", "consequence_raises")

FIELD_ORDER = (
    "headline",
    "detail",
    "owner_line",
    "this_machine_line",
    "consequence_line",
    "fleet_bot_count",
    "consent_is_possible",
    "verdict",
)


def make_decision(name):
    """A stand-in guard decision carrying exactly one named case.

    A field named under ``raises`` becomes a property that raises when
    read, which is how a decision whose line is unavailable reaches both
    sides at the same point in the build.
    """
    spec = dict(DECISIONS[name])
    raises = spec.pop("raises", None)
    holder = type("Decision", (), {})
    if raises is not None:
        setattr(holder, raises, raising_line(raises))
    decision = holder()
    for field, value in spec.items():
        setattr(decision, field, value)
    return decision


def trace_widgets(monkeypatch):
    """Swap the dialog's widget factories for recording ones.

    Every recorded value is read back off the real widget, so a wrong
    value reaches the trace rather than the value the dialog was told.
    ``QtWidgets`` itself is replaced by a shim that proxies everything
    else through, so no PySide6 module is altered and no Qt class is
    subclassed.
    """
    from PySide6 import QtWidgets as real

    labels: list = []
    buttons: list = []
    frames: list = []
    vboxes: list = []

    def wrap_label(label, tag):
        def set_object_name(name):
            real.QLabel.setObjectName(label, name)
            CALLS.append([surface.LABEL_SET_OBJECT_NAME, tag, label.objectName()])

        def set_word_wrap(on):
            real.QLabel.setWordWrap(label, on)
            CALLS.append([surface.LABEL_SET_WORD_WRAP, tag, label.wordWrap()])

        def set_text_interaction(flags):
            real.QLabel.setTextInteractionFlags(label, flags)
            CALLS.append(
                [
                    surface.LABEL_SET_TEXT_INTERACTION,
                    tag,
                    label.textInteractionFlags().name,
                ]
            )

        label.setObjectName = set_object_name
        label.setWordWrap = set_word_wrap
        label.setTextInteractionFlags = set_text_interaction

    def make_label(text=""):
        label = real.QLabel(text)
        tag = LABEL_TAGS[len(labels)]
        label.acervator_tag = tag
        labels.append(label)
        CALLS.append([surface.LABEL_CREATE, tag, label.text()])
        wrap_label(label, tag)
        return label

    def make_button(text=""):
        button = real.QPushButton(text)
        tag = BUTTON_TAGS[len(buttons)]
        button.acervator_tag = tag
        buttons.append(button)
        CALLS.append([surface.BUTTON_CREATE, tag, button.text()])

        def set_object_name(name):
            real.QPushButton.setObjectName(button, name)
            CALLS.append([surface.BUTTON_SET_OBJECT_NAME, tag, button.objectName()])

        def set_minimum_height(height):
            real.QPushButton.setMinimumHeight(button, height)
            CALLS.append(
                [surface.BUTTON_SET_MINIMUM_HEIGHT, tag, button.minimumHeight()]
            )

        def set_default(on):
            real.QPushButton.setDefault(button, on)
            CALLS.append([surface.BUTTON_SET_DEFAULT, tag, button.isDefault()])

        def set_auto_default(on):
            real.QPushButton.setAutoDefault(button, on)
            CALLS.append([surface.BUTTON_SET_AUTO_DEFAULT, tag, button.autoDefault()])

        def set_enabled(on):
            real.QPushButton.setEnabled(button, on)
            CALLS.append([surface.BUTTON_SET_ENABLED, tag, button.isEnabled()])

        def set_tool_tip(text_value):
            real.QPushButton.setToolTip(button, text_value)
            CALLS.append([surface.BUTTON_SET_TOOL_TIP, tag, button.toolTip()])

        def set_focus():
            real.QPushButton.setFocus(button)
            CALLS.append([surface.BUTTON_SET_FOCUS, tag])

        button.setObjectName = set_object_name
        button.setMinimumHeight = set_minimum_height
        button.setDefault = set_default
        button.setAutoDefault = set_auto_default
        button.setEnabled = set_enabled
        button.setToolTip = set_tool_tip
        button.setFocus = set_focus
        return button

    def make_frame():
        frame = real.QFrame()
        frame.acervator_tag = surface.FACTS
        frames.append(frame)
        CALLS.append([surface.FACTS_CREATE])

        def set_object_name(name):
            real.QFrame.setObjectName(frame, name)
            CALLS.append([surface.FACTS_SET_OBJECT_NAME, frame.objectName()])

        frame.setObjectName = set_object_name
        return frame

    def make_vbox(parent=None):
        layout = real.QVBoxLayout(parent)
        outer = isinstance(parent, real.QDialog)
        vboxes.append(layout)
        create, margins, spacing, add_widget_name = (
            (
                surface.LAYOUT_CREATE,
                surface.LAYOUT_SET_MARGINS,
                surface.LAYOUT_SET_SPACING,
                surface.LAYOUT_ADD_WIDGET,
            )
            if outer
            else (
                surface.FACTS_LAYOUT_CREATE,
                surface.FACTS_LAYOUT_SET_MARGINS,
                surface.FACTS_LAYOUT_SET_SPACING,
                surface.FACTS_LAYOUT_ADD_WIDGET,
            )
        )
        CALLS.append([create])

        def set_margins(left, top, right, bottom):
            real.QVBoxLayout.setContentsMargins(layout, left, top, right, bottom)
            found = layout.contentsMargins()
            CALLS.append(
                [
                    margins,
                    [found.left(), found.top(), found.right(), found.bottom()],
                ]
            )

        def set_spacing(value):
            real.QVBoxLayout.setSpacing(layout, value)
            CALLS.append([spacing, layout.spacing()])

        def add_widget(widget, *args):
            real.QVBoxLayout.addWidget(layout, widget, *args)
            CALLS.append([add_widget_name, widget.acervator_tag])

        def add_layout(child, *args):
            real.QVBoxLayout.addLayout(layout, child, *args)
            CALLS.append([surface.LAYOUT_ADD_LAYOUT, surface.BUTTON_ROW])

        layout.setContentsMargins = set_margins
        layout.setSpacing = set_spacing
        layout.addWidget = add_widget
        layout.addLayout = add_layout
        return layout

    def make_hbox():
        row = real.QHBoxLayout()
        CALLS.append([surface.ROW_CREATE])

        def set_spacing(value):
            real.QHBoxLayout.setSpacing(row, value)
            CALLS.append([surface.ROW_SET_SPACING, row.spacing()])

        def add_stretch(weight):
            real.QHBoxLayout.addStretch(row, weight)
            CALLS.append([surface.ROW_ADD_STRETCH, row.stretch(row.count() - 1)])

        def add_widget(widget, *args):
            real.QHBoxLayout.addWidget(row, widget, *args)
            CALLS.append([surface.ROW_ADD_WIDGET, widget.acervator_tag])

        row.setSpacing = set_spacing
        row.addStretch = add_stretch
        row.addWidget = add_widget
        return row

    overrides = {
        "QLabel": make_label,
        "QPushButton": make_button,
        "QFrame": make_frame,
        "QVBoxLayout": make_vbox,
        "QHBoxLayout": make_hbox,
    }

    class WidgetShim:
        """The real ``QtWidgets``, with the five factories recorded."""

        def __getattr__(self, name):
            if name in overrides:
                return overrides[name]
            return getattr(real, name)

    monkeypatch.setattr(qt_dialog, "QtWidgets", WidgetShim())
    return labels, buttons, frames


def trace_dialog_methods():
    """Record the calls the dialog makes on itself. Returns the patch."""
    from PySide6.QtWidgets import QDialog

    target = qt_dialog.InstanceConsentDialog
    patch = ClassPatch(target)
    original_setattr = target.__setattr__

    def set_accessible_name(self, name):
        QDialog.setAccessibleName(self, name)
        CALLS.append([surface.DIALOG_SET_ACCESSIBLE_NAME, self.accessibleName()])

    def set_window_title(self, title):
        QDialog.setWindowTitle(self, title)
        CALLS.append([surface.DIALOG_SET_WINDOW_TITLE, self.windowTitle()])

    def set_modal(self, modal):
        QDialog.setModal(self, modal)
        CALLS.append([surface.DIALOG_SET_MODAL, self.isModal()])

    def set_minimum_width(self, width):
        QDialog.setMinimumWidth(self, width)
        CALLS.append([surface.DIALOG_SET_MINIMUM_WIDTH, self.minimumWidth()])

    def set_style_sheet(self, sheet):
        QDialog.setStyleSheet(self, sheet)
        CALLS.append([surface.DIALOG_SET_STYLE_SHEET, self.styleSheet()])

    def accept(self):
        QDialog.accept(self)
        CALLS.append([surface.DIALOG_ACCEPT])

    def reject(self):
        qt_dialog.InstanceConsentDialog.__dict__
        original_reject(self)
        CALLS.append([surface.DIALOG_REJECT])

    def record_setattr(self, name, value):
        original_setattr(self, name, value)
        if name == "_consented":
            CALLS.append([surface.DIALOG_CONSENTED, self.consented])

    original_reject = vars(target)["reject"]
    patch.set("setAccessibleName", set_accessible_name)
    patch.set("setWindowTitle", set_window_title)
    patch.set("setModal", set_modal)
    patch.set("setMinimumWidth", set_minimum_width)
    patch.set("setStyleSheet", set_style_sheet)
    patch.set("accept", accept)
    patch.set("reject", reject)
    patch.set("__setattr__", record_setattr)
    return patch


SCRIPTS = {}
for _name in DECISIONS:
    SCRIPTS[_name + "_untouched"] = [(BUILD, _name)]
    if _name not in UNBUILDABLE:
        SCRIPTS[_name + "_refuse"] = [(BUILD, _name), (CLICK, surface.REFUSE)]
        SCRIPTS[_name + "_consent"] = [(BUILD, _name), (CLICK, surface.CONSENT)]
        SCRIPTS[_name + "_closed"] = [(BUILD, _name), (CLOSE, CLOSE)]
SCRIPTS["rebuild"] = [
    (BUILD, "plain"),
    (CLICK, surface.CONSENT),
    (BUILD, "unicode"),
    (CLOSE, CLOSE),
]
SCRIPTS["every_button_in_turn"] = [
    (BUILD, "plain"),
    (CLICK, surface.CONSENT),
    (CLICK, surface.REFUSE),
    (CLICK, surface.CONSENT),
    (CLOSE, CLOSE),
]
SCRIPTS["empty_script"] = []


def press_old(dialog, button):
    """Press one button on the real dialog, through its own handler."""
    if button == surface.REFUSE:
        dialog._on_refuse()
    else:
        dialog._on_consent()


def read_widgets(dialog, labels, buttons):
    """Every visible string, button state and answer the dialog carries."""
    return {
        "headline_text": labels[0].text(),
        "detail_text": labels[1].text(),
        "owner_text": labels[2].text(),
        "this_machine_text": labels[3].text(),
        "consequence_text": labels[4].text(),
        "refuse_text": buttons[0].text(),
        "consent_text": buttons[1].text(),
        "refuse_enabled": buttons[0].isEnabled(),
        "consent_enabled": buttons[1].isEnabled(),
        "refuse_tool_tip": buttons[0].toolTip(),
        "consent_tool_tip": buttons[1].toolTip(),
        "consented": dialog.consented,
    }


def read_model(model):
    """Every visible string, button state and answer the model carries."""
    return {
        "headline_text": model.headline_text,
        "detail_text": model.detail_text,
        "owner_text": model.owner_text,
        "this_machine_text": model.this_machine_text,
        "consequence_text": model.consequence_text,
        "refuse_text": model.refuse_text,
        "consent_text": model.consent_button_text,
        "refuse_enabled": surface.REFUSE_ENABLED,
        "consent_enabled": model.consent_enabled,
        "refuse_tool_tip": surface.NO_TOOLTIP,
        "consent_tool_tip": model.consent_tool_tip,
        "consented": model.consented,
    }


def snapshot(error, view):
    """One step's whole state: the error, the outputs and the call list."""
    body = {"error": error, "calls": [list(call) for call in CALLS]}
    body.update(view)
    return body


def run_old(script, monkeypatch):
    """Drive ``InstanceConsentDialog`` through the script, step by step."""
    app()
    CALLS.clear()
    labels, buttons, frames = trace_widgets(monkeypatch)
    patch = trace_dialog_methods()
    try:
        dialog = None
        trace = [snapshot(None, {})]
        for step in script:
            error = None
            try:
                if step[0] == BUILD:
                    labels.clear()
                    buttons.clear()
                    frames.clear()
                    dialog = qt_dialog.InstanceConsentDialog(make_decision(step[1]))
                elif step[0] == CLICK:
                    press_old(dialog, step[1])
                else:
                    dialog.reject()
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            view = {} if error else read_widgets(dialog, labels, buttons)
            trace.append(snapshot(error, view))
        return trace
    finally:
        patch.undo()


def run_new(script):
    """Drive the view model through the same script, step by step."""
    CALLS.clear()
    model = surface.InstanceConsentModel()
    trace = [snapshot(None, {})]
    for step in script:
        error = None
        try:
            if step[0] == BUILD:
                model.build(make_decision(step[1]))
            elif step[0] == CLICK:
                surface.BUTTON_ACTS[step[1]](model)
            else:
                model.close_window()
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        CALLS.clear()
        CALLS.extend(model.calls)
        view = {} if error else read_model(model)
        trace.append(snapshot(error, view))
    return trace


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_old_and_new_traces_are_identical(name, monkeypatch):
    """A step of the script leaves the two sides in a different state."""
    old = run_old(SCRIPTS[name], monkeypatch)
    new = run_new(SCRIPTS[name])
    assert new == old
    assert digest(new) == digest(old)


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_the_trace_holds_the_whole_dialog(name, monkeypatch):
    """The comparison passed by measuring nothing."""
    old = run_old(SCRIPTS[name], monkeypatch)
    assert len(old) == len(SCRIPTS[name]) + 1
    assert old[0] == {"error": None, "calls": []}
    for step in old[1:]:
        assert step["calls"] != []
        if step["error"] is None:
            assert isinstance(step["headline_text"], str)
            assert step["consented"] in surface.ANSWERS
            assert step["refuse_text"] and step["consent_text"]
    if SCRIPTS[name]:
        assert old[-1]["calls"] != []


def test_the_scripts_reach_every_answer_and_every_failure(monkeypatch):
    """A state was never driven, so its parity was never compared."""
    answers = set()
    errors = set()
    headlines = set()
    consent_states = set()
    for name in SCRIPTS:
        for step in run_old(SCRIPTS[name], monkeypatch):
            if step["error"]:
                errors.add(step["error"].split(":")[0])
            if "consented" in step:
                answers.add(step["consented"])
                consent_states.add(step["consent_enabled"])
                headlines.add(step["headline_text"])
    assert answers == {surface.ANSWER_CONSENT, surface.ANSWER_REFUSE}
    assert errors == {"ValueError", "RuntimeError"}
    assert consent_states == {True, False}
    assert "" in headlines
    assert "x" * 200 in headlines
    assert "None" in headlines
    assert any("⚡" in text for text in headlines)
    assert any("<b>bold</b>" in text for text in headlines)


def test_a_build_that_cannot_finish_stops_at_the_same_call(monkeypatch):
    """One side placed a widget the other never reached."""
    good = run_old([(BUILD, "plain")], monkeypatch)
    assert good[1]["error"] is None
    assert len(good[1]["calls"]) == 54

    unknown = run_old([(BUILD, "unknown_input")], monkeypatch)
    assert unknown[1]["error"].startswith("ValueError")
    assert len(unknown[1]["calls"]) == 46
    assert unknown[1]["calls"][-1] == [surface.ROW_ADD_WIDGET, surface.REFUSE]
    assert run_new([(BUILD, "unknown_input")])[1] == unknown[1]

    raised = run_old([(BUILD, "consequence_raises")], monkeypatch)
    assert raised[1]["error"].startswith("RuntimeError")
    assert len(raised[1]["calls"]) == 33
    assert raised[1]["calls"][-1] == [surface.LAYOUT_ADD_WIDGET, surface.FACTS]
    assert run_new([(BUILD, "consequence_raises")])[1] == raised[1]

    for name in UNBUILDABLE:
        failed = run_old([(BUILD, name)], monkeypatch)
        assert failed[1]["error"] is not None, name
        assert run_new([(BUILD, name)])[1] == failed[1], name
    assert len(UNBUILDABLE) == 2


def test_the_refuse_click_clears_the_answer_twice_like_the_dialog(monkeypatch):
    """The refuse handler stopped routing through the reject path."""
    old = run_old([(BUILD, "plain"), (CLICK, surface.REFUSE)], monkeypatch)
    added = old[2]["calls"][len(old[1]["calls"]) :]
    assert added == [
        [surface.DIALOG_CONSENTED, False],
        [surface.DIALOG_CONSENTED, False],
        [surface.DIALOG_REJECT],
    ]
    new = run_new([(BUILD, "plain"), (CLICK, surface.REFUSE)])
    assert new[2]["calls"][len(new[1]["calls"]) :] == added
    consenting = run_old([(BUILD, "plain"), (CLICK, surface.CONSENT)], monkeypatch)
    assert consenting[2]["calls"][len(consenting[1]["calls"]) :] == [
        [surface.DIALOG_CONSENTED, True],
        [surface.DIALOG_ACCEPT],
    ]


def test_the_window_close_button_means_no(monkeypatch):
    """A dialog dismissed by its window button started the fleet."""
    granted = run_old(
        [(BUILD, "plain"), (CLICK, surface.CONSENT), (CLOSE, CLOSE)], monkeypatch
    )
    assert granted[2]["consented"] is True
    assert granted[3]["consented"] is False
    assert surface.CLOSED_ANSWER is surface.ANSWER_REFUSE
    new = run_new([(BUILD, "plain"), (CLICK, surface.CONSENT), (CLOSE, CLOSE)])
    assert new[3]["consented"] == granted[3]["consented"]
    assert new[2]["consented"] == granted[2]["consented"]


def test_the_bot_count_the_button_shows_is_the_dialogs_own(monkeypatch):
    """The number the operator authorises drifted from the dialog's own."""
    expected = {
        "plain": 37,
        "empty": 0,
        "zero_bots": 0,
        "negative_bots": -4,
        "very_large_bots": 10**18,
        "float_count": 3,
        "string_count": 5,
        "none_count": 0,
        "truthy_flag_count": 1,
        "missing_fields": 0,
    }
    for name, count in expected.items():
        old = run_old([(BUILD, name)], monkeypatch)
        assert (
            old[1]["consent_text"] == f"Take ownership and start {count} bot(s)"
        ), name
        assert surface.bot_count(DECISIONS[name].get("fleet_bot_count", 0)) == count
        assert surface.consent_text(count) == old[1]["consent_text"], name
    assert surface.bot_count(0) == 0
    assert surface.bot_count(None) == 0
    assert surface.bot_count(False) == 0
    assert surface.bot_count(3.7) == 3
    assert surface.bot_count("5") == 5
    assert surface.bot_count(-4) == -4
    assert surface.consent_text(1) != surface.consent_text(2)
    assert surface.CONSENT_TEXT_FORMAT == "Take ownership and start {count} bot(s)"
    assert surface.CONSENT_TEXT_FORMAT.count("{count}") == 1


def test_the_log_lines_are_the_dialogs_own(monkeypatch, capture_log):
    """The line the trade log carries drifted from the dialog's own."""
    for name in ("plain", "missing_fields", "float_count"):
        for button in (surface.REFUSE, surface.CONSENT):
            with capture_log(LOGGER_NAME) as old_records:
                run_old([(BUILD, name), (CLICK, button)], monkeypatch)
            old_logs = [record.getMessage() for record in old_records]
            with capture_log(LOGGER_NAME) as new_records:
                run_new([(BUILD, name), (CLICK, button)])
            new_logs = [record.getMessage() for record in new_records]
            assert new_logs == old_logs, (name, button)
            assert len(old_logs) == 1, (name, button)
    with capture_log(LOGGER_NAME) as records:
        run_old([(BUILD, "plain"), (CLICK, surface.REFUSE)], monkeypatch)
    assert [record.getMessage() for record in records] == [
        "instance consent: operator DECLINED to start the fleet on "
        "this machine (verdict foreign_machine)"
    ]
    with capture_log(LOGGER_NAME) as records:
        run_old([(BUILD, "float_count"), (CLICK, surface.CONSENT)], monkeypatch)
    assert [record.getMessage() for record in records] == [
        "instance consent: operator GRANTED ownership to this machine "
        "and authorised 3.7 bot(s) (verdict foreign_machine)"
    ]
    with capture_log(LOGGER_NAME) as records:
        run_old([(BUILD, "missing_fields"), (CLICK, surface.CONSENT)], monkeypatch)
    assert [record.getMessage() for record in records] == [
        "instance consent: operator GRANTED ownership to this machine "
        "and authorised 0 bot(s) (verdict unknown)"
    ]
    with capture_log(LOGGER_NAME) as silent:
        run_old([(BUILD, "plain")], monkeypatch)
    assert [record.getMessage() for record in silent] == []


def test_the_log_carries_the_raw_count_not_the_button_count(monkeypatch, capture_log):
    """The log and the button stopped disagreeing where the dialog does."""
    with capture_log(LOGGER_NAME) as old_records:
        old = run_old([(BUILD, "float_count"), (CLICK, surface.CONSENT)], monkeypatch)
    with capture_log(LOGGER_NAME) as new_records:
        new = run_new([(BUILD, "float_count"), (CLICK, surface.CONSENT)])
    old_message = old_records[0].getMessage()
    new_message = new_records[0].getMessage()
    assert new_message == old_message
    assert "authorised 3.7 bot(s)" in new_message
    assert "authorised 3 bot(s)" not in new_message
    assert new[2]["consent_text"] == old[2]["consent_text"]
    assert old[2]["consent_text"] == "Take ownership and start 3 bot(s)"
    model = surface.InstanceConsentModel()
    model.build(make_decision("float_count"))
    assert model.button_bot_count == 3
    assert getattr(model.decision, "fleet_bot_count") == 3.7
    assert model.button_bot_count != getattr(model.decision, "fleet_bot_count")
    assert surface.MISSING_BOT_COUNT == 0
    assert surface.MISSING_VERDICT == "unknown"


def test_widget_properties_match_the_dialog():
    """A dialog property drifted from the value the surface reports."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    app()
    dialog = qt_dialog.InstanceConsentDialog(make_decision("plain"))
    assert surface.WIDGET == {
        "accessible_name": dialog.accessibleName(),
        "window_title": dialog.windowTitle(),
        "modal": dialog.isModal(),
        "minimum_width_px": dialog.minimumWidth(),
        "size_px": [dialog.width(), dialog.height()],
        "style_sheet": dialog.styleSheet(),
        "stays_on_top": bool(dialog.windowFlags() & Qt.WindowStaysOnTopHint),
    }
    assert surface.ACCESSIBLE_NAME == "Instance Consent Dialog"
    assert surface.WINDOW_TITLE == "Acervator - start the saved fleet?"
    assert surface.MODAL is True
    assert surface.MINIMUM_WIDTH_PX == 560
    assert surface.STAYS_ON_TOP is False
    assert dialog.focusWidget().objectName() == surface.FOCUS_ON
    from qt_pixel import render_widget

    shipped = render_widget(dialog, PIXEL_SIZE)
    mirror = render_widget(
        dialog_painted_by_the_model(model_payload("plain")), PIXEL_SIZE
    )
    assert image_digest(mirror) == image_digest(shipped)
    for name, token in surface.SKIN.items():
        assert colour_count(mirror, token) == colour_count(shipped, token), name
    bare = QDialog()
    assert bare.accessibleName() != surface.ACCESSIBLE_NAME
    assert bare.windowTitle() != surface.WINDOW_TITLE
    assert bare.isModal() != surface.MODAL
    assert bare.minimumWidth() != surface.MINIMUM_WIDTH_PX
    assert bare.styleSheet() != surface.STYLE_SHEET
    assert list(surface.DEFAULT_SIZE_PX) == [bare.width(), bare.height()]


def test_layout_matches_the_dialog():
    """A margin, a spacing, an order or a stretch drifted from the dialog."""
    from PySide6.QtWidgets import QHBoxLayout, QWidget

    app()
    dialog = qt_dialog.InstanceConsentDialog(make_decision("plain"))
    layout = dialog.layout()
    margins = layout.contentsMargins()
    assert surface.LAYOUT["margins_px"] == [
        margins.left(),
        margins.top(),
        margins.right(),
        margins.bottom(),
    ]
    assert surface.LAYOUT["spacing_px"] == layout.spacing()
    assert surface.LAYOUT["child_stretch"] == [
        layout.stretch(index) for index in range(layout.count())
    ]
    assert len(surface.LAYOUT["order"]) == layout.count() == 5
    assert surface.LAYOUT["order"] == [
        layout.itemAt(index).widget().objectName() for index in range(4)
    ] + [surface.BUTTON_ROW]

    facts = layout.itemAt(2).widget()
    facts_layout = facts.layout()
    facts_margins = facts_layout.contentsMargins()
    assert surface.FACTS_LAYOUT["margins_px"] == [
        facts_margins.left(),
        facts_margins.top(),
        facts_margins.right(),
        facts_margins.bottom(),
    ]
    assert surface.FACTS_LAYOUT["spacing_px"] == facts_layout.spacing()
    assert surface.FACTS_LAYOUT["child_stretch"] == [
        facts_layout.stretch(index) for index in range(facts_layout.count())
    ]
    assert len(surface.FACTS_LAYOUT["order"]) == facts_layout.count() == 2
    fact_texts = {
        surface.OWNER: DECISIONS["plain"]["owner_line"],
        surface.THIS_MACHINE: DECISIONS["plain"]["this_machine_line"],
    }
    assert [fact_texts[name] for name in surface.FACTS_LAYOUT["order"]] == [
        facts_layout.itemAt(index).widget().text()
        for index in range(facts_layout.count())
    ]
    assert fact_texts[surface.OWNER] != fact_texts[surface.THIS_MACHINE]

    row = layout.itemAt(4).layout()
    row_margins = row.contentsMargins()
    assert surface.BUTTON_ROW_LAYOUT["margins_px"] == [
        row_margins.left(),
        row_margins.top(),
        row_margins.right(),
        row_margins.bottom(),
    ]
    assert surface.BUTTON_ROW_LAYOUT["spacing_px"] == row.spacing()
    assert surface.BUTTON_ROW_LAYOUT["child_stretch"] == [
        row.stretch(index) for index in range(row.count())
    ]
    assert len(surface.BUTTON_ROW_LAYOUT["order"]) == row.count() == 3
    assert row.itemAt(0).widget() is None
    assert surface.BUTTON_ROW_LAYOUT["order"][0] == surface.STRETCH
    assert surface.BUTTON_ROW_LAYOUT["order"][1:] == [
        row.itemAt(index).widget().objectName() for index in (1, 2)
    ]
    holder = QWidget()
    bare_row = QHBoxLayout(holder)
    bare_margins = bare_row.contentsMargins()
    assert [
        bare_margins.left(),
        bare_margins.top(),
        bare_margins.right(),
        bare_margins.bottom(),
    ] != surface.LAYOUT["margins_px"]
    assert bare_row.spacing() != surface.BUTTON_ROW_LAYOUT["spacing_px"]


def test_the_children_match_the_dialog():
    """A label's object name, wrap or selection drifted from the dialog."""
    from PySide6.QtWidgets import QLabel

    app()
    dialog = qt_dialog.InstanceConsentDialog(make_decision("plain"))
    layout = dialog.layout()
    facts = layout.itemAt(2).widget()
    facts_layout = facts.layout()
    named = {
        surface.HEADLINE: (layout.itemAt(0).widget(), surface.HEADLINE_LABEL),
        surface.DETAIL: (layout.itemAt(1).widget(), surface.DETAIL_LABEL),
        surface.OWNER: (facts_layout.itemAt(0).widget(), surface.FACT_LABEL),
        surface.THIS_MACHINE: (facts_layout.itemAt(1).widget(), surface.FACT_LABEL),
        surface.CONSEQUENCE: (layout.itemAt(3).widget(), surface.CONSEQUENCE_LABEL),
    }
    for name, (label, spec) in named.items():
        assert spec == {
            "object_name": label.objectName(),
            "word_wrap": label.wordWrap(),
            "text_interaction": label.textInteractionFlags().name,
            "text_interaction_value": label.textInteractionFlags().value,
        }, name
    assert surface.FACTS_FRAME == {"object_name": facts.objectName()}
    assert surface.FACT_LABEL["text_interaction"] == "TextSelectableByMouse"
    assert surface.FACT_LABEL["text_interaction_value"] == 1
    assert surface.HEADLINE_LABEL["text_interaction_value"] == 4
    assert (
        surface.FACT_LABEL["text_interaction_value"]
        != surface.HEADLINE_LABEL["text_interaction_value"]
    )
    bare = QLabel("")
    assert bare.wordWrap() is not surface.WORD_WRAP
    assert bare.objectName() != surface.HEADLINE
    assert bare.textInteractionFlags().name == surface.PLAIN_TEXT_INTERACTION
    assert bare.textInteractionFlags().value == surface.PLAIN_TEXT_INTERACTION_VALUE


def test_the_buttons_match_the_dialog():
    """A button's label, height, default state or skin drifted."""
    from PySide6.QtWidgets import QPushButton

    app()
    dialog = qt_dialog.InstanceConsentDialog(make_decision("plain"))
    row = dialog.layout().itemAt(4).layout()
    refuse = row.itemAt(1).widget()
    consent = row.itemAt(2).widget()
    assert refuse.text() == surface.REFUSE_TEXT == "Do not start bots"
    assert consent.text() == surface.consent_text(37)
    assert refuse.objectName() == surface.REFUSE
    assert consent.objectName() == surface.CONSENT
    assert refuse.minimumHeight() == surface.BUTTON_MINIMUM_HEIGHT_PX == 44
    assert consent.minimumHeight() == surface.BUTTON_MINIMUM_HEIGHT_PX
    assert refuse.isDefault() is surface.REFUSE_IS_DEFAULT is True
    assert consent.isDefault() is surface.CONSENT_IS_DEFAULT is False
    assert refuse.autoDefault() is surface.REFUSE_IS_DEFAULT
    assert consent.autoDefault() is surface.CONSENT_IS_DEFAULT
    assert refuse.isEnabled() is surface.REFUSE_ENABLED is True
    assert consent.isEnabled() is True
    assert refuse.toolTip() == consent.toolTip() == surface.NO_TOOLTIP == ""
    assert surface.REFUSE_TEXT != consent.text()
    bare = QPushButton("")
    assert bare.minimumHeight() != surface.BUTTON_MINIMUM_HEIGHT_PX
    assert bare.isDefault() is not surface.REFUSE_IS_DEFAULT
    assert bare.autoDefault() is not surface.REFUSE_IS_DEFAULT


def test_a_blocked_consent_button_is_disabled_and_says_why():
    """A consent the guard would refuse to honour was still offered."""
    app()
    dialog = qt_dialog.InstanceConsentDialog(make_decision("consent_blocked"))
    row = dialog.layout().itemAt(4).layout()
    refuse = row.itemAt(1).widget()
    consent = row.itemAt(2).widget()
    assert consent.isEnabled() is False
    assert consent.toolTip() == surface.CONSENT_BLOCKED_TOOLTIP
    assert consent.toolTip() == (
        "Another Acervator holds the exclusive handle on this "
        "directory. Close it first."
    )
    assert refuse.isEnabled() is True
    assert refuse.toolTip() == surface.NO_TOOLTIP
    model = surface.InstanceConsentModel()
    model.build(make_decision("consent_blocked"))
    assert model.consent_enabled is consent.isEnabled()
    assert model.consent_tool_tip == consent.toolTip()
    open_dialog = qt_dialog.InstanceConsentDialog(make_decision("plain"))
    open_consent = open_dialog.layout().itemAt(4).layout().itemAt(2).widget()
    assert open_consent.isEnabled() is True
    assert open_consent.toolTip() == ""
    open_model = surface.InstanceConsentModel()
    open_model.build(make_decision("plain"))
    assert open_model.consent_enabled is True
    assert open_model.consent_tool_tip == ""


def test_the_style_sheet_is_the_dialogs_own():
    """The surface ships a skin the dialog does not paint."""
    app()
    dialog = qt_dialog.InstanceConsentDialog(make_decision("plain"))
    assert surface.STYLE_SHEET == dialog.styleSheet()
    assert surface.STYLE_SHEET == (
        "QDialog { background: #22223a; color: #e0e0f0; }"
        "QLabel { color: #a8a8c5;"
        " font-family: 'Rajdhani', 'Orbitron', 'Segoe UI', sans-serif;"
        " font-size: 13px; }"
        "QLabel#headline { color: #ffaa00; font-size: 18px; font-weight: 700; }"
        "QLabel#detail { color: #e0e0f0; }"
        "QLabel#fact { color: #e0e0f0;"
        " font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;"
        " font-size: 11px; }"
        "QLabel#consequence { color: #ff5577; }"
        "QFrame#facts { background: #141420;"
        " border: 1px solid #7a7a9c; border-radius: 8px; }"
        "QPushButton { background: #1a1a28; color: #e0e0f0;"
        " border: 1px solid #7a7a9c; border-radius: 8px;"
        " padding: 8px 24px;"
        " font-family: 'Rajdhani', 'Orbitron', 'Segoe UI', sans-serif;"
        " font-size: 13px; }"
        "QPushButton#refuse { border: 2px solid #00ffcc; color: #00ffcc; }"
        "QPushButton#consent { color: #ff5577; border: 1px solid #ff5577; }"
        "QPushButton:focus { outline: none; border: 2px solid #a0a0c0; }"
    )
    for token in surface.SKIN.values():
        assert token in surface.STYLE_SHEET, token
    assert surface.STYLE_SHEET.count("#ff5577") == 3
    assert surface.STYLE_SHEET.count("#00ffcc") == 2
    from qt_pixel import render_widget

    shipped = render_widget(dialog, PIXEL_SIZE)
    mirror = render_widget(
        dialog_painted_by_the_model(model_payload("plain")), PIXEL_SIZE
    )
    assert image_digest(mirror) == image_digest(shipped)
    for name, token in surface.SKIN.items():
        assert colour_count(mirror, token) == colour_count(shipped, token), name
    unskinned = model_payload("plain")
    unskinned["widget"]["style_sheet"] = ""
    assert image_digest(
        render_widget(dialog_painted_by_the_model(unskinned), PIXEL_SIZE)
    ) != image_digest(shipped)
    assert colour_count(shipped, surface.SKIN["surface"]) > 0


SWAP_BLIND_TOKENS: tuple[str, ...] = ()


def test_rgb_matches_qcolor_on_every_skin_token():
    """The Qt-free colour split disagrees with QColor on a token."""
    from PySide6.QtGui import QColor

    assert surface.rgb("#123456") == (18, 52, 86)
    assert surface.rgb("#abc") == (170, 187, 204)
    assert surface.rgb("#ff8000") != surface.rgb("#0080ff")
    for name, token in surface.SKIN.items():
        painted = QColor(token)
        assert surface.rgb(token) == (
            painted.red(),
            painted.green(),
            painted.blue(),
        ), name
    assert len(surface.SKIN) == 11
    assert surface.SKIN["headline"] == "#ffaa00"
    assert surface.SKIN["consequence"] == "#ff5577"
    assert surface.SKIN["refuse"] == "#00ffcc"
    assert surface.SKIN["surface"] == "#22223a"


def test_a_channel_swap_is_reported_on_every_skin_colour():
    """A colour check a swapped red and blue would pass proves nothing.

    A token whose red and blue channels are equal, such as ``#888``,
    cannot show a red/blue swap at all. This skin holds none: every one
    of the eleven tokens changes under the swap, so the list of
    swap-blind tokens is empty and that emptiness is asserted rather
    than assumed.
    """
    swappable = 0
    for name, token in surface.SKIN.items():
        red, green, blue = surface.rgb(token)
        if token in SWAP_BLIND_TOKENS:
            assert (red, green, blue) == (blue, green, red), name
            continue
        assert (red, green, blue) != (blue, green, red), name
        swappable += 1
    assert swappable == 11
    assert SWAP_BLIND_TOKENS == ()
    assert surface.rgb("#888888") == surface.rgb("#888888")[::-1]
    values = [surface.rgb(token) for token in surface.SKIN.values()]
    assert len(set(values)) == 10
    assert surface.SKIN["consequence"] == surface.SKIN["consent"]


def test_the_shipped_strings_are_the_dialogs_own():
    """A string the operator reads was retyped rather than carried over."""
    dialog_text = DIALOG_PATH.read_text(encoding="utf-8")
    for literal in (
        surface.ACCESSIBLE_NAME,
        surface.WINDOW_TITLE,
        surface.REFUSE_TEXT,
        surface.CONSENT_TEXT_FORMAT.replace("{count}", "{count}"),
        surface.RELEASE_LOG,
        surface.MISSING_VERDICT,
        surface.HEADLINE,
        surface.DETAIL,
        surface.FACT_OBJECT_NAME,
        surface.CONSEQUENCE,
        surface.REFUSE,
        surface.CONSENT,
        surface.FACTS,
    ):
        assert literal in dialog_text, literal
    for line in (surface.REFUSE_LOG, surface.CONSENT_LOG, surface.BUILD_FAILED_LOG):
        for half in line.split(" "):
            assert half in dialog_text, half
    for half in surface.CONSENT_BLOCKED_TOOLTIP.split("directory. "):
        assert half in dialog_text, half


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
    import ast

    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any(name.startswith("PySide6") for name in imported), imported
    assert not any(name.startswith("shiboken") for name in imported), imported
    assert imported == {"logging", "types", "typing", "__future__", ""}
    dialog_tree = ast.parse(DIALOG_PATH.read_text(encoding="utf-8"))
    dialog_imports = {
        (node.module or "")
        for node in ast.walk(dialog_tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in dialog_imports), dialog_imports


def test_the_connect_sites_match_the_actions():
    """A signal wiring appeared on one side and not the other."""
    from PySide6.QtWidgets import QPushButton

    app()
    dialog = qt_dialog.InstanceConsentDialog(make_decision("plain"))
    row = dialog.layout().itemAt(4).layout()
    refuse = row.itemAt(1).widget()
    consent = row.itemAt(2).widget()
    live = refuse.receivers(CLICKED_SIGNAL) + consent.receivers(CLICKED_SIGNAL)
    assert live == 2
    assert refuse.receivers(CLICKED_SIGNAL) == 1
    assert consent.receivers(CLICKED_SIGNAL) == 1
    assert QPushButton("bare").receivers(CLICKED_SIGNAL) == 0

    dialog_text = DIALOG_PATH.read_text(encoding="utf-8")
    surface_text = SURFACE_PATH.read_text(encoding="utf-8")
    assert dialog_text.count(".connect(") == live == 2
    assert "self._refuse_button.clicked.connect(self._on_refuse)" in dialog_text
    assert "self._consent_button.clicked.connect(self._on_consent)" in dialog_text
    assert surface_text.count(".connect(") == 0
    assert len(surface.ACTIONS) == live
    assert set(surface.ACTIONS) == {"refuse.clicked", "consent.clicked"}
    assert surface.ACTIONS["refuse.clicked"] == "refuse"
    assert surface.ACTIONS["consent.clicked"] == "consent"
    for target in surface.ACTIONS.values():
        assert callable(getattr(surface.InstanceConsentModel, target)), target
    assert set(surface.BUTTON_ACTS) == set(BUTTON_TAGS)
    assert surface.BUTTON_ACTS[surface.REFUSE] is surface.InstanceConsentModel.refuse
    assert surface.BUTTON_ACTS[surface.CONSENT] is surface.InstanceConsentModel.consent


METHOD_MAP = {
    "InstanceConsentDialog.__init__": "InstanceConsentModel.build",
    "InstanceConsentDialog.consented": "InstanceConsentModel.consented",
    "InstanceConsentDialog._on_refuse": "InstanceConsentModel.refuse",
    "InstanceConsentDialog._on_consent": "InstanceConsentModel.consent",
    "InstanceConsentDialog.reject": "InstanceConsentModel.close_window",
    "release_dialog": "release_model",
    "ask_for_consent": "ask_model_for_consent",
}

INHERITED_MAP = {
    "QDialog.close": "InstanceConsentModel.close",
    "QWidget.setParent": "InstanceConsentModel.set_parent",
}

MODEL_MEMBERS = {
    "__init__",
    "consented",
    "build",
    "refuse",
    "consent",
    "close_window",
    "close",
    "set_parent",
}


def members(owner):
    """Every method and property a class defines, by name."""
    import inspect

    found = set()
    for name, value in vars(owner).items():
        if name.startswith("__") and name != "__init__":
            continue
        if inspect.isfunction(value) or isinstance(value, property):
            found.add(name)
    return found


def resolve(dotted):
    """The member a dotted name in the map points at, inside the surface."""
    found = surface
    for part in dotted.split("."):
        found = getattr(found, part)
    return found


def qt_member_names():
    """Every method and property the Qt module defines, as dotted names."""
    import inspect

    names = {
        name
        for name, value in vars(qt_dialog).items()
        if inspect.isfunction(value) and value.__module__ == qt_dialog.__name__
    }
    for member in members(qt_dialog.InstanceConsentDialog):
        names.add("InstanceConsentDialog." + member)
    return names


def test_every_dialog_member_has_a_counterpart():
    """A method exists on one side and nowhere on the other."""
    assert qt_member_names() == set(METHOD_MAP)
    assert len(METHOD_MAP) == 7
    for target in METHOD_MAP.values():
        assert resolve(target) is not None, target
    assert members(surface.InstanceConsentModel) == MODEL_MEMBERS
    assert len(MODEL_MEMBERS) == 8
    assert set(INHERITED_MAP.values()) < {
        "InstanceConsentModel." + name for name in MODEL_MEMBERS
    }
    assert len(INHERITED_MAP) == 2
    assert MODEL_MEMBERS - {name.split(".")[-1] for name in METHOD_MAP.values()} == {
        "__init__",
        "close",
        "set_parent",
    }


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    assert "InstanceConsentDialog._on_refuse" in qt_member_names()
    assert "InstanceConsentDialog.consented" in qt_member_names()
    assert "release_dialog" in qt_member_names()
    assert "InstanceConsentDialog.setStyleSheet" not in qt_member_names()
    assert "logger" not in qt_member_names()
    assert isinstance(vars(qt_dialog.InstanceConsentDialog)["consented"], property)
    assert isinstance(vars(surface.InstanceConsentModel)["consented"], property)
    with pytest.raises(AttributeError):
        resolve("InstanceConsentModel.no_such_member")
    assert MODEL_MEMBERS - {"build"} != MODEL_MEMBERS
    assert members(surface.InstanceConsentModel) - {"close"} != MODEL_MEMBERS
    assert members(qt_dialog.InstanceConsentDialog) == {
        "__init__",
        "consented",
        "_on_refuse",
        "_on_consent",
        "reject",
    }


CALL_NAMES = {
    "DIALOG_CONSENTED": "dialog.consented",
    "DIALOG_SET_ACCESSIBLE_NAME": "dialog.setAccessibleName",
    "DIALOG_SET_WINDOW_TITLE": "dialog.setWindowTitle",
    "DIALOG_SET_MODAL": "dialog.setModal",
    "DIALOG_SET_MINIMUM_WIDTH": "dialog.setMinimumWidth",
    "DIALOG_SET_STYLE_SHEET": "dialog.setStyleSheet",
    "LAYOUT_CREATE": "layout.create",
    "LAYOUT_SET_MARGINS": "layout.setContentsMargins",
    "LAYOUT_SET_SPACING": "layout.setSpacing",
    "LAYOUT_ADD_WIDGET": "layout.addWidget",
    "LAYOUT_ADD_LAYOUT": "layout.addLayout",
    "FACTS_CREATE": "facts.create",
    "FACTS_SET_OBJECT_NAME": "facts.setObjectName",
    "FACTS_LAYOUT_CREATE": "facts_layout.create",
    "FACTS_LAYOUT_SET_MARGINS": "facts_layout.setContentsMargins",
    "FACTS_LAYOUT_SET_SPACING": "facts_layout.setSpacing",
    "FACTS_LAYOUT_ADD_WIDGET": "facts_layout.addWidget",
    "ROW_CREATE": "row.create",
    "ROW_SET_SPACING": "row.setSpacing",
    "ROW_ADD_STRETCH": "row.addStretch",
    "ROW_ADD_WIDGET": "row.addWidget",
    "LABEL_CREATE": "label.create",
    "LABEL_SET_OBJECT_NAME": "label.setObjectName",
    "LABEL_SET_WORD_WRAP": "label.setWordWrap",
    "LABEL_SET_TEXT_INTERACTION": "label.setTextInteractionFlags",
    "BUTTON_CREATE": "button.create",
    "BUTTON_SET_OBJECT_NAME": "button.setObjectName",
    "BUTTON_SET_MINIMUM_HEIGHT": "button.setMinimumHeight",
    "BUTTON_SET_DEFAULT": "button.setDefault",
    "BUTTON_SET_AUTO_DEFAULT": "button.setAutoDefault",
    "BUTTON_SET_ENABLED": "button.setEnabled",
    "BUTTON_SET_TOOL_TIP": "button.setToolTip",
    "BUTTON_SET_FOCUS": "button.setFocus",
    "DIALOG_ACCEPT": "dialog.accept",
    "DIALOG_REJECT": "dialog.reject",
    "DIALOG_EXEC": "dialog.exec",
    "DIALOG_CLOSE": "dialog.close",
    "DIALOG_SET_PARENT": "dialog.setParent",
}


def test_the_call_names_are_the_ones_the_trace_writes():
    """The trace and the surface stopped agreeing on what to call a call.

    The Qt side of the trace builds each label from these literals, so a
    label read out of the surface cannot make both sides agree by
    definition.
    """
    for constant, literal in CALL_NAMES.items():
        assert getattr(surface, constant) == literal, constant
    assert len(set(CALL_NAMES.values())) == 38


def test_the_dialog_starts_no_timer():
    """A wait appeared on one side and not the other.

    The dialog waits on the operator, not on a clock. The watcher below
    counts every timer any Qt object starts while the dialog is built and
    every button is pressed, and its positive control proves it counts.
    """
    from PySide6.QtCore import QObject, QTimer

    app()
    started: list = []
    original_start_timer = QObject.startTimer
    original_timer_start = QTimer.start
    original_single_shot = QTimer.singleShot

    def watch_start_timer(self, *args, **kwargs):
        started.append(("startTimer", args))
        return original_start_timer(self, *args, **kwargs)

    def watch_timer_start(self, *args, **kwargs):
        started.append(("QTimer.start", args))
        return original_timer_start(self, *args, **kwargs)

    def watch_single_shot(*args, **kwargs):
        started.append(("singleShot", args))
        return original_single_shot(*args, **kwargs)

    QObject.startTimer = watch_start_timer
    QTimer.start = watch_timer_start
    QTimer.singleShot = watch_single_shot
    try:
        dialog = qt_dialog.InstanceConsentDialog(make_decision("plain"))
        dialog._on_consent()
        dialog._on_refuse()
        dialog.reject()
        observed = list(started)
        started.clear()
        QTimer().start(250)
    finally:
        QObject.startTimer = original_start_timer
        QTimer.start = original_timer_start
        QTimer.singleShot = original_single_shot
    assert started == [("QTimer.start", (250,))]
    assert observed == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert len(surface.TIMERS) == len(observed) == 0


def model_payload(spec, button=None, closed=False):
    """The surface payload for one decision case."""
    model = surface.InstanceConsentModel()
    fields = dict(DECISIONS[spec])
    fields.pop("raises", None)
    return surface.build_view_model(
        model,
        headline=str(fields.get("headline", "")),
        detail=str(fields.get("detail", "")),
        owner_line=str(fields.get("owner_line", "")),
        this_machine_line=str(fields.get("this_machine_line", "")),
        consequence_line=str(fields.get("consequence_line", "")),
        fleet_bot_count=fields.get("fleet_bot_count", 0),
        consent_is_possible=fields.get("consent_is_possible", True),
        verdict=fields.get("verdict", surface.MISSING_VERDICT),
        button=button,
        closed=closed,
    )


def dialog_painted_by_the_dialog(spec):
    """The shipped dialog, built from one decision case."""
    app()
    return qt_dialog.InstanceConsentDialog(make_decision(spec))


def dialog_painted_by_the_model(payload):
    """A bare dialog filled only from the payload, never from the dialog."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
    )

    properties = payload["widget"]
    dialog = QDialog()
    dialog.setAccessibleName(properties["accessible_name"])
    dialog.setWindowTitle(properties["window_title"])
    dialog.setModal(properties["modal"])
    dialog.setMinimumWidth(properties["minimum_width_px"])
    dialog.resize(properties["size_px"][0], properties["size_px"][1])
    dialog.setStyleSheet(properties["style_sheet"])

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(*payload["layout"]["margins_px"])
    layout.setSpacing(payload["layout"]["spacing_px"])

    def make_label(text, spec):
        label = QLabel(text)
        label.setObjectName(spec["object_name"])
        label.setWordWrap(spec["word_wrap"])
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag(spec["text_interaction_value"])
        )
        return label

    facts = QFrame()
    facts.setObjectName(payload["facts_frame"]["object_name"])
    facts_layout = QVBoxLayout(facts)
    facts_layout.setContentsMargins(*payload["facts_layout"]["margins_px"])
    facts_layout.setSpacing(payload["facts_layout"]["spacing_px"])
    fact_lines = {
        surface.OWNER: make_label(payload["owner_text"], payload["fact_label"]),
        surface.THIS_MACHINE: make_label(
            payload["this_machine_text"], payload["fact_label"]
        ),
    }
    for index, name in enumerate(payload["facts_layout"]["order"]):
        facts_layout.addWidget(
            fact_lines[name], payload["facts_layout"]["child_stretch"][index]
        )

    row = QHBoxLayout()
    row.setContentsMargins(*payload["button_row"]["margins_px"])
    row.setSpacing(payload["button_row"]["spacing_px"])

    pressable = {}
    for name in payload["button_row"]["order"]:
        if name == surface.STRETCH:
            continue
        spec = payload["buttons"][name]
        button = QPushButton(spec["text"])
        button.setObjectName(name)
        button.setMinimumHeight(spec["minimum_height_px"])
        button.setDefault(spec["is_default"])
        button.setAutoDefault(spec["is_default"])
        button.setEnabled(spec["enabled"])
        button.setToolTip(spec["tool_tip"])
        pressable[name] = button

    placed = {
        surface.HEADLINE: make_label(
            payload["headline_text"], payload["headline_label"]
        ),
        surface.DETAIL: make_label(payload["detail_text"], payload["detail_label"]),
        surface.FACTS: facts,
        surface.CONSEQUENCE: make_label(
            payload["consequence_text"], payload["consequence_label"]
        ),
    }
    for index, name in enumerate(payload["layout"]["order"]):
        if name == surface.BUTTON_ROW:
            layout.addLayout(row)
        else:
            layout.addWidget(placed[name], payload["layout"]["child_stretch"][index])
    for index, name in enumerate(payload["button_row"]["order"]):
        if name == surface.STRETCH:
            row.addStretch(payload["button_row"]["child_stretch"][index])
        else:
            row.addWidget(
                pressable[name], payload["button_row"]["child_stretch"][index]
            )
    pressable[payload["focus_on"]].setFocus()
    return dialog


PIXEL_SPECS = (
    "plain",
    "empty",
    "zero_bots",
    "negative_bots",
    "unicode",
    "consent_blocked",
    "long_spaced_headline",
    "markup_in_text",
)


@pytest.mark.parametrize("spec", PIXEL_SPECS)
def test_the_two_sides_render_the_same_pixels(spec):
    """The page paints a value, a colour or a position the dialog does not."""
    app()
    from_dialog = render_offscreen(dialog_painted_by_the_dialog(spec), PIXEL_SIZE)
    from_model = render_offscreen(
        dialog_painted_by_the_model(model_payload(spec)), PIXEL_SIZE
    )
    assert from_dialog.size() == from_model.size()
    assert image_digest(from_dialog) == image_digest(from_model)


def test_the_two_sides_paint_the_same_count_of_every_skin_colour():
    """The two sides declared one colour and painted another.

    The exact declared token is compared between the two sides, not
    against a number this test carries. A window asking for one colour
    can be painted a different one by the platform style, so a fixed
    count would be a statement about the operating system rather than
    about the product.
    """
    app()
    from_dialog = render_offscreen(dialog_painted_by_the_dialog("plain"), PIXEL_SIZE)
    from_model = render_offscreen(
        dialog_painted_by_the_model(model_payload("plain")), PIXEL_SIZE
    )
    painted = 0
    for name, token in surface.SKIN.items():
        shipped = colour_count(from_dialog, token)
        mirror = colour_count(from_model, token)
        assert shipped == mirror, name
        painted += 1 if shipped else 0
    assert painted >= 1
    assert colour_count(from_dialog, "#ff00ff") == colour_count(from_model, "#ff00ff")
    assert colour_count(from_dialog, "#ff00ff") == 0


def altered_digests(spec, alter, size=PIXEL_SIZE):
    """The shipped render and the render of a payload one edit apart."""
    app()
    payload = model_payload(spec)
    alter(payload)
    shipped = render_offscreen(dialog_painted_by_the_dialog(spec), size)
    altered = render_offscreen(dialog_painted_by_the_model(payload), size)
    return image_digest(shipped), image_digest(altered)


def _repaint_the_surface(payload):
    payload["widget"]["style_sheet"] = payload["widget"]["style_sheet"].replace(
        surface.SKIN["surface"], "#0a0a14"
    )


def _repaint_the_headline(payload):
    payload["widget"]["style_sheet"] = payload["widget"]["style_sheet"].replace(
        surface.SKIN["headline"], "#00aaff"
    )


def _repaint_the_consequence(payload):
    payload["widget"]["style_sheet"] = payload["widget"]["style_sheet"].replace(
        surface.SKIN["consequence"], "#00aaff"
    )


def _repaint_the_facts_panel(payload):
    payload["widget"]["style_sheet"] = payload["widget"]["style_sheet"].replace(
        surface.SKIN["facts_surface"], "#3a1414"
    )


def _repaint_the_refuse_border(payload):
    payload["widget"]["style_sheet"] = payload["widget"]["style_sheet"].replace(
        surface.SKIN["refuse"], "#ff8800"
    )


def _drop_the_style_sheet(payload):
    payload["widget"]["style_sheet"] = ""


def _move_the_margins(payload):
    payload["layout"]["margins_px"] = [40, 40, 40, 40]


def _move_the_facts_margins(payload):
    payload["facts_layout"]["margins_px"] = [2, 2, 2, 2]


def _move_the_button_row_margins(payload):
    payload["button_row"]["margins_px"] = [30, 30, 30, 30]


def _close_the_spacing(payload):
    payload["layout"]["spacing_px"] = 0


def _close_the_facts_spacing(payload):
    payload["facts_layout"]["spacing_px"] = 0


def _close_the_row_spacing(payload):
    payload["button_row"]["spacing_px"] = 0


def _stretch_the_facts(payload):
    payload["layout"]["child_stretch"] = [0, 0, 1, 0, 0]


def _swap_the_layout_order(payload):
    payload["layout"]["order"] = [
        surface.CONSEQUENCE,
        surface.DETAIL,
        surface.FACTS,
        surface.HEADLINE,
        surface.BUTTON_ROW,
    ]


def _swap_the_button_order(payload):
    payload["button_row"]["order"] = [
        surface.STRETCH,
        surface.CONSENT,
        surface.REFUSE,
    ]


def _move_the_stretch_to_the_end(payload):
    payload["button_row"]["order"] = [
        surface.REFUSE,
        surface.CONSENT,
        surface.STRETCH,
    ]
    payload["button_row"]["child_stretch"] = [0, 0, 1]


def _swap_the_fact_lines(payload):
    payload["facts_layout"]["order"] = [surface.THIS_MACHINE, surface.OWNER]


def _move_the_button_row_up(payload):
    payload["layout"]["order"] = [
        surface.HEADLINE,
        surface.BUTTON_ROW,
        surface.DETAIL,
        surface.FACTS,
        surface.CONSEQUENCE,
    ]


def _widen_the_minimum(payload):
    payload["widget"]["minimum_width_px"] = 900


def _rename_the_refuse_button(payload):
    payload["buttons"][surface.REFUSE]["text"] = "No"


def _rename_the_consent_button(payload):
    payload["buttons"][surface.CONSENT]["text"] = "Yes"


def _shrink_the_buttons(payload):
    payload["buttons"][surface.REFUSE]["minimum_height_px"] = 12
    payload["buttons"][surface.CONSENT]["minimum_height_px"] = 12


def _stop_the_word_wrap(payload):
    payload["headline_label"]["word_wrap"] = False


def _rename_the_headline_object(payload):
    payload["headline_label"]["object_name"] = surface.DETAIL


def _rename_the_facts_object(payload):
    payload["facts_frame"]["object_name"] = "not_facts"


def _rename_the_fact_object(payload):
    payload["fact_label"]["object_name"] = surface.DETAIL


def _shorten_the_headline(payload):
    payload["headline_text"] = "R"


def _blank_the_consequence(payload):
    payload["consequence_text"] = ""


def _blank_a_fact_line(payload):
    payload["owner_text"] = ""


PIXEL_DEFECTS = {
    "blank_a_fact_line": ("plain", _blank_a_fact_line),
    "blank_the_consequence": ("plain", _blank_the_consequence),
    "close_the_facts_spacing": ("plain", _close_the_facts_spacing),
    "close_the_row_spacing": ("plain", _close_the_row_spacing),
    "close_the_spacing": ("plain", _close_the_spacing),
    "drop_the_style_sheet": ("plain", _drop_the_style_sheet),
    "move_the_button_row_margins": ("plain", _move_the_button_row_margins),
    "move_the_button_row_up": ("plain", _move_the_button_row_up),
    "move_the_facts_margins": ("plain", _move_the_facts_margins),
    "move_the_margins": ("plain", _move_the_margins),
    "rename_the_consent_button": ("plain", _rename_the_consent_button),
    "rename_the_fact_object": ("plain", _rename_the_fact_object),
    "rename_the_facts_object": ("plain", _rename_the_facts_object),
    "rename_the_headline_object": ("plain", _rename_the_headline_object),
    "rename_the_refuse_button": ("plain", _rename_the_refuse_button),
    "repaint_the_consequence": ("plain", _repaint_the_consequence),
    "repaint_the_facts_panel": ("plain", _repaint_the_facts_panel),
    "repaint_the_headline": ("plain", _repaint_the_headline),
    "repaint_the_refuse_border": ("plain", _repaint_the_refuse_border),
    "repaint_the_surface": ("plain", _repaint_the_surface),
    "shorten_the_headline": ("long_headline", _shorten_the_headline),
    "shrink_the_buttons": ("plain", _shrink_the_buttons),
    "stop_the_word_wrap": ("long_spaced_headline", _stop_the_word_wrap),
    "stretch_the_facts": ("plain", _stretch_the_facts),
    "swap_the_button_order": ("plain", _swap_the_button_order),
    "swap_the_fact_lines": ("plain", _swap_the_fact_lines),
    "swap_the_layout_order": ("plain", _swap_the_layout_order),
    "move_the_stretch_to_the_end": (
        "plain",
        _move_the_stretch_to_the_end,
        WIDE_PIXEL_SIZE,
    ),
    "widen_the_minimum": ("plain", _widen_the_minimum),
}


@pytest.mark.parametrize("name", sorted(PIXEL_DEFECTS))
def test_the_pixel_check_reports_one_planted_defect(name):
    """The image comparison passes whatever the second side paints."""
    planted = PIXEL_DEFECTS[name]
    spec, alter = planted[0], planted[1]
    size = planted[2] if len(planted) > 2 else PIXEL_SIZE
    shipped, altered = altered_digests(spec, alter, size)
    assert shipped != altered


def test_the_wide_render_gives_the_button_row_room_to_move():
    """The stretch defects were measured at a width with no slack.

    The two stretch checks above only mean something where the row has
    free space to distribute. At the default width the two buttons fill
    the row and no arrangement can differ; at the wide width the spacer
    takes real pixels. Both widths are legal for this dialog, whose
    minimum width is smaller than either.
    """
    app()
    for size, expected_slack in ((PIXEL_SIZE, False), (WIDE_PIXEL_SIZE, True)):
        dialog = dialog_painted_by_the_dialog("plain")
        render_offscreen(dialog, size)
        row = dialog.layout().itemAt(4).layout()
        assert (row.itemAt(0).geometry().width() > 0) is expected_slack, size
        assert size[0] >= surface.MINIMUM_WIDTH_PX


def test_the_text_a_picture_may_not_show_is_compared_as_exact_strings():
    """The render was trusted to tell two strings of one length apart.

    A host with no font installed for the offscreen platform paints
    every character as the same empty box, so a same-length swap changes
    no pixel there. The host is asked at run time rather than assumed,
    and the string comparison reports the swap on every host either way.
    """
    app()
    shipped_payload = model_payload("plain")
    disguised = model_payload("plain")
    original = disguised["headline_text"]
    disguised["headline_text"] = "".join(
        " " if character == " " else "Z" for character in original
    )
    assert disguised["headline_text"] != original
    assert len(disguised["headline_text"]) == len(original)
    assert disguised["headline_text"].count(" ") == original.count(" ")
    shipped = render_offscreen(dialog_painted_by_the_model(shipped_payload), PIXEL_SIZE)
    swapped = render_offscreen(dialog_painted_by_the_model(disguised), PIXEL_SIZE)
    if host_has_fonts():
        assert image_digest(shipped) != image_digest(swapped)
    else:
        assert image_digest(shipped) == image_digest(swapped)
    assert shipped_payload["headline_text"] != disguised["headline_text"]


def test_the_tool_tip_a_picture_cannot_see_is_compared_as_a_string():
    """The reason a blocked consent gives never reaches a pixel."""
    app()
    blocked = model_payload("consent_blocked")
    disguised = model_payload("consent_blocked")
    disguised["buttons"][surface.CONSENT]["tool_tip"] = "different reason"
    shipped = render_offscreen(dialog_painted_by_the_model(blocked), PIXEL_SIZE)
    altered = render_offscreen(dialog_painted_by_the_model(disguised), PIXEL_SIZE)
    assert image_digest(shipped) == image_digest(altered)
    assert blocked["buttons"][surface.CONSENT]["tool_tip"] != (
        disguised["buttons"][surface.CONSENT]["tool_tip"]
    )
    assert (
        blocked["buttons"][surface.CONSENT]["tool_tip"]
        == surface.CONSENT_BLOCKED_TOOLTIP
    )
    assert model_payload("plain")["buttons"][surface.CONSENT]["tool_tip"] == ""


def test_the_answer_a_picture_cannot_see_is_compared_as_a_value(monkeypatch):
    """The answer the dialog carries never reaches a pixel.

    ``consented`` is painted nowhere, so no render can report a wrong
    answer. It is compared as an exact value in every trace, and the two
    values it can hold are pinned here.
    """
    old = run_old([(BUILD, "plain"), (CLICK, surface.CONSENT)], monkeypatch)
    assert old[1]["consented"] is False
    assert old[2]["consented"] is True
    assert surface.ANSWERS == (True, False)
    assert len(set(surface.ANSWERS)) == 2
    assert surface.DEFAULT_ANSWER is surface.ANSWER_REFUSE
    assert surface.CLOSED_ANSWER is surface.ANSWER_REFUSE
    assert surface.BUILD_FAILED_ANSWER is surface.ANSWER_REFUSE
    assert surface.ANSWER_CONSENT is True
    assert surface.BUTTON_ANSWERS == {surface.REFUSE: False, surface.CONSENT: True}
    same = model_payload("plain")
    other = model_payload("plain", button=surface.CONSENT)
    assert same["consented"] != other["consented"]
    assert same["headline_text"] == other["headline_text"]
    assert image_digest(
        render_offscreen(dialog_painted_by_the_model(same), PIXEL_SIZE)
    ) == image_digest(render_offscreen(dialog_painted_by_the_model(other), PIXEL_SIZE))


def test_the_default_button_a_picture_may_not_show_is_compared_as_a_flag():
    """Which button the Return key presses was left to the render."""
    app()
    dialog = qt_dialog.InstanceConsentDialog(make_decision("plain"))
    row = dialog.layout().itemAt(4).layout()
    assert row.itemAt(1).widget().isDefault() is surface.REFUSE_IS_DEFAULT
    assert row.itemAt(2).widget().isDefault() is surface.CONSENT_IS_DEFAULT
    assert surface.REFUSE_IS_DEFAULT is not surface.CONSENT_IS_DEFAULT
    swapped = model_payload("plain")
    swapped["buttons"][surface.REFUSE]["is_default"] = False
    swapped["buttons"][surface.CONSENT]["is_default"] = True
    shipped = render_offscreen(
        dialog_painted_by_the_model(model_payload("plain")), PIXEL_SIZE
    )
    altered = render_offscreen(dialog_painted_by_the_model(swapped), PIXEL_SIZE)
    if host_has_fonts():
        assert image_digest(shipped) == image_digest(altered)
    else:
        assert image_digest(shipped) == image_digest(altered)


def test_the_button_state_a_picture_cannot_see_is_compared_as_a_flag():
    """Whether a button can be pressed never reaches a pixel.

    The skin sets one text colour for every button and carries no
    disabled rule, so a disabled button paints exactly what an enabled
    one paints. The state is compared as an exact flag in every trace
    step and against the real widget below.
    """
    app()
    shipped = render_offscreen(
        dialog_painted_by_the_model(model_payload("plain")), PIXEL_SIZE
    )
    disabled = model_payload("plain")
    disabled["buttons"][surface.REFUSE]["enabled"] = False
    assert image_digest(
        render_offscreen(dialog_painted_by_the_model(disabled), PIXEL_SIZE)
    ) == image_digest(shipped)

    blocked_shipped = render_offscreen(
        dialog_painted_by_the_model(model_payload("consent_blocked")), PIXEL_SIZE
    )
    unblocked = model_payload("consent_blocked")
    unblocked["buttons"][surface.CONSENT]["enabled"] = True
    assert image_digest(
        render_offscreen(dialog_painted_by_the_model(unblocked), PIXEL_SIZE)
    ) == image_digest(blocked_shipped)
    assert ":disabled" not in surface.STYLE_SHEET

    dialog = dialog_painted_by_the_dialog("consent_blocked")
    row = dialog.layout().itemAt(4).layout()
    assert row.itemAt(2).widget().isEnabled() is False
    assert row.itemAt(1).widget().isEnabled() is surface.REFUSE_ENABLED
    model = surface.InstanceConsentModel()
    model.build(make_decision("consent_blocked"))
    assert model.consent_enabled is False
    model.build(make_decision("plain"))
    assert model.consent_enabled is True


def test_the_stretch_weight_a_picture_cannot_see_is_compared_as_a_number():
    """How hard the spacer pushes never reaches a pixel.

    ``addStretch`` places a spacer that expands whatever weight it
    carries, so dropping the weight to zero paints the same picture. The
    spacer's POSITION does change the picture, which is why
    ``move_the_stretch_to_the_end`` stays a pixel check. The weight is
    read off the real dialog as a number instead.
    """
    app()
    for size in (PIXEL_SIZE, WIDE_PIXEL_SIZE):
        shipped = render_offscreen(
            dialog_painted_by_the_model(model_payload("plain")), size
        )
        flattened = model_payload("plain")
        flattened["button_row"]["child_stretch"] = [0, 0, 0]
        assert image_digest(
            render_offscreen(dialog_painted_by_the_model(flattened), size)
        ) == image_digest(shipped), size
    dialog = dialog_painted_by_the_dialog("plain")
    row = dialog.layout().itemAt(4).layout()
    assert [row.stretch(index) for index in range(row.count())] == [1, 0, 0]
    assert surface.BUTTON_ROW_LAYOUT["child_stretch"] == [1, 0, 0]
    assert surface.STRETCH_WEIGHT == 1
    assert surface.BUTTON_ROW_LAYOUT["child_stretch"][0] == surface.STRETCH_WEIGHT


def test_the_focus_a_picture_cannot_see_is_compared_as_a_name():
    """Which button the keyboard starts on never reaches a pixel.

    The focus rule paints a ring only while the window is active, and an
    offscreen render has no active window. The focused child is read off
    the real dialog by name instead.
    """
    app()
    shipped = render_offscreen(
        dialog_painted_by_the_model(model_payload("plain")), PIXEL_SIZE
    )
    moved = model_payload("plain")
    moved["focus_on"] = surface.CONSENT
    assert image_digest(
        render_offscreen(dialog_painted_by_the_model(moved), PIXEL_SIZE)
    ) == image_digest(shipped)
    dialog = dialog_painted_by_the_dialog("plain")
    assert dialog.focusWidget().objectName() == surface.FOCUS_ON == surface.REFUSE
    assert dialog.focusWidget().objectName() != surface.CONSENT
    assert colour_count(shipped, surface.SKIN["focus_ring"]) == 0


BLIND_TO_THE_PICTURE = {
    "window_size": "test_widget_properties_match_the_dialog",
    "answer": "test_the_answer_a_picture_cannot_see_is_compared_as_a_value",
    "tool_tip": "test_the_tool_tip_a_picture_cannot_see_is_compared_as_a_string",
    "default_button": (
        "test_the_default_button_a_picture_may_not_show_is_compared_as_a_flag"
    ),
    "line_text": "test_the_text_a_picture_may_not_show_is_compared_as_exact_strings",
    "log_line": "test_the_log_lines_are_the_dialogs_own",
    "button_enabled": "test_the_button_state_a_picture_cannot_see_is_compared_as_a_flag",
    "focus": "test_the_focus_a_picture_cannot_see_is_compared_as_a_name",
    "stretch_weight": (
        "test_the_stretch_weight_a_picture_cannot_see_is_compared_as_a_number"
    ),
    "accessible_name": "test_widget_properties_match_the_dialog",
    "modal_flag": "test_widget_properties_match_the_dialog",
    "stays_on_top_flag": "test_widget_properties_match_the_dialog",
    "timer_delay": "test_the_dialog_starts_no_timer",
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report.

    Thirteen values never reach a pixel comparison, each named here
    with the check that does cover it. The window size is overwritten by
    the render size before the grab. The answer, the accessible name,
    the modal flag and the always-on-top flag are painted nowhere. The
    tool tip only appears when a pointer rests on the button. The log
    line goes to a file. The default-button flag paints no mark on this
    style. Whether a button can be pressed paints nothing, because the
    skin carries no disabled rule. The focus ring needs an active
    window, which an offscreen render has none of. The spacer's weight
    changes nothing because the spacer expands at any weight. Two
    strings of one length and one word shape paint the same boxes on a
    host with no glyphs. The dialog starts no timer, so no delay can be
    seen.
    """
    app()
    assert len(BLIND_TO_THE_PICTURE) == 13
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by

    shipped = render_offscreen(dialog_painted_by_the_dialog("plain"), PIXEL_SIZE)
    resized = model_payload("plain")
    resized["widget"]["size_px"] = [520, 360]
    assert image_digest(
        render_offscreen(dialog_painted_by_the_model(resized), PIXEL_SIZE)
    ) == image_digest(shipped)

    renamed = model_payload("plain")
    renamed["widget"]["accessible_name"] = "Something Else"
    renamed["widget"]["modal"] = False
    assert image_digest(
        render_offscreen(dialog_painted_by_the_model(renamed), PIXEL_SIZE)
    ) == image_digest(shipped)

    dialog = qt_dialog.InstanceConsentDialog(make_decision("plain"))
    assert list(surface.DEFAULT_SIZE_PX) == [dialog.width(), dialog.height()]


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    payload = model_payload("plain", button=surface.CONSENT)
    encoded = json.loads(json.dumps(payload))
    assert encoded["headline_text"] == DECISIONS["plain"]["headline"]
    assert encoded["consented"] is True
    assert encoded["built"] is True
    assert encoded["calls"][-1] == ["dialog.accept"]
    assert encoded["answers"] == [True, False]
    assert encoded["default_answer"] is False
    assert encoded["closed_answer"] is False
    assert encoded["build_failed_answer"] is False
    assert encoded["timers"] == {}
    assert encoded["timer_delays_ms"] == []
    assert encoded["focus_on"] == "refuse"
    assert encoded["button_bot_count"] == 37
    assert encoded["skin"]["headline"] == [255, 170, 0]
    assert encoded["skin"]["consequence"] == [255, 85, 119]
    assert encoded["skin"]["refuse"] == [0, 255, 204]
    assert encoded["skin"]["surface"] == [34, 34, 58]
    assert encoded["widget"]["accessible_name"] == "Instance Consent Dialog"
    assert encoded["widget"]["minimum_width_px"] == 560
    assert encoded["buttons"]["refuse"]["text"] == "Do not start bots"
    assert encoded["buttons"]["consent"]["text"] == (
        "Take ownership and start 37 bot(s)"
    )
    assert len(encoded["calls"]) == 56


def test_view_model_matches_the_dialog_on_the_same_decision(monkeypatch):
    """The bridge payload disagrees with the dialog on the same decision."""
    CALLS.clear()
    labels, buttons, _frames = trace_widgets(monkeypatch)
    dialog = qt_dialog.InstanceConsentDialog(make_decision("plain"))
    payload = model_payload("plain")
    assert payload["headline_text"] == labels[0].text()
    assert payload["detail_text"] == labels[1].text()
    assert payload["owner_text"] == labels[2].text()
    assert payload["this_machine_text"] == labels[3].text()
    assert payload["consequence_text"] == labels[4].text()
    assert payload["consented"] == dialog.consented
    assert [payload["buttons"][name]["text"] for name in BUTTON_TAGS] == [
        button.text() for button in buttons
    ]
    assert [payload["buttons"][name]["enabled"] for name in BUTTON_TAGS] == [
        button.isEnabled() for button in buttons
    ]


def test_the_surface_reads_a_real_guard_decision():
    """The surface disagrees with the product's own decision object."""
    from src.core import instance_guard

    app()
    identity = instance_guard.MachineIdentity(
        fingerprint="a" * 64,
        host="kiosk-01",
        os_user="anthony",
        platform="win32",
        strength="strong",
        source="registry",
    )
    decision = instance_guard.GuardDecision(
        verdict=instance_guard.VERDICT_FOREIGN_MACHINE,
        permits_auto_start=False,
        headline="This fleet was last used by another machine.",
        detail="Starting it here takes ownership away from that machine.",
        identity=identity,
        claim=None,
        claim_state="absent",
        lock_state=instance_guard.LOCK_ACQUIRED,
        fleet_bot_count=38,
    )
    dialog = qt_dialog.InstanceConsentDialog(decision)
    model = surface.InstanceConsentModel()
    model.build(decision)
    layout = dialog.layout()
    facts_layout = layout.itemAt(2).widget().layout()
    row = layout.itemAt(4).layout()
    assert model.headline_text == layout.itemAt(0).widget().text()
    assert model.detail_text == layout.itemAt(1).widget().text()
    assert model.owner_text == facts_layout.itemAt(0).widget().text()
    assert model.this_machine_text == facts_layout.itemAt(1).widget().text()
    assert model.consequence_text == layout.itemAt(3).widget().text()
    assert model.refuse_text == row.itemAt(1).widget().text()
    assert model.consent_button_text == row.itemAt(2).widget().text()
    assert model.consent_enabled is row.itemAt(2).widget().isEnabled()
    assert model.button_bot_count == 38
    assert model.consented is dialog.consented is False
    assert "38 bot(s)" in model.consequence_text
    assert model.owner_text == (
        "This fleet carries no record of the machine that last used it."
    )
    blocked = instance_guard.GuardDecision(
        verdict=instance_guard.VERDICT_LIVE_INSTANCE,
        permits_auto_start=False,
        headline="Another Acervator is running.",
        detail="Two copies on one account read the same wallet.",
        identity=identity,
        claim=None,
        claim_state="absent",
        lock_state="held_by_other",
        fleet_bot_count=38,
    )
    blocked_model = surface.InstanceConsentModel()
    blocked_model.build(blocked)
    assert blocked_model.consent_enabled is False
    assert blocked_model.consent_tool_tip == surface.CONSENT_BLOCKED_TOOLTIP


class ReleaseStub:
    """A surface whose two release calls are recorded, or made to raise."""

    def __init__(self, raise_on=None):
        self.raise_on = raise_on
        self.calls: list = []
        self.released = False

    def close(self):
        self.calls.append(surface.DIALOG_CLOSE)
        if self.raise_on == surface.DIALOG_CLOSE:
            raise RuntimeError("Internal C++ object already deleted.")

    def setParent(self, parent=None):
        self.calls.append(surface.DIALOG_SET_PARENT)
        if self.raise_on == surface.DIALOG_SET_PARENT:
            raise RuntimeError("Internal C++ object already deleted.")
        self.released = True

    def set_parent(self, parent=None):
        self.setParent(parent)


def test_release_runs_the_same_two_steps_in_the_same_order(capture_log):
    """The release order changed, or a step was dropped."""
    old_stub = ReleaseStub()
    with capture_log(LOGGER_NAME) as old_records:
        qt_dialog.release_dialog(old_stub)
    new_stub = ReleaseStub()
    with capture_log(LOGGER_NAME) as new_records:
        surface.release_model(new_stub)
    assert old_stub.calls == [surface.DIALOG_CLOSE, surface.DIALOG_SET_PARENT]
    assert new_stub.calls == old_stub.calls
    assert old_stub.released is new_stub.released is True
    assert [record.getMessage() for record in old_records] == []
    assert [record.getMessage() for record in new_records] == []


def test_release_of_nothing_does_nothing(monkeypatch, capture_log):
    """A missing surface was released anyway, or a stand-in was built.

    Neither side may create a surface in order to release one. The count
    of surfaces built during the call is what proves it, because a
    stand-in built and released inside the function leaves the log and
    the return value unchanged.
    """
    built: list = []

    class CountingModel(surface.InstanceConsentModel):
        def __init__(self):
            built.append(self)
            super().__init__()

    monkeypatch.setattr(surface, "InstanceConsentModel", CountingModel)
    monkeypatch.setattr(qt_dialog, "InstanceConsentDialog", CountingModel, raising=True)
    with capture_log(LOGGER_NAME) as old_records:
        assert qt_dialog.release_dialog(None) is None
    with capture_log(LOGGER_NAME) as new_records:
        assert surface.release_model(None) is None
    assert built == []
    assert [record.getMessage() for record in old_records] == []
    assert [record.getMessage() for record in new_records] == []
    surface.release_model(CountingModel())
    assert len(built) == 1
    built.clear()
    positive = ReleaseStub(raise_on=surface.DIALOG_CLOSE)
    with capture_log(LOGGER_NAME) as noisy:
        surface.release_model(positive)
    assert len(noisy) == 1
    assert built == []


def test_a_surface_already_destroyed_is_reported_not_raised(capture_log):
    """A release of a destroyed window took the launch down."""
    for step in (surface.DIALOG_CLOSE, surface.DIALOG_SET_PARENT):
        old_stub = ReleaseStub(raise_on=step)
        with capture_log(LOGGER_NAME) as old_records:
            qt_dialog.release_dialog(old_stub)
        new_stub = ReleaseStub(raise_on=step)
        with capture_log(LOGGER_NAME) as new_records:
            surface.release_model(new_stub)
        old_logs = [record.getMessage() for record in old_records]
        new_logs = [record.getMessage() for record in new_records]
        assert new_logs == old_logs, step
        assert len(old_logs) == 1, step
        assert old_logs[0] == (
            "instance consent dialog was already destroyed: "
            "Internal C++ object already deleted."
        )
        assert new_stub.calls == old_stub.calls, step
        assert new_stub.released is old_stub.released
    assert surface.RELEASE_LOG == "instance consent dialog was already destroyed: %s"


def ask_old(spec, press=None, exec_result="accepted", monkeypatch=None):
    """Drive ``ask_for_consent`` with a stubbed modal loop."""
    app()
    patch = ClassPatch(qt_dialog.InstanceConsentDialog)
    seen: list = []

    def exec_modal(self):
        seen.append(self)
        if press == surface.REFUSE:
            self._on_refuse()
        elif press == surface.CONSENT:
            self._on_consent()
        elif press == CLOSE:
            self.reject()
        return 1 if exec_result == "accepted" else 0

    patch.set("exec", exec_modal)
    try:
        return qt_dialog.ask_for_consent(make_decision(spec)), seen
    finally:
        patch.undo()


def ask_new(spec, press=None):
    """Drive ``ask_model_for_consent`` on the same decision."""
    seen: list = []

    def factory():
        model = surface.InstanceConsentModel()
        seen.append(model)
        return model

    granted = surface.ask_model_for_consent(
        make_decision(spec),
        button=None if press in (None, CLOSE) else press,
        closed=press == CLOSE,
        factory=factory,
    )
    return granted, seen


ASK_CASES = {
    "granted": ("plain", surface.CONSENT, True),
    "refused": ("plain", surface.REFUSE, False),
    "closed": ("plain", CLOSE, False),
    "untouched": ("plain", None, False),
    "blocked_untouched": ("consent_blocked", None, False),
    "unicode_granted": ("unicode", surface.CONSENT, True),
    "zero_granted": ("zero_bots", surface.CONSENT, True),
    "unbuildable": ("unknown_input", None, False),
    "raising_line": ("consequence_raises", None, False),
}


@pytest.mark.parametrize("name", sorted(ASK_CASES))
def test_ask_for_consent_answers_the_same_way(name, capture_log):
    """The launch got a different answer from the two sides."""
    spec, press, expected = ASK_CASES[name]
    with capture_log(LOGGER_NAME) as old_records:
        old_answer, old_seen = ask_old(spec, press)
    with capture_log(LOGGER_NAME) as new_records:
        new_answer, new_seen = ask_new(spec, press)
    assert old_answer is expected, name
    assert new_answer == old_answer, name
    assert [record.getMessage() for record in new_records] == [
        record.getMessage() for record in old_records
    ], name
    assert len(new_seen) == 1
    assert (len(old_seen) == 1) is (spec not in UNBUILDABLE)


def test_a_dialog_that_cannot_be_built_is_a_refusal(capture_log):
    """A surface the operator never saw collected a consent."""
    with capture_log(LOGGER_NAME) as old_records:
        old_answer, old_seen = ask_old("unknown_input")
    old_logs = [record.getMessage() for record in old_records]
    with capture_log(LOGGER_NAME) as new_records:
        new_answer, _new_seen = ask_new("unknown_input")
    new_logs = [record.getMessage() for record in new_records]
    assert old_answer is False
    assert new_answer is old_answer
    assert old_seen == []
    assert len(old_logs) == 1
    assert new_logs == old_logs
    assert old_logs[0].startswith("instance consent dialog could not be shown (")
    assert "Treating this as a refusal" in old_logs[0]
    assert surface.BUILD_FAILED_ANSWER is False
    with capture_log(LOGGER_NAME) as quiet_records:
        good_answer, good_seen = ask_old("plain", surface.CONSENT)
    assert good_answer is True
    assert len(good_seen) == 1
    assert len([record for record in quiet_records if record.levelname == "ERROR"]) == 0


def test_a_failed_build_is_never_released(capture_log):
    """A surface that was never built was released anyway."""
    released: list = []

    class CountingModel(surface.InstanceConsentModel):
        def set_parent(self, parent=None):
            released.append(parent)
            super().set_parent(parent)

    with capture_log(LOGGER_NAME):
        surface.ask_model_for_consent(
            make_decision("unknown_input"), factory=CountingModel
        )
    assert released == [None]
    released.clear()
    with capture_log(LOGGER_NAME):
        surface.ask_model_for_consent(make_decision("plain"), factory=CountingModel)
    assert released == [None]
    released.clear()

    def refuse_to_build():
        raise RuntimeError("no surface could be created")

    with capture_log(LOGGER_NAME) as records:
        answer = surface.ask_model_for_consent(
            make_decision("plain"), factory=refuse_to_build
        )
    assert answer is False
    assert released == []
    assert len(records) == 1


def test_bridge_registers_the_instance_consent_method():
    """The renderer cannot reach the consent surface through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "instance_consent.state"
    assert registry[surface.METHOD] is surface.view_model
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 51,
                "method": surface.METHOD,
                "params": {
                    "reset": True,
                    "headline": "Another machine owns this fleet.",
                    "detail": "Starting it here takes ownership.",
                    "owner_line": "Last used by kiosk-01 (anthony).",
                    "this_machine_line": "This machine is laptop-02 (anthony).",
                    "consequence_line": "37 bot(s) against the live account.",
                    "fleet_bot_count": 37,
                    "consent_is_possible": True,
                    "verdict": "foreign_machine",
                },
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    assert answer["result"]["headline_text"] == "Another machine owns this fleet."
    assert answer["result"]["consented"] is False
    assert answer["result"]["buttons"]["consent"]["text"] == (
        "Take ownership and start 37 bot(s)"
    )


def test_the_bridge_carries_every_button():
    """A button press over the bridge changed nothing."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()

    def call(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 52, "method": surface.METHOD, "params": params}),
            registry,
        )["result"]

    for name, expected in surface.BUTTON_ANSWERS.items():
        pressed = call({"reset": True, "headline": "H", "button": name})
        assert pressed["consented"] is expected, name
    closed = call({"reset": True, "headline": "H", "closed": True})
    assert closed["consented"] is surface.CLOSED_ANSWER
    untouched = call({"reset": True, "headline": "H"})
    assert untouched["consented"] is surface.DEFAULT_ANSWER
    blocked = call({"reset": True, "consent_is_possible": False})
    assert blocked["buttons"]["consent"]["enabled"] is False
    assert blocked["buttons"]["consent"]["tool_tip"] == surface.CONSENT_BLOCKED_TOOLTIP
    assert call({"reset": True})["buttons"]["consent"]["text"] == (
        "Take ownership and start 0 bot(s)"
    )
    call({"reset": True})


def test_the_bridge_keeps_the_answer_until_a_reset():
    """The dialog forgot its answer between two bridge calls."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()

    def call(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 53, "method": surface.METHOD, "params": params}),
            registry,
        )["result"]

    call({"reset": True, "headline": "H", "button": surface.CONSENT})
    kept = call({"headline": "H"})
    assert len(kept["calls"]) > 56
    assert call({"reset": True, "headline": "H"})["calls"] == kept["calls"][-54:]
    call({"reset": True})


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'instance_consent.state', 'params':"
    " {'reset': True, 'headline': 'Another machine owns this fleet.',"
    " 'detail': 'Starting it here takes ownership.',"
    " 'owner_line': 'Last used by kiosk-01 (anthony).',"
    " 'this_machine_line': 'This machine is laptop-02 (anthony).',"
    " 'consequence_line': '37 bot(s) against the live account.',"
    " 'fleet_bot_count': 37, 'consent_is_possible': True,"
    " 'verdict': 'foreign_machine'}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)


def run_probe(prelude):
    done = subprocess.run(
        [sys.executable, "-"],
        input=(prelude + QT_PROBE).encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the consent surface pulled Qt into the backend process."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["headline_text"] == "Another machine owns this fleet."
    assert result["widget"]["window_title"] == "Acervator - start the saved fleet?"
    assert result["buttons"]["refuse"]["text"] == "Do not start bots"
    assert result["buttons"]["consent"]["text"] == "Take ownership and start 37 bot(s)"
    assert result["consented"] is False


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


BLOCK_QT = (
    "import sys\n"
    "import importlib.abc\n"
    "class _Refuse(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'PySide6' or name.startswith('PySide6.'):\n"
    "            raise ImportError('PySide6 blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, _Refuse())\n"
)

HEADLESS_PROBE = BLOCK_QT + (
    "import json, sys\n"
    "from src.gui.main_tabs import instance_consent_surface as s\n"
    "model = s.InstanceConsentModel()\n"
    "model.build(s.decision_facts(headline='H', detail='D', owner_line='O',\n"
    "    this_machine_line='T', consequence_line='C', fleet_bot_count=37,\n"
    "    consent_is_possible=True, verdict='foreign_machine'))\n"
    "model.consent()\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'consented': model.consented,\n"
    "    'consent_text': model.consent_button_text,\n"
    "    'calls': len(model.calls)}))\n"
)


def test_the_surface_builds_in_a_process_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    done = subprocess.run(
        [sys.executable, "-"],
        input=HEADLESS_PROBE.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    answered = json.loads(done.stdout.decode().splitlines()[-1])
    assert answered["qt"] is False
    assert answered["consented"] is True
    assert answered["consent_text"] == "Take ownership and start 37 bot(s)"
    assert answered["calls"] == 56


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    done = subprocess.run(
        [sys.executable, "-"],
        input=probe.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    assert json.loads(done.stdout.decode().splitlines()[-1])["qt"] is True


def test_the_qt_block_stops_the_dialog_module():
    """The Qt block let a module through that imports PySide6."""
    probe = BLOCK_QT + (
        "import json\n"
        "try:\n"
        "    from src.gui import instance_consent_dialog\n"
        "    blocked = False\n"
        "except ImportError:\n"
        "    blocked = True\n"
        "print(json.dumps({'blocked': blocked}))\n"
    )
    done = subprocess.run(
        [sys.executable, "-"],
        input=probe.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    assert json.loads(done.stdout.decode().splitlines()[-1])["blocked"] is True
