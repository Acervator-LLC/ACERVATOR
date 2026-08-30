"""The Qt setup wizard and the Qt-free surface, side by side.

A failure means the view model writes a different page title, field,
placeholder, switch, venue entry, colour, status line, answer, refusal
or sequence of calls than ``InitWizard`` does on the same input.

Every credential in this file is invented. Nothing here reads or writes
the runtime tree, and no venue is contacted: the credential test runs
through a stub handed to both sides.
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

from src.gui import init_wizard as shipped
from src.gui.main_tabs import init_wizard_surface as surface
from tests.fixtures.host_fonts import has_real_fonts
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
WIZARD_PATH = REPO_ROOT / "src/gui/init_wizard.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/init_wizard_surface.py"
BRIDGE_PATH = REPO_ROOT / "src/core/desktop_bridge.py"
HISTORY_PATH = REPO_ROOT / "src/gui/history_tab.py"
VISUALIZER_PATH = REPO_ROOT / "src/gui/bot_visualizer.py"

METHOD_NAME = "init_wizard.state"
CLICKED_SIGNAL = "2clicked()"
TOGGLED_SIGNAL = "2toggled(bool)"
CURRENT_ID_SIGNAL = "2currentIdChanged(int)"

PAGE_SIZE = (560, 380)

BUILD = "build"
SET = "set"
CHECK = "check"
PICK = "pick"
PAGE = "page"
TEST = "test"
SKIP = "skip"
VALIDATE = "validate"
RESULTS = "results"

CALLS: list[list] = []
WARNINGS: list[list] = []
PAGE_CELL = [surface.NO_PAGE_ID]
CHECK_ORDER = [surface.CHECK_TAGS]
ALIVE: list = []


def app():
    """The process application object every render and widget needs."""
    from qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    """One offscreen render of `widget`, at `size`."""
    from qt_pixel import render_widget

    return render_widget(widget, size)


def digest(trace):
    """A SHA-256 over every value one trace carries."""
    return hashlib.sha256(
        json.dumps(trace, sort_keys=True, default=repr).encode("utf-8")
    ).hexdigest()


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


class Factory:
    """A recording stand-in for one Qt class.

    Calling it builds the real widget and records what came off it.
    Every other name, such as an enum member the wizard reads, is the
    real class's own.
    """

    def __init__(self, real, make):
        self.real = real
        self.make = make

    def __call__(self, *args, **kwargs):
        return self.make(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.real, name)


class Answer:
    """One stubbed credential-test answer, of the shape the wizard reads."""

    def __init__(self, success, message):
        self.success = success
        self.message = message


NAMES = {
    "plain": "Ann",
    "empty": "",
    "blank": "   ",
    "unicode": "Δ→⚡ Ann",
    "long": "x" * 200,
    "markup": "<b>bold</b> & co",
    "apostrophe": "O'Brien",
    "wrong_capitals": "aNN bROWN",
    "newline": "Ann\nBrown",
    "nothing": None,
    "number": 42,
    "fraction": 3.5,
    "thousand_million": 1000000000,
    "one_billionth": 1e-9,
    "infinity": float("inf"),
    "truth": True,
    "listed": ["Ann"],
    "raw_bytes": b"Ann",
}

INDEXES = {
    "first": 0,
    "venue_with_note": 11,
    "last": 14,
    "negative": -1,
    "past_the_end": 15,
    "thousand_million": 1000000000,
    "one_billionth": 1e-9,
    "fraction": 1.5,
    "infinity": float("inf"),
    "text": "kucoin",
    "nothing": None,
    "truth": True,
    "huge": 10**18,
}

SWITCHES = {
    "on": True,
    "off": False,
    "one": 1,
    "zero": 0,
    "text": "yes",
    "nothing": None,
    "fraction": 0.0,
}

OUTCOMES = {
    "ok": (True, "Connected to Kucoin. 900 markets, 3 assets with balance."),
    "refused": (False, "Invalid API key."),
    "empty_message": (False, ""),
    "unicode_message": (True, "Δ→⚡ connected"),
    "long_message": (False, "y" * 200),
    "markup_message": (False, "<b>bad</b> & key"),
    "apostrophe_message": (False, "the venue's refusal"),
    "newline_message": (False, "line one\nline two"),
    "raised": None,
}

RAISED_TEXT = "ccxt package not installed."

INVENTED = (
    "invented-key-0001",
    "invented-secret-0001",
    "invented-phrase-0001",
)
INVENTED_KEY, INVENTED_SECRET, INVENTED_PASSPHRASE = INVENTED


def outcome_answer(name):
    """The stubbed answer one named outcome gives, or the error it raises."""
    found = OUTCOMES[name]
    if found is None:
        raise RuntimeError(RAISED_TEXT)
    return Answer(found[0], found[1])


def trace_widgets(monkeypatch):
    """Swap the wizard's widget classes for recording stand-ins.

    Every recorded value is read back off the real widget, so a wrong
    value reaches the trace rather than the value the wizard was told.
    """
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QLabel,
        QLineEdit,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
        QWizardPage,
    )

    labels: list = []
    lines: list = []
    checks: list = []
    buttons: list = []
    boxes: list = []
    combos: list = []
    pages: list = []
    layouts: list = []

    def make_label(text=""):
        label = QLabel(text)
        tag = surface.LABEL_TAGS[len(labels)]
        label.acervator_tag = tag
        labels.append(label)
        CALLS.append([surface.LABEL_CREATE, tag, label.text()])

        def set_word_wrap(on):
            QLabel.setWordWrap(label, on)
            CALLS.append([surface.LABEL_SET_WORD_WRAP, tag, label.wordWrap()])

        def set_property(name, value):
            QLabel.setProperty(label, name, value)
            CALLS.append([surface.LABEL_SET_PROPERTY, tag, name, label.property(name)])

        def set_text(value):
            QLabel.setText(label, value)
            CALLS.append([surface.LABEL_SET_TEXT, tag, label.text()])

        def set_style_sheet(sheet):
            QLabel.setStyleSheet(label, sheet)
            CALLS.append([surface.LABEL_SET_STYLE_SHEET, tag, label.styleSheet()])

        def set_visible(on):
            QLabel.setVisible(label, on)
            CALLS.append([surface.LABEL_SET_VISIBLE, tag, not label.isHidden()])

        label.setWordWrap = set_word_wrap
        label.setProperty = set_property
        label.setText = set_text
        label.setStyleSheet = set_style_sheet
        label.setVisible = set_visible
        return label

    def make_line():
        line = QLineEdit()
        tag = surface.LINE_TAGS[len(lines)]
        line.acervator_tag = tag
        lines.append(line)
        CALLS.append([surface.LINE_CREATE, tag, line.text()])

        def set_placeholder(text):
            QLineEdit.setPlaceholderText(line, text)
            CALLS.append([surface.LINE_SET_PLACEHOLDER, tag, line.placeholderText()])

        def set_text(value):
            QLineEdit.setText(line, value)
            CALLS.append([surface.LINE_SET_TEXT, tag, line.text()])

        def set_echo_mode(mode):
            QLineEdit.setEchoMode(line, mode)
            CALLS.append([surface.LINE_SET_ECHO_MODE, tag, line.echoMode().value])

        def set_visible(on):
            QLineEdit.setVisible(line, on)
            CALLS.append([surface.LINE_SET_VISIBLE, tag, not line.isHidden()])

        line.setPlaceholderText = set_placeholder
        line.setText = set_text
        line.setEchoMode = set_echo_mode
        line.setVisible = set_visible
        return line

    def make_text():
        box = QTextEdit()
        tag = surface.TEXT_TAGS[len(boxes)]
        box.acervator_tag = tag
        boxes.append(box)
        CALLS.append([surface.TEXT_CREATE, tag, box.toPlainText()])

        def set_maximum_height(height):
            QTextEdit.setMaximumHeight(box, height)
            CALLS.append([surface.TEXT_SET_MAXIMUM_HEIGHT, tag, box.maximumHeight()])

        def set_placeholder(text):
            QTextEdit.setPlaceholderText(box, text)
            CALLS.append([surface.TEXT_SET_PLACEHOLDER, tag, box.placeholderText()])

        def set_tool_tip(text):
            QTextEdit.setToolTip(box, text)
            CALLS.append([surface.TEXT_SET_TOOL_TIP, tag, box.toolTip()])

        def set_plain_text(value):
            QTextEdit.setPlainText(box, value)
            CALLS.append([surface.TEXT_SET_PLAIN_TEXT, tag, box.toPlainText()])

        def set_style_sheet(sheet):
            QTextEdit.setStyleSheet(box, sheet)
            CALLS.append([surface.TEXT_SET_STYLE_SHEET, tag, box.styleSheet()])

        box.setMaximumHeight = set_maximum_height
        box.setPlaceholderText = set_placeholder
        box.setToolTip = set_tool_tip
        box.setPlainText = set_plain_text
        box.setStyleSheet = set_style_sheet
        return box

    def make_check(text=""):
        check = QCheckBox(text)
        tag = CHECK_ORDER[0][len(checks)]
        check.acervator_tag = tag
        checks.append(check)
        CALLS.append([surface.CHECK_CREATE, tag, check.text()])

        def set_tool_tip(value):
            QCheckBox.setToolTip(check, value)
            CALLS.append([surface.CHECK_SET_TOOL_TIP, tag, check.toolTip()])

        def set_checked(on):
            QCheckBox.setChecked(check, on)
            CALLS.append([surface.CHECK_SET_CHECKED, tag, check.isChecked()])

        check.setToolTip = set_tool_tip
        check.setChecked = set_checked
        return check

    def make_button(text=""):
        button = QPushButton(text)
        tag = surface.BUTTON_TAGS[len(buttons)]
        button.acervator_tag = tag
        buttons.append(button)
        CALLS.append([surface.BUTTON_CREATE, tag, button.text()])

        def set_tool_tip(value):
            QPushButton.setToolTip(button, value)
            CALLS.append([surface.BUTTON_SET_TOOL_TIP, tag, button.toolTip()])

        def set_style_sheet(sheet):
            QPushButton.setStyleSheet(button, sheet)
            CALLS.append([surface.BUTTON_SET_STYLE_SHEET, tag, button.styleSheet()])

        def set_enabled(on):
            QPushButton.setEnabled(button, on)
            CALLS.append([surface.BUTTON_SET_ENABLED, tag, button.isEnabled()])

        button.setToolTip = set_tool_tip
        button.setStyleSheet = set_style_sheet
        button.setEnabled = set_enabled
        return button

    def make_combo():
        combo = QComboBox()
        tag = surface.COMBO_TAGS[len(combos)]
        combo.acervator_tag = tag
        combos.append(combo)
        CALLS.append([surface.COMBO_CREATE, tag])

        def add_item(label, data=None):
            QComboBox.addItem(combo, label, data)
            last = combo.count() - 1
            CALLS.append(
                [
                    surface.COMBO_ADD_ITEM,
                    tag,
                    combo.itemText(last),
                    combo.itemData(last),
                ]
            )

        def set_current_index(index):
            QComboBox.setCurrentIndex(combo, index)
            CALLS.append([surface.COMBO_SET_CURRENT_INDEX, tag, combo.currentIndex()])

        combo.addItem = add_item
        combo.setCurrentIndex = set_current_index
        return combo

    def make_page():
        page = QWizardPage()
        tag = surface.PAGES[len(pages)]
        page.acervator_tag = tag
        pages.append(page)
        CALLS.append([surface.PAGE_CREATE, tag])

        def set_title(text):
            QWizardPage.setTitle(page, text)
            CALLS.append([surface.PAGE_SET_TITLE, tag, page.title()])

        def set_sub_title(text):
            QWizardPage.setSubTitle(page, text)
            CALLS.append([surface.PAGE_SET_SUB_TITLE, tag, page.subTitle()])

        def set_final_page(on):
            QWizardPage.setFinalPage(page, on)
            CALLS.append([surface.PAGE_SET_FINAL, tag, page.isFinalPage()])

        page.setTitle = set_title
        page.setSubTitle = set_sub_title
        page.setFinalPage = set_final_page
        return page

    def make_layout(parent=None):
        layout = QVBoxLayout(parent)
        tag = surface.PAGES[len(layouts)]
        layouts.append(layout)
        CALLS.append([surface.LAYOUT_CREATE, tag])

        def add_widget(widget, *args):
            QVBoxLayout.addWidget(layout, widget, *args)
            CALLS.append([surface.LAYOUT_ADD_WIDGET, tag, widget.acervator_tag])

        def add_spacing(size):
            QVBoxLayout.addSpacing(layout, size)
            spacer = layout.itemAt(layout.count() - 1).spacerItem()
            CALLS.append([surface.LAYOUT_ADD_SPACING, tag, spacer.sizeHint().height()])

        layout.addWidget = add_widget
        layout.addSpacing = add_spacing
        return layout

    class WarningBox:
        """A stand-in for the message box the username check raises."""

        @staticmethod
        def warning(parent, title, text):
            WARNINGS.append([title, text])
            CALLS.append([surface.MESSAGE_BOX_WARNING, title, text])

    def record_safe_events(reason="", _force=False):
        CALLS.append([surface.SAFE_PROCESS_EVENTS, reason])
        return False

    monkeypatch.setattr(shipped, "QLabel", Factory(QLabel, make_label))
    monkeypatch.setattr(shipped, "QLineEdit", Factory(QLineEdit, make_line))
    monkeypatch.setattr(shipped, "QTextEdit", Factory(QTextEdit, make_text))
    monkeypatch.setattr(shipped, "QCheckBox", Factory(QCheckBox, make_check))
    monkeypatch.setattr(shipped, "QPushButton", Factory(QPushButton, make_button))
    monkeypatch.setattr(shipped, "QComboBox", Factory(QComboBox, make_combo))
    monkeypatch.setattr(shipped, "QWizardPage", Factory(QWizardPage, make_page))
    monkeypatch.setattr(shipped, "QVBoxLayout", Factory(QVBoxLayout, make_layout))
    monkeypatch.setattr(shipped, "QMessageBox", WarningBox)
    monkeypatch.setattr(shipped, "safe_process_events", record_safe_events)
    return labels, lines, checks, buttons, boxes, combos


def trace_wizard_methods():
    """Record the calls the wizard makes on itself. Returns the patch."""
    from PySide6.QtWidgets import QWizard

    target = shipped.InitWizard
    patch = ClassPatch(target)

    def set_window_title(self, title):
        QWizard.setWindowTitle(self, title)
        CALLS.append([surface.WIZARD_SET_WINDOW_TITLE, self.windowTitle()])

    def set_minimum_size(self, width, height):
        QWizard.setMinimumSize(self, width, height)
        CALLS.append(
            [
                surface.WIZARD_SET_MINIMUM_SIZE,
                [self.minimumWidth(), self.minimumHeight()],
            ]
        )

    def set_wizard_style(self, style):
        QWizard.setWizardStyle(self, style)
        CALLS.append([surface.WIZARD_SET_WIZARD_STYLE, self.wizardStyle().value])

    def add_page(self, page):
        page_id = QWizard.addPage(self, page)
        CALLS.append([surface.WIZARD_ADD_PAGE, page.acervator_tag, page_id])
        return page_id

    def reject(self):
        QWizard.reject(self)
        CALLS.append([surface.WIZARD_REJECT])

    def current_id(self):
        return PAGE_CELL[0]

    patch.set("setWindowTitle", set_window_title)
    patch.set("setMinimumSize", set_minimum_size)
    patch.set("setWizardStyle", set_wizard_style)
    patch.set("addPage", add_page)
    patch.set("reject", reject)
    patch.set("currentId", current_id)
    return patch


def stub_validator(monkeypatch, outcome):
    """Point the wizard's credential check at one named stubbed answer."""
    from src.exchange import api_validator

    def validate(exchange_id, _api_key, _api_secret, _passphrase):
        CALLS.append([surface.VALIDATE_CALL, exchange_id])
        return outcome_answer(outcome)

    monkeypatch.setattr(api_validator, "validate_credentials", validate)


def surface_validator(outcome):
    """The same stubbed answer, for the surface's own credential test."""

    def validate(_exchange_id, _api_key, _api_secret, _passphrase):
        return outcome_answer(outcome)

    return validate


SCRIPTS: dict[str, list] = {}
for _name, _value in NAMES.items():
    SCRIPTS["name_" + _name] = [
        (BUILD, False),
        (SET, surface.USERNAME, _value),
        (PAGE, 0),
        (VALIDATE,),
        (RESULTS,),
    ]
    SCRIPTS["key_" + _name] = [
        (BUILD, False),
        (SET, surface.API_KEY, _value),
        (SET, surface.API_SECRET, INVENTED_SECRET),
        (TEST, "ok"),
        (RESULTS,),
    ]
    SCRIPTS["secret_" + _name] = [
        (BUILD, False),
        (SET, surface.API_KEY, INVENTED_KEY),
        (SET, surface.API_SECRET, _value),
        (TEST, "ok"),
        (RESULTS,),
    ]
    SCRIPTS["passphrase_" + _name] = [
        (BUILD, False),
        (PICK, 11),
        (SET, surface.PASSPHRASE, _value),
        (PAGE, 2),
        (RESULTS,),
    ]
for _name, _value in INDEXES.items():
    SCRIPTS["index_" + _name] = [
        (BUILD, False),
        (PICK, _value),
        (PAGE, 2),
        (SET, surface.API_KEY, INVENTED_KEY),
        (SET, surface.API_SECRET, INVENTED_SECRET),
        (TEST, "ok"),
        (RESULTS,),
    ]
for _name, _value in SWITCHES.items():
    SCRIPTS["show_key_" + _name] = [
        (BUILD, False),
        (CHECK, surface.SHOW_KEY, _value),
        (RESULTS,),
    ]
    SCRIPTS["skip_creds_" + _name] = [
        (BUILD, False),
        (SET, surface.API_KEY, INVENTED_KEY),
        (SET, surface.API_SECRET, INVENTED_SECRET),
        (SET, surface.PASSPHRASE, INVENTED_PASSPHRASE),
        (CHECK, surface.SKIP_CREDS, _value),
        (RESULTS,),
    ]
    SCRIPTS["fresh_start_" + _name] = [
        (BUILD, True),
        (CHECK, surface.FRESH_START, _value),
        (RESULTS,),
    ]
    SCRIPTS["fresh_start_absent_" + _name] = [
        (BUILD, False),
        (CHECK, surface.FRESH_START, _value),
        (RESULTS,),
    ]
for _name in OUTCOMES:
    SCRIPTS["test_" + _name] = [
        (BUILD, False),
        (SET, surface.API_KEY, INVENTED_KEY),
        (SET, surface.API_SECRET, INVENTED_SECRET),
        (TEST, _name),
        (RESULTS,),
    ]

SCRIPTS["empty_script"] = []
SCRIPTS["untouched"] = [(BUILD, False), (RESULTS,)]
SCRIPTS["untouched_upgrade"] = [(BUILD, True), (RESULTS,)]
SCRIPTS["skip_setup"] = [(BUILD, False), (SKIP,), (RESULTS,)]
SCRIPTS["skip_setup_upgrade"] = [(BUILD, True), (SKIP,), (RESULTS,)]
SCRIPTS["page_walk"] = [
    (BUILD, False),
    (PAGE, 0),
    (PAGE, 1),
    (PAGE, 2),
    (PAGE, -1),
    (VALIDATE,),
]
SCRIPTS["passphrase_venue_then_page"] = [(BUILD, False), (PICK, 11), (PAGE, 2)]
SCRIPTS["plain_venue_then_page"] = [(BUILD, False), (PICK, 0), (PAGE, 2)]
SCRIPTS["no_venue_then_test"] = [
    (BUILD, False),
    (PICK, -1),
    (SET, surface.API_KEY, INVENTED_KEY),
    (SET, surface.API_SECRET, INVENTED_SECRET),
    (TEST, "ok"),
]
SCRIPTS["test_with_no_credentials"] = [(BUILD, False), (TEST, "ok"), (RESULTS,)]
SCRIPTS["test_with_blank_credentials"] = [
    (BUILD, False),
    (SET, surface.API_KEY, "   "),
    (SET, surface.API_SECRET, "   "),
    (TEST, "ok"),
]
SCRIPTS["test_then_page_clears_the_status"] = [
    (BUILD, False),
    (SET, surface.API_KEY, INVENTED_KEY),
    (SET, surface.API_SECRET, INVENTED_SECRET),
    (TEST, "refused"),
    (PAGE, 2),
]
SCRIPTS["show_key_on_then_off"] = [
    (BUILD, False),
    (CHECK, surface.SHOW_KEY, True),
    (CHECK, surface.SHOW_KEY, False),
    (CHECK, surface.SHOW_KEY, False),
    (CHECK, surface.SHOW_KEY, True),
]
SCRIPTS["validate_on_the_other_pages"] = [
    (BUILD, False),
    (SET, surface.USERNAME, ""),
    (PAGE, 1),
    (VALIDATE,),
    (PAGE, 2),
    (VALIDATE,),
    (PAGE, 0),
    (VALIDATE,),
]
SCRIPTS["everything_in_turn"] = [
    (BUILD, True),
    (SET, surface.USERNAME, "Ann"),
    (CHECK, surface.FRESH_START, True),
    (PICK, 11),
    (SET, surface.API_KEY, INVENTED_KEY),
    (SET, surface.API_SECRET, INVENTED_SECRET),
    (SET, surface.PASSPHRASE, INVENTED_PASSPHRASE),
    (CHECK, surface.SHOW_KEY, True),
    (PAGE, 2),
    (TEST, "ok"),
    (VALIDATE,),
    (RESULTS,),
    (SKIP,),
    (RESULTS,),
]

OLD_SETTERS = {
    surface.USERNAME: lambda w, v: w._username.setText(v),
    surface.API_KEY: lambda w, v: w._api_key.setText(v),
    surface.API_SECRET: lambda w, v: w._api_secret.setPlainText(v),
    surface.PASSPHRASE: lambda w, v: w._passphrase.setText(v),
}
NEW_SETTERS = {
    surface.USERNAME: surface.InitWizardModel.set_username,
    surface.API_KEY: surface.InitWizardModel.set_api_key,
    surface.API_SECRET: surface.InitWizardModel.set_api_secret,
    surface.PASSPHRASE: surface.InitWizardModel.set_passphrase,
}
OLD_CHECKS = {
    surface.SHOW_KEY: lambda w, v: w._show_key.setChecked(v),
    surface.SKIP_CREDS: lambda w, v: w._skip_creds.setChecked(v),
    surface.FRESH_START: lambda w, v: w._fresh_start.setChecked(v),
}
NEW_CHECKS = {
    surface.SHOW_KEY: surface.InitWizardModel.set_show_key,
    surface.SKIP_CREDS: surface.InitWizardModel.set_skip_creds,
    surface.FRESH_START: surface.InitWizardModel.set_fresh_start,
}


def read_widgets(wizard, buttons):
    """Every visible string, switch, colour and answer the wizard carries."""
    return {
        "username_text": wizard._username.text(),
        "api_key_text": wizard._api_key.text(),
        "api_secret_text": wizard._api_secret.toPlainText(),
        "passphrase_text": wizard._passphrase.text(),
        "api_key_echo": wizard._api_key.echoMode().value,
        "passphrase_echo": wizard._passphrase.echoMode().value,
        "api_secret_style": wizard._api_secret.styleSheet(),
        "show_key_checked": wizard._show_key.isChecked(),
        "skip_creds_checked": wizard._skip_creds.isChecked(),
        "fresh_start_checked": (
            wizard._fresh_start.isChecked() if wizard._fresh_start else None
        ),
        "exchange_index": wizard._exchange_combo.currentIndex(),
        "exchange_id": wizard._exchange_combo.currentData(),
        "exchange_label_text": wizard._exchange_combo.currentText(),
        "passphrase_label_visible": not wizard._passphrase_label.isHidden(),
        "passphrase_visible": not wizard._passphrase.isHidden(),
        "passphrase_hint_visible": not wizard._passphrase_hint.isHidden(),
        "feedback_text": wizard._feedback.text(),
        "feedback_style": wizard._feedback.styleSheet(),
        "test_button_enabled": wizard._test_btn.isEnabled(),
        "skip_button_style": buttons[0].styleSheet(),
        "skipped": wizard.was_skipped(),
        "warning": list(WARNINGS[-1]) if WARNINGS else None,
    }


def read_model(model):
    """Every visible string, switch, colour and answer the model carries."""
    return {
        "username_text": model.username_text,
        "api_key_text": model.api_key_text,
        "api_secret_text": model.api_secret_text,
        "passphrase_text": model.passphrase_text,
        "api_key_echo": surface.ECHO_VALUES[model.api_key_echo],
        "passphrase_echo": surface.ECHO_VALUES[model.passphrase_echo],
        "api_secret_style": model.api_secret_style,
        "show_key_checked": model.show_key_checked,
        "skip_creds_checked": model.skip_creds_checked,
        "fresh_start_checked": model.fresh_start_checked,
        "exchange_index": model.exchange_index,
        "exchange_id": model.exchange_id,
        "exchange_label_text": model.exchange_label_text,
        "passphrase_label_visible": model.passphrase_label_visible,
        "passphrase_visible": model.passphrase_visible,
        "passphrase_hint_visible": model.passphrase_hint_visible,
        "feedback_text": model.feedback_text,
        "feedback_style": model.feedback_style,
        "test_button_enabled": model.test_button_enabled,
        "skip_button_style": surface.SKIP_BUTTON_STYLE,
        "skipped": model.was_skipped(),
        "warning": model.warning,
    }


def snapshot(error, view, answer=None):
    """One step's whole state: the error, the answer, the values, the calls."""
    body = {
        "error": error,
        "answer": answer,
        "calls": [list(call) for call in CALLS],
    }
    body.update(view)
    return body


def run_old(script, monkeypatch):
    """Drive ``InitWizard`` through the script, step by step."""
    app()
    CALLS.clear()
    WARNINGS.clear()
    PAGE_CELL[0] = surface.NO_PAGE_ID
    CHECK_ORDER[0] = surface.CHECK_TAGS
    labels, lines, checks, buttons, boxes, combos = trace_widgets(monkeypatch)
    patch = trace_wizard_methods()
    try:
        wizard = None
        trace = [snapshot(None, {})]
        for step in script:
            error = None
            answer = None
            try:
                if step[0] == BUILD:
                    for holder in (labels, lines, checks, buttons, boxes, combos):
                        holder.clear()
                    WARNINGS.clear()
                    PAGE_CELL[0] = surface.NO_PAGE_ID
                    CHECK_ORDER[0] = (
                        surface.UPGRADE_CHECK_TAGS if step[1] else surface.CHECK_TAGS
                    )
                    wizard = shipped.InitWizard(step[1])
                    ALIVE.append(wizard)
                elif step[0] == SET:
                    OLD_SETTERS[step[1]](wizard, step[2])
                elif step[0] == CHECK:
                    OLD_CHECKS[step[1]](wizard, step[2])
                elif step[0] == PICK:
                    wizard._exchange_combo.setCurrentIndex(step[1])
                elif step[0] == PAGE:
                    PAGE_CELL[0] = step[1]
                    wizard._on_page_changed(step[1])
                elif step[0] == TEST:
                    stub_validator(monkeypatch, step[1])
                    wizard._test_api()
                elif step[0] == SKIP:
                    wizard._on_skip()
                elif step[0] == VALIDATE:
                    answer = wizard.validateCurrentPage()
                else:
                    answer = wizard.get_results()
            except Exception as exc:
                error = type(exc).__name__
            view = read_widgets(wizard, buttons) if wizard is not None else {}
            trace.append(snapshot(error, view, answer))
        return trace
    finally:
        patch.undo()


def run_new(script):
    """Drive the view model through the same script, step by step."""
    CALLS.clear()
    model = None
    trace = [snapshot(None, {})]
    for step in script:
        error = None
        answer = None
        try:
            if step[0] == BUILD:
                model = surface.InitWizardModel(step[1])
            elif step[0] == SET:
                NEW_SETTERS[step[1]](model, step[2])
            elif step[0] == CHECK:
                NEW_CHECKS[step[1]](model, step[2])
            elif step[0] == PICK:
                model.set_exchange_index(step[1])
            elif step[0] == PAGE:
                model.on_page_changed(step[1])
            elif step[0] == TEST:
                model.test_api(surface_validator(step[1]))
            elif step[0] == SKIP:
                model.on_skip()
            elif step[0] == VALIDATE:
                answer = model.validate_current_page()
            else:
                answer = model.get_results()
        except Exception as exc:
            error = type(exc).__name__
        CALLS.clear()
        if model is not None:
            CALLS.extend(model.calls)
        view = read_model(model) if model is not None else {}
        trace.append(snapshot(error, view, answer))
    return trace


# ---------------------------------------------------------------------
# The two sides, driven together
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_old_and_new_traces_are_identical(name, monkeypatch):
    """A step of the script leaves the two sides in a different state."""
    old = run_old(SCRIPTS[name], monkeypatch)
    new = run_new(SCRIPTS[name])
    assert new == old, name
    assert digest(new) == digest(old), name


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_the_trace_holds_the_whole_wizard(name, monkeypatch):
    """The comparison passed by measuring nothing."""
    old = run_old(SCRIPTS[name], monkeypatch)
    assert len(old) == len(SCRIPTS[name]) + 1
    assert old[0] == {"error": None, "answer": None, "calls": []}
    for step in old[1:]:
        assert step["calls"] != []
        assert isinstance(step["username_text"], str)
        assert isinstance(step["feedback_style"], str)
        assert step["api_key_echo"] in (0, 2)


def test_the_digest_tells_two_different_traces_apart():
    """The trace digest returns one value whatever the trace holds."""
    one = run_new(SCRIPTS["untouched"])
    other = run_new(SCRIPTS["untouched_upgrade"])
    assert one != other
    assert digest(one) != digest(other)
    assert digest(one) == digest(run_new(SCRIPTS["untouched"]))


def test_the_scripts_reach_every_path_and_both_kinds_of_outcome(monkeypatch):
    """A state was never driven, so its parity was never compared."""
    errors = set()
    answered = 0
    refused = 0
    feedback_styles = set()
    venues = set()
    names = set()
    switches = set()
    for name in SCRIPTS:
        for step in run_old(SCRIPTS[name], monkeypatch):
            if step["error"]:
                errors.add(step["error"])
                refused += 1
            else:
                answered += 1
            for call in step["calls"]:
                if call[0] == surface.LABEL_SET_STYLE_SHEET:
                    feedback_styles.add(call[2])
            if "feedback_style" in step:
                feedback_styles.add(step["feedback_style"])
                venues.add(step["exchange_id"])
                names.add(step["username_text"])
                switches.add(step["show_key_checked"])
    assert errors == {"TypeError", "OverflowError", "AttributeError"}
    assert answered > 0 and refused > 0
    assert feedback_styles == {
        "",
        surface.feedback_style(surface.FEEDBACK_ERROR_COLOR),
        surface.feedback_style(surface.FEEDBACK_INFO_COLOR),
        surface.feedback_style(surface.FEEDBACK_SUCCESS_COLOR),
    }
    assert None in venues
    assert "binance" in venues and "kucoin" in venues and "poloniex" in venues
    assert "" in names
    assert "x" * 200 in names
    assert "O'Brien" in names
    assert "Ann\nBrown" in names
    assert any("⚡" in found for found in names)
    assert any("<b>bold</b>" in found for found in names)
    assert switches == {True, False}


def test_every_test_path_is_driven_on_both_sides(monkeypatch):
    """A credential-test path was never compared."""
    reached = set()
    for outcome, wanted in (
        (None, surface.TEST_PATH_MISSING),
        ("ok", surface.TEST_PATH_SUCCESS),
        ("refused", surface.TEST_PATH_REFUSED),
        ("raised", surface.TEST_PATH_RAISED),
    ):
        model = surface.InitWizardModel()
        if outcome is not None:
            model.set_api_key(INVENTED_KEY)
            model.set_api_secret(INVENTED_SECRET)
        model.test_api(surface_validator(outcome or "ok"))
        assert model.test_path == wanted, outcome
        reached.add(model.test_path)
    without_venue = surface.InitWizardModel()
    without_venue.set_exchange_index(surface.NO_EXCHANGE_INDEX)
    without_venue.set_api_key(INVENTED_KEY)
    without_venue.set_api_secret(INVENTED_SECRET)
    with pytest.raises(AttributeError):
        without_venue.test_api(surface_validator("ok"))
    reached.add(without_venue.test_path)
    assert reached == set(surface.TEST_PATHS)
    assert len(reached) == 5
    old = run_old(SCRIPTS["no_venue_then_test"], monkeypatch)
    assert old[-1]["error"] == "AttributeError"
    assert run_new(SCRIPTS["no_venue_then_test"]) == old


def test_a_refused_input_names_its_own_type_on_both_sides(monkeypatch):
    """A refusal on one side carried no reason a reader can act on."""
    old = run_old(SCRIPTS["name_number"], monkeypatch)
    assert old[2]["error"] == "TypeError"
    with pytest.raises(TypeError) as reported:
        surface.text_value(42)
    assert "int" in str(reported.value)
    with pytest.raises(TypeError) as index_error:
        surface.index_value("kucoin")
    assert "str" in str(index_error.value)
    with pytest.raises(TypeError) as check_error:
        surface.checked_value("yes")
    assert "str" in str(check_error.value)
    with pytest.raises(OverflowError) as overflow:
        surface.index_value(float("inf"))
    assert str(overflow.value) == surface.INDEX_OVERFLOW
    assert surface.text_value(None) == ""
    assert surface.checked_value(1) is True
    assert surface.index_value(1.5) == 1


# ---------------------------------------------------------------------
# The wizard enumerated
# ---------------------------------------------------------------------


def test_the_connect_sites_match_the_actions():
    """A signal wiring appeared on one side and not the other."""
    from PySide6.QtWidgets import QCheckBox, QPushButton

    app()
    wizard = shipped.InitWizard()
    ALIVE.append(wizard)
    buttons = {button.text(): button for button in wizard.findChildren(QPushButton)}
    skip = buttons["Skip Setup"]
    live = (
        skip.receivers(CLICKED_SIGNAL)
        + wizard._test_btn.receivers(CLICKED_SIGNAL)
        + wizard._show_key.receivers(TOGGLED_SIGNAL)
        + wizard.receivers(CURRENT_ID_SIGNAL)
    )
    assert skip.receivers(CLICKED_SIGNAL) == 1
    assert wizard._test_btn.receivers(CLICKED_SIGNAL) == 1
    assert wizard._show_key.receivers(TOGGLED_SIGNAL) == 1
    assert wizard.receivers(CURRENT_ID_SIGNAL) == 1
    assert live == 4
    assert QPushButton("bare").receivers(CLICKED_SIGNAL) == 0
    assert QCheckBox("bare").receivers(TOGGLED_SIGNAL) == 0

    wizard_text = WIZARD_PATH.read_text(encoding="utf-8")
    assert wizard_text.count(".connect(") == live == 4
    assert SURFACE_PATH.read_text(encoding="utf-8").count(".connect(") == 0
    assert len(surface.ACTIONS) == live
    assert set(surface.ACTIONS) == {
        "skip_button.clicked",
        "show_key.toggled",
        "test_button.clicked",
        "wizard.currentIdChanged",
    }
    for target in surface.ACTIONS.values():
        assert callable(getattr(surface.InitWizardModel, target)), target


METHOD_MAP = {
    "InitWizard.__init__": "InitWizardModel.__init__",
    "InitWizard._on_skip": "InitWizardModel.on_skip",
    "InitWizard.was_skipped": "InitWizardModel.was_skipped",
    "InitWizard._toggle_visibility": "InitWizardModel.toggle_visibility",
    "InitWizard._on_page_changed": "InitWizardModel.on_page_changed",
    "InitWizard._test_api": "InitWizardModel.test_api",
    "InitWizard.validateCurrentPage": "InitWizardModel.validate_current_page",
    "InitWizard.get_results": "InitWizardModel.get_results",
}

MODEL_MEMBERS = {
    "__init__",
    "_build_welcome_page",
    "_build_exchange_page",
    "_build_credentials_page",
    "set_username",
    "set_api_key",
    "set_api_secret",
    "set_passphrase",
    "set_show_key",
    "set_skip_creds",
    "set_fresh_start",
    "set_exchange_index",
    "on_skip",
    "was_skipped",
    "toggle_visibility",
    "on_page_changed",
    "_write_feedback",
    "_enable_test_button",
    "test_api",
    "validate_current_page",
    "get_results",
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
    """Every method the wizard module defines, as dotted names."""
    import inspect

    names = {
        name
        for name, value in vars(shipped).items()
        if inspect.isfunction(value) and value.__module__ == shipped.__name__
    }
    for member in members(shipped.InitWizard):
        names.add("InitWizard." + member)
    return names


def test_every_wizard_member_has_a_counterpart():
    """A method exists on one side and nowhere on the other."""
    assert qt_member_names() == set(METHOD_MAP)
    assert len(METHOD_MAP) == 8
    for target in METHOD_MAP.values():
        assert resolve(target) is not None, target
    assert members(surface.InitWizardModel) == MODEL_MEMBERS
    assert len(MODEL_MEMBERS) == 21
    assert {name.split(".")[-1] for name in METHOD_MAP.values()} < MODEL_MEMBERS


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    assert "InitWizard._test_api" in qt_member_names()
    assert "InitWizard.get_results" in qt_member_names()
    assert "InitWizard.setStyleSheet" not in qt_member_names()
    assert "logger" not in qt_member_names()
    assert "InitWizardModel.on_skip" not in qt_member_names()
    with pytest.raises(AttributeError):
        resolve("InitWizardModel.no_such_member")
    assert MODEL_MEMBERS - {"test_api"} != MODEL_MEMBERS
    assert members(surface.InitWizardModel) - {"on_skip"} != MODEL_MEMBERS
    assert members(shipped.InitWizard) == {
        "__init__",
        "_on_skip",
        "was_skipped",
        "_toggle_visibility",
        "_on_page_changed",
        "_test_api",
        "validateCurrentPage",
        "get_results",
    }


def test_one_class_on_each_side():
    """A class appeared on one side and not the other."""
    import inspect

    shipped_classes = {
        name
        for name, value in vars(shipped).items()
        if inspect.isclass(value) and value.__module__ == shipped.__name__
    }
    surface_classes = {
        name
        for name, value in vars(surface).items()
        if inspect.isclass(value) and value.__module__ == surface.__name__
    }
    assert shipped_classes == {"InitWizard"}
    assert surface_classes == {"InitWizardModel", "TestAnswer"}
    assert len(shipped_classes) == 1
    assert "InitWizardModel" in surface_classes


CALL_NAMES = {
    "WIZARD_SET_WINDOW_TITLE": "wizard.setWindowTitle",
    "WIZARD_SET_MINIMUM_SIZE": "wizard.setMinimumSize",
    "WIZARD_SET_WIZARD_STYLE": "wizard.setWizardStyle",
    "WIZARD_ADD_PAGE": "wizard.addPage",
    "WIZARD_REJECT": "wizard.reject",
    "PAGE_CREATE": "page.create",
    "PAGE_SET_TITLE": "page.setTitle",
    "PAGE_SET_SUB_TITLE": "page.setSubTitle",
    "PAGE_SET_FINAL": "page.setFinalPage",
    "LAYOUT_CREATE": "layout.create",
    "LAYOUT_ADD_WIDGET": "layout.addWidget",
    "LAYOUT_ADD_SPACING": "layout.addSpacing",
    "LABEL_CREATE": "label.create",
    "LABEL_SET_WORD_WRAP": "label.setWordWrap",
    "LABEL_SET_PROPERTY": "label.setProperty",
    "LABEL_SET_TEXT": "label.setText",
    "LABEL_SET_STYLE_SHEET": "label.setStyleSheet",
    "LABEL_SET_VISIBLE": "label.setVisible",
    "LINE_CREATE": "line.create",
    "LINE_SET_PLACEHOLDER": "line.setPlaceholderText",
    "LINE_SET_TEXT": "line.setText",
    "LINE_SET_ECHO_MODE": "line.setEchoMode",
    "LINE_SET_VISIBLE": "line.setVisible",
    "COMBO_CREATE": "combo.create",
    "COMBO_ADD_ITEM": "combo.addItem",
    "COMBO_SET_CURRENT_INDEX": "combo.setCurrentIndex",
    "CHECK_CREATE": "check.create",
    "CHECK_SET_TOOL_TIP": "check.setToolTip",
    "CHECK_SET_CHECKED": "check.setChecked",
    "TEXT_CREATE": "text.create",
    "TEXT_SET_MAXIMUM_HEIGHT": "text.setMaximumHeight",
    "TEXT_SET_PLACEHOLDER": "text.setPlaceholderText",
    "TEXT_SET_TOOL_TIP": "text.setToolTip",
    "TEXT_SET_PLAIN_TEXT": "text.setPlainText",
    "TEXT_SET_STYLE_SHEET": "text.setStyleSheet",
    "BUTTON_CREATE": "button.create",
    "BUTTON_SET_TOOL_TIP": "button.setToolTip",
    "BUTTON_SET_STYLE_SHEET": "button.setStyleSheet",
    "BUTTON_SET_ENABLED": "button.setEnabled",
    "SAFE_PROCESS_EVENTS": "wizard.safeProcessEvents",
    "VALIDATE_CALL": "wizard.validateCredentials",
    "MESSAGE_BOX_WARNING": "messageBox.warning",
}


def test_the_call_names_are_the_ones_the_trace_writes():
    """The trace and the surface stopped agreeing on what to call a call."""
    for constant, literal in CALL_NAMES.items():
        assert getattr(surface, constant) == literal, constant
    assert len(set(CALL_NAMES.values())) == 42


def test_the_wizard_starts_no_timer_and_the_counter_reports_one_elsewhere():
    """A wait appeared on one side and not the other.

    The wizard waits on the operator, not on a clock. The same counter is
    pointed at ``history_tab``, which does start one, so a zero here is a
    fact about the wizard rather than a broken counter.
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
        wizard = shipped.InitWizard()
        ALIVE.append(wizard)
        wizard._on_page_changed(2)
        wizard._show_key.setChecked(True)
        wizard._on_skip()
        observed = list(started)
        started.clear()
        QTimer().start(400)
    finally:
        QObject.startTimer = original_start_timer
        QTimer.start = original_timer_start
        QTimer.singleShot = original_single_shot
    assert started == [("QTimer.start", (400,))]
    assert observed == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert WIZARD_PATH.read_text(encoding="utf-8").count("QTimer") == 0
    assert HISTORY_PATH.read_text(encoding="utf-8").count("QTimer") > 0


def test_the_wizard_reaches_no_bus_topic_and_the_counter_reports_one_elsewhere():
    """A bus subscription appeared on one side and not the other.

    The same counter is pointed at ``bot_visualizer``, which does
    subscribe, so a zero here is a fact about the wizard.
    """
    wizard_text = WIZARD_PATH.read_text(encoding="utf-8")
    visualizer_text = VISUALIZER_PATH.read_text(encoding="utf-8")
    assert wizard_text.count(".subscribe(") == 0
    assert wizard_text.count("event_bus") == 0
    assert visualizer_text.count(".subscribe(") == 2
    assert "wire.created" in visualizer_text
    assert surface.BUS_TOPICS == ()
    assert len(surface.BUS_TOPICS) == wizard_text.count(".subscribe(") == 0


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
    assert imported == {"math", "typing", "__future__"}
    wizard_imports = {
        (node.module or "")
        for node in ast.walk(ast.parse(WIZARD_PATH.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in wizard_imports)


# ---------------------------------------------------------------------
# The surface holds its own values
# ---------------------------------------------------------------------


def test_the_surface_does_not_follow_a_changed_colour_in_the_shipped_file(
    monkeypatch,
):
    """The surface reads its colours from the shipped file after all."""
    from src.gui import design_system

    app()
    before = run_old([(BUILD, False)], monkeypatch)[1]["skip_button_style"]
    assert before == surface.SKIP_BUTTON_STYLE == "color: #888; padding: 8px;"
    monkeypatch.setattr(design_system, "CARD_METRIC_LABEL", "#123456")
    after = run_old([(BUILD, False)], monkeypatch)[1]["skip_button_style"]
    assert after == "color: #123456; padding: 8px;"
    assert after != before
    assert surface.SKIP_BUTTON_STYLE == before
    assert surface.SKIP_BUTTON_COLOR == "#888"
    assert surface.SKIN["skip_button"] == "#888"


def test_the_surface_does_not_follow_a_changed_venue_list_in_the_shipped_file(
    monkeypatch,
):
    """The surface reads its venue list from the connector after all."""
    from src.exchange import ccxt_connector

    app()
    before = run_old([(BUILD, False), (PICK, 0)], monkeypatch)[2]
    assert before["exchange_id"] == "binance"
    assert before["exchange_label_text"] == "Binance"
    monkeypatch.setattr(
        ccxt_connector, "SUPPORTED_EXCHANGES", {"acmevenue": "acmevenue"}
    )
    monkeypatch.setattr(ccxt_connector, "PASSPHRASE_EXCHANGES", {"acmevenue"})
    after = run_old([(BUILD, False), (PICK, 0)], monkeypatch)[2]
    assert after["exchange_id"] == "acmevenue"
    assert after["exchange_label_text"] == "Acmevenue (requires passphrase)"
    assert list(surface.EXCHANGE_IDS)[0] == "binance"
    assert len(surface.EXCHANGE_IDS) == 15
    assert surface.EXCHANGE_LABELS[0] == "Binance"
    assert "acmevenue" not in surface.EXCHANGE_IDS


def test_the_surface_does_not_follow_a_changed_status_colour(monkeypatch):
    """The surface reads its status colours from the shipped file after all."""
    from src.gui import design_system

    app()
    script = [
        (BUILD, False),
        (SET, surface.API_KEY, INVENTED_KEY),
        (SET, surface.API_SECRET, INVENTED_SECRET),
        (TEST, "ok"),
    ]
    before = run_old(script, monkeypatch)[-1]["feedback_style"]
    assert before == "color: #00ff88;"
    monkeypatch.setattr(design_system, "SUCCESS", "#abcdef")
    after = run_old(script, monkeypatch)[-1]["feedback_style"]
    assert after == "color: #abcdef;"
    assert run_new(script)[-1]["feedback_style"] == before
    assert surface.FEEDBACK_SUCCESS_COLOR == "#00ff88"


def test_the_shipped_venue_list_matches_the_surfaces_own():
    """The two sides list different venues on the same connector."""
    from src.exchange.ccxt_connector import PASSPHRASE_EXCHANGES, SUPPORTED_EXCHANGES

    assert list(surface.EXCHANGE_IDS) == sorted(SUPPORTED_EXCHANGES)
    assert list(surface.PASSPHRASE_EXCHANGE_IDS) == sorted(PASSPHRASE_EXCHANGES)
    assert surface.EXCHANGE_LABELS == tuple(
        found.capitalize()
        + (" (requires passphrase)" if found in PASSPHRASE_EXCHANGES else "")
        for found in sorted(SUPPORTED_EXCHANGES)
    )


def test_the_shipped_colours_match_the_surfaces_own():
    """The two sides paint the status line in different colours."""
    from src.gui import design_system

    assert surface.SKIP_BUTTON_COLOR == design_system.CARD_METRIC_LABEL
    assert surface.FEEDBACK_ERROR_COLOR == design_system.ERROR
    assert surface.FEEDBACK_INFO_COLOR == design_system.STATUS_INFO
    assert surface.FEEDBACK_SUCCESS_COLOR == design_system.SUCCESS
    assert len(surface.SKIN) == 4


def test_the_safe_events_reason_is_the_wizards_own(monkeypatch):
    """The status pause carries a different reason on the two sides."""
    script = [
        (BUILD, False),
        (SET, surface.API_KEY, INVENTED_KEY),
        (SET, surface.API_SECRET, INVENTED_SECRET),
        (TEST, "ok"),
    ]
    old = run_old(script, monkeypatch)[-1]["calls"]
    paused = [call for call in old if call[0] == surface.SAFE_PROCESS_EVENTS]
    assert paused == [[surface.SAFE_PROCESS_EVENTS, "legacy P4.1 site"]]
    assert surface.SAFE_EVENTS_REASON == "legacy P4.1 site"
    new = run_new(script)[-1]["calls"]
    assert [call for call in new if call[0] == surface.SAFE_PROCESS_EVENTS] == paused


# ---------------------------------------------------------------------
# The completeness of the comparison
# ---------------------------------------------------------------------

CONSTANT_LOCATION = {
    "METHOD": ("method", None),
    "LOGGER_NAME": ("logger_name", None),
    "WINDOW_TITLE": ("window_title", None),
    "MINIMUM_SIZE_PX": ("minimum_size_px", None),
    "WIZARD_STYLE": ("wizard_style", None),
    "WIZARD_STYLE_VALUE": ("wizard_style_value", None),
    "WELCOME": ("pages", 0),
    "EXCHANGE": ("pages", 1),
    "CREDENTIALS": ("pages", 2),
    "PAGES": ("pages", None),
    "PAGE_IDS": ("page_ids", None),
    "FINAL_PAGE": ("final_page", None),
    "NO_PAGE_ID": ("no_page_id", None),
    "VALIDATED_PAGE_ID": ("validated_page_id", None),
    "PASSPHRASE_PAGE_ID": ("passphrase_page_id", None),
    "FRESH_TITLE": ("page_titles", "welcome"),
    "FRESH_SUBTITLE": ("page_subtitles", "welcome"),
    "EXCHANGE_TITLE": ("page_titles", "exchange"),
    "EXCHANGE_SUBTITLE": ("page_subtitles", "exchange"),
    "CREDENTIALS_TITLE": ("page_titles", "credentials"),
    "CREDENTIALS_SUBTITLE": ("page_subtitles", "credentials"),
    "WIDGET_NAMES": ("widget_names", None),
    "USERNAME_LABEL": ("widget_names", 0),
    "USERNAME": ("widget_names", 1),
    "FRESH_START": ("widget_names", 2),
    "WELCOME_SPACING": ("widget_names", 3),
    "SKIP_BUTTON": ("widget_names", 4),
    "EXCHANGE_LABEL": ("widget_names", 5),
    "EXCHANGE_COMBO": ("widget_names", 6),
    "API_KEY_LABEL": ("widget_names", 7),
    "API_KEY": ("widget_names", 8),
    "SHOW_KEY": ("widget_names", 9),
    "API_SECRET_LABEL": ("widget_names", 10),
    "API_SECRET": ("widget_names", 11),
    "PASSPHRASE_LABEL": ("widget_names", 12),
    "PASSPHRASE": ("widget_names", 13),
    "PASSPHRASE_HINT": ("widget_names", 14),
    "SKIP_CREDS": ("widget_names", 15),
    "TEST_BUTTON": ("widget_names", 16),
    "FEEDBACK": ("widget_names", 17),
    "EMPTY_TEXT": ("empty_text", None),
    "LABEL_TEXTS": ("label_texts", None),
    "PLACEHOLDERS": ("placeholders", None),
    "TOOL_TIPS": ("tool_tips", None),
    "CHECK_TEXTS": ("check_texts", None),
    "BUTTON_TEXTS": ("button_texts", None),
    "USERNAME_DEFAULT": ("username_default", None),
    "WELCOME_SPACING_PX": ("welcome_spacing_px", None),
    "API_SECRET_MAX_HEIGHT_PX": ("api_secret_max_height_px", None),
    "SKIP_BUTTON_COLOR": ("skip_button_color", None),
    "FEEDBACK_ERROR_COLOR": ("feedback_error_color", None),
    "FEEDBACK_INFO_COLOR": ("feedback_info_color", None),
    "FEEDBACK_SUCCESS_COLOR": ("feedback_success_color", None),
    "SKIN": ("skin", None),
    "SKIP_BUTTON_STYLE_FORMAT": ("skip_button_style_format", None),
    "FEEDBACK_STYLE_FORMAT": ("feedback_style_format", None),
    "NO_STYLE": ("no_style", None),
    "STYLES": ("styles", None),
    "SKIP_BUTTON_STYLE": ("skip_button_style", None),
    "SECRET_HIDDEN_STYLE": ("secret_hidden_style", None),
    "SECRET_SHOWN_STYLE": ("secret_shown_style", None),
    "ECHO_MODES": ("echo_modes", None),
    "ECHO_NORMAL": ("echo_modes", 0),
    "ECHO_PASSWORD": ("echo_modes", 1),
    "ECHO_VALUES": ("echo_values", None),
    "PASSPHRASE_HINT_WORD_WRAP": ("passphrase_hint_word_wrap", None),
    "FEEDBACK_WORD_WRAP": ("feedback_word_wrap", None),
    "MUTED_PROPERTY": ("muted_property", 0),
    "MUTED_VALUE": ("muted_value", None),
    "EXCHANGE_IDS": ("exchange_ids", None),
    "PASSPHRASE_EXCHANGE_IDS": ("passphrase_exchange_ids", None),
    "EXCHANGE_NOTES": ("exchange_notes", None),
    "PASSPHRASE_SUFFIX": ("passphrase_suffix", None),
    "DEFAULT_EXCHANGE_INDEX": ("default_exchange_index", None),
    "NO_EXCHANGE_INDEX": ("no_exchange_index", None),
    "NO_EXCHANGE_ID": ("no_exchange_id", None),
    "NO_EXCHANGE_LABEL": ("no_exchange_label", None),
    "EXCHANGE_LABELS": ("exchange_labels", None),
    "EXCHANGE_ITEMS": ("exchange_items", None),
    "MISSING_CREDENTIALS_TEXT": ("missing_credentials_text", None),
    "TESTING_FORMAT": ("testing_format", None),
    "TEST_FAILED_FORMAT": ("test_failed_format", None),
    "USERNAME_REQUIRED_TITLE": ("username_required", 0),
    "USERNAME_REQUIRED_TEXT": ("username_required", 1),
    "NO_WARNING": ("no_warning", None),
    "SAFE_EVENTS_REASON": ("safe_events_reason", None),
    "SKIPPED_DEFAULT": ("skipped_default", None),
    "FRESH_START_ABSENT": ("fresh_start_absent", None),
    "FRESH_START_DEFAULT": ("fresh_start_default", None),
    "SHOW_KEY_DEFAULT": ("show_key_default", None),
    "SKIP_CREDS_DEFAULT": ("skip_creds_default", None),
    "TEST_BUTTON_ENABLED": ("test_button_enabled_default", None),
    "PASSPHRASE_VISIBLE_DEFAULT": ("passphrase_visible_default", None),
    "INT32_MIN": ("int32_min", None),
    "INT32_MAX": ("int32_max", None),
    "WRONG_TEXT_TYPE": ("wrong_text_type", None),
    "WRONG_CHECK_TYPE": ("wrong_check_type", None),
    "WRONG_INDEX_TYPE": ("wrong_index_type", None),
    "INDEX_OVERFLOW": ("index_overflow", None),
    "ACTIONS": ("actions", None),
    "TIMERS": ("timers", None),
    "TIMER_DELAYS_MS": ("timer_delays_ms", None),
    "BUS_TOPICS": ("bus_topics", None),
    "LABEL_TAGS": ("label_tags", None),
    "LINE_TAGS": ("line_tags", None),
    "CHECK_TAGS": ("check_tags", None),
    "BUTTON_TAGS": ("button_tags", None),
    "TEXT_TAGS": ("text_tags", None),
    "COMBO_TAGS": ("combo_tags", None),
    "PAGE_ORDERS": ("page_orders", None),
    "WELCOME_ORDER": ("page_orders", "welcome"),
    "EXCHANGE_ORDER": ("page_orders", "exchange"),
    "CREDENTIALS_ORDER": ("page_orders", "credentials"),
    "PAGE_TITLES": ("page_titles", None),
    "PAGE_SUBTITLES": ("page_subtitles", None),
    "RESULT_FIELDS": ("result_fields", None),
    "TEST_PATHS": ("test_paths", None),
    "TEST_PATH_MISSING": ("test_paths", 0),
    "TEST_PATH_NO_EXCHANGE": ("test_paths", 1),
    "TEST_PATH_SUCCESS": ("test_paths", 2),
    "TEST_PATH_REFUSED": ("test_paths", 3),
    "TEST_PATH_RAISED": ("test_paths", 4),
    "NO_TEST_PATH": ("no_test_path", None),
}

# The constants no snapshot key carries, each with the check that
# covers it.
NOT_IN_THE_SNAPSHOT = {
    **{
        name: "test_the_call_names_are_the_ones_the_trace_writes" for name in CALL_NAMES
    },
    "UPGRADE_TITLE": "test_the_upgrade_wording_is_the_wizards_own",
    "UPGRADE_SUBTITLE": "test_the_upgrade_wording_is_the_wizards_own",
    "UPGRADE_PAGE_TITLES": "test_the_upgrade_wording_is_the_wizards_own",
    "UPGRADE_PAGE_SUBTITLES": "test_the_upgrade_wording_is_the_wizards_own",
    "UPGRADE_PAGE_ORDERS": "test_the_upgrade_wording_is_the_wizards_own",
    "UPGRADE_WELCOME_ORDER": "test_the_upgrade_wording_is_the_wizards_own",
    "UPGRADE_CHECK_TAGS": "test_the_upgrade_wording_is_the_wizards_own",
    "STEP_NAMES": "test_the_bridge_reads_every_step_name",
}

CONSTANT_TOTAL = 173


def surface_constants():
    """Every value the surface exports that is not a function or a class."""
    import types

    return {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("_")
        and not callable(value)
        and not isinstance(value, types.ModuleType)
        and name != "annotations"
    }


def carried(payload, key, inner):
    """The value one snapshot key holds, at its inner position if it has one."""
    found = payload[key]
    return found if inner is None else found[inner]


def as_lists(value):
    """`value` with every tuple turned into a list, at every depth.

    The snapshot is JSON, which has no tuple, so a tuple on the surface
    and a list in the snapshot are the same value.
    """
    if isinstance(value, (list, tuple)):
        return [as_lists(one) for one in value]
    if isinstance(value, dict):
        return {key: as_lists(one) for key, one in value.items()}
    return value


def test_every_constant_the_surface_holds_reaches_the_snapshot():
    """A constant the surface exports is in no snapshot the tests read."""
    payload = surface.build_view_model()
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    unaccounted = []
    for name, value in constants.items():
        if name in CONSTANT_LOCATION:
            key, inner = CONSTANT_LOCATION[name]
            assert carried(payload, key, inner) == as_lists(value), name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted
    assert len(CONSTANT_LOCATION) + len(NOT_IN_THE_SNAPSHOT) == CONSTANT_TOTAL


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    payload = surface.build_view_model()
    from_constants = {key for key, _ in CONSTANT_LOCATION.values()}
    built_per_call = {
        "is_upgrade",
        "skipped",
        "current_page_id",
        "username_text",
        "api_key_text",
        "api_secret_text",
        "passphrase_text",
        "api_key_echo",
        "passphrase_echo",
        "api_secret_style",
        "show_key_checked",
        "skip_creds_checked",
        "fresh_start_checked",
        "exchange_index",
        "exchange_id",
        "exchange_label_text",
        "passphrase_label_visible",
        "passphrase_visible",
        "passphrase_hint_visible",
        "feedback_text",
        "feedback_style",
        "test_button_enabled",
        "warning",
        "validated",
        "results",
        "buttons",
        "calls",
        "test_path",
    }
    assert set(payload) == from_constants | built_per_call
    assert len(payload) == 113
    for key in built_per_call:
        assert key in payload


def test_the_completeness_checks_can_report_a_made_up_name():
    """The completeness checks passed because they look at nothing."""
    payload = surface.build_view_model()
    invented = "INVENTED_CONSTANT"
    assert invented not in CONSTANT_LOCATION
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    assert "invented_snapshot_key" not in payload
    assert "WIDGET_NAMES" in surface_constants()
    assert "LABEL_TEXTS" in surface_constants()
    assert "InitWizardModel" not in surface_constants()
    assert "build_view_model" not in surface_constants()
    with pytest.raises(KeyError):
        carried(payload, "invented_snapshot_key", None)
    with pytest.raises(KeyError):
        carried(payload, "page_titles", "invented_page")


def test_the_upgrade_wording_is_the_wizards_own(monkeypatch):
    """The upgrade page says something the wizard does not."""
    old = run_old([(BUILD, True)], monkeypatch)[1]["calls"]
    titles = [call for call in old if call[0] == surface.PAGE_SET_TITLE]
    subtitles = [call for call in old if call[0] == surface.PAGE_SET_SUB_TITLE]
    assert titles[0] == [surface.PAGE_SET_TITLE, "welcome", surface.UPGRADE_TITLE]
    assert subtitles[0][2] == surface.UPGRADE_SUBTITLE
    assert surface.UPGRADE_PAGE_TITLES["welcome"] == surface.UPGRADE_TITLE
    assert surface.UPGRADE_PAGE_SUBTITLES["welcome"] == surface.UPGRADE_SUBTITLE
    assert surface.UPGRADE_TITLE != surface.FRESH_TITLE
    assert surface.UPGRADE_SUBTITLE != surface.FRESH_SUBTITLE
    assert surface.UPGRADE_CHECK_TAGS == (
        surface.FRESH_START,
        surface.SHOW_KEY,
        surface.SKIP_CREDS,
    )
    assert surface.UPGRADE_WELCOME_ORDER == (
        surface.USERNAME_LABEL,
        surface.USERNAME,
        surface.FRESH_START,
        surface.WELCOME_SPACING,
        surface.SKIP_BUTTON,
    )
    assert surface.UPGRADE_PAGE_ORDERS["welcome"] == surface.UPGRADE_WELCOME_ORDER
    added = [
        call
        for call in old
        if call[0] == surface.LAYOUT_ADD_WIDGET and call[1] == "welcome"
    ]
    assert [call[2] for call in added] == [
        surface.USERNAME_LABEL,
        surface.USERNAME,
        surface.FRESH_START,
        surface.SKIP_BUTTON,
    ]
    fresh = run_old([(BUILD, False)], monkeypatch)[1]["calls"]
    fresh_added = [
        call
        for call in fresh
        if call[0] == surface.LAYOUT_ADD_WIDGET and call[1] == "welcome"
    ]
    assert surface.FRESH_START not in [call[2] for call in fresh_added]


def test_the_bridge_reads_every_step_name():
    """A step the surface can take is unreachable through the bridge."""
    assert set(surface.STEP_NAMES) == {
        "username",
        "api_key",
        "api_secret",
        "passphrase",
        "show_key",
        "skip_creds",
        "fresh_start",
        "exchange_index",
        "page_id",
        "skip",
        "test",
    }
    assert len(surface.STEP_NAMES) == 11
    driven = surface.build_view_model(
        True,
        {name: None for name in surface.STEP_NAMES},
    )
    assert driven["username_text"] == surface.USERNAME_DEFAULT
    every = surface.view_model(
        {
            "is_upgrade": True,
            "username": "Ann",
            "api_key": INVENTED_KEY,
            "api_secret": INVENTED_SECRET,
            "passphrase": INVENTED_PASSPHRASE,
            "show_key": True,
            "skip_creds": False,
            "fresh_start": True,
            "exchange_index": 11,
            "page_id": 2,
            "skip": True,
            "test": {"success": True, "message": "Connected."},
        }
    )
    assert every["username_text"] == "Ann"
    assert every["fresh_start_checked"] is True
    assert every["exchange_id"] == "kucoin"
    assert every["passphrase_visible"] is True
    assert every["feedback_text"] == "Connected."
    assert every["skipped"] is True
    assert every["results"]["api_key"] == INVENTED_KEY


# ---------------------------------------------------------------------
# The pictures
# ---------------------------------------------------------------------

PICTURE_SPECS = {
    "first_run": (False, {}),
    "upgrade": (True, {}),
    "named": (False, {"username": "Ann"}),
    "empty_name": (False, {"username": ""}),
    "unicode_name": (False, {"username": "Δ→⚡ Ann"}),
    "long_name": (False, {"username": "x" * 200}),
    "markup_name": (False, {"username": "<b>bold</b> & co"}),
    "apostrophe_name": (False, {"username": "O'Brien"}),
    "passphrase_venue": (False, {"exchange_index": 11, "page_id": 2}),
    "plain_venue": (False, {"exchange_index": 0, "page_id": 2}),
    "credentials_shown": (
        False,
        {
            "api_key": INVENTED_KEY,
            "api_secret": INVENTED_SECRET,
            "passphrase": INVENTED_PASSPHRASE,
            "show_key": True,
        },
    ),
    "test_succeeded": (
        False,
        {
            "api_key": INVENTED_KEY,
            "api_secret": INVENTED_SECRET,
            "test": {"success": True, "message": "Connected to Binance."},
        },
    ),
    "test_refused": (
        False,
        {
            "api_key": INVENTED_KEY,
            "api_secret": INVENTED_SECRET,
            "test": {"success": False, "message": "Invalid API key."},
        },
    ),
    "test_without_credentials": (False, {"test": {"success": True, "message": "x"}}),
}


def model_payload(spec):
    """The surface payload for one picture case, stamped."""
    is_upgrade, steps = PICTURE_SPECS[spec]
    return sealed(surface.build_view_model(is_upgrade, dict(steps)))


def drive_shipped(wizard, steps, monkeypatch):
    """Run the same steps over the shipped wizard, in the surface's order."""
    if steps.get("username") is not None:
        wizard._username.setText(steps["username"])
    if steps.get("api_key") is not None:
        wizard._api_key.setText(steps["api_key"])
    if steps.get("api_secret") is not None:
        wizard._api_secret.setPlainText(steps["api_secret"])
    if steps.get("passphrase") is not None:
        wizard._passphrase.setText(steps["passphrase"])
    if steps.get("fresh_start") is not None and wizard._fresh_start is not None:
        wizard._fresh_start.setChecked(steps["fresh_start"])
    if steps.get("skip_creds") is not None:
        wizard._skip_creds.setChecked(steps["skip_creds"])
    if steps.get("show_key") is not None:
        wizard._show_key.setChecked(steps["show_key"])
    if steps.get("exchange_index") is not None:
        wizard._exchange_combo.setCurrentIndex(steps["exchange_index"])
    if steps.get("page_id") is not None:
        wizard._on_page_changed(steps["page_id"])
    if steps.get("test") is not None:
        from src.exchange import api_validator

        answer = steps["test"]

        def validate(_exchange_id, _api_key, _api_secret, _passphrase):
            return Answer(answer["success"], answer["message"])

        monkeypatch.setattr(api_validator, "validate_credentials", validate)
        wizard._test_api()
    if steps.get("skip"):
        wizard._on_skip()
    return wizard


def wizard_painted_by_the_wizard(spec, monkeypatch):
    """The shipped wizard, driven by one picture case."""
    app()
    is_upgrade, steps = PICTURE_SPECS[spec]
    wizard = shipped.InitWizard(is_upgrade)
    ALIVE.append(wizard)
    return drive_shipped(wizard, dict(steps), monkeypatch)


def wizard_painted_by_the_model(payload):
    """A bare wizard filled only from the payload, never from the wizard."""
    unaltered(payload)
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QLabel,
        QLineEdit,
        QPushButton,
        QTextEdit,
        QVBoxLayout,
        QWizard,
        QWizardPage,
    )

    wizard = QWizard()
    wizard.setWindowTitle(payload["window_title"])
    wizard.setMinimumSize(*payload["minimum_size_px"])
    wizard.setWizardStyle(QWizard.WizardStyle(payload["wizard_style_value"]))
    labels = payload["label_texts"]
    holes = payload["placeholders"]
    tips = payload["tool_tips"]
    echo = payload["echo_values"]

    def make_label(tag):
        label = QLabel(labels[tag])
        if tag == surface.PASSPHRASE_HINT:
            label.setWordWrap(payload["passphrase_hint_word_wrap"])
            label.setProperty(*payload["muted_property"])
        return label

    def make_child(tag):
        if tag in labels and tag != surface.FEEDBACK:
            return make_label(tag)
        if tag == surface.FEEDBACK:
            found = QLabel(payload["feedback_text"])
            found.setWordWrap(payload["feedback_word_wrap"])
            found.setStyleSheet(payload["feedback_style"])
            return found
        if tag == surface.USERNAME:
            found = QLineEdit()
            found.setPlaceholderText(holes[tag])
            found.setText(payload["username_text"])
            return found
        if tag == surface.API_KEY:
            found = QLineEdit()
            found.setPlaceholderText(holes[tag])
            found.setEchoMode(QLineEdit.EchoMode(echo[payload["api_key_echo"]]))
            found.setText(payload["api_key_text"])
            return found
        if tag == surface.PASSPHRASE:
            found = QLineEdit()
            found.setPlaceholderText(holes[tag])
            found.setEchoMode(QLineEdit.EchoMode(echo[payload["passphrase_echo"]]))
            found.setText(payload["passphrase_text"])
            return found
        if tag == surface.API_SECRET:
            found = QTextEdit()
            found.setMaximumHeight(payload["api_secret_max_height_px"])
            found.setPlaceholderText(holes[tag])
            found.setToolTip(tips[tag])
            found.setPlainText(payload["api_secret_text"])
            found.setStyleSheet(payload["api_secret_style"])
            return found
        if tag == surface.EXCHANGE_COMBO:
            found = QComboBox()
            for label, data in payload["exchange_items"]:
                found.addItem(label, data)
            found.setCurrentIndex(payload["exchange_index"])
            return found
        if tag in payload["check_texts"]:
            found = QCheckBox(payload["check_texts"][tag])
            if tag in tips:
                found.setToolTip(tips[tag])
            if tag == surface.SHOW_KEY:
                found.setChecked(payload["show_key_checked"])
            elif tag == surface.SKIP_CREDS:
                found.setChecked(payload["skip_creds_checked"])
            else:
                found.setChecked(bool(payload["fresh_start_checked"]))
            return found
        spec = payload["buttons"][tag]
        found = QPushButton(spec["text"])
        found.setToolTip(spec["tool_tip"])
        found.setStyleSheet(spec["style_sheet"])
        found.setEnabled(spec["enabled"])
        return found

    placed: dict = {}
    for name in payload["pages"]:
        page = QWizardPage()
        page.setTitle(payload["page_titles"][name])
        page.setSubTitle(payload["page_subtitles"][name])
        if name == payload["final_page"]:
            page.setFinalPage(True)
        layout = QVBoxLayout(page)
        for tag in payload["page_orders"][name]:
            if tag == surface.WELCOME_SPACING:
                layout.addSpacing(payload["welcome_spacing_px"])
                continue
            child = make_child(tag)
            placed[tag] = child
            layout.addWidget(child)
        wizard.addPage(page)
    if payload["current_page_id"] == payload["passphrase_page_id"]:
        placed[surface.PASSPHRASE_LABEL].setVisible(payload["passphrase_label_visible"])
        placed[surface.PASSPHRASE].setVisible(payload["passphrase_visible"])
        placed[surface.PASSPHRASE_HINT].setVisible(payload["passphrase_hint_visible"])
    ALIVE.append(wizard)
    return wizard


def font_note():
    """Which font answer this host gave, carried into a failure message."""
    return "real fonts" if has_real_fonts() else "no fonts"


@pytest.mark.parametrize("spec", sorted(PICTURE_SPECS))
@pytest.mark.parametrize("page_id", [0, 1, 2])
def test_the_two_sides_paint_one_page(spec, page_id, monkeypatch):
    """The surface painted a value, a colour or a position the wizard did not."""
    app()
    old = wizard_painted_by_the_wizard(spec, monkeypatch)
    new = wizard_painted_by_the_model(model_payload(spec))
    assert_pictures_match(
        old_side=render_offscreen(old.page(page_id), PAGE_SIZE),
        new_side=render_offscreen(new.page(page_id), PAGE_SIZE),
        note="%s, page %d, %s" % (spec, page_id, font_note()),
    )


def test_the_picture_check_reports_two_different_real_inputs(monkeypatch):
    """The picture check passes whatever the second side paints.

    Two real inputs, one driven into each side. A first-run page one
    carries no start-fresh switch and a different title; an upgrade page
    one carries both, so a pass proves the comparison reports it.
    """
    app()
    assert PICTURE_SPECS["first_run"] != PICTURE_SPECS["upgrade"]
    assert_pictures_differ(
        old_side=render_offscreen(
            wizard_painted_by_the_wizard("first_run", monkeypatch).page(0), PAGE_SIZE
        ),
        new_side=render_offscreen(
            wizard_painted_by_the_model(model_payload("upgrade")).page(0), PAGE_SIZE
        ),
        note="a first run from the wizard against an upgrade from the surface, %s"
        % font_note(),
    )


def test_the_picture_check_reports_two_different_status_lines(monkeypatch):
    """The status line's picture check passes whatever the surface paints."""
    app()
    assert_pictures_differ(
        old_side=render_offscreen(
            wizard_painted_by_the_wizard("test_succeeded", monkeypatch).page(2),
            PAGE_SIZE,
        ),
        new_side=render_offscreen(
            wizard_painted_by_the_model(model_payload("test_refused")).page(2),
            PAGE_SIZE,
        ),
        note="a green status from the wizard against a red one from the surface, %s"
        % font_note(),
    )


@pytest.mark.parametrize("page_id", [0, 1, 2])
def test_the_painted_page_shows_more_than_one_colour(page_id):
    """The two sides matched because the page painted one flat colour."""
    app()
    from PySide6.QtGui import QColor

    image = render_offscreen(
        wizard_painted_by_the_model(model_payload("credentials_shown")).page(page_id),
        PAGE_SIZE,
    )
    seen = set()
    for x in range(0, image.width(), 3):
        for y in range(0, image.height(), 3):
            seen.add(QColor(image.pixelColor(x, y)).name())
    assert len(seen) > 2, "page %d painted %d colours" % (page_id, len(seen))


def test_the_two_sides_declare_and_paint_the_same_skin(monkeypatch):
    """The two sides declared one colour and painted another."""
    app()
    old = wizard_painted_by_the_wizard("test_refused", monkeypatch)
    payload = model_payload("test_refused")
    assert (
        surface.SKIN["skip_button"] in payload["buttons"]["skip_button"]["style_sheet"]
    )
    assert surface.SKIN["feedback_error"] in payload["feedback_style"]
    new = wizard_painted_by_the_model(payload)
    for page_id in (0, 1, 2):
        assert_pictures_match(
            old_side=render_offscreen(old.page(page_id), PAGE_SIZE),
            new_side=render_offscreen(new.page(page_id), PAGE_SIZE),
            note="skin, page %d, %s" % (page_id, font_note()),
        )


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on."""
    app()
    from PySide6.QtWidgets import QLabel

    narrow = QLabel("iiii")
    wide = QLabel("WWWW")
    if has_real_fonts():
        assert (
            narrow.sizeHint().width() != wide.sizeHint().width()
        ), "the host reports fonts and every glyph still has one width"
    else:
        assert (
            narrow.sizeHint().width() == wide.sizeHint().width()
        ), "the host reports no fonts and the glyphs still have their own widths"


def test_two_names_of_equal_length_paint_different_widths():
    """With fonts installed the glyphs stopped deciding the width.

    The shared marker is asked after the application exists, never at
    import time: the font database cannot be read before then.
    """
    app()
    if not has_real_fonts():
        pytest.skip("a measured string width needs a font database")
    from PySide6.QtWidgets import QLabel

    narrow = QLabel("iiiiiiii")
    wide = QLabel("WWWWWWWW")
    assert len(narrow.text()) == len(wide.text())
    assert narrow.sizeHint().width() < wide.sizeHint().width()


# ---------------------------------------------------------------------
# What no picture can report, each read off both sides instead
# ---------------------------------------------------------------------


def test_the_window_title_a_picture_cannot_see_is_compared_as_text(monkeypatch):
    """The window title is painted by the desktop, not into the page."""
    old = run_old([(BUILD, False)], monkeypatch)[1]["calls"]
    titled = [call for call in old if call[0] == surface.WIZARD_SET_WINDOW_TITLE]
    assert titled == [[surface.WIZARD_SET_WINDOW_TITLE, "Acervator - Setup"]]
    assert surface.WINDOW_TITLE == "Acervator - Setup"
    assert model_payload("first_run")["window_title"] == surface.WINDOW_TITLE


def test_the_minimum_size_a_picture_cannot_see_is_compared_as_numbers(monkeypatch):
    """The render size overwrites the window size before the grab."""
    old = run_old([(BUILD, False)], monkeypatch)[1]["calls"]
    sized = [call for call in old if call[0] == surface.WIZARD_SET_MINIMUM_SIZE]
    assert sized == [[surface.WIZARD_SET_MINIMUM_SIZE, [600, 450]]]
    assert list(surface.MINIMUM_SIZE_PX) == [600, 450]
    assert model_payload("first_run")["minimum_size_px"] == [600, 450]


def test_the_wizard_style_a_picture_may_not_show_is_compared_as_a_number(monkeypatch):
    """The wizard's frame style paints no mark inside a page."""
    old = run_old([(BUILD, False)], monkeypatch)[1]["calls"]
    styled = [call for call in old if call[0] == surface.WIZARD_SET_WIZARD_STYLE]
    assert styled == [[surface.WIZARD_SET_WIZARD_STYLE, 1]]
    assert surface.WIZARD_STYLE_VALUE == 1
    assert surface.WIZARD_STYLE == "ModernStyle"


def test_the_tool_tips_a_picture_cannot_see_are_compared_as_text(monkeypatch):
    """A tool tip appears only while a pointer rests on the control."""
    old = run_old([(BUILD, True)], monkeypatch)[1]["calls"]
    tipped = {
        call[1]: call[2]
        for call in old
        if call[0]
        in (
            surface.CHECK_SET_TOOL_TIP,
            surface.BUTTON_SET_TOOL_TIP,
            surface.TEXT_SET_TOOL_TIP,
        )
    }
    assert tipped == dict(surface.TOOL_TIPS)
    assert len(surface.TOOL_TIPS) == 3
    assert "you're" in surface.TOOL_TIPS[surface.FRESH_START]
    assert "\n" in surface.TOOL_TIPS[surface.API_SECRET]
    assert "\\n" in surface.TOOL_TIPS[surface.API_SECRET]


def test_the_placeholders_a_picture_may_not_show_are_compared_as_text(monkeypatch):
    """A placeholder shows only while the field is empty and unfocused."""
    old = run_old([(BUILD, False)], monkeypatch)[1]["calls"]
    holes = {
        call[1]: call[2]
        for call in old
        if call[0] in (surface.LINE_SET_PLACEHOLDER, surface.TEXT_SET_PLACEHOLDER)
    }
    assert holes == dict(surface.PLACEHOLDERS)
    assert len(surface.PLACEHOLDERS) == 4
    assert surface.PLACEHOLDERS[surface.API_SECRET].endswith("(PEM with \\n is OK)")


def test_the_hidden_key_a_picture_shows_as_dots_is_compared_as_a_mode(monkeypatch):
    """Which characters a hidden field paints is the platform's choice."""
    script = [
        (BUILD, False),
        (SET, surface.API_KEY, INVENTED_KEY),
        (CHECK, surface.SHOW_KEY, True),
        (CHECK, surface.SHOW_KEY, False),
    ]
    old = run_old(script, monkeypatch)
    assert old[1]["api_key_echo"] == 2
    assert old[3]["api_key_echo"] == 0
    assert old[4]["api_key_echo"] == 2
    assert run_new(script) == old
    assert surface.ECHO_VALUES == dict(zip(surface.ECHO_MODES, (0, 2), strict=True))
    assert surface.ECHO_MODES == ("Normal", "Password")


def test_the_secret_style_a_picture_may_not_show_is_compared_as_text(monkeypatch):
    """A transparent text colour paints the same page as an empty box."""
    script = [
        (BUILD, False),
        (SET, surface.API_SECRET, INVENTED_SECRET),
        (CHECK, surface.SHOW_KEY, True),
        (CHECK, surface.SHOW_KEY, False),
    ]
    old = run_old(script, monkeypatch)
    assert old[1]["api_secret_style"] == ""
    assert old[3]["api_secret_style"] == surface.SECRET_SHOWN_STYLE == ""
    assert old[4]["api_secret_style"] == surface.SECRET_HIDDEN_STYLE
    hidden = "color: transparent; background-selection-color: transparent;"
    assert surface.SECRET_HIDDEN_STYLE == hidden
    assert surface.STYLES["hidden_field"] == hidden
    assert run_new(script) == old


def test_the_muted_property_a_picture_may_not_show_is_compared_as_a_value(monkeypatch):
    """A style hook with no rule behind it paints nothing."""
    old = run_old([(BUILD, False)], monkeypatch)[1]["calls"]
    marked = [call for call in old if call[0] == surface.LABEL_SET_PROPERTY]
    assert marked == [
        [surface.LABEL_SET_PROPERTY, surface.PASSPHRASE_HINT, "muted", True]
    ]
    assert surface.MUTED_PROPERTY == "muted"
    assert surface.MUTED_VALUE is True


def test_the_word_wrap_a_picture_may_not_show_is_compared_as_a_flag(monkeypatch):
    """A wrap changes nothing until a line is longer than the box."""
    old = run_old([(BUILD, False)], monkeypatch)[1]["calls"]
    wrapped = {
        call[1]: call[2] for call in old if call[0] == surface.LABEL_SET_WORD_WRAP
    }
    assert wrapped == {
        surface.PASSPHRASE_HINT: True,
        surface.FEEDBACK: True,
    }
    assert surface.PASSPHRASE_HINT_WORD_WRAP is True
    assert surface.FEEDBACK_WORD_WRAP is True


def test_the_final_page_flag_a_picture_cannot_see_is_compared_as_a_flag(monkeypatch):
    """Which page ends the wizard paints no mark inside the page."""
    old = run_old([(BUILD, False)], monkeypatch)[1]["calls"]
    finals = [call for call in old if call[0] == surface.PAGE_SET_FINAL]
    assert finals == [[surface.PAGE_SET_FINAL, surface.CREDENTIALS, True]]
    assert surface.FINAL_PAGE == surface.CREDENTIALS


def test_the_button_state_a_picture_may_not_show_is_compared_as_a_flag(monkeypatch):
    """Whether the test button can be pressed is compared as a flag."""
    script = [
        (BUILD, False),
        (SET, surface.API_KEY, INVENTED_KEY),
        (SET, surface.API_SECRET, INVENTED_SECRET),
        (TEST, "ok"),
    ]
    old = run_old(script, monkeypatch)
    turned = [
        call for call in old[-1]["calls"] if call[0] == surface.BUTTON_SET_ENABLED
    ]
    assert turned == [
        [surface.BUTTON_SET_ENABLED, surface.TEST_BUTTON, False],
        [surface.BUTTON_SET_ENABLED, surface.TEST_BUTTON, True],
    ]
    assert old[-1]["test_button_enabled"] is True
    assert run_new(script) == old
    assert surface.TEST_BUTTON_ENABLED is True


def test_the_answer_a_picture_cannot_see_is_compared_as_a_value(monkeypatch):
    """The six values the caller collects are painted nowhere."""
    script = SCRIPTS["everything_in_turn"]
    old = run_old(script, monkeypatch)
    results = [step["answer"] for step in old if isinstance(step["answer"], dict)]
    assert len(results) == 2
    assert set(results[0]) == set(surface.RESULT_FIELDS)
    assert results[0]["username"] == "Ann"
    assert results[0]["exchange_id"] == "kucoin"
    assert results[0]["api_key"] == INVENTED_KEY
    assert results[0]["fresh_start"] is True
    assert run_new(script) == old


def test_the_username_refusal_a_picture_cannot_see_is_compared_as_text(monkeypatch):
    """The refusal to leave page one opens a box no page render holds."""
    script = [(BUILD, False), (SET, surface.USERNAME, "  "), (PAGE, 0), (VALIDATE,)]
    old = run_old(script, monkeypatch)
    assert old[-1]["answer"] is False
    assert old[-1]["warning"] == ["Username Required", "Please enter a username."]
    assert surface.USERNAME_REQUIRED_TITLE == "Username Required"
    assert surface.USERNAME_REQUIRED_TEXT == "Please enter a username."
    assert run_new(script) == old
    allowed = [(BUILD, False), (SET, surface.USERNAME, "Ann"), (PAGE, 0), (VALIDATE,)]
    assert run_old(allowed, monkeypatch)[-1]["answer"] is True
    assert run_new(allowed)[-1]["answer"] is True


def test_the_current_page_the_check_reads_is_the_scripted_one(monkeypatch):
    """The page-one check answers the same whatever page the wizard is on."""
    on_page_one = [(BUILD, False), (SET, surface.USERNAME, ""), (PAGE, 0), (VALIDATE,)]
    on_page_two = [(BUILD, False), (SET, surface.USERNAME, ""), (PAGE, 1), (VALIDATE,)]
    assert run_old(on_page_one, monkeypatch)[-1]["answer"] is False
    assert run_old(on_page_two, monkeypatch)[-1]["answer"] is True
    assert run_new(on_page_one)[-1]["answer"] is False
    assert run_new(on_page_two)[-1]["answer"] is True
    assert surface.VALIDATED_PAGE_ID == 0
    assert surface.NO_PAGE_ID == -1


def test_the_venue_data_a_picture_cannot_see_is_compared_as_text(monkeypatch):
    """The venue id behind each list entry is painted nowhere."""
    old = run_old([(BUILD, False)], monkeypatch)[1]["calls"]
    added = [call for call in old if call[0] == surface.COMBO_ADD_ITEM]
    assert [[call[2], call[3]] for call in added] == [
        list(item) for item in surface.EXCHANGE_ITEMS
    ]
    assert len(added) == 15
    assert added[2][2] == "Bitget (requires passphrase)"
    assert added[2][3] == "bitget"


BLIND_TO_THE_PICTURE = {
    "window_title": "test_the_window_title_a_picture_cannot_see_is_compared_as_text",
    "minimum_size": (
        "test_the_minimum_size_a_picture_cannot_see_is_compared_as_numbers"
    ),
    "wizard_style": (
        "test_the_wizard_style_a_picture_may_not_show_is_compared_as_a_number"
    ),
    "tool_tip": "test_the_tool_tips_a_picture_cannot_see_are_compared_as_text",
    "placeholder": (
        "test_the_placeholders_a_picture_may_not_show_are_compared_as_text"
    ),
    "echo_mode": ("test_the_hidden_key_a_picture_shows_as_dots_is_compared_as_a_mode"),
    "hidden_field_style": (
        "test_the_secret_style_a_picture_may_not_show_is_compared_as_text"
    ),
    "muted_property": (
        "test_the_muted_property_a_picture_may_not_show_is_compared_as_a_value"
    ),
    "word_wrap": "test_the_word_wrap_a_picture_may_not_show_is_compared_as_a_flag",
    "final_page": (
        "test_the_final_page_flag_a_picture_cannot_see_is_compared_as_a_flag"
    ),
    "button_enabled": (
        "test_the_button_state_a_picture_may_not_show_is_compared_as_a_flag"
    ),
    "results": "test_the_answer_a_picture_cannot_see_is_compared_as_a_value",
    "username_warning": (
        "test_the_username_refusal_a_picture_cannot_see_is_compared_as_text"
    ),
    "current_page": "test_the_current_page_the_check_reads_is_the_scripted_one",
    "venue_data": "test_the_venue_data_a_picture_cannot_see_is_compared_as_text",
    "skipped": "test_the_skip_button_answer_is_compared_as_a_flag",
    "timer_delay": (
        "test_the_wizard_starts_no_timer_and_the_counter_reports_one_elsewhere"
    ),
    "bus_topic": (
        "test_the_wizard_reaches_no_bus_topic_and_the_counter_reports_one_elsewhere"
    ),
    "line_text": "test_old_and_new_traces_are_identical",
}


def test_the_skip_button_answer_is_compared_as_a_flag(monkeypatch):
    """Whether the setup was skipped is painted nowhere."""
    script = [(BUILD, False), (SKIP,)]
    old = run_old(script, monkeypatch)
    assert old[1]["skipped"] is False
    assert old[2]["skipped"] is True
    assert old[2]["calls"][-1] == [surface.WIZARD_REJECT]
    assert run_new(script) == old
    assert surface.SKIPPED_DEFAULT is False


def test_everything_a_picture_cannot_report_is_named_and_covered(monkeypatch):
    """A value no render can report was left to the render to report."""
    app()
    assert len(BLIND_TO_THE_PICTURE) == 19
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by
    old = wizard_painted_by_the_wizard("first_run", monkeypatch)
    payload = model_payload("first_run")
    assert payload["window_title"] == old.windowTitle()
    assert payload["minimum_size_px"] == [old.minimumWidth(), old.minimumHeight()]
    assert payload["wizard_style_value"] == old.wizardStyle().value
    assert_pictures_match(
        old_side=render_offscreen(old.page(0), PAGE_SIZE),
        new_side=render_offscreen(
            wizard_painted_by_the_model(payload).page(0), PAGE_SIZE
        ),
        note=font_note(),
    )


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    payload = surface.view_model(
        {
            "is_upgrade": True,
            "username": "Ann",
            "api_key": INVENTED_KEY,
            "api_secret": INVENTED_SECRET,
            "exchange_index": 11,
            "page_id": 2,
            "test": {"success": True, "message": "Connected."},
        }
    )
    back = json.loads(json.dumps(payload, ensure_ascii=True))
    assert back["window_title"] == "Acervator - Setup"
    assert back["page_titles"]["welcome"] == "Acervator - New Version"
    assert back["exchange_labels"][11] == "Kucoin (requires passphrase)"
    assert back["feedback_style"] == "color: #00ff88;"
    assert back["results"]["exchange_id"] == "kucoin"
    assert back["timers"] == {}
    assert back["timer_delays_ms"] == []
    assert back["bus_topics"] == []
    assert len(back["calls"]) == 100


def test_the_bridge_registers_the_init_wizard_method():
    """The renderer cannot reach the setup wizard through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == METHOD_NAME
    assert registry[surface.METHOD] is surface.view_model
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 21, "method": surface.METHOD, "params": {}}), registry
    )
    assert answer["ok"] is True
    assert answer["result"]["window_title"] == "Acervator - Setup"
    assert len(answer["result"]["exchange_ids"]) == 15


def test_the_bridge_registration_is_two_lines_and_no_more():
    """The bridge grew more than the one registration this unit adds."""
    text = BRIDGE_PATH.read_text(encoding="utf-8")
    assert text.count("init_wizard_surface") == 3
    assert "init_wizard_surface.METHOD: init_wizard_surface.view_model" in text
    assert "        init_wizard_surface,\n" in text


def test_the_bridge_import_list_stays_alphabetical():
    """A surface was added out of order, so the next one lands anywhere."""
    text = BRIDGE_PATH.read_text(encoding="utf-8")
    block = text.split("from src.gui.main_tabs import (")[1].split(")")[0]
    names = [line.strip().rstrip(",") for line in block.strip().splitlines()]
    assert names == sorted(names), names
    assert "init_wizard_surface" in names
    assert names.index("header_strip_surface") < names.index("init_wizard_surface")
    assert names.index("init_wizard_surface") < names.index("instance_consent_surface")


def test_the_bridge_answers_with_no_parameters_at_all():
    """A request carrying no values ended the session."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 22, "method": surface.METHOD}), registry
    )
    assert answer["ok"] is True
    result = answer["result"]
    assert result["username_text"] == "User"
    assert result["exchange_id"] == "binance"
    assert result["feedback_text"] == ""
    assert result["skipped"] is False


def test_the_bridge_ignores_a_parameter_it_does_not_know():
    """A parameter the surface does not read ended the request."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 23,
                "method": surface.METHOD,
                "params": {"invented": [1, 2], "group": "x"},
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    assert "invented" not in answer["result"]
    assert answer["result"]["window_title"] == "Acervator - Setup"


def test_the_bridge_reports_a_request_the_surface_refuses():
    """A bad value ended the session instead of answering."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 24, "method": surface.METHOD, "params": {"username": 42}}),
        registry,
    )
    assert answer["ok"] is False
    assert answer["error"]["type"] == "TypeError"
    overflowed = desktop_bridge.handle_line(
        json.dumps(
            {"id": 25, "method": surface.METHOD, "params": {"exchange_index": 1e400}}
        ),
        registry,
    )
    assert overflowed["ok"] is False
    assert overflowed["error"]["type"] == "OverflowError"


def test_the_answer_is_the_same_on_every_call_with_the_same_request():
    """The answer changed between two calls with the same values."""
    first = surface.view_model({"username": "Ann"})
    second = surface.view_model({})
    third = surface.view_model({"username": "Ann"})
    assert first == third
    assert digest(first) == digest(third)
    assert first != second


# ---------------------------------------------------------------------
# The surface without Qt, proved in a process of its own
# ---------------------------------------------------------------------

BLOCK_QT = (
    "import sys\n"
    "class Refuse:\n"
    "    def find_module(self, name, path=None):\n"
    "        return self\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name.split('.')[0] in ('PySide6', 'shiboken6'):\n"
    "            raise ImportError('Qt is blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, Refuse())\n"
)

BRIDGE_PROBE = BLOCK_QT + (
    "import json\n"
    "from src.core import desktop_bridge\n"
    "frame = desktop_bridge.handle_line(json.dumps({'id': 1,\n"
    "    'method': 'init_wizard.state',\n"
    "    'params': {'username': 'Ann', 'exchange_index': 11, 'page_id': 2}}),\n"
    "    desktop_bridge.build_registry())\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules, 'frame': frame}))\n"
)

SURFACE_PROBE = BLOCK_QT + (
    "import json\n"
    "from src.gui.main_tabs import init_wizard_surface as s\n"
    "model = s.InitWizardModel(True)\n"
    "model.set_username('Ann')\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'window_title': s.WINDOW_TITLE,\n"
    "    'exchange_ids': list(s.EXCHANGE_IDS),\n"
    "    'exchange_labels': list(s.EXCHANGE_LABELS),\n"
    "    'label_texts': dict(s.LABEL_TEXTS),\n"
    "    'skin': dict(s.SKIN),\n"
    "    'calls': len(model.calls),\n"
    "    'results': model.get_results()}))\n"
)


def run_script(source):
    """Run one probe in a fresh process and return what it printed."""
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode("utf-8").splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the setup wizard pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["username_text"] == "Ann"
    assert result["exchange_id"] == "kucoin"
    assert result["passphrase_visible"] is True


def test_the_surface_carries_every_value_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(SURFACE_PROBE)
    assert answered["qt"] is False
    assert answered["window_title"] == "Acervator - Setup"
    assert answered["exchange_ids"] == list(surface.EXCHANGE_IDS)
    assert answered["exchange_labels"] == list(surface.EXCHANGE_LABELS)
    assert answered["label_texts"] == dict(surface.LABEL_TEXTS)
    assert answered["skin"] == dict(surface.SKIN)
    assert answered["calls"] == 85
    assert answered["results"]["username"] == "Ann"


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script(
        "import sys\nimport PySide6.QtCore\n" + BRIDGE_PROBE.replace(BLOCK_QT, "")
    )
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_qt_block_stops_the_shipped_wizard():
    """The Qt block let the shipped wizard through, so it proves nothing."""
    answered = run_script(
        BLOCK_QT
        + (
            "import json\n"
            "from src.gui import init_wizard as w\n"
            "print(json.dumps({'has_qt': w._HAS_QT,\n"
            "    'has_wizard': hasattr(w, 'InitWizard')}))\n"
        )
    )
    assert answered["has_qt"] is False
    assert answered["has_wizard"] is False
